#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worklist Driver -- WEB WAVE (2026-08-11). Proves: the atom registry + all worklist gates + `next_atom`
are namespace-AGNOSTIC and work on a WEB ledger (dapphunt/hunt-web2) IDENTICALLY to the contract.

Context: before this wave the web template (`hypotheses_web_template.md`) did NOT carry an `## Atom Registry` section ->
for web hunts the driver was C1-silent (no registry -> all worklist gates silent). The web wave added the section
to the web template; the engine did not need to be touched (the section is found by the `## Atom Registry` header, all parsers
are namespace-agnostic). THIS test is the proof: on a ledger with web trimmings (MODEL `<TB|AC>`, web-depth,
web scout partitions) the behavior is the same.

It separately proves the decision on `_SRC_ID_RE` (NOT extended to `TB-`/`AC-`): an atom is sourced from `D-NN`
(the namespace is UNIVERSAL contract+web) -> the existence check works; `TB-NN`/`AC-NN` = an invariant in
`system_model.md` (analogue of `I-NN`) -> treated as a label, NOT existence-checked (otherwise FP on every legit
invariant-sourced atom -- an invariant is not written into the ledger).

Rule (feedback_hook_must_prove_firing): each case proves FIRING or a motivated silence.
Run: py -3 -X utf8 scripts/_methodology/worklist_web_replay.py

NOTE on kept Russian: a few fixture/assertion strings (the MODEL loop-state line, the model table header, and the
driver directive prefixes asserted in drive()) are parser input / compared against gate output and are kept
verbatim in Russian; each is marked with a comment at its line.
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

REG_HDR = "## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n|---|---|---|---|---|---|---|\n"


def reg(rows):
    body = "".join("| %s | %s | %s | %s | %s | %s | %s |\n" % r for r in rows)
    return REG_HDR + body + "\n"


def web_ledger(registry_block, pick="AX-04", it=7, raw=""):
    """WEB trimmings of the ledger: MODEL line `<TB|AC>` (not N/A -- a real dApp/web2), a web-depth hint,
    web scout partitions. Proves that the worklist gates are indifferent to the web content around the registry."""
    ls = ("# webtarget — Hypotheses Registry\n\n"
          "**Target:** app.example.com (dApp frontend + web2 API)\n\n"
          "## Loop State\n"
          "- **Iteration #:** " + str(it) + "\n"
          "- **Current pick:** " + pick + "\n"
          # KEPT RU: MODEL line is parser input (Russian: "TB total / ABSENT / open D-NN / current")
          "- **MODEL (T10/T13 — WEB-профиль):** TB всего: 6 / ABSENT: 1 / открытых D-NN: 2 / текущий: D-03\n"
          "- **Depth-Lead:** TB-authz-bypass — 3/5 (L1 request→L3 authz-middleware→L5 ORM)\n")
    return ls + "\n" + registry_block + raw + "\n## Active Hypotheses\n\n"


results = []
_LC = g.LOOP_CONTINUE_REASON


