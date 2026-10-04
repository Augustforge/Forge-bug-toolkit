#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-SHADOW golden reference (Worklist Driver Stage 2 BLOCKER, plan section 8 G-shadow).

The current `main()` completeness-gate = a priority if-cascade of ~43 ledger-state detectors: the first
truthy `_block(...)` does `sys.exit(0)` → WINS (the rest are shadowed — shadowing). The cascade is
hardened by 15 incidents; the ORDER = a finely tuned contract (the specific overrides the general). Stage 2
will replace the cascade with atom-producers with `MAX(rank)` selection — a DIFFERENT priority model. This test FIXES
the winner of the current cascade on shadowing scenarios (several detectors active at once) → golden
reference: after the refactor `assert winning atom == the old cascade` (otherwise behavior was silently changed).

Role BEFORE the refactor: `cascade_winner(sid)` reproduces the first-wins semantics of main() for ledger-state
detectors; the test captures the current winner. Role AFTER the refactor: the same file checks the next_atom driver.

Run: py -3 -X utf8 scripts/_methodology/shadowing_regression.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

_HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

_cur = {"dir": None}
g.freshest_active_ledger = lambda sid: (
    (os.path.join(_cur["dir"], "hypotheses.md"), _cur["dir"]) if _cur["dir"] else (None, None)
)

# ── CASCADE: the EXACT order of ledger-state detectors from main() (grep _block, 2026-08-11) ───────
# (name, callable, is_giveup) in main() ORDER. First truthy = winner. Message-based detectors
# (ABORT/paraphrase/LEDGER_LIVE/CHAT_WALL — read last_assistant/last_user, not ledger-state) are NOT included:
# they remain a blocklist safety net (plan section 1 "Fate of the 44 gates"), they do NOT become atom-producers.
# manual/INFO gating is reflected in the `gated` field (checked separately, matrix — Stage 2 G-matrix acceptance).
CASCADE = [
    ("missing_impacts",            g.active_ledger_missing_impacts,        False, ""),
    ("missing_oos",                g.active_ledger_missing_oos,            False, ""),   # OOS intake (2026-08-11)
    ("missing_loopstate",          g.active_ledger_missing_loopstate,      False, ""),
    ("model_before_scout",         g.active_model_before_scout,            False, "manual"),
    ("scout_pending",              g.active_ledger_scout_pending,          False, ""),
    ("boundary_scout_skipped",     g.active_ledger_boundary_scout_skipped, False, ""),
    ("optmenu_todo",               g.active_ledger_optmenu_todo,           False, ""),
    ("wave_pending",               g.active_ledger_wave_pending,           False, ""),
    ("clone_diff_skipped",         g.active_clone_diff_skipped,            False, ""),
    ("authz_matrix_skipped",       g.active_authz_matrix_skipped,          False, ""),
    ("operation_coverage",         g.active_operation_coverage_incomplete, False, ""),
    ("ai_trust_unresolved",        g.active_ai_trust_unresolved,           False, ""),
    ("t4_claimed_unlogged",        g.ledger_t4_claimed_but_unlogged,       False, ""),
    # NB: active_t4_decomposition_incomplete (S3) lives in the SUCCESS-EXIT path, not in the main cascade —
    # it is not in CASCADE (like active_library_not_banked / submit-OOS). Checked by t4_decomposition_replay.
    ("composite_abandoned",        g.active_ledger_composite_abandoned,    False, "manual+info"),
    ("intent_steelman_missing",    g.active_ledger_intent_steelman_missing, False, "manual+info"),
    ("depthmap_placeholder",       g.active_ledger_depthmap_placeholder,   False, "manual+info"),
    ("depthmap_single_subsystem",  g.active_ledger_depthmap_single_subsystem, False, "manual+info"),
    ("depth_t12_incomplete",       g.active_depth_t12_incomplete,          False, "manual+info"),
    ("fork_diff_unrun",            g.active_fork_diff_unrun,               False, "manual+info"),
    ("defi_value_unmapped",        g.active_defi_value_unmapped,           False, "manual+info"),
    ("moneylead_shallow",          g.active_moneylead_shallow,             False, "manual+info"),
    ("wide_but_shallow",           g.active_ledger_wide_but_shallow,       False, "manual+info"),
    ("chain_dependency_unproven",  g.active_chain_dependency_unproven,     False, "manual+info"),
    ("model_incomplete",           g.active_model_incomplete,              False, "manual"),
    ("model_order_violation",      g.active_model_order_violation,         False, "manual"),
    ("divergence_unresolved",      g.active_divergence_unresolved,         False, "manual"),
    ("wave_transition_needed",     g.active_wave_transition_needed,        True,  "manual"),
    ("model_axes_incomplete",      g.active_model_axes_incomplete,         True,  "manual"),
    ("axes_without_waves",         g.active_axes_without_waves,            True,  "manual"),
    ("t11_undecided",              g.active_t11_undecided,                 False, "manual"),
    ("attention_gap_skipped",      g.active_attention_gap_skipped,         False, "manual"),
    ("undup_sweep_incomplete",     g.active_undup_sweep_incomplete,        False, "manual"),
    ("composition_pass_skipped",   g.active_composition_pass_skipped,      False, "manual"),
    ("undup_origin_missing",       g.active_undup_origin_missing,          False, "manual"),
    ("pattern_replay_skipped",     g.active_pattern_replay_skipped,        False, "manual"),
    ("exposure_scan_skipped",      g.active_exposure_scan_skipped,         False, "manual"),
    ("core_enforced_needs_t9",     g.active_core_enforced_needs_t9,        True,  "manual"),
    ("wave_codefirst_nudge",       g.active_wave_codefirst_nudge,          False, "manual"),
    ("axis_queue_empty",           g.active_axis_queue_empty,              False, "manual"),
    ("banked_composite_unchecked", g.active_banked_composite_unchecked,    False, "manual"),
    ("banked_without_oos_check",   g.active_banked_without_oos_check,      False, "manual"),   # OOS banked (2026-08-11)
    ("banked_without_t4",          g.active_banked_without_t4,             False, "manual"),   # T4 banked (S3 D4)
    ("registry_unpopulated",       g.active_registry_unpopulated,          False, "manual"),   # Worklist S1
    ("pick_not_from_queue",        g.active_pick_not_from_queue,           False, "manual"),   # Worklist S1
    ("atom_closed_no_narrative",   g.active_atom_closed_without_narrative, False, "manual"),   # Worklist S1
    ("atom_src_ungrounded",        g.active_atom_src_ungrounded,           False, "manual"),   # Worklist S2 (judge-B D2)
]

