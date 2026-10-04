#!/usr/bin/env python3
"""
display_vs_reality_grep.py — Find UI assertions that may diverge from on-chain reality.

Display vs reality is one of the most under-explored dApp hypothesis sources:
- UI shows "Expires in 30 days" → contract Permit deadline = 1 year (or infinite)
- UI shows "Estimated outcome: 100 USDC" → eth_call gives X, actual tx delivers Y
- UI shows ENS name "vitalik.eth" → resolved address differs from displayed
- UI shows "Slippage: 0.5%" default → no warning when liquidity thin and slippage 20%
- UI shows "Approval: 100 USDC" → actual `approve(spender, MAX_UINT256)` sent
- UI shows blocklist message → on-chain blocklist isn't enforced
- UI shows USDC 6 decimals → display divides by 1e6 but code expects 1e18

Heuristics: walk JS bundle text for known patterns and flag candidate UI strings
that are typically misaligned with their on-chain side.

Usage:
    python3 display_vs_reality_grep.py --bundle sessions/$DOMAIN/bundle-main.js \
        --output sessions/$DOMAIN/hypothesis/display_vs_reality.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class DisplayMismatch:
    finding_id: str
    surface: str            # "expiry" / "slippage" / "approval" / "decimals" / "ens" / "gas" / "blocklist" / "chain_display" / "intent_swap"
    severity_hint: str
    pattern_matched: str
    location_excerpt: str
    description: str
    verification_hint: str  # how to confirm this is real, not a false positive


@dataclass
class DisplayReport:
    target: str
    mismatches: List[DisplayMismatch] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)


# ── Data-Flow Divergence Map (FDE Plan 4, Task 5): source→sink pairing ──────────────────────────
# Static dupe of runtime signature-integrity: for one logical value (amount/recipient/chainId/
# deadline), find the variable feeding the DOM-display sink and the variable feeding the
# signing/tx-payload sink. Same variable = no divergence; different variable = candidate finding
# (Aave×CoW class: output-box reads destSpotAmount, signed order reads buyAmount minus fees).

@dataclass
class DataFlowRow:
    logical_value: str      # "amount" / "recipient" / "chainId" / "deadline"
    display_source: str     # variable/expression feeding the DOM-display sink ("?" if unresolved)
    reality_sink: str       # variable/expression feeding the signing/tx-payload sink ("?" if unresolved)
    same_var: str            # "Y" / "N" / "INCONCLUSIVE (minified)"
    divergence: str          # human-readable note, "" when same_var == "Y"


# Pattern set per surface. Each tuple = (surface, severity, regex, description, verification_hint).
_PATTERNS: List[Tuple[str, str, str, str, str]] = [
    # ── Expiry display ──
    (
        "expiry",
        "medium",
        r"(?:expires?\s+(?:in\s+)?[\d]+\s*(?:day|month|year|hour|minute|min))",
        "UI may display a finite expiry (e.g. '30 days') while contract Permit deadline could be far longer.",
        "Sign a test Permit with the burner wallet, decode the on-chain deadline from the signed payload, "
        "and confirm it matches the UI-displayed expiry.",
    ),
    (
        "expiry",
        "high",
        r"(?:Permit2|permit2_?expiry).*?(?:forever|unlimited|max(?:uint|imum)?)",
        "Permit2 default UI says 'forever' or 'unlimited' expiry — high-risk default.",
        "Check the Permit2 signing flow; verify the user can see and change expiry before confirming.",
    ),

    # ── Slippage ──
    (
        "slippage",
        "medium",
        r"slippage(?:\s*tolerance)?\s*[:=]\s*['\"]?(?:0\.1|0\.5|1)\s*%?",
        "Low default slippage with no UI warning for low-liquidity tokens can sandwich users.",
        "Find a thin-liquidity pool the dApp exposes; check whether UI shows a slippage warning when "
        "expected execution diverges from default tolerance.",
    ),

    # ── Intent-based swap divergence (taxonomy 16.9; Aave×CoW $50M 2026; reference_ehsan_aave_cow) ──
    (
        "intent_swap",
        "high",
        r"(?:destSpotAmount|beforeFees|beforeNetworkCosts|spotAmount|optimisticAmount)",
        "UI output box may read a BEFORE-costs amount while the signed buyAmount is derived elsewhere "
        "(minus fees/flash-loan/slippage) — displayed != signed (Aave destSpotAmount vs buyAmountBigInt).",
        "Trace the output-box variable to where the order is signed; confirm the displayed number is the "
        "SAME value that becomes buyAmount in the posted order. Different var = finding.",
    ),
    (
        "intent_swap",
        "high",
        r"getAppDataForQuote[\s\S]{0,120}?(?:return\s+undefined|=>\s*undefined|return;)",
        "Quote requested WITHOUT flash-loan/hook appData that defines execution — quote-context != "
        "post-context. Order later posted with different receiver/from/hooks/EIP-1271.",
        "Diff the quote request vs the posted order: compare receiver, from, hooks, appData, signingScheme "
        "— not just amount. Structurally different requests = the user saw a quote from another universe.",
    ),
    (
        "intent_swap",
        "medium",
        r"postLimitOrder|postSwapOrder(?!FromQuote)",
        "Order built fresh & posted instead of safe postSwapOrderFromQuote() — order is route-unbound; "
        "the signed minOut floor becomes the SOLE constraint (solver free to pick any venue).",
        "Confirm the posted order has no route binding to the shown quote; check the signed minOut floor "
        "magnitude. Weak floor + route-unbound = catastrophic-execution risk (Cat 5.8 backend half).",
    ),

    # ── Approval (UI claims fixed amount but code uses max) ──
    (
        "approval",
        "high",
        r"(?:approve|spending\s+(?:limit|allowance)|max(?:imum)?\s+allowance).*?MAX_UINT256",
        "Approval flow likely sends unlimited allowance regardless of UI-displayed amount.",
        "Inspect tx data sent to the wallet on Approve button. If amount = max uint, but UI shows a finite "
        "value, that's a display-vs-reality mismatch (Medium-High).",
    ),

    # ── Decimals ──
    (
        "decimals",
        "low",
        r"decimals\s*[:=]\s*(?:6|18)\b",
        "Hardcoded token decimals — if the dApp accepts arbitrary tokens, a 6/18 decimal mismatch causes "
        "either display rounding errors or precision loss.",
        "Find a non-standard-decimals token (e.g. 8 dec for WBTC) and observe UI display vs underlying "
        "on-chain balance.",
    ),

    # ── ENS / SNS display ──
    (
        "ens",
        "medium",
        r"(?:resolveName|lookupAddress|ens\.resolve|ensName)",
        "ENS/SNS resolution: UI may show resolved name while signing payload references a different "
        "(spoofable) address. Check that the displayed name matches the actual recipient.",
        "Send a tx to a known ENS-mapped address; check what address the wallet shows in confirmation "
        "vs what UI displayed.",
    ),

    # ── Gas estimation ──
    (
        "gas",
        "low",
        r"(?:estimateGas|gasEstimate|gas\s*[:=]\s*['\"]?\d{6,})",
        "Static gas estimate displayed in UI may not reflect actual gas burned for nested approve+swap "
        "or batched calls.",
        "Compare UI's 'Estimated gas' string vs the actual gas reported by the wallet on tx preview, "
        "especially for multi-step flows.",
    ),

    # ── Blocklist UI vs on-chain ──
    (
        "blocklist",
        "medium",
        r"(?:blocklist|sanctioned|restricted\s+region|OFAC|geo[_-]?block|chainalysis|TRM\s*labs?)",
        "Blocklist / sanctions UI may be UI-only (frontend rejects request) — contract typically still "
        "accepts. Check that on-chain enforcement actually exists.",
        "Try to interact with the contract directly (cast call) from a blocked address scenario; if the "
        "contract still accepts, the UI is decorative.",
    ),

    # ── Chain display ──
    (
        "chain_display",
        "low",
        r"(?:displayedChainName|chainName\s*[:=]|networkName\s*[:=])",
        "UI may render a chain name that doesn't match the wallet's connected chain — confusion vector "
        "for cross-chain replay.",
        "Switch the wallet to a chain the dApp supports but doesn't expect; observe whether the UI "
        "continues to render the originally displayed chain name.",
    ),

    # ── Tx hash display only (no human-readable decode) ──
    (
        "tx_decode",
        "low",
        r"data\s*[:=]\s*['\"]0x[a-f0-9]{8,}",
        "Hardcoded calldata string in UI — if displayed as 'Confirm Transaction (0x…)' without method "
        "decoding, user signs blind.",
        "Inspect the wallet popup when the user clicks Confirm. If only the hex is visible, that's a "
        "transparency issue and may be reportable as informational.",
    ),

    # ── Risk-engine indicator without enforcement ──
    (
        "risk_engine",
        "low",
        r"(?:halliday|witnesschain|trm[-_]?labs|risk[-_]?score)",
        "Risk engine integration: confirm whether UI score is decorative or actually blocks tx submission.",
        "Open a swap to a 'risky' token; check whether UI lets you sign anyway or hard-blocks. "
        "Decorative-only is at least an Informational finding.",
    ),
]


# display-source pass: named UI-render variables (assignment RHS = the actual source feeding the
# label/`.textContent`/JSX box). Regex must carry exactly ONE capture group.
_DATAFLOW_DISPLAY_SOURCE: Dict[str, List[str]] = {
    "amount": [
        r"\b(?:displayAmt|outputAmount|amountOut|formattedAmount|displayAmount|amountLabel)\s*=\s*([A-Za-z_$][\w$.]*)",
    ],
    "recipient": [
        r"\b(?:recipientLabel|displayRecipient|toDisplay|recipientText)\s*=\s*([A-Za-z_$][\w$.]*)",
    ],
    "chainId": [
        r"\b(?:displayedChainName|chainNameLabel|networkLabel)\s*=\s*([A-Za-z_$][\w$.]*)",
    ],
    "deadline": [
        r"\b(?:expiryLabel|deadlineDisplay|expiresInLabel)\s*=\s*([A-Za-z_$][\w$.]*)",
    ],
}

# reality-sink pass: the variable bound to the wire-protocol field name inside the
# signing/tx-payload object literal (`field: variable`). Gated below to lines near a sink-call
# marker (co-location engine, mirrors wallet_metadata_xss_check.py:174-203 Pass3, ±N lines).
_DATAFLOW_REALITY_SINK: Dict[str, List[str]] = {
    "amount": [
        r"\b(?:buyAmount|sellAmount)\s*:\s*([A-Za-z_$][\w$.]*)",
    ],
    "recipient": [
        r"\b(?:to|receiver|recipient)\s*:\s*([A-Za-z_$][\w$.]*)",
    ],
    "chainId": [
        r"\bchainId\s*:\s*([A-Za-z_$][\w$.]*)",
    ],
    "deadline": [
        r"\bdeadline\s*:\s*([A-Za-z_$][\w$.]*)",
    ],
}

# Sink-call markers: signing/broadcast entrypoints. A reality-sink field match only counts if it
# sits within DATAFLOW_PROX_LINES of one of these (avoids matching a stray `to:`/`deadline:` in
# unrelated object literals, e.g. React props).
_SINK_CONTEXT_MARKER_RX = re.compile(
    r"signTypedData|eth_sendTransaction|sendTransaction|_signTypedData|\bapprove\s*\(", re.IGNORECASE
)

DATAFLOW_PROX_LINES = 10


def _find_capture_matches(content: str, pattern: str) -> List[Tuple[int, str]]:
    """Return [(line_no, captured_group_1)] for every match of a 1-capture-group pattern."""
    matches: List[Tuple[int, str]] = []
    rx = re.compile(pattern)
    for idx, line in enumerate(content.split("\n"), 1):
        for m in rx.finditer(line):
            if m.lastindex:
                matches.append((idx, m.group(1)))
    return matches


def _marker_lines(content: str, marker_rx: "re.Pattern") -> List[int]:
    return [idx for idx, line in enumerate(content.split("\n"), 1) if marker_rx.search(line)]


def _near_any(line_no: int, marker_line_nos: List[int], prox: int) -> bool:
    return any(abs(line_no - mline) <= prox for mline in marker_line_nos)


def _looks_minified_var(name: str) -> bool:
    """1-2 char identifiers (a, b, _0x1f, t.n) are typical post-minification temp names — a
    pairing built off one of these can't be trusted."""
    core = name.split(".")[-1]
    return len(core) <= 2


