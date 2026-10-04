# -*- coding: utf-8 -*-
"""Replay for autonomous_hunt_guard.py (PreToolUse, AskUserQuestion) — autonomous-mode guard.

Proves DENY (active hunt + direction menu without HUNT-EXIT → block) AND the allow branches (top-up Watson
request / real HUNT-EXIT / foreign session / non-hunt / non-AskUserQuestion). Rule
feedback_hook_must_prove_firing: the test proves FIRING. Isolation via BBT_SESSIONS_DIR."""
import json, os, subprocess, sys, time, tempfile, shutil

ROOT = os.getcwd()
if not os.path.isdir(os.path.join(ROOT, "sessions")):
    r = os.getcwd()
    while r and not os.path.isdir(os.path.join(r, "sessions")):
        nxt = os.path.dirname(r)
        if nxt == r: break
        r = nxt
    ROOT = r
HOOK = os.path.join(ROOT, "scripts", "hooks", "autonomous_hunt_guard.py")

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

SCRATCH = tempfile.mkdtemp()
_seq = [0]

def new_sessions():
    _seq[0] += 1
    d = os.path.join(SCRATCH, "sessions_%d" % _seq[0])
    os.makedirs(d, exist_ok=True)
    return d

def mk_hunt(sessions_dir, slug, sid, ledger="# ledger\n## Loop State\n- Iteration: 8\n"):
    d = os.path.join(sessions_dir, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write(str(int(time.time())) + "\n" + sid)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger)
    return d

def run(tool, sid, sessions_dir, questions=None):
    payload = {"tool_name": tool, "session_id": sid}
    if questions is not None:
        payload["tool_input"] = {"questions": questions}
    env = dict(os.environ)
    env["BBT_SESSIONS_DIR"] = sessions_dir
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, HOOK],
                       input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, env=env)
    out = (p.stdout or b"").decode("utf-8", "replace").strip()
    try:
        return json.loads(out) if out else None
    except Exception:
        return {"raw": out}

def is_deny(res):
    try:
        return res["hookSpecificOutput"]["permissionDecision"] == "deny"
    except Exception:
        return False

# direction menu (as in a real hunt)
DIRECTION_Q = [{  # NOTE: Russian question/option texts in these fixtures are input data for the guard's Russian-keyword detection; kept as is (logic)
    "question": "Оба in-scope контракта Orca вскрыты статикой начисто. Куда дальше?",
    "header": "Next move",
    "options": [
        {"label": "Собрать differential-fuzz harness", "description": "Trident/fork-harness в Docker"},
        {"label": "Забанчить snapshot, уйти на свежий таргет", "description": "single-target-mastery"},
        {"label": "Ещё один cold-restart axis (T9)", "description": "новая ось two_hop"},
    ],
}]
# OPSEC/top-up question (a legitimate Watson request)
TOPUP_Q = [{
    "question": "Burner пуст — залить $5 на баланс для fork-PoC?",
    "header": "Top-up",
    "options": [{"label": "Да, залей", "description": "пополнить burner"},
                {"label": "Нет", "description": "без on-chain"}],
}]
# template-HUNT-EXIT (blockquote instruction, NOT a real exit)
LEDGER_TEMPLATE_EXIT = ("# ledger\n## Loop State\n- Iteration: 8\n"
                        "> **`HUNT-EXIT: T4-CONFIRMED <High|Critical>`** — впиши ТОЛЬКО после T4\n")
# real HUNT-EXIT (hunt finished with a finding)
LEDGER_REAL_EXIT = ("# ledger\n## Loop State\n- Iteration: 12\n"
                    "HUNT-EXIT: T4-CONFIRMED High\n")

try:
    # 1) DENY: active hunt + direction menu, no real HUNT-EXIT → block.
    s = new_sessions(); mk_hunt(s, "orca", "sid-A")
    r1 = run("AskUserQuestion", "sid-A", s, questions=DIRECTION_Q)
    check("1 DENY: active hunt + 'where next' direction menu → deny", is_deny(r1),
          "got %r" % (r1 if r1 else None))
    check("1 DENY: reason carries the autonomous-mode mandate", r1 is not None and
          "АВТОНОМНЫЙ" in json.dumps(r1, ensure_ascii=False))  # Russian marker kept: matches the hook's actual reason text

    # 2) ALLOW: top-up/OPSEC Watson request (burner balance) → let through.
    s = new_sessions(); mk_hunt(s, "orca", "sid-B")
    r2 = run("AskUserQuestion", "sid-B", s, questions=TOPUP_Q)
    check("2 ALLOW: top-up burner question → allow (legit Watson request)", not is_deny(r2),
          "got %r" % (r2 if r2 else None))

    # 3) ALLOW: real HUNT-EXIT in the ledger → the question (submit/next target) is legitimate.
    s = new_sessions(); mk_hunt(s, "orca", "sid-C", ledger=LEDGER_REAL_EXIT)
    r3 = run("AskUserQuestion", "sid-C", s, questions=DIRECTION_Q)
    check("3 ALLOW: real HUNT-EXIT → allow (hunt finished with a finding)", not is_deny(r3),
          "got %r" % (r3 if r3 else None))

    # 3b) DENY: template-HUNT-EXIT (blockquote instruction) does NOT count as real → deny anyway.
    s = new_sessions(); mk_hunt(s, "orca", "sid-D", ledger=LEDGER_TEMPLATE_EXIT)
    r3b = run("AskUserQuestion", "sid-D", s, questions=DIRECTION_Q)
    check("3b DENY: template-HUNT-EXIT (blockquote) + direction menu → deny (not a real exit)",
          is_deny(r3b), "got %r" % (r3b if r3b else None))

    # 4) ALLOW: foreign sid (not the marker owner) → allow (session scope).
    s = new_sessions(); mk_hunt(s, "orca", "sid-OWNER")
    r4 = run("AskUserQuestion", "sid-OTHER", s, questions=DIRECTION_Q)
    check("4 ALLOW: foreign sid → allow (not our hunt)", not is_deny(r4),
          "got %r" % (r4 if r4 else None))

    # 5) ALLOW: no active hunt (empty sessions) → an ordinary question is legitimate.
    s = new_sessions()
    r5 = run("AskUserQuestion", "sid-A", s, questions=DIRECTION_Q)
    check("5 ALLOW: no active hunt → allow", not is_deny(r5),
          "got %r" % (r5 if r5 else None))

    # 6) ALLOW: non-AskUserQuestion tool → allow (not our concern).
    s = new_sessions(); mk_hunt(s, "orca", "sid-E")
    r6 = run("Edit", "sid-E", s)
    check("6 ALLOW: non-AskUserQuestion tool (Edit) → allow", not is_deny(r6),
          "got %r" % (r6 if r6 else None))

    # 7) DENY: even an empty/option-less AskUserQuestion on an active hunt (not top-up) → block.
    s = new_sessions(); mk_hunt(s, "orca", "sid-F")
    r7 = run("AskUserQuestion", "sid-F", s, questions=[{"question": "Продолжать ту же ось или сменить?",
                                                        "header": "?", "options": []}])
    check("7 DENY: direction question without top-up vocabulary → deny", is_deny(r7),
          "got %r" % (r7 if r7 else None))

finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

print("=== AUTONOMOUS HUNT GUARD REPLAY (AskUserQuestion direction-menu → deny) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
