#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test for Worklist Driver Stage 1 -- 3 gates on the atom registry (`## Atom Registry`).

Plan: methodology/plans/worklist_driver_plan.md §1/§3/§8. Gates (behind WORKLIST_DRIVER_ENABLED):
  - active_pick_not_from_queue          -- off-queue-pick fix: pick = registry head
    ((1) >1 ACTIVE / (2) pick bypasses the registry / (3) the driven atom is not max-rank even with 0 ACTIVE / (4) rank>80).
  - active_atom_closed_without_narrative -- C3: CLOSED without a proof entry in the REAL sections
    (Refuted/Verifier Log/Axes-Closed) -- a bare mention in Notes / a duplicate row does NOT count.
  - active_registry_unpopulated          -- adoption: a mature+active ledger with an empty registry → populate it.

Rule (feedback_hook_must_prove_firing): the test MUST prove FIRING on the real shape of the failure.
Covers the Stage 1 acceptance defects: judge-2 D2 (adoption)/D3 (0-ACTIVE head)/D4 (proof sections)/D1 (rank-
gaming), judge-1 (padding on both sides), auditor-2 (title-FP, Notes-bypass, dup-row, durability/mtime).
Monkeypatches freshest_active_ledger; the ledger lives in a temp folder. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/worklist_driver_gate_replay.py
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
    """rows: list of tuples (id,type,title,src,rank,status,closes)."""
    body = "".join("| %s | %s | %s | %s | %s | %s | %s |\n" % r for r in rows)
    return REG_HDR + body + "\n"


def ledger(registry_block, pick="{H-NN or score-5 file}", it=7, loop_extra="",
           refuted="", refuted_hdr="## Refuted", verifier="", axes_closed="", notes="",
           raw="", active=""):
    """Full ledger: Loop State + registry + (optional) Refuted/Verifier Log/Axes-Closed/Notes/raw/Active."""
    ls = ("# t — Hypotheses Registry\n\n## Loop State\n"
          "- **Iteration #:** " + str(it) + "\n"
          "- **Current pick:** " + pick + "\n")
    if axes_closed:
        ls += "- **Axes-Closed (backward proof-log):** " + axes_closed + "\n"
    if loop_extra:
        ls += loop_extra + "\n"
    out = ls + "\n" + registry_block
    if refuted:
        out += "\n" + refuted_hdr + "\n" + refuted + "\n"
    if verifier:
        out += "\n## Verifier Log\n" + verifier + "\n"
    if notes:
        out += "\n## Notes\n" + notes + "\n"
    if raw:
        out += "\n" + raw + "\n"
    out += "\n## Active Hypotheses\n" + active + "\n"
    return out


# KEEP: "{краткое имя}" ("short name") and "{число}" ("number") are template placeholder fixtures (Russian in the source template)
TMPL_ROW = ("{AX-01}", "{axis}", "{краткое имя}", "{D-NN|T14-gap}", "{число}", "{OPEN}", "{-}")

results = []


def run(name, fn_name, ledger_txt, expect, flag=True):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old_flag = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = flag
    try:
        got = bool(getattr(g, fn_name)("sid"))
    finally:
        g.WORKLIST_DRIVER_ENABLED = old_flag
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


# ══════════════════════════════════════════════════════════════════════════════
print("── active_pick_not_from_queue (off-queue-pick fix: pick = registry head)")

run("(a) off-queue pick bypasses the registry (OPEN queue non-empty) → fire", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "liquidation-band", "D-03", "30", "OPEN", "-"),
                ("AX-05", "axis", "governance-timelock", "T6-pair", "28", "OPEN", "-")]),
           pick="optimizer-rounding — an axis I set myself (mock-vs-prod)"), True)

run("(b) >1 ACTIVE → fire", "active_pick_not_from_queue",
    ledger(reg([("H-07", "hypothesis", "share-inflation", "D-03", "27", "ACTIVE", "-"),
                ("H-08", "hypothesis", "oracle-conf-strip", "D-04", "24", "ACTIVE", "-")]),
           pick="H-07"), True)

run("(c) ACTIVE is not max-rank (head 35 OPEN skipped) → fire", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band-regression", "D-05", "35", "OPEN", "-"),
                ("H-09", "hypothesis", "dust-rounding", "code-read", "20", "ACTIVE", "-")]),
           pick="H-09"), True)

# judge-2 D3: 0 ACTIVE, pick on a lower OPEN, the OPEN head (35) skipped → fire (generalized head).
run("(c2/D3) 0 ACTIVE: pick=lower OPEN (20), OPEN head (35) skipped → fire", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band-regression", "D-05", "35", "OPEN", "-"),
                ("H-09", "hypothesis", "dust-rounding", "D-03", "20", "OPEN", "-")]),
           pick="H-09 — driving the lower one"), True)

# judge-2 D1: rank-gaming (rank 999 is impossible by the formula, <=80) → fire.
run("(c3/D1) rank-gaming: AX-99 rank 999 ACTIVE → fire (rank>80 impossible)", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "OPEN", "-"),
                ("AX-99", "axis", "my-pet-invented", "gut-feel", "999", "ACTIVE", "-")]),
           pick="AX-99"), True)

# red-team FP #4: rank>80 on a CLOSED atom (not oa) must NOT make the pick gate fire on a healthy head.
run("(c4) rank>80 on a CLOSED atom (not oa) + healthy ACTIVE head → silent", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "ACTIVE", "-"),
                ("H-09", "hypothesis", "old", "D-03", "999", "CLOSED", "-")]),
           pick="AX-04"), False)

# re-judge/red-team title-FN: 1 ACTIVE non-head + a drift pick with the head's title word → fire (ACTIVE authoritative).
run("(c5/title-FN) 1 ACTIVE non-head(20) + drift pick with the head's distinctive title → fire",
    "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "liquidation-band", "D-05", "35", "OPEN", "-"),
                ("H-09", "hypothesis", "dust", "D-03", "20", "ACTIVE", "-")]),
           pick="mentioned liquidation-band, but actually driving an invented reentrancy axis"), True)

# common-word title (`oracle`, not distinctive) does NOT match → drift is not masked → fire.
run("(c6) 0 ACTIVE + drift pick with a common-word head title (oracle) → fire (not distinctive)",
    "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "oracle", "D-05", "35", "OPEN", "-"),
                ("AX-05", "axis", "band", "D-03", "20", "OPEN", "-")]),
           pick="checking an oracle-adjacent new idea that I came up with myself"), True)

run("(d) healthy: 1 ACTIVE max-rank, pick in sync → silent", "active_pick_not_from_queue",
    ledger(reg([("H-09", "hypothesis", "dust-rounding", "D-05", "35", "ACTIVE", "-"),
                ("AX-04", "axis", "band-regression", "code-read", "20", "OPEN", "-")]),
           pick="H-09"), False)

# the distinctive-title FP fix still holds: the pick describes the head by its compound title → silent.
run("(d1b) 0 ACTIVE + pick = head compound title (liquidation-band) → silent (anti-FP)",
    "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "liquidation-band", "D-05", "30", "OPEN", "-"),
                ("AX-05", "axis", "gov-timelock", "code-read", "20", "OPEN", "-")]),
           pick="liquidation-band — driving the head"), False)

# red-team FN-1 (precedence regression): 1 ACTIVE=head, but the pick drives ANOTHER lower atom → fire (2b).
run("(c7/FN-1) 1 ACTIVE=head(35), pick on a lower OPEN(20) → fire (pick≠ACTIVE desync)",
    "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-05", "35", "ACTIVE", "-"),
                ("AX-05", "axis", "gov", "D-03", "20", "OPEN", "-")]),
           pick="AX-05 — actually driving the lower axis"), True)

# red-team FN-2: a single-word LONG title (`liquidation`, not compound) in a drift pick → fire (does not mask).
run("(c8/FN-2) 0 ACTIVE + single-word head title (liquidation) in drift → fire (not compound)",
    "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "liquidation", "D-05", "35", "OPEN", "-"),
                ("AX-05", "axis", "band", "D-03", "20", "OPEN", "-")]),
           pick="thinking about liquidation timing, a new idea that I came up with myself"), True)

# red-team round-3 FP (order-dependent): longest-title match. H-07 'band-drift' (early) must NOT
# override the head H-08 'liquidation-band-drift' when the pick names the HEAD → silent.
run("(c9) longest-title: pick=head 'liquidation-band-drift', early row 'band-drift' → silent",
    "active_pick_not_from_queue",
    ledger(reg([("H-07", "hypothesis", "band-drift", "D-03", "20", "OPEN", "-"),
                ("H-08", "hypothesis", "liquidation-band-drift", "D-05", "35", "ACTIVE", "-")]),
           pick="driving liquidation-band-drift — the registry head"), False)

# auditor-2 FP: the pick is described by the head's TITLE (not id) → silent (title-fallback).
run("(d2) pick by head TITLE (not id) → silent (title-fallback, anti-FP)", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "liquidation-band", "D-05", "30", "OPEN", "-"),
                ("AX-05", "axis", "gov-timelock", "code-read", "20", "OPEN", "-")]),
           pick="liquidation-band — driving the head"), False)

# auditor-2: a stub-src ACTIVE row (real id+rank, src=TBD) does NOT count as an atom → silent.
run("(d3) stub-src ACTIVE (src=TBD) is not an atom → silent", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "OPEN", "-"),
                ("H-99", "hypothesis", "stub", "TBD", "20", "ACTIVE", "-")]),
           pick="AX-04 — taking the head"), False)

run("(e) legacy without a registry section → silent (C1)", "active_pick_not_from_queue",
    ("# t\n\n## Loop State\n- **Iteration #:** 7\n- **Current pick:** myaxis I set it myself\n\n## Active Hypotheses\n\n"), False)

run("(f) untouched template (placeholder {AX-01}) → silent", "active_pick_not_from_queue",
    ledger(reg([TMPL_ROW])), False)

run("(g) first pass: OPEN atoms, pick placeholder → silent", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-03", "30", "OPEN", "-"),
                ("AX-05", "axis", "gov", "T6-pair", "28", "OPEN", "-")]),
           pick="{H-NN or score-5 file}"), False)

run("(g2) pick = real OPEN head id, 0 ACTIVE → silent", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-03", "30", "OPEN", "-"),
                ("AX-05", "axis", "gov", "T6-pair", "20", "OPEN", "-")]),
           pick="AX-04 — driving the head"), False)

run("(h) off-queue config + MANUAL → silent", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-03", "30", "OPEN", "-")]),
           pick="my own axis off-registry", loop_extra="- **HUNT-MODE: MANUAL**"), False)

run("(i) off-queue config + HUNT-EXIT High → silent", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-03", "30", "OPEN", "-")]),
           pick="my own axis off-registry", loop_extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)

run("(j) off-queue config + flag OFF → silent (rollback)", "active_pick_not_from_queue",
    ledger(reg([("AX-04", "axis", "band", "D-03", "30", "OPEN", "-"),
                ("AX-05", "axis", "gov", "T6-pair", "28", "OPEN", "-")]),
           pick="my own axis off-registry"), False, flag=False)

# ══════════════════════════════════════════════════════════════════════════════
print("── active_atom_closed_without_narrative (C3: CLOSED without proof in REAL sections)")

run("(A) orphaned CLOSED (no ### H-09 in proof sections) → fire", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "share-inflation", "D-03", "27", "CLOSED", "-")])), True)

run("(B) CLOSED + ### H-09 [KILLED] in Refuted → silent", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "share-inflation", "D-03", "27", "CLOSED", "-")]),
           refuted="### H-09 [KILLED]: share inflation\n- **Killed by:** guard vault.sol:88\n"), False)

