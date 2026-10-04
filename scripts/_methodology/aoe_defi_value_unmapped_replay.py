#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AOE money-lead durability-companion replay — PROVES the detector
`active_defi_value_unmapped` fires (operator 2026-08-06: "it fired on the words money/DeFi and didn't lose them").

The hole the detector closes: `active_moneylead_shallow` comes alive ONLY when the
`## Value Concentration` section is MAPPED. On a DeFi/money target with a FORGOTTEN value section, moneylead silently
sleeps -> the $-targeted discipline is lost in a new session. The companion forces writing out the value nodes.

System rule ([[feedback_hook_must_prove_firing]]): a replay MUST prove FIRING — fail if the
detector is removed. The detector is called from the LIVE hook (importlib, not a copy); remove the function/reason -> `call()`
returns "MISSING" -> firing cases FAIL -> exit 1. Run against a stripped copy:
    py -3 -X utf8 aoe_defi_value_unmapped_replay.py <path/to/stripped_hook.py>

What is proven:
  (a) FIRES: DeFi signal in the ledger + model built (>=1 grounded I-NN) + pool >=4 H + value NOT mapped;
  (b) SILENT: value already mapped (moneylead zone) / N/A sentinel / model NOT built (model-first
      rules) / web2 ledger without a money signal / pool is small;
  (c) fail-open: no active ledger / broken input -> None (NEVER holds blindly);
  (d) NOT corpus-gated: fires regardless of `_false_refute_corpus_count` (depth companion);
  (+) SILENT on the untouched templates system_model_template.md + hypotheses_template.md;
  (+) coupling drift guard: fires on the REAL model template with one grounded I-NN + a DeFi ledger ->
      if `## Value Concentration` / `## Invariants` are renamed, the case fails;
  (+) proof-of-firing: detector + reason + helpers are wired into the hook.

Run: py -3 -X utf8 scripts/_methodology/aoe_defi_value_unmapped_replay.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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
        return gate.active_defi_value_unmapped(sid)
    except AttributeError:
        return "MISSING"


# ── Model fixtures ─────────────────────────────────────────────────────────────────────────────────
# NOTE: Cyrillic table headers / placeholders below are kept as-is — they mirror the real template format the hook parses.
# grounded I-NN = a row with non-empty check(idx2) and pred(idx6); an empty one = "model not built".
_INV_GROUNDED = (
    "## Invariants — `I-NN`\n\n"
    "| ID | Формула | check: | Класс | Источник | component: | pred: | Статус | file:line | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| I-01 | supply==sum | verify total==sum(balances) | state | docs | Vault | ENFORCED | | | | cold | |\n"
)
_INV_EMPTY = (                             # template's empty I-01 -> grounded=0 -> model NOT built
    "## Invariants — `I-NN`\n\n"
    "| ID | Формула | check: | Класс | Источник | component: | pred: | Статус | file:line | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| I-01 | | | state | | | | | | | cold | |\n"
)
_VC_HDR = ("## Value Concentration — узлы концентрации value/authority\n\n"
           "| Узел | Тип | reachable-$ | Достижим кем | Нить |\n|---|---|---|---|---|\n")
_VC_PLACEHOLDER = _VC_HDR + "| {узел 1} | {тип} | {reachable} | {роль} | {— / I-NN} |\n"
_VC_MAPPED = _VC_HDR + "| StakingVault | TVL-pool | $2.1M reachable | permissionless deposit | I-01 |\n"
_VC_NA = _VC_HDR + "| N/A — web2 target, единой value-концентрации нет | | | | |\n"  # "no single value concentration" (kept: fixture)

MODEL_BUILT_UNMAPPED = "# system_model.md\n\n" + _INV_GROUNDED + "\n" + _VC_PLACEHOLDER   # firing model
MODEL_BUILT_MAPPED = "# system_model.md\n\n" + _INV_GROUNDED + "\n" + _VC_MAPPED
MODEL_BUILT_NA = "# system_model.md\n\n" + _INV_GROUNDED + "\n" + _VC_NA
MODEL_UNBUILT_UNMAPPED = "# system_model.md\n\n" + _INV_EMPTY + "\n" + _VC_PLACEHOLDER    # grounded=0

# ── Ledger fixtures ──────────────────────────────────────────────────────────────────────────────────
_HDR = "# T — Hypotheses Registry\n"
_DEFI_4H = ("### H-01: collateral rounding in liquidation\n### H-02: vault share inflation\n"
            "### H-03: oracle staleness window\n### H-04: borrow-rate manipulation\n")
_DEFI_2H = "### H-01: collateral rounding in liquidation\n### H-02: vault share inflation\n"
_WEB2_4H = ("### H-01: reflected XSS in search box\n### H-02: IDOR on user profile endpoint\n"
            "### H-03: open redirect via return_url\n### H-04: JWT alg-confusion bypass\n")