def _bundle_is_minified(text: str) -> bool:
    """Heuristic: minifiers collapse whitespace/newlines into a handful of very long lines,
    unlike hand-authored/dev-build JS which wraps at readable widths."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return False
    max_len = max(len(ln) for ln in lines)
    return len(lines) <= 3 and max_len > 150


def trace_dataflow(text: str) -> List[DataFlowRow]:
    """Two-pass source→sink trace + pairing for logical values (amount/recipient/chainId/
    deadline). Directed grep, not a full AST/dataflow analysis — see module docstring header."""
    rows: List[DataFlowRow] = []
    minified = _bundle_is_minified(text)
    sink_marker_lines = _marker_lines(text, _SINK_CONTEXT_MARKER_RX)

    for logical_value, display_patterns in _DATAFLOW_DISPLAY_SOURCE.items():
        display_hits: List[Tuple[int, str]] = []
        for pat in display_patterns:
            display_hits.extend(_find_capture_matches(text, pat))

        raw_sink_hits: List[Tuple[int, str]] = []
        for pat in _DATAFLOW_REALITY_SINK[logical_value]:
            raw_sink_hits.extend(_find_capture_matches(text, pat))
        sink_hits = [
            (ln, var) for ln, var in raw_sink_hits
            if _near_any(ln, sink_marker_lines, DATAFLOW_PROX_LINES)
        ]

        if display_hits and sink_hits:
            d_var = display_hits[0][1]
            s_var = sink_hits[0][1]
            if minified and (_looks_minified_var(d_var) or _looks_minified_var(s_var)):
                rows.append(DataFlowRow(
                    logical_value=logical_value, display_source=d_var, reality_sink=s_var,
                    same_var="INCONCLUSIVE (minified)",
                    divergence="Identifiers look minifier-erased — pairing not trustworthy; "
                                "re-check with a runtime/browser trace instead of static grep.",
                ))
            elif d_var == s_var:
                rows.append(DataFlowRow(
                    logical_value=logical_value, display_source=d_var, reality_sink=s_var,
                    same_var="Y", divergence="",
                ))
            else:
                rows.append(DataFlowRow(
                    logical_value=logical_value, display_source=d_var, reality_sink=s_var,
                    same_var="N",
                    divergence=(
                        f"display reads `{d_var}`, signing/tx payload reads `{s_var}` — different "
                        f"source variable feeding {logical_value}; confirm the two are the SAME "
                        f"value at signing time (Aave×CoW destSpotAmount-vs-buyAmount class)."
                    ),
                ))
        elif minified and (display_hits or sink_hits):
            rows.append(DataFlowRow(
                logical_value=logical_value,
                display_source=display_hits[0][1] if display_hits else "?",
                reality_sink=sink_hits[0][1] if sink_hits else "?",
                same_var="INCONCLUSIVE (minified)",
                divergence="Only one side of the pair resolved in a minified bundle — identifiers "
                            "erased on the other side; cannot confirm pairing statically.",
            ))
        # else: no signal at all for this logical_value — nothing to report, stay silent.

    if not rows and minified:
        # R3: minified bundle where NOTHING paired anywhere must still surface a row, not go
        # silently empty — the analyst needs to know static tracing was defeated, not that the
        # dApp has zero display/sink surfaces.
        rows.append(DataFlowRow(
            logical_value="amount", display_source="?", reality_sink="?",
            same_var="INCONCLUSIVE (minified)",
            divergence="Bundle appears minified (identifiers erased) — static source->sink "
                        "pairing not possible; re-check with a runtime/browser trace.",
        ))

    return rows


def dataflow_map_to_markdown(target: str, rows: List[DataFlowRow]) -> str:
    """Serialize Data-Flow Divergence rows into dataflow_map.md format. Empty rows (no display/
    sink surfaces detected, and bundle not minified) still produce a file — 'RESULT: N/A — ...' —
    mirroring clone_diff_to_markdown's convention (Task 3) so downstream gates can tell
    'ran, nothing to trace' apart from 'never ran'."""
    lines = [f"# Data-Flow Divergence Map — {target}"]
    if not rows:
        lines.append("RESULT: N/A — no display/sink pairs detected")
        return "\n".join(lines) + "\n"
    divergent = sum(1 for r in rows if r.same_var == "N")
    lines.append(f"RESULT: {len(rows)} traced value(s), {divergent} diverging")
    lines.append("")
    lines.append("| logical-value | display-source | reality-sink | same-var?(Y/N) | divergence |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        lines.append(f"| {r.logical_value} | {r.display_source} | {r.reality_sink} | {r.same_var} | {r.divergence} |")
    return "\n".join(lines) + "\n"


def write_dataflow_map_md(md_out, target: str, rows: List[DataFlowRow]) -> Path:
    """Write dataflow_map.md to the EXACT path given — full session path, never CWD-relative or
    rewritten (same session-path rule as Task 3's write_clone_diff_md)."""
    path = Path(md_out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dataflow_map_to_markdown(target, rows), encoding="utf-8")
    return path


def scan_bundle(text: str, target: str) -> DisplayReport:
    report = DisplayReport(target=target)
    counter = 1

    for surface, severity, rx, description, hint in _PATTERNS:
        for m in re.finditer(rx, text, re.IGNORECASE):
            # Excerpt = up to 80 chars around match
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            excerpt = text[start:end].replace("\n", " ").strip()
            if len(excerpt) > 160:
                excerpt = excerpt[:157] + "..."
            report.mismatches.append(
                DisplayMismatch(
                    finding_id=f"DR{counter:03d}",
                    surface=surface,
                    severity_hint=severity,
                    pattern_matched=m.group(0)[:80],
                    location_excerpt=excerpt,
                    description=description,
                    verification_hint=hint,
                )
            )
            counter += 1

    # Dedupe by (surface, pattern_matched) — keep first occurrence
    seen = set()
    unique: List[DisplayMismatch] = []
    for m in report.mismatches:
        key = (m.surface, m.pattern_matched.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(m)
    report.mismatches = unique

    report.hypotheses = [
        f"H[{m.finding_id}]: surface={m.surface} — {m.description}"
        for m in unique
    ]
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--bundle", action="append", type=Path, default=[], help="Bundle file (repeatable)")
    parser.add_argument("--target", default="<bundle>", help="Target URL for report metadata")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--md-out", type=Path,
                         help="Full path to write the Data-Flow Divergence Map markdown "
                              "(e.g. sessions/$DOMAIN/dataflow_map.md) — written EXACTLY as given, "
                              "never CWD-relative or rewritten")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.bundle:
        parser.error("at least one --bundle PATH required")

    combined_text_parts: List[str] = []
    for bp in args.bundle:
        if bp.exists():
            try:
                combined_text_parts.append(bp.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
    combined = "\n".join(combined_text_parts)

    report = scan_bundle(combined, args.target)
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if args.md_out:
        dataflow_rows = trace_dataflow(combined)
        write_dataflow_map_md(args.md_out, args.target, dataflow_rows)

    if not args.quiet:
        print(f"Bundle target: {report.target}")
        print(f"Display-vs-reality candidates: {len(report.mismatches)}")
        by_surface: Dict[str, int] = {}
        for m in report.mismatches:
            by_surface[m.surface] = by_surface.get(m.surface, 0) + 1
        for surface, n in sorted(by_surface.items()):
            print(f"  {surface}: {n}")
    return 0 if not report.mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
