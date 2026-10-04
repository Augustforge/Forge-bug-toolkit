# -*- coding: utf-8 -*-
"""Selftest для tls_fingerprint.py — fail-closed, read-only guard, profile-guard, unsupported-degradation,
ok-путь через мок curl_cffi-клиента (БЕЗ реальных сетевых запросов)."""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tls_fingerprint as tf  # noqa: E402

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


class _Resp:
    def __init__(self, code, text, headers):
        self.status_code, self.text, self.headers = code, text, headers

class _MockClient:
    """Имитация curl_cffi.requests: .request(method,url,...) → _Resp. Пишет last-call для проверки."""
    def __init__(self):
        self.calls = []
    def request(self, method, url, headers=None, data=None, impersonate=None, timeout=None):
        self.calls.append({"method": method, "url": url, "impersonate": impersonate})
        return _Resp(200, "OK-BODY", {"server": "cloudflare"})

# 1) FAIL-CLOSED: без allow_live+opsec → blocked_by_policy, клиент НЕ вызван
mc = _MockClient()
r1 = tf.fetch("https://cf-target/api", opsec_ok=False, allow_live=False, _client=mc)
check("1 FAIL-CLOSED: без opsec → blocked_by_policy", r1["status"] == "blocked_by_policy", r1["status"])
check("1 FAIL-CLOSED: клиент НЕ вызван (запрос не ушёл)", len(mc.calls) == 0)

# 2) read-only guard: POST без allow_write → blocked_write
r2 = tf.fetch("https://t/api", method="POST", opsec_ok=True, allow_live=True, _client=_MockClient())
check("2 read-only: POST без allow_write → blocked_write", r2["status"] == "blocked_write", r2["status"])

# 3) POST с allow_write → проходит гейт (ok через мок)
mc3 = _MockClient()
r3 = tf.fetch("https://t/api", method="POST", opsec_ok=True, allow_live=True, allow_write=True, _client=mc3)
check("3 POST + allow_write → ok", r3["status"] == "ok" and mc3.calls[0]["method"] == "POST", r3["status"])

# 4) bad profile → bad_profile (до сетевого вызова)
mc4 = _MockClient()
r4 = tf.fetch("https://t", impersonate="netscape2000", opsec_ok=True, allow_live=True, _client=mc4)
check("4 bad profile → bad_profile", r4["status"] == "bad_profile" and len(mc4.calls) == 0, r4["status"])

# 5) ok-путь (GET): мок вернул 200 + body + headers + impersonate проброшен
mc5 = _MockClient()
r5 = tf.fetch("https://cf/api", impersonate="chrome120", opsec_ok=True, allow_live=True, _client=mc5)
check("5 ok: http_status 200 + body", r5["status"] == "ok" and r5["http_status"] == 200 and r5["body"] == "OK-BODY")
check("5 ok: impersonate проброшен в клиент", mc5.calls[0]["impersonate"] == "chrome120")
check("5 ok: headers захвачены", r5["headers"].get("server") == "cloudflare")

# 6) unsupported: curl_cffi отсутствует (подменяем _load на None) + _client=None → unsupported
_orig = tf._load_curl_cffi
try:
    tf._load_curl_cffi = lambda: None
    r6 = tf.fetch("https://t", opsec_ok=True, allow_live=True, _client=None)
    check("6 unsupported: нет curl_cffi → status unsupported + install-hint",
          r6["status"] == "unsupported" and "curl_cffi" in (r6["note"] or ""), r6["status"])
finally:
    tf._load_curl_cffi = _orig

# 7) profiles() непустой список
check("7 profiles(): непустой список impersonate-целей", isinstance(tf.profiles(), list) and len(tf.profiles()) >= 5)

# 8) request_failed: клиент бросает → graceful
class _Boom:
    def request(self, *a, **k):
        raise RuntimeError("tls handshake failed")
r8 = tf.fetch("https://t", opsec_ok=True, allow_live=True, _client=_Boom())
check("8 request_failed: исключение клиента → graceful status", r8["status"] == "request_failed", r8["status"])

print("=== TLS_FINGERPRINT SELFTEST (dual-use, fail-closed, mocked) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + str(detail)) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d проверок зелёные" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
