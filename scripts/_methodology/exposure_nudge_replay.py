# -*- coding: utf-8 -*-
"""Replay for exposure_scan_nudge.py (PreToolUse) — ad-hoc secret-grep → nudge toward secret_exposure_scanner.

Proves FIRING (Bash/PowerShell grep+secret, Grep-tool secret pattern → reminder) AND the off-switch
(calling the producer → silent, non-secret grep → silent, no hunt / foreign sid / dedup). Rule
feedback_hook_must_prove_firing: the test must prove it FIRES. Isolation via BBT_SESSIONS_DIR
(per-case temp sessions, the real sessions/ is left untouched). Real subprocess calls."""
import json, os, subprocess, sys, time, tempfile, shutil

ROOT = os.getcwd()
if not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    r = os.getcwd()
    while r and not os.path.isdir(os.path.join(r, "bug-bounty-toolkit", "sessions")):
        nxt = os.path.dirname(r)
        if nxt == r: break
        r = nxt
    ROOT = r
HOOK = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks", "exposure_scan_nudge.py")

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

def run(tool, sid, sessions_dir, command=None, pattern=None):
    payload = {"tool_name": tool, "session_id": sid}
    tin = {}
    if command is not None:
        tin["command"] = command
    if pattern is not None:
        tin["pattern"] = pattern
    if tin:
        payload["tool_input"] = tin
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

def ctx(res):
    try: return res["hookSpecificOutput"]["additionalContext"]
    except Exception: return ""

def mk_hunt(sessions_dir, slug, sid):
    d = os.path.join(sessions_dir, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write(str(int(time.time())) + "\n" + sid)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write("# ledger\n")
    return d

try:
    # 1) FIRING: Bash grep + secret token → reminder.
    s = new_sessions(); mk_hunt(s, "t1", "sid-A")
    r1 = run("Bash", "sid-A", s, command="grep -rniE 'api[_-]?key|secret|token' sessions/t1/bundle/")
    check("1 FIRING: Bash grep + secret → reminder",
          "EXPOSURE-SCAN" in ctx(r1), "ctx-head=%r" % (ctx(r1)[:60] if r1 else None))
    check("1 FIRING: reminder points to producer secret_exposure_scanner",
          "secret_exposure_scanner" in ctx(r1))

    # 1b) DEDUP: second one within the window → silence.
    r1b = run("Bash", "sid-A", s, command="rg 'apikey' bundle/main.js")
    check("1b DEDUP: repeat within window → silence", r1b is None, "got %r" % (ctx(r1b)[:40] if r1b else None))

    # 2) FIRING: rg over a source-map with 'private_key' → reminder.
    s = new_sessions(); mk_hunt(s, "t2", "sid-B")
    r2 = run("Bash", "sid-B", s, command="rg -n 'private_key' app.js.map")
    check("2 FIRING: rg + private_key → reminder", "EXPOSURE-SCAN" in ctx(r2),
          "ctx-head=%r" % (ctx(r2)[:40] if r2 else None))

    # 3) FIRING: PowerShell Select-String password → reminder.
    s = new_sessions(); mk_hunt(s, "t3", "sid-C")
    r3 = run("PowerShell", "sid-C", s, command="Get-Content main.js | Select-String 'password'")
    check("3 FIRING: PowerShell Select-String password → reminder", "EXPOSURE-SCAN" in ctx(r3),
          "ctx-head=%r" % (ctx(r3)[:40] if r3 else None))

    # 4) FIRING: Grep-tool with a secret pattern → reminder.
    s = new_sessions(); mk_hunt(s, "t4", "sid-D")
    r4 = run("Grep", "sid-D", s, pattern="AKIA[0-9A-Z]{16}")
    check("4 FIRING: Grep-tool AKIA pattern → reminder", "EXPOSURE-SCAN" in ctx(r4),
          "ctx-head=%r" % (ctx(r4)[:40] if r4 else None))

    # 5) OFF: calling the producer ITSELF (secret_exposure_scanner) → silent (this is not ad-hoc).
    s = new_sessions(); mk_hunt(s, "t5", "sid-E")
    r5 = run("Bash", "sid-E", s,
             command="py -3 scripts/_methodology/secret_exposure_scanner.py --target bundle --session-dir sessions/t5")
    check("5 OFF: calling the producer → silence", r5 is None, "got %r" % (ctx(r5)[:40] if r5 else None))

    # 5b) OFF: a secret-grep by name, but it is secret_validate (our harness) → silent.
    r5b = run("Bash", "sid-E", s, command="py -3 scripts/web2/secret_validate.py --key ghp_xxx")
    check("5b OFF: secret_validate harness → silence", r5b is None,
          "got %r" % (ctx(r5b)[:40] if r5b else None))

    # 6) OFF: non-secret grep (an ordinary code search) → silent.
    s = new_sessions(); mk_hunt(s, "t6", "sid-F")
    r6 = run("Bash", "sid-F", s, command="grep -rn 'function handleClick' src/")
    check("6 OFF: non-secret grep → silence", r6 is None, "got %r" % (ctx(r6)[:40] if r6 else None))

    # 6b) OFF: Grep-tool with a non-secret pattern → silent.
    r6b = run("Grep", "sid-F", s, pattern="useEffect")
    check("6b OFF: Grep-tool non-secret pattern → silence", r6b is None,
          "got %r" % (ctx(r6b)[:40] if r6b else None))

    # 7) OFF: no active hunt (empty sessions) → silent.
    s = new_sessions()
    r7 = run("Bash", "sid-A", s, command="grep -rn secret bundle/")
    check("7 OFF: no active hunt → silence", r7 is None, "got %r" % (ctx(r7)[:40] if r7 else None))

    # 8) OFF: foreign sid (not the marker owner) → silent.
    s = new_sessions(); mk_hunt(s, "t8", "sid-OWNER")
    r8 = run("Bash", "sid-OTHER", s, command="grep -rn apikey bundle/")
    check("8 OFF: foreign sid → silence (session scope)", r8 is None,
          "got %r" % (ctx(r8)[:40] if r8 else None))

    # 9) OFF: non-grep tool (Edit) → silent.
    s = new_sessions(); mk_hunt(s, "t9", "sid-G")
    r9 = run("Edit", "sid-G", s, command="secret token apikey")
    check("9 OFF: non-grep tool (Edit) → silence", r9 is None, "got %r" % (ctx(r9)[:40] if r9 else None))

finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

print("=== EXPOSURE-SCAN NUDGE REPLAY (ad-hoc secret-grep → producer) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
