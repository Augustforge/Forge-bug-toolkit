# -*- coding: utf-8 -*-
"""web2_antifp_lint.py -- FDE Plan 5, Task 10: anti-FP gates + Pitfalls (anti-false-negative) +
403/WAF class + remnant classes in the web2 pre-submit / T4 branch.

Owner = `sessions/_methodology/submission_checklist.yaml` (already the T4-verify / pre-submit checklist;
the auto_invalid/severity_cap/quality_required/confidence_gates sections are of the same nature as the new
web2 sections). `failure_modes.md` (rejected-report log, a different kind of artifact -- NOT a prescriptive
checklist) is untouched.

Two blocks of checks:
  1. UNIT on the coded rules -- `valid_marker`/`sufficient_sample` from `web2_antifp.py`.
  2. PRESENCE -- the sections `web2_anti_fp` (4 rules) / `web2_403_waf_bypass` (403-bypass class) /
     `web2_remnant_classes` (4 classes) / `web2_pitfalls` (>=3 anti-false-negative sub-sections)
     are present in submission_checklist.yaml.

FIRING is proven against `.sdd/backups/submission_checklist.yaml.pretask10.orig` (state BEFORE
Task 10) -- the PRESENCE block must FAIL there and PASS on the current file. The unit block does not need
FIRING (the rules are coded in a separate new module -- on the backup it simply would not import; here
we prove it by the very fact that the functions exist and behave per spec).
"""
import os
import sys

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt

sys.path.insert(0, os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "_methodology"))

CHECKLIST = os.path.join(ROOT, "bug-bounty-toolkit", "sessions", "_methodology",
                          "submission_checklist.yaml")
CHECKLIST_PRETASK10 = os.path.join(ROOT, "bug-bounty-toolkit", "methodology", "plans", ".sdd",
                                    "backups", "submission_checklist.yaml.pretask10.orig")

ANTI_FP_IDS = ("marker-discipline", "body-diff-rule", "statistical-sample-rule", "shell-loop-ban")
REMNANT_IDS = ("dns-rebinding", "backslash-powered-scanning", "keyhacks", "origin-ip-behind-cdn")
PITFALL_IDS = (
    "bola-method-coverage",
    "uuid-mistaken-for-protection",
    "forwarded-header-403-bypass",
    "bfla-jwt-claim-vs-server",
)


def _read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def presence_lint(text):
    """PRESENCE checks over the text of submission_checklist.yaml. Returns [(name, bool)]."""
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    # (1) 4 anti-FP rules (id: ... lines inside web2_anti_fp)
    for rule_id in ANTI_FP_IDS:
        check("anti-FP rule '%s' present" % rule_id, ("id: %s" % rule_id) in text)

    # (2) 403/WAF-bypass as a separate class
    check("section web2_403_waf_bypass present", "web2_403_waf_bypass:" in text)
    check("403-bypass mentioned as a class", "403-bypass" in text or "403/WAF-bypass" in text
          or "403/WAF-BYPASS" in text)
    check("id: waf-vs-auth-403 present", "id: waf-vs-auth-403" in text)
    # The Russian "НЕ classify_error" below is matched against the yaml text ("NOT classify_error") -- kept verbatim.
    check("classify_http integration mentioned (NOT classify_error)",
          "classify_http" in text and "НЕ classify_error" in text)

    # (3) 4 remnant classes
    for remnant_id in REMNANT_IDS:
        check("remnant class '%s' present" % remnant_id, ("id: %s" % remnant_id) in text)

    # (4) Pitfalls (>=3 anti-false-negative sub-sections) -- section + >=3 specific ids
    check("section web2_pitfalls present", "web2_pitfalls:" in text)
    # The Russian literals below are matched against the yaml text ("SEPARATE mechanism" / "anti-false-negative") -- kept verbatim.
    check("web2_pitfalls marked as a SEPARATE mechanism from anti-FP (anti-false-negative)",
          "ОТДЕЛЬНЫЙ механизм" in text and "false-negative" in text.lower()
          or "анти-false-negative" in text)
    present_pitfalls = [pid for pid in PITFALL_IDS if ("id: %s" % pid) in text]
    check("Pitfalls: >=3 sub-sections present (%d/%d found: %s)"
          % (len(present_pitfalls), len(PITFALL_IDS), ", ".join(present_pitfalls)),
          len(present_pitfalls) >= 3)

    return results


