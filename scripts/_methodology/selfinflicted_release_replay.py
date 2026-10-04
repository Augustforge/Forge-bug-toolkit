# -*- coding: utf-8 -*-
"""Replay for the SELF-INFLICTED FALSE-RELEASE (incident 2026-08-18).

Defect: the Stop hook injects its own reason as a user msg with `isMeta:true`. The EXIT-KNOWLEDGE reminder
quotes the word «уходим» ("you exit with success or «уходим»…"; Russian for "we're leaving"). The next Stop read THAT reminder as the
operator's LAST message → the RELEASE match caught «уходим» from OUR OWN text → the give-up slipped through
EXACTLY on the hunt wrap-up (after EXIT-KNOWLEDGE fired). The agent gave up and stopped,
the operator pressed /compact+"continue" by hand — the engine disarmed itself.

Fix: main() skips `isMeta` user messages (a harness injection marker, not operator input) +
a backup strip of "stop hook feedback:" in _strip_machine_text_user.

Rule feedback_hook_must_prove_firing: the test proves FIRING (self-inflicted → BLOCK) AND
non-regression (a real «уходим» from the operator → RELEASE, the prerogative is intact). Run through the LIVE gate binary
(subprocess) — the most honest: reproduces main() end-to-end, not a copy of the logic. An isolated slug
in the REAL sessions/ (arming computes root from __file__), cleaned up."""
import importlib.util, os, sys, time, tempfile, shutil, json, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "sessions")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
SCRATCH = tempfile.mkdtemp()
SLUG = "_sirtest"
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

# A substantive active ledger (>=3 I/H-NN, fresh, no HUNT-EXIT/MANUAL) — arms the ledger-state.
LEDGER = ("# _sirtest — Registry\n## Loop State\n- HUNT-MODE: AUTONOMOUS\n- Iteration: 4\n"
          "## Active\n- **I-01** a\n- **I-02** b\n- **I-03** c\n- **H-04** d\n"
          "EXIT-KNOWLEDGE (snapshot+patterns). LIBRARY: updated.\n")

# EXIT-KNOWLEDGE reminder (abridged) — it is THE ONE that quotes «уходим». Injected as an isMeta user msg.
# Russian text kept verbatim: fixture input matched by the gate's Russian-language regexes / strip logic.
HOOK_FEEDBACK = ("Stop hook feedback:\nEXIT-KNOWLEDGE (operator 2026-08-13 — «после ухода данные должны "
                 "вноситься на будущее»). Ledger: выходишь (success или «уходим»), но знание на будущее "
                 "не забанковано. Внеси wave-snapshot / undup_pattern / memory-index. Пометь "
                 "`EXIT-KNOWLEDGE: DONE`.")

# Assistant give-up (same class as the incident: "your call... I continue on your word"). Russian fixture: KEEP.
GIVEUP = ("Бро, честный итог. Модель доведена до executable-закрытия. 0 payable Critical/High. Осталась "
          "одна low-EV ось (decoder-sanitization, scope-мутная). Твой вызов: гнать T9 или банкуем таргет "
          "под single-target-mastery и возвращаемся по wave-delta? Продолжаю по твоему слову — сам петлю "
          "без твоего стира не гоню, high-EV поверхность закрыта.")

# Real operator message "all, we're leaving this target, enough" — Russian fixture matched by the RELEASE regex: KEEP.
REAL_OPERATOR_UHODIM = "всё, уходим с этого таргета, хватит"


def mk_ledger():
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(LEDGER)
    return d


def edit_line():
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Edit",
         "input": {"file_path": "sessions/%s/hypotheses.md" % SLUG}}]}})


def user_line(text, is_meta):
    o = {"type": "user", "message": {"role": "user", "content": text}}
    if is_meta:
        o["isMeta"] = True
    return json.dumps(o, ensure_ascii=False)


def asst_line(text):
    return json.dumps({"type": "assistant", "message": {"role": "assistant",
                       "content": [{"type": "text", "text": text}]}}, ensure_ascii=False)


def run_gate(lines):
    """Writes a transcript, calls the LIVE gate binary, returns (blocked, reason_head)."""
    tp = os.path.join(SCRATCH, "tr_%d.jsonl" % len(results))
    with open(tp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    payload = json.dumps({"session_id": "sir-sid-1", "transcript_path": tp})
    p = subprocess.run([sys.executable, "-X", "utf8", HOOK], input=payload,
                       capture_output=True, text=True, encoding="utf-8")
    out = (p.stdout or "").strip()
    if not out:
        return (False, "")
    try:
        j = json.loads(out)
        return (j.get("decision") == "block", (j.get("reason") or "")[:80])
    except Exception:
        return (False, out[:80])


def clean_marker():
    mk = os.path.join(SESSIONS, SLUG, ".hunt_active")
    if os.path.exists(mk):
        os.remove(mk)


try:
    mk_ledger()

    # 1) SELF-INFLICTED: an isMeta hook-feedback with «уходим» + an assistant give-up → BLOCK (the engine holds).
    #    An exact reproduction of the incident: the EXIT-KNOWLEDGE reminder (isMeta) is the last user, the give-up is the last
    #    assistant. BEFORE: «уходим» from the reminder → false RELEASE. NOW: isMeta is skipped → the give-up holds.
    clean_marker()
    blocked, reason = run_gate([edit_line(), user_line(HOOK_FEEDBACK, True), asst_line(GIVEUP)])
    check("1 SELF-INFLICTED: isMeta reminder with «уходим» + give-up → BLOCK (not a self-release)",
          blocked, "blocked=%s reason=%s" % (blocked, reason))

    # 2) NON-REGRESSION: a REAL «уходим» from the operator (isMeta NOT set) + give-up → RELEASE (prerogative intact).
    clean_marker()
    blocked2, _ = run_gate([edit_line(), asst_line(GIVEUP), user_line(REAL_OPERATOR_UHODIM, False)])
    check("2 NON-REGRESSION: a real «уходим» from the operator (not isMeta) → RELEASE (operator's prerogative)",
          not blocked2, "blocked=%s" % blocked2)

    # 3) BACKUP STRIP: the isMeta field is not set, but the «Stop hook feedback:» prefix is present → it is still
    #    stripped in _strip_machine_text_user → the give-up holds (the harness may not have set isMeta).
    clean_marker()
    blocked3, _ = run_gate([edit_line(), user_line(HOOK_FEEDBACK, False), asst_line(GIVEUP)])
    check("3 BACKUP: «Stop hook feedback:» without isMeta → strip-prefix → BLOCK",
          blocked3, "blocked=%s" % blocked3)

    # 4) FUNCTION LEVEL: _strip_machine_text_user cuts the «stop hook feedback:» tail with «уходим».
    spec = importlib.util.spec_from_file_location("gate", HOOK)
    g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
    stripped = g._strip_machine_text_user("норм " + HOOK_FEEDBACK)  # "норм" ("ok") = Russian fixture input: KEEP
    check("4 _strip_machine_text_user: «уходим» from the hook feedback is cut out",
          "уходим" not in stripped.lower(), "stripped=%r" % stripped[:40])

finally:
    clean_marker()
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(SCRATCH, ignore_errors=True)

print("=== SELF-INFLICTED FALSE-RELEASE REPLAY (the hook does not read its own reason as \"the operator said\") ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
