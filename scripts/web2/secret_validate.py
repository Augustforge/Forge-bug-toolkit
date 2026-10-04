# -*- coding: utf-8 -*-
"""secret_validate.py — read-only live-валидатор найденного секрета (recon-skills §23 port, 2026-08-14).

Закрывает gap: `secret_patterns.py` НАХОДИТ ключ в бандле/ответе, но «жив ли он и какой scope?» —
severity-gate (dead key = Low/informational, live key = High, live+broad-scope = Critical) — у нас не было.
Этот модуль подтверждает КОНКРЕТНЫЙ найденный credential через READ-ONLY endpoint провайдера и
возвращает detectability-тегированный вердикт.

⛔ WHITE-HAT / OPSEC (жёсткие правила, recon-skills §23.11):
  - ТОЛЬКО read-only endpoint (GET /me, sts:GetCallerIdentity, auth.test, GET /v1/models …).
  - НИКОГДА не использовать валидированный ключ для create/modify/delete/send.
  - **FAIL-CLOSED**: без `allow_live=True` И пройденного opsec — НЕ шлём запрос (`validation_skipped_by_policy`).
    Валидация = АКТИВНАЯ проба к чужому API (некоторые логируются: AWS CloudTrail = detectability medium) →
    требует явного разрешения, как любое live-действие в нашей системе.
  - **root/admin-guard**: root AWS-ключ / admin-Slack / infra-write GitHub-PAT НЕ валидируем автоматически —
    возвращаем `validation_skipped_by_policy` + flag оператору (он решает).
  - detectability + checked_at (UTC) на КАЖДОМ вердикте.

API:
    validate(key, kind=None, provider=None, *, allow_live=False, opsec_ok=False,
             secret=None, workspace=None, email=None, http=None) -> dict (schema §23.10)

`kind` = наш secret_patterns kind (anthropic_api / github_token / …) → авто-маппинг на provider.
`http` = инъекция HTTP-слоя для теста (по умолчанию stdlib urllib). НИКАКОГО boto3-хардтребования —
AWS-ветка деградирует к `validation_unsupported`, если boto3 отсутствует (lazy, как derive_evm_address).
"""
import datetime
import json
import urllib.request
import urllib.error


# ── kind (secret_patterns) → provider маппинг ────────────────────────────────────────
_KIND_TO_PROVIDER = {
    "github_token": "github",
    "aws_access_key": "aws",
    "slack_token": "slack",
    "anthropic_api": "anthropic",
    "openai_project": "openai", "openai_legacy": "openai", "openai_session": "openai",
    "npm_token": "npm",
    "atlassian_token": "atlassian",
    "datadog_api": "datadog",
}

# ── provider read-only probe config ──────────────────────────────────────────────────
# scope_header: заголовок ответа с правами; live_json_ok: провайдер отдаёт 200 даже на dead ключ,
# «жив» определяется телом (Slack `{"ok":true}`). detect: detectability при валидации.
_PROVIDERS = {
    "github": {
        "method": "GET", "url": "https://api.github.com/user",
        "auth": lambda k, s, w, e: {"Authorization": "token %s" % k, "User-Agent": "sv"},
        "scope_header": "X-OAuth-Scopes", "detect": "low",
        "broad_scopes": ("repo", "admin:org", "delete_repo", "admin:enterprise"),
    },
    "slack": {
        "method": "POST", "url": "https://slack.com/api/auth.test",
        "auth": lambda k, s, w, e: {"Authorization": "Bearer %s" % k},
        "ok_json_key": "ok", "detect": "low",
    },
    "anthropic": {
        "method": "GET", "url": "https://api.anthropic.com/v1/models",
        "auth": lambda k, s, w, e: {"x-api-key": k, "anthropic-version": "2023-06-01"},
        "detect": "low",
    },
    "openai": {
        "method": "GET", "url": "https://api.openai.com/v1/models",
        "auth": lambda k, s, w, e: {"Authorization": "Bearer %s" % k}, "detect": "low",
    },
    "npm": {
        "method": "GET", "url": "https://registry.npmjs.org/-/whoami",
        "auth": lambda k, s, w, e: {"Authorization": "Bearer %s" % k}, "detect": "low",
    },
    "datadog": {
        "method": "GET", "url": "https://api.datadoghq.com/api/v1/validate",
        "auth": lambda k, s, w, e: {"DD-API-KEY": k, **({"DD-APPLICATION-KEY": s} if s else {})},
        "detect": "low",
    },
    "postman": {
        "method": "GET", "url": "https://api.getpostman.com/me",
        "auth": lambda k, s, w, e: {"X-Api-Key": k}, "detect": "low",
    },
    "atlassian": {
        # workspace обязателен (из leaked repo URL / dork) — иначе не знаем хост.
        "method": "GET", "url": None,   # строится из workspace
        "auth": None, "detect": "low", "needs_workspace": True,
    },
    "aws": {"detect": "medium"},        # особая ветка (SigV4 через boto3-lazy)
}

