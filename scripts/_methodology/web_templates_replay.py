# -*- coding: utf-8 -*-
"""Replay: web-profile templates (system_model_web / hypotheses_web) are recognized by the existing
parsers of completeness-gate and model_first_nudge -- a web model ARMS the 12 model detectors, not N/A.

NOTE on kept Russian: the model/ledger table headers in the fixtures below (Invariants and Divergences column
names, the MODEL loop-state line, and axis-coverage prose) are parser input and are kept verbatim in Russian,
as are the two template-text literals compared against the real template files (the Russian "Resolution" column name
and the Russian "undup_origin multiplier" phrase). Each is marked "KEPT RU" where it occurs."""
import os, sys, importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT: break
    ROOT = nxt
HOOKS = os.path.join(ROOT, "scripts", "hooks")
METH = os.path.join(ROOT, "sessions", "_methodology")

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

gate = _load("hunt_completeness_gate", os.path.join(HOOKS, "hunt_completeness_gate.py"))
nudge = _load("model_first_nudge", os.path.join(HOOKS, "model_first_nudge.py"))

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

# 1) the web model template is CREATED (file deliverable).
model_tpl = os.path.join(METH, "system_model_web_template.md")
check("1 system_model_web_template.md created", os.path.exists(model_tpl))

# 2) The parser recognizes a FILLED web invariant (emulating agent work: TB-I01/AC-I01 with check+pred).
# KEPT RU: table header cells (Formula / Axis / Source / Status) are parser input.
web_model_filled = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| TB-I01 | origin===exact | how to validate origin | origin-trust | CSP | msgRouter | ENFORCED | ENFORCED-PARTIAL | b:1 | 0 | cold | pm |\n"
    "| AC-I01 | ownership | authz on the method? | object-authz | OpenAPI | orders | ENFORCED | ABSENT | /api/o/:id | 0 | cold | mw |\n"
)
check("2 nudge._model_has_real_invariant recognizes a filled TB-I01/AC-I01",
      nudge._model_has_real_invariant(web_model_filled))
check("2 gate._i_rows parses >=2 web invariants", len(gate._i_rows(web_model_filled)) >= 2,
      "got %d" % len(gate._i_rows(web_model_filled)))

# 3) CRITICAL: an EMPTY skeleton FROM THE FILE (the working row `| TB-I01 | | | ... |`) is NOT recognized as real.
if os.path.exists(model_tpl):
    tpl_text = open(model_tpl, encoding="utf-8").read()
    body = "\n".join(l for l in tpl_text.splitlines() if not l.lstrip().startswith(">"))
    check("3 an empty skeleton from the FILE → NOT a real invariant (a fresh template does not arm)",
          not nudge._model_has_real_invariant(body),
          "the template falsely looks built -- the working skeleton row must be EMPTY")
    check("3 the file carries the web invariant form TB-I01/AC-I01 (skeleton)",
          "tb-i01" in tpl_text.lower() or "ac-i01" in tpl_text.lower())

# 4) a web MODEL line (TB counter, not N/A) -> NOT _model_na (the model is armed).
# KEPT RU: the MODEL line below is parser input (Russian: "TB total / ABSENT / open D-NN").
check("4 web MODEL line (TB counter) → _model_na=False (does not disarm)",
      not gate._model_na("- **MODEL (WEB):** TB всего: 6 / ABSENT: 2 / открытых D-NN: 2"))

# 5) an explicit N/A still silences (a pure static site) -- the contract semantics are intact.
check("5 'MODEL: N/A — static site' → _model_na=True (N/A is legit)",
      gate._model_na("MODEL: N/A — static site"))

# 6) web-ledger template: the scout section is present, enforcement fields in place, the MODEL line gives no false N/A.
web_tpl = os.path.join(METH, "hypotheses_web_template.md")
check("6 hypotheses_web_template.md created", os.path.exists(web_tpl))
if os.path.exists(web_tpl):
    t = open(web_tpl, encoding="utf-8").read()
    low = t.lower()
    check("6 web-ledger carries ## Scout Fan-Out", "## scout fan-out" in low)
    check("6 web-ledger carries ## Loop State (loop state)", "loop state" in low)
    check("6 web-ledger carries ## Banked Findings", "banked findings" in low)
    check("6 web-ledger carries ## Verifier Log", "verifier log" in low)
    check("6 web-ledger carries BOUNDARY-MAP (§38 parity)", "boundary-map" in low)
    check("6 web-ledger carries OPT-TODO (§38 parity)", "opt-todo" in low)
    check("6 web-ledger carries WAVE-2 (§38 parity)", "wave-2" in low)
    check("6 web-ledger carries the web partitions P-SIGN and P-AUTHZ", "p-sign" in low and "p-authz" in low)
    check("6 web-ledger MODEL line does NOT give a false _model_na (in placeholder/backtick)",
          not gate._model_na(t))

# 7) active_model_axes_incomplete: the axis set is chosen by the namespace of the model's invariants (profile-aware).
web_axes = gate._axes_for_model("| TB-I01 | origin === exact | check | origin-trust | ...")
names = " ".join(n for n, _ in web_axes).lower()
check("7 _axes_for_model(TB-) → trust axes (origin/signature), NOT contract ones",
      "origin" in names and "signature" in names and "cross-function" not in names)
