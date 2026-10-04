# -*- coding: utf-8 -*-
"""End-to-end smoke: runs hunt_completeness_gate.py as a REAL Stop hook (subprocess, real stdin JSON),
with a temporary session under the real sessions/ dir (a marker with a test sid = armed new session).
Checks the scenarios by block/reason. Cleans up after itself. Answers "does it work in new sessions"."""
import json, os, subprocess, sys, time, tempfile, shutil

ROOT = os.environ.get("BBT_ROOT") or os.getcwd()
if not os.path.isdir(os.path.join(ROOT, "sessions")):
    # search upward from cwd
    r = os.getcwd()
    while r and not os.path.isdir(os.path.join(r, "sessions")):
        nxt = os.path.dirname(r)
        if nxt == r: break
        r = nxt
    ROOT = r
assert os.path.isdir(os.path.join(ROOT, "sessions")), "ROOT not found: " + ROOT
SESSIONS = os.path.join(ROOT, "sessions")
HOOK = os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py")
SCRATCH = os.path.dirname(os.path.abspath(__file__))

def win_fwd(p):
    """Windows path with forward slashes (transcript gotcha: backslash -> invalid JSON \\U -> fail-open)."""
    return os.path.abspath(p).replace("\\", "/")

def make_transcript(user_text, asst_text):
    fd, path = tempfile.mkstemp(suffix=".jsonl", dir=SCRATCH)
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": user_text}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": asst_text}}) + "\n")
    return path

def run_hook(sid, transcript):
    payload = json.dumps({"session_id": sid, "transcript_path": win_fwd(transcript)})
    p = subprocess.run([sys.executable, HOOK], input=payload.encode("utf-8"), capture_output=True)
    out = (p.stdout or b"").decode("utf-8", "replace").strip()
    err = (p.stderr or b"").decode("utf-8", "replace").strip()
    if not out:
        if err:
            print("    [hook stderr]:", err[:200])
        return None  # exit 0 with no output = NOT a block (loop released / not a hunt)
    try:
        return json.loads(out)
    except Exception:
        return {"raw": out}

def scenario(name, sid, ledger_text, user_text, asst_text, model_text=None):
    d = os.path.join(SESSIONS, "_gatetest_" + sid)
    if os.path.exists(d): shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    tpaths = []
    try:
        with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
            f.write(ledger_text)
        if model_text is not None:  # OBS-10: model gates (axes-without-waves) read system_model.md next to the ledger
            with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
                f.write(model_text)
        # marker: line 1 = timestamp, line 2 = session_id (arms a new session with this sid)
        with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
            f.write("%d\n%s" % (int(time.time()), sid))
        tr = make_transcript(user_text, asst_text); tpaths.append(tr)
        res = run_hook(sid, tr)
        blocked = bool(res and res.get("decision") == "block")
        reason = (res or {}).get("reason", "") if res else ""
        return blocked, reason
    finally:
        shutil.rmtree(d, ignore_errors=True)
        for t in tpaths:
            try: os.remove(t)
            except Exception: pass

# NOTE: Russian text inside the ledger/transcript fixtures below is test INPUT matched by the hook's
# Russian-aware regexes ("продолжай" = "continue", etc.) and is intentionally kept as-is.
LOOPSTATE = "## Loop State\n- **Iteration #:** {it}\n- **Depth-Lead:** {dl}\n- **Exit:** T4 High/Crit only.\n"
SCOUT_OK = "\n## Scout Fan-Out\n**Status:** `N/A — single-contract`\n"
IMPACTS_OK = "**Impacts in Scope:** N/A — no formal impacts list\n"

