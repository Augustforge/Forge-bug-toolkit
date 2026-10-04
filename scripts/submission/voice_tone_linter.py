#!/usr/bin/env python3
"""
voice_tone_linter.py — Scan draft reports for AI/automation reveals.

Background:
On 2026-05-20 a first draft included "Testing was performed in a headless
Chromium under Playwright" — that single sentence reveals the report was
produced with automation, not by a human researcher. HackenProof/Immunefi/
Cantina submissions must read as written by the human hunter, not an agent.

This linter scans for:
1. Automation framework names (playwright, headless, puppeteer, selenium)
2. AI/agent reveal language (Claude, agent, harness, LLM, bot session)
3. First-person plural that betrays multi-actor authorship ("we performed")
4. Tool-revealing phrasings that betray automated tooling (nuclei output, burp scan log)

Usage:
    python3 voice_tone_linter.py --file draft_report.md
    python3 voice_tone_linter.py --file draft_report.md --json
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
class Reveal:
    rule_id: str
    severity: str
    line: int
    matched: str
    suggestion: str
    category: str


_RULES = [
    # ── Automation framework names ──
    (
        "automation_playwright",
        "high",
        r"\bplaywright\b",
        'Replace with "browser" or remove the sentence. Playwright is automation framework — naming it reveals AI/agent authorship.',
        "automation_framework",
    ),
    (
        "automation_puppeteer",
        "high",
        r"\bpuppeteer\b",
        'Same as Playwright — drop or replace with "browser".',
        "automation_framework",
    ),
    (
        "automation_selenium",
        "high",
        r"\bselenium\b",
        'Drop or replace with "browser".',
        "automation_framework",
    ),
    (
        "automation_headless",
        "high",
        r"\bheadless(?:\s+(?:chromium|chrome|firefox|browser))?\b",
        'Replace "headless Chromium" / "headless browser" with "a regular browser" or "DevTools".',
        "automation_framework",
    ),
    (
        "automation_chromium_devtools_protocol",
        "medium",
        r"\bChrome\s+DevTools\s+Protocol\b|\bCDP\s+session\b",
        'Avoid naming the protocol — say "the browser console" or "DevTools".',
        "automation_framework",
    ),
    (
        "automation_phrasings",
        "high",
        r"\b(?:automated\s+(?:browser|session|test)|automation\s+framework|automated\s+exploration)\b",
        'Rewrite as personal action: "I tested in a browser", "I conducted in a regular browser".',
        "automation_framework",
    ),

    # ── AI/agent reveals ──
    (
        "ai_claude",
        "high",
        r"\bClaude\b",
        'Never name the AI assistant. Remove entirely.',
        "ai_reveal",
    ),
    (
        "ai_anthropic",
        "high",
        r"\bAnthropic\b",
        'Never name the AI provider. Remove entirely.',
        "ai_reveal",
    ),
    (
        "ai_openai_gpt",
        "high",
        r"\b(?:OpenAI|ChatGPT|GPT-\d|GPT\d)\b",
        'Never name AI providers. Remove entirely.',
        "ai_reveal",
    ),
    (
        "ai_assistant_terms",
        "high",
        r"\b(?:the\s+(?:assistant|agent|model|harness|LLM)|AI\s+assistant|LLM\s+session)\b",
        'Remove agent/assistant references — write in 1st person ("I observed") or 3rd-passive ("the request was sent").',
        "ai_reveal",
    ),
    (
        "ai_bot_session",
        "medium",
        r"\bbot\s+(?:session|run|execution)\b",
        'Remove "bot session" — sounds like automation. Use "research session" or just drop.',
        "ai_reveal",
    ),
    (
        "ai_thinking_block",
        "high",
        r"<thinking>|</thinking>|\bchain[- ]of[- ]thought\b",
        'Internal AI tags must never appear in submitted reports.',
        "ai_reveal",
    ),

    # ── First-person plural betrays multi-actor authorship ──
    (
        "we_performed",
        "medium",
        r"\bwe\s+(?:performed|observed|tested|noted|conducted|confirmed|verified|reproduced|executed|analyzed|assessed)\b",
        'Switch to "I performed" / "I observed" — single hunter voice. Or 3rd-passive: "the request was sent".',
        "voice_consistency",
    ),
    (
        "our_team",
        "low",
        r"\b(?:our\s+team|our\s+(?:researcher|hunter|tester)|the\s+team)\b",
        'Single hunter — drop "our team" / "the team".',
        "voice_consistency",
    ),

    # ── Tool-revealing phrasings ──
    (
        "tool_nuclei",
        "low",
        r"\bnuclei\s+(?:output|template|scan(?:ner)?)\b",
        'Describe the finding in protocol terms instead of naming nuclei. Say "I sent a HEAD request" / "I issued a GET" instead.',
        "tool_reveal",
    ),
    (
        "tool_burp_log",
        "medium",
        r"\bBurp(?:\s+Suite)?(?:\s+(?:scan|log|output|repeater))?\b",
        'Mentioning Burp is fine if real hunters use it. Burp scan/log output literally is a paste of tool result — paraphrase the request/response.',
        "tool_reveal",
    ),
    (
        "tool_sqlmap_output",
        "medium",
        r"\bsqlmap\s+(?:output|scan|log)\b",
        'Describe the SQL injection observation in prose. Tool output as evidence is fine but should be wrapped not narrated.',
        "tool_reveal",
    ),

    # ── Phrasings that betray run-time AI behavior ──
    (
        "ai_step_by_step_internal",
        "medium",
        r"\b(?:let me|I'll)\s+(?:think|analyze|reason|check)\b",
        'Strip first-person planning language ("let me think") — that\'s assistant chatter, not report content.',
        "ai_reveal",
    ),
    (
        "ai_apology",
        "low",
        r"\b(?:I apologize|sorry,?\s+I)\b",
        'Apologies have no place in a bug bounty report. Remove.',
        "ai_reveal",
    ),

    # ── Time/date placeholders that betray scripted output ──
    (
        "placeholder_token",
        "high",
        r"\{\{[A-Z_]+\}\}",
        'Unfilled template placeholder — fill before submit.',
        "template",
    ),
]


_COMPILED = [
    (rid, sev, re.compile(rx, re.IGNORECASE | re.MULTILINE), sug, cat)
    for (rid, sev, rx, sug, cat) in _RULES
]


def lint_text(text: str) -> List[Reveal]:
    reveals: List[Reveal] = []
    lines = text.splitlines()
    offsets = [0]
    running = 0
    for ln in lines:
        running += len(ln) + 1
        offsets.append(running)

    def offset_to_line(offset: int) -> int:
        for i, o in enumerate(offsets):
            if offset < o:
                return i
        return len(lines)

    for rid, sev, regex, suggestion, category in _COMPILED:
        for m in regex.finditer(text):
            ln_num = offset_to_line(m.start())
            matched_snippet = m.group(0).strip()
            if len(matched_snippet) > 120:
                matched_snippet = matched_snippet[:117] + "..."
            reveals.append(
                Reveal(
                    rule_id=rid,
                    severity=sev,
                    line=ln_num,
                    matched=matched_snippet,
                    suggestion=suggestion,
                    category=category,
                )
            )
    reveals.sort(key=lambda r: (r.line, r.rule_id))
    return reveals


def format_report(reveals: List[Reveal], path: Optional[Path]) -> str:
    if not reveals:
        return f"Voice linter: PASS — {path or '<stdin>'}\n0 reveals found. Submission voice clean.\n"

    out = []
    out.append(f"Voice linter: FAIL — {path or '<stdin>'}")
    out.append(f"{len(reveals)} reveal(s) found.")
    sev_counts = {"high": 0, "medium": 0, "low": 0}
    for r in reveals:
        sev_counts[r.severity] = sev_counts.get(r.severity, 0) + 1
    out.append(
        f"Severity breakdown: high={sev_counts['high']} medium={sev_counts['medium']} low={sev_counts['low']}"
    )
    out.append("")
    for r in reveals:
        out.append(f"  [{r.severity.upper():6}] L{r.line:>4}  rule={r.rule_id}  ({r.category})")
        out.append(f"           matched: {r.matched}")
        out.append(f"           fix:     {r.suggestion}")
        out.append("")
    out.append("Reports must read as written by a human hunter, not an AI assistant.")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--file", type=Path, help="Path to draft report (markdown).")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exit-zero", action="store_true")
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

    reveals = lint_text(text)

    if args.json:
        print(json.dumps([asdict(r) for r in reveals], ensure_ascii=False, indent=2))
    else:
        print(format_report(reveals, args.file))

    if args.exit_zero:
        return 0
    return 0 if not reveals else 1


if __name__ == "__main__":
    sys.exit(main())
