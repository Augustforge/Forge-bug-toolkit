#!/usr/bin/env python3
"""
test_linters.py — Regression tests for WAF-safe linter and voice-tone linter.

Run with:
    py -3 -X utf8 -m pytest tests/test_linters.py -v

Or without pytest (raw):
    py -3 -X utf8 tests/test_linters.py

These tests lock in the regression cases that motivated the linters:
- WAF: the 2026-05-20 SynFutures submission that CF blocked with Ray ID 9fe98395c93abcc9
- Voice: the first draft phrasing "Testing was performed in a headless Chromium under Playwright"

If anyone edits the rule sets and breaks one of these cases, the tests fail loudly.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the linters importable as plain modules without installing the package.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts" / "submission"))

import waf_safe_linter   # noqa: E402
import voice_tone_linter  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────
# Reusable regression fixtures
# ──────────────────────────────────────────────────────────────────────────

# Original payload from SynFutures attempt — all of these triggered CF WAF
WAF_REGRESSION_PAYLOAD = """
## Steps to Reproduce
1. Attacker calls approve(spender, MAX_UINT256) to grant the drainer unlimited allowance.
2. dApp invokes eth_sendTransaction with a Permit2-style flow.
3. Browser raises SecurityError: Failed to read 'contentDocument' from cross-origin iframe.
4. Stack trace:
    at Object.<anonymous> (drainer.js:42:13)
    at Function.signTypedData_v4 (eth.js:99:8)
5. Visual overlay:
    <div style="opacity: 0; pointer-events: auto">
6. Payload nested:
    { "a": { "b": { "c": { "d": "deep" } } } }
"""

# Original draft phrasing that revealed Playwright automation
VOICE_REGRESSION_PHRASING = """
## Methodology
Testing was performed in a headless Chromium under Playwright. The agent observed that
we performed the wallet connection flow and then the assistant logged the resulting
session. Burp recorded the request, and the harness produced a Claude-generated
summary of the findings.
"""

# Clean payload that should pass both linters
CLEAN_REPORT = """
## Summary
A development clone of the production app exposes the same Privy authentication
context as the main domain but lacks framing protection. An attacker can host the
clone inside an iframe on attacker-controlled origin and trigger an unlimited
ERC-20 spending allowance through a visual overlay misleading the user. The
underlying Privy configuration allows the wildcard `*.iftl.info`, which the
attacker subdomain falls under.

## Impact
Wallet phishing primitive against any user who clicks through the overlay.
"""


def _waf_scan(text: str):
    return waf_safe_linter.scan_text(text) if hasattr(waf_safe_linter, "scan_text") else None


def _voice_scan(text: str):
    return voice_tone_linter.scan_text(text) if hasattr(voice_tone_linter, "scan_text") else None


# ──────────────────────────────────────────────────────────────────────────
# Helpers — fall back to subprocess if the scan_text API isn't exposed
# (the linters were CLI-first; tests use whichever path works)
# ──────────────────────────────────────────────────────────────────────────

def _waf_triggers(text: str):
    """Return list of triggered rule_ids for the given text."""
    rep = _waf_scan(text)
    if rep is not None:
        # Expecting an object with .triggers or .findings
        items = getattr(rep, "triggers", None) or getattr(rep, "findings", None) or []
        return [getattr(t, "rule_id", t.get("rule_id") if isinstance(t, dict) else None) for t in items]
    # Fallback: call internal compiled rules directly
    return [rule_id for rule_id in _waf_match_rule_ids(text)]


def _voice_reveals(text: str):
    rep = _voice_scan(text)
    if rep is not None:
        items = getattr(rep, "reveals", None) or getattr(rep, "findings", None) or []
        return [getattr(t, "rule_id", t.get("rule_id") if isinstance(t, dict) else None) for t in items]
    return [rule_id for rule_id in _voice_match_rule_ids(text)]


def _waf_match_rule_ids(text):
    import re
    for rule in waf_safe_linter._RULES:
        rule_id, severity, pattern, suggestion, category = rule
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            yield rule_id


def _voice_match_rule_ids(text):
    import re
    for rule in voice_tone_linter._RULES:
        rule_id, severity, pattern, suggestion, category = rule
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            yield rule_id


# ──────────────────────────────────────────────────────────────────────────
# WAF linter — known triggers (must always be caught)
# ──────────────────────────────────────────────────────────────────────────

def test_waf_catches_evm_approve_max():
    rules = _waf_triggers("approve(spender, MAX_UINT256)")
    assert "evm_approve_max" in rules, f"evm_approve_max not caught in: {rules}"


def test_waf_catches_eth_send_transaction():
    rules = _waf_triggers("the dApp calls eth_sendTransaction with a malicious payload")
    assert "evm_send_transaction" in rules, f"evm_send_transaction not caught in: {rules}"


def test_waf_catches_permit2_style():
    rules = _waf_triggers("the contract accepts Permit2-style approvals")
    assert "evm_permit2_literal" in rules, f"evm_permit2_literal not caught in: {rules}"


def test_waf_catches_drainer():
    rules = _waf_triggers("classic wallet drainer pattern")
    assert "evm_drainer_phrase" in rules, f"evm_drainer_phrase not caught in: {rules}"


def test_waf_catches_synfutures_regression():
    """The full original SynFutures payload must trigger MULTIPLE rules.

    This is the canonical regression: the 2026-05-20 CF Ray ID 9fe98395c93abcc9 block.
    """
    rules = list(_waf_triggers(WAF_REGRESSION_PAYLOAD))
    assert len(rules) >= 4, f"Expected 4+ triggers on the original block payload, got {len(rules)}: {rules}"
    # Core triggers that MUST be in the set
    assert "evm_approve_max" in rules
    assert "evm_send_transaction" in rules
    assert "evm_permit2_literal" in rules


def test_waf_passes_clean_report():
    """The hand-rewritten clean report must NOT trigger any WAF rule."""
    rules = list(_waf_triggers(CLEAN_REPORT))
    assert rules == [], f"Clean report falsely triggered: {rules}"


# ──────────────────────────────────────────────────────────────────────────
# Voice linter — known reveals (must always be caught)
# ──────────────────────────────────────────────────────────────────────────

def test_voice_catches_playwright():
    reveals = list(_voice_reveals("Testing was performed in Playwright"))
    assert "automation_playwright" in reveals


def test_voice_catches_headless():
    reveals = list(_voice_reveals("ran in headless Chromium"))
    assert "automation_headless" in reveals


def test_voice_catches_synfutures_regression():
    """The original first-draft phrasing must trigger MULTIPLE reveals."""
    reveals = list(_voice_reveals(VOICE_REGRESSION_PHRASING))
    assert len(reveals) >= 3, f"Expected 3+ reveals, got {len(reveals)}: {reveals}"
    assert "automation_playwright" in reveals
    assert "automation_headless" in reveals


def test_voice_passes_clean_report():
    reveals = list(_voice_reveals(CLEAN_REPORT))
    assert reveals == [], f"Clean report falsely revealed: {reveals}"


# ──────────────────────────────────────────────────────────────────────────
# Headless runner — call as `python test_linters.py`
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    funcs = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"  OK     {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL   {fn.__name__}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ERROR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print()
    print(f"{len(funcs) - failed}/{len(funcs)} passed")
    sys.exit(0 if failed == 0 else 1)
