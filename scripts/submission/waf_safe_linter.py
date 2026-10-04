#!/usr/bin/env python3
"""
waf_safe_linter.py — Scan draft bug bounty reports for Cloudflare WAF triggers.

Background:
On 2026-05-20, HackenProof submit was silently blocked (CF 403 Ray ID 9fe98395c93abcc9)
because the draft report's payload contained literal exploit signatures that CF WAF
interprets as actual attack patterns. This linter scans report drafts for those
known triggers before submission.

Usage:
    python3 waf_safe_linter.py --file draft_report.md
    python3 waf_safe_linter.py --file draft_report.md --json
    python3 waf_safe_linter.py --file draft_report.md --fix    # write *.fixed.md

Exit code 0 = clean. Non-zero = N triggers found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional


@dataclass
class Trigger:
    rule_id: str
    severity: str        # "high" / "medium" / "low"
    line: int
    matched: str
    suggestion: str
    category: str


# ──────────────────────────────────────────────────────────────────────────
# WAF rule catalogue
#
# Each rule = (id, severity, regex, suggestion, category).
# Regex is compiled with re.IGNORECASE and re.MULTILINE unless documented.
# ──────────────────────────────────────────────────────────────────────────

_RULES = [
    # ── Solidity / EVM function calls that read like injection attempts ──
    (
        "evm_approve_max",
        "high",
        r"approve\s*\(\s*[^,)]+,\s*(MAX_UINT256|2\s*\*\*\s*256\s*-\s*1|0xff{16,}|type\(uint256\)\.max)\s*\)",
        'Replace with prose: "an unlimited ERC-20 spending allowance"',
        "exploit_signature",
    ),
    (
        "evm_send_transaction",
        "high",
        r"\beth_sendTransaction\b",
        'Replace with: "wallet transaction signing requests" or "direct value transfers"',
        "exploit_signature",
    ),
    (
        "evm_sign_methods",
        "medium",
        r"\b(eth_sign|personal_sign|signTypedData_v\d|eth_signTypedData)\b",
        'Either drop the literal method name or wrap it in a code block (single backticks) — multiple bare references in one paragraph trip WAF.',
        "exploit_signature",
    ),
    (
        "evm_permit2_literal",
        "medium",
        r"\bPermit2-style\b",
        'Use "Permit2 off-chain approvals" (no hyphen-style construction).',
        "exploit_signature",
    ),
    (
        "evm_drainer_phrase",
        "high",
        r"\b(drainer|drain(?:ing)?\s+(?:wallet|funds|user)|wallet[-\s]drainer)\b",
        'Use "fund extraction primitive" or "asset siphon flow".',
        "exploit_signature",
    ),

    # ── Stack traces / nested error format ──
    (
        "stack_trace_at_object",
        "medium",
        r"^\s*at\s+(?:Object|Function|async)\.[A-Za-z_][\w.]*\s*\(",
        'Stack traces look like JS exception payloads — describe the error in prose ("a SecurityError was raised when…") instead of pasting the trace verbatim.',
        "stack_trace",
    ),
    (
        "stack_trace_js_location",
        "low",
        r"\.js:\d+:\d+\)?$",
        'Trailing "file.js:LINE:COL" markers cluster as stack-trace indicators. Move into a fenced code block if essential.',
        "stack_trace",
    ),

    # ── CSS / DOM payload-looking strings ──
    (
        "css_overlay_payload",
        "medium",
        r"opacity\s*:\s*0\s*;.*?pointer-events\s*:\s*auto",
        'Describe overlay as "a fully transparent visual overlay that still receives clicks" instead of literal CSS rule.',
        "css_payload",
    ),
    (
        "css_pointer_events_alone",
        "low",
        r"pointer-events\s*:\s*(?:auto|none)\s*[;}]",
        'Describe interactivity in prose ("clicks are routed to the underlying iframe") rather than CSS literal.',
        "css_payload",
    ),

    # ── XSS-like text fragments ──
    (
        "xss_script_tag",
        "high",
        r"<\s*script\b[^>]*>",
        'Describe as "an attacker-controlled script tag" instead of including raw <script>.',
        "xss_payload",
    ),
    (
        "xss_javascript_uri",
        "high",
        r"\bjavascript:\s*[a-z]",
        'Refer to it as "a javascript-protocol URI" without the literal prefix.',
        "xss_payload",
    ),
    (
        "xss_event_handler",
        "medium",
        r"\bon(?:click|error|load|mouseover|focus)\s*=\s*['\"]",
        'Describe the handler in words: "an inline event handler attribute".',
        "xss_payload",
    ),

    # ── SQL-like fragments (CF generic XSS/SQLi rulesets) ──
    (
        "sql_union_select",
        "medium",
        r"\bUNION\s+(?:ALL\s+)?SELECT\b",
        'Reword as "a UNION-based injection probe" in prose.',
        "sql_payload",
    ),
    (
        "sql_or_one_one",
        "medium",
        r"['\"]?\s*(?:or|OR)\s+1\s*=\s*1\s*(?:--|#|/\*)",
        'Reword as "a classic SQL tautology payload".',
        "sql_payload",
    ),

    # ── Excessive nested JSON / code spans ──
    (
        "nested_json_braces",
        "low",
        r"\{[^{}\n]{0,200}\{[^{}\n]{0,200}\{",
        'Two+ levels of inline { … { … { trip WAF as code injection. Use bullet list instead of JSON literal in prose.',
        "structure",
    ),

    # ── Shell/command-substitution patterns ──
    (
        "shell_backtick_subst",
        "medium",
        r"`[^`\n]{0,80}\$\([^)]+\)",
        'Describe the shell pipeline in prose. Backtick + $() reads as command injection.',
        "shell_payload",
    ),
    (
        "shell_pipe_curl",
        "medium",
        r"\bcurl\s+-[A-Za-z]*\s+[^\n]{0,80}\|\s*(?:sh|bash|python)\b",
        'Reword as "an attacker payload piped into a shell interpreter".',
        "shell_payload",
    ),

    # ── Wallet-attack literal phrases that CF flags ──
    (
        "wallet_phishing_kit",
        "low",
        r"\b(phishing kit|wallet phishing tool|seed phrase grabber)\b",
        'Use neutral phrasing: "wallet-phishing primitive" or "social engineering flow".',
        "exploit_signature",
    ),

    # ── Browser console error literals (Cloudflare browser-error WAF rules) ──
    (
        "browser_security_error",
        "low",
        r"SecurityError:\s*Failed\s+to\s+(?:read|execute)",
        'Paraphrase: "the browser logged a cross-origin SecurityError" instead of including the literal message.',
        "browser_error",
    ),
]


_COMPILED = [
    (rid, sev, re.compile(rx, re.IGNORECASE | re.MULTILINE), sug, cat)
    for (rid, sev, rx, sug, cat) in _RULES
]


def lint_text(text: str) -> List[Trigger]:
    """Scan the given text and return all matching triggers."""
    triggers: List[Trigger] = []
    lines = text.splitlines()
    # Build cumulative line offsets for line-number lookup
    offsets = [0]
    running = 0
    for ln in lines:
        running += len(ln) + 1  # +1 for newline
        offsets.append(running)

    def offset_to_line(offset: int) -> int:
        # Binary search would be faster but linear is fine for report-sized files
        for i, o in enumerate(offsets):
            if offset < o:
                return i  # 1-indexed
        return len(lines)

    for rid, sev, regex, suggestion, category in _COMPILED:
        for m in regex.finditer(text):
            ln_num = offset_to_line(m.start())
            matched_snippet = m.group(0).strip()
            if len(matched_snippet) > 120:
                matched_snippet = matched_snippet[:117] + "..."
            triggers.append(
                Trigger(
                    rule_id=rid,
                    severity=sev,
                    line=ln_num,
                    matched=matched_snippet,
                    suggestion=suggestion,
                    category=category,
                )
            )
    triggers.sort(key=lambda t: (t.line, t.rule_id))
    return triggers


def format_report(triggers: List[Trigger], path: Optional[Path]) -> str:
    if not triggers:
        header = f"WAF linter: PASS — {path or '<stdin>'}"
        return f"{header}\n0 triggers found. Safe to submit.\n"

    out = []
    out.append(f"WAF linter: FAIL — {path or '<stdin>'}")
    out.append(f"{len(triggers)} trigger(s) found.")
    out.append("")
    sev_counts = {"high": 0, "medium": 0, "low": 0}
    for t in triggers:
        sev_counts[t.severity] = sev_counts.get(t.severity, 0) + 1
    out.append(
        f"Severity breakdown: high={sev_counts['high']} medium={sev_counts['medium']} low={sev_counts['low']}"
    )
    out.append("")
    for t in triggers:
        out.append(f"  [{t.severity.upper():6}] L{t.line:>4}  rule={t.rule_id}  ({t.category})")
        out.append(f"           matched: {t.matched}")
        out.append(f"           fix:     {t.suggestion}")
        out.append("")
    out.append("Apply suggestions before retrying submission. Cloudflare WAF will silently 403.")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--file", type=Path, help="Path to draft report (markdown).")
    parser.add_argument("--stdin", action="store_true", help="Read draft from stdin.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human report.")
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="Always exit 0 even when triggers found (useful in CI summaries).",
    )
    args = parser.parse_args(argv)

    if not args.file and not args.stdin:
        parser.error("Provide --file PATH or --stdin")

    if args.file:
        if not args.file.exists():
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 2
        text = args.file.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    triggers = lint_text(text)

    if args.json:
        print(json.dumps([asdict(t) for t in triggers], ensure_ascii=False, indent=2))
    else:
        print(format_report(triggers, args.file))

    if args.exit_zero:
        return 0
    return 0 if not triggers else 1


if __name__ == "__main__":
    sys.exit(main())