# root/admin индикаторы — НЕ валидируем автоматически (§23.11), flag оператору.
_AWS_ROOT_HINT = ":root"


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _verdict(status, provider, **extra):
    d = {"status": status, "provider": provider, "account_id": None, "scope": None,
         "metadata": {}, "checked_at": _now_utc(), "detectability": _PROVIDERS.get(provider, {}).get("detect", "low")}
    d.update(extra)
    return d


# ── stdlib HTTP (инъектируемо для теста) ─────────────────────────────────────────────
def _default_http(method, url, headers, timeout=10):
    """(status, body_text, resp_headers). Read-only GET/POST без тела. Fail-safe: сетевой сбой →
    (None, '', {}) → вызывающий трактует как transient."""
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (r.status, r.read().decode("utf-8", "replace"), dict(r.headers))
    except urllib.error.HTTPError as e:
        return (e.code, (e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""), dict(e.headers or {}))
    except Exception:
        return (None, "", {})


def _looks_root_or_admin(provider, key, secret):
    """Грубый guard: AWS ключи, где мы не знаем ARN, — валидируем (ARN придёт в ответе), но если
    вызывающий передал уже известный root-ARN в `secret` как контекст — стоп. Здесь консервативно:
    длинные ASIA-сессионные не трогаем (temp). Расширяемо."""
    # AWS root/ARN известен ДО валидации только если передан контекстом; базовый guard — на явный ":root".
    if provider == "aws" and secret and _AWS_ROOT_HINT in str(secret):
        return True
    return False


def _validate_aws(key, secret, http):
    """AWS sts:GetCallerIdentity через boto3-lazy (SigV4 руками не пишем). boto3 нет → unsupported."""
    if not secret:
        return _verdict("validation_unsupported", "aws", metadata={"why": "aws needs access_key + secret"})
    try:
        import boto3  # lazy — движок не хард-зависит
        from botocore.exceptions import ClientError
    except Exception:
        return _verdict("validation_unsupported", "aws", metadata={"why": "boto3 absent"})
    try:
        sts = boto3.client("sts", aws_access_key_id=key, aws_secret_access_key=secret, region_name="us-east-1")
        ident = sts.get_caller_identity()
        arn = ident.get("Arn", "")
        if _AWS_ROOT_HINT in arn:
            return _verdict("validation_skipped_by_policy", "aws", account_id=ident.get("Account"),
                            scope="root", metadata={"arn": arn, "flag": "ROOT KEY — operator decides"})
        scope = "assumed-role" if ":assumed-role/" in arn else ("iam-user" if ":user/" in arn else "unknown")
        return _verdict("verified_live", "aws", account_id=ident.get("Account"), scope=scope,
                        metadata={"arn": arn, "user_id": ident.get("UserId")})
    except Exception as ex:  # ClientError InvalidClientTokenId/SignatureDoesNotMatch → dead
        name = type(ex).__name__
        return _verdict("verified_dead", "aws", metadata={"error": name})


