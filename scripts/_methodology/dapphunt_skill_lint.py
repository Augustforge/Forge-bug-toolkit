# -*- coding: utf-8 -*-
"""Presence-lint: `.claude/commands/dapphunt.md` FDE Plan 4 Task 9+10 (§3/§3.4/§4.1, §8.4/§9/§11) —
Task 9: Phase P-SM (surface-trust model first, divergence-first) + rewritten `MODEL: N/A` prose
(a web-profile model is MANDATORY for a normal dApp, N/A only for a pure static site) +
Phase 6 R1 injection (`eip1193_mock_provider.js` BEFORE `browser_navigate`).
Task 10: workflow reorder (AUGMENT existing phases, NOT a teardown) — Phase 5 Cross-Clone Differential
(`clone_diff.md` with the full session path), Phase 6 Runtime Observation Harness (keeping wallet-audit),
Reference Files of the new artifacts (`runtime_harness`/`web_severity`/`clone_diff.md`), P-SM sync in
Phase Budget Summary + Cognitive Framework.
Task 10 review-fix [Important]: `dataflow_map.md` was a dangling reference (mentioned in Reference Files,
but `display_vs_reality_grep.py` in Phase 2.5 Step 2 was called without `--md-out` — the artifact was never
created). Phase 2.5 Step 2 now carries `--md-out bug-bounty-toolkit/sessions/$DOMAIN/dataflow_map.md`
with the full session path (symmetric to Phase 5 `clone_diff.md`); check (l) gates the regression.

Proves FIRING, not a no-op: all checks are run BOTH against the CURRENT file (must PASS) AND
against a baseline backup of the state BEFORE the corresponding task (at least some checks must FAIL).
Task 9 checks (a)-(f) are compared with `.sdd/backups/dapphunt.md.orig` (pre-Task-9). Task 10 checks (g)-(k)
are compared with `.sdd/backups/dapphunt.md.pretask10.orig` (pre-Task-10, i.e. the state right AFTER
Task 9 — Phase P-SM is already there, but not a single Task-10 addition yet). A gate that passes on
BOTH files proves nothing.
"""
import os
import re
import sys

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt

DAPPHUNT_MD = os.path.join(ROOT, ".claude", "commands", "dapphunt.md")
DAPPHUNT_MD_ORIG = os.path.join(ROOT, "bug-bounty-toolkit", "methodology", "plans", ".sdd",
                                 "backups", "dapphunt.md.orig")
DAPPHUNT_MD_PRETASK10 = os.path.join(ROOT, "bug-bounty-toolkit", "methodology", "plans", ".sdd",
                                      "backups", "dapphunt.md.pretask10.orig")

TRUST_AXES = [
    "origin-trust",
    "signature-integrity",
    "data-source-trust",
    "session-auth",
    "asset-identity",
    "clone-parity",
]

# Marker phrases of the three T10/§3.4 operators (same in spirit as `J-M` in /deephunt).
# NOTE: the Cyrillic markers below are kept as-is — they are matched against the Russian-language skill file (logic).
OPERATOR_MARKERS = [
    "На всех ли",       # operator 1: "on all routes/components/clones/chains?" ("Is it on all of them?")
    "Канонический механизм или самодел",  # operator 2 ("Canonical mechanism or home-grown?")
    "pred:",             # operator 3: pred against fact (needs at least one pred: besides the operator-2 fingerprint)
]

FORBIDDEN_SENTINEL = "SURFACE-MODEL:"
OLD_MODEL_NA_LINE = "MODEL: N/A — dapphunt frontend"

# Task-10 new-artifact markers (10b Reference Files).
TASK10_REF_MARKERS = ["runtime_harness", "web_severity", "clone_diff.md"]

CLONE_DIFF_SESSION_PATH = "--md-out bug-bounty-toolkit/sessions/$DOMAIN/clone_diff.md"
DATAFLOW_MAP_SESSION_PATH = "--md-out bug-bounty-toolkit/sessions/$DOMAIN/dataflow_map.md"


def _phase_section(text, phase_num, next_phase_num):
    """Cuts out the text of phase `phase_num` from its `### Phase N` heading to the heading
    `### Phase next_phase_num` (exclusive). Searches by the phase NAME (number), not by line number —
    lines shifted after Task 9, a brief requirement. Returns "" if the heading is not found
    (the phase is absent in this version of the file — the calling check then honestly FAILs)."""
    m = re.search(r"###\s*Phase\s*%s\b" % re.escape(str(phase_num)), text)
    if not m:
        return ""
    start = m.start()
    m2 = re.search(r"###\s*Phase\s*%s\b" % re.escape(str(next_phase_num)), text[start:])
    if not m2:
        return text[start:]
    return text[start:start + m2.start()]