def fire(name, detector, ledger_txt, expect, flag=True, model=None):
    """expect True -> the detector MUST return truthy; False -> None/empty. Monkeypatches freshest_active_ledger.
    model -> writes `system_model.md` NEXT TO it (for the invariant-src existence check against the model, red-team MED)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    if model is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = flag
    try:
        res = getattr(g, detector)("sid")
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    got = bool(res)
    ok = (got == expect)
    print("  [%s] %s: %s=%s expect=%s" % ("PASS" if ok else "FAIL", name, detector, got, expect))
    results.append(ok)


# a real web model (invariant system) for the invariant-src differential check.
# KEPT RU: the table header cell "инвариант" ("invariant") and "Ось" ("Axis") is parser input.
_WEB_MODEL = (
    "# system_model — WEB\n\n"
    "| id | инвариант | check | Ось | ... |\n"
    "| TB-I01 | ∀ postMessage: event.origin === EXACT | origin? | origin-trust | ... |\n"
    "| TB-I03 | ∀ SIWE: nonce single-use | nonce? | session-auth | ... |\n"
    "| AC-I01 | ∀ endpoint: ownership(caller,O) | authz-mw? | object-authz | ... |\n"
    "| AC-I05 | ∀ tenant: row-level isolation | tenant-scope? | tenant | ... |\n"
)


def drive(name, ledger_txt, expect_kind, expect_head=None):
    """next_atom on a web ledger: DRIVE/HANDOFF/FALLBACK + an optional check of the named head."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        directive, _adv = g.next_atom("sid")
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    has_contract = _LC in directive
    if expect_kind == "DRIVE":
        # KEPT RU: compared against the gate's directive text (Russian: "WORKLIST-DRIVER (Stage 2): machine registry")
        kind_ok = directive.startswith("⚙ WORKLIST-DRIVER (Этап 2): машинный реестр") and has_contract
    elif expect_kind == "HANDOFF":
        # KEPT RU: compared against the gate's directive text (Russian: "the registry head changed")
        kind_ok = ("голова реестра сменилась" in directive) and has_contract
    elif expect_kind == "FALLBACK":
        kind_ok = (directive == _LC)
    else:
        kind_ok = False
    head_ok = (expect_head is None) or (("`%s`" % expect_head) in directive)
    ok = kind_ok and head_ok
    print("  [%s] %s: kind=%s head=%s" % ("PASS" if ok else "FAIL", name,
          "ok" if kind_ok else "WRONG(%r…)" % directive[:60], expect_head if head_ok else "MISS"))
    results.append(ok)


# ══════════════════════════════════════════════════════════════════════════════
print("── W1: worklist gates fire on a WEB ledger IDENTICALLY to the contract (namespace-agnosticism)")

# W1a: an empty registry (placeholder only) on web -> registry_unpopulated fires (as on the contract).
_TPL = "## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n|---|---|---|---|---|---|---|\n| {AX-01} | {axis} | {x} | {D-NN} | {n} | {OPEN} | {-} |\n\n"
# a real pick (actively working, iter=7>=3) + a placeholder-only registry -> unpopulated fires.
fire("W1a placeholder-only registry + real pick → unpopulated fire", "active_registry_unpopulated",
     web_ledger(_TPL, pick="AX-04"), True)

# W1b: a healthy web registry (D-03 grounded, 1 ACTIVE=pick) -> unpopulated silent.
fire("W1b healthy web registry → unpopulated silent", "active_registry_unpopulated",
     web_ledger(reg([("AX-04", "axis", "authz-bypass", "D-03", "35", "ACTIVE", "-")]), pick="AX-04",
                raw="## Divergences\n### D-03: authz not enforced on /api/admin — routes.ts:88\n"), False)

# W1c: pick outside the registry (a real-hunt case on web) -> pick_not_from_queue fires.
fire("W1c pick off-registry (web real-hunt) → pick_not_from_queue fire", "active_pick_not_from_queue",
     web_ledger(reg([("AX-04", "axis", "authz-bypass", "D-03", "35", "OPEN", "-")]),
                pick="i-will-break-jwt-myself"), True)

# W1d: >1 ACTIVE on web -> pick_not_from_queue fires (single-pick violated).
fire("W1d two ACTIVE (web) → pick_not_from_queue fire", "active_pick_not_from_queue",
     web_ledger(reg([("AX-04", "axis", "bola", "D-03", "35", "ACTIVE", "-"),
                     ("AX-05", "axis", "ssti", "D-04", "20", "ACTIVE", "-")]), pick="AX-04"), True)

# W1e: a CLOSED atom without a proof record on web -> atom_closed_without_narrative fires.
fire("W1e orphaned CLOSED (web) → atom_closed_without_narrative fire", "active_atom_closed_without_narrative",
     web_ledger(reg([("H-09", "hypothesis", "idor", "D-03", "27", "CLOSED", "-")]), pick="none"), True)

# W1f: CLOSED + proof `### H-09 [KILLED]` in ## Refuted -> silent.
fire("W1f CLOSED + proof in Refuted (web) → silent", "active_atom_closed_without_narrative",
     web_ledger(reg([("H-09", "hypothesis", "idor", "D-03", "27", "CLOSED", "-")]), pick="none",
                raw="## Refuted\n### H-09 [KILLED]: ownership check in place — handler.ts:140\n"), False)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── W2: src-grounding — TWO surfaces: D-NN vs LEDGER, TB-I/AC-I vs MODEL (red-team MED fix)")

