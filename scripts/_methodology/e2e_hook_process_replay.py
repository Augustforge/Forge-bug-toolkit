#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E: hunt_completeness_gate AS A PROCESS (Stop-hook contract), not as importable functions.

Why: all the other replay tests monkeypatch `freshest_active_ledger` and call `active_*` directly.
That does NOT prove the hook WORKS end-to-end: stdin payload -> `hunt_is_active` (marker) -> search for the
freshest ledger -> cascade -> `{"decision":"block"}` / silent release. Final acceptance ("check that
everything really works and the behavior is what it should be").

Hook contract: stdin = JSON `{"session_id": …}`; block = stdout JSON `{"decision":"block","reason":…}`
+ exit 0; release = EMPTY stdout + exit 0.

The real sessions/ are untouched (unique slug `_e2etest_*`, cleanup in finally -- the fork_diff_gate_replay pattern).
NOTE: Russian text in the ledger fixtures and user/assistant messages below is test INPUT parsed by the
gate's Russian-aware regexes (e.g. "уходи"/"уходим" = "leave"/"we're leaving") and is kept as-is.
Run: py -3 -X utf8 scripts/_methodology/e2e_hook_process_replay.py
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOOK = os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py")
SESSIONS = os.path.join(ROOT, "sessions")

MATURE_MODEL = (
    "# system_model.md\n\n## Invariants\n"
    "- **I-01** [state] check: supply conserved pred: ENFORCED status: ENFORCED\n"
    "- **I-02** [state] check: rate monotonic pred: ENFORCED status: ENFORCED\n"
    "- **I-03** [state] check: accrual pred: ABSENT status: ABSENT\n"
    "\n## Divergences\n- **D-01** — accrual gap → H-03\n"
    "\n## Attention Gaps\n- gap-1 Vault.sol cold-audit-hole\n"
)

results = []
made = []


def sess(slug, ledger, model=MATURE_MODEL, files=()):
    d = os.path.join(SESSIONS, slug)
    made.append(d)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger)
    if model is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model)
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), slug))
    for fn in files:
        p = os.path.join(d, fn)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("artifact")
    return d


SCRATCH = os.environ.get("TEMP") or "/tmp"


# default assistant text "Продолжаю копать H-03." = "Continuing to dig into H-03."; user text "изучай таргет" = "study the target"
def _transcript(assistant_text="Продолжаю копать H-03.", user_text="изучай таргет"):
    """Fake transcript JSONL -- WITHOUT it main() does a fail-safe release (does not read last_*),
    and the ENTIRE main cascade (give-up/thin/structural) does not run. The real Stop hook always provides it."""
    p = os.path.join(SCRATCH, "_e2e_transcript.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": user_text}}) + "\n")
        f.write(json.dumps({"type": "assistant",
                            "message": {"role": "assistant", "content": assistant_text}}) + "\n")
    return p


# default assistant text "Запустил веер, продолжаю." = "Launched the fan-out, continuing."
def _transcript_bg(assistant_text="Запустил веер, продолжаю.", user_text="изучай таргет"):
    """Transcript with a background Workflow tool_use in flight (no task-notification) -> pending_bg_work
    returns (1, None). Timestamp deliberately omitted (age=None still enters the release branch)."""
    p = os.path.join(SCRATCH, "_e2e_transcript_bg.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": user_text}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": assistant_text},
            {"type": "tool_use", "name": "Workflow", "id": "wf_e2e_fanout", "input": {}},
        ]}}) + "\n")
    return p


