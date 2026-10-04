# -*- coding: utf-8 -*-
"""Replay for error_recovery.py (Task 1, FDE Plan 5).

Proves: (1) classify_error() really classifies BY subprocess-domain stderr SIGNATURES, each
enum as a separate case, including timed_out=True and fail-open on unknown stderr; (2) recovery_action()
maps the error_class of both domains to the right action; (3) classify_http() is SEPARATE HTTP logic,
domain separation proven explicitly: 403+WAF signature in body -> WAF_BLOCK, bare 403 -> AUTH_DENIED (this is
the contract that saves Task 3/Task 4 from a false BOLA/broken-auth); (4) result_shape() computes
success/partial correctly and passes ts through as given (no generation).
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


er = _load("error_recovery", os.path.join(HERE, "error_recovery.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


classify_error = er.classify_error
classify_http = er.classify_http
recovery_action = er.recovery_action
result_shape = er.result_shape

# ── classify_error: subprocess domain, one case per enum ──────────────────────────────────
check("classify_error: '429 rate limit' -> RATE_LIMITED",
      classify_error("Error: 429 Too Many Requests", 1) == er.RATE_LIMITED)

check("classify_error: 'command not found' -> TOOL_NOT_FOUND",
      classify_error("bash: nuclei: command not found", 127) == er.TOOL_NOT_FOUND)

check("classify_error: 'No such file or directory' -> TOOL_NOT_FOUND",
      classify_error("sh: /usr/bin/foo: No such file or directory", 127) == er.TOOL_NOT_FOUND)

check("classify_error: timed_out=True -> TIMEOUT (regardless of text)",
      classify_error("", 1, timed_out=True) == er.TIMEOUT)

check("classify_error: 'timed out' in text (no flag) -> TIMEOUT",
      classify_error("curl: (28) Connection timed out after 30001 ms", 28) == er.TIMEOUT)

check("classify_error: 'Permission denied' -> PERMISSION",
      classify_error("bash: ./scan.sh: Permission denied", 126) == er.PERMISSION)

check("classify_error: 'Temporary failure in name resolution' -> NETWORK",
      classify_error("curl: (6) Could not resolve host: Temporary failure in name resolution", 6)
      == er.NETWORK)

check("classify_error: 'Connection refused' -> NETWORK",
      classify_error("curl: (7) Failed to connect: Connection refused", 7) == er.NETWORK)

check("classify_error: clean exit0, empty stderr -> OK",
      classify_error("", 0) == er.OK)

check("classify_error: unknown stderr, exit!=0 -> OK (fail-open, no guessing)",
      classify_error("some totally unrecognized garbage output", 3) == er.OK)

check("classify_error: unknown input does not crash (None stderr)",
      classify_error(None, 1) == er.OK)

# ── recovery_action: action mapping by error_class (both domains) ────────────────────────────────
check("recovery_action: RATE_LIMITED -> RETRY_BACKOFF",
      recovery_action(er.RATE_LIMITED) == er.RETRY_BACKOFF)

check("recovery_action: TIMEOUT -> RETRY_BACKOFF",
      recovery_action(er.TIMEOUT) == er.RETRY_BACKOFF)

check("recovery_action: NETWORK -> RETRY_BACKOFF",
      recovery_action(er.NETWORK) == er.RETRY_BACKOFF)

check("recovery_action: SERVER_ERR -> RETRY_BACKOFF",
      recovery_action(er.SERVER_ERR) == er.RETRY_BACKOFF)

check("recovery_action: TOOL_NOT_FOUND -> SWITCH_TOOL",
      recovery_action(er.TOOL_NOT_FOUND) == er.SWITCH_TOOL)

check("recovery_action: WAF_BLOCK -> ESCALATE",
      recovery_action(er.WAF_BLOCK) == er.ESCALATE)

check("recovery_action: AUTH_DENIED -> ESCALATE",
      recovery_action(er.AUTH_DENIED) == er.ESCALATE)

check("recovery_action: PERMISSION -> ESCALATE",
      recovery_action(er.PERMISSION) == er.ESCALATE)

check("recovery_action: OK -> NONE",
      recovery_action(er.OK) == er.NONE_ACTION)

check("recovery_action: unknown class -> NONE (fail-open)",
      recovery_action("TOTALLY_UNKNOWN_CLASS") == er.NONE_ACTION)

# ── classify_http: HTTP domain, domain separation proven explicitly ──────────────────────────────────
check("classify_http: status=429 -> RATE_LIMITED",
      classify_http(429, "") == er.RATE_LIMITED)

check("classify_http: Retry-After header (even without 429) -> RATE_LIMITED",
      classify_http(503, "", headers={"Retry-After": "30"}) == er.RATE_LIMITED)

check("classify_http: 403 + body 'mod_security triggered' -> WAF_BLOCK",
      classify_http(403, "Request blocked by mod_security rule 12345") == er.WAF_BLOCK)

check("classify_http: 403 + body 'cloudflare' -> WAF_BLOCK",
      classify_http(403, "<html>Attention Required! | Cloudflare</html>") == er.WAF_BLOCK)

check("classify_http: 403 BARE body (no WAF signature) -> AUTH_DENIED, NOT WAF_BLOCK "
      "(domain separation: this is the contract that saves Task3/Task4 from a false BOLA)",
      classify_http(403, '{"error": "forbidden"}') == er.AUTH_DENIED)

check("classify_http: 401 -> AUTH_DENIED",
      classify_http(401, '{"error": "unauthorized"}') == er.AUTH_DENIED)

check("classify_http: 500 -> SERVER_ERR",
      classify_http(500, "Internal Server Error") == er.SERVER_ERR)

check("classify_http: 502 -> SERVER_ERR (whole 5xx range)",
      classify_http(502, "Bad Gateway") == er.SERVER_ERR)

check("classify_http: 200 -> OK",
      classify_http(200, '{"ok": true}') == er.OK)

check("classify_http: garbage status does not crash -> OK (fail-open)",
      classify_http("not-a-status", "") == er.OK)

# ── result_shape: unified contract ──────────────────────────────────────────────────────────────
r1 = result_shape("partial output", "", None, timed_out=True, exec_time=30.0, ts=12345)
check("result_shape: timeout+non-empty stdout -> partial==True", r1["partial"] is True)
check("result_shape: timeout -> success==False", r1["success"] is False)
check("result_shape: ts is passed through as given (12345)", r1["ts"] == 12345)

r2 = result_shape("ok output", "", 0, timed_out=False, exec_time=1.2, ts=None)
check("result_shape: exit0, not timed_out -> success==True", r2["success"] is True)
check("result_shape: exit0 -> partial==False", r2["partial"] is False)
check("result_shape: ts=None stays None (not generated)", r2["ts"] is None)

r3 = result_shape("", "boom", 1, timed_out=False, exec_time=0.5, ts=999)
check("result_shape: exit1 -> success==False", r3["success"] is False)
check("result_shape: exit1, not timed_out -> partial==False", r3["partial"] is False)

r4 = result_shape("", "", None, timed_out=True, exec_time=30.0, ts=1)
check("result_shape: timeout WITHOUT stdout -> partial==False (partial requires non-empty stdout)",
      r4["partial"] is False)

check("result_shape: contract keys are complete",
      set(r1.keys()) == {"stdout", "stderr", "return_code", "success", "timed_out", "partial",
                          "exec_time", "ts"})

print("=== ERROR_RECOVERY REPLAY (Task 1, FDE Plan 5) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