# W2a: a web atom src=D-99 (not in the narrative) -> src_ungrounded fires (D-NN is universal, a bogus head).
fire("W2a src=D-99 (not in narrative, web) → src_ungrounded fire", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "authz-bypass", "D-99", "35", "OPEN", "-")]), pick="AX-04"), True)

# ── red-team MED counterexample: an invariant-src is checked AGAINST THE MODEL, not ignored as a label ──
# W2b: src=TB-I99 (an invariant that is NOT in the model) -> FIRE (a fabricated invariant head).
fire("W2b src=TB-I99 (nonexistent invariant, model present) → FIRE (red-team MED)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-05", "axis", "fabricated-authz-head", "TB-I99", "40", "ACTIVE", "-")]),
                pick="AX-05"), True, model=_WEB_MODEL)

# W2c: src=TB-I01 (the invariant is REALLY in the model) -> silent (grounded against the model).
fire("W2c src=TB-I01 (invariant in model) → silent (grounded vs model)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "origin-sweep", "TB-I01", "35", "OPEN", "-")]), pick="AX-04"),
     False, model=_WEB_MODEL)

# W2c2-4: AC-I differential + padding.
fire("W2c2 src=AC-I05 (in model) → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "tenant-sweep", "AC-I05", "35", "OPEN", "-")]), pick="AX-04"),
     False, model=_WEB_MODEL)
fire("W2c3 src=AC-I77 (nonexistent) → fire", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "AC-I77", "35", "ACTIVE", "-")]), pick="AX-04"),
     True, model=_WEB_MODEL)
fire("W2c4 src=TB-I1 padding <-> model TB-I01 → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "TB-I1", "35", "OPEN", "-")]), pick="AX-04"),
     False, model=_WEB_MODEL)

# W2c5: an invariant-src, but there is NO MODEL (file absent) -> silent (fail-safe label, nothing to check against).
fire("W2c5 src=TB-I99 but NO model → silent (fail-safe)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "TB-I99", "35", "OPEN", "-")]), pick="AX-04"), False)

# W2c6: MODEL: N/A + an invariant-src -> FIRE (self-contradiction: no model -> the invariant is fictitious; red-team#2 MED-1).
fire("W2c6 src=TB-I99 + MODEL:N/A → FIRE (MED-1)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "TB-I99", "35", "ACTIVE", "-")]), pick="AX-04",
                raw="- **MODEL:** N/A — static site\n"), True, model=_WEB_MODEL)

# W2d: a web atom src=D-03 + `### D-03` in the narrative -> silent (grounded in the LEDGER, as contract S2).
fire("W2d src=D-03 grounded in narrative → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "authz", "D-03", "35", "OPEN", "-")]), pick="AX-04",
                raw="## Divergences\n### D-03: authz gap — routes.ts:88\n"), False)

# W2e: a web atom src=H-77 (a hypothesis, not in the narrative) -> fire (H-NN is universal).
fire("W2e src=H-77 (not in narrative, web) → fire", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "authz", "H-77", "35", "ACTIVE", "-")]), pick="AX-04"), True)

# W2f/g: contract-side symmetry — I-NN is also checked against the model (the latent hole is closed symmetrically).
# KEPT RU: the table header cell "инвариант" ("invariant") is parser input.
_CONTRACT_MODEL = "# system_model\n\n| id | инвариант | ... |\n| I-01 | forall redeem: band enforced | ... |\n| I-03 | forall mint: supply cap | ... |\n"
fire("W2f contract src=I-99 (nonexistent) + model → fire (I-NN symmetry)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-99", "35", "ACTIVE", "-")]), pick="AX-04"),
     True, model=_CONTRACT_MODEL)
