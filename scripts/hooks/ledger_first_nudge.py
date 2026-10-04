#!/usr/bin/env python3
"""PostToolUse hook (matcher: Task) — LEDGER-FIRST scout-return nudge.

Purpose: close a recurring miss — an instance launches a scout fan-out
(Task subagents), gets leads back and NARRATES their merge as a WALL OF TEXT in
CHAT, while `hypotheses.md` stays an empty template. The Stop gate only catches
this at the END of the turn (context is already saturated). This hook fires
EARLIER — on the Task subagent's return — and nudges "leads into the file as the
FIRST action", exactly at the point of failure.

Logic (everything is a no-op on any ambiguity, fail-open):
  - Fires only on PostToolUse Task.
  - Only if a hunt is running IN THIS session (own fresh `.hunt_active`,
    session_id-scoped).
  - Only if the active ledger is `thin` (not a single real `### H-<digit>` /
    scout-H-NN entry) — i.e. leads have NOT been recorded yet. Once recorded, we
    do not nudge (no noise).
  - Debounce: at most once per 120s (marker `.last_ledger_nudge` in the session
    folder) — so a batch of 5 parallel Tasks does not emit 5 identical reminders.
  - Injects additionalContext (PostToolUse). Never blocks.

Fail-open: any error -> exit 0 with no output.
"""
import sys
import os
import re
import json
import glob
import time


def _read_marker(marker_path):
    """(valid, sid). valid=False if the marker is empty/corrupt (0 bytes from an interrupted write)."""
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


def _owned_markers(current_sid):
    """Fresh (<24h) .hunt_active markers for this session — (mtime, path). Session-scoped (same logic
    as the completeness gate, cross-fire fix 2026-07-08): corrupt/empty marker -> skip; if we know our
    own sid -> own only our own (sidless/foreign -> not ours); if no id arrived -> fall back to legacy."""
    out = []
    try:
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
        sessions = os.path.join(root, "bug-bounty-toolkit", "sessions")
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


_REAL_H_RE = re.compile(r"(?m)^\s*#{1,4}\s*H-\d")   # ### H-01 (not the template H-{NN})
_SCOUT_LEAD_RE = re.compile(r"\bH-\d{1,3}\b")        # H-NN in the scout table/header


def _ledger_thin(marker):
    """True if the ledger holds no real hypothesis/lead at all (empty template)."""
    ledger = os.path.join(os.path.dirname(marker), "hypotheses.md")
    if not os.path.exists(ledger):
        return False
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return False
    if _REAL_H_RE.search(txt):
        return False
    body = txt.split("Active Hypotheses", 1)[0]
    # WARNING 2026-07-28: examples in the template ITSELF (`Depth-Lead: {... H-03 — 3/5 ...}`) matched as
    # "a lead is already recorded" -> a fresh ledger looked non-empty and the nudge stayed silent even with
    # the correct tool name. Placeholders `{...}` are instruction, not work: strip them before searching.
    body = re.sub(r"\{[^{}]*\}", " ", body, flags=re.S)
    if _SCOUT_LEAD_RE.search(body):
        return False
    return True


def _debounced(marker, window=120):
    """True if we already nudged within the last `window` seconds (do not spam on a batch of Tasks)."""
    stamp = os.path.join(os.path.dirname(marker), ".last_ledger_nudge")
    now = time.time()
    try:
        if os.path.exists(stamp) and (now - os.path.getmtime(stamp)) < window:
            return True
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(str(int(now)))
    except Exception:
        return False
    return False


NUDGE = (
    "LEDGER-FIRST (scout-return). Task subagent(s) returned, but the active `hypotheses.md` is still "
    "an empty template (zero recorded H/leads). FIRST action NOW = Edit the ledger: each lead -> "
    "a `## Scout Fan-Out` section (table + flip Status from PENDING) + promote into Active `H-NN` "
    "(prediction + `file:line` + falsifier); weak ones -> Building Blocks. THEN — a short status in chat "
    "(1-3 lines + link to the ledger). Do NOT narrate the merge/leads as a wall of text in chat — it saturates "
    "context and loses work (the strata/impossible-cloud miss). The file = working surface, chat = not a notepad."
)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # WARNING 2026-07-28: in this harness the subagent tool is named **Agent**, not Task —
    # checked across 970 calls in all transcripts: Task=0, Agent=970. A hook keyed on "Task"
    # did not fire EVEN ONCE (went blind silently, exactly as the Workflow plan predicted).
    if (data.get("tool_name") or "") not in ("Agent", "Task", "Workflow"):
        sys.exit(0)

    current_sid = data.get("session_id") or ""
    owned = _owned_markers(current_sid)
    if not owned:
        sys.exit(0)

    _, marker = max(owned)  # most recent = current hunt
    if not _ledger_thin(marker):
        sys.exit(0)         # leads already recorded -> no noise
    if _debounced(marker):
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": NUDGE,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