web2_axes = gate._axes_for_model("| AC-I01 | ownership | check | object-authz | ...")
names2 = " ".join(n for n, _ in web2_axes).lower()
check("7 _axes_for_model(AC-) → access axes (authz/tenant), NOT contract ones",
      "authz" in names2 and "tenant" in names2 and "temporal" not in names2)
contract_axes = gate._axes_for_model("| I-01 | supply==sum | check | state | ...")
names3 = " ".join(n for n, _ in contract_axes).lower()
check("7 _axes_for_model(I-) → contract axes (cross-function/economic) preserved",
      "cross-function" in names3 and "economic" in names3)

# 8) bullet namespace: a web model in BULLET form also yields the right namespace (agents drift into bullets).
check("8 _model_namespace bullet TB → 'TB'",
      gate._model_namespace("- **TB-I01** [origin-trust] check: x pred: ABSENT") == "TB")
check("8 _model_namespace bullet AC → 'AC'",
      gate._model_namespace("- **AC-I01** [object-authz] check: x pred: ABSENT") == "AC")
check("8 _axes_for_model bullet TB → trust axes (origin)",
      "origin" in " ".join(n for n,_ in gate._axes_for_model("- **TB-I01** origin-trust")).lower())

# 8) _NA_AXIS_RE counts a web N/A axis (not only a contract one).
check("8 _NA_AXIS_RE counts a web N/A axis (clone-parity: N/A)",
      bool(gate._NA_AXIS_RE.search("clone-parity: N/A — single deploy")))
check("8 _NA_AXIS_RE counts a contract N/A axis (temporal: N/A) — regression",
      bool(gate._NA_AXIS_RE.search("temporal: N/A — not applicable")))

# 9) NUDGE FIRE-PATH (§39 / feedback_hook_must_prove_firing): the model-first nudge MUST FIRE on a
#    fresh web ledger (Scout PENDING, web MODEL line not N/A), otherwise there is no model-first steering for web.
#    N/A (a pure static site) and Scout Status DONE silence it -- the contract semantics are intact.
#    Temp dir (we do not touch real sessions): _should_nudge(marker) reads hypotheses.md next to the marker.
import tempfile as _tf, shutil as _sh
_d = _tf.mkdtemp(prefix="webnudge_")
try:
    _marker = os.path.join(_d, ".hunt_active")
    open(_marker, "w", encoding="utf-8").write("0\nX")
    _lp = os.path.join(_d, "hypotheses.md")
    # KEPT RU: the MODEL line is parser input (Russian: "TB total / ABSENT / open D-NN").
    open(_lp, "w", encoding="utf-8").write(
        "## Loop State\n"
        "- **MODEL (T10/T13 — divergence-first, WEB-профиль):** TB всего: 2 / ABSENT: 1 / открытых D-NN: 1\n"
        "## Scout Fan-Out\n**Status:** `PENDING`\n")
    check("9 nudge._should_nudge FIRES on a fresh web ledger (Scout PENDING, web MODEL not N/A)",
          nudge._should_nudge(_marker),
          "the web MODEL line wrongly silences the nudge — the §39 model-first steering is lost")
    open(_lp, "w", encoding="utf-8").write(
        "## Loop State\n- MODEL: N/A — static site\n## Scout Fan-Out\n**Status:** `PENDING`\n")
    check("9 nudge._should_nudge SILENT on MODEL: N/A (a pure static site)",
          not nudge._should_nudge(_marker))
    # KEPT RU: the MODEL line is parser input (Russian: "TB total").
    open(_lp, "w", encoding="utf-8").write(
        "## Loop State\n- **MODEL (WEB):** TB всего: 6\n## Scout Fan-Out\n**Status:** `DONE 2026-08-05`\n")
    check("9 nudge._should_nudge SILENT on Scout Status DONE (the wave is done)",
          not nudge._should_nudge(_marker))
finally:
    _sh.rmtree(_d, ignore_errors=True)

# 10) active_clone_diff_skipped (Task 4, FDE profile-dapphunt-web3-frontend): the web P-CLONE partition is
#     active (Scout DONE), but the producer `clone_diff.md` (Task 3: asymmetry_scanner_dapp.py --md-out)
#     was not run -> the gate holds the turn. Contract namespace (deephunt) / P-CLONE N/A / producer already
#     run / Scout still PENDING -> silent (schema-independence + escape hatches, brief §Logic).
#     Isolation: monkeypatch gate.freshest_active_ledger (the same trick as scout_gates_replay.py for the
#     sibling detectors boundary_scout/wave_pending) -> NEVER touches the real sessions/.
import uuid as _uuid

# KEPT RU: table header cells (Formula / Axis / Source / Status) are parser input.
_TB_MODEL_CD = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| TB-I01 | origin===exact | how to validate origin | origin-trust | CSP | msgRouter | ENFORCED | "
    "ENFORCED-PARTIAL | b:1 | 0 | cold | pm |\n"
)
_I_MODEL_CD = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| I-01 | supply==sum | how to validate supply | state | code | Vault | ENFORCED | ENFORCED | f:1 | 0 | "
    "cold | pm |\n"
)