fire("W2g contract src=I-01 (in model) → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-01", "35", "OPEN", "-")]), pick="AX-04"),
     False, model=_CONTRACT_MODEL)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── W2H: pick_not_from_queue — uncovered clauses on web (auditor defect #1)")

# W2H-4: rank-gaming — an ACTIVE atom with rank>80 (the formula ceiling) on web -> fire (clause 4).
fire("W2H-4 rank>80 gaming (web) → pick_not_from_queue fire", "active_pick_not_from_queue",
     web_ledger(reg([("AX-04", "axis", "inflated", "D-03", "999", "ACTIVE", "-")]), pick="AX-04",
                raw="## Divergences\n### D-03: x — a.ts:1\n"), True)

# W2H-2b: exactly 1 ACTIVE, but pick references ANOTHER atom -> desync (clause 2b).
fire("W2H-2b 1 ACTIVE + pick->another atom (web) → fire", "active_pick_not_from_queue",
     web_ledger(reg([("AX-04", "axis", "band", "D-03", "35", "ACTIVE", "-"),
                     ("AX-05", "axis", "other", "D-04", "20", "OPEN", "-")]), pick="AX-05",
                raw="## Divergences\n### D-03: x\n### D-04: y\n"), True)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── W5: red-team #2 counterexamples — symmetric canonicalization + declaration-only + N/A-fire")

# models with namespaced invariants / prose / a skeleton.
_M_VAULT = "# model\n\n| id | inv | ... |\n| VAULT-I03 | reserve solvent | ... |\n"
_M_PROSE = "# model\n\nArchitecture: see Figure I-7 (flow diagram). No tabular invariants.\n"
_M_ORACLE = "# model\n\n| ORACLE-I01 | price fresh | ... |\n"
_M_SKELETON = "# model\n\n| TB-I01 | | | origin-trust | | | | | | | cold | |\n"   # empty description
_M_BLOCKQUOTE = "# model\n\n> Example: `| TB-I01 | origin exact | ... |` — how to fill this in.\n"
_M_BULLET = "# model\n\n- **AC-I05** [authz] check: tenant isolation on EVERY request\n"

# HIGH-1a: the model carries ONLY VAULT-I03; a fabricated src=I-03 -> FIRE (ns-preserving, bare I-3 does not ground).
fire("W5-H1a model=VAULT-I03 only, src=I-03 → FIRE (ns-drop closed)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-03", "35", "ACTIVE", "-")]), pick="AX-04"), True, model=_M_VAULT)
# HIGH-1b: an incidental `I-7` in the model's PROSE; src=I-07 -> FIRE (prose != declaration).
fire("W5-H1b model prose 'Figure I-7', src=I-07 → FIRE (prose≠decl)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-07", "35", "ACTIVE", "-")]), pick="AX-04"), True, model=_M_PROSE)
# HIGH-1c: src=VAULT-I03 + model VAULT-I03 -> silent (ns preserved on both sides).
fire("W5-H1c src=VAULT-I03 + model VAULT-I03 → silent (grounded)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "VAULT-I03", "35", "OPEN", "-")]), pick="AX-04"), False, model=_M_VAULT)

# MED-1b: NO model file (not N/A) + src=TB-I99 -> silent (build window; W2c6 covered N/A->FIRE).
fire("W5-M1b no model file (not N/A), src=TB-I99 → silent (build window)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "TB-I99", "35", "OPEN", "-")]), pick="AX-04"), False)

# MED-2a: src=VAULT-I99 (ns 5, not in the model) -> FIRE (no longer leaks into a label).
fire("W5-M2a src=VAULT-I99 (ns5, nonexistent) → FIRE (label-escape closed)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "VAULT-I99", "35", "ACTIVE", "-")]), pick="AX-04"), True, model=_M_VAULT)
# MED-2b: src=ORACLE-I01 (ns 6) + model ORACLE-I01 -> silent.
fire("W5-M2b src=ORACLE-I01 (ns6) + model → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "ORACLE-I01", "35", "OPEN", "-")]), pick="AX-04"), False, model=_M_ORACLE)

# LOW-1: D-I01 / H-I5 (malformed divergence-ns) -> silent (not an invariant, do not enter the invariant branch).
fire("W5-L1a src=D-I01 (malformed) → silent (not an invariant)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "D-I01", "35", "ACTIVE", "-")]), pick="AX-04"), False, model=_M_VAULT)
fire("W5-L1b src=H-I5 (malformed) → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "H-I5", "35", "ACTIVE", "-")]), pick="AX-04"), False, model=_M_VAULT)

# verifier#1: a skeleton row (empty description) and a blockquote example do NOT ground a fiction.
fire("W5-V1a skeleton row (empty description), src=TB-I01 → FIRE", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "TB-I01", "35", "ACTIVE", "-")]), pick="AX-04"), True, model=_M_SKELETON)
fire("W5-V1b blockquote example, src=TB-I01 → FIRE", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "TB-I01", "35", "ACTIVE", "-")]), pick="AX-04"), True, model=_M_BLOCKQUOTE)
# a bullet declaration of a REAL invariant -> silent.
fire("W5-V1c bullet decl AC-I05, src=AC-I05 → silent (grounded)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "AC-I05", "35", "OPEN", "-")]), pick="AX-04"), False, model=_M_BULLET)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── W6: red-team #3 — markdown-emphasis strip (MED-1) · stale N/A FP (MED-2) · bullet-strict (LOW-1)")