# judge-2 D4 / auditor-2 Notes-bypass: a bare mention in Notes (not proof) → fire.
run("(C/D4) CLOSED + bare mention of H-09 in ## Notes (not proof) → fire", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "share-inflation", "D-03", "27", "CLOSED", "-")]),
           notes="remember to revisit H-09 idea later\n"), True)

# auditor-2 dup-row: a duplicate of the registry table row in Notes (not proof) → fire.
run("(C2) CLOSED + duplicate registry row in Notes (not proof) → fire", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "share-inflation", "D-03", "27", "CLOSED", "-")]),
           notes="| H-09 | hypothesis | share-inflation | D-03 | 27 | CLOSED | - |\n"), True)

run("(C3) CLOSED + H-09 in Verifier Log → silent", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "share-inflation", "D-03", "27", "CLOSED", "-")]),
           verifier="- 2026-08-11 — H-09 — verdict: kill — checker:cold-subagent\n"), False)

# judge-1 D1/D2: padding on both sides. reg H-9 CLOSED + proof `### H-09` in Refuted → silent.
run("(P1) reverse-pad: reg H-9 CLOSED + ### H-09 in Refuted → silent (padding on both sides)",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-9", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           refuted="### H-09 [KILLED]: x\n- **Killed by:** g.sol:1\n"), False)

# judge-1 D2: non-H id padding. reg AX-4 CLOSED + AX-04 in Axes-Closed → silent.
run("(P2) non-H pad: reg AX-4 CLOSED + AX-04 in Axes-Closed → silent",
    "active_atom_closed_without_narrative",
    ledger(reg([("AX-4", "axis", "keeper", "T14-gap", "18", "CLOSED", "-")]),
           axes_closed="AX-04 keeper · outcome:clean · close-grade:depth-drive · proof:5/5"), False)

# padding does not overdo it: reg H-9 CLOSED, proof only H-90 → still fire (H-9 != H-90).
run("(P3) padding does not falsely silence: reg H-9 CLOSED + only H-90 in Refuted → fire",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-9", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           refuted="### H-90 [KILLED]: other\n- **Killed by:** g.sol:1\n"), True)

# red-team #1 (HIGH): decoy section via substring match. `## Refuted Notes` is NOT proof → fire.
run("(I) decoy `## Refuted Notes` with a bare H-09 (not canonical Refuted) → fire", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           refuted="remember H-09 idea to revisit\n", refuted_hdr="## Refuted Notes"), True)

# `## Not Refuted` (the heading NEGATES closure) is NOT proof → fire.
run("(J) decoy `## Not Refuted` with H-09 → fire", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           raw="## Not Refuted Yet\nH-09 still open honestly\n"), True)

# canonical parenthetical `## Refuted (kept for chaining — T6)` WITH proof → silent (parenthetical accepted).
run("(K) canonical `## Refuted (kept…)` + ### H-09 [KILLED] → silent (parenthetical accepted)",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           refuted="### H-09 [KILLED]: x — g.sol:1\n", refuted_hdr="## Refuted (kept for chaining — T6)"), False)

# red-team FP-1 (marker-based): non-canonical section `## Refuted Hypotheses` + a real kill-tag → silent
# (the `[KILLED]` marker next to the id = proof, section-name-agnostic; a decoy without a marker still fires).
run("(K2/FP-1) non-canonical `## Refuted Hypotheses` + ### H-09 [KILLED] → silent (marker-based)",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           refuted="### H-09 [KILLED]: x — g.sol:1\n", refuted_hdr="## Refuted Hypotheses"), False)

# marker-based: `## Verifier` (without "Log") + a REAL verdict → silent (the section name does not matter, the marker does).
run("(K3) `## Verifier` (non-canonical) + H-09 verdict: kill → silent (marker-based)",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           raw="## Verifier\n- H-09 — verdict: kill — checker:cold-subagent\n"), False)

# red-team round-3 anti-laundering: a marker WORD in a NON-closing context → still fire.
run("(L1) H-09 CLOSED + `verdict: pending` (not a real verdict) → fire (semantic-strict)",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           active="H-09 — need to check verdict: pending\n"), True)
run("(L2) H-09 CLOSED + `proof: needed to close` (bare proof removed) → fire",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           notes="TODO: proof: collect for H-09, not yet\n"), True)
run("(L3) H-09 CLOSED + `[LOW-DEFERRED]` (not a closure, building-block) → fire",
    "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           raw="## Building Blocks\n- H-09 [LOW-DEFERRED] dig deeper later\n"), True)

run("(D) axis AX-07 CLOSED, id nowhere in proof → fire", "active_atom_closed_without_narrative",
    ledger(reg([("AX-07", "axis", "keeper-race", "T14-gap", "18", "CLOSED", "-")])), True)

run("(D2) axis AX-07 CLOSED + bullet in Axes-Closed → silent", "active_atom_closed_without_narrative",
    ledger(reg([("AX-07", "axis", "keeper-race", "T14-gap", "18", "CLOSED", "-")]),
           axes_closed="AX-07 keeper-race · outcome:clean · close-grade:depth-drive · proof:5/5"), False)

run("(E) no CLOSED rows → silent", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "ACTIVE", "-"),
                ("AX-04", "axis", "y", "D-05", "30", "OPEN", "-")]), pick="H-09"), False)

run("(F) legacy without a registry section → silent (C1)", "active_atom_closed_without_narrative",
    ("# t\n\n## Loop State\n- **Iteration #:** 7\n\n## Active Hypotheses\n\n"), False)

run("(G) orphaned CLOSED + flag OFF → silent (rollback)", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")])), False, flag=False)

run("(H) orphaned CLOSED + MANUAL → silent", "active_atom_closed_without_narrative",
    ledger(reg([("H-09", "hypothesis", "x", "D-03", "27", "CLOSED", "-")]),
           loop_extra="- **HUNT-MODE: MANUAL**"), False)

# ══════════════════════════════════════════════════════════════════════════════
print("── active_registry_unpopulated (adoption: mature+active ledger with an empty registry)")

# judge-2 D2: iter>=3 + a real pick + an empty registry (placeholder) → fire.
run("(R1/D2) iter7 + real pick + placeholder registry → fire", "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05 — driving the thread", it=7), True)

# silent: the registry is populated.
run("(R2) registry populated with a valid atom → silent", "active_registry_unpopulated",
    ledger(reg([("AX-04", "axis", "band", "D-03", "30", "OPEN", "-")]),
           pick="AX-04", it=7), False)

# silent: iter<3 (early recon).
run("(R3) iter2 + real pick + empty registry → silent (early recon)", "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05 — driving the thread", it=2), False)

# silent: placeholder pick (not actively working).
run("(R4) iter7 + placeholder pick + empty registry → silent", "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="{H-NN or score-5 file}", it=7), False)

# silent: no registry section (C1: web/legacy).
run("(R5) no registry section (C1) → silent", "active_registry_unpopulated",
    ("# t\n\n## Loop State\n- **Iteration #:** 7\n- **Current pick:** H-05\n\n## Active Hypotheses\n\n"), False)

# silent: MANUAL.
run("(R6) fire-config + MANUAL → silent", "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05", it=7, loop_extra="- **HUNT-MODE: MANUAL**"), False)

# silent: HUNT-EXIT.
run("(R7) fire-config + HUNT-EXIT → silent", "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05", it=7, loop_extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)

# silent: flag OFF.
run("(R8) fire-config + flag OFF → silent (rollback)", "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05", it=7), False, flag=False)

# red-team #2 anti iter-freeze: iter=2 is frozen, BUT >=2 real ### H-NN + an empty registry → fire.
run("(R9/iter-freeze) iter2 + >=2 real ### H-NN + empty registry → fire (maturity by hypotheses)",
    "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05 — driving", it=2,
           active="### H-05: leak\n- **State:** C-PoC-attempting\n### H-06: race\n- **State:** A\n"), True)

# silent: iter2 + <2 hypotheses → immature (do not force the registry early).
run("(R10) iter2 + 1 hypothesis → silent (immature)", "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05", it=2, active="### H-05: leak\n- **State:** A\n"), False)

# red-team FN-3: iter2 is frozen + >=2 BULLET hypotheses `- **H-NN:**` (not a heading) + an empty registry → fire.
run("(R9b/FN-3) iter2 + 2 bullet hypotheses `- **H-NN:**` + empty registry → fire (bullet form counts)",
    "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05 — driving", it=2,
           active="- **H-05:** leak via stale oracle\n- **H-06:** race on withdraw\n"), True)

# re-judge #2: MODEL: N/A (small contract/frontend) → adoption does not force the registry → silent.
run("(R11) MODEL: N/A + fire-config → silent (registry is redundant on a small contract/frontend)",
    "active_registry_unpopulated",
    ledger(reg([TMPL_ROW]), pick="H-05 — driving", it=7,
           loop_extra="- **MODEL: N/A — small contract <300 LOC**"), False)

# ══════════════════════════════════════════════════════════════════════════════
print("── active_atom_src_ungrounded (judge-B D2: OPEN/ACTIVE atom with an id-src that is absent from the narrative)")

# (S1) OPEN atom src=D-99, which is NOWHERE in the ledger → fire (fictitious justification).
run("(S1) OPEN src=D-99 (absent from narrative) → fire", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "D-99", "35", "OPEN", "-")]), pick="AX-04"), True)

# (S2) OPEN src=D-03, there really is a `### D-03` in Divergences → silent (grounded).
run("(S2) OPEN src=D-03 + ### D-03 in narrative → silent (grounded)", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "D-03", "35", "OPEN", "-")]), pick="AX-04",
           raw="## Divergences\n### D-03: band not enforced on the redeem path — vault.sol:88\n"), False)

# (S3) src=code-read (a label, not an id) → NOT existence-checked → silent.
run("(S3) src=code-read (label) → silent (not an id)", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "code-read", "35", "OPEN", "-")]), pick="AX-04"), False)

# (S4) src=AX-05 (registry-self id, excluded) → silent even without a narrative entry (AX is not checked).
run("(S4) src=AX-05 (registry-self, not D/H/BB) → silent", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "AX-05", "35", "OPEN", "-"),
                ("AX-05", "axis", "gov", "code-read", "20", "OPEN", "-")]), pick="AX-04"), False)

# (S5) ACTIVE src=H-77 is absent → fire (the ACTIVE side too).
run("(S5) ACTIVE src=H-77 (absent from narrative) → fire", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "H-77", "35", "ACTIVE", "-")]), pick="AX-04"), True)

# (S6) padding: src=D-3, the narrative carries ### D-03 → silent (padding-tolerant, like C3).
run("(S6) src=D-3 + ### D-03 in narrative → silent (padding on both sides)", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "D-3", "35", "OPEN", "-")]), pick="AX-04",
           raw="## Divergences\n### D-03: x — a.sol:1\n"), False)

# (S7) no registry section (C1) → silent.
run("(S7) no registry (C1) → silent", "active_atom_src_ungrounded",
    ("# t\n\n## Loop State\n- **Iteration #:** 7\n\n## Active Hypotheses\n\n"), False)

# (S8) fictitious src + flag OFF → silent (rollback).
run("(S8) OPEN src=D-99 + flag OFF → silent (rollback)", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "D-99", "35", "OPEN", "-")]), pick="AX-04"), False, flag=False)


