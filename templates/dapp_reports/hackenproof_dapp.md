<!--
HackenProof dApp report template (per [[feedback-hackenproof-format]])

7 fields in this exact order:
  1. Target
  2. Category
  3. Severity level
  4. Title
  5. Vulnerability details
  6. Validation steps
  7. Supporting files / PoC

Critical rules:
- Voice: 1st person OR 3rd-passive. NEVER "we", NEVER mention AI/Playwright/automation/agent/Claude.
- Supporting files: list only, NO content duplication.
- HTML files NOT accepted — use .md with embedded code block, or .zip.
- WAF-safe: no literal exploit signatures (eth_sendTransaction, approve(MAX_UINT256)),
  no stack traces verbatim, no nested JSON, no opacity:0/pointer-events:auto literals.

Severity:
- Critical = no user action / private key leak / mass auth bypass
- High = user-click + significant fund loss (SynFutures class)
- Medium = social engineering required + meaningful impact
- Low = PII / hygiene / UX DoS
-->

## 1. Target

{{TARGET}}

## 2. Category

{{CATEGORY}}

## 3. Severity level

{{SEVERITY}}

## 4. Title

{{TITLE}}

## 5. Vulnerability details

{{VULN_DETAILS}}

## 6. Validation steps

{{VALIDATION_STEPS}}

## 7. Supporting files / PoC

Attached files:

{{SUPPORTING_FILES}}

<!--
After fill, run BOTH linters before submit:
  python3 scripts/submission/waf_safe_linter.py --file <this file>
  python3 scripts/submission/voice_tone_linter.py --file <this file>

If Cloudflare WAF returns 403 even after linter pass:
  python3 scripts/submission/ray_id_support_handler.py \
    --platform hackenproof --ray-id <ID> --report-id <ID> --output support.md
-->
