# -*- coding: utf-8 -*-
"""Replay for the LEDGER-STATE arming of the engine (2026-08-18, "hold for a week" behavior).

Proves: the engine arms by LEDGER STATE (a fresh substantive active ledger that THIS session edits),
the marker = a fast cache. The key part is the META-EXCLUSION (a session editing toolkit code scripts/hooks|_methodology
= debugging, we do NOT arm — something re-arm lacked). Rule feedback_hook_must_prove_firing: the test proves both
FIRING (arm) and protections (meta / exit / manual / thin / stale / read-only). Temporary `_lstest_*` in the
REAL sessions/ (arming computes root from __file__), cleaned up."""
import importlib.util, os, sys, time, tempfile, shutil, json

_HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "sessions")
SCRATCH = tempfile.mkdtemp()
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

SUBSTANTIAL = ("# t — Registry\n## Loop State\n- HUNT-MODE: AUTONOMOUS\n"
               "## Active\n- **H-01** a\n- **H-02** b\n- **I-03** c\n- **I-04** d\n")
EXIT = SUBSTANTIAL + "\nHUNT-EXIT: T4-CONFIRMED High\n"
MANUAL = SUBSTANTIAL + "\n- **HUNT-MODE: MANUAL**\n"
THIN = "# t\n## Loop State\n- **H-01** one\n"   # <3 ids

def mk_ledger(slug, body, age_sec=0):
    d = os.path.join(SESSIONS, slug)
    if os.path.exists(d): shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p = os.path.join(d, "hypotheses.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    if age_sec:
        old = time.time() - age_sec
        os.utime(p, (old, old))
    return d

def mk_tr(edits=None, reads=None, toolkit=None):
    """Transcript: edits/reads = slugs (Edit/Read of sessions/{slug}/hypotheses.md); toolkit = paths under
    scripts/hooks|_methodology (Edit) → meta signal."""
    p = os.path.join(SCRATCH, "tr_%d.jsonl" % len(results))
    lines = []
    for slug in (edits or []):
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit",
             "input": {"file_path": "sessions/%s/hypotheses.md" % slug}}]}}))
    for slug in (reads or []):
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Read",
             "input": {"file_path": "sessions/%s/hypotheses.md" % slug}}]}}))
    for fp in (toolkit or []):
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": fp}}]}}))
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p

CLEANUP = []
def mk(slug, body=SUBSTANTIAL, age=0):
    d = mk_ledger(slug, body, age); CLEANUP.append(d); return d

def armed(slug):
    return os.path.exists(os.path.join(SESSIONS, slug, ".hunt_active"))