if os.path.exists(web_tpl):
    _web_tpl_raw = open(web_tpl, encoding="utf-8").read()
    _orig_freshest = gate.freshest_active_ledger
    _cd_dirs = []

    def _mk_clone_case(status_done, pclone_na, model_text, make_clone_diff):
        """Temp session dir (NOT the real sessions/) built from the real hypotheses_web_template.md."""
        d = _tf.mkdtemp(prefix="clonediff_")
        _cd_dirs.append(d)
        txt = _web_tpl_raw
        if status_done:
            txt = txt.replace("**Status:** `PENDING`", "**Status:** `DONE 2026-08-05`", 1)
        if pclone_na:
            txt = txt.replace("| P-CLONE / P-LOGIC | | | | |",
                               "| P-CLONE / P-LOGIC | N/A — single deploy | | | |", 1)
        open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8").write(txt)
        if model_text is not None:
            open(os.path.join(d, "system_model.md"), "w", encoding="utf-8").write(model_text)
        if make_clone_diff:
            open(os.path.join(d, "clone_diff.md"), "w", encoding="utf-8").write(
                "RESULT: N/A — single deploy\n")
        return os.path.join(d, "hypotheses.md"), d

    try:
        _sid = "clonediff-test-" + _uuid.uuid4().hex[:8]

        p1, d1 = _mk_clone_case(True, False, _TB_MODEL_CD, False)
        gate.freshest_active_ledger = lambda sid, _p=p1, _d=d1: (_p, _d)
        check("10 active_clone_diff_skipped FIRES (web DONE + P-CLONE active + no clone_diff.md)",
              gate.active_clone_diff_skipped(_sid))

        p2, d2 = _mk_clone_case(True, False, _TB_MODEL_CD, True)
        gate.freshest_active_ledger = lambda sid, _p=p2, _d=d2: (_p, _d)
        check("10 NEGATIVE-1 SILENT (clone_diff.md already run)",
              not gate.active_clone_diff_skipped(_sid))

        p3, d3 = _mk_clone_case(True, True, _TB_MODEL_CD, False)
        gate.freshest_active_ledger = lambda sid, _p=p3, _d=d3: (_p, _d)
        check("10 NEGATIVE-2 SILENT (P-CLONE marked N/A — single deploy)",
              not gate.active_clone_diff_skipped(_sid))

        p4, d4 = _mk_clone_case(True, False, _I_MODEL_CD, False)
        gate.freshest_active_ledger = lambda sid, _p=p4, _d=d4: (_p, _d)
        check("10 NEGATIVE-3 SILENT (contract-namespace I-NN, deephunt not affected)",
              not gate.active_clone_diff_skipped(_sid))

        p5, d5 = _mk_clone_case(False, False, _TB_MODEL_CD, False)
        gate.freshest_active_ledger = lambda sid, _p=p5, _d=d5: (_p, _d)
        check("10 NEGATIVE-4 SILENT (Scout Fan-Out Status still PENDING, the template default)",
              not gate.active_clone_diff_skipped(_sid))
    finally:
        gate.freshest_active_ledger = _orig_freshest
        for _d in _cd_dirs:
            _sh.rmtree(_d, ignore_errors=True)

# 11) AC gate-parity FIRING regress (Task 6, business-logic axis): active_model_axes_incomplete
#     blocks a MATURE AC-model (>=3 non-placeholder AC-I invariants, no open D-NN) when 2 of the
#     6 web2 axes (system_model_web_template.md:169-177) are un-covered in prose, and passes once
#     all 6 are seeded. Proves the web2 axis-seed mechanism (incl. the new business-logic axis
#     text this task added to `## Business Logic`) is actually gated, mirroring the TB-/I- cases
#     in section 7 above but through the REAL blocking path (active_model_axes_incomplete), not
#     just _axes_for_model() name selection. Gate code itself is untouched (namespace-agnostic).
# KEPT RU: table header cells (Formula / Axis / Source / Status) are parser input.
_AC_I_ROWS = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| AC-I01 | ownership(caller,O) on every method | authz-mw on EVERY method? | object-authz | OpenAPI | orders | ENFORCED | ENFORCED | /api/orders/:id | 0 | cold | authz-mw |\n"
    "| AC-I02 | admin functions check the role | role-check on privileged? | function-authz | OpenAPI | admin | ENFORCED | ENFORCED | /api/admin/users | 0 | cold | rbac |\n"
    "| AC-I03 | session cannot be forged | JWT signature enforced? | auth-integrity | OpenAPI | session | ENFORCED | ENFORCED | /api/login | 0 | cold | jwt-mw |\n"
)
# 4 of 6 axes are covered in prose (object-authz/function-authz/auth-integrity/tenant-isolation) -- no
# input-sink and business-logic words -> missing==2 -> the gate MUST hold the exit.
# KEPT RU: the axis-coverage prose lines below ("Ось <axis> покрыта: ..." = "Axis <axis> covered: ...") are
# parser input for the prose axis-coverage detector and are kept verbatim.
_AC_MODEL_4AXES = _AC_I_ROWS + (
    "\nОсь object-authz покрыта: ownership проверяется на каждом эндпоинте.\n"
    "Ось function-authz покрыта: role gate на admin-функциях.\n"
    "Ось auth-integrity покрыта: JWT signature validated on every session.\n"
    "Ось tenant-isolation покрыта: workspace scoping enforced per request.\n"
)
# the same + the 2 missing axes (incl. OUR new business-logic axis from `## Business Logic`) -> missing==0.
_AC_MODEL_6AXES = _AC_MODEL_4AXES + (
    "Ось input-sink покрыта: SQLi/SSTI payloads tested against every write endpoint.\n"
    "Ось business-logic покрыта: race condition probes run against one-shot redeem/checkout flows.\n"
)
# KEPT RU: the MODEL line is parser input (Russian: "AC total / ABSENT / open D-NN").
_AC_LEDGER = (
    "## Loop State\n- Iteration #: 4\n"
    "- **MODEL (WEB):** AC всего: 3 / ABSENT: 0 / открытых D-NN: 0\n"
)