# MED-1: markdown emphasis on src no longer bypasses the gate (we strip `*`/`_` like sibling cells).
# `**D-99**` (bold, nonexistent divergence) -> FIRE (the divergence branch is not bypassed).
fire("W6-M1a src=**D-99** (bold, nonexistent) → FIRE (emphasis-bypass closed)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "**D-99**", "35", "ACTIVE", "-")]), pick="AX-04"), True)
# `**I-99**` (bold, nonexistent invariant) + model -> FIRE (the invariant branch is not bypassed).
fire("W6-M1b src=**I-99** (bold, nonexistent invariant) → FIRE", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "**I-99**", "35", "ACTIVE", "-")]), pick="AX-04"), True, model=_WEB_MODEL)
# `_H-77_` (italic, nonexistent hypothesis) -> FIRE (underscore is stripped too).
fire("W6-M1c src=_H-77_ (italic, nonexistent) → FIRE", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "_H-77_", "35", "ACTIVE", "-")]), pick="AX-04"), True)
# `**D-03**` (bold) + D-03 in the ledger -> silent (emphasis stripped correctly, grounding preserved).
fire("W6-M1d src=**D-03** (bold) + D-03 in ledger → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "**D-03**", "35", "OPEN", "-")]), pick="AX-04",
                raw="## Divergences\n### D-03: x — a.ts:1\n"), False)

# MED-2: stale `MODEL: N/A` (append-trace) + a REALLY built model with I-01 + src=I-01 -> silent (FP closed).
_M_I01 = "# model\n\n| id | inv | ... |\n| I-01 | forall x holds | ... |\n"
fire("W6-M2a stale N/A + model with I-01 + src=I-01 → silent (FP closed)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-01", "35", "OPEN", "-")]), pick="AX-04",
                raw="- **MODEL:** N/A — early undecided\n"), False, model=_M_I01)
# stale N/A + a model WITHOUT I-99 + src=I-99 -> FIRE (fabrication is still caught via membership).
fire("W6-M2b stale N/A + model without I-99 + src=I-99 → FIRE", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-99", "35", "ACTIVE", "-")]), pick="AX-04",
                raw="- **MODEL:** N/A — early\n"), True, model=_M_I01)

# LOW-1: a bullet declaration requires bold. A prose mention `- I-9 discussed` does NOT ground a fiction src=I-9.
_M_PROSE_BULLET = "# model\n\n- I-9 discussed in passing (not a declaration)\n- Important: I-7 was tricky\n"
fire("W6-L1a prose bullet '- I-9 discussed' + src=I-9 → FIRE (not a declaration)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-9", "35", "ACTIVE", "-")]), pick="AX-04"), True, model=_M_PROSE_BULLET)
# a bold declaration `- **I-05**` + src=I-05 -> silent (a real declaration).
_M_BOLD_BULLET = "# model\n\n- **I-05** [state] check: supply invariant\n"
fire("W6-L1b bold decl '- **I-05**' + src=I-05 → silent", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-05", "35", "OPEN", "-")]), pick="AX-04"), False, model=_M_BOLD_BULLET)
# red-team #4: a non-bold colon-def declaration (the real format of a real-world model `- I-13: ...`) -> silent (we do not drop legit).
_M_COLON_BULLET = "# model\n\n- I-13: LinearCreditDebtTracker single source of debt\n- I-14: OneToOneAggregator\n"
fire("W6-L1c real-world non-bold '- I-13: ...' + src=I-13 → silent (not FP)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-13", "35", "OPEN", "-")]), pick="AX-04"), False, model=_M_COLON_BULLET)
# ...but a prose mention `- I-9 discussed` (no `:`/bold) is NOT a declaration -> src=I-9 is a fiction -> FIRE (we hold LOW-1).
fire("W6-L1d prose '- I-9 discussed' (no colon) + src=I-9 → FIRE (LOW-1 held)", "active_atom_src_ungrounded",
     web_ledger(reg([("AX-04", "axis", "x", "I-9", "35", "ACTIVE", "-")]), pick="AX-04"), True,
     model="# model\n\n- I-9 discussed in passing (not a declaration)\n")