def _section(text, start_marker, end_marker=None):
    """Cuts out the text between the first occurrence of `start_marker` and the next `end_marker` (exclusive),
    or to the end of the file if `end_marker` is not given / not found after `start_marker`. A literal
    substring search (not regex) — section headings are stable strings ('## Reference Files' etc.)."""
    i = text.find(start_marker)
    if i == -1:
        return ""
    if end_marker:
        j = text.find(end_marker, i + len(start_marker))
        if j != -1:
            return text[i:j]
    return text[i:]


def lint(text):
    """Runs all presence checks over the file text. Returns a list of (name, bool, detail)."""
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    # (a) Phase P-SM is present
    check("(a) '### Phase P-SM' heading is present", "### Phase P-SM" in text)

    # (b) 6 trust axes are listed (somewhere in the file, usually inside P-SM)
    missing_axes = [ax for ax in TRUST_AXES if ax not in text]
    check("(b) all 6 trust axes are listed (%s)" % ", ".join(TRUST_AXES),
          len(missing_axes) == 0,
          ("missing: %s" % ", ".join(missing_axes)) if missing_axes else "")

    # (c) 3 operators are mentioned
    missing_ops = [m for m in OPERATOR_MARKERS if m not in text]
    check("(c) 3 operators are mentioned (%s)" % ", ".join(OPERATOR_MARKERS),
          len(missing_ops) == 0,
          ("missing markers: %s" % ", ".join(missing_ops)) if missing_ops else "")

    # (d) the old MODEL:N/A-as-default line is NO LONGER present
    check("(d) old default line '%s' is absent (rewritten)" % OLD_MODEL_NA_LINE,
          OLD_MODEL_NA_LINE not in text)

    # (e) Phase 6 carries "inject BEFORE navigate" / init-script-browser_evaluate-before-browser_navigate
    has_navigate_order = (
        "browser_navigate" in text
        and ("browser_evaluate" in text or "init-script" in text)
        and ("ДО" in text and "browser_navigate" in text)  # "ДО" = "BEFORE" (Cyrillic marker kept: matches the Russian skill file)
    )
    # more precisely: look for the pattern "ДО ... browser_navigate" itself within a single phrase
    r1_marker = "ДО** `browser_navigate`" in text or "ДО `browser_navigate`" in text
    check("(e) Phase 6 carries the instruction 'inject BEFORE browser_navigate'",
          has_navigate_order and r1_marker)

    # (f) the forbidden sentinel SURFACE-MODEL: did not appear
    check("(f) forbidden sentinel '%s' is absent" % FORBIDDEN_SENTINEL,
          FORBIDDEN_SENTINEL not in text)

    # ── Task 10 checks (g)-(k) ──────────────────────────────────────────────

    # (g) Reference Files contains the new Task-10 artifacts
    ref_section = _section(text, "## Reference Files")
    missing_refs = [m for m in TASK10_REF_MARKERS if m not in ref_section]
    check("(g) Reference Files carries %s" % ", ".join(TASK10_REF_MARKERS),
          len(missing_refs) == 0,
          ("missing: %s" % ", ".join(missing_refs)) if missing_refs else "")

    # (h) Phase 5 carries the clone_diff.md session path AND the iframe/DNS content is preserved (augment, not wipe)
    phase5 = _phase_section(text, 5, 6)
    low5 = phase5.lower()
    check("(h) Phase 5: '%s' + iframe/DNS content preserved" % CLONE_DIFF_SESSION_PATH,
          bool(phase5) and CLONE_DIFF_SESSION_PATH in phase5 and "iframe" in low5 and "dns" in low5,
          "" if phase5 else "Phase 5 not found")

    # (i) Phase 6 preserved the wallet-audit content (wallet_integration_grep.py) + carries runtime_harness
    phase6 = _phase_section(text, 6, 7)
    check("(i) Phase 6: wallet_integration_grep.py preserved + runtime_harness added",
          bool(phase6) and "wallet_integration_grep.py" in phase6 and "runtime_harness" in phase6,
          "" if phase6 else "Phase 6 not found")

    # (j) Phase Budget Summary contains P-SM
    budget_section = _section(text, "## Phase Budget Summary", "## Cognitive Framework")
    check("(j) Phase Budget Summary contains 'P-SM'", "P-SM" in budget_section)

    # (k) Cognitive Framework Quick Reference contains P-SM
    cognitive_section = _section(text, "## Cognitive Framework", "## Reference Files")
    check("(k) Cognitive Framework contains 'P-SM'", "P-SM" in cognitive_section)

    # (l) review-fix [Important]: Phase 2.5 Step 2 carries display_vs_reality_grep.py WITH --md-out
    # dataflow_map.md (the full session path) — otherwise Reference Files points to an artifact that the
    # producer never writes (a dangling reference, dataflow_map.md was never created).
    phase25 = _phase_section(text, "2.5", "3")
    check("(l) Phase 2.5: display_vs_reality_grep.py carries '%s'" % DATAFLOW_MAP_SESSION_PATH,
          bool(phase25) and "display_vs_reality_grep.py" in phase25
          and DATAFLOW_MAP_SESSION_PATH in phase25,
          "" if phase25 else "Phase 2.5 not found")

    return results


