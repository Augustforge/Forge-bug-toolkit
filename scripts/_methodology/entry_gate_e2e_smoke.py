# -*- coding: utf-8 -*-
"""End-to-end smoke for the entry hook (hunt_entry_gate.py) + the CHAIN with the completeness hook.
Answers "does it work in NEW sessions": the entry hook on a hunt URL arms a marker with the sid of THIS
very session, RESUME with a DIFFERENT sid = a new session takes over the ledger + arms itself with its own sid, then the
Stop gate (proven separately) blocks. Real subprocess calls, cleans up after itself.
NOTE: Russian prompts/strings below are test INPUTS matched by the hooks' Russian-aware regexes
(e.g. "продолжай" = "continue", "изучи" = "study", "глубже"/"везде" = "deeper"/"everywhere"); they are kept as-is."""
import json, os, subprocess, sys, time, tempfile, shutil

ROOT = os.getcwd()
if not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    r = os.getcwd()
    while r and not os.path.isdir(os.path.join(r, "bug-bounty-toolkit", "sessions")):
        nxt = os.path.dirname(r)
        if nxt == r: break
        r = nxt
    ROOT = r
SESSIONS = os.path.join(ROOT, "bug-bounty-toolkit", "sessions")
ENTRY = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks", "hunt_entry_gate.py")
STOP = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks", "hunt_completeness_gate.py")
SCRATCH = tempfile.mkdtemp()

TEST_SLUG = "gatetestproto"   # from the URL immunefi.com/bug-bounty/gatetestproto/...
TEST_DIR = os.path.join(SESSIONS, TEST_SLUG)

def win_fwd(p): return os.path.abspath(p).replace("\\", "/")

def run(hookpath, payload):
    p = subprocess.run([sys.executable, hookpath], input=json.dumps(payload).encode("utf-8"),
                       capture_output=True)
    out = (p.stdout or b"").decode("utf-8", "replace").strip()
    try:
        return json.loads(out) if out else None
    except Exception:
        return {"raw": out}

def run_entry(sid, prompt):
    return run(ENTRY, {"prompt": prompt, "session_id": sid})

def run_entry_tr(sid, prompt, model):
    """A4: entry hook with a transcript whose last assistant model = `model` (the observer)."""
    tr = os.path.join(SCRATCH, "obs_%s.jsonl" % sid)
    with open(tr, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant", "isSidechain": False,
                            "message": {"role": "assistant", "model": model,
                                        "content": "работаю"}}) + "\n")  # "работаю" = "working"
    return run(ENTRY, {"prompt": prompt, "session_id": sid, "transcript_path": win_fwd(tr)})

def write_snapshot_stub(model_version):
    """A4: minimal snapshot.json with a given model_version (simulates a previous visit)."""
    os.makedirs(TEST_DIR, exist_ok=True)
    with open(os.path.join(TEST_DIR, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": {"slug": TEST_SLUG, "date": "2026-01-01",
                            "model_version": model_version}, "functions": {}}, f)

def run_stop(sid, user_text, asst_text):
    tr = os.path.join(SCRATCH, "tr_%s.jsonl" % sid)
    with open(tr, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": user_text}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": asst_text}}) + "\n")
    return run(STOP, {"session_id": sid, "transcript_path": win_fwd(tr)})

def marker_sid():
    m = os.path.join(TEST_DIR, ".hunt_active")
    if not os.path.exists(m): return None
    lines = open(m, encoding="utf-8").read().splitlines()
    return lines[1].strip() if len(lines) >= 2 else None

def ctx(res):
    try: return res["hookSpecificOutput"]["additionalContext"]
    except Exception: return ""

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

