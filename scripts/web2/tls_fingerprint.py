# -*- coding: utf-8 -*-
"""tls_fingerprint.py — JA3/JA4 ClientHello impersonation для anti-bot-gated API (recon-skills port, 2026-08-14).

Закрывает задокументированную боль (CLAUDE.md §7: «CF часто блочит curl/WebFetch»): наш единственный
обход anti-bot был полный Playwright (медленно, тяжело). Этот слой через `curl_cffi` подделывает
TLS-fingerprint (JA3/JA4 ClientHello) реального браузера → `error_oracle.py`/`authz_diff.py` могут
пробивать CF/Akamai/DataDome-fingerprinted API на HTTP-СКОРОСТИ, без браузера.

⛔ DUAL-USE / WHITE-HAT (fail-closed, как secret_validate):
  - anti-bot bypass = dual-use. Легитимен ТОЛЬКО для доступа к IN-SCOPE авторизованному таргету
    (наша программа разрешает тестирование) — НЕ для mass-scraping / обхода чужих защит без разрешения.
  - **FAIL-CLOSED**: без `allow_live=True` И `opsec_ok=True` → НЕ шлём запрос. Это активная сетевая
    проба (fingerprint-spoof к чужому хосту) → требует явного разрешения + пройденного opsec.
  - **read-only default**: GET/HEAD. Мутирующие методы (POST/PUT/DELETE) требуют явного `allow_write=True`.
  - `curl_cffi` — LAZY (движок не хард-зависит): отсутствует → `status=unsupported` + install-hint,
    вызывающий деградирует к Playwright (fail-open в сторону «не сломать хант»).

API:
    available() -> bool
    profiles() -> list[str]                          # доступные impersonate-цели
    fetch(url, *, method="GET", impersonate="chrome120", headers=None, data=None,
          opsec_ok=False, allow_live=False, allow_write=False, timeout=15, _client=None) -> dict
"""

# curl_cffi impersonate-цели (браузер-профили TLS/JA3). Подмножество — самые ходовые.
_PROFILES = ["chrome120", "chrome116", "chrome110", "chrome107", "chrome104",
             "edge101", "edge99", "safari17_0", "safari15_5", "firefox133", "firefox117"]

_READONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _load_curl_cffi():
    """Lazy-import curl_cffi.requests. Отсутствует → None (движок деградирует, не падает)."""
    try:
        from curl_cffi import requests as _cc  # noqa
        return _cc
    except Exception:
        return None


def available():
    return _load_curl_cffi() is not None


def profiles():
    return list(_PROFILES)


def _verdict(status, **extra):
    d = {"status": status, "http_status": None, "body": None, "headers": {},
         "impersonate": None, "note": None}
    d.update(extra)
    return d


def fetch(url, *, method="GET", impersonate="chrome120", headers=None, data=None,
          opsec_ok=False, allow_live=False, allow_write=False, timeout=15, _client=None):
    """TLS-impersonated HTTP-проба. Возвращает dict (status/http_status/body/headers/impersonate).

    FAIL-CLOSED: без allow_live+opsec_ok → status='blocked_by_policy' (запрос НЕ ушёл).
    read-only default: мутирующий метод без allow_write → status='blocked_write'.
    curl_cffi нет → status='unsupported' (+install hint). `_client` — инъекция для теста."""
    m = str(method).upper()

    # ⛔ fail-closed gate — активная fingerprint-проба требует явного разрешения + opsec.
    if not (allow_live and opsec_ok):
        return _verdict("blocked_by_policy",
                        note="fail-closed: allow_live+opsec_ok обязательны (fingerprint-проба = active, dual-use)")

    # read-only guard — мутирующий метод только с явным allow_write.
    if m not in _READONLY_METHODS and not allow_write:
        return _verdict("blocked_write", note="метод %s требует allow_write=True (read-only default)" % m)

    if impersonate not in _PROFILES:
        return _verdict("bad_profile", note="unknown impersonate %r; profiles(): %s" % (impersonate, _PROFILES[:3]))

    cc = _client or _load_curl_cffi()
    if cc is None:
        return _verdict("unsupported", note="curl_cffi не установлен → деградируй к Playwright. Установка: pip install curl_cffi")

    try:
        resp = cc.request(m, url, headers=headers or {}, data=data,
                          impersonate=impersonate, timeout=timeout)
        body = getattr(resp, "text", None)
        return _verdict("ok", http_status=getattr(resp, "status_code", None),
                        body=body, headers=dict(getattr(resp, "headers", {}) or {}),
                        impersonate=impersonate)
    except Exception as ex:
        return _verdict("request_failed", note="%s: %s" % (type(ex).__name__, str(ex)[:120]),
                        impersonate=impersonate)


if __name__ == "__main__":
    import json
    import sys
    u = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    # demo: fail-closed (без opsec) — показывает форму вердикта, НЕ шлёт запрос
    print(json.dumps(fetch(u), indent=2, ensure_ascii=False))
    print("available(curl_cffi):", available())