# ══════════════════════════════════════════════════════════════════════════════
print("\n── W3: next_atom actively dictates the head on a WEB ledger (DRIVE/HANDOFF/FALLBACK)")

# W3a: 1 ACTIVE web atom -> DRIVE, names the head AX-04.
drive("W3a healthy web ACTIVE → DRIVE names AX-04",
      web_ledger(reg([("AX-04", "axis", "authz-bypass", "D-03", "35", "ACTIVE", "-")]), pick="AX-04"),
      "DRIVE", expect_head="AX-04")

# W3b: 0 ACTIVE, the OPEN queue is non-empty -> HANDOFF (the real-hunt moment on web), names the max-rank head.
drive("W3b 0 ACTIVE web queue → HANDOFF names head",
      web_ledger(reg([("AX-04", "axis", "authz", "D-03", "20", "OPEN", "-"),
                      ("AX-07", "axis", "ssrf", "D-05", "40", "OPEN", "-")]), pick="none"),
      "HANDOFF", expect_head="AX-07")

# W3c: no registry section (a legacy web ledger before the web wave) -> FALLBACK (byte-for-byte LOOP_CONTINUE, C1-silent).
drive("W3c no registry (legacy web) → FALLBACK",
      ("# webtarget\n\n## Loop State\n- **Iteration #:** 3\n- **Current pick:** H-01\n\n"
       "## Active Hypotheses\n\n"),
      "FALLBACK")

# W3d: flag OFF on a healthy web registry -> FALLBACK (rollback path).
d = tempfile.mkdtemp()
with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
    f.write(web_ledger(reg([("AX-04", "axis", "authz", "D-03", "35", "ACTIVE", "-")]), pick="AX-04"))
_cur["dir"] = d
_old = g.WORKLIST_DRIVER_ENABLED
g.WORKLIST_DRIVER_ENABLED = False
try:
    _dir, _ = g.next_atom("sid")
finally:
    g.WORKLIST_DRIVER_ENABLED = _old
    shutil.rmtree(d, ignore_errors=True)
_ok = (_dir == _LC)
print("  [%s] W3d flag OFF (web) → FALLBACK: %s" % ("PASS" if _ok else "FAIL", "ok" if _ok else "LEAK"))
results.append(_ok)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── W4: the REAL web template carries `## Atom Registry` + a placeholder registry = unpopulated")

_WEB_TPL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "..", "sessions", "_methodology", "hypotheses_web_template.md")
_WEB_TPL = os.path.normpath(_WEB_TPL)
with open(_WEB_TPL, "r", encoding="utf-8") as f:
    _tpl_txt = f.read()
_has_section = "## Atom Registry" in _tpl_txt
print("  [%s] W4a the web template contains the `## Atom Registry` section" % ("PASS" if _has_section else "FAIL"))
results.append(_has_section)
# rows are parsed, but the placeholder row `{AX-01}` is filtered out -> _valid_atoms is empty (as on the contract).
_rows = g._atom_rows(_tpl_txt)
_section_present = _rows is not None
_no_valid = _section_present and (len(g._valid_atoms(_rows)) == 0)
print("  [%s] W4b the section parses, the placeholder is not counted as an atom (valid=0)"
      % ("PASS" if (_section_present and _no_valid) else "FAIL"))
results.append(_section_present and _no_valid)


print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