_orig_freshest_ac = gate.freshest_active_ledger
_ac_dirs = []


def _mk_ac_case(model_text):
    d = _tf.mkdtemp(prefix="acaxes_")
    _ac_dirs.append(d)
    open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8").write(_AC_LEDGER)
    open(os.path.join(d, "system_model.md"), "w", encoding="utf-8").write(model_text)
    return os.path.join(d, "hypotheses.md"), d


try:
    _sid_ac = "acaxes-test-" + _uuid.uuid4().hex[:8]

    p6, d6 = _mk_ac_case(_AC_MODEL_4AXES)
    gate.freshest_active_ledger = lambda sid, _p=p6, _d=d6: (_p, _d)
    r4 = gate.active_model_axes_incomplete(_sid_ac)
    check("11 active_model_axes_incomplete FIRES on a mature AC-model with 2 axes missing",
          r4 is not None, "got %r — a 4/6-axis AC-model should block, not pass through" % (r4,))

    p7, d7 = _mk_ac_case(_AC_MODEL_6AXES)
    gate.freshest_active_ledger = lambda sid, _p=p7, _d=d7: (_p, _d)
    r6 = gate.active_model_axes_incomplete(_sid_ac)
    check("11 active_model_axes_incomplete SILENT once all 6 web2 axes seeded (incl. business-logic)",
          r6 is None, "got %r — a 6/6-axis AC-model should pass, not block" % (r6,))
finally:
    gate.freshest_active_ledger = _orig_freshest_ac
    for _d in _ac_dirs:
        _sh.rmtree(_d, ignore_errors=True)

# 12) FIX-ROUND-1 (Task 6 review CRITICAL): the `attack_path_hint` column MUST sit BEFORE the Resolution column
#     in `## Divergences`, not after. Three gate functions read the resolution cell POSITIONALLY
#     as `_cells(line)[-1]` (`_has_open_divergence`, `active_divergence_unresolved`,
#     `active_core_enforced_needs_t9`) -- if `attack_path_hint` were the trailing column, a RESOLVED
#     D-NN (`→ H-NN`) with a filled hint would read as `c[-1]` == hint text (not the resolution) ==
#     open forever. This proves the fixed column order (`... | Rank | attack_path_hint | Resolution |`)
#     keeps the Resolution column last, so a resolved row with BOTH cells filled is correctly read as CLOSED.
_D_ROW_RESOLVED_BOTH_FILLED = (
    "| D-01 | AC-I01 | api.py:42 | ENFORCED-PARTIAL | all-users | 3 | yes | 2 | cold | 12 | "
    "probe: replay POST twice concurrently on redeem | → H-02 |"
)
check("12 _has_open_divergence: resolved D-NN with BOTH attack_path_hint+Resolution filled -> CLOSED",
      gate._has_open_divergence(_D_ROW_RESOLVED_BOTH_FILLED) is False,
      "got True -- attack_path_hint column leaking into c[-1] would make a resolved row look open")

_orig_freshest_res = gate.freshest_active_ledger
_res_dirs = []
try:
    _sid_res = "divresolved-test-" + _uuid.uuid4().hex[:8]
    # KEPT RU: table header cells (Formula / Axis / Source / Status; Inv / Where / Status / Rank / Resolution)
    # and the MODEL line are parser input.
    _model_resolved = (
        "## Invariants\n"
        "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| AC-I01 | ownership(caller,O) | authz-mw on EVERY method? | object-authz | OpenAPI | orders | ENFORCED | ENFORCED-PARTIAL | /api/redeem | 0 | cold | authz-mw |\n"
        "## Divergences\n"
        "| ID | Инв | Где | Статус | vw | pc | t0 | conv | heat | Ранг | attack_path_hint | Резолюция |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        + _D_ROW_RESOLVED_BOTH_FILLED + "\n"
    )
    _rd = _tf.mkdtemp(prefix="divresolved_")
    _res_dirs.append(_rd)
    open(os.path.join(_rd, "hypotheses.md"), "w", encoding="utf-8").write(
        "## Loop State\n- **MODEL (WEB):** AC всего: 1 / ABSENT: 0 / открытых D-NN: 0\n")
    open(os.path.join(_rd, "system_model.md"), "w", encoding="utf-8").write(_model_resolved)
    gate.freshest_active_ledger = lambda sid, _p=os.path.join(_rd, "hypotheses.md"), _d=_rd: (_p, _d)
    r_res = gate.active_divergence_unresolved(_sid_res)
    check("12 active_divergence_unresolved SILENT on resolved D-NN with hint+resolution both filled",
          r_res is None, "got %r -- resolved row misread as open (attack_path_hint/Resolution swapped?)" % (r_res,))
