#!/usr/bin/env python3
"""Stop hook — AUTONOMOUS Hunt-Loop engine + completeness-gate.

Purpose (2 roles):
  A) AUTONOMOUS LOOP ENGINE (2026-07-02): active hunt => the turn does NOT end by default -
     the Stop hook blocks the exit, forcing the next single-pick. This implements codex-driver-loop
     ("a single call has no option to return to the user") WITHOUT the operator typing /loop:
     they just give the hunt target, then the loop spins on its own (hours/days) until it finds High/Critical.
     Medium/Low are picked up and submitted AS WE GO, but they do NOT end the loop (operator 2026-07-06).
  B) COMPLETENESS-GATE: prevent a premature abort / dumping findings into chat /
     losing Loop State (all based on real past hunts).
Lesson (reference_brutecat_ai): an instruction in the prompt is not enough - a gate/engine in the hook is needed.

The only legitimate loop exits (otherwise - block, the turn continues):
  - (success) the ledger has `HUNT-EXIT: T4-CONFIRMED <High|Critical>` - written AFTER a real T4;
              Medium/Low do NOT release (banked along the way, but not an exit - operator 2026-07-06);
  - (release) the operator themselves said a RELEASE word ("we're leaving" / "take another one" / "stop hunt" ...);
  - (manual)  the ledger has `HUNT-MODE: MANUAL` - emergency off (then block only on give-up).
  - (off)     the ledger has `HUNT-MODE: OFF` - FULL disarm of a misfire marker (the entry hook falsely
              armed, e.g. a github link from subagent output): hunt_is_active=False, the gate is silent.
Anti-spin safety: circuit_broken() releases ONLY the default loop after 8 blocks in a row with no ledger write
(genuine dead-spin repeats). WARNING 2026-07-07 (operator: "token-burn insurance is not
needed"): the 30-min timer was REMOVED - it confused a legit read-heavy phase (audits/scouts, 30 min without a ledger write)
with a dead loop and released the loop; worse - it released exactly on a give-up message (see GIVE-UP
NEVER RELEASES below). GIVE-UP (REASON) is NOT released by the circuit breaker at all - held for good.
stop_hook_active is NOT used for bail (otherwise the loop would die after the 1st block).
Keep-alive: each block bumps the mtime of .hunt_active so a long loop does not expire under the 24h filter.

Fail-open: any parsing/logic error -> exit 0 (never block or loop because of a breakage).
"""
import sys
import json
import os
import re
import glob
import time
import datetime


def _read_marker(marker_path):
    """(valid, sid). valid=False if the marker is empty/whitespace/broken (0 bytes from an interrupted write by
    the entry hook: open('w') truncated to 0, the process died before write). sid = 2nd non-empty line or None
    (legacy - a marker without a recorded session_id)."""
    try:
        with open(marker_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return (False, None)
    if not raw.strip():
        return (False, None)  # 0 bytes / whitespace = broken marker, NOT armed (cross-fire incident 2026-07-08)
    lines = raw.splitlines()
    sid = lines[1].strip() if len(lines) >= 2 and lines[1].strip() else None
    return (True, sid)


def _marker_sid(marker_path):
    """session_id from the marker (2nd line). None = legacy/missing/broken. (compatibility)"""
    return _read_marker(marker_path)[1]


# HUNT-MODE: OFF = FULL disarm of a misfire marker (stronger than MANUAL). MANUAL = "a real hunt, manual
# wheel, but we still catch give-up"; OFF = "this is NOT a hunt AT ALL" (the entry hook falsely armed -
# classic: a github link from research-subagent output, e.g. a public audits repo path -> sessions/audits).
# On OFF hunt_is_active=False: methodology/meta sessions where I quote abort vocabulary are not caught.
# WARNING BUG-FIX (2026-07-07): the control-token regexes MATCHED THE TEMPLATE INSTRUCTION (the ledger describes
# `HUNT-MODE: MANUAL` / `HUNT-EXIT: T4-CONFIRMED <High|Critical>` in its RULES) -> on EVERY fresh hunt
# success-exit / manual-mode falsely fired -> the completeness-gate was SILENTLY DISARMED. Fix: MANUAL/OFF -
# line-anchored (real activation = token at the START of a line, optional bullet/blockquote; template instructions
# are mid-line / in backticks -> do not match). _EXIT_RE - forbids `<` (placeholder = `<High|Critical>`,
# real token = `High`/`Critical` without angle brackets). Fail-safe: a miss = we do NOT exit / stay autonomous.
_OFF_RE = re.compile(r"(?m)^[ \t>*\-]{0,8}HUNT-MODE[:*\s]*OFF\b", re.I)  # OBS-5: tolerates markdown `- **HUNT-MODE:** OFF`


def _ledger_disarmed(marker_path):
    """True if the sibling hypotheses.md carries `HUNT-MODE: OFF` (full disarm of a misfire marker).
    Fail-safe: no file/read error -> False (we do NOT disarm - better to keep the gate than to accidentally
    remove it from a REAL hunt on a read error)."""
    try:
        ledger = os.path.join(os.path.dirname(marker_path), "hypotheses.md")
        with open(ledger, "r", encoding="utf-8") as f:
            return bool(_OFF_RE.search(f.read()))
    except Exception:
        return False


def _owned_markers(current_sid):
    """Fresh (<24h) .hunt_active markers belonging to THIS session - a list of (mtime, path).
    Session scope against cross-fire. WARNING FIX 2026-07-08 (cross-fire incident): the old logic
    'marker without sid = may be mine -> enable' was ITSELF the source of cross-fire - an empty/
    sidless marker of someone else's (or a live one in a neighbouring window) hunt armed ANY session, including
    meta/system ones. Now, since the entry hook ALWAYS writes sid:
      - a broken/0-byte marker (interrupted write) -> always skip;
      - current_sid is KNOWN -> we own ONLY a marker with OUR sid (sidless/foreign -> not ours:
        had it been my hunt, the entry hook would have staked my sid);
      - current_sid is empty (the hook got no id) -> fallback: sidless = 'maybe mine' (enable),
        cut off only a known foreign sid.
    A broken sidless marker of a live hunt needs to be RE-armed (a prompt with intent+slug/URL in
    ITS window -> the entry hook rewrites it correctly), not silently cross-fire everywhere."""
    out = []
    try:
        here = os.path.abspath(__file__)
        # hooks -> scripts -> bug-bounty-toolkit -> project root
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        sessions = os.path.join(root, "sessions")
        now = time.time()
        for m in glob.glob(os.path.join(sessions, "*", ".hunt_active")):
            if now - os.path.getmtime(m) >= 24 * 3600:
                continue
            valid, sid = _read_marker(m)
            if not valid:
                continue  # 0 bytes / broken marker -> not armed (cross-fire fix)
            if current_sid:
                if sid != current_sid:
                    continue  # we know our own id -> own only our marker (sidless/foreign -> skip)
            elif sid is not None:
                continue  # no id came -> cut off only a marker with a known (foreign) sid
            if _ledger_disarmed(m):
                continue  # HUNT-MODE: OFF -> misfire, not counted as an active hunt (full disarm)
            out.append((os.path.getmtime(m), m))
    except Exception:
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Background work (subagent / workflow) - "in flight" detection (phase 3, rescoped 2026-07-28).
#
# Why not "tool_use without tool_result": a background launch returns an ack IMMEDIATELY ("Async agent launched
# successfully"), the result arrives as a separate event. The real pair is the launch id `toolu_...` <->
# `<task-notification><tool-use-id>toolu_...</tool-use-id>`. Verified on real transcripts.
#
# WARNING P7-CORE (2026-07-29): count as pending ONLY truly background launches (Workflow is always async;
# Agent/Task - only with `input.run_in_background=true`). A foreground subagent blocks the main turn,
# is already finished by Stop and sends NO notification - the old code held it as a permanent hang, so a single
# synchronous scout fan-out released the Stop gate on EVERY turn and the whole autoloop/structural gates were no-ops.
#
# What the hook does about it: while work is in flight - it RELEASES the turn. The harness will re-wake me
# with a notification on its own, whereas blocking would force digging in parallel with the scouts and duplicating them.
# WARNING A watchdog is mandatory: a crashed/lost agent never sends a notification, and without a timeout
# "release while in flight" = a silently dead autoloop. Older than BG_WATCHDOG -> gate as usual.
BG_WATCHDOG = 900          # sec (15 min) - longer than this, "in flight" is considered lost
_BG_TOOLS = ("Agent", "Task", "Workflow")
_NOTIF_ID_RE = re.compile(r"<tool-use-id>\s*([A-Za-z0-9_\-]+)\s*</tool-use-id>")

# ─── WORKLIST DRIVER (2026-08-11) — feature-flag ────────────────────────────────
# Plan: methodology/plans/worklist_driver_plan.md
# Diagnosis: the hunt plan lives as passive TEXT in the ledger -> the LLM drifts every iteration (give-up /
# going the wrong way when switching axis / a forgotten undup). Fix: a machine registry of atoms
# (section `## Atom Registry`) dictates the NEXT atom = the OPEN row with max rank, rather than "the
# instance picks itself". Stage 1 (behind this flag) - two ADDITIVE gates on the new registry:
#   - active_pick_not_from_queue          - `Current pick` must = the registry ACTIVE row,
#                                           exactly 1 ACTIVE, ACTIVE = max-rank among OPEN+ACTIVE.
#   - active_atom_closed_without_narrative - linking gate (C3): an atom CLOSED without a proof entry in
#                                           Refuted/Verifier Log/Axes-Closed would blind 39 prose gates.
# ROLLBACK (operator: "going back to the old one must be painless"): WORKLIST_DRIVER_ENABLED = False -> both gates
# go silent immediately (old behaviour 1:1, runtime-off without git); full code rollback = git reset --hard
# <baseline>. The gates are ADDITIVE + fail-safe: silent until the registry is filled with real atoms (no section
# `## Atom Registry` in web/legacy ledgers; placeholder row `{AX-01}` = not an atom) -> zero
# blast radius on existing hunts. Stages 2-3 (next_atom driver, verifier channel) are also behind the flag.
WORKLIST_DRIVER_ENABLED = True


def _parse_ts(s):
    try:
        return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        return None


def pending_bg_work(transcript_path):
    """(how many background launches without a notification, age of the OLDEST in seconds|None).
    Fail-open: any parsing breakage -> (0, None), i.e. the hook behaves as before."""
    launched, done = {}, set()
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                ts = _parse_ts(o.get("timestamp") or "")
                # 1) launches
                msg = o.get("message", o)
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use" \
                                and b.get("name") in _BG_TOOLS and b.get("id"):
                            # P7-CORE (2026-07-29): "in flight" at Stop time can ONLY be a truly
                            # background launch. A foreground subagent (Agent/Task WITHOUT
                            # run_in_background=true) BLOCKS the main turn - by Stop it is already
                            # FINISHED, the result is in context, it sends NO task-notification (synchronous).
                            # The old code counted it as pending -> a permanent hang (the notification never comes) ->
                            # the bg-watchdog released EVERY Stop -> the autoloop and ALL structural gates
                            # (scout/depth/model/give-up) were bypassed by one scout fan-out. Measured on
                            # a real hunt: 12 foreground scouts, 0 task-notifications, 0 Stop blocks for the hunt.
                            # Workflow is always async (returns a task-id) -> always bg.
                            inp = b.get("input") or {}
                            is_bg = b.get("name") == "Workflow" or inp.get("run_in_background") is True
                            if is_bg:
                                launched[b["id"]] = ts
                # 2) completion notifications (may also sit in the str-content of a top-level record)
                for blob in (o.get("content"), content):
                    if isinstance(blob, str) and "task-notification" in blob:
                        done.update(_NOTIF_ID_RE.findall(blob))
                    elif isinstance(blob, list):
                        for b in blob:
                            t = b.get("text") if isinstance(b, dict) else (b if isinstance(b, str) else "")
                            if t and "task-notification" in t:
                                done.update(_NOTIF_ID_RE.findall(t))
    except Exception:
        return 0, None
    # OBS-1 (2026-07-28): previously returned the age of the OLDEST pending (`min(stamps)`).
    # Defect: "permanent hangs" (a launch whose `task-notification` ID did not match) accumulate in the transcript,
    # their age grows without bound (>watchdog) and MASKS fresh background work -> the bg-watchdog never
    # released the turn, even when a fresh subagent was really running. Fix: (1) drop the lost ones (older than
    # LOST - the notification clearly will not come); (2) return the age of the YOUNGEST pending ("is there AT LEAST ONE
    # fresh background job"), not the oldest - it is fresh work that requires releasing the turn.
    now = time.time()
    LOST = 4 * BG_WATCHDOG      # >1h without a notification = launch lost (notif did not match), do not block
    pend = [t for i, t in launched.items()
            if i not in done and not (t and (now - t) > LOST)]
    if not pend:
        return 0, None
    stamps = [t for t in pend if t]
    if not stamps:
        return len(pend), None
    return len(pend), max(0.0, now - max(stamps))


# -- parallel-during-fanout (2026-08-13 + 2026-08-19, operator point 4) --------------------------------
# The fan-out (Workflow) grinds 20-30 min in the background while the main agent IDLES waiting for a notification. Rule:
# fan-out = explore-wide (background, finds NEW places); main agent = exploit-deep (serial, opens up the ALREADY
# CHOSEN strongest thread) - run IN PARALLEL (without a fan-out the agent itself found a live bug -> hands must not
# wait). Release-on-bg: force a parallel depth-drive ONLY with a designated Depth-Lead; NO chosen
# thread -> release (2026-08-19, operator): the hunter either pays down ledger debt OR WAITS for the fan-out - idle is legit here.
# Otherwise (the old "force on any Active H-NN") a hunter with no thread invented shallow busywork
# on invariants that the FAN-OUT is itself checking -> premature "sound" + duplication.
PARALLEL_DRIVE_REASON = (
    "PARALLEL-DRIVE (2026-08-13 + 2026-08-19, operator). %d background launches "
    "(fan-out/scout) in flight (age %ds), and you HAVE the strongest thread SELECTED (**Depth-Lead**). DO NOT IDLE "
    "for the 20-30 min wait on the fan-out: fan-out = explore-wide (background, finds NEW places), YOU = exploit-deep (serial, "
    "open THIS SELECTED thread in depth >=5 layers to a PoC). Without a fan-out one agent found a live bug - hands do not "
    "wait. WARNING Discipline: drive ONLY the designated Depth-Lead (a thread the fan-out will NOT override), NOT a "
    "shallow spot-check of invariants (that is the fan-out's JOB - duplication + premature 'sound'). The notification "
    "will come - you will merge the leads into the ledger. Do the next depth step of THIS thread NOW (satisfiable - the fan-out "
    "continues in the background; no depth on the thread and no ledger debt -> it is acceptable to WAIT for the fan-out, idle is legit)."
)


def _can_drive_parallel(current_sid):
    """parallel-drive (2026-08-13 + 2026-08-19, operator): force serial-depth IN PARALLEL with the background
    fan-out ONLY with a **designated Depth-Lead** (a specific STRONGEST thread chosen in Loop State).
    Previously we also forced on ">=1 live Active H-NN" - but in a mature hunt open H-NNs ALWAYS exist -> the gate
    over-forced, and a hunter with no real chosen thread invented shallow busywork: spot-checking
    invariants that the FAN-OUT was checking at that very moment -> a premature "A53 sound" (getManagedAssets
    only) + duplication of the fan-out's work. Rule (operator): the parallel hand = exploit-deep on an ALREADY chosen thread;
    no designated Depth-Lead -> we do NOT force (release) - the hunter pays down ledger debt (the LEDGER-FIRST gates lead
    it) OR WAITS for the fan-out (idle is legit: the fan-out does explore-wide, the harness re-wakes with a notification).
    "A pile of open H-NNs without a chosen thread" != a drive signal. Fail-safe: no ledger / breakage -> False."""
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return False
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _has_valid_exit(lt):
        return False                                     # hunt finished - do not drive
    return _depth_lead_active(lt)                        # ONLY a designated Depth-Lead (not "any Active H-NN")


def hunt_is_active(current_sid):
    """The gate is active ONLY during a real hunt IN THIS session - otherwise meta conversations
    about methodology (where I quote abort vocabulary) or a hunt in a neighbouring window would be caught as
    false positives. Marker: sessions/{target}/.hunt_active, fresh (<24h), scoped
    to session_id. No fresh marker of its own -> not on a hunt."""
    return bool(_owned_markers(current_sid))


# -- LEDGER-STATE as the source of truth for arming (2026-08-18, operator: "should hold for a week") --
# Problem: the engine is armed ONLY by the `.hunt_active` marker, and it is fragile - the entry hook sets it only on
# a recognised hunt-URL, it is sid-scoped (breaks in a new session / after /compact) and gets lost. A clean URL entry in one session
# kept the marker alive. Multi-session hunts lose it -> hunt_is_active=False ->
# the engine is silent -> the hunter freely stops and waits. Fix: marker = a fast CACHE; truth = the ledger STATE.
# A hunt is active if THIS session is actively EDITING a fresh substantive active hunt ledger. The key part is the
# META-EXCEPTION (which the re-arm lacked -> it falsely held debug sessions): a session editing toolkit code
# (scripts/hooks|_methodology) = debugging the system, NOT a hunt (the hunter NEVER touches this code).
_TOOLKIT_EDIT_RE = re.compile(r"scripts[/\\]+(?:hooks|_methodology)[/\\]", re.I)
_LEDGER_EDIT_PATH_RE = re.compile(r"sessions[/\\]+([A-Za-z0-9_.\-]+)[/\\]+hypotheses\.md")
_A_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def _session_ledger_edits(tpath):
    """(edited_slugs, is_meta): from the transcript - which sessions/{slug}/hypotheses.md THIS session WROTE to
    (Edit/Write; Read/Grep inspection does NOT count), and whether it edited toolkit code (-> a debug session). One pass."""
    edited, is_meta = set(), False
    if not tpath or not os.path.exists(tpath):
        return (edited, is_meta)
    try:
        with open(tpath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "tool_use" not in line:
                    continue
                if "hypotheses.md" not in line and "scripts" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message") or obj
                content = msg.get("content") if isinstance(msg, dict) else None
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"
                            and b.get("name") in _A_WRITE_TOOLS):
                        continue
                    tin = b.get("input") or {}
                    fp = tin.get("file_path") or tin.get("notebook_path") or ""
                    if not isinstance(fp, str):
                        continue
                    if _TOOLKIT_EDIT_RE.search(fp):
                        is_meta = True
                    m = _LEDGER_EDIT_PATH_RE.search(fp)
                    if m:
                        edited.add(m.group(1))
    except Exception:
        return (set(), False)
    return (edited, is_meta)


def _real_ledger_hunt_exit(lt):
    """A real HUNT-EXIT: T4-CONFIRMED line (not a blockquote template / backtick / placeholder)."""
    for ln in (lt or "").splitlines():
        s = ln.lstrip()
        if s.startswith(">") or "`" in ln or "{" in ln:
            continue
        if re.search(r"HUNT-EXIT\s*:\s*T4-CONFIRMED\s+(?:High|Critical)", ln, re.I):
            return True
    return False


def _ledger_state_active(current_sid, tpath):
    """The engine is ON if THIS session is actively editing a FRESH (<12h) SUBSTANTIVE (>=3 I/H-NN) active (no
    real HUNT-EXIT / `HUNT-MODE: MANUAL`) hunt ledger. A meta session (toolkit edit) is excluded. We arm the
    freshest one -> recreate the marker on current_sid (self-heal marker-falloff). True if armed. Additive:
    called ONLY when there is no marker of its own (a live-marker hunt never gets here -> zero changes)."""
    if not current_sid:
        return False
    edited, is_meta = _session_ledger_edits(tpath)
    if is_meta or not edited:
        return False                                       # debug session / did not edit a ledger -> not a hunt
    try:
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        sessions = os.path.join(root, "sessions")
        now = time.time()
        cand = []
        for slug in edited:
            led = os.path.join(sessions, slug, "hypotheses.md")
            try:
                cand.append((os.path.getmtime(led), slug))
            except OSError:
                continue
        for _mt, slug in sorted(cand, reverse=True):        # freshest (= the one actually in progress)
            sdir = os.path.join(sessions, slug)
            mk = os.path.join(sdir, ".hunt_active")
            led = os.path.join(sdir, "hypotheses.md")
            # WARNING do NOT skip an existing marker (2026-08-18): we get here ONLY if there is no FRESH marker of
            # our own (hunt_is_active=False). So the marker here is either FOREIGN (hijacked by a meta mention of the
            # slug: the entry hook re-armed it with the meta session's sid -> the real hunter lost ownership and
            # stopped being held), or MINE but stale (>24h). In BOTH cases, since I am actively editing a fresh
            # substantive ledger - I am the real worker, so I TAKE OVER the marker (overwrite below on current_sid).
            try:
                if now - os.path.getmtime(led) >= 12 * 3600:
                    continue                                # not fresh
                with open(led, "r", encoding="utf-8") as f:
                    lt = f.read()
            except Exception:
                continue
            if _real_ledger_hunt_exit(lt):
                continue                                    # finished with success
            if re.search(r"(?im)^\s*[-*>#\s]*\**\s*HUNT-MODE:\s*MANUAL", lt):
                continue                                    # emergency off
            if len(set(re.findall(r"(?i)\b(?:H|I|AC|TB)-\d+\b", lt))) < 3:
                continue                                    # not substantive (profile-agnostic: contract I/H + web AC/TB)
            try:
                with open(mk, "w", encoding="utf-8") as f:
                    f.write(str(int(now)) + "\n" + current_sid)
                return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def extract_text(msg):
    if isinstance(msg, str):
        return msg
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


# S35.4(b) notification-border (Task 6, confirmed hole). `last_user`/`last_assistant`
# below are read FROM THE TRANSCRIPT by role (`type"/"role" == "user"`), not from the raw prompt. The async completion
# of a background Agent/Task/Workflow arrives as a transcript record `{"type":"user", "content": "<task-notification>
# ...</task-notification>"}` (`pending_bg_work` above already parses this for the BG-watchdog; the same format
# is reproduced by the `notification()` fixture in `bg_watchdog_replay.py`) - i.e. the task-notification lands
# EXACTLY in the role that this parser treats as "the operator wrote". Same class as the earlier cross-session incident
# (`hunt_entry_gate.py` already fixes it via `_MACHINE_BLOCK_RE`/`_strip_machine_text` on the UserPromptSubmit
# input) - here there was NO equivalent strip: RELEASE/INFO_REQUEST would match against the
# CONTENT of the notification (a subagent report, which could carry hostile text from an external page/
# repo/audit - "we're leaving"/"next target"/"why" -> a false early release of the turn OR false suppression of
# LEDGER-LIVE/MODEL nudges). `prompt_injection_guard.py` does NOT catch this (PostToolUse sees only
# the tool_response of real synchronous calls; an async task-notification has no tool_response - documented
# in its own header as a named remnant -> Plan 6). Fail-open: error -> original text.
_MACHINE_BLOCK_RE = re.compile(
    r"<task-notification>.*?</task-notification>"
    r"|<system-reminder>.*?</system-reminder>"
    r"|<task-id>.*?</task-id>"
    r"|\[SYSTEM NOTIFICATION[^\]]*\][^\n]*(?:\n(?!\n)[^\n]*)*"
    r"|(?:Agent|Task)\s+\"[^\"]+\"\s+(?:finished|completed)[^\n]*(?:\n(?!\n)[^\n]*)*"
    r"|<function_results>.*?</function_results>",
    re.I | re.S)


def _strip_machine_text(text):
    """Strip machine insertions (task-notification/system-reminder/tool-id/agent notifications) -
    their content = external DATA, not the operator's intent. Fail-open: error -> original text.
    For the ASSISTANT role (my text MAY discuss these tags in prose) - non-greedy, so as not to
    over-strip legit reasoning. The USER role is stripped more robustly - see `_strip_machine_text_user`."""
    try:
        return _MACHINE_BLOCK_RE.sub(" ", text or "")
    except Exception:
        return text or ""


# S35.4(b) hardening (Plan 6 fix1, nested close-tag bypass). The non-greedy `_MACHINE_BLOCK_RE`
# closes on the FIRST `</task-notification>`; an attacker whose content a subagent echoes INSIDE the
# notification block (we read hostile external text via scouts) inserts a premature
# `</task-notification>` into the body -> the tail with `move on`/"we're leaving" survives in `last_user` -> a false RELEASE ->
# the loop silently stops. Key asymmetry: genuine operator/user text NEVER contains
# harness tags, while my assistant text MAY (discusses them in prose). So for the USER role: any
# machine marker => the entire tail from the FIRST marker is machine - we take only the genuine prefix BEFORE it,
# and cut the rest (robust to a nested fake close-tag). Over-stripping user content is safe:
# there are no legit tags there, nothing to protect. The ASSISTANT path is NOT touched by this strip (see _strip_machine_text).
_USER_MACHINE_MARKERS = (
    "<task-notification>", "</task-notification>",
    "<system-reminder>", "</system-reminder>",
    "<task-id>", "</task-id>",
    "<function_results>", "</function_results>",
    "[system notification",
    # Backup to the isMeta skip (2026-08-18): Stop-hook feedback is injected as a user msg with
    # the prefix "Stop hook feedback:". Usually caught by the isMeta skip in main(), but if the harness did not set the field
    # - cut from the prefix (the whole reason is machine-generated, genuine operator text is not written like that).
    "stop hook feedback:",
)


def _strip_machine_text_user(text):
    """USER role: genuine operator text without harness tags. Any machine marker -> take only the prefix
    BEFORE THE FIRST marker (robust to a nested fake close-tag that the non-greedy strip missed).
    No markers -> text untouched (a genuine "we're leaving"/RELEASE phrase survives). Fail-open: error -> original text."""
    try:
        t = text or ""
        low = t.lower()
        cut = min((i for i in (low.find(m) for m in _USER_MACHINE_MARKERS) if i != -1), default=-1)
        if cut != -1:
            return t[:cut]
        return t
    except Exception:
        return text or ""


# The operator explicitly releases from the target -> do NOT block (their prerogative). Phrase lists below = Russian DATA, kept verbatim.
RELEASE = [
    "уходим", "уходи с", "бери другую", "другую цель", "другой таргет",
    "смени цель", "сменить цель", "сменим таргет", "стоп хант", "стоп охот",
    "заканчивай хант", "хватит копать", "переключаемся", "переключись",
    "move on", "next target", "go next", "это нормально уйти", "abort ok",
    # natural-language stop by the operator ("enough hunting for the test... enough")
    # was not matched -> the loop kept fighting the end of the turn after an explicit human stop. Only
    # last_user (the agent cannot self-release). NL-stop phrases added (targeted, without a broad "enough").
    "хватит охот", "останови хант", "останови охот", "заканчивай тест", "хватит теста",
    "хватит для теста", "для теста хватит", "для понимания достаточно", "достаточно для теста",
    "хватит на этом", "стоп тест", "останови тест",
]

# My abort/no-findings/surrender language - what we gate. Narrow hunt-specific phrases,
# NOT a bare "abort" (too broad, would catch meta conversations).
ABORT = [
    "ничего не нашёл", "ничего не нашел", "не нашёл бага", "не нашел бага",
    "не нашёл уязвим", "не нашел уязвим", "no findings", "nothing found",
    "bad ev", "bad-ev", "плохой ev", "плохой эв", "diminishing returns",
    "предлагаю уйти", "предлагаю abort", "предлагаю пивот", "предлагаю сменить",
    "предлагаю abort", "стоит уйти с", "лучше уйти", "лучше abort",
    "all hypotheses refuted", "все гипотезы опровергнуты", "чистого эксплойта нет",
    "чистого эксплоита нет", "пере-аудирован", "переаудирован",
    "что дальше будем", "что дальше копать", "что дальше делаем",
    "не нашёл, что дальше", "не нашел, что дальше",
    # 2026-06-25: an instance bypassed the list TWICE by rephrasing.
    # Forbidden frame (hardened/well-audited/public-crowd) + park + EV justifications + target change.
    # NB (2026-07-06, gate_replay FP fix): a bare "hardened" (incl. its Russian-inflected forms) was REMOVED - it is a
    # raw adjective-OBSERVATION, an FP on a legit continuation ("the core looks hardened, but I did not dig in ->
    # I dig the periphery"). A real give-up is caught by: the COMPOUNDS below (`config-hardened`/"objectively
    # hardened", exit context) + BREADTH_RE (coverage+exhaustion coupling) + co-lexicon (well-audited/
    # bad-EV/"I suggest leaving"), which is present in real give-up cases. Measured with gate_replay.py.
    "well-audited", "well audited",
    "аудированн", "хорошо проаудир", "плотно покрыт", "ядро сложности",
    "public с 2024", "public с 2025", "(толпа)", "ре-аудит такого", "чистый ре-аудит",
    "низкий ev", "низкий эв", "лучшим ev", "лучшим эв", "лучший ev",
    "низкий ожидаемый", "ожидаемый выхлоп", "низкий выхлоп", "выхлоп на вложенн",
    "на вложенный час", "выхлоп неясен", "инфра-инвестиц", "инфра инвестиц",
    "park харнесс", "park-харнесс", "паркую харнесс", "park таргет", "паркую таргет",
    "переключаемся на таргет", "переключаемся на цель", "переключаемся сейчас",
    "переключаемся на другой", "при следующем релизе", "следующем релизе",
    "окно ре-аудита", "следующем bump", "single-target mastery",
    # 2026-07-02: the 3rd rephrasing bypass (after the first two). The instance claimed
    # FALSE exhaustion ("checked EACH of ~40 in 30 min") + park-as-known-clean +
    # give-up-as-a-question to the operator. The structural catch is DECISION_Q_RE below; here is pointed lexicon.
    "только по твоему", "по твоему слову",
    "поверхности не осталось", "поверхност не осталось", "не осталось поверхн",
    "novel-поверхност", "новой поверхност", "новой novel", "novel-surface не",
    "упёрся", "уперся", "упёрлись", "уперлись",
    "known-clean", "known clean", "паркую как", "park как",
    "подтверждённо-чист", "подтвержденно-чист", "подтверждённо чист", "подтвержденно чист",
    "med+ нет", "нет med+", "med+ отсут", "med+ не найд", "нет ни одного med",
    # 2026-07-29: "No confirmed in-scope Medium+" - "medium+ нет" (the full word) did not
    # match the abbreviated "med+ нет".
    "medium+ нет", "нет medium+", "medium+ отсут", "medium+ не найд", "in-scope medium+ нет",
    "хант исчерпыва", "хант исчерпан", "исчерпывающий хант", "surface исчерпан",
    # 2026-07-06: FALSE exhaustion in ~2h on a multi-chain/100+-market surface
    # ("scraped the whole scope, certainty HIGH, config-hardened, all defects latent"). A breadth-
    # sweep passed off as depth-exhaustion. Pointed lexicon (backstop); the main catch is BREADTH_RE below.
    "вычерпал", "вычерпан", "скоуп закрыт", "весь скоуп", "config-hardened", "конфиг-hardened",
    "объективно hardened", "объективно config", "certainty high", "certainty: high",
    "все латентные", "всё латентн", "все дефекты латентн", "currently-exploitable",
    "currently exploitable", "currently exploitable critical", "весь скоуп закрыт", "скоуп вычерпан",
    # 2026-07-07: exhaustion verdict via "scope collapse" - phrases that bypassed the detectors
    # (the 5th paraphrase bypass). The escape was through a legit pause
    # (the operator asked a question -> the hook let it ANSWER, a falsely-exhausted verdict was packed into the answer).
    "provably balanc", "provably bound", "deployed=audited", "deployed == audited",
    "deployed соответств", "exhaustively verified", "exhaustively-verified", "verified hardened",
    "реально исчерпан", "исчерпан на", "таргет исчерпан", "жечь твою rep", "жечь rep",
    "достижимого in-scope", "достижимого high", "достижимого crit", "achievable in-scope",
    # FIX-E (2026-08-12, operator: "why write the last one? there are many axes"): finite-framing =
    # false-exhaustion (there is no "last axis" - under the axiom axes are generated endlessly). The exact
    # phrases of the run. They hold the gate + surface the de-shadow backlog (run the generators / seed the queue).
    "исчерпан глубиной", "depth-exhaust", "surface depth", "исчерпан на уровне", "on-chain исчерпан",
    "непокрыто только", "непокрыто: только", "последняя непокрытая", "последняя on-chain ось",
    "последний непокрытый", "последняя ось", "последний фронтир", "последнем фронтире",
    "нет открытых нитей", "нечего вскрывать",
    # 2026-07-07 (6th bypass, web/dapphunt): exhaustion verdict "web deep-covered, High/Crit empty".
    "low ev", "low-ev", "deep-covered", "deep covered", "high/crit пуст", "high/critical пуст",
    "скоуп пуст", "скоуп по high", "0 in-scope high", "0 in-scope critical",
    "exhaustive web", "exhaustive pass", "все 4 веб",
]

# Structural abort detection - catches a FORK QUESTION ("dig here or switch?")
# regardless of vocabulary. In the loop I do not ask the operator "continue or leave" - I dig.
# Insurance against rephrasing: new words will not bypass the very structure of the offered choice.
FORK_RE = re.compile(
    r"развилк"
    r"|как скажешь[^.?!]{0,60}(продолж|переключ|копать)"
    r"|(продолж\w*|копать|копаю|гоню|гнать)[^?]{0,140}\bили\b[^?]{0,60}"
    r"(переключ|park|парк|смен\w*\s*цел|уход|друг\w*\s*(цел|таргет))"
    r"|(копать|копаю)\s+здесь[^?]{0,40}\bили\b"
    # reverse order (2026-07-02): "'we're leaving'->I park ... or give a new axis ... I will continue"
    r"|(уход\w*|уйти|уйд[её]м|park|парк|паркую|заверш\w*|стоп|known.?clean)"
    r"[^?]{0,160}\bили\b[^?]{0,90}(продолж|копа\w+|нов\w+\s+ос|задай|дай\s+ось|угол|вектор|сам)"
    # PIVOT-fork (2026-07-06): "two options: pivot to another target, OR finish off the latent one".
    # The structure "change target OR finish here" = handing the wheel back, regardless of words.
    r"|(пивот|пивотн\w*|друг\w*\s*(таргет|цел|программ)|смен\w*\s*(таргет|цел))"
    r"[^?]{0,120}\bили\b[^?]{0,90}(доб\w+|продолж|копа\w+|остат\w+|латент|дожм|дожа)"
    r"|(два\s+вариант|двух\s+вариант|выбор:|варианта:)[^?]{0,140}\bили\b"
    r"|(доб\w+|дожм\w*|дожа\w*)[^?]{0,90}\bили\b[^?]{0,90}(пивот|смен\w*\s*(таргет|цел)|друг\w*\s*(таргет|цел))"
    # 2026-07-07: "either upgrade the target, or another target" - an alternation via "либо...либо"
    # (FORK_RE caught only "или"). Handing back the wheel via a target choice, regardless of the conjunction.
    r"|\bлибо\b[^.?!]{0,110}\bлибо\b[^.?!]{0,110}(таргет|цел|программ|surface|поверхност|upgrade|апгрейд)"
    # 2026-07-07: "push one of the axes further OR consider it closed?" - a continue/close fork.
    r"|(гнать|гоню|продолж\w*|копа\w+|пуш\w+|доб\w+)[^?]{0,110}\bили\b[^?]{0,70}"
    r"(закрыт|заверш|считаем\s+\w*\s*закрыт|закрыт\w*\s+(таргет|веб|скоуп|scope))"
    # 2026-07-29: a fork via a SLASH, not "или" - "keep pushing / we're leaving - up to you". The slash = the same
    # handing back of the wheel (continue-vs-leave), FORK caught only the conjunction "или".
    r"|(дожим\w*|доб\w+|дожа\w*|продолж\w*|копа\w+|гнать|гоню|пуш\w+)\s*/\s*"
    r"(уход\w*|уйти|уйд[её]м|уйд\w*|стоп|заверш\w*|abort|бросить|пивот)"
    r"|(уход\w*|уйти|уйд[её]м|стоп|заверш\w*|abort|пивот)\s*/\s*"
    r"(дожим\w*|доб\w+|дожа\w*|продолж\w*|копа\w+|остат\w+)",
    re.I,
)

# Give-up-as-a-question: during a hunt I end the turn by asking the operator to MAKE A DECISION
# about the hunt direction (rather than confirm a concrete Watson action). In the loop I do NOT ask
# "what to do next / decide for me / give an axis" - I dig (T9 on an axis that I set).
# A paraphrase-resistant STRUCTURAL signal: soliciting a decision from the operator. Catches rephrasings
# that the blocklist misses (earlier bypasses got past the lexicon 3 times with new words).
# NB: concrete Watson requests ("top up $5 on the burner", "sign the mainnet-tx") do NOT fall here -
# that is not "your decision about direction" but a point action.
DECISION_Q_RE = re.compile(
    r"что\s+реша\w*"                                  # "what do you decide"
    r"|что\s+скаж\w*"                                 # "what do you say"
    r"|что\s+(будем\s+|дальше\s+)?дела\w*\s+дальше"   # what (shall we) do next
    r"|куда\s+(дальше|копа\w+|идём|идем|пойд|двиг)"   # where next / where to dig / where do we go
    r"|скажи[,\s]+(куда|что\s+дела|как\s+быть)"       # "tell me where" / tell me what to do (2026-07-06)
    r"|скажи\s+куда"
    r"|скажи\s+(вектор|угол|ось|направлен|инсайт)"    # "tell me the vector - I will take it" (2026-07-07)
    r"|куда\s+[^?\n]{0,20}(дальше|пуш\w+|копа\w+|двиг\w+)"  # "where can I push next" (2026-07-07)
    r"|считаем\s+[^?\n]{0,30}(закрыт|заверш|достаточн)"     # "consider the web closed?" (2026-07-07)
    r"|тво[ёе]\s+(решени|слово|выбор|отмашк)"         # your decision/word/choice/go-ahead
    r"|по\s+твоему\s+слову|только\s+по\s+твоему"      # finish only on your word
    r"|тебе\s+(реша|выбир)\w*"                        # it is for you to decide/choose
    r"|реши\w*\s+сам|как\s+реши\w*|решай\s+сам"       # decide yourself / as you decide
    r"|жду\s+(тво\w+\s+)?(решени|реакци|отмашк|слова|указан)"  # waiting for your decision
    r"|задай\s+(себе\s+|мне\s+|нов\w+\s+)*(ось|угол|вектор|направлен|инсайт|scope)"  # set a new axis yourself
    r"|дай\s+(мне\s+)?(ось|угол|вектор|направлен|инсайт|scope)"
    r"|your\s+call|up\s+to\s+you|you\s+decide|let\s+me\s+know\s+(how|what|which)"
    # 2026-07-29 (7th paraphrase bypass): "the decision on ... is up to you (it is your prerogative)".
    # Handing over the wheel via "up to you"/"prerogative" - DECISION_Q had neither.
    r"|решени\w*[^.?!\n]{0,40}за\s+тобой|за\s+тобой[^.?!\n]{0,30}(реша|решени|прерогатив|выбор)"
    r"|тво[йяё]\s+прерогатив|это\s+тво[йяё]\s+(прерогатив|реш)"
    # 2026-08-18 (8th paraphrase bypass): "the exit here is up to you" (exit, not "decision"); a conditional
    # handing back of the wheel "say we leave - I record / say dig an angle - I take it" = handing the choice to the operator.
    r"|выход[^.?!\n]{0,25}за\s+тобой|за\s+тобой[^.?!\n]{0,20}(уход|выход|фиксир)"
    r"|скажешь\s+[^.?!\n]{0,45}(беру|возьм|фиксир|сделаю|запущу|погна)",
    re.I,
)

# BREADTH!=DEPTH - structural detection of FALSE EXHAUSTION (2026-07-06): an instance ended the
# turn with a claim of FULL COVERAGE of the scope ("the whole scope is closed / all N chains / every feed
# covered / end-to-end / certainty HIGH") as the justification for "no Crit/High". That is a BREADTH sweep (file-level)
# passed off as DEPTH exhaustion. On a multi-chain/100+-market surface over hours this is physically impossible
# = under-digging. Structure: coverage-claim + exhaustion-conclusion. Catches regardless of exact words.
# Anti-FP: requires BOTH - "full coverage" AND "closed/clean/certainty/no-crit" (a plain progress
# report "went through the score-5 gap-map" without an exhaustion conclusion does NOT trigger).
BREADTH_RE = re.compile(
    r"(весь\s+скоуп|весь\s+scope|вес[ья]\s+объ[её]м|весь\s+(permissionless\s+)?value.?flow|"
    r"весь\s+permissionless|in-scope\s+(surface|поверхност)|"
    r"все\s+\d*\s*(чейн|сет|網|рынк|маркет|market|chain|фид|feed|адаптер|контракт)|"
    r"кажд\w+\s+(фид|рынок|контракт|feed|market|адаптер|чейн)|end.?to.?end|покрыто\s+end)"
    r"[^?]{0,160}"
    r"(закрыт|вычерпан|исчерпан|полностью\s+покрыт|on-chain.?верифиц|certainty|hardened|"
    r"provably\s+balanc|deployed=audited|deployed\s*==\s*audited|exhaustively\s+verif|"
    r"нет\s+(currently|current|actively)|(critical|high|крит\w*)\s+(нет|не\s+достиг|отсут)|"
    r"нет\s+(critical|high|крит))",
    re.I,
)

# PARAPHRASE-GIVEUP (8th bypass, 2026-08-09). The instance does NOT write "abort/I give up/
# pivot" (caught by ABORT/FORK/DECISION_Q), but gives an "honest FINAL report" with the forbidden frames
# in new words: "the target is really hardened / the un-dup surface is cleaned out / the pass is exhaustive / further
# EV only in a multi-day fork-PoC / wait for the next release" + handing the wheel back to the operator. BREADTH_RE requires
# "the whole scope", these phrases bypass it. The root is the same as earlier bypasses - the synonym race
# cannot be won point-wise, so we catch a CLUSTER (>=2 different give-up categories) + a NEGATIVE override
# on continuation (an instance that CONTINUES - "the loop continues / next axis / building wave-3" -
# does NOT exit even though it writes "the target is hardened": a legit continuation, not a give-up).
_PG_CONTINUE_RE = re.compile(
    r"петл\w+\s+продолж|следующ\w+\s+(ось|axis|нит|wave|волн)|стро\w+\s+wave|строю\s+модель|"
    r"продолжаю\s+(копа|гна|drive|хант|глуб)|next\s+axis|перех\w+\s+(к|на|в)\s+\w*(ось|wave|нит|волн)|"
    r"гоню\s+(дальше|вглубь|нить)|читаю\s+\w|T9\s+(cold-?)?restart|запускаю\s+scout", re.I)
_PG_CATS = (
    # (a) hardened/clean frame about the TARGET/surface (not a single "I-NN/the core is hardened"). Two
    #     observed cases: "the protocol is exceptionally hardened" / "the target is really clean on deployment" - both FORBIDDEN
    #     frames about the TARGET (not "everything is clean" - that is in (b)); clean/protected added next to target/protocol.
    #     +2026-08-18: English "hardened" (the regex was Russian-centric - the Russian stem for "hardened" caught it, English "hardened" did not)
    #     in BOTH orders ("target hardened" and "hardened $25k-target").
    re.compile(r"(таргет|протокол|проект|target|protocol)\s+\w*\s*(захард|чист|clean|защищ|hardened)|"
               r"hardened\b[^.\n]{0,20}(таргет|target|деплой|протокол|protocol)|"
               r"(un-?dup\s+)?поверхност\w*\s+(вычищен|выеден|исчерпан)|surface\s+\w*\s*(cleaned|exhausted|picked)", re.I),
    # (b) "exhaustive/full pass" - an exhaustion narrative. Observed: "(in-scope) depth is exhausted"
    #     - exhaustion about DEPTH (not about the pass), added.
    re.compile(r"проход\w*\s+исчерпывающ|исчерпывающ\w+\s+(и\s+)?честн|полн\w+\s+(divergence|проход|прогон)|"
               r"вс[её]\s+(чист|защищ|enforced|покрыт)|всю\s+\w*\s*поверхност|"
               r"глубин\w+\s+\w*\s*исчерпан|in-?scope\s+\w*\s*исчерпан", re.I),
    # (c) bad-EV pivot (an exit on EV is forbidden). +2026-08-18: "bad EV", English "low-EV"/"low-payout" (there was only
    #     the Russian "low EV"/"bad EV" - a Russian-English gap let the text "= bad EV"/"low-payout" through).
    re.compile(r"(дальше|остал\w+|весь|низк\w+|плох\w+)\s+EV\b|EV\s+только\s+(в|=)|многодневн\w+\s+fork|"
               r"diminish|низк\w+\s+EV|плох\w+\s+EV|bad\s+EV|low-?ev\b|low-?payout|low\s+payout", re.I),
    # (d) park-as-exit: wait for a release/upgrade, hunt the delta later
    re.compile(r"ждать\s+(следующ\w+\s+)?(релиз|upgrade|деплой|апгрейд|next\s+release)|хантить\s+дельт\w+\s+(потом|когда|позже)|"
               r"вернут\w+\s+(на|когда|к)\s+\w*релиз", re.I),
    # (e) a final report handing back the wheel to the operator: "honest conclusion/result/final/status", "final on <target>"
    re.compile(r"честн\w+\s+(вывод|итог|финал|статус)|финал\s+по\s+\w|итог\s+по\s+(нит|таргет|прогон)", re.I),
    # (f) decision-Q handing back the wheel. Observed: "decide, Bro, we're leaving". +2026-08-18: hand-back offers "Dig X
    #     further?" / "name the angle" / "say we leave" / "if you want to turn around - say so" (a structural
    #     handing back of the choice to the operator, not one phrase). `решай\b` (not "решаю" - that is not an imperative).
    re.compile(r"что\s+(мне\s+)?(делать|дальше)|решай\b|тебе\s+решать|тво[её]\s+(слово|решение)|"
               r"копа\w*[^.?!\n]{0,30}дальше\s*\?|назови\s+(угол|ось|вектор|таргет)|"
               r"скажешь?\s+«?\s*уходим|если\s+хочешь[^.\n]{0,40}(разверн|переключ|уйти|свеж)", re.I),
    # (g) pivot-suggestion / switch-target - a FORBIDDEN anti-surrender frame (project rule: "do not suggest pivot /
    #     abort until a bug is found"). 2026-08-18: "turn to a fresher/quieter target / let's switch".
    re.compile(r"разверн\w+\s+(на|его)?[^.\n]{0,25}(таргет|target|деплой|программ|проект|свеж|тих|другой)|"
               r"переключ\w+\s+(на|ся)[^.\n]{0,25}(таргет|target|свеж|другой|тих|программ)|"
               r"pivot\s+to[^.\n]{0,20}(fresh|another|new|quiet)\s*target|"
               r"уйти\s+на\s+(свеж|другой|тих)|развернуть\s+на\s+(более\s+)?(свеж|тих|другой)", re.I),
)


def _paraphrase_giveup(text):
    """8th paraphrase bypass: an "honest final report" with hardened/exhaustion/bad-EV/park/decision
    frames = a hidden give-up. True if >=2 DIFFERENT give-up categories AND NO continuation signal
    (an instance that continues the loop is not an exit). Anti-FP: a single "the core/I-NN is hardened as
    expected, continuing" -> categories<2 OR continuation-override -> False."""
    al = (text or "").lower()
    if not al:
        return False
    cat_hits = [i for i, rx in enumerate(_PG_CATS) if rx.search(al)]
    returns_wheel = 5 in cat_hits                    # cat (f) - handing back the wheel (decide/what to do/up to you)
    # the continuation-override saves ONLY when the agent does NOT hand back the wheel. Observed: "options:
    # T9 cold-restart / wait for deploys / we leave - decide, Bro" LISTS T9 as an option (does not do it), and
    # `_PG_CONTINUE_RE` caught the mention "T9 restart" -> falsely lifted the give-up. Handing back the wheel + listing =
    # a decision menu, NOT a continuation (the agent sets the axis, not the operator - autonomous-no-menus).
    if _PG_CONTINUE_RE.search(al) and not returns_wheel:
        return False                                 # the instance REALLY continues work -> not a give-up
    return len(cat_hits) >= 2


# DEPTH-LEAD-FIRST (2026-07-06, operator: "in new sessions you take breadth, not depth-lead"). The root
# of the false-exhaustion miss: the instance maps the whole scope / spawns H-NNs, but drives NOT A SINGLE thread
# down >=5 layers (depth-ceiling). BREADTH_RE catches the SYMPTOM at exit ("scope closed"); this catches
# the CAUSE mid-loop - a "wide-but-shallow" ledger state: >=min_hyps real hypotheses AND no
# thread has reached depth-lead >=5 layers. Anti-FP (operator: "do not fire on the first breadth pass"):
# the ordering in main() puts this check AFTER scout-pending - while the first scout runs (PENDING), the
# SCOUT_REASON fires and this guard is silent; it turns on only when the pool is filled (scout DONE/N/A) + hypotheses
# >=min_hyps + depth is zero. This is not a hard block on top of the autoloop, but a SWITCH of the forcing-reason to a depth focus
# (escalating nudge: each turn of "wide instead of deep" -> a depth order again). Source field:
# the `Depth-Lead:` line(s) in Loop State -> the max of layers (numbers on the line, or k/5).
# ONLY the bold FIELD `**Depth-Lead:**`, NOT prose mentions of "depth-lead" in the rules text. A latent
# regression (found 2026-07-12): prose lines of the RULES block with "depth-lead" + a number ("6/10 biggest
# hacks", "5/5 payout", ">=5 layers") inflated claimed -> any ledger with a RULES block read as
# layers>=5 -> wide_but_shallow NEVER fired (neutralised). The `**` requirement cuts out prose.
_DEPTH_LEAD_LINE_RE = re.compile(r"(?im)^[^\n]*\*\*\s*depth[\s\-_]*lead[^\n]*$")


def _depth_layers(line):
    """The number of layers reached from the Depth-Lead line. Template format = `H-03 — 3/5 (chain)` ->
    we take the NUMERATOR (3 reached out of 5). WARNING BUG-FIX 2026-07-07: previously the fallback = max-of-all-numbers,
    and a date "2026"/amount "$2.38M" on the Depth-Lead line returned 2026 -> the gate falsely counted "depth >=5
    reached" and went silent. Now we strip years/amounts and accept ONLY the form `k/N` OR "N layers";
    a bare number NO LONGER inflates depth. No valid form -> 0."""
    line = re.sub(r"\bH-\d+\b", "", line, flags=re.I)              # strip the hypothesis ID (H-03 -> empty)
    line = re.sub(r"\b(?:19|20)\d\d\b", "", line)                  # years/dates (2026-07-07)
    line = re.sub(r"\$?\d[\d.,]*\s*[mkbмкб]\b", "", line, flags=re.I)  # amounts ($2.38M, 24.5M, 500k)
    m = re.search(r"(\d+)\s*/\s*\d+", line)                        # k/5 -> reached k
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d+)\s*(?:сло|layer|уров)", line, re.I)      # "5 layers" (RU/EN)
    if m2:
        return int(m2.group(1))
    return 0                                                       # no k/N form or "N layers" -> 0


# ─────────────────────────────────────────────────────────────────────────────
# T12 - Predictive Boundary Crossing (phase 2 of depth_engine_plan).
# Diagnosis: we had a depth METRIC and no depth METHOD. `call->state->external->hook->accounting` inside
# a single file = "5/5", the gate is satisfied, no understanding of the system - Goodhart on its own counter.
# Cure: a layer counts ONLY if (1) a representation boundary was crossed and (2) the prediction
# was recorded BEFORE the crossing and verified AFTER. A crossing without a prediction = movement, not understanding.
# A caveat against a new Goodhart: a heavy artifact is required for a claim of >=3 layers, not for every step.
_T12_CLAIM_MIN = 3
_TRACE_HDR_RE = re.compile(r"(?im)^[^\n]*\*\*\s*depth[\s\-_]*trace[^\n]*$")
_TRACE_NA_RE = re.compile(r"N/?A\s*[—\-]", re.I)
_LAYER_RE = re.compile(r"(?im)^\s*L\d+\b")


def _trace_block(txt):
    """The text of the DEPTH-TRACE section (from its line to the next top-level Loop State field)."""
    m = _TRACE_HDR_RE.search(txt)
    if not m:
        return None
    rest = txt[m.start():]
    lines = rest.splitlines()
    out = [lines[0]] if lines else []
    for line in lines[1:]:
        # the next Loop State list field (`- **Something:**`) closes the block
        if re.match(r"^\s{0,2}-\s+\*\*", line):
            break
        out.append(line)
    return "\n".join(out)


_PMISS_RE = re.compile(r"(?im)^[^\n]*\*\*\s*prediction[\s\-_]*miss[^\n]*$")
_PMISS_N_RE = re.compile(r"(\d+)")
# "I did not understand the system -> I dig THIS SAME layer" - a legitimate outcome of a miss (the depth counter does not grow).
_PMISS_OK_RE = re.compile(r"не\s+понял|этот\s+же\s+слой|модель\s+был[аи]\s+неверн|model\s+revision",
                          re.I)


def active_depth_t12_incomplete(current_sid):
    """A depth claim of >=3 without an honest T12 trace + an undigested prediction miss.
    Returns a STRING of reasons (or None)."""
    ledger, _root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None

    # (0) A prediction miss is a GENERATOR, not an accounting error: `predicted != observed` must become
    #     either a new `D-NN` (the system behaves unexpectedly), or an explicit note "did not understand -> digging
    #     this same layer" / a model fix. A silently swallowed miss = a thrown-away entry point.
    pm = _PMISS_RE.search(txt)
    if pm and "{" not in pm.group(0):
        # Count digits ONLY in the field value: the label itself contains "T12", and a naive search for
        # digits over the whole line would read it as "12 misses" (caught by the replay test "misses 0").
        tail = pm.group(0).split(":**", 1)[-1] if ":**" in pm.group(0) else pm.group(0)
        n = _PMISS_N_RE.search(tail)
        if n and int(n.group(1)) > 0 and not _PMISS_OK_RE.search(txt):
            mpath = os.path.join(os.path.dirname(ledger), "system_model.md")
            has_div = False
            if os.path.exists(mpath):
                try:
                    with open(mpath, "r", encoding="utf-8") as f:
                        has_div = any(_D_ROW_RE.match(l) for l in f)
                except Exception:
                    has_div = False
            if not has_div:
                return ("prediction misses recorded: %s, but no `D-NN` was created "
                        "and there is no note 'did not understand -> digging this same layer'/model fix - the miss "
                        "was swallowed silently" % n.group(1))

    # WARNING 2026-07-28 (finding #1): it used `.search()` = the FIRST match, and the first in every ledger is the
    # heading of the RULES block "8. **DEPTH-LEAD-FIRST...**" (not a `- ` field) -> _depth_layers=0 -> claim<MIN
    # ALWAYS -> the gate was DEAD. _max_depth (findall+max, now skipping the `{` placeholder) takes the REAL
    # filled Depth-Lead field; the heading and an unfilled `{...}` example give 0.
    claim = _max_depth(txt)
    if claim < _T12_CLAIM_MIN:
        return None                                  # early layers do not require an artifact

    block = _trace_block(txt)
    if block is None:
        return ("claimed %d layers, but there is no `DEPTH-TRACE` section at all - a layer without "
                "`boundary`/`predicted`/`observed` does not count" % claim)
    body = "\n".join(block.splitlines()[1:]) if "\n" in block else ""
    head = block.splitlines()[0] if block.splitlines() else ""
    if "{" in block:
        return "claimed %d layers, but `DEPTH-TRACE` is an unfilled placeholder" % claim
    if _TRACE_NA_RE.search(head) or _TRACE_NA_RE.search(body):
        return ("claimed %d layers (>=%d), but `DEPTH-TRACE` is marked `N/A` - the sentinel is legitimate "
                "ONLY for a claim of <%d" % (claim, _T12_CLAIM_MIN, _T12_CLAIM_MIN))

    low = block.lower()
    reasons = []
    if not _LAYER_RE.search(block):
        reasons.append("no `L{N}` layer at all")
    if "boundary:" not in low:
        reasons.append("no `boundary:` field - the TYPE of the crossed boundary is not stated "
                       "(static->runtime / module->module / spec->implementation / deploy->deploy / "
                       "code->live state)")
    has_pred, has_obs = "predicted:" in low, "observed:" in low
    if has_obs and not has_pred:
        reasons.append("there is `observed:` but NO `predicted:` - a retroactive prediction does not "
                       "count, this is the first thing the gate checks")
    elif not has_pred:
        reasons.append("no `predicted:` - a crossing without a prediction = movement, not understanding")
    elif not has_obs:
        reasons.append("no `observed:` with a reference to an artifact (run log / trace / RPC output)")
    if "fan-in:" not in low:
        reasons.append("no `fan-in:` - who ELSE writes to this state (by grep, not by judgement). "
                       "Depth without fan-in is a pipe, not a slice; a writer from ANOTHER subsystem = "
                       "a ready second piece of evidence for T6")
    if not reasons:
        return None
    return "claimed %d layers, but: %s" % (claim, "; ".join(reasons))


_D_ROW_RE = re.compile(r"(?m)^\s*\|\s*\**\s*D-\d+\s*\**\s*\|")  # a real divergence row `| D-NN |` (\** = bold)
# a resolution that removes a D-NN from the "open breadth": killed / banked / de-minimis / low-deferred
_D_RESOLVED_RE = re.compile(r"KILLED|\bбанк\b|\bbank(?:ed)?\b|de-?minimis|LOW-DEFERRED", re.I)


def _open_divergence_count(ledger_path):
    """The number of OPEN `D-NN` (not KILLED, not banked) in the sibling `system_model.md`. FIX-2 (2026-08-12):
    breadth is expressed by DIVERGENCES, not only H-NN - a HYBRID fan-out lays down N D-NN,
    1 H is promoted -> the H-counter is small, the gate is silent, although depth-trace=0. An open D-NN = a `| D-NN |` row
    WITHOUT a killed/bank marker in the resolution. Banked/killed are NOT counted (they are resolved -> not "hanging breadth"
    that must be driven deep; otherwise it over-fires on an exhausted ledger where a NEW AXIS is needed, not depth)."""
    smd = os.path.join(os.path.dirname(ledger_path), "system_model.md")
    try:
        with open(smd, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return 0
    return sum(1 for ln in lines if _D_ROW_RE.match(ln) and not _D_RESOLVED_RE.search(ln))


def active_ledger_wide_but_shallow(current_sid, min_hyps=4):
    """True if the ledger is "wide-but-shallow": >=min_hyps real leads (### H-N + OPEN D-NN from
    system_model.md, FIX-2), but NO thread has been driven to depth-lead >=5 layers. A breadth-over-depth sign.
    False while the pool is small (<min_hyps) OR some thread is already >=5. None = no active ledger. The anti-FP for the "first
    breadth pass" is the ordering in main() (scout-pending is checked earlier and blocks with its own
    reason). FIX-2: previously only `### H-N` were counted -> breadth in D-NN (9 divergences from a fan-out with 1 H)
    was not caught by the gate (a gap found in a judged live run: "the main failure of the enabler")."""
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if len(_REAL_H_RE.findall(txt)) + _open_divergence_count(ledger) < min_hyps:
        return False  # the pool is still small - too early to require a depth-lead (the thread may not be found yet)
    layers = 0
    for line in _DEPTH_LEAD_LINE_RE.findall(txt):
        if "{" in line:
            continue  # an unfilled placeholder field != real depth (otherwise the example "3/5" inflates)
        layers = max(layers, _depth_layers(line))
    return layers < 5


DEPTH_LEAD_REASON = (
    "DEPTH-LEAD-FIRST (2026-07-06, operator: 'in new sessions you take breadth, not depth-lead'). Ledger "
    "shows >=4 hypotheses, but the `Depth-Lead` field is < 5 layers - NOT A SINGLE thread has been driven DEEP. This is "
    "breadth-over-depth: you are mapping the scope / spawning H-NNs instead of DRIVING the strongest thread "
    "DOWN. Breadth is needed TO FIND a thread, NOT to fill time. RULE: after ONE recon/scout "
    "pass the next committed action = DRIVE the strongest hypothesis (max severity x confidence) down "
    ">=5 layers (call->state->external->hook->accounting), depth-ceiling. A second breadth pass (another scout / "
    "another file classification / another H-NN) is FORBIDDEN until at least one thread has depth-trace >=5. "
    "NOW: pick ONE strongest thread, update the `Depth-Lead:` field in Loop State (H-NN + layer counter) "
    "and drive it down layer by layer - do NOT add new H, do NOT launch another scout. The bug sits in the JOINT of layers "
    "(>=5), not in a single function at depth 2-3 (the auditor's depth ceiling is 4-5 layers, the crit lives below). "
    "⚠ BOUNDARY-BREADTH - the same prohibition (mythos T1 boundary-centric): listing external dependencies / "
    "verify-sites / deprecated paths as a LIST != covering. A boundary lead = a FULL depth-lead - write it into the "
    "`Depth-Lead:` field (e.g. `oracle-verifier — 4/5 (consumer→iface→verifier→pairing)`) and drive the same ONE "
    "boundary down >=5 layers (in a past hunt: down to the pairing INPUTS at layer 6). 'dependency audited / redundant' = "
    "[SCOPED-OUT], needs a falsifier file:line in the verifier, NOT a wave-off. "
    "⚠ SELECT-PRIORITY un-dup (a past hunt: 2 Crits -> both DUPLICATE $0): a cross-subsystem "
    "Crit-capable COMPOSITE (a thread through DISTANT subsystems in DIFFERENT repos/modules) OVERTAKES a "
    "single-subsystem mid-depth lead in the first DRIVE - the un-dup thread FIRST. Duplicates live at mid-depth "
    "(where the crowd reaches); an un-dup crit sits in the JOINT of distant subsystems below the depth-ceiling, it is yours for the "
    "full amount. Banking a mid-depth submit != progress toward the goal (that is a duplicate layer). Do not abandon a written-out "
    "composite as 'unproven/amplification/NEXT' - drive it to a D-PoC or KILL with a falsifier."
)


# === MONEYLEAD-GATE BEGIN (AOE S4 money-lead-first depth-gate + S3 value section) ===============
# Value-aware specialisation of active_ledger_wide_but_shallow (same class: breadth/shallowness -> hold
# + an order to drive down). As soon as the value concentration is MAPPED (the `## Value Concentration` section in
# system_model.md carries real reachable-$ nodes), the strongest thread by reachable-$ MUST go down
# >=5 layers (first DRIVE = max-reachable-$; a second node is forbidden until depth-5). Stands BEFORE generic
# wide_but_shallow -> with mapped value a $-targeted depth order is more precise.
#
# RED RESOLUTION (Mandate 0.9, do not break): reachable-$ = a tie-break INSIDE divergence-first, NOT a replacement of
# the D-NN/attention-gap by $-ranking and NOT a parallel "$-first" SELECT compass. The gate forces DEPTH
# (shallow-stopping), not a $-first choice of PLACE - the PLACE is still indicated by the model + attention map.
#
# NOT corpus-gated (unlike AOE profile-cleared S2.1): depth gates ship at once, like
# wide_but_shallow - this is about shallow-stopping, not false-refute. fail-open: any breakage -> None.
VALUE_SECTION_TITLE = "Value Concentration"          # section heading in system_model.md (a stable prefix)
_VALUE_NA_RE = re.compile(r"^\s*N/?A\b", re.I)       # `N/A — <reason>` sentinel (small/non-DeFi) in the 1st cell


def _value_concentration_mapped(model_text):
    """True if the `## Value Concentration` section carries >=1 REAL concentration node: a table
    data row without a `{` placeholder, 1st cell non-empty and not an `N/A` sentinel. No section / only
    placeholders / N/A (small/non-DeFi target) -> False (value not mapped -> money-lead is not applicable).
    `_section_rows` already cuts the header+separator and returns only data rows."""
    if not model_text:
        return False
    for r in _section_rows(model_text, VALUE_SECTION_TITLE):
        if "{" in r:
            continue                       # an unfilled placeholder `{node 1}` - not a real node
        cells = _cells(r)
        if not cells:
            continue
        node = cells[0].strip()
        if not node or _VALUE_NA_RE.match(node):
            continue                       # an empty cell / `N/A — <reason>` = not a concentration node
        return True                        # >=1 real node -> value is MAPPED
    return False


def active_moneylead_shallow(current_sid, min_hyps=4):
    """AOE S4 money-lead-first depth-gate. True if the value concentration is MAPPED (the
    `## Value Concentration` section in system_model.md carries real nodes) AND the hypothesis pool is filled (>=min_hyps
    `### H-N`), but NO thread has been driven to depth-lead >=5 layers -> the strongest thread by reachable-$ must be
    driven DOWN. False if: no value section/empty/`N/A` (small/non-DeFi) OR a thread is already >=5 OR the pool is small.
    None = no active ledger. NOT corpus-gated (the depth gate ships at once). fail-open: breakage -> None.
    A High/Crit success-exit does NOT get here - main() short-circuits on ledger_success_exit BEFORE this
    detector (High/Crit is never blocked)."""
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
        mt = None
        mpath = os.path.join(os.path.dirname(ledger), "system_model.md")
        if os.path.exists(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                mt = f.read()
    except Exception:
        return None                        # fail-open (like all detectors)
    if _model_na(txt):
        return False                       # MODEL: N/A off-switch (cold-review 2026-08-06) -> silent, like the whole model family
    if not _value_concentration_mapped(mt):
        return False                       # value not mapped -> silent (small/non-DeFi/pre-model)
    if len(_REAL_H_RE.findall(txt)) < min_hyps:
        return False                       # the pool is small - too early to require depth (the strongest thread may not be found)
    return _max_depth(txt) < 5             # value mapped + pool full, but thread < 5 -> depth order


MONEYLEAD_REASON = (
    "MONEY-LEAD DEPTH-GATE (AOE S4 - money-lead-first depth). The value concentration is MAPPED (the "
    "`## Value Concentration` section in system_model.md carries real reachable-$ nodes), the hypothesis pool is filled, but "
    "NO thread has been driven to depth-lead >=5 layers. Once the value is localised, the strongest thread by "
    "**reachable-$** (NOT headline-TVL: exit-liquidity / caps / permissionless path) MUST go DOWN "
    ">=5 layers (call->state->external->hook->accounting) BEFORE you open a second node. "
    "🔴 RESOLUTION (do not mix up, Mandate 0.9): reachable-$ here is a **tie-break INSIDE divergence-first**, NOT the "
    "primary SELECT driver and NOT a replacement of `D-NN`/attention-gap by $-ranking. The PLACE is still indicated by "
    "the model (`D-NN`) and the attention map (T14); the $-weight only orders among EQUAL divergence signals - which "
    "of the divergence threads to drive FIRST. Do NOT create a parallel '$-first' compass. NOW: from "
    "`## Value Concentration` take the node with max reachable-$ to which an open "
    "divergence/hypothesis is already attached (`I-NN`/`H-NN` in the 'Thread' column); update the `Depth-Lead:` field in Loop State (H-NN + "
    "layer counter) and drive this ONE thread down layer by layer to 5/5. Do NOT add new H, do NOT launch another "
    "scout. The bug sits in the JOINT of layers (>=5) on the path to the money - below the auditor's depth ceiling (4-5), not in a "
    "single function at depth 2-3."
)


# ═══ DEFI-VALUE-UNMAPPED companion (operator, 2026-08-06) ═════════════════════════════════════════
# money-lead durability HOLE: active_moneylead_shallow comes alive ONLY when `## Value Concentration`
# is MAPPED. On a DeFi/money target where the value section was FORGOTTEN to be filled, moneylead silently sleeps ->
# the $-targeted discipline is lost in a new session ("it fired on the words money/DeFi and did not lose it").
# The companion forces writing out the value nodes when: a money signal exists + the model is built + the pool is filled +
# value is NOT mapped + NOT a deliberate N/A. Then moneylead comes alive afterwards. Stands BEFORE moneylead.
# The lexicon is NARROW and money-specific. cold-review 2026-08-06 removed words with web2/infra collisions:
# bare `borrow`/`borrowing` (Rust borrow-checker), `yield` (generator kw), `swap` (OS swap-space),
# `reserves`/`ltv`/`stake` (generic/analytics). Added the bridge/cross-chain class (a first-class
# money target, cold-review FN). The remaining soft collisions (oracle/mint/burn/vault) are damped by the COMBINATION:
# the detector forces ONLY with a built T10 model + a pool of >=4 H + NOT `MODEL: N/A` (the main anti-FP -
# a web2/non-DeFi target sets MODEL: N/A -> the detector is silent regardless of lexicon).
_DEFI_SIGNAL_RE = re.compile(
    r"\b(?:collateral|over-?collateral\w*|under-?collateral\w*|liquidat\w*|lending|borrower|"
    r"vault|amm|dex|perp\w*|tranche|yield[-\s]?farm\w*|staking|tvl|oracle|bad[-\s]?debt|"
    r"share[-\s]?price|redeem|flash[-\s]?loan|bridge\w*|relayer\w*|cross-chain|wrapped[-\s]?token|"
    r"merkle|mint\w*|burn\w*)\b",
    re.I,
)


def _defi_signal(text):
    """A narrow finance-specific DeFi signal (collateral/lending/vault/AMM/liquidation/oracle...).
    Deliberately does NOT include generic token/mint/deposit/pool (too noisy for web2). Grepped ONLY over the
    LEDGER (my work: hypotheses/scope), NOT over the text of the system_model template - the template is stuffed
    instructive words (oracle/TVL/collateral in `>` hints) and would fire on ANY target.
    Fires only in combination (value NOT mapped + model built + pool >=N) -> a false maximum =
    a request to write out the value section, lifted by a deliberate N/A sentinel."""
    return bool(_DEFI_SIGNAL_RE.search(text or ""))


def _value_na_declared(model_text):
    """True if the `## Value Concentration` section EXISTS and carries a deliberate `N/A` sentinel -
    in a table row OR in prose/bullet (cold-review 2026-08-06: agents drift from tables to bullets, as
    happened with `## Invariants` -> `_i_rows` had to tolerate both; the same class here). Distinguishes "deliberately
    not applicable" from "forgot to fill" (placeholder/empty) - the companion forces only the latter. `>` lines
    (template instructions) and `{` placeholders are ignored."""
    txt = model_text or ""
    i = txt.find("## " + VALUE_SECTION_TITLE)
    if i < 0:
        return False
    j = txt.find("\n## ", i + 1)
    block = txt[i + 1:j if j > 0 else len(txt)]     # +1: skip the section heading line
    for line in block.splitlines():
        s = line.strip()
        if not s or s.startswith(">") or s.startswith("#") or "{" in s:
            continue                       # instruction/heading/placeholder - not a deliberate N/A
        cell0 = _cells(s)[0].strip() if s.startswith("|") else s.lstrip("-*> ").strip()
        if _VALUE_NA_RE.match(cell0):
            return True                    # N/A in a table row OR prose/bullet
    return False


def active_defi_value_unmapped(current_sid, min_hyps=4):
    """AOE S4 money-lead durability-companion (2026-08-06). True if the target carries a money/DeFi
    signal, the model is ALREADY built (>=1 grounded I-NN) and the hypothesis pool is filled (>=min_hyps), BUT the
    `## Value Concentration` section is NOT mapped and NOT marked with a deliberate `N/A` -> force writing out value nodes
    (otherwise active_moneylead_shallow silently sleeps on a DeFi target). False if: value is mapped/N/A / no
    money signal / model not built / pool small. None = no active ledger. NOT corpus-gated
    (a depth-companion, ships at once). fail-open: any breakage -> None. High/Crit does not get here
    (main() short-circuits on ledger_success_exit earlier)."""
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
        mt = ""
        mpath = os.path.join(os.path.dirname(ledger), "system_model.md")
        if os.path.exists(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                mt = f.read()
    except Exception:
        return None                        # fail-open (like all detectors)
    if _model_na(txt):
        return False                       # MODEL: N/A off-switch (cold-review 2026-08-06) -> silent, like the whole model family
    if _value_concentration_mapped(mt):
        return False                       # value already mapped -> this is the moneylead gate's zone, not ours
    if _value_na_declared(mt):
        return False                       # deliberate N/A (non-DeFi/no single value) -> do not force
    if _grounded_i_count(mt) < 1:
        return False                       # model not built yet -> model-first rules, we do not jump ahead
    if not _defi_signal(txt):              # the signal is taken from the LEDGER, not from the instructive mt template
        return False                       # no money signal -> generic/web2, money-lead not applicable
    if len(_REAL_H_RE.findall(txt)) < min_hyps:
        return False                       # the pool is small - early phase, the strongest thread may not be found
    return True


DEFI_VALUE_UNMAPPED_REASON = (
    "DEFI-VALUE-UNMAPPED (AOE S4 money-lead durability, 2026-08-06). The target carries a money/DeFi "
    "signal (collateral / lending / vault / AMM / liquidation / oracle...), the model is built and the hypothesis pool is "
    "filled, but the `## Value Concentration` section in system_model.md is NOT mapped (placeholder/empty). While "
    "it is empty, the money-lead depth-gate silently sleeps and the $-targeted discipline is lost. NOW: write "
    "into `## Value Concentration` the real reachable-$ concentration nodes (where the extractable "
    "value lies/flows - pools / vault-share / collateral / fee-accrual, column reachable!=TVL) and tie each to an "
    "open divergence/hypothesis (`D-NN`/`H-NN`). If the target is REALLY not about a single value concentration - "
    "write `N/A — <reason>` as the first line (lifts the gate). This is NOT a $-first SELECT (Mandate 0.9): value = "
    "a tie-break INSIDE divergence-first, only so that moneylead later drives the strongest $-thread down >=5."
)
# ═══ DEFI-VALUE-UNMAPPED companion END ════════════════════════════════════════════════════════
# ═══ MONEYLEAD-GATE END ═══════════════════════════════════════════════════════════════════════


# The ledger of the CURRENT hunt = the FRESHEST .hunt_active (<24h). Critical: the loopstate/scout
# checks must look ONLY at the active session, otherwise cross-fire onto other people's stale sessions
# (2026-06-26: the gate fired LOOP_STATE on a 24h-old target while the user was in a different session).
def freshest_active_ledger(current_sid):
    try:
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        fresh = _owned_markers(current_sid)  # already session-scoped
        if not fresh:
            return None, None
        _, marker = max(fresh)  # the most recently touched = the current hunt
        # WARNING BUG-FIX (2026-07-07): previously `hypotheses.md` was hardcoded. An instance created a SECOND ledger
        # `hypotheses_web.md` (dapphunt) -> all ledger-state gates read the OLD SC ledger, while the web work
        # went outside the gate. Any non-canonical ledger (hypotheses_web/hypotheses_sc/...) was un-gated.
        # Fix: the freshest `hypotheses*.md` in the hunt folder = the current working surface.
        cands = glob.glob(os.path.join(os.path.dirname(marker), "hypotheses*.md"))
        if not cands:
            return None, None
        ledger = max(cands, key=os.path.getmtime)
        return ledger, root
    except Exception:
        return None, None


# Loop State - the resumable core of the ledger. If the active ledger lost it (an instance
# rewrote it in its own format, 2026-06-25), the loop cannot be continued from the exact branch.
# ─────────────────────────────────────────────────────────────────────────────
# MODEL gates (divergence-first, T10/T13 - depth_engine_plan phase 1).
#
# Why 4 functions, not 12 (consolidation S11.4): twelve separate block points = twelve
# chances of a deadlock and twelve replay tests. The checks are grouped by NATURE: artifact completeness
# (one function, a LIST of reasons in one message) - order (pred could not appear after status) -
# abandoned work (D-NN) - knowledge bank at exit (library).
#
# The sentinel `MODEL: N/A — <reason>` in Loop State lifts ALL four at once (K2 of the plan): the entry hook
# arms the marker on any hunt-URL, including a dapphunt front/web2/small contract, where T10 forbids itself -
# otherwise a deadlock out of nowhere. The pattern is the same as for scout/impacts/BOUNDARY-MAP.
# Anti-FP: the sentinel counts ONLY on a line without backticks and without `{` - otherwise the INSTRUCTION
# about it in the ledger template would catch it (there it is written in backticks inside a `{...}` placeholder).
_MODEL_NA_RE = re.compile(r"MODEL[:*\s]*N/?A", re.I)  # OBS-5: tolerates markdown `- **MODEL:** N/A`
# 2026-08-04: an instance names the wave invariants namespaced - `TB-I1` (token-bridge), `W3-I1`
# (wave-3) - instead of continuing `I-13...`. We recognise both `I-\d+` and `<PREFIX>-I<n>` (<=4-char prefix), otherwise
# `_wave_i_counts` sees ZERO invariants under `## WAVE-*` -> axes_without_waves/new_axis false-fire on a
# CORRECTLY built multi-wave (P10 principle "do not fight the form - recognise it"). `D-\d+` is not caught
# (an `I` is required after the prefix, backtracking rules out `D-01`).
_INV_ID = r"(?:[A-Za-z][A-Za-z0-9]{0,3}-)?I-?\d+"
_I_ROW_RE = re.compile(r"^\s*\|\s*\**\s*" + _INV_ID + r"\s*\**\s*\|", re.I)  # \** = bold `**I-01**` (justlenddao 2026-08-18)
_D_ROW_RE = re.compile(r"^\s*\|\s*\**\s*D-\d+\s*\**\s*\|")  # \** = bold `**D-01**`
_CANON_TODO_RE = re.compile(r"CANON-TODO", re.I)
_LIB_TODO_RE = re.compile(r"LIBRARY-TODO", re.I)
_DIV_RESOLVED_RE = re.compile(r"(→|->)\s*H-\d+|KILLED\s+\S+:\d+", re.I)
_VALID_STATUS = ("ENFORCED-PARTIAL", "SUBSTITUTED", "ENFORCED", "IMPLICIT", "ABSENT")


# OBS-28-fix (2026-08-04): we read the model status sentinel ONLY from the STATUS line (MODEL at the
# start of the line), NOT from the trace history ("- 1 - recon ...; MODEL:BUILDING -> expecting..."). The append-only trace
# is not erased -> a historical line would forever falsely lift the model gates (the same class as the nudge).
_MODEL_STATUS_LINE_RE = re.compile(r"^\s*[-*>]*\s*\*{0,2}\s*MODEL\b", re.I)


def _model_na(ledger_text):
    for line in ledger_text.splitlines():
        if "`" in line or "{" in line:
            continue
        if _MODEL_STATUS_LINE_RE.match(line) and _MODEL_NA_RE.search(line):
            return True
    return False


# OBS-2 (2026-07-28): divergence-first order = the `I-NN` model FIRST, the scout cuts
# partitions BY INVARIANTS AFTER it. While `MODEL: BUILDING` (the model is being built) - the scout is rightfully deferred,
# and scout_pending must NOT force (otherwise it pulls back to the old breadth-before-model order). Anti-FP as
# `_model_na`: lines with backtick/`{` (an instruction about the sentinel in the template) do not count.
_MODEL_BUILDING_RE = re.compile(r"MODEL[:*\s]*BUILDING", re.I)  # tolerates markdown `- **MODEL:** BUILDING`


def _model_building(ledger_text):
    for line in ledger_text.splitlines():
        if "`" in line or "{" in line:
            continue
        if _MODEL_STATUS_LINE_RE.match(line) and _MODEL_BUILDING_RE.search(line):
            return True
    return False


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _model_ctx(current_sid):
    """(ledger_text, model_text|None, model_rel_path) or None if the gates are not applicable."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _model_na(lt):
        return None
    mpath = os.path.join(os.path.dirname(ledger), "system_model.md")
    mt = None
    if os.path.exists(mpath):
        try:
            with open(mpath, "r", encoding="utf-8") as f:
                mt = f.read()
        except Exception:
            mt = None
    try:
        rel = os.path.relpath(mpath, root)
    except Exception:
        rel = mpath
    return lt, mt, rel


# P10 (2026-07-29): an agent wrote real `I-NN` as a bullet list `- **I-01** [economic] ...
# check: ...`, NOT as a 12-column table -> `_I_ROW_RE` (pipe-only) returned 0 rows on a BUILT
# model -> ALL model gates went blind (would shout "zero I-NN" on 12 invariants; wave_transition/T9 did not
# force). "Prose beats the scaffold by convenience": 12 pipe columns are unreadable -> the agent naturally goes to
# bullets. Do not fight the format (a losing race, like the give-up regexes) - RECOGNISE both. From a bullet
# we extract into the same 12-cell form: id - formula - check - class - ... - pred - status - ... (what was not found
# - empty; an empty status/pred is then honestly caught by model_incomplete as "set enforcement/pred").
_I_BULLET_RE = re.compile(r"^\s*[-*]\s*\*\*\s*" + _INV_ID + r"\s*\*\*", re.I)
_B_CLASS_RE = re.compile(r"\[\s*(economic|state)\s*\]", re.I)
_B_CHECK_RE = re.compile(r"check:\s*(.+?)(?:\s+pred:|\s+status:|\s+enforcement:|$)", re.I | re.S)
_B_PRED_RE = re.compile(r"pred:\s*([A-Za-z][A-Za-z-]*)", re.I)
# status only AFTER an explicit marker (status:/enforcement:/->), otherwise an enforcement word from the formula = FP
_B_STATUS_MARKED_RE = re.compile(
    r"(?:(?:status|enforcement)\s*[:=]\s*|→\s*)"
    r"(ENFORCED-PARTIAL|SUBSTITUTED|ENFORCED|IMPLICIT|ABSENT)\b", re.I)
_B_ID_RE = re.compile(r"I-\d+", re.I)


def _bullet_to_cells(line):
    """Bullet `- **I-NN** [class] ... check: ... pred: ... status: ...` -> the 12-cell form (empty where absent)."""
    c = [""] * 12
    mid = _B_ID_RE.search(line)
    c[0] = mid.group(0).upper() if mid else ""
    c[1] = line.strip()[:80]                    # formula stub (non-empty -> not "formula missing")
    mc = _B_CHECK_RE.search(line)
    if mc:
        c[2] = mc.group(1).strip()
    mcl = _B_CLASS_RE.search(line)
    if mcl:
        c[3] = mcl.group(1).lower()
    mp = _B_PRED_RE.search(line)
    if mp:
        c[6] = mp.group(1).upper()
    ms = _B_STATUS_MARKED_RE.search(line)       # status only after an explicit marker (anti-FP from the formula)
    if ms:
        c[7] = ms.group(1).upper()
    return c


def _i_rows(model_text):
    """I-NN rows in BOTH formats: a 12-column pipe table AND a bullet `- **I-NN** ...` (P10)."""
    rows = []
    for l in (model_text or "").splitlines():
        if _I_ROW_RE.match(l):
            rows.append(_cells(l))
        elif _I_BULLET_RE.match(l):
            rows.append(_bullet_to_cells(l))
    return rows


_SECTION_HDR_RE = re.compile(r"^#{2,3}\s+(.*)")


def _wave_i_counts(model_text):
    """I-NN grouped by wave sections (## / ###). The limit <=12 applies PER WAVE (OBS-8/9,
    a 6-axis scaffold), NOT globally: `## Invariants` (wave 1) + `## WAVE-2/3...` +
    a seed scaffold by axes - a legitimate multi-wave, not a shotgun list. `## Long Tail` (a store
    of over-limit ones) is excluded. Returns {section_title: count} only for sections with >=1 `I-NN`."""
    counts = {}
    cur = "(preamble)"
    for l in (model_text or "").splitlines():
        h = _SECTION_HDR_RE.match(l)
        if h:
            cur = h.group(1).strip()
            continue
        if "long tail" in cur.lower():
            continue                                 # a store of over-limit ones - not a wave
        if _I_ROW_RE.match(l) or _I_BULLET_RE.match(l):
            counts[cur] = counts.get(cur, 0) + 1
    return counts


def _norm_status(v):
    """Normalises an enforcement value: strips markdown wrapping (`**ENFORCED-PARTIAL**`, backtick)
    and case. 2026-08-04: bold values `**ENFORCED-PARTIAL**` did not match `_VALID_STATUS`
    -> maturity undercounted (7 of 12) -> the maturity gates went blind. The same class as the namespaced ID."""
    return (v or "").replace("*", "").replace("`", "").strip().upper()


def _status_of(cells):
    s = _norm_status(cells[7] if len(cells) > 7 else "")
    if s in _VALID_STATUS:
        return s
    # 2026-08-09: a compact <8-column I-NN table (`| I-01 | axis | formula |
    # component | ENFORCED | class |` = 6 cells) holds the status NOT in idx7 -> maturity undercounted 0 of
    # 12 -> the WHOLE maturity-gated cluster (fork-diff/undup/t11/axes/attention) was silently blind. The same class
    # as namespaced-ID/bold/bullets - "compactness beats the scaffold". Fallback: a cell ENTIRELY
    # equal to a valid status token (formula = a long sentence, `_norm_status` does not extract
    # a substring -> will not match; whole-cell membership = no FP). WARNING ONLY for len(cells)<8: in
    # the canonical 12-col format `pred:`@idx6 LEGITIMATELY holds a status token, and the scan would confuse pred with
    # status -> break active_model_incomplete (an empty status + a filled pred = "predicted, did not
    # verify" MUST fire). A compact table (<8 cells) carries no pred/status pair -> the scan is safe.
    if len(cells) < 8:
        for c in reversed(cells):
            n = _norm_status(c)
            if n in _VALID_STATUS:
                return n
    return s


def _pred_of(cells):
    """The `pred:` column (expected status, set BEFORE the code) - the 7th cell (index 6)."""
    return _norm_status(cells[6] if len(cells) > 6 else "")


def _i_matured_count(model_text):
    """The number of MATURE I-NN: a row carries a VALID `pred:` OR Status. A model where enforcement lives in
    `pred:` (bullet format, the real Status is described in prose - "VERIFIED", "SUBSTITUTED (D-04)") - is already
    mature for the maturity gates. An empty Status field is caught SEPARATELY by active_model_incomplete ("set
    Status as a field"), WITHOUT blinding the whole maturity cluster. (2026-07-31: pred-only bullets ->
    _status_of=empty -> statused=0<3 -> t11/axes/attention/model_axes silently turned off - "prose
    beats the scaffold", a layer deeper than P10: there bullet PARSING was fixed, but _status_of still
    looked into the empty status column.)"""
    n = 0
    for r in _i_rows(model_text):
        if _status_of(r) in _VALID_STATUS or _pred_of(r) in _VALID_STATUS:
            n += 1
    return n


_D_BULLET_RE = re.compile(r"^\s*[-*]\s*\*\*\s*D-\d+", re.I)  # `- **D-01 ...` (bullet form of D-NN)


def _has_open_divergence(model_text):
    """An open live `D-NN` in the model - as a table (`| D-NN |`) OR a bullet (`- **D-NN**`), NOT
    marked with a resolution (`-> H-NN` / `KILLED file:line`). The bullet form was previously seen only by the pipe
    detector `_D_ROW_RE` -> an open D-NN written in prose was skipped (the whole model in bullets
    - D-NN too) -> the escape "drive the open D-NN" falsely stayed silent, the gate could force on top of a live thread."""
    for line in (model_text or "").splitlines():
        if _D_ROW_RE.match(line):
            c = _cells(line)
            if not _DIV_RESOLVED_RE.search(c[-1] if c else ""):
                return True
        elif _D_BULLET_RE.match(line):
            if not _DIV_RESOLVED_RE.search(line):
                return True
    return False


def _section_rows(model_text, title):
    """Data rows of a markdown table inside the section `## {title}` (without the header and separator)."""
    txt = model_text or ""
    i = txt.find("## " + title)
    if i < 0:
        return []
    j = txt.find("\n## ", i + 1)
    block = txt[i:j if j > 0 else len(txt)]
    rows = [l for l in block.splitlines() if l.strip().startswith("|")]
    data = [r for r in rows if not set(r.replace("|", "").strip()) <= set("-: ")]
    return data[1:] if len(data) > 1 else []


def _section_content_lines(model_text, title):
    """Non-empty NON-table content lines of the section `## {title}` (bullets/prose), except the heading and
    `{...}` placeholders. Table (`|...`) lines are NOT counted - they (with a correct header cut) are given by
    `_section_rows`. Together they cover BOTH forms: a section filled with bullets (Attention Gaps),
    looked "empty" to `_section_rows` alone."""
    txt = model_text or ""
    i = txt.find("## " + title)
    if i < 0:
        return []
    j = txt.find("\n## ", i + 1)
    block = txt[i:(j if j > 0 else len(txt))].splitlines()[1:]  # without the heading line
    out = []
    for l in block:
        s = l.strip()
        # FIX-D (2026-08-12): a `>` blockquote = a template INSTRUCTION ("Filled from
        # deep/crowd_heat.json..."), NOT filled content. Previously it was not skipped -> an untouched Attention
        # Gaps template (only `>` prose) read as "filled" -> the T14 gate was silent for the WHOLE run (template-satisfies-gate).
        if (not s or s.startswith("#") or s.startswith("|") or s.startswith(">") or "{" in s):
            continue                                   # empty/subheading/table/blockquote instruction/placeholder
        out.append(s)
    return out


def active_model_incomplete(current_sid):
    """Model completeness. Returns a STRING of reasons (or None) - one block, not twelve."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    _lt, mt, rel = ctx
    if mt is None:
        return "%s was not created - the model (T10) is not built" % rel
    rows = _i_rows(mt)
    if not rows:
        return "%s is empty: zero `I-NN` (the corpus is not assembled - this is NOT 'nothing to model')" % rel

    # OBS-18 (2026-07-28): in the `MODEL: BUILDING` phase the code is NOT read (T10 order: I-NN+pred
    # BEFORE the code) -> the enforcement status is RIGHTFULLY empty. The old gate measured "shotgun"/"no status" by
    # the empty STATUS -> 3 false messages on a legit pause mid-BUILDING (the agent waits for corpus/scope).
    # Fix: on BUILDING we measure "shotgun" by `pred:` (the grounding of the model: the BASE is expected-ENFORCED,
    # suspect <=half) - a real from-the-head shotgun is caught, while a disciplined model passes.
    # status/canon/negatives - operators of the enforcement phase (require code) -> not checked on BUILDING.
    building = _model_building(_lt)
    reasons = []
    statuses = [_status_of(r) for r in rows]

    # --- Phase-independent: list size and presence of `check:` (valid both before and after the code) ---
    # The limit <=12 is PER WAVE (OBS-8/9), NOT global: a multi-wave by axes (scaffold) is legitimate.
    # Count per section, block only if ONE wave is bloated (a real shotgun), not the sum of waves.
    wave_over = {k: v for k, v in _wave_i_counts(mt).items() if v > 12}
    if wave_over:
        worst = max(wave_over.values())
        reasons.append("%d `I-NN` in one wave with a limit of 12/wave - a shotgun list does not discriminate "
                       "(the excess -> `## Long Tail`; a NEW axis -> a separate section `## WAVE-N`, not into the current one)"
                       % worst)
    if any(len(r) > 2 and not r[2] for r in rows):
        reasons.append("there is an `I-NN` without a `check:` field - a formula without an executable check = an opinion")
    # OBS-19 (2026-07-29): the model MUST be grounded on the CURRENT corpus, not "from the head".
    # The `## Corpus` section exists (template), but all source rows are empty (no "what it gives"/link) -> the I-NN
    # are built from memory about the protocol, not from the project's docs/tests (a risk of stale knowledge). We check
    # only if the section is present at all (synthetic models without it are not our business).
    if "## Corpus" in (mt or ""):
        crows = _section_rows(mt, "Corpus")
        if crows and not any(len(_cells(r)) > 1 and any(c.strip() for c in _cells(r)[1:]) for r in crows):
            reasons.append("`## Corpus` is empty (0 named sources) with %d `I-NN` - the model is FROM THE HEAD, "
                           "not grounded on the CURRENT corpus; name docs/README/tests/audits/reference "
                           "(or a surrogate: the project's tests / economic sense) - otherwise you search by stale "
                           "knowledge about the protocol" % len(rows))

    if building:
        preds = [_pred_of(r) for r in rows]
        if any(not p for p in preds):
            n = sum(1 for p in preds if not p)
            reasons.append("%d `I-NN` without `pred:` - a status prediction is mandatory BEFORE the code "
                           "(otherwise the pred<->fact divergence is unmeasurable)" % n)
        non_enf_pred = sum(1 for p in preds if p and p != "ENFORCED")
        if non_enf_pred > 0.5 * len(rows):
            reasons.append("%d of %d with `pred:` non-ENFORCED (>50%%) - a 'everything is broken' shotgun model, "
                           "not grounded on the corpus (a BASE of expected-`ENFORCED` is needed, suspect <=half)"
                           % (non_enf_pred, len(rows)))
    else:
        if any(s not in _VALID_STATUS for s in statuses):
            n = sum(1 for s in statuses if s not in _VALID_STATUS)
            reasons.append("%d `I-NN` without an enforcement status - 'not marked' != 'verified'" % n)
        non_enf = sum(1 for s in statuses if s != "ENFORCED")
        if non_enf > 0.5 * len(rows):
            reasons.append("%d of %d are marked risky (>50%%) - this is a shotgun, not a model"
                           % (non_enf, len(rows)))
        for r in rows:
            cls = (r[3].lower() if len(r) > 3 else "")
            if "econom" in cls and _status_of(r) == "ABSENT" and not (len(r) > 2 and r[2]):
                reasons.append("an economic `ABSENT` without a named permissionless sequence "
                               "-> this is `Long Tail`, not a divergence")
                break
        if any(s == "ENFORCED" for s in statuses) and not _section_rows(mt, "Missing Negatives"):
            reasons.append("there is `ENFORCED`, but `## Missing Negatives` is empty - the operator 'on all "
                           "paths?' was not run (test negatives are mechanically enumerable)")
        if _CANON_TODO_RE.search(mt or ""):
            reasons.append("`CANON-TODO` is hanging - the operator 'is the mechanism canonical?' was not run "
                           "(a canon substitution = `SUBSTITUTED`, priority above `ABSENT`)")
    if not reasons:
        return None
    return "%s: " % rel + "; ".join(reasons)


def active_model_order_violation(current_sid):
    """Idea F: `pred:` must exist BEFORE the status. A status is present, pred is empty = retroactive."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    _lt, mt, rel = ctx
    if mt is None:
        return None                      # this is caught by active_model_incomplete
    bad = [r[0] for r in _i_rows(mt)
           if _status_of(r) in _VALID_STATUS and len(r) > 6 and not r[6]]
    if bad:
        return "%s: %s - status set, but `pred:` is empty" % (rel, ", ".join(bad[:5]))
    return None


def active_divergence_unresolved(current_sid):
    """Abandoned `D-NN` (including unpassed `hot`). Resolution = `-> H-NN` or `KILLED file:line`."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    _lt, mt, rel = ctx
    if mt is None:
        return None
    open_rows = []
    for line in (mt or "").splitlines():
        if not _D_ROW_RE.match(line):
            continue
        c = _cells(line)
        res = c[-1] if c else ""
        if not _DIV_RESOLVED_RE.search(res):
            heat = ""
            for cell in c:
                if cell.lower() in ("hot", "cold"):
                    heat = cell.lower()
            open_rows.append("%s%s" % (c[0], " [hot]" if heat == "hot" else ""))
    if open_rows:
        return "%s: open divergences without a resolution - %s" % (rel, ", ".join(open_rows[:6]))
    return None


def active_library_not_banked(current_sid):
    """Idea A+E: at EXIT the primitive `I-NN` must move into invariant_library.md with a `fingerprint:`.
    Otherwise the hunt's knowledge is thrown away and the next target on the same primitive costs the same.
    Checked ONLY when an exit token is written (in the loop this is meaningless). A legacy ledger without the
    `LIBRARY:` field is not blocked - the gate hangs on the sentinel, not on its absence."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if not _i_rows(mt):
        return None
    if not ledger_success_exit(current_sid):
        return None
    if _LIB_TODO_RE.search(lt):
        return rel
    return None


def active_ledger_missing_loopstate(current_sid):
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            if "loop state" not in f.read().lower():
                return os.path.relpath(ledger, root)
    except Exception:
        return None
    return None


# Impacts in Scope - recon-completeness (2026-07-06: instances systematically capture Assets in Scope,
# but FORGET Impacts in Scope - the program's per-impact severity rubric, which calibrates severity AND
# sets WHAT to look for). The template header carries a sentinel `{IMPACTS-TODO ...}`; while it hangs - the section is not captured.
# Anti-FP: block ONLY while the sentinel `IMPACTS-TODO` literally stands (filled with real impacts OR
# `N/A — no formal impacts list` -> sentinel lifted -> passes). A small/no-program target = N/A, not a block.
_IMPACTS_TODO_RE = re.compile(r"IMPACTS-TODO", re.I)


def active_ledger_missing_impacts(current_sid):
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
        if _IMPACTS_TODO_RE.search(txt):
            return os.path.relpath(ledger, root)
    except Exception:
        return None
    return None


# active_impacts_intake_paraphrased (2026-08-18, operator: "missed the exact Impacts in scope") -
# a feedback action-item "extend the missing_impacts sentinel". `IMPACTS-TODO`
# is lifted by ANY filling - it does not distinguish a VERBATIM rubric from a research SUMMARY. In one case the agent filled a summary
# + ITSELF marked "research-paraphrased, VERIFY VERBATIM / research-gap", lifted the sentinel, drove the
# hunt -> anchored on "permanent-freeze", missed the verbatim clause "temporary-freezing = High (24h
# doubling)", re-applied an OOS carve-out to an explicit in-scope exception (a cap-bypass) = a frame-error from
# a PARTIAL intake. Fire <=> a FILLED intake (not a `{}` template / not a blockquote) carries a SELF-DECLARED marker
# "non-verbatim / paraphrased / research-gap". Satisfiable: capture the VERBATIM rubric via Playwright, resolve the marker.
_INTAKE_PARAPHRASE_RE = re.compile(r"перефразир|дословно\s+свер|research[\s\-]*дыр", re.I)


def active_impacts_intake_paraphrased(current_sid):
    """The intake is filled with a research SUMMARY (not verbatim), the hunter itself marked "paraphrased/verify verbatim
    /research-gap" and lifted IMPACTS-TODO -> hunted the wrong impact set (missed a verbatim High clause).
    Fire <=> the marker is in FILLED (not a `{}` template / not a blockquote) content. Off: MANUAL/OFF, HUNT-EXIT, no marker.
    Satisfiable - a Playwright-verbatim rubric + resolving the marker. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    depth = 0
    for line in lt.splitlines():
        opens, closes = line.count("{"), line.count("}")
        inside = depth > 0 or opens > 0
        depth = max(0, depth + opens - closes)
        s = line.lstrip()
        if inside or s.startswith(">"):
            continue
        if _INTAKE_PARAPHRASE_RE.search(line):
            return os.path.relpath(ledger, root)
    return None


IMPACTS_PARAPHRASE_REASON = (
    "IMPACTS INTAKE PARAPHRASED (2026-08-18). Ledger `%s`: "
    "you lifted `IMPACTS-TODO`, but the intake is a research SUMMARY, not a VERBATIM rubric (your own marker: "
    "'research-paraphrased / VERIFY VERBATIM / research-gap'). The full Impacts-in-Scope rubric "
    "says WHAT to look for - from a partial summary you hunt the WRONG impact set (a past case: anchored on "
    "permanent-freeze, missed the verbatim clause 'temporary-freezing = High' + re-applied an OOS carve-out to an "
    "explicit in-scope exception = frame-error). NOW: capture the VERBATIM Impacts/Out-of-Scope rubric via "
    "Playwright (not a research-summary), check each severity clause + the explicit in-scope exceptions from OOS, "
    "update the header and resolve the marker. Satisfiable - close the intake-gap, the loop continues."
)


# Asset-reconciliation (2026-08-13, operator point 1): Immunefi declares "N total assets in scope",
# while the research fetch returns a FRAGMENT of the table (~12 rows of 52) -> missed assets = missed in-scope
# targets, silently. The rule "M<N or N>12 -> open Immunefi YOURSELF via Playwright, take the full list"
# WOULD HANG AS PROSE -> the sentinel `ASSETS-RECON` (header), the completeness-gate holds the exit while it hangs. Lifted =
# reconciled (<=12 all extracted / playwright-full / N/A repo). Anti-FP: only the literal sentinel in the HEADER.
_ASSETS_RECON_RE = re.compile(r"ASSETS-RECON", re.I)

ASSETS_RECON_REASON = (
    "ASSETS UNRECONCILED (2026-08-13, operator point 1). Ledger `%s`: the header carries the sentinel "
    "`ASSETS-RECON` - you did NOT reconcile the asset count. Immunefi declares 'N total assets in scope', while "
    "the research fetch returns a FRAGMENT of the table (~12 rows of 52) -> missed assets = missed in-scope "
    "targets, silently. NOW: reconcile the declared N with the extracted M. **M<N OR N>12 -> open Immunefi YOURSELF via "
    "Playwright (`browser_navigate`), take the FULL asset list** + re-check the program (scope/OOS). "
    "<=12 and all extracted -> the research agent was enough. Write `**Assets in Scope:** N total / M extracted · "
    "[research-fetch|playwright-full]` (or `N/A — repo/no-program`) and LIFT the sentinel `ASSETS-RECON`. This is NOT "
    "a loop exit (a satisfiable intake-gate)."
)


def active_ledger_assets_unreconciled(current_sid):
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
        if _ASSETS_RECON_RE.search(_ledger_header(txt)):    # only in the header (red-team D7: the body does not block)
            return os.path.relpath(ledger, root)
    except Exception:
        return None
    return None


# Out-of-Scope disqualifiers - money-critical recon (2026-08-11: a report was closed OOS $0 because the
# disqualifier from the /scope/ tab was missed - only the in-scope rubric of /information/ was read). The rule
# "read OOS BEFORE submitting" HUNG AS PROSE (feedback_read_scope_before_severity + submission_checklist) and
# was skippable - prose gets skipped ("hook > prose"). A separate sentinel `OOS-TODO` (does NOT duplicate
# IMPACTS-TODO: that one was lifted by filling in-scope, while OOS was never read). Anti-FP: block ONLY while the
# literal sentinel hangs; filled the disqualifiers OR `N/A — no formal OOS list` -> lifted -> passes.
_OOS_TODO_RE = re.compile(r"OOS-TODO", re.I)


_LOOPSTATE_HDR_RE = re.compile(r"(?im)^\s*##\s+Loop\s+State\b")


def _ledger_header(txt):
    """The ledger header - the frontmatter up to `## Loop State` (the Assets/Impacts/Out-of-Scope fields live there; the block
    `## ⚠ LEDGER RULES` comes BEFORE the fields, so a split on the first `## ` would cut them off - split exactly on
    Loop State, the hypothesis body is always AFTER). Sentinels are searched ONLY here (red-team D7: `OOS-TODO` in a hypothesis
    body gave a false eternal block). No Loop State (malformed) -> the whole txt (fail-safe as before)."""
    m = _LOOPSTATE_HDR_RE.search(txt or "")
    return (txt or "")[:m.start()] if m else (txt or "")


def active_ledger_missing_oos(current_sid):
    """Holds the exit while the sentinel `OOS-TODO` hangs in the ledger HEADER (Out-of-Scope disqualifiers were not
    read from /scope/). A small/no-program = `N/A — no formal OOS list` lifts it. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
        if _OOS_TODO_RE.search(_ledger_header(txt)):        # D7: header only, not the hypothesis body
            return os.path.relpath(ledger, root)
    except Exception:
        return None
    return None


# Submit-time OOS disqualifier (2026-08-11): before declaring HUNT-EXIT (= ready to submit High/Crit)
# the finding MUST be checked against the captured Out-of-Scope list -> a line `OOS-CHECK: <finding> vs
# out-of-scope -> PASS/<reason>`. This is the SECOND layer (the first is the intake `OOS-TODO`): even a filled OOS does not
# guarantee that the finding was CHECKED against it before submission (exactly the miss of 2026-08-10 - OOS was available, but
# not applied to the finding). Stands in the success-exit path (like active_library_not_banked): we do not release
# HUNT-EXIT until OOS-CHECK is logged. Anti-FP: an N/A-OOS ledger (no-program) does not require a check -
# if the whole OOS = `N/A — no formal OOS list`, there is nothing to check against -> skip.
# OOS-CHECK requires a REAL verdict (PASS/DISQUALIFIED/CLEAR/CLEAN), not a bare `OOS-CHECK:` (audit:
# presence-only was bypassed by `OOS-CHECK: TODO`). Semantics as for the C3 markers: we force WRITING the outcome of the check.
_OOS_CHECK_RE = re.compile(r"OOS-CHECK\s*:[^\n]*?\b(PASS|DISQUALIFIED|CLEAR|CLEAN|IN[\s-]?SCOPE|OUT[\s-]?OF[\s-]?SCOPE)\b", re.I)
# D6: `[ \t]*` after `:` - do NOT cross `\n` (otherwise the value jumped to the next line).
_OOS_FIELD_RE = re.compile(r"(?im)^[ \t]*\**[ \t]*Out-of-Scope[^\n:]*:[ \t]*(.*)$")


def _oos_captured_real(txt):
    """True - the ledger HEADER has a FILLED Out-of-Scope disqualifier (not `OOS-TODO`, not a bare
    `N/A`, not empty). Only then is the submit-OOS-CHECK meaningful. Legacy/no-program without an OOS field or with `N/A` ->
    False -> the submit-gate is silent. We search in the header (D7: do not catch `Out-of-Scope` in hypothesis prose)."""
    for m in _OOS_FIELD_RE.finditer(_ledger_header(txt)):
        val = m.group(1).strip().strip("{}").strip()
        if not val:
            continue
        if _OOS_TODO_RE.search(val):
            continue                                       # still TODO (the intake-gate holds this)
        # D4: N/A-off ONLY when the whole value ~ an N/A stub (anchor `^N/A`), not a substring
        # (a real list "centralization; testnet N/A; admin-key" is no longer muted falsely).
        if re.match(r"^\s*N/?A\b", val, re.I) or re.search(r"no formal OOS", val, re.I):
            continue                                       # N/A — no-program
        return True                                        # a real disqualifier is captured
    return False


def active_submit_without_oos_check(current_sid):
    """success-exit path: HUNT-EXIT is declared (ready to submit), OOS is really captured, but there is NO
    `OOS-CHECK:` line -> the finding was not checked against Out-of-Scope. Holds the release until OOS-CHECK appears. Off:
    HUNT-EXIT NOT declared (mid-hunt - not our business); OOS not captured / = N/A (nothing to check against);
    manual; OOS-CHECK already present. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(txt):
        return None
    # Judge-2 (final acceptance, defense-in-depth): an internal exit-guard - SYMMETRY with the sibling
    # `active_banked_without_oos_check`. Currently safe ONLY because the only call-site is inside
    # `if ledger_success_exit(...)`; without the guard any future refactor/over-eager loop over all `active_*` would get
    # false mid-hunt fires (OOS is filled by the intake-gate at the start -> the condition is already met mid-hunt).
    if not _has_valid_exit(txt):
        return None                                        # HUNT-EXIT not declared -> the submit-gate is not active
    if _OOS_CHECK_RE.search(txt):
        return None                                        # the finding is checked against OOS -> we release
    if not _oos_captured_real(txt):
        return None                                        # no real OOS (N/A/no-program/legacy)
    return os.path.relpath(ledger, root)


# Scout Fan-Out - explore-wide fan-out. explore-wide counts as worked off ONLY when Status is
# a canonical terminal value: `DONE` / `N/A` / `DEFERRED`. Everything else (`PENDING`, empty,
# AND ANY home-made status like `IN-FLIGHT`/`WIP`) = not worked off -> block.
# OBS-20 (2026-07-29): an agent CONSCIOUSLY wrote `Status: IN-FLIGHT`, knowing the old gate
# blocks "only raw PENDING" - bypassed the mechanism with a home-made status (exactly the SUBSTITUTED pattern).
# The prose "follow the canon" loses to convenience -> we validate the allowed values structurally.
_SCOUT_STATUS_RE = re.compile(r"status\s*:?\s*\**\s*`?\s*([^\n`]+)", re.I)


def active_ledger_scout_pending(current_sid):
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            raw = f.read()
        # OBS-2: while the model is being built - the scout by invariants is logically AFTER it -> we do not force.
        if _model_building(raw):
            return None
        low = raw.lower()
        # FP-fix (2026-08-12): the template RULES prose (Rule 7) contains `## Scout Fan-Out` in
        # backticks -> a naive low.find("## scout fan-out") latched onto it (mid-line, in backticks), and
        # NOT onto the real section heading -> _SCOUT_STATUS_RE grabbed the first stray `status` token
        # (Atom Registry `| status |` / Loop State "surface-status)") -> a legit `Status: DONE` read as
        # non-canonical -> an eternal PENDING block on a finished fan-out. Anchor on the line-start heading
        # (the real `## Scout Fan-Out`; a RULES mention inside a line after "Section `" does not match `^##`).
        m0 = re.search(r"(?m)^\s{0,3}##\s+scout fan-out", low)
        if not m0:
            return None  # no fan-out section (a small contract) - not our business
        i = m0.start()
        m = _SCOUT_STATUS_RE.search(raw[i:])
        val = (m.group(1).strip().lower() if m else "")
        # Canonical PASS: DONE / N/A / DEFERRED. Otherwise (PENDING / empty / IN-FLIGHT / any
        # home-made) -> block. startswith tolerates a tail ("DONE 2026", "N/A — single", "DEFERRED -> after").
        if val.startswith("done") or val.startswith("n/a") or val.startswith("deferred"):
            return None
        return os.path.relpath(ledger, root)
    except Exception:
        return None
    return None


def _grounded_i_count(model_text):
    """How many I-NN are REALLY built = a row with non-empty `check:` (idx2) AND `pred:` (idx6).
    A template `| I-01 | | | state | ... |` (empty check) does NOT count (P0/P1)."""
    n = 0
    for r in _i_rows(model_text):
        if len(r) > 6 and r[2] and r[6]:
            n += 1
    return n


def active_model_before_scout(current_sid):
    """P0 (2026-07-29): divergence-first ORDER - the `I-NN` model FIRST, the scout cuts partitions
    BY INVARIANTS AFTER. Previously the MODEL gate stood LAST in main() (K5) -> scout/depth shadowed it ->
    the fan-out went BEFORE the model, by files, not by invariants. This EARLY gate (before scout-pending) forces
    the model when: scout is still PENDING (fan-out not launched) AND the model is really empty (zero grounded I-NN) AND not
    N/A/BUILDING. Depth gates are untouched (they come later, the model exists by then) -> K5 preserved."""
    if not active_ledger_scout_pending(current_sid):
        return None                      # scout not PENDING (DONE/N-A/DEFERRED/building/no section)
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None                      # MODEL: N/A - lifted
    lt, mt, rel = ctx
    if _model_building(lt):
        return None                      # the model is being built - scout is rightfully deferred (OBS-2)
    if _grounded_i_count(mt) > 0:
        return None                      # the model is really built -> scout is legit (forced by scout_pending)
    return rel                           # scout PENDING + model empty -> force the MODEL BEFORE the fan-out


# P-B boundary-scout SKIPPED (2026-07-12): an instance marked Scout Fan-Out DONE, but did not launch the P-B
# boundary-scout as a SEPARATE agent - "smeared the trust boundary across the code scouts". This is a
# scout_fanout violation: P-B is an ORTHOGONAL axis (the perimeter, not a code subsystem); when sprayed
# the single perimeter map is lost + the choice of the STRONGEST boundary as depth-lead (many of the largest hacks
# live at the boundary, not in code). Structural tell: the `BOUNDARY-MAP` field still holds a `{` placeholder
# (P-B did not write the map). Fire ONLY on a canonical SC ledger (there is a P-B row / BOUNDARY-MAP field) +
# Status DONE - PENDING is caught earlier by scout_pending; N/A/DEFERRED are legit (a small contract / deferred).
def active_ledger_boundary_scout_skipped(current_sid):
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    low = txt.lower()
    if "scout fan-out" not in low:
        return None
    if "boundary/trust-perimeter" not in low and "boundary-map" not in low:
        return None  # non-canonical / web flow-table (F1-F5) - no P-B row, not our check (anti-FP)
    sm = re.search(r"status[:*\s]*`?\s*(pending|done|deferred|n/?a)", low)
    if not sm or sm.group(1) != "done":
        return None  # only after a declared DONE (PENDING -> scout_pending; N/A/DEFERRED legit)
    # FP-fix (2026-07-16): we target exactly the FIELD bullet `- **BOUNDARY-MAP`, NOT the prose in the RULES block
    # (that descriptive line itself contains `BOUNDARY-MAP {placeholder}` as an example -> the old greedy
    # `^[^\n]*boundary-map` matched IT first and forever saw `{` -> an FP on every SC hunt).
    m = re.search(r"(?im)^\s*-\s*\*\*\s*boundary-map[^\n]*$", txt)
    # WARNING 2026-07-28 (finding #2): NOT a bare `{` - the trailing doc on the template's own field line contains
    # the literal `` `{` `` (an explanation about the placeholder), because of which `"{" not in ...` was forever false ->
    # the P-B gate blocked FOREVER even after a real fill. We check the PAIR `{...}` (that IS the
    # placeholder), a single `{` in prose does not form it. The same logic as DEPTH-MAP (everything inside `{}`).
    if m and not re.search(r"\{[^}]*\}", m.group(0)):
        return None  # BOUNDARY-MAP is filled (real boundaries OR N/A) -> P-B recorded
    if not m:
        return None  # no field bullet at all (non-canonical ledger) - anti-FP, not our check
    return os.path.relpath(ledger, root)  # DONE, but BOUNDARY-MAP placeholder/missing -> P-B skipped


# OPTIONAL-menu not consulted (2026-07-12): P8 cross-chain / P7 gov / P9 zk / P10 keeper -
# selective partitions by trigger. An instance free-styled past it (a BTC<->RSK bridge -> P8 conservation was NOT driven by
# a separate scout, where bridge crits live). We do not run a keyword grep over the target (FP-prone), but force an EXPLICIT
# triage record: the sentinel `OPT-TODO` in Scout Fan-Out holds until the instance writes for EACH of P7-P10
# matched->scout / skip-if->reason (a pattern like IMPACTS-TODO). Fire on a canonical ledger + Status DONE.
_OPT_TODO_RE = re.compile(r"OPT-TODO", re.I)


def active_ledger_optmenu_todo(current_sid):
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    low = txt.lower()
    if "scout fan-out" not in low:
        return None
    sm = re.search(r"status[:*\s]*`?\s*(pending|done|deferred|n/?a)", low)
    if not sm or sm.group(1) != "done":
        return None
    # FP-fix (2026-07-16): the sentinel is searched ONLY in the FIELD bullet `- **OPTIONAL-menu triage`,
    # NOT in the RULES prose (that describes the mechanism and mentions `OPT-TODO` literally -> the old
    # `_OPT_TODO_RE.search(txt)` matched rules lines -> an FP on every filled ledger).
    m = re.search(r"(?im)^\s*-\s*\*\*\s*optional-menu triage[^\n]*$", txt)
    if m and _OPT_TODO_RE.search(m.group(0)):
        return os.path.relpath(ledger, root)  # the field holds the sentinel -> triage not done
    return None


# WAVE-2 forgotten (2026-07-12, operator: "Optional goes to wave 2, CORE NEVER goes.
# Do not forget the 2nd wave!"). Cap = 7 concurrent; matched-optional (P7-P10) OR CORE overflow beyond
# 7 -> a deferred WAVE 2. Risk: an instance ran wave 1, marked DONE, forgot about wave 2. Enforcement:
# the line `WAVE-2: <partitions> — PENDING` holds the gate until the wave is run (-> DONE). CORE does NOT go to
# wave 2 - only optional/overflow. Structurally like scout `PENDING`: mtime-independent, paraphrase-resistant.
# FP-fix (2026-07-16): we target the FIELD bullet `- **WAVE-2`, NOT the RULES prose (the rule line describes
# the mechanism and contains `WAVE-2 ... PENDING` as an example -> the old `^[^\n]*wave-2[^\n]*pending` matched IT -> FP).
_WAVE_PENDING_RE = re.compile(r"(?im)^\s*-\s*\*\*\s*wave[\s\-]*2[^\n]*\bpending\b")


def active_ledger_wave_pending(current_sid):
    """True->relpath if the ledger has a WAVE-2 ... PENDING line (a deferred wave not run).
    None = no active ledger / no deferred wave."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    # OBS-3 (2026-07-28): strip `{...}` placeholders - an untouched template carries the EXAMPLE
    # `{... WAVE-2: ... — PENDING ...}`, on which the detector falsely fired (the same template-placeholder
    # blindness that was fixed for `active_ledger_thin`; `wave_pending` did not get the fix and the sentinel did not cover it).
    txt = re.sub(r"\{[^{}]*\}", " ", txt, flags=re.S)
    if _WAVE_PENDING_RE.search(txt):
        return os.path.relpath(ledger, root)
    # P9 (2026-07-29): an agent wrote `WAVE-2 PENDING` NOT into the field bullet `- **WAVE-2`, but INTO the
    # Status line of Scout Fan-Out ("Status: DONE ... -> WAVE-2 PENDING") -> the field-only regex went blind.
    # We catch the WAVE-2...PENDING pair anywhere, but FIRST strip backtick inline code (the template RULES prose
    # holds `WAVE-2 ... PENDING` as an EXAMPLE in backticks -> otherwise an FP on every ledger).
    no_code = re.sub(r"`[^`\n]*`", " ", txt)
    if re.search(r"wave[\s\-]*2[^\n]{0,80}\bpending\b", no_code, re.I):
        return os.path.relpath(ledger, root)
    return None


# P-CLONE producer skipped (Task 4, profile-dapphunt-web3-frontend): Cross-Clone became a mandatory
# phase (S7) for web hunts - if Scout Fan-Out marked the P-CLONE partition active (not N/A/DEFERRED) and the
# wave is DONE, the mandatory artifact `clone_diff.md` (producer: asymmetry_scanner_dapp.py --md-out, Task 3)
# must have been run. The file is absent from the session dir -> block (forces either running the scanner, or explicitly
# marking the partition `N/A — single deploy`). Schema-independent: contract namespace (no TB-) -> None
# (deephunt is not affected - _model_namespace returns "" for I-NN models).
def active_clone_diff_skipped(current_sid):
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    if _model_namespace(mt or "") != "TB":
        return None  # not a web profile (contract/AC/no model) - not our check
    low = lt.lower()
    if "scout fan-out" not in low:
        return None
    sm = re.search(r"status[:*\s]*`?\s*(pending|done|deferred|n/?a)", low)
    if not sm or sm.group(1) != "done":
        return None  # PENDING -> active_ledger_scout_pending catches earlier; N/A/DEFERRED legit
    # The partition row - ONLY a pipe-table row (not the descriptive bullet `P-CLONE` in the RULES prose above).
    m = re.search(r"(?im)^\s*\|[^\n]*p-clone[^\n]*$", lt)
    if not m:
        return None  # no P-CLONE partition in the fan-out (non-canonical ledger) - anti-FP
    if "n/a" in m.group(0).lower() or "deferred" in m.group(0).lower():
        return None  # P-CLONE marked N/A/DEFERRED - legitimately lifted (e.g. single deploy)
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    if os.path.exists(os.path.join(os.path.dirname(ledger), "clone_diff.md")):
        return None  # producer run (incl. content RESULT: N/A — single deploy)
    return os.path.relpath(ledger, root)


# P-AUTHZ producer skipped (Task 9, profile-web2-hunt): the authz-diff harness = the CORE of the web2 profile
# (S17) - if Scout Fan-Out marked the P-AUTHZ partition active (not N/A/deferred) and the wave is DONE,
# the mandatory artifact `authz_matrix.md` (producer: authz_diff.py run_authz_matrix, Task 3) must
# have been run. The file is absent from the session dir -> block (forces either running the harness, or explicitly
# marking the partition N/A/deferred). A structural copy of active_clone_diff_skipped (TB->AC, clone->authz,
# P-CLONE->P-AUTHZ, clone_diff.md->authz_matrix.md). Schema-independent: TB-/contract namespace -> None
# (dapphunt/deephunt are not affected - _model_namespace returns not "AC" for them).
def active_authz_matrix_skipped(current_sid):
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    if _model_namespace(mt or "") != "AC":
        return None  # not a web2 profile (dapphunt/contract/no model) - not our check
    low = lt.lower()
    if "scout fan-out" not in low:
        return None
    sm = re.search(r"status[:*\s]*`?\s*(pending|done|deferred|n/?a)", low)
    if not sm or sm.group(1) != "done":
        return None  # PENDING -> active_ledger_scout_pending catches earlier; N/A/DEFERRED legit
    # The partition row - ONLY a pipe-table row (not the descriptive bullet `P-AUTHZ` in the RULES prose above).
    # WARNING the row is combined `| P-SIGN / P-AUTHZ |` (one template row for TB+AC) - we match `p-authz`
    # directly; the namespace guard above has already cut off TB models before this line.
    m = re.search(r"(?im)^\s*\|[^\n]*p-authz[^\n]*$", lt)
    if not m:
        return None  # no P-AUTHZ partition in the fan-out (non-canonical ledger) - anti-FP
    if "n/a" in m.group(0).lower() or "deferred" in m.group(0).lower():
        return None  # P-AUTHZ marked N/A/deferred - legitimately lifted
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    if os.path.exists(os.path.join(os.path.dirname(ledger), "authz_matrix.md")):
        return None  # producer run (incl. MODE: single+unauth / RESULT: matrix-run, 0 divergences)
    return os.path.relpath(ledger, root)


# Operation-outcome coverage (Task 2, Plan 9 hunter-parity): run_authz_matrix now emits EXACTLY ONE
# row for EACH (operation, role) check with an explicit status enum (`tested-clean`/`divergent`/
# `inconclusive-<class>`/`excluded`/`blocked`) -- "checked-clean" is distinguishable from "not tested". This gate
# = a CONTENT check of the co-located producer file (authz_matrix.md for AC, clone_diff/dataflow_map for TB): the file
# EXISTS, but at least one (operation, role) row WITHOUT a valid status -> coverage not accounted -> block. Differs
# from active_authz_matrix_skipped (that one is for the ABSENCE of the file); this one fires only when the file is PRESENT,
# but rows lack a status (e.g. a hand-made / pre-Task-2 file). Namespace-consistent with the sibling
# producer gates (AC->authz_matrix, TB->clone/dataflow); contract namespace ("") -> None. Off-switch
# `MODEL: N/A` (via `_model_ctx`), like the siblings. WARNING TB producers (clone_diff/dataflow_map) carry
# delta rows, NOT (operation, role) rows -> there is no `исход` ("outcome") column -> the parser finds no operation
# table there and stays silent (TB operation-completeness DEFERRED: these producers have no N-roles x M-operations form;
# documented in operation_coverage_gate_replay.py). Schema-independent, but the producer choice is by namespace.
_OP_STATUS_HDR_RE = re.compile(r"\bисход\b", re.I)
_OP_VALID_STATUS_RE = re.compile(
    r"^(tested-clean|divergent|excluded|blocked|inconclusive-[a-z0-9_\-]+)$", re.I)


def _op_coverage_incomplete_file(path):
    """True - `path` (producer .md) holds an operation-coverage table (a header with the `исход` ("outcome") column AND a
    marker of an operation table endpoint/role) and >=1 data row whose `исход` cell is empty / `-` / not a
    valid status enum. No file / no such table / all rows have a status -> False. Fail-open
    (unreadable -> False). Cells do not contain `|` (the producer sanitises `_safe_cell`: `|`->`/`)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return False
    # status_idx: None = outside an operation table; -1 = an operation table WITHOUT the `исход` column (legacy/
    # pre-Task-2 -> the whole table has no status); >=0 = the index of the `исход` column.
    status_idx = None
    # an operation table is recognised by a header with endpoint AND role (a D-NN block does not carry them - anti-FP).
    def _is_op_header(low):
        return ("endpoint" in low and "роль" in low) or ("operation" in low and "role" in low)
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|"):
            status_idx = None                            # left the table
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and all(set(c) <= set("-: ") for c in cells):
            continue                                     # separator row |---|---| - skip
        low = s.lower()
        if status_idx is None:
            if _is_op_header(low):                        # header of an operation table
                status_idx = -1
                for i, c in enumerate(cells):
                    if _OP_STATUS_HDR_RE.search(c):
                        status_idx = i                   # found the `исход` column
                        break
            continue
        # data row inside an opened operation table
        if status_idx < 0:
            return True                                  # a table without the `исход` column -> a row without a status
        if status_idx >= len(cells):
            return True                                  # the row is shorter than the header -> the status cell is absent
        cell = cells[status_idx]
        if not cell or cell == "-" or not _OP_VALID_STATUS_RE.match(cell):
            return True
    return False


def active_operation_coverage_incomplete(current_sid):
    """Task 2 (Plan 9): a co-located producer CONTENT gate. The producer file for the model namespace EXISTS, but
    at least one (operation, role) row has no valid status -> relpath(ledger). Off-switch: `MODEL:
    N/A` (`_model_ctx` None) + contract namespace (no producer). AC -> authz_matrix.md; TB ->
    clone_diff.md/dataflow_map.md (they have no operation table -> the parser is silent, see the comment above)."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    ns = _model_namespace(mt or "")
    if ns == "AC":
        producers = ["authz_matrix.md"]
    elif ns == "TB":
        producers = ["clone_diff.md", "dataflow_map.md"]
    else:
        return None                                      # contract / no model - no producer
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    ddir = os.path.dirname(ledger)
    for name in producers:
        if _op_coverage_incomplete_file(os.path.join(ddir, name)):
            return os.path.relpath(ledger, root)
    return None


# P-AI producer skipped (Task 3, Plan 7 S60, profile-web-ai-surface): an AI/LLM feature on web hunts
# carries its own trust boundary (context!=instruction, tool-call re-authz AFTER the LLM: injection->priv tool-call /
# RAG bleed / prompt-extract / SSRF-via-agent / output->sink, Cat 28) - if Scout Fan-Out marked the
# P-AI partition active (not N/A/deferred = an AI surface detected) and the wave is DONE, the mandatory artifact
# `ai_trust_matrix.md` (producer: ai_injection_diff.py run_ai_trust_matrix, Task 1) must have been run.
# The file is absent from the session dir -> block (forces either running the harness, or marking P-AI `N/A — no AI
# surface`). A structural copy of active_authz_matrix_skipped (the producer-absent canon; authz->ai-trust,
# P-AUTHZ->P-AI, authz_matrix.md->ai_trust_matrix.md), BUT the namespace guard covers BOTH web profiles: the ai-trust
# axis lives in both TB- (dapphunt) and AC- (web2) models -> `not in ("AC","TB")` instead of a single
# `!= "AC"`. deephunt gives "" -> excluded, the gate is silent there. The partition regex anchors `p-ai\b` (anti-
# match with P-AUTHZ/P-AUTH/other P-*). STOP the off-switch is DELIBERATELY without `_i_matured_count`/`if not manual`
# (R5, review #2-F1): the producer-absent canon (active_authz_matrix_skipped) does not use them - it is an idiom
# of the SENTINEL family (active_undup_sweep_incomplete). We follow the producer-absent reference VERBATIM.
def active_ai_trust_unresolved(current_sid):
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    if _model_namespace(mt or "") not in ("AC", "TB"):
        return None  # not a web profile (contract/deephunt/no model) - not our check
    low = lt.lower()
    if "scout fan-out" not in low:
        return None
    sm = re.search(r"status[:*\s]*`?\s*(pending|done|deferred|n/?a)", low)
    if not sm or sm.group(1) != "done":
        return None  # PENDING -> active_ledger_scout_pending catches earlier; N/A/DEFERRED legit
    # The partition row - ONLY a pipe-table row. Anchor `p-ai\b` (not the prefix of `p-authz`/`p-auth` etc.).
    m = re.search(r"(?im)^\s*\|[^\n]*\bp-ai\b[^\n]*$", lt)
    if not m:
        return None  # no P-AI partition in the fan-out (non-canonical ledger) - anti-FP
    if "n/a" in m.group(0).lower() or "deferred" in m.group(0).lower():
        return None  # P-AI marked `N/A — no AI surface` / deferred - legitimately lifted
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    if os.path.exists(os.path.join(os.path.dirname(ledger), "ai_trust_matrix.md")):
        return None  # producer run (incl. RESULT: ai-trust matrix-run, 0 divergences)
    return os.path.relpath(ledger, root)


# -- DEPTH-QUALITY gates (a past hunt 2026-07-12: 2 Crits submitted -> BOTH DUPLICATE $0) --
# Diagnosis (measured on a live ledger, not by feel): the instance WROTE OUT an un-dup lead (a beacon
# CL-exit->sweep->WithdrawalVault->pool totalDeposits->share-price = a 5-layer CROSS-SUBSYSTEM composite
# across two subsystems) and ABANDONED it as "unproven amplification / NEXT", banking a mid-depth
# H-09 -> a duplicate. Duplicates live at mid-depth (where the crowd reaches); an un-dup crit sits at the JOINT OF DISTANT
# subsystems below the depth-ceiling. The existing wide_but_shallow catches "no depth-lead", but does NOT catch
# (B) an abandoned written-out composite and (A) a fake "5/5" claim without a map. Two structural gates
# (state, not prose - a lesson: "MANDATORY" in a doc loses, forcing = a hook on the ledger state).

# (B) NO-ABANDON-COMPOSITE: a Crit/High-capable amplification/cross-thread composite is deferred without a resolution.
# Catches the instance's NATURAL entry (`AMPLIFICATION THREAD` / `cross-thread seed` - observed in practice),
# does not require remembering a sentinel. Window-scoped (~600 chars from the marker): marker + crit word
# + deferral WITHOUT a resolution = anti-FP (an actively driven "PoC building"/"T4"/"confirmed" OR a killed-with-
# falsifier composite does NOT trigger - a resolution in the window un-gates).
_COMP_MARK_RE = re.compile(r"amplification thread|amplif-thread|cross-thread seed", re.I)
_COMP_CRIT_RE = re.compile(r"critical|\bhigh\b|insolven|theft|\bsteal|freez|orphaned|drain|inflat|\bmint", re.I)
_COMP_DEFER_RE = re.compile(r"\bnext\b|pending|unproven|chasing|\bchase\b|to-?do|could reach|not yet|отлож|позже", re.I)
_COMP_RESOLVE_RE = re.compile(r"\bpoc\b|d-poc|\bt4\b|killed|falsifier|refuted|confirm|\bdriven\b|de-minimis|подтвер", re.I)
# The boundary = the next BULLET (`- `/`* `) or section (`##`/`###`). We scope the window to the bullet, NOT to the section:
# an amplification thread lives in ITS OWN bullet, while the whole H-NN block may be KILLED on ANOTHER (main)
# vector (a case: the main halt-vector KILLED, but the AMPLIFICATION sub-thread OPEN) - block-scope
# would falsely un-gate by the main vector's resolution. Bullet-scope cuts this precisely.
_COMP_BULLET_END_RE = re.compile(r"\n[ \t]*[-*] |\n#{2,3}\s")


def _composite_open(txt):
    """True if there is a Crit/High-capable composite WITHOUT a resolution. Window = the marker's BULLET (from the marker to
    the next `- `/`* `/section, cap 600): marker + crit word + deferral in the bullet, WITHOUT a resolution in
    the bullet (an actively driven "PoC done"/"T4 confirm" OR killed-with-falsifier in THIS bullet = silent;
    a resolution of ANOTHER bullet/vector of the same H-NN does not un-gate)."""
    for m in _COMP_MARK_RE.finditer(txt):
        s = m.start()
        nb = _COMP_BULLET_END_RE.search(txt[s + 1:s + 600])
        end = (s + 1 + nb.start()) if nb else min(len(txt), s + 600)
        w = txt[s:end]
        if _COMP_CRIT_RE.search(w) and _COMP_DEFER_RE.search(w) and not _COMP_RESOLVE_RE.search(w):
            return True
    return False


def active_ledger_composite_abandoned(current_sid):
    """True->relpath if a Crit-capable composite is written out but deferred without a resolution (needs DRIVE to a D-PoC
    OR KILL with a falsifier). None = no active ledger / no open composite."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    return os.path.relpath(ledger, root) if _composite_open(txt) else None


# ── T6 (Plan 9, Tier B — intent-steelman scoped-to-DRIVE) ──
# An external practitioner's observation: "AI is strong at finding the UNUSUAL, weak at the question 'is this even a bug or BY DESIGN?'". A hypothesis
# that REACHED DRIVE (State resolved to `C-PoC-attempting` / `D-PoC`) MUST carry a birth-time field
# **Intent-steelman: the strongest argument that the behaviour is INTENDED, with a `file:line` proof
# (docstring/NatSpec/test/comment/commit) OR a deliberate `N/A — no intent evidence`. Checked BEFORE
# spending depth on a PoC. Scoped-to-DRIVE (NOT every MAYBE/A/B/building-block - otherwise friction on the whole loop).
# Merge-guard (R4): birth-time "did the system INTEND this?" BEFORE depth != verify-time self-steelman before T4
# ("is my finding FALSE?" AFTER the PoC, mythos T4 STEP) - DIFFERENT questions, both FULL gates, do not conflate.
# The off-switch is natural (like the composite/chain gates, NOT model-maturity): the template State = a slash MENU
# (`A-formulating / ... / D-Parked`) -> contains `/` -> not resolved to DRIVE -> does not trigger. DRIVE by
# itself is a sufficient signal (we do not wait for a mature model: the birth-time check happens on promotion to C+).
_STATE_LINE_RE = re.compile(r"(?im)^\s*[-*]\s*\*\*state:\*\*\s*(?P<val>[^\n]+)$")
_DRIVE_STATE_RE = re.compile(r"^\s*(?:C-PoC-attempting|D-PoC)\b", re.I)
_INTENT_FIELD_RE = re.compile(r"(?im)^\s*[-*]\s*\*\*intent-steelman\b[^\n]*$")
# Intent proof: `file:line` (`Foo.sol:42`, any `:\d+`) / a deliberate `N/A` / a reference to a `commit`.
_INTENT_PROOF_RE = re.compile(r":\d+|\bN/?A\b|\bcommit\b", re.I)
_HNN_BLOCK_SPLIT_RE = re.compile(r"(?m)^###\s+")


def _drive_intent_missing(ledger_text):
    """[H-NN, ...] for hypotheses in the DRIVE state (State resolved to `C-PoC-attempting`/`D-PoC`) that
    have no FILLED **Intent-steelman field (proof `file:line`/`N/A`/`commit`). An empty list =
    all DRIVE hypotheses are grounded OR none reached DRIVE (the template slash-menu State and the terminal
    D-Killed/D-Parked do NOT count as DRIVE - the gate does not touch them, no retroactive friction)."""
    txt = ledger_text or ""
    out = []
    for blk in _HNN_BLOCK_SPLIT_RE.split(txt):
        if not blk:
            continue
        head = blk.splitlines()[0]
        if not head.strip().upper().startswith("H-"):
            continue                                  # the block is not a hypothesis (prose before the first ###)
        sm = _STATE_LINE_RE.search(blk)
        if not sm:
            continue                                  # no State line (Refuted/Parked blocks of the template)
        val = sm.group("val").strip()
        if "/" in val:
            continue                                  # template slash-menu - State not resolved to DRIVE
        if not _DRIVE_STATE_RE.match(val):
            continue                                  # A/B/D-Killed/D-Parked - not DRIVE (scoped-to-DRIVE)
        hid = head.split()[0].rstrip(":") if head.split() else "H-??"
        fm = _INTENT_FIELD_RE.search(blk)
        if not fm:
            out.append(hid)                           # no Intent-steelman field at all
            continue
        s = fm.start()
        nb = _COMP_BULLET_END_RE.search(blk[s + 1:s + 800])  # the field may be multi-line - up to the bullet/section
        end = (s + 1 + nb.start()) if nb else min(len(blk), s + 800)
        body = blk[s:end]
        if "{" in body:
            out.append(hid)                           # the {INTENT-TODO ...} placeholder was not lifted
        elif not _INTENT_PROOF_RE.search(body):
            out.append(hid)                           # filled, but without a `file:line`/`N/A`/commit proof
    return out


def active_ledger_intent_steelman_missing(current_sid):
    """T6 (Plan 9, Tier B): a hypothesis in DRIVE (State `C-PoC-attempting`/`D-PoC`) without a birth-time
    intent-steelman (an argument that the behaviour is INTENDED, with a `file:line`/`N/A`/commit proof). Holds the
    exit while at least one DRIVE hypothesis is not grounded. The off-switch is natural (no resolved
    DRIVE claim -> None), model-maturity is NOT needed. `is_giveup=False` (satisfiable). Returns
    "H-NN, ..." or None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    missing = _drive_intent_missing(txt)
    return ", ".join(missing[:8]) if missing else None


INTENT_STEELMAN_REASON = (
    "INTENT-STEELMAN MISSING (Plan 9, Tier B - T6; an external practitioner: 'AI is strong at the UNUSUAL, weak at \"is this a bug or "
    "BY DESIGN?\"'). Hypothesis(es) %s reached DRIVE (State C-PoC-attempting / D-PoC), but do NOT carry the birth-time "
    "field **Intent-steelman. BEFORE burning depth on a PoC - write the STRONGEST argument that this behaviour is "
    "INTENDED (by design), with a MANDATORY `file:line` proof (docstring / NatSpec / test / comment / "
    "commit message): found proof of intent -> severity down / KILL (this is not a bug but a design); found nowhere "
    "-> write `N/A — no intent evidence found` (the absence itself = a signal: the behaviour is not pinned anywhere as "
    "a design -> the hypothesis is STRONGER). WARNING R4 merge-guard: this is a birth-time 'is the system DESIGNED so?' BEFORE depth - "
    "DIFFERENT from the verify-time self-steelman before T4 ('is my finding FALSE?' AFTER the PoC, mythos T4 STEP); do not "
    "conflate. Scoped-to-DRIVE: hypotheses in the A/B/MAYBE/building-block field do NOT require it."
)


# Task 6 (Plan 6, S27 residual): cross-attack-chains - co-occurrence != dependency. Findings on
# ONE target, listed NEXT TO each other (`**Composite candidates:** BB-08b, BB-10` - a real form from
# a past ledger; co-occurring `BB-NN` in one `## Building Blocks` bullet), are NOT a chain without a
# PROVEN transfer output-A->input-B (mythos Technique 3 "Draw the Dependency": the second step must
# be IMPOSSIBLE without the first - the output PHYSICALLY becomes the input, not just "both were found here").
# A bullet/field-scoped window (the same pattern as `_composite_open` above). The off-switch = the very nature of the
# match: the claim regex requires a REAL (not a `{TODO}` placeholder) value - an empty/template ledger
# never matches (no separate maturity threshold is needed, unlike Task 1/2/3 `_i_matured_count`).
_CHAIN_CLAIM_RE = re.compile(
    r"\*\*Composite candidates:\*\*\s*(?P<cand>[^\n]+)"
    # fix-round 1 (MINOR, opus review): bare `,` connector dropped — matched non-chain co-listings
    # ("Refuted BB-01, BB-02 today"). Requires an actual combine/direction word now.
    # fix-round 5 (a live hunt 2026-08-12): `->` REMOVED from the loose alternation. In ledgers `->`
    # overwhelmingly means a TRANSITION (severity `INERT->OOS/Low`, `Medium->High`, status `PENDING->DONE`,
    # resolution `-> H-03`), NOT a chain connector. A case: "LEAD-1 late-close (BB-12, ... slash-dodge
    # INERT->OOS/Low), LEAD-2 rent-dust (BB-13)" = TWO SEPARATE residuals, the arrow glued to
    # severity tokens inside the [0,80] window -> a false chain-claim. The agent was forced to MUTILATE the ledger
    # ("removing the arrow between BB refs, surgical prose-fix") to bypass the gate - a gate that forces
    # damaging the artifact is worse than no gate. The discriminator = ADJACENCY: a real terse chain
    # is written `BB-04 -> BB-05` (the arrow RIGHT between the ids), a transition - with its own tokens right next to the arrow
    # and the ids far away in prose. Cost: `BB-04 (dust) -> BB-05` (prose between the id and the arrow) is no longer caught -
    # accepted: let a word connector be there. Unambiguous `+`/`&`/`with`/`chain*`/`combin*` are untouched.
    r"|(?P<bb>BB-\d+(?:[^\n]{0,80}?(?:\+|&|\bwith\b|\bchain\w*\b|\bcombin\w*\b)[^\n]{0,80}?"
    r"|\s*(?:→|->)\s*)BB-\d+)",
    re.I,
)
# fix-round 1 (IMPORTANT, opus review): `**Composite candidates:**` filled with a none-marker —
# `—`/`N/A`/`none`/`нет` (Russian "none") — is a FILLED field, not a `{TODO}`-placeholder, so the old `"{" in cand`
# off-switch didn't catch it. Real ledgers from several past hunts
# write exactly this after resolving a lead as non-composite.
#
# fix-round 2 (opus review): round-1's zero-id-ref check still fired on a LONE `BB-06`/`H-01` (one
# ref, no second party) — real ledgers write exactly this too (folksfinance:352, impossible-cloud-
# network:136, chainlink/user hypotheses.md) after merely NOTING a possible candidate without ever
# linking it. Mirrors the bb-branch's own bar (≥2 ids via a connector): a claim now requires ≥2
# DISTINCT id-refs, OR exactly 1 id-ref plus an explicit chain-word nearby (a hunter naming ONE
# candidate while saying "chained with"/"combines"/"feeds"/etc is still making a real claim, with the
# parent H-NN as the implicit first party).
_CHAIN_ID_ALL_RE = re.compile(r"\b(?:BB|H)-\d+", re.I)
_CHAIN_WORD_NEARBY_RE = re.compile(r"\bchain\w*\b|\bcombin\w*\b|\bwith\b|→|\bfeeds?\b|\bconsumes?\b", re.I)
# An explicit output->input transfer - what "draw the dependency graph" requires to be written in words, not
# only a co-occurrence list. Does not claim NLP completeness (a soft-nudge, not a hard-block): the goal is to
# make the hunter SPELL OUT the transfer, rather than silently assume it from adjacency.
_CHAIN_DEP_PROOF_RE = re.compile(
    r"\boutput\b[^\n]{0,150}?\binput\b|\binput\b[^\n]{0,150}?\boutput\b"
    r"|\bfeeds?\b[^\n]{0,60}?\binput\b|\bimpossible\s+without\b"
    r"|\bconsumes?\b[^\n]{0,60}?\boutput\b"
    r"|\breads?\b[^\n]{0,60}?\bwrit(?:e|es|ten)\b|\bwrit(?:e|es|ten)\b[^\n]{0,60}?\breads?\b",
    re.I,
)
_CHAIN_WINDOW_END_RE = re.compile(r"\n[ \t]*[-*] |\n#{2,3}\s")


def _chain_claim_unproven(ledger_text):
    """The first co-occurrence chain-claim (`**Composite candidates:**` with a real value OR >=2
    `BB-NN` in one bullet via a connector) WITHOUT an output->input dependency proof in the window around it
    (250 chars BEFORE + up to the next bullet/section AFTER, the same bullet-scope as `_composite_open`).
    True = there is an unverified claim."""
    txt = ledger_text or ""
    for m in _CHAIN_CLAIM_RE.finditer(txt):
        cand = m.group("cand")
        if cand is not None:
            if not cand.strip() or "{" in cand:
                continue                              # an unfilled template placeholder - not a claim
            _ids = set(x.upper() for x in _CHAIN_ID_ALL_RE.findall(cand))
            if len(_ids) < 2 and not (len(_ids) == 1 and _CHAIN_WORD_NEARBY_RE.search(cand)):
                continue                              # a none-marker / a single id without a chain word - not a claim
        else:
            # fix-round 3 (opus review): the bb branch matches `BB-NN ...connector... BB-NN`, but the regex
            # does NOT check that these are TWO DIFFERENT ids - the same id mentioned twice in a narrative
            # (e.g. "BB-06 = adversary-'for' only ... driving skeptic-T4 on BB-06"), the non-greedy
            # `[^\n]{0,80}?` latches onto the second reference and falsely matches as a co-occurrence claim.
            #
            # fix-round 4 (opus review): round-3's span-distinct-`set()` guard counted distinct ids over
            # the WHOLE captured span, not over the TWO ENDS that the regex really paired - a random
            # THIRD id inside the span "rescued" a self-reference into an imaginary chain (a real case:
            # "BB-07-Low, 17 oracle-adapter I-22-PARTIAL→running)... Net: 1 marginal Low (H-09) +
            # BB-07" - the regex ends BB-07...BB-07 (a self-reference), but the span also carries H-09 (a tally of
            # findings, not a chain id) -> {BB-07,H-09}=2 distinct -> round-3 falsely let it through). Endpoint-
            # guard: we compare EXACTLY the first and last `BB-`/`H-` id found in the captured
            # bb text - since the bb alternation LITERALLY anchors on `BB-\d+ ... BB-\d+` at the start and
            # end of the pattern, findall()[0]/findall()[-1] are exactly the two ends the regex paired;
            # whatever dangles BETWEEN them (H-09, status arrows I-22-PARTIAL->running) does not matter.
            _bb_ids = _CHAIN_ID_ALL_RE.findall(m.group("bb") or "")
            if _bb_ids and _bb_ids[0].upper() == _bb_ids[-1].upper():
                continue                              # both ends are the same id - not a claim
        s = m.start()
        pre = txt[max(0, s - 250):s]
        nb = _CHAIN_WINDOW_END_RE.search(txt[m.end():m.end() + 400])
        post_end = m.end() + (nb.start() if nb else min(400, len(txt) - m.end()))
        post = txt[s:post_end]
        if not _CHAIN_DEP_PROOF_RE.search(pre + post):
            return True
    return False


def active_chain_dependency_unproven(current_sid):
    """Task 6 (S27): a claimed chain of findings (co-occurrence) WITHOUT a proven transfer
    output-A->input-B. A soft-nudge (`is_giveup=False` at the call-site) - holds the turn, does not block
    for good. Namespace-agnostic (`Composite candidates:`/`BB-NN` is a common ledger template form
    in all profiles). Returns relpath(ledger) or None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    return os.path.relpath(ledger, root) if _chain_claim_unproven(txt) else None


CHAIN_DEPENDENCY_REASON = (
    "DRAW THE DEPENDENCY (Plan 6, S27, mythos Technique 3). A chain of findings is claimed "
    "(`Composite candidates:` / co-occurring `BB-NN`) in %s WITHOUT an explicit output-A->input-B transfer. "
    "Co-occurrence (found on one target / listed next to each other) is NOT a chain. A real chain "
    "= the second step is IMPOSSIBLE without the first: A.output PHYSICALLY becomes B.input (a specific field/"
    "variable/state that B reads/uses is created EXACTLY via A) - real exploit chains in the wild were like this, not coincidences. "
    "Write the explicit transfer NEXT TO the claim (`A.output "
    "feeds B.input`, name the field/variable), OR break the claim if these are just two independent "
    "observations on one target (then they remain separate Building Blocks, not a composite)."
)


# (A) DEPTH-MAP UNGROUNDED: a depth-lead CLAIMS >=5 layers, but the interaction map (the **DEPTH-MAP field,
# L1->L5 with file:line + a subsystem per layer) is still `{placeholder}`. Closes the gaming of "I will write 5/5 to
# shut up wide_but_shallow without a real cross-subsystem trace". A sentinel pattern like BOUNDARY-MAP:
# we do not parse subsystem semantics (FP-prone), we force WRITING the map; N/A - single-subsystem can be filled in
# for a legit single-subsystem deep bug. Fire ONLY on a claim >=5 (otherwise wide_but_shallow governs).
_DEPTHMAP_FIELD_RE = re.compile(r"(?im)^[^\n]*\*\*depth-map\b[^\n]*$")


def active_ledger_depthmap_placeholder(current_sid):
    """True->relpath if some depth-lead claims >=5 layers, while the **DEPTH-MAP field holds a `{` placeholder
    (the map is not written out). None = no ledger / no >=5 claim / no field (legacy) / the map is filled (or N/A)."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    claimed = 0
    for line in _DEPTH_LEAD_LINE_RE.findall(txt):
        if "{" in line:
            continue  # an unfilled placeholder field != a real claim >=5
        claimed = max(claimed, _depth_layers(line))
    if claimed < 5:
        return None  # no claim >=5 -> nothing to ground (wide_but_shallow governs the "no depth" case)
    fields = _DEPTHMAP_FIELD_RE.findall(txt)
    if not fields:
        return None  # legacy ledger without a DEPTH-MAP field - not our check
    if any("{" in ln for ln in fields):
        return os.path.relpath(ledger, root)  # claim >=5, but the map = placeholder -> not grounded
    return None


# (A+) CROSS-SUBSYSTEM soft-check: DEPTH-MAP is FILLED (not a placeholder), claim >=5, but the map crosses
# <3 distinct subsystems -> "5 layers in ONE file" != anti-duplicate depth (an un-dup crit sits at the joint of DISTANT
# subsystems). A soft-nudge (is_giveup=False): resolved EITHER by adding cross-subsystem layers, OR by an explicit
# `N/A — single-subsystem (<primitive>)` for a legit single-subsystem but deep bug.
# Anti-FP: we count max(distinct file-basename, distinct `(subsystem)` tags) - either is enough; N/A /
# single-subsystem escape; fire ONLY on a filled map (placeholder -> the depthmap_placeholder gate).
_FILE_BASENAME_RE = re.compile(r"([\w\-]+\.(?:sol|go|rs|move|cairo|vy|py|ts|js|c|h|cpp|hpp|circom|zok))\b", re.I)
_SUBSYS_TAG_RE = re.compile(r"\(([^)\n]{2,40})\)")


def _depthmap_block(txt):
    """The text of the DEPTH-MAP block: from the **DEPTH-MAP field to the next bullet/section (a map may be multi-line)."""
    m = _DEPTHMAP_FIELD_RE.search(txt)
    if not m:
        return None
    s = m.start()
    nb = _COMP_BULLET_END_RE.search(txt[s + 1:s + 800])
    end = (s + 1 + nb.start()) if nb else min(len(txt), s + 800)
    return txt[s:end]


def _distinct_subsystems(block):
    files = set(b.lower() for b in _FILE_BASENAME_RE.findall(block))
    tags = set(t.strip().lower() for t in _SUBSYS_TAG_RE.findall(block) if "→" not in t and "->" not in t)
    return max(len(files), len(tags))


# OBS-6: a killed/archived depth thread (killed by falsifier) = not an active >=5 claim; we do not gate its map.
_KILLED_LEAD_RE = re.compile(r"KILLED|archiv|архив", re.I)


def active_ledger_depthmap_single_subsystem(current_sid):
    """True->relpath if a depth-lead claims >=5, DEPTH-MAP is filled, but crosses <3 subsystems and is NOT
    marked single-subsystem/N/A. None = no ledger / no >=5 / no field / placeholder / cross-subsystem OK /
    explicit single-subsystem."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    claimed = 0
    for line in _DEPTH_LEAD_LINE_RE.findall(txt):
        if "{" in line:
            continue
        # OBS-6 (2026-07-28): a KILLED/archived thread = NOT an active >=5 claim. Depth-lead
        # with `KILLED`/`archiv`/`архив` - this is the map of a thread closed by a falsifier (D-09: a cross-repo
        # trace, honestly killed), not a "5/5" self-report. Previously it required a manual `N/A` workaround.
        if _KILLED_LEAD_RE.search(line):
            continue
        claimed = max(claimed, _depth_layers(line))
    if claimed < 5:
        return None
    block = _depthmap_block(txt)
    if not block or "{" in block:
        return None  # no field / placeholder (-> depthmap_placeholder gate)
    low = block.lower()
    if "single-subsystem" in low or "n/a" in low or "n\\a" in low:
        return None  # the instance EXPLICITLY admitted one-subsystem (a legit single-subsystem deep bug) -> not our check
    if _KILLED_LEAD_RE.search(block):
        return None  # OBS-6: DEPTH-MAP marked KILLED/archive = the map of a killed thread, not an active claim
    if _distinct_subsystems(block) >= 3:
        return None  # the map crosses >=3 subsystems -> cross-subsystem OK
    return os.path.relpath(ledger, root)


# FORK-DIFF gate (fork confession 2026-08-09): on a fork target the instance closed threads with the phrase
# "canonical parent / matches parent" = a CLASSIFICATION passed off as a falsifier + zero executable verification
# (neither a fork-PoC, nor an invariant test). This is the intersection of two mandates that nothing caught:
# (1) feedback_canonical_mechanism_substituted - "canonical" = a trigger to dig (SUBSTITUTED/fork deviation),
# NOT a wave-off; (2) BREADTH!=DEPTH / FALSE-EXHAUSTION - the 6th paraphrase bypass. A lesson: the regex race
# cannot be won - a gate on the ledger STATE. The state signal = the field `PARENT-FORK:` (the parent identified
# explicitly/via identify_parent). If the parent is NOT N/A and the executable diff (family_fork_diff / invariant-test-
# on-fork) was not run - we hold the exit. Part 3 (contained): on a depth claim >=5 on a fork the `observed:` in
# DEPTH-TRACE must reference an executable artifact (not a static code match). Off-switch: an immature
# model / MODEL: N/A / no field / `PARENT-FORK: N/A — not a fork` / a `{` placeholder. Structurally like
# clone_diff/authz (producer-absent), but by the STATE of the field, not by the fan-out partition.
# The field is formatted `- **PARENT-FORK:** <val>` - the closing `**` come RIGHT after `:`, so
# after the colon we swallow optional `**` before the value (otherwise they get into the capture).
_PARENT_FORK_RE = re.compile(r"(?im)^\s*[-*]\s*\*\*\s*PARENT-FORK:\s*\*{0,2}\s*(.+?)\s*\*{0,2}\s*$")
_FORK_DIFF_FIELD_RE = re.compile(r"(?im)^\s*[-*]\s*\*\*\s*Fork-diff:\s*\*{0,2}\s*(.+?)\s*\*{0,2}\s*$")
# an executable artifact in DEPTH-TRACE or in the Fork-diff field: a real run, not reading the source.
# `fork_diff`/`family_fork_diff` (underscore) are caught via `[-\s_]?`; `\b` before fork was removed deliberately
# (otherwise `family_fork_diff` did not match - `_` = a word char, no boundary).
_EXEC_ARTIFACT_RE = re.compile(
    r"forge|anvil|foundry|fork[-\s_]?(?:diff|test|run|poc)|simnet|clarinet|prover|"
    r"echidna|medusa|trident|\.log\b|\btrace\b|\brpc\b|\bpoc\b", re.I)
_FORK_NA_RE = re.compile(r"n/?a|not a fork|не форк|no parent|нет родител", re.I)


def _fork_diff_done(lt, sess_dir):
    """Was the executable fork-diff run? The field `Fork-diff: DONE — <artifact>` (not `{`, DONE + an exec reference)
    OR a `fork_diff*` file in the session dir / deep/. Fail-safe: doubt -> not done (we hold)."""
    fm = _FORK_DIFF_FIELD_RE.search(lt)
    if fm:
        val = fm.group(1).strip()
        if "{" not in val and re.search(r"\bDONE\b", val, re.I) and _EXEC_ARTIFACT_RE.search(val):
            return True
    try:
        cands = list(os.listdir(sess_dir))
        deep = os.path.join(sess_dir, "deep")
        if os.path.isdir(deep):
            cands += os.listdir(deep)
        if any(f.lower().startswith("fork_diff") for f in cands):
            return True
    except Exception:
        pass
    return False


def active_fork_diff_unrun(current_sid):
    """The fork parent is identified, but the executable differential against it was not run -> we hold the exit.
    Returns a reason STRING (or None). State-based (the PARENT-FORK field), not lexicon."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None                                  # no ledger / MODEL: N/A
    lt, mt, _rel = ctx
    if not mt or _i_matured_count(mt) < 3:
        return None                                  # immature model - we do not block early recon
    m = _PARENT_FORK_RE.search(lt)
    if not m:
        return None                                  # no field (non-canonical/old ledger) - anti-FP
    val = m.group(1).strip()
    if "{" in val or not val:
        return None                                  # an untouched placeholder
    if _FORK_NA_RE.search(val):
        return None                                  # explicitly declared "not a fork" - legitimately lifted
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    sess = os.path.dirname(ledger)
    if not _fork_diff_done(lt, sess):
        return ("the fork parent is identified (`PARENT-FORK: %s`), but the executable differential against it "
                "was not run - 'canonical / matches parent' = NOT a falsifier, but a trigger for fork-diff "
                "(`family_fork_diff` / invariant-test-on-fork). Run it and log "
                "`Fork-diff: DONE — <artifact>`, OR mark `PARENT-FORK: N/A — not a fork`"
                % val[:60])
    # Part 3 (contained in the fork-armed path): the diff was run, but on a claim >=5 the strongest thread must
    # carry an executable `observed:` - a static code match on a fork does not count as depth.
    claim = _max_depth(lt)
    if claim >= _T12_CLAIM_MIN:
        block = _trace_block(lt)
        # the body without the `DEPTH-TRACE` heading line (otherwise the word "trace" in the heading = a false exec match).
        body = "\n".join(block.splitlines()[1:]) if block else ""
        if block and "{" not in block and not _EXEC_ARTIFACT_RE.search(body):
            return ("claimed %d layers on a fork, but `observed:` in `DEPTH-TRACE` does not reference an "
                    "executable artifact (fork-run / test / log) - a static 'matches parent "
                    "file:line' on a fork does NOT count as depth (that is exactly where the fork deviation lives)"
                    % claim)
    return None


# --- EXECUTABLE-FLOOR on NON-forks (B2, audit 2026-08-09) -------------------------------------
# ROOT (a past audit): 21 T9 axes closed, ZERO fork-PoC/invariant tests - all depth-traces were
# static (scout returned ENFORCED -> closed). The FORK-DIFF mandate requires an executable artifact on a
# depth claim, but arms ONLY from `PARENT-FORK` (forks). On a NON-fork there was no analogue -> "scout
# CLEAN = recon-grade passed off as depth-grade" slipped through. The fix is a soft-nudge (not a hard-block: non-EVM/
# no-harness targets are possible): a mature model + >=threshold axes + 0 executable runs -> remind to
# run the strongest thread executably. Silent if executable already happened (targets with real PoCs/fuzz runs
# are NOT flagged - precise targeting of the past case). We harden to a block after measuring FP (like fork_undeclared).
EXEC_FLOOR_AXES = 5  # retune point: after N closed T9 axes with zero executable = a sign of under-digging
# WARNING Only STRONG signals of a REAL run - NOT bare mentions of tools (a past FP:
# a T11-VERDICT carried "forge/echidna unavailable, DEFERRED" -> a bare `\bechidna\b` falsely = executable-happened).
# A run is proven by: `[PASS]` (forge/foundry), `runs: N`/`N PASS` (fuzz output), T11-VERDICT explicitly DONE
# (not APPLICABLE/PENDING), Fork-diff DONE. Tool mentions in the text do NOT count.
_EXEC_RUN_LEDGER_RE = re.compile(
    r"\[\s*PASS\s*\]|\bruns:\s*\d|\b\d[\d×xX*]*\s*PASS\b|"
    r"T11-VERDICT:[^\n]*\bDONE\b|Fork-diff:[^\n]*\bDONE\b", re.I)
_EXEC_FILE_RE = re.compile(r"\.t\.sol$|^fork_diff|\.medusa\.sol$|fuzz.*\.(?:sol|rs)$", re.I)


def _has_executable_run(lt, sess_dir):
    """True if the hunt REALLY executed something: the ledger carries [PASS]/forge test/T11-DONE/Fork-diff DONE/
    echidna/medusa/trident/clarinet OR the session dir (or deep/) holds an executable artifact
    (*.t.sol / fork_diff* / *.medusa.sol / fuzz*.sol|.rs) OR there is a foundry `out/` (compilation happened).
    Fail-safe: doubt -> False (then the soft-nudge will remind - it is not a block)."""
    if _EXEC_RUN_LEDGER_RE.search(lt or ""):
        return True
    try:
        cands = list(os.listdir(sess_dir))
        if os.path.isdir(os.path.join(sess_dir, "out")):
            return True                              # foundry out/ = compilation/a run happened
        deep = os.path.join(sess_dir, "deep")
        if os.path.isdir(deep):
            cands += os.listdir(deep)
        if any(_EXEC_FILE_RE.search(f) for f in cands):
            return True
    except Exception:
        pass
    return False


def active_executable_floor_unrun(current_sid):
    """B2: a mature model + >=EXEC_FLOOR_AXES closed T9 axes + NOT a fork + ZERO executable runs ->
    return the axis count (for the reason). None otherwise. A fork is excluded (fork_diff_unrun/fork_undeclared already
    require an executable differential). fail-open. State-based (the T9-axes / PARENT-FORK fields / artifacts),
    not lexicon. A soft-nudge in main (pending_reminder), not a hard-block."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None                                  # no ledger / MODEL: N/A
    lt, mt, _rel = ctx
    if not mt or _i_matured_count(mt) < 3:
        return None                                  # immature model - we do not touch early recon
    axes = _t9_axes_used(lt)
    if axes < EXEC_FLOOR_AXES:
        return None                                  # few axes - too early to require the executable-floor
    pf = _PARENT_FORK_RE.search(lt)
    if pf and "{" not in pf.group(1) and pf.group(1).strip() and not _FORK_NA_RE.search(pf.group(1)):
        return None                                  # an identified fork -> the fork path governs (we do not duplicate)
    ledger, _root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    if _has_executable_run(lt, os.path.dirname(ledger)):
        return None                                  # executable already happened -> the floor is satisfied
    return axes


EXEC_FLOOR_REMINDER = (
    "⚙️ EXECUTABLE-FLOOR (audit-B2, soft - does NOT hold the exit). %d T9 axes closed, but ZERO "
    "executable runs - all depth-traces are STATIC (scout ENFORCED / reading the source). On a "
    "non-fork 'scout returned CLEAN' = recon-grade passed off as depth-grade (a past audit 2026-08-09: "
    "21 axes, 0 fork-PoC). Subtle bugs (rounding / interest-accrual edge / liquidation-dust / "
    "conservation under real state) are visible ONLY by execution, not by static analysis. BEFORE continuing "
    "breadth: bring up the Docker bbt and run executably >=1 STRONGEST thread (fork-PoC / invariant test / "
    "fuzz-harness). If executable is physically inapplicable (non-EVM without a harness) -> note this in the ledger EXPLICITLY, "
    "not silently (otherwise under-digging masquerades as exhaustion)."
)


# --- ZERO-D-NN escalation (B4, audit 2026-08-09, Mandate 0.9 enforcement) ----------------------
# ROOT (a past audit): the model is built (T10), but the `## Divergences` section produced ZERO `D-NN`
# over the WHOLE hunt - and `blind_spots.md` is untouched. Mandate 0.9: "zero D-NN = the detector did NOT fire, NOT
# the target is empty -> the metric NEVER ends the hunt, it ESCALATES the method (a silent generator -> a record
# in blind_spots.md)". That was prose - not enforced. Divergence-first = the headline of the whole FDE upgrade;
# if its main product (the model<->code divergence) is silent and this is swallowed - the backbone is off.
# A soft-nudge (method escalation, not an exit block): a mature model + >=threshold axes + 0 D-NN + blind_spots
# not mentioned -> remind to escalate the generator + write it down. Off as soon as blind_spots is mentioned.
ZERO_DNN_AXES = 3  # retune point: after N closed axes of a mature model with 0 D-NN = a silent generator
ZERO_DNN_ITER = 6  # OR: long on ONE axis (>=N iterations) with 0 D-NN = the same silent generator
ZERO_DNN_WAVES = 3  # OR (FEAT-F): a mature multi-wave model (>=N I-NN waves) with 0 D-NN = a silent generator
                   # (a past audit 2026-08-09: iter 8, T9-axes=0, an anomaly in a deposit accounting variable
                   #  was observed in the ledger but abandoned as a "seed", not raised to D-NN - the axes threshold skipped it)
_D_ANY_BULLET_RE = re.compile(r"^\s*[-*]\s*\*\*\s*D-\d", re.I)  # `- **D-01**` (any, incl. resolved)


_ITER_TRACE_BULLET_RE = re.compile(r"(?m)^\s*[-*]\s*(\d+)\s*[—–-]\s")  # `- 7 — <text>` in the Per-iteration trace


def _loopstate_iter(ledger_text):
    """Hunt progress = max(the `Iteration #: N` field, the number of per-iteration-trace entries). The agent often does
    NOT update the field (a case: field=1, but the trace reached 8) - trace bullets grow in fact, more reliable. 0 if
    neither exists."""
    txt = ledger_text or ""
    m = _LOOPSTATE_ITER_RE.search(txt)
    field = int(m.group(1)) if m else 0
    nums = [int(x) for x in _ITER_TRACE_BULLET_RE.findall(txt)]
    trace_max = max(nums) if nums else 0
    return max(field, trace_max)


def _dnn_total_count(model_text):
    """How many `D-NN` IN TOTAL in the model (open + resolved) - as a table (`| D-NN |`) OR a bullet
    (`- **D-NN**`). 0 = the divergence generator produced NOT ONE over the hunt (Mandate 0.9 is silent)."""
    n = 0
    for line in (model_text or "").splitlines():
        if _D_ROW_RE.match(line) or _D_ANY_BULLET_RE.match(line):
            n += 1
    return n


# R5 (SUD-MED-1, 2026-08-12): the B4 off-switch was lifted by ANY mention of "blind_spots" in
# ledger+model. But (a) system_model_template carried "blind_spots.md" in an instruction prose (line ~274) ->
# on an untouched model the gate was DEAD; (b) banking a random insight ("-> bank blind_spots/
# pattern-library") != escalating the METHOD. Mandate 0.9 steps 2+3 = "change the GENERATOR + write the silent one into
# blind_spots" - the off-switch now requires BOTH on one line IN THE LEDGER (not in model prose/template).
_BLINDSPOT_MARK_RE = re.compile(r"blind[-_\s]?spot", re.I)
_DNN_ESCALATION_RE = re.compile(
    r"model[-\s]?vs[-\s]?live|commodity[-\s]?subtraction|assumption[-\s]?mining|negative[-\s]?space|"
    r"fan[-\s]?in|смен\w*\s+генератор|switch\w*\s+generator|generator[-\s]?switch|"
    r"new\s+generator|другой\s+генератор|сменил\s+метод", re.I)


def active_zero_divergence_unescalated(current_sid):
    """B4: a mature model + >=ZERO_DNN_AXES closed T9 axes + ZERO D-NN over the hunt + the method NOT escalated
    -> return the axis count (for the reason). None otherwise. Off: immature / MODEL N/A / >=1 D-NN (the generator
    worked) / a REAL escalation record (blind-spot + generator switch on one line in the ledger,
    Mandate 0.9). fail-open, state-based. R5: the bare word "blind_spots" NO LONGER lifts it."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    if not mt or _i_matured_count(mt) < 3:
        return None                                  # immature model - too early
    axes = _t9_axes_used(lt)
    itr = _loopstate_iter(lt)
    # FEAT-F (2026-08-12): the third armed trigger - the number of MODEL WAVES. Covers "a rich multi-wave
    # model (>=3 I-NN waves), but T9-restart was not done (axes<3) and the hunt is short (itr<6), 0 D-NN" - maturity
    # by waves, not by axes/iterations. A wave = `## Invariants` (wave-1) + extra `## WAVE-*` sections.
    waves = 1 + len([k for k in _wave_i_counts(mt) if _WAVE_SECTION_RE.search(k)])
    if axes < ZERO_DNN_AXES and itr < ZERO_DNN_ITER and waves < ZERO_DNN_WAVES:
        return None                                  # few axes AND iterations AND waves - the generator is still working
    if _dnn_total_count(mt) > 0:
        return None                                  # >=1 D-NN -> the generator worked, not silent
    for line in (lt or "").splitlines():
        if _BLINDSPOT_MARK_RE.search(line) and _DNN_ESCALATION_RE.search(line):
            return None                              # a REAL escalation: blind-spot + generator switch (Mandate 0.9)
    return max(axes, itr, 1)                          # for the reason (axes OR iterations, whichever triggered)


ZERO_DNN_REMINDER = (
    "🔬 ZERO-D-NN (audit-B4, Mandate 0.9, soft - does NOT hold the exit). The model is built, but over %d axes/"
    "iterations the `## Divergences` section produced ZERO `D-NN` - the divergence-first generator (the HEADLINE of the whole "
    "upgrade) is SILENT. Mandate 0.9: zero D-NN = 'the detector did NOT fire', NOT 'the target is empty' -> the metric does NOT "
    "end the hunt, it ESCALATES the method (a past audit: 0 D-NN over 5 axes; another: iter 8 on one axis, an accounting "
    "anomaly was observed but abandoned as a 'seed'). NOW: (1) if you observed something UNEXPECTED "
    "(predicted!=observed / a strange value / !=) - raise it into a `D-NN` IMMEDIATELY, do NOT park it as "
    "seed/BB; (2) change the generator - model-vs-live-runtime (T12 fan-in) / commodity-subtraction / "
    "assumption-mining (NatSpec/docs 'should' without enforcement) / negative-space (un-modeled OUTSIDE the model); "
    "(3) write the silent generator into `sessions/_methodology/blind_spots.md`. Zero D-NN - an order to dig "
    "DIFFERENTLY, not a 'clean' signal."
)


# FORK-UNDECLARED nudge (2026-08-09): the fork-diff gate above arms ONLY from the handwritten
# field `PARENT-FORK`. A real fork target carried no field -> the flagship gate SILENT, although the ledger
# ITSELF declared 8x "canonical parent / byte-for-byte / fork of X" in kill proofs. This is exactly
# a "months-silent gate" (project rule): arming only from a self-written field = bypassed by not writing
# the field. Fix: if the ledger ITSELF declares a fork of a named parent, while the `PARENT-FORK` field is empty -
# we force filling it (then fork-diff is guaranteed to arm). A soft-nudge (n=1 + a semi-lexical
# signal): rides with LOOP_CONTINUE, not a hard-block; we harden to a block after 3-5 hunts with FP measurement.
# SUD-HIGH-2 + R3 (2026-08-12): _FORK_PARENTS was EVM-only -> fork-enforcement DARK on
# Solana/Cosmos/Move forks (a real case: a fork of a validator client). Added
# SPECIFIC fork implementations (not generic chain names like "solana"/"sui"/"cosmos" - those are ubiquitous -> FP:
# in every Solana hunt "solana"+"fork" occur by chance). The FP control is double: the parent AND the fork frame
# MUST be on ONE line + parent != target-slug.
_FORK_PARENTS = ("compound", "comptroller", "aave", "uniswap", "morpho", "curve", "balancer",
                 "makerdao", "yearn", "venus", "sushiswap", "pancakeswap", "trader joe", "sonne",
                 "cream", "solidly", "velodrome", "gmx",
                 # Solana validator/program forks (jito-solana, firebam):
                 "agave", "firedancer", "jito-solana", "solana-labs", "anza",
                 # Cosmos SDK/consensus forks:
                 "cosmos-sdk", "cometbft", "tendermint", "cosmwasm", "wasmd", "osmosis",
                 # Move framework forks (Sui/Aptos):
                 "aptos-core", "aptos-framework", "sui-framework", "move-stdlib")
_FORK_FRAME = ("canonical", "каноничн", "fork", "форк", "байт-в-байт", "byte-for-byte", "based on")


def active_fork_undeclared(current_sid):
    """The ledger ITSELF declares a fork of a named parent, but the `PARENT-FORK` field is not filled -> a nudge to
    fill it (otherwise the fork-diff gate silently does not arm). Returns the parent name (or None). Off:
    immature model / MODEL: N/A / the PARENT-FORK field already exists."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    if not mt or _i_matured_count(mt) < 3:
        return None
    pf = _PARENT_FORK_RE.search(lt)
    if pf and "{" not in pf.group(1) and pf.group(1).strip():
        return None                                  # the field is already filled -> the fork-diff gate governs
    # the target slug: a protocol is NOT a fork of itself (a past FP 2026-08-09: target `X`
    # in _FORK_PARENTS + "Fork-PoC accepted" in the scope line -> a false "fork of X"). A parent
    # equal to the target name is excluded.
    ledger, _root = freshest_active_ledger(current_sid)
    slug = os.path.basename(os.path.dirname(ledger)).lower() if ledger else ""
    # We cut out the PARENT-FORK/Fork-diff field BLOCKS (the field line + its indented continuation up to the next
    # `- **` field / `##` section): their template placeholder carries an EXAMPLE "Compound v2 - ..." which the
    # detector read as a hunter's declaration (a past FP; a nested `{...}` inside the placeholder
    # broke the naive regex cut `\{[^{}]*\}`). A filled PARENT-FORK does not get here (the off-switch above).
    _sk = False
    _scan_lines = []
    for _ln in lt.splitlines():
        _st = _ln.lstrip()
        if re.match(r"[-*]\s*\*\*\s*(PARENT-FORK|Fork-diff)\b", _st, re.I):
            _sk = True
            continue
        if _sk and (re.match(r"[-*]\s*\*\*", _st) or _st.startswith("#")):
            _sk = False                              # the next field / section began
        if not _sk:
            _scan_lines.append(_ln)
    scan = "\n".join(_scan_lines)
    # fork declaration: the line carries a named parent (!= target) AND fork/canonical framing.
    # "fork-poc" is cleaned out - it is a PoC method (Immunefi boilerplate), not a statement of a fork ancestor.
    for line in scan.splitlines():
        low = line.lower().replace("fork-poc", "").replace("fork poc", "")
        if not any(k in low for k in _FORK_FRAME):
            continue
        for p in _FORK_PARENTS:
            if p in low and p not in slug and slug not in p:
                return p
    return None


# OBS-8/OBS-9 (2026-07-28): per-subsystem model coverage. Wave 1 closed the model of ONE
# subsystem (12 `I-NN`) -> Active H-NN is empty -> the instance reached the "closed" boundary and stopped / went
# code-first on a new subsystem. No gate forced (a) the TRANSITION to the next model wave (OBS-8),
# nor (b) MODEL-FIRST on a new subsystem instead of code-first (OBS-9). `active_model_incomplete` looks
# at ONE `I-NN` list and is silent when it is BUILT and closed. The mechanism is the section
# `## Subsystem Model Coverage` in system_model.md: a list of in-scope subsystems x model status
# (`MODELED` / `unmodeled` / `N/A`). The limit <=12 `I-NN` is PER WAVE/subsystem, not global.
_COVERAGE_TITLE = "Subsystem Model Coverage"
_WAVE_NEXT_RE = re.compile(r"WAVE-NEXT\s*[:=]\s*\S", re.I)
_HNN_HEAD_RE = re.compile(r"^###\s+(H-\S.*)$")
_DEAD_TAG_RE = re.compile(r"\[\s*(KILLED|CONTESTED|PARKED)\b", re.I)  # tolerates `[CONTESTED/building-block]`
_ORIGIN_LINE_RE = re.compile(r"^\s*[-*]\s*\*\*origin", re.I)
_MODEL_BACKED_RE = re.compile(r"D-NN|D-C\d|D-\d|model-back", re.I)


def _coverage_rows(model_text):
    """[(subsystem, inscope_lower, model_STATUS, ref), ...] from ## Subsystem Model Coverage (or [])."""
    out = []
    for r in _section_rows(model_text, _COVERAGE_TITLE):
        c = _cells(r)
        if len(c) >= 3 and c[0] and not c[0].startswith("{"):
            out.append((c[0], c[1].lower(), c[2].upper(), c[3] if len(c) > 3 else ""))
    return out


def _active_hnn(ledger_text):
    """[[heading, origin_line, is_live], ...] for ### H-NN in the ## Active Hypotheses section."""
    txt = ledger_text or ""
    i = txt.find("## Active Hypotheses")
    if i < 0:
        return []
    j = txt.find("\n## ", i + 1)
    block = txt[i: j if j > 0 else len(txt)]
    out, cur = [], None
    for line in block.splitlines():
        m = _HNN_HEAD_RE.match(line)
        if m:
            if cur is not None:
                out.append(cur)
            head = m.group(1)
            live = not _DEAD_TAG_RE.search(head) and not head.strip().startswith("{")
            cur = [head, "", live]
        elif cur is not None and _ORIGIN_LINE_RE.match(line):
            cur[1] = line
    if cur is not None:
        out.append(cur)
    return out


WAVE_TRANSITION_REASON = (
    "WAVE-TRANSITION (OBS-8 + P8 T9-forcing, 2026-07-29). The model wave is CLOSED (all `I-NN` "
    "resolved) and Active H-NN is EMPTY, BUT `## Subsystem Model Coverage` holds >=1 in-scope "
    "subsystem/ASSET `unmodeled`: %s. This is NOT exhaustion - the end of ONE wave with uncovered axes "
    "('12 I-NN closed != the target is empty', the Hunt-Loop axiom). WARNING THE CORE IS ALL `ENFORCED` (all threads CONTESTED/"
    "OOS, no divergences) - this is NOT a reason to exit, but the STRONGEST signal to CHANGE AXIS/ASSET: the bug is not where "
    "you looked - restart T10 on a DIFFERENT asset/direction (a past case: gave up on 'the core is hard, "
    "all OOS, small max payout' without touching the governance contracts - the only remaining Critical-impact - and "
    "the freshest asset). The divergence-first ORDER on a new axis (STRICTLY): (1) T14 attention-gap if not "
    "run yet (it prioritises the ORDER of axes - a breadth pointer, one run per repo); (2) a NEW I-NN "
    "model wave FROM SCRATCH (T10, the model BEFORE the code; RULE 0: saw the code -> a cold agent) on the prioritised "
    "uncovered axis/asset, <=12 `I-NN` with `pred:` -> write + `MODELED` in Coverage; (3) ONLY THEN scout "
    "by the NEW invariants (reset Scout Status -> PENDING, Depth-Lead -> none yet); (4) depth on the new "
    "`D-NN`. Do NOT jump straight into code/fan-out on a new axis - the model FIRST. Either `MODEL: BUILDING` while "
    "you build; or `N/A — <reason>` if the axis is really outside the model (trusted/not deployed/out of scope - but "
    "governance with a Critical impact is NOT that). Lifted by a live Active H-NN, `MODEL: BUILDING`/"
    "`WAVE-NEXT:`, or by zeroing unmodeled-in-scope."
)

WAVE_CODEFIRST_REASON = (
    "MODEL-FIRST NUDGE (OBS-9, 2026-07-28). Active has a live H-NN with origin `code-read` "
    "WITHOUT model-backing (`D-NN`), while `## Subsystem Model Coverage` holds uncovered subsystems: %s. A smell of "
    "code-first on a new subsystem (a past lesson): reading-down catches single lines but misses the "
    "`SUBSTITUTED` class (a credit->raw-token substitution through the same generic mechanism - the model caught it, "
    "code-read did not). Build an I-NN model wave of the subsystem (the model BEFORE the code) -> enforcement -> `D-NN`; if "
    "the code-read H-NN is confirmed by an independent model - promote the origin to `D-NN` (un-dup by construction). "
    "Soft-nudge: not a block (T14-Path-B code-read leads are legit), but model-first is stronger."
)

CORE_ENFORCED_T9_REASON = (
    "T9-COLD-RESTART (P8-HARD, 2026-07-29). OBJECTIVE state: all built `I-NN` = "
    "`ENFORCED`, zero open `D-NN`, zero live Active H-NN - the core of THIS axis is exhausted CLEAN. This is "
    "NOT 'no bugs' (the axiom 'bugs are everywhere': a long-lived protocol - 4 years, tier-1 audits, a bug worth $billions), but a "
    "T9 trigger: the anchored frame must be BROKEN. Forced by FACT (not by the honesty of Coverage - closing "
    "Coverage with `N/A` and exiting will NOT work). NOW (mythos T9): (1) pick a NEW axis - a different ASSET / "
    "direction / class that the model has not touched yet (YOU set the AXIS, not a self-reset with the same view); "
    "(2) launch a COLD subagent (fresh context, SENIOR tier) on this axis with an order to build an "
    "INDEPENDENT I-NN model wave FROM SCRATCH (T10, the model BEFORE the code) - cold breaks the anchor that the main "
    "agent does not see; (3) mark the axis in `T9 restart axes used` of Loop State; (4) the new wave -> a fan-out over its "
    "invariants -> depth on the new `D-NN`. Axes already worked: %d. WARNING If this is the 3rd empty axis - "
    "SURFACE a short status to the operator (gap-map: which axes were passed, all ENFORCED) and CONTINUE to AXIS 4 (park "
    "does NOT exist, the exit is only T4 High/Crit or the operator's 'we're leaving'). A silent generator (0 `D-NN` on the "
    "axis) -> a record in `sessions/_methodology/blind_spots.md`: '0 divergences = the detector did not fire', NOT "
    "'the target is empty'."
)


def active_wave_transition_needed(current_sid):
    """OBS-8 (hard): a closed model wave + an empty live pool + uncovered in-scope subsystems."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    if mt is None:
        return None  # caught by active_model_incomplete
    cov = _coverage_rows(mt)
    unmodeled = [c[0] for c in cov if c[1].startswith("y") and c[2] == "UNMODELED"]
    if not unmodeled:
        return None  # all in-scope subsystems MODELED/N-A -> no transition needed
    live = [h for h in _active_hnn(lt) if h[2]]
    building = _model_building(lt) or bool(_WAVE_NEXT_RE.search(lt))
    i_rows = _i_rows(mt)
    all_resolved = bool(i_rows) and all(_status_of(r) in _VALID_STATUS for r in i_rows)
    if all_resolved and not live and not building:
        return WAVE_TRANSITION_REASON % ", ".join(unmodeled[:6])
    return None


# P8-HARD (T9 cold-restart forcing, 2026-07-29). wave_transition (OBS-8) relies on the HONESTY of
# Coverage: the agent may NOT write the uncovered axis / close everything with `N/A` and exit on "the core is hard". This
# gate looks at the OBJECTIVE state of the model, not Coverage: all built `I-NN` = `ENFORCED`
# (zero divergence candidates) + zero open `D-NN` + zero live Active H-NN = the core of THIS axis is
# exhausted clean. This is NOT "no bugs" (the axiom "bugs are everywhere"), but a T9 signal: a cold subagent on a NEW
# axis/asset. Forced regardless of whether the agent admitted axes in Coverage -> gaming Coverage does not save it.
_T9_AXES_RE = re.compile(r"(?im)^[^\n]*\*\*\s*T9[^\n]*axes[^\n]*$")


def _t9_axes_used(ledger_text):
    """How many T9 axes are already worked (from the `T9 restart axes used:` field of Loop State). A `{...}` placeholder
    and a bare `0` -> 0. We count the listed axes (by commas) OR an explicit number."""
    m = _T9_AXES_RE.search(ledger_text or "")
    if not m:
        return 0
    line = m.group(0)
    if "{" in line:
        return 0                                     # an unfilled template placeholder
    tail = line.split(":", 1)[-1] if ":" in line else line
    tail = re.sub(r"\*+", "", tail).strip()
    if not tail or tail.lower().startswith("0"):
        return 0
    # "axis1, axis2" -> 2; otherwise the first number on the line
    if "," in tail:
        return len([p for p in tail.split(",") if p.strip()])
    mnum = re.search(r"\b([1-9])\b", tail)
    return int(mnum.group(1)) if mnum else (1 if tail else 0)


def active_core_enforced_needs_t9(current_sid):
    """P8-HARD: all `I-NN` ENFORCED + 0 open `D-NN` + 0 live Active H-NN -> the axis core is exhausted ->
    force a T9 cold-restart on a NEW axis. Returns a reason string (or None). Coverage-independent."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None                                  # MODEL: N/A - lifted
    lt, mt, rel = ctx
    if _model_building(lt):
        return None
    rows = _i_rows(mt)
    statused = [r for r in rows if _status_of(r) in _VALID_STATUS]
    if len(statused) < 3:
        return None                                  # the model is thin/without statuses -> model_incomplete catches
    if not all(_status_of(r) == "ENFORCED" for r in statused):
        return None                                  # there is PARTIAL/ABSENT/SUBSTITUTED -> this is D-NN work, not T9
    # zero OPEN divergences (an open D-NN = divergence_unresolved forces it, not T9)
    for line in (mt or "").splitlines():
        if _D_ROW_RE.match(line):
            c = _cells(line)
            if not _DIV_RESOLVED_RE.search(c[-1] if c else ""):
                return None
    # zero live Active H-NN (a live hypothesis = not exhausted, single-pick drives it)
    if [h for h in _active_hnn(lt) if h[2]]:
        return None
    axes = _t9_axes_used(lt)
    return CORE_ENFORCED_T9_REASON % axes


# ─── MODEL MULTI-WAVE (aevo 2026-07-29) ──────────────────────────────────────────────────────
# ROOT: T10 builds the model with ONE wave of I-NN (usually single-function correctness - "what does the
# function do"). When it is exhausted without a live D-NN and the vertical threads went OOS, the agent treats this
# as "the model is built, no bugs" - instead of "ONE AXIS of invariants is exhausted -> build the next on a
# DIFFERENT axis". A past case is direct proof: wave 1 (I-01..09) = zero D-NN, a wave 2 forced by the operator
# (cross-connector isolation) instantly produced a HIGH D-02 in the in-scope Vault. This is BREADTH!=DEPTH at
# the model level: one I-NN wave != exhaustion of the model. Build as many waves as needed (operator 2026-07-29:
# "even 100, until you find it"); an empty wave = a trigger of a new axis, NOT an exit. Escalation: axes-incomplete
# (cheap, inside the model) BEFORE core_enforced_needs_t9 (cold-restart, expensive) - do not jump into T9 until the
# invariant axes are passed.
_INV_AXES = [
    ("cross-function (the joint of two functions)",
     re.compile(r"cross-?function|cross-?func|стык\s+функ|между\s+(двумя\s+)?функц", re.I)),
    ("order-dependent / sequence (a sequence of calls)",
     re.compile(r"order-?depend|последовательност\w*\s+вызов|call[\s-]*sequence|\bsequence\b"
                r"|reentran|повторн\w+\s+вызов|двойн\w+\s+(вызов|consume)", re.I)),
    ("temporal (per-block / checkpoint / time)",
     re.compile(r"temporal|per-?block|checkpoint|time-?depend|во\s+времени|в\s+одном\s+блоке"
                r"|same[\s-]*block", re.I)),
    ("cross-subsystem / isolation (resource isolation between instances)",
     re.compile(r"cross-?connector|cross-?subsystem|isolation|изоляц|per-?connector"
                r"|между\s+(connector|инстанс|подсистем|компонент)", re.I)),
    ("economic-sequence (a risk-free cycle / no-free-money)",
     re.compile(r"economic-?sequence|цикл\s+без\s+риск|no[\s-]*free|безрисков|arbitrage"
                r"|атака\s+дешевле|profitable\s+loop", re.I)),
]

# WEB profiles: the invariant axes differ from the contract ones (2026-08-05). active_model_axes_incomplete
# picks a set by the namespace of the model's predominant invariants: `I-` -> contract; `TB-` -> dapphunt trust-axes;
# `AC-` -> web2 access-axes. A web invariant catches the same axis by its class word.
_INV_AXES_DAPPHUNT = [
    ("origin-trust (who embeds/postMessage/CORS)", re.compile(r"origin-?trust|postmessage|iframe|frame-?ancestor|cors|redirect_uri", re.I)),
    ("signature-integrity (shown==signed)", re.compile(r"signature-?integrity|eip-?712|typed-?data|displayed?.{0,12}sign|permit", re.I)),
    ("data-source-trust (RPC/indexer/tokenlist)", re.compile(r"data-?source|rpc|indexer|tokenlist|subgraph", re.I)),
    ("session-auth (nonce/replay/SIWE/initData)", re.compile(r"session-?auth|siwe|siws|nonce|initdata|replay", re.I)),
    ("asset-identity (decimals/chainId/token)", re.compile(r"asset-?identity|decimals|chainid|token\s*identity|ens", re.I)),
    ("clone-parity (clones/deploys are protected equally)", re.compile(r"clone-?parity|staging|deploy.{0,10}diff|multi-?chain", re.I)),
]
_INV_AXES_WEB2 = [
    ("object-authz / BOLA (ownership on an endpoint)", re.compile(r"object-?authz|bola|idor|ownership", re.I)),
    ("function-authz / BFLA (a role on a privileged function)", re.compile(r"function-?authz|bfla|role|privileg|admin.{0,10}func", re.I)),
    ("auth-integrity (session/JWT/OAuth/reset)", re.compile(r"auth-?integrity|jwt|oauth|session|reset-?token", re.I)),
    ("tenant-isolation (org/workspace)", re.compile(r"tenant|workspace|multi-?tenant|org.{0,6}isolation", re.I)),
    ("input-sink (SQL/SSTI/cmd/SSRF)", re.compile(r"input-?sink|sqli|ssti|ssrf|injection|command-?inj", re.I)),
    ("business-logic (race/payment/workflow)", re.compile(r"business-?logic|race|payment-?bypass|workflow-?skip|quantity", re.I)),
]


# P2-finalfix (bullet-namespace class): _model_namespace counted ONLY a pipe table,
# while _i_rows/_model_has_real_invariant/_I_BULLET_RE(_HDR_RE) nearby already recognise the bullet form
# `- **TB-I01** ...` (agents drift into bullets - P10). A web model in bullets -> namespace="" -> contract axes
# -> a false active_model_axes_incomplete on dapphunt/web2. We mirror the same bullet pattern.
_TB_BULLET_RE = re.compile(r"^\s*[-*]\s*\*\*\s*TB-I", re.I)
_AC_BULLET_RE = re.compile(r"^\s*[-*]\s*\*\*\s*AC-I", re.I)


def _model_namespace(model_text):
    """The predominant invariant namespace: 'TB' / 'AC' / '' (contract). Counts I-NN table rows
    AND the bullet form `- **TB-I01**` / `- **AC-I01**`."""
    tb = ac = 0
    for line in (model_text or "").splitlines():
        s = line.strip()
        if s.startswith("| TB-I") or s.startswith("|TB-I") or _TB_BULLET_RE.match(line):
            tb += 1
        elif s.startswith("| AC-I") or s.startswith("|AC-I") or _AC_BULLET_RE.match(line):
            ac += 1
    if tb and tb >= ac:
        return "TB"
    if ac:
        return "AC"
    return ""


def _axes_for_model(model_text):
    """The axis set by the model namespace: TB->dapphunt, AC->web2, otherwise contract."""
    ns = _model_namespace(model_text)
    if ns == "TB":
        return _INV_AXES_DAPPHUNT
    if ns == "AC":
        return _INV_AXES_WEB2
    return _INV_AXES


MODEL_AXES_REASON = (
    "MODEL MULTI-WAVE GATE (2026-07-29). The model %s is built and there are no open live `D-NN` - but this is "
    "the exhaustion of ONE AXIS of invariants (usually single-function correctness 'what does the function do'), NOT of the "
    "model. Different axes express DIFFERENT classes of bugs; cross-function / order-dependent / temporal / "
    "isolation / economic-sequence invariants a single-function wave STRUCTURALLY does not express. PROVEN in "
    "a past hunt: wave 1 (I-01..09, vertical flows) = zero D-NN 'clean', threads went to OOS at depth 2-3 -> "
    "the agent got stuck; a forced wave 2 (cross-connector isolation - the HORIZONTAL between connectors) "
    "instantly produced a HIGH D-02 in the in-scope Vault (a global balance, per-connector limits). An empty wave = "
    "a signal of a NEW axis, NOT 'no bugs' (build as many waves as needed until you find it - operator 2026-07-29). "
    "NOW: build the NEXT I-NN wave on an UNCOVERED axis (in `system_model.md`, a new section `WAVE-N`). "
    "🔴 PURITY GUARD (otherwise T10 degrades): formulate the axis invariant FROM THE SPEC/PURPOSE ('what must the system "
    "GUARANTEE on axis <X>?') BEFORE re-entering the implementation - `pred:` BEFORE the code, THEN "
    "enforcement. The wave-1 model has already read the code - do not rediscover bugs from the code, otherwise `D-NN` degenerates "
    "into 'code vs code' instead of 'independent model vs code' and loses its divergence power. Uncovered axes: %s. For "
    "EACH - either wave invariants, or "
    "a deliberate `<axis>: N/A — <reason>` (like the scout's OPTIONAL menu). A thread stuck on OOS at depth "
    "2-3 = change the AXIS (the horizontal between components vs the vertical of one flow), NOT a dead end. order-dependent "
    "axes = the T11 input (`t11_applicable.py`). Only when ALL axes are covered with zero D-NN - escalation to T9 "
    "cold-restart. Declared the next wave -> write `WAVE-NEXT: <axis>` in the ledger (lifts the gate while "
    "it is being built)."
)

AXES_WAVES_REASON = (
    "AXES-WITHOUT-WAVES (2026-07-30 - an enforcement hole 'changing the axis WITHOUT a new I-NN "
    "wave'). Loop State declares `T9 restart axes used: %d`, but `%s` has only %d extra `## WAVE-*` "
    "waves with `I-NN` built (+%d axes marked `N/A`) - FEWER than the number of declared axes. This is EXACTLY the "
    "multi-wave FAIL seen on two real hunts: you changed the axis (T9 / a new direction) and "
    "drove new `H-NN`, WITHOUT seeding an invariant wave for it. The model froze on wave 1, the axes are hunted "
    "code-first -> a miss of the `SUBSTITUTED`/`ABSENT` class (un-dup lives in the ABSENCE of a check, visible only "
    "to one who KNEW the invariant IN ADVANCE - T10 step 6; a cross-connector D-02 surfaced ONLY via a forced wave 2). "
    "NOW for EACH declared axis without a wave: (1) build `## WAVE-N (<axis>)` in system_model.md - <=12 "
    "`I-NN` FROM THE SPEC/PURPOSE of the axis (cross-function / order-dependent / temporal / cross-subsystem-isolation "
    "/ economic-sequence), each `check:`/`component:`/`pred:` BEFORE re-reading the code (RULE 0: saw the code -> "
    "a cold agent builds the wave, otherwise `D-NN` degenerates into 'code vs code'); OR an explicit line `<axis>: N/A — "
    "<reason>` if the axis is really outside the model. (2) THEN the fan-out - **HYBRID Scout Fan-Out** "
    "(`divergence_fanout.workflow.js`) over the new `I-NN`, NOT the CLASSIC manual `scout_fanout`. (3) depth on the "
    "new `D-NN`. Lifted when extra waves + `N/A` axes >= declared, or `MODEL: BUILDING` / "
    "`WAVE-NEXT:` while you build."
)

T11_UNDECIDED_REASON = (
    "T11-UNDECIDED (2026-07-30 - 'harness-as-generator was never applied in 4 hunts'). "
    "The model is mature (`%s`), but the ledger has NO `T11-VERDICT:` verdict - phase J2 (fuzzer-generator) was silently "
    "skipped. Measured: the `t11_applicable.py` detector on real session targets returned **APPLICABLE** "
    "(invariant-heavy stateful + build), while the instances went past it because nothing blocked the skip. "
    "T11 = a fuzzer as a GENERATOR of divergences (looks for a SEQUENCE that breaks an order-dependent `I-NN`, "
    "which reading cannot catch) - a machine source of `D-NN`, complementary to manual T10. NOW: run "
    "`py -3 -X utf8 scripts/_methodology/t11_applicable.py <target> --model "
    "sessions/<slug>/system_model.md` and WRITE into the ledger a line `T11-VERDICT: <APPLICABLE|MAYBE|SKIP|N/A>` "
    "(+reason). `APPLICABLE` -> build a harness from order-dependent `I-NN` (fizz/Echidna for EVM · Trident for "
    "Solana, `scripts/web3/hypothesis/harness_from_invariant.md`), run BEFORE the hypothesis. `SKIP — <no "
    "build / stateless parser = T8, not T11>` = a legitimate pass (the gate does not force the fuzzing itself, only a conscious "
    "decision). A `{...}` placeholder does not count as a verdict."
)

ATTENTION_GAP_REASON = (
    "ATTENTION-GAP-SKIPPED (2026-07-30 - T14 is built, but 0 artifacts in 4 hunts). The model is mature, "
    "there are no open live `D-NN` (you are about to conclude the axis 'with nothing'), but `## Attention Gaps` in `%s` is empty and not "
    "marked `N/A`. T14 is the SECOND independent source of PLACE (after `D-NN`): where the auditor did NOT look "
    "(an inversion of the audit map, `audit_coverage_invert.py`) + where the author did NOT look (traces of haste in git, "
    "`commit_archaeology.py`). An intersection with `D-NN` = maximum priority. Concluding 'nothing there' without "
    "running T14 = searching in the same place as the crowd. NOW: either run `py -3 -X utf8 "
    "scripts/_methodology/audit_coverage_invert.py` + `commit_archaeology.py` (the FULL "
    "history is needed, not `--depth 1`) and enter the findings in `## Attention Gaps` (place · source · "
    "intersection with `D-NN`); or `Attention Gaps: N/A — <no audits / shallow git / nothing to invert>` "
    "as an explicit line. An open live `D-NN` lifts the gate (drive it - T14 will wait)."
)

UNDUP_SWEEP_REASON = (
    "UN-DUP SWEEP INCOMPLETE (Plan 6, S50.1/S51). `## Un-Dup Sweep` in the ledger carries generators applicable by "
    "profile WITHOUT a status: %s. The crowd finds duplicates exactly where the source of PLACE was not "
    "run systematically (S54 - un-dup = an enforced layer of the loop, not 'remember to apply'). For EACH "
    "write either `RUN` (run -> the lead is recorded in the Scout table/Active above), or `N/A — <reason>` "
    "(not applicable ON THIS target - already set profile `N/A — web-only` need not be touched), "
    "or `-> D-NN <id>` (produced a divergence in `system_model.md`). Fill the lines - the gate will release the hold."
)

# Task 2 (Plan 6, S43.1/S50/S51): the threshold ">=N boundaries" is not named as a number in the design - a constant with
# a default of 3 (the same threshold as `_i_matured_count(mt) >= 3` of the maturity family), tune at review.
COMPOSITION_MIN_BOUNDARIES = 3

COMPOSITION_REASON = (
    "COMPOSITION PASS SKIPPED (Plan 6, S43.1/S50 - the main un-dup generator: cross-thread synthesis "
    "web instance). The model `%s` is mature (`_i_matured_count>=3`) and carries >=%d trust boundaries (`I-NN`/`TB-NN`/"
    "`AC-NN` rows with non-empty `Source`+`component:`), but `composition_map.md` co-located with the ledger "
    "is absent/empty. The composition graph catches seams that NO single-I-NN status expresses: "
    "the output of one boundary = the input of another, and 'who validates at the seam?' is a question the crowd also does not "
    "ask systematically (un-dup by construction). NOW: run `py -3 -X utf8 "
    "scripts/web2/composition_map.py --model <system_model.md> --session-dir "
    "<dirname(ledger)>` - edges without a validator (Status != ENFORCED), not yet entered into `## Divergences`, "
    "will come out as `D-NN` candidates with `undup_origin: composition-seam`. Enter the real findings into the model."
)

# Task 3 (Plan 6, S48.2/S44/S50.3): undup_origin - the SECOND-TO-LAST cell of a D-NN row (`c[-2]`),
# inserted BEFORE the `Resolution` (`c[-1]`) in system_model_web_template.md/system_model_template.md.
# `single-boundary-obvious` is matched ENTIRELY FROM THE START of the line (not a substring) - it does not accidentally catch
# compound values like "composition-seam; severity_undup: single-boundary-obvious does not fit".
_UNDUP_ORIGIN_WEAK_RE = re.compile(r"^single-boundary-obvious\b", re.I)
# 2026-08-09 audits: strong origin tokens (S48.2). A whole-line scan = format-robust
# (a pipe with any column layout + a bullet D-NN); the same class of fix as `_status_of` - the gate must
# not go blind on a natural format. `guard-asymmetry-seam` added by A3 (scout constraint-mismatch).
_UNDUP_ORIGIN_STRONG_RE = re.compile(
    r"\b(composition-seam|docs-runtime-gap|ui-hidden|commodity-cold|assumption-gap|"
    r"negative-space|interrupted-path|third-party-seam|guard-asymmetry-seam)\b", re.I)


def _undup_origin_missing_rows(model_text):
    """D-NN rows (a `| D-NN | ... |` table) whose `undup_origin` (`c[-2]`, the second-to-last cell -
    positional-hazard R5: the column is ALWAYS BEFORE the Resolution `c[-1]`, robust to any future insertion
    of columns to the LEFT of it, the same pattern that `_has_open_divergence`/`active_divergence_unresolved`
    use for `c[-1]`) is empty / `{TODO}` / only `single-boundary-obvious` (an admission of a duplicate,
    not a source of PLACE). Returns a list of IDs (the first cell), or []. The bullet form of D-NN (`_D_BULLET_RE`)
    is NOT covered - undup_origin has no positional anchor there (the same boundary as for the other D-NN columns:
    the table is a machine-readable contract, a bullet is prose outside the gate)."""
    out = []
    for line in (model_text or "").splitlines():
        is_pipe = bool(_D_ROW_RE.match(line))
        is_bullet = bool(_D_BULLET_RE.match(line))
        if not (is_pipe or is_bullet):
            continue
        # Plan 6 fix1: a killed divergence (Resolution = `KILLED file:line`/archive) will not go to submit ->
        # it needs no origin, and the gate stands BEFORE active_core_enforced_needs_t9, so a dead row
        # would block the path to T9. We flag only LIVE ones (open OR `-> H-NN`-driven).
        if is_pipe:
            c = _cells(line)
            if len(c) < 3:
                continue                          # no room for undup_origin apart from the ID/Resolution
            if _KILLED_LEAD_RE.search(c[-1]):
                continue
            did = c[0]
        else:                                     # bullet D-NN (`- **D-NN — ...`, a bullet class)
            if _KILLED_LEAD_RE.search(line):
                continue
            mid = re.search(r"D-\d+", line)
            did = mid.group(0) if mid else line.strip()[:16]
        # 2026-08-09: origin present = a strong origin token ANYWHERE in the line
        # (whole-line, format-robust to the pipe column layout AND to a bullet - the earlier `c[-2]` logic
        # went blind: a pipe without an origin column -> c[-2] landed in a foreign cell = a false "present";
        # bullets were not covered at all). `single-boundary-obvious` without a strong one = weak -> we flag.
        if _UNDUP_ORIGIN_STRONG_RE.search(line):
            continue
        out.append(did)
    return out


def active_undup_origin_missing(current_sid):
    """Task 3: a mature model (`_i_matured_count(mt) >= 3`) carries a `D-NN` without a filled/strong
    `undup_origin` - likely-dup, the source of PLACE (S48.2 "why did 100 hunters miss this?") is not
    named. Soft-nudge: `is_giveup=False` (satisfiable fill-or-strengthen; STILL holds the turn -
    "soft" here means "not giveup-hard", NOT "releases"). The off-switch is the same signal as for
    `active_attention_gap_skipped`/`active_undup_sweep_incomplete`: `_model_ctx` (None on
    `MODEL: N/A`) + `_i_matured_count(mt) >= 3` (anti-FP on the first scout pass/a trivial target).
    Applies to LIVE D-NN rows - open AND `-> H-NN`-driven (Plan 6 fix1: killed `KILLED`/archive
    are excluded - they will not go to submit, no origin needed, and the gate stands BEFORE active_core_enforced_needs_t9).
    undup_origin is a separate axis from the resolution: important also for those already taken into DRIVE `-> H-NN` (Task 4 T4-verifier
    requires it, empty/weak -> downgrade likely-dup). Namespace-agnostic (the D-NN table is one form in
    all profiles: web/contract).
    Returns "rel: D-01, D-02, ..." or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    _lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None                               # the first scout pass - the model is still being built
    missing = _undup_origin_missing_rows(mt)
    if not missing:
        return None
    return "%s: undup_origin is not filled/weak - %s" % (rel, ", ".join(missing[:8]))


UNDUP_ORIGIN_REASON = (
    "UNDUP-ORIGIN MISSING (Plan 6, S48.2/S44/S50.3). %s. undup_origin answers the adversarial "
    "question 'why did 100 hunters miss this?' - an empty/`{TODO}`/`single-boundary-obvious` cell "
    "= the source of PLACE is not named, the finding is indistinguishable from what the crowd already found (likely-dup). Write "
    "into the second-to-last cell of the row (BEFORE Resolution) a concrete source: `composition-seam` / "
    "`docs-runtime-gap` / `ui-hidden` / `commodity-cold` / `assumption-gap` / `negative-space` / "
    "`interrupted-path` / `third-party-seam` - `single-boundary-obvious` is also an acceptable ADMISSION of a "
    "duplicate (comes with a low rank multiplier, see the formula prose in `system_model_*_template.md`), "
    "but not a stronger source."
)


def active_model_axes_incomplete(current_sid):
    """2026-07-29: the model is built, there are no open live `D-NN`, but the axes cross-function / order /
    temporal / isolation / economic are NOT covered -> one axis is exhausted, not the model. Force the next axis
    (waves are unlimited). Returns (rel, missing_axes[]) or None. Coverage-independent."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None                                  # MODEL: N/A - lifted
    lt, mt, rel = ctx
    if _model_building(lt) or _WAVE_NEXT_RE.search(lt or ""):
        return None                                  # the agent already declared the next wave -> in progress
    if _i_matured_count(mt) < 3:
        return None                                  # the model is thin -> model_incomplete catches
    # an open live D-NN (not "-> H-NN" / not "KILLED"), a table OR a bullet -> drive it, we do not force axes
    if _has_open_divergence(mt):
        return None
    # exclude the template INSTRUCTIONS before searching for markers: block quotes (`>`) and unfilled
    # placeholders (`{TODO}` / `{...}`) - otherwise the axis marker words in the template itself falsely "cover"
    # the axes and the detector goes blind on a fresh model (template<->detector, the template_sentinel class).
    body = "\n".join(l for l in (mt or "").splitlines()
                     if not l.lstrip().startswith(">") and "{" not in l)
    missing = [name for name, rx in _axes_for_model(mt) if not rx.search(body)]
    if len(missing) <= 1:                            # >=4/5 axes covered -> the axes are passed, let T9 take it
        return None
    return (rel, missing)


# -- OBS-10 (2026-07-30): "changing the axis WITHOUT a new I-NN wave" ---------------------------------
# Both instances declared `T9 restart axes used: 3` in Loop State, but the model stayed on wave 1 and they drove
# new axes with bare H-NN. active_model_axes_incomplete matches axis NAMES in the model PROSE (fragile: the word
# "temporal" in the text falsely "covers" an axis) and is silent while the agent is "in flight". This gate is a COUNTING
# invariant, not a marker: how many axes are DECLARED (the ledger counter) vs how many waves are BUILT (the model). Each
# declared T9 axis must have EITHER a `## WAVE-N` section with `I-NN`, OR an explicit `N/A` mark.
_T9_AXES_USED_RE = re.compile(r"T9\s*restart\s*axes\s*used:?\**\s*(\d+)", re.I)
_WAVE_SECTION_RE = re.compile(r"wave", re.I)
# 2026-08-18: the floor by STATE, NOT by phrase (operator: "you cannot put all the words in the base").
# The `T9 restart axes used` counter could remain a template, but the field `Current pick` / `Depth-Lead`
# (the authoritative "what I am doing now") names the CURRENT axis: `-> pivot to Axis-2`, `AXIS-2 pivot` /
# `reset to axis-2` / a Russian-language "pivot -> axis-2". The verb/order/language do not matter - we key on the identifier
# `axis-N` in the current-state field. floor = max_index - 1 (Axis-1 = the original, N>=2 = a restart axis ->
# the restart count, the semantics of `T9 restart axes used`). Scope of 2 fields -> no Axis-Queue/RULES noise. A target that writes
# `AX-NN` (not `axis`) is not caught, its counter (17) leads.
_CURRENT_AXIS_FIELD_RE = re.compile(r"(?im)^.*(?:current\s+pick|depth[\s\-]?lead)\b.*$")
_AXIS_IDX_RE = re.compile(r"\baxis[\s\-]?(\d+)", re.I)
# P2-finalfix (web N/A axis): the second alternation carried ONLY contract axis words -> a web hunt
# that marked a trust/access axis `N/A` (`clone-parity: N/A — single deploy`) was not counted ->
# a false active_axes_without_waves Stop block. Web axis words added (dapphunt TB- + web2 AC-),
# contract words left as they were.
_NA_AXIS_RE = re.compile(
    r"(?im)^(?=.*(?:\bn/?a\b|не\s*примен|out[\s-]*of[\s-]*scope))"
    r"(?=.*(?:cross-function|cross-subsystem|order|sequence|temporal|isolation|economic"
    r"|origin-?trust|signature-?integrity|data-?source|session-?auth|asset-?identity|clone-?parity"
    r"|object-?authz|function-?authz|auth-?integrity|tenant|input-?sink|business-?logic)).*$"
)


def _t9_axes_declared(ledger_text):
    """The max number of T9 axes: max(the prose counter of Loop State `T9 restart axes used: N`, the number of
    CLOSED axis-like atoms in `## Atom Registry`, a floor by an EXPLICIT pivot declaration `pivot to Axis-N` /
    `AXIS-N =`). An unfilled template ('{0-3+ ...}' - with a `{`) and struck-through ('~~ ...~~') are ignored.
    N-1 (2026-08-12): previously it hung ONLY on the prose counter -> the agent under-declared
    it (1 with 6 closed axis atoms) and muted BOTH re-arm gates. The registry = the machine truth of the axis count.
    2026-08-18, operator: the counter `T9 restart axes used` was left as a TEMPLATE `{...}`, but the hunter
    EXPLICITLY pivoted (`pivot to Axis-2 Scheduled Transactions`) and drove cold scouts WITHOUT a wave -> n=0 muted
    axes_without_waves (per-wave model-first blindness, "after wave-1 it slid"). A floor by the pivot declaration
    catches this, WITHOUT touching hunts with a filled counter (max: 17/6 are already >= pivot-idx). A ranked Axis-Queue
    (`1) ... 2) ...`) is NOT caught - the prefix `Axis`/`AXIS` right next to the digit is needed."""
    n = 0
    for l in (ledger_text or "").splitlines():
        if "{" in l or "~~" in l:                    # placeholder / struck-through-superseded (~~...~~)
            continue
        m = _T9_AXES_USED_RE.search(l)
        if m:
            try:
                n = max(n, int(m.group(1)))
            except ValueError:
                pass
    rows = _atom_rows(ledger_text)                   # N-1: a floor by the registry's real CLOSED axes
    if rows:
        closed_ax = sum(1 for a in rows if a.get("status") == "CLOSED"
                        and (a.get("type") or "").strip().lower() in _AXIS_LIKE_TYPES)
        n = max(n, closed_ax)
    max_axis = 0                                     # the current axis from Current pick / Depth-Lead
    for line in _CURRENT_AXIS_FIELD_RE.findall(ledger_text or ""):
        if "{" in line:                              # an unfilled template field - skip
            continue
        for am in _AXIS_IDX_RE.finditer(line):
            try:
                max_axis = max(max_axis, int(am.group(1)))
            except ValueError:
                pass
    if max_axis >= 2:                                # N>=2 = a restart axis; floor = N-1 (the restart count)
        n = max(n, max_axis - 1)
    return n


def _pivot_axis_demand(ledger_text):
    """The demand of active_axes_without_waves WITHOUT the bulk closed-registry (2026-08-19 measurement): only
    the prose counter `T9 restart axes used: N` (filled, a genuine declaration) + the pivot declaration
    `Current pick/Depth-Lead: axis-N`. Does NOT count ALL closed axis atoms: on a mature hunt there are 62 of them,
    most are ordinary SELECT-picks (not a T9 restart), and the demand "a WAVE section for EVERY closed axis" =
    unsatisfiable (18 waves < 62 -> required +44). The cumulative "closed-without-a-wave" catch (anti-under-declaration)
    was moved to model_first_nudge - that one catches scout-first on a new axis PREVENTIVELY at the
    Agent boundary, not after the fact. The gate remains valuable as CURRENT-STATE (pivoted to axis-N without a wave).
    Returns N (0 if neither a counter nor a pivot). `_t9_axes_declared` (with the closed-count) is NOT touched - it is used by
    the fan-out floor + active_t9_count_untracked."""
    n = 0
    for l in (ledger_text or "").splitlines():
        if "{" in l or "~~" in l:                    # placeholder / struck-through-superseded
            continue
        m = _T9_AXES_USED_RE.search(l)
        if m:
            try:
                n = max(n, int(m.group(1)))
            except ValueError:
                pass
    max_axis = 0                                     # the pivot declaration: Current pick / Depth-Lead: axis-N
    for line in _CURRENT_AXIS_FIELD_RE.findall(ledger_text or ""):
        if "{" in line:
            continue
        for am in _AXIS_IDX_RE.finditer(line):
            try:
                max_axis = max(max_axis, int(am.group(1)))
            except ValueError:
                pass
    if max_axis >= 2:                                # N>=2 = a restart axis; floor = N-1 (the restart count)
        n = max(n, max_axis - 1)
    return n


def active_axes_without_waves(current_sid):
    """OBS-10: Loop State declares `T9 restart axes used: N` (N>=1), but the extra `## WAVE-*` waves with `I-NN`
    plus explicit `N/A` axes in the model < N -> an axis change without a new invariant wave. Counting, not a marker
    in prose (unlike active_model_axes_incomplete). Returns (rel, N, extra_waves, na) or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None                                  # MODEL: N/A - lifted
    lt, mt, rel = ctx
    if mt is None:
        return None                                  # caught by active_model_incomplete
    if _model_building(lt) or _WAVE_NEXT_RE.search(lt or ""):
        return None                                  # the agent is building the next wave -> in progress
    if _i_matured_count(mt) < 3:
        return None                                  # a thin model -> model_incomplete catches
    n = _pivot_axis_demand(lt)                       # 2026-08-19: current-pivot + prose counter,
    if n < 1:                                        # WITHOUT the bulk closed-registry (otherwise 62 -> an unsatisfiable demand)
        return None                                  # no axes declared (neither pivot nor counter, or only the template)
    extra_waves = len([k for k in _wave_i_counts(mt) if _WAVE_SECTION_RE.search(k)])
    na = len(_NA_AXIS_RE.findall(mt or ""))
    if extra_waves + na < n:
        return (rel, n, extra_waves, na)
    return None


# -- active_t9_count_untracked (2026-08-13, operator: "forgot I-NN on the new waves") --
# The COMPLEMENT of OBS-10: active_axes_without_waves forces "a wave per axis" ONLY when the counter `T9 restart axes
# used: N` is set (N>=1). A past hunt left it as the template placeholder `{0-3+...}` + an empty registry ->
# `_t9_axes_declared=0` -> OBS-10 thinks "no axes" -> per-wave model-first BLIND -> the agent went scout-first on
# T9 axes (several of them) without a fresh I-NN model wave. Another hunt kept the counter -> OBS-10 worked.
# This gate catches the REVERSE side: the agent BUILDS extra `## WAVE-N` waves (uses T9 axes), but the counter is not
# maintained -> force setting it (which enables OBS-10 + all the per-wave enforcement). Fire: extra_waves>=1 in the
# model AND `_t9_axes_declared==0`. Off: MANUAL/OFF, HUNT-EXIT, MODEL N/A, a thin model.
def active_t9_count_untracked(current_sid):
    """The agent builds extra `## WAVE-N` waves (T9 axes are used), but `T9 restart axes
    used: N` is not set (placeholder/0) and the registry is empty -> `_t9_axes_declared=0` -> active_axes_without_waves
    is BLIND, per-wave model-first is not forced. Returns (rel, extra_waves) or None. A satisfiable soft-nudge."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None or _i_matured_count(mt) < 3:
        return None
    if _MANUAL_RE.search(lt or "") or _OFF_RE.search(lt or ""):
        return None
    if _has_valid_exit(lt or ""):
        return None
    if _model_building(lt) or _WAVE_NEXT_RE.search(lt or ""):
        return None                                      # building a wave right now - in progress
    extra_waves = len([k for k in _wave_i_counts(mt) if _WAVE_SECTION_RE.search(k)])
    if extra_waves < 1:
        return None                                      # no extra waves - T9 axes are not used, nothing to track
    if _t9_axes_declared(lt) >= 1:
        return None                                      # the counter/registry tracks the axes - OBS-10 works
    return (rel, extra_waves)


T9_COUNT_UNTRACKED_REASON = (
    "T9-COUNT UNTRACKED (2026-08-13, operator: 'forgot I-NN on the new waves'). Ledger `%s`: "
    "you built %d extra `## WAVE-N` wave(s) in the model (using T9 axes), BUT `T9 restart axes used: N` is not "
    "set (left as the placeholder `{0-3+...}`/0) and the registry is empty -> `_t9_axes_declared=0`. Consequence: the gate "
    "`active_axes_without_waves` (forces an I-NN model wave with `pred:` for EACH new axis BEFORE scout) is BLIND - "
    "it thinks 'no axes'. That is exactly how you go scout-first instead of model-first on T9 axes (anchored on 'what everyone "
    "finds anyway'). A past hunt kept the counter -> it worked. NOW: (1) set `T9 restart axes used: N` to the real "
    "number of closed+active axes; (2) populate `## Atom Registry` (each axis = an atom row); (3) on "
    "EACH new axis - a fresh `## WAVE-N` with `I-NN` (`pred:` BEFORE the code) -> a fan-out BY invariants -> D-NN -> DRIVE. "
    "This is NOT a loop exit (satisfiable - set the counter/registry and continue)."
)


# -- OBS-11 (2026-07-30): T11 (Harness as Generator) is applicable, but NOT run ------------------
# The t11_applicable.py detector on BOTH sessions returned APPLICABLE (invariant-heavy stateful + build),
# but in 4 hunts it was never launched: T11 = phase J2 of the skill, nothing forces it -> silently skipped.
# The gate does NOT force the fuzzing itself (expensive, operator: "not on every hunt"), but forces a CONSCIOUS decision:
# a mature model must carry in the ledger the detector verdict `T11-VERDICT: APPLICABLE|MAYBE|SKIP|N/A`.
# A skip = silent, an entry `SKIP — <reason>` = a legitimate pass. The detector is objective -> we do not
# re-detect applicability in the gate (template pollution), but demand to RUN it and record the verdict.
_T11_VERDICT_RE = re.compile(r"(?im)T11[-\s]*VERDICT[:=*\s]*(?:APPLICABLE|MAYBE|SKIP|N/?A)")


def _t11_decided(ledger_text):
    for l in (ledger_text or "").splitlines():
        if "{" in l:                                 # a template placeholder - not a decision
            continue
        if _T11_VERDICT_RE.search(l):
            return True
    return False


def active_t11_undecided(current_sid):
    """OBS-11: the model is mature (>=3 statused I-NN), but the ledger has no `T11-VERDICT:` verdict - phase J2
    (harness-as-generator) silently skipped. Returns rel or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None                                  # MODEL: N/A - lifted
    lt, mt, rel = ctx
    if mt is None:
        return None                                  # caught by active_model_incomplete
    if _i_matured_count(mt) < 3:
        return None                                  # the model is still being built -> model_incomplete
    if _t11_decided(lt):
        return None                                  # the detector was run, the verdict is recorded
    return rel


# -- OBS-12 (2026-07-30): T14 (attention-gap) is built, but NOT gated -> 0 artifacts in 4 hunts --
# audit_coverage_invert.py / commit_archaeology.py - the scripts exist, but in the hook there is only a soft-nudge.
# A reversal into a decision-gate (operator 2026-07-30): the `## Attention Gaps` section is empty and not marked `N/A`,
# AND there are no open live D-NN (i.e. you are about to conclude the axis "with nothing") -> block. Forces T14 BEFORE the conclusion
# "nothing there", without hindering driving (an open D-NN -> silent). Escape: fill the section OR `N/A — <reason>`.
_ATTN_NA_RE = re.compile(r"(?im)attention[\s-]*gaps?[^\n]{0,60}\bn/?a\b")


def _attention_gaps_filled_or_na(model_text):
    if _ATTN_NA_RE.search(model_text or ""):
        return True
    # filled in ANY form - a table (data rows, header cut) OR bullets/prose. A past hunt kept
    # T14 in bullets -> _section_rows alone saw "empty" and the gate would falsely force on top of a done mapping.
    if len(_section_rows(model_text or "", "Attention Gaps")) > 0:
        return True
    return len(_section_content_lines(model_text or "", "Attention Gaps")) > 0


def active_attention_gap_skipped(current_sid):
    """OBS-12: a mature model, zero open live D-NN, but `## Attention Gaps` is empty and not `N/A` ->
    T14 skipped before the conclusion "nothing there". Returns rel or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None                                  # the model is still being built
    if _model_building(lt) or _WAVE_NEXT_RE.search(lt or ""):
        return None                                  # building a wave -> not the time for T14
    if _attention_gaps_filled_or_na(mt):
        return None                                  # filled or deliberately N/A
    if _has_open_divergence(mt):                     # an open live D-NN (table/bullet) -> drive it
        # FIX-D (2026-08-12, operator: "T14 is always needed"): an open D-NN mutes T14, but
        # NOT forever. In a long multi-axis hunt there is always ONE open D-NN -> T14 (commit_archaeology /
        # audit_coverage_invert) was not forced the WHOLE run (7 axes closed, T14 never). T14 = the second
        # source of PLACE, cheap, needed >=1 time. After >=2 closed axis-like atoms an open D-NN NO LONGER
        # mutes (an early phase with 0-1 closed axes - drive D-NN, T14 later). Non-driver/no registry -> the old mute.
        _r = _atom_rows(lt)
        _closed_ax = [a for a in (_r or []) if a.get("status") == "CLOSED"
                      and (a.get("type") or "").strip().lower() in _AXIS_LIKE_TYPES]
        if len(_closed_ax) < 2:
            return None
        # >=2 closed axes + T14 never filled -> we fire DESPITE an open D-NN
    return rel


def _attention_gap_coverage(model_text):
    """The number of FILLED attention-gap entries: table data rows `_section_rows` + non-table
    content bullets `_section_content_lines` (that one already cuts `>` instructions/placeholders, FIX-D). Table
    and bullet do not overlap (content_lines skips `|`), so the sum = the number of entries."""
    return (len(_section_rows(model_text or "", "Attention Gaps")) +
            len(_section_content_lines(model_text or "", "Attention Gaps")))


def active_attention_gap_stale(current_sid):
    """Residual #2 (a judged live run, MED): T14 (attention-gap) once-per-hunt. Filled `## Attention
    Gaps` ONCE at the start -> `active_attention_gap_skipped` (cov>0) is silent FOREVER, although each new
    T9 axis = a new TERRITORY (other files/subsystems) with a FRESH attention map (where the auditor/author did not
    look EXACTLY in this zone). A long multi-axis hunt (7 axes) ran T14 exactly once. Mirrors the
    per-wave re-arm of the model (`active_axes_without_waves`): Loop State declares `T9 restart axes used: N`
    (N>=2), but attention-gap entries < N -> the map lags behind the axis expansion. A complement of
    `active_attention_gap_skipped` (that one - cov==0 "never"; this one - 0<cov<N "lagging"). PRIOR-PATTERNS
    deliberately is NOT re-armed: the fingerprint library is target-GLOBAL (a grep over all the code), a repeat per
    axis gives the same result - not per-territory. Off: MODEL: N/A, a thin model, building a wave, hunt-
    global `Attention Gaps N/A`, <2 axes, cov covered. Satisfiable. Returns (rel, N, cov) or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None                                  # the model is still being built
    if _model_building(lt) or _WAVE_NEXT_RE.search(lt or ""):
        return None                                  # building a wave -> not the time
    if _ATTN_NA_RE.search(mt or ""):
        return None                                  # hunt-global N/A -> a deliberate refusal, respect
    n = _t9_axes_declared(lt)
    if n < 2:
        return None                                  # <2 axes - too early to judge staleness
    cov = _attention_gap_coverage(mt)
    if cov < 1:
        return None                                  # cov==0 "never" - that is active_attention_gap_skipped
    if cov >= n:
        return None                                  # the map keeps up with the axes
    return (rel, n, cov)


ATTENTION_GAP_STALE_REASON = (
    "ATTENTION-GAP STALE (residual #2, 2026-08-12). Model `%s`: Loop State declares "
    "`T9 restart axes used: %d`, but entries in `## Attention Gaps` total only %d - T14 was run ONCE at the start "
    "and was not updated for the new axes. Each T9 axis = a new TERRITORY (other files/subsystems) -> its own FRESH "
    "attention map (where the auditor/author did not look EXACTLY in this zone). A once-per-hunt T14 goes blind on the "
    "territory of axes 2..N. NOW: for each new axis run `audit_coverage_invert.py` / "
    "`commit_archaeology.py` over ITS files and write the place(s) into `## Attention Gaps` (an intersection with `D-NN` = "
    "max priority), OR mark the axis `AX-NN: attention N/A — <reason>` (no new files / no audit). "
    "This is NOT a loop exit (satisfiable). (A hunt-global `Attention Gaps N/A` lifts the gate entirely.)"
)


# -- FEAT-E (2026-08-12, operator: "the fan-out ran ONCE, then it slid into single scouts") --
# The HYBRID Scout Fan-Out (divergence_fanout) PRODUCES D-NN / cross-thread / severity - skipping it on axes
# 2..N = the root of under-producing divergences. Project rule: "Scout = once at the start + ON EVERY T9 axis".
# The gate mirrors active_attention_gap_stale (re-arm per-axis): axes declared N>=threshold, but fan-out runs < N.
# A soft-nudge (the fan-out is expensive - not a hard-block). Off: MODEL N/A, a thin model, building a wave, <3 axes,
# hunt-global `fanout N/A`, runs >= axes.
_FANOUT_WF_RE = re.compile(r"wf_[a-z0-9]{4,}", re.I)                  # Workflow runId - reliable, not in prose
# 2026-08-19: the real run log - a BARE Workflow runId (without `wf_`) in merge headings:
# `### WAVE-16 MERGE (HYBRID-fan-out wz9twjv1b, 8 agents)` (the heading uses the Russian word for "fan-out"). The old counter saw only the `wf_` form -> 2 of 11.
# A TIGHT separator `[\s:,—()\-]{0,4}` (not `\D*`) between the context and the id - otherwise `<fan-out word> (divergence_fanout.
# workflow.js)` would give an FP on "workflow". id = w + 6..20 alnum (runId ~9), bare letter words after the fan-out word/
# fanout only with a solid separator will not pass (in prose letters follow the fan-out word, not a bare w-id).
_FANOUT_RUNID_CTX_RE = re.compile(
    r"(?i)(?:hybrid[-\s]*веер|hybrid[-\s]*fan-?out|\bfanout\b|\bвеер\b)[\s:,—()\-]{0,4}\b(w[a-z0-9]{6,20})\b")
_FANOUT_FIELD_RE = re.compile(r"^\s*[-*]?\s*\*{0,2}\s*hybrid[-\s]*fanout\s*[:=]", re.I)  # a structural run record
_FANOUT_NA_RE = re.compile(r"(?im)(?:fan-?out|веер)[^\n]{0,40}\bn/?a\b")
HYBRID_FANOUT_MIN_AXES = 3
HYBRID_FANOUT_MIN_WAVES = 2   # a real 2nd model wave = the fan-out is justified (2026-08-19)


def _fanout_run_count(lt, rows):
    """The number of HYBRID fan-out runs (DISTINCT). Per-line: a wf_-runId has priority (unique per run, not in
    prose), otherwise a structural `HYBRID-fanout:` field line (distinct by content) + the registry's fanout atoms.
    Does NOT count bare script names (`divergence_fanout`/`scout_fanout`) from the template RULES prose ->
    floor=0 on an untouched ledger (no FP from prose). The reason asks to log `HYBRID-fanout: <axis> — wf_<id>`."""
    keys = set()
    for line in (lt or "").splitlines():
        if "{" in line or line.lstrip().startswith(">"):
            continue                                    # placeholder / RULES-blockquote - not a real run
        wf = _FANOUT_WF_RE.search(line)
        if wf:
            keys.add(wf.group(0).lower())
            continue
        rids = _FANOUT_RUNID_CTX_RE.findall(line)      # bare runId in a WAVE-MERGE heading
        if rids:
            for r in rids:
                keys.add("rid:" + r.lower())
            continue
        if _FANOUT_FIELD_RE.match(line):
            keys.add("hf:" + re.sub(r"\s+", " ", line.strip().lower())[:50])
    for a in (rows or []):
        if (a.get("type") or "").strip().lower() == "fanout":
            keys.add("atom:" + (a.get("id") or ""))
    return len(keys)


def active_hybrid_fanout_stale(current_sid):
    """FEAT-E: fan-out-per-wave. Axes declared N>=HYBRID_FANOUT_MIN_AXES, but HYBRID fan-out runs < N -> the fan-out
    lagged behind the axis expansion (run once at the start, single scouts afterwards). Returns (rel, N, runs)
    or None. Soft-nudge (the fan-out is expensive)."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None                                  # the model is still being built
    if _model_building(lt) or _WAVE_NEXT_RE.search(lt or ""):
        return None                                  # building a wave -> not the time
    if _line_signal_present(lt, _FANOUT_NA_RE):
        return None                                  # hunt-global fanout N/A (small/single-file) - respect (Z2: skip placeholder/instruction)
    # past audit 2026-08-13 (operator note 5): FEAT-E hung ONLY on the number of AXES (`_t9_axes_declared`), but per
    # CLAUDE.md AXIS != WAVE - a broad axis = SEVERAL model waves `## WAVE-N`. In early waves there are few axes
    # (<HYBRID_FANOUT_MIN_AXES) -> the threshold muted the fan-out although there were already 3+ waves (6 waves / 2 fan-outs, the gate stayed silent
    # because at the moment of wave-3 there were <3 closed axes). Fix: n = max(axes, model waves) - the fan-out is re-armed
    # per-AXIS AND per-WAVE (WAVE-N). The wave counter = the same as in active_axes_without_waves (WAVE sections + 1
    # base Invariants wave) -> consistent (axes <= waves <= fan-outs). ADDITIVE: n only GROWS (max), legacy
    # per-axis behaviour is preserved, per-wave is added. mt is mature (passed maturity<3 above) -> the base wave exists.
    n_axes = _t9_axes_declared(lt)
    n_waves = len([k for k in _wave_i_counts(mt) if _WAVE_SECTION_RE.search(k)]) + 1
    # Two-pronged floor (fire-early eligibility, a past hunt 2026-08-19, operator: "fan-out on EVERY wave"):
    # a real 2nd model wave (`## WAVE-N`) = the fan-out is justified per-wave. A single MIN=3 muted WAVE-2
    # (n_waves=2<3) -> a plain scout slipped through. The axis path MIN_AXES=3 is left ONLY in the floor (the fan-out is expensive on a
    # single-wave small hunt). Fire if >=2 model waves OR >=3 axes.
    if n_waves < HYBRID_FANOUT_MIN_WAVES and n_axes < HYBRID_FANOUT_MIN_AXES:
        return None                                  # 1 wave AND <3 axes - early/small hunt (the fan-out is expensive)
    # DEMAND = the number of model WAVES, NOT max(axes, waves) (a past hunt 2026-08-19 measure): on a mature hunt
    # `_t9_axes_declared` counts ALL closed axes (62 in one case, most closed scout-cheap) -> max gave a
    # demand of "a fan-out on EVERY closed axis" (62) = unsatisfiable -> noise -> the hunter dismissed the real signal
    # "you did not fan out this wave". The gate's reason AND the methodology: "fan-out on EVERY WAVE, AXIS!=WAVE" - the fan-out maps
    # to a model wave (fresh invariant frame), not to a cheaply closed axis. "Axes without waves" = the concern of
    # active_axes_without_waves, not of the fan-out gate (clean separation).
    runs = _fanout_run_count(lt, _atom_rows(lt))
    if runs >= n_waves:
        return None                                  # the fan-out keeps up with the model waves
    return (rel, n_waves, runs)


HYBRID_FANOUT_STALE_REASON = (
    "HYBRID-FANOUT STALE (FEAT-E, past hunt 2026-08-12 + a past audit 2026-08-13 per-wave). Ledger `%s`: "
    "model waves declared %d, but HYBRID Scout Fan-Out runs total only %d - the fan-out was run once at the start, "
    "then only single scouts. AXIS != WAVE: a broad axis = several model waves `## WAVE-N`, the fan-out is needed on "
    "EVERY one (a past audit: 6 waves / 2 fan-outs, 'forgot on the 3rd'). HYBRID-"
    "fan-out (`divergence_fanout`) = a mechanized cross-thread T6 that BIRTHS `D-NN` / distant pairs / "
    "severity escalation - skipping it on axes/waves 2..N = the ROOT of under-producing divergences (a past hunt: D-NN=0). "
    "CLAUDE.md: 'Scout = once at the start + ON EVERY T9 axis/wave'. NOW: on the current wave run "
    "`divergence_fanout.workflow.js` (fan-out over the `I-NN` of this axis -> synthesis-reduce looks for distant pairs) and "
    "log the run (`HYBRID-fanout: <axis> — wf_<id> / N agents`), OR mark `fanout N/A — <reason>` "
    "(small axis / single-file). This is NOT a loop exit (satisfiable, soft - the fan-out is expensive)."
)


# Task 1 (FDE Plan 6, §50.1/§51): the `## Un-Dup Sweep` status cell counts as filled only
# if it carries `RUN` / `N/A — <reason>` / `→ D-NN <id>` - empty or a `{TODO}` placeholder = the seed
# generator has not been run/justified yet. Tolerates a markdown wrapper (`**RUN**`, `` `RUN` ``), as
# _norm_status does for enforcement statuses.
_UNDUP_OK_RE = re.compile(r"^(RUN\b|N/A\s*[—\-–]\s*\S|→\s*D-\d+)", re.I)


def _undup_status_ok(status):
    s = (status or "").replace("*", "").replace("`", "").strip()
    if not s or "{" in s:
        return False
    return bool(_UNDUP_OK_RE.match(s))


def _undup_sweep_incomplete_rows(ledger_text):
    """Rows of `## Un-Dup Sweep` (Task 1) whose status is NOT `RUN`/a justified `N/A`/`→ D-NN` -
    an unfilled seed generator applicable by profile. Namespace-agnostic: the section has the same
    form in web and contract ledgers (P6) - read by the presence of the heading, not by a fixed profile.
    Returns a list of generator names (first cell), or []."""
    out = []
    for line in _section_rows(ledger_text or "", "Un-Dup Sweep"):
        r = _cells(line)
        if len(r) < 2:
            continue
        name = r[0].strip()
        if not name:
            continue
        if not _undup_status_ok(r[1]):
            out.append(name)
    return out


def active_undup_sweep_incomplete(current_sid):
    """FDE Plan 6 §50.1/§51: the `## Un-Dup Sweep` section is seeded by profile of the target with applicable
    generators (`{TODO}`) + known-inapplicable ones (`N/A — <reason>`). An applicable generator
    left without a status on a MATURE ledger = an un-dup source of PLACES that the crowd may also have
    not run systematically - the hook holds the exit until every row carries `RUN` / a justified
    `N/A` / `→ D-NN <id>`. Off-switch (P5/P6, the same signal as `active_attention_gap_skipped`):
    `_model_ctx` (None on `MODEL: N/A`) + maturity `_i_matured_count(mt) >= 3` - anti-FP on the first
    scout pass and on trivial targets (the section ships in EVERY ledger). Namespace-agnostic:
    fires on the presence of the `## Un-Dup Sweep` section, not on a fixed profile (Task 1 covers both
    templates). Returns "gen1, gen2, ..." or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None                                  # first scout pass - the model is still being built
    if "## Un-Dup Sweep" not in (lt or ""):
        return None                                  # the section is not created (ledger predates Plan 6)
    incomplete = _undup_sweep_incomplete_rows(lt)
    if not incomplete:
        return None
    return ", ".join(incomplete[:8])


# ── Task 5 (FDE Plan 7, TIER B §61 · §48.1 Un-dup Pattern Amplifier): PRIOR-PATTERNS recon-producer ──
# ⚠ SENTINEL class - the INVERSE of producer-absent Task 3 (`active_ai_trust_unresolved`): the off-switch here =
# `_model_ctx` + `_i_matured_count(mt) >= 3` (the same signal as `active_undup_sweep_incomplete` /
# `active_composition_pass_skipped`). For producer-absent Task 3 `_i_matured_count` is on the CONTRARY forbidden (there the
# gate is triggered by the Scout partition P-AI, not by model maturity) - do not confuse. Detect - the ledger LINE
# `PRIOR-PATTERNS:` (sentinel), NOT file-presence: the line is written by the producer `pattern_replay.py` (auto-grep
# of `fingerprint`s of past confirmed un-dups from `undup_pattern_library.md` -> `PRIOR-PATTERNS: N matched`).
_PRIOR_PATTERNS_RE = re.compile(
    r"(?im)^[^\n]*?\bPRIOR-PATTERNS\b[^:\n]*:\**[ \t]*(.*?)[ \t]*$")


def _prior_patterns_unfilled(ledger_text):
    """True - the `PRIOR-PATTERNS:` line is present, but the value is a sentinel (`{...}` / empty) =
    the producer has not been run -> hold. False - either there is no line at all (ledger predates Task 5: anti-FP, the gate is silent),
    or the value is real (`N matched` / `0 matched` - the producer has been run). Matches the FIRST occurrence
    (the badge line in Loop State comes first; other mentions in prose are not at the start of a bare line)."""
    m = _PRIOR_PATTERNS_RE.search(ledger_text or "")
    if not m:
        return False
    val = m.group(1).strip()
    return (not val) or ("{" in val)


def active_pattern_replay_skipped(current_sid):
    """Task 5: a mature model (`_i_matured_count(mt) >= 3`), but the ledger line `PRIOR-PATTERNS:` carries
    `{TODO}`/empty - proactive un-dup compounding (§48.1) has not been run: the auto-grep of `fingerprint`s of
    past confirmed un-dups over the target code is not done, a matched pattern (the crowd did not close it anywhere =
    un-dup by construction, stronger than ordinary transfer) is skipped as a seed hypothesis. Sentinel class -
    detect the ledger line, NOT a file. Off-switch - the same signal as `active_undup_sweep_incomplete` /
    `active_composition_pass_skipped`: `_model_ctx` (None on `MODEL: N/A`) + `_i_matured_count(mt) >= 3`
    (anti-FP on the first scout pass / a trivial target). `is_giveup=False` (satisfiable - run
    producer / fill in a value; it still holds the turn). Namespace-agnostic (one line in all
    profiles - Task 5 seeds it into both templates). Returns relpath(ledger) or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None                                  # first scout pass - the model is still being built
    if not _prior_patterns_unfilled(lt):
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    return os.path.relpath(ledger, root)


PATTERN_REPLAY_REASON = (
    "PRIOR-PATTERNS SKIPPED (FDE Plan 7, TIER B §61 · §48.1 Un-dup Pattern Amplifier). Ledger `%s` — "
    "the model is mature (`_i_matured_count>=3`), but the `PRIOR-PATTERNS:` line = `{TODO}`/empty: proactive "
    "un-dup compounding has not been run. Every confirmed un-dup of a past hunt is abstracted into "
    "`sessions/_methodology/undup_pattern_library.md` (pattern + `fingerprint:` + where to look); entering a "
    "target you MUST grep them OVER the target code - a matched pattern = a seed hypothesis of the HIGHEST priority, because "
    "the crowd did not close it anywhere (un-dup by construction, stronger than ordinary transfer). NOW: run "
    "`py -3 -X utf8 scripts/_methodology/pattern_replay.py --src <target-repo> "
    "--session-dir <dirname(ledger)>` - it will write `PRIOR-PATTERNS: N matched` (lifts the hold), each "
    "matched -> create an H-NN. No access to the code / empty library -> it becomes `PRIOR-PATTERNS: 0 matched` "
    "(that also lifts it - the producer was run, there was simply nothing to match)."
)


# ── P0-Exposure (SlowMist Aug-2026, Exposure Engine): EXPOSURE-SCAN sentinel producer ──
# ⚠ SENTINEL class, a structural copy of active_pattern_replay_skipped (ledger LINE, NOT file-presence):
# the line `EXPOSURE-SCAN: N secrets / M pii / K data / 0` is written by the producer secret_exposure_scanner.py
# (a cross-engine pre-T1 secret/key/PII/data grep-pass over the clone + bundle + source-map + git history;
# for a live target - plus runtime_harness.capture_exposure). Off-switch - the same signal of the un-dup family
# soft-nudge (`active_pattern_replay_skipped`/`active_undup_sweep_incomplete`): `_model_ctx` +
# `_i_matured_count(mt) >= 3` (anti-FP on the first scout pass / a trivial target). Namespace-
# agnostic (one line in all 3 profiles - seeded into both ledger templates).
_EXPOSURE_SCAN_RE = re.compile(
    r"(?im)^[^\n]*?\bEXPOSURE-SCAN\b[^:\n]*:\**[ \t]*(.*?)[ \t]*$")


def _exposure_scan_unfilled(ledger_text, ledger_dir=None):
    """True - hold. False - lift. Hold when: (a) the `EXPOSURE-SCAN:` line is present, but the value
    is a sentinel (`{...}`/empty) = the producer has not been run; OR (b) the value looks real (file-scan
    counters), but the producer artifact `exposure_scan.md` is ABSENT from the session-dir = an ad-hoc grep wrote
    the line by hand, the systematic secret_exposure_scanner was NOT run (a past hunt 2026-08-14: the hunter ran
    an ad-hoc grep, not the producer with the decode layer/PII/git-history). Lift when: there is no line at all (anti-FP,
    ledger predates P0-Exposure), OR `N/A — reason` (deliberately lifted - no access to the code), OR the `[runtime]` tag
    (live web2/dapphunt path web2_exposure.capture_exposure - does not write the exposure_scan.md artifact), OR
    a real value AND the exposure_scan.md artifact exists (the producer was run). Matches the FIRST occurrence."""
    m = _EXPOSURE_SCAN_RE.search(ledger_text or "")
    if not m:
        return False
    val = m.group(1).strip()
    if (not val) or ("{" in val):
        return True
    low = val.lower()
    if low.startswith("n/a") or "[runtime]" in low:
        return False   # deliberately lifted / runtime path (no artifact written) -> producer check not needed
    # file-scan value -> the producer secret_exposure_scanner MUST have left exposure_scan.md.
    # An ad-hoc grep + a manual line will not create it -> hold (closes the gate's gameability).
    if ledger_dir:
        if not os.path.exists(os.path.join(ledger_dir, "exposure_scan.md")):
            return True
    return False


def active_exposure_scan_skipped(current_sid):
    """P0-Exposure: a mature model (`_i_matured_count(mt) >= 3`), but the ledger line `EXPOSURE-SCAN:` carries
    `{TODO}`/empty - the cross-engine secret/key/PII/financial-data grep-pass (secret_exposure_scanner.py)
    has not been run: a hardcoded/leaked key (Cat 4.10 class, the cheapest Critical), bulk PII,
    financial/closed data are not checked in the code, the bundle/source-map or git. Sentinel class - detect
    the ledger line, NOT a file. Off-switch - the same signal as `active_pattern_replay_skipped`: `_model_ctx`
    (None on `MODEL: N/A`) + `_i_matured_count(mt) >= 3`. `is_giveup=False` (satisfiable - run
    the producer / write `N/A — reason`). Namespace-agnostic. Returns relpath(ledger) or None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    if not _exposure_scan_unfilled(lt, os.path.dirname(ledger)):
        return None
    return os.path.relpath(ledger, root)


EXPOSURE_SCAN_REASON = (
    "EXPOSURE-SCAN SKIPPED (P0-2, Aug-2026, Exposure Engine · Cat 4.10). Ledger `%s` — the model is "
    "mature (`_i_matured_count>=3`), but the `EXPOSURE-SCAN:` line = `{TODO}`/empty: the cross-engine secret/"
    "key/PII/financial-data grep-pass has not been run. A hardcoded/leaked key (a real-world six-figure case), bulk PII, "
    "financial/closed data - the CHEAPEST Critical, living IN the code/bundle/source-map/git, not in the logic. "
    "NOW: `py -3 -X utf8 scripts/_methodology/secret_exposure_scanner.py --target "
    "<clone> --session-dir <dirname(ledger)> [--git-history]` - it will write `EXPOSURE-SCAN: N secrets / M pii / "
    "K data / 0` (lifts the hold), every secret/key -> H-NN (offline-derive + keypair->role correlation "
    "for severity). ⚠️ an ad-hoc `grep` over the bundle does NOT lift it: the line is written ONLY by the producer (it leaves the "
    "artifact `exposure_scan.md` - the gate checks for its presence; the decode layer catches encoded keys, "
    "PII, git-history, which a bare grep misses). A live target with a frontend -> runtime-sweep "
    "(`web2_exposure.capture_exposure`/`runtime_harness.capture_exposure`, OPSEC fail-closed) -> write "
    "`EXPOSURE-SCAN: N secrets / ... [runtime]` (the `[runtime]` tag lifts it without an artifact - the live path does not "
    "write one). No access to the code -> `EXPOSURE-SCAN: N/A — <reason>` (also lifts it)."
)


# ── Hunt Strategy Layer (2026-08-08): active_axis_queue_empty - the forward queue of axis changes ──
# The operator's pain "I forget where to go next" = there is no FORWARD ranked queue of axes. We hold the exit when >=1 axis
# is CLOSED (`T9 restart axes used: N>=1`), and the `Axis-Queue` field is empty/`none`/only stubs - AND I am actually
# BETWEEN axes (0 live Active H-NN, `Depth-Lead: none yet`). On a BROAD axis (mid-drive: a live H-NN OR
# Depth-Lead leads a thread) the gate is SILENT - it does not force an axis change early (operator 2026-08-08, AXIS!=WAVE).
# ⚠ READS THE LEDGER DIRECTLY (freshest_active_ledger), NOT via `_model_ctx`: an axis can close on a
# `MODEL: N/A` target (a small contract / web without a model) - the trigger = an axis closing, not model maturity
# (unlike the un-dup family pattern_replay/exposure). Anti-FP of the same class as WAVE-2/EXPOSURE-SCAN:
# the field is absent (a legacy session predating the layer) -> silent; value = a `{...}` placeholder -> empty (an untouched
# template is lifted earlier via t9=0). Anti-gaming: a stub (`N) TBD` without `src:`) is NOT a queue element -
# need >=1 line `N) <axis> … src:<real token>` (check EXECUTION, not the word; lesson of sentinel/WAVE-2).
_AQ_FIELD_RE = re.compile(r"(?im)^\s{0,3}-\s+\*\*\s*axis[\s\-_]*queue\b")
_AQ_ROW_RE = re.compile(r"(?im)^\s*\d+\)\s*\S.*?\bsrc:\s*(\S+)")
_AQ_STUB_SRC_RE = re.compile(r"^(tbd|todo|none|later|\?+|[—\-–]+|\{|<)", re.I)
# Field-anchored Depth-Lead (stricter than the prose-tolerant `_DEPTH_LEAD_LINE_RE`): ONLY the `- **Depth-Lead:**`
# Loop State field, NOT the RULES heading `8. **DEPTH-LEAD-FIRST…**` and NOT an inline `` `Depth-Lead` `` in prose.
_DEPTH_LEAD_FIELD_RE = re.compile(r"(?im)^\s{0,3}-\s+\*\*\s*depth[\s\-_]*lead\s*:")


def _axis_queue_block(ledger_text):
    """Text of the `- **Axis-Queue …:**` field (from its line to the next Loop State field `- **` or section
    `## `). None - no field at all (a legacy ledger predating the layer -> anti-FP: the gate is silent)."""
    lines = (ledger_text or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        if _AQ_FIELD_RE.match(line):
            start = idx
            break
    if start is None:
        return None
    out = [lines[start]]
    for line in lines[start + 1:]:
        if re.match(r"^\s{0,3}-\s+\*\*", line) or line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def _axis_queue_empty(ledger_text):
    """True - the Axis-Queue field EXISTS, but is empty gate-wise: a `{...}` placeholder / `none` / only stubs
    without a valid `src:`. False - no field (legacy -> anti-FP) OR >=1 real axis `N) … src:<token>`."""
    block = _axis_queue_block(ledger_text)
    if block is None:
        return False                                 # field absent (old session) -> silent
    val = block.split(":**", 1)[1] if ":**" in block else block
    if "{" in val:                                   # unfilled placeholder
        return True
    for m in _AQ_ROW_RE.finditer(block):
        tok = m.group(1).strip("`*<>").strip()
        if tok and not _AQ_STUB_SRC_RE.match(tok):
            return False                             # >=1 real axis in the queue -> not empty
    return True                                      # none / only stubs / prose without lines -> empty


def _depth_lead_active(ledger_text):
    """True - the `- **Depth-Lead:**` field carries a real thread (not `none yet` / not a `{...}` placeholder /
    not `—`). Mid-drive signal: I am driving a thread deep on the current axis -> the gate does not force an axis change."""
    for line in (ledger_text or "").splitlines():
        if not _DEPTH_LEAD_FIELD_RE.match(line):
            continue
        val = line.split(":**", 1)[-1] if ":**" in line else line.split(":", 1)[-1]
        val = val.replace("*", "").replace("`", "").strip()
        if not val or "{" in val:
            continue                                 # placeholder/empty -> not active
        low = val.lower()
        if low.startswith(("none", "—", "-", "–", "n/a")):
            continue                                 # `none yet` -> no thread chosen
        return True
    return False


def active_axis_queue_empty(current_sid):
    """Hunt Strategy Layer: >=1 axis CLOSED (`T9 restart axes used: N>=1`), but `Axis-Queue` is empty/`none`/
    only stubs AND I am BETWEEN axes (0 live Active H-NN + `Depth-Lead: none yet`) -> the forward plan of axis
    changes is not written ("forgot where to go next"). Off-switch: first pass (0 axes); mid-drive (a live H-NN /
    Depth-Lead leads a thread - a broad axis is not disturbed); MANUAL/OFF; HUNT-EXIT. NOT gated on model-
    maturity (an axis closes on `MODEL: N/A` too). Satisfiable soft-nudge (fill in the queue). Reads the ledger
    directly. Returns relpath(ledger) or None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None                                  # emergency manual mode
    if _has_valid_exit(lt):
        return None                                  # hunt finished by T4 High/Crit
    # WORKLIST DRIVER Stage 2 re-point (§1 promise, judge-B D1): the `## Atom Registry` registry now carries
    # the forward queue of axes (`type:axis status:OPEN`), and next_atom dictates a named-HANDOFF/QUEUE_EMPTY on
    # an axis change. While the flag is ON and the registry is populated with valid atoms - this prose Axis-Queue gate STANDS
    # ASIDE (otherwise it fires BEFORE next_atom at the very moment of a past hunt -> the instance gets an old
    # nag about the deprecated prose field, the named-HANDOFF does not get through, axes get duplicated). Flag OFF / no registry
    # -> old behaviour (prose Axis-Queue lives in parallel). ADDITIVE.
    if WORKLIST_DRIVER_ENABLED:
        _wl_rows = _atom_rows(lt)
        if _wl_rows is not None and _valid_atoms(_wl_rows):
            return None                              # the registry owns the forward queue -> next_atom dictates
    if _t9_axes_used(lt) < 1:
        return None                                  # first pass - no axis has been closed yet
    if [h for h in _active_hnn(lt) if h[2]]:
        return None                                  # mid-drive: a live Active H-NN on the current axis
    if _depth_lead_active(lt):
        return None                                  # mid-drive: Depth-Lead leads a thread deep
    if not _axis_queue_empty(lt):
        return None                                  # the queue is non-empty (>=1 axis with a valid src)
    return os.path.relpath(ledger, root)


AXIS_QUEUE_REASON = (
    "AXIS-QUEUE EMPTY (Hunt Strategy Layer, 2026-08-08 — forward plan of axis changes). Ledger `%s`: >=1 axis "
    "is CLOSED (`T9 restart axes used` >=1), but the `Axis-Queue` field is empty/`none`/only stubs, AND you are BETWEEN "
    "axes (0 live Active H-NN, `Depth-Lead: none yet`) - you forgot to write down WHERE to dig next (that very "
    "pain of 'I forget where to go next'). This is NOT an exit: the axiom 'bugs are everywhere' -> the loop has one exit = "
    "`HUNT-EXIT: T4-CONFIRMED <High|Critical>`. NOW fill `Axis-Queue` with a RICH ranked queue "
    "of FUTURE axes (many, not 1-2), EACH as a line `N) <axis> — src:<D-NN|T14-gap|score-4-file|T6-pair|"
    "prior-pattern|T9-frame> · rank:<severity×confidence×undup>`: (1) BUILD new ones - gap-map "
    "(unread score-4/5) / cold-axis (T9 new frame) / matched `PRIOR-PATTERNS` (top rank, "
    "`src:prior-pattern`); (2) EXTEND - Refuted H-NN of a closed axis -> T6 recombination -> a new axis; "
    "**Closed×Closed cross-thread** - pairs of closed-with-proof axes with shared state/fan-in -> a composite "
    "axis `undup:composition-seam` + HIGH rank -> Composite watch; (3) REBUILD - T9 cold restart. "
    "Include Medium axes (the severity weight keeps the Crit head start, but Medium does not drop out). ⚠ A stub (`N) TBD` without "
    "`src:`) does NOT count - you need >=1 axis with a valid `src:`. A broad axis (12+ I-NN, dozens of H-NN, many "
    "DRIVE) on ONE axis is legitimate: while you drive a thread (a live H-NN / Depth-Lead != none) the gate is SILENT, "
    "an axis change only on REAL exhaustion (all I-NN resolved AND 0 live H-NN AND 0 open D-NN)."
)


AXIS_QUEUE_THIN_MIN_CLOSED = 2   # >=N closed axes = a proven multi-axis hunt -> a forward plan is mandatory
AXIS_QUEUE_THIN_MIN_OPEN = 3     # <N OPEN atoms with rank+src = a thin queue (reactive one-at-a-time)


def active_axis_queue_thin(current_sid, min_closed=AXIS_QUEUE_THIN_MIN_CLOSED, min_open=AXIS_QUEUE_THIN_MIN_OPEN):
    """FIX-B (past hunt 2026-08-12, judge-2 3/10): a RICH ranked forward queue. `active_axis_queue_empty`
    under the driver mode STANDS ASIDE at >=1 valid atom (delegates to registry next_atom);
    `active_registry_drained_no_exit` is silent at >=1 OPEN/ACTIVE. Result (that hunt): the WHOLE run 1 ACTIVE + 0 OPEN
    (reactive one-at-a-time "off the top of the head") - NO gate required a forward plan ahead. Fire <=>
    WORKLIST_DRIVER_ENABLED AND >=min_closed CLOSED axis-like atoms (a proven multi-axis hunt) AND <min_open
    OPEN atoms with real rank+src. Off: MANUAL/OFF, HUNT-EXIT, flag off, no registry, <min_closed closed.
    Does not FP on a deep single-axis DRIVE: OPEN hypotheses of the current axis count into the queue (>=3 -> silent).
    Satisfiable soft-nudge (seed >=3 ranked FUTURE axes from D-NN/T14-gap/prior-pattern/Closed×Closed)."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    rows = _atom_rows(lt)
    if rows is None:
        return None
    closed_axes = [a for a in rows if a.get("status") == "CLOSED"
                   and (a.get("type") or "").strip().lower() in _AXIS_LIKE_TYPES]
    if len(closed_axes) < min_closed:
        return None                                     # not a multi-axis hunt yet - a forward plan is early
    open_ranked = [a for a in rows if a.get("status") == "OPEN"
                   and a.get("rank") is not None and _src_real(a.get("src"))]
    if len(open_ranked) >= min_open:
        return None                                     # a rich queue exists
    return (os.path.relpath(ledger, root), len(closed_axes), len(open_ranked))


AXIS_QUEUE_THIN_REASON = (
    "AXIS-QUEUE THIN (FIX-B, past hunt 2026-08-12, judge-2). Ledger `%s`: %d axes closed, but the registry has "
    "only %d OPEN atoms with real rank+src - this is a REACTIVE one-at-a-time 'off the top of the head', NOT a rich "
    "ranked forward queue. This is exactly how the loop degenerates within an hour: no seeded frontier -> exhausted the current "
    "axis -> 'the last axis' -> false-exhaustion. The axiom 'bugs are everywhere': axes are INFINITE, they must be GENERATED "
    "ahead, not taken one at a time. NOW seed >=%d OPEN atoms `type:axis` with a real `src:`+`rank` from: "
    "(1) BUILD - gap-map / cold-axis T9 / matched PRIOR-PATTERNS (top rank); (2) EXTEND - Refuted "
    "H-NN of a closed axis -> T6 recombination; **Closed×Closed cross-thread** (pairs of closed-with-proof axes with shared "
    "state -> a composite axis `undup:composition-seam`, HIGH rank); (3) REBUILD - T9 cold-restart. "
    "Rank severity×confidence×undup, head = Depth-Lead. Satisfiable - write the atoms, then drive the head."
)


# ── active_axis_reranked_midqueue (past audit 2026-08-13, operator: "the main thing is to go in queue order") ──
# The agent found an axis STRONGER than the queue heads (an economic-manipulation one) and TOOK it ad-hoc on T9, raising it ABOVE the tails of the
# LIVE queue (`re-ranked ABOVE stale queue-tails`) - a jump past the order. Order = LAW: you go along the
# ranked queue (take the heads by rank), write a new axis (even a stronger one) in as OPEN, finish the current
# head, and a rebuild (class-exhaustive re-ranking) - ONLY when the queue is exhausted. If an axis
# turned out stronger than the tails - this is a sign of an UNDER-filled queue (the strong one was not generated in advance), cured
# by a rebuild on exhaustion, NOT by a jump now. Fire: a reorder marker in the ledger (not a placeholder/prose rule).
_AXIS_REORDER_RE = re.compile(
    r"re-?rank\w*\s+\w{0,6}\s*above|above\s+\w{0,8}\s*(?:stale\s+)?queue[\s-]*tail|"
    r"popped\s+t9[^\n]{0,50}\babove\b|подн\w+\s+выше\s+хвост|переставил\w*\s+выше\s+очеред|"
    r"выше\s+застоя\w*\s+хвост|above\s+stale\s+queue", re.I)


def active_axis_reranked_midqueue(current_sid):
    """Past audit: a new axis was raised ABOVE the tails of the live queue and taken out of order. Fire:
    a reorder marker in a real ledger line (the very admission "re-ranked ABOVE queue-tails" = the tails are alive =
    the queue is not exhausted). Off: MANUAL/OFF, HUNT-EXIT, placeholder-only. Satisfiable soft-nudge.
    ⚠ BRACE-AWARE (`_line_signal_present`): a multi-line `{...}` template placeholder carries the reorder marker
    as an anti-gaming EXAMPLE - a naive per-line `{` skip would read the continuation lines as an admission."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if not _line_signal_present(lt, _AXIS_REORDER_RE):
        return None
    return os.path.relpath(ledger, root)


AXIS_REORDER_REASON = (
    "AXIS RE-RANKED MID-QUEUE (past audit 2026-08-13, operator: 'the main thing is to go in queue order'). "
    "Ledger `%s`: you raised a new axis ABOVE the tails of the LIVE queue and are taking it out of order (marker "
    "`re-ranked ABOVE queue-tails` / `popped T9 … above`). **Order = LAW:** you go along the ranked "
    "queue (take the heads by rank, single-pick), you do NOT jump to an ad-hoc axis in the middle - even if it is "
    "stronger. If an axis turned out stronger than the tails - that is a sign the queue was UNDER-filled (the strong one "
    "was not generated in advance), NOT a reason to jump. NOW: (1) write the new axis into the queue as `OPEN` (into "
    "the ranking, not as the ACTIVE head); (2) finish the CURRENT head to closure; (3) when the queue is exhausted "
    "(0 live OPEN) - rebuild it class-exhaustive (run the classes Cat 1/3/5/6/22/8… as candidate axes, "
    "rank by EV) -> take the new head IN ORDER. Remove the reorder marker. This is NOT a loop exit "
    "(satisfiable - align the queue and continue)."
)


# ── active_axis_closed_critical_only (past audit 2026-08-13, operator: "why only critical?") ──
# The agent closed an axis on a scout verdict "no unprivileged Critical" - a narrow frame. Our loop-exit = High/
# Critical (High ON PAR with Critical), + Medium - a full DRIVE (bank), Low - harvest. "No Critical"
# != the axis is clean: High and Medium must be EXPLICITLY assessed and (Medium/Low) banked. Fire: the axis is marked
# closed/hardened with a Critical-only negation AND there is no parallel High/Medium verdict in the same context.
_CRIT_ONLY_CLOSE_RE = re.compile(
    r"(?:no|нет|zero|0)\s+\w{0,18}\s*(?:unprivileged\s+)?critical\b|"
    r"nothing\s+\w{0,10}\s*exploitable|no\s+\w{0,10}\s*exploit\b", re.I)
_HIGH_MED_VERDICT_RE = re.compile(
    r"\bno\s+\w{0,12}\s*high\b|нет\s+\w{0,12}\s*high|\bhigh/critical\b|high[\s-]*crit|"
    r"medium[\s:=-]|no\s+medium|нет\s+medium|banked|\blow[\s-]*deferred\b|severity\s*[:=]", re.I)


def active_axis_closed_critical_only(current_sid):
    """Past audit: an axis closed on "no Critical" without an explicit High/Medium assessment. Loop-exit =
    High/Critical (High on par), Medium = DRIVE+bank. Fire: a Critical-only-negation closure AND in the same
    context (+-3 lines) there is no High/Medium/banked verdict. Off: MANUAL/OFF, HUNT-EXIT, placeholder."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    lines = lt.splitlines()
    depth = 0                                            # BRACE-AWARE: a multi-line `{...}` placeholder skip
    for i, line in enumerate(lines):
        opens, closes = line.count("{"), line.count("}")
        inside = depth > 0 or opens > 0
        depth = max(0, depth + opens - closes)
        if inside or line.lstrip().startswith(">"):
            continue                                     # placeholder/prose rule
        if not _CRIT_ONLY_CLOSE_RE.search(line):
            continue
        # context +-3 lines: is there an explicit High/Medium/banked verdict nearby?
        ctx = " ".join(lines[max(0, i - 3):min(len(lines), i + 4)])
        if _HIGH_MED_VERDICT_RE.search(ctx):
            continue                                     # High/Medium assessed nearby - the frame is complete
        return os.path.relpath(ledger, root)
    return None


AXIS_CRIT_ONLY_REASON = (
    "AXIS CLOSED CRITICAL-ONLY (past audit 2026-08-13, operator: 'why only critical?'). Ledger "
    "`%s`: you closed an axis on 'no unprivileged Critical' - a NARROW frame. Our loop-exit = **High/Critical** "
    "(High ON PAR with Critical, not 'incidentally'), + **Medium** - a full DRIVE (deeper right away, bank in "
    "`## Banked Findings`, push ceiling->High), **Low** - cost-gated harvest. 'No Critical' != the axis is clean: "
    "a scout that found no Critical may have missed a High OR not assessed Medium. NOW reformulate the axis "
    "closure: (1) **no unprivileged High/Critical** (that is the loop-exit - prove it with a falsifier, not 'no "
    "Critical'); (2) **Medium:** found/none - if yes -> bank + push ceiling; (3) **Low:** harvest <=1 step "
    "/ `[LOW-DEFERRED]`. Found Lows (BB-NN) -> into `## Banked Findings`, do not drop them. This is NOT a loop exit "
    "(satisfiable - finish assessing the severity levels and continue)."
)


# ── A5 (Wave 1 2026-08-08): active_banked_composite_unchecked - banked × T6 composite ──
# banked findings (confirmed Medium/Low) = PROVEN building-blocks (more reliable than refuted hypotheses).
# Before a batch-submit - a mandatory T6 pass over the bank: the output of one -> the input of another (Low×Low ->
# precondition, Low+High -> escalate, Medium×Medium -> Crit). A double benefit: severity-boost + un-dup
# (the crowd submits small stuff one at a time = duplicates). Reads the ledger DIRECTLY (banked are independent of model-maturity),
# like active_axis_queue_empty. Satisfiable soft-nudge (is_giveup=False): do the pass / mark "no pairs".
_BANKED_HDR_RE = re.compile(r"(?im)^\s*##\s+Banked\s+Findings\b")
_BANKED_T6_FIELD_RE = re.compile(r"(?im)^\s{0,3}[-*>]?\s*\*{0,2}\s*banked\s+t6[\s\-_]*pass\b")


def _banked_section(ledger_text):
    """Body of the `## Banked Findings` section (up to the next `## `). None - no section (legacy -> anti-FP)."""
    lines = (ledger_text or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        if _BANKED_HDR_RE.match(line):
            start = idx
            break
    if start is None:
        return None
    out = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def _banked_rows(ledger_text):
    """Number of REAL finding rows in the Banked Findings table (an empty placeholder `| | ... |`, header
    and separator do not count). Independent of the number of columns (7 old / 9 with output/input)."""
    sec = _banked_section(ledger_text)
    if not sec:
        return 0
    n = 0
    for line in sec.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        joined = "".join(cells)
        if not joined or set(joined) <= set("-: "):     # empty placeholder / separator
            continue
        low = " ".join(cells).lower()
        if "severity" in low and "h-nn" in low:         # header
            continue
        substantive = [c for c in cells if c and c != "-"]
        if len(substantive) >= 2:                        # more than one index #
            n += 1
    return n


def _banked_t6_done_count(ledger_text):
    """SUD-MED-2 (past hunt): N from `Banked T6-pass: DONE (N=k)` - over how many banked the T6 pass was run.
    Returns: None - the field is not DONE (pass not done); -1 - DONE WITHOUT N (old format -> backward-compat,
    treated as "the current bank is covered", lifts); int k - DONE(N=k). Re-arm: banked>k -> the pass is stale
    (the bank grew, new output->input pairs are unchecked)."""
    for line in (ledger_text or "").splitlines():
        if not _BANKED_T6_FIELD_RE.match(line):
            continue
        if line.lstrip().startswith(">"):
            continue
        val = line.split(":", 1)[-1] if ":" in line else ""
        val = val.replace("*", "").replace("`", "").strip()
        if "{" in val:
            continue
        if re.search(r"\bDONE\b", val, re.I):
            m = re.search(r"\bN\s*=\s*(\d+)", val)
            return int(m.group(1)) if m else -1
    return None


def active_banked_composite_unchecked(current_sid):
    """A5: >=2 banked findings in the ledger, but the T6 pass over the bank is not done (`Banked T6-pass:` empty/
    placeholder/no field) -> before submission the output->input pairs of banked are unchecked. Off-switch:
    MANUAL/OFF, HUNT-EXIT, <2 banked. Satisfiable soft-nudge. Reads the ledger directly. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    banked = _banked_rows(lt)
    if banked < 2:
        return None                                      # <2 banked -> nothing to build chains from
    done_n = _banked_t6_done_count(lt)                   # SUD-MED-2: re-arm on bank growth
    if done_n is None:
        return os.path.relpath(ledger, root)             # the pass is not done at all
    if done_n < 0:
        return None                                      # DONE without N (old format) - backward-compat lifts
    if banked > done_n:
        return os.path.relpath(ledger, root)             # the bank grew beyond the checked amount -> re-arm (new pairs)
    return None                                          # the pass covered the current bank (done_n >= banked)


# ── FEAT-I (past hunt 2026-08-12): a single cross-thread T6 engine. cross-thread was FRAGMENTED into 3
# mechanisms (fan-out-synthesis / refuted-merge / banked-T6), and refuted hypotheses + resolved D-NN are also
# building-blocks (CLAUDE.md: refuted stay for chains) - but crossing them was NOT forced (only
# banked-T6). A single counter: refuted([KILLED]/[CONTESTED]) + banked + D-NN. When >=threshold accumulates without a
# cross-thread-synthesis record -> nudge to run synthesis over the WHOLE pool. Re-arm on growth (DONE(N=k), like
# banked-T6). A complement of banked_composite (that one - banked×banked; this one - the whole pool of building-blocks).
_CROSSTHREAD_SYNTH_FIELD_RE = re.compile(
    r"^\s*[-*]?\s*\*{0,2}\s*cross-?thread[\s-]*(?:synth\w*|t6)\s*[:=]", re.I)
CROSSTHREAD_MIN_BB = 4        # >=N proven building-blocks (refuted+banked+D-NN) = time to cross distant ones


def _line_signal_present(txt, rgx):
    """rgx found in a REAL ledger line - NOT in a `{placeholder}` and NOT in a `>`-blockquote (the template's RULES instruction
    contains the field NAME -> a naive .search would blind the gate on an untouched template / placeholder).
    BRACE-AWARE (judge-2, final acceptance): placeholders are MULTI-LINE - `{` on the first line, the text
    continues on the following lines WITHOUT a brace. A naive per-line skip let the continuation through as a "real
    entry" (regression caught by template_sentinel: `…requires adversarial cold-recheck…` on the 2nd line of the
    Severity placeholder blinded FEAT-C). We track the `{`/`}` depth across lines."""
    depth = 0
    for line in (txt or "").splitlines():
        opens, closes = line.count("{"), line.count("}")
        inside = depth > 0 or opens > 0            # the line is inside/starts a placeholder block
        depth = max(0, depth + opens - closes)
        if inside or line.lstrip().startswith(">"):
            continue
        if rgx.search(line):
            return True
    return False


def _refuted_bb_count(ledger_text):
    """Number of refuted/contested building-blocks: `### …[KILLED]`/`[CONTESTED]` H-NN headings (CLAUDE.md:
    refuted stay building-blocks for T6 chains). A `{` placeholder does not count."""
    n = 0
    for line in (ledger_text or "").splitlines():
        s = line.strip()
        if s.startswith("###") and "{" not in s and _DEAD_TAG_RE.search(s):
            n += 1
    return n


def _crossthread_synth_count(ledger_text):
    """N from `cross-thread synthesis: DONE (N=k)` - over how many building-blocks synthesis was run. None -
    the field is not DONE; -1 - DONE without N (legacy, lifts once); k - DONE(N=k). A mirror of _banked_t6_done_count."""
    for line in (ledger_text or "").splitlines():
        if not _CROSSTHREAD_SYNTH_FIELD_RE.match(line):
            continue
        val = line.split(":", 1)[-1] if ":" in line else line.split("=", 1)[-1]
        val = val.replace("*", "").replace("`", "").strip()
        if "{" in val:
            continue
        if re.search(r"\bDONE\b", val, re.I):
            m = re.search(r"\bN\s*=\s*(\d+)", val)
            return int(m.group(1)) if m else -1
    return None


def active_crossthread_synthesis_stale(current_sid):
    """FEAT-I: a single cross-thread engine. >=CROSSTHREAD_MIN_BB proven building-blocks (refuted +
    banked + D-NN), but cross-thread synthesis over the pool is not run / lags behind growth -> nudge. Re-arm on
    growth (DONE(N=k), bb>k). Returns (rel, bb, done) or None. Off: MANUAL/OFF, HUNT-EXIT, immature
    model, <building-blocks threshold. Soft-nudge (satisfiable)."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None or _i_matured_count(mt) < 3:
        return None                                      # immature model - building-blocks not accumulated yet
    if _MANUAL_RE.search(lt or "") or _OFF_RE.search(lt or ""):
        return None
    if _has_valid_exit(lt or ""):
        return None
    bb = _refuted_bb_count(lt) + _banked_rows(lt) + _dnn_total_count(mt)
    if bb < CROSSTHREAD_MIN_BB:
        return None                                      # few building-blocks - too early to cross
    done_n = _crossthread_synth_count(lt)
    if done_n is None:
        return (rel, bb, 0)                              # synthesis was not run at all
    if done_n < 0:
        return None                                      # DONE without N (legacy) - lifts once
    if bb > done_n:
        return (rel, bb, done_n)                         # the pool grew beyond the checked amount -> re-arm
    return None


CROSSTHREAD_SYNTHESIS_STALE_REASON = (
    "CROSS-THREAD SYNTHESIS STALE (FEAT-I, past hunt 2026-08-12). Model/ledger `%s`: accumulated %d "
    "proven building-blocks (refuted `[KILLED]`/`[CONTESTED]` + banked findings + `D-NN`), but "
    "cross-thread synthesis over them is not run / lags behind (covered %d). cross-thread was FRAGMENTED "
    "(fan-out-synthesis / refuted-merge / banked-T6) - and refuted hypotheses and resolved `D-NN` = THE SAME "
    "building-blocks (CLAUDE.md: refuted stay for chains), nobody forced crossing them. An un-dup "
    "crit lives in the JOINT of DISTANT evidence from DIFFERENT subsystems/classes (a past hunt: Accounting × Mock-vs-Prod). "
    "NOW: run a synthesis agent (`divergence_fanout` reduce phase OR a manual cross-thread T6) over the "
    "WHOLE pool of building-blocks - look for `output->input` pairs between DISTANT ones (refuted-A × banked-B × D-NN-C), "
    "not neighbouring ones. ⚠ ONE reasoner holds the WHOLE pool - do NOT split it by subsystem like a scout-fanout (partitioning "
    "by subsystem = the INVERSE reflex: the cross-pair lives BETWEEN agents -> it falls apart by construction; a past hunt "
    "2026-08-19 missed an A74 EP-side × A75 rate-side pair). Valid: `divergence_fanout` reduce (one senior tier "
    "over the WHOLE batch) OR one cold agent with the whole list; if redundancy is needed - the same whole-pool synthesis N "
    "times, not a split. Log `cross-thread synthesis: DONE (N=<number covered>)` (when the pool grows the gate "
    "will rise AGAIN). This is NOT a loop exit (satisfiable, soft)."
)


# ── FEAT-C (past hunt 2026-08-12, operator: "when you refute a finding - the agents or you yourself must re-check"):
# false-refute guard. A strong thread (a refuted H-NN with High/Critical severity) accepted on ITS OWN falsifier without an
# adversarial cold re-check -> risk of false-refute (a past hunt: first-pass abort -> reversal -> 2 findings). Retention
# in cross-thread is already covered by FEAT-I (refuted = building-block); HERE - re-checking the refute before accepting it.
# Past audit 2026-08-13 (operator note 6): I-08 (High/Crit) closed as `[SCOPED-OUT]` - the soft-kill taxonomy
# of a STRONG thread also requires a cold-recheck (an OOS/keeper-gated judgement may be wrong: a permissionless
# path / trusted-actor unverified). We extend the head to soft-kill tags (SCOPED-OUT/ASSUMED-CANONICAL),
# not only hard [KILLED]/[CONTESTED]. Only High/Crit (severity in the block) -> soft-nudge, not noise.
_REFUTE_HEAD_RE = re.compile(
    r"^\s*#{2,4}\s+\S.*\[\s*(?:KILLED|CONTESTED|SCOPED[-\s]?OUT|ASSUMED[-\s]?CANONICAL)\b", re.I)
_HIGH_SEV_RE = re.compile(r"\b(?:high|critical|crit)\b", re.I)
_COLD_RECHECK_RE = re.compile(
    r"cold[-\s]?re-?check|adversarial\s+re-?check|2nd[-\s]?agent|second\s+agent|"
    r"re-?verified\s+cold|refute[-\s]?recheck|cold[-\s]?agent\s+refut", re.I)
# Past audit note 6 (the MAIN hole): the LABEL line `cold-recheck (FEAT-C): PENDING` contains the word
# "cold-recheck" -> the old substring off-switch (`_line_signal_present(_COLD_RECHECK_RE)`) falsely muted the
# gate although the recheck was NOT done. The off-switch now requires an OUTCOME (confirmed/refuted/…) AND NOT pending.
_RECHECK_OUTCOME_RE = re.compile(
    r"подтверд|опроверг|confirm|refut|upheld|overturn|revers|устоял|развал|сто[ия][тл]|held\b", re.I)
_RECHECK_PENDING_RE = re.compile(r"\bpending\b|\btodo\b|\bnone\s+yet\b|\bн/?д\b", re.I)
STRONG_REFUTE_MIN = 1


def _cold_recheck_done(ledger_text):
    """FEAT-C off-switch: cold-recheck counts ONLY if the line carries a recheck MARKER + an OUTCOME
    (confirmed/refuted/confirm/refut/…) and NOT pending/placeholder/blockquote. Past audit note 6:
    the label line `cold-recheck (FEAT-C): PENDING` muted the gate with the word "cold-recheck" without a real
    recheck. We require an OUTCOME, not just the word. Zero-FP: a `{...}` placeholder and a `> ...` instruction are skipped."""
    for line in (ledger_text or "").splitlines():
        if "{" in line or line.lstrip().startswith(">"):
            continue
        if (_COLD_RECHECK_RE.search(line) and _RECHECK_OUTCOME_RE.search(line)
                and not _RECHECK_PENDING_RE.search(line)):
            return True
    return False


def _strong_refute_count(ledger_text):
    """refuted/contested H-NN threads with High/Critical severity (a strong thread). Z2-fix (judge MED): severity
    is looked up in the BLOCK (heading + body up to the next heading/blank line), since the canonical format puts
    `### H-NN [KILLED]: <one-line>` in the heading, and `**Severity:** High` in the BODY. A `{` placeholder does not count."""
    lines = (ledger_text or "").splitlines()
    n = 0
    for i, line in enumerate(lines):
        if "{" in line or not _REFUTE_HEAD_RE.match(line):
            continue
        # блок нити: heading + тело до следующего `###`-heading / пустой строки (≤8 строк)
        block = [line]
        for j in range(i + 1, min(i + 9, len(lines))):
            nxt = lines[j]
            if not nxt.strip() or nxt.lstrip().startswith("###"):
                break
            block.append(nxt)
        if _HIGH_SEV_RE.search(" ".join(block)):
            n += 1
    return n


def active_strong_refute_unrechecked(current_sid):
    """FEAT-C: ≥STRONG_REFUTE_MIN сильных refute (High/Crit нить [KILLED]/[CONTESTED]), но НИ ОДНОЙ
    cold-recheck записи → сильную нить приняли на свой falsifier без adversarial перепроверки (риск
    false-refute, Superform-урок). Возвращает (rel, N) либо None. Off: MANUAL/OFF, HUNT-EXIT, незрелая
    модель, 0 сильных refute, ≥1 cold-recheck. Soft-nudge."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None or _i_matured_count(mt) < 3:
        return None                                      # незрелая модель — рано
    if _MANUAL_RE.search(lt or "") or _OFF_RE.search(lt or ""):
        return None
    if _has_valid_exit(lt or ""):
        return None
    strong = _strong_refute_count(lt)
    if strong < STRONG_REFUTE_MIN:
        return None                                      # нет сильных refute — нечего перепроверять
    if _cold_recheck_done(lt):
        return None                                      # ≥1 cold-recheck с ИСХОДОМ (не PENDING-лейбл, lombard п.6)
    return (rel, strong)


STRONG_REFUTE_REASON = (
    "STRONG REFUTE UNRECHECKED (FEAT-C, jito-live 2026-08-12). Ledger `%s`: %d сильных нитей (High/Critical) "
    "помечены `[KILLED]`/`[CONTESTED]` на СВОЙ falsifier, но НИ ОДНОЙ adversarial cold-recheck записи. "
    "false-refute = дорогой промах: Superform first-pass «всё опровергнуто» → the operator развернул → второй "
    "проход нашёл 2 РЕАЛЬНЫХ бага. Сильную нить нельзя принять killed на self-falsifier: (1) refute-cooldown — "
    "НЕ убивай нить в той же итерации, где открыл (force ≥1 depth-layer перед kill, быстрый kill = недокоп); "
    "(2) сильный refute → COLD-агент (maker≠checker) пытается ОПРОВЕРГНУТЬ твой falsifier (default: refuted "
    "неверен, пока cold-агент не подтвердит). СЕЙЧАС: возьми сильнейший refuted High/Crit, прогони cold-агента "
    "на РЕ-falsify, впиши `cold-recheck: <нить> — <cold-агент подтвердил/опроверг refute>`. Refuted-нить "
    "ОСТАЁТСЯ building-block для cross-thread (FEAT-I). Это НЕ выход петли (satisfiable, soft)."
)


def active_banked_without_oos_check(current_sid):
    """Out-of-Scope на banked-подаче (аудит полноты 2026-08-11 — ГЛАВНАЯ дыра): ≥1 banked finding + OOS
    РЕАЛЬНО захвачен, но нет валидной `OOS-CHECK:` строки → banked Medium/Low подаются batch'ем БЕЗ
    сверки с дисквалификаторами. submit-OOS-CHECK живёт только в HUNT-EXIT пути (High/Crit); banked
    петлю не завершают и туда не попадают → без этого гейта Medium/Low = тот же OOS-close $0 (а OOS
    чаще бьёт по Medium: centralization/trusted-actor редко Critical, и the operator хантит Medium наравне).
    Off: MANUAL/OFF; HUNT-EXIT (submit-гейт закрывает); OOS не захвачен/N/A; уже есть OOS-CHECK.
    Satisfiable soft-nudge (сверь КАЖДУЮ banked-находку). relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None                                      # HUNT-EXIT → submit-гейт закрывает
    if _banked_rows(lt) < 1:
        return None                                      # нечего подавать
    if not _oos_captured_real(lt):
        return None                                      # OOS N/A / no-program → сверять не с чем
    if _OOS_CHECK_RE.search(lt):
        return None                                      # сверка проведена
    return os.path.relpath(ledger, root)


def active_banked_atom_unsynced(current_sid):
    """FIX-5 (ethena-live 2026-08-12, judge): split-brain реестр↔таблица — Atom Registry несёт ≥1 атом
    `status:BANKED`, а таблица `## Banked Findings` пуста (0 реальных строк). `active_banked_composite_unchecked`
    и OOS-check читают ТАБЛИЦУ (`_banked_rows`) → при пустой таблице считают «0 banked» и молчат, хотя банк
    заявлен в реестре → banked-находка теряется/не форсится перед batch-submit. Fire ⇔ BANKED-атом есть И
    `_banked_rows`==0 И реестр существует. Off: MANUAL/OFF, HUNT-EXIT, нет реестра (C1 silent). Satisfiable
    soft-nudge. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    rows = _atom_rows(lt)
    if not rows:                                         # None (нет реестра) / пусто → C1 silent
        return None
    if not any(r.get("status") == "BANKED" for r in rows):
        return None                                      # реестр не заявляет banked → нечего синхронить
    if _banked_rows(lt) > 0:
        return None                                      # таблица заполнена → синхронно
    return os.path.relpath(ledger, root)


BANKED_ATOM_UNSYNCED_REASON = (
    "BANKED ATOM UNSYNCED (FIX-5, ethena-live 2026-08-12, judge). Ledger `%s`: Atom Registry несёт "
    "атом(ы) `status:BANKED`, а таблица `## Banked Findings` ПУСТА. Split-brain: batch-submit и "
    "`active_banked_composite_unchecked`/OOS-check читают ТАБЛИЦУ — при пустой таблице считают «0 banked» "
    "и молчат, banked-находка теряется перед подачей. СЕЙЧАС: для КАЖДОГО BANKED-атома впиши строку в "
    "`## Banked Findings` (severity | H-NN | что | output | input | payout-tier | found_by | статус). "
    "Satisfiable — синхронизируй реестр и таблицу, потом banked-кластер (T6/OOS/T4) отработает корректно."
)


# ── active_banked_prose_unsynced (veda 2026-08-18, the operator: «даже если программа не платит Low/Medium —
# он всё равно должен их записывать и ВЕСТИ, чтобы потом смержить и сделать T6») ──
# Хантер нашёл confirmed Low/Medium building-blocks и записал их ПРОЗОЙ (bare-теги [LOW-DEFERRED]/
# [LOW-CONTESTED]/[MEDIUM-*], «Banked Low/info: X; Y; Z») — даже мог прогнать T6 прозой («T6 pass DONE:
# no payable pair» в тексте), НО таблица `## Banked Findings` ПУСТА. Тогда active_banked_composite_unchecked
# (читает ТАБЛИЦУ + поле `Banked T6-pass`) видит 0 banked → структурный T6 не форсится, building-blocks не
# мержатся и не компаундятся (undup_pattern / cross-target transfer). Sibling active_banked_atom_unsynced:
# тот — для реестр-атомов `status:BANKED`; этот — для ПРОЗЫ без атома (veda банчила именно так). Fire ⇔
# ≥MIN prose-строк с bare Low/Medium-тегом И `_banked_rows`==0 И нет реестр-BANKED-атома (иначе atom-gate).
# Off: MANUAL/OFF, HUNT-EXIT, таблица непуста. Satisfiable soft-nudge (banked Low/Med петлю не завершают).
_BANKED_PROSE_TAG_RE = re.compile(r"\[(?:LOW|MED(?:IUM)?)[A-Z/\-]*\]", re.I)
BANKED_PROSE_MIN = 2


def _banked_prose_tag_lines(ledger_text):
    """Число РАЗЛИЧНЫХ prose-строк с bare confirmed-Low/Medium building-block тегом ([LOW-DEFERRED]/
    [LOW-CONTESTED]/[MEDIUM-*]) — хантерская конвенция «записанный banked building-block». НЕ считаем:
    blockquote-инструкцию (`>`), header (`#`), `{}`-плейсхолдер шаблона, backtick-инлайн-пример
    (`` `[LOW-DEFERRED]` `` в прозе-правиле = образец, не находка). Backtick-спаны вырезаются до матча."""
    n = 0
    depth = 0
    for line in (ledger_text or "").splitlines():
        opens, closes = line.count("{"), line.count("}")
        inside = depth > 0 or opens > 0
        depth = max(0, depth + opens - closes)
        s = line.lstrip()
        if inside or s.startswith(">") or s.startswith("#"):
            continue
        bare = re.sub(r"`[^`]*`", " ", line)               # вырезать backtick-инлайн-примеры
        if _BANKED_PROSE_TAG_RE.search(bare):
            n += 1
    return n


def active_banked_prose_unsynced(current_sid):
    """veda: confirmed Low/Medium building-blocks записаны ПРОЗОЙ (bare-теги), но таблица `## Banked
    Findings` пуста → composite-T6/компаундинг слепы. Fire ⇔ ≥BANKED_PROSE_MIN prose-tag-строк И
    `_banked_rows`==0 И нет реестр-BANKED-атома (тот путь у atom-gate). Off: MANUAL/OFF, HUNT-EXIT,
    таблица непуста. Satisfiable soft-nudge. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _banked_rows(lt) > 0:
        return None                                        # таблица заполнена → структурно синхронно
    rows = _atom_rows(lt)
    if rows and any(r.get("status") == "BANKED" for r in rows):
        return None                                        # реестр-BANKED есть → atom-gate ведёт синк
    if _banked_prose_tag_lines(lt) < BANKED_PROSE_MIN:
        return None                                        # прозой banked building-blocks не заявлены
    return os.path.relpath(ledger, root)


BANKED_PROSE_UNSYNCED_REASON = (
    "BANKED PROSE UNSYNCED (veda 2026-08-18, the operator «записывай Low/Medium building-blocks СТРУКТУРНО, чтобы "
    "смержить и сделать T6 — даже если программа их не платит»). Ledger `%s`: ты записал confirmed Low/"
    "Medium дефекты ПРОЗОЙ (теги [LOW-DEFERRED]/[LOW-CONTESTED]/[MEDIUM-*]), а таблица `## Banked Findings` "
    "ПУСТА. Машинный T6-мерж (`active_banked_composite_unchecked`) читает ТАБЛИЦУ → видит 0 banked → "
    "структурный composite НЕ форсится, building-blocks не скрещиваются в Critical и не компаундятся "
    "(undup_pattern / cross-target). **Low/Medium не платятся на ЭТОЙ программе ≠ выкидываем:** они — "
    "ДОКАЗАННЫЕ building-blocks (Low×Low→precondition, Low+High→escalate до Crit, Medium×Medium→Crit), а "
    "Critical УЖЕ платят. СЕЙЧАС: впиши КАЖДЫЙ в `## Banked Findings` строкой (severity | H-NN | что | "
    "output | input | payout-tier | found_by | статус) → потом banked-T6 пасс отработает над РЕАЛЬНЫМИ "
    "output→input парами. Satisfiable — синхронизируй прозу в таблицу, петля продолжается."
)


# ── active_medium_tier_undriven (0x 2026-08-18, the operator «Medium ищется НАРАВНЕ, а они его забывают») ──
# 0x-дыра ≠ veda: 0x структурно забанчил + T6 прогнал, НО банк ВЕСЬ Low/info (0 Medium) — Medium-тир как
# ВЫДЕЛЕННЫЙ DRIVE не гонялся (griefing/temp-freeze/gas-DoS/positive-slippage/permanent-freeze), банчил
# только incidental Low при Crit/High-охоте. Measure-first: severity в ГИПОТЕЗАХ машинно НЕ тегается,
# «Medium» в прозе = boilerplate 30+ (мандат/шаблон) → детект по тексту фрагилен. НАДЁЖНО парсится severity-
# колонка таблицы ## Banked Findings. Fire ⇔ T6-pass DONE (банк «завершён» = wind-down) И ≥1 banked-row
# И ВСЕ Low/info-тир (0 Medium/High/Crit) И нет `Medium-tier`-маркера. Satisfiable: гони Medium как DRIVE
# (→ Medium-строка) ИЛИ отметь `Medium-tier: driven — refuted <falsifier>` (честный «гнал, нет Medium»).
# Off: MANUAL/OFF, HUNT-EXIT, T6 не DONE (банк копится → composite ведёт), пустой банк (prose/atom-гейты),
# есть Medium+ строка, есть маркер. Satisfiable soft-nudge (banked Low петлю не завершают).
_MEDPLUS_SEV_RE = re.compile(r"med(?:ium)?|high|crit", re.I)
_MEDIUM_TIER_MARKER_RE = re.compile(r"(?i)\bmedium[\s\-]?(?:tier|pass|drive|sweep|свип)\b")


def _banked_row_severities(ledger_text):
    """Severity-ячейки (cells[1]) реальных строк ## Banked Findings. [] — таблица пуста/нет секции."""
    sec = _banked_section(ledger_text)
    if not sec:
        return []
    out = []
    for line in sec.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        joined = "".join(cells)
        if not joined or set(joined) <= set("-: "):
            continue
        low = " ".join(cells).lower()
        if "severity" in low and "h-nn" in low:
            continue
        if cells[1].strip().lower() in ("severity", "sev"):  # header-остаток (короткий хедер без H-NN)
            continue
        subst = [c for c in cells if c and c != "-"]
        if len(subst) >= 2 and len(cells) >= 2:
            out.append(cells[1])
    return out


def _has_medium_tier_marker(ledger_text):
    """Хантер ЯВНО отметил Medium-тир как DRIVE (строка `Medium-tier`/`Medium Pass`/`Medium-drive` с
    контентом) — не blockquote-инструкция / не `{}`-плейсхолдер / не header-без-контента."""
    for line in (ledger_text or "").splitlines():
        s = line.lstrip()
        if s.startswith(">") or "{" in line:
            continue
        if not _MEDIUM_TIER_MARKER_RE.search(line):
            continue
        tail = line.split(":", 1)[-1] if ":" in line else ""
        if s.startswith("#"):                              # `## Medium Pass` header — нужен контент под ним, не само имя
            continue
        if len(tail.replace("*", "").replace("`", "").strip()) >= 8:
            return True
    return False


def active_medium_tier_undriven(current_sid):
    """0x: банк ВЕСЬ Low + T6 done → Medium-тир не гонялся выделенным DRIVE. Fire ⇔ T6-DONE И ≥1 banked-row
    И все Low/info-тир И нет Medium-маркера. Off: MANUAL/OFF, HUNT-EXIT, T6 не DONE, пустой банк, есть
    Medium+ строка/маркер. Satisfiable soft-nudge. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _banked_t6_done_count(lt) is None:
        return None                                        # банк ещё не «завершён» T6-пассом → рано (composite ведёт)
    if _banked_rows(lt) < 1:
        return None                                        # пустой банк (проверенный счётчик) → prose/atom-гейты, не сюда
    sevs = _banked_row_severities(lt)
    if not sevs:
        return None
    if any(_MEDPLUS_SEV_RE.search(s) for s in sevs):
        return None                                        # ≥1 Medium/High строка → тир затронут
    if _has_medium_tier_marker(lt):
        return None                                        # явно отмечен Medium-DRIVE (гнал, нет → refuted)
    return os.path.relpath(ledger, root)


MEDIUM_TIER_UNDRIVEN_REASON = (
    "MEDIUM TIER UNDRIVEN (0x 2026-08-18, the operator «Medium ищется НАРАВНЕ с High/Crit, а вы его забываете»). "
    "Ledger `%s`: T6-пасс по банку DONE, но банк ВЕСЬ Low/info — НИ ОДНОЙ Medium-строки. Значит Medium-тир "
    "ты не гнал как ВЫДЕЛЕННЫЙ DRIVE, а забанчил только incidental Low при Crit/High-охоте. Medium = "
    "полноценный DRIVE (глубже сразу, не «по пути»; выплаты $2-5K+): прогони Medium-СПЕЦИФИЧНЫЕ классы "
    "СИСТЕМАТИЧЕСКИ — griefing · temporary-freezing · gas-griefing/DoS · positive-slippage/value-leak · "
    "permanent-freeze · rounding/dust-accrual · MEV-grief — каждый как гипотеза из КОДА (prediction + "
    "`file:line` + falsifier), не чеклистом. Найдено → строка в `## Banked Findings` (push ceiling→High). "
    "Genuinely нет Medium → отметь `Medium-tier: driven — refuted <класс/falsifier>` (честный «гнал, чисто»). "
    "Satisfiable — прогони тир, петля продолжается (Medium банк её НЕ завершает)."
)


BANKED_OOS_REASON = (
    "BANKED OOS-CHECK UNCHECKED (money-critical, 2026-08-11). Ledger `%s`: есть banked finding(s) и "
    "реально захваченный Out-of-Scope список, но НЕТ валидной `OOS-CHECK:` строки — banked Medium/Low "
    "уйдут batch'ем БЕЗ сверки с дисквалификаторами. Ровно тот промах, что закрыл репорт 2026-08-10, и "
    "OOS чаще бьёт по Medium (centralization/trusted-actor редко Critical). ПЕРЕД подачей banked сверь "
    "КАЖДУЮ находку с Out-of-Scope дисквалификаторами из шапки и впиши `OOS-CHECK: <находка> vs "
    "out-of-scope → PASS` (чиста) ЛИБО `→ DISQUALIFIED: <clause>` (попадает → НЕ подавай эту, убери из "
    "banked). Особо: зависит ли impact от промаха trusted-актора (oracle/keeper/multisig/admin) → почти "
    "всегда centralization-clause = OOS. Satisfiable — сверь и впиши вердикт (не голое `OOS-CHECK:`)."
)


# ── FEAT-L (jito-live 2026-08-12): value-at-risk структурное. `attack_ev_estimate.py`/`fork_profit_delta.py`
# готовы, но $-at-risk не квантифицируется структурно перед подачей → приоритет подачи (Reliability×$-at-risk,
# FEAT-A даёт Reliability) не считается. R10 SAFETY: magnitude/$-at-risk мерится ТОЛЬКО на ФОРКЕ (CLAUDE.md
# запрет live-state/market-manip). Комплемент moneylead_shallow (тот форсит DEPTH на money-lead; этот —
# КВАНТИФИКАЦИЮ $ перед подачей). Soft-nudge, banked-scope (как banked_without_oos_check).
# parenthetical-tolerant (Z2 судья MED): шаблон-поле `**Value-at-risk (FEAT-L — …):**` — скобка перед `:`.
_VALUE_AT_RISK_RE = re.compile(r"^\s*[-*]?\s*\*{0,2}\s*value[\s-]*at[\s-]*risk\s*(?:\([^)]*\))?\s*\*{0,2}\s*[:=]", re.I)


def _value_at_risk_quantified(lt):
    """Поле `Value-at-risk:` несёт РЕАЛЬНОЕ число ($/сумма), не `{плейсхолдер}`/пусто. Число = квантификация."""
    for line in (lt or "").splitlines():
        if not _VALUE_AT_RISK_RE.match(line):
            continue
        val = (line.split(":", 1)[-1] if ":" in line else line.split("=", 1)[-1])
        val = val.replace("*", "").replace("`", "").strip()
        if "{" in val or not val:
            continue
        if re.search(r"\d", val):
            return True
    return False


# ── FEAT-K (jito-live 2026-08-12): banked-staleness. banked finding долго лежит (хант тянется) → перед
# batch-submit re-check freshness (Templar-урок: deployed≠HEAD, «жив сегодня vs спящий» применим и к банку —
# код мог зафикситься/измениться, пока находка ждала подачи). FEAT-D (banked auto-rerun) = SUD-MED-2 (banked-T6
# DONE(N=k) re-arm на рост); ЗДЕСЬ — K (staleness re-check перед подачей). Порог iter — banked успел устареть.
_FRESHNESS_RE = re.compile(
    r"freshness[-\s]?check|still[-\s]?live|re-?check\s+live|deployed[\s=]+HEAD|жив\s+сегодня|"
    r"live-?current\s+re-?verif|banked[-\s]?freshness", re.I)
BANKED_STALENESS_ITER = 10   # banked лежит ≥N итераций → re-check перед подачей (ретюн-точка)


def active_banked_staleness_unchecked(current_sid):
    """FEAT-K: ≥1 banked finding + хант тянется (iter≥BANKED_STALENESS_ITER = banked успел устареть) +
    нет freshness-check записи → перед batch-submit re-check жив ли баг (deployed≠HEAD, live-current не
    forkable history). Off: MANUAL/OFF, HUNT-EXIT, 0 banked, короткий хант, freshness сделан. Soft-nudge."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _banked_rows(lt) < 1:
        return None
    if _loopstate_iter(lt) < BANKED_STALENESS_ITER:
        return None                                      # хант ещё короткий — banked свежий
    if _line_signal_present(lt, _FRESHNESS_RE):
        return None                                      # freshness-check сделан (не плейсхолдер/инструкция)
    return os.path.relpath(ledger, root)


BANKED_STALENESS_REASON = (
    "BANKED STALENESS UNCHECKED (FEAT-K, jito-live 2026-08-12). Ledger `%s`: есть banked finding(s), хант "
    "тянется ≥%d итераций — banked лежит давно и мог УСТАРЕТЬ. Templar-урок: deployed≠HEAD, «жив сегодня vs "
    "спящий» применим и к БАНКУ (код мог зафикситься/измениться, пока находка ждала batch-submit; "
    "precondition, что был живым на iter 3, к iter %d мог исчезнуть). ПЕРЕД подачей re-check КАЖДУЮ banked: "
    "(1) deployed-код == тот, где нашёл (code_hash / re-read live) — не HEAD-фикс; (2) precondition жив "
    "СЕЙЧАС (live-current, не forkable history — eth_call state-override / re-run PoC на свежем форке). "
    "Впиши `banked-freshness: <находка> — still-live / STALE (убрать)`. Это НЕ выход петли (satisfiable, soft)."
)


def active_value_at_risk_unquantified(current_sid):
    """FEAT-L: ≥1 banked confirmed finding, но $-at-risk не квантифицирован структурно (`Value-at-risk:` с
    числом) → nudge оценить через `fork_profit_delta.py`/`attack_ev_estimate.py` НА ФОРКЕ (R10 SAFETY:
    magnitude только на форке). Reliability × $-at-risk = приоритет подачи. Off: MANUAL/OFF, HUNT-EXIT,
    0 banked, уже квантифицировано. Soft-nudge. relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _banked_rows(lt) < 1:
        return None
    if _value_at_risk_quantified(lt):
        return None
    return os.path.relpath(ledger, root)


VALUE_AT_RISK_REASON = (
    "VALUE-AT-RISK UNQUANTIFIED (FEAT-L, jito-live 2026-08-12). Ledger `%s`: есть banked confirmed "
    "finding(s), но $-at-risk не квантифицирован структурно. Приоритет подачи = **Reliability × $-at-risk** "
    "(Reliability — FEAT-A); без $-числа приоритет не посчитать, и severity-калибровка держится на глаз. "
    "СЕЙЧАС: для каждой находки оцени сумму под угрозой через `fork_profit_delta.py` / `attack_ev_estimate.py` "
    "и впиши `Value-at-risk: $<число> (fork: <артефакт>)`. ⚠ **R10 SAFETY: magnitude/$-at-risk мерится "
    "ТОЛЬКО на ФОРКЕ** (CLAUDE.md запрет live-state-mutation / market-manipulation — probe-swap / триггер "
    "каскада / live-bid = ЭКСПЛУАТАЦИЯ, не верификация). Это НЕ выход петли (satisfiable, soft)."
)


BANKED_COMPOSITE_REASON = (
    "BANKED T6-PASS UNCHECKED (A5, Волна 1 2026-08-08; ⚠ target-правка the operator 2026-08-12). Ledger `%s`: ≥2 "
    "confirmed banked findings, но T6-пасс по БАНКУ не отмечен. banked = ДОКАЗАННЫЕ building-blocks — ПЕРЕД "
    "batch-submit пройди пары `output→input`. ⚠ **ЦЕЛЬ = ЛЮБАЯ эскалация до Medium+, НЕ только Critical** "
    "(частый промах: «не дотянул до Crit → DONE» — НЕВЕРНО): Low×Low → **Medium** (два leak = precondition), "
    "Low+Medium → **High**, Medium×Medium → **High/Crit**. Любой severity-boost через складывание = находка. "
    "⚠ **Не «очевидные пары», а CROSS-THREAD через ДАЛЁКИЕ подсистемы/репо** — un-dup живёт в стыке далёких "
    "модулей (ethena-промах: D-03 UStb-self-burn × D-08 OFT-adapter × D-01 silo-exit = ОДИН класс через 3 "
    "разных репо, назван «паттерном» прозой, но НЕ сложен в находку). ⚠ синтез = ОДИН агент над ВСЕМ банком, "
    "НЕ дроби по подсистемам (партиция рушит кросс-пару по построению — enzyme A74×A75 промах). "
    "Переиспользуй chain-dependency guard "
    "(нужен доказанный A.output→B.input, ложные цепочки не форси). Затем впиши `Banked T6-pass:** DONE — "
    "chain: banked-X.output→banked-Y.input (severity → Medium/High/Crit)` ЛИБО `DONE — no chainable pairs "
    "(проверил cross-thread пары из РАЗНЫХ подсистем, эскалации до Medium+ нет: <почему>)`. Голое «no "
    "chainable Crit» без cross-thread-разбора = ленивый пасс. ⚠ **SUD-MED-2 (the operator 2026-08-12): помечай "
    "`DONE (N=<число banked на момент пасса>)`** — банк РАСТЁТ, и при новых banked (banked>N) гейт СНОВА "
    "поднимется (T6-пасс не одноразовый: пары надо перепроверять по мере роста). Старый `DONE` без N "
    "снимает разово (legacy). Satisfiable, НЕ выход петли."
)


# ══════════════════════════════════════════════════════════════════════════════
# WORKLIST DRIVER — Этап 1: реестр атомов (`## Atom Registry`) + 2 гейта (за WORKLIST_DRIVER_ENABLED).
# План: methodology/plans/worklist_driver_plan.md §1 (Слой 1) / §3 (Этап 1) / §8 (C1/C2/C3).
# Реестр = машинная проекция worklist'а с ЕДИНЫМ ключом `id`. Формат строки:
#   | id | type | title | src | rank | status | closes |
# Anti-gaming (template Rule): строка без РЕАЛЬНОГО `rank`/`src` (`{...}`/`TBD`) НЕ атом. Оба гейта
# МОЛЧАТ без секции `## Atom Registry` (C1: web/legacy-ledger не ловятся ложно) и без валидных атомов
# (первый проход). Читают ledger НАПРЯМУЮ (реестр живёт и на `MODEL: N/A`), как active_axis_queue_empty.
_ATOM_REG_HDR_RE = re.compile(r"(?im)^\s*##\s+Atom\s+Registry\b")
_CURRENT_PICK_RE = re.compile(r"(?im)^\s{0,3}-\s+\*\*\s*current\s+pick\s*:\s*\*\*\s*(.*)$")
_ATOM_STUB_RE = re.compile(r"^(tbd|todo|none|later|\?+|-{1,}|—+|–+)$", re.I)


def _id_match_in_text(atom_id, text):
    """Токен-точное вхождение id, ТОЛЕРАНТНОЕ к zero-padding с ОБЕИХ сторон (судья-1 D1/D2, судья-2):
    `AX-4`↔`AX-04`, `H-9`↔`H-09` матчатся в любом направлении, но `AX-4` НЕ матчит `AX-40`
    (word-boundary + `(?![0-9])`). Формат id `<PREFIX>-<NN>` (≤6 букв-префикс) → паттерн `PREFIX-0*NN`;
    иначе точный re.escape с alnum-границами."""
    aid = (atom_id or "").strip()
    m = re.match(r"^([A-Za-z]{1,6})-0*(\d+)$", aid)
    if m:
        pat = r"(?<![A-Za-z0-9])" + re.escape(m.group(1)) + r"-0*" + m.group(2) + r"(?![0-9])"
    else:
        pat = r"(?<![A-Za-z0-9])" + re.escape(aid) + r"(?![A-Za-z0-9])"
    return bool(re.search(pat, text or "", re.I))


# C3 proof = id атома на строке С РЕАЛЬНЫМ ЗАКРЫВАЮЩИМ маркером, ГДЕ УГОДНО вне таблицы реестра. Marker-
# based, НЕ section-name-based (round-2 FP-1: точный матч имени резал легит `## Refuted Hypotheses`).
# ⚠ Маркеры СЕМАНТИЧЕСКИ-СТРОГИЕ (round-3 red-team: marker-anywhere реоткрыл Notes-bypass — слово
# `verdict:`/`proof:` в НЕ-закрывающем контексте `verdict: pending`/`нужен proof:` фейкало proof): маркер
# сам обязан кодировать ЗАКРЫТИЕ. Kill-tag (БЕЗ `[LOW-DEFERRED]` — это «не закрыто, building-block»),
# `killed by`, `verdict:` ТОЛЬКО с реальным вердиктом (kill/confirm/downgrade/refute/invalid), `close-grade:`
# (Axes-Closed). Голый `proof:` УБРАН (слишком широк). Same-line = закрывающая запись this-id (без cross-
# contamination), section-name-агностично (как читают 39 прозо-гейтов: `[KILLED]` = закрытие где угодно).
_C3_MARKER_RE = re.compile(
    r"\[(KILLED|CONTESTED|SCOPED-OUT|DE-MINIMIS|ASSUMED-CANONICAL)\]"
    r"|killed\s+by"
    r"|verdict\s*:\s*(kill|confirm|downgrade|refut|invalid|valid|no[\s-]?bug)"
    r"|close-grade\s*:", re.I)


def _registry_line_span(ledger_text):
    """(start, end) индексы строк секции `## Atom Registry` (заголовок..след. `## `), либо None."""
    lines = (ledger_text or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        if _ATOM_REG_HDR_RE.match(line):
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return (start, end)


def _c3_proof_lines(ledger_text):
    """Строки ledger'а ВНЕ таблицы реестра — среди них ищется `id + proof-маркер` (C3)."""
    lines = (ledger_text or "").splitlines()
    span = _registry_line_span(ledger_text)
    if span is None:
        return lines
    return [l for i, l in enumerate(lines) if not (span[0] <= i < span[1])]


def _atom_registry_section(ledger_text):
    """Тело секции `## Atom Registry` (от строки после заголовка до следующей `## `). None — секции нет
    вовсе (C1: web/legacy-ledger до Worklist Driver → anti-FP, гейт молчит)."""
    lines = (ledger_text or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        if _ATOM_REG_HDR_RE.match(line):
            start = idx
            break
    if start is None:
        return None
    out = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


# SUD-LOW-1 + R2 (jito-live 2026-08-12): единый status-normalizer атомов реестра. jito нёс неканонические
# статусы (CLOSED(ВЕЕР)/RUNNING/REFUTED/BANKED) → driver-логика (status in OPEN/ACTIVE, ==CLOSED) их не
# распознавала → атомы в статус-ЛИМБЕ (ни закрыт, ни открыт). Канон = 5 значений: OPEN/ACTIVE/CLOSED/
# BANKED/PARKED. Скобочный суффикс срезается (`CLOSED(веер)`→CLOSED). Неизвестный статус → passthrough
# (upper), не теряется. BANKED/PARKED сохранены (спец-обработка banked-гейтов / park-семантики).
_ATOM_STATUS_CANON = {
    "OPEN": "OPEN", "PENDING": "OPEN", "QUEUED": "OPEN", "TODO": "OPEN", "NEW": "OPEN",
    "ACTIVE": "ACTIVE", "RUNNING": "ACTIVE", "IN-FLIGHT": "ACTIVE", "INFLIGHT": "ACTIVE",
    "IN-PROGRESS": "ACTIVE", "DRIVING": "ACTIVE", "WIP": "ACTIVE",
    "CLOSED": "CLOSED", "REFUTED": "CLOSED", "KILLED": "CLOSED", "DONE": "CLOSED",
    "RESOLVED": "CLOSED", "DEAD": "CLOSED", "DUPLICATE": "CLOSED", "DEDUP": "CLOSED",
    "BANKED": "BANKED", "PARKED": "PARKED",
}


def _norm_atom_status(raw):
    """SUD-LOW-1: канонизирует статус атома реестра к 5 значениям (OPEN/ACTIVE/CLOSED/BANKED/PARKED).
    Синонимы (RUNNING→ACTIVE, REFUTED/KILLED/DONE→CLOSED, PENDING/QUEUED→OPEN) + скобочный суффикс
    (`CLOSED(веер)`→CLOSED). Неизвестный → passthrough (upper), не теряется."""
    s = _norm_status(raw)                       # markdown-strip + upper
    if not s:
        return ""
    s = re.sub(r"\s*\([^)]*\)\s*", "", s).strip()   # CLOSED(ВЕЕР) → CLOSED
    return _ATOM_STATUS_CANON.get(s, s)


def _atom_rows(ledger_text):
    """Строки-атомы реестра как список dict'ов {id,type,title,src,rank,status,closes}. None — секции
    нет (C1 silent). `rank` = float либо None (не-число / `{...}`-placeholder). Header/separator/
    placeholder-строки (`{` в id) отфильтрованы. НЕ фильтрует по статусу/rank — вызывающий решает
    (pick-logic берёт _valid_atoms с real rank+src; C3 берёт CLOSED-строки независимо от rank)."""
    sec = _atom_registry_section(ledger_text)
    if sec is None:
        return None
    rows = []
    for line in sec.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 6:
            continue
        aid = cells[0].replace("*", "").replace("`", "").strip()
        if not aid or "{" in aid:
            continue                                       # placeholder / template-строка = не атом
        low = aid.lower()
        if low in ("id", "atom_id"):
            continue                                       # header
        if set(aid) <= set("-: "):
            continue                                       # separator
        rankcell = cells[4] if len(cells) > 4 else ""
        rank = None
        if "{" not in rankcell:
            m = re.search(r"-?\d+(?:\.\d+)?", rankcell)
            if m:
                rank = float(m.group(0))
        rows.append({
            "id": aid,
            "type": (cells[1].replace("*", "").replace("`", "").strip().lower() if len(cells) > 1 else ""),
            "title": (cells[2].strip() if len(cells) > 2 else ""),
            # src — grounding-критичное поле: снимаем markdown-emphasis (`*`/`_`/backtick) КАК sibling-
            # ячейки (red-team #3 MED-1: `**D-99**`/`*I-99*` якорь `^` роняли → атом «label» → ВЕСЬ
            # src-gate молча обходился; в отрендеренной таблице bold-id идентичен легит-рефу).
            "src": (cells[3].replace("*", "").replace("_", "").replace("`", "").strip() if len(cells) > 3 else ""),
            "rank": rank,
            "status": _norm_atom_status(cells[5]) if len(cells) > 5 else "",
            "closes": (cells[6].replace("*", "").replace("`", "").strip() if len(cells) > 6 else ""),
        })
    return rows


def _src_real(src):
    """src засчитывается как реальный (не заглушка): непусто, без `{`, не tbd/todo/none/`-`/`—`."""
    v = (src or "").strip().strip("<>").strip()
    if not v or "{" in v:
        return False
    return not _ATOM_STUB_RE.match(v)


def _valid_atoms(rows):
    """Атомы, засчитываемые в worklist (anti-gaming template Rule): реальный ЧИСЛОВОЙ rank И реальный src."""
    return [r for r in rows if r["rank"] is not None and _src_real(r["src"])]


def _current_pick(ledger_text):
    """Значение поля Loop State `- **Current pick:**` (без markdown-обёртки). '' — поля нет."""
    m = _CURRENT_PICK_RE.search(ledger_text or "")
    if not m:
        return ""
    return m.group(1).replace("*", "").replace("`", "").strip()


def _pick_is_real(pick):
    """pick указывает на реальную цель (не placeholder/`none`/`-`)."""
    if not pick or "{" in pick:
        return False
    low = pick.strip().lower()
    return not low.startswith(("none", "-", "—", "–", "n/a", "tbd", "todo"))


RANK_MAX = 80.0   # потолок формулы rank = severity_w(≤4)×conf(≤1.0)×undup(≤2.0)×10 = 80; выше = невозможно


def _pick_target(rows, pick):
    """Атом реестра, на который ссылается `Current pick`: сначала по id (padding-толерантно), затем по
    COMPOUND-title (несёт `-`/`_`/пробел — распознаваемо-специфичный, не одно общее слово). None — pick
    не ссылается ни на один атом. ⚠ Только compound-title (red-team FN-2): чистый `len>=8` пропускал
    длинные ОДНОСЛОВНИКИ (`liquidation`/`transfer`/`governance`), рутинно встречающиеся в drift-прозе →
    маскировали дрейф. Compound-признак (`liquidation-band`) специфичен, общее слово — нет."""
    for r in rows:
        if _id_match_in_text(r["id"], pick):
            return r
    low = (pick or "").lower()
    # ⚠ САМЫЙ ДЛИННЫЙ (специфичный) compound-title-матч, НЕ первый (red-team round-3 FP: `band-drift`
    # (early row) выигрывал у `liquidation-band-drift` (голова) → order-dependent ложный 2b-FIRE).
    best = None
    for r in rows:
        t = (r["title"] or "").strip()
        if t and any(c in t for c in "-_ ") and t.lower() in low:
            if best is None or len(t) > len((best["title"] or "").strip()):
                best = r
    return best


def _patchdiff_bonus(atom):
    """G-patchdiff (§8): src помечен patch-diff/T5-seed (аудит-дифф → «go FIRST») → tie-break-буст
    ТОЛЬКО при РАВНОМ rank (rank доминирует; на не-tie иррелевантен). Не меняет ни одного FIRING-
    решения pick-гейта (клауза 3 сравнивает rank-ЗНАЧЕНИЯ, ties не фаирят) — только КАКОЙ id назван
    головой при точном равенстве. 1/0."""
    s = (atom.get("src") or "").lower()
    return 1 if ("patch" in s or "t5-seed" in s or "diff-seed" in s) else 0


def _registry_head(oa):
    """Атом-ГОЛОВА = max-rank среди OPEN∪ACTIVE. Tie-break: (rank, patch-diff-буст, id) — на РАВНОМ
    rank patch-diff-seeded атом впереди (§8 G-patchdiff), иначе детерминированно по id. None — oa пусто."""
    if not oa:
        return None
    return max(oa, key=lambda a: (a["rank"], _patchdiff_bonus(a), a["id"]))


def _atom_str(atom):
    """Человекочитаемое имя КОНКРЕТНОГО атома: `AX-04` (band-regression, rank 35, src D-05). src =
    origin-указатель «откуда атом» (судья-B Д3: даёт «куда смотреть», не только «что гнать»). None → заглушка."""
    if atom is None:
        return "(нет атома)"
    src = (atom.get("src") or "").strip()
    srcpart = (", src %s" % src) if src and src not in ("-", "—", "–") else ""
    return "`%s` (%s, rank %g%s)" % (atom["id"], (atom["title"] or "—").strip(), atom["rank"], srcpart)


def _head_str(oa):
    """Человекочитаемое имя ГОЛОВЫ реестра (compute-and-name) для pick-гейта / HANDOFF."""
    h = _registry_head(oa)
    if h is None:
        return "(в реестре нет ни одной OPEN/ACTIVE-строки — заведи голову с rank)"
    return _atom_str(h)


def active_pick_not_from_queue(current_sid):
    """Worklist Driver Этап 1 (livepeer-fix). Держит выход, когда `Current pick` расходится с
    вычисленной ГОЛОВОЙ реестра: (1) >1 ACTIVE-строки; (2) pick реальный, но НЕ ссылается ни на один
    атом (по id ИЛИ compound-title) — импровизация мимо worklist'а; (2b) ровно 1 ACTIVE, а pick
    ссылается на ДРУГОЙ атом (pick≠ACTIVE-маркер desync — red-team FN-1); (3) гонимый атом НЕ max-rank
    среди OPEN∪ACTIVE (ловится и при 0 ACTIVE — судья-2 D3); (4) rank OPEN/ACTIVE-кандидата > 80
    (rank-gaming). Off-switch: флаг off; секции нет (C1); нет валидных атомов; MANUAL/OFF; HUNT-EXIT.
    Возвращает (relpath, head_str) для compute-and-name directive, либо None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None                                        # аварийный ручной режим
    if _has_valid_exit(lt):
        return None                                        # хант завершён T4 High/Crit
    rows = _atom_rows(lt)
    if rows is None:
        return None                                        # C1: секции нет → silent (web/legacy)
    atoms = _valid_atoms(rows)
    if not atoms:
        return None                                        # первый проход — реестр ещё пуст
    # SUD-LOW-1: fanout-атом (веер, RUNNING→ACTIVE) = ПАРАЛЛЕЛЬНАЯ генерация, НЕ второй single-pick DRIVE —
    # исключаем из active/oa-подсчёта, иначе «веер RUNNING + основной ACTIVE» = ложный «>1 ACTIVE».
    _pk = [a for a in atoms if (a.get("type") or "").strip().lower() != "fanout"]
    active = [a for a in _pk if a["status"] == "ACTIVE"]
    oa = [a for a in _pk if a["status"] in ("OPEN", "ACTIVE")]
    hit = (os.path.relpath(ledger, root), _head_str(oa))
    # (1) больше одной ACTIVE — single-pick нарушен
    if len(active) > 1:
        return hit
    # (4) rank-gaming: OPEN/ACTIVE-кандидат с rank выше формульного потолка = липовая «голова».
    #     Только oa (не CLOSED/PARKED — их устаревший rank к выбору головы иррелевантен, red-team FP #4).
    if any(a["rank"] > RANK_MAX for a in oa):
        return hit
    pick = _current_pick(lt)
    picked = _pick_target(rows, pick) if _pick_is_real(pick) else None
    # (2) pick реальный, но не ссылается НИ НА ОДИН атом реестра → импровизация мимо worklist'а
    if _pick_is_real(pick) and oa and picked is None:
        return hit
    # (2b) ровно 1 ACTIVE, но pick ссылается на ДРУГОЙ атом → pick↔ACTIVE-маркер рассинхрон (red-team
    #      FN-1): держишь голову ACTIVE, а pick гонит нижний атом — оба «валидны», но расходятся.
    if len(active) == 1 and picked is not None and picked["id"] != active[0]["id"]:
        return hit
    # (3) гонимый атом не max-rank → пропустил голову очереди. Ровно 1 ACTIVE = машинная ИСТИНА того,
    #     что гонится (status-маркер авторитетнее pick-текста). При 0 ACTIVE → pick-target (судья-2 D3).
    drive = active[0] if len(active) == 1 else (
        picked if (picked is not None and picked.get("rank") is not None) else None)
    if drive is not None and oa and drive["rank"] < max(a["rank"] for a in oa):
        return hit
    return None


PICK_NOT_FROM_QUEUE_REASON = (
    "PICK-NOT-FROM-QUEUE (Worklist Driver Этап 1, 2026-08-11 — livepeer-fix). Ledger `%s`: твой "
    "`Current pick` РАСХОДИТСЯ с головой машинного реестра `## Atom Registry`. Это ровно та болезнь "
    "(livepeer при смене оси): очередь НЕпуста, а ты пошёл СВОИМ путём мимо неё. **ГОЛОВА РЕЕСТРА = %s "
    "— гони ЕЁ** (не выбирай заново каждый ход). Приведи в порядок ОДНО из: (1) если >1 строки `ACTIVE` "
    "— оставь РОВНО ОДНУ (single-pick), остальные верни в `OPEN`/`PARKED`; (2) если гонишь цель, которой "
    "НЕТ строкой в реестре — заведи её `| id | type | title | src | rank | status:ACTIVE | closes |` "
    "(rank = severity_w×confidence_w×undup_mult×10, ≤80), ЛИБО переключись на голову выше; (2b) если "
    "pick и `ACTIVE`-строка указывают на РАЗНЫЕ атомы — синхронизируй их (pick = id той строки, что "
    "`ACTIVE`); (3) пометь ГОЛОВУ `ACTIVE` и впиши её `id` в `Current pick`; хочешь легитимно гнать "
    "нижнюю по rank — СНАЧАЛА переоцени rank головы (park/понизь с обоснованием); (4) rank > 80 "
    "невозможен по формуле — не раздувай rank, чтобы липовая ось стала головой. Это НЕ выход петли "
    "(satisfiable) — синхронь pick с головой и копай."
)


def _closed_atoms(rows):
    return [r for r in rows if r["status"] == "CLOSED"]


def active_atom_closed_without_narrative(current_sid):
    """Worklist Driver Этап 1 — связка-гейт C3 (аудит §8). Атом реестра со `status: CLOSED`, чьё `id`
    НЕ встречается НИГДЕ в нарративе вне самой таблицы реестра (нет `### H-NN` в `## Refuted`, нет
    записи в `## Verifier Log`/`## Axes-Closed`/per-iteration-trace), = «закрыт на бумаге реестра, но
    без proof-записи». Это КРИТ-дыра C3: 39 существующих гейтов (exhaustion-shape, T4-integrity, kill-
    taxonomy) читают ПРОЗУ, а не реестр — фейковый CLOSED в реестре ослепил бы их. Держим выход, пока
    proof-запись не появится. Off-switch: флаг off; секции нет (C1); нет CLOSED-строк; MANUAL/OFF;
    HUNT-EXIT. Читает ledger напрямую. Satisfiable soft-nudge. relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    rows = _atom_rows(lt)
    if rows is None:
        return None                                        # C1: секции нет → silent
    closed = _closed_atoms(rows)
    if not closed:
        return None
    proof_lines = _c3_proof_lines(lt)                      # строки ledger'а ВНЕ таблицы реестра
    for a in closed:
        proven = any(_id_match_in_text(a["id"], l) and _C3_MARKER_RE.search(l) for l in proof_lines)
        if not proven:
            return os.path.relpath(ledger, root)           # CLOSED без proof-маркера → прозо-гейты слепнут
    return None


ATOM_CLOSED_NO_NARRATIVE_REASON = (
    "ATOM-CLOSED-WITHOUT-NARRATIVE (Worklist Driver Этап 1, связка-гейт C3, 2026-08-11). Ledger `%s`: "
    "в `## Atom Registry` есть строка со `status: CLOSED`, но её `id` НЕ встречается в РЕАЛЬНЫХ proof-"
    "секциях (`## Refuted` / `## Verifier Log` / `## Axes-Closed`). Это опасно: 39 существующих "
    "completeness-гейтов (FALSE-EXHAUSTION shape, T4-integrity, kill-taxonomy) читают ИМЕННО эти секции, "
    "а НЕ реестр — «закрытие» только строкой реестра (или голое упоминание id в `## Notes`) их ОСЛЕПЛЯЕТ, "
    "и недокоп маскируется под «исчерпано». Впиши РЕАЛЬНУЮ proof-запись под этот `id`: для гипотезы "
    "H-NN — `### H-NN [KILLED]` с falsifier `file:line` в `## Refuted` (или `[CONTESTED]`, если guard "
    "не provably достаточен) ЛИБО запись в `## Verifier Log`; для оси — буллет в `## Axes-Closed` с "
    "`close-grade` + `proof`. Затем оставь строку реестра `CLOSED`. Это НЕ выход петли (satisfiable) — "
    "proof восстанавливает связь реестр↔нарратив, и прозо-гейты снова видят."
)


# ДВЕ ФОРМЫ id-src, проверяемые ПРОТИВ РАЗНЫХ поверхностей (Волна web red-team MED-фикс, 2026-08-11):
#  • `D-NN`/`H-NN`/`BB-NN` (дивергенция/гипотеза/BB — namespace УНИВЕРСАЛЕН contract+web) → existence-чек
#    в ПРОЗЕ ЛЕДДЖЕРА (`_c3_proof_lines`), т.к. эти записи живут в ledger'е.
#  • `I-NN`/`TB-INN`/`AC-INN` (ИНВАРИАНТ — contract `I-01`, web `TB-I01`/`AC-I01`, namespaced `W3-I1`) →
#    existence-чек в `system_model.md` (`_norm_inv`/`_model_invariant_ids`, СИММЕТРИЧНАЯ канонизация,
#    извлечение из строк-деклараций, не whole-prose), т.к. инварианты живут ТАМ.
# Прежний вывод «инвариант в ледджере нет → трактуем как label» был НЕВЕРЕН (red-team): проверять надо по
# МОДЕЛИ (гейтам доступна), а не сдаваться. Иначе сфабрикованная голова `src: TB-I99` (несущ. инвариант)
# проходит молча, и driver АКТИВНО её диктует — ровно тот laundered-wrong-axis дрейф, что C3 ловит для D-NN.
# web строго хуже contract был именно потому, что web-placeholder РЕКЛАМИРУЕТ TB-I/AC-I как src (для
# dapphunt/web2 инвариант-валидирующая ось легитимна); теперь оба канала проверяются симметрично.
# Дефис/форма ОБЯЗАТЕЛЬНЫ (red-team RT-Д1): `-?` FP-фаирил на free-text метках `D3-fork`/`BB8`/`H2-audit`;
# `D-` требует, чтобы это был настоящий id-референс (`D-99`), а не метка с цифрой. `\b` после цифр
# допускает аннотацию (`D-05 (band)`) и multi-src (`H-05,H-06` → чекается первый). Leading-noise
# (`див D-99`) не матчит `^` → трактуется как label (осознанный escape, симметрия C3, RT-Д2).
_SRC_ID_RE = re.compile(r"^(D|H|BB)-(\d+)\b", re.I)

# ЕДИНАЯ канонизация инвариант-id для src-grounding — СИММЕТРИЧНА на src- и model-стороне (red-team #2
# HIGH-1: раньше src-сторона namespace СОХРАНЯЛА, а model-сторона его РОНЯЛА `VAULT-I03`→`I-3`, и любой
# `I-\d` из ПРОЗЫ модели заземлял фикцию). Namespace ≤8 симв. (MED-2: `VAULT`/`ORACLE`-инварианты больше не
# утекают в label). D/H/BB как namespace ЗАПРЕЩЕНЫ (LOW-1: `D-I01`/`H-I5` = малформ divergence-ref, не
# инвариант). НЕ трогает `_INV_ID` (line 964, hardened model-гейты `_I_ROW_RE`/`_wave_i_counts`) — отдельная.
_INV_ID_SRC_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{0,7}-)?I-?0*(\d+)\b", re.I)
_INV_NS_RESERVED = ("D", "H", "BB")   # divergence/hypothesis/BB namespaces — не инвариант


def _norm_inv(tok):
    """Каноничная форма инвариант-id → (NAMESPACE_upper, int(num)), padding-толерантно (`TB-I1`↔`TB-I01`),
    namespace-preserving (`VAULT-I03`→`('VAULT',3)` ≠ `I-3`). None — не инвариант-форма ИЛИ reserved-ns
    (`D`/`H`/`BB` → малформ divergence-ref, не инвариант). `D-05`/`AX-05` → None (после ns нужен `I`)."""
    m = _INV_ID_SRC_RE.match((tok or "").strip())
    if not m:
        return None
    ns = (m.group(1) or "").upper().rstrip("-")
    if ns in _INV_NS_RESERVED:
        return None
    return (ns, int(m.group(2)))


# ДЕКЛАРАЦИЯ инварианта в модели: table-row `| X-I01 | <непустое описание> | …` ЛИБО bullet-декларация.
# Извлекаем ТОЛЬКО отсюда, НЕ whole-prose grep (red-team #2 HIGH-1: инцидентный `I-7` в прозе ≠ инвариант).
# Blockquote-примеры (`>`) и скелет-строки (пустая ячейка-описание) пропускаются (verifier #1 fail-open).
# Bullet-ДЕКЛАРАЦИЯ = id в начале + ЛИБО bold `**X-I01**`, ЛИБО colon-def `X-I01:` (red-team #3 LOW-1 закрыл
# рыхлый `\*{0,2}`, ловивший прозо-упоминание `- I-9 discussed`; red-team #4 LOW: strict-bold-only ронял
# ЛЕГИТ non-bold `- I-13: LinearCreditDebtTracker…` реальной сессии enzyme-onyx). Дискриминатор
# декларация↔упоминание — id-в-начале-then-(bold|colon), НЕ наличие bold. `- I-9 discussed` (нет `:`/bold),
# `- Important: I-7…` (id не первый) → упоминание, пропуск.
_INV_CORE = r"([A-Za-z][A-Za-z0-9]{0,7}-)?I-?0*\d+"
_INV_BULLET_DECL_RE = re.compile(
    r"^[-*]\s*(?:\*\*\s*" + _INV_CORE + r"\s*\*\*|" + _INV_CORE + r"\s*:)", re.I)


def _model_invariant_ids(model_text):
    """Множество каноничных инвариант-id {(ns, num)} из СТРОК-ДЕКЛАРАЦИЙ модели. Пусто — модели нет /
    инвариантов нет. Симметрично `_norm_inv` (одна канонизация src↔model)."""
    out = set()
    if not model_text:
        return out
    for line in model_text.splitlines():
        s = line.strip()
        if not s or s.startswith(">"):
            continue                                       # blockquote-пример — не декларация
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2 or not cells[1]:
                continue                                   # header/separator/скелет (пустое описание)
            n = _norm_inv(cells[0].replace("*", "").replace("`", ""))
            if n is not None:
                out.add(n)
            continue
        if _INV_BULLET_DECL_RE.match(s):
            n = _norm_inv(re.sub(r"^[-*]\s*(?:\*\*\s*)?", "", s))   # снять `- ` + опц. bold-open → id в начале
            if n is not None:
                out.add(n)
    return out


def active_atom_src_ungrounded(current_sid):
    """Worklist Driver Этап 2 (судья-B Д2, симметрия C3 для OPEN/ACTIVE) + Волна web red-team MED-фикс.
    Валидный OPEN/ACTIVE-атом с id-ФОРМОЙ src, которого НЕТ на его поверхности-обосновании → липовая
    «голова» (laundered-wrong-axis), которую driver активно продиктует. ДВЕ проверяемые формы:
      • `D-NN`/`H-NN`/`BB-NN` → existence в ПРОЗЕ ЛЕДДЖЕРА (вне таблицы реестра; записи живут в ledger'е);
      • `I-NN`/`TB-I01`/`AC-I01`/`VAULT-I03` (инвариант, ns≤8, namespace-preserving) → existence в
        `system_model.md` СТРОКАХ-ДЕКЛАРАЦИЯХ (`_model_invariant_ids`, не whole-prose; web-placeholder
        легитимно предлагает TB-I/AC-I как src → фабрикация ловится, red-team #2 HIGH/MED).
    Не-id src (code-read/T6-pair/gap-map/prior-pattern), AX-NN (реестр-self), `D-I01`/`H-I5` (малформ
    divergence-ns) НЕ инвариант → label. `MODEL: N/A` + инвариант-src → FIRE (self-contradiction: модели
    нет → инвариант фиктивен, MED-1). Файл модели отсутствует, но НЕ N/A → silent (окно построения; зрелый
    держат model-гейты). Off: флаг/секции нет/нет OPEN-ACTIVE/MANUAL/OFF/EXIT. Satisfiable. relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    rows = _atom_rows(lt)
    if rows is None:
        return None                                        # C1: секции нет → silent
    oa = [a for a in _valid_atoms(rows) if a["status"] in ("OPEN", "ACTIVE")]
    if not oa:
        return None
    proof_lines = _c3_proof_lines(lt)                      # строки ledger'а ВНЕ таблицы реестра
    # инвариант-форма src (`I-01`/`TB-I01`/`AC-I01`) чекается против МОДЕЛИ, а не ледджера (red-team MED).
    # ⚠ Модель читаем ВСЕГДА (не гейтим на `_model_na`, red-team #3 MED-2): `_model_na` any-wins → stale
    # `MODEL: N/A` (append-трейс) при РЕАЛЬНО построенной модели фаирил бы на легит инвариант-src. Порядок:
    # (1) инвариант в модели → grounded, silent (даже при stale N/A); (2) модель-файл ЕСТЬ, инварианта нет
    # → фикция, FIRE; (3) модель-файла нет + N/A → self-contradiction (модели нет → инвариант фиктивен),
    # FIRE; (4) модель-файла нет + не N/A → окно построения → silent (зрелый держат model-гейты).
    model_na = _model_na(lt)
    model_invs = None
    mpath = os.path.join(os.path.dirname(ledger), "system_model.md")
    if os.path.exists(mpath):
        try:
            with open(mpath, "r", encoding="utf-8") as f:
                model_invs = _model_invariant_ids(f.read())
        except Exception:
            model_invs = None
    for a in oa:
        src = (a.get("src") or "").strip()
        m = _SRC_ID_RE.match(src)
        if m:
            ref = "%s-%s" % (m.group(1).upper(), m.group(2))   # нормализуем `D05`/`D-5` → `D-5`
            if not any(_id_match_in_text(ref, l) for l in proof_lines):
                # ре-судья #3 (compute-and-name): называем КОНКРЕТНЫЙ атом + его фиктивный src.
                return (os.path.relpath(ledger, root), a["id"], src)
            continue
        n = _norm_inv(src)                                  # инвариант-форма src (namespace-preserving)?
        if n is not None:
            if model_invs is not None:                      # модель-файл прочитан
                if n not in model_invs:                     # инварианта в модели нет → фикция (даже при stale N/A)
                    return (os.path.relpath(ledger, root), a["id"], src)
                # инвариант РЕАЛЬНО в модели → grounded, silent (перебивает stale N/A)
            elif model_na:                                  # модели-файла нет + N/A → definitionally фиктивен
                return (os.path.relpath(ledger, root), a["id"], src)
            # модели-файла нет + не N/A → окно построения → silent (держат model-гейты)
    return None


ATOM_SRC_UNGROUNDED_REASON = (
    "ATOM-SRC-UNGROUNDED (Worklist Driver Этап 2, судья-B Д2 — симметрия C3 + Волна web red-team, "
    "2026-08-11). Ledger `%s`: атом `%s` в `## Atom Registry` (`OPEN`/`ACTIVE`) несёт `src: %s` — id-форму "
    "(дивергенция `D-NN`/`H-NN`/`BB-NN` ЛИБО инвариант `I-NN`/`TB-I01`/`AC-I01`), но этого id НЕТ на его "
    "поверхности-обосновании: дивергенция — в нарративе ледджера (`## Divergences`/`## Active`/`## Refuted`/"
    "`## Building Blocks`), инвариант — в `system_model.md`. Это фиктивное обоснование: атом со ссылкой на "
    "несуществующую дивергенцию/инвариант = липовая «голова», которую driver активно продиктует как "
    "приоритет (laundered-wrong-axis). Приведи в порядок: либо впиши РЕАЛЬНУЮ запись под этот id "
    "(`### D-NN` дивергенция с `undup_origin` / `### H-NN` гипотеза с prediction+falsifier / строку "
    "инварианта `| TB-I01 | … |` в `system_model.md`), либо замени `src` на честный label (`code-read`/"
    "`gap-map`/`T6-pair`/`prior-pattern`) — тогда rank считается от реального источника, а не от фикции. "
    "Это НЕ выход петли (satisfiable) — grounded-src восстанавливает доверие к rank головы."
)


_REAL_HNN_HEAD_RE = re.compile(r"(?im)^\s*#{3,}\s*H-\d+")
_REAL_HNN_BULLET_RE = re.compile(r"(?im)^\s{0,3}[-*]\s*\*{0,2}\s*H-\d+")


def _real_hyp_count(ledger_text):
    """Число РЕАЛЬНЫХ гипотез H-NN в ledger'е (заголовки `### H-NN` И буллеты `- **H-NN:**`) — сигнал
    зрелости, НЕ завязанный на self-report `Iteration #` (red-team: iter можно заморозить на 2; FN-3:
    буллет-форма гипотез тоже считается). Placeholder `H-{NN}` (с `{`) не считается (`H-\\d+` требует
    цифру сразу после `H-`). Уникализируем по нормализованному id (заголовок+буллет одной H не двоят)."""
    txt = ledger_text or ""
    ids = set()
    for m in re.finditer(r"(?im)(?:^\s*#{3,}\s*|^\s{0,3}[-*]\s*\*{0,2}\s*)(H-\d+)", txt):
        ids.add(m.group(1).upper())
    return len(ids)


def active_registry_unpopulated(current_sid):
    """Worklist Driver Этап 1 — гейт adoption реестра (судья-2 D2: реестр опт-ин, сырой livepeer-дрейф
    БЕЗ реестра эскейпит оба гейта). Держит выход, когда ledger ЗРЕЛЫЙ и я АКТИВНО работаю (реальный
    `Current pick`), но `## Atom Registry` пуст/только-placeholder (0 валидных атомов) → машинный
    worklist не ведётся, pick-гейт беззуб. Форсит населить реестр. Зрелость = iter≥3 ИЛИ ≥2 реальных
    `### H-NN` (не только self-report iter — red-team: iter-freeze усыплял гейт). Off-switch: флаг off;
    секции нет (C1: web/legacy); `MODEL: N/A` (мелкий контракт/фронт — реестр избыточен, ре-судья #2);
    MANUAL/OFF; HUNT-EXIT; pick не реален; незрелый ledger. Satisfiable soft-nudge. relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _model_na(lt):
        return None                                        # MODEL: N/A — реестр не форсим (мелкий/фронт)
    rows = _atom_rows(lt)
    if rows is None:
        return None                                        # C1: секции нет (web/legacy) → silent
    if _valid_atoms(rows):
        return None                                        # реестр населён → всё в порядке
    if not _pick_is_real(_current_pick(lt)):
        return None                                        # не работаю активно (placeholder/первый проход)
    if _loopstate_iter(lt) < 3 and _real_hyp_count(lt) < 2:
        return None                                        # незрело: ни iter≥3, ни ≥2 гипотез (anti iter-freeze)
    return os.path.relpath(ledger, root)


REGISTRY_UNPOPULATED_REASON = (
    "REGISTRY-UNPOPULATED (Worklist Driver Этап 1, adoption-гейт, 2026-08-11). Ledger `%s`: ты активно "
    "работаешь (реальный `Current pick`, итерация ≥3), но `## Atom Registry` пуст / только-placeholder "
    "(0 валидных атомов). Машинный worklist НЕ ведётся → дрейф (give-up / уход-не-туда как livepeer) "
    "рождается заново, а pick-гейт беззуб (ему не с чем сверять). Населити реестр СЕЙЧАС: перенеси свой "
    "текущий план в строки `| id | type | title | src | rank | status | closes |` — КАЖДАЯ открытая "
    "гипотеза H-NN и КАЖДАЯ ось из `Axis-Queue` = строка (rank = severity_w×confidence_w×undup_mult×10, "
    "≤80; src = D-NN/T14-gap/score-4/T6-pair/prior-pattern/T9-frame). Текущий `Current pick` = строка со "
    "`status: ACTIVE`. Дальше СЛЕДУЮЩИЙ атом берётся из реестра (голова = max-rank OPEN), а не выбирается "
    "заново каждый ход. Это НЕ выход петли (satisfiable) — заполни реестр и продолжай копать."
)


def active_registry_section_absent(current_sid):
    """Worklist Driver — adoption-гейт присутствия секции (1inch re-pilot MED-1 / судья дрейфа, 2026-08-11).
    Весь драйвер opt-in на ЛИТЕРАЛЬНЫЙ заголовок `## Atom Registry`: переименуй/удали его → `_atom_rows`
    вернёт None → ВСЕ registry-гейты (pick / drained / unpopulated / closed-narrative / src-ungrounded)
    молчат по C1-short-circuit `if rows is None`, даже в полной give-up-форме. `active_registry_unpopulated`
    ТОЖЕ C1-молчит → секцию ничто не форсит существовать (её сеет только шаблон). Это ШИРОЧАЙШИЙ escape:
    невадоптящий/дрейфующий инстанс обходит весь worklist. Держит выход, когда ledger ЗРЕЛЫЙ и я активно
    работаю (реальный `Current pick`), НО секции `## Atom Registry` нет ВОВСЕ. Комплемент `unpopulated`
    (та ловит секция-ЕСТЬ-но-пуста; эта — секции НЕТ) — взаимоисключающи по `_atom_rows is None`. FP-риск
    низкий: оба шаблона (contract+web) СЕЙЧАС несут секцию, `_model_na` исключает мелкий контракт/фронт →
    сорвать можно только активным удалением template-default секции (ровно laundered-drift, что C3/src-
    grounding полицают для других полей). Единственный реальный FP-остаток = pre-driver legacy, поднятый
    после шипа драйвера — крыт той же maturity-меркой (iter≥3 ∨ ≥2 H-NN). Off-switch: флаг off; секция ЕСТЬ
    (→ unpopulated/drained territory); `MODEL: N/A`; pick не реален; незрелый ledger; MANUAL/OFF; HUNT-EXIT.
    Satisfiable soft-nudge (заведи секцию из шаблона). relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _model_na(lt):
        return None                                        # MODEL: N/A — реестр избыточен (мелкий/фронт)
    if _atom_rows(lt) is not None:
        return None                                        # секция ЕСТЬ → unpopulated/drained ловят пустоту/слив
    if not _pick_is_real(_current_pick(lt)):
        return None                                        # не работаю активно (placeholder/первый проход)
    if _loopstate_iter(lt) < 3 and _real_hyp_count(lt) < 2:
        return None                                        # незрело (anti iter-freeze, как unpopulated)
    return os.path.relpath(ledger, root)


REGISTRY_SECTION_ABSENT_REASON = (
    "REGISTRY-SECTION-ABSENT (Worklist Driver adoption-гейт, 1inch re-pilot MED-1, 2026-08-11). Ledger "
    "`%s`: ты активно работаешь (реальный `Current pick`, итерация ≥3 / ≥2 гипотез), НО секции `## Atom "
    "Registry` НЕТ ВОВСЕ (переименована/удалена/не заведена). Без неё ВЕСЬ Worklist Driver слеп — pick / "
    "drained / unpopulated / closed-narrative / src-ungrounded молчат по C1, и give-up / уход-не-туда "
    "(livepeer) снова рождаются без гейта. Секция — template-default (её несут ОБА шаблона: contract и "
    "web); её отсутствие на зрелом активном ханте = отклонение. СЕЙЧАС заведи её из шаблона "
    "(`sessions/_methodology/hypotheses_template.md` / `hypotheses_web_template.md`) с ТОЧНЫМ заголовком "
    "`## Atom Registry` и перенеси текущий план в строки `| id | type | title | src | rank | status | "
    "closes |` (`Current pick` = строка со `status: ACTIVE`, голова = max-rank OPEN). Это НЕ выход петли "
    "(satisfiable) — заведи секцию и продолжай копать. (Мелкий контракт <300 LOC / чистый фронт → "
    "`MODEL: N/A` снимает и этот гейт.)"
)


_CLOSE_GRADE_DEEP_RE = re.compile(r"close-grade\s*[:=]\s*\**\s*(depth-drive|executable)", re.I)
# GROUNDED observed = строка `observed:` с РЕАЛЬНЫМ артефактом (file:line / run-log / fork-diff / RPC /
# storage-slot / event-log). Финальный судья residual #1: голый `observed: x` бесплатен → padding-геймится
# (10 depth-drive − 8 голых `observed:` = 2 < 3 глушит гейт). Требуем file:line → «цитируй реальный код»
# (T12-канон observed:file:line). На реальном treadmill A/B было 0 file:line-observed → гейт всё равно фаирит.
# MED-3 (jito-live 2026-08-12): observed-kw и артефакт в ЛЮБОМ порядке на строке (было: observed→артефакт
# через `.*?` → file:line ДО observed не ловился). jito depth-trace пишет `L1 enqueue_withdrawal.rs:64,117
# — VRT escrow ... (observed:64 ✓)` — реальный file:line ПЕРЕД словом observed → старый regex MISS,
# недосчёт 9→3 на живом ханте, что ложно РАЗДУВАЛО active_axes_depth_inflated на честно-глубоком ханте.
# Разнесено на два независимых матча (kw + artifact) — порядок безразличен; голый observed без артефакта
# по-прежнему НЕ считается (residual #1 padding-guard сохранён).
_OBSERVED_KW_RE = re.compile(r"\bobserved\s*[:=]", re.I)
_ARTIFACT_CITE_RE = re.compile(
    r"[\w/.\\-]+\.(?:sol|rs|vy|move|cairo|go|ts|js|py|yul|sw|huff):\d+"
    r"|run-?log|fork-?diff|\bRPC\b|storage[-\s]?slot|event[-\s]?log|invariant[-\s]?test", re.I)
AXES_DEPTH_INFLATION_MIN = 3   # (#depth-drive-осей − #grounded-observed) ≥ порог → инфляция depth-ярлыка


def _grounded_observed_count(txt):
    """Число РАЗЛИЧНЫХ `observed:`-строк с реальным артефактом (file:line/run-log/fork-diff/RPC/slot/event).
    Distinct (нормализованный ключ) — анти-copy-paste-padding: 8 копий одной строки = 1 доказательство.
    Голый `observed: prose` без артефакта НЕ считается (residual #1: raise bar от токена к цитате кода).
    MED-3: observed-kw и артефакт матчатся независимо → file:line ДО или ПОСЛЕ observed равнозначны."""
    seen = set()
    for line in (txt or "").splitlines():
        if _OBSERVED_KW_RE.search(line) and _ARTIFACT_CITE_RE.search(line):
            seen.add(re.sub(r"\s+", " ", line.strip().lower()))
    return len(seen)


def _deep_labeled_closed_axes(rows, proof_lines):
    """CLOSED type:axis атомы, чьё закрытие в НАРРАТИВЕ (вне таблицы реестра) помечено
    `close-grade:depth-drive|executable` — т.е. ЗАЯВЛЕНА глубокая проработка оси."""
    out = []
    for a in rows:
        if a["status"] == "CLOSED" and (a["type"] or "").strip().lower() == "axis":
            for l in proof_lines:
                if _id_match_in_text(a["id"], l) and _CLOSE_GRADE_DEEP_RE.search(l):
                    out.append(a["id"])
                    break
    return out


# FIX-A (ethena-live 2026-08-12, judge-2 3/10): format-DECOUPLED счёт заявленных depth-осей. Судья замерил
# недосчёт 5→2: `_deep_labeled_closed_axes` требует (a) `type:axis` В РЕЕСТРЕ И (b) close-grade в узких
# `_c3_proof_lines` — а ethena использовал `type:scout-partition` для 5 из 7 осей + close-grades в свободном
# блобе `T9 restart axes used`. Итог: 7 осей с `close-grade:depth-drive`/`executable` при 0 grounded observed,
# а гейт насчитал 2 → `2-0<3` молчал. Fix: считать axis-id на ЛЮБОЙ close-grade-deep строке (T9-блоб /
# Axes-Closed / registry closes-cell) + CLOSED axis-like атомы (axis/scout-partition/cross-thread).
_AXIS_ID_RE = re.compile(r"\b(AX-\d+)\b")   # FIX-A: только AX-оси в line-scan (D-NN/H-NN ≠ ось; axis-like
                                             # атомы с иным id ловит part-2 по registry-типу)
_AXIS_LIKE_TYPES = {"axis", "scout-partition", "cross-thread"}
# SUD-HIGH-1 (jito-live 2026-08-12): prose-keyed close-grade осей. jito `## Axes-Closed` пишет оси bullet'ами
# `  - **vault epoch/withdrawal/reward core (I-04/I-07)** · … · close-grade:depth-drive ·` — ключ оси = BOLD-NAME,
# БЕЗ AX-id → line-scan по `_AXIS_ID_RE` их пропускал → оба anti-breadth гейта СЛЕПЫ на prose-layout (тот же
# format-decoupling рецидив, что ethena FIX-A/FIX-F ловили для type-decoupling). Fallback на bold-name ключ.
_AXIS_BULLET_RE = re.compile(r"^\s*[-*]\s+(\S.*)$")        # любой непустой bullet-заголовок
_AXIS_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")               # bold-name внутри заголовка (jito-формат)
# Ось-сигнатура Axes-Closed-bullet'а: `· outcome:` / `· src:` / `close-grade:`. Отличает НАСТОЯЩУЮ закрытую
# ось от прозаического bullet'а (`- **Residual signal:** …`, `- **surface-status:** …`) — иначе wrapped-
# lookup жадно цеплял бы любой заголовок как ось (jito-FP: `name:residual signal:`). Требование маркера
# позволяет расширить ключ на NON-bold bullet'ы (буквальный template-формат `- <ось> · src: · close-grade:`)
# без риска: имя = bold-name, если есть, иначе текст заголовка до первого `·`.
_AXIS_MARKER_RE = re.compile(r"·\s*outcome\s*[:=]|·\s*src\s*[:=]|close-grade\s*[:=]", re.I)


def _bullet_axis_name(line):
    """Ключ оси из bullet-заголовка, ТОЛЬКО если строка несёт ось-маркер (outcome/src/close-grade).
    Имя = bold-name (jito `- **name** · …`) либо, если bold нет, текст до первого `·` (template
    `- <ось> · src: …`). None — если не bullet ИЛИ без ось-маркера (прозаический `- **Residual signal:**`)."""
    m = _AXIS_BULLET_RE.match(line)
    if not m or not _AXIS_MARKER_RE.search(line):
        return None
    head = m.group(1)
    b = _AXIS_BOLD_RE.search(head)
    name = b.group(1) if b else head.split("·")[0]
    return "name:" + re.sub(r"\s+", " ", name.strip().lower())[:80]


def _grade_line_axis_keys(lines, idx, grade_re, non_axis):
    """DISTINCT-ключи осей на close-grade строке lines[idx]. AX-id (кроме non-axis-typed в реестре)
    приоритетен; если AX-паттерна на строке НЕТ вовсе → prose-ключ `name:<bold>` из bullet-заголовка на
    этой ИЛИ ближайшей (≤3) строке ВЫШЕ (R1: close-grade часто обёрнут на wrapped-строку, bold-name на
    заголовке; jito-203). Пустая строка рвёт bullet-блок — сквозь неё не тянем (PK8 anti-jump). Если AX-id
    есть, но ВСЕ non-axis-typed → пусто (респект типа, DI18: bold-fallback НЕ применяется)."""
    line = lines[idx]
    if "{" in line or line.lstrip().startswith(">"):
        return set()                                 # Z2-fix (судья LOW): плейсхолдер/RULES-blockquote-пример не ось
    if not grade_re.search(line):
        return set()
    raw_ids = _AXIS_ID_RE.findall(line)
    keys = {m for m in raw_ids if m not in non_axis}
    if keys:
        return keys
    if raw_ids:            # AX-id есть, но все помечены не-axis-типом → не прибегать к bold-name (респект типа)
        return set()
    for j in range(idx, max(-1, idx - 4), -1):
        if _AXIS_BULLET_RE.match(lines[j]):
            name = _bullet_axis_name(lines[j])       # None, если bullet без ось-маркеров (прозаический → не ось)
            return {name} if name else set()
        if j < idx and not lines[j].strip():
            break          # пустая строка = граница bullet-блока (PK8): не связывать close-grade с далёким заголовком
    return set()


def _depth_claimed_axes(lt, rows):
    """DISTINCT axis-ключи, заявленные с `close-grade:depth-drive|executable` ГДЕ УГОДНО в ledger, format-
    decoupled (FIX-A type + SUD-HIGH-1 prose-key). Источник (1): любая close-grade-deep строка → AX-id ИЛИ
    bold-name ключ. Источник (2): CLOSED axis-like атом, чей id стоит на close-grade-deep строке."""
    ids = set()
    lines = (lt or "").splitlines()
    # id'ы, помеченные в реестре ЯВНО не-axis-типом (hypothesis/verify/banked/…) → исключить из line-scan:
    # DI7 — type:hypothesis depth-drive = легит single-pick DRIVE, НЕ ось-treadmill (респектим тип).
    non_axis = {a["id"] for a in (rows or [])
                if (a.get("type") or "").strip()
                and (a.get("type") or "").strip().lower() not in _AXIS_LIKE_TYPES}
    for idx in range(len(lines)):
        ids |= _grade_line_axis_keys(lines, idx, _CLOSE_GRADE_DEEP_RE, non_axis)
    for a in (rows or []):
        if a.get("status") == "CLOSED" and (a.get("type") or "").strip().lower() in _AXIS_LIKE_TYPES:
            for line in lines:
                if _id_match_in_text(a["id"], line) and _CLOSE_GRADE_DEEP_RE.search(line):
                    ids.add(a["id"])
                    break
    return ids


def active_axes_depth_inflated(current_sid):
    """Worklist Driver — anti-breadth-treadmill (1inch long-run, the operator: «меняли ось каждые 2 минуты»,
    судья: worklist-гейты держат МЕХАНИКУ, не ГЛУБИНУ). Депт-гейты (`active_ledger_wide_but_shallow`/
    `depth_spin`/T12) кейзятся на ПРОЗЕ (`### H-NN`/`Depth-Lead:`) → СЛЕПЫ к реестровому формату: агент
    закрыл 10-12 осей за 30 мин, каждую self-пометил `close-grade:depth-drive`, а реальных depth-trace
    (`observed:`-строк) — 0-1, и НИ ОДИН гейт не возразил (замер A: 10 depth-drive / 1 observed; B: 12/0).
    Держит выход, когда ЗАЯВЛЕННАЯ глубина осей НЕ подкреплена observed-артефактами: (#CLOSED type:axis
    с close-grade:depth-drive|executable) − (#`observed:`-строк в ledger) ≥ 3. Каждый настоящий depth-drive
    рождает ≥1 `observed:` (T12-канон); много ярлыков при ~0 observed = breadth-театр. Off-switch: флаг off;
    секции нет; <4 depth-drive-осей (рано/лениво — мелкий хант закрывает мало осей); MANUAL/OFF; HUNT-EXIT.
    Satisfiable soft-nudge (гони ОДНУ ось вглубь с реальным DEPTH-TRACE, не скользи). relpath|(rel,n,ev)."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None                                        # хант завершён T4 High/Crit
    rows = _atom_rows(lt)
    if rows is None:
        return None                                        # C1: секции нет → silent
    deep = _depth_claimed_axes(lt, rows)                # FIX-A: format-decoupled (было _deep_labeled_closed_axes,
                                                           # недосчёт 5→2 из-за type:axis+узкие proof-строки)
    if len(deep) < 4:
        return None                                        # рано/лениво — мало закрытых depth-drive осей
    evidence = _grounded_observed_count(lt)             # residual #1: distinct observed:file:line, не голый токен
    if len(deep) - evidence >= AXES_DEPTH_INFLATION_MIN:
        return (os.path.relpath(ledger, root), len(deep), evidence)
    return None


AXES_DEPTH_INFLATED_REASON = (
    "AXES-DEPTH-INFLATED (Worklist Driver anti-breadth-treadmill, 1inch long-run, 2026-08-12). Ledger `%s`: "
    "ты закрыл %d осей с `close-grade:depth-drive`/`executable`, но реальных depth-trace (`observed:`-строк) "
    "всего %d. ЗАЯВЛЕННАЯ глубина НЕ подкреплена артефактами — это breadth-treadmill: смена оси каждые "
    "пару минут с self-ярлыком «глубоко пройдено», а не докоп. Настоящая ось = ЧАСЫ вниз (сильные лиды, "
    "кросс-нити, depth-ceiling ≥5 слоёв), НЕ 2-минутный проскок. Каждый depth-drive ОБЯЗАН родить реальный "
    "`DEPTH-TRACE` с `predicted:`/`observed:` + `file:line`-артефакт (T12-канон: слой = граница + "
    "предсказание ДО + факт ПОСЛЕ). СЕЙЧАС: возьми СИЛЬНЕЙШУЮ открытую ось, впиши `DEPTH-TRACE` (≥5 слоёв "
    "call→state→external→hook→accounting, каждый с `observed: file:line`) и гони ЕЁ вглубь — НЕ закрывай "
    "новые оси, пока эта не доведена. Это НЕ выход петли (satisfiable) — подтверди глубину и продолжай. "
    "(`close-grade:scout-verified`/`[SCOPED-OUT]` для быстрого дисмисса оси НЕ считается depth-drive и не "
    "триггерит — не ври ярлыком: мелкую ось помечай scout-verified, а не depth-drive.)"
)


# FIX-F (ethena-live 2026-08-12, judge-3 6/10, HIGH — scout-verified breadth-escape). active_axes_depth_inflated
# ловит ТОЛЬКО close-grade:depth-drive/executable → агент, помечающий оси ЧЕСТНЫМ ярлыком `scout-verified`
# (что REASON выше сам и советует для мелких осей), ПОЛНОСТЬЮ обходит FIX-A и продолжает breadth-парад легально.
# Template прозой говорит «≫половины scout-verified = breadth-tilt, НЕ exhaustion», но это НЕ enforced. Здесь —
# enforce: закрыл много осей, БОЛЬШИНСТВО scout-verified, реальной глубины (grounded observed) ~нет → breadth-tilt.
_CLOSE_GRADE_SCOUT_RE = re.compile(r"close-grade\s*[:=]\s*\**\s*(scout-?verified|scoped-?out)", re.I)
AXES_BREADTH_TILT_MIN = 4        # ≥N закрытых axis-like атомов = достаточно, чтобы судить о tilt
AXES_BREADTH_TILT_MIN_GROUNDED = 2  # <N grounded observed при majority-scout = нет реальной глубины нигде


def _scout_graded_axes(lt, rows):
    """DISTINCT axis-id'ы, закрытые с `close-grade:scout-verified|scoped-out` (format-decoupled, как
    _depth_claimed_axes): line-scan по close-grade-scout строкам (AX-id) + CLOSED axis-like атомы, чей id
    стоит на такой строке. Респектит тип (non-axis-typed AX-id из line-scan исключается — как FIX-A)."""
    ids = set()
    lines = (lt or "").splitlines()
    non_axis = {a["id"] for a in (rows or [])
                if (a.get("type") or "").strip()
                and (a.get("type") or "").strip().lower() not in _AXIS_LIKE_TYPES}
    for idx in range(len(lines)):
        ids |= _grade_line_axis_keys(lines, idx, _CLOSE_GRADE_SCOUT_RE, non_axis)
    for a in (rows or []):
        if a.get("status") == "CLOSED" and (a.get("type") or "").strip().lower() in _AXIS_LIKE_TYPES:
            for line in lines:
                if _id_match_in_text(a["id"], line) and _CLOSE_GRADE_SCOUT_RE.search(line):
                    ids.add(a["id"])
                    break
    return ids


def active_axes_breadth_tilt(current_sid):
    """FIX-F (judge-3, HIGH): scout-verified breadth-tilt — закрыл ≥AXES_BREADTH_TILT_MIN axis-like атомов,
    БОЛЬШИНСТВО помечены `scout-verified`/`scoped-out` (не depth-drive), И <2 grounded observed во всём
    ledger'е → это breadth-парад под честным слабым ярлыком (обход FIX-A). Комплемент FIX-A: тот ловит
    инфляцию depth-drive-ярлыка, этот — избыток scout-verified-закрытий. Off: MANUAL/OFF, HUNT-EXIT, флаг,
    реестра нет, <min закрытых, scout ≤ depth (глубина преобладает — легит), есть ≥2 grounded observed
    (реальная глубина где-то есть). Satisfiable soft-nudge (гони scout-оси ГЛУБЖЕ сам с observed:file:line)."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    rows = _atom_rows(lt)
    if rows is None:
        return None
    scout = _scout_graded_axes(lt, rows)
    deep = _depth_claimed_axes(lt, rows)
    total = len(scout | deep)                            # все закрытые (с любым depth/scout ярлыком) оси
    if total < AXES_BREADTH_TILT_MIN:
        return None
    if len(scout) <= len(deep):
        return None                                      # глубина преобладает → не tilt (FIX-A управляет)
    if len(scout) * 2 <= total:
        return None                                      # scout не большинство → не tilt
    if _grounded_observed_count(lt) >= AXES_BREADTH_TILT_MIN_GROUNDED:
        return None                                      # реальная глубина где-то есть → не пустой парад
    return (os.path.relpath(ledger, root), total, len(scout), len(deep))


AXES_BREADTH_TILT_REASON = (
    "AXES-BREADTH-TILT (FIX-F, ethena-live 2026-08-12, judge-3). Ledger `%s`: закрыто %d осей, из них %d "
    "помечены `scout-verified`/`scoped-out` (vs %d depth-drive), И реальной глубины (grounded `observed:"
    "file:line`) во всём ledger'е <2. Это BREADTH-ПАРАД под ЧЕСТНЫМ слабым ярлыком: scout-verified = "
    "cold-scout ENFORCED БЕЗ main-agent depth-drive → ≫половины scout-закрытий = ширина, НЕ исчерпание "
    "глубиной (template это прозой говорит — теперь enforced). Аксиома «баги везде»: осей бесконечно, но "
    "закрывать их scout-верификацией пачками ≠ хантить. СЕЙЧАС: возьми СИЛЬНЕЙШУЮ scout-закрытую ось, "
    "переоткрой и гони САМ вниз ≥5 слоёв (depth-ceiling call→state→external→hook→accounting) с реальным "
    "`DEPTH-TRACE` (`observed: file:line` на каждый слой) — un-dup крит живёт НИЖЕ scout-глубины, в стыке "
    "далёких подсистем. Держи баланс: scout-verified для быстрого честного дисмисса ОК, но не как основной "
    "режим закрытия осей. Satisfiable — доведи ≥1 ось до реальной глубины, продолжай."
)


# ── FEAT-G (jito-live 2026-08-12): depth-per-axis floor. FIX-A глобальный (#depth-drive − #observed ≥3) не
# ловит РАННИЙ close ОДНОЙ сильной нити — глобально observed хватает от других осей. Per-axis: depth-drive
# ось, чей proof заявляет `depth-trace N/M` с N<5, пройдена НИЖЕ depth-ceiling (CLAUDE.md: тяни ОДНУ нить
# ≥5 слоёв call→state→external→hook→accounting; «тут чисто» на глубине 3 = не докопал). Комплемент FIX-A.
DEPTH_CEILING_FLOOR = 5
_AXIS_DEPTH_PROOF_RE = re.compile(r"depth-trace\s*(\d+)\s*/\s*\d+", re.I)


def _shallow_depth_drive_axes(lt):
    """Число depth-drive осей, чей блок (close-grade строка + до 6 wrapped-строк) несёт `depth-trace N/M`
    с N<DEPTH_CEILING_FLOOR — заявлен depth-drive, а пройдено <5 слоёв (ранний close ниже depth-ceiling).
    Требует ЯВНОЕ число слоёв (надёжно, без co-location проблемы observed-в-другой-секции)."""
    lines = (lt or "").splitlines()
    n = 0
    for i, line in enumerate(lines):
        if "{" in line or not _CLOSE_GRADE_DEEP_RE.search(line):
            continue
        # Z2-fix (судья LOW, block-window bleed): блок оси = close-grade строка + wrapped-продолжение
        # ДО СЛЕДУЮЩЕГО bullet-заголовка / пустой строки (≤6 строк) — не «утекать» на depth-trace соседней оси.
        # Судья-2 LOW-6: рвём ТОЛЬКО на bullet'е того же/меньшего отступа (sibling/parent = чужая ось);
        # ВЛОЖЕННЫЙ sub-bullet (больший отступ) = продолжение ЭТОЙ оси (`- proof: depth-trace 3/5`) —
        # иначе depth-trace не виден и мелкая ось не флагается (FN, введённый bleed-фиксом).
        own_indent = len(line) - len(line.lstrip())
        block = [line]
        for j in range(i + 1, min(i + 7, len(lines))):
            nxt = lines[j]
            if not nxt.strip():
                break                                   # пустая строка — граница блока
            if _AXIS_BULLET_RE.match(nxt) and (len(nxt) - len(nxt.lstrip())) <= own_indent:
                break                                   # bullet того же/меньшего уровня — чужая ось
            block.append(nxt)
        m = _AXIS_DEPTH_PROOF_RE.search(" ".join(block))
        if m and int(m.group(1)) < DEPTH_CEILING_FLOOR:
            n += 1
    return n


def active_axis_depth_below_ceiling(current_sid):
    """FEAT-G: ≥1 depth-drive ось с proof `depth-trace N/M`, N<5 → сильная нить закрыта ниже depth-ceiling
    (per-axis floor, комплемент глобального FIX-A). Возвращает (rel, N) либо None. Off: флаг, MANUAL/OFF,
    HUNT-EXIT, реестра нет, 0 shallow-осей. Soft-nudge (доведи нить до ≥5 слоёв)."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _atom_rows(lt) is None:
        return None                                      # C1: реестра нет → silent (web/legacy)
    n = _shallow_depth_drive_axes(lt)
    if n < 1:
        return None
    return (os.path.relpath(ledger, root), n)


AXIS_DEPTH_FLOOR_REASON = (
    "AXIS DEPTH BELOW CEILING (FEAT-G, jito-live 2026-08-12). Ledger `%s`: %d ось(ей) помечены "
    "`close-grade:depth-drive`, но proof заявляет `depth-trace N/M` с N<5 — сильная нить закрыта НИЖЕ "
    "depth-ceiling. FIX-A ловит инфляцию depth-ярлыка ГЛОБАЛЬНО (#depth-drive − #observed), но ранний "
    "close ОДНОЙ сильной нити глобальный счёт пропускает (observed хватает от ДРУГИХ осей). CLAUDE.md: "
    "человек-аудитор слепнет на ~4-5 слоях — выжившие криты живут НИЖЕ; тяни ОДНУ цепочку ≥5 слоёв "
    "(call→state→external→hook→accounting), баг в их СТЫКЕ. «Тут чисто» на глубине 3 = не докопал. "
    "СЕЙЧАС: возьми эту depth-drive ось, догони нить до ≥5 слоёв с `observed: file:line` на КАЖДЫЙ слой "
    "(depth-trace 5/5+), ЛИБО честно перемаркируй `close-grade:scout-verified` (мелкая ось, не depth-drive). "
    "Это НЕ выход петли (satisfiable, soft)."
)


# ── Residual #3 (ethena-live judge-3, MED): observed:file:line VERIFIABILITY ──────────────────────────
# FIX-A/FIX-F считают `observed: File.sol:NNN` доказательством глубины, но regex-матч НЕ проверяет, что
# файл реально существует → цитата фабрикуема (судья: «satisfiable сфабрикованным file:line»). Это
# static-gate ПОТОЛОК (текст-гейт не верифицирует семантику «я прошёл границу»), но фабрикацию МОЖНО
# удорожить: если src таргета co-located в session-папке — цитируемый basename ОБЯЗАН там существовать.
# Зеркалит active_atom_src_ungrounded (тот верифицирует `src`-поле против поверхности; этот — `observed:`
# против файловой системы). FP-safe fail-open: нет co-located дерева / большой реальный клон / хоть одна
# цитата резолвится → silent. Фаирит ТОЛЬКО на near-certain фабрикации (дерево есть, тип совпал, НИ ОДНА
# цитата не резолвится). Партиал по построению: смесь real+fake не ловит (принятый потолок).
_OBSERVED_CITE_RE = re.compile(
    r"observed\s*[:=][^\n]*?([\w.\\/-]+\.(?:sol|rs|vy|move|cairo|go|ts|js|py|yul|sw|huff)):\d+", re.I)
_SRC_SCAN_EXTS = (".sol", ".rs", ".vy", ".move", ".cairo", ".go", ".ts", ".js", ".py", ".yul", ".sw", ".huff")
_SRC_SCAN_SKIP_DIRS = {".git", "node_modules", ".foundry", "out", "artifacts", "cache", ".cache",
                       "lib", "dist", "build", "target", "__pycache__", ".venv", "venv"}
_MAX_SRC_SCAN = 40000     # выше типичного клона; превышение = большой реальный клон → fail-open (None)


def _session_src_basenames(session_dir):
    """Множество lower-basename'ов source-файлов под session_dir (bounded). None = НЕВЕРИФИЦИРУЕМО
    (fail-open): src не co-located (пусто) ЛИБО клон > _MAX_SRC_SCAN (большой реальный → не наказываем)."""
    names = set()
    count = 0
    try:
        for dirpath, dirs, files in os.walk(session_dir):
            dirs[:] = [d for d in dirs if d not in _SRC_SCAN_SKIP_DIRS]
            for fn in files:
                if fn.lower().endswith(_SRC_SCAN_EXTS):
                    names.add(fn.lower())
                    count += 1
                    if count > _MAX_SRC_SCAN:
                        return None                  # большой реальный клон → fail-open
    except Exception:
        return None
    return names or None                             # пусто → src не co-located → fail-open


def active_observed_fabricated(current_sid):
    """Residual #3 (ethena-live judge-3, MED): `observed: File.sol:NNN`-цитаты FIX-A/FIX-F проверяемы на
    существование, если src таргета co-located в session-папке. НИ ОДНА из ≥2 distinct-цитат не резолвится
    в реальный basename (при наличии дерева с файлами того же типа) → фабрикация depth-grounding → держим.
    FP-safe fail-open: нет реестра (C1) / нет co-located дерева / большой клон / ≥1 цитата резолвится /
    тип не совпал (layout mismatch) → silent. Партиал по построению (смесь real+fake не ловит — принятый
    static-gate потолок). Возвращает (rel, n_fabricated) либо None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    if _atom_rows(lt) is None:
        return None                                  # C1: нет реестра → silent (как axis-гейты)
    cites = set()
    for line in lt.splitlines():
        m = _OBSERVED_CITE_RE.search(line)
        if m:
            cites.add(os.path.basename(m.group(1).replace("\\", "/")).lower())
    if len(cites) < 2:
        return None                                  # мало цитат — не судим
    names = _session_src_basenames(os.path.dirname(ledger))
    if names is None:
        return None                                  # fail-open: нет co-located дерева / большой клон
    if any(c in names for c in cites):
        return None                                  # ≥1 резолвится → правдоподобная глубина → silent
    cited_exts = {os.path.splitext(c)[1] for c in cites}
    tree_exts = {os.path.splitext(n)[1] for n in names}
    if not (cited_exts & tree_exts):
        return None                                  # дерево не содержит файлов цитируемого типа → layout mismatch
    return (os.path.relpath(ledger, root), len(cites))


OBSERVED_FABRICATED_REASON = (
    "OBSERVED-FABRICATED (residual #3, ethena-live judge-3 2026-08-12). Ledger `%s`: %d цитат `observed: "
    "File.ext:NNN` в DEPTH-TRACE, НО НИ ОДИН из этих файлов НЕ существует в co-located src таргета "
    "(session-папка содержит source-дерево того же типа, basename'ы цитат там отсутствуют). depth-grounding "
    "сфабрикован — FIX-A/FIX-F зачли бы эти строки как доказательство глубины, а код не цитируется. Настоящий "
    "`observed:` цитирует РЕАЛЬНУЮ строку кода (T12-канон: граница + факт ПОСЛЕ = конкретный file:line, "
    "который открывается). СЕЙЧАС: открой реальные файлы оси, впиши `observed:` с ФАКТИЧЕСКИМИ путями:строками "
    "из кода (не по памяти/догадке). Это НЕ выход петли (satisfiable) — заземли depth-trace на реальный код."
)


# Recognized un-dup/attention origins — засчитываются как grounding высокого ранга (МЕСТО из источника,
# которого у толпы нет). Голый label (`code-read`/`gut`/`review`/`important`) — НЕ grounding для top-ранга.
_GROUNDED_SRC_ORIGINS = (
    "attention-gap", "t14-gap", "t14", "commit-arch", "negative-space", "prior-pattern", "t6-pair", "t6",
    "composition-seam", "docs-runtime-gap", "model-vs-runtime", "assumption-min", "assumption-gap",
    "score-4", "score-5", "score-n", "patch-diff", "t5-seed", "diff-seed", "cold-axis", "t9-frame",
    "gap-map", "undup", "boundary", "third-party-seam",
)
RANK_EVIDENCE_MIN = 40.0   # rank головы ≥ этого (High-ish) требует grounded src (id ИЛИ recognized origin)
RANK_IDFORM_MIN = 56.0     # rank головы ≥ этого (Crit-tier) требует КОНКРЕТНЫЙ id-form (D/I-NN) — origin-label
#                            недостаточно (confirmatory судья residual: origin-label = un-checked one-word door;
#                            Crit-претензия = найденное расхождение → цитируй D-NN, не категорию «где смотреть»)


def _src_is_idform(src):
    """src = конкретный id-референс: D/H/BB-NN (existence чекает active_atom_src_ungrounded) ИЛИ инвариант."""
    return bool(_SRC_ID_RE.match(src or "")) or _norm_inv(src) is not None


def _src_grounded_for_rank(src):
    """src головы засчитан grounded для HIGH-ранга (40-55): id-form (D/H/BB/I-NN) ЛИБО recognized un-dup/
    attention origin (attention-gap/negative-space/…). Голый label (`code-read`/`gut`) → False."""
    s = (src or "").strip().lower()
    if not s or s in ("-", "—", "–", "tbd", "todo"):
        return False
    if _src_is_idform(src):
        return True
    return any(o in s for o in _GROUNDED_SRC_ORIGINS)


def active_head_rank_unjustified(current_sid):
    """Worklist Driver — rank-evidence гейт (финальный судья residual #2, Axis-2 потолок self-declared-rank
    laundering). Голова реестра (max-rank OPEN∪ACTIVE — то, что driver АКТИВНО диктует как next_atom) с
    rank ≥ RANK_EVIDENCE_MIN, но НЕ-grounded src (ни D/H/BB/I-NN, ни recognized un-dup/attention origin —
    голый label) → высокий ранг НЕ обоснован = возможная laundered-wrong-axis, всплывшая в голову голым
    числом (gate-comment §C3 признаёт: гейты держат «гони свою заявленную max-rank голову», не «голова
    реально лучшая»). Держит выход: обоснуй голову real D-NN/I-NN (divergence-first) или recognized-origin,
    ЛИБО снизь ранг. Композится с active_atom_src_ungrounded (тот ловит ФАБРИКОВАННЫЙ id; этот — high-rank
    БЕЗ id). Off-switch: флаг off; секции нет; нет валидных атомов; голова rank<порог; src grounded;
    MANUAL/OFF; HUNT-EXIT. Satisfiable soft-nudge. relpath|(rel, head_id, rank, src)."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if _has_valid_exit(lt):
        return None
    rows = _atom_rows(lt)
    if rows is None:
        return None
    atoms = _valid_atoms(rows)
    if not atoms:
        return None                                        # первый проход — реестр пуст
    oa = [a for a in atoms if a["status"] in ("OPEN", "ACTIVE")]
    head = _registry_head(oa)
    if head is None:
        return None                                        # нет живой головы (drained ловит отдельно)
    if head["rank"] < RANK_EVIDENCE_MIN:
        return None                                        # голова не претендует на High-ранг → не требуем
    src = (head["src"] or "—").strip()
    # Crit-tier (≥56): нужен КОНКРЕТНЫЙ id-form (D/I-NN); origin-label не хватает (закрыт one-word-door).
    if head["rank"] >= RANK_IDFORM_MIN:
        if _src_is_idform(src):
            return None
        return (os.path.relpath(ledger, root), head["id"], head["rank"], src, "crit")
    # High-tier (40-55): id-form ИЛИ recognized-origin ок; голый label → fire.
    if _src_grounded_for_rank(src):
        return None
    return (os.path.relpath(ledger, root), head["id"], head["rank"], src, "high")


_HEAD_RANK_REQ = {
    "crit": ("это CRIT-ранг (≥%g) → обязателен КОНКРЕТНЫЙ `D-NN` (расхождение модель↔код, divergence-first "
             "T10) или `I-NN`. Recognized-origin (`attention-gap`/`negative-space`/…) НЕ хватает: категория "
             "«где смотреть» ≠ найденное расхождение. Crit-претензию цитируй конкретным D-NN" % RANK_IDFORM_MIN),
    "high": ("это High-ранг (≥%g) → нужен grounded src: `D-NN`/`I-NN` ЛИБО recognized un-dup/attention origin "
             "(`attention-gap`/`T14-gap`/`negative-space`/`prior-pattern`/`T6-pair`/`composition-seam`/"
             "`score-4-file`/`cold-axis`…), НЕ голый label" % RANK_EVIDENCE_MIN),
}
HEAD_RANK_UNJUSTIFIED_REASON = (
    "HEAD-RANK-UNJUSTIFIED (Worklist Driver rank-evidence гейт, финальный судья Axis-2, 2026-08-12). Ledger "
    "`%s`: голова реестра `%s` несёт rank %g (driver АКТИВНО диктует её как next_atom), но `src` = `%s` не "
    "обосновывает ранг. Гейты держат «гони заявленную max-rank голову», не «голова реально лучшая» → чужую/"
    "слабую ось можно ЗАЛОНДРИТЬ в голову голым высоким числом (потолок Axis-2). %s. СЕЙЧАС: либо замени "
    "`src` головы на обоснованный (и убедись, что он реально существует — иначе active_atom_src_ungrounded "
    "держит), либо ЧЕСТНО снизь rank (severity×confidence×undup) до обоснованного. Это НЕ выход петли "
    "(satisfiable) — обоснуй голову и гони её."
)  # %-ы: relpath, head_id, rank, src, <tier-requirement из _HEAD_RANK_REQ> → кортеж (rel,id,rank,src,tier)


def active_registry_drained_no_exit(current_sid):
    """Worklist Driver — liveness-компаньон (1inch пилот HIGH-1, 2026-08-11). Pick-гейт
    `active_pick_not_from_queue` — КОНСИСТЕНТНОСТНЫЙ (pick = max-rank голова, ровно 1 ACTIVE), а НЕ
    liveness: на пустом OPEN/ACTIVE-множестве голову нарушать нечем → молчит by design. А
    `active_axis_queue_empty` при драйвере-ON с ЛЮБЫМИ валидными атомами (вкл. CLOSED — `_valid_atoms`
    статус-агностичен) встаёт в сторону («реестр owns forward-queue»). Итог (эмпирика пилота): give-up-
    состояние «все атомы CLOSED, новой OPEN-строки нет» невидимо ОБОИМ гейтам — даже когда C3 proof честно
    записан. Этот гейт закрывает шов: держит выход, когда реестр НЁС валидные атомы, но СЕЙЧАС 0 OPEN/ACTIVE
    (все CLOSED/PARKED/BANKED) и нет HUNT-EXIT → «слил реестр = give-up» (аксиома баги-везде: слил → генери
    новую ось, а не выходи). Отделено от genuine first-pass: там 0 валидных атомов ЛЮБОГО статуса (это
    territory `active_registry_unpopulated`) → молчим; тут ≥1 валидный, но НИ ОДНОГО живого. Banked
    Medium/Low петлю НЕ завершают → all-BANKED тоже drained (генери следующую ось). Off-switch: флаг off;
    секции нет (C1); 0 валидных атомов (first-pass); ≥1 OPEN/ACTIVE (реестр жив); MANUAL/OFF; HUNT-EXIT.
    Satisfiable soft-nudge (is_giveup=False по форме, но семантически анти-give-up). relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None                                        # аварийный ручной режим
    if _has_valid_exit(lt):
        return None                                        # хант завершён T4 High/Crit
    rows = _atom_rows(lt)
    if rows is None:
        return None                                        # C1: секции нет (web/legacy) → silent
    atoms = _valid_atoms(rows)
    if not atoms:
        return None                                        # 0 валидных → genuine first-pass (unpopulated territory)
    if any(a["status"] in ("OPEN", "ACTIVE") for a in atoms):
        return None                                        # ≥1 живой атом → реестр ведёт worklist
    return os.path.relpath(ledger, root)                   # ≥1 валидный, но все CLOSED/PARKED/BANKED → drained


REGISTRY_DRAINED_REASON = (
    "REGISTRY-DRAINED (Worklist Driver liveness-компаньон, 1inch пилот HIGH-1, 2026-08-11). Ledger `%s`: "
    "в `## Atom Registry` ЕСТЬ валидные атомы, но НИ ОДНОГО со `status: OPEN`/`ACTIVE` — все CLOSED/PARKED/"
    "BANKED, и новой OPEN-строки нет. Ты СЛИЛ реестр = give-up-состояние. Оно невидимо consistency-pick-"
    "гейту (нет головы — нечего нарушать) и axis-queue-гейту (реестр с CLOSED-атомами уводит его в "
    "сторону) — именно поэтому держит ЭТОТ гейт. Это НЕ выход петли: аксиома «баги есть ВЕЗДЕ» → «слил "
    "реестр» = «ещё не докопал», НЕ «таргет пуст»; единственный выход = `HUNT-EXIT: T4-CONFIRMED "
    "<High|Critical>` (banked Medium/Low петлю НЕ завершают). СЕЙЧАС заведи ≥1 новую OPEN-строку с "
    "`rank`+`src`: (1) СТРОИТЬ — gap-map (непрочитанные score-4/5) / cold-axis (T9 новый фрейм) / "
    "совпавшие `PRIOR-PATTERNS`; (2) ДОСТРАИВАТЬ — Refuted/CLOSED оси → T6-рекомбинация пар "
    "(Closed×Closed cross-thread с общим shared-state/fan-in → composite-ось, высокий ранг); (3) "
    "ПЕРЕСТРАИВАТЬ — T9 cold restart на новой оси. Затем сделай её ACTIVE и продолжай копать."
)


# Task 2 (FDE План 6, §43.1/§50/§51): composition_map.py — главный un-dup-генератор (web-инстанс
# cross-thread synthesis), строит граф `граница A --доверяет--> граница B` из `Источник`/`component:`
# полей модельных I-NN/TB-NN/AC-NN строк. Producer-absent класс, структурная копия
# `active_clone_diff_skipped`/`active_authz_matrix_skipped` (co-located: producer пишет
# `dirname(ledger)/composition_map.md`, детектор читает ТОТ ЖЕ путь) — но, в отличие от них,
# NAMESPACE-АГНОСТИЧЕН (не гейтится на TB-/AC- namespace: composition-граф строится из 12-колоночного
# контракта, общего всем 3 профилям §51, включая contract) и off-switch того же семейства, что
# `active_undup_sweep_incomplete` (Task 1): `_model_ctx` + `_i_matured_count(mt) >= 3`, а не
# Scout Fan-Out партиция-статус (партиции P-COMPOSITION в веере нет — этот гейт триггерится наличием
# ГРАНИЦ в модели, не разметкой партиции).
def _composition_boundary_count(model_text):
    """Число edge-eligible `I-NN`-строк: и `Источник`(idx4), и `component:`(idx5) заполнены реальным
    значением (не пусто, не `{TODO}`-плейсхолдер, не голый `-`/`—`). Каждая такая строка = одна
    граница composition-графа (`Источник --доверяет--> component`). Тот же 12-колоночный контракт,
    что `composition_map.py::parse_model_rows` (переиспользован по ФОРМАТУ — этот файл намеренно не
    импортирует producer-модули scripts/web2/, self-contained regex-парсер, как везде в этом хуке)."""
    n = 0
    for r in _i_rows(model_text):
        src = r[4].strip() if len(r) > 4 else ""
        comp = r[5].strip() if len(r) > 5 else ""
        if not src or not comp or "{" in src or "{" in comp:
            continue
        if src.strip("-—").strip() and comp.strip("-—").strip():
            n += 1
    return n


def active_composition_pass_skipped(current_sid):
    """Task 2: зрелая модель (`_i_matured_count(mt) >= 3`) несёт >= `COMPOSITION_MIN_BOUNDARIES`
    edge-eligible границ (см. `_composition_boundary_count`), но co-located `composition_map.md`
    отсутствует/пуст → держит выход (`is_giveup=False`, satisfiable — прогнать producer). Auto-
    глушится на `MODEL: N/A` (`_model_ctx` -> None) и на первом scout-проходе (тонкая модель).
    Возвращает rel(ledger) либо None."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, rel = ctx
    if mt is None:
        return None
    if _i_matured_count(mt) < 3:
        return None                                  # первый scout-проход — модель ещё строится
    if _composition_boundary_count(mt) < COMPOSITION_MIN_BOUNDARIES:
        return None                                  # модель без достаточного числа границ — не наш чек
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    cm_path = os.path.join(os.path.dirname(ledger), "composition_map.md")
    if os.path.exists(cm_path):
        try:
            with open(cm_path, "r", encoding="utf-8") as f:
                if f.read().strip():
                    return None                      # producer прогнан, файл непустой
        except Exception:
            return None                              # fail-open: нечитаемый файл не блокирует
    return os.path.relpath(ledger, root)


def active_wave_codefirst_nudge(current_sid):
    """OBS-9 (soft): live code-read H-NN без model-backing при непокрытых подсистемах."""
    ctx = _model_ctx(current_sid)
    if not ctx:
        return None
    lt, mt, _rel = ctx
    if mt is None:
        return None
    cov = _coverage_rows(mt)
    unmodeled = [c[0] for c in cov if c[1].startswith("y") and c[2] == "UNMODELED"]
    if not unmodeled:
        return None
    live = [h for h in _active_hnn(lt) if h[2]]
    codefirst = [h[0] for h in live
                 if re.search(r"code-read", h[1], re.I) and not _MODEL_BACKED_RE.search(h[1])]
    if codefirst:
        return WAVE_CODEFIRST_REASON % ", ".join(unmodeled[:6])
    return None


COMPOSITE_REASON = (
    "NO-ABANDON-COMPOSITE (Berachain 2026-07-12: 2 Crit поданы → ОБА DUPLICATE $0). В активном ledger "
    "есть Crit/High-capable КОМПОЗИТ (amplification / cross-thread тред через ДАЛЁКИЕ подсистемы), но он "
    "ОТЛОЖЕН без резолюции ('unproven' / 'amplification' / 'NEXT' / 'chasing' / 'could reach') — это РОВНО "
    "берачейновский промах: инстанс ВЫПИСАЛ un-dup лид (BB-35: beacon CL-exit→sweep→WithdrawalVault→pool "
    "totalDeposits→share-price, 5 слоёв cross-subsystem) и БРОСИЛ его, забанковав mid-depth дубль → $0. "
    "Дубликаты живут на mid-depth (куда доходит толпа); un-dup крит сидит в СТЫКЕ далёких подсистем ниже "
    "depth-ceiling — он ТВОЙ на полную сумму. ПРАВИЛО: выписанный Crit-capable композит = НЕ место отдыха. "
    "Либо DRIVE его вниз до D-PoC (гони цепочку слой-за-слоем через подсистемы, НЕ бросай на 'дорого "
    "доказать / нужен fork' — fork-PoC и есть работа), заполнив `DEPTH-MAP`; либо HARD-KILL с falsifier'ом "
    "`file:line` (→ [CONTESTED]/[KILLED], резолюция снимет гейт). Пометь резолюцию в треде "
    "(PoC / T4 / KILLED file:line / DRIVEN / confirmed) — тогда гейт отпустит."
)


DEPTHMAP_REASON = (
    "DEPTH-MAP UNGROUNDED (Berachain 2026-07-12). Depth-Lead ЗАЯВЛЯЕТ ≥5 слоёв, но поле `DEPTH-MAP` держит "
    "`{placeholder}` — карта взаимодействия НЕ выписана. Анти-геймінг: '5/5' в Depth-Lead без реального "
    "cross-subsystem трейса = self-report, не глубина (толпа доходит до mid-depth и дублирует; un-dup крит — "
    "в стыке ДАЛЁКИХ подсистем). ЗАПОЛНИ `DEPTH-MAP`: L1→L2→…→L5, где КАЖДЫЙ слой = `file:line` + имя "
    "ПОДСИСТЕМЫ/репо (call→state→external→hook→accounting через РАЗНЫЕ модули, не 5 строк в одном файле). "
    "Если баг реально one-subsystem-deep (Orchard-class внутри одного примитива) — впиши `N/A — "
    "single-subsystem (<примитив>)` явно. Placeholder `{…}` держит гейт до записи карты."
)


DEPTHMAP_SINGLE_REASON = (
    "DEPTH-MAP SINGLE-SUBSYSTEM (Berachain 2026-07-12). Depth-Lead заявляет ≥5 и `DEPTH-MAP` ЗАПОЛНЕН, но "
    "карта пересекает <3 различных подсистем/файлов — это «5 слоёв в ОДНОМ файле», а НЕ анти-дубль-глубина. "
    "Дубликаты живут на mid-depth ОДНОЙ подсистемы (толпа доходит); un-dup крит сидит в СТЫКЕ ДАЛЁКИХ "
    "подсистем (напр. beacon-kit↔staking-pools: CL-exit→sweep→vault-credit→pool-accounting→share-price — "
    "РАЗНЫЕ репо/модули). ЛИБО дотяни карту через далёкие подсистемы (call→state в модуле A → external-call "
    "в модуле B → hook в модуле C → accounting в модуле D — каждый слой `file:line`+подсистема, ≥3 разных); "
    "ЛИБО, если баг реально one-subsystem-deep (Orchard-class внутри одного примитива — legit), впиши "
    "`N/A — single-subsystem (<примитив>)` в DEPTH-MAP явно (тогда гейт отпустит). Soft-nudge: это суждение, "
    "но un-dup крит почти всегда cross-subsystem — не соглашайся на single-subsystem по лени."
)


# Находочный контент в ЧАТ вместо ledger (gap strata 2026-06-30): инстанс вываливал лиды/
# рефьюты простынёй в чат, hypotheses.md не трогал. Раньше считал "хуком не лечится" — неверно
# (first-pass abort преждевременный): структурный сигнал детектируем — находочная простыня в
# финальном сообщении + ledger не троган в этом turn.
FINDING_ID_RE = re.compile(r"\b[LH]-\d{1,3}\b")  # L-01 / H-12 = нумерованные лиды/гипотезы
FINDING_TERMS = [
    "зарефьют", "рефьют", "опроверг", "refuted",
    "building block", "building-block",
    "гипотез", "hypothes",
    "горячий", "живой и", "критический лид", "лид:",
]


def findings_signal(text):
    """Сила 'это находочный контент, которому место в ledger'. L/H-ID = +2, термин = +1."""
    score = 2 * len(FINDING_ID_RE.findall(text))
    low = text.lower()
    score += sum(low.count(t) for t in FINDING_TERMS)
    return score


def active_ledger_stale(current_sid, max_age=300):
    """True если активный ledger не модифицировался последние max_age сек (прокси 'не записал
    в этом turn'). Нет активного ledger → None (не наша забота)."""
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        return (time.time() - os.path.getmtime(ledger)) > max_age
    except Exception:
        return None


# Реальная (не-template) записанная работа в ledger. mtime-прокси (active_ledger_stale) имел
# дыру: entry-gate создаёт ledger со свежим mtime, инстанс пишет ТОЛЬКО шапку (mtime свежий,
# <300с → 'не stale'), а лиды/гипотезы сыплет в ЧАТ — файл остаётся пустым шаблоном, гейт молчит
# (impossible-cloud-network 2026-07-01). Content-детект mtime-независим: есть ли в файле хоть
# одна РЕАЛЬНАЯ `### H-<цифра>` гипотеза ИЛИ заполненный scout-лид (H-NN в таблице). Нет ничего =
# вся находочная работа мимо файла.
_REAL_H_RE = re.compile(r"(?m)^\s*#{1,4}\s*H-\d")          # ### H-01 (не шаблонный H-{NN})
_SCOUT_LEAD_RE = re.compile(r"\bH-\d{1,3}\b")               # H-NN где-либо (напр. в scout-таблице)


def active_ledger_thin(current_sid):
    """True если в активном ledger НЕ записано ни одной реальной гипотезы/лида (всё ещё
    пустой template) — независимо от mtime. None = нет активного ledger."""
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if _REAL_H_RE.search(txt):
        return False                                        # есть реальная H-гипотеза
    # scout-таблица: реальный H-NN в строке-лиде (шаблон использует H-{NN}, не матчится)
    body = txt.split("Active Hypotheses", 1)[0]             # шапка+scout часть
    # ⚠ 2026-07-28: но ПРИМЕРЫ внутри плейсхолдеров шаблона (`Depth-Lead: {… H-03 — 3/5 …}`)
    # матчились как «лиды записаны» → LEDGER-LIVE guard считал НЕТРОНУТЫЙ шаблон заполненным и
    # не срабатывал ровно в своём сценарии (скауты вернулись, находки в чате, файл пуст).
    # Тот же корень, что у слепоты `ledger_first_nudge`. Плейсхолдер = инструкция, не работа.
    body = re.sub(r"\{[^{}]*\}", " ", body, flags=re.S)
    if _SCOUT_LEAD_RE.search(body):
        return False                                        # scout-лиды записаны
    return True                                             # пусто → находки мимо файла


# the operator САМ попросил инфу в чат → вываливать легитимно, gate не трогаем.
INFO_REQUEST = [
    "объясни", "поясни", "покажи", "выведи", "распиш", "расскаж",
    "что такое", "как работает", "почему", "в чём", "в чем",
]

LEDGER_LIVE_REASON = (
    "LEDGER-LIVE-GATE (gap strata 2026-06-30). Ты вываливаешь находки/лиды/рефьюты простынёй "
    "в ЧАТ, а активный `hypotheses.md` в этом turn не тронут. Ledger — single source of truth: "
    "лиды (file:line + prediction + falsifier), рефьюты (с falsifier'ом), building blocks и "
    "обновление Loop State ОБЯЗАНЫ идти ТУДА live, а не в контекст. Сейчас: занеси всё в ledger "
    "(Active / Refuted-с-falsifier / Building Blocks + Loop State), the operator — только короткий "
    "статус (1-3 строки + ссылка на ledger). Контекст — не свалка находок."
)


# Стена ТЕЛ лидов/гипотез в ЧАТЕ даже когда файл ВЕДЁТСЯ (impossible-cloud-network 2026-07-01:
# инстанс писал в ledger И копипастил полные тела LEAD-XX/H-NN — CLASS/PREDICTION/FALSIFIER/
# SEVERITY/CONFIDENCE — в чат). ledger-live тут молчит (файл не thin). Это чисто многословность:
# schema-поля лида принадлежат ФАЙЛУ, в чат — только 1-строчный статус. Детект = кол-во
# schema-лейблов в финальном сообщении (каждый = поле тела лида, в нормальном статусе их нет).
_LEAD_FIELD_RE = re.compile(
    r"\b(PREDICTION|FALSIFIER|FALSIFYER|CLASS|SEVERITY|CONFIDENCE)\s*:", re.I
)


def chat_lead_body_fields(text):
    """Сколько schema-полей тела лида (PREDICTION/FALSIFIER/CLASS/SEVERITY/CONFIDENCE) в чате.
    Одно тело лида = ~5 полей; порог ≥3 = минимум одно полное тело вставлено в чат."""
    return len(_LEAD_FIELD_RE.findall(text))


CHAT_WALL_REASON = (
    "CHAT-WALL-GATE (impossible-cloud 2026-07-01). Ты копипастишь ПОЛНЫЕ тела лидов/гипотез в ЧАТ "
    "(schema-поля CLASS/PREDICTION/FALSIFIER/SEVERITY/CONFIDENCE). Хорошо, что файл ведёшь — но эти "
    "тела принадлежат ТОЛЬКО `hypotheses.md`, НЕ чату. the operator читает LEDGER, чат-стена = чистый шум, "
    "забивающий контекст. ПРАВИЛО ЧАТА (жёстко): НИКОГДА не пиши в чат тело лида (LEAD-XX / H-NN + "
    "PREDICTION/FALSIFIER/...). Максимум в чат — статус-строка вида: `Nх лидов → ledger <path>; "
    "далее: <одно действие>`. Если ловишь себя на 'LEAD-' или 'H-NN:' с описанием в чате — СТОП, это "
    "в файл. Сейчас: дай короткий статус (1-3 строки + ссылка), тела уже в ledger."
)


MODEL_BEFORE_SCOUT_REASON = (
    "MODEL-BEFORE-SCOUT (P0 divergence-first, katana 2026-07-29). Scout Fan-Out `PENDING`, но модель "
    "`%s` РЕАЛЬНО ПУСТА (ноль `I-NN` с заполненными `check:`+`pred:` — шаблонная `| I-01 |` не в счёт). "
    "Divergence-first ПОРЯДОК: независимая модель `I-NN` (формулами, с `pred:` ДО чтения кода) ПЕРВОЙ → "
    "ТОЛЬКО ПОТОМ scout режет партиции ПО ИНВАРИАНТАМ («найди, где `I-06` не enforced на всех путях»), а "
    "не по файлам. Веер ДО модели идёт «туда, куда идёт толпа» → дубли (Berachain: 2 Crit → оба $0). "
    "СЕЙЧАС: построй `I-NN` в `system_model.md` (≤12, каждый `check:`/`component:`/`pred:`) — можно "
    "буллетами `- **I-NN** [class] … check: … pred: …` ИЛИ 12-колоночной таблицей; либо поставь "
    "`MODEL: BUILDING` пока строишь; либо `MODEL: N/A — <причина>` (мелкий контракт <300 LOC / фронт / "
    "web2). Потом веер по инвариантам. Чеклист: `_methodology/independent_model_first.md`."
)

SCOUT_REASON = (
    "SCOUT-GATE (Hunt-Loop explore-wide). Секция `## Scout Fan-Out` в активном ledger всё ещё "
    "`PENDING` — explore-wide веер не отработан, single-pick deep рискует на неполном surface. "
    "Многоподсистемный/крупный таргет → запусти веер СРАЗУ по полной модели (НЕ по старым 5): "
    "**≤7 read-only `sonnet`-субагентов** (`subagent_type: general-purpose`) в ОДНОМ сообщении. "
    "CORE (запускай ВЕСЬ, вмещается в 7): **(1) P-B boundary/trust-perimeter — ОБЯЗАТЕЛЬНО ОТДЕЛЬНЫМ "
    "скаутом** (5 детекторов verifier_binding/bls_pairing/orphaned_tvl --src + oracle_report_timestamp_bound "
    "(5.14 future-dated) + breaker_rearm_cooldown (9.7) + 3 под-линзы периметра → "
    "сильнейшая граница как depth-lead → строка `BOUNDARY-MAP:`; 6/10 крупнейших хаков 2026 жили на "
    "границе, НЕ размазывай её по код-скаутам); (2) P1 accounting/shares; (3) P2 oracle/external; "
    "(4) P3 access/trust; (5) P4 state-machine/lifecycle; (6) P5 external-calls/reentrancy; "
    "**(7) P6 economic/incentive — strong-default** (3 сканера checkpoint_staleness + peg_check_asymmetry "
    "(3.16 mint/burn peg) + asymmetry_scanner --output <session> + 3 линзы round-trip/liquidation-gaming/MEV; "
    "skip только на чистом NFT/registry). "
    "**OPTIONAL-меню (бери по trigger, впиши triage → сними `OPT-TODO`):** P7 governance (timelock/vote), "
    "P8 cross-chain (bridge/peg/мульти-деплой → conservation-инвариант, ОБЯЗАТЕЛЕН на мостах), P9 "
    "ZK-circuit (circom/halo2/BLS-agg), P10 keeper/sequencer. Если CORE+matched > 7 → лишнее в "
    "`WAVE-2: … PENDING` (CORE в волну 2 НЕ уезжает НИКОГДА). Каждый scout → лиды (file:line + prediction "
    "+ falsifier) → merge: anti-slop + dedup + cross-thread T6-пасс по парам из разных партиций → H-NN → "
    "заполни таблицу + `BOUNDARY-MAP` + OPTIONAL-triage + WAVE-2 → смени Status на `DONE`. Спека: "
    "`sessions/_methodology/scout_fanout.md`. Одиночный мелкий контракт → Status "
    "`N/A — single-contract` (P-B → `N/A — no external trust boundary`) и в single-pick. Ранняя разведка, "
    "fan-out отложен (fingerprint бандла / web) → Status `DEFERRED → after <recon-step>`. ⚠ Гейт "
    "пропускает ТОЛЬКО канонические `DONE`/`N/A`/`DEFERRED`; `PENDING`, пусто И ЛЮБОЙ самодельный статус "
    "(`IN-FLIGHT`/`WIP`/…) блокируют — не обходи механизм своим значением (анти-gaming, hyperlane)."
)


BOUNDARY_SCOUT_REASON = (
    "P-B BOUNDARY-SCOUT GATE (Rootstock 2026-07-12). Scout Fan-Out помечен DONE, но P-B boundary-scout "
    "ОТДЕЛЬНЫМ агентом не отработал — поле `BOUNDARY-MAP` всё ещё placeholder. P-B — ОБЯЗАТЕЛЬНАЯ партиция "
    "(scout_fanout): граница доверия = ОРТОГОНАЛЬНАЯ ось (периметр, не код-подсистема). «Размажешь» её по "
    "код-скаутам (P1-P6) — теряешь единую карту периметра И выбор СИЛЬНЕЙШЕЙ границы как depth-lead, а 6/10 "
    "крупнейших хаков 2026 жили именно на границе (Bonzo/Supra verifier, Summer.fi external-token-в-NAV, "
    "Aztec live↔deprecated), НЕ в коде таргета. СЕЙЧАС: запусти ОТДЕЛЬНЫЙ P-B boundary-scout (read-only "
    "sonnet, general-purpose) — 3 детектора (verifier_binding_audit / bls_pairing_zero_input / "
    "orphaned_tvl_enum --src) + 3 под-линзы (trust-boundary map / verifier-input-binding / temporal-state) → "
    "верни СИЛЬНЕЙШУЮ границу как depth-lead и впиши строку `BOUNDARY-MAP: <границы>` (либо `N/A — no external "
    "trust boundary` для мелкого контракта без внешних деп). НЕ продолжай single-pick deep, пока периметр не "
    "отдельно-скаучен. Спека: `_methodology/scout_fanout.md` § P-B boundary-scout."
)

OPTMENU_REASON = (
    "OPTIONAL-MENU TRIAGE GATE (Rootstock 2026-07-12). Scout Fan-Out DONE, но сентинел `OPT-TODO` ещё висит — "
    "ты НЕ зафиксировал triage OPTIONAL-меню (P7 governance / P8 cross-chain / P9 ZK-circuit / P10 keeper-"
    "sequencer). Именно так инстанс на BTC↔RSK мосту пропустил P8 cross-chain-conservation (сожжено==выпущено "
    "через границу, класс Verus-2026), где живут bridge-криты. Меню НЕ авто-применяется — консультируй его "
    "СОЗНАТЕЛЬНО каждый хант. СЕЙЧАС: для КАЖДОЙ P7-P10 впиши строку triage — `MATCHED (<trigger>) → scout` "
    "ЛИБО `skip-if (<причина>)`; запусти отдельным скаутом MATCHED-партиции (bridge/peg/мульти-деплой → P8 "
    "ОБЯЗАТЕЛЕН; timelock/governor → P7; circom/halo2/BLS-agg → P9; keeper/sequencer/relayer → P10) и СНИМИ "
    "сентинел `OPT-TODO`. Спека: `_methodology/scout_fanout.md` § OPTIONAL-меню."
)

WAVE_PENDING_REASON = (
    "WAVE-2 GATE (Rootstock 2026-07-12, the operator: «CORE не уезжает НИКОГДА, optional — в волну 2; не забывать "
    "про 2-ю волну!»). В ledger висит `WAVE-2: … PENDING` — отложенная волна скаутов НЕ прогнана. Cap = 7 "
    "одновременных: matched-optional (P7-P10) ИЛИ CORE-overflow сверх 7 уехали в волну 2, а ты про неё забыл. "
    "СЕЙЧАС: прогони отложенные партиции волны 2 (read-only sonnet-скауты, тот же merge: anti-slop → dedup → "
    "cross-thread T6 → H-NN) и смени строку WAVE-2 на `DONE`. Напоминание: CORE (P-B + P1-P6) в волну 2 НЕ "
    "уезжает никогда — если он там, ты неправильно спартиционировал. Explore-wide не закрыт, пока WAVE-2 PENDING."
)

CLONE_DIFF_REASON = (
    "P-CLONE PRODUCER GATE (Task 4, FDE profile-dapphunt-web3-frontend). Cross-Clone — обязательная фаза "
    "(§7) на web-хантах: партиция `P-CLONE` в Scout Fan-Out активна (не N/A/DEFERRED), волна DONE, но "
    "`sessions/$DOMAIN/clone_diff.md` не прогнан. СЕЙЧАС: прогони "
    "`asymmetry_scanner_dapp.py --md-out sessions/$DOMAIN/clone_diff.md` ЛИБО пометь строку P-CLONE "
    "`N/A — single deploy`, если у таргета один деплой без клонов/staging."
)

AUTHZ_MATRIX_REASON = (
    "P-AUTHZ PRODUCER GATE (Task 9, FDE profile-web2-hunt). web2 P-AUTHZ активна, но "
    "`sessions/$DOMAIN/authz_matrix.md` не прогнан — authz-diff harness = ядро "
    "web2 (§17); прогони `authz_diff.py` (`run_authz_matrix`) под `opsec_preflight('web2')` ЛИБО "
    "пометь P-AUTHZ `N/A` / файл `MODE: single+unauth`. NB: `0 divergences` ≠ проверено на full-leak "
    "BOLA (см. blind_spots.md BS-05)."
)

OP_COVERAGE_REASON = (
    "OPERATION-COVERAGE GATE (Task 2, Plan 9 hunter-parity). `authz_matrix.md` присутствует, но хоть "
    "одна (operation, role) строка НЕ несёт валидного статус-enum'а в колонке `исход` "
    "(`tested-clean` / `divergent` / `inconclusive-<class>` / `excluded` / `blocked`) — «проверено-"
    "чисто» НЕЛЬЗЯ отличить от «не тестили» (Marius: каждая операция → исход, нельзя молча пропустить). "
    "СЕЙЧАС: перегони producer `authz_diff.py` (`run_authz_matrix`) — он эмитит РОВНО ОДНУ строку на "
    "каждый (operation, role) чек с явным статусом; ЛИБО, если правил файл руками, проставь статус в "
    "каждой строке. Старый до-Task-2 файл без колонки `исход` → перегенерируй."
)

AI_TRUST_REASON = (
    "P-AI PRODUCER GATE (Task 3, FDE План 7 §60, profile-web-ai-surface). AI/LLM-фича детектнута "
    "(партиция `P-AI` в Scout Fan-Out активна, не N/A, волна DONE), но "
    "`sessions/$DOMAIN/ai_trust_matrix.md` не прогнан — AI-surface несёт свой "
    "trust-boundary (context≠instruction, tool-call re-authz ПОСЛЕ LLM: injection→priv tool-call / "
    "RAG bleed / prompt-extract / SSRF-via-agent / output→sink, Cat 28). СЕЙЧАС: прогони "
    "`ai_injection_diff.py` (`run_ai_trust_matrix`) под `opsec_preflight('web2')` ЛИБО пометь строку "
    "P-AI `N/A — no AI surface`, если у таргета нет AI/LLM-поверхности."
)

IMPACTS_REASON = (
    "IMPACTS-IN-SCOPE GATE (recon-completeness, 2026-07-06). Шапка ledger всё ещё держит сентинел "
    "`{IMPACTS-TODO ...}` — ты снял Assets in Scope, но НЕ снял **Impacts in Scope** (per-impact "
    "severity-рубрику ПРОГРАММЫ). Это критично ДВАЖДЫ: (1) калибрует severity (что программа считает "
    "Critical/High/Medium по каждому impact — иначе overstate → rep-friction, understate → недобор), "
    "(2) задаёт ЧТО вообще искать (in-scope impacts = мишени; out-of-scope/known-issue = не тратить время). "
    "СЕЙЧАС: сними из программы дословно список Impacts in Scope + severity-рубрику + явные out-of-scope/"
    "known-issue impacts → впиши в шапку `**Impacts in Scope:**` и СНИМИ сентинел `IMPACTS-TODO`. "
    "Repo/no-program без формального списка impacts → впиши `N/A — no formal impacts list` (сентинел "
    "тоже снимется). Recon-субагент обычно уже видел это в отчёте — занеси в ledger, не держи «в голове»."
)


OOS_REASON = (
    "OUT-OF-SCOPE GATE (money-critical recon, 2026-08-11). Шапка ledger держит сентинел `{OOS-TODO ...}` "
    "— ты НЕ вычитал **Out-of-Scope дисквалификаторы** из вкладки программы `/scope/` Out-of-Scope. Это "
    "ОТДЕЛЬНО от in-scope рубрики `/information/` (промах 2026-08-10: репорт закрыт OOS $0, т.к. читал "
    "только in-scope, а дисквалификатор из /scope/ пропустил — validity кода ≠ payability по scope). "
    "СЕЙЧАС: открой вкладку Out-of-Scope программы и сними ДОСЛОВНО program-specific дисквалификаторы — "
    "centralization/admin-key/trusted-actor risks, known-issues, тестнет, already-reported, social-eng, "
    "best-practice-без-impact, любые out-of-scope clauses → впиши в `**Out-of-Scope (disqualifiers):**` и "
    "СНИМИ сентинел `OOS-TODO`. Repo/no-program → `N/A — no formal OOS list`. Держи этот список под рукой: "
    "перед подачей (HUNT-EXIT) каждую находку сверишь с ним (OOS-CHECK) — находка в OOS = $0 даже с PoC."
)


OOS_CHECK_REASON = (
    "OOS-CHECK GATE (submit-time дисквалификатор, 2026-08-11). Ты объявил `HUNT-EXIT` (готов подавать "
    "High/Critical), но в ledger НЕТ строки `OOS-CHECK:` — находка НЕ сверена с захваченным Out-of-Scope "
    "списком. Это ровно тот промах, что закрыл репорт 2026-08-10 (OOS был доступен, но не применён к "
    "находке). СЕЙЧАС: сверь свою находку с каждым Out-of-Scope дисквалификатором из шапки и впиши строку "
    "`OOS-CHECK: <краткое имя находки> vs out-of-scope → PASS` (если чиста) ЛИБО `→ DISQUALIFIED: <clause>` "
    "(если попадает — тогда НЕ подавай, вернись в петлю за другой находкой). Особо проверь: зависит ли "
    "impact от промаха trusted-актора (oracle/keeper/multisig/admin) → почти всегда centralization-clause "
    "= OOS. Без OOS-CHECK выход держится (money-critical: подача OOS-находки = $0 + rep-friction)."
)


LOOP_STATE_REASON = (
    "LEDGER-GUARD (Hunt-Loop). Активный ledger потерял блок `## Loop State` — значит он "
    "переписан своим форматом мимо канонического template. Без Loop State (Iteration #, "
    "Current pick, Last SELECT-branch, per-iteration trace) петля НЕ resumable: при компакте/"
    "рестарте нельзя продолжить с точной ветки. ДОБАВЬ блок `## Loop State` из "
    "`sessions/_methodology/hypotheses_template.md` в ledger и веди его в "
    "конце КАЖДОЙ итерации. Свой формат (KNOWN ISSUES / Drift signals) можешь оставить — но "
    "Loop State + Refuted-с-falsifier + Building Blocks ОБЯЗАТЕЛЬНЫ поверх него."
)

REASON = (
    "COMPLETENESS-GATE (loop-guard, reference_brutecat_ai). Ты завершаешь хант с abort/"
    "no-findings — но решение уйти с таргета принимает ТОЛЬКО the operator, не ты, и НЕ спустя ~30 мин. "
    "Прежде чем сказать 'не нашёл', явно пройди 5 пунктов deephunt 'When to ABORT' (по одному, вслух): "
    "(1) gap-map: ВСЕ score-4/5 файлы реально прочитаны построчно, список непрочитанных пуст? "
    "(2) агрессивный second-pass с НОВЫМИ углами/threat-models пройден (не повтор first-pass)? "
    "(3) depth-ceiling: top-3 entrypoints протрассированы вниз >=5 слоёв (call->state->external->hook->settle)? "
    "(4) T6 composite re-run на КАЖДОМ D-Kill (refuted -> building block -> пере-сцеплен)? "
    "(5) НЕ сработал ли запрещённый фрейм 'hardened/well-audited/bad EV' как причина выхода? "
    "(6) COLD RESTART (mythos T9) прогнан? Когда (1)+(2)+(4) пусты — это entry-gate Cold Restart: "
    "'беспросветный тупик' = anchoring, НЕ 'багов нет'. ОБЯЗАТЕЛЬНО запусти cold-субагента на НОВОЙ оси "
    "(ось задаёшь ТЫ); после 3 пустых осей — surface статус the operator (gap-map пруф) и CONTINUE на оси 4, "
    "НЕ park (под Hunt-Loop аксиомой park НЕ существует). "
    "(7) BREADTH≠DEPTH (TermMax-урок): заявил 'весь скоуп закрыт / все N чейнов / каждый фид покрыт / "
    "end-to-end / certainty HIGH'? Это BREADTH-sweep (file-level классификация), НЕ depth-exhaustion. "
    "На мульти-чейн/100+-рынков surface за часы охватить ГЛУБИНОЙ физически нельзя = недокоп. Exhaustion "
    "требует ГЛУБИНЫ, не ширины: depth-ceiling ≥5 слоёв на СИЛЬНЕЙШЕЙ нити + T6 composite на латентных + "
    "(мульти-деплой) T8 cross-chain differential. **≥2 латентных дефекта = surface ПЛОДОРОДНЫЙ** (не "
    "'все латентные, чисто'): где 5 латентных поодиночке 'мертвы' — 6-й боевой сидит ГЛУБЖЕ или в их ПАРЕ "
    "(T6). Мульти-чейн same-protocol: config/band-дельта между чейнами (есть на A, нет на B) = "
    "'deployed<audited' defense-regression = боевой лид, НЕ 'латентный Medium' — тяни вниз. "
    "Хоть один пункт != PASS -> вернись к копанию, выход закрыт. ~30 мин 'ничего' = недокоп, не 'чисто' "
    "(баги есть везде — аксиома). ЕДИНСТВЕННЫЙ выход петли = T4-подтверждённый HIGH/CRITICAL баг (success); "
    "Medium и Low фиксируй И ПОДАВАЙ по ходу — но они петлю НЕ завершают (the operator 2026-07-06: выход только "
    "High/Critical). Найден Medium → сабмить + жми severity ceiling (chain/PoC до High) и продолжай копать. "
    "Иначе уйти можно ТОЛЬКО когда the operator сам сказал 'уходим'. "
    "И НЕ заканчивай turn вопросом к the operator ('что решаешь / задай ось / по твоему слову') — ось задаёшь "
    "ТЫ, а продолжение = СПАВНИ Task cold-субагента (subagent_type general-purpose, sonnet, read-only) на "
    "новой оси ПРЯМО СЕЙЧАС, не жди ответа. Заявка 'проверил КАЖДЫЙ из N контрактов' за ~30 мин = ложная "
    "исчерпанность (физически не успел построчно) → это и есть недокоп; вместо декларации — cold-скаут в код."
)


# ─────────────────────────────────────────────────────────────────────────────
# LOOP-DROP-GUARD (2026-07-02, the operator: «хант должен идти САМ, бесконечно, в каждой новой сессии;
# я только даю цель охоты, /loop писать не должен»). Движок автономной петли = САМ Stop-хук:
# активный хант ⇒ turn НЕ завершается по умолчанию (это и есть codex-эффект «у отдельного вызова
# нет опции вернуться к юзеру»), пока НЕ выполнено одно из:
#   (success) в ledger записан `HUNT-EXIT: T4-CONFIRMED <High|Critical>` (после реального T4; Medium/Low НЕ выход);
#   (release) the operator сказал RELEASE-слово («уходим» и т.п.);
#   (manual)  в ledger стоит `HUNT-MODE: MANUAL` — аварийный off, старое поведение (блок только на give-up).
# Анти-спин safety (circuit breaker): default-петлю отпускаем, ТОЛЬКО если ledger НЕ двигается 8 блоков
# подряд (genuine dead-spin). GIVE-UP (REASON) circuit breaker'ом НЕ отпускается — держим намертво (the operator
# 2026-07-07: страховка от токенов не нужна; артикулированный give-up = НЕ мёртвый спин, это то, что мы
# гейтим). 30-мин таймер УБРАН: путал legit read-heavy фазу с мёртвым циклом. Fail-open везде.
# ─────────────────────────────────────────────────────────────────────────────
# Success-выход СТРОГО High/Critical (the operator 2026-07-06): Medium — банк+сабмит ПО ХОДУ, но петлю
# НЕ завершает; единственный success-выход = T4-подтверждённый High/Critical (или the operator «уходим»).
# Токен с Medium (или без severity) НЕ выпускает — совпадает с severity-priority мандатом (primary
# = Crit/High). Толерантен к разделителям/markdown между CONFIRMED и severity (`: `, ` **`, ` <`).
_EXIT_RE = re.compile(r"HUNT-EXIT:\s*T4-CONFIRMED[^A-Za-z0-9<]{0,6}(?:HIGH|CRITICAL)\b", re.I)
# Отмена exit-токена (Berachain 2026-07-13 live-test): инстанс записал HUNT-EXIT после T4, но при
# дедупе/реверсе ОТМЕНИЛ находку (H-09: "confirmed-real но not confidently-Critical-exploitable; kept
# banked"), а токен остался в файле → ledger_success_exit выпускал петлю на УСТАРЕВШЕМ токене =
# banked-and-exited (ровно класс из ретроспективы). Void-маркер = строка, где HUNT-EXIT рядом с
# supersede/reverse/void/retract/"not a clean loop-exit". Токен валиден ТОЛЬКО если он ПОСЛЕ последней
# отмены (позиционно) — ре-подтверждение после реверса разрешено, устаревший до реверса — нет.
_EXIT_VOID_RE = re.compile(
    r"(?im)^[^\n]*(?:HUNT-EXIT[^\n]*(?:supersed|revers|voided?|retract|withdrawn|not a clean loop)"
    r"|(?:supersed|revers|retract)[^\n]*HUNT-EXIT)[^\n]*$"
)
_MANUAL_RE = re.compile(r"(?m)^[ \t>*\-]{0,8}HUNT-MODE[:*\s]*MANUAL\b", re.I)  # OBS-5: терпит markdown `- **HUNT-MODE:** MANUAL`
FROZEN_RELEASE = 8  # Stop-блоков подряд без движения ledger → safety-release (анти-спин)


def _has_valid_exit(t):
    """Действующий HUNT-EXIT токен (T4 High/Crit), ИГНОРИРУЯ backtick-code-спаны (re-pilot MED-4, судья
    round-2 HIGH): `HUNT-EXIT: T4-CONFIRMED High` в прозе/примере/RULES-указателе ≠ реальный выход. Реальный
    токен = Loop-State поле, НЕ обёрнутое в backtick'и. Точный скип НА УРОВНЕ СЕГМЕНТА (не всей строки, как
    `_model_na`): строка реального выхода МОЖЕТ нести backtick-ссылку на файл (`vault.sol:88`) — скип всей
    строки пропустил бы настоящий выход = петля не отпустит (хуже FP). Проверяем `_EXIT_RE`/`_EXIT_VOID_RE`
    ТОЛЬКО в even-сегментах `split('`')` (текст ВНЕ code-спанов). Плейсхолдер `<High|Critical>` уже не
    матчит (`<` вне сепаратора), Medium — тоже. Позиционная void-семантика ledger_success_exit сохранена:
    валиден только exit ПОСЛЕ последней отмены (Berachain 2026-07-13). Unifies 11 off-switch call-sites +
    ledger_success_exit; раньше простые сайты были non-positional (`and not void`) — теперь все positional
    (строго корректнее: ре-подтверждение ПОСЛЕ реверса честно выпускает). Fail-safe: пусто → False."""
    if not t:
        return False
    pos = 0
    last_exit = -1
    last_void = -1
    for line in t.splitlines(keepends=True):
        segs = line.split("`")
        even = [segs[i] for i in range(0, len(segs), 2)]     # сегменты ВНЕ backtick-code-спанов
        if any(_EXIT_RE.search(s) for s in even):
            last_exit = pos
        if any(_EXIT_VOID_RE.search(s) for s in even):
            last_void = pos
        pos += len(line)
    if last_exit < 0:
        return False
    return last_exit > last_void


def _read_ledger(current_sid):
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def ledger_success_exit(current_sid):
    """True если в ledger записан ДЕЙСТВУЮЩИЙ токен успешного выхода (T4-подтверждённый High/Critical).
    Medium/Low НЕ выпускают петлю (the operator 2026-07-06) — _EXIT_RE матчит только HIGH|CRITICAL.
    Berachain 2026-07-13: токен, ОТМЕНённый последующим supersede/reversal (_EXIT_VOID_RE), не
    считается — иначе устаревший HUNT-EXIT от отменённой находки выпускает петлю (banked-and-exited).
    Валиден только exit-токен ПОСЛЕ последней отмены (позиционно)."""
    return _has_valid_exit(_read_ledger(current_sid))


def ledger_manual_mode(current_sid):
    """True если хант помечен HUNT-MODE: MANUAL — автопетля выключена (аварийный тормоз)."""
    t = _read_ledger(current_sid)
    return bool(t and _MANUAL_RE.search(t))


# ── EXIT-KNOWLEDGE banking + marker-cleanup (the operator 2026-08-13, «после ухода данные должны вноситься») ──
# ДЫРА: на success HUNT-EXIT частично форсился банк (invariant_library gate), а на manual «уходим» —
# МГНОВЕННЫЙ release без сохранения знания на будущее: ни wave-snapshot (ре-визит), ни undup_pattern
# (компаундинг), ни memory-INDEX (прецедент). Компаундинг = суть длинной охоты; теряли накопленное на
# каждом «уходим». Теперь ОБА выхода форсят EXIT-KNOWLEDGE-чеклист (satisfiable сентинелом DONE).
# + marker-cleanup: завершённый хант снимает СВОЙ .hunt_active (jito: H-06 SUBMITTED, но маркер жил +
# keep-alive его бампал → цеплял methodology-сессию). Снимаем ТОЛЬКО owned (свой sid).
_EXIT_KNOWLEDGE_DONE_RE = re.compile(r"(?im)^\s*[-*>]*\s*\*{0,2}\s*EXIT-KNOWLEDGE\s*[:=]\s*\**\s*DONE")

EXIT_KNOWLEDGE_REASON = (
    "EXIT-KNOWLEDGE (the operator 2026-08-13 — «после ухода данные должны вноситься на будущее»). Ledger `%s`: "
    "выходишь (success ИЛИ «уходим»), но знание на БУДУЩЕЕ не забанковано. Компаундинг — суть длинной "
    "охоты: без банка теряем накопленное на каждом выходе. ПЕРЕД выходом внеси (что применимо): "
    "(1) **wave-snapshot** — `py -3 -X utf8 scripts/wave_delta.py snapshot <slug> "
    "--src <path>` (ре-визит-хук на следующем релизе пойдёт по ДЕЛЬТЕ, не с нуля); (2) **undup_pattern** — "
    "fingerprint находки/паттерна в `sessions/_methodology/undup_pattern_library.md` (PRIOR-PATTERNS "
    "следующего таргета = moat); (3) **memory-INDEX** — строка ханта в `memory/INDEX_projects.md` (таргет, "
    "находки, уроки, чем кончилось); (4) invariant_library — примитивы (отдельный LIBRARY-gate). Пометь "
    "`EXIT-KNOWLEDGE: DONE — <что внёс>`. Тривиальный хант без работы → `EXIT-KNOWLEDGE: DONE — N/A`. НЕ "
    "держит намертво (satisfiable за один шаг)."
)


def _hunt_had_substance(lt, current_sid):
    """Была ли в ханте реальная работа, достойная банка на будущее (≥1 сильный refute ИЛИ зрелая модель
    ИЛИ ≥2 закрытых оси). Тривиальный хант (N/A модель, 0 находок) → False → EXIT-KNOWLEDGE не форсим."""
    if _strong_refute_count(lt) > 0:
        return True
    ctx = _model_ctx(current_sid)
    if ctx and ctx[1] is not None and _i_matured_count(ctx[1]) >= 3:
        return True
    rows = _atom_rows(lt)
    if rows and sum(1 for a in rows if a.get("status") == "CLOSED") >= 2:
        return True
    return False


def active_exit_knowledge_pending(current_sid):
    """the operator 2026-08-13: на выходе (success/manual) внести данные на будущее (snapshot/pattern/memory).
    Pending, если хант имел реальную работу И нет `EXIT-KNOWLEDGE: DONE`. Тривиальный хант → None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _EXIT_KNOWLEDGE_DONE_RE.search(lt):
        return None                                  # уже внесено
    if not _hunt_had_substance(lt, current_sid):
        return None                                  # нечего банковать
    return os.path.relpath(ledger, root)


def _cleanup_owned_marker(current_sid):
    """A (the operator 2026-08-13): хант завершён (success HUNT-EXIT ИЛИ manual «уходим») → снять СВОЙ .hunt_active,
    чтобы keep-alive не держал его вечно. Снимаем ТОЛЬКО owned (свой sid) — чужой хант не трогаем. Fail-safe."""
    try:
        for _, m in _owned_markers(current_sid):
            try:
                os.remove(m)
            except Exception:
                pass
    except Exception:
        pass


# ── FEAT-A (jito-live 2026-08-12, the operator): T4-v2 Reliability-gate. T4 верификатор = 2 СУРОВЫХ cold-агента
# дают Reliability% (жив ли баг СЕЙЧАС / $-at-risk / severity-push-потолок / не забанит ли триаж), + свой
# финальный T4 главным агентом → финальная Reliability. the operator: «менее 50% не подавать даже High/Crit —
# лежат забанкованые, охота НЕ заканчивается». Gate держит success-выход, пока финальная Reliability не
# записана И ≥RELIABILITY_MIN. НЕ трогает off-switch `_has_valid_exit` (11 сайтов) — живёт в success-каскаде
# рядом с OOS/T4-decomposition. <50% → void HUNT-EXIT + банк `[LOW-RELIABILITY]`, петля продолжается.
# parenthetical-tolerant (Z2 судья HIGH-2): шаблон-поле `**Final Reliability (FEAT-A — …):** 72%` несёт
# скобку МЕЖДУ именем и `:` → in-place fill не матчился, hard-gate ловушка. Терпим `(...)` перед `:`.
_RELIABILITY_RE = re.compile(
    r"(?im)^\s*[-*>]*\s*\*{0,2}\s*(?:final[\s-]*)?reliability\s*(?:\([^)]*\))?\s*\*{0,2}\s*[:=]\s*\**\s*(\d{1,3})\s*%")
RELIABILITY_MIN = 50


def _reliability_pct(ledger_text):
    """Финальная Reliability % из ledger (`Reliability: 72%` / `Final Reliability = 40%`). Берёт ПОСЛЕДНЮЮ
    записанную (финальная оценка главного агента после 2 cold-агентов). None — не записана. Плейсхолдер
    `{…}`-строка пропускается. `>`-blockquote (RULES-проза) исключён (не поле)."""
    vals = []
    for line in (ledger_text or "").splitlines():
        if "{" in line or line.lstrip().startswith(">"):
            continue
        m = _RELIABILITY_RE.match(line)
        if m:
            vals.append(int(m.group(1)))
    return vals[-1] if vals else None


# ── FEAT-B (jito-live 2026-08-12, the operator: «под имунне шаблон есть, но берёт иногда не тот»): платформа-
# детект → правильный шаблон репорта. При HUNT-EXIT на Immunefi-таргете форсим шаблон
# `templates/dapp_reports/immunefi_dapp.md` (submit-нудж). Off: exit не объявлен, не Immunefi, шаблон указан.
_PLATFORM_RE = re.compile(r"(?im)^\s*[-*>]*\s*\*{0,2}\s*platform\s*[:=]\s*\**\s*([^\n*`]+)")
_IMMUNEFI_RE = re.compile(r"immunefi", re.I)
_REPORT_TMPL_RE = re.compile(r"report[-\s]?template\s*[:=]|immunefi_dapp\.md|disclosure_web3\.md", re.I)


def active_report_template_unset(current_sid):
    """FEAT-B: HUNT-EXIT на Immunefi-таргете, но правильный шаблон репорта не выбран → nudge использовать
    `templates/dapp_reports/immunefi_dapp.md` (the operator: «берёт иногда не тот»). Возвращает relpath|None.
    Off: exit не объявлен, MANUAL, платформа не Immunefi, шаблон уже указан."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt):
        return None
    if not _has_valid_exit(lt):
        return None                                      # не готов подавать → рано про шаблон
    plat = _PLATFORM_RE.search(lt)
    if not plat or not _IMMUNEFI_RE.search(plat.group(1)):
        return None                                      # не Immunefi (у др. платформ свой шаблон/поток)
    if _line_signal_present(lt, _REPORT_TMPL_RE):
        return None                                      # шаблон явно выбран (Z2: skip плейсхолдер-инструкцию immunefi_dapp.md)
    return os.path.relpath(ledger, root)


REPORT_TEMPLATE_REASON = (
    "REPORT TEMPLATE UNSET (FEAT-B, jito-live 2026-08-12). Ledger `%s`: HUNT-EXIT на Immunefi-таргете, но "
    "шаблон репорта не выбран — берётся «иногда не тот» (the operator). Для Immunefi заполняй СТРОГО по "
    "`templates/dapp_reports/immunefi_dapp.md` (Immunefi-специфичная структура: severity по их рубрике, "
    "Bug Description / Impact / Risk / PoC / Recommendation). Впиши `report-template: immunefi_dapp.md` и "
    "заполни репорт по нему (не generic disclosure). Это НЕ выход петли (satisfiable, soft)."
)


def active_lowrel_exit_blocked(current_sid):
    """FEAT-A: HUNT-EXIT High/Crit объявлен, но финальная Reliability НЕ записана ИЛИ <RELIABILITY_MIN →
    держим выход. 2 cold-агента T4-v2 дают Reliability% + свой финальный T4; <50% = не подавать даже
    High/Crit, банкуй `[LOW-RELIABILITY]`, петля продолжается. Возвращает (rel_path, pct|-1) либо None.
    Off: MANUAL (не форсим), exit не объявлен, Reliability≥порог. Живёт в success-каскаде."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt):
        return None                                      # ручной режим — не форсим
    if not _has_valid_exit(lt):
        return None                                      # exit не объявлен → не наше дело
    pct = _reliability_pct(lt)
    if pct is not None and pct >= RELIABILITY_MIN:
        return None                                      # Reliability достаточна → выпускаем
    return (os.path.relpath(ledger, root), pct if pct is not None else -1)


LOWREL_EXIT_REASON = (
    "LOW-RELIABILITY EXIT BLOCKED (FEAT-A T4-v2, jito-live 2026-08-12). Ledger `%s`: HUNT-EXIT High/Crit "
    "объявлен, но финальная Reliability = %s (нужно ≥50%%). Reliability = payability («заплатят», не просто "
    "«баг реален»). ПОРЯДОК: (1) 2 СУРОВЫХ COLD-агента (maker≠checker, независимые) перепроверяют находку и "
    "КАЖДЫЙ даёт Reliability%% по осям: **жив ли баг СЕЙЧАС** (live-current, не forkable history) · **$-at-risk** "
    "(на форке, FEAT-L) · **severity-push-потолок** (реальная magnitude, не инфляция) · **триаж-риск** (не "
    "закроют ли dup/known-issue/intended/OOS/centralization); (2) ТЫ в основной сессии делаешь свой финальный "
    "T4 и ставишь **`Final Reliability: N%%`**. Если N<50 — НЕ подавай даже High/Crit: void HUNT-EXIT "
    "(`SUPERSEDED — reliability N%%`), банкни находку `[LOW-RELIABILITY]` в `## Banked Findings`, и петля "
    "ПРОДОЛЖАЕТСЯ (the operator: «лежат забанкованые, охота не заканчивается»). Если N≥50 — впиши `Final Reliability: "
    "N%%` и выход откроется. Это НЕ обычный soft-nudge — это финальный payability-gate перед подачей."
)


# active_t4_integrator_missing (the operator 2026-08-18, T4-v2 3-агента) — High/Crit-подача требует A3 cold-
# ИНТЕГРАТОРА сверх 2 специалистов (A1 validity+dedup / A2 scope+payability). A3 = 3-й cold-агент, СЛЕПОЙ
# к выводам A1/A2 (без анкера), мандат: независимо пере-вывести ОБА домена + найти ШОВ — validity×payability
# interaction (та же precondition/актор/клауза, что делает баг валидным, не она ли меняет scope/severity?
# veda D-01: compromised-strategist оживляет cap-bypass = ровно то, что триаж закрывает как centralization).
# Сплит-пара A1/A2 структурно слепа на шве — каждый держит ПОЛОВИНУ. A3 = seam-integrator + tie-break.
# ТОЛЬКО High/Crit (money-critical); Med/Low = 2 специалиста (шов-риск пропорционален ставке). Fire ⇔
# High/Crit HUNT-EXIT И нет A3-seam-вердикта в Verifier Log. Off: MANUAL/OFF, не exit. Satisfiable. Живёт в
# success-каскаде (рядом с lowrel — A3 питает Final Reliability). feedback_detector_state_not_phrase: ключ —
# наличие A3-записи+seam-вердикта, не словоформа.
_T4_A3_RE = re.compile(r"(?i)\b(?:t4[\s\-]?)?a3\b.*(?:integrator|seam|интеграт)")
_T4_A3_SEAM_RE = re.compile(r"(?i)seam[\s\-:=]*(?:clear|flip|clean|ok|проверен|чист|флип|held)")


def active_t4_integrator_missing(current_sid):
    """High/Crit-подача без A3 cold-интегратора (seam-вердикт validity×payability). Fire ⇔ valid exit И
    нет (A3-запись И seam-вердикт) в FILLED (не `{}`-шаблон / не blockquote / не backtick) Verifier Log.
    Off: MANUAL/OFF, не exit. Satisfiable soft-nudge (A3 = 3-й cold-агент на Crit/High). relpath|None."""
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return None
    if not _has_valid_exit(lt):
        return None                                      # только на High/Crit-подаче
    a3 = seam = False
    depth = 0
    for line in lt.splitlines():
        opens, closes = line.count("{"), line.count("}")
        inside = depth > 0 or opens > 0
        depth = max(0, depth + opens - closes)
        s = line.lstrip()
        if inside or s.startswith(">"):
            continue
        bare = re.sub(r"`[^`]*`", " ", line)
        if _T4_A3_RE.search(bare):
            a3 = True
        if _T4_A3_SEAM_RE.search(bare):
            seam = True
    if a3 and seam:
        return None                                      # A3-интегратор + seam-вердикт записан
    return os.path.relpath(ledger, root)


T4_INTEGRATOR_REASON = (
    "T4 A3-INTEGRATOR MISSING (the operator 2026-08-18, T4-v2 3-агента). Ledger `%s`: подача **High/Critical**, но "
    "в Verifier Log нет A3-интегратора с seam-вердиктом. T4-v2 = **сплит-специалисты A1 (validity+repro+"
    "dedup) / A2 (scope+payability+$-at-risk+триаж)** идут ГЛУБОКО, но структурно слепы на ШВЕ между "
    "валидностью и payability: часто баг валиден и OOS по ОДНОЙ причине (veda D-01: compromised-strategist, "
    "что оживляет cap-bypass, = ровно то, что триаж закроет как centralization). На High/Crit нужен **A3 = "
    "3-й COLD-агент (general-purpose), СЛЕПОЙ к выводам A1/A2** (без анкера): независимо пере-выводит ОБА "
    "домена + целенаправленно ищет шов — «та же precondition/актор/клауза, что даёт валидность, не меняет "
    "ли scope/severity?» + независимый overall (tie-break). СЕЙЧАС: запусти A3 cold-субагентом, впиши "
    "`T4-A3 [integrator]: SEAM-CLEAR|SEAM-FLIP — <overall verdict> — seam:<взаимодействие validity×payability> "
    "— checker:cold-subagent(blind)`. **A3 нашёл SEAM-FLIP → void HUNT-EXIT** (баг не payable, как казалось), "
    "петля продолжается. Med/Low A3 НЕ нужен (2 специалиста; шов-риск пропорционален ставке). Satisfiable — "
    "прогони A3, петля держится только до записи seam-вердикта."
)


# ─── FALSE-EXHAUSTION guard (KAST 2026-07-07) ──────────────────────────────────────────────────
# KAST-класс: инстанс объявил ~1500 LOC «exhaustively verified / deployed=audited / достижимого
# High-Crit нет» после ~13 kill'ов и НУЛЯ записей в Verifier Log. Ложная исчерпанность, замаскированная
# под «схлопывание скоупа». Корень — НЕ дыра в give-up-детекторе (её латаем как бэкстоп выше), а
# отсутствие требования ПОЗИТИВНОГО доказательства глубины: инстанс убил гору гипотез, не запустив
# ни одной adversarial-проверки, и упаковал вердикт в легит-паузу. Fix = контекст, а не фраза:
#   (1) T4-integrity — kill, ссылающийся на T4/cold-verify, ОБЯЗАН иметь запись в Verifier Log;
#   (2) exhaustion-shape — ≥EXHAUSTION_KILL_MIN soft-kill'ов + пустой T4-лог = доказанно мелкая
#       проработка → мягкая exhaustion-лексика начинает считаться give-up. В ЗДОРОВОМ ledger те же
#       слова НЕ блокируют (обычное обсуждение одной гипотезы) — phrasing не трогаем, трогаем СОСТОЯНИЕ.
# OBS-17b (2026-07-28): тег с СУФФИКСОМ (`[KILLED — intended]`, `[DUP — known-issue]`, `[SCOPED-OUT: …]`)
# раньше НЕ считался (regex требовал `\]` сразу) → гейт зависел от дисциплины писать голый `[KILLED]`, а я
# её не держал (реальные kill'ы decentraland `[DUP-provisional]`/`[KILLED — intended]` давали count=0 →
# false-NEGATIVE: 6 таких kill'ов + пустой verifier НЕ ловились). Матчим ключевое слово + `\b` (суффикс
# ок). Precision держит `_real_kill_count` (strip scaffold + `{`-плейсхолдеры), поэтому расширение не
# возвращает template-FP. Добавлены DUP/DUPLICATE/KNOWN-ISSUE (known-issue-dup — kill-категория гейта).
_KILL_TAG_RE = re.compile(
    r"\[\s*(?:KILLED|SCOPED[-\s]?OUT|DE[-\s]?MINIMIS|DUP|DUPLICATE|KNOWN[-\s]?ISSUE|"
    r"ASSUMED[-\s]?CANONICAL)\b", re.I)
_T4_CLAIM_RE = re.compile(r"T4[\s\-]*(?:verdict|kill|убил|confirm|verify|cold)|cold[\s\-]*verif", re.I)
EXHAUSTION_KILL_MIN = 6   # ≥ столько soft-kill'ов при пустом Verifier Log = exhaustion-shape

# Мягкая exhaustion-лексика — вердикт-слова «тут больше нет бага». Учитывается ТОЛЬКО в exhaustion-
# shape (иначе те же слова в здоровом обсуждении = FP). НЕ включаем голое «чист/clean» (FP на «gap-map
# чист») — только явные вердикт-фразы.
SOFT_EXHAUSTION = [
    "исчерпан", "исчерпыва", "exhaust", "deployed=audited", "deployed == audited",
    "deployed соответств", "provably balanc", "provably bound", "verified hardened",
    "exhaustively verified", "exhaustively-verified", "hardened", "well-audited",
    "de-minimis", "де-минимис", "достижим", "achievable", "все кандидаты мертв",
    "нет ни одного", "no findings", "nothing found", "surface exhausted", "жечь",
]


def _verifier_log_empty(txt):
    """True если секция `## Verifier Log` не содержит НИ ОДНОЙ реальной записи (только template-
    placeholder `- {timestamp} — H-{NN} …`). Реальная запись = строка-буллет БЕЗ `{`-плейсхолдера,
    упоминающая H-<цифра>. Нет секции → считаем пустой."""
    m = re.search(r"##\s*Verifier Log(.*)$", txt, re.I | re.S)
    if not m:
        return True
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith("-") and "{" not in s and re.search(r"H-\d", s):
            return False   # реальная T4-запись найдена
    return True


# ── WORKLIST DRIVER Этап 3 — Слой 3 (verifier-канал): T4-ДЕКОМПОЗИЦИЯ ────────────────────────────
# План §1 Слой-3 / §2 рубрика ось-4: «T4 = полный набор под-шагов (STEP 0/1.5/2.5-4gate/2.6/2.7 +
# evidence + confidence), а НЕ факт строки `T4: PASS`». Stop-хук НЕ может спавнить cold-агента — он
# ВАЛИДИРУЕТ ФАКТ его работы. mythos Technique 4 STEP 3 УЖЕ говорит «verifier-log без fresh-runtime
# (2.6) / precondition-matrix (2.7) → not submit-ready», но ПРОЗОЙ → пропускаемо (тот же класс, что
# OOS-промах: хук > проза). Гейт срабатывает ТОЛЬКО на submit-момент (HUNT-EXIT = готов подавать),
# satisfiable (называет недостающие под-шаги). Проверяет 5 критичных маркеров в `## Verifier Log`:
#   STEP 0 dedup · cold-checker (B5) · терминальный verdict · STEP 2.6 fresh-runtime · STEP 2.7 матрица.
_T4_MIN_CONFIDENCE = 80   # mythos: confidence <80 → это LEAD, не submit
# Судья-ось-4 Д1/Д4/Д7: покрываем ВСЕ под-шаги, названные рубрикой §2, и требуем ИСХОД (а не просто
# упоминание шага) там, где негативный исход = KILL по эталону: dedup с МАТЧЕМ (mythos STEP 0) и
# fresh-runtime `PoC FAIL` (mythos STEP 2.6) означают, что находка МЕРТВА — такой ledger не submit-ready.
_T4_SUB = (
    ("STEP 0 dedup С ИСХОДОМ «чисто» (audit/known-issue/Solodit; МАТЧ = дубль = $0 = KILL, не подача)",
     # ре-судья D8: окно 160→260 (перечисление audit-файлов + core-nouns ПЕРЕД «→ чисто» превышало 160
     # → false-fire на легит clean-dedup).
     re.compile(r"(step\s*0|dedup|previously[\s-]?disclosed|solodit|known[\s-]?issue)[^\n]{0,260}?"
                r"(чист|clean|no[\s-]?match|нет\s+матч|не\s+найден|not\s+found|prior[\s-]?art\s*:?\s*(нет|none|no))", re.I)),
    ("STEP 1.5 self-steelman (сам написал case ПРОТИВ находки ДО передачи checker'у)",
     re.compile(r"step\s*1\.5|self[\s-]?steelman|steelman|case\s+against|контр[\s-]?аргумент", re.I)),
    # RT-Д4: `cold subagent` БЕЗ префикса `checker:` — естественная формулировка, ложно фаирила.
    ("checker:cold-subagent (B5 — холодный, не warm-main)",
     re.compile(r"cold[\s-]?subagent|cold[\s-]?context\s+(verifier|agent|subagent)|maker\s*≠\s*checker"
                r"|холодн\w*\s+(субагент|верификатор)", re.I)),
    # RT-Д5: синонимы вердикта (`Result: CONFIRMED` / `Вывод: PASS`) — форма не должна нагружать переписью.
    # ре-судья D6: `\**\s*` + требование двоеточия сужает спуф «итог: reject гипотезы X» в прозе — вердикт
    # обязан стоять сразу за ключом (окно 0), а не где-то в предложении.
    ("терминальный verdict (PASS/DOWNGRADE/BLOCK/REJECT — «probably real» не вердикт)",
     re.compile(r"(verdict|вердикт)\s*:?\s*\**\s*(pass|confirm|downgrade|block|reject|kill)"
                r"|(result|вывод|conclusion|итог)\s*:\s*\**\s*(pass|confirm(ed)?|downgrade|block|reject|kill)", re.I)),
    # ре-судья D6: голое `reachability` больше НЕ засчитывает все 4 гейта — нужен явный маркер набора
    # (`STEP 2.5` / `4 gates` / `gate1..gate4`) ЛИБО ≥2 разных гейт-имени в одной записи.
    ("STEP 2.5 четыре последовательных гейта (attack-execution → reachability → trigger → impact)",
     re.compile(r"step\s*2\.5|4\s*gate|четыре\s+гейт"
                r"|gate\s*[1-4][^\n]{0,200}?gate\s*[1-4]"
                r"|(attack[\s-]?execution|reachability|trigger|impact)[^\n]{0,200}?"
                r"(attack[\s-]?execution|reachability|trigger|impact)", re.I)),
    # ре-судья D1 (named в якоре-10): mythos STEP 1 — «No artifact = it's a LEAD, not a finding».
    ("evidence-artifact (СЫРОЙ вывод PoC: tx-hash/trace/stdout/receipt/лог-файл — не пересказ)",
     re.compile(r"evidence|artifact|артефакт|tx[\s-]?hash|0x[0-9a-f]{16,}|trace|stdout|receipt|"
                r"forge\s+test|cast\s+call|anvil|лог[\s-]?файл|\.log\b|\.json\b", re.I)),
    # ре-судья D3 (named в якоре-10): mythos STEP 0 SUBMIT-TIME FRESHNESS — жив ли баг СЕЙЧАС
    # (deployed≠HEAD, фикс мог быть задеплоен между находкой и подачей).
    ("current-exploitability (жив СЕЙЧАС: свежий блок/deployed-code сверен, не forkable history)",
     re.compile(r"current[\s-]?exploitab|submit[\s-]?time\s+fresh|freshness|жив\s+сейчас|live[\s-]?current|"
                r"deployed[\s^\n]{0,12}(≠|!=|vs|соответств)|code[\s-]?hash|актуальн\w*\s+блок|current\s+block", re.I)),
    ("STEP 2.6 fresh-runtime С ИСХОДОМ «PoC PASS» (FAIL на свежем состоянии = баг жил в residue = KILL)",
     re.compile(r"(step\s*2\.6|fresh[\s-]?runtime|re[\s-]?provision|fresh\s+(fork|session|burner|state))"
                r"[^\n]{0,200}?(poc\s*:?\s*pass|pass\s+on\s+fresh|прош[её]л|воспроизв|reproduc)", re.I)),
    ("STEP 2.7 precondition negative-control matrix (каждая precondition флипнута + unstated)",
     re.compile(r"step\s*2\.7|precondition[\s-]?matrix|negative[\s-]?control|precondition.{0,30}(pass|fail|fires)", re.I)),
)
_T4_CONFIDENCE_RE = re.compile(r"confidence\s*:?\s*\**\s*(\d{1,3})\s*%?", re.I)


# RT-Д3: строка считается ШАБЛОННОЙ только по КАНОНИЧЕСКИМ плейсхолдерам, а не по любому `{`
# (голый `"{" not in l` рубил ЛЕГИТ-записи с solidity/JSON-снипетами `balances[a]={0}` и `{85}%` →
# ложное срабатывание на валидной работе). Плейсхолдеры канона: {timestamp} {дата} {NN} {N} H-{NN} {tier}.
# ре-судья D7: точные КАНОНИЧЕСКИЕ токены с `}`-границей — голое `N`/`block`/`date` матчило легит
# `{nonce}`/`{blockNumber}`/`{precondition}` и выбрасывало валидную строку целиком (false-fire).
_T4_PLACEHOLDER_RE = re.compile(
    r"\{\s*(timestamp|дата|date|NN|N|tier|block|\.\.\.)\s*\}"
    r"|H-\{NN\}|\{прогнал|\{мой сильнейший|\{re-provisioned|\{precond-1", re.I)


def _verifier_log_body(txt):
    """Тело секции `## Verifier Log` БЕЗ `>`-blockquote-гайда (он описывает правила и содержит те же
    слова — иначе гейт читал бы собственную инструкцию как выполненную работу; тот же класс, что
    `_strip_scaffold`) и БЕЗ шаблонных placeholder-строк. '' — секции нет."""
    m = re.search(r"##\s*Verifier Log(.*?)(?=\n##\s|\Z)", txt or "", re.I | re.S)
    if not m:
        return ""
    return "\n".join(l for l in m.group(1).splitlines()
                     if not l.lstrip().startswith(">") and not _T4_PLACEHOLDER_RE.search(l))


def active_t4_decomposition_incomplete(current_sid):
    """Worklist Driver Этап 3 (Слой 3, ось-4). На submit-моменте (HUNT-EXIT объявлен) `## Verifier Log`
    обязан нести ПОЛНЫЙ T4, а не одну строку «verdict: confirm». Возвращает (relpath, «чего не хватает»)
    либо None. Off: флаг off; MANUAL/OFF; нет HUNT-EXIT (не submit-момент); void-exit."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(txt) or _OFF_RE.search(txt):
        return None
    # RT-Д1 (HIGH): submit-момент определяем ТОЙ ЖЕ позиционной логикой, что впускает в success-путь
    # (`ledger_success_exit`: валиден exit ПОСЛЕ последней отмены). Наивный `_EXIT_VOID_RE.search(txt)`
    # давал рассинхрон: легит re-confirm-after-void входил в success-путь, а гейт молчал (void-маркер
    # выше по тексту) → тонкий T4 выпускался ровно на самой рискованной популяции (прошедшей реверс).
    if not ledger_success_exit(current_sid):
        return None                                        # не submit-момент → гейт спит
    body = _verifier_log_body(txt)
    missing = [label for label, rx in _T4_SUB if not rx.search(body)]
    # confidence≥80 (судья-ось-4 Д2: шаблон учит полю `confidence: N%`, детектор его игнорировал —
    # template↔detector рассинхрон). mythos: <80 → это LEAD, не submit. Берём МАКСИМУМ по записям
    # (в логе могут быть старые kill-записи с низкой уверенностью — судим по лучшей).
    _confs = [int(m.group(1)) for m in _T4_CONFIDENCE_RE.finditer(body) if m.group(1).isdigit()]
    if not _confs:
        missing.append("confidence: N%% (число; mythos: <%d%%%% = LEAD, не submit)" % _T4_MIN_CONFIDENCE)
    elif max(_confs) < _T4_MIN_CONFIDENCE:
        missing.append("confidence ≥%d%%%% (сейчас %d%%%% → это LEAD, не submit-ready)"
                       % (_T4_MIN_CONFIDENCE, max(_confs)))
    if not missing:
        return None
    return (os.path.relpath(ledger, root), "; ".join(missing))


T4_DECOMPOSITION_REASON = (
    "T4-DECOMPOSITION INCOMPLETE (Worklist Driver Этап 3, Слой-3 verifier-канал, 2026-08-11). Ledger "
    "`%s`: ты объявил `HUNT-EXIT` (готов подавать High/Critical), но `## Verifier Log` НЕ несёт полный "
    "T4 — не хватает: **%s**. Строка «verdict: confirm» ≠ T4: mythos Technique 4 STEP 3 прямо говорит "
    "«verifier-log без fresh-runtime (2.6) или precondition-matrix (2.7) → NOT submit-ready, находка "
    "верифицирована НЕполно вне зависимости от tier». Cold-верификация убивает ~25%% ложных — это "
    "дешевле, чем rejected-репорт + rep-friction. СЕЙЧАС: спавни ХОЛОДНЫЙ субагент (fresh context, "
    "maker≠checker, `general-purpose`) и залогируй его работу в `## Verifier Log` по канону: "
    "`- <дата> — H-NN — STEP 0 dedup: <audits/Solodit прогон, чисто> — verdict: PASS|DOWNGRADE-to-<tier>"
    "|BLOCK|REJECT — checker:cold-subagent — STEP 2.6 fresh-runtime: re-provisioned <fresh fork@block / "
    "fresh session+burner>, PoC PASS|FAIL — STEP 2.7 precondition-matrix: <precond-1 OFF → fires/not-"
    "fires; …> + unstated: <...> — confidence: <N>%%`. ⚠ Каждый под-шаг — РЕАЛЬНЫЙ прогон, не "
    "декларация: статика проверяет НАЛИЧИЕ и ИСХОД записи, но доказать, что cold-прогон был, она НЕ "
    "может — фабрикацию полной записи не ловит НИКТО (T4-INTEGRITY ловит лишь ОТСУТСТВИЕ записи и в "
    "success-пути даже не достигается). Это твоя профессиональная честность, а не гонка с гейтом: "
    "фиктивный T4 = rejected-репорт + rep-damage, дороже любого прогона. Это НЕ выход петли "
    "(satisfiable) — доверифицируй и подавай."
)


# ── FIX-J (T4-backstop hardening, стресс-тест 2026-08-12): фабрикацию Verifier Log НЕ ловил НИКТО ──────
# Стресс: shaped-но-липовый T4-лог (все 10 маркеров + `forge test → PASS`/`tx 0xdead…` вписаны руками,
# 0 прогонов) → ВСЕ 3 T4-гейта пропустили. Stop-хук физически НЕ может запустить forge → executable-
# верификация невозможна В хуке. ЕДИНСТВЕННОЕ, что хук может дёшево+offline: проверить, что PoC-ТЕСТ-
# ФАЙЛЫ, на которые ссылается лог (`exploit.t.sol`/`poc.t.rs`), реально существуют co-located (зеркало
# active_observed_fabricated / FIX-H). Поднимает цену фабрикации со «впиши строку» до «создай файл».
# ЧЕСТНЫЙ ПОТОЛОК: inline-only evidence (fake tx-hash без файла) + fake `poc.log`-цитата НЕ ловятся — это
# the operator/harness-территория (петля отдаёт claimed High/Crit человеку). Fail-open: нет co-located test-дерева
# / тест-файлы не цитируются / ≥1 резолвится → silent. Фаирит на near-certain фабрикации (цитируемые
# `.t.sol`/`.t.rs` того типа есть в дереве, но ни один цитируемый basename не существует).
# judge-6 FP-fix: armed ТОЛЬКО PoC-тест-файлы `.t.sol`/`.t.rs`. `.log`/`.json`/`.txt`/`.out` ВЫБРОШЕНЫ —
# они decoy-prone: честный хант гонит PoC в Docker (poc.log остаётся в контейнере, НЕ в session-папке), а
# session типично засорена same-type recon-шумом (recon.log/scout.json/nuclei.out) → FIX-J ложно фаирил бы
# «фабрикация» на ЧЕСТНОМ ханте на submit-моменте (FP). PoC-тест-файл (`exploit.t.sol`) редко decoy — это
# сильнейший чистый сигнал (цитата на несуществующий PoC-тест), почти без FP. Цена: фабрикатор, цитирующий
# fake `poc.log` вместо fake `.t.sol`, не ловится — но это тот же inline-класс, честный потолок (harness/the operator).
_T4_ARTIFACT_FILE_RE = re.compile(r"\b([\w./\\-]+\.(?:t\.sol|t\.rs))\b", re.I)
_T4_ARTIFACT_EXTS = (".t.sol", ".t.rs")


def _artifact_basename(path):
    """basename с учётом двойных расширений `.t.sol`/`.t.rs` (os.path.basename достаточно — двойной
    суффикс сохраняется в basename)."""
    return os.path.basename((path or "").replace("\\", "/")).lower()


def _session_artifact_basenames(session_dir):
    """Множество lower-basename'ов artifact-файлов (log/json/txt/out/trace/*.t.sol/*.t.rs) под
    session_dir (bounded). None = НЕВЕРИФИЦИРУЕМО (fail-open): нет co-located artifact-дерева ЛИБО
    клон > _MAX_SRC_SCAN. Зеркало _session_src_basenames, другой набор расширений."""
    names = set()
    count = 0
    try:
        for dirpath, dirs, files in os.walk(session_dir):
            dirs[:] = [d for d in dirs if d not in _SRC_SCAN_SKIP_DIRS]
            for fn in files:
                low = fn.lower()
                if low.endswith(_T4_ARTIFACT_EXTS):
                    names.add(low)
                    count += 1
                    if count > _MAX_SRC_SCAN:
                        return None
    except Exception:
        return None
    return names or None


def _cited_artifact_ext(basename):
    """Расширение artifact-файла с учётом двойного `.t.sol`/`.t.rs`."""
    low = (basename or "").lower()
    for e in (".t.sol", ".t.rs"):
        if low.endswith(e):
            return e
    return os.path.splitext(low)[1]


def active_t4_evidence_fabricated(current_sid):
    """FIX-J (T4-backstop hardening): на submit-моменте (`HUNT-EXIT`) `## Verifier Log` ссылается на
    PoC-ТЕСТ-ФАЙЛЫ (`exploit.t.sol`/`poc.t.rs`), НО НИ ОДИН не существует в co-located session-дереве
    (при наличии дерева с тест-файлами того же типа) → evidence-артефакт сфабрикован (цитата на
    несуществующий PoC-тест). Зеркало active_observed_fabricated для T4-канала. FP-safe fail-open: не
    submit-момент / нет реестра / тест-файлы не цитируются / нет co-located test-дерева / тип не совпал /
    ≥1 резолвится → silent. judge-6 FP-fix: armed только `.t.sol`/`.t.rs` (не decoy-prone `.log`/`.json`).
    ЧЕСТНЫЙ ПОТОЛОК: inline-only + fake `poc.log`-цитата НЕ ловятся (the operator/harness). Возвращает
    (rel, n_cited) либо None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(txt) or _OFF_RE.search(txt):
        return None
    if not ledger_success_exit(current_sid):
        return None                                        # не submit-момент → спит (как decomposition-гейт)
    if _atom_rows(txt) is None:
        return None                                        # C1: нет реестра → silent
    body = _verifier_log_body(txt)
    cited = set()
    for m in _T4_ARTIFACT_FILE_RE.finditer(body):
        cited.add(_artifact_basename(m.group(1)))
    if not cited:
        return None                                        # inline-only → потолок, не ловим
    names = _session_artifact_basenames(os.path.dirname(ledger))
    if names is None:
        return None                                        # fail-open: нет co-located artifact-дерева
    if any(c in names for c in cited):
        return None                                        # ≥1 резолвится → правдоподобно → silent
    cited_exts = {_cited_artifact_ext(c) for c in cited}
    tree_exts = {_cited_artifact_ext(n) for n in names}
    if not (cited_exts & tree_exts):
        return None                                        # дерево не содержит файлов цитируемого типа → mismatch
    return (os.path.relpath(ledger, root), len(cited))


T4_EVIDENCE_FABRICATED_REASON = (
    "T4-EVIDENCE FABRICATED (FIX-J, T4-backstop hardening, стресс-тест 2026-08-12). Ledger `%s`: ты "
    "объявил `HUNT-EXIT` (готов подавать High/Critical), `## Verifier Log` ссылается на %d PoC-тест-"
    "файл(ов) (`exploit.t.sol`/`poc.t.rs`), НО НИ ОДИН не существует в co-located session-дереве "
    "(тест-дерево того же типа есть, цитируемые basename'ы отсутствуют). evidence-артефакт сфабрикован — "
    "цитата на несуществующий PoC-тест = ложное доказательство глубины на самом дорогом (submit) моменте. "
    "Настоящее доказательство = РЕАЛЬНО прогнанный PoC-тест, лежащий в session-папке и открывающийся. "
    "СЕЙЧАС: прогони PoC реально (fork/Foundry в Docker bbt), сохрани тест-файл в session-папку, сошлись "
    "на РЕАЛЬНЫЙ путь. Это НЕ выход петли (satisfiable) — заземли evidence на существующий артефакт. "
    "(Честный предел: inline evidence + fake `poc.log`-цитата хук не верифицирует — истину исполнения "
    "подтверждает harness-прогон + the operator перед подачей.)"
)


def active_submit_checklist_atom_missing(current_sid):
    """Worklist Driver Этап 3 (§8 G-submit, судья-ось-4 Д3): рубрика требует submit-checklist «КАК АТОМ»,
    а не строкой enum. На submit-моменте (`HUNT-EXIT`) реестр обязан нести атом `type:submit-checklist`
    в статусе CLOSED — доказательство, что `submission_checklist.yaml` (auto_invalid / severity_cap /
    **project-tests** / OOS-CHECK) прогнан по КОНКРЕТНОЙ находке, а не «помню, что надо». Закрывает и
    Д5-часть (project-tests входит в чеклист). Off: флаг off; НЕТ секции `## Atom Registry` (C1 — legacy/
    web без реестра → нулевой blast-radius); MANUAL/OFF; не submit-момент. relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(txt) or _OFF_RE.search(txt):
        return None
    # RT-Д1 (HIGH): submit-момент определяем ТОЙ ЖЕ позиционной логикой, что впускает в success-путь
    # (`ledger_success_exit`: валиден exit ПОСЛЕ последней отмены). Наивный `_EXIT_VOID_RE.search(txt)`
    # давал рассинхрон: легит re-confirm-after-void входил в success-путь, а гейт молчал (void-маркер
    # выше по тексту) → тонкий T4 выпускался ровно на самой рискованной популяции (прошедшей реверс).
    if not ledger_success_exit(current_sid):
        return None                                        # не submit-момент → гейт спит
    rows = _atom_rows(txt)
    if rows is None:
        return None                                        # C1: реестра нет → silent (legacy/web)
    for r in rows:
        if "submit-checklist" in (r.get("type") or "") and r.get("status") == "CLOSED":
            return None                                    # прогнан и закрыт
    return os.path.relpath(ledger, root)


SUBMIT_CHECKLIST_ATOM_REASON = (
    "SUBMIT-CHECKLIST ATOM MISSING (Worklist Driver Этап 3, §8 G-submit, 2026-08-11). Ledger `%s`: ты "
    "объявил `HUNT-EXIT` (готов подавать), но в `## Atom Registry` НЕТ атома `type:submit-checklist` со "
    "статусом `CLOSED`. Pre-submit gate — это РАБОТА по конкретной находке, а не «помню, что надо»: "
    "прогони `sessions/_methodology/submission_checklist.yaml` по НЕЙ и заведи строку "
    "`| SC-01 | submit-checklist | pre-submit <H-NN> | submission_checklist | <rank> | CLOSED | H-NN |`. "
    "Что обязано быть пройдено: **auto_invalid** (out-of-scope-target · out-of-scope-disqualifier-clause · "
    "previously-disclosed) · **severity_cap** (weird-tokens / admin-access / rounding-dust — не завышай "
    "tier) · **project's own tests** (intended behavior = reject + rep-damage: прогони тесты таргета на "
    "своё поведение) · **permissionless-filter** («КТО триггерит?» — governance/admin-only = OOS-мусор) · "
    "**quality_required** (undup-origin present · poc-assertion-fails-on-revert · severity-economic-"
    "justified). Каждый пункт — реальный прогон, результат в теле атома/`## Verifier Log`. Это НЕ выход "
    "петли (satisfiable) — прогони чеклист, закрой атом, подавай."
)


_EXIT_CRIT_RE = re.compile(r"HUNT-EXIT:\s*T4-CONFIRMED[^A-Za-z0-9<]{0,6}CRITICAL\b", re.I)
_EXT_REVIEW_NA_RE = re.compile(r"external[\s-]?review\s*:?\s*\**\s*(N/?A|не\s+нужен|not\s+needed|skip)", re.I)


def active_external_review_atom_missing(current_sid):
    """Worklist Driver Этап 3 (§8 G-peer, ре-судья D2): якорь-10 требует submit-checklist **И
    external-review** «как атомы». Триггер СУЖЕН до CRITICAL-подачи (G-peer: «Critical>$100K / TSS-ZK» —
    hard-гейт на каждую находку дал бы FP там, где внешнее суждение не нужно): на `HUNT-EXIT:
    T4-CONFIRMED Critical` реестр обязан нести атом `type:external-review` в статусе CLOSED ЛИБО явный
    отказ `external-review: N/A — <причина>` в ledger. Off: флаг off; не Critical-выход; нет реестра
    (C1); MANUAL/OFF. Satisfiable soft-nudge. relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(txt) or _OFF_RE.search(txt):
        return None
    if not ledger_success_exit(current_sid):
        return None                                        # не submit-момент
    if not _EXIT_CRIT_RE.search(txt):
        return None                                        # High → внешнее ревью не форсим (G-peer)
    if _EXT_REVIEW_NA_RE.search(txt):
        return None                                        # осознанный отказ с причиной
    rows = _atom_rows(txt)
    if rows is None:
        return None                                        # C1: реестра нет → silent
    for r in rows:
        if "external-review" in (r.get("type") or "") and r.get("status") == "CLOSED":
            return None
    return os.path.relpath(ledger, root)


EXTERNAL_REVIEW_REASON = (
    "EXTERNAL-REVIEW ATOM MISSING (Worklist Driver Этап 3, §8 G-peer, 2026-08-11). Ledger `%s`: подача "
    "**CRITICAL** — самая дорогая и самая рискованная категория (максимальный payout, максимальный "
    "репутационный урон при ошибке), но в `## Atom Registry` НЕТ атома `type:external-review` со "
    "статусом `CLOSED`. Critical-находка заслуживает второго НЕЗАВИСИМОГО взгляда перед отправкой: "
    "спорная платформенная классификация (какой именно tier по рубрике программы) · экономика impact'а "
    "(кто теряет, компаундится ли, возможен ли make-whole) · спорный scope (граница in/out) · "
    "примитив, где мы исторически слабы (TSS/ZK/consensus — см. `learning_paths/`). СЕЙЧАС: заведи "
    "`| ER-01 | external-review | <что ревьюим> | <src> | <rank> | CLOSED | H-NN |` и закрой его "
    "РЕАЛЬНЫМ ревью — cold-субагент с ДРУГИМ фокусом (не тот, что делал T4: тот проверял «реален ли "
    "баг», этот — «правильно ли мы его подаём и оценили») ЛИБО вопрос the operator, если нужно человеческое "
    "решение. Не нужен → впиши `external-review: N/A — <причина>` в ledger. Это НЕ выход петли "
    "(satisfiable) — Critical подаётся один раз, второй взгляд дешевле переподачи."
)


def _banked_confirmed_rows(ledger_text):
    """Banked-строки, ЗАЯВЛЕННЫЕ готовыми к подаче (статус несёт `confirmed`), с их H-NN (если указан).
    `T4-pending`/`pending`/`[HUMAN-PENDING]` НЕ считаются — они ещё не подаются (политика banked:
    статус `confirmed / T4-pending`). Возвращает список (row_text, hnn|None)."""
    sec = _banked_section(ledger_text)
    if not sec:
        return []
    out = []
    for line in sec.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        low = s.lower()
        if "severity" in low and "h-nn" in low:
            continue                                       # header
        if set(s.replace("|", "").strip()) <= set("-: "):
            continue                                       # separator
        if "{" in s:
            continue                                       # placeholder-строка шаблона
        if "confirmed" not in low:
            continue                                       # ещё не заявлена готовой
        if re.search(r"t4-pending|human-pending|\bpending\b", low):
            continue                                       # явно ждёт верификации/актора
        m = re.search(r"(H-\d+)", s, re.I)
        out.append((s, m.group(1).upper() if m else None))
    return out


def active_banked_without_t4(current_sid):
    """Worklist Driver Этап 3 (ре-судья D4 — banked-дыра оси-4): banked Medium/Low подаются ПАЧКОЙ и
    НИКОГДА не пишут `HUNT-EXIT` → submit-гейты (T4-декомпозиция / submit-checklist) для них не
    армятся, и пачка ($2-5K за штуку) уходит с НУЛЕВЫМ enforcement верификации. Держим подачу, когда
    banked-строка ЗАЯВЛЕНА `confirmed` (не `T4-pending`), а её `H-NN` НЕ встречается в `## Verifier Log`.
    Политика banked прямо требует «T4 — перед фактической подачей». Off: MANUAL/OFF; HUNT-EXIT (там
    работают submit-гейты); нет banked-строк `confirmed`; строка без H-NN (нечего сверять). relpath|None."""
    if not WORKLIST_DRIVER_ENABLED:
        return None
    ledger, root = freshest_active_ledger(current_sid)
    if not ledger:
        return None
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    if _MANUAL_RE.search(txt) or _OFF_RE.search(txt):
        return None
    if _has_valid_exit(txt):
        return None                                        # HUNT-EXIT → submit-гейты закрывают
    rows = _banked_confirmed_rows(txt)
    if not rows:
        return None
    vbody = _verifier_log_body(txt)
    for _s, hnn in rows:
        if not hnn:
            continue                                       # строка без H-NN — нечего сверять
        if not _id_match_in_text(hnn, vbody):
            return (os.path.relpath(ledger, root), hnn)
    return None


BANKED_T4_REASON = (
    "BANKED WITHOUT T4 (Worklist Driver Этап 3, ре-судья D4, 2026-08-11). Ledger `%s`: banked-находка "
    "`%s` помечена **confirmed** (= заявлена готовой к batch-подаче), но её `H-NN` НЕ встречается в "
    "`## Verifier Log` — T4 по ней НЕ проведён. Это дыра на самом частом пути денег: banked Medium/Low "
    "подаются ПАЧКОЙ и никогда не пишут `HUNT-EXIT`, поэтому submit-гейты (T4-декомпозиция / "
    "submit-checklist) для них не армятся — пачка ушла бы с нулевой верификацией. Политика banked прямо "
    "требует: **T4 — перед фактической подачей** (в ledger статус `confirmed / T4-pending`). СЕЙЧАС "
    "одно из двух: (а) прогони cold-T4 по этой находке и залогируй в `## Verifier Log` (STEP 0 dedup → "
    "чисто · verdict · `checker:cold-subagent` · STEP 2.6 fresh-runtime PoC PASS · STEP 2.7 "
    "precondition-matrix · confidence), ЛИБО (б) верни статус в `T4-pending`, если подавать ещё рано. "
    "Medium $2-5K × N в пачке — не дешевле, чем один High: rejected-пачка бьёт по rep так же. "
    "Satisfiable — верифицируй и подавай."
)


def ledger_exhaustion_shape(current_sid):
    """True = ledger в 'форме исчерпанности': ≥EXHAUSTION_KILL_MIN soft-kill'ов И пустой Verifier Log.
    Это НЕ вывод 'багов нет' — это 'много убито, ноль adversarial-проверок' = доказанно мелкая
    проработка. В этом состоянии мягкая exhaustion-лексика трактуется как give-up (anti-FP: порог
    ≥6 — ранний хант с 2-3 kill'ами не триггерит)."""
    t = _read_ledger(current_sid)
    if not t:
        return False
    return _real_kill_count(t) >= EXHAUSTION_KILL_MIN and _verifier_log_empty(t)


def soft_exhaustion_signal(text):
    """Мягкая exhaustion-лексика в сообщении (учитывается ТОЛЬКО когда ledger_exhaustion_shape)."""
    low = text.lower()
    return [s for s in SOFT_EXHAUSTION if s in low]


def _strip_scaffold(txt):
    """FP-fix (2026-07-16): убирает template-scaffold перед поиском claim-паттернов, чтобы гейт
    матчил РЕАЛЬНЫЕ заявления в kill-телах, а НЕ собственную template-прозу (rules-блок + `>`-гайд-
    блокноты в Refuted/Verifier-Log-заголовках содержат «cold-verify»/«T4-аудит» как ОПИСАНИЕ правила →
    старый голый search(t) их ловил → фейковый T4-INTEGRITY блок на каждом заполненном ledger'е)."""
    m = re.search(r"(?im)^#\s+\S.*hypotheses registry", txt)
    body = txt[m.end():] if m else txt
    # drop: (a) `>`-гайд-блокноты; (b) exit-condition boilerplate строки (`HUNT-EXIT`/`T4-confirmed` —
    # это описание УСПЕШНОГО выхода петли, НЕ claim о cold-verify kill'а; ловится отдельным exit-механизмом).
    out = []
    for l in body.splitlines():
        s = l.lstrip()
        if s.startswith(">"):
            continue
        if re.search(r"hunt-exit|t4-confirmed", l, re.I):
            continue
        out.append(l)
    return "\n".join(out)


def _real_kill_count(txt):
    """OBS-17 (2026-07-28): считает РЕАЛЬНЫЕ kill-теги, НЕ template-scaffold. Голый
    `_KILL_TAG_RE.findall(txt)` ловил 8 примеров из kill-таксономии (rules-блок + `>`-гайды +
    плейсхолдер `### H-{NN} [KILLED]: {one-line}`) → ЛЮБОЙ свежесозданный ledger давал kills=8≥6 →
    exhaustion_shape ложно True на pristine/спурьёзном ledger'е (тот же класс template-слепоты, что
    OBS-3). Фикс: strip scaffold (`>`-блоки, pre-registry rules) + отбрасываем `{`-плейсхолдер-строки."""
    n = 0
    for l in _strip_scaffold(txt).splitlines():
        if "{" in l:            # template-плейсхолдер (`[KILLED]: {one-line}`) — не реальный kill
            continue
        n += len(_KILL_TAG_RE.findall(l))
    return n


def ledger_t4_claimed_but_unlogged(current_sid):
    """True если ledger ССЫЛАЕТСЯ на T4/cold-verify в kill'ах, но Verifier Log ПУСТ (KAST: 'T4 verdict:
    DOWNGRADE' в прозе H-01, Verifier Log = template placeholder). Fake-T4 integrity check. Анти-FP:
    требует ≥3 kill'а (ранний хант без kill'ов не триггерит) + T4-claim ищется в теле БЕЗ template-scaffold."""
    t = _read_ledger(current_sid)
    if not t:
        return False
    if _real_kill_count(t) < 3:   # OBS-17: реальные kill'ы, не template-scaffold
        return False
    return bool(_T4_CLAIM_RE.search(_strip_scaffold(t))) and _verifier_log_empty(t)


# ─── AOE §2.1/§4/§5.3/§5.4 — PROFILE-CLEARED gate (attacker-capability realism, symmetric) ─────
# Чинит рецидивный промах «преждевременный practicality-рефьют» (Superform/ShapeShift-реверсы):
# система убивает баг как «непрактично / де-минимис / дорого», не посчитав РЕАЛЬНЫЕ ресурсы
# атакующего (flash-liquidity / MEV-bundle / multi-block / Sybil) и не сверив с payout-clauses.
#
# Механизм = ledger_t4_claimed_but_unlogged (ОБРАЗЕЦ): гейт на СОСТОЯНИЕ структурного ТЕГА, НЕ на
# лексику (лексика битая 5×). Practicality-kill = канонический тег `[DE-MINIMIS]` / `[PRACTICALITY]`
# / структурное поле `practicality:` (refute-сторона). Capital-dependent confirm = тег `[CAPITAL-DEP]`
# (confirm-сторона: severity держится ТОЛЬКО на «профитно при экзотическом капитале»). ЛЮБОЙ из них
# ОБЯЗАН нести companion-поле `profile-cleared: <ref>` — иначе гейт держит выход (симметрия §2.1: и
# refute, и confirm нетятся против профиля attacker_capability_baseline.md, не против сырого «дорого»).
# `profile-cleared` покрывает и manufacturable-preconditions (§2.1 №2: «нужен разбаланс/nonce/резерв» →
# создаётся ли дёшево через профиль? flash-swap двигает резерв в тот же tx = НЕ рефьют).
#
# corpus-first (§2.1/§4/§6): hard-блок активен ТОЛЬКО при >=2 labeled false-refute кейсах в
# regression_manifest.yaml (§6, предусловие трека — measure-don't-feel: сначала replay-тест, потом гейт).
# <2 / битый манифест → reminder-режим (не держит выход). fail-open: любая поломка → None (как все детекторы).
#
# §5.4 white-hat: `profile-cleared: UNRESOLVED-needs-approval` — ВАЛИДНЫЙ не-блокирующий статус
# (реализм достижим только active-пробой → гейт НЕ форсит active-действие, спрашиваем the operator per-vector).
FALSE_REFUTE_CORPUS_MIN = 2
_DEMINIMIS_TAG_RE = re.compile(r"\[\s*(?:DE[-\s]?MINIMIS|PRACTICALITY)\b", re.I)
_CAPITAL_DEP_TAG_RE = re.compile(r"\[\s*CAPITAL[-\s]?DEP\b", re.I)
_PRACTICALITY_FIELD_RE = re.compile(r"^\s*[-*>\s]*\**\s*practicality\s*\**\s*[:=]", re.I)
# companion-поле `profile-cleared: <ref>` (ref непустой; UNRESOLVED-needs-approval валиден — §5.4).
_PROFILE_CLEARED_RE = re.compile(r"^\s*[-*>\s]*\**\s*profile[-\s]?cleared\s*\**\s*[:=]\s*(\S+)", re.I)


def _false_refute_corpus_count():
    """Число labeled кейсов в `false_refute_eval.cases` манифеста (§6). -1 = манифест недоступен/битый
    (fail-open → reminder). Парсим без yaml-зависимости (хук — чистый stdlib): считаем `- name:` под
    ВЛОЖЕННЫМ `cases:` блока `false_refute_eval:`, до следующего top-level (column-0) ключа
    (top-level `cases:` протокольных кейсов и `symmetry_reference:` НЕ считаем)."""
    try:
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        mpath = os.path.join(root, "sessions",
                             "_methodology", "regression_manifest.yaml")
        with open(mpath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return -1
    in_block = False
    count = 0
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if ln[:1] not in (" ", "\t"):          # top-level ключ (column-0) закрывает/открывает блок
            in_block = s.startswith("false_refute_eval:")
            continue
        if in_block and re.match(r"^\s+-\s+name\s*:", ln):
            count += 1
    return count


def _count_practicality_triggers(txt):
    """Реальные practicality/confirm-триггеры (СТРУКТУРНЫЕ теги, НЕ лексика): `[DE-MINIMIS]`/
    `[PRACTICALITY]` + `[CAPITAL-DEP]` + поле `practicality:`. Скаффолд/`{}`-плейсхолдеры не в счёт
    (та же дисциплина, что _real_kill_count → анти-template-FP)."""
    n = 0
    for l in _strip_scaffold(txt).splitlines():
        if "{" in l:
            continue
        n += len(_DEMINIMIS_TAG_RE.findall(l))
        n += len(_CAPITAL_DEP_TAG_RE.findall(l))
        if _PRACTICALITY_FIELD_RE.search(l):
            n += 1
    return n


def _count_profile_cleared(txt):
    """Реальные companion-поля `profile-cleared: <ref>` (ref непустой; UNRESOLVED-needs-approval ок)."""
    n = 0
    for l in _strip_scaffold(txt).splitlines():
        if "{" in l:
            continue
        if _PROFILE_CLEARED_RE.search(l):
            n += 1
    return n


def active_practicality_kill_unprofiled(current_sid):
    """AOE §2.1/§4 profile-cleared гейт. Возвращает (mode, detail) либо None.
      mode='hard'     — держать выход (corpus >=2 labeled кейсов);
      mode='reminder' — не держать, только напомнить (corpus <2 / битый манифест — safe-fallback).
    Триггер = >=1 practicality/capital-триггер, у которого НЕТ companion `profile-cleared: <ref>`
    (число cleared < число триггеров). Симметрия §2.1 (refute [DE-MINIMIS]/practicality И confirm
    [CAPITAL-DEP]) — единый companion-реквайр. Fail-open: любая поломка → None."""
    try:
        t = _read_ledger(current_sid)
        if not t:
            return None
        triggers = _count_practicality_triggers(t)
        if triggers < 1:
            return None
        if _count_profile_cleared(t) >= triggers:
            return None          # каждый триггер несёт companion profile-cleared → чисто
        detail = ("practicality/de-minimis/capital-dep триггеров: %d, а структурных полей "
                  "`profile-cleared: <ref>`: %d" % (triggers, _count_profile_cleared(t)))
        mode = "hard" if _false_refute_corpus_count() >= FALSE_REFUTE_CORPUS_MIN else "reminder"
        return (mode, detail)
    except Exception:
        return None


# EARLY-EXHAUSTION (Sky 2026-07-07) — схема-независимый structural tell: заявление о ПОЛНОМ охвате
# («exhaustive pass done / deep-covered / весь скоуп закрыт / no High-Crit») на Iteration #1-2 = физически
# невозможно (the operator: «как он все 4 веб-ассета вглубь за 20 мин?»). НЕ зависит от kill-тегов/Verifier-схемы —
# читает КАНОНИЧЕСКИЙ `Iteration #` из Loop State + exhaustion-claim в той же секции. Anti-FP: exhaustion-
# лексикон СТРОГИЙ (вердикт-фразы, не template-boilerplate); легит ранний статус (scout вернулся / гоню H-NN)
# его не несёт.
_LOOPSTATE_ITER_RE = re.compile(r"iteration\s*#?\s*[:*]*\s*(\d+)", re.I)
_EARLY_EXHAUST_RE = re.compile(
    r"exhaustive|deep[\s-]?covered|scope\W{0,6}covered|no\s+high/?crit|0\s+in-scope\s+(?:high|crit)|"
    r"весь\s+скоуп\s+закрыт|исчерпан\w*\s+(?:surface|веб|scope|скоуп)|deep-covered",
    re.I,
)


def ledger_early_exhaustion(current_sid, max_iter=2):
    """True если Loop State на Iteration ≤max_iter НЕСЁТ exhaustion-claim (полный охват). Ловит
    ложную исчерпанность за минуты, схема-независимо (не считает kill-теги). Anti-FP: строгий лексикон
    + скоуп на Loop State секцию (template-boilerplate не матчит)."""
    t = _read_ledger(current_sid)
    if not t:
        return False
    ms = re.search(r"##\s*Loop State(.*?)(?:\n##\s|\Z)", t, re.I | re.S)
    region = ms.group(1) if ms else t
    mi = _LOOPSTATE_ITER_RE.search(region)
    if not mi or int(mi.group(1)) > max_iter:
        return False
    return bool(_EARLY_EXHAUST_RE.search(region))


# ─── DEPTH-SPIN guard (Sky 2026-07-07 — durable core) ──────────────────────────────────────────
# Корень авто-петли: Stop-хук держит turn (не даёт выйти), но НЕ умеет заставить копать ВГЛУБЬ.
# Инстанс удовлетворяет «continue» рационализацией («ещё раз убедился — тут чисто»), бампая mtime
# ledger'а → circuit_broken (mtime-based) не трогает, петля «жива», но глубина НЕ растёт = холостой
# ход. Detector: за K дефолт-блоков ledger МЕНЯЛСЯ (mtime рос), но depth-метрики (max depth-lead слой,
# кол-во T4-записей) НЕ выросли → инстанс ЭЛАБОРИРУЕТ, не углубляется → escalate reason на жёсткий
# «спавни cold-агент, гони ОДНУ нить до 5/5». Это сдвиг с детекта фразы на ПРИНУЖДЕНИЕ к глубине,
# схема-независимо (читает канонические Depth-Lead + Verifier Log).
def _max_depth(txt):
    """Максимум достигнутых слоёв по всем строкам Depth-Lead (через фикснутый _depth_layers).
    ⚠ 2026-07-28 (scout-веер по своим хукам, находка #4): пропускаем строки с `{`-плейсхолдером —
    незаполненный field-пример `{… H-03 — 3/5 …}` иначе давал ФАНТОМНЫЙ слой 3 (poison baseline
    depth_spin + ложный claim для T12). Единая логика с guarded-циклами wide_but_shallow/depthmap."""
    d = 0
    for line in _DEPTH_LEAD_LINE_RE.findall(txt):
        if "{" in line:
            continue
        d = max(d, _depth_layers(line))
    return d


def _t4_count(txt):
    """Число РЕАЛЬНЫХ записей в Verifier Log (буллет без `{`-placeholder, с H-<цифра>)."""
    m = re.search(r"##\s*Verifier Log(.*)$", txt, re.I | re.S)
    if not m:
        return 0
    n = 0
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith("-") and "{" not in s and re.search(r"H-\d", s):
            n += 1
    return n


DEPTH_SPIN_K = 4   # дефолт-блоков подряд с движением ledger но БЕЗ роста глубины → spin


def depth_spin(current_sid, K=DEPTH_SPIN_K):
    """True если за K дефолт-блоков ledger писался (mtime рос), но НИ max-depth, НИ T4-count не выросли
    = рационализация вместо копания. Состояние в sidecar `.depth_guard` (отдельно от `.loop_guard`).
    Прогресс глубины (новый слой ИЛИ новый T4) СБРАСЫВАЕТ streak. Fail-open: поломка → False."""
    ledger, _ = freshest_active_ledger(current_sid)
    if not ledger:
        return False
    try:
        txt = open(ledger, "r", encoding="utf-8").read()
        md, t4 = _max_depth(txt), _t4_count(txt)
        # K1 (конфликт T12 × depth_spin, вскрыт при финальной сверке плана): третий исход промаха
        # предсказания — «я НЕ ПОНЯЛ систему → копаю ЭТОТ ЖЕ слой, счётчик глубины НЕ растёт» — это
        # КОРРЕКТНОЕ поведение T12, а для depth_spin оно неотличимо от элаборации. Без этой поправки
        # два наших enforcement'а тянули бы в разные стороны. Поэтому прогрессом считается ТАКЖЕ
        # новая пара predicted/observed: она нефальсифицируема так же, как новый слой или T4-запись.
        po = min(txt.lower().count("predicted:"), txt.lower().count("observed:"))
        mt = os.path.getmtime(ledger)
        gp = os.path.join(os.path.dirname(ledger), ".depth_guard")
        streak = 0
        if os.path.exists(gp):
            try:
                p = open(gp, "r", encoding="utf-8").read().split()
                p_mt, p_md, p_t4 = float(p[0]), int(p[1]), int(p[2])
                # формат sidecar: старый «mt md t4 streak» (4 поля) / новый «mt md t4 po streak» (5).
                if len(p) >= 5:
                    p_po, p_streak = int(p[3]), int(p[4])
                else:
                    p_po, p_streak = 0, int(p[3])
                if md > p_md or t4 > p_t4 or po > p_po:
                    streak = 0                       # глубина / T4 / новая пара pred-obs → сброс
                elif abs(mt - p_mt) > 1e-6:
                    streak = p_streak + 1             # ledger писался, движения нет → +1
                else:
                    streak = p_streak                # ledger не тронут (думал/читал) → держим
            except Exception:
                streak = 0
        with open(gp, "w", encoding="utf-8") as f:
            f.write("%r %d %d %d %d" % (mt, md, t4, po, streak))
        return streak >= K
    except Exception:
        return False


DEPTH_SPIN_REASON = (
    "DEPTH-SPIN GATE (Sky 2026-07-07 — durable). Ты «продолжаешь» уже {K}+ ходов, ledger растёт, но "
    "ГЛУБИНА НЕ движется: max depth-lead стоит, ноль новых T4-записей. Это ЭЛАБОРАЦИЯ (переписываешь "
    "«ещё раз убедился — чисто»), НЕ копание. Петля держит turn не чтобы ты рационализировал, а чтобы ты "
    "УГЛУБЛЯЛСЯ. СТОП писать анализ-выводы. СЕЙЧАС ровно одно: выбери СИЛЬНЕЙШУЮ нить (max severity×"
    "confidence), обнови `Depth-Lead:` и СПАВНИ Task cold-субагента (subagent_type general-purpose, sonnet, "
    "read-only) с ОДНОЙ задачей — протрассировать эту нить на СЛЕДУЮЩИЙ слой (call→state→external→hook→"
    "accounting) ИЛИ adversarial-атаковать твой слабейший kill (почему он НА САМОМ ДЕЛЕ достижим). Верни "
    "управление ТОЛЬКО когда в ledger лёг НОВЫЙ depth-слой (5/5) ИЛИ НОВАЯ запись в Verifier Log. Баг живёт "
    "в СТЫКЕ слоёв ≥5 (депт-потолок аудитора 4-5) — там, куда ты ещё не спустился."
).replace("{K}", str(DEPTH_SPIN_K))


T4_INTEGRITY_REASON = (
    "T4-INTEGRITY GATE (KAST 2026-07-07). Твои kill'ы ССЫЛАЮТСЯ на T4/cold-verify, но `## Verifier Log` "
    "ПУСТ (только template-placeholder). Заявленный, но НЕ залогированный T4 = фейковый T4: ты списал "
    "гипотезу как 'проверено холодным верификатором', не запустив его. Каждый kill по T4 ОБЯЗАН иметь "
    "запись в Verifier Log (`- <дата> — H-NN — verdict: kill/confirm/downgrade — сигнал`). СЕЙЧАС: для "
    "каждого kill'а, где написано T4/cold-verify — ЛИБО реально прогони cold-субагента (maker≠checker, "
    "differential-confirm) и залогируй verdict, ЛИБО убери ложную ссылку на T4 и оставь честный "
    "`file:line` falsifier. Без реального Verifier Log kill по T4 не считается подтверждённым."
)

EARLY_EXHAUSTION_REASON = (
    "EARLY-EXHAUSTION GATE (Sky 2026-07-07). Loop State показывает Iteration #1-2 И заявление о ПОЛНОМ "
    "охвате («exhaustive pass done / deep-covered / весь скоуп закрыт / High-Crit нет»). За 1-2 итерации "
    "(минуты/часы) ГЛУБИНОЙ охватить surface физически нельзя — это BREADTH-sweep (file-level классификация), "
    "выданный за DEPTH-exhaustion (the operator: «как все 4 веб-ассета вглубь за 20 мин?»). Exhaustion требует "
    "ГЛУБИНЫ, не ширины: depth-ceiling ≥5 слоёв на СИЛЬНЕЙШЕЙ нити + T6 composite на латентных + логированный "
    "T4. СЕЙЧАС: выбери сильнейшую нить (max severity×confidence), обнови `Depth-Lead:` и гони её вниз слой "
    "за слоем (call→state→external→hook→accounting); каждую убитую гипотезу — с `file:line` falsifier'ом ИЛИ "
    "[SCOPED-OUT]/[DE-MINIMIS] + adversarial cold-переаудит в Verifier Log. Убери claim «исчерпано/covered» из "
    "Loop State, пока нет ≥1 нити на 5/5 И ≥1 залогированного T4. Выход — только T4 High/Critical или the operator «уходим»."
)

KILL_AUDIT_REASON = (
    "FALSE-EXHAUSTION GATE (KAST 2026-07-07). Ledger в форме исчерпанности: ≥6 kill'ов "
    "(KILLED/SCOPED-OUT/DE-MINIMIS) И НОЛЬ записей в Verifier Log. Ты убил гору гипотез без единой "
    "adversarial-проверки — это НЕ 'багов нет', это НЕДО-проверка. Kill по основаниям 'out-of-scope / "
    "trusted-role / de-minimis / known-issue-duplicate' = СУЖДЕНИЕ о scope/severity, а НЕ falsifier "
    "(guard, делающий баг невозможным) — именно там прячутся баги (KAST H-01 'out-of-scope' противоречил "
    "собственному ledger'у: yield-bot .all() кранкует USDKY; H-02 'known-issue' — novel permissionless-"
    "угол сам-признан НЕ отделённым). СЕЙЧАС: (1) выбери 3 самых консеквентных/слабых kill'а (приоритет "
    "SCOPED-OUT/DE-MINIMIS/known-issue-dup); (2) СПАВНИ cold-T9-субагента (general-purpose, sonnet, "
    "read-only), задача которого — АТАКОВАТЬ основание kill'а (не код — сам KILL: «почему этот "
    "out-of-scope НА САМОМ ДЕЛЕ достижим», «почему этот de-minimis амплифицируем через цикл/накопление / "
    "дешёвый капитал профиля» — нетий de-minimis против attacker_capability_baseline.md (flash-liquidity / "
    "MEV-bundle / multi-block / Sybil делают его достижимым/амплифицируемым? AOE §2.1 profile-cleared); "
    "(3) залогируй каждый verdict в Verifier Log. Если surface СУЗИЛСЯ (подсистема объявлена out-of-scope/"
    "не-задеплоена) — это сигнал RE-СКАУТИТЬ суженное ГЛУБЖЕ (меньше кода → можно гнать нить вниз ≥5 "
    "слоёв), НЕ выходить. НЕ выдавай the operator вердикт 'исчерпано', пока ≥1 реальный T4 не залогирован И "
    "слабейшие kill'ы не пережили adversarial-аудит. Выход из петли — только T4-подтверждённый "
    "High/Critical или слово the operator «уходим»."
)

PROFILE_CLEARED_REASON = (
    "PROFILE-CLEARED GATE (AOE §2.1/§4 — attacker-capability realism, симметричный). %s. "
    "Practicality-kill (`[DE-MINIMIS]`/`[PRACTICALITY]`/поле `practicality:`) ИЛИ capital-dependent "
    "confirm (`[CAPITAL-DEP]` — severity держится на «профитно при экзотическом капитале») ОБЯЗАН нести "
    "структурное поле `profile-cleared: <ref>` — НЕ прозой «дорого/экзотично», а ссылкой на "
    "`sessions/_methodology/attacker_capability_baseline.md` (или per-target `attacker_profile.md`), "
    "которая НЕТИТ суждение против РЕАЛЬНЫХ ресурсов атакующего. Это чинит рецидивный промах "
    "«преждевременный practicality-рефьют» (Superform/ShapeShift-реверсы: surface объявлен исчерпанным, "
    "а баг сидел в непрочитанном/недооценённом слое). СЕЙЧАС: для КАЖДОГО practicality/de-minimis kill'а и "
    "capital-обоснованного confirm'а добавь строку `profile-cleared: <ref>` — **(refute)** докажи, что "
    "flash-liquidity / MEV-bundle / multi-block / Sybil НЕ делает атаку дешёвой/амплифицируемой И что "
    "manufacturable-precondition (разбаланс пула / nonce / пустой резерв) НЕ создаётся дёшево через профиль "
    "(flash-swap двигает резерв в тот же tx = НЕ рефьют); **(confirm)** нетий заявленную severity против "
    "program payout-clauses (flashloan-exclusion / capital-cap — эталон sherlock-euler: реальный $100M "
    "срезан ПРАВИЛАМИ программы до Low). Симметрия обязательна — и refute, и confirm нетятся против профиля. "
    "Если реализм достижим ТОЛЬКО active-пробой живой системы → ставь `profile-cleared: "
    "UNRESOLVED-needs-approval` (white-hat §5.4: гейт НЕ форсит active-действие) и спроси the operator per-vector. "
    "Профиль строится из ПУБЛИЧНЫХ/СТАТИЧЕСКИХ данных (on-chain read через burner / DefiLlama / доки), НЕ "
    "трогая живые системы. Шаблон профиля: `sessions/_methodology/attacker_profile_template.md`."
)

PROFILE_CLEARED_REMINDER = (
    "⚠ PROFILE-CLEARED REMINDER (AOE §2.1, corpus-first reminder-режим). %s. Практика/de-minimis kill "
    "без структурного `profile-cleared: <ref>` рискует быть ПРЕЖДЕВРЕМЕННЫМ practicality-рефьютом "
    "(Superform/ShapeShift-класс). hard-блок ещё НЕ армирован (<2 labeled false-refute кейсов в "
    "regression_manifest.yaml / манифест недоступен), поэтому выход НЕ держу — но добавь "
    "`profile-cleared: <ref>`, нетящий суждение против attacker_capability_baseline.md (симметрично на "
    "confirm-стороне — против payout-clauses). Профиль — из публичных/статических данных, active-only "
    "реализм → `UNRESOLVED-needs-approval`."
)


def touch_current_marker(current_sid):
    """Keep-alive: бампнуть mtime .hunt_active текущего ханта, чтобы длинная автопетля
    (часы/дни без нового промпта the operator) не протухла по 24ч-фильтру _owned_markers."""
    try:
        ledger, _ = freshest_active_ledger(current_sid)
        if ledger:
            m = os.path.join(os.path.dirname(ledger), ".hunt_active")
            if os.path.exists(m):
                os.utime(m, None)
    except Exception:
        pass


def circuit_broken(current_sid):
    """Анти-спин safety (ТОЛЬКО default-петля; give-up НЕ проходит сюда — держится намертво).
    True = петлю пора отпустить (мёртвый спин), False = держать блок. Спин = ledger не двигается
    FROZEN_RELEASE блоков подряд с тем же mtime (genuine повторение). Прогресс (mtime сдвинулся) →
    сброс счётчика. ⚠ 30-мин таймер УБРАН 2026-07-07 (the operator: страховка от токенов не нужна; таймер
    выпускал петлю в legit read-heavy фазе и на give-up). Fail-open: поломка → True (не зациклить)."""
    try:
        ledger, _ = freshest_active_ledger(current_sid)
        if not ledger:
            return True
        gp = os.path.join(os.path.dirname(ledger), ".loop_guard")
        cur_m = os.path.getmtime(ledger)
        prev_m, streak = None, 0
        if os.path.exists(gp):
            try:
                parts = open(gp, "r", encoding="utf-8").read().split()
                prev_m, streak = float(parts[0]), int(parts[1])
            except Exception:
                prev_m, streak = None, 0
        if prev_m is not None and abs(cur_m - prev_m) < 1e-6:
            streak += 1          # ledger не двинулся с прошлого блока
        else:
            streak = 0           # прогресс → сброс окна
        if streak >= FROZEN_RELEASE:
            with open(gp, "w", encoding="utf-8") as f:
                f.write("%r 0" % cur_m)   # сброс после trip (даёт новое окно, если хант продолжат)
            return True
        with open(gp, "w", encoding="utf-8") as f:
            f.write("%r %d" % (cur_m, streak))
        return False
    except Exception:
        return True


def _generator_backlog(current_sid):
    """FIX de-shadow (ethena-live 2026-08-12, judge-2 3/10 + the operator): агрегат НЕпрогнанных генераторов МЕСТА
    (T11/T14/EXPOSURE/PRIOR-PATTERNS/Un-Dup Sweep). КОРЕНЬ провала: каждый — самостоятельный EXIT-holder-гейт,
    НО в first-wins каскаде `_block`+`sys.exit` затеняется ПЕРВЫМ фаирящим (обычно generic give-up) → агент
    видит «копай глубже» (общее), а НЕ «прогони T11/T14/exposure/pattern» (конкретное). Ethena: все эти гейты
    ФАИРИЛИ, но я ни одного сообщения не увидел → 80% тулкита не выстрелило. Суффикс приклеивается к ЛЮБОМУ
    block-reason'у → конкретные пропущенные генераторы ВСЕГДА доходят. Fail-open (ошибка → пустой суффикс)."""
    try:
        missing = []
        if active_t11_undecided(current_sid):
            missing.append("T11-VERDICT (фаззер-как-генератор — прогони t11_applicable.py, реши APPLICABLE/SKIP+причина)")
        if active_attention_gap_skipped(current_sid):
            missing.append("T14 attention-gap (commit_archaeology.py / audit_coverage_invert.py — указывают КУДА копать)")
        elif active_attention_gap_stale(current_sid):
            missing.append("T14 attention-gap RE-ARM (residual #2 — карта внимания отстала от T9-осей, до-картируй новые оси)")
        if active_hybrid_fanout_stale(current_sid):
            missing.append("HYBRID Scout Fan-Out RE-ARM (FEAT-E — веер отстал от T9-осей; divergence_fanout РОЖДАЕТ D-NN, гони на текущей оси)")
        if active_pattern_replay_skipped(current_sid):
            missing.append("PRIOR-PATTERNS (pattern_replay.py — совпавшие прошлые un-dup fingerprint'ы = seed высшего ранга)")
        if active_exposure_scan_skipped(current_sid):
            missing.append("EXPOSURE-SCAN (secret_exposure_scanner.py — захардкоженный ключ = самый дешёвый Crit)")
        if active_undup_sweep_incomplete(current_sid):
            missing.append("Un-Dup Sweep генераторы (composition/commodity-subtraction/assumption-mining/negative-space/…)")
        if not missing:
            return ""
        return ("\n\n⚙ НЕПРОГНАННЫЕ ГЕНЕРАТОРЫ МЕСТА (de-shadow, ethena-урок): эти гейты ФАИРЯТ, но затеняются "
                "первым в каскаде — ты видишь общее «копай глубже», а система КОНКРЕТНО просит прогнать ДО "
                "закрытия оси (не только на финальном выходе): " + " · ".join(missing) + ". Каждый = отдельный "
                "источник МЕСТА/находки; ~80% тулкита не выстрелило в ethena-прогоне именно из-за этого затенения.")
    except Exception:
        return ""


def _block(reason, current_sid, is_giveup=False):
    """Единая точка блока: circuit breaker → keep-alive маркер → block.
    is_giveup=True (артикулированный abort/fork/decision-Q/breadth) → circuit breaker ОБХОДИТСЯ,
    держим намертво: give-up = НЕ мёртвый спин, это ровно то, что гейтим, отпускать его нельзя
    (the operator 2026-07-07). Только default-петля (is_giveup=False) может отпуститься по 8-streak.
    FIX de-shadow: к КАЖДОМУ reason'у приклеиваем backlog непрогнанных генераторов (T11/T14/exposure/
    pattern/undup) — иначе они молча затеняются первым фаирящим гейтом (ethena: 80% тулкита не выстрелило)."""
    if not is_giveup and circuit_broken(current_sid):
        sys.exit(0)   # genuine dead-spin default-петли → safety-release (give-up сюда не заходит)
    touch_current_marker(current_sid)
    print(json.dumps({"decision": "block", "reason": reason + _generator_backlog(current_sid)}))
    sys.exit(0)


FORK_DIFF_REASON = (
    "FORK-DIFF GATE (Compound-fork confession 2026-08-09). %s. "
    "На форке «canonical / совпадает с родителем» — это КЛАССИФИКАЦИЯ, а не доказательство отсутствия "
    "девиации: чем каноничнее механизм, тем охотнее его считают данностью, там и живут выжившие криты "
    "(feedback_canonical_mechanism_substituted). Тонкие баги форка (rounding / interest-accrual edge / "
    "liquidation dust / exchange-rate под реальным state) видны ТОЛЬКО при исполнении на форке — "
    "статикой их не видно. **Инструмент ПО ЭКОСИСТЕМЕ (H-exec/R8, family_fork_diff — EVM-only):** "
    "EVM → `differential_observation.family_fork_diff(parent, fork, target)` + `identify_parent` (A8) / "
    "invariant-тест на mainnet-форке (Foundry в Docker bbt); **Solana → clone-программу на "
    "`solana-test-validator` + Trident invariant-fuzz / differential против родителя (agave/firedancer/"
    "jito-solana), `family_fork_diff` тут НЕ применим**; Cosmos/Move → invariant-тест на форке чейна / "
    "simnet. Это часы, не минуты — но это и есть глубина. Сними держание одним из двух: (1) прогони diff → "
    "`Fork-diff: DONE — <артефакт: trident_*.log / fork_diff.* / invariant-test>`; (2) если таргет НЕ форк "
    "ИЛИ executable-инструмент для этой экосистемы отсутствует → `PARENT-FORK: N/A — <причина>` (не "
    "блокируем выход тем, чего нет — но статический «matches parent» без прогона НЕ засчитывается)."
)

FORK_UNDECLARED_REMINDER = (
    "FORK-UNDECLARED (benqi audit 2026-08-09). Твой ledger сам декларирует форк родителя «%s» "
    "(canonical/байт-в-байт/fork), но поле `PARENT-FORK` в Loop State пусто → флагманский FORK-DIFF "
    "гейт НЕ армится (арм только от поля = обходится ненаписанием поля, «месяцами-молчащий гейт»). "
    "Заполни `PARENT-FORK: %s v<N> — <fingerprint>` (тогда fork-diff потребует executable-diff против "
    "родителя) ЛИБО `PARENT-FORK: N/A — <причина>`, если это НЕ форк. Soft-nudge: не держит выход."
)

T12_REASON = (
    "T12-GATE (Predictive Boundary Crossing, фаза 2). %s. "
    "Слой засчитывается ТОЛЬКО при ДВУХ условиях: (1) пересечена ГРАНИЦА представления — статика→"
    "рантайм / модуль A→модуль B / спека→реализация / деплой A→деплой B / код→живое on-chain "
    "состояние; (2) `predicted:` записан ДО пересечения и `observed:` проверен ПОСЛЕ, со ссылкой на "
    "артефакт (лог forge/anvil, трейс, вывод RPC). Пять чтений подряд в одном файле = ОДИН слой; "
    "пересечение без предсказания = НОЛЬ слоёв (это перемещение, а не понимание). "
    "`fan-in:` заполняется ГРЕПОМ — все writer'ы состояния этого слоя: провал аудитора чаще не «не "
    "спустился глубже», а «не спросил, кто ещё пишет в состояние»; писатель из ДРУГОЙ подсистемы = "
    "готовая вторая улика для T6, а `fan-in > 1` при `ENFORCED` на твоей ветке = прямое подозрение на "
    "`ENFORCED-PARTIAL`. Промах `predicted ≠ observed` — ГЕНЕРАТОР: (а) система ведёт себя неожиданно "
    "→ новый `D-NN` высшего приоритета; (б) не понял систему → копай ЭТОТ ЖЕ слой (счётчик не растёт, "
    "depth-spin это учитывает); (в) модель была неверна → правка `system_model.md`. Заполни "
    "`DEPTH-TRACE` в Loop State по факту, задним числом «я так и думал» не засчитывается."
)

MODEL_REASON = (
    "MODEL-GATE (divergence-first, T10/T13). Модель системы — ОБЪЕКТИВНЫЙ источник МЕСТА против "
    "дублей (Berachain: 2 Critical → оба DUPLICATE, $0 — промах был не в глубине, а в оригинальности "
    "точки входа). Проблема: %s. "
    "Почини в `system_model.md` и продолжай петлю: (1) корпус БЕЗ кода → `I-NN` формулами, ≤12, "
    "каждый с `check:`/`component:`/`pred:`; (2) потом код → enforcement по 5 статусам; (3) прогони "
    "операторы «на всех ли путях?», «а канонический ли механизм?» (сверь `fingerprint:` в "
    "`methodology/invariant_library.md`), «`pred:` против факта». Чеклист: "
    "`_methodology/independent_model_first.md`. Если T10 к этому таргету неприменим (мелкий контракт "
    "<300 LOC / фронт / web2) — поставь в Loop State строку `MODEL: N/A — <причина>` (без backtick'ов "
    "и фигурных скобок), гейт снимется. Ноль `D-NN` — это «детектор не сработал», НЕ «таргет чистый»: "
    "эскалируй метод по таблице §10 (какой генератор молчит → своя эскалация: ноль `I-NN` → суррогатный "
    "корпус · все `ENFORCED` → оператор на всех путях · attention-gaps пусты → T10-B family diff · всё "
    "молчит → T9 cold-restart на новой оси) И ЗАФИКСИРУЙ молчащий генератор в "
    "`sessions/_methodology/blind_spots.md` (молчание не завершает хант, но и не проглатывается — это "
    "вход в карту слепых зон, метрика покрытия классов)."
)

MODEL_ORDER_REASON = (
    "MODEL-ORDER (идея F). %s. `pred:` — ожидаемый статус, он обязан быть записан ДО чтения кода: "
    "именно расхождение `pred: ENFORCED` → факт `ABSENT/SUBSTITUTED` указывает место, которое ВСЕ "
    "считают закрытым (un-dup по построению — так вскрылся весь класс `SUBSTITUTED` в фазе 0). "
    "Проставленный задним числом `pred:` этого сигнала не даёт вовсе. Заполни `pred:` для тех `I-NN`, "
    "код которых ещё НЕ читал; для уже прочитанных — честно пометь `pred: —` и не считай их сигналом."
)

DIVERGENCE_REASON = (
    "DIVERGENCE-UNRESOLVED. %s. Дивергенция — это ЛИД, а не запись в дневнике: доведи до DRIVE "
    "(`→ H-NN`) либо убей hard-falsifier'ом (`KILLED file:line`). "
    "⚠ Если брошены `hot`-дивергенции: `hot` ≠ «закрыто» — толпа смотрела, но НЕ доводила (EtherFi H2 "
    "и 0x Settler жили в обсуждённых местах, Orchard прожил 4 года под tier-1 аудитами). Порядок — "
    "`cold` первыми, `hot` ОБЯЗАТЕЛЬНО, но позже. **«Там людно» falsifier'ом не считается и киллом "
    "не является**; просроченным `hot` считается только то, где dedup-чек нашёл КОНКРЕТНЫЙ отчёт с "
    "ТЕМ ЖЕ механизмом."
)

LIBRARY_REASON = (
    "LIBRARY-NOT-BANKED (идея A+E). Хант выходит с подтверждённой находкой, но модель (%s) не "
    "разобрана в капитал: примитивные `I-NN` не вынесены в `methodology/invariant_library.md`. "
    "Сегодня «инвариант держится» = ноль ценности; в библиотеке это АКТИВ — следующий хант на том же "
    "примитиве инстанциирует модель за минуты вместо 30-45, а T10-B (диф форка против эталона) "
    "становится машиной. Вынеси ТОЛЬКО примитивные инварианты (не бизнес-логику таргета), каждый с "
    "`ref:` (`file:line` эталона) и `fingerprint:` канонического механизма — отпечаток и есть то, чем "
    "ловится подмена (`SUBSTITUTED`). Затем замени сентинел на `LIBRARY: updated` (или "
    "`LIBRARY: N/A — примитивов не было`) — и я выпущу."
)

LOOP_CONTINUE_REASON = (
    "LOOP-DROP-GUARD (autonomous Hunt-Loop, 2026-07-02). Хант АКТИВЕН, High/Critical ещё НЕ подтверждён, "
    "the operator не говорил 'уходим' → петля НЕ завершается, ты продолжаешь САМ (твой codex-режим: нет "
    "опции вернуться к the operator с 'что дальше'). НЕ спрашивай его. Выбери СЛЕДУЮЩИЙ single-pick по "
    "приоритету и работай: (1) открытая гипотеза с макс. severity×confidence → DRIVE до PoC/Kill; "
    "иначе (2) непрочитанный построчно score-5 файл → H-NN из кода; иначе (3) score-4; иначе "
    "(4) refuted → building-block → T6-композит (пара классов); иначе (5) T9 cold-restart: СПАВНИ "
    "Task cold-субагента (general-purpose, sonnet, read-only) на НОВОЙ оси (ось задаёшь ТЫ) → лиды в "
    "ledger. Веди `hypotheses.md` LIVE (каждая гипотеза со статусом; Loop State в конце итерации); в "
    "чат — максимум 1-3 строки статуса. ВЫХОД из петли РОВНО ОДИН: после РЕАЛЬНОГО T4-подтверждения "
    "HIGH/CRITICAL бага впиши в ledger строку `HUNT-EXIT: T4-CONFIRMED <High|Critical>` — тогда я тебя "
    "выпущу. Medium/Low НЕ выход (the operator 2026-07-06): нашёл Medium → сабмить + жми ceiling до High + "
    "копай дальше, петля НЕ завершается. Иначе уйти — только когда the operator сам напишет 'уходим'. "
    "Баги есть везде: 'чисто' = недокоп."
)


def _exit_diff(current_sid):
    """B6 (audit 2026-08-09): при RELEASE («уходим») собрать незакрытые soft-completeness-гейты и
    вывести the operator на stderr — НЕ блок (уход = прерогатива the operator), но недокоп фиксируется, не уходит
    МОЛЧА. Корень (1inch audit): Un-Dup Sweep / PRIOR-PATTERNS / EXPOSURE / D-NN — все `TODO`/пусто на
    выходе, автономный выход их держит, а человеческий «уходим» их не проверял. fail-open (любая
    поломка — тихо, чтобы не мешать выходу). Переиспользует существующие детекторы (single source)."""
    checks = (
        ("Un-Dup Sweep не завершён", active_undup_sweep_incomplete),
        ("PRIOR-PATTERNS не прогнан (компаундинг)", active_pattern_replay_skipped),
        ("EXPOSURE-SCAN не прогнан", active_exposure_scan_skipped),
        ("0 D-NN не эскалирован (Mandate 0.9 → blind_spots)", active_zero_divergence_unescalated),
        ("executable-floor: 0 executable-прогонов за хант", active_executable_floor_unrun),
    )
    gaps = []
    for label, fn in checks:
        try:
            if fn(current_sid):
                gaps.append(label)
        except Exception:
            pass
    if gaps:
        try:
            sys.stderr.write(
                "\n⚠ EXIT-ДИФФ (audit-B6) — выходим по «уходим», но НЕЗАКРЫТО:\n  - "
                + "\n  - ".join(gaps)
                + "\n(это НЕ блокирует выход — уход твоя прерогатива — но фиксируется, чтобы недокоп "
                "не маскировался молча под «ушли». Стоит закрыть перед следующим заходом.)\n")
        except Exception:
            pass


# ═══════════════════ WORKLIST DRIVER Этап 2 — next_atom active dictation ═══════════════════
# (за WORKLIST_DRIVER_ENABLED, план §1 Слой-2 / §3 Этап 2). Заменяет СТАТИЧНЫЙ LOOP_CONTINUE_REASON в
# DEFAULT-ветке АКТИВНОЙ диктовкой головы машинного реестра `## Atom Registry`. ЯДРО: структурный каскад
# (42 детектора) НЕ тронут → shadowing тривиально сохранён (golden reference shadowing_regression.py);
# ranked-соревнование живёт ТОЛЬКО среди worklist-строк (гипотезы/оси), где раньше стоял статичный
# SELECT-текст и рождался livepeer-дрейф. next_atom достигается СТРОГО после всех is_giveup-гейтов
# каскада (§1 subsume). НЕ пишет в ledger (не инфлейтит mtime → circuit_broken жив). fail-open в
# LOOP_CONTINUE (нулевой blast-radius: нет реестра / первый проход / MODEL:N/A / off → старая проза).

def _weak_classes(_cache={}):
    """G-weak (§8): множество классов с исторической accuracy<0.30 при n>=5 из calibration_log.jsonl.
    Только finding-записи (несут `class`[]+`outcome`); regression-строки (recall/fp_rate) игнорятся.
    accuracy = доля outcome, начинающихся с `TRUE`. fail-open (нет файла/парс-фейл → пусто). Кэш на
    процесс (хук short-lived). ⚠ armed-trigger: при текущих ~9 finding-записях ни один класс не наберёт
    n>=5 → пусто (no-op), активируется при накоплении калибровки (YAGNI-farm-fit: deferred-by-data)."""
    if "v" in _cache:
        return _cache["v"]
    weak = set()
    try:
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        path = os.path.join(root, "sessions", "_methodology", "calibration_log.jsonl")
        tot, good = {}, {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                cls = o.get("class")
                oc = o.get("outcome")
                if not isinstance(cls, list) or not oc:
                    continue
                ocu = str(oc).upper()
                # C-D1 accuracy-семантика: PENDING = НЕ решено → исключаем из знаменателя (не hit, не miss).
                # INCORPORATED (валидная находка, слитая дедупом в другую) = TRUE, а не промах.
                if "PENDING" in ocu:
                    continue
                decided_true = ocu.startswith("TRUE") or "INCORPORATED" in ocu
                for c in cls:
                    c = str(c).strip().lower()
                    if not c:
                        continue
                    tot[c] = tot.get(c, 0) + 1
                    if decided_true:
                        good[c] = good.get(c, 0) + 1
        for c, n in tot.items():
            if n >= 5 and (good.get(c, 0) / float(n)) < 0.30:
                weak.add(c)
    except Exception:
        pass
    _cache["v"] = weak
    return weak


def _class_tokens(text):
    """Множество alnum-токенов строки (для token-subset матча слаб-класса, судья-C D2)."""
    return set(t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t)


DRIVE_HEAD_PREFIX = (
    "⚙ WORKLIST-DRIVER (Этап 2): машинный реестр уже посчитал твой SELECT — **ГОНИ ГОЛОВУ %s**. Она "
    "`ACTIVE`: НЕ перевыбирай каждый ход, продолжай ЕЁ вниз ≥5 слоёв (call→state→external→hook→"
    "accounting) до PoC/Kill; обнови её `status`/`closes` в `## Atom Registry`, когда закроешь. Не "
    "импровизируй мимо очереди (это и есть livepeer-болезнь). Ниже — полный контракт петли и "
    "fallback-SELECT на случай реального тупика по этой голове:"
)
HANDOFF_HEAD_PREFIX = (
    "⚙ WORKLIST-DRIVER (Этап 2): голова реестра сменилась (прошлая ось закрыта / нет `ACTIVE`) — "
    "**следующая ГОЛОВА = %s**. Это МОМЕНТ смены оси, где рождается livepeer-дрейф: НЕ уходи в свой "
    "угол — пометь ЭТУ строку `status: ACTIVE`, впиши её id в `Current pick`, гони её вниз ≥5 слоёв. "
    "Считаешь другую нить сильнее — СНАЧАЛА подними ей rank в реестре с обоснованием (не молча мимо "
    "очереди). Контракт петли ниже:"
)
QUEUE_EMPTY_PREFIX = (
    "⚙ WORKLIST-DRIVER (Этап 2): в `## Atom Registry` НЕТ ни одной `OPEN`/`ACTIVE`-строки (всё "
    "CLOSED/PARKED) — ось исчерпана, но это НЕ выход (баги есть везде). РЕГЕНЕРИРУЙ очередь тремя "
    "режимами и заведи новые `OPEN`-атомы с rank: (a) gap-map непрочитанных score-4/5 → H-NN; "
    "(b) T9 cold-restart на НОВОЙ оси (ось задаёшь ТЫ, спавни cold-субагента read-only); (c) refuted "
    "building-blocks → T6-композит (пары классов). Внеси ≥1 новую голову в реестр и гони её. "
    "Контракт петли ниже:"
)
WEAK_CLASS_ADVISORY = (
    "⚠ WORKLIST-DRIVER (G-weak): голова `%s` попадает в класс `%s` с исторической accuracy<30%% "
    "(n≥5, calibration_log). НЕ «пропусти» — удвой скепсис на T4 и не трать глубину на слабый лид без "
    "сильного prediction+falsifier; реши сам — гнать или переоценить rank."
)

# ── Этап 3, Слой-2 примеси: periodic synthesis + identity re-injection ────────────────────────────
# Каденция по `Iteration #` из ledger (durable через compact, БЕЗ записи состояния → mtime не инфлейтим,
# circuit_broken жив). Взаимно простые периоды (5 и 8) → редко совпадают, не спамят одновременно.
SYNTHESIS_EVERY = 5      # cross-thread T6 форсинг (план §1 Слой-3: periodic synthesis-атом)
IDENTITY_EVERY = 8       # Шерлок-фрейм (план §1: против вырождения worklist в чеклист-косплей)

SYNTHESIS_ADVISORY = (
    "🔗 CROSS-THREAD SYNTHESIS (итерация %d, каждая %d-я — план §1 Слой-3). Single-pick гонит нить "
    "ВГЛУБЬ, но Crit-цепочки рождаются на СТЫКЕ далёких улик — а их никто не сводит, пока идёт drive. "
    "СЕЙЧАС (параллельно, НЕ бросая голову): спавни ХОЛОДНЫЙ субагент (`general-purpose`, read-only) и "
    "дай ему РОВНО две МАКСИМАЛЬНО ДАЛЁКИЕ улики из `## Building Blocks`/`## Refuted` (разные файлы/"
    "подсистемы/классы — чем дальше, тем ценнее) + вопрос: «связаны ли они через shared state / общий "
    "fan-in / порядок операций так, что вместе дают то, чего нет по отдельности?». Пара сработала → "
    "новый атом `type:cross-thread` с высоким rank; нет → лог в `## Composite Chains Generated` "
    "(«пара X×Y — нет связи»), это тоже знание. Ты продолжаешь гнать голову, cold-агент считает пару."
)
IDENTITY_ADVISORY = (
    "🕵 РЕЖИМ ШЕРЛОКА (итерация %d, каждая %d-я — не задача, а фрейм). Реестр — инструмент, а не "
    "чеклист: галочки не находят баги, находит ЛЮБОПЫТСТВО к аномалии. Спроси себя прямо сейчас: "
    "**какая МЕЛОЧЬ в коде показалась «странной, но наверное так задумано» — и я прошёл мимо?** "
    "(off-by-one · unchecked return · asymmetry между близнецами-функциями · `assign` без `copy` · "
    "комментарий «should» без enforce · ОТСУТСТВИЕ check/reload/guard = «собака, что не залаяла»). "
    "Именно там живут выжившие аудиты криты — толпа проходит мимо «наверное задумано». Одна такая "
    "мелочь → новый атом в реестр с честным rank. Аудиты НЕ показатель: баги есть везде."
)


def next_atom(current_sid):
    """Возвращает (directive, advisory[]) для DEFAULT-ветки. directive — активная диктовка головы
    реестра (PREFIX + полный LOOP_CONTINUE_REASON, чтобы контракт выхода НИКОГДА не терялся — ось-1),
    ЛИБО чистый LOOP_CONTINUE (fallback). advisory — soft-rider'ы (G-weak). Off-switch согласован с
    pick-гейтом: MANUAL/OFF/HUNT-EXIT/MODEL:N/A → старая проза."""
    if not WORKLIST_DRIVER_ENABLED:
        return LOOP_CONTINUE_REASON, []
    ledger, _root = freshest_active_ledger(current_sid)
    if not ledger:
        return LOOP_CONTINUE_REASON, []
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return LOOP_CONTINUE_REASON, []
    if _MANUAL_RE.search(lt) or _OFF_RE.search(lt):
        return LOOP_CONTINUE_REASON, []
    if _has_valid_exit(lt):
        return LOOP_CONTINUE_REASON, []
    # NB: НЕ глушим на MODEL: N/A (в отличие от registry_unpopulated adoption-гейта): next_atom не ФОРСИТ
    # реестр, а лишь диктует голову ЕСЛИ он есть. Опт-ин в реестр на мелком контракте (N/A) → драйвер
    # честно работает. Консистентно с pick-гейтом (у него тоже нет N/A-off-switch). C1-тишина ниже.
    rows = _atom_rows(lt)
    if rows is None:
        return LOOP_CONTINUE_REASON, []                 # C1: секции нет → legacy/web fallback
    atoms = _valid_atoms(rows)
    if not atoms:
        return LOOP_CONTINUE_REASON, []                 # первый проход — реестр ещё пуст
    oa = [a for a in atoms if a["status"] in ("OPEN", "ACTIVE")]
    if not oa:                                          # все CLOSED/PARKED/BANKED → ось исчерпана
        return QUEUE_EMPTY_PREFIX + "\n\n" + LOOP_CONTINUE_REASON, []
    active = [a for a in oa if a["status"] == "ACTIVE"]
    # subject = атом, который РЕАЛЬНО гонится/будет гнаться. Если есть ACTIVE — это ровно 1 строка
    # (>1 заблокировал бы pick-гейт клауза-1) и она ГАРАНТИРОВАННО ко-максимальна по rank (иначе клауза-3
    # pick-гейта заблокировала бы выше) → гоним ЕЁ (не соседа-tie-break-победителя). 0 ACTIVE → голова.
    # Судья-A Дефект-1: strict-id-равенство с головой давало ложный HANDOFF на РАВНОМ rank (ACTIVE делит
    # max с OPEN-соседом, но проигрывает tie-break) — Stage-2 велел уйти, пока pick-гейт молчал.
    subject = active[0] if active else _registry_head(oa)
    advisory = []
    weak = _weak_classes()
    if weak and subject is not None:
        atoks = _class_tokens((subject.get("title") or "") + " " + (subject.get("type") or ""))
        # token-SUBSET (судья-C D2): весь слаб-класс ⊆ токенов атома. `oracle`⊆`oracle-conf-strip` ✓;
        # `auth`⊄`author-check` (substring `w in hay` давал ложный advisory). Multi-token класс тоже ловится.
        hit = next((w for w in weak if _class_tokens(w) and _class_tokens(w) <= atoks), None)
        if hit:
            advisory.append(WEAK_CLASS_ADVISORY % (subject["id"], hit))
    # Этап 3 примеси: каденция по Iteration # (durable, без записи состояния). Едут КАК RIDER'Ы —
    # НЕ подменяют directive: single-pick/depth-drive не рвём, synthesis считает cold-агент параллельно.
    _it = _loopstate_iter(lt)
    if _it and _it > 0:
        if _it % SYNTHESIS_EVERY == 0:
            advisory.append(SYNTHESIS_ADVISORY % (_it, SYNTHESIS_EVERY))
        if _it % IDENTITY_EVERY == 0:
            advisory.append(IDENTITY_ADVISORY % (_it, IDENTITY_EVERY))
    if active:                                          # 1 ACTIVE ко-максимален → DRIVE, называем ЕГО
        directive = DRIVE_HEAD_PREFIX % _atom_str(active[0])
    else:                                               # 0 ACTIVE, все OPEN → реальная смена оси → HANDOFF
        directive = HANDOFF_HEAD_PREFIX % _head_str(oa)
    return directive + "\n\n" + LOOP_CONTINUE_REASON, advisory


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # NB: stop_hook_active НЕ используется для blanket-bail — иначе автопетля («держи turn до High/Critical»)
    # умирала бы после первого блока. Анти-зацикливание обеспечивает circuit_broken() (мёртвый спин).
    # session_id текущей сессии → скоупим guard, чтобы хант в соседнем окне не фонил тут.
    current_sid = data.get("session_id") or ""

    tpath = data.get("transcript_path")
    # ⛔ МЕТА-ИСКЛЮЧЕНИЕ поверх ЛЮБОГО арминга (veda 2026-08-18): entry-хук армит маркер на УПОМИНАНИЕ
    # slug'а в сообщении the operator — СВОИМ sid текущей сессии. Значит мета-дебаг-сессия (the operator спросил ПРО
    # хант veda → маркер veda создан моим sid) «владеет» чужим hunt-маркером → hunt_is_active=True обходил
    # мета-исключение (оно жило только в _ledger_state_active). Сессия, правящая toolkit-код
    # (scripts/hooks|_methodology), = ДЕБАГ системы, НИКОГДА не держится — даже владея маркером.
    _edited_ledgers, _is_meta = _session_ledger_edits(tpath)
    if _is_meta:
        sys.exit(0)

    # Не на ханте → не блокируем. Арминг: (1) свой свежий маркер (быстрый кэш) ИЛИ (2) LEDGER-STATE —
    # ЭТА сессия активно правит свежий содержательный активный hunt-ledger (self-heal marker-falloff,
    # OZ 2026-08-18). Аддитивно: (2) зовётся ТОЛЬКО при отсутствии (1) → jito с живым маркером не задет.
    if not hunt_is_active(current_sid):
        if not _ledger_state_active(current_sid, tpath):
            sys.exit(0)

    # SUCCESS-выход: в ledger `HUNT-EXIT: T4-CONFIRMED High|Critical` (реальный High/Crit баг подтверждён) →
    # петля выполнила свой ЕДИНСТВЕННЫЙ легальный выход. Отпускаем — но СНАЧАЛА банк знания:
    # библиотека инвариантов пополняется ИМЕННО здесь, иначе гейт «на выходе» никогда не сработает
    # (после exit-токена хук молчит). Разблокируется одной строкой `LIBRARY: updated` в ledger.
    if ledger_success_exit(current_sid):
        # OOS-INTAKE в success-пути (red-team D1, HIGH): быстрый HUNT-EXIT за один turn от свежего
        # ledger'а мог выпустить с НЕвычитанным OOS (сентинел OOS-TODO висит), т.к. intake-гейт живёт в
        # основном каскаде, а success-exit выходит раньше. Форсим вычитку OOS ДАЖЕ на быстром выходе.
        _oo = active_ledger_missing_oos(current_sid)
        if _oo:
            _block(OOS_REASON, current_sid)
        # Submit-time OOS-дисквалификатор (money-critical, 2026-08-11): не выпускаем HUNT-EXIT, пока
        # находка не сверена с Out-of-Scope (OOS-CHECK). Стоит ПЕРЕД library-банком (сначала «а вообще
        # payable ли по scope?», потом банк знания). Off: OOS=N/A / manual / уже есть OOS-CHECK.
        _oc = active_submit_without_oos_check(current_sid)
        if _oc:
            _block(OOS_CHECK_REASON, current_sid)
        # T4-ДЕКОМПОЗИЦИЯ (Этап 3, Слой-3 verifier-канал): submit-момент требует ПОЛНЫЙ T4 в Verifier
        # Log (STEP 0 dedup / cold-checker / verdict / 2.6 fresh-runtime / 2.7 precondition-matrix), а
        # не строку «verdict: confirm». Стоит ПОСЛЕ OOS (сначала «payable ли по scope», потом «доверено
        # ли»), ПЕРЕД library-банком. За флагом WORKLIST_DRIVER_ENABLED.
        _t4d = active_t4_decomposition_incomplete(current_sid)
        if _t4d:
            _block(T4_DECOMPOSITION_REASON % _t4d, current_sid)
        # FEAT-A (jito-live, the operator): финальный payability-gate. HUNT-EXIT High/Crit не выпускает, пока
        # Final Reliability (2 cold-агента T4-v2 + свой T4) не записана и ≥50%. <50% → void + банк
        # [LOW-RELIABILITY], петля продолжается (the operator: «менее 50 не подавать даже High/Crit»).
        _lr = active_lowrel_exit_blocked(current_sid)
        if _lr:
            _block(LOWREL_EXIT_REASON % (_lr[0], ("%d%%" % _lr[1]) if _lr[1] >= 0 else "НЕ записана"), current_sid)
        # T4-v2 3-агента (the operator 2026-08-18): High/Crit-подача требует A3 cold-ИНТЕГРАТОРА (seam validity×
        # payability) сверх 2 специалистов. Стоит ПОСЛЕ lowrel (A3 питает Final Reliability), ПЕРЕД report-template.
        _ti = active_t4_integrator_missing(current_sid)
        if _ti:
            _block(T4_INTEGRATOR_REASON % _ti, current_sid)
        # FEAT-B (jito-live): платформа-детект → правильный шаблон репорта. Immunefi-таргет + HUNT-EXIT
        # без выбранного шаблона → nudge на templates/dapp_reports/immunefi_dapp.md (the operator: «берёт не тот»).
        _rt = active_report_template_unset(current_sid)
        if _rt:
            _block(REPORT_TEMPLATE_REASON % _rt, current_sid)
        # FIX-J (T4-backstop hardening, стресс-тест 2026-08-12): decomposition-гейт форсит ФОРМУ T4 (маркеры),
        # но фабрикацию (`forge test → PASS`/fake tx вписаны, 0 прогонов) не ловит НИКТО. FIX-J проверяет, что
        # цитируемые artifact-ФАЙЛЫ реально существуют co-located (зеркало observed_fabricated). Стоит СРАЗУ
        # после decomposition (сначала «форма T4 полна», потом «artifact-файлы не фиктивны»). Fail-open потолок.
        _t4e = active_t4_evidence_fabricated(current_sid)
        if _t4e:
            _block(T4_EVIDENCE_FABRICATED_REASON % (_t4e[0], _t4e[1]), current_sid)
        # SUBMIT-CHECKLIST АТОМ (§8 G-submit): pre-submit gate прогнан по КОНКРЕТНОЙ находке (auto_invalid
        # / severity_cap / project-tests / permissionless / quality_required), а не «помню, что надо».
        # Стоит ПОСЛЕ T4 (сначала «находка реальна», потом «оформлена по правилам площадки»). C1-silent.
        _sca = active_submit_checklist_atom_missing(current_sid)
        if _sca:
            _block(SUBMIT_CHECKLIST_ATOM_REASON % _sca, current_sid)
        # EXTERNAL-REVIEW (§8 G-peer): только на CRITICAL-подаче — второй независимый взгляд на самую
        # дорогую категорию (классификация/экономика/scope/слабый примитив). Off: High / N/A-отказ / C1.
        _era = active_external_review_atom_missing(current_sid)
        if _era:
            _block(EXTERNAL_REVIEW_REASON % _era, current_sid)
        _lib = active_library_not_banked(current_sid)
        if _lib:
            _block(LIBRARY_REASON % _lib, current_sid)
        # EXIT-KNOWLEDGE (the operator 2026-08-13): последним в success — внести snapshot/pattern/memory на будущее
        # (library уже забанкован выше). Держит success-release, пока не `EXIT-KNOWLEDGE: DONE`.
        _ek = active_exit_knowledge_pending(current_sid)
        if _ek:
            _block(EXIT_KNOWLEDGE_REASON % _ek, current_sid)
        _cleanup_owned_marker(current_sid)           # хант завершён успехом → снять СВОЙ маркер (keep-alive не держит вечно)
        sys.exit(0)

    tpath = data.get("transcript_path")
    if not tpath:
        sys.exit(0)  # без транскрипта не прочитать last_* → fail-safe release (не блокируем вслепую)

    last_assistant = ""
    last_user = ""
    try:
        with open(tpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message", obj)
                role = obj.get("type") or msg.get("role") or obj.get("role")
                text = extract_text(msg)
                if not text:
                    continue
                if role == "assistant" or msg.get("role") == "assistant":
                    last_assistant = text
                elif role in ("user", "human") or msg.get("role") == "user":
                    # ⛔ isMeta=True → сообщение ВПРЫСНУТО харнессом/хуком (Stop-hook feedback,
                    # slash-command output, system-reminder), НЕ напечатано the operator. Читать его как
                    # «the operator сказал X» = SELF-INFLICTED FALSE-RELEASE: наш же EXIT-KNOWLEDGE-ремайндер
                    # цитирует слово «уходим» («выходишь success или "уходим"…») → RELEASE-матч
                    # отпускал give-up РОВНО на сворачивании ханта (veda 2026-08-18: give-up ускользал
                    # ПОСЛЕ того как EXIT-KNOWLEDGE-гейт впрыснул свой reason как isMeta user-msg →
                    # следующий Stop читал ЕГО как последний user → false RELEASE → петля стопалась,
                    # the operator жал /compact+«продолжай» вручную). isMeta = чистый харнесс-маркер
                    # инъекции (реальный ввод the operator его не несёт). Пропускаем — last_user остаётся
                    # ПОСЛЕДНИМ РЕАЛЬНЫМ сообщением the operator. Чинит и любой будущий self-read: block
                    # REASON / INFO_REQUEST-лексика в наших же ремайндерах больше не трактуется как the operator.
                    if obj.get("isMeta"):
                        continue
                    last_user = text
    except Exception:
        sys.exit(0)

    # §35.4(b) fix: task-notification/system-reminder блоки — ДАННЫЕ, не команда the operator/наше
    # рассуждение (см. комментарий у _strip_machine_text выше). Стрипаем ОБА перед любым keyword-матчем.
    # USER-роль — робастный prefix-cut (Plan 6 fix1: вложенный close-tag не должен пропускать хвост в
    # RELEASE-матч); ASSISTANT-роль — non-greedy (мой текст обсуждает эти теги, не over-strip'аем).
    last_user = _strip_machine_text_user(last_user)
    last_assistant = _strip_machine_text(last_assistant)

    ul = last_user.lower()
    _release_hit = any(r in ul for r in RELEASE)
    # lombard-audit 2026-08-13: голое «уходи» (императив, the operator «здесь уходи ты не охотник») — release,
    # но список RELEASE ловил лишь «уходим»/«уходи с». Добавляем `\bуходи\b` с anti-FP на отрицание
    # («не уходи»/«пока не уходи» = продолжай, НЕ release).
    if not _release_hit and re.search(r"\bуходи\b", ul) and not re.search(r"(?:не|пока\s+не)\s+уходи", ul):
        _release_hit = True
    if _release_hit:
        # EXIT-KNOWLEDGE (the operator 2026-08-13): «уходим» больше НЕ мгновенный release без банка знания.
        # Если хант имел реальную работу и данные на будущее не внесены → reminder ОДИН раз (satisfiable
        # сентинелом DONE), потом release. the operator's прерогатива уважена (держит один шаг, не намертво).
        _ek = active_exit_knowledge_pending(current_sid)
        if _ek:
            _block(EXIT_KNOWLEDGE_REASON % _ek, current_sid)
        _cleanup_owned_marker(current_sid)  # the operator отпустил → хант закрыт → снять СВОЙ маркер
        _exit_diff(current_sid)     # B6: собрать незакрытые гейты → stderr INFO (не блок)
        sys.exit(0)  # the operator отпустил — его прерогатива

    # HUNT-MODE: MANUAL в ledger → автопетля выключена, поведение как раньше (блок только на give-up
    # + структурные напоминания, БЕЗ default-continue). Аварийный тормоз.
    manual = ledger_manual_mode(current_sid)

    al = last_assistant.lower()
    pending_reminder = ""   # AOE profile-cleared reminder-режим (corpus<2) — едет с LOOP_CONTINUE, не держит

    # 1) Явный give-up / развилка / решение-the operator → сильный anti-abort REASON.
    #    + PARAPHRASE-GIVEUP (8-й bypass, livepeer/rocketpool 2026-08-09): «честный финальный рапорт» с
    #    hardened/exhaustion/bad-EV/park фреймами новыми словами — обходил ABORT/BREADTH_RE. is_giveup=True
    #    → держим намертво (circuit breaker НЕ выпускает, в отличие от LOOP_CONTINUE-пути).
    if any(a in al for a in ABORT) or FORK_RE.search(al) or DECISION_Q_RE.search(al) \
            or BREADTH_RE.search(al) or _paraphrase_giveup(al):
        _block(REASON, current_sid, is_giveup=True)  # give-up держим намертво (circuit breaker обходится)

    # 1b) FALSE-EXHAUSTION (KAST 2026-07-07): ledger доказанно мелкий (≥6 kill / ноль T4-записей) →
    #     мягкая exhaustion-лексика в сообщении трактуется как give-up (в ЗДОРОВОМ ledger те же слова
    #     не блокируют — контекст решает, а не фраза). Держим намертво (is_giveup=True).
    if ledger_exhaustion_shape(current_sid) and soft_exhaustion_signal(al):
        _block(KILL_AUDIT_REASON, current_sid, is_giveup=True)

    # 1c) EARLY-EXHAUSTION (Sky 2026-07-07): заявление о полном охвате на Iteration ≤2 = физически
    #     невозможно (schema-независимо, читает канонический Iteration # из Loop State). Держим намертво.
    if ledger_early_exhaustion(current_sid):
        _block(EARLY_EXHAUSTION_REASON, current_sid, is_giveup=True)

    # 2) Находки/тела лидов в ЧАТ вместо ledger (skip если the operator сам просил инфу в чат).
    if not any(q in ul for q in INFO_REQUEST):
        if len(last_assistant) > 800 and findings_signal(last_assistant) >= 3 \
                and (active_ledger_stale(current_sid) or active_ledger_thin(current_sid)):
            _block(LEDGER_LIVE_REASON, current_sid)
        # Стена ТЕЛ лидов в чате даже при ведомом файле (≥3 schema-поля = ≥1 полное тело).
        if chat_lead_body_fields(last_assistant) >= 3:
            _block(CHAT_WALL_REASON, current_sid)

    # 2b) ФОНОВАЯ РАБОТА В ПОЛЁТЕ (фаза 3): скауты/workflow ещё считают → отпускаем turn.
    #     Харнесс переподнимет меня уведомлением о завершении, а блокировка здесь заставила бы
    #     копать ПАРАЛЛЕЛЬНО со своими же скаутами (дублирование + жжём токены на блоках).
    #     Стоит ПОСЛЕ give-up/chat-детекторов (их пропускать нельзя даже с работой в полёте)
    #     и ДО структурных гейтов (структуру как раз и наполняют возвращающиеся лиды).
    #     ⚠ Сторож: старше BG_WATCHDOG без уведомления = агент, вероятно, потерян → НЕ отпускаем,
    #     гейтим как обычно, иначе упавший субагент = молча умершая автопетля.
    _bg_n, _bg_age = pending_bg_work(tpath)
    if _bg_n and (_bg_age is None or _bg_age <= BG_WATCHDOG):
        # lombard-audit п.4 (parallel-during-fanout): веер/scout в фоне — НЕ простаивай, если есть ЖИВАЯ
        # нить. Форсим ПАРАЛЛЕЛЬНЫЙ serial depth-drive (веер = explore-wide фон; ты = exploit-deep serial).
        # Нет живой нити (первый scout-проход до модели) → release как раньше (ждём scout). manual → release.
        if not manual and _can_drive_parallel(current_sid):
            _block(PARALLEL_DRIVE_REASON % (_bg_n, int(_bg_age) if _bg_age is not None else 0), current_sid)
        sys.exit(0)

    # 3) Структурные пробелы ledger'а (recon-completeness / resumability / explore-wide).
    #    Impacts in Scope — ПЕРВЫМ (recon-порядок: пойми per-impact severity-рубрику ДО веера/копания).
    if active_ledger_missing_impacts(current_sid):
        _block(IMPACTS_REASON, current_sid)
    # veda 2026-08-18: IMPACTS-TODO снят, но intake — research-САММАРИ (само-заявленный маркер «перефраз/
    # дословно сверить/research-дыра») → хантил не тот impact-набор. Рядом с missing_impacts (тот же
    # recon-порядок: полная verbatim-рубрика ДО глубокой работы = ЧТО искать).
    _iip = active_impacts_intake_paraphrased(current_sid)
    if _iip:
        _block(IMPACTS_PARAPHRASE_REASON % _iip, current_sid)
    # Out-of-Scope дисквалификаторы (money-critical, 2026-08-11) — рядом с impacts (тот же recon-порядок:
    # вычитай OOS ДО глубокой работы, чтобы не копать/подавать находку в OOS). Отдельный сентинел OOS-TODO.
    if active_ledger_missing_oos(current_sid):
        _block(OOS_REASON, current_sid)
    # Asset-reconciliation (lombard-audit п.1) — тот же recon-порядок: сверь заявленное N assets с
    # извлечённым M ДО копания (M<N/N>12 → Playwright сам). Пропущенный ассет = пропущенный in-scope таргет.
    if active_ledger_assets_unreconciled(current_sid):
        _block(ASSETS_RECON_REASON, current_sid)
    if active_ledger_missing_loopstate(current_sid):
        _block(LOOP_STATE_REASON, current_sid)
    # 3-P0) MODEL-BEFORE-SCOUT (katana 2026-07-29): divergence-first порядок — модель `I-NN` ПЕРВОЙ,
    #       веер режет партиции ПО ИНВАРИАНТАМ ПОСЛЕ. Стоит ПЕРЕД scout-pending: если модель реально
    #       пуста, форсим её, а не веер (иначе scout идёт по файлам «туда, куда идёт толпа»). Depth-гейты
    #       позже → не затеняются (K5 сохранён). Не глушится INFO_REQUEST (P2: model — дефицит артефакта,
    #       не give-up), но уважает manual.
    if not manual:
        _mbs = active_model_before_scout(current_sid)
        if _mbs:
            _block(MODEL_BEFORE_SCOUT_REASON % _mbs, current_sid)
    if active_ledger_scout_pending(current_sid):
        _block(SCOUT_REASON, current_sid)
    # 3a-i) P-B boundary-scout отдельным агентом (Rootstock 2026-07-12): Scout DONE, но BOUNDARY-MAP
    #       placeholder → P-B «размазан» по код-скаутам, не запущен отдельно. Soft-nudge (решается запуском).
    if active_ledger_boundary_scout_skipped(current_sid):
        _block(BOUNDARY_SCOUT_REASON, current_sid)
    # 3a-ii) OPTIONAL-меню (P7-P10) сознательно консультировано? Сентинел OPT-TODO висит на DONE → нет.
    if active_ledger_optmenu_todo(current_sid):
        _block(OPTMENU_REASON, current_sid)
    # 3a-iii) WAVE-2 не забыта (the operator: CORE не уезжает, optional — в волну 2): `WAVE-2 … PENDING` → прогнать.
    if active_ledger_wave_pending(current_sid):
        _block(WAVE_PENDING_REASON, current_sid)
    # 3a-iv) P-CLONE producer (Task 4, FDE): web-хант, партиция P-CLONE активна, Scout DONE, но
    #        `clone_diff.md` не прогнан — Cross-Clone обязательная фаза §7. Contract-namespace → None.
    if active_clone_diff_skipped(current_sid):
        _block(CLONE_DIFF_REASON, current_sid)
    # 3a-v) P-AUTHZ producer (Task 9, FDE profile-web2-hunt): web2-хант, партиция P-AUTHZ активна,
    #       Scout DONE, но `authz_matrix.md` не прогнан — authz-diff harness = ядро web2 (§17).
    #       dapphunt/contract-namespace → None.
    if active_authz_matrix_skipped(current_sid):
        _block(AUTHZ_MATRIX_REASON, current_sid)
    # 3a-v2) OPERATION-COVERAGE (Task 2, Plan 9): producer authz_matrix.md ЕСТЬ, но (operation, role)
    #        строка без статуса — «чисто» неотличимо от «не тестили». Content-чек co-located producer'а.
    if active_operation_coverage_incomplete(current_sid):
        _block(OP_COVERAGE_REASON, current_sid)
    # 3a-vi) P-AI producer (Task 3, FDE План 7 §60): web-хант (TB/AC), AI/LLM-фича — партиция P-AI
    #        активна, Scout DONE, но `ai_trust_matrix.md` не прогнан — AI-surface trust-boundary (Cat 28).
    #        contract/deephunt-namespace → None. DESIGN-FLAG (для Task 11 review): дизайн §60.3 предлагал
    #        держать AI-surface существующим active_divergence_unresolved — здесь осознанное усиление
    #        отдельным producer-absent гейтом (симметрия с clone/authz), намеренное отклонение от дизайна.
    if active_ai_trust_unresolved(current_sid):
        _block(AI_TRUST_REASON, current_sid)

    # 3c) T4-INTEGRITY (KAST 2026-07-07): kill'ы ссылаются на T4/cold-verify, но Verifier Log ПУСТ →
    #     фейковый T4. Soft-nudge (is_giveup=False): решается логированием реального verdict'а.
    if ledger_t4_claimed_but_unlogged(current_sid):
        _block(T4_INTEGRITY_REASON, current_sid)

    # 3c-AOE) PROFILE-CLEARED (AOE §2.1/§4/§5.4 — ЯДРО трека): practicality-kill ([DE-MINIMIS]/
    #     [PRACTICALITY]/practicality:) ИЛИ capital-dependent confirm ([CAPITAL-DEP]) без структурного
    #     `profile-cleared: <ref>` (нетящего суждение против attacker_capability_baseline.md). Гейт на
    #     СОСТОЯНИЕ тега (образец T4-integrity), НЕ лексика. corpus-first: hard-блок только при >=2 labeled
    #     кейсах в манифесте, иначе reminder (едет с LOOP_CONTINUE, не держит выход — §5.4 гейт НЕ форсит
    #     active-действие). Симметрия: refute И confirm требуют ref. Уважает manual + INFO_REQUEST.
    if not manual and not any(q in ul for q in INFO_REQUEST):
        _pc = active_practicality_kill_unprofiled(current_sid)
        if _pc:
            _pc_mode, _pc_detail = _pc
            if _pc_mode == "hard":
                _block(PROFILE_CLEARED_REASON % _pc_detail, current_sid)
            else:
                pending_reminder = PROFILE_CLEARED_REMINDER % _pc_detail

    # 3b) DEPTH-QUALITY кластер (Berachain 2026-07-12: 2 Crit → оба DUPLICATE $0). Порядок = приоритет
    #     (первый _block выходит): (B) брошенный Crit-композит > (A) фейковая «5/5»-заявка без карты >
    #     (generic) широко-но-мелко. Стоит ПОСЛЕ scout-pending (первый breadth-проход стреляет SCOUT_REASON,
    #     не это). Не блокирует в MANUAL (аварийный ручной режим) и на INFO_REQUEST (the operator сам спросил).
    if not manual and not any(q in ul for q in INFO_REQUEST):
        if active_ledger_composite_abandoned(current_sid):
            _block(COMPOSITE_REASON, current_sid)
        # T6 (Plan 9, Tier B): гипотеза дошла до DRIVE (State C-PoC-attempting/D-PoC) без birth-time
        # intent-steelman («а это баг или замысел?» с file:line-пруфом). Стоит в DRIVE-quality кластере
        # (per-hypothesis, до траты глубины). Off-switch натуральный (нет резолвнутого DRIVE → молчит).
        _is = active_ledger_intent_steelman_missing(current_sid)
        if _is:
            _block(INTENT_STEELMAN_REASON % _is, current_sid)
        if active_ledger_depthmap_placeholder(current_sid):
            _block(DEPTHMAP_REASON, current_sid)
        if active_ledger_depthmap_single_subsystem(current_sid):
            _block(DEPTHMAP_SINGLE_REASON, current_sid)
        # T12 (фаза 2): слой засчитывается только при пересечённой границе + предсказании ДО/ПОСЛЕ.
        # Стоит ПОСЛЕ карты (placeholder/single-subsystem дают более базовое сообщение) и ПЕРЕД
        # wide_but_shallow: сначала честность заявленной глубины, потом её ширина.
        _t12 = active_depth_t12_incomplete(current_sid)
        if _t12:
            _block(T12_REASON % _t12, current_sid)
        # FORK-DIFF (confession 2026-08-09): родитель форка опознан, но executable differential не
        # прогнан — «canonical» выдан за falsifier. Стоит ПОСЛЕ T12 (сначала честность depth-shape,
        # потом executable-верификация против родителя). Off: не форк / незрелая модель / MODEL: N/A.
        _fd = active_fork_diff_unrun(current_sid)
        if _fd:
            _block(FORK_DIFF_REASON % _fd, current_sid)
        # FORK-UNDECLARED (benqi audit 2026-08-09): ledger сам заявляет форк родителя, но поле
        # PARENT-FORK пусто → fork-diff гейт не армится. Soft-nudge (не hard-block: сигнал полу-
        # лексический, n=1) — форсит декларацию поля, чтобы hard fork-diff гейт ожил на след. Stop.
        if not pending_reminder:
            _fu = active_fork_undeclared(current_sid)
            if _fu:
                pending_reminder = FORK_UNDECLARED_REMINDER % (_fu, _fu.capitalize())
        # EXECUTABLE-FLOOR (B2, audit 2026-08-09): ≥5 T9-осей + 0 executable-прогонов + не форк →
        # soft-nudge прогнать executable сильнейшую нить (axelar: 21 ось, 0 fork-PoC). Не hard-block
        # (не-EVM/без-харнесс возможны). Молчит если executable уже был (balancer/1inch не флагаются).
        if not pending_reminder:
            _ef = active_executable_floor_unrun(current_sid)
            if _ef:
                pending_reminder = EXEC_FLOOR_REMINDER % _ef
        # ZERO-D-NN (B4, audit 2026-08-09, Mandate 0.9): зрелая модель + ≥3 осей + 0 D-NN за хант +
        # blind_spots не помянут → soft-nudge эскалировать divergence-генератор + записать (1inch: 0 D-NN).
        if not pending_reminder:
            _zd = active_zero_divergence_unescalated(current_sid)
            if _zd:
                pending_reminder = ZERO_DNN_REMINDER % _zd
        # AOE §4 money-lead-first: value ЗАМАПЛЕНА (## Value Concentration), но сильнейшая $-нить не на
        # 5 → depth-приказ на неё. Value-aware вариант wide_but_shallow, стоит ПЕРЕД ним: при
        # замапленной ценности $-таргетированный приказ точнее generic depth-lead. Молчит без
        # value-секции → wide_but_shallow ловит остальное. reachable-$ = tie-break ВНУТРИ
        # divergence-first (Mandate 0.9), НЕ $-первый SELECT. НЕ corpus-gated (depth-гейт).
        # AOE durability-companion (the operator 2026-08-06): DeFi/money-таргет, но value НЕ замаплена →
        # форс выписать ## Value Concentration ПЕРЕД тем как moneylead сможет ожить (иначе на
        # DeFi-цели забытая value-секция = money-lead молча спит). Сначала замапь, потом гони вниз.
        if active_defi_value_unmapped(current_sid):
            _block(DEFI_VALUE_UNMAPPED_REASON, current_sid)
        if active_moneylead_shallow(current_sid):
            _block(MONEYLEAD_REASON, current_sid)
        if active_ledger_wide_but_shallow(current_sid):
            _block(DEPTH_LEAD_REASON, current_sid)
        # Task 6 (FDE План 6, §27): заявленная цепочка находок (co-occurrence) без доказанной
        # передачи выход-A→вход-B. Тот же INFO_REQUEST-уважающий кластер, что composite/depthmap/
        # wide-but-shallow (append-only, последним): «нарисуй граф зависимости», не блокирует
        # намертво (is_giveup=False по умолчанию у _block).
        _cc = active_chain_dependency_unproven(current_sid)
        if _cc:
            _block(CHAIN_DEPENDENCY_REASON % _cc, current_sid)

    # 3d) MODEL-кластер (divergence-first, T10/T13 — фаза 1 depth_engine_plan).
    #     ПОРЯДОК: стоит ПОСЛЕ depth-quality кластера сознательно. Гейт модели персистентный (пока
    #     файл не заполнен, он выстрелит и на следующем ходу), а depth-гейты адресуют гипотезу В
    #     РАБОТЕ — их сообщение конкретнее и срочнее. Поставленный раньше, MODEL-гейт ЗАТЕНЯЛ бы их
    #     (проверено e2e-смоуком: 3 сценария depth перестали получать своё сообщение).
    #     Все три снимаются сентинелом `MODEL: N/A — <причина>` (K2) — мелкий контракт/фронт/web2.
    # P2 (katana 2026-07-29): MODEL-кластер НЕ глушится INFO_REQUEST — модель это ДЕФИЦИТ АРТЕФАКТА
    #     (divergence-first фундамент), а не give-up: вопрос the operator не отменяет её необходимость. При
    #     ПОЛНОЙ модели гейты молчат → строка 2330 (INFO → exit) пропускает ответ. Глушился только пустой
    #     вопрос (бытовые «покажи/почему/в чём») → выключал T10-форс при живом диалоге. Manual уважаем.
    if not manual:
        _m = active_model_incomplete(current_sid)
        if _m:
            _block(MODEL_REASON % _m, current_sid)
        _m = active_model_order_violation(current_sid)
        if _m:
            _block(MODEL_ORDER_REASON % _m, current_sid)
        _m = active_divergence_unresolved(current_sid)
        if _m:
            _block(DIVERGENCE_REASON % _m, current_sid)
        # OBS-8 (wave-transition): закрытая модель-волна + пустой live-пул + непокрытые подсистемы =
        # НЕ исчерпанность → держим твёрдо (is_giveup), как анти-false-exhaustion.
        _m = active_wave_transition_needed(current_sid)
        if _m:
            _block(_m, current_sid, is_giveup=True)
        # MODEL MULTI-WAVE (aevo): модель есть, ноль открытых D-NN, но оси инвариантов (cross-function/
        # order/temporal/isolation/economic) не покрыты → исчерпана ОДНА ось, не модель. Форс следующей
        # оси. Стоит ПЕРЕД core_enforced_t9: волна инвариантов дешевле cold-restart (не прыгай в T9, пока
        # оси не пройдены). Держим твёрдо (is_giveup — анти-false-exhaustion на уровне модели).
        _ax = active_model_axes_incomplete(current_sid)
        if _ax:
            _block(MODEL_AXES_REASON % (_ax[0], "; ".join(_ax[1])), current_sid, is_giveup=True)
        # OBS-10 (gmtrade + aave-v4 2026-07-30): СЧЁТНЫЙ инвариант «заявленные T9-оси vs построенные
        # волны». Ловит «сменил ось → погнал H-NN, НЕ засеял волну I-NN» — промах, который marker-based
        # axes_incomplete проскакивал (имя оси в прозе ложно «покрывает»). Держим твёрдо (is_giveup).
        _aw = active_axes_without_waves(current_sid)
        if _aw:
            _block(AXES_WAVES_REASON % (_aw[1], _aw[0], _aw[2], _aw[3]), current_sid, is_giveup=True)
        # originprotocol-audit (the operator «забыл I-NN на новых волнах»): КОМПЛЕМЕНТ OBS-10 — агент строит
        # доп-волны, но `T9 restart axes used` не проставлен + реестр пуст → _t9_axes_declared=0 → OBS-10
        # слеп → scout-first вместо model-first на T9-осях. Форсит проставить счётчик/реестр.
        _t9u = active_t9_count_untracked(current_sid)
        if _t9u:
            _block(T9_COUNT_UNTRACKED_REASON % (_t9u[0], _t9u[1]), current_sid)
        # OBS-11 (T11): зрелая модель без вердикта `T11-VERDICT:` → фаза J2 (harness-as-generator)
        # молча пропущена (детектор APPLICABLE, но ничто не форсило). Decision-sentinel, не hard-fuzz.
        _t11 = active_t11_undecided(current_sid)
        if _t11:
            _block(T11_UNDECIDED_REASON % _t11, current_sid)
        # OBS-12 (T14): зрелая модель, 0 открытых D-NN, `## Attention Gaps` пуста и не N/A → второй
        # источник МЕСТА пропущен перед выводом «нечего». Открытый D-NN снимает (драйвь его раньше).
        _ag = active_attention_gap_skipped(current_sid)
        if _ag:
            _block(ATTENTION_GAP_REASON % _ag, current_sid)
        # Residual #2 (ethena-live judge-3): T14 once-per-hunt — заполнил `## Attention Gaps` раз →
        # attention_gap_skipped молчит навсегда, хотя каждая новая T9-ось = новая территория. Re-arm
        # per-axis (зеркалит active_axes_without_waves): осей заявлено N≥2, а записей attention-gap < N.
        _ags = active_attention_gap_stale(current_sid)
        if _ags:
            _block(ATTENTION_GAP_STALE_REASON % (_ags[0], _ags[1], _ags[2]), current_sid)
        # FEAT-E (jito-live): HYBRID Scout Fan-Out (divergence_fanout) — веер-per-wave re-arm. Осей N≥3,
        # прогонов веера < N → веер отстал (гнался раз на старте). Веер РОЖДАЕТ D-NN/cross-thread/severity —
        # корень их недорождения (jito: D-NN=0). Soft-nudge (веер дорогой). Зеркалит attention_gap_stale.
        _hfs = active_hybrid_fanout_stale(current_sid)
        if _hfs:
            _block(HYBRID_FANOUT_STALE_REASON % (_hfs[0], _hfs[1], _hfs[2]), current_sid)
        # Task 1 (FDE План 6, §50.1/§51): зрелая модель + `## Un-Dup Sweep` секция несёт применимый
        # по профилю генератор без статуса → un-dup-источник МЕСТА пропущен. Soft-nudge
        # (is_giveup=False — satisfiable fill-or-N/A, всё равно держит turn). Стоит рядом с
        # attention-gap (та же роль — второй/третий независимый источник МЕСТА).
        _us = active_undup_sweep_incomplete(current_sid)
        if _us:
            _block(UNDUP_SWEEP_REASON % _us, current_sid)
        # Task 2 (FDE План 6, §43.1/§50/§51): зрелая модель с >=COMPOSITION_MIN_BOUNDARIES границами,
        # но co-located `composition_map.md` не прогнан — главный un-dup-генератор пропущен. Тот же
        # soft-nudge off-switch, что active_undup_sweep_incomplete (рядом по роли — источник МЕСТА).
        _cm = active_composition_pass_skipped(current_sid)
        if _cm:
            _block(COMPOSITION_REASON % (_cm, COMPOSITION_MIN_BOUNDARIES), current_sid)
        # Task 3 (FDE План 6, §48.2/§44/§50.3): D-NN без заполненного/сильного undup_origin — likely-
        # dup, источник МЕСТА не назван. Тот же soft-nudge off-switch, что Task 1/2 (рядом по роли —
        # третий независимый un-dup-сигнал).
        _uo = active_undup_origin_missing(current_sid)
        if _uo:
            _block(UNDUP_ORIGIN_REASON % _uo, current_sid)
        # Task 5 (FDE План 7, TIER B §61 · §48.1): зрелый ledger + `PRIOR-PATTERNS: {TODO}`/пусто →
        # проактивный un-dup компаундинг (греп `fingerprint`'ов прошлых confirmed un-dup по коду
        # таргета) пропущен. SENTINEL-класс (ledger-строка), тот же soft-nudge off-switch, что Task
        # 1/2/3 (рядом по роли — «что уже ловили и толпа не закрыла нигде», не «где расходится модель»).
        _pr = active_pattern_replay_skipped(current_sid)
        if _pr:
            _block(PATTERN_REPLAY_REASON % _pr, current_sid)
        # P0-Exposure (SlowMist Aug-2026, Exposure Engine · Cat 4.10): зрелый ledger + `EXPOSURE-SCAN:
        # {TODO}`/пусто → кросс-движковый secret/key/PII/financial-data grep-pass (secret_exposure_scanner.py)
        # не прогнан. SENTINEL-класс (ledger-строка), тот же soft-nudge off-switch, что Task 1/2/3/5.
        _ex = active_exposure_scan_skipped(current_sid)
        if _ex:
            _block(EXPOSURE_SCAN_REASON % _ex, current_sid)
        # P8-HARD (T9 cold-restart, katana): все I-NN ENFORCED + 0 D-NN + 0 живых H = ядро оси исчерпано
        # → форс T9 на НОВОЙ оси cold-агентом. Coverage-независим (gaming закрытым Coverage не спасает).
        # Стоит ПОСЛЕ wave_transition (то конкретнее — «вот непокрытая подсистема») и ПОСЛЕ axes-incomplete
        # (оси инвариантов пройдены раньше T9). Держим твёрдо (is_giveup — анти-выход).
        _m = active_core_enforced_needs_t9(current_sid)
        if _m:
            _block(_m, current_sid, is_giveup=True)
        # OBS-9 (model-first nudge): code-read H-NN без model-backing при непокрытых подсистемах — soft.
        _m = active_wave_codefirst_nudge(current_sid)
        if _m:
            _block(_m, current_sid)
        # Hunt Strategy Layer (2026-08-08): ≥1 ось ЗАКРЫТА + `Axis-Queue` пусто/none/заглушки + МЕЖДУ
        # осями (0 живых H-NN, Depth-Lead none) → forward-план смены осей не записан («забыл куда дальше»).
        # Читает ledger НАПРЯМУЮ (НЕ model-gated: ось закрывается и на MODEL: N/A — там весь model-кластер
        # выше молчит, а этот ловит). Стоит ПОСЛЕ wave_transition/core_enforced_t9: их directива конкретнее
        # (вот непокрытая подсистема / cold-restart), этот — остаток. Комплемент, не конфликт: wave-
        # transition = «построй ВОЛНУ», axis-queue = «запиши следующую ОСЬ». Satisfiable soft-nudge.
        _aq = active_axis_queue_empty(current_sid)
        if _aq:
            _block(AXIS_QUEUE_REASON % _aq, current_sid)
        # FIX-B (ethena-live 2026-08-12, judge-2): БОГАТАЯ forward-очередь. active_axis_queue_empty под driver
        # стоит в стороне при ≥1 валидном атоме; drained молчит при ≥1 OPEN/ACTIVE → «1 ACTIVE + 0 OPEN»
        # (реактивный one-at-a-time) не ловился. Companion: ≥2 закрытых оси + <3 OPEN-ранжированных → nudge.
        _aqt = active_axis_queue_thin(current_sid)
        if _aqt:
            _block(AXIS_QUEUE_THIN_REASON % (_aqt[0], _aqt[1], _aqt[2], AXIS_QUEUE_THIN_MIN_OPEN), current_sid)
        # originprotocol-audit (the operator «главное чтобы шёл по очереди»): новая ось поднята выше хвостов живой
        # очереди и взята мимо порядка (`re-ranked ABOVE queue-tails`) — прыжок. Порядок = закон.
        _arm = active_axis_reranked_midqueue(current_sid)
        if _arm:
            _block(AXIS_REORDER_REASON % _arm, current_sid)
        # originprotocol-audit (the operator «почему только критикал?»): ось закрыта по «нет Critical» без явной
        # оценки High/Medium — узкий фрейм (loop-exit=High/Critical, Medium=DRIVE+банк).
        _aco = active_axis_closed_critical_only(current_sid)
        if _aco:
            _block(AXIS_CRIT_ONLY_REASON % _aco, current_sid)
        # A5 (Волна 1 2026-08-08): ≥2 confirmed banked findings, но T6-пасс по банку не отмечен →
        # перед batch-submit не проверены пары output→input (доказанные building-blocks → цепочка →
        # severity-boost + un-dup). Читает ledger напрямую (banked независимы от model-maturity).
        # Satisfiable soft-nudge, НЕ выход петли (banked Medium/Low её не завершают). Последним в кластере.
        # FIX-5 (ethena-live 2026-08-12, judge): split-brain — атомы `status:BANKED` есть, а таблица
        # `## Banked Findings` пуста → composite/OOS/T4 banked-гейты (читают таблицу) молчат. Форсим синк
        # ПЕРВЫМ в кластере, чтобы остальные banked-гейты видели реальные строки. Satisfiable soft-nudge.
        _bau = active_banked_atom_unsynced(current_sid)
        if _bau:
            _block(BANKED_ATOM_UNSYNCED_REASON % _bau, current_sid)
        # veda 2026-08-18 (the operator «Low/Medium building-blocks записывай структурно для T6-мержа даже если не
        # платят»): confirmed Low/Medium заявлены ПРОЗОЙ (bare-теги), таблица пуста → composite слеп. Форсим
        # синк прозы→таблица ПОСЛЕ atom-sync (тот — для реестр-атомов), ПЕРЕД composite (чтобы тот увидел строки).
        _bpu = active_banked_prose_unsynced(current_sid)
        if _bpu:
            _block(BANKED_PROSE_UNSYNCED_REASON % _bpu, current_sid)
        _bc = active_banked_composite_unchecked(current_sid)
        if _bc:
            _block(BANKED_COMPOSITE_REASON % _bc, current_sid)
        # 0x 2026-08-18 (the operator «Medium наравне, а забывают»): T6-пасс DONE, но банк ВЕСЬ Low → Medium-тир
        # не гнался выделенным DRIVE. Стоит ПОСЛЕ composite (тот форсит T6-DONE, который здесь = wind-down-сигнал).
        _mtu = active_medium_tier_undriven(current_sid)
        if _mtu:
            _block(MEDIUM_TIER_UNDRIVEN_REASON % _mtu, current_sid)
        # FEAT-I (jito-live): единый cross-thread движок — ≥4 building-blocks (refuted+banked+D-NN) без
        # synthesis-пасса / отстал от роста. Комплемент banked_composite (тот banked×banked; этот — весь пул).
        _cts = active_crossthread_synthesis_stale(current_sid)
        if _cts:
            _block(CROSSTHREAD_SYNTHESIS_STALE_REASON % (_cts[0], _cts[1], _cts[2]), current_sid)
        # FEAT-C (jito-live): false-refute guard — сильная нить (High/Crit [KILLED]) без adversarial
        # cold-recheck (риск false-refute, Superform-урок). Retention→T6 покрыт FEAT-I; здесь — перепроверка.
        _sru = active_strong_refute_unrechecked(current_sid)
        if _sru:
            _block(STRONG_REFUTE_REASON % (_sru[0], _sru[1]), current_sid)
        # Out-of-Scope на banked-подаче (money-critical, 2026-08-11): banked Medium/Low не проходят через
        # HUNT-EXIT submit-гейт → форсим OOS-сверку тут (закрывает дыру инцидента для Medium/Low).
        _boc = active_banked_without_oos_check(current_sid)
        if _boc:
            _block(BANKED_OOS_REASON % _boc, current_sid)
        # FEAT-L (jito-live): $-at-risk не квантифицирован структурно перед подачей banked → приоритет
        # подачи (Reliability×$-at-risk) не посчитать. R10 SAFETY: magnitude только на форке.
        _var = active_value_at_risk_unquantified(current_sid)
        if _var:
            _block(VALUE_AT_RISK_REASON % _var, current_sid)
        # FEAT-K (jito-live): banked-staleness — banked лежит давно (iter≥10) без freshness-check →
        # re-check жив ли баг перед batch-submit (Templar: deployed≠HEAD).
        _bs = active_banked_staleness_unchecked(current_sid)
        if _bs:
            _block(BANKED_STALENESS_REASON % (_bs, BANKED_STALENESS_ITER, BANKED_STALENESS_ITER), current_sid)
        # BANKED БЕЗ T4 (ре-судья D4): banked `confirmed` без записи в Verifier Log — пачка Medium/Low
        # уходит с нулевой верификацией (submit-гейты армятся только на HUNT-EXIT). Тот же banked-кластер.
        _bt4 = active_banked_without_t4(current_sid)
        if _bt4:
            _block(BANKED_T4_REASON % _bt4, current_sid)
        # WORKLIST DRIVER Этап 1 (за WORKLIST_DRIVER_ENABLED, план §3): машинный реестр атомов диктует
        # голову. ADDITIVE — молчат без секции `## Atom Registry` / без валидных атомов (C1 + первый
        # проход) → нулевой blast-radius на legacy-ханты. Оба satisfiable soft-nudge (is_giveup=False).
        # (a) pick мимо головы реестра = livepeer-fix; (b) C3-связка: CLOSED без proof-записи в прозе
        # ослепил бы 39 прозо-гейтов. Стоят последними в кластере (реестр = проекция всего worklist'а).
        if WORKLIST_DRIVER_ENABLED:
            # adoption-гейт присутствия секции (re-pilot MED-1) ПЕРВЫМ: секции `## Atom Registry` нет вовсе
            # на зрелом активном ledger'е → весь драйвер слеп по C1. Комплемент unpopulated (секция-есть-пуста).
            _rsa = active_registry_section_absent(current_sid)
            if _rsa:
                _block(REGISTRY_SECTION_ABSENT_REASON % _rsa, current_sid)
            # adoption-гейт пустоты: секция ЕСТЬ, но пуста/placeholder на зрелом активном ledger'е — населить
            # (иначе pick-гейт беззуб). Off: нет секции (C1→section_absent выше) / placeholder-pick / iter<3.
            _ru = active_registry_unpopulated(current_sid)
            if _ru:
                _block(REGISTRY_UNPOPULATED_REASON % _ru, current_sid)
            # liveness-компаньон (1inch пилот HIGH-1): реестр НЁС валидные атомы, но 0 OPEN/ACTIVE (все
            # CLOSED/PARKED/BANKED) без HUNT-EXIT = give-up-шов, невидимый pick-гейту (нет головы) и
            # axis-queue (CLOSED-атомы уводят в сторону). Взаимоисключающ с unpopulated (0 валидных).
            # NB (re-pilot MED-2, idle-ACTIVE stall): «атом ACTIVE, но не гонится» — НЕ задача этого гейта.
            # Драйвер стирит КАКОЙ атом; effort-liveness ACTIVE-атома ловит depth_spin ниже (ledger писался
            # K+ ходов, а глубина/T4/pred-obs не выросли = рационализация → форс cold-spawn). Полностью
            # мёртвый ledger (mtime заморожен) → circuit_broken anti-spin release by-design (не жжём токены).
            _rd = active_registry_drained_no_exit(current_sid)
            if _rd:
                _block(REGISTRY_DRAINED_REASON % _rd, current_sid)
            # anti-breadth-treadmill (1inch long-run, the operator «меняли ось каждые 2 минуты»): много осей
            # закрыто self-ярлыком depth-drive, но observed-артефактов нет → depth-театр, депт-гейты слепы
            # к реестровому формату. Держит выход, пока заявленная глубина не подкреплена DEPTH-TRACE.
            _di = active_axes_depth_inflated(current_sid)
            if _di:
                _block(AXES_DEPTH_INFLATED_REASON % _di, current_sid)
            # FIX-F (judge-3, HIGH): scout-verified breadth-escape — FIX-A ловит depth-drive-ярлык, этот ловит
            # избыток scout-verified-закрытий (честный слабый ярлык обходил FIX-A). Комплемент, стоит СРАЗУ после.
            _bt = active_axes_breadth_tilt(current_sid)
            if _bt:
                _block(AXES_BREADTH_TILT_REASON % (_bt[0], _bt[1], _bt[2], _bt[3]), current_sid)
            # FEAT-G (jito-live): depth-per-axis floor — depth-drive ось с proof `depth-trace N/M`, N<5
            # (ранний close сильной нити ниже depth-ceiling). Per-axis комплемент глобального FIX-A.
            _adf = active_axis_depth_below_ceiling(current_sid)
            if _adf:
                _block(AXIS_DEPTH_FLOOR_REASON % (_adf[0], _adf[1]), current_sid)
            # Residual #3 (judge-3, MED): observed:file:line verifiability — FIX-A/FIX-F зачитывают
            # `observed: File.sol:NNN` как глубину, но не проверяют существование файла (фабрикуемо). Если
            # src co-located — цитируемый basename обязан существовать. Fail-open (нет дерева → silent).
            _of = active_observed_fabricated(current_sid)
            if _of:
                _block(OBSERVED_FABRICATED_REASON % (_of[0], _of[1]), current_sid)
            _pq = active_pick_not_from_queue(current_sid)   # (relpath, head_str) — compute-and-name
            if _pq:
                _block(PICK_NOT_FROM_QUEUE_REASON % _pq, current_sid)
            _cn = active_atom_closed_without_narrative(current_sid)
            if _cn:
                _block(ATOM_CLOSED_NO_NARRATIVE_REASON % _cn, current_sid)
            # (c) судья-B Д2: OPEN/ACTIVE-атом с id-образным `src`, которого нет в нарративе = фиктивное
            #     обоснование (симметрия C3 для OPEN-стороны). Ловит подмножество laundered-wrong-axis.
            _su = active_atom_src_ungrounded(current_sid)
            if _su:
                _block(ATOM_SRC_UNGROUNDED_REASON % _su, current_sid)
            # rank-evidence (финальный судья Axis-2): голова с Crit-ранком, но голым src = laundered-wrong-
            # axis всплыла в голову голым числом. Композится с src_ungrounded (тот — фабрикованный id).
            _hr = active_head_rank_unjustified(current_sid)
            if _hr:
                _block(HEAD_RANK_UNJUSTIFIED_REASON % (_hr[0], _hr[1], _hr[2], _hr[3], _HEAD_RANK_REQ[_hr[4]]),
                       current_sid)

    # 4) DEFAULT автопетля (codex-режим): хант жив, High/Critical не подтверждён, the operator не отпускал → НЕ
    #    завершаем turn, гоним следующий single-pick. Off только HUNT-MODE: MANUAL. INFO_REQUEST →
    #    отвечаю the operator и стоплю (он сам спросил — легальная пауза, петля возобновится следующим turn'ом).
    if manual:
        sys.exit(0)
    if any(q in ul for q in INFO_REQUEST):
        sys.exit(0)
    # DEPTH-SPIN (durable core): петля жива, но глубина стоит K+ ходов (ledger растёт рационализацией,
    # не копанием) → escalate дефолтный continue на жёсткую cold-spawn директиву. mtime движется →
    # circuit_broken не отпустит (не мёртвый спин, а холостой ход) → инстанс форсится ВГЛУБЬ.
    if depth_spin(current_sid):
        _block(DEPTH_SPIN_REASON, current_sid)
    # WORKLIST DRIVER Этап 2 (§8 G-advisory — 2 канала Слоя-2): directive = активная голова реестра
    # ЛИБО LOOP_CONTINUE fallback; advisory[] = soft-rider'ы (G-weak). pending_reminder (4 rider'а выше:
    # PROFILE-CLEARED / FORK-UNDECLARED / EXEC-FLOOR / ZERO-D-NN) едет ПЕРВЫМ — раньше он прямо prepend'ился
    # к LOOP_CONTINUE (стр. ~5250); теперь оба rider-канала сливаются в один _block. Флаг off → чистый
    # LOOP_CONTINUE (побайтово старое поведение — тривиальный откат).
    if WORKLIST_DRIVER_ENABLED:
        _directive, _advisory = next_atom(current_sid)
    else:
        _directive, _advisory = LOOP_CONTINUE_REASON, []
    _riders = ([pending_reminder] if pending_reminder else []) + _advisory
    _block("\n\n".join(_riders + [_directive]) if _riders else _directive, current_sid)


if __name__ == "__main__":
    main()
