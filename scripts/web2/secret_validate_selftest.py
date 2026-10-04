# -*- coding: utf-8 -*-
"""Selftest для secret_validate.py — БЕЗ реальных сетевых запросов (HTTP-слой инъектируется моком).
Доказывает: fail-closed (без allow_live молчит), kind→provider маппинг, live/dead/scope-парсинг,
broad-scope→scope_unrestricted, Slack ok-json класс, AWS root-guard, schema-полнота, detectability-тег."""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import secret_validate as sv  # noqa: E402

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def mock_http(status, body="", headers=None):
    """Фабрика HTTP-мока: возвращает (method,url,hdrs)->(status,body,resp_headers)."""
    return lambda method, url, hdrs, timeout=10: (status, body, headers or {})


SCHEMA_KEYS = {"status", "provider", "account_id", "scope", "metadata", "checked_at", "detectability"}

# 1) FAIL-CLOSED: без allow_live/opsec_ok → skipped, БЕЗ вызова http.
called = {"n": 0}
def spy(*a, **k):
    called["n"] += 1
    return (200, "{}", {})
r1 = sv.validate("sk-ant-api03-x", kind="anthropic_api", http=spy)  # allow_live/opsec по умолчанию False
check("1 FAIL-CLOSED: без allow_live+opsec → validation_skipped_by_policy",
      r1["status"] == "validation_skipped_by_policy", r1["status"])
check("1 FAIL-CLOSED: http НЕ вызван (live-проба не ушла)", called["n"] == 0, "calls=%d" % called["n"])

# 2) kind→provider маппинг
check("2 mapping: anthropic_api → anthropic", sv._KIND_TO_PROVIDER.get("anthropic_api") == "anthropic")
check("2 mapping: openai_legacy → openai", sv._KIND_TO_PROVIDER.get("openai_legacy") == "openai")

# 3) LIVE github 200 + scope header → verified_live + scope
r3 = sv.validate("ghp_x", kind="github_token", allow_live=True, opsec_ok=True,
                 http=mock_http(200, '{"login":"u"}', {"X-OAuth-Scopes": "read:user, gist"}))
check("3 LIVE github 200 → verified_live", r3["status"] == "verified_live", r3["status"])
check("3 LIVE github scope извлечён из заголовка", r3["scope"] == "read:user, gist", repr(r3["scope"]))

# 4) BROAD scope (repo) → scope_unrestricted (severity-boost сигнал)
r4 = sv.validate("ghp_x", kind="github_token", allow_live=True, opsec_ok=True,
                 http=mock_http(200, "{}", {"X-OAuth-Scopes": "repo, admin:org"}))
check("4 BROAD scope repo/admin:org → scope_unrestricted", r4["status"] == "scope_unrestricted", r4["status"])

# 5) DEAD 401 → verified_dead
r5 = sv.validate("ghp_x", kind="github_token", allow_live=True, opsec_ok=True, http=mock_http(401, "unauthorized"))
check("5 DEAD 401 → verified_dead", r5["status"] == "verified_dead", r5["status"])

# 6) Slack ok-json класс: {"ok":true} → live; {"ok":false} → dead
r6a = sv.validate("xoxb-x", kind="slack_token", allow_live=True, opsec_ok=True,
                  http=mock_http(200, '{"ok":true,"team":"T","user_id":"U1"}'))
check("6 Slack ok:true → verified_live", r6a["status"] == "verified_live", r6a["status"])
r6b = sv.validate("xoxb-x", kind="slack_token", allow_live=True, opsec_ok=True,
                  http=mock_http(200, '{"ok":false,"error":"invalid_auth"}'))
check("6 Slack ok:false → verified_dead", r6b["status"] == "verified_dead", r6b["status"])

# 7) Anthropic 200 → verified_live
r7 = sv.validate("sk-ant-api03-x", kind="anthropic_api", allow_live=True, opsec_ok=True,
                 http=mock_http(200, '{"data":[]}'))
check("7 Anthropic 200 → verified_live", r7["status"] == "verified_live", r7["status"])

# 8) AWS root-guard: secret с ':root' контекстом → skipped (не валидируем автоматически)
r8 = sv.validate("AKIA...", kind="aws_access_key", allow_live=True, opsec_ok=True,
                 secret="arn:aws:iam::123:root")
check("8 AWS root-hint → validation_skipped_by_policy (operator decides)",
      r8["status"] == "validation_skipped_by_policy", r8["status"])

# 9) 429 → live (quota exhausted)
r9 = sv.validate("sk-x", kind="openai_legacy", allow_live=True, opsec_ok=True, http=mock_http(429, ""))
check("9 OpenAI 429 → verified_live (quota_exhausted)",
      r9["status"] == "verified_live" and r9["scope"] == "quota_exhausted", r9["status"])

# 10) unknown kind → validation_unsupported
r10 = sv.validate("x", kind="nonexistent_kind", allow_live=True, opsec_ok=True)
check("10 unknown kind → validation_unsupported", r10["status"] == "validation_unsupported", r10["status"])

# 11) transient: http вернул None → validation_failed_transient
r11 = sv.validate("ghp_x", kind="github_token", allow_live=True, opsec_ok=True, http=mock_http(None))
check("11 network None → validation_failed_transient", r11["status"] == "validation_failed_transient", r11["status"])

# 12) SCHEMA-полнота + detectability-тег на КАЖДОМ вердикте
all_verdicts = [r1, r3, r4, r5, r6a, r6b, r7, r8, r9, r10, r11]
check("12 SCHEMA: все вердикты несут полный набор полей",
      all(SCHEMA_KEYS.issubset(v.keys()) for v in all_verdicts))
check("12 detectability-тег присутствует везде",
      all(v.get("detectability") in ("low", "medium", "high") for v in all_verdicts))
check("12 checked_at (UTC ISO) присутствует везде", all(v.get("checked_at") for v in all_verdicts))

# 13) atlassian без workspace → unsupported (needs_workspace)
r13 = sv.validate("ATATT...", kind="atlassian_token", allow_live=True, opsec_ok=True)
check("13 atlassian без workspace → validation_unsupported", r13["status"] == "validation_unsupported", r13["status"])

print("=== SECRET_VALIDATE SELFTEST (read-only, fail-closed, mocked HTTP) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d проверок зелёные" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