LEDGER_DEFI_4H = _HDR + _DEFI_4H + "## Loop State\n- **Depth-Lead:** H-01 — 3/5\n"
LEDGER_DEFI_2H = _HDR + _DEFI_2H + "## Loop State\n- **Depth-Lead:** H-01 — 2/5\n"
LEDGER_WEB2_4H = _HDR + _WEB2_4H + "## Loop State\n- **Depth-Lead:** H-01 — 3/5\n"
LEDGER_SUCCESS = _HDR + "### H-01: real bug\nHUNT-EXIT: T4-CONFIRMED High\n"

# cold-review 2026-08-06 fixtures
_TECH_4H = ("### H-01: Rust borrow checker bypass in async executor\n"
            "### H-02: increase swap space to avoid OOM in worker\n"
            "### H-03: memory reserves leak in connection generator\n"
            "### H-04: LTV analytics dashboard off-by-one\n")      # none of these words is in the new regex
_BRIDGE_4H = ("### H-01: relayer forges merkle proof to mint wrapped tokens\n"
              "### H-02: validator threshold bypass on withdrawal finalize\n"
              "### H-03: lock-and-mint replay across chain reorg\n"
              "### H-04: burn-and-claim double-spend via message relay\n")   # bridge/mint/burn/merkle/wrapped
LEDGER_TECH_4H = _HDR + _TECH_4H + "## Loop State\n- **Depth-Lead:** H-01 — 3/5\n"
LEDGER_BRIDGE_4H = _HDR + _BRIDGE_4H + "## Loop State\n- **Depth-Lead:** H-01 — 3/5\n"
LEDGER_DEFI_MODELNA = _HDR + _DEFI_4H + ("## Loop State\n- **MODEL:** N/A — small target, T10 skipped\n"
                                          "- **Depth-Lead:** H-01 — 3/5\n")
MODEL_BUILT_NA_PROSE = ("# system_model.md\n\n" + _INV_GROUNDED +
                        "\n## Value Concentration — узлы концентрации value/authority\n\n"
                        "N/A — governance-voting UI, no fund custody on this surface\n")


results = []


def check(name, cond, why):
    ok = bool(cond)
    print("  [%s] %-54s — %s" % ("PASS" if ok else "FAIL", name, why))
    results.append(ok)


print("AOE money-lead durability-companion — proof-of-firing (detector from the live hunt_completeness_gate.py)\n")

# (a) FIRES — DeFi ledger + model built + 4 H + value placeholder (forgotten)
set_corpus(2)
put_model(MODEL_BUILT_UNMAPPED)
put_ledger(LEDGER_DEFI_4H)
r = call()
check("(a) FIRES: DeFi + model built + 4H + value unmapped", r != "MISSING" and r is True,
      "money signal in the ledger, model exists, pool is full, value forgotten -> force writing out ## Value Concentration")

# (b1) SILENT — value already mapped -> the moneylead gate's zone, not the companion's
put_model(MODEL_BUILT_MAPPED)
put_ledger(LEDGER_DEFI_4H)
check("(b1) SILENT when value already mapped", call() is False,
      "value is mapped -> that is the moneylead depth-gate's job, the companion is silent")

# (b2) SILENT — deliberate N/A sentinel
put_model(MODEL_BUILT_NA)
put_ledger(LEDGER_DEFI_4H)
check("(b2) SILENT on `N/A — <reason>` sentinel", call() is False,
      "a deliberate N/A (not about a single value) lifts the companion")

# (b3) SILENT — model NOT built (grounded I-NN=0) -> model-first rules, we don't jump ahead
put_model(MODEL_UNBUILT_UNMAPPED)
put_ledger(LEDGER_DEFI_4H)
check("(b3) SILENT when model not built (0 grounded I-NN)", call() is False,
      "model is empty -> active_model_incomplete forces IT; the companion does not jump ahead of model-first")

# (b4) SILENT — web2 ledger without a money signal
put_model(MODEL_BUILT_UNMAPPED)
put_ledger(LEDGER_WEB2_4H)
check("(b4) SILENT on web2 ledger (no DeFi signal)", call() is False,
      "XSS/IDOR/redirect/JWT — no financial vocabulary -> money-lead not applicable, don't force value")

# (b4') SILENT — tech/infra vocabulary (cold-review #1): Rust borrow-checker / swap-space / reserves / LTV
put_model(MODEL_BUILT_UNMAPPED)
put_ledger(LEDGER_TECH_4H)
check("(b4') SILENT on tech/infra lexicon (regex not over-broad)", call() is False,
      "borrow checker / swap space / reserves / LTV-analytics — removed from the regex -> NOT a money signal (cold-review #1)")