try:
    if os.path.exists(TEST_DIR): shutil.rmtree(TEST_DIR, ignore_errors=True)

    # 1) ARM: immunefi program URL -> creates ledger + marker with this session's sid.
    URL = "https://immunefi.com/bug-bounty/%s/information" % TEST_SLUG
    r1 = run_entry("gt-sid-A", "изучи %s" % URL)
    ledger_exists = os.path.exists(os.path.join(TEST_DIR, "hypotheses.md"))
    check("1 ARM: ledger created", ledger_exists)
    check("1 ARM: marker sid == session A", marker_sid() == "gt-sid-A", "got %r" % marker_sid())
    # "АКТИВИРОВАН" = "ACTIVATED" -- literal Russian marker emitted by the hook; kept as-is
    check("1 ARM: context 'ACTIVATED'", "АКТИВИРОВАН" in ctx(r1))
    # B1: a new hunt MUST carry the EV-ANGLE forcing reminder (handed-URL EV recon).
    check("1 ARM: B1 EV-ANGLE injected on a new hunt (FIRING)", "EV-ANGLE" in ctx(r1),
          "ctx head=%r" % (ctx(r1)[:120] if ctx(r1) else None))
    # "глубже" = "deeper", "везде" = "everywhere" -- literal Russian substrings emitted by the hook; kept as-is
    check("1 ARM: B1 EV-ANGLE is NOT a reason to leave (carries 'dig deeper / bugs everywhere')",
          ("глубже" in (ctx(r1) or "").lower()) and ("везде" in (ctx(r1) or "").lower()))

    # mark the ledger as "real work" -- to check that RESUME does NOT overwrite it
    lp = os.path.join(TEST_DIR, "hypotheses.md")
    txt = open(lp, encoding="utf-8").read().replace("Iteration #:** {N}", "Iteration #:** 5  MARK-REAL-WORK")
    open(lp, "w", encoding="utf-8").write(txt)

    # 2) NEW SESSION (different sid), same target -> RESUME: ledger NOT overwritten, marker taken over by sid B.
    r2 = run_entry("gt-sid-B", "продолжай %s" % URL)
    preserved = "MARK-REAL-WORK" in open(lp, encoding="utf-8").read()
    check("2 RESUME: ledger NOT overwritten (work intact)", preserved)
    check("2 RESUME: marker taken over by sid B (a new session arms itself with its own id)",
          marker_sid() == "gt-sid-B", "got %r" % marker_sid())
    check("2 RESUME: context 'RESUME'", "RESUME" in ctx(r2))

    # 3) CHAIN: new session B armed -> Stop gate with sid B + give-up -> BLOCK.
    # (assistant text "Изучил всё, ... Считаем закрытым или другой берём?" = give-up phrasing; kept Russian)
    rs = run_stop("gt-sid-B", "продолжай",
                  "Всё изучил, in-scope High/Crit нет, таргет hardened. Считаем закрытым или другой берём?")
    blocked = bool(rs and rs.get("decision") == "block")
    check("3 CHAIN: Stop gate armed in new session B → give-up BLOCK", blocked,
          (rs or {}).get("reason", "")[:50])

    # 3b) RESUME-BY-SLUG (new session WITHOUT a link): intent word + hunt-folder name -> take over the marker.
    #     Closes the hole "continue digging <slug>" in a new session (otherwise Stop cuts off the old sid).
    r3b = run_entry("gt-sid-E", "копай дальше по %s вглубь" % TEST_SLUG)
    check("3b RESUME-BY-SLUG: marker taken over by sid E (no URL, only slug+intent)",
          marker_sid() == "gt-sid-E", "got %r" % marker_sid())
    check("3b RESUME-BY-SLUG: context 'RESUME'", "RESUME" in ctx(r3b))
    # anti-FP: same slug WITHOUT an intent word (a plain mention) -> does NOT take over.
    run_entry("gt-sid-F", "кстати помнишь %s, что там было?" % TEST_SLUG)
    check("3b anti-FP: slug mention without intent → marker NOT hijacked (stayed E)",
          marker_sid() == "gt-sid-E", "got %r" % marker_sid())

    # 3c) OBS-22: an EVAL verb ("have a look"/"break down"/"take a look") + slug = DISCUSSION, NOT
    #     resume -> the marker is NOT hijacked. Previously a broad INTENT stole the marker of a LIVE hunt when the target
    #     was merely being discussed in another session ("look at the folder <slug>").
    run_entry("gt-sid-H", "глянь папку %s, что там агент записал" % TEST_SLUG)
    check("3c OBS-22: eval 'глянь'+slug → marker NOT stolen (stayed E)",
          marker_sid() == "gt-sid-E", "got %r" % marker_sid())
    run_entry("gt-sid-I", "разбери и проанализируй почему %s сделал так" % TEST_SLUG)
    check("3c OBS-22: eval 'разбери/проанализ'+slug → marker NOT stolen (stayed E)",
          marker_sid() == "gt-sid-E", "got %r" % marker_sid())
    # conversely: a strong resume verb + slug -> takeover WORKS (resume not broken).
    run_entry("gt-sid-J", "продолжай %s" % TEST_SLUG)
    check("3c OBS-22: resume 'продолжай'+slug → takeover works (sid J)",
          marker_sid() == "gt-sid-J", "got %r" % marker_sid())

    # 3d) OBS-22-fix2: an audit message with a PASTED quote of an instance containing a
    #     hunt word ('bug-hunting' -> substring 'hunt'). The user's verb = 'смотри' ("look", a discussion).
    #     Previously 'hunt' in the quote stole the live hunt's marker onto the audit sid. Now intent is read ONLY
    #     from the framing BEFORE the quote -> NOT a takeover (marker stays J).
    run_entry("gt-sid-K", "смотри а этот %s провалил вот его ответ: я гнал bug-hunting скаутов, а не строил I-NN" % TEST_SLUG)
    check("3d OBS-22-fix2: eval 'смотри'+quote with 'bug-hunting' → marker NOT stolen (stayed J)",
          marker_sid() == "gt-sid-J", "got %r" % marker_sid())
    # anti-regression: same slug + hunt word in the FRAMING (not in the quote) -> takeover works.
    run_entry("gt-sid-L", "давай продолжим хант %s, вот его прошлый статус: closed" % TEST_SLUG)
    check("3d anti-regression: 'продолжим хант' in framing (hunt word BEFORE the quote) → takeover (sid L)",
          marker_sid() == "gt-sid-L", "got %r" % marker_sid())

    # 7) MACHINE-TEXT (chain-name incident): task-notification/system-reminder with URL|slug+intent
    #    as DATA (not user intent) -> the entry hook does NOT arm / take over. Same class
    #    as prompt injection: untrusted machine text injects into our parser.
    last_sid = marker_sid()  # gt-sid-L from block 3d
    machine_prompt = (
        "<task-notification>\n<task-id>abc123</task-id>\n"
        "Agent \"map skills\" finished. Result: hunt.md покрывает чейны "
        "%s, optimism, base; изучи их роутинг и продолжай хант по каждому.\n"
        "</task-notification>" % TEST_SLUG
    )
    run_entry("gt-sid-MACHINE", machine_prompt)
    check("7 MACHINE: task-notification with slug+intent → marker NOT taken over (stayed L)",
          marker_sid() == last_sid, "got %r (was %r)" % (marker_sid(), last_sid))
    # anti-FP: a system-reminder block with a program URL -> also does NOT arm a new session
    before7 = set(os.listdir(SESSIONS))
    run_entry("gt-sid-MACHINE2",
              "<system-reminder>изучи https://immunefi.com/bug-bounty/somenewproto/ per recall</system-reminder>")
    after7 = set(os.listdir(SESSIONS))
    check("7 MACHINE: system-reminder with program-URL → does NOT create a false session",
          "somenewproto" not in (after7 - before7), "new=%s" % (after7 - before7))

    # 7d) IMPORTANT-1: bare-text notification (Task word / no angle brackets) with a program-URL -> does NOT arm.
    before7d = set(os.listdir(SESSIONS))
    run_entry("gt-sid-BARE",
              "Task \"map skills\" completed. Result: изучи https://immunefi.com/bug-bounty/somebaretarget/ per recall")
    after7d = set(os.listdir(SESSIONS))
    check("7d BARE: Task-word notification with program-URL → does NOT create a false session",
          "somebaretarget" not in (after7d - before7d), "new=%s" % (after7d - before7d))

    # 7e) REGRESSION closed: the natural user phrase "Agent <name> completed ..." + program-URL
    #     WITHOUT quotes and without angle brackets = legitimate input -> MUST arm (bare-Agent alt removed).
    before7e = set(os.listdir(SESSIONS))
    r7e = run_entry("gt-sid-BAREOK",
                    "Agent gogo completed scan, изучи https://immunefi.com/bug-bounty/legittarget/")
    check("7e BARE-LEGIT: 'Agent gogo completed …'+URL (natural speech) → arms (output present)",
          r7e is not None, "got %r" % ("None" if r7e is None else "ARMED"))
    check("7e BARE-LEGIT: session legittarget created (URL not eaten by strip)",
          "legittarget" in (set(os.listdir(SESSIONS)) - before7e))

    # 8) CHAIN-GUARD (chain-name incident): a network name as the ONLY slug hit -> NOT resume (too generic,
    #    sits in any methodology/machine text). A real target with such a name comes in via
    #    detect() by URL, not via slug-guess. UNIT on the pure _resume_hits (no filesystem).
    sys.path.insert(0, os.path.dirname(ENTRY))
    import importlib
    heg = importlib.import_module("hunt_entry_gate")
    active = {"arbitrum", "gatetestproto"}
    # pure chain-slug + resume-intent, arbitrum is among active -> filtered out (empty)
    hits_chain = heg._resume_hits("продолжай arbitrum вглубь", active)
    check("8 CHAIN-GUARD: 'продолжай arbitrum' + active{arbitrum} → filtered out (no resume)",
          hits_chain == [], "got %r" % hits_chain)
    # real non-chain slug + resume-intent -> passes (resume not broken)
    hits_real = heg._resume_hits("продолжай gatetestproto вглубь", active)
    check("8 CHAIN-GUARD: real slug 'gatetestproto' → passes (resume works)",
          hits_real == ["gatetestproto"], "got %r" % hits_real)
    # chain-slug WITHOUT resume-intent -> empty (intent gate)
    check("8 CHAIN-GUARD: 'arbitrum' without resume-intent → empty",
          heg._resume_hits("что там по arbitrum было", active) == [], "")

    # 9) WEB-TEMPLATE: live dApp/web2 domain -> the entry hook drops in the web template (web partitions), not contract.
    sys.path.insert(0, os.path.dirname(ENTRY))
    import importlib as _il
    heg2 = _il.import_module("hunt_entry_gate")
    check("9 _is_web_target: github repo → False (contract/repo)",
          not heg2._is_web_target("https://github.com/org/repo", "изучи контракт"))
    check("9 _is_web_target: etherscan address → False",
          not heg2._is_web_target("https://etherscan.io/address/0xabc", "изучи"))
    check("9 _is_web_target: live dApp domain → True",
          heg2._is_web_target("https://app.somedex.finance/swap", "изучи dapp"))
    check("9 _is_web_target: intent '/dapphunt' forces web even on a program-URL",
          heg2._is_web_target("https://immunefi.com/bug-bounty/somedapp/", "dapphunt проверь фронт"))
    # Standoff365/BI.ZONE (Russian web2 segment): detect() arms on a bare program-URL + web2 template by default.
    check("9 standoff365: detect() arms on a bare program-URL",
          heg2.detect("https://bugbounty.standoff365.com/programs/flowwow") ==
          ("flowwow", "https://bugbounty.standoff365.com/programs/flowwow"))
    check("9 _is_web_target: standoff365 program → True (web2 default, not contract)",
          heg2._is_web_target("https://bugbounty.standoff365.com/programs/flowwow",
                              "https://bugbounty.standoff365.com/programs/flowwow"))
    check("9 _is_web_target: bi.zone program → True (web2 default)",
          heg2._is_web_target("https://bugbounty.bi.zone/programs/x", "изучай"))

    # 9g) GENERALIST web2 platforms (flowwow class: host not in PROGRAM_HOSTS -> detect()=None -> the hook was silent,
    #     ledger/model/marker were not created). hackerone/bugcrowd/intigriti/yeswehack -> detect() arms
    #     AND web2 default (in BOTH lists: PROGRAM_HOSTS + _WEB2_PROGRAM_HOSTS).
    _GENERALIST = {
        "hackerone.com": "https://hackerone.com/acmecorp",
        "bugcrowd.com":  "https://bugcrowd.com/acmecorp",
        "intigriti.com": "https://app.intigriti.com/programs/acme/acmecorp/detail",
        "yeswehack.com": "https://yeswehack.com/programs/acmecorp",
    }
    for _host, _url in _GENERALIST.items():
        _d = heg2.detect(_url)
        check("9g detect() arms on a program-URL (%s)" % _host, _d is not None,
              "got %r" % (_d,))
        check("9g _is_web_target → True (web2 default) (%s)" % _host,
              heg2._is_web_target(_url, _url))

    # 9 (user_prompt): web intent in MACHINE text does not flip the template (detection by user_prompt, not raw).
    heg2b = _il.import_module("hunt_entry_gate")
    # direct unit: _is_web_target reads what it is given; in main() it is given user_prompt (stripped).
    # check that strip removes machine intent: the string is entirely machine -> intent cut out.
    stripped = heg2b._strip_machine_text("<task-notification>frontend dapp helper</task-notification>")
    check("9 user_prompt: machine-text dapp-intent is cut by strip → will not flip the template",
          "dapp" not in stripped.lower() and "frontend" not in stripped.lower())

    # 4) DENYLIST: github reference repo + intent -> does NOT arm (no false session).
    before = set(os.listdir(SESSIONS))
    run_entry("gt-sid-C", "изучи https://github.com/gogotheauditor/audits аудит")
    after = set(os.listdir(SESSIONS))
    new_dirs = after - before
    check("4 DENYLIST: reference repo (audits) does NOT arm", "audits" not in new_dirs, "new=%s" % new_dirs)

    # 4b) OBS-15: COMPOUND reference slug (not equal to `audits`) -> detect() returns None (does not arm).
    #     Hermetic: use a slug that is certainly not in SESSIONS (do not rely on "no new folder",
    #     since a real smart-contract-audits already exists and "no-new" would pass trivially).
    r4b = run_entry("gt-sid-G", "изучи https://github.com/someorg/protocol-security-audits аудит")
    check("4b OBS-15: compound reference slug (protocol-security-audits) → does NOT arm (None)",
          r4b is None, "got %r" % (r4b if r4b is None else "ARMED"))

    # 4c) UNIT anti-over-block: the helper cuts reference repos but NOT real targets (else false-negative).
    sys.path.insert(0, os.path.dirname(ENTRY))
    import importlib
    heg = importlib.import_module("hunt_entry_gate")
    ref_true = all(heg._is_reference_slug(s) for s in
                   ["smart-contract-audits", "audits", "foo-writeups", "awesome-defi", "team-pocs"])
    tgt_false = not any(heg._is_reference_slug(s) for s in
                        ["creditsmanager", "uniswap-v4-core", "morpho-blue",
                         "gmx-synthetics", "aave-v3-origin"])
    check("4c UNIT: reference slugs → True (smart-contract-audits/foo-writeups/awesome/pocs)", ref_true)
    check("4c UNIT: real target slugs → False (creditsmanager/uniswap-v4-core/morpho-blue/…)", tgt_false)

    # 5) NO-OP: an ordinary prompt without a URL -> creates nothing.
    r5 = run_entry("gt-sid-D", "давай обсудим методологию give-up детекторов")
    check("5 NO-OP: non-hunt prompt → no output", r5 is None)

    # 6) P6 (meta-session): a meta signal WITH a link -> does NOT arm (the link = the subject
    #    of a conversation about the system, not a target). Real case: "this is not a hunt ... we're improving the system".
    r6 = run_entry("gt-sid-M1", "Смотри это не охота, мы улучшаем систему; глянь immunefi.com/bug-bounty/katana/")
    check("6 P6: 'this is not a hunt' + link → does NOT arm", r6 is None)
    r6b = run_entry("gt-sid-M2", "давай починим хуки системы на примере https://immunefi.com/bug-bounty/berachain/")
    check("6b P6: 'let's fix the hooks' + link → does NOT arm", r6b is None)
    # anti-FP: a legit hunt with a link arms as before
    r6c = run_entry("gt-sid-M3", "изучи https://immunefi.com/bug-bounty/uniswap/")
    check("6c P6 anti-FP: legit 'изучи'+link → arms (output present)", r6c is not None)

    # A4) MODEL-REAUDIT (model_version x wave_delta snapshot): a change of the observer model since the last
    #     snapshot forces a REVISIT re-audit (a new model sees what the old one missed).
    URL = "https://immunefi.com/bug-bounty/%s/information" % TEST_SLUG
    # A4a: snapshot(old) + current model(new) -> MODEL-REAUDIT in the context.
    if os.path.exists(TEST_DIR): shutil.rmtree(TEST_DIR, ignore_errors=True)
    write_snapshot_stub("claude-opus-4-7")
    r_a4a = run_entry_tr("gt-sid-A4A", "изучи %s" % URL, "claude-opus-4-8")
    check("A4a MODEL-REAUDIT: snapshot(4-7) + current(4-8) → re-audit note injected",
          "MODEL-REAUDIT" in ctx(r_a4a), "ctx-head=%r" % ctx(r_a4a)[:60])
    # A4b: snapshot == current model -> REVISIT present, but MODEL-REAUDIT silent (reverting the comparison fails it).
    if os.path.exists(TEST_DIR): shutil.rmtree(TEST_DIR, ignore_errors=True)
    write_snapshot_stub("claude-opus-4-8")
    r_a4b = run_entry_tr("gt-sid-A4B", "изучи %s" % URL, "claude-opus-4-8")
    check("A4b MODEL-REAUDIT: equal versions → REVISIT present, NO re-audit note (silent)",
          "REVISIT" in ctx(r_a4b) and "MODEL-REAUDIT" not in ctx(r_a4b))
    # A4c: entry records the current model in .observer_model (bridge to the wave_delta snapshot).
    obs = os.path.join(TEST_DIR, ".observer_model")
    check("A4c .observer_model written with the current model",
          os.path.exists(obs) and open(obs, encoding="utf-8").read().strip() == "claude-opus-4-8",
          "got %r" % (open(obs, encoding="utf-8").read().strip() if os.path.exists(obs) else None))
    # A4d: wave_delta snapshot reads .observer_model -> stamps meta.model_version.
    WD = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "wave_delta.py")
    srcdir = os.path.join(SCRATCH, "a4src"); os.makedirs(srcdir, exist_ok=True)
    open(os.path.join(srcdir, "X.sol"), "w").write("function f() public {}")
    subprocess.run([sys.executable, WD, "snapshot", TEST_SLUG, "--src", srcdir],
                   capture_output=True)
    snap = json.load(open(os.path.join(TEST_DIR, "snapshot.json"), encoding="utf-8"))
    check("A4d wave_delta snapshot stamped model_version from .observer_model",
          snap.get("meta", {}).get("model_version") == "claude-opus-4-8",
          "got %r" % snap.get("meta", {}).get("model_version"))

