#!/usr/bin/env python3
"""PreToolUse hook (matcher: AskUserQuestion) — AUTONOMOUS MODE guard.

Purpose: close a hole (orca 2026-08-18) — during an active hunt the hunter, instead of continuing
autonomously, calls `AskUserQuestion` with a decision menu "Next move: where to?" (differential-fuzz /
snapshot-and-leave / T9), HANDING the wheel back to the operator. This is exactly what
feedback_autonomous_no_menus forbids: do not hand back the wheel, dig until T4 High/Crit or an explicit
"we're leaving". Root cause: the completeness gate (Stop hook) holds the turn ONLY at COMPLETION;
`AskUserQuestion` is a tool PAUSE (waits for an answer), the turn does not end -> the Stop hook does not
fire. `AskUserQuestion` = the ONLY tool that returns the wheel while bypassing all hooks. DECISION_Q_RE in
the Stop hook catches give-up PROSE, but a menu goes through a tool, not prose.

Fire (deny) iff (a) tool == AskUserQuestion AND (b) a hunt is running IN THIS session (own fresh `.hunt_active`) AND
              (c) there is NO real `HUNT-EXIT: T4-CONFIRMED` in the ledger (hunt not finished by a finding) AND
              (d) the question is NOT about OPSEC/top-up (a legit Watson request — "fund the burner with $5").
Silence (allow) iff not a hunt / hunt finished with HUNT-EXIT / question about top-up-balance-burner / foreign session.
Fail-open: any error -> exit 0 (allow) with no output (never break the work).

Deny (not a reminder): a menu direction must NOT reach the operator — it IS the handing back of the wheel. The reason
goes to the agent as feedback -> it continues autonomously (SELECT the strongest axis / T9, the axis is set by IT).
"""
import sys
import os
import re
import json
import glob
import time


def _read_marker(marker_path):
    try:
        with open(marker_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return (False, None)
    if not raw.strip():
        return (False, None)
    lines = raw.splitlines()
    sid = lines[1].strip() if len(lines) >= 2 and lines[1].strip() else None
    return (True, sid)


def _sessions_root():
    env = os.environ.get("BBT_SESSIONS_DIR")
    if env:
        return env
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
    return os.path.join(root, "bug-bounty-toolkit", "sessions")


def _owned_markers(current_sid):
    out = []
    try:
        sessions = _sessions_root()
        now = time.time()
        for m in glob.glob(os.path.join(sessions, "*", ".hunt_active")):
            if now - os.path.getmtime(m) >= 24 * 3600:
                continue
            valid, sid = _read_marker(m)
            if not valid:
                continue
            if current_sid:
                if sid != current_sid:
                    continue
            elif sid is not None:
                continue
            out.append((os.path.getmtime(m), m))
    except Exception:
        return []
    return out


# A real HUNT-EXIT in the ledger (not a template blockquote instruction, not a backtick example). The line is NOT in a
# `>` block and NOT in inline `code` + carries HUNT-EXIT + T4-CONFIRMED. (Same class as machine-vs-template in the
# other hooks — the template carries `HUNT-EXIT: T4-CONFIRMED <High|Critical>` as an INSTRUCTION.)
_HUNT_EXIT_RE = re.compile(r"HUNT-EXIT\s*:\s*T4-CONFIRMED\s+(?:High|Critical)", re.I)


def _real_hunt_exit(marker):
    """True iff the ledger carries a REAL HUNT-EXIT: T4-CONFIRMED High|Critical line (not an instruction)."""
    try:
        with open(os.path.join(os.path.dirname(marker), "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    for ln in lt.splitlines():
        s = ln.lstrip()
        if s.startswith(">") or s.startswith("<") or "`" in ln or "{" in ln:
            continue                       # blockquote / placeholder / inline-code = instruction, not fact
        if _HUNT_EXIT_RE.search(ln):
            return True
    return False


# OPSEC/top-up Watson request — the ONLY legit question during an active hunt (a pinpoint real-world action,
# not a "direction decision"): fund the burner, sign a mainnet tx, grant access. We do not block it.
# NOTE: this regex intentionally keeps its original Russian alternatives so it still matches localized question text.
_TOPUP_RE = re.compile(
    r"top-?up|пополн|залей|зали\w+|баланс|balance|burner|бёрнер|бернер|"
    r"подпиш|подпис\w+|mainnet-tx|газ\b|\bgas\b|средств|денег|\$\d|оплат|fee\b|комисс",
    re.I)


def _question_text(data):
    """Collect the text of AskUserQuestion questions + options (for top-up detection)."""
    tin = data.get("tool_input") or {}
    parts = []
    qs = tin.get("questions")
    if isinstance(qs, list):
        for q in qs:
            if not isinstance(q, dict):
                continue
            parts.append(str(q.get("question", "")))
            parts.append(str(q.get("header", "")))
            opts = q.get("options")
            if isinstance(opts, list):
                for o in opts:
                    if isinstance(o, dict):
                        parts.append(str(o.get("label", "")))
                        parts.append(str(o.get("description", "")))
    return " ".join(parts)


DENY_REASON = (
    "🤖 AUTONOMOUS MODE (feedback_autonomous_no_menus) — do NOT hand back the wheel with a 'where to next' decision menu. "
    "An active hunt is running and there is no real `HUNT-EXIT: T4-CONFIRMED`. Axiom: bugs are EVERYWHERE -> 0 findings = "
    "\"not dug deep enough yet\", NOT an exit and NOT a reason to ask the operator. YOU make the SELECT of the next move yourself: "
    "strongest open thread (severity×confidence) -> unread score-5 file -> T6 composite from "
    "refuted -> pop the head of the `Axis-Queue` -> T9 cold-restart (YOU set the AXIS, not the operator). Options like "
    "a differential-fuzz fan-out / T9-new-axis are YOUR moves: EXECUTE the strongest one immediately, do not put it in a "
    "menu. The only two exits from the loop: (1) write `HUNT-EXIT: T4-CONFIRMED <High|Critical>` into the ledger "
    "after a real T4; (2) the operator writes \"we're leaving\" THEMSELVES (you do not initiate it). The only exception — an "
    "OPSEC/top-up blocker (burner empty, a signature needed): then ask in SHORT text about the balance, NOT a "
    "direction decision menu. Keep hunting."
)


def _emit_deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name") or ""
    current_sid = data.get("session_id") or ""

    if tool != "AskUserQuestion":
        sys.exit(0)
    owned = _owned_markers(current_sid)
    if not owned:
        sys.exit(0)                        # not a hunt — an ordinary question is legit
    _, marker = max(owned)

    try:
        if _real_hunt_exit(marker):
            sys.exit(0)                    # hunt finished by a finding — the question (submit/next target) is legit
        if _TOPUP_RE.search(_question_text(data)):
            sys.exit(0)                    # OPSEC/top-up Watson request — legit, let it through
        _emit_deny(DENY_REASON)            # direction menu during an active hunt -> block, continue on your own
    except Exception:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
