#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for Worklist Driver Stage 3, Layer-3 (verifier channel) -- T4 DECOMPOSITION.

Plan §1 Layer-3 / §2 rubric axis-4: "T4 = the full set of sub-steps (STEP 0/2.5-4gate/2.6/2.7 + evidence +
confidence) with proof fields, NOT the fact of a `T4: PASS` line". The gate `active_t4_decomposition_incomplete`
fires ONLY at the submit moment (`HUNT-EXIT` declared) and requires 5 markers in `## Verifier Log`:
  STEP 0 dedup · checker:cold-subagent (B5) · terminal verdict · STEP 2.6 fresh-runtime ·
  STEP 2.7 precondition-matrix.
Source of the rule: Technique 4 STEP 3 ("verifier-log missing fresh-runtime (2.6) or the
precondition matrix (2.7) -> not submit-ready") -- it was skippable as prose, now it is a hook.

Rule (feedback_hook_must_prove_firing): the test PROVES firing on the real shape of the miss ("verdict:
confirm" and nothing else) + the off-switch + anti-self-reading (a `>`-blockquote guide in the section does not count as work).
Exit 1 on any FAIL. Run: py -3 -X utf8 scripts/_methodology/t4_decomposition_replay.py

NOTE on kept Russian: the Verifier Log fixture records (FULL_T4, THIN_T4, VLOG_H05, banked/guide fixtures) are
inputs to the gate's marker regexes (including Russian outcome markers such as the dedup "clean"/"MATCH" words and the
"N/A" escape line) and are kept verbatim in Russian, together with every .replace() target that must match them.
Comments and test names are English.
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

results = []


def run(name, ledger_txt, expect, flag=True, expect_missing=None):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = flag
    try:
        res = g.active_t4_decomposition_incomplete("sid")
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    got = bool(res)
    ok = got == expect
    if ok and expect_missing and res:
        ok = expect_missing.lower() in res[1].lower()
    print("  [%s] %s: fired=%s expect=%s%s" % ("PASS" if ok else "FAIL", name, got, expect,
          (" missing=%r" % res[1][:70]) if res else ""))
    results.append(ok)


HDR = "# t — Registry\n\n**Target:** x\n"
EXIT = "\nHUNT-EXIT: T4-CONFIRMED High\n"
TAIL = "\n## Active Hypotheses\n### H-01: t\n- State: D\n"

# The canonical FULL T4 (7 sub-steps + confidence>=80) -- as in the template.
FULL_T4 = (
    "\n## Verifier Log (T4)\n"
    "- 2026-08-11 — H-01 — **STEP 0 dedup:** прогнал audits/*.pdf + Solodit по core-nouns → чисто — "
    "**STEP 1.5 self-steelman:** case против — «может, это intended rounding» — опровергнут: NatSpec "
    "требует симметрии — **verdict: PASS** — `checker:cold-subagent` — **STEP 2.5 gates:** gate1 "
    "attack-execution guard не рвёт; gate2 reachability достижимо; gate3 trigger unprivileged; gate4 "
    "impact LP теряют — **STEP 2.6 fresh-runtime:** re-provisioned fresh "
    "fork@21050000, cheatcode-state сброшен → PoC PASS — **STEP 2.7 precondition-matrix:** "
    "precond-1 (empty-pool) OFF → not-fires; precond-2 (fee=0) OFF → still-fires; unstated-surfaced: "
    "pre-funded balance — **evidence-artifact:** forge test trace, tx 0xabc123def4567890 — "
    "**current-exploitability:** deployed code-hash сверен с HEAD на current block → баг жив — "
    "**confidence:** 85% — **undup_origin:** composition-seam\n")

# A thin record -- exactly what was missed before ("T4: PASS" and nothing else).
THIN_T4 = "\n## Verifier Log (T4)\n- 2026-08-11 — H-01 — verifier verdict: confirm — looks valid\n"

# ══════════════════════════════════════════════════════════════════════════════
print("── FIRING: submit moment with an INCOMPLETE T4")

run("(a) HUNT-EXIT + thin record 'verdict: confirm' → fire (not submit-ready)",
    HDR + EXIT + THIN_T4 + TAIL, True, expect_missing="STEP 2.6")

run("(b) HUNT-EXIT + empty Verifier Log → fire (no T4 at all)",
    HDR + EXIT + "\n## Verifier Log (T4)\n" + TAIL, True)

run("(c) HUNT-EXIT + no Verifier Log section → fire",
    HDR + EXIT + TAIL, True)

# partial T4: dedup+verdict+cold present, but NO 2.6/2.7 (exactly the STEP 3 "not submit-ready" case).
run("(d) HUNT-EXIT + dedup+verdict+cold, but without 2.6/2.7 → fire (STEP 3)",
    HDR + EXIT + "\n## Verifier Log (T4)\n- 2026-08-11 — H-01 — STEP 0 dedup: Solodit чисто — "
    "verdict: PASS — `checker:cold-subagent`\n" + TAIL, True, expect_missing="2.6")

# warm-main checker (B5 miss: a warm main agent instead of a cold one) -> fire.
run("(e) HUNT-EXIT + full T4, but checker:warm-main → fire (B5 cold is mandatory)",
    HDR + EXIT + FULL_T4.replace("`checker:cold-subagent`", "`checker:warm-main`") + TAIL,
    True, expect_missing="cold-subagent")

print("\n── SILENT: full T4 / not the submit moment / off-switch")

run("(f) HUNT-EXIT + FULL T4 (5 sub-steps) → silent (submit-ready)",
    HDR + EXIT + FULL_T4 + TAIL, False)

run("(g) NO HUNT-EXIT + thin record → silent (not the submit moment, the gate sleeps)",
    HDR + THIN_T4 + TAIL, False)

run("(h) HUNT-EXIT + thin record + MANUAL → silent",
    HDR + EXIT + THIN_T4 + "\nHUNT-MODE: MANUAL\n" + TAIL, False)

run("(i) HUNT-EXIT + thin record + flag OFF → silent (rollback)",
    HDR + EXIT + THIN_T4 + TAIL, False, flag=False)

# void-exit (HUNT-EXIT cancelled by SUPERSEDED) -> not the submit moment -> silent.
run("(j) HUNT-EXIT SUPERSEDED (void) + thin record → silent (not the submit moment)",
    HDR + EXIT + "\n- HUNT-EXIT above SUPERSEDED by this reversal — finding withdrawn.\n"
    + THIN_T4 + TAIL, False)

print("\n── anti-self-reading: the `>`-blockquote guide of the section does NOT count as work done")

# The guide block (as in the template) contains ALL the marker words. If the gate read it, it would always be silent.
GUIDE_ONLY = (
    "\n## Verifier Log (T4)\n"
    "> 🔴 ПОЛНЫЙ T4 перед подачей. Нужны: STEP 0 dedup · `checker:cold-subagent` · терминальный "
    "verdict: PASS/DOWNGRADE/BLOCK/REJECT · STEP 2.6 fresh-runtime · STEP 2.7 precondition-matrix.\n"
    "- {timestamp} — H-{NN} — verifier verdict: confirm / kill — `checker:cold-subagent|warm-main`\n")
run("(k) HUNT-EXIT + only the guide block and a placeholder → fire (guide ≠ work)",
    HDR + EXIT + GUIDE_ONLY + TAIL, True)

print("\n── judge axis-4 D1/D2/D4/D7: completeness of sub-steps, confidence>=80, OUTCOME (not just a mention)")

# (D1) complete by the old 5, but WITHOUT STEP 1.5 steelman and STEP 2.5 gates -> fire (the rubric requires 7).
_no15 = FULL_T4.replace("**STEP 1.5 self-steelman:** case против — «может, это intended rounding» — "
                        "опровергнут: NatSpec требует симметрии — ", "")
run("(D1a) without STEP 1.5 self-steelman → fire", HDR + EXIT + _no15 + TAIL, True, expect_missing="1.5")

_no25 = FULL_T4.replace("**STEP 2.5 gates:** gate1 attack-execution guard не рвёт; gate2 reachability "
                        "достижимо; gate3 trigger unprivileged; gate4 impact LP теряют — ", "")
run("(D1b) without the STEP 2.5 four gates → fire", HDR + EXIT + _no25 + TAIL, True, expect_missing="2.5")

# (D2) confidence missing / below 80 -> fire (<80 = LEAD, not submit).
run("(D2a) full T4, but WITHOUT confidence → fire",
    HDR + EXIT + FULL_T4.replace(" — **confidence:** 85%", "") + TAIL, True, expect_missing="confidence")
run("(D2b) confidence: 40% (<80) → fire (this is a LEAD, not a submit)",
    HDR + EXIT + FULL_T4.replace("85%", "40%") + TAIL, True, expect_missing="confidence")
run("(D2c) confidence: 80% exactly → silent (threshold inclusive)",
    HDR + EXIT + FULL_T4.replace("85%", "80%") + TAIL, False)

# (D4) OUTCOME: a dedup with a MATCH (duplicate = KILL) and a PoC FAIL on fresh (residue = KILL) must NOT pass.
run("(D4a) STEP 0 dedup found a MATCH (duplicate) → fire (not 'clean')",
    HDR + EXIT + FULL_T4.replace("по core-nouns → чисто", "по core-nouns → МАТЧ audit M-04 (дубль)")
    + TAIL, True, expect_missing="STEP 0")
run("(D4b) STEP 2.6 fresh-runtime → PoC FAIL (the bug lived in residue) → fire",
    HDR + EXIT + FULL_T4.replace("cheatcode-state сброшен → PoC PASS", "cheatcode-state сброшен → PoC FAIL")
    + TAIL, True, expect_missing="2.6")

print("\n── D3 (§8 G-submit): the submit-checklist AS A registry ATOM, not an enum")

REG = ("\n## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n|---|---|---|---|---|---|---|\n"
       "| AX-04 | axis | band | code-read | 35 | CLOSED | H-01 |\n")
SC_ATOM = "| SC-01 | submit-checklist | pre-submit H-01 | submission_checklist | 30 | CLOSED | H-01 |\n"


def run_sc(name, ledger_txt, expect, flag=True):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = flag
    try:
        got = bool(g.active_submit_checklist_atom_missing("sid"))
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    ok = got == expect
    print("  [%s] %s: fired=%s expect=%s" % ("PASS" if ok else "FAIL", name, got, expect))
    results.append(ok)


run_sc("(D3a) HUNT-EXIT + registry WITHOUT a submit-checklist atom → fire", HDR + EXIT + REG + TAIL, True)
run_sc("(D3b) HUNT-EXIT + submit-checklist CLOSED → silent", HDR + EXIT + REG + SC_ATOM + TAIL, False)
run_sc("(D3c) submit-checklist in OPEN status (not run) → fire",
       HDR + EXIT + REG + SC_ATOM.replace("| CLOSED |", "| OPEN |") + TAIL, True)
run_sc("(D3d) NO Atom Registry section (C1 legacy/web) → silent (zero blast radius)",
       HDR + EXIT + TAIL, False)
run_sc("(D3e) NO HUNT-EXIT (not the submit moment) → silent", HDR + REG + TAIL, False)
run_sc("(D3f) HUNT-EXIT + no atom + flag OFF → silent (rollback)", HDR + EXIT + REG + TAIL, False, flag=False)

print("\n── red-team RT-D1 (HIGH): re-confirm-after-void — positional logic, not a naive void-search")

# RT-D1: HUNT-EXIT -> SUPERSEDED -> a NEW HUNT-EXIT (a legit re-confirmation). ledger_success_exit=True
# (positionally), so the success path ENTERS -> the T4 gate MUST work. A naive `_EXIT_VOID_RE.search`
# stayed silent (a void is higher up in the text) -> a thin T4 was released on the riskiest population.
_RECONFIRM = (EXIT + "\n- HUNT-EXIT above SUPERSEDED by this reversal — finding withdrawn.\n"
              + "\nHUNT-EXIT: T4-CONFIRMED Critical — re-confirmed with a new fork PoC.\n")
run("(RT-D1a) re-confirm-after-void + THIN T4 → fire (the gate does not sleep on a re-confirmation)",
    HDR + _RECONFIRM + THIN_T4 + TAIL, True)
run("(RT-D1b) re-confirm-after-void + FULL T4 → silent (a valid release)",
    HDR + _RECONFIRM + FULL_T4 + TAIL, False)
# control: a void WITHOUT a re-confirmation -> the success path is not entered -> the gate sleeps (as before).
run("(RT-D1c) void without a re-confirmation → silent (not the submit moment)",
    HDR + EXIT + "\n- HUNT-EXIT above SUPERSEDED by this reversal — withdrawn.\n" + THIN_T4 + TAIL, False)

print("\n── red-team RT-D3/D4/D5: anti-FP on LEGIT wording (do not punish rewriting valid work)")

# RT-D3: a legit record with solidity/JSON braces in the body -> the line must NOT be dropped as a placeholder.
_BRACES = FULL_T4.replace("pre-funded balance", "pre-funded balance; state balances[addr] = {0}")
run("(RT-D3) full T4 + solidity braces `{0}` in the line → silent (not a placeholder)",
    HDR + EXIT + _BRACES + TAIL, False)
# control: a REAL canonical template line (with {timestamp}/{NN}) does not count as work.
run("(RT-D3-ctrl) only the template line `- {timestamp} — H-{NN} — verdict: …` → fire (template ≠ work)",
    HDR + EXIT + "\n## Verifier Log (T4)\n- {timestamp} — H-{NN} — verifier verdict: confirm — "
    "`checker:cold-subagent` — STEP 0 dedup — STEP 1.5 steelman — STEP 2.5 gate1 — STEP 2.6 "
    "fresh-runtime PoC PASS — STEP 2.7 precondition-matrix — confidence: 90%\n" + TAIL, True)

# RT-D4/D5: a natural ENGLISH wording of a full T4 record (without `checker:`, without the word verdict).
_EN = ("\n## Verifier Log (T4)\n"
       "- 2026-08-11 — H-01 — STEP 0 dedup: audits + Solodit checked → clean, no match — "
       "STEP 1.5 self-steelman: strongest case against — rounding may be intended — refuted by NatSpec — "
       "Result: CONFIRMED — verified independently by a cold subagent in fresh context — "
       "STEP 2.5 gates: gate1 attack-execution ok; gate2 reachability ok; gate3 trigger unprivileged; "
       "gate4 impact LPs lose — STEP 2.6: fresh fork re-provisioned at current block → PoC PASS — "
       "STEP 2.7 negative-control matrix: precond-1 off → not-fires; unstated: pre-funded — "
       "evidence: forge test trace + receipt 0xdeadbeef12345678 — "
       "current-exploitability: verified against deployed code-hash at current block — "
       "confidence: 88%\n")
run("(RT-D4/D5) English full T4 (`cold subagent` without `checker:`, `Result: CONFIRMED`) → silent",
    HDR + EXIT + _EN + TAIL, False)

print("\n── re-judge D1/D3: evidence-artifact + current-exploitability (named in anchor-10)")

run("(D1) full T4 WITHOUT evidence-artifact → fire",
    HDR + EXIT + FULL_T4.replace("**evidence-artifact:** forge test trace, tx 0xabc123def4567890 — ", "")
    + TAIL, True, expect_missing="evidence")
run("(D3) full T4 WITHOUT current-exploitability → fire",
    HDR + EXIT + FULL_T4.replace("**current-exploitability:** deployed code-hash сверен с HEAD на "
                                 "current block → баг жив — ", "") + TAIL, True, expect_missing="current-exploit")

print("\n── re-judge D6/D7: marker precision (a spoof does not pass, a legit one is not chopped)")

# D6: a bare `reachability` in prose no longer counts all 4 STEP 2.5 gates.
_one_word = FULL_T4.replace("**STEP 2.5 gates:** gate1 attack-execution guard не рвёт; gate2 reachability "
                            "достижимо; gate3 trigger unprivileged; gate4 impact LP теряют",
                            "checked reachability")
run("(D6) the single word `reachability` instead of 4 gates → fire (the set is not counted)",
    HDR + EXIT + _one_word + TAIL, True, expect_missing="2.5")
# D7: legit braced tokens (`{nonce}`, `{blockNumber}`) are NOT counted as a template placeholder.
run("(D7) full T4 + legit `{nonce}`/`{blockNumber}` in the line → silent (not a placeholder)",
    HDR + EXIT + FULL_T4.replace("pre-funded balance", "pre-funded {nonce} at {blockNumber}") + TAIL, False)

print("\n── re-judge D2 (§8 G-peer): external-review atom on a CRITICAL submission")


def run_gate(fn_name, name, ledger_txt, expect, flag=True):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = flag
    try:
        got = bool(getattr(g, fn_name)("sid"))
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    ok = got == expect
    print("  [%s] %s: fired=%s expect=%s" % ("PASS" if ok else "FAIL", name, got, expect))
    results.append(ok)


EXIT_CRIT = "\nHUNT-EXIT: T4-CONFIRMED Critical\n"
ER_ROW = "| ER-01 | external-review | tier classification | judge | 30 | CLOSED | H-01 |\n"

run_gate("active_external_review_atom_missing", "(D2a) CRITICAL + registry without external-review → fire",
         HDR + EXIT_CRIT + REG + FULL_T4 + TAIL, True)
run_gate("active_external_review_atom_missing", "(D2b) CRITICAL + external-review CLOSED → silent",
         HDR + EXIT_CRIT + REG + ER_ROW + FULL_T4 + TAIL, False)
run_gate("active_external_review_atom_missing", "(D2c) HIGH (not Critical) → silent (G-peer: Crit only)",
         HDR + EXIT + REG + FULL_T4 + TAIL, False)
# KEPT RU: the N/A escape line below is matched by the gate's N/A regex; the tail text is free-form.
run_gate("active_external_review_atom_missing", "(D2d) CRITICAL + `external-review: N/A — not needed` → silent",
         HDR + EXIT_CRIT + REG + "\nexternal-review: N/A — тривиальная классификация\n" + FULL_T4 + TAIL, False)
run_gate("active_external_review_atom_missing", "(D2e) CRITICAL without a registry (C1 legacy) → silent",
         HDR + EXIT_CRIT + FULL_T4 + TAIL, False)

print("\n── re-judge D4: banked `confirmed` without a T4 record (a batch of Mediums leaves without verification)")

# KEPT RU: the banked-table header cells "Что" ("What") and "Статус" ("Status") are parser input.
BANKED_CONF = ("\n## Banked Findings\n| Severity | H-NN | Что | output | input | tier | found_by | Статус |\n"
               "|---|---|---|---|---|---|---|---|\n"
               "| Medium | H-05 | oracle conf-strip | over-val | — | $3K | scan | confirmed |\n")
BANKED_PEND = BANKED_CONF.replace("| confirmed |", "| confirmed / T4-pending |")
VLOG_H05 = ("\n## Verifier Log (T4)\n- 2026-08-11 — H-05 — STEP 0 dedup: чисто — verdict: PASS — "
            "`checker:cold-subagent` — STEP 2.6 fresh-runtime: PoC PASS — STEP 2.7 precondition-matrix: "
            "precond-1 OFF → not-fires — confidence: 82%\n")

run_gate("active_banked_without_t4", "(D4a) banked confirmed H-05 + NO record in the Verifier Log → fire",
         HDR + BANKED_CONF + TAIL, True)
run_gate("active_banked_without_t4", "(D4b) banked confirmed H-05 + a T4 record present → silent",
         HDR + BANKED_CONF + VLOG_H05 + TAIL, False)
run_gate("active_banked_without_t4", "(D4c) status `confirmed / T4-pending` → silent (not being submitted yet)",
         HDR + BANKED_PEND + TAIL, False)
run_gate("active_banked_without_t4", "(D4d) banked + HUNT-EXIT → silent (the submit gates cover it)",
         HDR + EXIT + BANKED_CONF + TAIL, False)
run_gate("active_banked_without_t4", "(D4e) no banked rows → silent", HDR + TAIL, False)
run_gate("active_banked_without_t4", "(D4f) banked confirmed + flag OFF → silent (rollback)",
         HDR + BANKED_CONF + TAIL, False, flag=False)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