def ledger(it, dl, kills=0, verifier=False, exhaust_note=""):
    t = "# test — Registry\n" + IMPACTS_OK
    t += LOOPSTATE.format(it=str(it) + (" " + exhaust_note if exhaust_note else ""), dl=dl)
    t += SCOUT_OK
    t += "\n## Active Hypotheses\n### H-01: test hypothesis\n- State: A\n"
    for i in range(kills):
        t += "\n### H-%02d [KILLED]: k\n- Killed by: T4 cold-verify file.sol:%d\n" % (i + 2, i)
    t += "\n## Verifier Log (T4)\n"
    if verifier:
        # FULL T4 (Stage 3): 7 sub-steps + confidence>=80 -- otherwise the submit gate T4-DECOMPOSITION holds
        # the release on HUNT-EXIT. Outcomes are positive (dedup "clean", 2.6 "PoC PASS") -- else the finding is dead.
        # (Fixture text below stays Russian: it is matched by the gate's regexes.)
        t += ("- 2026-07-07 — H-03 — STEP 0 dedup: audits+Solodit по core-nouns → чисто — "
              "STEP 1.5 self-steelman: case против — «может intended» — опровергнут NatSpec — "
              "verdict: PASS — `checker:cold-subagent` — STEP 2.5 gates: gate1 attack-execution ok; "
              "gate2 reachability ok; gate3 trigger unprivileged; gate4 impact LP теряют — "
              "STEP 2.6 fresh-runtime: re-provisioned fresh "
              "fork@21050000 → PoC PASS на свежем состоянии — STEP 2.7 precondition-matrix: "
              "precond-1 OFF → not-fires; unstated: pre-funded balance — evidence-artifact: forge test "
              "trace, tx 0xabc123def4567890 — current-exploitability: deployed code-hash сверен с HEAD "
              "на current block → жив — confidence: 90% — file.sol:10\n")
    else:
        t += "- {timestamp} — H-{NN} — verifier verdict: ...\n"
    return t

results = []

# 1) False exhaustion on a web target: iter1 + exhaustion-claim + give-up message -> BLOCK (give-up).
# (assistant text kept in Russian: give-up phrasing matched by the gate)
b, r = scenario("sky", "gt-sky-0001",
    ledger(1, "poll-sink 5/5 killed", kills=0, verifier=False, exhaust_note="(exhaustive web pass done)"),
    "продолжай",
    "Отработал все 4 веб-ассета вглубь. 0 in-scope High/Critical. EV hardened. Гнать одну из low-EV осей дальше или считаем Sky-веб закрытым?")
results.append(("1 web-target give-up → BLOCK give-up", b and "COMPLETENESS-GATE" in r or "EXHAUSTION" in r, b, r[:60]))

# 2) exhaustion-shape: 6 kills + empty verifier + soft-lexicon NOT from ABORT -> FALSE-EXHAUSTION.
b, r = scenario("exh", "gt-exh-0002",
    ledger(9, "none", kills=6, verifier=False),
    "продолжай",
    "Все кандидаты мертвы, идти больше некуда по этой поверхности.")
results.append(("2 exhaustion-shape → BLOCK FALSE-EXH", b and "FALSE-EXHAUSTION" in r, b, r[:60]))

# 3) benign working status (healthy ledger) -> BLOCK, but LOOP-CONTINUE (not give-up).
b, r = scenario("ben", "gt-ben-0003",
    ledger(3, "H-04 — 4/5 (call->state->external->hook)", kills=1, verifier=True),
    "продолжай",
    "Гоню H-04 вглубь, слой 4 пройден, ledger обновлён. Далее: слой 5 accounting.")
giveup_sigs = ["FALSE-EXHAUSTION", "EARLY-EXHAUSTION"]
results.append(("3 benign → CONTINUE (not give-up)", b and not any(s in r for s in giveup_sigs), b, r[:60]))

# 4) HUNT-EXIT High -> NOT a block (the loop performed its exit).
lt = ledger(5, "H-01 5/5", kills=2, verifier=True) + "\nHUNT-EXIT: T4-CONFIRMED High\n"
b, r = scenario("exit", "gt-exit-0004", lt, "продолжай", "Подтвердил High через T4, записал HUNT-EXIT.")
results.append(("4 HUNT-EXIT High → NOT a block", not b, b, r[:60]))

# 5) the operator's RELEASE word -> NOT a block.
# (user text "всё, уходим с этого таргета" = "that's it, we're leaving this target" -- release-word fixture, kept Russian)
b, r = scenario("rel", "gt-rel-0005",
    ledger(2, "none", kills=6, verifier=False),
    "всё, уходим с этого таргета",
    "Понял, surface тонкий, все кандидаты мертвы.")
results.append(("5 release word (\"leaving\") → NOT a block", not b, b, r[:60]))