def _read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def main():
    current_text = _read(DAPPHUNT_MD)
    if not current_text:
        print("[FAIL] %s not found or empty" % DAPPHUNT_MD)
        sys.exit(1)

    print("=== DAPPHUNT SKILL LINT (Plan 4 Task 9 (a)-(f) + Task 10 (g)-(l)) ===\n")

    print("-- CURRENT dapphunt.md (all 12 checks must PASS) --")
    current_results = lint(current_text)
    current_ok = sum(1 for _, p, _ in current_results if p)
    for n, p, d in current_results:
        print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
    print("  %d/%d\n" % (current_ok, len(current_results)))

    orig_exists = os.path.exists(DAPPHUNT_MD_ORIG)
    firing_proved_9 = False
    if orig_exists:
        orig_text = _read(DAPPHUNT_MD_ORIG)
        print("-- .sdd/backups/dapphunt.md.orig (pre-Task-9, at least some checks must FAIL) --")
        orig_results = lint(orig_text)
        orig_ok = sum(1 for _, p, _ in orig_results if p)
        for n, p, d in orig_results:
            print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
        print("  %d/%d\n" % (orig_ok, len(orig_results)))
        # FIRING is proven if .orig fails AT LEAST ONE of (a)/(b)/(c)/(d)/(e) —
        # (f) also PASSes on .orig (the sentinel is absent there too, that is not a regression).
        core_checks_9 = orig_results[:5]  # (a)-(e)
        firing_proved_9 = any(not p for _, p, _ in core_checks_9)
        print(("  [PASS] " if firing_proved_9 else "  [FAIL] ")
              + "Task-9 FIRING proven: .orig fails at least one of (a)-(e)\n")
    else:
        print("  [FAIL] backup %s not found — Task-9 FIRING not proven\n" % DAPPHUNT_MD_ORIG)

    pretask10_exists = os.path.exists(DAPPHUNT_MD_PRETASK10)
    firing_proved_10 = False
    if pretask10_exists:
        pretask10_text = _read(DAPPHUNT_MD_PRETASK10)
        print("-- .sdd/backups/dapphunt.md.pretask10.orig (pre-Task-10, at least some of "
              "(g)-(l) must FAIL) --")
        pretask10_results = lint(pretask10_text)
        pretask10_ok = sum(1 for _, p, _ in pretask10_results if p)
        for n, p, d in pretask10_results:
            print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
        print("  %d/%d\n" % (pretask10_ok, len(pretask10_results)))
        # (a)-(f) must stay green on pretask10 (Task-9 is already applied to this backup) —
        # a regression here would mean the pretask10 backup was taken from the wrong point.
        task9_checks_on_pretask10 = pretask10_results[:6]  # (a)-(f)
        task9_still_pass = all(p for _, p, _ in task9_checks_on_pretask10)
        # Task-10 FIRING is proven if pretask10 fails AT LEAST ONE of (g)-(l).
        core_checks_10 = pretask10_results[6:12]  # (g)-(l)
        firing_proved_10 = any(not p for _, p, _ in core_checks_10)
        print(("  [PASS] " if task9_still_pass else "  [FAIL] ")
              + "Task-9 checks (a)-(f) stay green on the pretask10 backup\n")
        print(("  [PASS] " if firing_proved_10 else "  [FAIL] ")
              + "Task-10 FIRING proven: pretask10 fails at least one of (g)-(l)\n")
        firing_proved_10 = firing_proved_10 and task9_still_pass
    else:
        print("  [FAIL] backup %s not found — Task-10 FIRING not proven\n" % DAPPHUNT_MD_PRETASK10)

    all_current_pass = current_ok == len(current_results)
    overall_ok = all_current_pass and orig_exists and firing_proved_9 and pretask10_exists and firing_proved_10

    print("=== RESULT: %s ===" % ("PASS" if overall_ok else "FAIL"))
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