def fire_hook(sid, assistant_text="Продолжаю копать H-03.", user_text="изучай таргет", transcript=None):
    """Run the hook AS A PROCESS with a real payload. -> (blocked: bool, reason: str, rc: int)"""
    payload = {"session_id": sid, "transcript_path": transcript or _transcript(assistant_text, user_text)}
    p = subprocess.run([sys.executable, "-X", "utf8", HOOK],
                       input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    out = (p.stdout or "").strip()
    if not out:
        return (False, "", p.returncode)
    try:
        j = json.loads(out)
        return (j.get("decision") == "block", j.get("reason", ""), p.returncode)
    except Exception:
        return (False, "UNPARSED:" + out[:200], p.returncode)


def check(name, cond, detail=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  -- " + detail) if (detail and not cond) else ""))
    results.append(bool(cond))


# ── Full "healthy" ledger that passes the submit cascade (success path) ────────────────────────────
# (Russian values below, e.g. "прочитаны" = "read", "забанкован" = "banked", are parsed by the gate -- kept as-is)
LOOP_HEALTHY = (
    "# t — Hypotheses Registry\n\n## Loop State\n"
    "- **Iteration #:** 12\n"
    "- **Current pick:** H-03\n"
    "- **Depth-Lead:** H-03 — 5/5 (call->state->external->hook->accounting)\n"
    "- **T9 restart axes used:** 2\n"
    "- **PARENT-FORK:** N/A — not a fork\n"
    "- **Platform:** Immunefi (TestTarget)\n"
    "- **Impacts in scope:** прочитаны (direct theft, insolvency)\n"
    "- **Out-of-Scope:** прочитан — centralization, best-practice\n"
    "- **PRIOR-PATTERNS:** 0 matched\n"
    "- **T11-VERDICT:** SKIP — не invariant-heavy\n"
    "- **EXPOSURE-SCAN:** DONE — 0 secrets\n"
    "- **LIBRARY: updated** — ERC4626-share fingerprint забанкован\n"
)

REGISTRY = (
    "\n## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n"
    "|---|---|---|---|---|---|---|\n"
    "| H-03 | hypothesis | share-inflation | D-01 | 30 | ACTIVE | - |\n"
    "| AX-01 | axis | vault-core | D-01 | 20 | CLOSED | H-01 |\n"
)
# Pre-submit atoms (§8 G-submit): the success exit requires them CLOSED in the registry + a proof entry in the narrative.
REGISTRY_SUBMIT = REGISTRY + (
    "| SUB-01 | submit-checklist | pre-submit gate H-03 | submission_checklist.yaml | 40 | CLOSED | H-03 |\n"
    "| REV-01 | external-review | cold-review H-03 перед подачей | T4-verifier | 38 | CLOSED | H-03 |\n"
)
SUBMIT_PROOF = (
    "\n## Axes-Closed\n"
    "- SUB-01 pre-submit gate · src:submission_checklist.yaml · outcome:clean · close-grade:executable · "
    "proof: auto_invalid/severity_cap/quality_required/project_tests пройдены\n"
    "- REV-01 external-review · src:T4-verifier · outcome:clean · close-grade:executable · "
    "proof: cold-агент подтвердил severity и payability\n"
)

DEPTH = (
    "\n## DEPTH-TRACE (T12)\n```\n"
    "L1 boundary: call->state\n   predicted: shares mint 1:1\n   observed: Vault.sol:120 rounding down\n   fan-in: mint <- deposit :88\n"
    "L2 boundary: state->external\n   predicted: rate stable\n   observed: Vault.sol:214 rate drift\n   fan-in: rate <- accrue :200\n"
    "L3 boundary: external->hook\n   predicted: hook no-op\n   observed: Hook.sol:44 reenter path\n   fan-in: hook <- call :40\n"
    "L4 boundary: hook->accounting\n   predicted: totals match\n   observed: Vault.sol:301 delta\n   fan-in: total <- burn :290\n"
    "L5 boundary: accounting->exit\n   predicted: exit exact\n   observed: Vault.sol:355 dust\n   fan-in: exit <- redeem :350\n```\n"
)

AXES = (
    "\n## Axes-Closed\n"
    "  - **vault-core (I-01)** · src:model · outcome:clean · close-grade:depth-drive · proof:depth-trace 5/5\n"
)

# FULL T4 -- all 9 sub-steps of `_T4_SUB` (otherwise T4-DECOMPOSITION blocks earlier in the success cascade).
# (Russian narrative text below is parsed/matched by the gate -- kept as-is.)
VERIFIER_FULL = (
    "\n## Verifier Log (T4)\n"
    "- **STEP 0 dedup:** Solodit + audits/ + known-issue — прогнан, no-match → чисто\n"
    "- **STEP 1.5 self-steelman:** сам написал case against — «это intended rounding?» опровергнуто Vault.sol:120\n"
    "- **checker:cold-subagent** (maker≠checker) — независимый general-purpose, холодный контекст\n"
    "- **verdict:** CONFIRM — share-inflation воспроизведён\n"
    "- **STEP 2.5 4 gates:** attack-execution ok → reachability ok → trigger ok → impact direct-theft\n"
    "- **evidence-artifact:** forge test stdout + trace, test/ShareInflation.t.sol, поток в poc.log\n"
    "- **current-exploitability:** deployed-code сверен на свежем блоке — жив СЕЙЧАС (не forkable history)\n"
    "- **STEP 2.6 fresh-runtime:** re-run на свежем форке — PoC PASS\n"
    "- **STEP 2.7 precondition negative-control matrix:** каждая precondition флипнута — PoC падает без неё\n"
    "- **confidence:** 85%\n"
    # T4-v2 3-agent (High/Crit): A3 cold integrator seam validity x payability (active_t4_integrator_missing)
    "- **T4-A3 [integrator]:** SEAM-CLEAR — overall CONFIRM — seam: validity-precond независим от scope-клаузы — checker:cold-subagent(blind)\n"
)

SUBMIT_FIELDS = (
    "- **OOS-CHECK:** share-inflation vs out-of-scope → PASS (не centralization)\n"
    "- **Final Reliability:** 72%\n"
    "- report-template: immunefi_dapp.md\n"
    "- **EXIT-KNOWLEDGE: DONE** — snapshot + undup_pattern + memory-INDEX забанкованы\n"
)

try:
    print("=== E2E: hunt_completeness_gate AS A PROCESS (Stop-hook contract) ===\n")

    # (1) NOT on a hunt (no marker) -> the hook is silent (meta conversations are not blocked)
    print("── (1) not on a hunt")
    b, r, rc = fire_hook("_e2etest_nohunt_absent")
    check("(1) no .hunt_active → release (empty stdout, rc=0)", (not b) and rc == 0, "b=%s rc=%s r=%s" % (b, rc, r[:80]))

    # (2) active hunt + thin ledger -> BLOCK (the loop holds)
    print("\n── (2) active hunt, thin ledger")
    sess("_e2etest_thin", "# t\n\n## Loop State\n- **Iteration #:** 1\n")
    b, r, rc = fire_hook("_e2etest_thin")
    check("(2) thin ledger → BLOCK (the loop holds the turn)", b and rc == 0, "b=%s rc=%s" % (b, rc))
    check("(2b) reason is non-empty and contains an instruction", bool(r and len(r) > 50), "len=%d" % len(r or ""))

    # (3) FEAT-A E2E: HUNT-EXIT High WITHOUT Final Reliability -> BLOCK specifically by the payability gate
    print("\n── (3) FEAT-A: HUNT-EXIT without Reliability")
    led3 = (LOOP_HEALTHY + "- **HUNT-EXIT: T4-CONFIRMED High**\n"
            + "- **OOS-CHECK:** finding vs out-of-scope → PASS\n"
            + REGISTRY + DEPTH + AXES + VERIFIER_FULL + "\n## Active Hypotheses\n")
    sess("_e2etest_norel", led3, files=("test/ShareInflation.t.sol",))
    b, r, rc = fire_hook("_e2etest_norel")
    check("(3) HUNT-EXIT without Reliability → BLOCK", b, "b=%s r=%s" % (b, (r or "")[:100]))
    check("(3b) blocks SPECIFICALLY FEAT-A (LOW-RELIABILITY in reason)", "RELIABILITY" in (r or "").upper(),
          "reason head: " + (r or "")[:160])

    # (4) FEAT-A E2E: Reliability 40% (<50) -> still BLOCK (do not submit even High)
    print("\n── (4) FEAT-A: Reliability 40% (<50)")
    led4 = led3.replace("## Active Hypotheses", "- **Final Reliability:** 40%\n\n## Active Hypotheses")
    sess("_e2etest_lowrel", led4, files=("test/ShareInflation.t.sol",))
    b, r, rc = fire_hook("_e2etest_lowrel")
    check("(4) Reliability 40% → BLOCK (payability gate)", b and "RELIABILITY" in (r or "").upper(),
          "b=%s r=%s" % (b, (r or "")[:120]))

    # (5) MAIN: a full correct success exit -> RELEASE (the hunt CAN finish)
    print("\n── (5) full correct success exit")
    led5 = (LOOP_HEALTHY + "- **HUNT-EXIT: T4-CONFIRMED High**\n" + SUBMIT_FIELDS
            + REGISTRY_SUBMIT + DEPTH + AXES + SUBMIT_PROOF + VERIFIER_FULL + "\n## Active Hypotheses\n")
    sess("_e2etest_exit_ok", led5, files=("test/ShareInflation.t.sol",))
    b, r, rc = fire_hook("_e2etest_exit_ok")
    check("(5) HUNT-EXIT + Reliability 72% + OOS + T4 + LIBRARY → RELEASE (the hunt finishes)",
          (not b) and rc == 0, "b=%s rc=%s reason=%s" % (b, rc, (r or "")[:300]))

    # (6) MANUAL mode: the emergency brake does not hold routinely
    print("\n── (6) HUNT-MODE: MANUAL")
    sess("_e2etest_manual", LOOP_HEALTHY + "- **HUNT-MODE: MANUAL**\n" + REGISTRY + "\n## Active Hypotheses\n")
    b, r, rc = fire_hook("_e2etest_manual")
    check("(6) MANUAL + no give-up → RELEASE (emergency off works)", (not b) and rc == 0,
          "b=%s r=%s" % (b, (r or "")[:150]))

    # (7) give-up lexicon on an active hunt -> BLOCK (anti-give-up is alive after all edits)
    print("\n── (7) give-up on an active hunt")
    sess("_e2etest_giveup", LOOP_HEALTHY + REGISTRY + DEPTH + AXES + "\n## Active Hypotheses\n")
    # give-up lives in the LAST assistant message (transcript), not in the ledger -- that is how the real hook sees it
    # (assistant text: "Target hardened, no bugs. Suggest a pivot to another project -- bad EV." kept Russian: give-up phrasing fixture)
    b, r, rc = fire_hook("_e2etest_giveup",
                         assistant_text="Таргет hardened, багов нет. Предлагаю пивот на другой проект — bad EV.")
    check("(7) give-up lexicon → BLOCK (anti-give-up not broken)", b, "b=%s r=%s" % (b, (r or "")[:120]))

    # (8) FEAT-B E2E: Immunefi + HUNT-EXIT + Reliability ok, but template not chosen -> BLOCK by the template gate
    print("\n── (8) FEAT-B: Immunefi without report-template")
    led8 = led5.replace("- report-template: immunefi_dapp.md\n", "")
    sess("_e2etest_notmpl", led8, files=("test/ShareInflation.t.sol",))
    b, r, rc = fire_hook("_e2etest_notmpl")
    # "ШАБЛОН" = "TEMPLATE" (Russian), compared against the hook's reason text -- kept as-is
    check("(8) Immunefi exit without a template → BLOCK (FEAT-B in the success cascade)",
          b and ("TEMPLATE" in (r or "").upper() or "ШАБЛОН" in (r or "").upper()),
          "b=%s r=%s" % (b, (r or "")[:160]))

    # (9) parallel-during-fanout: fan-out (Workflow) in the background + a LIVE thread -> BLOCK parallel-drive
    #     (the agent does NOT idle, it drives the thread serially in parallel with the fan-out). Before: release -> waited 20-30 min.
    print("\n── (9) parallel-during-fanout: fan-out in background + live thread")
    led9 = ("# t\n\n## Loop State\n- **Iteration #:** 4\n"
            "- **Depth-Lead:** H-03 Vault.sol:120 — 3/5\n\n"
            "## Active Hypotheses\n### H-03: share-inflation\n- State: A\n")
    sess("_e2etest_paralleldrive", led9)
    b, r, rc = fire_hook("_e2etest_paralleldrive", transcript=_transcript_bg())
    check("(9) fan-out in background + live thread → BLOCK (parallel-drive, no idling)",
          b and "PARALLEL-DRIVE" in (r or "").upper(), "b=%s r=%s" % (b, (r or "")[:160]))

    # (10) control: fan-out in background, BUT no live thread (first scout pass) -> RELEASE (wait for scout as before).
    print("\n── (10) parallel-during-fanout control: fan-out in background, no live thread")
    led10 = ("# t\n\n## Loop State\n- **Iteration #:** 1\n- **Depth-Lead:** none yet\n\n"
             "## Active Hypotheses\n\n")
    sess("_e2etest_bgnolead", led10)
    b, r, rc = fire_hook("_e2etest_bgnolead", transcript=_transcript_bg())
    check("(10) fan-out in background + no live thread → RELEASE (first scout pass waits)",
          (not b) and rc == 0, "b=%s rc=%s r=%s" % (b, rc, (r or "")[:120]))

    # (11) release on a bare "уходи" ("leave"): the operator says "здесь уходи" ("leave here") -> RELEASE.
    # (user text "здесь уходи ты не охотник ты чинишь систему" = "leave here, you're not a hunter, you're fixing the system" -- kept Russian: release-word fixture)
    print("\n── (11) release detection of a bare «уходи» (\"leave\")")
    sess("_e2etest_uhodi", "# t\n\n## Loop State\n- **Iteration #:** 1\n", model=None)  # trivial -> release is clean of ek
    b, r, rc = fire_hook("_e2etest_uhodi", user_text="здесь уходи ты не охотник ты чинишь систему")
    check("(11) operator «уходи» (\"leave\") → RELEASE", (not b) and rc == 0, "b=%s rc=%s" % (b, rc))
    # (12) anti-FP: "пока не уходи" ("don't leave yet") -> NOT release (thin ledger -> BLOCK held).
    print("\n── (12) anti-FP: «не уходи» (\"don't leave\") does not release")
    sess("_e2etest_neuhodi", "# t\n\n## Loop State\n- **Iteration #:** 1\n")
    b, r, rc = fire_hook("_e2etest_neuhodi", user_text="пока не уходи, копай дальше эту нить")
    check("(12) «не уходи» (\"don't leave\") → NOT release (the loop holds a thin ledger)", b, "b=%s r=%s" % (b, (r or "")[:80]))

    # (13) EXIT-KNOWLEDGE: "уходим" ("we're leaving") + real work + data NOT entered -> BLOCK reminder.
    print("\n── (13) exit-knowledge: «уходим» (\"we're leaving\") without banking knowledge")
    led13 = "# t\n\n## Loop State\n- **Iteration #:** 5\n" + REGISTRY + "\n## Active Hypotheses\n"
    sess("_e2etest_ek_pending", led13)   # MATURE_MODEL by default -> substance=True
    b, r, rc = fire_hook("_e2etest_ek_pending", user_text="ок уходим с этого таргета")
    check("(13) «уходим» + work without EXIT-KNOWLEDGE → BLOCK (enter snapshot/pattern/memory)",
          b and "EXIT-KNOWLEDGE" in (r or "").upper(), "b=%s r=%s" % (b, (r or "")[:160]))

    # (14) EXIT-KNOWLEDGE: DONE -> RELEASE + marker cleanup (its own .hunt_active removed).
    print("\n── (14) exit-knowledge: DONE → release + marker cleanup")
    led14 = led13 + "- **EXIT-KNOWLEDGE: DONE** — snapshot+pattern+memory\n"
    d14 = sess("_e2etest_ek_done", led14)
    b, r, rc = fire_hook("_e2etest_ek_done", user_text="ок уходим")
    marker_gone = not os.path.exists(os.path.join(d14, ".hunt_active"))
    check("(14) «уходим» + EXIT-KNOWLEDGE DONE → RELEASE + marker removed",
          (not b) and rc == 0 and marker_gone, "b=%s rc=%s marker_gone=%s" % (b, rc, marker_gone))

    # (15) control: "уходим" + a trivial hunt (no substance) -> RELEASE (nothing to bank).
    print("\n── (15) exit-knowledge control: trivial hunt")
    sess("_e2etest_ek_trivial", "# t\n\n## Loop State\n- **Iteration #:** 1\n", model=None)
    b, r, rc = fire_hook("_e2etest_ek_trivial", user_text="уходим отсюда")
    check("(15) «уходим» + trivial hunt (no work) → RELEASE (nothing to bank)",
          (not b) and rc == 0, "b=%s rc=%s" % (b, rc))

    # (16) success HUNT-EXIT, but EXIT-KNOWLEDGE not entered -> BLOCK (knowledge banking on success too).
    print("\n── (16) exit-knowledge on the success exit")
    led16 = led5.replace("- **EXIT-KNOWLEDGE: DONE** — snapshot + undup_pattern + memory-INDEX забанкованы\n", "")
    sess("_e2etest_ek_success", led16, files=("test/ShareInflation.t.sol",))
    b, r, rc = fire_hook("_e2etest_ek_success")
    check("(16) success exit without EXIT-KNOWLEDGE → BLOCK (knowledge banking forced on success too)",
          b and "EXIT-KNOWLEDGE" in (r or "").upper(), "b=%s r=%s" % (b, (r or "")[:160]))

finally:
    for d in made:
        shutil.rmtree(d, ignore_errors=True)

ok = sum(1 for x in results if x)
print("\n%d/%d E2E process-level cases green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
