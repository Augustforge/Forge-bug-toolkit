# -*- coding: utf-8 -*-
"""error_recovery.py -- Shared-Core error classifier + unified result-shape (FDE Plan 5, Task 1).

Two DIFFERENT domains, two SEPARATE functions -- do not mix them up:
  - `classify_error()`  -- subprocess domain: stderr/exit_code of external tools (recon.sh/scan.sh).
  - `classify_http()`   -- in-process HTTP domain: status/body/headers of a response (authz_diff, requests/httpx).
    WAF_BLOCK != AUTH_DENIED: a 403 by itself does NOT mean WAF -- a WAF signature in the body is needed, otherwise it is
    an auth-403 (and conversely, a mistake here is a false BOLA/broken-auth in the Task 3/Task 4 consumers).

`recovery_action()` accepts the enum of EITHER classifier and says what to do next.
`result_shape()` -- the unified contract of an execution result (for subprocess runners).

Fail-open everywhere: unknown/garbage input -> a safe default (`OK` / `NONE`), never crashes.
Determinism: no network, no time.time()/Date.now() inside -- `ts` in result_shape comes
from OUTSIDE and is simply passed through (None stays None, not generated).
"""

# ── error_recovery: subprocess-domain enum ──────────────────────────────────────────────────────
TIMEOUT = "TIMEOUT"
PERMISSION = "PERMISSION"
RATE_LIMITED = "RATE_LIMITED"
TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
NETWORK = "NETWORK"
OK = "OK"

# ── classify_http: HTTP-domain enum ──────────────────────────────────────────────────────────────
WAF_BLOCK = "WAF_BLOCK"
AUTH_DENIED = "AUTH_DENIED"
SERVER_ERR = "SERVER_ERR"

# ── recovery_action enum ────────────────────────────────────────────────────────────────────────
RETRY_BACKOFF = "RETRY_BACKOFF"
SWITCH_TOOL = "SWITCH_TOOL"
ESCALATE = "ESCALATE"
NONE_ACTION = "NONE"

_RATE_LIMIT_SIGNATURES = ("429", "too many requests", "retry-after")
_TIMEOUT_SIGNATURES = ("timeout", "timed out")
_TOOL_NOT_FOUND_SIGNATURES = ("command not found", "no such file")
_NETWORK_SIGNATURES = (
    "connection refused",
    "name or service not known",
    "temporary failure in name resolution",
    "network is unreachable",
    "could not resolve host",
    "dns",
)
_PERMISSION_SIGNATURES = ("permission denied",)

_WAF_BODY_SIGNATURES = (
    "mod_security",
    "modsecurity",
    "cloudflare",
    "access denied",
    "request blocked",
    "captcha",
    "challenge",
)


def classify_error(stderr, exit_code, timed_out=False):
    """Subprocess domain: classifies an external tool error by stderr/exit_code/timed_out.

    Returns one of: TIMEOUT / PERMISSION / RATE_LIMITED / TOOL_NOT_FOUND / NETWORK / OK.
    Fail-open: unknown stderr with exit_code!=0 and no signatures -> OK (we cannot classify,
    but we also do not crash/escalate on no grounds).
    """
    try:
        if timed_out:
            return TIMEOUT

        text = (stderr or "")
        text_lower = text.lower()

        if any(sig in text_lower for sig in _TIMEOUT_SIGNATURES):
            return TIMEOUT

        if any(sig in text_lower for sig in _RATE_LIMIT_SIGNATURES):
            return RATE_LIMITED

        if any(sig in text_lower for sig in _TOOL_NOT_FOUND_SIGNATURES):
            return TOOL_NOT_FOUND

        if any(sig in text_lower for sig in _NETWORK_SIGNATURES):
            return NETWORK

        if any(sig in text_lower for sig in _PERMISSION_SIGNATURES):
            return PERMISSION

        if exit_code == 0:
            return OK

        # exit!=0 but no signature fired -- fail-open, no guessing.
        return OK
    except Exception:
        return OK


