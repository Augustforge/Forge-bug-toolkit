#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AOE money-lead depth-gate replay — PROVES the detector
`active_moneylead_shallow` fires (AOE §4 — money-lead-first depth; §3 value section).

System rule ([[feedback_hook_must_prove_firing]]): a replay test MUST prove FIRING —
it must fail if the detector is removed. Here the detector is called directly from the LIVE hook (importlib, not a copy);
remove the function/reason -> `call()` returns "MISSING" -> firing cases FAIL -> exit 1. Run against a
stripped copy: `py -3 -X utf8 aoe_moneylead_gate_replay.py <path/to/stripped_hook.py>`.

What is proven (brief Task 4, item 4):
  (a) FIRES (holds + depth order) when the value section is MAPPED, the pool is >=4 H, and the strongest $-thread is <5;
  (b) SILENT when the thread is already >=5 LAYERS OR the value section is absent/placeholder/N-A OR a High/Crit is found
      (success-exit short-circuits in main() BEFORE the detector — proven via ledger_success_exit);
  (c) fail-open: no active ledger / broken input -> None (NEVER holds blindly);
  (d) NOT corpus-gated: fires regardless of `_false_refute_corpus_count` (0 / -1 / 2);
  (+) SILENT on the untouched templates system_model_template.md + hypotheses_template.md;
  (+) proof-of-firing: detector + reason are wired into the hook.

Run: py -3 -X utf8 scripts/_methodology/aoe_moneylead_gate_replay.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# The HOOK path can be overridden via argv[1] — to check "the test fails without the detector" against a stripped copy.
HOOK = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks", "hunt_completeness_gate.py")
TPL_LEDGER = os.path.join(ROOT, "bug-bounty-toolkit", "sessions", "_methodology", "hypotheses_template.md")
TPL_MODEL = os.path.join(ROOT, "bug-bounty-toolkit", "sessions", "_methodology", "system_model_template.md")