# ── Scout Fan-Out enforcement gates — real main() path through the ordering ──
def scout_ledger(scout_body):
    """Ledger that passes ALL early checks (impacts/loopstate/scout-pending/give-up) to reach
    the scout gates. iter=3 + depth 2/5 + 1 H + 0 kills -> wide-shallow/early-exhaust/t4 do not trigger."""
    t = "# test — Registry\n" + IMPACTS_OK
    t += LOOPSTATE.format(it="3", dl="H-01 — 2/5 (call->state)")
    # P0: the early MODEL-BEFORE-SCOUT gate sits before scout-pending. These scenarios test the
    # SCOUT sub-gates, not the model -> lift the model gate with a sentinel, otherwise on PENDING it shadows SCOUT.
    t += "- **MODEL: N/A — e2e scout-focused test**\n"
    t += "\n## Scout Fan-Out\n" + scout_body
    t += "\n## Active Hypotheses\n### H-01: test\n- State: A\n"
    t += "\n## Verifier Log (T4)\n- {timestamp} — H-{NN} — ...\n"
    return t

# assistant text: "Scout merge is ready, driving H-01 deeper, layer 2 passed, ledger updated." (kept Russian: fixture)
BENIGN = "Scout merge готов, гоню H-01 вглубь, слой 2 пройден, ledger обновлён."

# 6) Scout DONE + P-B BOUNDARY-MAP placeholder -> BLOCK P-B-SCOUT.
# (BOUNDARY-MAP placeholder "{граница1; …}" = "{boundary1; …}" -- kept Russian: template-placeholder fixture)
b, r = scenario("pbskip", "gt-pbskip-0006", scout_ledger(
    "**Status:** `DONE 2026-07-12`\n| P-B boundary/trust-perimeter (MANDATORY) | | | |\n"
    "| P1 accounting | s | 2 | H-01 |\n- **BOUNDARY-MAP (от P-B):** {граница1; …}\n"),
    "продолжай", BENIGN)
results.append(("6 P-B skipped (BOUNDARY-MAP placeholder) → BLOCK", b and "BOUNDARY-SCOUT" in r, b, r[:60]))

# 7) Scout DONE + BOUNDARY-MAP filled + OPT-TODO hanging -> BLOCK OPTIONAL-MENU.
# ("{для каждой P7-P10}" = "{for each of P7-P10}" -- kept Russian: placeholder fixture)
b, r = scenario("opttodo", "gt-opttodo-0007", scout_ledger(
    "**Status:** `DONE`\n| P-B boundary/trust-perimeter (MANDATORY) | s | 1 | H-01 |\n"
    "- **BOUNDARY-MAP:** oracle-verifier; bridge-mint\n"
    "- **OPTIONAL-menu triage [OPT-TODO]:** {для каждой P7-P10}\n"),
    "продолжай", BENIGN)
results.append(("7 OPT-TODO hanging → BLOCK OPTIONAL-MENU", b and "OPTIONAL-MENU" in r, b, r[:60]))

# 8) Scout DONE + everything filled + WAVE-2 PENDING -> BLOCK WAVE-2.
b, r = scenario("wave", "gt-wave-0008", scout_ledger(
    "**Status:** `DONE`\n| P-B boundary/trust-perimeter (MANDATORY) | s | 1 | H-01 |\n"
    "- **BOUNDARY-MAP:** oracle-verifier\n- **OPTIONAL triage:** P8 MATCHED->scout; P7 skip-if\n"
    "- **WAVE-2:** P8 cross-chain — PENDING\n"),
    "продолжай", BENIGN)
results.append(("8 WAVE-2 PENDING → BLOCK WAVE-2", b and "WAVE-2" in r, b, r[:60]))

# 9) Scout DONE + all clean (BOUNDARY filled / no OPT-TODO / WAVE-2 N/A) -> the scout gates STAY SILENT,
#    falls through to LOOP-CONTINUE (real no-false-positive through the ordering, NOT the scout reasons).
b, r = scenario("clean", "gt-clean-0009", scout_ledger(
    "**Status:** `DONE`\n| P-B boundary/trust-perimeter (MANDATORY) | s | 1 | H-01 |\n"
    "- **BOUNDARY-MAP:** oracle-verifier\n- **OPTIONAL triage:** all skip-if\n- **WAVE-2:** N/A\n"),
    "продолжай", BENIGN)
mine = ("BOUNDARY-SCOUT" in r) or ("OPTIONAL-MENU" in r) or ("WAVE-2" in r)
results.append(("9 all-clean scout → scout gates silent (no-FP)", b and not mine, b, r[:60]))

# 10) FIRST RUN: Scout PENDING -> the SCOUT-GATE starting reason describes the FULL CORE=7 model
#     (P-B mandatory + P6 + <=7 + OPTIONAL menu), not the old 5. This is the proactive driver of the first fan-out.
b, r = scenario("pending", "gt-pending-0010", scout_ledger("**Status:** `PENDING`\n"),
    "продолжай", BENIGN)