# (S10/RT-D1) a free-text label with a digit (`D3-fork`/`BB8`/`H2-audit`) is NOT an id → silent (the hyphen is mandatory).
run("(S10a/RT-D1) src=D3-fork (label, no hyphen D-) → silent", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "D3-fork", "35", "OPEN", "-")]), pick="AX-04"), False)
run("(S10b/RT-D1) src=BB8 (label) → silent", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "BB8", "35", "OPEN", "-")]), pick="AX-04"), False)
run("(S10c/RT-D1) src=H2-audit (label) → silent", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "H2-audit", "35", "OPEN", "-")]), pick="AX-04"), False)
# an annotated real id `D-05 (band)` is still checked (grounded in the narrative → silent).
run("(S10d) src=`D-05 (band)` annotated id + ### D-05 in narrative → silent (grounded)",
    "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "D-05 (band)", "35", "OPEN", "-")]), pick="AX-04",
           raw="## Divergences\n### D-05: band — a.sol:1\n"), False)
# ...but an annotated id WITHOUT a narrative entry → fire (the annotation does not rescue a fiction).
run("(S10e) src=`D-88 (fork)` id without a narrative entry → fire", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "band", "D-88 (fork)", "35", "OPEN", "-")]), pick="AX-04"), True)


# (S9/#3 compute-and-name) the reason NAMES a specific atom + a fictitious src (re-judge #3).
def src_ungrounded_name_check():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger(reg([("AX-07", "axis", "reentrancy", "D-99", "40", "OPEN", "-")]), pick="AX-07"))
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        res = g.active_atom_src_ungrounded("sid")
        msg = g.ATOM_SRC_UNGROUNDED_REASON % res if res else ""
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    ok = (isinstance(res, tuple) and len(res) == 3 and res[1] == "AX-07" and res[2] == "D-99"
          and "AX-07" in msg and "D-99" in msg)
    print("  [%s] (S9/#3) reason names atom AX-07 + src D-99: res=%r" % ("PASS" if ok else "FAIL", res))
    results.append(ok)


src_ungrounded_name_check()

# ── invariant-src against the MODEL (web red-team MED wave — I-NN/TB-I/AC-I are checked in system_model.md) ──
print("── active_atom_src_ungrounded: invariant-src (I-NN/TB-I/AC-I) existence check in system_model.md")


