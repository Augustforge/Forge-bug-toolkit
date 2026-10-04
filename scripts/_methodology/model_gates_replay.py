#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test for the MODEL gates (divergence-first, phase 1 of depth_engine_plan).

Four points of the block (consolidation of 12 checks into 4 functions -- plan section 11.4):
  active_model_incomplete       -- completeness of the `system_model.md` artifact (list of reasons)
  active_model_order_violation  -- `pred:` could not appear AFTER `status:` (idea F)
  active_divergence_unresolved  -- abandoned `D-NN`, including unvisited `hot` ones
  active_library_not_banked     -- on exit: primitive `I-NN` not moved into the library (idea A+E)

Rule: replay test first, gate second (we got burned on BREADTH_RE). Monkeypatches
freshest_active_ledger; the model is placed NEXT TO the ledger, as in production. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/model_gates_replay.py

Note: many fixture strings below stay in Russian on purpose -- they are inputs to Russian-matching
regexes / parsers in the hook (table headers, sentinels, status words). English comments explain them.
"""
import importlib.util
import os
import re
import shutil
import sys
import tempfile

import os as _os  # P4: path from __file__, not from CWD
_HOOK = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

_cur = {"dir": None}
g.freshest_active_ledger = lambda sid: (
    (os.path.join(_cur["dir"], "hypotheses.md"), _cur["dir"]) if _cur["dir"] else (None, None)
)

LEDGER_OK = "# t — Hypotheses Registry\n\n## Loop State\n- **Iteration #:** 3\n"
LEDGER_NA = LEDGER_OK + "- **MODEL: N/A — single contract <300 LOC**\n"

# Table header (Russian column names kept: "Formula", "Class", "Source", "Status" -- parsed by the hook)
HDR = (
    "## Invariants\n"
    "| ID | Формула | check | Класс | Источник | component | pred | Статус | file:line | tests | crowd-heat | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def row(i, check="what to check", cls="state", src="docs", comp="vault",
        pred="ENFORCED", status="ENFORCED", loc="a.sol:10", tests="2", heat="cold", lib=""):
    return "| I-%02d | f%d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n" % (
        i, i, check, cls, src, comp, pred, status, loc, tests, heat, lib)


# Missing Negatives table: header = "Test | Negative | Axis | Hits"; the row = "t.sol:10 | RedeemTwice | repeat | I-01"
NEG_EMPTY = "\n## Missing Negatives\n\n| Тест | Негатив | Ось | Бьёт по |\n|---|---|---|---|\n"
NEG_FILLED = (NEG_EMPTY + "| t.sol:10 | RedeemTwice | repeat | I-01 |\n")
# CANON-TODO (Russian text kept, matched by the hook): "the canon operator was not run"
CANON_TODO = "\n- [ ] **`CANON-TODO`** — оператор канона не прогнан\n"
# CANON_DONE (kept): "the canon operator was run over all I-NN from the standard"
CANON_DONE = "\n- [x] оператор канона прогнан по всем I-NN из стандарта\n"

# Divergences table header: "... | Status | ... | Rank | Resolution" (Russian column names kept)
DIV_HDR = (
    "\n## Divergences\n"
    "| ID | I-NN | Где | Статус | value | paths | tests=0 | conv | crowd-heat | Ранг | Резолюция |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def drow(i, heat="cold", res="→ H-03"):
    return "| D-%02d | I-01 | a.sol:10 | ABSENT | high | 3 | yes | 2 | %s | 9 | %s |\n" % (i, heat, res)


def model(rows, negatives=NEG_FILLED, canon=CANON_DONE, divs=""):
    return HDR + "".join(rows) + canon + negatives + divs


def setup(ledger_txt, model_txt=None):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    _cur["dir"] = d
    return d


results = []


def run(name, ledger_txt, model_txt, fn, expect):
    d = setup(ledger_txt, model_txt)
    try:
        got = bool(fn("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


print("── A. active_model_incomplete (artifact completeness)")
GOOD3 = model([row(1), row(2), row(3, status="ABSENT", pred="ABSENT")])
run("no model at all -> fire", LEDGER_OK, None, g.active_model_incomplete, True)
run("model exists, 0 I-NN rows -> fire", LEDGER_OK, model([]), g.active_model_incomplete, True)
run("sentinel MODEL: N/A + no model -> silent", LEDGER_NA, None, g.active_model_incomplete, False)
run("3 rows, all filled -> silent", LEDGER_OK, GOOD3, g.active_model_incomplete, False)
run("row without status (unmapped) -> fire", LEDGER_OK,
    model([row(1), row(2, status="")]), g.active_model_incomplete, True)
run("13 rows in a single wave (shotgun) -> fire", LEDGER_OK,
    model([row(i) for i in range(1, 14)]), g.active_model_incomplete, True)
# aevo 2026-07-29: the limit <=12 is PER WAVE, NOT global. A 6-axis skeleton / multi-wave is legitimate.
_TABLE = HDR.split("\n", 1)[1]                        # table header without "## Invariants"
def _waves(*sizes):
    out, base = "", 0
    for wi, n in enumerate(sizes):
        hdr = "## Invariants\n" if wi == 0 else "\n## WAVE-%d — новая ось\n" % (wi + 1)  # "new axis"
        out += hdr + _TABLE + "".join(row(base + j) for j in range(1, n + 1))
        base += n
    return out + CANON_DONE + NEG_FILLED
run("2 waves 9+6=15 global, <=12 each -> silent (multi-wave by axes, not a shotgun)", LEDGER_OK,
    _waves(9, 6), g.active_model_incomplete, False)
run("1 wave of 15 (a real shotgun in one section) -> fire", LEDGER_OK,
    _waves(15), g.active_model_incomplete, True)
run("4 rows, 3 non-ENFORCED (75%) -> fire", LEDGER_OK,
    model([row(1), row(2, status="ABSENT", pred="ABSENT"),
           row(3, status="ENFORCED-PARTIAL", pred="ABSENT"),
           row(4, status="SUBSTITUTED", pred="ENFORCED")]), g.active_model_incomplete, True)
run("exactly 12 rows, 6 non-ENFORCED (50%) -> silent", LEDGER_OK,
    model([row(i) for i in range(1, 7)] +
          [row(i, status="ABSENT", pred="ABSENT") for i in range(7, 13)]),
    g.active_model_incomplete, False)
run("row without check: -> fire", LEDGER_OK,
    model([row(1, check=""), row(2)]), g.active_model_incomplete, True)
run("ENFORCED present, but Missing Negatives empty -> fire", LEDGER_OK,
    model([row(1), row(2)], negatives=NEG_EMPTY), g.active_model_incomplete, True)
# A model without a single ENFORCED always trips shotgun (0 of N enforced > 50%) -- this is by design,
# so the negatives rule is checked by the CONTENT of the reason, not by whether it fired.
d = setup(LEDGER_OK, model([row(1, status="ABSENT", pred="ABSENT"),
                            row(2, status="IMPLICIT", pred="ABSENT")], negatives=NEG_EMPTY))
_reason = g.active_model_incomplete("sid") or ""
shutil.rmtree(d, ignore_errors=True)
_ok = "Missing Negatives" not in _reason
print("  [%s] no ENFORCED at all -> negatives NOT required (reason is not about them)"
      % ("PASS" if _ok else "FAIL"))
results.append(_ok)
run("CANON-TODO pending -> fire", LEDGER_OK,
    model([row(1), row(2)], canon=CANON_TODO), g.active_model_incomplete, True)
run("economic ABSENT without check -> fire", LEDGER_OK,
    model([row(1), row(2, cls="economic", status="ABSENT", pred="ABSENT", check="")]),
    g.active_model_incomplete, True)
run("economic ABSENT with a named sequence -> silent", LEDGER_OK,
    model([row(1), row(2, cls="economic", status="ABSENT", pred="ABSENT",
                       check="permissionless mint→redeem в одной tx качает fees")]),  # "in a single tx pumps fees"
    g.active_model_incomplete, False)

print("── A2. active_model_incomplete on the MODEL: BUILDING phase (OBS-18 hyperlane 2026-07-28)")
# Code NOT read -> status is LEGITIMATELY empty; the "shotgun" is measured by pred:, status/canon/negatives are not run.
LEDGER_BUILD = LEDGER_OK + "- **MODEL: BUILDING** (строю волну, код не читан)\n"  # "building a wave, code not read"
# The exact Hyperlane case: 12 I-NN, pred 9xENFORCED + 3xENFORCED-PARTIAL, status EMPTY, CANON-TODO pending.
GROUNDED_BUILD = model(
    [row(i, status="", pred="ENFORCED") for i in range(1, 10)] +
    [row(i, status="", pred="ENFORCED-PARTIAL") for i in range(10, 13)],
    canon=CANON_TODO)
run("BUILDING: grounded (9 pred-ENF/3-PARTIAL, status empty, CANON-TODO) -> silent [Hyperlane]",
    LEDGER_BUILD, GROUNDED_BUILD, g.active_model_incomplete, False)
run("BUILDING: 12/12 pred-ABSENT (shotgun from the head) -> fire (by pred, not by status)", LEDGER_BUILD,
    model([row(i, status="", pred="ABSENT") for i in range(1, 13)]), g.active_model_incomplete, True)
run("BUILDING: row without `pred:` -> fire (pred is required BEFORE code)", LEDGER_BUILD,
    model([row(1, status="", pred=""), row(2, status="", pred="ENFORCED")]),
    g.active_model_incomplete, True)
run("BUILDING: 13 I-NN -> fire (the limit is phase-independent)", LEDGER_BUILD,
    model([row(i, status="", pred="ENFORCED") for i in range(1, 14)]), g.active_model_incomplete, True)
run("BUILDING: row without `check:` -> fire (phase-independent)", LEDGER_BUILD,
    model([row(1, status="", pred="ENFORCED", check=""), row(2, status="", pred="ENFORCED")]),
    g.active_model_incomplete, True)
run("BUILDING: 6/12 pred-PARTIAL (exactly half) -> silent (<=half is ok)", LEDGER_BUILD,
    model([row(i, status="", pred="ENFORCED") for i in range(1, 7)] +
          [row(i, status="", pred="ENFORCED-PARTIAL") for i in range(7, 13)]),
    g.active_model_incomplete, False)
# CONTRAST: the same empty-status model, but WITHOUT building (enforcement claimed) -> fire (status is required
# after code) -- the fix does not let an empty status slip through forever, only in the BUILDING phase.
run("NOT building (enforcement phase) + empty statuses -> fire (regression: status is required after code)",
    LEDGER_OK, model([row(i, status="", pred="ENFORCED") for i in range(1, 4)]),
    g.active_model_incomplete, True)

print("── A3. active_model_incomplete: grounding in the corpus (OBS-19, 2026-07-29 -- not 'from the head')")
# Corpus section: heading "Corpus -- what was read BEFORE code"; columns "Source | What it gives | Link";
# row labels "docs / whitepaper", "project tests" (Russian kept, matched by the hook)
CORPUS_EMPTY = ("\n## Corpus — что прочитано ДО кода\n| Источник | Что даёт | Ссылка |\n|---|---|---|\n"
                "| docs / whitepaper | | |\n| тесты проекта | | |\n")
CORPUS_FILLED = ("\n## Corpus — что прочитано ДО кода\n| Источник | Что даёт | Ссылка |\n|---|---|---|\n"
                 "| docs | mailbox spec: process/verify | https://docs |\n"
                 "| тесты проекта | инвариант conservation | test/Warp.t.sol:88 |\n")  # "invariant conservation"
run("model + `## Corpus` EMPTY (0 sources) -> fire (from the head) [Hyperlane case]", LEDGER_BUILD,
    GROUNDED_BUILD + CORPUS_EMPTY, g.active_model_incomplete, True)
run("model + `## Corpus` FILLED (docs+tests named) -> silent (grounded)", LEDGER_BUILD,
    GROUNDED_BUILD + CORPUS_FILLED, g.active_model_incomplete, False)
run("no `## Corpus` section at all (synthetic) -> grounding not checked (old tests intact)",
    LEDGER_BUILD, GROUNDED_BUILD, g.active_model_incomplete, False)
run("enforcement phase + `## Corpus` empty -> also fire (grounding is needed in any phase)",
    LEDGER_OK, GOOD3 + CORPUS_EMPTY, g.active_model_incomplete, True)

print("── B. active_model_order_violation (pred after status = backdated)")
run("status present, pred empty -> fire", LEDGER_OK,
    model([row(1), row(2, pred="")]), g.active_model_order_violation, True)
run("both filled -> silent", LEDGER_OK, GOOD3, g.active_model_order_violation, False)
run("pred present, status empty (code not read yet) -> silent", LEDGER_OK,
    model([row(1, status="")]), g.active_model_order_violation, False)
run("sentinel MODEL: N/A -> silent", LEDGER_NA,
    model([row(1, pred="")]), g.active_model_order_violation, False)

print("── C. active_divergence_unresolved (abandoned D-NN, incl. hot)")
run("D-NN without resolution -> fire", LEDGER_OK,
    model([row(1)], divs=DIV_HDR + drow(1, res="")), g.active_divergence_unresolved, True)
run("D-NN -> H-03 -> silent", LEDGER_OK,
    model([row(1)], divs=DIV_HDR + drow(1)), g.active_divergence_unresolved, False)
run("D-NN KILLED with falsifier -> silent", LEDGER_OK,
    model([row(1)], divs=DIV_HDR + drow(1, res="KILLED pool.sol:88")),
    g.active_divergence_unresolved, False)
run("cold resolved, hot abandoned -> fire", LEDGER_OK,
    model([row(1)], divs=DIV_HDR + drow(1) + drow(2, heat="hot", res="")),
    g.active_divergence_unresolved, True)
run("'it is crowded there' instead of a resolution -> fire (not a falsifier)", LEDGER_OK,
    model([row(1)], divs=DIV_HDR + drow(2, heat="hot", res="там людно, аудит смотрел")),  # "it is crowded there, the audit looked at it"
    g.active_divergence_unresolved, True)
run("no Divergences section -> silent", LEDGER_OK, GOOD3, g.active_divergence_unresolved, False)

print("── D. active_library_not_banked (on exit; idea A+E)")
LEDGER_EXIT = LEDGER_OK + "\nHUNT-EXIT: T4-CONFIRMED High\n"
run("exit, model non-empty, LIBRARY-TODO pending -> fire",
    LEDGER_EXIT + "- **LIBRARY:** {LIBRARY-TODO ...}\n", GOOD3, g.active_library_not_banked, True)
run("exit, LIBRARY: updated -> silent",
    LEDGER_EXIT + "- **LIBRARY:** updated\n", GOOD3, g.active_library_not_banked, False)
run("exit, LIBRARY: N/A -- no primitives -> silent",
    LEDGER_EXIT + "- **LIBRARY: N/A — примитивов не было**\n", GOOD3,  # sentinel text kept: "there were no primitives"
    g.active_library_not_banked, False)
run("exit, but MODEL: N/A -> silent",
    LEDGER_NA + "\nHUNT-EXIT: T4-CONFIRMED High\n- **LIBRARY:** {LIBRARY-TODO}\n", None,
    g.active_library_not_banked, False)
run("no exit yet -> silent (not the time)",
    LEDGER_OK + "- **LIBRARY:** {LIBRARY-TODO}\n", GOOD3, g.active_library_not_banked, False)

print("── E. active_wave_transition_needed / active_wave_codefirst_nudge (OBS-8/OBS-9, per-subsystem)")
ROWS3 = [row(1), row(2), row(3, status="ABSENT", pred="ABSENT")]  # all statuses valid = resolved


def COV(rows):
    return ("\n## Subsystem Model Coverage\n| Subsystem | In-scope | Model | Ref |\n"
            "|---|---|---|---|\n" + "".join(rows))


COV_UNMODELED = COV(["| offchain-mp | yes | MODELED | I-01..12 |\n",
                     "| rentals | yes | unmodeled | — |\n"])
COV_ALLDONE = COV(["| offchain-mp | yes | MODELED | I-01..12 |\n",
                   "| rentals | yes | N/A | вне модели |\n"])  # "outside the model"
COV_UNMODELED_OOS = COV(["| offchain-mp | yes | MODELED | I-01..12 |\n",
                         "| some-lib | no | unmodeled | out of scope |\n"])  # unmodeled BUT out-of-scope

ACT = "\n## Active Hypotheses\n\n"
LIVE_MODELBACKED = ACT + "### H-01: x\n- **origin:** ⬆ D-C07 model-backed (code-read corroborated)\n- **State:** A\n"
LIVE_CODEFIRST = ACT + "### H-01: x\n- **origin:** T14-place × code-read\n- **State:** A-formulating\n"
DEAD_ONLY = ACT + "### H-01 [KILLED]: x\n- **origin:** code-read\n- **Killed by:** a.sol:1\n"
# building-block with a suffix in the tag -- the real ledger format (integration bug: `[CONTESTED/...]`
# did not match the strict `\[CONTESTED\]` -> a building-block was falsely counted live -> codefirst FP on a live hunt)
CONTESTED_SUFFIX = (ACT + "### H-01: live model-backed\n- **origin:** D-C07 model-backed\n- **State:** A\n"
                    + "### H-02 [CONTESTED/building-block]: bb\n- **origin:** code-read × composite\n- **State:** bb\n")
BUILDING = "\n- **MODEL: BUILDING** (строю Credits волну)\n"  # "building the Credits wave"

# --- OBS-8 wave-transition (hard) ---
run("closed wave + unmodeled in-scope + empty Active -> FIRE", LEDGER_OK,
    model(ROWS3, divs=COV_UNMODELED), g.active_wave_transition_needed, True)
run("+ live Active H-NN -> silent (there is live work)", LEDGER_OK + LIVE_MODELBACKED,
    model(ROWS3, divs=COV_UNMODELED), g.active_wave_transition_needed, False)
run("+ MODEL: BUILDING (building the next wave) -> silent", LEDGER_OK + BUILDING,
    model(ROWS3, divs=COV_UNMODELED), g.active_wave_transition_needed, False)
run("all subsystems MODELED/N-A (no unmodeled) -> silent", LEDGER_OK,
    model(ROWS3, divs=COV_ALLDONE), g.active_wave_transition_needed, False)
run("unmodeled BUT out-of-scope -> silent (not our scope)", LEDGER_OK,
    model(ROWS3, divs=COV_UNMODELED_OOS), g.active_wave_transition_needed, False)
run("no Coverage section at all -> silent", LEDGER_OK,
    model(ROWS3), g.active_wave_transition_needed, False)
run("not all I-NN resolved (status empty) -> silent (that is active_model_incomplete)", LEDGER_OK,
    model([row(1), row(2, status="")], divs=COV_UNMODELED), g.active_wave_transition_needed, False)
run("only KILLED H-NN (not live) + unmodeled -> FIRE (killed does not block the transition)",
    LEDGER_OK + DEAD_ONLY, model(ROWS3, divs=COV_UNMODELED), g.active_wave_transition_needed, True)
run("sentinel MODEL: N/A -> silent (ctx None)", LEDGER_NA,
    model(ROWS3, divs=COV_UNMODELED), g.active_wave_transition_needed, False)

# --- OBS-9 model-first nudge (soft) ---
run("live code-read H-NN without D-NN + unmodeled -> FIRE (code-first smell)",
    LEDGER_OK + LIVE_CODEFIRST, model(ROWS3, divs=COV_UNMODELED), g.active_wave_codefirst_nudge, True)
run("live H-NN model-backed (D-NN) + unmodeled -> silent (un-dup, ok)",
    LEDGER_OK + LIVE_MODELBACKED, model(ROWS3, divs=COV_UNMODELED), g.active_wave_codefirst_nudge, False)
run("code-read H-NN, but all subsystems covered -> silent",
    LEDGER_OK + LIVE_CODEFIRST, model(ROWS3, divs=COV_ALLDONE), g.active_wave_codefirst_nudge, False)
run("[CONTESTED/building-block] suffix = NOT live -> codefirst silent (only H-01 model-backed is live)",
    LEDGER_OK + CONTESTED_SUFFIX, model(ROWS3, divs=COV_UNMODELED), g.active_wave_codefirst_nudge, False)
run("[CONTESTED/...] building-block is not counted in the live pool -> wave_transition FIRE if it is the only one",
    LEDGER_OK + ACT + "### H-09 [CONTESTED/building-block]: bb\n- **origin:** code-read\n- **State:** bb\n",
    model(ROWS3, divs=COV_UNMODELED), g.active_wave_transition_needed, True)

print("── P10 (katana 2026-07-29): I-NN in bullet format is recognized (not only a pipe table)")


def bmodel(n, with_status=True, with_pred=True, cov=""):
    """A model where I-NN are written as BULLETS `- **I-NN** [class] … check: … pred: … status: …`
    (the real katana format), not a 12-column table."""
    out = ["## Invariants — `I-NN` (pred: до чтения кода)\n\n"]  # "pred: before reading code"
    for i in range(1, n + 1):
        pr = " pred: ENFORCED" if with_pred else ""
        st = " status: ENFORCED" if with_status else ""
        out.append("- **I-%02d** [state] Invariant %d: formula. check: go verify X-%d.%s%s\n"
                   % (i, i, i, pr, st))
    return "".join(out) + NEG_FILLED + CANON_DONE + cov


# direct parser contract: bullets give a non-empty _i_rows (the root of the katana blindness)
_br = g._i_rows(bmodel(12))
print("  [%s] bullet model: _i_rows == 12 (was 0 -> blindness): got=%d"
      % ("PASS" if len(_br) == 12 else "FAIL", len(_br)))
results.append(len(_br) == 12)
_c = g._bullet_to_cells("- **I-01** [economic] Formula. check: verify X. pred: ENFORCED status: ENFORCED")
_okc = _c[0] == "I-01" and _c[3] == "economic" and _c[6] == "ENFORCED" and _c[7] == "ENFORCED" and bool(_c[2])
print("  [%s] bullet->cells: id/class/pred/status/check extracted" % ("PASS" if _okc else "FAIL"))
results.append(_okc)

run("bullet model, 12 I-NN, complete -> active_model_incomplete silent (not 'zero I-NN')",
    LEDGER_OK, bmodel(12), g.active_model_incomplete, False)
run("bullet model WITHOUT status (katana: enforcement in the ledger, not in the model) -> fire (set it in the model)",
    LEDGER_OK, bmodel(3, with_status=False), g.active_model_incomplete, True)

print("── P8 (T9-forcing): all-ENFORCED bullet wave + uncovered ASSET -> wave_transition FIRE")
run("bullet model all-ENFORCED + Coverage unmodeled + Active empty -> FIRE (T9 new axis/asset)",
    LEDGER_OK, bmodel(3, cov=COV_UNMODELED), g.active_wave_transition_needed, True)
run("bullet model all-ENFORCED + Coverage all covered -> silent",
    LEDGER_OK, bmodel(3, cov=COV_ALLDONE), g.active_wave_transition_needed, False)

print("── P8-HARD (T9 cold-restart): all ENFORCED + 0 D-NN + 0 live H -> FIRE (Coverage-INDEPENDENT)")
LIVE_H = LEDGER_OK + "\n## Active Hypotheses\n### H-05: live\n- **origin:** code-read\n- State: A\n"
run("all-ENFORCED + Active empty + Coverage CLOSED (all MODELED) -> FIRE T9 (does not look at Coverage)",
    LEDGER_OK, bmodel(3, cov=COV_ALLDONE), g.active_core_enforced_needs_t9, True)
run("all-ENFORCED + NO Coverage section at all -> FIRE (Coverage-independent -- gaming does not help)",
    LEDGER_OK, bmodel(3), g.active_core_enforced_needs_t9, True)
run("ABSENT among statuses -> silent (that is D-NN work, not T9)",
    LEDGER_OK, model([row(1), row(2), row(3, status="ABSENT", pred="ABSENT")]),
    g.active_core_enforced_needs_t9, False)
run("open D-NN (res empty) -> silent (divergence_unresolved forces it)",
    LEDGER_OK, model([row(1), row(2), row(3)], divs=DIV_HDR + drow(1, res="")),
    g.active_core_enforced_needs_t9, False)
run("live Active H-NN present -> silent (single-pick drives it, not T9)",
    LIVE_H, model([row(1), row(2), row(3)]), g.active_core_enforced_needs_t9, False)
run("thin model (<3 statused) -> silent (model_incomplete catches it earlier)",
    LEDGER_OK, model([row(1), row(2)]), g.active_core_enforced_needs_t9, False)
run("MODEL: N/A -> silent (ctx None)", LEDGER_NA, bmodel(3), g.active_core_enforced_needs_t9, False)

print("── MODEL MULTI-WAVE (aevo 2026-07-29): single-axis model + 0 D-NN -> FIRE the next invariant axis")
# Wave-2 axes text (Russian kept, matched by axis-marker regexes): "function seam; call sequence; per-block;
# isolation between connectors; risk-free economic loop"
AXES_W2 = ("\n## Invariants — WAVE 2\n"
           "- cross-function стык функций; order-dependent последовательность вызовов; temporal per-block;\n"
           "  cross-connector isolation между connector; economic-sequence безрисковый цикл\n")
run("single-function wave (no axis markers) + 0 open D -> FIRE (catches the aevo stall)",
    LEDGER_OK, bmodel(9), g.active_model_axes_incomplete, True)
run("model + wave 2 (all 5 axes covered) -> silent (does not spam after it is built)",
    LEDGER_OK, bmodel(9) + AXES_W2, g.active_model_axes_incomplete, False)
run("open D-NN (res empty) -> silent (drive D, do not force new axes)",
    LEDGER_OK, model([row(1), row(2), row(3)], divs=DIV_HDR + drow(1, res="")),
    g.active_model_axes_incomplete, False)
run("agent declared WAVE-NEXT in the ledger -> silent (next wave in progress)",
    LEDGER_OK + "\nWAVE-NEXT: order-dependent\n", bmodel(9), g.active_model_axes_incomplete, False)
run("thin model (<3 statused) -> silent (model_incomplete catches it earlier)",
    LEDGER_OK, bmodel(2), g.active_model_axes_incomplete, False)
run("MODEL: N/A -> silent (ctx None)", LEDGER_NA, bmodel(9), g.active_model_axes_incomplete, False)

# active_t9_count_untracked (originprotocol-audit 2026-08-13: "forgot I-NN on new waves"):
# COMPLEMENT of OBS-10 -- the agent builds extra `## WAVE-N` waves, but `T9 restart axes used` is not set +
# the registry is empty -> _t9_axes_declared=0 -> OBS-10 is blind -> scout-first instead of model-first. Forces the counter.
print("── T9U. active_t9_count_untracked (per-wave model-first is blind without an axis counter)")
_WAVE_INN = ("\n## WAVE-2 — AMO economic axis\n"
             "- **I-50** [economic] AMO tilt invariant. check: X. pred: ENFORCED status: ENFORCED\n")
# fire: an extra wave is built, but the T9 count is not set (LEDGER_OK has no T9 line), registry empty -> t9_declared=0
run("T9U1: WAVE-2 built + T9 count NOT set -> FIRE (counter blind, per-wave model-first not forced)",
    LEDGER_OK, bmodel(9) + _WAVE_INN, g.active_t9_count_untracked, True)
# silent: T9 count set (N>=1) -> OBS-10 works, this one is silent
run("T9U2: WAVE-2 + `T9 restart axes used: 2` set -> silent (OBS-10 leads)",
    LEDGER_OK + "\n- **T9 restart axes used:** 2\n", bmodel(9) + _WAVE_INN, g.active_t9_count_untracked, False)
# silent: no extra waves (extra=0) -> T9 axes are not used
run("T9U3: no extra waves (only Invariants) -> silent (T9 axes not used)",
    LEDGER_OK, bmodel(9), g.active_t9_count_untracked, False)
# silent: MODEL N/A
run("T9U4: MODEL N/A -> silent", LEDGER_NA, bmodel(9) + _WAVE_INN, g.active_t9_count_untracked, False)
# silent: thin model (bmodel(1)+WAVE = 2 statused < 3 -> being built)
run("T9U5: thin model (2 statused total) -> silent (being built)",
    LEDGER_OK, bmodel(1) + _WAVE_INN, g.active_t9_count_untracked, False)
# silent: WAVE-NEXT declared (wave in progress)
run("T9U6: WAVE-NEXT in the ledger -> silent (a wave is being built right now)",
    LEDGER_OK + "\nWAVE-NEXT: economic\n", bmodel(9) + _WAVE_INN, g.active_t9_count_untracked, False)
# silent: HUNT-EXIT
run("T9U7: HUNT-EXIT -> silent",
    LEDGER_OK + "\nHUNT-EXIT: T4-CONFIRMED High\n", bmodel(9) + _WAVE_INN, g.active_t9_count_untracked, False)

# PIVOT-FLOOR (flow-protocol 2026-08-18: "slid after wave-1"): the `T9 restart axes used` counter
# is left as a TEMPLATE, but the hunter EXPLICITLY pivoted (`pivot to Axis-2`) and ran cold scouts WITHOUT a wave ->
# _t9_axes_declared=0 silenced axes_without_waves (model-first-per-wave blindness). A floor on the pivot declaration
# catches it. FIRE on degradation (0 extra waves), SILENT after WAVE-2 is built (restart-count semantics).
_PIVOT_LEDGER = LEDGER_OK + "\n- **Current pick:** WAVE-1 exhausted → pivot to Axis-2 Scheduled Tx\n"
run("PIVOT1: Current pick=Axis-2 + template counter + 0 extra waves -> FIRE (slid into a cold scout without a wave)",
    _PIVOT_LEDGER, bmodel(9), g.active_axes_without_waves, True)
run("PIVOT2: same + WAVE-2 built -> silent (corrected: model->fan-out)",
    _PIVOT_LEDGER, bmodel(9) + _WAVE_INN, g.active_axes_without_waves, False)
run("PIVOT3 anti-FP: ranked Axis-Queue `1) 2)` (no Current pick/Depth-Lead with axis-N) -> silent",
    LEDGER_OK + "\n- Axis-Queue:\n  1) foo axis\n  2) bar axis\n", bmodel(9), g.active_axes_without_waves, False)
# OZ 2026-08-18: state-based (not a phrase) -- "AXIS-2 pivot" (verb AFTER) / Cyrillic "Пивот" / "reset на axis-2" (Russian "reset to axis-2").
run("PIVOT4 (OZ): `Current pick: AXIS-2 pivot` (verb after) -> FIRE (phrase-agnostic)",
    LEDGER_OK + "\n- **Current pick:** AXIS-2 pivot — oz-contracts v5.7 model-build\n",
    bmodel(9), g.active_axes_without_waves, True)
# PIVOT5 fixture stays Russian ("reset to axis-2, building the model") -- the test needs a Cyrillic context
run("PIVOT5 (OZ): `Depth-Lead: reset на axis-2` Cyrillic context -> FIRE (keys on axis-N, not the verb)",
    LEDGER_OK + "\n- **Depth-Lead:** none yet (reset на axis-2, строю модель)\n",
    bmodel(9), g.active_axes_without_waves, True)
run("PIVOT6 anti-FP: `Current pick: AXIS-1 exhausted` (still on axis-1) -> silent (N<2)",
    LEDGER_OK + "\n- **Current pick:** AXIS-1 confidential enforcement-exhausted\n",
    bmodel(9), g.active_axes_without_waves, False)

print("── F. active_undup_sweep_incomplete (Task 1, plan 6 sec. 50.1/51) -- REAL templates, not synthetics")
_TOOLKIT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_WEB_TPL_PATH = _os.path.join(_TOOLKIT_ROOT, "sessions", "_methodology", "hypotheses_web_template.md")
_CONTRACT_TPL_PATH = _os.path.join(_TOOLKIT_ROOT, "sessions", "_methodology", "hypotheses_template.md")
_WEB_TPL_RAW = open(_WEB_TPL_PATH, encoding="utf-8").read()
_CONTRACT_TPL_RAW = open(_CONTRACT_TPL_PATH, encoding="utf-8").read()


def _fill_undup_run(tpl_text):
    """Every seed row `| {TODO} |` (a generator applicable by profile) -> `| RUN |`. Rows
    `N/A — web-only` are already justified by the template and are not touched."""
    return tpl_text.replace("| {TODO} |", "| RUN |")


run("web template UNTOUCHED (15 seed rows `{TODO}`) + mature model (3 I-NN statused) -> FIRE",
    _WEB_TPL_RAW, GOOD3, g.active_undup_sweep_incomplete, True)
run("web template: all applicable rows -> RUN, no N/A rows in the web seed -> silent",
    _fill_undup_run(_WEB_TPL_RAW), GOOD3, g.active_undup_sweep_incomplete, False)
run("off-switch: web template UNTOUCHED + thin model (2 statused < 3) -> silent (first scout pass)",
    _WEB_TPL_RAW, model([row(1), row(2)]), g.active_undup_sweep_incomplete, False)
run("off-switch: web template UNTOUCHED + MODEL: N/A sentinel -> silent (ctx None)",
    _WEB_TPL_RAW + "\n- **MODEL: N/A — smoke-test**\n", GOOD3, g.active_undup_sweep_incomplete, False)
run("off-switch: no model at all (system_model.md absent) -> silent",
    _WEB_TPL_RAW, None, g.active_undup_sweep_incomplete, False)
run("ledger without a '## Un-Dup Sweep' section at all (pre-Plan-6 ledger) + mature model -> silent",
    LEDGER_OK, GOOD3, g.active_undup_sweep_incomplete, False)

run("contract template UNTOUCHED (8 seed `{TODO}` + 7 `N/A - web-only`) + mature model -> FIRE",
    _CONTRACT_TPL_RAW, GOOD3, g.active_undup_sweep_incomplete, True)
run("contract template: 8 applicable rows -> RUN, 7 profile N/A untouched -> silent",
    _fill_undup_run(_CONTRACT_TPL_RAW), GOOD3, g.active_undup_sweep_incomplete, False)
run("off-switch: contract template UNTOUCHED + thin model (2 statused < 3) -> silent",
    _CONTRACT_TPL_RAW, model([row(1), row(2)]), g.active_undup_sweep_incomplete, False)

# _undup_sweep_incomplete_rows: direct parser contract on the real web template (without the gate/model).
_incomplete_web = g._undup_sweep_incomplete_rows(_WEB_TPL_RAW)
print("  [%s] _undup_sweep_incomplete_rows(web UNTOUCHED) == 15 (all seed generators `{TODO}`): got=%d"
      % ("PASS" if len(_incomplete_web) == 15 else "FAIL", len(_incomplete_web)))
results.append(len(_incomplete_web) == 15)
_incomplete_contract = g._undup_sweep_incomplete_rows(_CONTRACT_TPL_RAW)
print("  [%s] _undup_sweep_incomplete_rows(contract UNTOUCHED) == 8 (7 N/A-web-only are already justified): got=%d"
      % ("PASS" if len(_incomplete_contract) == 8 else "FAIL", len(_incomplete_contract)))
results.append(len(_incomplete_contract) == 8)

print("── G. active_composition_pass_skipped (Task 2, plan 6 sec. 43.1/50/51) -- producer-absent class")


def run_cm(name, ledger_txt, model_txt, cm_content, expect):
    """Like `run()`, but optionally puts `composition_map.md` NEXT TO the ledger BEFORE calling the gate
    (co-located producer-absent form, as active_authz_matrix_skipped/active_clone_diff_skipped are really
    tested). cm_content=None -> the file is not created at all (producer was not run)."""
    d = setup(ledger_txt, model_txt)
    try:
        if cm_content is not None:
            with open(os.path.join(d, "composition_map.md"), "w", encoding="utf-8") as f:
                f.write(cm_content)
        got = bool(g.active_composition_pass_skipped("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


BOUND3 = GOOD3                              # 3 I-NN, default src=docs/comp=vault -> 3 edge-eligible boundaries
BOUND2 = model([row(1), row(2)])            # 2 boundaries < COMPOSITION_MIN_BOUNDARIES

run_cm("mature model (>=3 statused) + >=3 boundaries + composition_map.md ABSENT -> FIRE (producer-absent)",
       LEDGER_OK, BOUND3, None, True)
run_cm("same ledger/model, composition_map.md RUN (non-empty file) -> silent",
       LEDGER_OK, BOUND3,
       "RESULT: composition-map-run, 3 edges, 1 un-validated candidates (0 already-materialized skipped)\n",
       False)
run_cm("composition_map.md exists but is EMPTY (whitespace-only) -> FIRE (the gate treats 'empty' as not run)",
       LEDGER_OK, BOUND3, "   \n", True)
run_cm("model <3 boundaries (2 rows, both edge-eligible) -> silent (COMPOSITION_MIN_BOUNDARIES not reached)",
       LEDGER_OK, BOUND2, None, False)
run_cm("off-switch: thin model (1 statused I-NN < 3) -> silent (first scout pass)",
       LEDGER_OK, model([row(1)]), None, False)
run_cm("3 statused I-NN (maturity OK), but only 2 carry source+component -> silent (boundary != maturity)",
       LEDGER_OK, model([row(1), row(2), row(3, src="", comp="", status="ABSENT", pred="ABSENT")]),
       None, False)
run_cm("off-switch: MODEL: N/A sentinel -> silent (ctx None)",
       LEDGER_NA, BOUND3, None, False)
run_cm("off-switch: no model at all (system_model.md absent) -> silent",
       LEDGER_OK, None, None, False)
run_cm("rows without source/component (0 edge-eligible rows even with 3 statused I-NN) -> silent",
       LEDGER_OK,
       model([row(1, src="", comp=""), row(2, src="", comp=""),
              row(3, src="", comp="", status="ABSENT", pred="ABSENT")]),
       None, False)

# _composition_boundary_count: direct contract of the boundary counter (reused by Task 3/6 if needed).
_b3 = g._composition_boundary_count(BOUND3)
print("  [%s] _composition_boundary_count(3 rows, source+component filled) == 3: got=%d"
      % ("PASS" if _b3 == 3 else "FAIL", _b3))
results.append(_b3 == 3)
_b0 = g._composition_boundary_count(model([row(1, src=""), row(2, comp="")]))
print("  [%s] _composition_boundary_count(source/component empty) == 0: got=%d"
      % ("PASS" if _b0 == 0 else "FAIL", _b0))
results.append(_b0 == 0)

print("── H. active_undup_origin_missing (Task 3, plan 6 sec. 48.2/44/50.3) -- REAL templates, positional-covering")

_WEB_MODEL_PATH = _os.path.join(_TOOLKIT_ROOT, "sessions", "_methodology", "system_model_web_template.md")
_CONTRACT_MODEL_PATH = _os.path.join(_TOOLKIT_ROOT, "sessions", "_methodology", "system_model_template.md")
_WEB_MODEL_RAW = open(_WEB_MODEL_PATH, encoding="utf-8").read()
_CONTRACT_MODEL_RAW = open(_CONTRACT_MODEL_PATH, encoding="utf-8").read()


def _dnn_header_lines(tpl_text):
    r"""(header, separator) physical lines of the `## Divergences` table of the REAL template (positional
    truth -- we do not reinvent the columns by hand, we read them from the file on disk). The section heading
    is really `## Divergences — \`D-NN\`` -- we match with startswith, not exact equality."""
    lines = tpl_text.splitlines()
    idx = next(k for k, l in enumerate(lines) if l.strip().startswith("## Divergences"))
    k = idx + 1
    while k < len(lines) and not lines[k].strip().startswith("|"):
        k += 1
    return lines[k], lines[k + 1]


def _real_drow(tpl_text, i, undup="{TODO}", res=""):
    """A D-NN row WITH THE SAME number of columns as the REAL template on disk (positional-covering,
    R5): undup_origin = second-to-last cell (`c[-2]`), Resolution = last (`c[-1]`) -- exactly what
    to_dnn_row()/the template emit after Task 3."""
    hdr, _sep = _dnn_header_lines(tpl_text)
    n = len(g._cells(hdr))
    assert n >= 3, "D-NN header without undup_origin/Resolution?"
    cells = ["D-%02d" % i] + ["x"] * (n - 3) + [undup, res]
    return "| " + " | ".join(cells) + " |"


def _model_real_dnn(tpl_text, row_line):
    hdr, sep = _dnn_header_lines(tpl_text)
    return GOOD3 + "\n## Divergences\n" + hdr + "\n" + sep + "\n" + row_line + "\n"


# positional-hazard proof: the last column of the REAL template HEADER is Resolution (not shifted by
# the insertion of undup_origin BEFORE it).  The literal "резолюция" below is the Russian column name "Resolution"; KEEP.
_web_hdr, _web_sep = _dnn_header_lines(_WEB_MODEL_RAW)
_ok = g._cells(_web_hdr)[-1].lower().startswith("резолюция")
print("  [%s] web template (system_model_web_template.md): last D-NN header column == "
      "'Resolution...': got=%r" % ("PASS" if _ok else "FAIL", g._cells(_web_hdr)[-1]))
results.append(_ok)
_ok2 = g._cells(_web_hdr)[-2].strip().lower() == "undup_origin"
print("  [%s] web template: second-to-last D-NN header column == 'undup_origin': got=%r"
      % ("PASS" if _ok2 else "FAIL", g._cells(_web_hdr)[-2]))
results.append(_ok2)

_contract_hdr, _contract_sep = _dnn_header_lines(_CONTRACT_MODEL_RAW)
_ok3 = g._cells(_contract_hdr)[-1].lower().startswith("резолюция")  # Russian column name "Resolution"; KEEP
print("  [%s] contract template (system_model_template.md): last D-NN header column == "
      "'Resolution...': got=%r" % ("PASS" if _ok3 else "FAIL", g._cells(_contract_hdr)[-1]))
results.append(_ok3)
_ok4 = g._cells(_contract_hdr)[-2].strip().lower() == "undup_origin"
print("  [%s] contract template: second-to-last D-NN header column == 'undup_origin': got=%r"
      % ("PASS" if _ok4 else "FAIL", g._cells(_contract_hdr)[-2]))
results.append(_ok4)

# FIRING -- web template
run("web template, real D-NN row, undup_origin='{TODO}', open -> FIRE",
    LEDGER_OK, _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="")),
    g.active_undup_origin_missing, True)
run("web template, undup_origin empty string, open -> FIRE",
    LEDGER_OK, _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="", res="")),
    g.active_undup_origin_missing, True)
run("web template, undup_origin='single-boundary-obvious' (weak -- an admission of a duplicate) -> FIRE",
    LEDGER_OK,
    _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="single-boundary-obvious", res="")),
    g.active_undup_origin_missing, True)
run("web template, undup_origin filled ('composition-seam'), BUT the divergence is already resolved (-> H-01) "
    "-> STILL FIRE if origin is empty (test below) -- here FILLED -> silent",
    LEDGER_OK,
    _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="composition-seam", res="→ H-01")),
    g.active_undup_origin_missing, False)
run("web template, undup_origin EMPTY, divergence ALREADY resolved (-> H-01) -> STILL FIRE "
    "(undup_origin is an axis separate from resolution, the Task 4 T4 verifier requires it for those taken into DRIVE too)",
    LEDGER_OK,
    _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="", res="→ H-01")),
    g.active_undup_origin_missing, True)
run("web template, undup_origin filled ('docs-runtime-gap') -> silent",
    LEDGER_OK,
    _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="docs-runtime-gap", res="")),
    g.active_undup_origin_missing, False)

# off-switch (the same signal as active_attention_gap_skipped/active_undup_sweep_incomplete)
run("off-switch: MODEL: N/A -> silent (ctx None)",
    LEDGER_NA, _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="")),
    g.active_undup_origin_missing, False)
run("off-switch: thin model (2 statused < 3) -> silent (first scout pass)",
    LEDGER_OK,
    model([row(1), row(2)]) + "\n## Divergences\n" + _web_hdr + "\n" + _web_sep + "\n"
    + _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="") + "\n",
    g.active_undup_origin_missing, False)
run("off-switch: no model at all (system_model.md absent) -> silent",
    LEDGER_OK, None, g.active_undup_origin_missing, False)
run("no D-NN row at all in the model -> silent (nothing to check)",
    LEDGER_OK, GOOD3, g.active_undup_origin_missing, False)

# FIRING -- contract template (namespace-agnostic: the same logic without the TB-/AC- prefix)
run("contract template, real D-NN row, undup_origin='{TODO}' -> FIRE",
    LEDGER_OK,
    _model_real_dnn(_CONTRACT_MODEL_RAW, _real_drow(_CONTRACT_MODEL_RAW, 1, undup="{TODO}", res="")),
    g.active_undup_origin_missing, True)
run("contract template, undup_origin='commodity-cold' (filled) -> silent",
    LEDGER_OK,
    _model_real_dnn(_CONTRACT_MODEL_RAW, _real_drow(_CONTRACT_MODEL_RAW, 1, undup="commodity-cold", res="")),
    g.active_undup_origin_missing, False)

# _undup_origin_missing_rows: direct parser contract -- a mixed set (missing/weak/filled)
_MIXED = (
    GOOD3 + "\n## Divergences\n" + _web_hdr + "\n" + _web_sep + "\n"
    + _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="") + "\n"
    + _real_drow(_WEB_MODEL_RAW, 2, undup="", res="") + "\n"
    + _real_drow(_WEB_MODEL_RAW, 3, undup="single-boundary-obvious", res="") + "\n"
    + _real_drow(_WEB_MODEL_RAW, 4, undup="composition-seam", res="") + "\n"
)
_missing = g._undup_origin_missing_rows(_MIXED)
print("  [%s] _undup_origin_missing_rows: 3 of 4 rows (D-01 {TODO}/D-02 empty/D-03 weak) flagged, "
      "D-04 (composition-seam) NOT flagged: got=%r" % ("PASS" if _missing == ["D-01", "D-02", "D-03"] else "FAIL", _missing))
results.append(_missing == ["D-01", "D-02", "D-03"])

# Plan 6 fix1: a killed D-NN (Resolution `c[-1]` = `KILLED file:line`) with an empty/{TODO} origin is NOT flagged --
# it will not go into a submission, origin is not needed, and the gate sits BEFORE active_core_enforced_needs_t9 (a dead
# row would block the path to T9). An open one with {TODO} is still flagged (regression). `-> H-NN`
# (driven) stays flagged -- covered by the test on the row around ~539.
run("Plan 6 fix1: KILLED row with undup_origin='{TODO}' (Resolution='KILLED src/Foo.sol:42') -> silent "
    "(killed is not submitted, does not block T9)",
    LEDGER_OK,
    _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="KILLED src/Foo.sol:42")),
    g.active_undup_origin_missing, False)
run("Plan 6 fix1 regression: OPEN row with undup_origin='{TODO}' (Resolution empty) -> FIRE",
    LEDGER_OK,
    _model_real_dnn(_WEB_MODEL_RAW, _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="")),
    g.active_undup_origin_missing, True)
# direct parser contract: KILLED with {TODO} excluded, open with {TODO} flagged -- in one set
_KILL_MIX = (
    GOOD3 + "\n## Divergences\n" + _web_hdr + "\n" + _web_sep + "\n"
    + _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="KILLED src/Foo.sol:42") + "\n"
    + _real_drow(_WEB_MODEL_RAW, 2, undup="{TODO}", res="") + "\n"
)
_kill_missing = g._undup_origin_missing_rows(_KILL_MIX)
print("  [%s] _undup_origin_missing_rows: KILLED row (D-01) excluded, open one (D-02) flagged: got=%r"
      % ("PASS" if _kill_missing == ["D-02"] else "FAIL", _kill_missing))
results.append(_kill_missing == ["D-02"])

# format-robust (benqi+axelar audit 2026-08-09): BULLET D-NN (axelar class) + whole-line origin scan.
# The previous `c[-2]` logic was blind: axelar bullets were not covered, benqi pipe without an
# origin column -> c[-2] in a foreign cell = a false "present". Now: a strong origin token ANYWHERE in the
# line = present; a bullet is checked too; killed is excluded.
_BULLET_MIX = (
    GOOD3 + "\n## Divergences\n"
    + "- **D-01 — express-execute forged-origin spoof (rank 9.2, depth-pot 6).** no origin tag\n"
    + "- **D-02 — multicall reuse; undup_origin: composition-seam.** strong origin inline\n"
    + "- **D-03 — dead path (rank 2).** KILLED src/X.sol:10\n"
)
_bmiss = g._undup_origin_missing_rows(_BULLET_MIX)
print("  [%s] bullet D-NN: D-01 (no origin) flagged, D-02 (composition-seam) NOT flagged, "
      "D-03 (KILLED) excluded: got=%r" % ("PASS" if _bmiss == ["D-01"] else "FAIL", _bmiss))
results.append(_bmiss == ["D-01"])

# whole-line robustness (benqi class): a pipe row, the origin token NOT in c[-2] but in the description -> present.
_WHOLELINE = (
    GOOD3 + "\n## Divergences\n"
    + "| D-01 | I-1 | ENFORCED-PARTIAL | asymmetry via composition-seam across modules | open |\n"
)
_wl = g._undup_origin_missing_rows(_WHOLELINE)
print("  [%s] pipe without an origin column, but 'composition-seam' in the description -> NOT flagged (whole-line): "
      "got=%r" % ("PASS" if _wl == [] else "FAIL", _wl))
results.append(_wl == [])

# ── H2. Positional regression via indirect callers (_has_open_divergence is positionally safe
#        after inserting undup_origin BEFORE Resolution -- covers active_model_axes_incomplete/
#        active_attention_gap_skipped, both call _has_open_divergence).
_OPEN_ROW = _real_drow(_WEB_MODEL_RAW, 1, undup="{TODO}", res="")
_RESOLVED_ROW = _real_drow(_WEB_MODEL_RAW, 1, undup="composition-seam", res="→ H-01")
_open_res = g._has_open_divergence(_model_real_dnn(_WEB_MODEL_RAW, _OPEN_ROW))
print("  [%s] _has_open_divergence: Resolution empty (undup_origin='{TODO}') -> True: got=%r"
      % ("PASS" if _open_res is True else "FAIL", _open_res))
results.append(_open_res is True)
_resolved_res = g._has_open_divergence(_model_real_dnn(_WEB_MODEL_RAW, _RESOLVED_ROW))
print("  [%s] _has_open_divergence: Resolution='-> H-01' -> False (Resolution is still [-1] after Task 3): "
      "got=%r" % ("PASS" if _resolved_res is False else "FAIL", _resolved_res))
results.append(_resolved_res is False)

run("active_model_axes_incomplete: open D-NN (real web template, undup_origin='{TODO}', "
    "Resolution empty) -> silent (drive D, positional-safe after Task 3, do not force new axes)",
    LEDGER_OK, bmodel(9) + "\n## Divergences\n" + _web_hdr + "\n" + _web_sep + "\n" + _OPEN_ROW + "\n",
    g.active_model_axes_incomplete, False)
run("active_attention_gap_skipped: open D-NN (same row) + Attention Gaps empty -> silent "
    "(an open D-NN lifts it -- drive it before T14, positional-safe after Task 3)",
    LEDGER_OK, bmodel(9) + "\n## Divergences\n" + _web_hdr + "\n" + _web_sep + "\n" + _OPEN_ROW + "\n",
    g.active_attention_gap_skipped, False)
# FIX-D (ethena-live 2026-08-12): an untouched `## Attention Gaps` = ONLY the template `>`-blockquote
# instruction (not data) -> `_section_content_lines` used to count it as "filled" -> the T14 gate was silent for the WHOLE run
# (template-satisfies-gate). A built model (9 I-NN), NO open D-NN, Attention Gaps = only `>` prose
# + an empty table -> T14 MUST FIRE (the detector must fire on an untouched template).
# The prose below is the real template text (Russian kept, matched by the hook): "Attention Gaps -- a second source of PLACE (T14)",
# "Filled from `deep/crowd_heat.json` ...", "Source intersection = maximum priority: ...", table header "Place | Source | Intersects with D-NN? | Taken into work"
_ATTN_TEMPLATE_PROSE = (
    "\n## Attention Gaps — второй источник МЕСТА (T14)\n\n"
    "> Заполняется из `deep/crowd_heat.json` (T14-A, фаза J-2) и `deep/commit_archaeology.json` (T14-B, J-1).\n"
    "> **Пересечение источников = максимальный приоритет:** файл со следом спешки в дыре аудит-карты.\n\n"
    "| Место | Источник (audit-hole / commit-haste / class-hole) | Пересекается с `D-NN`? | Взято в работу |\n"
    "|---|---|---|---|\n")
run("active_attention_gap_skipped: Attention Gaps = only template `>` prose (untouched), 0 open D-NN "
    "-> FIRE [FIX-D >-skip, template-satisfies-gate closed]",
    LEDGER_OK, bmodel(9) + _ATTN_TEMPLATE_PROSE, g.active_attention_gap_skipped, True)
# anti-FP: the same section, but with a REAL data row (bullet content, not `>`) -> silent (T14 done).
run("active_attention_gap_skipped: Attention Gaps with REAL bullet content -> silent (T14 filled)",
    LEDGER_OK, bmodel(9) + _ATTN_TEMPLATE_PROSE + "- EthenaMinting.sol cold-audit-hole × commit-haste 2024-11\n",
    g.active_attention_gap_skipped, False)

# ── Residual #2 (ethena-live, MED): active_attention_gap_stale -- T14 re-arm per T9 axis.
# T14 once-per-hunt: filled `## Attention Gaps` once -> attention_gap_skipped (cov>0) is silent forever,
# although every new T9 axis = new territory. Re-arm: axes N>=2, and attention-gap entries < N -> FIRE.
print("── AS. active_attention_gap_stale (residual #2 -- T14 re-arm per T9 axis)")


def _L_AX(n):
    return LEDGER_OK + "\n- **T9 restart axes used:** %d\n" % n


def _attn(entries):
    return _ATTN_TEMPLATE_PROSE + "".join(
        "- gap-%d EthenaMinting.sol cold-audit-hole × commit-haste 2024-1%d\n" % (i, i % 10)
        for i in range(1, entries + 1))


run("stale: 4 T9 axes, 1 attention entry (cov<N) -> FIRE (re-arm T14 for the new axes)",
    _L_AX(4), bmodel(9) + _attn(1), g.active_attention_gap_stale, True)
run("stale: 5 axes, 2 entries (cov<N) -> FIRE",
    _L_AX(5), bmodel(9) + _attn(2), g.active_attention_gap_stale, True)
# anti-FP: cov==0 "never" is the job of active_attention_gap_skipped, NOT stale (complement).
run("stale: 4 axes, 0 entries (cov==0, template only) -> silent (that is attention_gap_skipped)",
    _L_AX(4), bmodel(9) + _ATTN_TEMPLATE_PROSE, g.active_attention_gap_stale, False)
# anti-FP: the map keeps up with the axes (cov>=N).
run("stale: 4 axes, 4 entries (cov>=N) -> silent (map keeps up)",
    _L_AX(4), bmodel(9) + _attn(4), g.active_attention_gap_stale, False)
run("stale: 3 axes, 5 entries (cov>N) -> silent",
    _L_AX(3), bmodel(9) + _attn(5), g.active_attention_gap_stale, False)
# anti-FP: <2 axes -- too early to judge staleness.
run("stale: 1 axis, 1 entry -> silent (n<2, too early)",
    _L_AX(1), bmodel(9) + _attn(1), g.active_attention_gap_stale, False)
run("stale: 0 axes declared, 1 entry -> silent (n<2)",
    LEDGER_OK, bmodel(9) + _attn(1), g.active_attention_gap_stale, False)
# anti-FP: hunt-global Attention Gaps N/A -> a deliberate opt-out, respect it.
# (Fixture text kept Russian, matched by the hook: "Attention Gaps N/A -- target without public audits")
run("stale: 4 axes, but Attention Gaps N/A -> silent (global-N/A lifts it)",
    _L_AX(4), bmodel(9) + "\n## Attention Gaps\n\nAttention Gaps N/A — таргет без публичных аудитов\n",
    g.active_attention_gap_stale, False)
# anti-FP: MODEL N/A -> the whole model cluster is silent.
run("stale: MODEL N/A -> silent",
    LEDGER_NA + "\n- **T9 restart axes used:** 4\n", None, g.active_attention_gap_stale, False)
# anti-FP: thin model (<3 statused I-NN) -> still being built.
run("stale: thin model (2 I-NN) -> silent (model being built)",
    _L_AX(4), bmodel(2) + _attn(1), g.active_attention_gap_stale, False)
# A T9 line as a template placeholder ({…}) does not count as a declared axis.
run("stale: T9 axes = placeholder {0-3+} -> silent (n<2, placeholder does not count)",
    LEDGER_OK + "\n- **T9 restart axes used:** {0-3+ …}\n", bmodel(9) + _attn(1),
    g.active_attention_gap_stale, False)

# N-1: registry-floor -- under-declaring the prose counter no longer silences the re-arm.
_REG_HDR_AS = ("\n## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n"
               "|---|---|---|---|---|---|---|\n")
def _reg_ax(n_closed, status="CLOSED", typ="axis"):
    return _REG_HDR_AS + "".join(
        "| AX-0%d | %s | ось-%d | D-01 | 20 | %s | - |\n" % (i, typ, i, status)  # "ось" = "axis" (fixture title text)
        for i in range(1, n_closed + 1))
# FIX-G via the registry: T9 counter=1 (under-declared), but 4 CLOSED axis atoms + 1 entry -> FIRE.
run("stale N-1: registry 4 CLOSED axis + T9 counter=1 (under-decl.) + 1 entry -> FIRE (registry-floor)",
    LEDGER_OK + "\n- **T9 restart axes used:** 1\n" + _reg_ax(4), bmodel(9) + _attn(1),
    g.active_attention_gap_stale, True)
# anti-FP: the same 4 axis atoms, but OPEN (not CLOSED) -> registry-floor=0 -> silent (OPEN axes are not closed).
run("stale N-1 anti-FP: registry 4 OPEN axis (not CLOSED) + T9=0 + 1 entry -> silent",
    LEDGER_OK + _reg_ax(4, status="OPEN") + "\n- **T9 restart axes used:** 0\n", bmodel(9) + _attn(1),
    g.active_attention_gap_stale, False)
# axes_without_waves REINTERPRETATION N-1 (enzymefinance 2026-08-19): bulk closed-registry is NO LONGER demand.
# 4 CLOSED registry axes + 0 pivot/counter -> silent. Previously registry-floor gave FIRE, but on a mature hunt
# closed-count=62 (ordinary SELECT picks, not T9 restart) -> "a WAVE for every closed axis" is unsatisfiable.
# The cumulative "closed-without-a-wave" catch moved to model_first_nudge (preventive at the Agent boundary).
run("axes_without_waves REINTERP.: registry 4 CLOSED axis, NO pivot/counter -> silent (closed-count is not demand)",
    LEDGER_OK + _reg_ax(4), bmodel(9), g.active_axes_without_waves, False)
# enzyme-shape guard: MANY closed axes (20) in the registry, NO pivot/counter, waves exist -> silent
# (20 closed scout axes no longer require 20 waves; it would have been FIRE 20>waves).
run("axes_without_waves enzyme-guard: 20 CLOSED registry + WAVE-2 + no pivot -> silent (axes do not inflate demand)",
    LEDGER_OK + _reg_ax(20), bmodel(9) + _WAVE_INN, g.active_axes_without_waves, False)
# anti-FP axes_without_waves: no registry at all + no T9 line -> demand=0 -> silent (legacy).
run("axes_without_waves N-1 anti-FP: no registry + no T9 line -> silent (legacy unchanged)",
    LEDGER_OK, bmodel(9), g.active_axes_without_waves, False)
# scout-partition is axis-like too -> a CLOSED scout-partition counts as an axis in the registry-floor.
run("stale N-1: registry 3 CLOSED scout-partition + T9=0 + 1 entry -> FIRE (scout-partition = axis-like)",
    LEDGER_OK + _reg_ax(3, typ="scout-partition") + "\n- **T9 restart axes used:** 0\n",
    bmodel(9) + _attn(1), g.active_attention_gap_stale, True)

# ── FEAT-E (jito-live 2026-08-12): active_hybrid_fanout_stale -- fan-out-per-wave re-arm (mirror of AS).
# The fan-out ran once at the start -> on axes 2..N single scouts -> D-NN/cross-thread are under-produced.
print("── FE. active_hybrid_fanout_stale (FEAT-E — HYBRID Scout Fan-Out re-arm per T9 axis)")


def _fan(n):
    """n runs of the HYBRID fan-out with unique wf_ runIds (distinct-countable)."""
    # fixture text kept Russian (matched by the hook): "axis-N", "5 agents"
    return "".join("- HYBRID-fanout: ось-%d — wf_run%04d / 5 агентов\n" % (i, i * 13 + 7) for i in range(1, n + 1))


def _waves(k):
    """k extra `## WAVE-N` waves with 1 I-NN each (gives _wave_i_counts sections with the word 'wave')."""
    # fixture text kept Russian (matched by the hook): "new axis", "wave invariant"
    return "".join(
        "\n## WAVE-%d — новая ось\n- **I-%02d** [state] волновой инвариант %d. check: X-%d. pred: ENFORCED status: ENFORCED\n"
        % (i, 50 + i, i, i) for i in range(2, 2 + k))


# FE1 (enzymefinance 2026-08-19: demand=WAVES, not axes): 4 closed axes, 1 wave (base), 1 fan-out -> SILENT.
# Fan-out-per-wave is satisfied (1 wave <- 1 fan-out). "4 axes, but 1 wave" is the concern of active_axes_without_waves,
# not of the fan-out gate. Previously n=max(4,1)=4 -> runs(1)<4 -> a false FIRE "fan-out for EVERY axis".
run("fanout-stale: 4 axes + 1 wave + 1 fan-out -> silent (demand=waves; axes without waves are the concern of axes_without_waves)",
    _L_AX(4) + _fan(1), bmodel(9), g.active_hybrid_fanout_stale, False)
# FE2: 5 axes, 5 runs (runs>=N) -> silent (fan-out keeps up).
run("fanout-stale: 5 axes, 5 fan-out runs -> silent (keeps up)",
    _L_AX(5) + _fan(5), bmodel(9), g.active_hybrid_fanout_stale, False)
# FE3: 2 axes (<3 threshold) -> silent (too early/small hunt, fan-out is expensive).
run("fanout-stale: 2 axes, 0 runs -> silent (n<3, threshold)",
    _L_AX(2), bmodel(9), g.active_hybrid_fanout_stale, False)
# FE4: 4 axes, hunt-global `fanout N/A` -> silent (a deliberate opt-out).
# (Fixture text kept Russian: "fanout N/A -- single-file contract, fan-out not needed")
run("fanout-stale: 4 axes, fanout N/A -> silent (global-N/A lifts it)",
    _L_AX(4) + "\n- **fanout N/A — single-file контракт, веер не нужен**\n", bmodel(9),
    g.active_hybrid_fanout_stale, False)
# FE5: MODEL N/A -> the whole model cluster is silent.
run("fanout-stale: MODEL N/A -> silent",
    LEDGER_NA + "\n- **T9 restart axes used:** 4\n", None, g.active_hybrid_fanout_stale, False)
# FE6: thin model (<3 statused I-NN) -> being built.
run("fanout-stale: thin model (2 I-NN) -> silent (being built)",
    _L_AX(4) + _fan(1), bmodel(2), g.active_hybrid_fanout_stale, False)
# FE7: a registry fanout atom also counts as a run (5 axes, 4 wf + 1 fanout atom = 5 -> silent).
run("fanout-stale: 5 axes, 4 wf + 1 registry fanout atom = 5 runs -> silent (atom = run)",
    _L_AX(5) + _fan(4) + _reg_ax(1, typ="fanout"), bmodel(9), g.active_hybrid_fanout_stale, False)
# FE8 (Z2 judge HIGH-1): a placeholder line `{… fanout N/A …}` (template instruction) does NOT lift the off-switch
# -> the gate stays LIVE (fire at 4 axes, 1 run). Previously _FANOUT_NA_RE.search matched the placeholder -> dead.
# (Fixture text kept Russian: "none yet -- OR `fanout N/A -- reason`")
run("fanout-stale: 3 waves, 1 run + placeholder `{fanout N/A}` -> FIRE (not dead, Z2-fix)",
    _L_AX(4) + _fan(1) + "\n- **HYBRID-fanout:** {none yet — ИЛИ `fanout N/A — причина`}\n",
    bmodel(9) + _waves(2), g.active_hybrid_fanout_stale, True)
# FE9 (Z2): a REAL `fanout N/A — single-file` (without {}) -> silent (a deliberate opt-out).
run("fanout-stale: 4 axes + real `fanout N/A — single-file` -> silent",
    _L_AX(4) + _fan(1) + "\n- fanout N/A — single-file контракт\n", bmodel(9), g.active_hybrid_fanout_stale, False)  # "contract"


# FEAT-E per-wave (lombard-audit 2026-08-13): AXIS != WAVE -- a broad axis = several model waves
# `## WAVE-N`. FEAT-E hung on the number of AXES -> on early waves (axes <3) the fan-out was silent, although there were already 3+ waves. Fix:
# demand = number of model waves (enzymefinance 2026-08-19). These tests PROVE per-wave firing.
# FE10: 1 axis (n_axes=1), 2 extra waves (n_waves=3), 2 fan-outs -> FIRE (runs=2 < n_waves=3).
run("fanout-stale PER-WAVE: 1 axis + 2 WAVE sections (3 waves) + 2 fan-outs -> FIRE (fan-out lagged behind waves, lombard)",
    _L_AX(1) + _fan(2), bmodel(9) + _waves(2), g.active_hybrid_fanout_stale, True)
# FE11 anti-FP: the fan-out keeps up with the waves (3 waves, 3 runs) -> silent.
run("fanout-stale PER-WAVE: 1 axis + 2 WAVE sections (3 waves) + 3 fan-outs -> silent (fan-out keeps up with waves)",
    _L_AX(1) + _fan(3), bmodel(9) + _waves(2), g.active_hybrid_fanout_stale, False)
# FE12 anti-FP: a single-wave model (n_waves=1) + 1 axis -> n=1<3 -> silent (per-wave does not FP at the start).
run("fanout-stale PER-WAVE: 1 axis + 0 WAVE sections (1 wave) + 0 fan-outs -> silent (n<3, too early)",
    _L_AX(1), bmodel(9), g.active_hybrid_fanout_stale, False)
# FE13 (enzymefinance 2026-08-19): WAVE-2 (n_waves=2) + 1 fan-out -> FIRE. Previously n=max(1,2)=2<MIN_AXES(3) ->
# silent -> a wave-2 plain scout slipped through. Wave-floor=2 catches it IMMEDIATELY (not deferring to wave-3).
run("fanout-stale PER-WAVE: 1 axis + 1 WAVE section (2 waves) + 1 fan-out -> FIRE (wave-2 no longer slips through)",
    _L_AX(1) + _fan(1), bmodel(9) + _waves(1), g.active_hybrid_fanout_stale, True)
# FE14 anti-FP: wave-2 + 2 fan-outs (keeps up) -> silent.
run("fanout-stale PER-WAVE: 1 axis + 1 WAVE section (2 waves) + 2 fan-outs -> silent (fan-out keeps up)",
    _L_AX(1) + _fan(2), bmodel(9) + _waves(1), g.active_hybrid_fanout_stale, False)
# FE15 anti-FP: 2 axes + 1 wave (n_waves=1) -> neither floor reached -> silent (FE3 class preserved).
run("fanout-stale: 2 axes + 1 wave -> silent (n_waves<2 AND n_axes<3 -- both floors missed)",
    _L_AX(2), bmodel(9), g.active_hybrid_fanout_stale, False)
# FE16 (enzymefinance 2026-08-19 CORE FIX): MANY closed axes (20) + 3 waves + 3 fan-outs -> silent.
# DEMAND=n_waves(3), NOT max(20,3)=20. Old logic: runs(3)<20 -> a false FIRE (a fan-out for EVERY scout axis,
# unsatisfiable on a mature hunt -> noise). Critical regression guard: axes no longer inflate demand.
run("fanout-stale CORE: 20 axes + 3 waves + 3 fan-outs -> silent (demand=waves, not 20 closed axes)",
    _L_AX(20) + _fan(3), bmodel(9) + _waves(2), g.active_hybrid_fanout_stale, False)
# FE17: the same 20 axes + 3 waves, but 2 fan-outs (< waves) -> FIRE (a real per-wave gap, axes do not mask it).
run("fanout-stale CORE: 20 axes + 3 waves + 2 fan-outs -> FIRE (fan-out lagged behind WAVES, axes do not inflate)",
    _L_AX(20) + _fan(2), bmodel(9) + _waves(2), g.active_hybrid_fanout_stale, True)
# FE18 (counter fix): a bare runId in the WAVE-MERGE heading `### WAVE-N MERGE (HYBRID-веер <id>...)` counts as a
# run -- enzyme logs it THIS way, the old counter saw only the `wf_` form (2 of 11). 3 bare ids = 3 runs.
# ("HYBRID-веер" = "HYBRID fan-out", "агентов" = "agents": Russian regex input, KEPT)
_BARE_MERGE = ("\n### WAVE-3 MERGE (HYBRID-веер wz9twjv1b, 8 агентов)\n"
               "### WAVE-4 MERGE (HYBRID-веер w2rfh09y8, 8 агентов)\n"
               "### WAVE-5 MERGE (HYBRID-веер wd6inhvl9, 8 агентов)\n")
run("fanout-stale counter: 1 axis + 3 waves + 3 bare runIds in MERGE headings -> silent (counter sees bare ids)",
    _L_AX(1) + _BARE_MERGE, bmodel(9) + _waves(2), g.active_hybrid_fanout_stale, False)
# FE19 anti-FP counter: 2 bare runIds + a prose line with `divergence_fanout.workflow.js` (NOT a runId --
# a tight separator cuts the FP on "workflow") -> runs=2 < 3 waves -> FIRE (workflow was not counted as a run).
# (prose line = "the fan-out (divergence_fanout.workflow.js) runs on every wave"; Russian regex input, KEPT)
run("fanout-stale counter anti-FP: 2 bare runIds + prose `workflow.js` -> FIRE (workflow is not a runId)",
    _L_AX(1) + "\n### WAVE-3 MERGE (HYBRID-веер wz9twjv1b, 8 агентов)\n"
    "### WAVE-4 MERGE (HYBRID-веер w2rfh09y8, 8 агентов)\n"
    "- веер (divergence_fanout.workflow.js) гоняется на каждой волне\n",
    bmodel(9) + _waves(2), g.active_hybrid_fanout_stale, True)

# ── FEAT-I (jito-live 2026-08-12): active_crossthread_synthesis_stale -- a single building-block engine.
print("── FI. active_crossthread_synthesis_stale (FEAT-I — refuted+banked+D-NN cross-thread re-arm)")


def _bb_ledger(n_ref, n_bank, synth=""):
    """n_ref refuted [KILLED] H-NN + n_bank banked findings + an optional synth line."""
    ref = "\n## Refuted\n" + "".join(
        "### H-%02d [KILLED] falsifier processor.rs:%d\n" % (i, i * 10) for i in range(1, n_ref + 1))
    # Banked Findings table header (Russian column names kept: "What", "Status")
    bank = ("\n## Banked Findings\n\n| # | Severity | H-NN | Что | output | input | tier | found_by | Статус |\n"
            "|---|---|---|---|---|---|---|---|---|\n" + "".join(
                "| %d | Low | H-%02d | leak-%d | out-%d | in-%d | tier4 | scout | confirmed |\n" % (i, i, i, i, i)
                for i in range(1, n_bank + 1)))
    return (LEDGER_OK + ref + bank + "\n" + (synth + "\n" if synth else "") + "\n## Active Hypotheses\n")


_MDL_DNN = bmodel(9) + "\n## Divergences\n- **D-01** — conservation gap → open\n"  # +1 D-NN
# FI1: 2 refuted + 2 banked + 1 D-NN = 5 bb (>=4), synthesis not run -> FIRE.
run("FI1: 2 refuted + 2 banked + 1 D-NN = 5 bb, no synthesis -> FIRE",
    _bb_ledger(2, 2), _MDL_DNN, g.active_crossthread_synthesis_stale, True)
# FI2: the same 5 bb + cross-thread synthesis DONE(N=5) -> silent.
run("FI2: 5 bb + synthesis DONE(N=5) -> silent (covered)",
    _bb_ledger(2, 2, "- **cross-thread synthesis:** DONE (N=5) — no distant pairs"),
    _MDL_DNN, g.active_crossthread_synthesis_stale, False)
# FI3: 5 bb + DONE(N=3) -> FIRE (the pool grew beyond what was checked).
run("FI3: 5 bb + synthesis DONE(N=3) -> FIRE (pool grew, re-arm)",
    _bb_ledger(2, 2, "- **cross-thread synthesis:** DONE (N=3) — chain A→B"),
    _MDL_DNN, g.active_crossthread_synthesis_stale, True)
# FI4: 1 refuted + 1 banked + 0 D-NN = 2 (<4) -> silent (too few building-blocks).
run("FI4: 2 building-blocks (<4) -> silent (too early)",
    _bb_ledger(1, 1), bmodel(9), g.active_crossthread_synthesis_stale, False)
# FI5: 5 bb + DONE without N -> silent (legacy backward-compat).
run("FI5: 5 bb + synthesis DONE without N -> silent (legacy)",
    _bb_ledger(2, 2, "- **cross-thread synthesis:** DONE — no pairs"),
    _MDL_DNN, g.active_crossthread_synthesis_stale, False)
# FI6: MODEL N/A -> silent.
run("FI6: MODEL N/A -> silent", _bb_ledger(2, 2) + "\n- **MODEL: N/A**\n",
    "MODEL: N/A — single contract\n", g.active_crossthread_synthesis_stale, False)
# FI7: immature model (2 I-NN) -> silent (building-blocks not yet accumulated).
run("FI7: immature model (2 I-NN) -> silent", _bb_ledger(2, 2), bmodel(2),
    g.active_crossthread_synthesis_stale, False)

# ── FEAT-C (jito-live 2026-08-12): active_strong_refute_unrechecked -- cold-recheck of a strong refute.
print("── FC. active_strong_refute_unrechecked (FEAT-C — false-refute guard)")
# 2 refuted High/Crit threads without a cold-recheck -> FIRE.
run("FC1: 2 refuted High threads + 0 cold-recheck -> FIRE",
    LEDGER_OK + "\n## Refuted\n### H-03 [KILLED] High severity — falsifier vault.rs:88\n"
    "### H-05 [CONTESTED] Critical share-inflation — guard blocks\n", bmodel(9),
    g.active_strong_refute_unrechecked, True)
# cold-recheck done -> silent. (Fixture text kept Russian: "cold agent confirmed the refute")
run("FC2: 2 refuted High + cold-recheck entry -> silent",
    LEDGER_OK + "\n## Refuted\n### H-03 [KILLED] High — falsifier vault.rs:88\n"
    "- cold-recheck: H-03 — cold-агент подтвердил refute\n", bmodel(9),
    g.active_strong_refute_unrechecked, False)
# refuted, but Low/Medium (not strong) -> silent.
run("FC3: refuted Low/Medium (not High/Crit) -> silent",
    LEDGER_OK + "\n## Refuted\n### H-07 [KILLED] Low dust-rounding — de-minimis\n", bmodel(9),
    g.active_strong_refute_unrechecked, False)
# immature model -> silent.
run("FC4: immature model (2 I-NN) -> silent",
    LEDGER_OK + "\n## Refuted\n### H-03 [KILLED] High — x\n", bmodel(2),
    g.active_strong_refute_unrechecked, False)
# HUNT-EXIT -> silent.
run("FC5: HUNT-EXIT -> silent",
    LEDGER_OK + "\n- **HUNT-EXIT: T4-CONFIRMED High**\n## Refuted\n### H-03 [KILLED] High — x\n", bmodel(9),
    g.active_strong_refute_unrechecked, False)
# placeholder refuted heading ({...}) -> silent.
run("FC6: refuted heading placeholder {…} -> silent",
    LEDGER_OK + "\n## Refuted\n### {H-NN [KILLED] High — falsifier}\n", bmodel(9),
    g.active_strong_refute_unrechecked, False)
# FC7 (Z2 judge MED): severity in the BODY (canonical format), heading without severity -> FIRE (Z2-fix block-scan).
run("FC7/Z2: `### H-03 [KILLED]: xss` + body `**Severity:** High` -> fire (severity in the body)",
    LEDGER_OK + "\n## Refuted\n### H-03 [KILLED]: reflected XSS via symbol\n"
    "- **Severity if confirmed:** High\n- falsifier: vault.rs:88\n", bmodel(9),
    g.active_strong_refute_unrechecked, True)
# FC8 (Z2): severity in the body, but Low -> silent (not a strong thread).
run("FC8/Z2: heading without sev + body `**Severity:** Low` -> silent (not High/Crit)",
    LEDGER_OK + "\n## Refuted\n### H-07 [KILLED]: dust rounding\n- **Severity if confirmed:** Low\n", bmodel(9),
    g.active_strong_refute_unrechecked, False)
# FC9 (lombard-audit item 6, the MAIN hole): a label line `cold-recheck: PENDING` does NOT lift the off-switch
# (previously the substring "cold-recheck" silenced the gate without a real recheck).
# (Fixture text kept Russian: "if I get the live rules")
run("FC9/lombard: refuted High + `cold-recheck: PENDING` -> FIRE (a PENDING label is not an off-switch)",
    LEDGER_OK + "\n## Refuted\n### H-03 [KILLED]: allowlist bypass\n- **Severity if confirmed:** High\n"
    "- cold-recheck (FEAT-C): PENDING — если добуду live-правила\n", bmodel(9),
    g.active_strong_refute_unrechecked, True)
# FC10 (lombard-audit item 6): a `[SCOPED-OUT]` of a strong thread also requires a cold-recheck (soft-kill taxonomy).
run("FC10/lombard: refuted High `[SCOPED-OUT]` + 0 cold-recheck -> FIRE (soft-kill of a strong thread)",
    LEDGER_OK + "\n## Refuted\n### H-01 [SCOPED-OUT — on-chain resolved]: merkle head/tail decoupling\n"
    "- **Severity if confirmed:** High/Critical\n", bmodel(9),
    g.active_strong_refute_unrechecked, True)
# FC11: `[SCOPED-OUT]` + cold-recheck WITH AN OUTCOME -> silent (the practice was followed).
# (Fixture text kept Russian: "cold agent refuted my falsifier, the bug is real")
run("FC11/lombard: `[SCOPED-OUT]` High + `cold-recheck — refuted the refute` -> silent",
    LEDGER_OK + "\n## Refuted\n### H-01 [SCOPED-OUT]: merkle decoupling\n- **Severity:** High\n"
    "- cold-recheck: H-01 — cold-агент опроверг мой falsifier, баг реален\n", bmodel(9),
    g.active_strong_refute_unrechecked, False)
# FC12: placeholder `- cold-recheck: {none yet …}` (with an outcome word inside {}) -> FIRE (a placeholder does not count).
# (Fixture text kept Russian: "cold agent confirmed/refuted")
run("FC12: refuted High + `cold-recheck: {none yet}` placeholder -> FIRE",
    LEDGER_OK + "\n## Refuted\n### H-03 [KILLED]: x\n- **Severity:** High\n"
    "- cold-recheck: {none yet — cold-агент подтвердил/опроверг}\n", bmodel(9),
    g.active_strong_refute_unrechecked, True)

print("── I. active_chain_dependency_unproven (Task 6, plan 6 sec. 27) — cross-attack-chains T3 gate")

CHAIN_NO_PROOF_1 = (
    LEDGER_OK + "\n### H-03: sAVAX external oracle\n"
    "- **Composite candidates:** BB-08b (staleness), BB-10 (external node)\n"
)
run("Composite candidates (real folksfinance H-03old form) without output->input nearby -> FIRE",
    CHAIN_NO_PROOF_1, None, g.active_chain_dependency_unproven, True)

CHAIN_NO_PROOF_2 = (
    LEDGER_OK + "\n## Building Blocks (T6 inventory — small signals to chain later)\n\n"
    "- [ ] BB-01 — auth.py:120 — missing token check — risk: low\n"
    "- [ ] BB-01 + BB-03 combine into a Critical drain (see H-05)\n"
    "- [ ] BB-03 — nonce.py:44 — nonce reuse — risk: med\n"
)
run("co-occurring BB-NN in one bullet (Building Blocks) without a dependency phrase -> FIRE",
    CHAIN_NO_PROOF_2, None, g.active_chain_dependency_unproven, True)

CHAIN_PROVEN = (
    LEDGER_OK + "\n### H-03: sAVAX external oracle\n"
    "- **Composite candidates:** BB-08b (staleness)\n"
    "  BB-08b's output (stale rate) feeds directly into this H's input valuation calc.\n"
)
run("Composite candidates with an explicit output->input nearby -> silent (proven link)",
    CHAIN_PROVEN, None, g.active_chain_dependency_unproven, False)

CHAIN_NONE_1 = (
    LEDGER_OK + "\n## Building Blocks (T6 inventory — small signals to chain later)\n\n"
    "- [ ] BB-01 — `{file}:{line}` — {observation} — risk: low/med\n"
    "- [ ] BB-02 — ...\n"
)
run("unfilled Building Blocks template -> silent (no claim, placeholder)",
    CHAIN_NONE_1, None, g.active_chain_dependency_unproven, False)

CHAIN_NONE_2 = (
    LEDGER_OK + "\n## Building Blocks (T6 inventory — small signals to chain later)\n\n"
    "- [ ] BB-01 — auth.py:120 — missing token check — risk: low\n"
    "- [ ] BB-02 — nonce.py:44 — nonce reuse — risk: med\n"
)
run("independent BB without a co-occurrence claim -> silent",
    CHAIN_NONE_2, None, g.active_chain_dependency_unproven, False)

# Structural check: the T3 gate is CALLED inside the `if not manual and not any(INFO_REQUEST)` cluster
# (composite/depth, 3b), BEFORE the MODEL cluster (which does NOT respect INFO_REQUEST, P2 katana) -- "respecting
# INFO_REQUEST" (Task 6 brief) is a property of the call SITE in main(), not of the detector itself (the same
# pattern as active_ledger_composite_abandoned/active_ledger_wide_but_shallow -- neither of them checks
# INFO_REQUEST by itself either, the call-site does it).
with open(_HOOK, "r", encoding="utf-8") as _f:
    _src = _f.read()
_main_idx = _src.find("\ndef main(")
_call_idx = _src.find("active_chain_dependency_unproven(current_sid)", _main_idx)
_cluster_idx = _src.rfind(
    "if not manual and not any(q in ul for q in INFO_REQUEST):", 0, _call_idx) if _call_idx > 0 else -1
_next_cluster_idx = _src.find("# 3d) MODEL-кластер", _cluster_idx) if _cluster_idx > 0 else -1  # hook comment marker "MODEL cluster" (Russian text in the hook source; KEEP)
_in_info_cluster = (_call_idx > 0 and _cluster_idx > 0 and _next_cluster_idx > 0
                     and _cluster_idx < _call_idx < _next_cluster_idx)
print("  [%s] T3-gate call sits inside the `if not manual and not any(INFO_REQUEST)` cluster "
      "(composite/depth), BEFORE the MODEL cluster: got=%s" % ("PASS" if _in_info_cluster else "FAIL", _in_info_cluster))
results.append(_in_info_cluster)

print("── I2. fix-round 1 — none-marker off-switch + comma-connector MINOR")
# IMPORTANT: `**Composite candidates:**` filled with a NONE MARKER (not a `{TODO}` placeholder, real
# text that hunters really write after resolving a lead as non-composite) -> the old off-switch
# ("{" in cand) did NOT catch it -> a spurious FIRE on almost every standard ledger
# (berachain/chainlink/enzyme-onyx/folksfinance/trufin/usdn-contracts/user). Fix: cand without a `BB-`/`H-` id
# reference -> not a claim.
# The tuple below includes the Russian none-marker "нет" ("none") -- a regex input, KEPT.
for _none_marker in ("—", "N/A", "none", "нет"):
    _ledger = LEDGER_OK + "\n### H-03: resolved, not a chain\n- **Composite candidates:** %s\n" % _none_marker
    run("none-marker '%s' in Composite candidates -> silent (not a claim, id-ref absent)" % _none_marker,
        _ledger, None, g.active_chain_dependency_unproven, False)

# NEGATIVE (regression guard): the real folksfinance form (id-ref present) MUST survive the fix -> still FIRE.
run("regression: Composite candidates with real BB ids (folksfinance form) STILL FIRE after fix-round 1",
    CHAIN_NO_PROOF_1, None, g.active_chain_dependency_unproven, True)

# MINOR: the comma-connector is removed from the bb branch -- a co-listing status line ("Refuted BB-01, BB-02 today")
# no longer matches (a lone comma, without a combine/direction word).
CHAIN_COMMA_ONLY = (
    LEDGER_OK + "\n## Building Blocks (T6 inventory — small signals to chain later)\n\n"
    "- [x] Refuted BB-01, BB-02 today — both dead ends, unrelated causes — risk: low\n"
)
run("MINOR fix: co-occurring BB-NN via a BARE comma (not a combine word) -> silent",
    CHAIN_COMMA_ONLY, None, g.active_chain_dependency_unproven, False)
# regression: the '+'-connector (a real claim pattern, the FIRING case above) is not hurt by removing the comma.
run("regression: '+'-connector BB-NN co-occurrence (CHAIN_NO_PROOF_2) STILL FIRE after fix-round 1",
    CHAIN_NO_PROOF_2, None, g.active_chain_dependency_unproven, True)

print("── I3. fix-round 2 — single-id false positive (round-1 residual)")
# Real ledgers (folksfinance:352, impossible-cloud-network:136, chainlink/user hypotheses.md)
# write a SINGLE candidate without a second side -> round-1 (0-id off-switch) did NOT catch this (1 id-ref
# is still "a reference"). Fix: require >=2 DISTINCT id-refs, OR 1 id-ref + an explicit chain word nearby.
run("single BB-06 (folksfinance:352 form, no chain word) -> silent (was an FP)",
    LEDGER_OK + "\n### H-02: some lead\n- **Composite candidates:** BB-06\n",
    None, g.active_chain_dependency_unproven, False)
run("single H-01 (impossible-cloud-network:136 / chainlink / user form) -> silent",
    LEDGER_OK + "\n### H-02: some lead\n- **Composite candidates:** H-01\n",
    None, g.active_chain_dependency_unproven, False)
run("1 id + an explicit chain word nearby ('chained with') -> FIRE (a real single-id claim is preserved)",
    LEDGER_OK + "\n### H-02: some lead\n- **Composite candidates:** BB-06 chained with reentrancy in H-02\n",
    None, g.active_chain_dependency_unproven, True)
run("regression: 2 distinct ids (folksfinance H-03old form, BB-08b + BB-10) STILL FIRE",
    CHAIN_NO_PROOF_1, None, g.active_chain_dependency_unproven, True)
run("regression: none-marker '—' STILL silent (round-1 not broken)",
    LEDGER_OK + "\n### H-03: resolved, not a chain\n- **Composite candidates:** —\n",
    None, g.active_chain_dependency_unproven, False)

print("── I4. fix-round 3 — bb-branch same-id-twice false positive")
# A real chainlink:550-style fragment: THE SAME id (BB-06) is mentioned TWICE in narrative (not a
# two-party claim; the "→" inside the text matched as a connector) -- round-2 deduped ONLY the cand branch,
# the bb branch (co-occurring BB-NN in Building Blocks) did not check id distinctness at all -> FP.
# (The fixture is a real Russian ledger fragment: "adversary-'for' only -> severity NOT trusted, realistically lower.
#  I am driving skeptic-T4 on BB-06 (the only one with a real incremental history)". KEPT -- regex input.)
CHAIN_SAME_ID_TWICE = (
    LEDGER_OK + "\n## Building Blocks (T6 inventory — small signals to chain later)\n\n"
    "- [x] BB-06 = adversary-«за» only → severity НЕ доверенный, реалистично ниже. "
    "Гоню skeptic-T4 на BB-06 (единственный с real incremental-историей) — risk: low\n"
)
run("chainlink:550-style: the same id (BB-06) twice in one bullet -> silent (was an FP)",
    CHAIN_SAME_ID_TWICE, None, g.active_chain_dependency_unproven, False)

# regression: the bb branch on 2 DIFFERENT ids (CHAIN_NO_PROOF_2, '+'-connector) STILL FIRE -- dedup did not
# over-silence a legitimate co-occurrence claim.
run("regression: bb branch, 2 DIFFERENT ids ('+'-connector, CHAIN_NO_PROOF_2) STILL FIRE after fix-round 3",
    CHAIN_NO_PROOF_2, None, g.active_chain_dependency_unproven, True)
# regression: the cand branch (folksfinance form, 2 different ids) is not affected by the bb-path edit.
run("regression: cand branch (folksfinance form, 2 different ids) STILL FIRE after fix-round 3",
    CHAIN_NO_PROOF_1, None, g.active_chain_dependency_unproven, True)

# FULL real file (the repro was found on it) -- must not falsely fire.
_CHAINLINK_LEDGER_PATH = _os.path.join(_TOOLKIT_ROOT, "sessions", "chainlink", "hypotheses.md")
if _os.path.exists(_CHAINLINK_LEDGER_PATH):
    _chainlink_raw = open(_CHAINLINK_LEDGER_PATH, encoding="utf-8").read()
    run("FULL sessions/chainlink/hypotheses.md -> silent (repro target, not only a one-line fragment)",
        _chainlink_raw, None, g.active_chain_dependency_unproven, False)
else:
    print("  [SKIP] sessions/chainlink/hypotheses.md is absent in this environment -- skipped")

print("── I5. fix-round 4 — bb-branch span-distinct fooled by a stray 3rd id")
# A real bug-bounties:215-style case: the bb alternation pairs the TWO ENDS BB-07...BB-07 (a self-reference,
# the same class as chainlink:550), but a STRAY id H-09 dangles between them (a findings tally
# "Net: 1 marginal Low (H-09) + BB-07", not a chain). Round-3's span-distinct set({BB-07,H-09})==2
# falsely "rescued" the self-reference -> FP. Round-4: compare exactly the TWO ENDS that the regex really
# paired (findall()[0]/findall()[-1]), not a distinct-set over the whole span.
# (Fixture kept Russian where it is real ledger prose: "N/A-marked", axes 1-3 -> WAVE-2/3/4; 4-17 -> N/A-marked.)
CHAIN_SAME_ENDPOINT_STRAY_ID = (
    LEDGER_OK + "\n- **T9 restart axes used:** 17 (16 liquidation dust-branch→CLEAN/BB-07-Low, "
    "17 oracle-adapter I-22-PARTIAL→running). Axes 1-3→WAVE-2/3/4; 4-17→N/A-помечены. "
    "**Net: 1 marginal Low (H-09) + BB-07 Low-self-mitigable.**\n"
)
run("bug-bounties:215-style: ends BB-07...BB-07 (self-reference) + a stray H-09 in the span -> silent (was an FP)",
    CHAIN_SAME_ENDPOINT_STRAY_ID, None, g.active_chain_dependency_unproven, False)

# regression: 2 DIFFERENT ENDS (BB-01...BB-03) -> STILL FIRE (the endpoint guard did not over-silence a legit claim).
run("regression: 2 different ENDPOINT ids (BB-01...BB-03, CHAIN_NO_PROOF_2) STILL FIRE after fix-round 4",
    CHAIN_NO_PROOF_2, None, g.active_chain_dependency_unproven, True)

# regression: same-endpoint WITHOUT a third id (chainlink:550, the round-3 case) -> STILL silent.
run("regression: chainlink:550-style (same endpoint, no stray id) STILL silent after fix-round 4",
    CHAIN_SAME_ID_TWICE, None, g.active_chain_dependency_unproven, False)

# FULL real file (the repro was found on it).
_BUGBOUNTIES_LEDGER_PATH = _os.path.join(_TOOLKIT_ROOT, "sessions", "bug-bounties", "hypotheses.md")
if _os.path.exists(_BUGBOUNTIES_LEDGER_PATH):
    _bugbounties_raw = open(_BUGBOUNTIES_LEDGER_PATH, encoding="utf-8").read()
    run("FULL sessions/bug-bounties/hypotheses.md -> silent (repro target, not only a one-line fragment)",
        _bugbounties_raw, None, g.active_chain_dependency_unproven, False)
else:
    print("  [SKIP] sessions/bug-bounties/hypotheses.md is absent in this environment -- skipped")

print("── I6. fix-round 5 (jito live run 2026-08-12) — severity arrow != chain-connector")
# A REAL FP on a LIVE hunt: the bb branch held `→` in the loose alternation `BB-NN [0,80] → [0,80] BB-NN`,
# but `→` in ledgers OVERWHELMINGLY means a TRANSITION (severity `INERT→OOS/Low`, `Medium→High`, status
# `PENDING→DONE`, resolution `→ H-03`), NOT a chain-connector. jito-335: "LEAD-1 late-close (BB-12, ...
# slash-dodge INERT→OOS/Low), LEAD-2 rent-dust (BB-13)" -- TWO SEPARATE residuals, the arrow glued
# to severity tokens. The gate fired -> the agent was forced to MUTILATE the ledger ("removing the arrow between
# BB refs, surgical prose-fix") to get around it. A gate that forces damage to the artifact is worse than no
# gate. Fix: `→`/`->` work ONLY in the adjacency form `BB-04 → BB-05` (the arrow DIRECTLY between ids,
# no prose) = a terse notation of a real chain; the loose alternation keeps the unambiguous
# `+`/`&`/`with`/`chain*`/`combin*`.
# (The fixtures below are real Russian ledger prose -- regex inputs, KEPT.)
CHAIN_SEVERITY_ARROW_JITO = (
    LEDGER_OK + "\n  - 12 — AX-11 epoch-crank tracker lifecycle: WAVE-8 (5 I-NN) + self-drive depth-6 "
    "+ cold-scout abc7b823 **CONVERGED** → H1-H5 KILLED, hardened. LEAD-1 late-close (BB-12, liveness "
    "self-heal, slash-dodge INERT→OOS/Low), LEAD-2 rent-dust (BB-13). EXPOSURE full-scope re-run.\n"
)
run("jito-335 (LIVE hunt): severity arrow INERT→OOS/Low between BB-12/BB-13 -> silent (was an FP, the agent "
    "mutilated the ledger to get around the gate)",
    CHAIN_SEVERITY_ARROW_JITO, None, g.active_chain_dependency_unproven, False)
run("severity transition Medium→High between two BB -> silent (same class)",
    LEDGER_OK + "\n- iter 7 — BB-04 dust-rounding, severity Medium→High после амплификации; "  # "after amplification"
    "BB-05 отдельный residual\n", None, g.active_chain_dependency_unproven, False)  # "a separate residual"
run("status transition PENDING→DONE between two BB -> silent (same class)",
    LEDGER_OK + "\n- BB-08 scout-lead, статус PENDING→DONE; BB-09 второй лид, не связаны\n",  # "status ...; second lead, not related"
    None, g.active_chain_dependency_unproven, False)
# anti-regression: a TERSE real chain `BB-04 → BB-05` (arrow DIRECTLY between ids) STILL FIRE --
# the narrowing must not blind the gate to genuine arrow-notation chains.
run("terse chain BB-04 → BB-05 (adjacency, no proof) -> STILL FIRE (not blinded)",
    LEDGER_OK + "\n- BB-04 → BB-05 — обе на vault, цепляем\n",  # "both on the vault, chaining"
    None, g.active_chain_dependency_unproven, True)
run("terse chain ASCII BB-04 -> BB-05 (adjacency) -> FIRE",
    LEDGER_OK + "\n- BB-04 -> BB-05 эскалация\n", None, g.active_chain_dependency_unproven, True)  # "escalation"
run("terse chain BB-04 → BB-05 WITH output->input proof -> silent (proven)",
    LEDGER_OK + "\n- BB-04 → BB-05: output BB-04 (stale flag) становится input BB-05\n",  # "becomes"
    None, g.active_chain_dependency_unproven, False)
# regression: the word connectors (rounds 1-4) are NOT touched by the narrowing.
run("regression: '+'-connector (CHAIN_NO_PROOF_2) STILL FIRE after fix-round 5",
    CHAIN_NO_PROOF_2, None, g.active_chain_dependency_unproven, True)
run("regression: Composite candidates (CHAIN_NO_PROOF_1) STILL FIRE after fix-round 5",
    CHAIN_NO_PROOF_1, None, g.active_chain_dependency_unproven, True)
# FULL real LIVE ledger of jito (read-only) -- the gate must not fire on it after the fix.
_JITO_LEDGER_PATH = _os.path.join(_TOOLKIT_ROOT, "sessions", "jito", "hypotheses.md")
if _os.path.exists(_JITO_LEDGER_PATH):
    _jito_raw = open(_JITO_LEDGER_PATH, encoding="utf-8").read()
    run("FULL live sessions/jito/hypotheses.md -> silent (do not disturb a real hunt)",
        _jito_raw, None, g.active_chain_dependency_unproven, False)
else:
    print("  [SKIP] sessions/jito/hypotheses.md is absent -- skipped")

print("── J. active_ai_trust_unresolved (Task 3, plan 7 sec. 60) — producer-absent canon (P-AI)")
# A copy of active_authz_matrix_skipped (producer-absent), BUT the namespace guard covers BOTH web profiles
# (the ai-trust axis lives in both the TB- and the AC- model). Tested like active_composition_pass_skipped (H/G):
# optionally put the producer `ai_trust_matrix.md` NEXT TO the ledger BEFORE the call (co-located form).


def run_ai(name, ledger_txt, model_txt, ai_content, expect):
    """Like run_cm, but puts `ai_trust_matrix.md` (the Task 1 producer) next to the ledger. ai_content=None
    -> the file is not created (producer was not run)."""
    d = setup(ledger_txt, model_txt)
    try:
        if ai_content is not None:
            with open(os.path.join(d, "ai_trust_matrix.md"), "w", encoding="utf-8") as f:
                f.write(ai_content)
        got = bool(g.active_ai_trust_unresolved("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


# web models: namespace TB (dapphunt) / AC (web2). {...} placeholders cut out.
# (Table headers and cell text are Russian fixture text parsed by the hook: "Formula", "surface-trust perimeter",
#  "check the boundary", "authz perimeter", "check the role", "check"; KEPT.)
WEB_MODEL_TB = (
    "## Invariants\n"
    "| ID | Формула | check |\n"
    "|---|---|---|\n"
    "| TB-I01 | surface-trust периметр | проверить границу |\n"
    "| TB-I02 | ai-trust: context != instruction | проверить re-authz |\n"
)
WEB_MODEL_AC = (
    "## Invariants\n"
    "| ID | Формула | check |\n"
    "|---|---|---|\n"
    "| AC-I01 | authz-периметр | проверить роль |\n"
    "| AC-I02 | ai-trust: tool-call re-authz | проверить |\n"
)
# discriminating-power fix (Task 3fix, sec. 60.3): the FIRING fixture MUST carry the ACTUAL P-AI
# row from hypotheses_web_template.md, NOT a simplified one. The previous fixture (`| P-AI | ai-trust:
# injection -> priv tool-call | Agent | 3 | H-40 |`) did NOT contain a literal `N/A`, so FIRING was
# falsely green: on the REAL template row (where `N/A` lived in the partition NAME) the gate line
# `if "n/a" in m.group(0)...: return None` always lifted the partition -> the gate was dead on any production
# ledger (discriminating power 0). The reword removed `N/A`/`deferred` from the pipe row; the test now
# LOADS the real row from the template (self-synchronizing -- new template<->test drift is impossible).
def _load_real_pai_row():
    """Reads the ACTUAL P-AI pipe row from hypotheses_web_template.md (the same regex as the gate)."""
    _tk = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # bug-bounty-toolkit
    tpl = os.path.join(_tk, "sessions", "_methodology", "hypotheses_web_template.md")
    pat = re.compile(r"(?im)^\s*\|[^\n]*\bp-ai\b[^\n]*$")
    with open(tpl, encoding="utf-8") as f:
        for ln in f:
            if pat.match(ln.rstrip("\n")):
                return ln if ln.endswith("\n") else ln + "\n"
    raise SystemExit("FATAL: P-AI pipe row not found in hypotheses_web_template.md (reword drift)")


REAL_PAI_ROW = _load_real_pai_row()  # the real template row, the lead filled in (ai-trust probe), without n/a


def _pai_with_lead(lead):
    """The REAL P-AI row, but the LEAD CELL (col2) replaced with `lead` -- the partition name is preserved."""
    cells = REAL_PAI_ROW.rstrip("\n").split("|")  # ['', ' P-AI (...) ', ' <lead> ', ' ', ' ', ' ', '']
    cells[2] = " %s " % lead
    return "|".join(cells) + "\n"


def _scout(row):
    # Scout Fan-Out table header: "Partition | leads | Scout | #leads | merged" (Russian column names kept)
    return ("\n## Scout Fan-Out\n- **Status:** DONE\n"
            "| Партиция | лиды | Scout | #лидов | merged |\n|---|---|---|---|---|\n" + row)


# Scout DONE + an active P-AI partition (the REAL template row, a filled lead without n/a -> must FIRE).
SCOUT_DONE_AI = _scout(REAL_PAI_ROW)
# The REAL row, but `N/A — no AI surface` written into the LEAD CELL (a legitimate opt-out -> the gate is silent).
SCOUT_DONE_AI_REAL_OPTOUT = _scout(_pai_with_lead("N/A — no AI surface"))
# P-AI marked N/A in the lead (simplified form, kept for coverage -- also an opt-out -> silent).
SCOUT_DONE_NOAI = _scout("| P-AI | N/A — no AI surface | — | — | — |\n")
# Scout DONE, but there is no P-AI partition in the fan-out at all (anti-FP: non-canonical/older ledger).
SCOUT_DONE_NO_PARTITION = _scout("| P-SIGN | signature integrity | Agent | 2 | H-10 |\n")
SCOUT_PENDING_AI = SCOUT_DONE_AI.replace("DONE", "PENDING")
# The REAL row, but `deferred` written into the LEAD CELL (legitimately deferred -> the gate is silent).
SCOUT_DONE_AI_DEFERRED = _scout(_pai_with_lead("ai-trust — DEFERRED to wave-2"))

# ── FIRING (producer-absent form on the REAL row -- proving discriminating power, not a fake green) ──
run_ai("FIRING (TB): web model + Scout DONE + REAL P-AI row + ai_trust_matrix.md ABSENT -> FIRE",
       LEDGER_OK + SCOUT_DONE_AI, WEB_MODEL_TB, None, True)
run_ai("FIRING (AC/web2): AC model + Scout DONE + REAL P-AI row + producer ABSENT -> FIRE (both profiles)",
       LEDGER_OK + SCOUT_DONE_AI, WEB_MODEL_AC, None, True)

# ── NEGATIVE (producer present / opt-out in the lead / no AI feature -> silent) ──
run_ai("NEGATIVE: producer ai_trust_matrix.md RUN (non-empty) -> silent",
       LEDGER_OK + SCOUT_DONE_AI, WEB_MODEL_TB,
       "RESULT: ai-trust-run, 2 probes, 0 divergences (context/instruction boundary enforced)\n", False)
run_ai("NEGATIVE: REAL row + `N/A` in the LEAD CELL (legit opt-out) -> silent",
       LEDGER_OK + SCOUT_DONE_AI_REAL_OPTOUT, WEB_MODEL_TB, None, False)
run_ai("NEGATIVE: P-AI marked `N/A — no AI surface` (simplified form) -> silent",
       LEDGER_OK + SCOUT_DONE_NOAI, WEB_MODEL_TB, None, False)
run_ai("NEGATIVE: REAL row + `DEFERRED` in the wave-2 lead -> silent (legitimately deferred)",
       LEDGER_OK + SCOUT_DONE_AI_DEFERRED, WEB_MODEL_TB, None, False)
run_ai("NEGATIVE: no P-AI partition in the fan-out at all -> silent (anti-FP, non-canonical ledger)",
       LEDGER_OK + SCOUT_DONE_NO_PARTITION, WEB_MODEL_TB, None, False)
run_ai("NEGATIVE: Scout PENDING (not DONE) -> silent (active_ledger_scout_pending catches it earlier)",
       LEDGER_OK + SCOUT_PENDING_AI, WEB_MODEL_TB, None, False)

# ── deephunt-silent / off-switch (namespace guard: contract -> "" -> None) ──
run_ai("deephunt-silent: contract model (I-NN, namespace='') + active P-AI -> silent (namespace guard)",
       LEDGER_OK + SCOUT_DONE_AI, GOOD3, None, False)
run_ai("off-switch: no model at all (system_model.md absent) -> silent (namespace '')",
       LEDGER_OK + SCOUT_DONE_AI, None, None, False)
run_ai("off-switch: MODEL: N/A sentinel -> silent (ctx None)",
       LEDGER_NA + SCOUT_DONE_AI, WEB_MODEL_TB, None, False)

# Direct contract: the gate returns the toolkit-rooted relpath of the ledger (co-located triple-sync), not None.
_d = setup(LEDGER_OK + SCOUT_DONE_AI, WEB_MODEL_TB)
_reason_path = g.active_ai_trust_unresolved("sid")
shutil.rmtree(_d, ignore_errors=True)
_ok_path = bool(_reason_path) and _reason_path.endswith("hypotheses.md")
print("  [%s] FIRING returns the ledger relpath (not a bare None): got=%r"
      % ("PASS" if _ok_path else "FAIL", _reason_path))
results.append(_ok_path)
# The reason constant carries the toolkit-rooted path of the producer (co-located triple-sync -- not a bare sessions/$DOMAIN).
_ok_reason = ("sessions/$DOMAIN/ai_trust_matrix.md" in g.AI_TRUST_REASON)
print("  [%s] AI_TRUST_REASON carries the toolkit-rooted `sessions/$DOMAIN/ai_trust_matrix.md`: got=%s"
      % ("PASS" if _ok_reason else "FAIL", _ok_reason))
results.append(_ok_reason)

print("── K. active_pattern_replay_skipped (Task 5, plan 7 sec. 61 / 48.1) — SENTINEL class (ledger line)")
# SENTINEL canon (the REVERSE of producer-absent Task 3 `active_ai_trust_unresolved`): off-switch =
# `_model_ctx` + `_i_matured_count(mt)>=3`. Detect the ledger line `PRIOR-PATTERNS:` (not file presence).
# We pull the real template line FROM hypotheses_template.md (template<->test self-sync, not a hardcoded form).
_PP_TPL_LINE = next(l for l in _CONTRACT_TPL_RAW.splitlines()
                    if l.strip().startswith("- **PRIOR-PATTERNS"))
_LEDGER_PP_TODO = LEDGER_OK + _PP_TPL_LINE + "\n"
_LEDGER_PP_EMPTY = LEDGER_OK + "- **PRIOR-PATTERNS (§48.1 — recon-producer):**\n"
_LEDGER_PP_FILLED = LEDGER_OK + "- **PRIOR-PATTERNS (§48.1 — recon-producer):** 3 matched — PAT-01@a.tsx:2\n"
_LEDGER_PP_ZERO = LEDGER_OK + "- **PRIOR-PATTERNS (§48.1 — recon-producer):** 0 matched\n"

# FIRING -- a mature model (3 statused I-NN) + the sentinel not lifted -> holds the exit
run("FIRING: mature model + PRIOR-PATTERNS: {TODO} (REAL template line) -> FIRE (holds the exit)",
    _LEDGER_PP_TODO, GOOD3, g.active_pattern_replay_skipped, True)
run("FIRING: mature model + PRIOR-PATTERNS: empty (value cleared) -> FIRE",
    _LEDGER_PP_EMPTY, GOOD3, g.active_pattern_replay_skipped, True)
# NEGATIVE -- the producer was run (a real value)
run("NEGATIVE: PRIOR-PATTERNS: 3 matched (producer run) -> silent",
    _LEDGER_PP_FILLED, GOOD3, g.active_pattern_replay_skipped, False)
run("NEGATIVE: PRIOR-PATTERNS: 0 matched (producer run, nothing to match) -> silent",
    _LEDGER_PP_ZERO, GOOD3, g.active_pattern_replay_skipped, False)
# off-switch (the same signal as active_undup_sweep_incomplete/active_composition_pass_skipped)
run("off-switch: first scout pass (2 statused < 3) + {TODO} -> silent",
    _LEDGER_PP_TODO, model([row(1), row(2)]), g.active_pattern_replay_skipped, False)
run("off-switch: MODEL: N/A sentinel + {TODO} -> silent (ctx None)",
    LEDGER_NA + _PP_TPL_LINE + "\n", GOOD3, g.active_pattern_replay_skipped, False)
run("off-switch: no model at all (system_model.md absent) + {TODO} -> silent",
    _LEDGER_PP_TODO, None, g.active_pattern_replay_skipped, False)
# anti-FP: no PRIOR-PATTERNS line at all (a pre-Task-5 ledger) -> silent even on a mature model
run("anti-FP: no PRIOR-PATTERNS line at all (pre-Task-5 ledger) + mature model -> silent",
    LEDGER_OK, GOOD3, g.active_pattern_replay_skipped, False)

# direct contract of the parser _prior_patterns_unfilled (template line {TODO} / filled / absent)
_u1 = g._prior_patterns_unfilled(_PP_TPL_LINE)
print("  [%s] _prior_patterns_unfilled(REAL {TODO} line) == True: got=%r"
      % ("PASS" if _u1 is True else "FAIL", _u1))
results.append(_u1 is True)
_u2 = g._prior_patterns_unfilled(_LEDGER_PP_FILLED)
print("  [%s] _prior_patterns_unfilled('... 3 matched') == False: got=%r"
      % ("PASS" if _u2 is False else "FAIL", _u2))
results.append(_u2 is False)
_u3 = g._prior_patterns_unfilled(LEDGER_OK)
print("  [%s] _prior_patterns_unfilled(no line at all) == False: got=%r"
      % ("PASS" if _u3 is False else "FAIL", _u3))
results.append(_u3 is False)

# ── parallel-during-fanout (lombard-audit 2026-08-13 + enzymefinance 2026-08-19): _can_drive_parallel
# forces serial-depth IN PARALLEL with the fan-out ONLY with a designated Depth-Lead. True -> the release site forces drive;
# False -> release (the hunter will write off the ledger debt OR wait for the fan-out -- idle is legitimate, NOT shallow busywork).
print("── PD. _can_drive_parallel (parallel-during-fanout, designated-Depth-Lead-only)")
# fixture text kept Russian: "layer 3/5"
_DL_ACTIVE = LEDGER_OK + "\n- **Depth-Lead:** H-03 MerkleValidator.sol:374 — слой 3/5\n"
# PD1 (enzyme 2026-08-19): an open Active H-NN WITHOUT a designated Depth-Lead -> False. Previously =True -> a hunter
# without a chosen thread invented shallow busywork over the fan-out invariants (a premature "sound").
run("PD1: Active H-NN WITHOUT Depth-Lead -> False (do not over-force; wait/record-debt, not busywork) [enzyme]",
    LIVE_H, None, g._can_drive_parallel, False)
run("PD2: active designated Depth-Lead -> True (drive THIS thread deep in parallel with the fan-out)",
    _DL_ACTIVE, None, g._can_drive_parallel, True)
run("PD3: no thread (empty Active, Depth-Lead none) -> False (wait for the fan-out)",
    LEDGER_OK + "\n- **Depth-Lead:** none yet\n## Active Hypotheses\n\n", None, g._can_drive_parallel, False)
run("PD4: HUNT-EXIT -> False (hunt finished, do not drive)",
    LIVE_H + "\nHUNT-EXIT: T4-CONFIRMED High\n", None, g._can_drive_parallel, False)
# PD5 (enzyme): open H-NN + designated Depth-Lead -> True (the thread is CHOSEN -> drive, the H-NN bunch does not interfere).
run("PD5: Active H-NN + designated Depth-Lead -> True (thread chosen)",
    LIVE_H + "\n- **Depth-Lead:** H-05 Vault.sol:88 — слой 4/5\n", None, g._can_drive_parallel, True)  # "layer 4/5"

print("── BOLD I-NN/D-NN (justlenddao 2026-08-18): the `| **I-01** |` bold wrapper is recognized")
# justlenddao's model bolded the id `| **I-01** |` -> _I_ROW_RE/_D_ROW_RE went blind -> _i_matured_count=0 with 12
# I-NN -> the WHOLE maturity cluster (model/exposure/undup/hybrid) was switched off. The regex now allows `\**`.
# (Cell text "description of the invariant", "what to check" is Russian fixture text, KEPT.)
_bold = ("_bold_I_ROW", bool(g._I_ROW_RE.match("| **I-01** | invariant description | check | comp | ENFORCED | state |")))
print("  [%s] _I_ROW_RE matches bold `| **I-01** |`: got=%s" % ("PASS" if _bold[1] else "FAIL", _bold[1]))
results.append(_bold[1])
_bold_d = bool(g._D_ROW_RE.match("| **D-01** | I-01 | a.sol:10 | ABSENT |"))
print("  [%s] _D_ROW_RE matches bold `| **D-01** |`: got=%s" % ("PASS" if _bold_d else "FAIL", _bold_d))
results.append(_bold_d)
_plain_ok = bool(g._I_ROW_RE.match("| I-01 | x |")) and not bool(g._I_ROW_RE.match("| D-01 | x |"))
print("  [%s] regression: plain `| I-01 |` matches, `| D-01 |` does NOT as I-NN: got=%s" % ("PASS" if _plain_ok else "FAIL", _plain_ok))
results.append(_plain_ok)
# maturity: a bold model of 3 mature rows -> _i_matured_count >= 3 (would have been 0 before the fix)
_bold_model = ("## Invariants\n"
               "| **I-01** | invariant one | what to check | comp | ENFORCED | state |\n"
               "| **I-02** | invariant two | what to check | comp | ABSENT | state |\n"
               "| **I-03** | invariant three | what to check | comp | ENFORCED | state |\n")
_mc = g._i_matured_count(_bold_model)
print("  [%s] _i_matured_count(bold model, 3 rows) >= 3 (was 0 -- blindness): got=%d" % ("PASS" if _mc >= 3 else "FAIL", _mc))
results.append(_mc >= 3)

ok = sum(results)
print("\n%d/%d model-gate cases green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