_NAME_IDX = {n: i for i, (n, _f, _g, _gt) in enumerate(CASCADE)}


def cascade_winner(sid):
    """The first truthy detector in CASCADE order = the winner (reproduces the first-wins main()).
    Returns name or None (none fired → default LOOP_CONTINUE)."""
    for name, fn, _isg, _gated in CASCADE:
        try:
            if fn(sid):
                return name
        except Exception:
            pass
    return None


def which_fire(sid):
    """All detectors that fired (for shadowing diagnostics) — in cascade order."""
    out = []
    for name, fn, _isg, _gated in CASCADE:
        try:
            if fn(sid):
                out.append(name)
        except Exception:
            pass
    return out


results = []


def scenario(name, ledger_text, expect_winner, model_text=None, min_fire=1):
    """Writes a ledger (+ optional system_model.md) to temp, checks: winner == expect_winner AND at least
    min_fire detectors really fired (proves SHADOWING, not a single trigger)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_text)
    if model_text is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_text)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        fired = which_fire("sid")
        winner = fired[0] if fired else None
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    ok = (winner == expect_winner) and (len(fired) >= min_fire)
    print("  [%s] %s: winner=%s expect=%s | fired=%s"
          % ("PASS" if ok else "FAIL", name, winner, expect_winner, fired))
    results.append(ok)


# ── Sanity: cascade order without holes/duplicates ────────────────────────────
_names = [n for n, _f, _g, _gt in CASCADE]
print("── CASCADE contract: %d ledger-state detectors, main() order fixed" % len(CASCADE))
assert len(_names) == len(set(_names)), "duplicates in CASCADE"
print("  [PASS] %d detectors, no duplicates; order = golden reference for Stage 2" % len(CASCADE))
results.append(len(_names) == len(set(_names)))

# ── SHADOWING scenarios: ≥2 detectors REALLY active → fix the OBSERVED winner ───────────────
# expect_winner = the FACT of the current cascade (golden reference, not a hypothesis). After the Stage-2 refactor the same
# file must yield the same winners — otherwise `MAX(rank)` silently changed the priority of the hardened cascade.
print("\n── SHADOWING: the winner under multiple firing (golden reference)")

# S1: a bare ledger (no Loop State, model empty) → loopstate ⊳ model_incomplete (loopstate is earlier).
S1 = "# t — Hypotheses Registry\n\n**Target:** x\n\n## Active Hypotheses\n\n"
scenario("S1 bare: loopstate ⊳ model_incomplete", S1, "missing_loopstate", min_fire=2)

# S2: Impacts present, Loop State ABSENT, scout PENDING, model empty → loopstate wins the 4-way shadowing.
S2 = ("# t\n\n**Impacts in Scope:** Critical: drain funds\n\n"
      "## Scout Fan-Out\n\n**Status:** `PENDING`\n\n## Active Hypotheses\n\n")
scenario("S2 no-loopstate 4-way: loopstate ⊳ (scout/model)", S2, "missing_loopstate", min_fire=3)

# S3: Impacts+LoopState present (MODEL real, not N/A), the model file is empty, scout PENDING →
#     model_before_scout ⊳ scout_pending ⊳ model_incomplete (divergence-first: the model BEFORE the fan-out).
S3 = ("# t\n\n**Impacts in Scope:** Critical: x\n\n## Loop State\n- **Iteration #:** 1\n"
      "\n## Scout Fan-Out\n\n**Status:** `PENDING`\n\n## Active Hypotheses\n\n")
scenario("S3 model-before-scout ⊳ scout ⊳ model_incomplete", S3, "model_before_scout", min_fire=2)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