def run_m(name, fn_name, ledger_txt, model_txt, expect):
    """run + also writes system_model.md alongside (for the invariant-src differential)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(model_txt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        got = bool(getattr(g, fn_name)("sid"))
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


_CM = "# system_model\n\n| id | inv | ... |\n| I-01 | band enforced | ... |\n| I-03 | supply cap | ... |\n"
_WM = "# system_model — WEB\n\n| TB-I01 | origin exact | ... |\n| AC-I05 | tenant isolation | ... |\n"

run_m("(S11a) contract src=I-99 (nonexistent) + model → fire", "active_atom_src_ungrounded",
      ledger(reg([("AX-04", "axis", "x", "I-99", "35", "ACTIVE", "-")]), pick="AX-04"), _CM, True)
run_m("(S11b) contract src=I-01 (in model) → silent", "active_atom_src_ungrounded",
      ledger(reg([("AX-04", "axis", "x", "I-01", "35", "OPEN", "-")]), pick="AX-04"), _CM, False)
run_m("(S11c) web src=TB-I99 (nonexistent) + model → fire", "active_atom_src_ungrounded",
      ledger(reg([("AX-04", "axis", "x", "TB-I99", "35", "ACTIVE", "-")]), pick="AX-04"), _WM, True)
run_m("(S11d) web src=AC-I05 (in model) → silent", "active_atom_src_ungrounded",
      ledger(reg([("AX-04", "axis", "x", "AC-I05", "35", "OPEN", "-")]), pick="AX-04"), _WM, False)
# (S11e) invariant-src, but there is NO model (run without a file) → silent (fail-safe label).
run("(S11e) src=I-99 without a model → silent (fail-safe)", "active_atom_src_ungrounded",
    ledger(reg([("AX-04", "axis", "x", "I-99", "35", "ACTIVE", "-")]), pick="AX-04"), False)

# ══════════════════════════════════════════════════════════════════════════════
print("── active_axis_queue_empty RE-POINT (judge-B D1: the registry owns the forward queue, the prose gate steps aside)")

_AQ_LOOP = ("- **Depth-Lead:** none yet\n- **T9 restart axes used:** 1 (treasury)\n- **Axis-Queue:** none\n")
# a config on which the prose Axis-Queue gate historically fires (an axis is closed, between axes, the queue is empty).

# (Q1) axis-queue config + NO registry → fire (the old behavior is intact for legacy).
run("(Q1) axis-queue config + NO registry → fire (legacy behavior)", "active_axis_queue_empty",
    ("# t\n\n## Loop State\n- **Iteration #:** 8\n- **Current pick:** none\n" + _AQ_LOOP
     + "\n## Active Hypotheses\n\n"), True)

# (Q2) the same config + a POPULATED registry (valid OPEN) → silent (re-point: next_atom dictates HANDOFF).
run("(Q2) axis-queue config + populated registry → silent (re-point, flag on)", "active_axis_queue_empty",
    ("# t\n\n## Loop State\n- **Iteration #:** 8\n- **Current pick:** AX-04\n" + _AQ_LOOP + "\n"
     + reg([("AX-04", "axis", "band", "D-05", "35", "OPEN", "-")]) + "## Active Hypotheses\n\n"), False)

# (Q3) the same + populated registry + flag OFF → fire (rollback: the prose Axis-Queue lives in parallel).
run("(Q3) axis-queue config + registry + flag OFF → fire (rollback, prose queue in parallel)",
    "active_axis_queue_empty",
    ("# t\n\n## Loop State\n- **Iteration #:** 8\n- **Current pick:** AX-04\n" + _AQ_LOOP + "\n"
     + reg([("AX-04", "axis", "band", "D-05", "35", "OPEN", "-")]) + "## Active Hypotheses\n\n"), True, flag=False)


# (Q4/#5 integral) ON A SINGLE off-queue ledger: axis_queue_empty is SILENT (re-point) AND next_atom issues
# a named HANDOFF of the head (re-judge #5 — the end-to-end chain of B-D1, which used to be stitched separately).
def repoint_handoff_integral():
    d = tempfile.mkdtemp()
    # axis-switch moment: the axis is closed by T9, 0 ACTIVE, an OPEN head with a grounded src, the prose Axis-Queue is empty.
    lt = ("# t\n\n## Loop State\n- **Iteration #:** 8\n- **Current pick:** none\n" + _AQ_LOOP + "\n"
          + reg([("AX-09", "axis", "reentrancy-hook", "code-read", "40", "OPEN", "-"),
                 ("AX-08", "axis", "dust", "T6-pair", "18", "OPEN", "-")])
          + "## Active Hypotheses\n\n")
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(lt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        aq_silent = (g.active_axis_queue_empty("sid") is None)   # re-point: the prose gate is silent
        directive, _ = g.next_atom("sid")                        # next_atom picks it up
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    is_handoff = "голова реестра сменилась" in directive  # KEEP: Russian string matches the hook output ("registry head changed")
    names_head = "`AX-09`" in directive                          # max-rank head
    ok = aq_silent and is_handoff and names_head
    print("  [%s] (Q4/#5) off-queue ledger: axis_queue silent=%s AND next_atom HANDOFF of head AX-09=%s"
          % ("PASS" if ok else "FAIL", aq_silent, is_handoff and names_head))
    results.append(ok)


repoint_handoff_integral()

# ══════════════════════════════════════════════════════════════════════════════
print("── active_registry_drained_no_exit (pilot HIGH-1: give-up seam — all atoms CLOSED, 0 OPEN/ACTIVE)")

# (DR1) drained: 2 CLOSED atoms, 0 OPEN/ACTIVE, no exit → fire (give-up seam).
run("(DR1) 2 CLOSED, 0 OPEN/ACTIVE, no exit → fire", "active_registry_drained_no_exit",
    ledger(reg([("H-05", "hypothesis", "sig-replay", "D-03", "24", "CLOSED", "-"),
                ("AX-04", "axis", "band", "D-05", "30", "CLOSED", "-")])), True)

# (DR2) healthy: 1 OPEN + 1 CLOSED → silent (there is a live head).
run("(DR2) 1 OPEN + 1 CLOSED → silent (live head)", "active_registry_drained_no_exit",
    ledger(reg([("H-05", "hypothesis", "x", "D-03", "24", "CLOSED", "-"),
                ("AX-04", "axis", "band", "D-05", "30", "OPEN", "-")]), pick="AX-04"), False)

# (DR3) genuine first pass: only the template stub (0 valid atoms) → silent (unpopulated territory).
run("(DR3) only placeholder (0 valid) → silent (first pass, not drained)", "active_registry_drained_no_exit",
    ledger(reg([TMPL_ROW])), False)

# (DR4) drained + HUNT-EXIT → silent (the hunt is finished).
run("(DR4) drained + HUNT-EXIT → silent", "active_registry_drained_no_exit",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "CLOSED", "-")]),
           loop_extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)

# (DR5) drained + flag OFF → silent (rollback).
run("(DR5) drained + flag OFF → silent (rollback)", "active_registry_drained_no_exit",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "CLOSED", "-")])), False, flag=False)

# (DR6) drained + MANUAL → silent.
run("(DR6) drained + MANUAL → silent", "active_registry_drained_no_exit",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "CLOSED", "-")]),
           loop_extra="- **HUNT-MODE: MANUAL**"), False)

# (DR7) drained + HUNT-MODE: OFF → silent (a disarmed reserve, like the pilot's final).
run("(DR7) drained + HUNT-MODE: OFF → silent", "active_registry_drained_no_exit",
    "HUNT-MODE: OFF\n" + ledger(reg([("AX-04", "axis", "band", "D-05", "30", "CLOSED", "-")])), False)

# (DR8) no registry section (C1: web/legacy) → silent.
run("(DR8) no registry section (C1) → silent", "active_registry_drained_no_exit",
    ("# t\n\n## Loop State\n- **Iteration #:** 7\n\n## Active Hypotheses\n\n"), False)

# (DR9) all PARKED (valid, 0 OPEN/ACTIVE) → fire (stagnation = give-up, unpark/generate).
run("(DR9) all PARKED, 0 OPEN/ACTIVE → fire (stagnation)", "active_registry_drained_no_exit",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "PARKED", "cond")])), True)

# (DR10) all BANKED (valid, 0 OPEN/ACTIVE) → fire (banked Medium/Low do NOT end the loop).
run("(DR10) all BANKED, 0 OPEN/ACTIVE → fire (banked do not end the loop)", "active_registry_drained_no_exit",
    ledger(reg([("H-05", "hypothesis", "medium-finding", "D-03", "40", "BANKED", "-")])), True)

# (DR11) 1 ACTIVE + the rest CLOSED → silent (live head).
run("(DR11) 1 ACTIVE + CLOSED → silent (live head)", "active_registry_drained_no_exit",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "ACTIVE", "-"),
                ("H-05", "hypothesis", "x", "D-03", "24", "CLOSED", "-")]), pick="AX-04"), False)


# (DR12/HIGH-1 integral) the EXACT pilot scenario: an honest all-CLOSED with proof in Axes-Closed (C3 satisfied)
# → drained FIRES, while pick/unpopulated/axis_queue are SILENT. Proves the seam is really closed: previously
# the give-up was invisible to all three. (a proof entry silences active_atom_closed_without_narrative.)
def drained_seam_integral():
    d = tempfile.mkdtemp()
    _AQ = ("- **Depth-Lead:** none yet\n- **T9 restart axes used:** 1 (fill-lifecycle)\n"
           "- **Axis-Queue:** none\n")
    lt = ledger(reg([("H-03", "hypothesis", "delegatecall-persist", "D-03", "24", "CLOSED", "-"),
                     ("AX-01", "axis", "fill-lifecycle", "D-05", "30", "CLOSED", "-")]),
                pick="none", it=8, loop_extra=_AQ,
                axes_closed="AX-01 fill-lifecycle · outcome:clean · close-grade:depth-drive · proof:5/5",
                refuted="### H-03 [KILLED]\nfalsifier: OrderMixin.sol:74 terminal revert unwinds state\n",
                verifier="H-03 cold-verify: delegatecall state unwound — confirmed KILLED\n")
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(lt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        drained = bool(g.active_registry_drained_no_exit("sid"))     # the NEW gate catches the give-up
        pick = bool(g.active_pick_not_from_queue("sid"))             # the old one — silent (no head)
        unpop = bool(g.active_registry_unpopulated("sid"))           # silent (there are valid CLOSED)
        aq = bool(g.active_axis_queue_empty("sid"))                  # silent (the registry steers it aside)
        cn = bool(g.active_atom_closed_without_narrative("sid"))     # silent (proof recorded)
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    ok = drained and not pick and not unpop and not aq and not cn
    print("  [%s] (DR12/HIGH-1) drained catches=%s, while pick/unpop/axis_queue/C3 are silent=%s/%s/%s/%s (seam closed)"
          % ("PASS" if ok else "FAIL", drained, pick, unpop, aq, cn))
    results.append(ok)


drained_seam_integral()

# ══════════════════════════════════════════════════════════════════════════════
print("── active_axes_depth_inflated (long-run: breadth treadmill — a depth-drive label without observed)")


def di_ledger(n_deep, n_obs, grade="depth-drive", typ="axis", bare_obs=0):
    """n_deep CLOSED atoms with close-grade + n_obs GROUNDED observed (file:line) + bare_obs BARE observed."""
    rows = [("AX-%02d" % i, typ, "axis-%d" % i, "I-0%d" % (i % 9 + 1), str(30 - i), "CLOSED", "AX-%02d" % i)
            for i in range(1, n_deep + 1)]
    proof = "## Axes-Closed\n" + "".join(
        "- AX-%02d axis-%d · outcome:clean · close-grade:%s · proof:5/5\n" % (i, i, grade)
        for i in range(1, n_deep + 1))
    obs = "## DEPTH-TRACE\n" + "".join("observed: OrderMixin.sol:%d cross-boundary\n" % (i * 7)
                                       for i in range(n_obs))
    obs += "".join("observed: looks fine, checked axis %d\n" % i for i in range(bare_obs))  # bare (not file:line)
    return ledger(reg(rows), pick="AX-01", it=15, raw=proof + "\n" + obs)


# (DI1) 5 depth-drive axes, 0 observed → fire (breadth theater, like a real A/B run).
run("(DI1) 5 depth-drive axes / 0 observed → fire", "active_axes_depth_inflated", di_ledger(5, 0), True)
# (DI2) 5 depth-drive axes, 5 observed → silent (depth is backed up).
run("(DI2) 5 depth-drive axes / 5 observed → silent (matched)", "active_axes_depth_inflated",
    di_ledger(5, 5), False)
# (DI3) 3 depth-drive axes (<4) → silent (early/lazy).
run("(DI3) 3 depth-drive axes (<4) / 0 observed → silent (lazy early)", "active_axes_depth_inflated",
    di_ledger(3, 0), False)
# (DI4) 5 axes, but close-grade:scout-verified (not depth-drive) → silent (the label is honest, not counted).
run("(DI4) 5 scout-verified axes / 0 observed → silent (not depth-drive)", "active_axes_depth_inflated",
    di_ledger(5, 0, grade="scout-verified"), False)
# (DI5) 6 depth-drive / 2 observed → 6-2=4>=3 → fire.
run("(DI5) 6 depth-drive / 2 observed (delta 4) → fire", "active_axes_depth_inflated",
    di_ledger(6, 2), True)
# (DI6) 5 depth-drive / 3 observed → 5-3=2<3 → silent (threshold boundary).
run("(DI6) 5 depth-drive / 3 observed (delta 2) → silent (threshold)", "active_axes_depth_inflated",
    di_ledger(5, 3), False)
# (DI7) type:hypothesis (not axis) depth-drive → not counted (axes only).
run("(DI7) 5 hypothesis depth-drive / 0 observed → silent (type:axis only)", "active_axes_depth_inflated",
    di_ledger(5, 0, typ="hypothesis"), False)
# (DI8) fire-config + HUNT-EXIT → silent.
run("(DI8) fire-config + HUNT-EXIT → silent", "active_axes_depth_inflated",
    di_ledger(5, 0)[:-1] + "\n- **HUNT-EXIT: T4-CONFIRMED High**\n", False)
# (DI9) fire-config + flag OFF → silent (rollback).
run("(DI9) fire-config + flag OFF → silent (rollback)", "active_axes_depth_inflated", di_ledger(5, 0), False,
    flag=False)
# (DI10) fire-config + MANUAL → silent.
run("(DI10) fire-config + MANUAL → silent", "active_axes_depth_inflated",
    di_ledger(5, 0) + "\n- **HUNT-MODE: MANUAL**\n", False)
# (DI11/padding — judge residual #1) 6 depth-drive + 8 BARE observed (no file:line) → FIRE (padding closed).
run("(DI11/padding) 6 depth-drive / 0 grounded / 8 bare observed → fire (not gamed by a token)",
    "active_axes_depth_inflated", di_ledger(6, 0, bare_obs=8), True)
# (DI12) 5 depth-drive / 5 grounded (file:line) + 3 bare → silent (grounded backs it up, bare are irrelevant).
run("(DI12) 5 depth-drive / 5 grounded file:line / 3 bare → silent", "active_axes_depth_inflated",
    di_ledger(5, 5, bare_obs=3), False)
# (DI13/distinct — anti copy-paste) 6 depth-drive / 1 file:line line REPEATED (n_obs=1) → fire (distinct=1).
run("(DI13/distinct) 6 depth-drive / 1 grounded → fire (6-1=5>=3)", "active_axes_depth_inflated",
    di_ledger(6, 1), True)
# ── FIX-A (ethena run 2026-08-12, judge-2 3/10): format-DECOUPLED counting. Exactly the ethena form that the
# OLD gate missed: type:scout-partition (not "axis") + close-grade in a free-form blob → undercount 5→2.
# (DI14) 5 CLOSED type:scout-partition depth-drive / 0 observed → FIRE (old: type≠axis → 0 → silent).
run("(DI14/FIX-A) 5 scout-partition depth-drive / 0 observed → fire [type-decoupled]", "active_axes_depth_inflated",
    di_ledger(5, 0, typ="scout-partition"), True)
# (DI15) 5 CLOSED type:cross-thread depth-drive / 0 observed → FIRE.
run("(DI15/FIX-A) 5 cross-thread depth-drive / 0 observed → fire [type-decoupled]", "active_axes_depth_inflated",
    di_ledger(5, 0, typ="cross-thread"), True)
# (DI16) scout-partition + 5 grounded observed → silent (proven → not inflation).
run("(DI16/FIX-A) 5 scout-partition / 5 grounded → silent", "active_axes_depth_inflated",
    di_ledger(5, 5, typ="scout-partition"), False)
# (DI17) close-grades in a FREE-FORM T9 blob (NOT in registry axis atoms) / 0 observed → FIRE via line-scan.
# KEEP: "осей" ("axes") in the Loop State fixture line below is test-fixture input to the T9 parser (unsure whether matched)
_T9BLOB = ("## Loop State\n- **T9 restart axes used:** 5 осей — "
           + " · ".join("AX-%02d core close-grade:depth-drive outcome:clean" % i for i in range(1, 6)) + "\n")
run("(DI17/FIX-A) 5 AX close-grade in a T9 blob, not in the registry / 0 observed → fire [line-scan]",
    "active_axes_depth_inflated",
    ledger(reg([("H-01", "hypothesis", "active-lead", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15, raw=_T9BLOB),
    True)
# (DI18/anti-FP) a T9 blob with AX ids marked type:hypothesis in the registry → do NOT count (respect the type, like DI7).
run("(DI18/FIX-A anti-FP) 5 AX in a T9 blob, but type:hypothesis in the registry → silent (respect the type)",
    "active_axes_depth_inflated",
    ledger(reg([("AX-%02d" % i, "hypothesis", "h%d" % i, "D-01", "20", "CLOSED", "-") for i in range(1, 6)]),
           pick="AX-01", it=15, raw=_T9BLOB), False)

# ══════════════════════════════════════════════════════════════════════════════
print("── active_axis_queue_thin (FIX-B, ethena run 2026-08-12, judge-2): rich forward queue")
_CLOSED_AX = lambda n: [("AX-%02d" % i, "axis", "closed-ax-%d" % i, "D-0%d" % (i % 9 + 1), str(30 - i), "CLOSED", "-")
                        for i in range(1, n + 1)]
_OPEN_AX = lambda n, base=50: [("AX-%02d" % (base + i), "axis", "future-ax-%d" % i, "D-0%d" % (i % 9 + 1),
                                str(25 - i), "OPEN", "-") for i in range(1, n + 1)]
# (BT1 ethena-shape) 3 CLOSED axes + 1 ACTIVE + 0 OPEN → FIRE (reactive one-at-a-time, thin queue).
run("(BT1/FIX-B) 3 closed axes + 1 ACTIVE + 0 OPEN → fire [thin queue]", "active_axis_queue_thin",
    ledger(reg(_CLOSED_AX(3) + [("H-09", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-09", it=15), True)
# (BT2 rich) 3 CLOSED + 3 OPEN ranked axes → silent (rich forward plan).
run("(BT2/FIX-B) 3 closed + 3 OPEN ranked axes → silent [rich queue]", "active_axis_queue_thin",
    ledger(reg(_CLOSED_AX(3) + _OPEN_AX(3)), pick="AX-51", it=15), False)
# (BT3 early) 1 CLOSED axis + 0 OPEN → silent (<2 closed, forward plan is early).
run("(BT3/FIX-B) 1 closed axis + 0 OPEN → silent [not multi-axis]", "active_axis_queue_thin",
    ledger(reg(_CLOSED_AX(1) + [("H-09", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-09", it=15), False)
# (BT4 deep single-axis anti-FP) 2 CLOSED + 1 ACTIVE + 3 OPEN hypotheses of the current axis → silent (queue >=3).
run("(BT4/FIX-B anti-FP) 2 closed + 3 OPEN hypotheses (current axis) → silent", "active_axis_queue_thin",
    ledger(reg(_CLOSED_AX(2) + [("H-09", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]
               + [("H-%02d" % (10 + i), "hypothesis", "lead-%d" % i, "D-01", str(22 - i), "OPEN", "-") for i in range(3)]),
           pick="H-09", it=15), False)
# (BT5 off) fire-config + HUNT-EXIT → silent.
run("(BT5/FIX-B) fire-config + HUNT-EXIT → silent", "active_axis_queue_thin",
    ledger(reg(_CLOSED_AX(3) + [("H-09", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-09", it=15,
           verifier="- HUNT-EXIT: T4-CONFIRMED High\n"), False)
# (BT6 rollback) fire-config + flag OFF → silent.
run("(BT6/FIX-B) fire-config + flag OFF → silent (rollback)", "active_axis_queue_thin",
    ledger(reg(_CLOSED_AX(3) + [("H-09", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-09", it=15),
    False, flag=False)

# ══════════════════════════════════════════════════════════════════════════════
print("── active_axes_breadth_tilt (FIX-F, ethena run 2026-08-12, judge-3 HIGH: scout-verified breadth escape)")
# (FT1) 5 scout-verified closed axes / 0 observed → FIRE (circumventing FIX-A with an honest label).
run("(FT1/FIX-F) 5 scout-verified / 0 observed → fire [scout-tilt]", "active_axes_breadth_tilt",
    di_ledger(5, 0, grade="scout-verified"), True)
# (FT2) 5 depth-drive / 0 observed → silent (FIX-A's case; FIX-F is silent because scout=0 <= deep).
run("(FT2/FIX-F) 5 depth-drive / 0 observed → silent (FIX-A catches it, not FIX-F)", "active_axes_breadth_tilt",
    di_ledger(5, 0, grade="depth-drive"), False)
# (FT3) 5 scout-verified + 3 grounded observed → silent (there is real depth somewhere).
run("(FT3/FIX-F) 5 scout-verified / 3 grounded → silent (depth exists)", "active_axes_breadth_tilt",
    di_ledger(5, 3, grade="scout-verified"), False)
# (FT4) 3 scout-verified (<4) / 0 observed → silent (early/small hunt).
run("(FT4/FIX-F) 3 scout-verified (<4) / 0 observed → silent [early]", "active_axes_breadth_tilt",
    di_ledger(3, 0, grade="scout-verified"), False)
# (FT5) fire-config + HUNT-EXIT → silent.
run("(FT5/FIX-F) fire-config + HUNT-EXIT → silent", "active_axes_breadth_tilt",
    di_ledger(5, 0, grade="scout-verified")[:-1] + "\n- **HUNT-EXIT: T4-CONFIRMED High**\n", False)
# (FT6) fire-config + flag OFF → silent (rollback).
run("(FT6/FIX-F) fire-config + flag OFF → silent (rollback)", "active_axes_breadth_tilt",
    di_ledger(5, 0, grade="scout-verified"), False, flag=False)

# ══════════════════════════════════════════════════════════════════════════════
print("── SUD-HIGH-1 (jito run 2026-08-12): prose-keyed axis close-grade (bold-name, WITHOUT AX-id) — format-decouple")
# jito Axes-Closed format: `  - **subsystem-core (I-04/I-07)** · src:model · outcome:clean · close-grade:depth-drive ·`
# — a bold-name KEY instead of an AX-id. `_AXIS_ID_RE`=AX-\d+ did not catch them → depth-claimed=0, scout-graded=0 → both
# anti-breadth gates were BLIND to the prose layout (the same format-decoupling relapse as ethena FIX-A/FIX-F).


def prose_axes(n, grade="depth-drive", n_obs=0, mixed=None):
    """n prose-keyed close-grade bullets WITHOUT AX-id (jito format: bold-name = the axis key).
    mixed: list of (count, grade) for a mix of grades (jito-shape FP guard). Registry without axis atoms."""
    specs = mixed if mixed is not None else [(n, grade)]
    body, k = "", 1
    for cnt, gr in specs:
        for _ in range(cnt):
            body += ("  - **subsystem-core-%d (I-%02d/I-%02d)** · src:model · outcome:clean · close-grade:%s ·\n"
                     % (k, k, k + 20, gr))
            k += 1
    proof = "## Axes-Closed\n" + body
    obs = "## DEPTH-TRACE\n" + "".join("observed: OrderMixin.sol:%d cross-boundary\n" % (i * 7) for i in range(n_obs))
    return ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
                  raw=proof + "\n" + obs)


# (PK1) 5 prose-keyed depth-drive axes (bold-name, 0 AX-id) / 0 observed → FIRE (was blind → 0<4 silent).
run("(PK1/SUD-HIGH-1) 5 prose-keyed depth-drive / 0 observed → fire [bold-name key]",
    "active_axes_depth_inflated", prose_axes(5, "depth-drive"), True)
# (PK2) 5 prose-keyed scout-verified axes / 0 observed → FIRE breadth-tilt (was blind).
run("(PK2/SUD-HIGH-1) 5 prose-keyed scout-verified / 0 observed → fire [breadth-tilt]",
    "active_axes_breadth_tilt", prose_axes(5, "scout-verified"), True)
# (PK3/FP-guard jito-shape) 3 depth-drive + 1 scout prose bullets (depth predominates) → depth-inflated SILENT.
run("(PK3/SUD-HIGH-1 FP jito) 3 depth + 1 scout prose / 0 obs → depth-inflated silent [<4 deep]",
    "active_axes_depth_inflated", prose_axes(0, mixed=[(3, "depth-drive"), (1, "scout-verified")]), False)
# (PK4/FP-guard jito-shape) the same 3 depth + 1 scout → breadth-tilt SILENT (scout=1 <= deep=3).
run("(PK4/SUD-HIGH-1 FP jito) 3 depth + 1 scout prose → breadth-tilt silent [scout<=deep]",
    "active_axes_breadth_tilt", prose_axes(0, mixed=[(3, "depth-drive"), (1, "scout-verified")]), False)
# (PK5/matched) 5 prose depth-drive + 5 grounded observed → silent (depth is backed up).
run("(PK5/SUD-HIGH-1) 5 prose depth-drive / 5 grounded observed → silent [matched]",
    "active_axes_depth_inflated", prose_axes(5, "depth-drive", n_obs=5), False)
# (PK6/anti-double-count) a bullet with BOTH an AX-id AND a bold-name on the close-grade line → count by AX-id (1 axis, not 2).


def _pk6():
    reg_rows = [("AX-%02d" % i, "axis", "ax-%d" % i, "I-01", "20", "CLOSED", "-") for i in range(1, 6)]
    body = "".join("  - **AX-%02d subsystem-core-%d** · outcome:clean · close-grade:depth-drive ·\n" % (i, i)
                   for i in range(1, 6))
    return ledger(reg(reg_rows), pick="AX-01", it=15, raw="## Axes-Closed\n" + body)


run("(PK6/SUD-HIGH-1 anti-double) 5 bullets with AX-id+bold-name → fire (5 axes, not 10)",
    "active_axes_depth_inflated", _pk6(), True)
# (PK7/R1 wrapped) close-grade on the 2nd (wrapped) line of the bullet, the bold-name on the heading (jito-203 form).


def _pk7(grade="scout-verified"):
    # KEEP: "веер" ("fan-out") in the proof text below is fixture text (fan-out regex in the hook matches the Russian word)
    body = "".join(
        "  - **subsystem-%d (W%d-I1..I7)** · src:model · outcome:clean ·\n"
        "    close-grade:%s+T4 · proof: веер all ENFORCED\n" % (i, i, grade)
        for i in range(1, 6))
    return ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
                  raw="## Axes-Closed\n" + body)


run("(PK7/R1 wrapped) 5 wrapped-scout close-grade (bold on the heading above) → breadth-tilt fire",
    "active_axes_breadth_tilt", _pk7("scout-verified"), True)
# (PK8/R1 wrapped anti-jump) close-grade wrapped across a BLANK line from the heading → do NOT pull it (block break).


def _pk8():
    body = ("  - **orphan-heading (I-01)** · src:model\n\n"
            "    close-grade:depth-drive · proof: stray\n") * 5   # the blank line breaks the link
    return ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
                  raw="## Axes-Closed\n" + body)


run("(PK8/R1 anti-jump) close-grade across a blank line from the bold heading → depth-inflated silent [break]",
    "active_axes_depth_inflated", _pk8(), False)
# (PK9/R1 anti-FP) prose bold bullets (`- **Residual signal:**` without axis markers) next to
# close-grade:depth-drive → do NOT count as an axis (jito FP: `name:residual signal:` was caught by the wrapped lookup).


def _pk9():
    body = "".join(
        "- **Residual signal:** crank enforcement is tight, guards on all paths.\n"
        "  close-grade:depth-drive learned about subsystem %d\n" % i for i in range(1, 8))
    # 5 REAL axes with axis markers, so the gate WOULD be armed IF Residual signal were counted (7+5=12).
    real = "".join("  - **real-axis-%d (I-0%d)** · src:model · outcome:clean · close-grade:scout-verified ·\n"
                   % (i, i) for i in range(1, 6))
    return ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
                  raw="## Axes-Closed\n" + real + body)


# Residual signal is NOT counted as depth → depth-claimed=0 <4 → depth-inflated silent (otherwise 7 false → fire).
run("(PK9/R1 anti-FP) prose `- **Residual signal:**` near close-grade → depth-inflated silent [not an axis]",
    "active_axes_depth_inflated", _pk9(), False)
# (PK10/R1 non-bold) the literal template format `- <axis> · src: · close-grade:depth-drive` WITHOUT bold →
# counted (name = text up to the first `·`). The template canonizes non-bold; the parser must cover both.


def _pk10():
    body = "".join("- vault-subsystem-%d · src:model · outcome:clean · close-grade:depth-drive · proof:5/5\n" % i
                   for i in range(1, 6))
    return ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
                  raw="## Axes-Closed\n" + body)


run("(PK10/R1 non-bold) 5 non-bold template axes close-grade:depth-drive / 0 obs → depth-inflated fire",
    "active_axes_depth_inflated", _pk10(), True)

# ── MED-3 (jito run): _grounded_observed_count undercounts a file:line that stands BEFORE `observed:` ──
# jito depth-trace: `L1 enqueue_withdrawal.rs:64,117 — VRT escrow ... (observed:64 ✓)` — a real file:line
# BEFORE the word observed; `_OBSERVED_ART_RE` (requires observed→artifact) → MISS. On jito an undercount 9→3.
print("── MED-3 (jito run): observed:file:line in ANY order (file:line BEFORE observed)")


def _med3(txt):
    ok = g._grounded_observed_count("## DEPTH-TRACE\n" + txt + "\n") >= 1
    print(("  [PASS]" if ok else "  [FAIL]") + " grounded_observed>=1 :: " + txt[:70])
    results.append(bool(ok))


# file:line BEFORE observed (jito L1-L6 form) — MISS before, >=1 after the fix.
_med3("L1 enqueue_withdrawal.rs:64,117 — VRT escrow + vrt_enqueued (observed:64 ok)")
_med3("L3 vault.rs:1135-1197 calculate_additional — reserve (observed:1194)")
# regression: file:line AFTER observed still counts.
_med3("observed: OrderMixin.sol:410 cross-boundary drift")
# regression: run-log/fork-diff artifacts are not affected.
_med3("observed: fork-diff shows delta on withdraw path")


def _med3_neg(txt):
    """negative: a bare observed WITHOUT an artifact — does NOT count (residual #1 preserved)."""
    bad = g._grounded_observed_count("## X\n" + txt + "\n") == 0
    print(("  [PASS]" if bad else "  [FAIL]") + " grounded_observed==0 (bare) :: " + txt[:60])
    results.append(bool(bad))


_med3_neg("observed: looks fine, checked the accounting path carefully")
_med3_neg("enqueue_withdrawal.rs mentioned but no line and no observed keyword")  # no observed + no :line

# ══════════════════════════════════════════════════════════════════════════════
print("── active_head_rank_unjustified (final judge Axis-2: a high-rank head with a bare src = laundered)")


def hr(rank, src, status="OPEN", extra_rows=None, **kw):
    rows = [("AX-01", "axis", "head-axis", src, str(rank), status, "-")]
    if extra_rows:
        rows += extra_rows
    return ledger(reg(rows), pick="AX-01", it=8, **kw)


# (HR1) head rank 45 + src=code-read (a bare label) → fire (high rank is not justified).
run("(HR1) rank45 + src=code-read → fire (bare label)", "active_head_rank_unjustified", hr(45, "code-read"), True)
# (HR2) head rank 45 + src=D-05 (id form) → silent (grounded; existence is checked by src_ungrounded separately).
run("(HR2) rank45 + src=D-05 (id) → silent (grounded form)", "active_head_rank_unjustified", hr(45, "D-05"), False)
# (HR3) head rank 30 (<40) + src=code-read → silent (below the threshold — not a Crit rank).
run("(HR3) rank30 + src=code-read → silent (below threshold)", "active_head_rank_unjustified", hr(30, "code-read"), False)
# (HR4) rank 50 + src=attention-gap → silent (recognized origin).
run("(HR4) rank50 + src=attention-gap → silent (origin)", "active_head_rank_unjustified", hr(50, "attention-gap"), False)
# (HR5) rank 50 + src=negative-space → silent (origin).
run("(HR5) rank50 + src=negative-space → silent", "active_head_rank_unjustified", hr(50, "negative-space"), False)
# (HR6) rank 80 + src=gut → fire (bare).
run("(HR6) rank80 + src=gut → fire", "active_head_rank_unjustified", hr(80, "gut"), True)
# (HR7) rank 45 + src=I-03 (invariant) → silent.
run("(HR7) rank45 + src=I-03 (invariant) → silent", "active_head_rank_unjustified", hr(45, "I-03"), False)
# (HR8) rank 45 + src=T6-pair → silent (origin).
run("(HR8) rank45 + src=T6-pair → silent", "active_head_rank_unjustified", hr(45, "T6-pair"), False)
# (HR9) fire-config + HUNT-EXIT → silent.
run("(HR9) rank45 code-read + HUNT-EXIT → silent", "active_head_rank_unjustified",
    hr(45, "code-read", loop_extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)
# (HR10) fire-config + flag OFF → silent (rollback).
run("(HR10) rank45 code-read + flag OFF → silent", "active_head_rank_unjustified", hr(45, "code-read"), False, flag=False)
# (HR11) fire-config + MANUAL → silent.
run("(HR11) rank45 code-read + MANUAL → silent", "active_head_rank_unjustified",
    hr(45, "code-read", loop_extra="- **HUNT-MODE: MANUAL**"), False)
# (HR12) head = max-rank: a rank60 code-read head ON TOP of rank45 D-05 → fire (the head is bare).
run("(HR12) head=rank60 code-read over rank45 D-05 → fire (head is bare)", "active_head_rank_unjustified",
    hr(45, "D-05", extra_rows=[("AX-02", "axis", "shiny", "code-read", "60", "OPEN", "-")]), True)
# (HR13) a grounded rank60 D-05 head over a bare rank45 code-read → silent (the head is justified, the tail does not matter).
run("(HR13) head=rank60 D-05 over rank45 code-read → silent (head grounded)", "active_head_rank_unjustified",
    hr(45, "code-read", extra_rows=[("AX-02", "axis", "strong", "D-05", "60", "OPEN", "-")]), False)
# (HR14) a CLOSED atom rank80 code-read (not OPEN/ACTIVE) + head rank20 → silent (closed ones are not the head).
run("(HR14) rank80 code-read CLOSED + OPEN rank20 origin → silent", "active_head_rank_unjustified",
    hr(20, "attention-gap", extra_rows=[("AX-02", "axis", "old", "code-read", "80", "CLOSED", "AX-02")]), False)
# ── two-tier (confirmatory judge residual: Crit rank >=56 requires an id form, an origin label is not enough) ──
# (HR15) rank70 + src=attention-gap → fire (Crit tier: origin is insufficient, D/I-NN is needed).
run("(HR15/crit) rank70 + attention-gap → fire (Crit needs an id, origin is not enough)", "active_head_rank_unjustified",
    hr(70, "attention-gap"), True)
# (HR16) rank70 + src=D-05 → silent (Crit-tier id form).
run("(HR16/crit) rank70 + D-05 → silent (id form)", "active_head_rank_unjustified", hr(70, "D-05"), False)
# (HR17) rank60 + src=negative-space → fire (Crit tier, origin is not enough).
run("(HR17/crit) rank60 + negative-space → fire", "active_head_rank_unjustified", hr(60, "negative-space"), True)
# (HR18) rank56 (boundary) + src=I-03 → silent (Crit id form).
run("(HR18/crit-boundary) rank56 + I-03 → silent", "active_head_rank_unjustified", hr(56, "I-03"), False)
# (HR19) rank55 (High boundary) + src=attention-gap → silent (High tier: origin is acceptable).
run("(HR19/high-boundary) rank55 + attention-gap → silent (High origin ok)", "active_head_rank_unjustified",
    hr(55, "attention-gap"), False)

# ══════════════════════════════════════════════════════════════════════════════
print("── active_registry_section_absent (re-pilot MED-1: the `## Atom Registry` section is ABSENT altogether → C1 escape)")

_MATURE_ACTIVE = "### H-05: leak\n- **State:** A\n### H-06: race\n- **State:** A\n"

# (SA1) mature (iter7) + a real pick + NO registry section → fire (the whole driver is blind).
run("(SA1) iter7 + real pick + NO section → fire", "active_registry_section_absent",
    ledger("", pick="H-05 — driving the thread", it=7, active=_MATURE_ACTIVE), True)

# (SA2) the section EXISTS (empty placeholder) → silent (this is unpopulated territory, not section_absent).
run("(SA2) section present (placeholder) → silent (unpopulated territory)", "active_registry_section_absent",
    ledger(reg([TMPL_ROW]), pick="H-05 — driving", it=7), False)

# (SA3) the section exists (populated) → silent.
run("(SA3) section present (populated) → silent", "active_registry_section_absent",
    ledger(reg([("AX-04", "axis", "band", "D-05", "30", "OPEN", "-")]), pick="AX-04", it=7), False)

# (SA4) iter2 + <2 hypotheses + no section → silent (immature).
run("(SA4) iter2 + <2 hyp + no section → silent (immature)", "active_registry_section_absent",
    ledger("", pick="H-05", it=2, active="### H-05: x\n- **State:** A\n"), False)

# (SA5) mature + placeholder pick + no section → silent (not actively working).
run("(SA5) iter7 + placeholder pick + no section → silent", "active_registry_section_absent",
    ledger("", pick="{H-NN or score-5 file}", it=7, active=_MATURE_ACTIVE), False)

# (SA6) MODEL: N/A (small/frontend) + no section → silent (the registry is redundant).
run("(SA6) MODEL: N/A + no section → silent (small/frontend)", "active_registry_section_absent",
    ledger("", pick="H-05 — driving", it=7, active=_MATURE_ACTIVE,
           loop_extra="- **MODEL: N/A — small contract <300 LOC**"), False)

# (SA7) HUNT-EXIT + no section → silent (the hunt is finished).
run("(SA7) HUNT-EXIT + no section → silent", "active_registry_section_absent",
    ledger("", pick="H-05", it=7, active=_MATURE_ACTIVE,
           loop_extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)

# (SA8) fire-config + flag OFF → silent (rollback).
run("(SA8) fire-config + flag OFF → silent (rollback)", "active_registry_section_absent",
    ledger("", pick="H-05 — driving", it=7, active=_MATURE_ACTIVE), False, flag=False)

# (SA9) fire-config + MANUAL → silent.
run("(SA9) fire-config + MANUAL → silent", "active_registry_section_absent",
    ledger("", pick="H-05 — driving", it=7, active=_MATURE_ACTIVE,
           loop_extra="- **HUNT-MODE: MANUAL**"), False)

# (SA10/MED-1 escape) the EXACT escape: the heading RENAMED `## Atom Registry` → `## Worklist` (the Worklist
# Driver marker stayed in the prose) + mature + pick → fire (a rename does not save from the adoption gate).
# KEEP: the Russian text in the fixture below ("гоню" = "driving", "машинный worklist ... для driver'а" =
# "machine worklist — SINGLE SOURCE for the driver") is a fixture input to the marker-matching regex (unsure) — left as-is
_RENAMED = ("# t\n\n## Loop State\n- **Iteration #:** 7\n- **Current pick:** AX-04 — гоню\n\n"
            "## Worklist (машинный worklist — SINGLE SOURCE для driver'а)\n\n"
            "| id | type | title | src | rank | status | closes |\n|---|---|---|---|---|---|---|\n"
            "| AX-04 | axis | band | D-05 | 30 | OPEN | - |\n\n## Active Hypotheses\n"
            "### H-05: x\n- **State:** A\n### H-06: y\n- **State:** A\n")
run("(SA10/MED-1) heading renamed `## Worklist` + mature + pick → fire (escape closed)",
    "active_registry_section_absent", _RENAMED, True)

# (SA11/iter-freeze) iter2 is frozen, BUT >=2 real ### H-NN + no section → fire (maturity by hypotheses).
run("(SA11/iter-freeze) iter2 + >=2 ### H-NN + no section → fire", "active_registry_section_absent",
    ledger("", pick="H-05 — driving", it=2, active=_MATURE_ACTIVE), True)

# ══════════════════════════════════════════════════════════════════════════════
print("── durability (axis-6): gates are read-only, do not move the ledger mtime → circuit_broken is not masked")


def durability_check():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "hypotheses.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(ledger(reg([("AX-04", "axis", "band", "D-05", "30", "OPEN", "-"),
                            ("AX-05", "axis", "gov", "T6-pair", "28", "OPEN", "-")]),
                       pick="my own axis off-registry", it=7))
    _cur["dir"] = d
    m0 = os.path.getmtime(p)
    old_flag = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        for _ in range(5):
            g.active_registry_unpopulated("sid")
            g.active_registry_drained_no_exit("sid")
            g.active_pick_not_from_queue("sid")
            g.active_atom_closed_without_narrative("sid")
        m1 = os.path.getmtime(p)
    finally:
        g.WORKLIST_DRIVER_ENABLED = old_flag
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if m0 == m1 else "FAIL"
    print("  [%s] mtime unchanged after 15 gate calls (5×3): before==after=%s" % (ok, m0 == m1))
    results.append(ok == "PASS")


