#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEMPLATE <-> DETECTOR consistency -- a permanent check (introduced 2026-07-28).

Why. A failure class that has already bitten us: the detector looks at the shape of the template, the template
gets edited -- and the detector silently goes blind. `ledger_first_nudge` did not fire for months because the
examples inside the template (`Depth-Lead: {… H-03 — 3/5 …}`) were read as "work already recorded". There are no
errors in the logs, the hook looks alive. Synthetic ledgers in other replay harnesses do NOT catch this class --
they test the detector's logic, not that it is consistent with the REAL template.

So the input here is the REAL files `hypotheses_template.md` and `system_model_template.md`, not
synthetics. We check both directions:
  FIRE   -- on an untouched template the detector MUST fire (otherwise it is blind: the sentinel was renamed,
            the placeholder rewritten, the section removed);
  SILENT -- on an untouched template the detector must stay silent (otherwise a new hunt is blocked out of the
            blue before the first action).

Run: py -3 -X utf8 scripts/_methodology/template_sentinel_check.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL_LEDGER = os.path.join(ROOT, "sessions", "_methodology", "hypotheses_template.md")
TPL_MODEL = os.path.join(ROOT, "sessions", "_methodology", "system_model_template.md")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = load(os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py"), "gate")
nudge = load(os.path.join(ROOT, "scripts", "hooks", "ledger_first_nudge.py"), "nudge")
entry = load(os.path.join(ROOT, "scripts", "hooks", "hunt_entry_gate.py"), "entry")

work = tempfile.mkdtemp()
shutil.copy(TPL_LEDGER, os.path.join(work, "hypotheses.md"))
shutil.copy(TPL_MODEL, os.path.join(work, "system_model.md"))
open(os.path.join(work, ".hunt_active"), "w", encoding="utf-8").write("0\nsid")

gate.freshest_active_ledger = lambda sid: (os.path.join(work, "hypotheses.md"), work)

results = []


def check(name, fn, expect_fire, why):
    try:
        got = bool(fn("sid"))
    except Exception as e:
        print("  [FAIL] %-38s EXCEPTION: %s" % (name, e))
        results.append(False)
        return
    ok = got == expect_fire
    print("  [%s] %-38s fired=%-5s expect=%-5s — %s"
          % ("PASS" if ok else "FAIL", name, got, expect_fire, why))
    results.append(ok)


print("UNTOUCHED ledger template + untouched model template (state: \"hunt just started\")\n")
print("── MUST FIRE (otherwise the detector went blind on a template edit)")
check("ledger_thin", gate.active_ledger_thin, True,
      "empty template = no work")
check("missing_impacts", gate.active_ledger_missing_impacts, True,
      "IMPACTS-TODO sentinel in place")
check("missing_oos", gate.active_ledger_missing_oos, True,
      "OOS-TODO sentinel in place (Out-of-Scope disqualifiers not read through)")
check("assets_unreconciled", gate.active_ledger_assets_unreconciled, True,
      "ASSETS-RECON sentinel in place (N total assets not reconciled with M extracted — lombard item 1)")
check("scout_pending", gate.active_ledger_scout_pending, True,
      "Scout Fan-Out Status: PENDING")
check("model_incomplete", gate.active_model_incomplete, True,
      "model = template: row I-01 without a status")

print("\n── MUST STAY SILENT (otherwise a new hunt is blocked before the first action)")
check("optmenu_todo", gate.active_ledger_optmenu_todo, False,
      "OPT-triage is asked only when Scout=DONE, silent on PENDING — by design")
check("missing_loopstate", gate.active_ledger_missing_loopstate, False,
      "the template has a Loop State section")
check("wide_but_shallow", gate.active_ledger_wide_but_shallow, False,
      "zero hypotheses is not \"wide-but-shallow\"")
check("moneylead_shallow", gate.active_moneylead_shallow, False,
      "template value section = `{узел 1}` placeholder + zero H → money-lead depth-gate stays silent")
check("depthmap_placeholder", gate.active_ledger_depthmap_placeholder, False,
      "no claim of >=5 layers yet")
check("depthmap_single_subsystem", gate.active_ledger_depthmap_single_subsystem, False,
      "no depth map yet")
check("depth_t12_incomplete", gate.active_depth_t12_incomplete, False,
      "claim <3 layers + Prediction-miss in a placeholder")
check("composite_abandoned", gate.active_ledger_composite_abandoned, False,
      "no composites written out yet")
check("model_order_violation", gate.active_model_order_violation, False,
      "no statuses yet → pred cannot be \"after the fact\"")
check("divergence_unresolved", gate.active_divergence_unresolved, False,
      "no divergences opened yet")
check("model_axes_incomplete (untouched template)", gate.active_model_axes_incomplete, False,
      "zero statused I-NN → model not built, axes-force stays silent (model_incomplete catches it earlier)")
check("library_not_banked", gate.active_library_not_banked, False,
      "HUNT-EXIT not recorded — too early to check the bank")
check("axis_reranked_midqueue (untouched template)", gate.active_axis_reranked_midqueue, False,
      "the Axis-Queue template carries the reorder marker `re-ranked ABOVE queue-tails` as an EXAMPLE inside a `{...}` "
      "placeholder → brace-aware _line_signal_present skips it (a naive per-line `{` would read a continuation)")
check("axis_closed_critical_only (untouched template)", gate.active_axis_closed_critical_only, False,
      "the template has no crit-only axis closure + brace-tracking skips placeholder examples")
check("undup_sweep_incomplete (untouched template, thin model)",
      gate.active_undup_sweep_incomplete, False,
      "model = template I-01 without a status → _i_matured_count<3, the off-switch keeps the gate quiet "
      "(first scout pass — Task 1, FDE Plan 6)")

print("\n── PostToolUse nudge on subagent return")
fired = nudge._ledger_thin(os.path.join(work, ".hunt_active"))
ok = fired is True
print("  [%s] %-38s thin=%-5s expect=True  — %s"
      % ("PASS" if ok else "FAIL", "nudge._ledger_thin", fired,
         "H-NN examples inside {...} do NOT count as work"))
results.append(ok)

# And the other side: as soon as a real hypothesis appears in the ledger, the nudge must go quiet.
p = os.path.join(work, "hypotheses.md")
with open(p, "a", encoding="utf-8") as f:
    f.write("\n### H-01: real hypothesis\n- **Code:** `src/A.sol:10`\n")
fired2 = nudge._ledger_thin(os.path.join(work, ".hunt_active"))
ok2 = fired2 is False
print("  [%s] %-38s thin=%-5s expect=False — %s"
      % ("PASS" if ok2 else "FAIL", "nudge after real H-01", fired2,
         "otherwise the nudge will spam the whole hunt"))
results.append(ok2)

import re as _re

print("\n── REALISTICALLY FILLED template: the detector MUST COME ALIVE (scout fan-out regression 2026-07-28)")
print("   Class: the detector looked at the shape of the REAL template (RULES header / trailing doc on")
print("   a field line) and was dead — synthetic ledgers in replay did not catch this.\n")

_LP = os.path.join(work, "hypotheses.md")
_TPL = open(TPL_LEDGER, encoding="utf-8").read()


def put(txt):
    open(_LP, "w", encoding="utf-8").write(txt)
    gate.freshest_active_ledger = lambda sid: (_LP, work)


def assert_true(name, cond, why):
    print("  [%s] %-42s -> %-5s expect=True  — %s"
          % ("PASS" if cond else "FAIL", name, cond, why))
    results.append(bool(cond))


def assert_false(name, cond, why):
    print("  [%s] %-42s -> %-5s expect=False — %s"
          % ("PASS" if (not cond) else "FAIL", name, cond, why))
    results.append(not cond)


# #4 — _max_depth must not pick up `{… H-03 — 3/5 …}` from an UNFILLED field example.
assert_true("_max_depth(untouched)==0", gate._max_depth(_TPL) == 0,
            "placeholder `{…3/5…}` = instruction, not work (there used to be a phantom 3)")

# R1 (SUD-HIGH-1/MED-3, live run) — TEMPLATE<->axes-PARSER consistency. In the untouched template close-grade
# is shown by a placeholder `close-grade:<depth-drive|…>` (angle brackets) → the axes parsers MUST return 0
# (otherwise a new hunt falsely counts the example as an axis). Catches a future edit that removes `<>` from the example.
_tpl_rows = gate._atom_rows(_TPL) or []
assert_true("_depth_claimed_axes(untouched)==0", len(gate._depth_claimed_axes(_TPL, _tpl_rows)) == 0,
            "placeholder `close-grade:<…>` is not counted as a depth axis (angle brackets block it)")
assert_true("_scout_graded_axes(untouched)==0", len(gate._scout_graded_axes(_TPL, _tpl_rows)) == 0,
            "placeholder `close-grade:<…>` is not counted as a scout axis")
assert_true("_grounded_observed(untouched)==0", gate._grounded_observed_count(_TPL) == 0,
            "the template has no real `observed: file:line` — only placeholders")
# POSITIVE — the detector MUST COME ALIVE on the real axes format (bold + template non-bold). Catches the case where
# the Axes-Closed format in the template changes and the parser goes blind (scout fan-out regression class: detector
# dead on a template edit). We insert 5 closed axes in exactly the two live forms.
# KEEP: "ось" (Russian for "axis") in the fixture axis names below is test-fixture input, left as-is
_live_axes = "\n## Axes-Closed\n" + "".join(
    "  - **bold-ось-%d (I-0%d)** · src:model · outcome:clean · close-grade:depth-drive · proof:5/5\n" % (i, i)
    for i in range(1, 4)) + "".join(
    "- nonbold-ось-%d · src:model · outcome:clean · close-grade:scout-verified · proof:5/5\n" % i
    for i in range(4, 6))
_tpl_live = _TPL + _live_axes
assert_true("_depth_claimed_axes(live)>=3 [bold+nonbold]",
            len(gate._depth_claimed_axes(_tpl_live, gate._atom_rows(_tpl_live) or [])) >= 3,
            "3 bold depth axes recognized (live bold format)")
assert_true("_scout_graded_axes(live)>=2 [nonbold]",
            len(gate._scout_graded_axes(_tpl_live, gate._atom_rows(_tpl_live) or [])) >= 2,
            "2 non-bold scout axes recognized (template format `- <axis> ·`)")
put(_TPL)  # restore the untouched template for the following checks

# Cross-cutting T (FEAT-A/L/E/I/C/K, live run 2026-08-12) — FEAT fields in the template are PLACEHOLDERS `{…}`:
# detectors MUST see them as NOT filled (otherwise the gate forces emptiness / is blind on the placeholder).
assert_true("_reliability_pct(untouched) is None", gate._reliability_pct(_TPL) is None,
            "FEAT-A: `Final Reliability: {N%}` placeholder → not a number")
assert_true("_value_at_risk_quantified(untouched)==False", gate._value_at_risk_quantified(_TPL) is False,
            "FEAT-L: `Value-at-risk: {none yet}` → not quantified")
assert_true("_fanout_run_count(untouched)==0", gate._fanout_run_count(_TPL, gate._atom_rows(_TPL) or []) == 0,
            "FEAT-E: `HYBRID-fanout: {none yet}` + RULES prose → 0 runs")
assert_true("_freshness NOT in placeholder", not gate._line_signal_present(_TPL, gate._FRESHNESS_RE),
            "FEAT-K: `banked-freshness: {none yet}` placeholder is not counted as done")
assert_true("_cold_recheck NOT in placeholder", not gate._line_signal_present(_TPL, gate._COLD_RECHECK_RE),
            "FEAT-C: `cold-recheck: {none yet}` placeholder is not counted as done")
assert_true("_crossthread_synth(untouched) is None", gate._crossthread_synth_count(_TPL) is None,
            "FEAT-I: `cross-thread synthesis: {none yet}` → not DONE")
assert_true("_banked_t6_done(untouched) is None", gate._banked_t6_done_count(_TPL) is None,
            "SUD-MED-2: `Banked T6-pass: {none yet}` → not DONE")

# Z2 (judge HIGH-2/MED): IN-PLACE fill of template FEAT fields — the detector MUST recognize the value even
# when the field name carries a parenthetical `(FEAT-X — …)` before `:`. Previously the sentinel checked ONLY the placeholder `{…}`
# → the parenthetical trap slipped through (hard-gate FEAT-A blocked exit even with Reliability recorded).
import re as _re


def _inplace(txt, field_re, value):
    """Replace the field's `{…}` placeholder (by the regex anchor of the name) with a real value — emulates an in-place fill."""
    out = []
    for l in txt.splitlines():
        if field_re.search(l) and "{" in l:
            l = _re.sub(r"\{[^{}]*\}", value, l)
        out.append(l)
    return "\n".join(out)


_rel_filled = _inplace(_TPL, _re.compile(r"final[\s-]*reliability", _re.I), "72%")
assert_true("_reliability_pct(in-place 72%)==72", gate._reliability_pct(_rel_filled) == 72,
            "FEAT-A: in-place `(FEAT-A — …):** 72%` recognized (parenthetical-tolerant)")
_var_filled = _inplace(_TPL, _re.compile(r"value[\s-]*at[\s-]*risk", _re.I), "$2.4M (fork: fpd.json)")
assert_true("_value_at_risk_quantified(in-place)==True", gate._value_at_risk_quantified(_var_filled) is True,
            "FEAT-L: in-place `(FEAT-L — …):** $2.4M` quantified (parenthetical-tolerant)")
# off-switch collision: an UNTOUCHED template (placeholders) must NOT falsely lift the FEAT-E/FEAT-B gates —
# _FANOUT_NA_RE / _REPORT_TMPL_RE must not match a REAL (non-{}, non-->) line in the untouched template.
assert_true("_fanout_na NOT in real template lines", not gate._line_signal_present(_TPL, gate._FANOUT_NA_RE),
            "FEAT-E: `fanout N/A` lives only in the {placeholder} → off-switch does not fire falsely")
assert_true("_report_tmpl NOT in real template lines", not gate._line_signal_present(_TPL, gate._REPORT_TMPL_RE),
            "FEAT-B: `immunefi_dapp.md` lives only in the {placeholder} → off-switch does not fire falsely")

# Judge-2 LOW-5: the canonical Refuted block MUST carry `Severity if confirmed` — otherwise FEAT-C
# (`_strong_refute_count` block-scan) does not see a strong thread and stays silent forever (template<->detector desync).
assert_true("Refuted template carries `Severity if confirmed`",
            "Severity if confirmed" in _TPL,
            "FEAT-C: without the severity field the block-scan does not recognize a High/Crit refuted thread")
_ref_filled = ("### H-03 [KILLED]: share inflation\n"
               "- **Severity if confirmed:** High\n"
               "- **Killed by (falsifier — MANDATORY):** Vault.sol:120 guard\n")
assert_true("_strong_refute_count(canonical filled block)==1",
            gate._strong_refute_count(_ref_filled) == 1,
            "FEAT-C: a filled canonical block with `Severity: High` is recognized as a strong thread")
assert_true("_strong_refute_count(untouched template)==0",
            gate._strong_refute_count(_TPL) == 0,
            "FEAT-C: an untouched template (placeholders) is not counted as a refuted thread")

# Judge-2 (final acceptance) — BRACE-AWARE: multi-line placeholder. `{` on line 1, the signal on line 2
# WITHOUT a brace. A naive per-line skip read the continuation as a real entry → blinded the gate.
_multiline_ph = ("- **Severity if confirmed:** {High|Critical — a strong thread\n"
                 "  requires adversarial cold-recheck, not a self-falsifier}\n")
assert_true("brace-aware: signal on line 2 of a {placeholder} is NOT counted",
            not gate._line_signal_present(_multiline_ph, gate._COLD_RECHECK_RE),
            "a multi-line placeholder is ignored entirely (depth-tracking of `{`/`}`)")
# KEEP: Russian fixture text ("cold agent confirmed the refute") — the line is regex-matched by the cold-recheck detector
_real_after_ph = _multiline_ph + "- cold-recheck: H-03 — cold-агент подтвердил refute\n"
assert_true("brace-aware: a REAL entry AFTER the placeholder is counted",
            gate._line_signal_present(_real_after_ph, gate._COLD_RECHECK_RE),
            "the closing `}` restores depth=0 → the next line is read normally")

# #1 — T12: in the real template the RULES header "8. **DEPTH-LEAD-FIRST**" comes first → previously
# .search() took IT (depth=0) → claim<3 always → the gate was DEAD. Fill the field 5/5 without DEPTH-TRACE.
def _fill_depth_lead(txt, val):
    return "\n".join(
        ("- **Depth-Lead:** " + val) if l.strip().startswith("- **Depth-Lead:**") else l
        for l in txt.splitlines())

t12_live = _fill_depth_lead(_TPL, "H-07 — 5/5 (call->state->external->hook->accounting)")
put(t12_live)
assert_true("t12 fires on filled 5/5 no-trace", bool(gate.active_depth_t12_incomplete("sid")),
            "a 5-layer claim without a DEPTH-TRACE section — the gate was forever dead (RULES header first)")
put(_TPL)
assert_false("t12 silent on untouched", bool(gate.active_depth_t12_incomplete("sid")),
             "fresh template: no real claim of >=3")

# #2 — P-B: the trailing doc on the BOUNDARY-MAP field line contains the literal `` `{` `` → the old `"{" not in`
# blocked FOREVER. Set Scout=DONE; fill ONLY the {…} placeholder, the doc prose stays.
_done = _TPL.replace("`PENDING`", "`DONE 2026-07-28`")
put(_done)
assert_true("pb-gate blocks on DONE+placeholder", bool(gate.active_ledger_boundary_scout_skipped("sid")),
            "Scout DONE, but BOUNDARY-MAP is still `{placeholder}` — the block is legitimate")


def _fill_boundary(txt):
    def repl(m):
        return _re.sub(r"\{[^}]*\}", "oracle Foo.sol:120; relayer Bar.sol:80", m.group(0), count=1)
    return _re.sub(r"(?im)^\s*-\s*\*\*\s*boundary-map[^\n]*$", repl, txt)


_done_filled = _fill_boundary(_done)
put(_done_filled)
assert_false("pb-gate silent on DONE+filled(keep prose)", bool(gate.active_ledger_boundary_scout_skipped("sid")),
             "placeholder filled, the literal `{` in the trailing doc must NOT block forever")

print("\n── slug normalization of explorer links (finding #3: two contracts → one sessions/address/)")
_s1 = entry.slug_from_url("https://etherscan.io/address/0xAAAA1111")
_s2 = entry.slug_from_url("https://basescan.org/address/0xBBBB2222")
_s3 = entry.slug_from_url("https://etherscan.io/address/0xAAAA1111")
assert_true("explorer slugs distinct", _s1 != _s2 and "address" not in (_s1, _s2),
            "different contracts/chains → different folders (both used to be `address`): %s vs %s" % (_s1, _s2))
assert_true("explorer slug stable", _s1 == _s3, "same URL → same slug (RESUME works)")
assert_true("immunefi slug intact", entry.slug_from_url("https://immunefi.com/bug-bounty/foobar") == "foobar",
            "regression: ordinary program links are not broken")
assert_true("github slug intact", entry.slug_from_url("https://github.com/org/myrepo") == "myrepo",
            "regression: github org/repo is not broken")

print("\n── OBS-fixes (live run 2026-07-28): recon/scout gates × template placeholders")

# OBS-3: wave_pending must NOT latch onto the template placeholder `{… WAVE-2: … PENDING …}`.
put(_TPL)
assert_false("wave_pending silent on untouched tpl", bool(gate.active_ledger_wave_pending("sid")),
             "placeholder `{…WAVE-2…PENDING…}` = example, not a deferred wave (there was a false force)")
# …but a real deferred wave (a line OUTSIDE {}) must be caught — the fix must not blind the detector.
_wave_real = _TPL + "\n- **WAVE-2 overflow (P8 conservation) — PENDING**\n"
put(_wave_real)
assert_true("wave_pending fires on real WAVE-2 PENDING", bool(gate.active_ledger_wave_pending("sid")),
            "a real `- **WAVE-2 … PENDING` line outside a placeholder → detection preserved")

# OBS-2: scout_pending honors `MODEL: BUILDING` — a scout by invariants is logically AFTER the model.
put(_TPL)
assert_true("scout_pending fires (no MODEL:BUILDING)", bool(gate.active_ledger_scout_pending("sid")),
            "untouched template: Scout PENDING, no model stage → force is legitimate (old behavior)")
_building = _TPL + "\n- **MODEL:** BUILDING — stateful EVM, T10 применим\n"  # KEEP: Russian fixture tail ("T10 applicable")
put(_building)
assert_false("scout_pending silent while MODEL:BUILDING", bool(gate.active_ledger_scout_pending("sid")),
             "model is being built → scout by invariants comes AFTER it, don't force (divergence-first order)")
# markdown tolerance of the regex: `**MODEL:** BUILDING` (as really written in Loop State) must match
assert_true("_model_building tolerates markdown", gate._model_building("- **MODEL:** BUILDING — x"),
            "the regex tolerates `**`/`:` between MODEL and BUILDING (otherwise the field bullet would not match)")

# OBS-5 (live run 2026-07-28): _MANUAL_RE/_OFF_RE/_MODEL_NA_RE — the same markdown blindness that
# _model_building had. Loop State writes fields as `- **HUNT-MODE:** MANUAL`; with the old `:\s*` they silently did NOT
# activate (the whole hunt thought it was in MANUAL, but ran autonomously). The detector MUST fire on a
# markdown-wrapped field, otherwise it is blind to a real ledger edit.
assert_true("_MANUAL_RE tolerates markdown", bool(gate._MANUAL_RE.search("- **HUNT-MODE:** MANUAL")),
            "the regex tolerates `:**` between HUNT-MODE and MANUAL (a bare line activated, markdown did not)")
assert_true("_OFF_RE tolerates markdown", bool(gate._OFF_RE.search("- **HUNT-MODE:** OFF")),
            "same class as MANUAL")
assert_true("_MODEL_NA_RE tolerates markdown", bool(gate._MODEL_NA_RE.search("- **MODEL:** N/A — web2")),
            "lifts the model gates on web2/frontend even when the field is in a markdown bullet")
assert_false("_MANUAL_RE not on AUTONOMOUS", bool(gate._MANUAL_RE.search("HUNT-MODE: AUTONOMOUS")),
             "does not catch another mode (anti-FP)")

print("\n── P1/P3 (live run 2026-07-29): the template `| I-01 |` is NOT counted as a built model")
print("   Class: the entry hook creates system_model.md from the template (example row `| I-01 | | | … |`) →")
print("   the \"model built\" detector would go blind, counting an empty template as a finished model.\n")
mfn = load(os.path.join(ROOT, "scripts", "hooks", "model_first_nudge.py"), "mfn")
_tpl_model = open(TPL_MODEL, encoding="utf-8").read()
# restore the UNTOUCHED template into work (intermediate cases overwrote hypotheses.md with a filled one)
shutil.copy(TPL_LEDGER, os.path.join(work, "hypotheses.md"))
shutil.copy(TPL_MODEL, os.path.join(work, "system_model.md"))

assert_false("nudge._model_has_real_invariant(template)",
             mfn._model_has_real_invariant(_tpl_model),
             "template I-01 (empty check+pred) ≠ a built model — the solo depth-guard stays sighted")
print("  [%s] gate._grounded_i_count(template)==0          got=%d expect=0 — %s"
      % ("PASS" if gate._grounded_i_count(_tpl_model) == 0 else "FAIL",
         gate._grounded_i_count(_tpl_model), "grounded I-NN on an empty template = 0"))
results.append(gate._grounded_i_count(_tpl_model) == 0)
check("active_model_incomplete (template)", gate.active_model_incomplete, True,
      "model not built (zero grounded I-NN) → the gate forces T10")
check("active_model_before_scout (template)", gate.active_model_before_scout, True,
      "P0: scout PENDING + model empty → force the MODEL BEFORE the fan-out")

print("\n── P-MULTI-WAVE (live run 2026-07-29): template axis marker words do NOT blind the axes detector")
print("   Class: the template's `Invariant Wave Axes` section contains cross-function/order/temporal/isolation/")
print("   economic → on a fresh model the detector could consider the axes \"covered\". Instructions (`>` and `{TODO}`)")
print("   are stripped, so a built wave-1 must TRIGGER the force of the next axis.\n")
# untouched model template + the agent appended WAVE 1 (3 single-function statused I-NN); no waves 2+
# KEEP: Russian "Формула-N" fixture formulas in model rows (unsure whether parsed; left as-is)
_w1 = ("\n- **I-01** [state] Формула-1. check: X. pred: ENFORCED status: ENFORCED\n"
       "- **I-02** [state] Формула-2. check: Y. pred: ENFORCED status: ENFORCED\n"
       "- **I-03** [state] Формула-3. check: Z. pred: ENFORCED status: ENFORCED\n")
open(os.path.join(work, "system_model.md"), "w", encoding="utf-8").write(_tpl_model + _w1)
check("active_model_axes_incomplete (template+wave1)", gate.active_model_axes_incomplete, True,
      "wave-1 built, axes 2-6 not covered — the detector is NOT blind to template marker words")

print("\n── money-lead depth-gate (§4): the value section of the REAL template is FILLED → the detector COMES ALIVE")
print("   Class: the detector is keyed on the heading `## Value Concentration` of the REAL model template —")
print("   if the section is renamed / removed → _section_rows returns empty → the detector silently goes blind (fails).\n")
# KEEP: the replaced string is an exact byte copy of the Russian template row (must match the template)
_ml_model = open(TPL_MODEL, encoding="utf-8").read().replace(
    "| {узел 1} | {тип} | {reachable, не headline-TVL} | {permissionless? / роль} | {— / I-NN} |",
    "| StakingVault | TVL-pool | $2.1M reachable | permissionless deposit | I-03 |")
open(os.path.join(work, "system_model.md"), "w", encoding="utf-8").write(_ml_model)
_ml_4h = "\n### H-01: a\n### H-02: b\n### H-03: c\n### H-04: d\n"
put(_TPL + _ml_4h + "- **Depth-Lead:** H-01 — 3/5 (call->state->external)\n")
assert_true("moneylead fires: value mapped + 4H + depth<5", bool(gate.active_moneylead_shallow("sid")),
            "filled `## Value Concentration` of the real template + pool + thread <5 → depth order on the $-thread")
put(_TPL + _ml_4h + "- **Depth-Lead:** H-01 — 5/5 (call->state->external->hook->accounting)\n")
assert_false("moneylead silent: thread at 5/5", bool(gate.active_moneylead_shallow("sid")),
             "the strongest $-thread reached 5 layers → the gate is silent even on the real template")

print("\n── undup_sweep gate (Task 1, FDE Plan 6 §50.1/§51): section <-> detector consistent")
print("   Class: the detector looks at the shape of the REAL `## Un-Dup Sweep` — if the section is renamed /")
print("   the status line rewritten, the detector silently goes blind (like ATTENTION_GAP/ledger_first_nudge).\n")

# The real model template (`system_model_template.md`) starts with ONE empty I-01 row —
# deliberately IMMATURE (the off-switch keeps the gate quiet, checked above). For FIRE/SILENT of the undup
# detector itself a MATURE model (>=3 statused I-NN) is needed — we synthesize it SEPARATELY (as the money-lead
# block does for `## Value Concentration`), and leave the ledger as the REAL untouched file.
# KEEP: Russian table column headers and cell text below are fixture inputs parsed by the gate (unsure) — left as-is
_MATURE_MODEL = (
    "## Invariants\n"
    "| ID | Ф | check: | Класс | Ист | component: | pred: | Статус | file:line | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| I-01 | supply==sum | верно ли supply | state | code | Vault | ENFORCED | ENFORCED | a.sol:1 | 0 | cold | |\n"
    "| I-02 | onlyOwner на mint | роль проверена? | access | code | Vault | ENFORCED | ENFORCED | a.sol:2 | 0 | cold | |\n"
    "| I-03 | redeem конс. | нет утечки | state | code | Vault | ABSENT | ABSENT | a.sol:3 | 0 | cold | |\n"
)
open(os.path.join(work, "system_model.md"), "w", encoding="utf-8").write(_MATURE_MODEL)

put(_TPL)
assert_true("undup_sweep FIRES on untouched real ledger + mature model",
            bool(gate.active_undup_sweep_incomplete("sid")),
            "untouched `## Un-Dup Sweep` (8 seed `{TODO}` + 7 `N/A — web-only`) + mature model → "
            "applicable generators without a status → the gate MUST hold (otherwise blind to a template edit)")

_undup_filled = _TPL.replace("| {TODO} |", "| RUN |")
put(_undup_filled)
assert_false("undup_sweep silent once every seed row carries RUN/justified N/A",
              bool(gate.active_undup_sweep_incomplete("sid")),
              "all 8 applicable rows -> RUN, 7 profile N/A untouched -> the gate lifts the hold")

put(_TPL)  # restore untouched ledger for any downstream reuse of `work`

print("\n── pattern_replay gate (Task 5, FDE Plan 7 §61 · §48.1): PRIOR-PATTERNS <-> detector consistent")
print("   Class: the detector looks at the shape of the REAL line `PRIOR-PATTERNS: {TODO}` in Loop State —")
print("   if the line is renamed / the value rewritten, the detector silently goes blind (like ATTENTION_GAP/undup_sweep).\n")


def _fill_prior_patterns(txt, val):
    return "\n".join(
        ("- **PRIOR-PATTERNS (§48.1 — recon-producer):** " + val)
        if l.strip().startswith("- **PRIOR-PATTERNS") else l
        for l in txt.splitlines())


# A mature model (>=3 statused I-NN) is synthesized separately (like the undup block above) — the real template
# model is deliberately immature (the off-switch keeps the gate quiet). Ledger — the REAL untouched _TPL with
# the sentinel `PRIOR-PATTERNS: {TODO}` in Loop State.
open(os.path.join(work, "system_model.md"), "w", encoding="utf-8").write(_MATURE_MODEL)
put(_TPL)
assert_true("pattern_replay FIRES on untouched real ledger (PRIOR-PATTERNS: {TODO}) + mature model",
            bool(gate.active_pattern_replay_skipped("sid")),
            "untouched line `PRIOR-PATTERNS: {TODO}` in Loop State + mature model → producer not "
            "run → the gate MUST hold (otherwise blind to a line rename)")

put(_fill_prior_patterns(_TPL, "3 matched — PAT-01@a.tsx:2"))
assert_false("pattern_replay silent once PRIOR-PATTERNS carries 'N matched' (producer was run)",
             bool(gate.active_pattern_replay_skipped("sid")),
             "producer wrote `3 matched` → sentinel lifted → the gate lifts the hold")

put(_TPL)  # restore untouched ledger

print("\n── exposure_scan gate (P0-2, Aug-2026): EXPOSURE-SCAN <-> detector consistent")
print("   Class: the detector looks at the shape of the REAL line `EXPOSURE-SCAN: {TODO}` in Loop State —")
print("   if the line is renamed / the value rewritten, the detector silently goes blind (like PRIOR-PATTERNS/undup_sweep).\n")


def _fill_exposure_scan(txt, val):
    return "\n".join(
        ("- **EXPOSURE-SCAN (P0-2 Exposure Engine):** " + val)
        if l.strip().startswith("- **EXPOSURE-SCAN") else l
        for l in txt.splitlines())


open(os.path.join(work, "system_model.md"), "w", encoding="utf-8").write(_MATURE_MODEL)
put(_TPL)
assert_true("exposure_scan FIRES on untouched real ledger (EXPOSURE-SCAN: {TODO}) + mature model",
            bool(gate.active_exposure_scan_skipped("sid")),
            "untouched line `EXPOSURE-SCAN: {TODO}` in Loop State + mature model → producer not "
            "run → the gate MUST hold (otherwise blind to a line rename)")

put(_fill_exposure_scan(_TPL, "2 secrets / 0 pii / 0 data / 0"))
# 2026-08-14 hardening: a real value WITHOUT the exposure_scan.md artifact = ad-hoc grep
# (a bare grep does NOT write it) → the producer secret_exposure_scanner was not run → the gate HOLDS. The test used to
# expect silent on a bare value (before this fix) → it lagged behind the contract; now it checks both links.
_exp_art = os.path.join(work, "exposure_scan.md")
if os.path.exists(_exp_art):
    os.remove(_exp_art)
assert_true("exposure_scan HOLDS on real value WITHOUT exposure_scan.md artifact (ad-hoc grep)",
            bool(gate.active_exposure_scan_skipped("sid")),
            "value filled in, but the producer artifact is missing → ad-hoc grep → the gate holds")
open(_exp_art, "w", encoding="utf-8").write("# exposure scan\n2 secrets / 0 pii / 0 data / 0\n")
assert_false("exposure_scan silent once value + exposure_scan.md artifact (producer ran FULLY)",
             bool(gate.active_exposure_scan_skipped("sid")),
             "producer wrote the line AND left exposure_scan.md → sentinel lifted → the gate lifts the hold")
os.remove(_exp_art)

put(_TPL)  # restore untouched ledger

print("\n── intent-steelman gate (Plan 9, Tier B · T6): H-NN State <-> **Intent-steelman field consistent")
print("   Class: the detector is keyed on a RESOLVED `- **State:** C-PoC-attempting/D-PoC` in an H-NN block +")
print("   the field `- **Intent-steelman ...`. The template State = a slash-MENU (A/B/C/D…) → NOT DRIVE, the gate is silent;")
print("   if State/the field is renamed in the template — the detector silently goes blind (like undup_sweep/pattern_replay).\n")


def _resolve_state(txt, val):
    return "\n".join(
        ("- **State:** " + val) if l.strip().startswith("- **State:**") else l
        for l in txt.splitlines())


def _fill_intent(txt, val):
    return "\n".join(
        ("- **Intent-steelman:** " + val) if l.strip().startswith("- **Intent-steelman") else l
        for l in txt.splitlines())


# the gate is NOT model-gated (the DRIVE state is a signal by itself) — the model in work does not matter.
put(_TPL)
assert_false("intent silent on untouched tpl (State = slash-menu, not DRIVE)",
             bool(gate.active_ledger_intent_steelman_missing("sid")),
             "untouched template: State = `A/B/C/D…` menu → H-NN not in DRIVE → the field is not required")

# resolve the State of the template H-NN to DRIVE, the field's {INTENT-TODO} placeholder NOT lifted → FIRE
_drive_ph = _resolve_state(_TPL, "C-PoC-attempting")
put(_drive_ph)
assert_true("intent FIRES: DRIVE + {INTENT-TODO} placeholder not lifted",
            bool(gate.active_ledger_intent_steelman_missing("sid")),
            "H-NN reached DRIVE (State C-PoC-attempting), but intent-steelman = {placeholder} → hold")

# the same DRIVE block, the field filled with a file:line proof → SILENT
_drive_filled = _fill_intent(_drive_ph, "NatSpec Vault.sol:42 pins this down as an invariant → KILL-candidate")
put(_drive_filled)
assert_false("intent silent: DRIVE + file:line proof filled",
             bool(gate.active_ledger_intent_steelman_missing("sid")),
             "the field carries `Vault.sol:42` → birth-time intent-check done → the gate lifts the hold")

# N/A — no intent evidence is also a valid resolution (absence of proof = a signal stronger than the hypothesis)
_drive_na = _fill_intent(_drive_ph, "N/A — no intent evidence found")
put(_drive_na)
assert_false("intent silent: DRIVE + `N/A — no intent evidence`",
             bool(gate.active_ledger_intent_steelman_missing("sid")),
             "no proof of intent anywhere → a conscious N/A lifts the hold (not an infinite block)")

# A DRIVE hypothesis with NO Intent-steelman field AT ALL (fresh H block) → FIRE (missing)
_drive_missing = _TPL + "\n### H-77: fresh drive hyp\n- **State:** D-PoC\n- **Code:** `src/A.sol:10`\n"
put(_drive_missing)
assert_true("intent FIRES: DRIVE hypothesis WITHOUT an Intent-steelman field at all",
            bool(gate.active_ledger_intent_steelman_missing("sid")),
            "fresh H-77 in D-PoC without the field → the task explicitly requires catching a missing field, not only a placeholder")

# scoped-to-DRIVE: State=B (not DRIVE) + {placeholder} → SILENT (don't load the whole loop)
_b_state = _resolve_state(_TPL, "B-sandbox-setup")
put(_b_state)
assert_false("intent silent: State=B (not DRIVE) even with {placeholder}",
             bool(gate.active_ledger_intent_steelman_missing("sid")),
             "scoped-to-DRIVE — A/B/MAYBE/building-block do NOT require the field (R4/T6, no friction on the loop)")

put(_TPL)  # restore untouched ledger

print("\n── axis_queue gate (Hunt Strategy Layer 2026-08-08): Axis-Queue <-> detector consistent")
print("   Class: the detector is keyed on the shape of the REAL field `- **Axis-Queue …:**` + `- **T9 restart axes")
print("   used:**` + `- **Depth-Lead:**` of Loop State. If the field is renamed / the placeholder rewritten — the detector")
print("   silently goes blind. NOT model-gated (an axis is closed on MODEL: N/A too) → the model file does not matter.\n")


def _set_t9(txt, val):
    return _re.sub(r"(?m)^(\s*-\s*\*\*\s*T9 restart axes used:\*\*).*$", r"\1 " + val, txt, count=1)


def _set_axis_queue(txt, val):
    # the Axis-Queue field is multi-line (`{…}` spans several lines) → consume up to the closing `}`.
    return _re.sub(r"(?ms)^(\s*-\s*\*\*\s*Axis-Queue[^\n]*?:\*\*).*?\}\s*$", r"\1 " + val, txt, count=1)


# SILENT on an untouched template: T9 = `{0-3+…}` → _t9_axes_used=0 → first pass → silent.
put(_TPL)
assert_false("axis_queue silent on untouched tpl (T9 {…} → 0 axes)",
             bool(gate.active_axis_queue_empty("sid")),
             "untouched template: no axis closed yet (t9=0), Axis-Queue is legitimately `{placeholder}` → silent")

# FIRE on the real template: an axis is CLOSED (t9=2), Axis-Queue emptied (`none`), Depth-Lead untouched
# (`{…}` placeholder → not active). "Between axes" = 0 LIVE H-NN: the template example `### H-{NN}:` in Active is
# counted as live by _HNN_HEAD_RE (H-\S), while in a real hunt with a closed axis the live H are moved to Refuted —
# we neutralize the placeholder with [KILLED] (the mid-drive off-switch correctly stays silent on a LIVE H, so the FIRE case
# must represent exactly the resolved Active state).
def _kill_active_placeholder(txt):
    return txt.replace("### H-{NN}: {one-line", "### H-{NN} [KILLED]: {one-line")
_aq_fire = _kill_active_placeholder(_set_axis_queue(_set_t9(_TPL, "2 (treasury, oracle)"), "none"))
put(_aq_fire)
assert_true("axis_queue FIRES: axis closed + Axis-Queue none + between axes",
            bool(gate.active_axis_queue_empty("sid")),
            "t9=2 closed, queue emptied to `none`, Depth-Lead placeholder + 0 live H → forward plan of "
            "axis changes not recorded → the gate MUST hold (otherwise blind to a field edit)")

# SILENT when the queue is filled with a valid axis with `src:` (the same real template form).
_aq_filled = _set_axis_queue(_set_t9(_TPL, "2 (treasury, oracle)"),
                             "\n  1) liquidation-accounting — src:D-03 · rank:high")
put(_aq_filled)
assert_false("axis_queue silent once queue carries valid src row",
             bool(gate.active_axis_queue_empty("sid")),
             "the queue carries `1) … — src:D-03` → forward plan recorded → the gate lifts the hold")

put(_TPL)  # restore untouched ledger


print("\n── A5 banked×T6 gate (Wave 1 2026-08-08): Banked T6-pass <-> detector consistent")
print("   Class: the detector is keyed on the shape of the REAL table `## Banked Findings` + the field `- **Banked")
print("   T6-pass:**`. If the field is renamed / the placeholder rewritten / the empty row changed — the detector goes blind.\n")

_EMPTY_BANKED = "| | | | | | | | | |"
_B_ROW1 = ("| 1 | Medium | H-03 | reflected XSS | attacker DOM string | admin session "
           "| tier2 | scout-P5 | confirmed |")
_B_ROW2 = ("| 2 | Low | H-07 | address leak | victim EOA | target addr "
           "| tier4 | deephunt-J5 | confirmed |")


def _set_banked(txt, rows):
    return txt.replace(_EMPTY_BANKED, "\n".join(rows), 1)


def _set_banked_t6(txt, val):
    return _re.sub(r"(?m)^(\s*-\s*\*\*\s*Banked T6-pass[^\n]*?:\*\*).*$", r"\1 " + val, txt, count=1)


# SILENT on an untouched template: an empty placeholder row → 0 banked → silent.
put(_TPL)
assert_false("banked_composite silent on untouched tpl (0 banked rows)",
             bool(gate.active_banked_composite_unchecked("sid")),
             "untouched template: an empty placeholder row → 0 banked → silent")

# FIRE on the real template: 2 banked rows filled, T6-pass = `{none yet}` (not done).
_bc_fire = _set_banked(_TPL, [_B_ROW1, _B_ROW2])
put(_bc_fire)
assert_true("banked_composite FIRES: 2 banked + T6-pass {none yet}",
            bool(gate.active_banked_composite_unchecked("sid")),
            "2 confirmed banked, T6-pass not done → hold the submission (otherwise blind to a table/field edit)")

# SILENT when T6-pass = DONE (the same real template field form).
_bc_done = _set_banked_t6(_bc_fire, "DONE — no chainable pairs")
put(_bc_done)
assert_false("banked_composite silent once T6-pass DONE",
             bool(gate.active_banked_composite_unchecked("sid")),
             "the field carries `DONE` → T6 pass over the bank done → the gate lifts the hold")

put(_TPL)  # restore untouched ledger


print("\n── Worklist Driver Stage 1 (2026-08-11): `## Atom Registry` <-> detectors consistent")
print("   Class: detectors are keyed on the shape of the REAL section `## Atom Registry` (table `| id | type |")
print("   ... | status | closes |`) + the field `- **Current pick:**`. If the section is renamed / columns changed /")
print("   the placeholder row `{AX-01}` changed — the detector silently goes blind. Behind the WORKLIST_DRIVER_ENABLED flag.\n")


def _add_atoms(txt, rows):
    """Inserts real atom rows right after the separator of the `## Atom Registry` table."""
    out, in_reg, done = [], False, False
    for l in txt.splitlines():
        out.append(l)
        if l.strip().startswith("## Atom Registry"):
            in_reg = True
        if in_reg and not done and _re.match(r"^\s*\|[-\s|]+\|\s*$", l):
            out.extend(rows)
            done = True
    return "\n".join(out)


def _set_pick(txt, val):
    return _re.sub(r"(?m)^(\s*-\s*\*\*\s*Current pick:\*\*).*$", r"\1 " + val, txt, count=1)


def _set_iter(txt, n):
    return _re.sub(r"(?m)^(\s*-\s*\*\*\s*Iteration #:\*\*).*$", r"\1 " + str(n), txt, count=1)


def _add_to_refuted(txt, line):
    """Inserts a line right after the `## Refuted …` heading (into the real proof section)."""
    out = []
    for l in txt.splitlines():
        out.append(l)
        if l.strip().startswith("## Refuted"):
            out.append(line)
    return "\n".join(out)


_AX_OPEN = ["| AX-04 | axis | liquidation-band | D-03 | 30 | OPEN | - |",
            "| AX-05 | axis | governance-timelock | T6-pair | 28 | OPEN | - |"]

# SILENT on an untouched template: the placeholder row `{AX-01}` = not an atom → no valid atoms → silent.
put(_TPL)
assert_false("pick_not_from_queue silent on untouched tpl (placeholder {AX-01} = not an atom)",
             bool(gate.active_pick_not_from_queue("sid")),
             "untouched template: the registry carries only the `{AX-01}` placeholder → 0 valid atoms → silent")

# FIRE (real-run class): the OPEN queue is non-empty (AX-04/AX-05), while Current pick went around the registry.
_pq_fire = _set_pick(_add_atoms(_TPL, _AX_OPEN), "optimizer-rounding — an axis I set myself (mock-vs-prod)")
put(_pq_fire)
assert_true("pick_not_from_queue FIRES: pick bypasses the registry (OPEN queue non-empty)",
            bool(gate.active_pick_not_from_queue("sid")),
            "AX-04/AX-05 OPEN in the registry, but the pick improvises around it → off-queue-pick class → the gate holds "
            "(otherwise blind to a section/column edit)")

# SILENT after the fix: the pick is synced with the registry head (references AX-04).
_pq_ok = _set_pick(_add_atoms(_TPL, _AX_OPEN), "AX-04 — taking the queue head")
put(_pq_ok)
assert_false("pick_not_from_queue silent once pick references registry head (AX-04)",
             bool(gate.active_pick_not_from_queue("sid")),
             "the pick references a real registry id → sync restored → the gate lifts the hold")

# C3 SILENT on an untouched template: the placeholder row is not CLOSED → no CLOSED atoms → silent.
put(_TPL)
assert_false("atom_closed_no_narrative silent on untouched tpl (no CLOSED rows)",
             bool(gate.active_atom_closed_without_narrative("sid")),
             "untouched template: the `{AX-01}` placeholder is not CLOSED → 0 CLOSED atoms → silent")

# C3 FIRE: H-91 CLOSED in the registry, but the id is NOWHERE in the template prose (no `### H-91` in Refuted).
_cn_fire = _add_atoms(_TPL, ["| H-91 | hypothesis | share-inflation | D-03 | 27 | CLOSED | - |"])
put(_cn_fire)
assert_true("atom_closed_no_narrative FIRES: H-91 CLOSED without a proof entry in prose",
            bool(gate.active_atom_closed_without_narrative("sid")),
            "H-91 CLOSED in the registry, id nowhere in the narrative → 39 prose gates would go blind → the gate holds")

# C3 SILENT after the fix: `### H-91 [KILLED]` appeared in the REAL proof section `## Refuted`
# (after judge-2 fix D4: a bare mention outside proof sections no longer counts).
put(_add_to_refuted(_cn_fire, "### H-91 [KILLED]: share inflation — guard vault.sol:88"))
assert_false("atom_closed_no_narrative silent once ### H-91 [KILLED] in ## Refuted",
             bool(gate.active_atom_closed_without_narrative("sid")),
             "a proof entry under H-91 in the real Refuted section → id in proof → the gate lifts the hold")
# (Notes-bypass D4 — a bare mention outside proof sections → FIRE — is densely covered in
#  worklist_driver_gate_replay.py cases C/C2, not duplicated here: an h3 `### Notes` in the tail of the real
#  template would land inside the last section `## Verifier Log` — an artifact of the template shape, not of the code.)

put(_TPL)  # restore untouched ledger

print("\n── active_registry_unpopulated (adoption gate, judge-2 D2): registry <-> detector consistent")
print("   Class: the detector is keyed on an empty `## Atom Registry` + a real `- **Current pick:**` + iter>=3.")
print("   If the section/field is renamed — it silently goes blind. Forces populating the registry on a mature active hunt.\n")

# SILENT on an untouched template: pick = placeholder `{...}` → not actively working → silent.
put(_TPL)
assert_false("registry_unpopulated silent on untouched tpl (placeholder pick)",
             bool(gate.active_registry_unpopulated("sid")),
             "untouched template: Current pick = `{...}` placeholder → not active work → silent")

# FIRE: a real pick + iter5 + the registry is still a placeholder (not populated) → force populating.
_ru_fire = _set_iter(_set_pick(_TPL, "H-05 — driving the thread"), 5)
put(_ru_fire)
assert_true("registry_unpopulated FIRES: real pick + iter5 + placeholder registry",
            bool(gate.active_registry_unpopulated("sid")),
            "active work (real pick, iter>=3), but the registry is empty → the machine worklist is not maintained → hold")

# SILENT after the fix: the registry is populated with valid atoms.
put(_add_atoms(_set_iter(_set_pick(_TPL, "AX-04 — head"), 5), _AX_OPEN))
assert_false("registry_unpopulated silent once registry populated",
             bool(gate.active_registry_unpopulated("sid")),
             "the registry carries valid atoms AX-04/AX-05 → the worklist is maintained → the gate lifts the hold")

put(_TPL)  # restore untouched ledger

shutil.rmtree(work, ignore_errors=True)
ok = sum(results)
print("\n%d/%d template<->detector cases green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
