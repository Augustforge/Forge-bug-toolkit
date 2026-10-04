#!/usr/bin/env python3
"""
audit_pdf_parser.py — extract findings from audit-report PDFs/markdown.

Strategy:
- Use pdftotext if available, fallback to PyPDF2.
- For .md inputs — just read.
- Parse sections by severity headers (Critical/High/Medium/Low/Informational/Acknowledged).
- Flag findings marked "acknowledged" or "won't fix" — those are still exploitable.
- Flag fix references like "Fixed in commit XYZ" — verify against current code.

Output: structured JSON of findings + "still-open" candidates.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


SEVERITY_HEADER = re.compile(
    r"^\s*#{1,4}\s*(?:\d+\.?\s*)?(critical|high|medium|low|informational|acknowledged|gas)\s*(?:severity|issues?|findings?)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
FINDING_HEADER = re.compile(
    r"^\s*#{2,5}\s*(?:\[\w\-\d+\]\s*)?(.+)$",
    re.MULTILINE,
)
STATUS_PATTERNS = [
    ("fixed", re.compile(r"\b(?:fix(?:ed)?|resolved|addressed)\b", re.IGNORECASE)),
    ("acknowledged", re.compile(r"\backnowledg(?:ed|ement)\b", re.IGNORECASE)),
    ("wontfix", re.compile(r"\b(?:won'?t\s*fix|wont-fix|out\s+of\s+scope)\b", re.IGNORECASE)),
    ("partial", re.compile(r"\b(?:partial(?:ly)?)\b", re.IGNORECASE)),
    ("open", re.compile(r"\b(?:open|unresolved|not\s+fixed)\b", re.IGNORECASE)),
]


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        if shutil.which("pdftotext"):
            try:
                r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    return r.stdout
            except Exception:
                pass
        try:
            import PyPDF2
            text = []
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text() or "")
            return "\n".join(text)
        except Exception:
            print(f"[!] Cannot extract PDF — install pdftotext or PyPDF2", file=sys.stderr)
            return ""
    return ""


def parse_findings(text: str) -> list[dict]:
    findings = []
    severity_blocks = []
    last_pos = 0
    last_sev = None
    for m in SEVERITY_HEADER.finditer(text):
        if last_sev:
            severity_blocks.append((last_sev, last_pos, m.start()))
        last_sev = m.group(1).lower()
        last_pos = m.end()
    if last_sev:
        severity_blocks.append((last_sev, last_pos, len(text)))

    for sev, start, end in severity_blocks:
        block = text[start:end]
        for fm in FINDING_HEADER.finditer(block):
            title = fm.group(1).strip()
            if len(title) < 8 or len(title) > 180:
                continue
            ctx_start = fm.end()
            ctx_end = min(ctx_start + 600, len(block))
            ctx = block[ctx_start:ctx_end]
            status = "unknown"
            for sname, sregex in STATUS_PATTERNS:
                if sregex.search(ctx):
                    status = sname
                    break
            findings.append({
                "severity": sev,
                "title": title,
                "status": status,
                "context_excerpt": ctx[:200].strip(),
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Parse audit reports for open findings")
    ap.add_argument("--report", required=True, action="append", help="PDF/MD audit report path (repeatable)")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    all_findings = []
    for r in args.report:
        p = Path(r)
        if not p.exists():
            print(f"[!] Missing: {p}", file=sys.stderr)
            continue
        text = extract_text(p)
        if not text:
            continue
        fs = parse_findings(text)
        for f in fs:
            f["source_report"] = str(p)
        all_findings.extend(fs)

    open_or_acked = [f for f in all_findings if f["status"] in ("acknowledged", "wontfix", "partial", "open", "unknown")]

    if not args.quiet:
        print(f"[+] Parsed {len(all_findings)} findings from {len(args.report)} report(s)")
        by_status = {}
        for f in all_findings:
            by_status.setdefault(f["status"], 0)
            by_status[f["status"]] += 1
        for s, n in sorted(by_status.items(), key=lambda x: -x[1]):
            print(f"  {s:15} {n}")
        print(f"\n[!] STILL-OPEN candidates (acked/partial/wontfix/unknown): {len(open_or_acked)}")
        for f in open_or_acked[:15]:
            print(f"  [{f['severity']:8}] [{f['status']:12}] {f['title'][:80]}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "audit_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")
        md = "# Audit Findings Analysis\n\n## Still-open candidates\n\n"
        for f in open_or_acked:
            md += f"- **[{f['severity']}/{f['status']}]** {f['title']}\n  - Source: {f['source_report']}\n  - Excerpt: {f['context_excerpt']}\n\n"
        (out / "audit_findings.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