core7 = b and "SCOUT-GATE" in r and "P-B" in r and "≤7" in r and "P6 economic" in r and "OPTIONAL" in r
results.append(("10 PENDING → SCOUT-GATE emits CORE=7 (P-B+P6+menu+≤7)", core7, b, r[:60]))

# 10b) P0: scout PENDING + model ACTUALLY EMPTY (no N/A, no system_model.md) ->
#      MODEL-BEFORE-SCOUT fires EARLIER than the scout gate (divergence-first: model BEFORE the fan-out).
p0_ledger = ("# test — Registry\n" + IMPACTS_OK
             + LOOPSTATE.format(it="2", dl="none yet")
             + "\n## Scout Fan-Out\n**Status:** `PENDING`\n"
             + "\n## Active Hypotheses\n### H-01: t\n- State: A\n")
b, r = scenario("p0mbs", "gt-p0mbs-010b", p0_ledger, "продолжай", BENIGN)
results.append(("10b P0 scout PENDING + empty model → MODEL-BEFORE-SCOUT (not SCOUT)",
                b and "MODEL-BEFORE-SCOUT" in r, b, r[:60]))

# ── DEPTH-QUALITY gates (duplicate-finding case) — real main() path ──
CLEAN_SCOUT = ("**Status:** `DONE`\n| P-B boundary/trust-perimeter (MANDATORY) | s | 1 | H-01 |\n"
    "- **BOUNDARY-MAP:** oracle-verifier\n- **OPTIONAL triage:** all skip-if\n- **WAVE-2:** N/A\n")

def depth_ledger(loop_extra, scout=CLEAN_SCOUT, tail=""):
    """Ledger that passes impacts/loopstate/scout-clean/give-up/t4 -> reaches the depth cluster (3b)."""
    t = "# test — Registry\n" + IMPACTS_OK
    t += "## Loop State\n- **Iteration #:** 5\n" + loop_extra + "- **Exit:** T4 High/Crit only.\n"
    t += "\n## Scout Fan-Out\n" + scout
    t += "\n## Active Hypotheses\n### H-01: test\n- State: A\n" + tail
    t += "\n## Verifier Log (T4)\n- {timestamp} — H-{NN} — ...\n"
    return t

# 11) Crit-composite written out and ABANDONED without resolution (natural AMPLIFICATION THREAD) -> BLOCK NO-ABANDON.
b, r = scenario("comp", "gt-comp-0011", depth_ledger(
    "- **Depth-Lead:** H-01 — 2/5 (call->state)\n",
    tail="\n### H-11 [ACTIVE]: churn\n- **AMPLIFICATION THREAD (chase → could reach SC-Critical):** "
         "beacon forced exit sweeps CL balance to WithdrawalVault WITHOUT totalDeposits decrement → "
         "orphaned-TVL / insolvency. Reading StakingPool now. Composite BB-35 (pending).\n"),
    "продолжай", BENIGN)
results.append(("11 abandoned Crit composite → BLOCK NO-ABANDON", b and "NO-ABANDON-COMPOSITE" in r, b, r[:60]))

# 12) Depth-Lead claims 5/5, but DEPTH-MAP = {placeholder} -> BLOCK DEPTH-MAP UNGROUNDED.
# ("заполнять ≥5" = "fill in >=5" -- kept Russian: template-placeholder fixture)
b, r = scenario("dmap", "gt-dmap-0012", depth_ledger(
    "- **Depth-Lead:** H-12 — 5/5 (ssz fork)\n- **DEPTH-MAP (заполнять ≥5):** {L1 … → L5}\n"),
    "продолжай", BENIGN)
results.append(("12 5/5 claim + DEPTH-MAP placeholder → BLOCK UNGROUNDED", b and "DEPTH-MAP UNGROUNDED" in r, b, r[:60]))

# 13) Composite RESOLVED (DRIVEN/T4) + DEPTH-MAP filled + 5/5 -> the depth gates STAY SILENT (no-FP), LOOP-CONTINUE.
b, r = scenario("depthok", "gt-depthok-0013", depth_ledger(
    "- **Depth-Lead:** H-12 — 5/5 (ssz fork)\n"
    "- **DEPTH-MAP:** L1 a.sol:1 (core) → L2 b.sol:2 (vault) → L3 c.go:3 (beacon) → L4 d.sol:4 → L5 e.sol:5\n",
    tail="\n### H-11 [ACTIVE]: amp DRIVEN to D-PoC, fork-PoC confirms, T4 verdict confirm — "
         "AMPLIFICATION THREAD Critical insolvency resolved. pool.sol:210.\n"),
    "продолжай", BENIGN)