durability_check()

# ── compute-and-name (axis-3): the directive NAMES the computed head, not just restates the rule ──
print("── compute-and-name (axis-3): the pick gate returns (relpath, head_str) with the head's id+rank")


def name_head_check():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "hypotheses.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(ledger(reg([("AX-04", "axis", "band-regression", "D-05", "35", "OPEN", "-"),
                            ("AX-05", "axis", "gov", "T6-pair", "20", "OPEN", "-")]),
                       pick="invented axis I set myself"))
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        res = g.active_pick_not_from_queue("sid")
        msg = g.PICK_NOT_FROM_QUEUE_REASON % res if res else ""
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    # KEEP: "ГОЛОВА РЕЕСТРА" ("REGISTRY HEAD") matches the hook's Russian message text (compared in code)
    ok = (isinstance(res, tuple) and "AX-04" in res[1] and "35" in res[1]
          and "AX-04" in msg and "ГОЛОВА РЕЕСТРА" in msg)
    print("  [%s] directive names head AX-04 (rank 35): head_str=%r"
          % ("PASS" if ok else "FAIL", res[1] if isinstance(res, tuple) else res))
    results.append(ok)


name_head_check()

# ── compact simulation (axis-6 durability, final judge): the registry = a section of the ledger FILE → survives compact ──
print("── compact-sim (axis-6): registry in a file → the verdict is stable across \"compact\" (re-read from the file)")


