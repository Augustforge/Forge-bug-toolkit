# -*- coding: utf-8 -*-
"""Replay for active_banked_prose_unsynced (example protocol, 2026-08-18).

Defect: the hunter recorded confirmed Low/Medium building-blocks IN PROSE (bare tags [LOW-DEFERRED]/
[LOW-CONTESTED]/[MEDIUM-*]) and even ran T6 in prose, BUT the `## Banked Findings` table is empty →
active_banked_composite_unchecked (reads the table) sees 0 banked → the structural T6-merge is not forced,
building-blocks are not crossed/compounded. Reviewer: "even if Low/Medium do not pay — record
them STRUCTURALLY so they can be merged and T6 done".

Rule feedback_hook_must_prove_firing: the test proves FIRING (prose+empty table → fire) AND
protections (clean template / table non-empty / registry atom / <MIN / backtick-blockquote example does not count).
feedback_detector_state_not_phrase: the key is the COUNT of prose-tag rows + table state, not a word form.
Isolated slug in the REAL sessions/ (freshest_active_ledger is armed by the marker), cleaned up."""
import importlib.util, os, sys, time, tempfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "sessions")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", HOOK)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

SLUG = "_bptest"
SID = "bp-sid-1"
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

HEAD = ("# _bptest — Registry\n## Loop State\n- HUNT-MODE: AUTONOMOUS\n- Iteration: 5\n"
        "## Active\n- **I-01** a\n- **I-02** b\n- **I-03** c\n")
# Prose with >=2 bare Low/Medium building-block tags (as in the example hunt: different rows).
PROSE = ("## Findings\n- **Banked [LOW-DEFERRED]:** dead ReentrancyGuard on queue (no exploit) — info\n"
         "- **Residual [LOW-CONTESTED]:** solver-excess dust drain — protocol Low\n"
         "- I-23 ShareWarden bypass → banked [MEDIUM-COMPLIANCE], deny-bypass class\n")
BANKED_EMPTY = ("## Banked Findings\n| # | Severity | H-NN | Что | output | input | tier | found_by | ст |\n"  # Cyrillic column names kept (fixture mirrors real ledger format)
                "|---|---|---|---|---|---|---|---|---|\n| | | | | | | | | |\n")
BANKED_ROW = ("## Banked Findings\n| # | Severity | H-NN | Что | output | input | tier | found_by | ст |\n"  # Cyrillic column names kept (fixture mirrors real ledger format)
              "|---|---|---|---|---|---|---|---|---|\n"
              "| 1 | Low | H-05 | dead guard | state-leak | precond | none | self | confirmed |\n")
# Backtick/blockquote tag examples (as in the template instruction) — must NOT be counted.
TEMPLATE_NOISE = ("> докоп ≥3 слоёв → `[LOW-DEFERRED]` в Building Blocks; Medium → `[MEDIUM-*]`.\n"  # Russian fixture text kept (input data)
                  "> Low cost-gated: ≤1 шаг → банк; иначе `[LOW-CONTESTED]`.\n")  # Russian fixture text kept (input data)


def write_ledger(body, age=0):
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p = os.path.join(d, "hypotheses.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    if age:
        old = time.time() - age
        os.utime(p, (old, old))
    # marker for freshest_active_ledger
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), SID))
    return d


def fires():
    return g.active_banked_prose_unsynced(SID) is not None


try:
    # 1) FIRE: prose with 3 Low/Med tags + empty table → sync not done.
    write_ledger(HEAD + PROSE + BANKED_EMPTY)
    check("1 FIRE: 3 prose Low/Med tags + empty table → fire", fires(),
          "lines=%d rows=%d" % (g._banked_prose_tag_lines(HEAD + PROSE + BANKED_EMPTY),
                                g._banked_rows(HEAD + PROSE + BANKED_EMPTY)))

    # 2) SILENT: table filled (>=1 real row) → structurally in sync.
    write_ledger(HEAD + PROSE + BANKED_ROW)
    check("2 SILENT: table non-empty → no fire", not fires())

    # 3) SILENT: only 1 prose tag (< MIN) → too early.
    ONE = "## Findings\n- **Banked [LOW-DEFERRED]:** single info finding\n"
    write_ledger(HEAD + ONE + BANKED_EMPTY)
    check("3 SILENT: 1 prose tag (<MIN=2) → no fire", not fires(),
          "lines=%d" % g._banked_prose_tag_lines(HEAD + ONE + BANKED_EMPTY))

    # 4) ANTI-FP: tags only in blockquote/backtick examples (template instruction) → not counted.
    write_ledger(HEAD + TEMPLATE_NOISE + BANKED_EMPTY)
    check("4 ANTI-FP: backtick/blockquote tags do not count → no fire", not fires(),
          "lines=%d" % g._banked_prose_tag_lines(HEAD + TEMPLATE_NOISE + BANKED_EMPTY))

    # 5) OFF: HUNT-EXIT → no fire.
    write_ledger(HEAD + PROSE + BANKED_EMPTY + "\nHUNT-EXIT: T4-CONFIRMED High\n")
    check("5 OFF: HUNT-EXIT → no fire", not fires())

    # 6) OFF: HUNT-MODE MANUAL → no fire.
    write_ledger(HEAD + "- **HUNT-MODE: MANUAL**\n" + PROSE + BANKED_EMPTY)
    check("6 OFF: MANUAL → no fire", not fires())

    # 7) counting contract: 3 distinct prose rows with a tag.
    check("7 counting: PROSE yields 3 tag rows", g._banked_prose_tag_lines(PROSE) == 3,
          "got=%d" % g._banked_prose_tag_lines(PROSE))

finally:
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

print("=== BANKED-PROSE-UNSYNCED REPLAY (prose Low/Med → structural table for the T6 merge) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