finally:
    gate.freshest_active_ledger = _orig_freshest_res
    for _d in _res_dirs:
        _sh.rmtree(_d, ignore_errors=True)

# 12b) TRIPWIRE (fix round 2): section 12 above proved the GATE CODE reads a hand-built row
# correctly -- it does NOT prove the TEMPLATE FILE itself still has the safe column order. The
# original Critical was a bug IN THE TEMPLATE (attack_path_hint placed after the Resolution column), not in
# gate code (gate code was never touched). Read the REAL `## Divergences` header straight out of
# `system_model_web_template.md` on disk and assert its column order -- this is the only check
# that would catch someone re-swapping the two columns in the .md file directly.
_web_tpl_text = open(model_tpl, encoding="utf-8").read() if os.path.exists(model_tpl) else ""
_div_start = _web_tpl_text.find("## Divergences")
_div_block = _web_tpl_text[_div_start:] if _div_start >= 0 else ""
_div_header_line = next((l for l in _div_block.splitlines() if l.strip().startswith("| ID |")), "")
_div_cells = gate._cells(_div_header_line) if _div_header_line else []
check("12b TRIPWIRE: real ## Divergences header found in system_model_web_template.md on disk",
      bool(_div_header_line), "no '| ID |' header line found under ## Divergences -- section renamed/removed?")
# KEPT RU: "резолюция" is the lowercased Russian "Resolution" column name in the real template header.
check("12b TRIPWIRE: last column of the REAL template's Divergences header is Resolution",
      bool(_div_cells) and "резолюция" in _div_cells[-1].lower(),
      "got last cell=%r -- column order regressed IN THE TEMPLATE ITSELF (the exact Critical class "
      "from round 1); mentally verify: swap the two columns back and this check must fail" % (
          _div_cells[-1] if _div_cells else None,))
check("12b TRIPWIRE: attack_path_hint is its OWN column, NOT the trailing one",
      bool(_div_cells) and any(c.strip() == "attack_path_hint" for c in _div_cells[:-1]),
      "attack_path_hint missing from the header, or landed in the last cell: %r" % (_div_cells,))

# 12c) fix round 2: cover the THIRD `c[-1]`-reading function (active_core_enforced_needs_t9) --
# round 1's section 12 only covered _has_open_divergence + active_divergence_unresolved. Build a
# model with ALL I-NN strictly ENFORCED (not PARTIAL) + the SAME resolved D-NN row (hint filled in
# the second-to-last cell) + a ledger with zero live Active H-NN -> every precondition for T9-force
# is met, so the function MUST fire (return non-None). If attack_path_hint leaked into c[-1]
# instead of the Resolution cell, `_DIV_RESOLVED_RE` would not match it, the loop would `return None` early,
# and T9 would be silently NEVER forced -- exactly the regression class this guards against.
# KEPT RU: table header cells are parser input.
_AC_I_ALL_ENFORCED = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| AC-I01 | ownership(caller,O) | authz-mw on EVERY method? | object-authz | OpenAPI | orders | ENFORCED | ENFORCED | /api/orders/:id | 0 | cold | authz-mw |\n"
    "| AC-I02 | admin functions check the role | role-check on privileged? | function-authz | OpenAPI | admin | ENFORCED | ENFORCED | /api/admin/users | 0 | cold | rbac |\n"
    "| AC-I03 | session cannot be forged | JWT signature enforced? | auth-integrity | OpenAPI | session | ENFORCED | ENFORCED | /api/login | 0 | cold | jwt-mw |\n"
    "## Divergences\n"
    "| ID | Инв | Где | Статус | vw | pc | t0 | conv | heat | Ранг | attack_path_hint | Резолюция |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    + _D_ROW_RESOLVED_BOTH_FILLED + "\n"
)
# KEPT RU: the MODEL line is parser input.
_ledger_core_t9 = "## Loop State\n- **MODEL (WEB):** AC всего: 3 / ABSENT: 0 / открытых D-NN: 0\n"

_orig_freshest_t9 = gate.freshest_active_ledger
_t9_dirs = []
try:
    _sid_t9 = "coret9-test-" + _uuid.uuid4().hex[:8]
    _t9d = _tf.mkdtemp(prefix="coret9_")
    _t9_dirs.append(_t9d)
    open(os.path.join(_t9d, "hypotheses.md"), "w", encoding="utf-8").write(_ledger_core_t9)
    open(os.path.join(_t9d, "system_model.md"), "w", encoding="utf-8").write(_AC_I_ALL_ENFORCED)
    gate.freshest_active_ledger = lambda sid, _p=os.path.join(_t9d, "hypotheses.md"), _d=_t9d: (_p, _d)
    r_t9 = gate.active_core_enforced_needs_t9(_sid_t9)
    check("12c active_core_enforced_needs_t9 FIRES correctly (all-ENFORCED + resolved D-NN with "
          "hint in second-to-last cell + 0 live H-NN) -- hint does NOT falsely mask c[-1]",
          r_t9 is not None,
          "got None -- attack_path_hint likely misread as c[-1], masking the resolved D-NN as "
          "unresolved and silently blocking the T9-force")