def load_gate():
    spec = importlib.util.spec_from_file_location("gate", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = load_gate()
work = tempfile.mkdtemp()
LP = os.path.join(work, "hypotheses.md")
MP = os.path.join(work, "system_model.md")


def put_model(txt):
    with open(MP, "w", encoding="utf-8") as f:
        f.write(txt)


def put_ledger(txt):
    with open(LP, "w", encoding="utf-8") as f:
        f.write(txt)
    gate.freshest_active_ledger = lambda sid: (LP, work)


def set_corpus(n):
    gate._false_refute_corpus_count = lambda: n


def call(sid="sid"):
    """Detector from the LIVE hook. Function removed -> 'MISSING' -> firing checks FAIL (proof-of-firing)."""
    try:
        return gate.active_moneylead_shallow(sid)
    except AttributeError:
        return "MISSING"


# ── Model fixtures (section `## Value Concentration`) ─────────────────────────────────────────────
# NOTE: Cyrillic fixture text below is kept as-is — it mirrors the real template format that the hook parses.
MODEL_MAPPED = (
    "# system_model.md\n\n"
    "## Value Concentration — узлы концентрации value/authority\n\n"
    "| Узел | Тип | reachable-$ | Достижим кем | Нить |\n"
    "|---|---|---|---|---|\n"
    "| StakingVault | TVL-pool | $2.1M reachable | permissionless deposit | I-03 |\n"
    "| Timelock | upgrade-auth | full TVL | 3/5 multisig | I-07 |\n"
)
MODEL_PLACEHOLDER = (          # only a `{…}` placeholder -> value NOT mapped
    "# system_model.md\n\n"
    "## Value Concentration — узлы концентрации value/authority\n\n"
    "| Узел | Тип | reachable-$ | Достижим кем | Нить |\n"
    "|---|---|---|---|---|\n"
    "| {узел 1} | {тип} | {reachable} | {роль} | {— / I-NN} |\n"
)
MODEL_NA = (                   # `N/A — <reason>` sentinel (small/non-DeFi) -> NOT mapped
    "# system_model.md\n\n"
    "## Value Concentration — узлы концентрации value/authority\n\n"
    "| Узел | Тип | reachable-$ | Достижим кем | Нить |\n"
    "|---|---|---|---|---|\n"
    "| N/A — web2 target, TVL-концентрации нет | | | | |\n"
)
MODEL_NOSECTION = "# system_model.md\n\n## Actors & Trust\n\n(нет секции Value Concentration)\n"  # fixture: "(no Value Concentration section)"

# ── Ledger fixtures (hypotheses + Depth-Lead) ─────────────────────────────────────────────────────
_HDR = "# T — Hypotheses Registry\n"
_4H = "### H-01: a\n### H-02: b\n### H-03: c\n### H-04: d\n"
_2H = "### H-01: a\n### H-02: b\n"
LEDGER_4H_SHALLOW = _HDR + _4H + "## Loop State\n- **Depth-Lead:** H-01 — 3/5 (call->state->external)\n"
LEDGER_4H_DEEP = _HDR + _4H + \
    "## Loop State\n- **Depth-Lead:** H-01 — 5/5 (call->state->external->hook->accounting)\n"
LEDGER_2H_SHALLOW = _HDR + _2H + "## Loop State\n- **Depth-Lead:** H-01 — 2/5 (call->state)\n"
LEDGER_SUCCESS = _HDR + "### H-01: real bug\nHUNT-EXIT: T4-CONFIRMED High\n"


results = []


def check(name, cond, why):
    ok = bool(cond)
    print("  [%s] %-52s — %s" % ("PASS" if ok else "FAIL", name, why))
    results.append(ok)


print("AOE money-lead depth-gate — proof-of-firing (detector from the live hunt_completeness_gate.py)\n")

# (a) FIRES — value mapped + 4 H + strongest thread at 3/5 (<5)
set_corpus(2)
put_model(MODEL_MAPPED)
put_ledger(LEDGER_4H_SHALLOW)
r = call()
check("(a) FIRES: value mapped + 4H + depth 3/5", r != "MISSING" and r is True,
      "value is localized, pool is full, thread <5 -> depth order on the $-thread")

# (b1) SILENT — thread reached 5/5
put_ledger(LEDGER_4H_DEEP)
check("(b1) SILENT when strongest thread at 5/5", call() is False,
      "strongest $-thread at 5 layers -> gate is silent")

# (b2) SILENT — no value section
put_model(MODEL_NOSECTION)
put_ledger(LEDGER_4H_SHALLOW)
check("(b2) SILENT when no Value Concentration section", call() is False,
      "small/non-DeFi without value concentration -> money-lead not applicable")

# (b2') SILENT — placeholder only (untouched section)
put_model(MODEL_PLACEHOLDER)
put_ledger(LEDGER_4H_SHALLOW)
check("(b2') SILENT when value section = {placeholder} only", call() is False,
      "an unfilled `{узел 1}` section != mapped value")  # `{узел 1}` = "{node 1}" (template placeholder, kept)

# (b2'') SILENT — N/A sentinel
put_model(MODEL_NA)
put_ledger(LEDGER_4H_SHALLOW)
check("(b2'') SILENT on `N/A — <reason>` sentinel", call() is False,
      "N/A (small/non-DeFi) lifts the money-lead depth gate")

# (small pool) SILENT — value mapped, but <4 H (pool is small, too early to demand depth)
put_model(MODEL_MAPPED)
put_ledger(LEDGER_2H_SHALLOW)
check("(pool) SILENT when <4 hypotheses", call() is False,
      "pool is small (2 H) — the strongest thread may not be found yet (anti-FP, like wide_but_shallow)")

# (b3) success-exit short-circuits in main() BEFORE the detector -> High/Crit is NOT blocked
put_ledger(LEDGER_SUCCESS)
check("(b3) success-exit short-circuits before detector", gate.ledger_success_exit("sid") is True,
      "main() line `if ledger_success_exit(...)` returns BEFORE money-lead -> High/Crit is not blocked")

# (c) fail-open — no active ledger -> None
gate.freshest_active_ledger = lambda sid: (None, None)
check("(c1) fail-open: no active ledger -> None", call() is None,
      "no hunt -> the detector does not hold blindly")
# (c2) fail-open — freshest points to a nonexistent file -> open() raises -> None
gate.freshest_active_ledger = lambda sid: (os.path.join(work, "GHOST.md"), work)
check("(c2) fail-open: broken ledger path -> None", call() is None,
      "parse/read error NEVER holds the exit")

# (d) NOT corpus-gated — same FIRES at corpus 0 and -1 (the detector does not read the corpus at all)
put_model(MODEL_MAPPED)
put_ledger(LEDGER_4H_SHALLOW)
set_corpus(0)
check("(d1) NOT corpus-gated: fires with corpus=0", call() is True,
      "the depth gate fires immediately, independent of the false-refute corpus (unlike profile-cleared)")
set_corpus(-1)
check("(d2) NOT corpus-gated: fires with corpus=-1", call() is True,
      "a broken/missing manifest does NOT affect the depth gate")

# (+) SILENT on UNTOUCHED templates — a fresh hunt is not blocked, the detector is consistent with the template
set_corpus(2)
put_model(open(TPL_MODEL, encoding="utf-8").read())
put_ledger(open(TPL_LEDGER, encoding="utf-8").read())
check("(+) SILENT on pristine template model+ledger", call() is False,
      "the template's value section = `{узел 1}` placeholder + zero real H -> does not fire")

# (+) coupling: the REAL template heading `## Value Concentration` is recognized by _value_concentration_mapped
_tpl_model_txt = open(TPL_MODEL, encoding="utf-8").read()
_tpl_filled = _tpl_model_txt.replace(
    "| {узел 1} | {тип} | {reachable, не headline-TVL} | {permissionless? / роль} | {— / I-NN} |",  # must match the real template row (kept)
    "| StakingVault | TVL-pool | $2.1M reachable | permissionless deposit | I-03 |")
put_model(_tpl_filled)
put_ledger(LEDGER_4H_SHALLOW)
check("(+) coupling: fires on realistically-filled REAL template", call() is True,
      "the `## Value Concentration` heading from the live template -> if renamed, this case fails (drift guard)")

# (+) proof-of-firing: the detector + reason MUST exist and be wired into the hook
check("(+) detector + reason + helper wired into hook", all(hasattr(gate, n) for n in
      ("active_moneylead_shallow", "MONEYLEAD_REASON", "_value_concentration_mapped", "VALUE_SECTION_TITLE")),
      "remove the detector/reason -> the test fails (feedback_hook_must_prove_firing)")

shutil.rmtree(work, ignore_errors=True)
n_ok = sum(results)
print("\n%d/%d AOE money-lead gate cases green" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
