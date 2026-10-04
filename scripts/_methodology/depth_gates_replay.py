#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for the 2 DEPTH-QUALITY gates (a hunt where 2 Crit candidates both ended up DUPLICATE):
(B) active_ledger_composite_abandoned — a Crit-capable composite was deferred without a resolution;
(A) active_ledger_depthmap_placeholder — depth-lead claims >=5, but the map = `{placeholder}`.
Monkeypatches freshest_active_ledger. Fire + anti-FP cases. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/depth_gates_replay.py

NOTE: Cyrillic strings inside ledger/model FIXTURES below are kept as-is — they are inputs to the hook's
Russian-aware regexes / template sentinels (logic). Comments and display names are English.
"""
import sys
import importlib.util, os, tempfile
import os as _os  # P4: path from __file__, not from CWD
_HOOK = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

def mk(txt):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(txt); f.close(); return f.name

_cur = {"p": None}
g.freshest_active_ledger = lambda sid: (_cur["p"], os.getcwd()) if _cur["p"] else (None, None)

def run(name, txt, fn, expect):
    _cur["p"] = mk(txt)
    got = bool(fn("sid"))
    ok = "PASS" if got == expect else "FAIL"
    print(f"  [{ok}] {name}: fired={got} expect={expect}")
    return ok == "PASS"

# A real-world fragment (positive): AMPLIFICATION THREAD, Crit, deferral, no resolution.
BERA_AMP = (
    "### H-11 [ACTIVE]: churn-limit\n"
    "- **AMPLIFICATION THREAD (chase → could reach SC-Critical):** beacon-INDUCED forced exit sweeps "
    "whole CL balance to WithdrawalVault WITHOUT matching withdrawal-NFT / totalDeposits decrement → "
    "possible orphaned-TVL / insolvency. Reading StakingPool/WithdrawalVault now.\n"
    "- **Composite:** BB-35/BB-37 + Y4 cap-churn edges (pending).\n"
)
# The same composite, but RESOLVED (driven/confirmed) — a resolution in the window -> does NOT trigger.
BERA_AMP_RESOLVED = (
    "### H-11 [ACTIVE]: churn-limit\n"
    "- **AMPLIFICATION THREAD:** beacon exit → WithdrawalVault → insolvency (Critical). DRIVEN to D-PoC, "
    "fork-PoC confirms, T4 verdict: confirm. `pool.sol:210`.\n"
)
# A killed-with-falsifier composite — a resolution -> silent.
BERA_AMP_KILLED = (
    "### H-11 [KILLED]: churn-limit\n"
    "- **cross-thread seed:** forced-exit × pool-accounting could reach Critical insolvency — but "
    "KILLED by falsifier: WithdrawalVault.sol:88 decrements totalDeposits on sweep. pending? no.\n"
)

DMAP_L = "## Loop State\n- **Iteration #:** 5\n- **Depth-Lead:** %s\n%s"
DMAP_FIELD_PLACEHOLDER = "- **DEPTH-MAP (заполнять когда ≥5):** {L1 … → L5}\n"  # label kept: "(fill in when >=5)" — mirrors real template
DMAP_FIELD_FILLED = "- **DEPTH-MAP:** L1 a.sol:1 (core) → L2 b.sol:2 (vault) → L3 c.go:3 (beacon) → L4 d.sol:4 → L5 e.sol:5\n"
DMAP_FIELD_NA = "- **DEPTH-MAP:** N/A — single-subsystem (halo2 gadget)\n"

results = []

# ── (B) composite_abandoned ──
# 1. AMPLIFICATION THREAD, Crit + deferral, no resolution -> FIRE.
results.append(run("B: amp abandoned → fire", BERA_AMP, g.active_ledger_composite_abandoned, True))
# 2. The same composite, DRIVEN/confirmed/T4 -> silent (a resolution in the window).
results.append(run("B: amp resolved (DRIVEN/T4) → silent", BERA_AMP_RESOLVED, g.active_ledger_composite_abandoned, False))
# 3. cross-thread seed KILLED with a falsifier -> silent.
results.append(run("B: amp killed+falsifier → silent", BERA_AMP_KILLED, g.active_ledger_composite_abandoned, False))
# 4. No composite marker at all -> silent (anti-FP on an ordinary ledger).
#    (fixture kept in Russian: "ordinary hypothesis" / "driving H-01 deeper")
results.append(run("B: no composite marker → silent", "### H-01: обычная гипотеза\n- State: A\n- gоню H-01 вглубь\n", g.active_ledger_composite_abandoned, False))
# 5. Marker present, but NOT crit-capable (Med griefing) -> silent (anti-FP: only Crit/High).
results.append(run("B: amp but Med-only → silent", "- **AMPLIFICATION THREAD:** griefing onboarding, Medium, victim no fund loss, pending review.\n", g.active_ledger_composite_abandoned, False))
# 6. Template Composite watch placeholder (fresh ledger, resolution words inside the field) -> silent (anti-self-fire).
#    (placeholder kept in Russian: mirrors the real template text)
results.append(run("B: template placeholder → silent",
    "- **Composite watch (T6):** {крит-composite помечай `AMPLIF-THREAD` + severity, НЕ бросай 'unproven/NEXT' — "
    "резолви: DRIVE→D-PoC ЛИБО KILL с falsifier. none пока нет.}\n", g.active_ledger_composite_abandoned, False))

# ── (A) depthmap_placeholder ──
# 7. Depth-Lead 5/5, DEPTH-MAP placeholder -> FIRE.
results.append(run("A: claim 5/5 + map placeholder → fire", DMAP_L % ("H-12 — 5/5 (ssz)", DMAP_FIELD_PLACEHOLDER), g.active_ledger_depthmap_placeholder, True))
# 8. Depth-Lead 5/5, DEPTH-MAP filled -> silent.
results.append(run("A: claim 5/5 + map filled → silent", DMAP_L % ("H-12 — 5/5 (ssz)", DMAP_FIELD_FILLED), g.active_ledger_depthmap_placeholder, False))
# 9. Depth-Lead 5/5, DEPTH-MAP N/A single-subsystem -> silent.
results.append(run("A: claim 5/5 + map N/A → silent", DMAP_L % ("H-12 — 5/5", DMAP_FIELD_NA), g.active_ledger_depthmap_placeholder, False))
# 10. Depth-Lead 3/5 (claim <5), placeholder -> silent (wide_but_shallow handles it, not us).
results.append(run("A: claim 3/5 + placeholder → silent", DMAP_L % ("H-03 — 3/5", DMAP_FIELD_PLACEHOLDER), g.active_ledger_depthmap_placeholder, False))
# 11. Depth-Lead 5/5, NO DEPTH-MAP field (legacy ledger) -> silent (not our check).
results.append(run("A: claim 5/5 + no field (legacy) → silent", DMAP_L % ("H-12 — 5/5", ""), g.active_ledger_depthmap_placeholder, False))

# ── (A+) cross-subsystem soft check: the map is filled, but <3 subsystems -> single-subsystem ──
DMAP_FIELD_SINGLE = "- **DEPTH-MAP:** L1 pool.sol:10 → L2 pool.sol:40 → L3 pool.sol:88 → L4 pool.sol:120 → L5 pool.sol:200\n"
DMAP_FIELD_TAGS3 = "- **DEPTH-MAP:** L1 a (core) → L2 b (vault) → L3 c (beacon) → L4 d (accounting)\n"
# 12. Filled with 1 file (pool.sol x5) -> FIRE (single-subsystem).
results.append(run("A+: filled 1-file (pool.sol) → fire", DMAP_L % ("H-12 — 5/5", DMAP_FIELD_SINGLE), g.active_ledger_depthmap_single_subsystem, True))
# 13. Filled with 5 different files -> silent (cross-subsystem).
results.append(run("A+: filled 5 files → silent", DMAP_L % ("H-12 — 5/5", DMAP_FIELD_FILLED), g.active_ledger_depthmap_single_subsystem, False))
# 14. Explicit N/A — single-subsystem -> silent (a legit escape for a known class of targets).
results.append(run("A+: N/A single-subsystem → silent", DMAP_L % ("H-12 — 5/5", DMAP_FIELD_NA), g.active_ledger_depthmap_single_subsystem, False))
# 15. 4 subsystem tags (no files) -> silent (>=3 subsystems).
results.append(run("A+: 4 subsystem tags → silent", DMAP_L % ("H-12 — 5/5", DMAP_FIELD_TAGS3), g.active_ledger_depthmap_single_subsystem, False))
# 16. Placeholder -> silent (that is caught by depthmap_placeholder, not single-subsystem).
results.append(run("A+: placeholder → silent (other gate)", DMAP_L % ("H-12 — 5/5", DMAP_FIELD_PLACEHOLDER), g.active_ledger_depthmap_single_subsystem, False))
# 17. claim 3/5 (<5) -> silent.
results.append(run("A+: claim 3/5 → silent", DMAP_L % ("H-03 — 3/5", DMAP_FIELD_SINGLE), g.active_ledger_depthmap_single_subsystem, False))
# OBS-6: a KILLED depth-lead = a killed thread (an archived cross-repo trace), NOT an active 5/5 claim -> silent
# natively, without a manual `N/A` workaround (a cross-repo D-09 was honestly killed by a falsifier).
# (fixture kept in Russian: "thread closed by a falsifier")
results.append(run("A+: KILLED depth-lead 5/5 + single-file map → silent (native killed)",
                   DMAP_L % ("D-09 KILLED (нить закрыта фальсификатором) — 5/5, trace archived", DMAP_FIELD_SINGLE),
                   g.active_ledger_depthmap_single_subsystem, False))
# regression guard: an ACTIVE (not killed) 5/5 + single-file still FIREs (the word killed must not mute a live claim).
results.append(run("A+: active 5/5 (not killed) + single-file → fire (OBS-6 regression)",
                   DMAP_L % ("H-12 — 5/5 active", DMAP_FIELD_SINGLE),
                   g.active_ledger_depthmap_single_subsystem, True))


# ─────────────────────────────────────────────────────────────────────────────
# T12 — Predictive Boundary Crossing (phase 2 of depth_engine_plan).
# A layer counts only if a boundary is crossed AND the prediction is written BEFORE, checked AFTER.
# One gate with a LIST of reasons (the same consolidation as the model gates) + K1: depth_spin must
# count a new predicted/observed pair as progress, otherwise our two enforcements pull in different
# directions (T12 tells you to linger on a layer — depth_spin treats lingering as elaboration).
print("\n── T12: active_depth_t12_incomplete")

# NOTE: the Cyrillic trace fixtures below are kept as-is (inputs to the hook's parser; .replace() targets must match).
TRACE_FULL = (
    "- **DEPTH-TRACE (T12):**\n"
    "  L3  boundary:  статика → рантайм (fork-прогон)\n"
    "      predicted: redeem() вернёт 99 ETH\n"
    "      observed:  revert ERC721IncorrectOwner ← forge-лог :214\n"
    "      fan-in:    fees ← redeem() :179 · withdrawFees() :261 (2 писателя)\n"
)
TRACE_NO_PRED = TRACE_FULL.replace("      predicted: redeem() вернёт 99 ETH\n", "")
TRACE_NO_FANIN = TRACE_FULL.replace(
    "      fan-in:    fees ← redeem() :179 · withdrawFees() :261 (2 писателя)\n", "")
TRACE_NO_BOUND = TRACE_FULL.replace("  L3  boundary:  статика → рантайм (fork-прогон)\n", "  L3\n")
TRACE_PLACEHOLDER = "- **DEPTH-TRACE (T12):** {Слой засчитывается, только если ...}\n"
TRACE_NA = "- **DEPTH-TRACE (T12):** N/A — заявка <3 слоёв\n"

def L(lead, trace):
    return "## Loop State\n- **Depth-Lead:** %s\n%s" % (lead, trace)

results.append(run("T12: claim 4/5 + full trace → silent",
                   L("H-03 — 4/5 (pool→vault)", TRACE_FULL), g.active_depth_t12_incomplete, False))
results.append(run("T12: claim 4/5 + trace placeholder → fire",
                   L("H-03 — 4/5", TRACE_PLACEHOLDER), g.active_depth_t12_incomplete, True))
results.append(run("T12: claim 4/5 + no trace at all → fire",
                   L("H-03 — 4/5", ""), g.active_depth_t12_incomplete, True))
results.append(run("T12: claim 2/5 (<3) + no trace → silent (artifact not required)",
                   L("H-03 — 2/5", ""), g.active_depth_t12_incomplete, False))
results.append(run("T12: claim 4/5 + N/A sentinel → fire (claim >=3, N/A not justified)",
                   L("H-03 — 4/5", TRACE_NA), g.active_depth_t12_incomplete, True))
results.append(run("T12: claim 2/5 + N/A sentinel → silent",
                   L("H-03 — 2/5", TRACE_NA), g.active_depth_t12_incomplete, False))
results.append(run("T12: observed present, predicted ABSENT → fire (after the fact)",
                   L("H-03 — 4/5", TRACE_NO_PRED), g.active_depth_t12_incomplete, True))
results.append(run("T12: no fan-in → fire (depth without fan-in = a tube, not a slice)",
                   L("H-03 — 4/5", TRACE_NO_FANIN), g.active_depth_t12_incomplete, True))
results.append(run("T12: no boundary type → fire",
                   L("H-03 — 4/5", TRACE_NO_BOUND), g.active_depth_t12_incomplete, True))

print("-- T12: a prediction miss = a generator (do not swallow silently)")
PM = """## Loop State
- **Depth-Lead:** H-03 — 2/5
- **Prediction-miss (T12):** %s
"""
MODEL_WITH_DIV = """## Divergences
| ID | I-NN | Где | Ст | v | p | t | c | heat | R | Рез |
|---|---|---|---|---|---|---|---|---|---|---|
| D-01 | I-01 | a.sol:10 | ABSENT | h | 3 | y | 2 | cold | 9 | -> H-05 |
"""

def run_pm(name, ledger_txt, model_txt, expect):
    d = tempfile.mkdtemp()
    lp = os.path.join(d, "hypotheses.md")
    open(lp, "w", encoding="utf-8").write(ledger_txt)
    if model_txt:
        open(os.path.join(d, "system_model.md"), "w", encoding="utf-8").write(model_txt)
    _cur["p"] = lp
    got = bool(g.active_depth_t12_incomplete("sid"))
    ok = got == expect
    print("  [%s] %s: fired=%s expect=%s" % ("PASS" if ok else "FAIL", name, got, expect))
    results.append(ok)

# (Russian field values kept: "2 промаха" = "2 misses"; "{счётчик промахов ...}" = "{miss counter ...}";
#  "не понял систему, копаю этот же слой" = "misunderstood the system, digging the same layer")
run_pm("misses present, no D-NN, no note -> fire", PM % "2 промаха", None, True)
run_pm("misses present, D-NN created -> silent", PM % "2 промаха", MODEL_WITH_DIV, False)
run_pm("0 misses -> silent", PM % "0", None, False)
run_pm("field untouched (placeholder) -> silent", PM % "{счётчик промахов ...}", None, False)
run_pm("miss + «misunderstood -> digging the same layer» -> silent",
       PM % "1 -- не понял систему, копаю этот же слой", None, False)

print("── K1: depth_spin counts a new predicted/observed pair as progress")
import os as _os
def spin_streak(txt_seq):
    """Run depth_spin over a sequence of ledger states; return the final streak."""
    d = tempfile.mkdtemp()
    p = _os.path.join(d, "hypotheses.md")
    _cur["p"] = p
    fired = False
    for i, t in enumerate(txt_seq):
        with open(p, "w", encoding="utf-8") as f:
            f.write(t)
        _os.utime(p, (1000 + i * 10, 1000 + i * 10))   # advance mtime = the ledger was written
        fired = g.depth_spin("sid")
    return fired

BASE = L("H-03 — 3/5", TRACE_FULL) + "\n"
# 5 turns in a row: the ledger is written, depth stands still, NO new predicted/observed -> spin catches it.
# (fixture line kept in Russian: "progress: rewrote the conclusion %d")
seq_stale = [BASE + ("- прогресс: переписал вывод %d\n" % i) for i in range(6)]
ok = spin_streak(seq_stale)
print("  [%s] K1: elaboration without new predicted/observed → fire: fired=%s expect=True"
      % ("PASS" if ok else "FAIL", ok))
results.append(ok)
# The same turns, but each one adds a NEW predicted/observed pair (T12: "misunderstood -> digging the same
# layer") — the depth by the counter does NOT grow, and depth-spin must NOT punish.
# (fixture values kept in Russian: "hypothesis %d" / "fact %d")
seq_t12 = [BASE + "".join(
    "  L%d predicted: гипотеза %d\n      observed: факт %d\n" % (3, j, j) for j in range(i + 1))
    for i in range(6)]
ok2 = not spin_streak(seq_t12)
print("  [%s] K1: new predicted/observed pairs → silent (correct T12 outcome): fired=%s expect=False"
      % ("PASS" if ok2 else "FAIL", not ok2))
results.append(ok2)

print("── FIX-2 (judge 7/10 «the main failure of the enabler»): wide_but_shallow catches breadth-in-D-NN")
WS_DEPTH_PH = "## Loop State\n- **Iteration #:** 5\n- **Depth-Lead:** {none yet — placeholder}\n"
WS_DEPTH_5 = "## Loop State\n- **Iteration #:** 5\n- **Depth-Lead:** H-01 — 5/5 (call->state->external->hook->accounting)\n"
WS_H1 = "### H-01: lead one\n- State: A\n"
WS_H4 = "".join("### H-0%d: lead %d\n- State: A\n" % (i, i) for i in range(1, 5))
_WS_HDR = "## Divergences\n| ID | I-NN | Где | Ст | v | p | t | c | heat | R | uo | Рез |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n"
WS_DIV_OPEN4 = _WS_HDR + "".join(
    "| D-0%d | I-0%d | a.sol:%d | ABSENT | h | 3 | y | 2 | cold | 9 | negative-space | -> H-0%d |\n" % (i, i, i, i)
    for i in range(1, 5))
# (resolution cells kept in Russian: "банк Medium" = "bank Medium", "банк Low" = "bank Low")
WS_DIV_RESOLVED4 = _WS_HDR + (
    "| D-01 | I-01 | a.sol:1 | ABSENT | h | 3 | y | 2 | cold | 9 | ns | -> банк Medium |\n"
    "| D-02 | I-02 | a.sol:2 | ABSENT | h | 3 | y | 2 | cold | 9 | ns | KILLED a.sol:9 |\n"
    "| D-03 | I-03 | a.sol:3 | ABSENT | h | 3 | y | 2 | cold | 9 | ns | -> банк Low |\n"
    "| D-04 | I-04 | a.sol:4 | ABSENT | h | 3 | y | 2 | cold | 9 | ns | de-minimis dust |\n")


def run_ws(name, ledger_txt, model_txt, expect):
    d = tempfile.mkdtemp()
    lp = os.path.join(d, "hypotheses.md")
    open(lp, "w", encoding="utf-8").write(ledger_txt)
    if model_txt:
        open(os.path.join(d, "system_model.md"), "w", encoding="utf-8").write(model_txt)
    _cur["p"] = lp
    got = bool(g.active_ledger_wide_but_shallow("sid"))
    ok = got == expect
    print("  [%s] %s: fired=%s expect=%s" % ("PASS" if ok else "FAIL", name, got, expect))
    results.append(ok)

# FIX2-a (MAIN — a blind spot): 1 H + 4 OPEN D-NN + depth placeholder -> h(1)+d_open(4)=5>=4, depth<5 -> FIRE (was silent — H-counter=1<4).
run_ws("1 H + 4 open D-NN + no depth → FIRE [FIX-2 breadth-in-D-NN]", WS_DEPTH_PH + WS_H1, WS_DIV_OPEN4, True)
# FIX2-b (anti-over-fire): 1 H + 4 RESOLVED D-NN (bank/killed/de-minimis) -> d_open=0, h=1<4 -> silent (exhausted -> a NEW axis is needed, not depth).
run_ws("1 H + 4 resolved D-NN (bank/killed) → silent [FIX-2 does not over-fire on exhausted]", WS_DEPTH_PH + WS_H1, WS_DIV_RESOLVED4, False)
# FIX2-c (regression H-only): 4 H + no system_model.md + no depth -> h=4>=4 -> FIRE (the old H behaviour is intact).
run_ws("4 H + no system_model + no depth → FIRE [regression H-only]", WS_DEPTH_PH + WS_H4, None, True)
# FIX2-d (anti-FP depth-5): 1 H + 4 open D-NN, but Depth-Lead 5/5 -> thread >=5 -> silent.
run_ws("1 H + 4 open D-NN + Depth-Lead 5/5 → silent [thread >=5]", WS_DEPTH_5 + WS_H1, WS_DIV_OPEN4, False)

ok = sum(results)
print(f"\n{ok}/{len(results)} depth+T12 cases green")
sys.exit(0 if ok == len(results) else 1)