minedepth = ("NO-ABANDON-COMPOSITE" in r) or ("DEPTH-MAP UNGROUNDED" in r) or ("SINGLE-SUBSYSTEM" in r)
results.append(("13 resolved+filled depth → depth gates silent (no-FP)", b and not minedepth, b, r[:60]))

# 14) Depth-Lead 5/5, DEPTH-MAP filled, but 1 file (pool.sol x5) -> BLOCK DEPTH-MAP SINGLE-SUBSYSTEM.
b, r = scenario("single", "gt-single-0014", depth_ledger(
    "- **Depth-Lead:** H-12 — 5/5 (pool accounting)\n"
    "- **DEPTH-MAP:** L1 pool.sol:10 → L2 pool.sol:40 → L3 pool.sol:88 → L4 pool.sol:120 → L5 pool.sol:200\n"),
    "продолжай", BENIGN)
results.append(("14 5/5 + 1-file map → BLOCK SINGLE-SUBSYSTEM", b and "SINGLE-SUBSYSTEM" in r, b, r[:60]))

# ── VOID-SUPERSEDE exit-token (live test) — a stale HUNT-EXIT does not release ──
# 15) HUNT-EXIT recorded, but LATER cancelled (SUPERSEDED reversal) + active work -> BLOCK (do not release).
# (reversal line "H-09 не confidently-Critical, kept banked" = "H-09 is not confidently Critical" -- kept Russian: fixture)
lt = (ledger(5, "H-01 5/5", kills=2, verifier=True) + "\nHUNT-EXIT: T4-CONFIRMED Critical\n"
      + "\n- HUNT-EXIT above SUPERSEDED by this reversal — H-09 не confidently-Critical, kept banked.\n")
b, r = scenario("void", "gt-void-0015", lt, "продолжай", "Отменил находку после T4-дедупа, продолжаю.")
results.append(("15 voided HUNT-EXIT → BLOCK (stale token does not release)", b, b, r[:60]))

# 16) HUNT-EXIT -> SUPERSEDED -> NEW HUNT-EXIT after cancellation (re-confirmed) -> NOT a block (valid).
lt = (ledger(5, "H-01 5/5", kills=2, verifier=True) + "\nHUNT-EXIT: T4-CONFIRMED Critical\n"
      + "\n- HUNT-EXIT above SUPERSEDED by this reversal — old finding retracted.\n"
      + "\nHUNT-EXIT: T4-CONFIRMED Critical — re-confirmed через новый fork-PoC + T4.\n")
b, r = scenario("reexit", "gt-reexit-0016", lt, "продолжай", "Ре-подтвердил Critical новым T4.")
results.append(("16 re-confirmed HUNT-EXIT after void → NOT a block", not b, b, r[:60]))