def compact_sim_check():
    """The registry lives in the ledger FILE, not in the LLM context. After compact (context reset) the gate re-reads
    the file and behaves IDENTICALLY — the state is not lost. We simulate: the verdict before and after "compact" (the file
    is untouched, the atoms are the same), + stability of the registry parse."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "hypotheses.md")
    lt = ledger(reg([("AX-04", "axis", "band", "D-05", "35", "OPEN", "-"),
                     ("AX-05", "axis", "gov", "T6-pair", "28", "OPEN", "-")]),
                pick="invented axis off-registry", it=7)
    with open(p, "w", encoding="utf-8") as f:
        f.write(lt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        v1 = bool(g.active_pick_not_from_queue("sid"))       # "before compact"
        atoms1 = g._valid_atoms(g._atom_rows(lt))
        # "compact": the context is reset, but the FILE is in place → the gate re-reads
        with open(p, "r", encoding="utf-8") as f:
            lt2 = f.read()
        v2 = bool(g.active_pick_not_from_queue("sid"))       # "after compact" (the same file read)
        atoms2 = g._valid_atoms(g._atom_rows(lt2))
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    ok = (v1 is True and v2 is True and v1 == v2
          and len(atoms1) == 2 and len(atoms2) == 2
          and [a["id"] for a in atoms1] == [a["id"] for a in atoms2])
    print("  [%s] registry durable across compact: fire before/after=%s/%s, atoms stable=%s"
          % ("PASS" if ok else "FAIL", v1, v2, [a["id"] for a in atoms2]))
    results.append(ok)


compact_sim_check()

print("── active_banked_atom_unsynced (FIX-5, ethena run 2026-08-12, judge): registry BANKED ↔ table empty")
# KEEP: the Russian table headers "Что" ("What") and "Статус" ("Status") below are parsed by the gate (column names) — left as-is
_BANK_TABLE = ("## Banked Findings\n\n| # | Severity | H-NN | Что | output | input | tier | found_by | Статус |\n"
               "|---|---|---|---|---|---|---|---|---|\n"
               "| 1 | Medium | D-02 | dust-window | supply in dust | admin redistribute | $10k | fanout | confirmed |\n")
_BANK_EMPTY = ("## Banked Findings\n\n| # | Severity | H-NN | Что | output | input | tier | found_by | Статус |\n"
               "|---|---|---|---|---|---|---|---|---|\n| | | | | | | | | |\n")
# (BAU-1 MAIN) the registry carries a BANKED atom, and the `## Banked Findings` section is ABSENT altogether → fire.
run("(BAU-1) BANKED atom + no Banked table → fire [FIX-5 split-brain]", "active_banked_atom_unsynced",
    ledger(reg([("H-05", "hypothesis", "active-lead", "D-01", "28", "ACTIVE", "-"),
                ("BK-02", "banked", "dust-window", "D-02", "14", "BANKED", "-")])), True)
# (BAU-1b) registry BANKED + the table exists, but an EMPTY placeholder row → fire.
run("(BAU-1b) BANKED atom + Banked table is an empty placeholder → fire", "active_banked_atom_unsynced",
    ledger(reg([("BK-03", "banked", "self-burn", "D-03", "14", "BANKED", "-")]), raw=_BANK_EMPTY), True)
# (BAU-2) registry BANKED + the Banked table filled with a real row → silent (in sync).
run("(BAU-2) BANKED atom + Banked table with a real row → silent", "active_banked_atom_unsynced",
    ledger(reg([("BK-02", "banked", "dust-window", "D-02", "14", "BANKED", "-")]), raw=_BANK_TABLE), False)
# (BAU-3) registry without BANKED atoms (all OPEN/ACTIVE) + an empty table → silent (nothing to sync).
run("(BAU-3) no BANKED atoms → silent", "active_banked_atom_unsynced",
    ledger(reg([("H-05", "hypothesis", "lead", "D-01", "28", "ACTIVE", "-"),
                ("AX-04", "axis", "next", "D-05", "20", "OPEN", "-")]), raw=_BANK_EMPTY), False)
# (BAU-4) HUNT-EXIT in the ledger → silent (submit path).
run("(BAU-4) BANKED atom + HUNT-EXIT → silent", "active_banked_atom_unsynced",
    ledger(reg([("BK-02", "banked", "dust", "D-02", "14", "BANKED", "-")]),
           verifier="- HUNT-EXIT: T4-CONFIRMED High\n"), False)
# (BAU-5) no `## Atom Registry` section at all (C1) → silent (_atom_rows None).
run("(BAU-5) no registry (C1) → silent", "active_banked_atom_unsynced",
    "# t\n\n## Loop State\n- **Iteration #:** 3\n\n## Active Hypotheses\n", False)

# ── Residual #3 (ethena run judge-3, MED): active_observed_fabricated ─────────────────────────────────
# FIX-A/FIX-F count `observed: File.sol:NNN` as depth without checking that the file exists (fabricable).
# If the src is co-located in the session folder — the cited basename MUST exist there. Fail-open: no
# tree / partial-resolve / layout mismatch → silent. Fires on near-certain fabrication.
print("── active_observed_fabricated (residual #3, judge-3 — observed:file:line verifiability)")


def run_src(name, fn_name, ledger_txt, src_files, expect, flag=True):
    """Like run(), but additionally lays out src files into the temp folder (a dict relpath→content
    or a list of relpaths). Checks FS verification of observed:file:line."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    for rel in (src_files or []):
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("// stub\ncontract X {}\n")
    _cur["dir"] = d
    old_flag = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = flag
    try:
        got = bool(getattr(g, fn_name)("sid"))
    finally:
        g.WORKLIST_DRIVER_ENABLED = old_flag
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


