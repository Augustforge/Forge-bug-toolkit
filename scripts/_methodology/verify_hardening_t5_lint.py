# -*- coding: utf-8 -*-
"""verify_hardening_t5_lint.py -- Plan 9 T5: verify-hardening methodology (Tier B).

Presence + parse lint proving Plan 9 T5 landed the five verify-hardening STEPS/entries into
`methodology/mythos_techniques.md` (T4, ONE verifier -- NOT 3 roles) and
`sessions/_methodology/submission_checklist.yaml`.

T5 items:
  (a) P10-clause -- hostile triager cannot invent a new angle to rescue a weak report + must pick
      the EXACT platform severity classification + verdict {PASS/BLOCK/DOWNGRADE/REJECT}.
  (b) fresh-runtime-T4 (standalone) -- re-provision runtime state (fresh fork block / burner
      nonce+allowance / fresh session) to kill residual-discovery-state PoCs.
  (c) precondition negative-control matrix -- falsify each STATED precondition one-at-a-time +
      surface unstated-but-required -> PASS/FAIL verifier-log.
  (d) self-steelman pre-T4 -- finder writes the strongest case AGAINST their own finding; the ONE
      verifier rebuts point-by-point.
  (e) submit-time dedup freshness recheck -- second dedup pass at submit (banked findings age).

FIRING is proved against `.sdd/plan9-hunter-parity/backups/*.p9t5.orig` (state BEFORE T5): the
presence-block MUST FAIL on the backups and PASS on the current files. Same discipline as
web2_antifp_lint.py. fail-open n/a -- this is an offline lint.
"""
import os
import sys

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt

MYTHOS = os.path.join(ROOT, "methodology", "mythos_techniques.md")
CHECKLIST = os.path.join(ROOT, "sessions", "_methodology",
                         "submission_checklist.yaml")
BACKUPS = os.path.join(ROOT, "methodology", "plans", ".sdd",
                       "plan9-hunter-parity", "backups")
MYTHOS_ORIG = os.path.join(BACKUPS, "mythos_techniques.md.p9t5.orig")
CHECKLIST_ORIG = os.path.join(BACKUPS, "submission_checklist.yaml.p9t5.orig")

# Tokens that T5 must introduce into mythos_techniques.md (T4 STEPS, ONE verifier).
MYTHOS_TOKENS = (
    "STEP 1.5 — SELF-STEELMAN",
    "P10 — HOSTILE-TRIAGER STANCE",
    "STEP 2.6 — FRESH-RUNTIME RE-PROVISION",
    "STEP 2.7 — PRECONDITION NEGATIVE-CONTROL MATRIX",
    "SUBMIT-TIME FRESHNESS RE-CHECK",
)
# New checklist ids T5 must introduce (must parse + be present).
CHECKLIST_IDS = (
    "p10-hostile-triager-classification",
    "precondition-negative-control-matrix",
    "submit-time-dedup-freshness",
)


def _read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def presence_results(mythos_text, checklist_text):
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    for tok in MYTHOS_TOKENS:
        check("mythos: %r present" % tok, tok in mythos_text)
    # P3 guard: still ONE verifier, not three (do not restructure into 3 roles).
    check("mythos: 'ONE verifier, not three' preserved (P3)", "ONE verifier, not three" in mythos_text)
    for cid in CHECKLIST_IDS:
        check("checklist: 'id: %s' present" % cid, ("id: %s" % cid) in checklist_text)
    return results


def parse_ok(checklist_text):
    import yaml
    docs = list(yaml.safe_load_all(checklist_text))
    return len(docs) >= 1


def main():
    mythos = _read(MYTHOS)
    checklist = _read(CHECKLIST)
    if not mythos or not checklist:
        print("[FAIL] target file(s) missing/empty")
        sys.exit(1)

    print("=== VERIFY-HARDENING T5 LINT (Plan 9) ===\n")

    # (1) YAML parse
    try:
        p_ok = parse_ok(checklist)
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] submission_checklist.yaml does NOT parse: %s" % exc)
        sys.exit(1)
    print(("  [PASS] " if p_ok else "  [FAIL] ") + "submission_checklist.yaml parses (yaml.safe_load_all)")

    # (2) PRESENCE on current (all must PASS)
    print("\n-- PRESENCE: CURRENT files (all must PASS) --")
    cur = presence_results(mythos, checklist)
    for n, ok in cur:
        print(("  [PASS] " if ok else "  [FAIL] ") + n)
    cur_ok = sum(1 for _, ok in cur if ok)
    print("  %d/%d" % (cur_ok, len(cur)))

    # (3) FIRING: backups (pre-T5) must FAIL presence
    print("\n-- FIRING: .p9t5.orig backups (must FAIL presence) --")
    have_backups = os.path.exists(MYTHOS_ORIG) and os.path.exists(CHECKLIST_ORIG)
    firing = False
    if have_backups:
        pre = presence_results(_read(MYTHOS_ORIG), _read(CHECKLIST_ORIG))
        pre_ok = sum(1 for _, ok in pre if ok)
        firing = any(not ok for _, ok in pre)
        print("  backup presence: %d/%d PASS (expected < %d)" % (pre_ok, len(pre), len(pre)))
        print(("  [PASS] " if firing else "  [FAIL] ")
              + "FIRING proven: the backup fails at least one presence check")
    else:
        print("  [FAIL] .p9t5.orig backups not found -- FIRING not proven")

    all_cur_pass = cur_ok == len(cur)
    overall = p_ok and all_cur_pass and have_backups and firing
    total_ok = int(p_ok) + cur_ok + int(firing)
    total = 1 + len(cur) + 1
    print("\n=== TOTAL: %d/%d -- %s ===" % (total_ok, total, "PASS" if overall else "FAIL"))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
