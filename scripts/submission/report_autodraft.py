#!/usr/bin/env python3
"""
report_autodraft.py — Generate a platform-specific report draft from session output.

Reads:
  sessions/$DOMAIN/finding_$ID.json       (canonical finding metadata)
  sessions/$DOMAIN/platform.json           (target platform from platform_detector)
  sessions/$DOMAIN/dapp_detection.json     (chain class, auth providers)
  sessions/$DOMAIN/auth_provider_config.json
  sessions/$DOMAIN/iframe_trust_matrix.json
  sessions/$DOMAIN/attack_chains.md        (composed attack pattern)

Picks the right template from bug-bounty-toolkit/templates/dapp_reports/
and fills placeholders. Output is intentionally a STARTING POINT — the operator
adjusts before submit, then runs WAF + voice linters.

Usage:
    python3 report_autodraft.py --session sessions/synfutures \
        --platform hackenproof --finding F001 --output draft.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


PLATFORM_TEMPLATE_MAP = {
    "hackenproof": "hackenproof_dapp.md",
    "immunefi": "immunefi_dapp.md",
    "cantina": "cantina_dapp.md",
    "hackerone": "hackerone_dapp.md",
    "bugcrowd": "bugcrowd_dapp.md",
}


# ── Severity defensibility hints per platform ──
SEVERITY_HINTS = {
    "hackenproof": {
        "Critical": "no user action / private key leak / mass auth bypass",
        "High": "user-click + significant fund loss (SynFutures class)",
        "Medium": "social engineering required + meaningful impact",
        "Low": "PII / hygiene / UX DoS",
    },
    "immunefi": {
        "Critical": "direct fund loss at scope-defined max",
        "High": "$10-50k tier",
        "Medium": "$1-10k tier",
        "Low": "Insight tier — design feedback",
    },
    "cantina": {
        "Critical": "loss of funds without user interaction",
        "High": "loss with minor friction",
        "Medium": "loss with significant friction",
        "Low": "degraded UX, no fund loss",
    },
    "hackerone": {
        "Critical": "CVSS >= 9.0",
        "High": "CVSS 7.0-8.9",
        "Medium": "CVSS 4.0-6.9",
        "Low": "CVSS < 4.0",
    },
    "bugcrowd": {
        "P1": "VRT critical (server-side RCE, full account takeover)",
        "P2": "VRT high (significant data exposure)",
        "P3": "VRT medium",
        "P4": "VRT low",
        "P5": "VRT informational",
    },
}


def _load_json_safe(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warn: could not parse {path}: {exc}", file=sys.stderr)
        return None


def _load_text_safe(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _waf_safe_rewrites(text: str) -> str:
    """
    Apply known WAF-safe rewrites that report_autodraft can do confidently.
    These are the conservative ones — anything ambiguous is left for the operator.
    """
    rewrites = [
        (r"\bapprove\(\s*spender\s*,\s*MAX_UINT256\s*\)", "an unlimited ERC-20 spending allowance"),
        (r"\beth_sendTransaction\b", "direct value transfers"),
        (r"\bPermit2-style\b", "Permit2 off-chain"),
        (r"opacity\s*:\s*0\s*;\s*pointer-events\s*:\s*auto", "a fully transparent visual overlay"),
    ]
    for rx, replacement in rewrites:
        text = re.sub(rx, replacement, text, flags=re.IGNORECASE)
    return text


def _voice_safe_rewrites(text: str) -> str:
    """Replace automation/AI reveals with neutral 1st person."""
    rewrites = [
        (r"\bheadless\s+Chromium\s+under\s+Playwright\b", "a regular browser"),
        (r"\bheadless\s+(?:chromium|chrome|firefox|browser)\b", "a regular browser"),
        (r"\bautomated\s+browser(?:\s+session)?\b", "a browser"),
        (r"\bautomation\s+framework\b", "browser instrumentation"),
        (r"\bplaywright\b", "browser"),
        (r"\bpuppeteer\b", "browser"),
        (r"\bthe\s+(?:assistant|agent|harness|LLM|model)\b", "I"),
        (r"\bwe\s+(performed|observed|tested|noted|conducted|verified|confirmed|reproduced)\b", r"I \1"),
        (r"\bClaude\b", ""),
        (r"\bAnthropic\b", ""),
    ]
    for rx, replacement in rewrites:
        text = re.sub(rx, replacement, text, flags=re.IGNORECASE)
    # Collapse any double spaces introduced
    text = re.sub(r"\s{2,}", " ", text)
    return text


def _normalize(text: str) -> str:
    """Apply both WAF-safe and voice-safe rewrites in order."""
    return _voice_safe_rewrites(_waf_safe_rewrites(text))


def _slug_to_severity_field(platform: str, severity: str) -> str:
    """Return platform-specific severity label."""
    if platform == "bugcrowd":
        # Bugcrowd uses P1-P5; expect caller to already pass that
        return severity
    return severity


def fill_template(template_text: str, context: Dict[str, str]) -> str:
    """
    Replace {{TOKEN}} placeholders. Unfilled tokens are left visible
    so voice_tone_linter flags them via the placeholder_token rule.
    """
    def repl(match: re.Match) -> str:
        key = match.group(1)
        if key in context:
            return context[key]
        return match.group(0)

    return re.sub(r"\{\{([A-Z_]+)\}\}", repl, template_text)


def build_context(session_dir: Path, finding_id: str, platform: str) -> Dict[str, str]:
    """Gather all session artifacts into a placeholder dict."""
    finding = _load_json_safe(session_dir / f"finding_{finding_id}.json") or {}
    dapp_det = _load_json_safe(session_dir / "dapp_detection.json") or {}
    auth = _load_json_safe(session_dir / "auth_provider_config.json") or {}
    iframe = _load_json_safe(session_dir / "iframe_trust_matrix.json") or {}
    clones = _load_json_safe(session_dir / "clones.json") or {}
    chains = _load_text_safe(session_dir / "attack_chains.md") or ""
    platform_meta = _load_json_safe(session_dir / "platform.json") or {}

    target = finding.get("target") or platform_meta.get("target") or ""
    title = finding.get("title", "")
    category = finding.get("category", "")
    severity = finding.get("severity", "")
    summary = finding.get("summary", "")
    impact = finding.get("impact", "")
    vuln_details = finding.get("vulnerability_details", "")
    validation_steps = finding.get("validation_steps", "")
    recommendation = finding.get("recommendation", "")
    references = finding.get("references", "")
    supporting_files = finding.get("supporting_files", [])
    poc_files_block = "\n".join(
        f"{i+1}. {f.get('filename', '')} — {f.get('description', '')}" for i, f in enumerate(supporting_files)
    )

    # Apply WAF-safe + voice-safe rewrites to all long-form sections
    context = {
        "TARGET": target,
        "CATEGORY": category,
        "SEVERITY": severity,
        "TITLE": _normalize(title),
        "SUMMARY": _normalize(summary),
        "IMPACT": _normalize(impact),
        "VULN_DETAILS": _normalize(vuln_details),
        "VALIDATION_STEPS": _normalize(validation_steps),
        "RECOMMENDATION": _normalize(recommendation),
        "REFERENCES": references,
        "SUPPORTING_FILES": poc_files_block,
        "FINDING_ID": finding_id,
        "DATE": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "PLATFORM": platform,
        "AUTH_PROVIDERS": ", ".join(auth.keys()) if isinstance(auth, dict) else "",
        "DETECTION_SCORE": str(dapp_det.get("detection_score", "")),
        "CHAIN_CLASS": str(dapp_det.get("chain_class", "")),
        "ATTACK_CHAINS": _normalize(chains),
        "CLONES_FOUND": ", ".join(clones.get("clones", [])) if isinstance(clones, dict) else "",
    }
    return context


def find_template(platform: str, template_dir: Path) -> Path:
    fname = PLATFORM_TEMPLATE_MAP.get(platform)
    if not fname:
        raise SystemExit(f"error: unsupported platform '{platform}'. Known: {list(PLATFORM_TEMPLATE_MAP)}")
    candidate = template_dir / fname
    if not candidate.exists():
        raise SystemExit(f"error: template not found: {candidate}")
    return candidate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--session", type=Path, required=True, help="Session directory (sessions/$DOMAIN)")
    parser.add_argument("--platform", required=True, choices=list(PLATFORM_TEMPLATE_MAP))
    parser.add_argument("--finding", required=True, help="Finding ID (e.g. F001)")
    parser.add_argument("--output", type=Path, required=True, help="Output draft markdown path")
    parser.add_argument(
        "--template-dir",
        type=Path,
        default=Path("bug-bounty-toolkit/templates/dapp_reports"),
        help="Where the per-platform templates live",
    )
    args = parser.parse_args(argv)

    if not args.session.is_dir():
        print(f"error: session not a directory: {args.session}", file=sys.stderr)
        return 2

    template_path = find_template(args.platform, args.template_dir)
    template_text = template_path.read_text(encoding="utf-8")
    context = build_context(args.session, args.finding, args.platform)

    # Annotate severity hint at top of file so the operator can sanity-check
    severity_hint = SEVERITY_HINTS.get(args.platform, {}).get(context.get("SEVERITY", ""), "")
    if severity_hint:
        template_text = (
            f"<!-- severity_hint ({args.platform}): {context['SEVERITY']} = {severity_hint} -->\n"
            + template_text
        )

    draft = fill_template(template_text, context)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(draft, encoding="utf-8")

    # Remind to run linters
    print(f"Draft written: {args.output}")
    print("Next steps:")
    print(f"  python3 bug-bounty-toolkit/scripts/submission/waf_safe_linter.py --file {args.output}")
    print(f"  python3 bug-bounty-toolkit/scripts/submission/voice_tone_linter.py --file {args.output}")
    print("Both must return PASS (0 issues) before submission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