try:
    # 1) ARM: the session edits a fresh substantive active ledger → armed + marker created.
    mk("_lstest_a")
    r1 = g._ledger_state_active("sid-A", mk_tr(edits=["_lstest_a"]))
    check("1 ARM: fresh substantive active ledger, the session EDITS it → armed",
          r1 and armed("_lstest_a"), "r=%s mk=%s" % (r1, armed("_lstest_a")))

    # 2) META-EXCLUSION: the session edits toolkit code (scripts/hooks) → NOT armed, even if it edited a ledger.
    mk("_lstest_b")
    tp = mk_tr(edits=["_lstest_b"], toolkit=["scripts/hooks/hunt_completeness_gate.py"])
    r2 = g._ledger_state_active("sid-B", tp)
    check("2 META-EXCL: the session edited toolkit code → NOT armed (debugging, not a hunt)",
          not r2 and not armed("_lstest_b"), "r=%s" % r2)

    # 3) READ-ONLY inspection (Read, not Edit) → NOT armed (a meta session reads other people's ledgers).
    mk("_lstest_c")
    r3 = g._ledger_state_active("sid-C", mk_tr(reads=["_lstest_c"]))
    check("3 READ-ONLY: only Read of a ledger (not Edit) → NOT armed", not r3 and not armed("_lstest_c"), "r=%s" % r3)

    # 4) HUNT-EXIT → NOT armed (finished with success).
    mk("_lstest_d", EXIT)
    r4 = g._ledger_state_active("sid-D", mk_tr(edits=["_lstest_d"]))
    check("4 HUNT-EXIT → NOT armed", not r4, "r=%s" % r4)

    # 5) HUNT-MODE: MANUAL → NOT armed (emergency off).
    mk("_lstest_e", MANUAL)
    r5 = g._ledger_state_active("sid-E", mk_tr(edits=["_lstest_e"]))
    check("5 MANUAL → NOT armed", not r5, "r=%s" % r5)

    # 6) THIN (<3 I/H-NN) → NOT armed (not substantive).
    mk("_lstest_f", THIN)
    r6 = g._ledger_state_active("sid-F", mk_tr(edits=["_lstest_f"]))
    check("6 THIN (<3 I/H-NN) → NOT armed", not r6, "r=%s" % r6)

    # 7) STALE (>12h) → NOT armed.
    mk("_lstest_g", SUBSTANTIAL, age=13 * 3600)
    r7 = g._ledger_state_active("sid-G", mk_tr(edits=["_lstest_g"]))
    check("7 STALE >12h → NOT armed", not r7, "r=%s" % r7)

    # 8) FRESHEST-FIRST: 2 touched → arm the freshest.
    df = mk("_lstest_fresh", SUBSTANTIAL, age=60)
    ds = mk("_lstest_stale2", SUBSTANTIAL, age=3 * 3600)
    r8 = g._ledger_state_active("sid-H", mk_tr(edits=["_lstest_stale2", "_lstest_fresh"]))
    check("8 FRESHEST-FIRST: arm the freshest of 2 touched",
          r8 and armed("_lstest_fresh") and not armed("_lstest_stale2"),
          "r=%s fresh=%s stale=%s" % (r8, armed("_lstest_fresh"), armed("_lstest_stale2")))

    # 9) RECLAIM of a FOREIGN marker (2026-08-18): the marker was hijacked by another session (sid-OLD, e.g. a meta-mention
    #    of the slug re-armed it), while the REAL hunter (sid-I) actively edits the ledger → takes the marker back.
    mk("_lstest_i")
    with open(os.path.join(SESSIONS, "_lstest_i", ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\nsid-OLD" % int(time.time()))
    r9 = g._ledger_state_active("sid-I", mk_tr(edits=["_lstest_i"]))
    mk_owner = ""
    try:
        mk_owner = open(os.path.join(SESSIONS, "_lstest_i", ".hunt_active")).read().splitlines()[1]
    except Exception:
        pass
    check("9 RECLAIM: foreign/hijacked marker + I actively edit the ledger → takeover to current_sid",
          r9 and mk_owner == "sid-I", "r=%s owner=%s" % (r9, mk_owner))

    # 10) _session_ledger_edits contract: Edit → edited, toolkit → is_meta.
    ed, meta = g._session_ledger_edits(mk_tr(edits=["_lstest_a"], toolkit=["scripts/_methodology/x.py"]))
    check("10 _session_ledger_edits: Edit ledger + toolkit-edit → edited+is_meta",
          "_lstest_a" in ed and meta, "ed=%s meta=%s" % (sorted(ed), meta))

    # 11) META-GUARD (2026-08-18): a pure debug session (edits ONLY toolkit, does not touch ledgers) →
    #     is_meta=True. This catches the main() guard `if _is_meta: sys.exit(0)` ON TOP of the owned marker — the entry hook
    #     arms the hunt with my sid on a mention, but the meta guard still does not let my session be held.
    ed2, meta2 = g._session_ledger_edits(mk_tr(toolkit=["scripts/hooks/hunt_completeness_gate.py"]))
    check("11 META-GUARD: pure toolkit session (0 ledger-edits) → is_meta (the main guard releases the marker owner)",
          meta2 and not ed2, "meta=%s ed=%s" % (meta2, sorted(ed2)))

finally:
    for d in CLEANUP:
        if os.path.exists(d): shutil.rmtree(d, ignore_errors=True)
    for name in list(os.listdir(SESSIONS)):
        if name.startswith("_lstest_"):
            shutil.rmtree(os.path.join(SESSIONS, name), ignore_errors=True)
    shutil.rmtree(SCRATCH, ignore_errors=True)

print("=== LEDGER-STATE ARM REPLAY (the engine holds by state, meta session excluded) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
