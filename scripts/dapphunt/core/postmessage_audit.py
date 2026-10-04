#!/usr/bin/env python3
"""
postmessage_audit.py — Find postMessage handlers and classify origin validation.

Categories:
- STRICT: e.origin === EXPECTED  (and === unstringified URL)
- SUBSTRING: e.origin.includes(...) / e.origin.indexOf(...) > -1 / e.origin.endsWith(...)
- REGEX: e.origin.match(...) — usually broken
- ALLOWLIST_ARRAY: trusted_origins.includes(e.origin)
- MISSING: no origin check before processing event.data
- UNKNOWN: handler present, validation not localizable

Patterns are heuristic — bundles are minified. Hunter must validate manually.

Usage:
    python3 postmessage_audit.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/postmessage_audit.json
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


# Roughly catch addEventListener('message', cb) — minifier may rename `addEventListener` to `addEventListener` (it's a builtin)
_LISTENER_RX = re.compile(r"addEventListener\s*\(\s*['\"]message['\"]\s*,", re.IGNORECASE)
# Origin check classifications
_STRICT_RX = re.compile(r"(?:e|event|msg)\.origin\s*(?:!==|===)\s*['\"]", re.IGNORECASE)
_INCLUDES_RX = re.compile(r"(?:e|event|msg)\.origin\.(?:includes|indexOf|endsWith|startsWith)\s*\(", re.IGNORECASE)
_REGEX_RX = re.compile(r"(?:e|event|msg)\.origin\.match\s*\(", re.IGNORECASE)
_ALLOWLIST_RX = re.compile(r"\.includes\s*\(\s*(?:e|event|msg)\.origin\s*\)", re.IGNORECASE)
# Dangerous data parsing inside handler
_EVAL_RX = re.compile(r"eval\s*\(\s*(?:e|event|msg)\.data", re.IGNORECASE)
_FUNCTION_CTOR_RX = re.compile(r"new\s+Function\s*\(\s*(?:e|event|msg)\.data", re.IGNORECASE)


@dataclass
class Handler:
    handler_id: str
    origin_validation: str    # STRICT / SUBSTRING / REGEX / ALLOWLIST_ARRAY / MISSING / UNKNOWN
    excerpt: str
    notes: List[str] = field(default_factory=list)


@dataclass
class PostMessageReport:
    target: str
    handlers: List[Handler] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-pm-audit/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _gather_bundle_text(target: str) -> str:
    html = _fetch(target)
    if not html:
        return ""
    parts = [html]
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    srcs = re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)

    def rank(u: str) -> tuple:
        lower = u.lower()
        return (0 if "/index-" in lower or "/main-" in lower else 1, 1 if "vendor" in lower or "polyfill" in lower else 0, -len(u))

    resolved = []
    for s in srcs:
        if s.startswith("//"):
            resolved.append(f"{parsed.scheme}:{s}")
        elif s.startswith("/"):
            resolved.append(f"{base}{s}")
        elif s.startswith("http"):
            resolved.append(s)
        else:
            resolved.append(urllib.parse.urljoin(target, s))
    for url in sorted(set(resolved), key=rank)[:5]:
        text = _fetch(url)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _classify_handler(window: str) -> str:
    if _STRICT_RX.search(window):
        return "STRICT"
    if _ALLOWLIST_RX.search(window):
        return "ALLOWLIST_ARRAY"
    if _INCLUDES_RX.search(window):
        return "SUBSTRING"
    if _REGEX_RX.search(window):
        return "REGEX"
    if re.search(r"(?:e|event|msg)\.origin", window, re.IGNORECASE):
        return "UNKNOWN"
    return "MISSING"


def scan(target: str) -> PostMessageReport:
    report = PostMessageReport(target=target)
    text = _gather_bundle_text(target)
    if not text:
        report.findings.append(f"Could not fetch content from {target}.")
        return report

    counter = 1
    for m in _LISTENER_RX.finditer(text):
        # Take a 600-char window after the listener — that's typically the callback body
        start = max(0, m.start() - 40)
        end = min(len(text), m.end() + 600)
        window_text = text[start:end]
        classification = _classify_handler(window_text)

        excerpt = window_text.replace("\n", " ")
        if len(excerpt) > 200:
            excerpt = excerpt[:197] + "..."

        notes: List[str] = []
        if _EVAL_RX.search(window_text):
            notes.append("eval(event.data) detected — critical RCE primitive if origin check is weak.")
        if _FUNCTION_CTOR_RX.search(window_text):
            notes.append("new Function(event.data) detected — critical RCE primitive if origin check is weak.")

        report.handlers.append(Handler(
            handler_id=f"PM{counter:03d}",
            origin_validation=classification,
            excerpt=excerpt,
            notes=notes,
        ))
        counter += 1

    # Aggregate findings
    for h in report.handlers:
        if h.origin_validation == "MISSING":
            report.findings.append(
                f"finding_candidate: handler {h.handler_id} has NO origin check. Any cross-origin iframe can drive event.data."
            )
        elif h.origin_validation == "SUBSTRING":
            report.findings.append(
                f"finding_candidate: handler {h.handler_id} uses substring origin check (includes/indexOf/endsWith). "
                f"Likely bypassable via `trusted.com.attacker.com`-style domain."
            )
        elif h.origin_validation == "REGEX":
            report.findings.append(
                f"finding_candidate: handler {h.handler_id} uses regex origin check — frequently broken. "
                f"Verify the regex anchors against full origin string."
            )
        if h.notes:
            for n in h.notes:
                report.findings.append(f"{h.handler_id}: {n}")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = scan(args.target)
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Target: {report.target}")
        print(f"postMessage handlers: {len(report.handlers)}")
        by_class: Dict[str, int] = {}
        for h in report.handlers:
            by_class[h.origin_validation] = by_class.get(h.origin_validation, 0) + 1
        for k, n in sorted(by_class.items()):
            print(f"  {k}: {n}")
        if report.findings:
            print(f"\nFinding candidates ({len(report.findings)}):")
            for f in report.findings:
                print(f"  • {f}")
    return 0 if not report.findings else 1


if __name__ == "__main__":
    sys.exit(main())