finally:
    gate.freshest_active_ledger = _orig_freshest_t9
    for _d in _t9_dirs:
        _sh.rmtree(_d, ignore_errors=True)

# 13) active_authz_matrix_skipped (Task 9, FDE profile-web2-hunt): the web2 P-AUTHZ partition is active
#     (Scout DONE), but the producer `authz_matrix.md` (Task 3: authz_diff.py run_authz_matrix) was not
#     run -> the gate holds the turn. dapphunt namespace (TB) / contract namespace (I-NN) / P-AUTHZ
#     N/A|deferred / producer already run / Scout still PENDING -> silent. Symmetric to section 10
#     (active_clone_diff_skipped): monkeypatch gate.freshest_active_ledger -> temp session dir,
#     built from the REAL hypotheses_web_template.md via .replace() -> NEVER touches the real
#     sessions/. NEGATIVE-6 proves namespace isolation IN BOTH DIRECTIONS: the old
#     active_clone_diff_skipped (TB detector) is silent on THIS AC fixture.
# KEPT RU: table header cells are parser input.
_AC_MODEL_AM = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| AC-I01 | ownership(caller,O) | authz-mw on EVERY method? | object-authz | OpenAPI | orders | "
    "ENFORCED | ENFORCED-PARTIAL | /api/orders/:id | 0 | cold | authz-mw |\n"
)

if os.path.exists(web_tpl):
    _orig_freshest_am = gate.freshest_active_ledger
    _am_dirs = []

    def _mk_authz_case(status_done, pauthz_mark, model_text, make_authz_matrix):
        """Temp session dir (NOT the real sessions/) built from the real hypotheses_web_template.md.
        pauthz_mark: None (active, not N/A/deferred) | 'n/a' | 'deferred'."""
        d = _tf.mkdtemp(prefix="authzmatrix_")
        _am_dirs.append(d)
        txt = _web_tpl_raw
        if status_done:
            txt = txt.replace("**Status:** `PENDING`", "**Status:** `DONE 2026-08-06`", 1)
        if pauthz_mark == "n/a":
            txt = txt.replace("| P-SIGN / P-AUTHZ | | | | |",
                               "| P-SIGN / P-AUTHZ | N/A | | | |", 1)
        elif pauthz_mark == "deferred":
            txt = txt.replace("| P-SIGN / P-AUTHZ | | | | |",
                               "| P-SIGN / P-AUTHZ | deferred | | | |", 1)
        open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8").write(txt)
        if model_text is not None:
            open(os.path.join(d, "system_model.md"), "w", encoding="utf-8").write(model_text)
        if make_authz_matrix:
            open(os.path.join(d, "authz_matrix.md"), "w", encoding="utf-8").write(
                "MODE: single+unauth\nRESULT: matrix-run, 0 divergences\n")
        return os.path.join(d, "hypotheses.md"), d

    try:
        _sid_am = "authzmatrix-test-" + _uuid.uuid4().hex[:8]

        pa1, da1 = _mk_authz_case(True, None, _AC_MODEL_AM, False)
        gate.freshest_active_ledger = lambda sid, _p=pa1, _d=da1: (_p, _d)
        check("13 active_authz_matrix_skipped FIRES (web2 DONE + P-AUTHZ active + no authz_matrix.md)",
              gate.active_authz_matrix_skipped(_sid_am))

        pa2, da2 = _mk_authz_case(True, None, _AC_MODEL_AM, True)
        gate.freshest_active_ledger = lambda sid, _p=pa2, _d=da2: (_p, _d)
        check("13 NEGATIVE-1 SILENT (authz_matrix.md already run, incl. single+unauth/0 divergences)",
              not gate.active_authz_matrix_skipped(_sid_am))

        pa3, da3 = _mk_authz_case(True, "n/a", _AC_MODEL_AM, False)
        gate.freshest_active_ledger = lambda sid, _p=pa3, _d=da3: (_p, _d)
        check("13 NEGATIVE-2a SILENT (P-AUTHZ marked N/A)",
              not gate.active_authz_matrix_skipped(_sid_am))

        pa3b, da3b = _mk_authz_case(True, "deferred", _AC_MODEL_AM, False)
        gate.freshest_active_ledger = lambda sid, _p=pa3b, _d=da3b: (_p, _d)
        check("13 NEGATIVE-2b SILENT (P-AUTHZ marked deferred)",
              not gate.active_authz_matrix_skipped(_sid_am))

        pa4, da4 = _mk_authz_case(True, None, _TB_MODEL_CD, False)
        gate.freshest_active_ledger = lambda sid, _p=pa4, _d=da4: (_p, _d)
        check("13 NEGATIVE-3 SILENT (TB-namespace dapphunt, P-SIGN active, web3 not affected)",
              not gate.active_authz_matrix_skipped(_sid_am))

        pa5, da5 = _mk_authz_case(True, None, _I_MODEL_CD, False)
        gate.freshest_active_ledger = lambda sid, _p=pa5, _d=da5: (_p, _d)
        check("13 NEGATIVE-4 SILENT (contract-namespace I-NN, deephunt not affected)",
              not gate.active_authz_matrix_skipped(_sid_am))

        pa6, da6 = _mk_authz_case(False, None, _AC_MODEL_AM, False)
        gate.freshest_active_ledger = lambda sid, _p=pa6, _d=da6: (_p, _d)
        check("13 NEGATIVE-5 SILENT (Scout Fan-Out Status still PENDING, the template default)",
              not gate.active_authz_matrix_skipped(_sid_am))

        pa7, da7 = _mk_authz_case(True, None, _AC_MODEL_AM, False)
        gate.freshest_active_ledger = lambda sid, _p=pa7, _d=da7: (_p, _d)
        check("13 NEGATIVE-6 namespace-parity SILENT (the old active_clone_diff_skipped is silent on an AC ledger)",
              not gate.active_clone_diff_skipped(_sid_am))
    finally:
        gate.freshest_active_ledger = _orig_freshest_am
        for _d in _am_dirs:
            _sh.rmtree(_d, ignore_errors=True)

