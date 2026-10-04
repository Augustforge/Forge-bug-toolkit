# -*- coding: utf-8 -*-
"""web2_antifp.py -- codified validators for the web2 anti-false-positive gates (FDE Plan 5, Task 10).

Two helpers, both backing the `web2_anti_fp` section of `submission_checklist.yaml`:
  - `valid_marker(m)`   -- Marker Discipline: a canary marker must be 8+ random characters,
    NEVER a dictionary/short word (`test`/`javascript`/`AAAA`) -- otherwise a reflected hit falsely matches
    legitimate page text.
  - `sufficient_sample(n)` -- Statistical-Sample Rule: a race/timing conclusion is legitimate only with n>=10
    repetitions (otherwise a single request = noise, not proof).

Pure functions, no network/subprocesses/time -- deterministic, safe for unit tests.
"""

_BANNED_MARKERS = ("test", "javascript", "aaaa")

_MIN_MARKER_LEN = 8
_MIN_SAMPLE_N = 10


def valid_marker(m):
    """Marker Discipline: True if `m` is a valid canary marker (8+ chars, not a dictionary word/
    not uniform), otherwise False. Fail-closed on garbage input (non-string -> False)."""
    if not isinstance(m, str):
        return False
    if len(m) < _MIN_MARKER_LEN:
        return False
    low = m.lower()
    if low in _BANNED_MARKERS:
        return False
    # uniform string (AAAAAAAA, ffffffff) -- even if long, is predictable / not statistically
    # unique -- same class of false reflected hit as a short dictionary marker.
    if len(set(low)) <= 1:
        return False
    return True


def sufficient_sample(n):
    """Statistical-Sample Rule: returns "INSUFFICIENT" for n<10 (a race/timing conclusion is unprovable),
    otherwise "SUFFICIENT". Does not raise on garbage input (fail-open to INSUFFICIENT --
    conservative, the unproven is not treated as proven)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "INSUFFICIENT"
    return "INSUFFICIENT" if n < _MIN_SAMPLE_N else "SUFFICIENT"