def classify_http(status, body="", headers=None):
    """HTTP domain: classifies an in-process HTTP response (authz_diff / requests / httpx).

    Returns one of: RATE_LIMITED / WAF_BLOCK / AUTH_DENIED / SERVER_ERR / OK.
    WAF_BLOCK requires status==403 AND a WAF signature in the body -- a bare 403 is AUTH_DENIED.
    Fail-open: non-int status / garbage headers -> OK.
    """
    try:
        status = int(status)
        body_lower = (body or "").lower()
        headers = headers or {}
        # case-insensitive header lookup without external dependencies
        headers_lower = {}
        try:
            headers_lower = {str(k).lower(): v for k, v in headers.items()}
        except Exception:
            headers_lower = {}

        if status == 429 or "retry-after" in headers_lower:
            return RATE_LIMITED

        if status == 403 and any(sig in body_lower for sig in _WAF_BODY_SIGNATURES):
            return WAF_BLOCK

        if status in (401, 403):
            return AUTH_DENIED

        if 500 <= status < 600:
            return SERVER_ERR

        return OK
    except Exception:
        return OK


_RETRY_BACKOFF_CLASSES = (TIMEOUT, RATE_LIMITED, NETWORK, SERVER_ERR)
_SWITCH_TOOL_CLASSES = (TOOL_NOT_FOUND,)
_ESCALATE_CLASSES = (PERMISSION, WAF_BLOCK, AUTH_DENIED)


def recovery_action(error_class):
    """Accepts an enum from classify_error() OR classify_http(), returns the recommended action.

    RETRY_BACKOFF (TIMEOUT/RATE_LIMITED/NETWORK/SERVER_ERR) / SWITCH_TOOL (TOOL_NOT_FOUND) /
    ESCALATE (PERMISSION/WAF_BLOCK/AUTH_DENIED) / NONE (OK or unknown class -- fail-open).
    """
    try:
        if error_class in _RETRY_BACKOFF_CLASSES:
            return RETRY_BACKOFF
        if error_class in _SWITCH_TOOL_CLASSES:
            return SWITCH_TOOL
        if error_class in _ESCALATE_CLASSES:
            return ESCALATE
        return NONE_ACTION
    except Exception:
        return NONE_ACTION


def result_shape(stdout, stderr, return_code, timed_out=False, exec_time=0.0, ts=None):
    """Unified result contract for subprocess runners.

    {stdout, stderr, return_code, success, timed_out, partial, exec_time, ts}
    success = (return_code==0 and not timed_out); partial = (timed_out and bool(stdout)).
    `ts` is put AS PASSED -- None stays None, the function generates nothing itself
    (determinism: no time.time() inside).

    🔴 TOOLKIT-CONTRACT (FDE Plan 6, §27 R12 -- DOCUMENTED, not rewritten): this is the CANONICAL
    result form of ANY subprocess runner in the toolkit (scout scripts, detectors, harnesses,
    wrappers around `subprocess.run`/`Bash`). Any script that parses the output of ANOTHER toolkit
    script (a scout subagent calling scanner.py and reading its stdout/exit_code; a merge step
    comparing the results of several runners) MUST expect EXACTLY these 8 fields -- not
    invent its own ad-hoc dict {ok, out, err} for each new script. Uniformity here is
    the prerequisite for `classify_error()`/`recovery_action()` (same file) to work on ANY
    result without a per-caller adapter. Entry-point reference for the scout contract:
    `sessions/_methodology/scout_fanout.md` ("Scout -- subagent contract").
    """
    success = (return_code == 0 and not timed_out)
    partial = bool(timed_out and stdout)
    return {
        "stdout": stdout,
        "stderr": stderr,
        "return_code": return_code,
        "success": success,
        "timed_out": timed_out,
        "partial": partial,
        "exec_time": exec_time,
        "ts": ts,
    }