# 14) Task 1 (FDE Plan 6, §50.1/§51): `## Un-Dup Sweep` + `## Human-Gated Surface` are present in
#     BOTH templates (web + contract), the profile seed is correct (web: 15 applicable `{TODO}`, no
#     profile N/A at all; contract: 8 applicable `{TODO}` + 7 `N/A — web-only`).
#     interrupted-path -- applicable for contract (Task 12, §51 matrix: deephunt ✅ "= Missing
#     Negatives (already)", deephunt is the primary source, the same status pattern as quantity-edge -- not N/A).
_CONTRACT_TPL = os.path.join(METH, "hypotheses_template.md")
_UNDUP_GENERATORS = [
    "composition", "commodity-subtraction", "model-vs-docs-runtime", "ui-forbidden",
    "semantic-field-diff", "legacy-alive", "assumption-mining", "negative-space",
    "third-party-seam", "interrupted-path", "cross-process", "client-trust",
    "multi-identity", "quantity-edge", "econ-abuse",
]
_CONTRACT_NA_WEB_ONLY = [
    "model-vs-docs-runtime", "ui-forbidden", "semantic-field-diff",
    "cross-process", "client-trust", "multi-identity", "econ-abuse",
]

if os.path.exists(web_tpl):
    check("14 web-ledger carries ## Un-Dup Sweep", "## un-dup sweep" in low)
    check("14 web-ledger carries ## Human-Gated Surface", "## human-gated surface" in low)
    check("14 web-ledger carries target_uniqueness (§56.1)", "target_uniqueness" in low)
    check("14 web-ledger carries models_run (§55.1)", "models_run" in low)
    check("14 web-ledger [HUMAN-PENDING] status in Human-Gated Surface", "[human-pending]" in low)
    _web_undup_rows = gate._undup_sweep_incomplete_rows(t)
    check("14 web-seed: ALL 15 generators applicable ({TODO}, no profile N/A)",
          len(_web_undup_rows) == 15, "got %d, want 15" % len(_web_undup_rows))
    for _g in _UNDUP_GENERATORS:
        check("14 web-seed carries the generator '%s'" % _g, _g in low)

if os.path.exists(_CONTRACT_TPL):
    _contract_tpl_text = open(_CONTRACT_TPL, encoding="utf-8").read()
    _contract_low = _contract_tpl_text.lower()
    check("14 contract-ledger carries ## Un-Dup Sweep", "## un-dup sweep" in _contract_low)
    check("14 contract-ledger carries ## Human-Gated Surface", "## human-gated surface" in _contract_low)
    _contract_undup_rows = gate._undup_sweep_incomplete_rows(_contract_tpl_text)
    check("14 contract-seed: EXACTLY 8 applicable generators ({TODO})",
          len(_contract_undup_rows) == 8, "got %d, want 8 — %r" % (len(_contract_undup_rows), _contract_undup_rows))
    for _g in _UNDUP_GENERATORS:
        check("14 contract-seed carries the generator '%s'" % _g, _g in _contract_low)
    for _g in _CONTRACT_NA_WEB_ONLY:
        _i = _contract_low.find(_g)
        _line = _contract_tpl_text.splitlines()[_contract_tpl_text[:_i].count("\n")] if _i >= 0 else ""
        check("14 contract-seed '%s' marked N/A — web-only (not {TODO})" % _g,
              "n/a" in _line.lower() and "web-only" in _line.lower(), _line)

# 15) Task 3 (FDE Plan 6, §48.2/§44/§50.3): the `undup_origin` column is present in the D-NN table of BOTH
#     templates (BEFORE the Resolution column, which stays the last cell), + the prose rank formula carries the
#     undup_origin multiplier. Namespace-agnostic: the same form for web/contract.
#     NOTE: `_CONTRACT_TPL` (section 14, above) is `hypotheses_template.md` (LEDGER, ## Un-Dup Sweep),
#     NOT `system_model_template.md` (MODEL, ## Divergences) -- D-NN lives ONLY in the model template,
#     contract_model_tpl below is a separate variable, we do not reuse the ledger path by name.
contract_model_tpl = os.path.join(METH, "system_model_template.md")


