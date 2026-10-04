#!/usr/bin/env python3
"""
ray_id_support_handler.py — Generate a support escalation request when Cloudflare
WAF blocks a bug bounty submission.

Background:
On 2026-05-20, HackenProof submission was blocked by CF WAF with Ray ID
9fe98395c93abcc9. The fix path was: (a) rewrite payload WAF-safe, (b) if still
blocked, message HackenProof support with the Ray ID so they can whitelist /
investigate. This script generates the support template.

Usage:
    python3 ray_id_support_handler.py \
        --platform hackenproof \
        --ray-id 9fe98395c93abcc9 \
        --report-id SYNFUDAP-51 \
        --output support_request.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


PLATFORM_SUPPORT_CHANNELS = {
    "hackenproof": {
        "name": "HackenProof",
        "preferred": "Intercom widget (bottom-right on dashboard.hackenproof.com)",
        "email": "support@hackenproof.com",
        "api_path_template": "/api/internal/user/reports/{report_id}",
    },
    "immunefi": {
        "name": "Immunefi",
        "preferred": "support@immunefi.com",
        "email": "support@immunefi.com",
        "api_path_template": "/api/reports/{report_id}",
    },
    "cantina": {
        "name": "Cantina",
        "preferred": "support@cantina.xyz or Discord ticket",
        "email": "support@cantina.xyz",
        "api_path_template": "/api/v1/findings/{report_id}",
    },
    "hackerone": {
        "name": "HackerOne",
        "preferred": "support@hackerone.com or in-platform ticket",
        "email": "support@hackerone.com",
        "api_path_template": "/reports/{report_id}",
    },
    "bugcrowd": {
        "name": "Bugcrowd",
        "preferred": "support@bugcrowd.com",
        "email": "support@bugcrowd.com",
        "api_path_template": "/submissions/{report_id}",
    },
}


def build_template(
    platform: str,
    ray_id: str,
    report_id: str,
    extra_context: Optional[str] = None,
) -> str:
    meta = PLATFORM_SUPPORT_CHANNELS.get(platform)
    if not meta:
        raise ValueError(f"Unsupported platform: {platform}")

    api_path = meta["api_path_template"].format(report_id=report_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    extra_block = ""
    if extra_context:
        extra_block = f"\nAdditional context:\n{extra_context.strip()}\n"

    template = f"""# Support request — Cloudflare WAF blocking submission

**Platform:** {meta['name']}
**Report ID:** {report_id}
**Cloudflare Ray ID:** {ray_id}
**Date:** {today}
**Preferred channel:** {meta['preferred']}
**Fallback email:** {meta['email']}

---

## Message body (ready to paste)

Hi {meta['name']} team,

I'm hitting a Cloudflare 403 Forbidden when trying to submit my report `{report_id}`.
The PATCH request to `{api_path}` is intercepted by your Cloudflare WAF and never
reaches the backend.

The report body contains technical content describing a Web3 frontend vulnerability
(EVM signatures, browser security headers, console error messages). Cloudflare's
generic WAF rules appear to interpret some of those technical descriptions as
attack payloads and block them.

Could you either:
1. Whitelist my account / IP for the duration of this submission, or
2. Confirm which payload pattern triggered the block so I can rephrase, or
3. Suggest the right way to submit Web3-technical reports through your platform.

**Cloudflare Ray ID:** `{ray_id}`
**Report ID:** `{report_id}`
{extra_block}
Thanks,
"""
    return template


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--platform", required=True, choices=list(PLATFORM_SUPPORT_CHANNELS))
    parser.add_argument("--ray-id", required=True, help="Cloudflare Ray ID from the 403 response")
    parser.add_argument("--report-id", required=True, help="Platform-side report ID (e.g. SYNFUDAP-51)")
    parser.add_argument("--extra", type=str, default=None, help="Optional extra context to append")
    parser.add_argument("--output", type=Path, help="Output markdown path")
    args = parser.parse_args(argv)

    template = build_template(args.platform, args.ray_id, args.report_id, args.extra)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(template, encoding="utf-8")
        print(f"Support template written: {args.output}")
    else:
        print(template)

    return 0


if __name__ == "__main__":
    sys.exit(main())
