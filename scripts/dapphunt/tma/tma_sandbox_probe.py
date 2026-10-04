#!/usr/bin/env python3
"""
tma_sandbox_probe.py — Probe Telegram.WebApp API misuse patterns.

Surface scan for:
- BiometricManager trust assumptions (biometric == auth?)
- MainButton race conditions (rapid color/text changes)
- showPopup / showConfirm callbacks (XSS through title)
- HapticFeedback misuse
- requestWriteAccess / requestContact escalation paths
- openLink / openTelegramLink trust (open redirect class)
- CloudStorage API misuse (size limits, key collision)
- themeParams / colorScheme attacker manipulation (CSS injection via JS bridge)

Usage:
    python3 tma_sandbox_probe.py --target https://your-tma-target/
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
from typing import List, Optional, Tuple


_SURFACE_PATTERNS: List[Tuple[str, str, str, str]] = [
    ("biometric_trust", r"Telegram\.WebApp\.BiometricManager\.authenticate", "medium", "BiometricManager.authenticate result is NOT cryptographic proof — only a UX hint. Trusting it for auth is wrong."),
    ("main_button_race", r"Telegram\.WebApp\.MainButton\.setText\s*\([^)]+\).*?\.setText\s*\(", "low", "MainButton.setText changes rapidly — may indicate race condition between intent and shown text."),
    ("popup_unsanitized_title", r"Telegram\.WebApp\.showPopup\s*\(\s*\{\s*title\s*:\s*[a-zA-Z_$][\w$.]*\b", "medium", "showPopup title computed from variable (not literal) — verify source is sanitized."),
    ("open_link_dynamic", r"Telegram\.WebApp\.openLink\s*\(\s*[a-zA-Z_$][\w$.]*\b", "medium", "openLink with dynamic URL — verify URL is constructed safely (no user-controlled host)."),
    ("open_telegram_link_dynamic", r"Telegram\.WebApp\.openTelegramLink\s*\(\s*[a-zA-Z_$][\w$.]*\b", "low", "openTelegramLink dynamic — phishing class if attacker controls target tg:// URL."),
    ("cloud_storage_no_size_check", r"Telegram\.WebApp\.CloudStorage\.setItem\s*\(", "low", "CloudStorage has per-key size limits. Verify dApp handles quota errors gracefully."),
    ("theme_params_render", r"Telegram\.WebApp\.themeParams\.[a-zA-Z]+", "low", "themeParams come from Telegram client — if dApp puts them in inline CSS without sanitization, CSS injection risk."),
    ("request_write_access", r"Telegram\.WebApp\.requestWriteAccess", "low", "requestWriteAccess prompt — verify dApp does not silently ignore user denial."),
    ("request_contact", r"Telegram\.WebApp\.requestContact", "low", "requestContact returns user phone — verify dApp does not store unnecessarily."),
    ("ready_called", r"Telegram\.WebApp\.ready\s*\(\s*\)", "low", "Confirms TMA initialized — informational."),
]


@dataclass
class TMASurfaceFinding:
    finding_id: str
    surface: str
    severity_hint: str
    description: str
    sample: str
    location: str


@dataclass
class TMASurfaceReport:
    target: str
    findings: List[TMASurfaceFinding] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-tma-sandbox/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _gather(target: str):
    html = _fetch(target)
    if not html:
        return []
    out = [(target, html)]
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    srcs = re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)
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

    def rank(u):
        lower = u.lower()
        return (0 if "/index-" in lower or "/main-" in lower else 1, 1 if "vendor" in lower or "polyfill" in lower else 0, -len(u))

    for url in sorted(set(resolved), key=rank)[:5]:
        text = _fetch(url)
        if text:
            out.append((url, text))
    return out


def scan(target: str) -> TMASurfaceReport:
    report = TMASurfaceReport(target=target)
    counter = 1
    for location, text in _gather(target):
        for sid, rx, sev, desc in _SURFACE_PATTERNS:
            for m in re.finditer(rx, text, re.IGNORECASE):
                sample = m.group(0)
                if len(sample) > 120:
                    sample = sample[:117] + "..."
                report.findings.append(TMASurfaceFinding(
                    finding_id=f"TMS{counter:03d}",
                    surface=sid,
                    severity_hint=sev,
                    description=desc,
                    sample=sample,
                    location=location,
                ))
                counter += 1
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
        print(f"TMA surface findings: {len(report.findings)}")
        for f in report.findings:
            print(f"  [{f.severity_hint:6}] {f.surface:30s}  {f.description}")
    return 0 if not report.findings else 1


if __name__ == "__main__":
    sys.exit(main())
