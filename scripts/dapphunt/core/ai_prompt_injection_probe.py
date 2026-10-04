#!/usr/bin/env python3
"""
ai_prompt_injection_probe.py — Map a dApp's LLM/AI attack surface (recon/scan only).

SCAN (static): fetch the dApp HTML + top JS bundles, detect (a) the presence of an
LLM/AI feature (chat assistant, "explain transaction", risk narrative, agentic
wallet), (b) the LLM provider/endpoint, (c) which attacker-controllable sources feed
it (on-chain token name/symbol/tokenURI, wallet metadata, ENS, order/dust memos),
and (d) agentic auto-execute signals (LLM output → buildTx/send without a confirm
gate). Emits ai_prompt_injection_probe.json. Mirrors the grep+compose style of
wallet_metadata_xss_check.py.

PAYLOAD CATALOG WITHHELD (public release): this open edition ships the scan/recon
half only. The concrete prompt-injection payload catalog and the filter-bypass
encoders (invisible-Unicode tag-block / zero-width interleave) that defeat a target's
input moderation are deliberately NOT included here — they are detection-evasion
tooling against a third party's safety filter and are out of scope for a public,
general-audience release. `build_payloads()` / `payload_catalog()` are kept as stubs
so the differential harness and its tests still import and run; wire in your own
authorized, scoped payloads if your engagement covers AI-surface testing.

WHITE-HAT SCOPE (non-negotiable): AI-surface testing is ONLY ever run against the
AI/LLM features of an in-scope TARGET dApp, with a BENIGN canary and no live exfil.
NEVER against bug-bounty triage AIs, platform moderation LLMs, or any assistant
outside the engagement. See threat_models/ai_agent_prompt_injection.yaml.

Usage:
    python3 ai_prompt_injection_probe.py --target https://app.example.com/ \
        --output sessions/$DOMAIN/ai_prompt_injection_probe.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


# ── Injection payload catalog — WITHHELD in the public release ──
# The concrete sendable payloads and the invisible-Unicode / zero-width filter-bypass
# encoders have been removed from this open edition (they are detection-evasion tooling
# against a third party's moderation). The stubs below keep the public contract intact
# so the differential harness and selftests still import and run; they return nothing.
_PAYLOAD_CATALOG: List[tuple] = []


def build_payloads(canary: str = "CANARY-OK", collector: Optional[str] = None) -> List[dict]:
    """Stub — the payload catalog is withheld from the public release (see module docstring).

    Returns an empty list. In an authorized engagement that covers AI-surface testing,
    supply your own scoped, benign-canary payloads here.
    """
    return []


# ── Static bundle scan ──
# Signals that an LLM/AI feature exists and which provider/endpoint.
_AI_FEATURE_SIGNALS = [
    (r"api\.anthropic\.com|/v1/messages\b", "anthropic", "Anthropic API call"),
    (r"api\.openai\.com|/v1/chat/completions\b", "openai", "OpenAI API call"),
    (r"\bclaude-[a-z0-9.\-]+\b", "anthropic", "Claude model id"),
    (r"\bgpt-4[\w.\-]*\b|\bgpt-3\.5\b", "openai", "GPT model id"),
    (r"system_?[Pp]rompt", "any", "system prompt construction"),
    (r"explain ?[Tt]ransaction|explainTx", "any", "tx-explainer feature"),
    (r"ai[ _]?assistant|aiAssistant|chatAssistant", "any", "AI assistant feature"),
    (r"agentic[ _]?[Cc]hat|agentExecute|autoExecute", "any", "agentic execution feature"),
    (r"risk[ _]?[Nn]arrative|riskExplanation", "any", "AI risk narrative"),
    (r"tool_calls|function_call|toolCalls", "any", "LLM tool/function calling"),
]

# Attacker-controllable sources that might feed the LLM.
_UNTRUSTED_SOURCES = [
    (r"\.name\(\)|tokenName|symbol\(\)|tokenSymbol", "on-chain token name/symbol"),
    (r"tokenURI|token_uri|metadata\.image|metadata\.name", "ERC-721 tokenURI/metadata"),
    (r"ensName|\.eth\b|resolveName", "ENS name"),
    (r"peer\.metadata\.(name|description)|proposer\.metadata", "wallet metadata"),
    (r"memo|orderTitle|listingNote|note\b", "order/listing memo"),
    (r"recentTx|history|activityFeed", "tx-history summary (dust-memo carrier)"),
]

# Agentic auto-execute signals: LLM output flowing into tx build/send.
_AGENTIC_SINKS = [
    (r"buildTx|encodeFunctionData|prepareTransaction|sendTransaction", "tx construction/send"),
    (r"signMessage|signTypedData|_signTypedData", "signing call"),
    (r"executeSwap|executeSend|submitOrder", "action execution"),
]


@dataclass
class ProbeReport:
    target: str
    bundles_scanned: List[str] = field(default_factory=list)
    ai_feature_hits: List[dict] = field(default_factory=list)
    untrusted_source_hits: List[dict] = field(default_factory=list)
    agentic_sink_hits: List[dict] = field(default_factory=list)
    provider_guess: Optional[str] = None
    has_ai_feature: bool = False
    agentic_risk: bool = False
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-aiprobe/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _gather_bundles(target: str) -> Dict[str, str]:
    html = _fetch(target)
    if not html:
        return {}
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    srcs = re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)
    resolved: List[str] = []
    for s in srcs:
        if s.startswith("//"):
            resolved.append(f"{parsed.scheme}:{s}")
        elif s.startswith("/"):
            resolved.append(f"{base}{s}")
        elif s.startswith("http"):
            resolved.append(s)
        else:
            resolved.append(f"{base}/{s}")
    bundles: Dict[str, str] = {target: html}
    for url in resolved[:6]:
        text = _fetch(url)
        if text:
            bundles[url] = text
    return bundles


def _find_lines(content: str, pattern: str) -> List[tuple]:
    matches: List[tuple] = []
    rx = re.compile(pattern, re.IGNORECASE)
    for idx, line in enumerate(content.split("\n"), 1):
        if rx.search(line):
            matches.append((idx, line.strip()[:240]))
    return matches


def scan(target: str) -> ProbeReport:
    rep = ProbeReport(target=target)
    bundles = _gather_bundles(target)
    rep.bundles_scanned = list(bundles.keys())

    for url, content in bundles.items():
        for pat, provider, desc in _AI_FEATURE_SIGNALS:
            for ln, txt in _find_lines(content, pat):
                rep.ai_feature_hits.append({"bundle": url, "line": ln, "signal": desc,
                                            "provider": provider, "excerpt": txt})
                if provider in ("anthropic", "openai") and not rep.provider_guess:
                    rep.provider_guess = provider
        for pat, desc in _UNTRUSTED_SOURCES:
            for ln, txt in _find_lines(content, pat):
                rep.untrusted_source_hits.append({"bundle": url, "line": ln, "source": desc, "excerpt": txt})
        for pat, desc in _AGENTIC_SINKS:
            for ln, txt in _find_lines(content, pat):
                rep.agentic_sink_hits.append({"bundle": url, "line": ln, "sink": desc, "excerpt": txt})

    rep.has_ai_feature = bool(rep.ai_feature_hits)
    rep.agentic_risk = bool(rep.ai_feature_hits and rep.agentic_sink_hits)

    if not rep.has_ai_feature:
        rep.notes.append("No LLM/AI feature signal in main bundle. Feature may live in a "
                         "lazy-loaded chunk, a worker, or server-side — check network tab for "
                         "/v1/messages or /v1/chat/completions while using the app.")
    if rep.has_ai_feature and rep.untrusted_source_hits:
        rep.notes.append("AI feature + attacker-controllable sources co-present → review "
                         "whether on-chain/metadata text can reach the model unsanitized.")
    if rep.agentic_risk:
        rep.notes.append("AGENTIC RISK: AI feature co-located with tx-build/sign sinks. Verify "
                         "whether execute requires explicit per-action user confirm. If not → "
                         "agentic auto-execute without confirm (ShapeShift class, up to Critical).")
    return rep


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", help="dApp base URL to scan")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    args = parser.parse_args(argv)

    if not args.target:
        parser.error("--target is required")

    rep = scan(args.target)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(asdict(rep), ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(asdict(rep), ensure_ascii=False, indent=2))
        return 0

    print(f"Target: {rep.target}")
    print(f"Bundles scanned: {len(rep.bundles_scanned)}")
    print(f"AI feature: {rep.has_ai_feature} (provider guess: {rep.provider_guess})")
    print(f"AI feature signals: {len(rep.ai_feature_hits)} | untrusted sources: "
          f"{len(rep.untrusted_source_hits)} | agentic sinks: {len(rep.agentic_sink_hits)}")
    print(f"Agentic auto-execute risk: {rep.agentic_risk}")
    for h in rep.ai_feature_hits[:8]:
        print(f"  [AI] {h['bundle']}:{h['line']} {h['signal']}")
    for note in rep.notes:
        print(f"  note: {note}")
    return 1 if rep.agentic_risk else 0


if __name__ == "__main__":
    sys.exit(main())