_REG_OBS = reg([("H-05", "hypothesis", "lead", "D-01", "28", "ACTIVE", "-"),
                ("AX-04", "axis", "band-regression", "D-05", "35", "OPEN", "-")])


def _obs(*cites):
    body = "".join("- DEPTH-TRACE layer%d observed: %s — value drift\n" % (i + 1, c)
                   for i, c in enumerate(cites))
    return "\n## Depth Traces\n" + body


# (OF-1 MAIN) the src tree exists (Vault.sol), but 2 observed citations point to nonexistent files of the same type → fire.
run_src("(OF-1) 2 fabricated observed (.sol tree exists, files do not) → fire", "active_observed_fabricated",
        _REG_OBS + _obs("src/Ghost.sol:42", "src/Phantom.sol:88"),
        ["src/Vault.sol", "src/Oracle.sol"], True)
# (OF-2) both citations resolve to real files → silent (plausible depth).
run_src("(OF-2) observed resolve to real files → silent", "active_observed_fabricated",
        _REG_OBS + _obs("src/Vault.sol:10", "src/Oracle.sol:20"),
        ["src/Vault.sol", "src/Oracle.sol"], False)
# (OF-3) partial: one resolves, one does not → silent (any-resolve → we do not punish).
run_src("(OF-3) partial (1 real + 1 fake) → silent (any-resolve)", "active_observed_fabricated",
        _REG_OBS + _obs("src/Vault.sol:10", "src/Ghost.sol:88"),
        ["src/Vault.sol"], False)
# (OF-4) fail-open: NO co-located src tree at all → silent (an absent clone cannot be verified).
run_src("(OF-4) no co-located src tree → silent (fail-open)", "active_observed_fabricated",
        _REG_OBS + _obs("src/Ghost.sol:42", "src/Phantom.sol:88"), [], False)
# (OF-5) <2 distinct citations → silent (too little data to judge).
run_src("(OF-5) 1 observed citation → silent (too little data)", "active_observed_fabricated",
        _REG_OBS + _obs("src/Ghost.sol:42"), ["src/Vault.sol"], False)
# (OF-6) layout mismatch: the tree is only .rs, citations are .sol → silent (type mismatch → we do not judge).
run_src("(OF-6) layout mismatch (.rs tree, .sol citations) → silent", "active_observed_fabricated",
        _REG_OBS + _obs("src/Ghost.sol:42", "src/Phantom.sol:88"),
        ["programs/lib.rs", "programs/state.rs"], False)
# (OF-7) MANUAL flag → silent.
run_src("(OF-7) HUNT-MODE: MANUAL → silent", "active_observed_fabricated",
        "**HUNT-MODE: MANUAL**\n\n" + _REG_OBS + _obs("src/Ghost.sol:42", "src/Phantom.sol:88"),
        ["src/Vault.sol"], False)
# (OF-8) no registry section (C1) → silent (_atom_rows None).
run_src("(OF-8) no registry (C1) → silent", "active_observed_fabricated",
        "# t\n\n## Loop State\n- **Iteration #:** 3\n" + _obs("src/Ghost.sol:42", "src/Phantom.sol:88"),
        ["src/Vault.sol"], False)
# (OF-9) dedup: the same fabricated citation ×3 = 1 distinct (<2) → silent (anti copy-paste citation inflation).
run_src("(OF-9) one fabricated citation ×3 (dedup <2) → silent", "active_observed_fabricated",
        _REG_OBS + _obs("src/Ghost.sol:42", "src/Ghost.sol:42", "src/Ghost.sol:42"),
        ["src/Vault.sol"], False)
# (OF-10) basename resolution ignores the directory: the citation `deep/Vault.sol` resolves to `src/Vault.sol` → silent.
run_src("(OF-10) basename resolution across different directories → silent (Vault.sol exists in src/)",
        "active_observed_fabricated",
        _REG_OBS + _obs("contracts/Vault.sol:10", "Oracle.sol:20"),
        ["src/Vault.sol", "src/Oracle.sol"], False)

# ── FIX-J (T4-backstop hardening, stress test 2026-08-12): active_t4_evidence_fabricated ──────────────
# the decomposition gate forces the FORM of T4, but does not catch fabrication (`forge test → PASS` written in, 0 runs).
# FIX-J: at the submit moment the cited artifact FILES (poc.log/exploit.t.sol/run.json) must exist
# co-located. Fail-open: no tree / inline-only / >=1 resolves → silent. A mirror of observed_fabricated.
print("── active_t4_evidence_fabricated (FIX-J, T4-backstop hardening)")


def _t4led(vlog):
    return ("# t\n\n## Loop State\n- **Iteration #:** 9\n- **Current pick:** H-01 done\n"
            "- **HUNT-EXIT: T4-CONFIRMED High**\n\n"
            + reg([("H-01", "hypothesis", "crit", "D-01", "60", "CLOSED", "-")])
            + "\n## Verifier Log\n" + vlog + "\n## Active Hypotheses\n")


# judge-6 FP fix: armed ONLY for PoC test files `.t.sol`/`.t.rs` (`.log`/`.json` dropped — decoy-prone).
# KEEP: "см." ("see") and "вывод в" ("output in") below are fixture evidence text for the T4 evidence parser (unsure) — left as-is
_VLOG_FILES = ("- 2026-08-12 — H-01 — verdict: PASS — checker:cold-subagent\n"
               "- evidence: forge test → PASS, см. test/Exploit.t.sol:42, confidence: 95%\n")
_VLOG_INLINE = ("- 2026-08-12 — H-01 — verdict: PASS — checker:cold-subagent\n"
                "- evidence: forge test → PASS, tx 0xdeadbeefdeadbeef1234, confidence: 95%\n")
_VLOG_LOG = ("- 2026-08-12 — H-01 — verdict: PASS — checker:cold-subagent\n"
             "- evidence: forge test → PASS, вывод в poc.log, confidence: 95%\n")

# (TE-1 MAIN) submit moment, the log refers to Exploit.t.sol, the co-located tree has a DIFFERENT .t.sol,
# but not this file → fabrication of a PoC test citation → fire.
run_src("(TE-1) HUNT-EXIT + citation Exploit.t.sol does NOT exist (.t.sol tree exists) → fire",
        "active_t4_evidence_fabricated", _t4led(_VLOG_FILES), ["test/Other.t.sol"], True)
# (TE-2) the citation resolves → silent (plausible).
run_src("(TE-2) cited Exploit.t.sol exists → silent",
        "active_t4_evidence_fabricated", _t4led(_VLOG_FILES), ["test/Exploit.t.sol"], False)