# (a2) FIRES — bridge/cross-chain ledger (cold-review #3: a bridge is a first-class money target)
put_model(MODEL_BUILT_UNMAPPED)
put_ledger(LEDGER_BRIDGE_4H)
check("(a2) FIRES on bridge ledger (relayer/merkle/mint/wrapped)", call() is True,
      "a bridge is a money target: relayer/merkle/mint/wrapped-token in the regex -> the companion forces value (cold-review #3)")

# (b7) SILENT — a deliberate N/A as PROSE (not a table row) lifts the gate (cold-review #2: format drift)
put_model(MODEL_BUILT_NA_PROSE)
put_ledger(LEDGER_DEFI_4H)
check("(b7) SILENT on N/A declared as prose (not table-row)", call() is False,
      "N/A as prose under the section = a deliberate refusal -> _value_na_declared catches prose/bullet (cold-review #2)")

# (b8) SILENT — the MODEL: N/A off-switch mutes the companion, like the whole model family (cold-review #4)
put_model(MODEL_BUILT_UNMAPPED)
put_ledger(LEDGER_DEFI_MODELNA)
check("(b8) SILENT on `MODEL: N/A` off-switch", call() is False,
      "the agent deliberately dropped T10 (MODEL: N/A) -> the companion is silent, like model_incomplete/moneylead (cold-review #4)")

# (b5) SILENT — pool is small (<4 H)
put_model(MODEL_BUILT_UNMAPPED)
put_ledger(LEDGER_DEFI_2H)
check("(b5) SILENT when <4 hypotheses (pool small)", call() is False,
      "pool is small (2 H) — early phase; the strongest thread may not be found yet (anti-FP)")

# (b6) success-exit short-circuits in main() BEFORE the companion -> High/Crit is not blocked
put_ledger(LEDGER_SUCCESS)
check("(b6) success-exit short-circuits before companion", gate.ledger_success_exit("sid") is True,
      "main() `if ledger_success_exit(...)` returns BEFORE the depth cluster -> High/Crit is not blocked")

# (c) fail-open — no active ledger / broken path -> None
gate.freshest_active_ledger = lambda sid: (None, None)
check("(c1) fail-open: no active ledger -> None", call() is None,
      "no hunt -> the companion does not hold blindly")
gate.freshest_active_ledger = lambda sid: (os.path.join(work, "GHOST.md"), work)
check("(c2) fail-open: broken ledger path -> None", call() is None,
      "read error NEVER holds the exit")

# (d) NOT corpus-gated — same FIRES at corpus 0 and -1 (the companion does not read the corpus at all)
put_model(MODEL_BUILT_UNMAPPED)
put_ledger(LEDGER_DEFI_4H)
set_corpus(0)
check("(d1) NOT corpus-gated: fires with corpus=0", call() is True,
      "the depth companion fires immediately, independent of the false-refute corpus")
set_corpus(-1)
check("(d2) NOT corpus-gated: fires with corpus=-1", call() is True,
      "a broken/missing manifest does NOT affect the depth companion")

# (+) SILENT on UNTOUCHED templates — a fresh hunt is not blocked
set_corpus(2)
put_model(open(TPL_MODEL, encoding="utf-8").read())
put_ledger(open(TPL_LEDGER, encoding="utf-8").read())
check("(+) SILENT on pristine template model+ledger", call() is False,
      "template: I-01 is empty (grounded=0) + zero real H -> the companion is silent at start")

# (+) coupling drift guard: the REAL model template, make one I-01 grounded, Value stays a placeholder,
#     ledger DeFi 4H -> fires. If `## Value Concentration` / `## Invariants` are renamed or the I-row is broken ->
#     _value_concentration_mapped/_grounded_i_count change -> this case fails.
_tpl = open(TPL_MODEL, encoding="utf-8").read()
_tpl_grounded = _tpl.replace(
    "| I-01 | | | state | | | | | | | cold | |",
    "| I-01 | supply==sum | verify total==sum(balances) | state | docs | Vault | ENFORCED | | | | cold | |")
put_model(_tpl_grounded)
put_ledger(LEDGER_DEFI_4H)
check("(+) coupling: fires on REAL template (grounded I-NN + value placeholder)", call() is True,
      "live headings `## Invariants` + `## Value Concentration` -> rename drift is caught")

# (+) proof-of-firing: the detector + reason + helpers MUST exist and be wired into the hook
check("(+) detector + reason + helpers wired into hook", all(hasattr(gate, n) for n in
      ("active_defi_value_unmapped", "DEFI_VALUE_UNMAPPED_REASON", "_defi_signal",
       "_value_na_declared", "_value_concentration_mapped", "_grounded_i_count")),
      "remove the detector/reason/helper -> the test fails (feedback_hook_must_prove_firing)")

shutil.rmtree(work, ignore_errors=True)
n_ok = sum(results)
print("\n%d/%d AOE defi-value-unmapped companion cases green" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
