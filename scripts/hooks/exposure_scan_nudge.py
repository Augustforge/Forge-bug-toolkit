#!/usr/bin/env python3
"""PreToolUse hook — ad-hoc secret-grep -> nudge toward the SYSTEMIC producer secret_exposure_scanner.py.

Purpose: close a miss (jetinfosystems_tab_1 2026-08-14) — during a hunt the hunter reaches for the familiar
ad-hoc `grep apikey|secret|token` over a bundle/source-map INSTEAD of the systemic detector, and only remembers
the producer after a nudge from the operator. The Stop gate `active_exposure_scan_skipped` holds the exit, but
catches it only ON EXIT, not at the MOMENT of working with the bundle. Precedent for the form —
model_first_nudge (a soft PreToolUse reminder at the action boundary, not a block).

Fire iff (a) ad-hoc secret-grep: Bash/PowerShell with a grep tool + a secret token, OR a Grep tool with
            a secret pattern (and it is NOT a call to the producer itself) AND
        (b) a hunt is running IN THIS session (own fresh `.hunt_active`, session-scoped) AND
        (c) not debounced (30 min window).
Silence iff no own active hunt / foreign session / a call to the producer / not a secret grep / already nudged.
Fail-open: any error -> exit 0 with no output (never break the work).

Why not web-only (unlike safeguard): a hardcoded/leaked key is the cheapest Critical in
ANY profile (Swan class Cat 4.10); the producer with its decode layer/PII/git-history is useful in both web2 and
contract deephunt (deephunt.md calls it). The trigger = the ad-hoc habit, not the target type.
"""
import sys
import os
import re
import json
import glob
import time


def _read_marker(marker_path):
    """(valid, sid). valid=False if the marker is empty/corrupt."""
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
    """The sessions/ directory. ENV BBT_SESSIONS_DIR overrides it (replay-test isolation)."""
    env = os.environ.get("BBT_SESSIONS_DIR")
    if env:
        return env
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(root, "sessions")


def _owned_markers(current_sid):
    """Fresh (<24h) .hunt_active markers for THIS session — (mtime, path). Same session-scoped logic."""
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


def _debounced(marker, window=1800, stampname=".last_exposure_nudge"):
    """True if we already nudged within the last `window` seconds (do not spam on a batch of grep calls)."""
    stamp = os.path.join(os.path.dirname(marker), stampname)
    now = time.time()
    try:
        if os.path.exists(stamp) and (now - os.path.getmtime(stamp)) < window:
            return True
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(str(int(now)))
    except Exception:
        return False
    return False


# grep tool in a shell command (bash/pwsh)
_GREP_TOOL_RE = re.compile(r"\b(?:grep|egrep|fgrep|rg|ripgrep|ag|findstr|select-string|sls)\b", re.I)
# secret token (what the hunter searches for ad-hoc). Matches the producer's classes (api-key/token/private-key/
# cloud prefixes). Specific enough not to catch an ordinary code grep.
_SECRET_TOKEN_RE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|secret|token|passw(?:or)?d|bearer|"
    r"private[_-]?key|access[_-]?key|client[_-]?secret|aws_?(?:access|secret)|"
    r"BEGIN[ _]?(?:RSA|EC|DSA|OPENSSH|PRIVATE)|xox[baprs]-|\bsk-|\bghp_|\bAKIA)")
# a call to the producer ITSELF / our harnesses — this is NOT ad-hoc, do not nudge.
_PRODUCER_RE = re.compile(
    r"secret_exposure_scanner|secret_validate|web2_exposure|exposure_scan|"
    r"runtime_harness|capture_exposure|secret_patterns", re.I)


def _is_adhoc_secret_grep(tool, data):
    """True iff an ad-hoc secret grep (Bash/PowerShell grep+secret OR a Grep tool with a secret pattern),
    and it is NOT a call to the producer."""
    tin = data.get("tool_input") or {}
    if (tool or "") in ("Bash", "PowerShell"):
        cmd = str(tin.get("command") or "")
        if _PRODUCER_RE.search(cmd):
            return False
        return bool(_GREP_TOOL_RE.search(cmd) and _SECRET_TOKEN_RE.search(cmd))
    if (tool or "") == "Grep":
        pat = str(tin.get("pattern") or "")
        if _PRODUCER_RE.search(pat):
            return False
        return bool(_SECRET_TOKEN_RE.search(pat))
    return False


EXPOSURE_NUDGE = (
    "🔎 EXPOSURE-SCAN — you are searching for secrets with an ad-hoc grep. Use the SYSTEMIC producer instead: "
    "`py -3 -X utf8 scripts/_methodology/secret_exposure_scanner.py --target "
    "<clone / bundle-dir> --session-dir <sessions/{slug}> [--git-history]`. It catches what a bare grep "
    "MISSES: encoded keys (base64/hex decode layer), PII, financial data, source-maps, "
    "git-history; each secret/key -> H-NN (offline-derive + keypair->role correlation for severity). "
    "Live front (web2/dapphunt, AFTER opsec_preflight fail-closed) -> `web2_exposure.capture_exposure` / "
    "`runtime_harness.capture_exposure` + the line `EXPOSURE-SCAN: N secrets / ... [runtime]`. ⚠️ Write the "
    "`EXPOSURE-SCAN:` line into the ledger ONLY from the producer — an ad-hoc grep result does NOT clear the gate "
    "(the `exposure_scan.md` artifact is checked). Spec: `scripts/_methodology/secret_exposure_scanner.py`."
)


def _emit(text):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": text,
        }
    }))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name") or ""
    current_sid = data.get("session_id") or ""

    if not _is_adhoc_secret_grep(tool, data):
        sys.exit(0)
    owned = _owned_markers(current_sid)
    if not owned:
        sys.exit(0)
    _, marker = max(owned)

    try:
        if _debounced(marker):
            sys.exit(0)
        _emit(EXPOSURE_NUDGE)
    except Exception:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