# (TE-3) fail-open: no test tree at all (only .sol source) → silent.
run_src("(TE-3) no co-located test tree (only .sol source) → silent (fail-open)",
        "active_t4_evidence_fabricated", _t4led(_VLOG_FILES), ["src/Vault.sol"], False)
# (TE-4) inline-only evidence (a fake tx, NOT a file) → silent (a recognized ceiling — the operator/harness territory).
run_src("(TE-4) inline-only (forge test/tx without a file) → silent (ceiling: inline is not caught)",
        "active_t4_evidence_fabricated", _t4led(_VLOG_INLINE), ["test/Other.t.sol"], False)
# (TE-5) not a submit moment (no HUNT-EXIT) → silent.
run_src("(TE-5) no HUNT-EXIT (not a submit) → silent",
        "active_t4_evidence_fabricated",
        ("# t\n\n## Loop State\n- **Iteration #:** 9\n- **Current pick:** H-01\n\n"
         + reg([("H-01", "hypothesis", "crit", "D-01", "60", "ACTIVE", "-")])
         + "\n## Verifier Log\n" + _VLOG_FILES + "\n## Active Hypotheses\n"), ["test/Other.t.sol"], False)
# (TE-6) MANUAL → silent.
run_src("(TE-6) HUNT-MODE: MANUAL → silent",
        "active_t4_evidence_fabricated",
        "**HUNT-MODE: MANUAL**\n\n" + _t4led(_VLOG_FILES), ["test/Other.t.sol"], False)
# (TE-7) partial: A.t.sol exists, B.t.sol does not → any-resolve → silent.
run_src("(TE-7) partial (A.t.sol exists, B.t.sol does not) → silent (any-resolve)",
        "active_t4_evidence_fabricated",
        _t4led("- evidence: A.t.sol + B.t.sol, verdict: PASS, confidence: 95%\n"),
        ["test/A.t.sol"], False)
# (TE-8) extension mismatch: the citation is .t.sol, the tree is only .t.rs → silent (type mismatch).
run_src("(TE-8) mismatch (citation Exploit.t.sol, tree only .t.rs) → silent",
        "active_t4_evidence_fabricated",
        _t4led("- evidence: Exploit.t.sol, verdict: PASS, confidence: 95%\n"), ["programs/poc.t.rs"], False)
# (TE-9) no registry (C1) → silent.
run_src("(TE-9) no registry (C1) → silent", "active_t4_evidence_fabricated",
        ("# t\n\n## Loop State\n- **HUNT-EXIT: T4-CONFIRMED High**\n\n## Verifier Log\n"
         + _VLOG_FILES + "\n## Active Hypotheses\n"), ["test/Other.t.sol"], False)
# (TE-10 JUDGE-6 FP) an honest Docker PoC: the log cites poc.log (output in the container), the session is littered with a
# decoy recon.log → `.log` is NOT armed → cited is empty → silent (NO false fire on an honest hunt).
run_src("(TE-10) honest Docker PoC: cite poc.log + session decoy recon.log → silent (FP fix judge-6)",
        "active_t4_evidence_fabricated", _t4led(_VLOG_LOG), ["recon.log", "scout.json"], False)

# ══════════════════════════════════════════════════════════════════════════════
print("── FEAT-G (jito run): active_axis_depth_below_ceiling — depth-per-axis floor (depth-trace N<5)")


def _gled(traces):
    """traces: a list of N — one depth-drive axis each with `proof:depth-trace N/5`."""
    # KEEP: "ось-%d" ("axis-%d") is a fixture bold-name key for the axis parser (unsure) — left as-is
    body = "".join(
        "  - **ось-%d (I-0%d)** · src:model · outcome:clean · close-grade:depth-drive ·\n"
        "    proof:depth-trace %d/5 (call→state→...)\n" % (i, i, n) for i, n in enumerate(traces, 1))
    return ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
                  raw="## Axes-Closed\n" + body)


# (G1) 1 depth-drive axis with depth-trace 3/5 (N<5) → FIRE (an early close below the ceiling).
run("(G1/FEAT-G) depth-drive axis depth-trace 3/5 → fire [below ceiling]",
    "active_axis_depth_below_ceiling", _gled([3]), True)
# (G2) depth-trace 5/5 (N>=5) → silent (brought up to the ceiling).
run("(G2/FEAT-G) depth-drive depth-trace 5/5 → silent [ceiling reached]",
    "active_axis_depth_below_ceiling", _gled([5]), False)
# (G3) depth-trace 6/6 (N>=5) → silent.
run("(G3/FEAT-G) depth-drive depth-trace 6/6 → silent",
    "active_axis_depth_below_ceiling", _gled([6]), False)
# (G4) mix: one 5/5, one 2/5 → FIRE (per-axis catches the early one, a global check would be satisfied).
run("(G4/FEAT-G) mix 5/5 + 2/5 → fire [per-axis catches the early one]",
    "active_axis_depth_below_ceiling", _gled([5, 2]), True)
# (G5) HUNT-EXIT → silent.
run("(G5/FEAT-G) depth-trace 3/5 + HUNT-EXIT → silent",
    "active_axis_depth_below_ceiling", _gled([3])[:-1] + "\n- **HUNT-EXIT: T4-CONFIRMED High**\n", False)
# (G6) flag off → silent (rollback).
run("(G6/FEAT-G) depth-trace 3/5 + flag off → silent", "active_axis_depth_below_ceiling", _gled([3]), False, flag=False)
# (G7) scout-verified (not depth-drive) with trace 2/5 → silent (not a depth-drive claim).
run("(G7/FEAT-G) scout-verified depth-trace 2/5 → silent (not depth-drive)",
    "active_axis_depth_below_ceiling",
    ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
           raw="## Axes-Closed\n  - **ось (I-01)** · close-grade:scout-verified · proof:depth-trace 2/5\n"), False)
# (G8 Z2 judge LOW, block-window bleed): depth-drive axis A (5/5, deep) — blank line — axis B (2/5).
# A must not absorb B's shallow trace (block boundary = bullet/blank line). Here B is also depth-drive → FIRE
# on B, but NOT falsely on A. We check that the count = 1 (only B), not 2 (A does not absorb).
_g8 = ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
             raw="## Axes-Closed\n"
                 "  - **ось-A (I-01)** · close-grade:depth-drive · proof:depth-trace 5/5 (deep)\n\n"
                 "  - **ось-B (I-02)** · close-grade:depth-drive · proof:depth-trace 2/5 (shallow)\n")
run("(G8/Z2 bleed) A(5/5) — blank — B(2/5): fire (B), A does NOT absorb → count=1",
    "active_axis_depth_below_ceiling", _g8, True)
# (G9 Z2 anti-bleed proof): depth-drive axis A WITHOUT its own number, a blank line, axis B(2/5) →
# A does NOT absorb B → A is not shallow; but B itself has no close-grade (proof-only) → A is deep → silent.
_g9 = ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
             raw="## Axes-Closed\n"
                 "  - **ось-A (I-01)** · close-grade:depth-drive · (no trace number here)\n\n"
                 "    proof:depth-trace 2/5 of a separate block\n")
run("(G9/Z2 bleed) A depth-drive without a number — blank — 2/5 → silent (A does not absorb across the boundary)",
    "active_axis_depth_below_ceiling", _g9, False)
# (G10 judge-2 LOW-6): proof on a NESTED sub-bullet (greater indent) — the axis block must NOT break
# (otherwise the depth-trace is not visible → a shallow axis is not flagged = an FN introduced by the bleed fix).
_g10 = ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
              raw="## Axes-Closed\n"
                  "  - **ось-A (I-01)** · src:model · outcome:clean · close-grade:depth-drive\n"
                  "    - proof: depth-trace 3/5 (nested sub-bullet)\n")
run("(G10/judge-2) proof on a NESTED sub-bullet (3/5) → fire (nesting does not break the block)",
    "active_axis_depth_below_ceiling", _g10, True)
# (G11 anti-FP) an ADJACENT axis of the same level still breaks the block (bleed protection preserved).
_g11 = ledger(reg([("H-01", "hypothesis", "cur", "D-01", "28", "ACTIVE", "-")]), pick="H-01", it=15,
              raw="## Axes-Closed\n"
                  "  - **ось-A (I-01)** · close-grade:depth-drive · (no number)\n"
                  "  - **ось-B (I-02)** · src:model · proof: depth-trace 2/5\n")
run("(G11/judge-2 anti-FP) an adjacent bullet of the SAME level breaks the block → silent (bleed protection intact)",
    "active_axis_depth_below_ceiling", _g11, False)

# ══════════════════════════════════════════════════════════════════════════════
print("── SUD-LOW-1 + R2 (jito run 2026-08-12): registry status normalizer + fanout visibility")
# the jito registry carried non-canonical statuses (CLOSED(ВЕЕР)/RUNNING/REFUTED) → the driver logic (status in
# OPEN/ACTIVE, ==CLOSED) did not recognize them → atoms in a status LIMBO. _norm_atom_status canonizes.


def _sl(name, raw_status, expect_canon):
    rows = g._atom_rows(reg([("AX-01", "axis", "t", "D-01", "20", raw_status, "-")]))
    got = rows[0]["status"] if rows else "??"
    ok = got == expect_canon
    print("  [%s] SUD-LOW-1 status '%s' → '%s' (expect '%s')" % ("PASS" if ok else "FAIL", raw_status, got, expect_canon))
    results.append(ok)


# KEEP: "CLOSED(ВЕЕР)" / "CLOSED(веер)" ("fan-out" in Cyrillic) are status-normalizer inputs (Russian logic values)
_sl("closed-veer", "CLOSED(ВЕЕР)", "CLOSED")
_sl("closed-veer-lat", "CLOSED(веер)", "CLOSED")
_sl("refuted", "REFUTED", "CLOSED")
_sl("killed", "KILLED", "CLOSED")
_sl("running", "RUNNING", "ACTIVE")
_sl("in-flight", "IN-FLIGHT", "ACTIVE")
_sl("pending", "PENDING", "OPEN")
_sl("banked-preserved", "BANKED", "BANKED")     # the special handling of the banked gates is preserved
_sl("parked-preserved", "PARKED", "PARKED")
_sl("open-canon", "OPEN", "OPEN")
_sl("active-canon", "ACTIVE", "ACTIVE")
_sl("unknown-passthrough", "WEIRD", "WEIRD")    # an unknown one is not lost (passthrough upper)

# Fanout visibility: a fan-out atom RUNNING(→ACTIVE) must NOT give a false ">1 ACTIVE" in the pick gate
# (fan-out = parallel generation, NOT a second single-pick DRIVE).
run("(SL-fanout) type:fanout RUNNING + main ACTIVE pick → pick-gate silent (fan-out ≠ a 2nd DRIVE)",
    "active_pick_not_from_queue",
    ledger(reg([("AX-01", "axis", "main-drive", "D-01", "30", "ACTIVE", "-"),
                ("AX-29", "fanout", "scout-fanout", "T1-partition", "25", "RUNNING", "-")]),
           pick="AX-01"), False)
# Control: TWO real ACTIVE (not fanout) still FIRE (single-pick violated).
run("(SL-fanout-ctl) 2 real ACTIVE (not fanout) → fire (single-pick violated)",
    "active_pick_not_from_queue",
    ledger(reg([("AX-01", "axis", "drive-a", "D-01", "30", "ACTIVE", "-"),
                ("AX-02", "axis", "drive-b", "D-02", "28", "ACTIVE", "-")]),
           pick="AX-01"), True)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