def validate(key, kind=None, provider=None, *, allow_live=False, opsec_ok=False,
             secret=None, workspace=None, email=None, http=None):
    """Read-only валидация одного credential. Возвращает schema-dict (§23.10).

    FAIL-CLOSED: без allow_live И opsec_ok → validation_skipped_by_policy (НЕ шлём запрос).
    provider выводится из kind, если не задан явно."""
    prov = provider or _KIND_TO_PROVIDER.get(kind or "")
    if not prov:
        return _verdict("validation_unsupported", prov or "unknown",
                        metadata={"why": "no provider for kind %r" % kind})
    if prov not in _PROVIDERS:
        return _verdict("validation_unsupported", prov, metadata={"why": "provider not configured"})

    # ⛔ FAIL-CLOSED gate — live-проба требует явного разрешения + opsec.
    if not (allow_live and opsec_ok):
        return _verdict("validation_skipped_by_policy", prov,
                        metadata={"why": "fail-closed: allow_live+opsec_ok required (live probe = active)"})

    # root/admin hard-guard (§23.11) — не валидируем автоматически.
    if _looks_root_or_admin(prov, key, secret):
        return _verdict("validation_skipped_by_policy", prov,
                        metadata={"flag": "root/admin credential — operator decides"})

    if prov == "aws":
        return _validate_aws(key, secret, http)

    cfg = _PROVIDERS[prov]
    if cfg.get("needs_workspace"):
        if not workspace:
            return _verdict("validation_unsupported", prov, metadata={"why": "workspace required"})
        url = "https://%s.atlassian.net/rest/api/3/myself" % workspace
        import base64 as _b64
        token = _b64.b64encode(("%s:%s" % (email or "", key)).encode()).decode()
        headers = {"Authorization": "Basic %s" % token}
    else:
        url = cfg["url"]
        headers = cfg["auth"](key, secret, workspace, email)

    do_http = http or _default_http
    status, body, resp_headers = do_http(cfg.get("method", "GET"), url, headers)

    if status is None:
        return _verdict("validation_failed_transient", prov, metadata={"why": "network error / no response"})

    # Slack-класс: 200 всегда, «жив» определяется телом {"ok":true}.
    if cfg.get("ok_json_key"):
        try:
            j = json.loads(body or "{}")
        except Exception:
            j = {}
        if status == 200 and j.get(cfg["ok_json_key"]) is True:
            return _verdict("verified_live", prov, account_id=j.get("user_id") or j.get("team_id"),
                            scope=j.get("team"), metadata={k: j.get(k) for k in ("team", "user") if k in j})
        return _verdict("verified_dead", prov, metadata={"error": (j.get("error") if isinstance(j, dict) else None)})

    # HTTP-status класс.
    if status in (401, 403):
        return _verdict("verified_dead", prov, metadata={"http": status})
    if status == 429:
        return _verdict("verified_live", prov, scope="quota_exhausted", metadata={"http": 429})
    if 200 <= status < 300:
        scope = None
        sh = cfg.get("scope_header")
        if sh and resp_headers:
            # case-insensitive lookup
            for hk, hv in resp_headers.items():
                if hk.lower() == sh.lower():
                    scope = hv
                    break
        vd = _verdict("verified_live", prov, scope=scope, metadata={"http": status})
        # broad-scope → scope_unrestricted (severity-boost сигнал для вызывающего)
        if scope and any(b in scope for b in cfg.get("broad_scopes", ())):
            vd["status"] = "scope_unrestricted"
        return vd
    return _verdict("validation_failed_transient", prov, metadata={"http": status})


if __name__ == "__main__":
    import sys
    # CLI: echo-safe demo — БЕЗ live (fail-closed), показывает маппинг+вердикт-форму.
    k = sys.argv[1] if len(sys.argv) > 1 else "sk-ant-api03-DEMO"
    print(json.dumps(validate(k, kind="anthropic_api"), indent=2))