def unit_lint():
    """Unit checks on the coded rules (web2_antifp.py). Returns [(name, bool)]."""
    from web2_antifp import valid_marker, sufficient_sample

    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    check("valid_marker('test') == False", valid_marker("test") is False)
    check("valid_marker('aB3xK9mQ') == True", valid_marker("aB3xK9mQ") is True)
    check("valid_marker('javascript') == False (dictionary word, also >=8)",
          valid_marker("javascript") is False)
    check("valid_marker('AAAAAAAA') == False (monotonous, long)",
          valid_marker("AAAAAAAA") is False)
    check("valid_marker('short1') == False (<8 chars)", valid_marker("short1") is False)
    check("valid_marker(None) == False (fail-closed on garbage)", valid_marker(None) is False)

    check("sufficient_sample(5) == 'INSUFFICIENT'", sufficient_sample(5) == "INSUFFICIENT")
    check("sufficient_sample(12) != 'INSUFFICIENT'", sufficient_sample(12) != "INSUFFICIENT")
    check("sufficient_sample(10) != 'INSUFFICIENT' (boundary n=10 inclusive)",
          sufficient_sample(10) != "INSUFFICIENT")
    check("sufficient_sample(9) == 'INSUFFICIENT' (boundary n=9)",
          sufficient_sample(9) == "INSUFFICIENT")
    check("sufficient_sample('garbage') == 'INSUFFICIENT' (fail-open toward unproven)",
          sufficient_sample("garbage") == "INSUFFICIENT")

    return results


def main():
    all_results = []

    print("=== WEB2 ANTI-FP LINT (FDE Plan 5, Task 10) ===\n")

    print("-- Unit: web2_antifp.py (valid_marker / sufficient_sample) --")
    u_results = unit_lint()
    for n, p in u_results:
        print(("  [PASS] " if p else "  [FAIL] ") + n)
    print("  %d/%d\n" % (sum(1 for _, p in u_results if p), len(u_results)))
    all_results.extend(u_results)

    current_text = _read(CHECKLIST)
    if not current_text:
        print("[FAIL] %s not found or empty" % CHECKLIST)
        sys.exit(1)

    print("-- PRESENCE: CURRENT submission_checklist.yaml (all must PASS) --")
    cur_results = presence_lint(current_text)
    for n, p in cur_results:
        print(("  [PASS] " if p else "  [FAIL] ") + n)
    cur_ok = sum(1 for _, p in cur_results if p)
    print("  %d/%d\n" % (cur_ok, len(cur_results)))
    all_results.extend(cur_results)

    pretask10_exists = os.path.exists(CHECKLIST_PRETASK10)
    firing_proved = False
    if pretask10_exists:
        pre_text = _read(CHECKLIST_PRETASK10)
        print("-- PRESENCE: .sdd/backups/submission_checklist.yaml.pretask10.orig "
              "(at least some must FAIL) --")
        pre_results = presence_lint(pre_text)
        for n, p in pre_results:
            print(("  [PASS] " if p else "  [FAIL] ") + n)
        pre_ok = sum(1 for _, p in pre_results if p)
        print("  %d/%d\n" % (pre_ok, len(pre_results)))
        firing_proved = any(not p for _, p in pre_results)
        print(("  [PASS] " if firing_proved else "  [FAIL] ")
              + "FIRING proven: the pretask10 backup fails at least one presence check\n")
    else:
        print("  [FAIL] backup %s not found -- FIRING not proven\n" % CHECKLIST_PRETASK10)

    all_current_pass = cur_ok == len(cur_results)
    total_ok = sum(1 for _, p in all_results if p)
    total = len(all_results)

    overall_ok = (
        all_current_pass
        and all(p for _, p in u_results)
        and pretask10_exists
        and firing_proved
    )

    print("=== TOTAL: %d/%d green -- %s ===" % (total_ok, total, "PASS" if overall_ok else "FAIL"))
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