def _dnn_header_and_sep(tpl_text):
    """(header, separator) physical lines of the `## Divergences` table -- anchored AT THE START OF A LINE
    (`l.strip().startswith("## Divergences")`), NOT a substring search over the whole text: the `## Business
    Logic` section higher up in the file MENTIONS `` `## Divergences` `` in prose (a backtick reference), and
    `text.find("## Divergences")` catches THAT earlier substring first -- shifts the block to the BL-NN
    table, whose separator (`|---|---|---|---|---|---|`, 6 columns) falsely matches before the
    real D-NN separator (13/12 columns). Returns (None, None) if the section is not found."""
    lines = tpl_text.splitlines()
    idx = next((k for k, l in enumerate(lines) if l.strip().startswith("## Divergences")), None)
    if idx is None:
        return None, None
    k = idx + 1
    while k < len(lines) and not lines[k].strip().startswith("|"):
        k += 1
    if k + 1 >= len(lines):
        return None, None
    return lines[k], lines[k + 1]


if os.path.exists(model_tpl):
    _div_hdr_web, _div_sep_web = _dnn_header_and_sep(_web_tpl_text)
    _cells_web = gate._cells(_div_hdr_web) if _div_hdr_web else []
    check("15 web template: the D-NN header carries an 'undup_origin' column",
          any(c.strip() == "undup_origin" for c in _cells_web), "cells=%r" % (_cells_web,))
    check("15 web template: 'undup_origin' is the SECOND-TO-LAST cell (right before Resolution)",
          len(_cells_web) >= 2 and _cells_web[-2].strip() == "undup_origin",
          "cells=%r" % (_cells_web,))
    # KEPT RU: "резолюция" is the lowercased Russian "Resolution" column name in the real template header.
    check("15 web template: Resolution is still the LAST cell after inserting undup_origin",
          bool(_cells_web) and "резолюция" in _cells_web[-1].lower(),
          "cells=%r" % (_cells_web,))
    # the `|---|` separator carries EXACTLY as many columns as the header (otherwise the markdown table
    # renders crooked -- a cheap sanity check that we updated BOTH the header AND the separator).
    check("15 web template: the D-NN table separator carries the same number of columns as the header",
          bool(_div_sep_web) and len(gate._cells(_div_sep_web)) == len(_cells_web),
          "hdr=%d sep=%d" % (len(_cells_web), len(gate._cells(_div_sep_web)) if _div_sep_web else -1))
    # KEPT RU: "undup_origin-множитель" ("undup_origin multiplier") is compared against the real template text.
    check("15 web template: the rank-formula prose carries the undup_origin multiplier",
          "undup_origin-множитель" in _web_tpl_text, "the formula does not mention the undup_origin multiplier")

if os.path.exists(contract_model_tpl):
    _contract_model_text = open(contract_model_tpl, encoding="utf-8").read()
    _div_hdr_c, _div_sep_c = _dnn_header_and_sep(_contract_model_text)
    _cells_c = gate._cells(_div_hdr_c) if _div_hdr_c else []
    check("15 contract template: the D-NN header carries an 'undup_origin' column",
          any(c.strip() == "undup_origin" for c in _cells_c), "cells=%r" % (_cells_c,))
    check("15 contract template: 'undup_origin' is the SECOND-TO-LAST cell (right before Resolution)",
          len(_cells_c) >= 2 and _cells_c[-2].strip() == "undup_origin", "cells=%r" % (_cells_c,))
    # KEPT RU: "резолюция" is the lowercased Russian "Resolution" column name in the real template header.
    check("15 contract template: Resolution is still the LAST cell after inserting undup_origin",
          bool(_cells_c) and "резолюция" in _cells_c[-1].lower(), "cells=%r" % (_cells_c,))
    check("15 contract template: the D-NN table separator carries the same number of columns as the header",
          bool(_div_sep_c) and len(gate._cells(_div_sep_c)) == len(_cells_c),
          "hdr=%d sep=%d" % (len(_cells_c), len(gate._cells(_div_sep_c)) if _div_sep_c else -1))
    # KEPT RU: "undup_origin-множитель" ("undup_origin multiplier") is compared against the real template text.
    check("15 contract template: the rank-formula prose carries the undup_origin multiplier",
          "undup_origin-множитель" in _contract_model_text)

    # 15b) integration: gate._undup_origin_missing_rows() recognizes a fresh skeleton template (no
    #      D-NN rows at all -- an empty table) as "nothing to check" (0 rows), not a false firing.
    check("15b contract template UNTOUCHED: gate._undup_origin_missing_rows == [] (no D-NN rows in the skeleton)",
          gate._undup_origin_missing_rows(_contract_model_text) == [])

if os.path.exists(model_tpl):
    check("15b web template UNTOUCHED: gate._undup_origin_missing_rows == [] (no D-NN rows in the skeleton)",
          gate._undup_origin_missing_rows(_web_tpl_text) == [])

print("=== WEB TEMPLATES REPLAY ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  — " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