# ── AXES-WITHOUT-WAVES (OBS-10) — real main() path through the ordering ──
# Full model (so earlier model gates stay silent) + a ledger claiming T9 axes. Checks that the
# COUNTING gate "axes without waves" actually REACHES a block in the runner (in the first probe T12
# shadowed it -- without this scenario an ordering regression would pass silently, template_sentinel class).
# (Table headers/cells in the model fixture are Russian and parsed by the gate -- kept as-is.)
_AXTABLE = ("| ID | F | check | Класс | Ист | component | pred | Статус | file:line | tests | crowd-heat | lib |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
def _axrow(i, st="ENFORCED"):
    return "| I-%02d | f%d | что | state | docs | vault | %s | %s | a.sol:%d | 2 | cold | |\n" % (i, i, st, st, 10 + i)
def axes_model(extra_waves=0):
    m = "## Invariants\n" + _AXTABLE + _axrow(1) + _axrow(2) + _axrow(3, "ABSENT")
    m += "\n- [x] оператор канона прогнан по всем I-NN из стандарта\n"
    m += "\n## Missing Negatives\n| Тест | Негатив | Ось | Бьёт |\n|---|---|---|---|\n| t.sol:10 | RedeemTwice | повтор | I-01 |\n"
    m += "\nОси в прозе: cross-function, order-dependent, temporal, cross-subsystem isolation, economic-sequence.\n"
    m += "\n## Subsystem Model Coverage\n| Подсистема | in-scope | статус |\n|---|---|---|\n| Vault | yes | MODELED |\n"
    m += "\n## Divergences\n| ID | I-NN | Где | Статус | Ранг | Резолюция |\n|---|---|---|---|---|---|\n| D-01 | I-03 | a.sol:9 | ABSENT | high | → H-03 |\n"
    for w in range(2, 2 + extra_waves):
        m += "\n## WAVE-%d — ось %d\n" % (w, w) + _AXTABLE + _axrow(100 * w + 1) + _axrow(100 * w + 2)
    return m
def axes_ledger(axes_line):
    return ("# t\n" + IMPACTS_OK + "## Loop State\n- **Iteration #:** 8\n- **Depth-Lead:** none yet\n"
            "- **Exit:** T4 High/Crit only.\n" + axes_line + SCOUT_OK +
            "\n## Verifier Log\n2026-07-30 — H-01 cold-verify confirmed a.sol:10\n")
# 17) 3 axes claimed / 0 waves built -> block SPECIFICALLY AXES-WITHOUT-WAVES (reached through the ordering).
b, r = scenario("axw", "gt-axw-0017", axes_ledger("- **T9 restart axes used:** 3 (treasury, position, oracle)\n"),
                "продолжай", "Оси пройдены.", model_text=axes_model(0))
results.append(("17 3 axes / 0 waves → AXES-WITHOUT-WAVES block", b and "AXES-WITHOUT-WAVES" in r, b, r[:55]))
# 18) 3 axes / 3 extra waves -> this gate STAYS SILENT (axes covered by waves).
b, r = scenario("axwok", "gt-axwok-0018", axes_ledger("- **T9 restart axes used:** 3 (a, b, c)\n"),
                "продолжай", "Три волны построены.", model_text=axes_model(3))
results.append(("18 3 axes / 3 waves → AXES-WITHOUT-WAVES did NOT fire", "AXES-WITHOUT-WAVES" not in r, b, r[:55]))

# ── T11-UNDECIDED (OBS-11) + ATTENTION-GAP-SKIPPED (OBS-12) — real main() path through the ordering ──
# Mature model (early model gates silent) + template axes (axes gates silent) -> we reach T11/T14.
_axled = axes_ledger("- **T9 restart axes used:** {0-3+ template}\n")  # n=0 -> axes gates silent
# 19) T11: no `T11-VERDICT:` -> block SPECIFICALLY T11-UNDECIDED (the J2 detector was not run).
b, r = scenario("t11", "gt-t11-0019", _axled, "продолжай", "Модель готова.", model_text=axes_model(0))
results.append(("19 no T11-VERDICT → T11-UNDECIDED block", b and "T11-UNDECIDED" in r, b, r[:55]))
# 20) T14: `T11-VERDICT` present (T11 silent), 0 open D-NN, no Attention Gaps -> ATTENTION-GAP-SKIPPED.
b, r = scenario("t14", "gt-t14-0020", _axled + "- **T11-VERDICT:** SKIP — checked\n",
                "продолжай", "T11 решён.", model_text=axes_model(0))
results.append(("20 T11 decided / attn empty → ATTENTION-GAP-SKIPPED block", b and "ATTENTION-GAP-SKIPPED" in r, b, r[:55]))

# ── WORKLIST DRIVER Stage 2 (next_atom active dictation) — real main() path through the DEFAULT branch ──
# Base = scenario 13 (depthok, proven to reach LOOP-CONTINUE) + a healthy `## Atom Registry`.
# Checks that the next_atom directive (naming the head AX-04) REALLY reaches a block through the full main().
_STAGE2_REG = ("\n## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n"
               "|---|---|---|---|---|---|---|\n"
               "| AX-04 | axis | band-regression | code-read | 35 | ACTIVE | - |\n"
               "| AX-05 | axis | governance | T6-pair | 28 | OPEN | - |\n")
# 21) healthy registry (pick=head=ACTIVE AX-04) -> block carries WORKLIST-DRIVER DRIVE + names AX-04.
#     Minimal fall-through ledger (4/5 depth -- NOT 5/5, T12 silent; SCOUT N/A; a MODEL: N/A sentinel would get in the
#     way of next_atom -> use the real small-model sentinel via the absence of model scaffolding).
# (Depth-Lead text "гоню голову реестра, слой в работе" = "driving the registry head, layer in progress" -- kept Russian: fixture)
_wl_ledger = (
    "# test — Registry\n" + IMPACTS_OK
    + "## Loop State\n- **Iteration #:** 3\n"
    + "- **Depth-Lead:** AX-04 — гоню голову реестра, слой в работе\n"
    + "- **Current pick:** AX-04\n- **Exit:** T4 High/Crit only.\n"
    + "- **MODEL: N/A — e2e worklist-focused test**\n"
    + SCOUT_OK
    + "\n## Active Hypotheses\n### H-01: test\n- State: A\n"
    + _STAGE2_REG
    + "\n## Verifier Log (T4)\n- 2026-07-07 — H-03 — verdict: kill — file.sol:10\n")
b, r = scenario("wl2", "gt-wl2-0021", _wl_ledger, "продолжай", BENIGN)
results.append(("21 healthy registry → WORKLIST-DRIVER DRIVE names head AX-04",
                b and "WORKLIST-DRIVER" in r and "AX-04" in r, b, r[:70]))

# 22) same registry + HUNT-MODE: MANUAL -> G-matrix row "next_atom respects manual": `if manual:
#     sys.exit(0)` EARLIER than next_atom -> NOT a block (the registry does not dictate in manual mode). Behavioral proof.
b, r = scenario("wl2m", "gt-wl2m-0022", _wl_ledger + "\nHUNT-MODE: MANUAL\n", "продолжай", BENIGN)
results.append(("22 healthy registry + MANUAL → NOT a block (next_atom respects manual, G-matrix)",
                not b, b, r[:70]))

# ── OUT-OF-SCOPE enforcement (money-critical) — real main() path ──
_OOS_REAL = "**Out-of-Scope (disqualifiers):** centralization risks, admin-key, known-issues\n"
# ("вычитать /scope/ …" = "read out /scope/ …" -- kept Russian: OOS-TODO placeholder fixture)
_OOS_TODO = "**Out-of-Scope (disqualifiers):** {OOS-TODO — вычитать /scope/ …}\n"

# 23) intake: IMPACTS lifted, but OOS-TODO hanging -> BLOCK OUT-OF-SCOPE (sits right after impacts).
b, r = scenario("oostodo", "gt-oostodo-0023",
    ledger(3, "H-04 — 4/5 (call->state)", kills=1, verifier=True).replace(IMPACTS_OK, IMPACTS_OK + _OOS_TODO),
    "продолжай", "Гоню H-04 вглубь.")
results.append(("23 OOS-TODO hanging → BLOCK OUT-OF-SCOPE", b and "OUT-OF-SCOPE" in r, b, r[:60]))

# 24) submit: HUNT-EXIT + real OOS captured, but NO OOS-CHECK -> BLOCK OOS-CHECK (success-exit path).
lt = (ledger(5, "H-01 5/5", kills=2, verifier=True).replace(IMPACTS_OK, IMPACTS_OK + _OOS_REAL)
      + "\nHUNT-EXIT: T4-CONFIRMED High\n")
b, r = scenario("ooscheck", "gt-ooscheck-0024", lt, "продолжай", "Подтвердил High через T4.")
results.append(("24 HUNT-EXIT + real OOS + no OOS-CHECK → BLOCK OOS-CHECK", b and "OOS-CHECK" in r, b, r[:60]))

# 25) submit: HUNT-EXIT + real OOS + OOS-CHECK PASS -> NOT a block (finding cross-checked, release).
lt = (ledger(5, "H-01 5/5", kills=2, verifier=True).replace(IMPACTS_OK, IMPACTS_OK + _OOS_REAL)
      + "\nHUNT-EXIT: T4-CONFIRMED High\n\nOOS-CHECK: H-01 vs out-of-scope → PASS\n"
      + "\n## Invariant Library\n- LIBRARY: updated — ERC4626 share-rounding fingerprint\n")
b, r = scenario("oospass", "gt-oospass-0025", lt, "продолжай", "Сверил с OOS, чисто. Подаю.")
results.append(("25 HUNT-EXIT + OOS-CHECK PASS → NOT a block (release)", not b, b, r[:60]))

# 26) red-team D1: fast HUNT-EXIT + OOS-TODO NOT read out -> the success path BLOCKS OUT-OF-SCOPE
#     (previously it released with an unread OOS = the original $0 miss one floor below).
lt = (ledger(5, "H-01 5/5", kills=2, verifier=True).replace(IMPACTS_OK, IMPACTS_OK + _OOS_TODO)
      + "\nHUNT-EXIT: T4-CONFIRMED High\n")
b, r = scenario("oostodoexit", "gt-oostodoexit-0026", lt, "продолжай", "Нашёл High, пишу HUNT-EXIT.")
results.append(("26 HUNT-EXIT + OOS-TODO (not read out) → BLOCK OUT-OF-SCOPE (D1 success-path)",
                b and "OUT-OF-SCOPE" in r, b, r[:60]))

# 27) banked Medium + real OOS + no OOS-CHECK -> BLOCK BANKED OOS (Medium/Low hole closed).
# (table header "Что"/"Статус" = "What"/"Status" -- kept Russian: parsed by the gate)
_BANKED = ("\n## Banked Findings\n| Severity | H-NN | Что | output | input | tier | found_by | Статус |\n"
           "|---|---|---|---|---|---|---|---|\n"
           "| Medium | H-05 | oracle conf-strip | over-val | — | $3K | scan | confirmed |\n")
lt = (ledger(4, "H-07 — гоню нить, слой в работе", kills=1, verifier=True)
      .replace(IMPACTS_OK, IMPACTS_OK + _OOS_REAL + "- **MODEL: N/A — e2e banked test**\n") + _BANKED)
b, r = scenario("bankedoos", "gt-bankedoos-0027", lt, "продолжай", "Забанковал Medium, гоню дальше.")
results.append(("27 banked Medium + real OOS + no OOS-CHECK → BLOCK BANKED OOS", b and "BANKED OOS" in r, b, r[:60]))

# 28) Stage 3 Layer-3: HUNT-EXIT + THIN T4 entry ("verdict: confirm" and nothing else) -> BLOCK T4-DECOMPOSITION
#     (STEP 3: without fresh-runtime 2.6 / precondition-matrix 2.7 the finding is NOT submit-ready).
# ("выглядит валидно" = "looks valid" -- kept Russian: fixture)
lt = (ledger(5, "H-01 — нить закрыта", kills=2, verifier=False)
      .replace(IMPACTS_OK, IMPACTS_OK + "**Out-of-Scope (disqualifiers):** N/A — no formal OOS list\n")
      + "\nHUNT-EXIT: T4-CONFIRMED High\n"
      + "\n- 2026-08-11 — H-01 — verifier verdict: confirm — выглядит валидно\n")
b, r = scenario("t4decomp", "gt-t4decomp-0028", lt, "продолжай", "Подтвердил High, подаю.")
results.append(("28 HUNT-EXIT + thin T4 → BLOCK T4-DECOMPOSITION (S3 Layer-3)",
                b and "T4-DECOMPOSITION" in r, b, r[:60]))

# 29-30) Stage 3 §8 G-submit: submit-checklist AS a registry atom (not an enum). Full T4 present, registry present,
#        but no submit-checklist atom -> BLOCK; add a CLOSED atom -> release.
_SC_REG = ("\n## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n"
           "|---|---|---|---|---|---|---|\n"
           "| AX-04 | axis | band | code-read | 35 | CLOSED | H-01 |\n")
_SC_ROW = "| SC-01 | submit-checklist | pre-submit H-01 | submission_checklist | 30 | CLOSED | H-01 |\n"
_sc_base = (ledger(5, "H-01 — нить закрыта", kills=2, verifier=True)
            .replace(IMPACTS_OK, IMPACTS_OK + "**Out-of-Scope (disqualifiers):** N/A — no formal OOS list\n")
            + "\nHUNT-EXIT: T4-CONFIRMED High\n"
            + "\n## Invariant Library\n- LIBRARY: updated — fingerprint записан\n")
b, r = scenario("scmiss", "gt-scmiss-0029", _sc_base + _SC_REG, "продолжай", "Подаю находку.")
results.append(("29 HUNT-EXIT + registry without submit-checklist atom → BLOCK (§8 G-submit)",
                b and "SUBMIT-CHECKLIST" in r, b, r[:60]))
b, r = scenario("scok", "gt-scok-0030", _sc_base + _SC_REG + _SC_ROW, "продолжай", "Чеклист прогнан, подаю.")
results.append(("30 HUNT-EXIT + submit-checklist CLOSED → NOT a block (release)", not b, b, r[:60]))

print("=== GATE END-TO-END SMOKE (real Stop hook, subprocess, armed new session) ===\n")
ok = 0
for name, passed, blocked, reason in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name)
    print("         blocked=%s reason=%r" % (blocked, reason))
    ok += 1 if passed else 0
print("\n%d/%d scenarios green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