finally:
    if os.path.exists(TEST_DIR): shutil.rmtree(TEST_DIR, ignore_errors=True)
    # session B's marker may have left .loop_guard/.depth_guard in TEST_DIR (removed by rmtree). Clean scratch.
    shutil.rmtree(SCRATCH, ignore_errors=True)
    for stray in ("audits",):  # in case the denylist is broken -- do not leave junk
        d = os.path.join(SESSIONS, stray)
        # do NOT delete -- audits may be real; only warn
        if os.path.exists(os.path.join(d, ".hunt_active")) and stray in ("audits",):
            pass
    # MINOR-3 (test-hygiene): diagnostic/pre-fix runs may leave stray folders of these
    # EXACT test slugs (not real targets) -- clean up with an explicit list + the gt-sid-* prefix.
    for stray in ("somenewproto", "somebaretarget", "legittarget"):
        d = os.path.join(SESSIONS, stray)
        if os.path.isdir(d): shutil.rmtree(d, ignore_errors=True)
    for name in list(os.listdir(SESSIONS)):
        if name.startswith("gt-sid-"):
            shutil.rmtree(os.path.join(SESSIONS, name), ignore_errors=True)

print("=== ENTRY-GATE END-TO-END SMOKE (+ chain with the Stop gate, new session) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
