# -*- coding: utf-8 -*-
"""error_oracle.py -- input->sink ось web2-профиля /hunt (FDE План 5, Task 4).

Дополняет `authz_diff.py` (роль-к-роли matrix): этот модуль щупает ОДИН вход (payload в поле формы /
query / body) против ОДНОГО sink'а -- сравнивает "чистый" baseline-ответ с ответом на инъекцию, ловит
CORS/security-header просчёты и вытягивает имена полей/таблиц из verbose ORM/validation-ошибок.

🔴 `"input-sink"` -- ОСЬ этой модели (dclass, который присваивается результату `blind_diff`), НЕ
канонический `differential_observation.Probe.KIND` (`Probe.KINDS` перечисляет `signature-integrity` /
`object-authz` / `function-authz` / `tenant-isolation` / `clone-parity` / `broken-auth` -- authz-ось,
не input-ось). Примитив `differential()` терпит неизвестный `kind` by design (fail-open: он просто
получает дефолтные `attack_path_hint`/`severity_seed`, см. `_DEFAULT_HINT`/`_DEFAULT_SEVERITY` там же)
-- именно на этом контракте построен `blind_diff` ниже, а не на попытке впихнуть input-sink в чужой enum.

Four functions (Produces):
  blind_diff(baseline_resp, payload_resp, probe="sqli") -> Divergence|None
  cors_capture(response_headers, origin_reflected) -> Divergence|None
  headers_capture(host_responses) -> list[Divergence]
  schema_hint_leak(error_body) -> dict{fields, tables}

Body-Diff Rule (Global Constraint): сравнивать НОРМАЛИЗОВАННОЕ тело (CSRF-токены/timestamps/nonces/
UUID вырезаны regex'ом на `<NORM>`), иначе baseline и payload-ответ разойдутся на шуме (разные CSRF-
токены в каждом ответе), а не на реальном инъекц-сигнале -- ложный Divergence на КАЖДОМ прогоне.

Дизайн `blind_diff` (суждение имплементера, нет верного значения в брифе -- см. отчёт): сравнение идёт
НЕ по сырому телу/статусу напрямую (это дало бы Divergence на любом безобидном различии ответа -- два
разных input естественно дают разный output), а по ЧЕТЫРЁМ derived-сигналам (error_sig / len_spike /
timing_spike / status_spike), уже посчитанным ИЗ нормализованного тела -- baseline-сторона диффа всегда
несёт канонический "нет сигнала" (None/False), payload-сторона несёт измеренные значения. `semantic_diff`
(через `differential()`) диффит эти fields, а не raw content -- это и есть "выше шума" фильтр из брифа.
Raw attacker-controlled текст: `blind_diff`/`headers_capture` никогда не кладут сырое тело ответа в
`Divergence.evidence` (только имена сработавших сигналов + НАШИ статические сигнатуры типа "sql syntax",
не сырой ответ) -- эти две функции guard'а не требуют (нечего сканировать -- attacker-текст никогда не
покидает функцию). 🔴 Два места, где attacker-controlled текст РЕАЛЬНО долетает до `evidence`/возврата,
и оба гонят его через guard fail-CLOSED: `schema_hint_leak` (field/table-имена ИЗ error body -- Produces
#4) и `cors_capture` (reflected `Access-Control-Allow-Origin`, когда `origin_reflected=True` -- сервер
отразил НАШ выбранный Origin обратно, значит значение полностью under attacker control).

WAF short-circuit: `classify_http(status, body, headers)` == `WAF_BLOCK` на payload_resp -> `blind_diff`
возвращает `None` ДО любого diff'а (403+WAF-сигнатура -- это WAF, не инъекция; не путать с чистым
403/401 authz-ответом, тот остаётся `AUTH_DENIED` и в этот early-return не попадает).

Fail-open everywhere (кроме guard-вызовов в `schema_hint_leak`/`cors_capture` -- см. комментарии там):
любая ошибка -> безопасный дефолт (`None` / `[]` / `{"fields": [], "tables": []}`), никогда не крашимся
наружу.
"""

import os
import re
import importlib.util


_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)                                     # .../bug-bounty-toolkit/scripts
_METHOD_DIR = os.path.join(_SCRIPTS_DIR, "_methodology")
_RUNTIME_HARNESS_PATH = os.path.join(_SCRIPTS_DIR, "dapphunt", "wallet_test", "runtime_harness.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_dobs = _load("differential_observation", os.path.join(_METHOD_DIR, "differential_observation.py"))
_err_rec = _load("error_recovery", os.path.join(_METHOD_DIR, "error_recovery.py"))
_pi_guard = _load("pi_guard_lib", os.path.join(_METHOD_DIR, "pi_guard_lib.py"))
_rh = _load("runtime_harness", _RUNTIME_HARNESS_PATH)

Divergence = _dobs.Divergence
Context = _dobs.Context
Probe = _dobs.Probe
Response = _dobs.Response
StaticDriver = _dobs.StaticDriver
differential = _dobs.differential

classify_http = _err_rec.classify_http
WAF_BLOCK = _err_rec.WAF_BLOCK


def _get(resp, key, default=None):
    """`resp` -- dict|object (fixture-friendly: тесты используют dict, живой driver может отдать
    объект-обёртку). Fail-open: битый доступ -> default."""
    try:
        if isinstance(resp, dict):
            return resp.get(key, default)
        return getattr(resp, key, default)
    except Exception:
        return default


def _guard_scan(text):
    """Fail-CLOSED guard wrapper (тот же паттерн, что `authz_diff._guard_scan` /
    `runtime_harness._guard_scan_value`): `True` -> blocked. Единственное fail-CLOSED исключение из
    общего fail-open этого модуля -- сбой сканера трактуем как "заблокировано", НЕ пропускаем сырой
    attacker-controlled текст как есть. Используется в `schema_hint_leak` и `cors_capture` -- двух
    местах модуля, где attacker-controlled текст реально долетает до `evidence`/возврата."""
    try:
        verdict = _pi_guard.scan(text)
        return bool(getattr(verdict, "blocked", False))
    except Exception:
        return True


# ---------------------------------------------------------------------------
# blind_diff -- SQLi/SSTI blind-diff (baseline vs injected)
# ---------------------------------------------------------------------------

# Body-Diff Rule: CSRF-токены / timestamps / nonces / UUID -> "<NORM>" ДО сравнения.
_NOISE_PATTERNS = (
    re.compile(r'"?csrf[-_]?token"?\s*[:=]\s*"?[\w\-.]+"?', re.I),
    re.compile(r'"?(xsrf[-_]?token|authenticity_token|_token)"?\s*[:=]\s*"?[\w\-.]+"?', re.I),
    re.compile(r'"?nonce"?\s*[:=]\s*"?[\w\-]+"?', re.I),
    re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'),  # uuid
    re.compile(r'\b\d{10,13}\b'),  # unix timestamp (сек/мс)
)


def _normalize_body(body):
    text = body if isinstance(body, str) else ("" if body is None else str(body))
    try:
        for pat in _NOISE_PATTERNS:
            text = pat.sub("<NORM>", text)
    except Exception:
        pass
    return text


# Статические (НАШИ, не attacker-controlled) сигнатуры -- безопасно класть имя сработавшей сигнатуры
# в evidence, это не сырой ответ таргета.
_SQLI_SIGNATURES = (
    "sql syntax", "you have an error in your sql syntax", "unclosed quotation mark",
    "quoted string not properly terminated", "sqlstate", "ora-00933", "ora-01756",
    "pg_query():", "sqlite3.operationalerror", "microsoft ole db provider for odbc drivers",
    "warning: mysql", "mysql_fetch_array", "syntax error at or near", "npgsql.postgresexception",
)
_SSTI_SIGNATURES = (
    "jinja2.exceptions", "templatesyntaxerror", "freemarker.core.parseexception",
    "org.thymeleaf.exceptions", "twig\\error\\", "velocity.exception", "undefinederror",
)
_SIGNATURE_SETS = {"sqli": _SQLI_SIGNATURES, "ssti": _SSTI_SIGNATURES}

_LEN_SPIKE_MIN_ABS = 50
_LEN_SPIKE_RATIO = 0.25
_TIMING_SPIKE_SECONDS = 2.0


def _detect_signature(text_lower, probe):
    sigs = _SIGNATURE_SETS.get(probe, _SQLI_SIGNATURES + _SSTI_SIGNATURES)
    for sig in sigs:
        if sig in text_lower:
            return sig
    return None


def blind_diff(baseline_resp, payload_resp, probe="sqli"):
    """baseline_resp/payload_resp: dict|object с status/body/headers (+ опц. elapsed/target/url).
    Возвращает Divergence(dclass="input-sink") если payload-ответ несёт сигнал ВЫШЕ шума
    (новая error-сигнатура / body-length spike / timing spike / status-class spike относительно
    нормализованного baseline), иначе None. 403+WAF-body в payload_resp -> None ДО diff'а."""
    try:
        p_status = _get(payload_resp, "status")
        p_body = _get(payload_resp, "body", "") or ""
        p_headers = _get(payload_resp, "headers", {}) or {}

        if classify_http(p_status, p_body, p_headers) == WAF_BLOCK:
            return None

        b_status = _get(baseline_resp, "status")
        b_body = _get(baseline_resp, "body", "") or ""

        b_norm = _normalize_body(b_body)
        p_norm = _normalize_body(p_body)
        b_lower = b_norm.lower()
        p_lower = p_norm.lower()

        b_sig = _detect_signature(b_lower, probe)
        p_sig = _detect_signature(p_lower, probe)
        error_sig_new = p_sig if (p_sig and not b_sig) else None

        len_delta = abs(len(p_norm) - len(b_norm))
        len_spike = len_delta > max(_LEN_SPIKE_MIN_ABS, _LEN_SPIKE_RATIO * len(b_norm))

        b_elapsed = _get(baseline_resp, "elapsed")
        p_elapsed = _get(payload_resp, "elapsed")
        timing_spike = False
        if isinstance(b_elapsed, (int, float)) and isinstance(p_elapsed, (int, float)):
            timing_spike = (p_elapsed - b_elapsed) > _TIMING_SPIKE_SECONDS

        status_spike = False
        try:
            if b_status is not None and p_status is not None:
                status_spike = int(b_status) < 500 and int(p_status) >= 500
        except Exception:
            status_spike = False

        # status=None/headers={} на ОБЕИХ сторонах намеренно: единственный канал сравнения -- fields
        # (derived-сигналы), сырой status/headers ответа НЕ участвует в diff'е (иначе безобидная
        # разница статуса/заголовков между baseline и payload шумила бы false-positive).
        baseline_fields = {"error_sig": None, "len_spike": False, "timing_spike": False, "status_spike": False}
        payload_fields = {
            "error_sig": error_sig_new,
            "len_spike": bool(len_spike),
            "timing_spike": bool(timing_spike),
            "status_spike": bool(status_spike),
        }

        target = (_get(payload_resp, "target") or _get(payload_resp, "url")
                  or _get(baseline_resp, "target") or probe)

        ctx_a = Context("baseline", StaticDriver(Response(status=None, fields=baseline_fields, headers={})))
        ctx_b = Context("payload", StaticDriver(Response(status=None, fields=payload_fields, headers={})))
        return differential(ctx_a, ctx_b, Probe("input-sink", target, payload={"probe": probe}))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# cors_capture -- ACAO:*+ACAC:true / origin-reflection без allowlist
# ---------------------------------------------------------------------------

def cors_capture(response_headers, origin_reflected):
    """`response_headers` -- dict заголовков ОДНОГО ответа. `origin_reflected` -- caller уже прогнал
    запрос с attacker-choosen Origin и увидел его отражённым в ACAO (это его наблюдение, не эта
    функция шлёт запросы). `ACAO:*`+`ACAC:true` ИЛИ `origin_reflected=True` -> Divergence класса
    data-exposure/origin-trust; strict CORS (нет ни того ни другого) -> None."""
    try:
        headers = response_headers if isinstance(response_headers, dict) else {}
        headers_lower = {}
        for k, v in headers.items():
            try:
                headers_lower[str(k).lower()] = v
            except Exception:
                continue

        acao = headers_lower.get("access-control-allow-origin")
        acac = headers_lower.get("access-control-allow-credentials")
        acac_true = isinstance(acac, str) and acac.strip().lower() == "true"
        wildcard_creds = (acao == "*") and acac_true

        if not (wildcard_creds or bool(origin_reflected)):
            return None

        # `acao` is attacker-controlled when origin_reflected=True (caller sent an attacker-chosen
        # Origin and the server echoed it back verbatim) -- Global Constraint: reflected input must be
        # guard-scanned BEFORE it lands in evidence (evidence -> system_model.md -> read by an agent,
        # Read isn't covered by the PostToolUse prompt-injection guard). Guard fail-CLOSED via
        # `_guard_scan`, same pattern as `schema_hint_leak`/`authz_diff._guard_scan`. Static wildcard
        # ("*", not reflected) is OUR classification of a fixed header value, not attacker text --
        # doesn't need scanning.
        acao_safe = acao
        if origin_reflected and isinstance(acao, str) and _guard_scan(acao):
            acao_safe = "[GUARD-BLOCKED]"

        return Divergence(
            dclass="data-exposure/origin-trust",
            ctx_pair=("observed", "spec-strict-cors"),
            evidence={
                "target": "cors",
                "access-control-allow-origin": acao_safe,
                "access-control-allow-credentials": acac,
                "origin_reflected": bool(origin_reflected),
            },
            attack_path_hint=("проверь credentialed cross-origin read: XHR/fetch с attacker-origin + "
                               "credentials:'include' против authenticated эндпоинта"),
            severity_seed="high",
            provenance="AUTO",
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# headers_capture -- обёртка над runtime_harness.capture_headers (N-way clone-diff)
#                    + недостающие security-headers per-host
# ---------------------------------------------------------------------------

_REQUIRED_SECURITY_HEADERS = ("content-security-policy", "strict-transport-security", "x-frame-options")


def _headers_of(resp):
    h = _get(resp, "headers", {})
    if not isinstance(h, dict):
        return {}
    out = {}
    for k, v in h.items():
        try:
            out[str(k).lower()] = v
        except Exception:
            continue
    return out


def headers_capture(host_responses):
    """`host_responses` = `{host: Response|dict}`. Возвращает pairwise clone-parity Divergence
    (переиспользует `runtime_harness.capture_headers`) + отдельный Divergence(dclass="security-headers")
    ПЕР хосту за недостающие CSP/HSTS/X-Frame-Options/frame-ancestors (frame-ancestors засчитан, если
    он есть как CSP-директива ИЛИ есть X-Frame-Options -- это две равнозначные защиты от clickjacking).
    Fail-open: битый вход -> то, что успел собрать capture_headers (обычно [])."""
    divergences = list(_rh.capture_headers(host_responses))
    if not isinstance(host_responses, dict):
        return divergences
    for host, resp in host_responses.items():
        try:
            headers_lower = _headers_of(resp)
            missing = [h for h in _REQUIRED_SECURITY_HEADERS if h not in headers_lower]
            csp = str(headers_lower.get("content-security-policy", "") or "")
            has_frame_ancestors = "frame-ancestors" in csp.lower()
            if not has_frame_ancestors and "x-frame-options" not in headers_lower:
                if "frame-ancestors" not in missing:
                    missing.append("frame-ancestors")
            if missing:
                divergences.append(Divergence(
                    dclass="security-headers",
                    ctx_pair=(str(host), "spec-baseline"),
                    evidence={"target": str(host), "missing": missing},
                    attack_path_hint=("проверь clickjacking/downgrade/XSS-blast-radius из-за "
                                       "отсутствующих security-headers: %s" % ", ".join(missing)),
                    severity_seed="med",
                    provenance="AUTO",
                ))
        except Exception:
            continue
    return divergences


# ---------------------------------------------------------------------------
# schema_hint_leak -- schema-enum via error-hints (PostgREST/Supabase/Zod/FastAPI)
# ---------------------------------------------------------------------------

_FIELD_HINT_PATTERNS = (
    re.compile(r'column\s+"([\w.]+)"\s+does not exist', re.I),                    # PostgREST/Supabase
    re.compile(r'"path"\s*:\s*\[\s*"([^"]+)"', re.I),                              # Zod
    re.compile(r'"loc"\s*:\s*\[\s*"[^"]*"\s*,\s*"([^"]+)"', re.I),                 # FastAPI/Pydantic
    re.compile(r'field required.{0,10}"([\w.]+)"', re.I),
)
_TABLE_HINT_PATTERNS = (
    re.compile(r'relation\s+"([\w.]+)"\s+does not exist', re.I),                   # PostgREST/Supabase
    re.compile(r'table\s+"([\w.]+)"\s+does not exist', re.I),
    re.compile(r'no such table:\s*([\w.]+)', re.I),                                # sqlite
)


def _dedup(seq):
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def schema_hint_leak(error_body):
    """error_body -- attacker-influenced (сервер вернул его в ответ на НАШ запрос, но его контент
    формируется таргетом из внутреннего состояния -- verbose ORM/validation ошибка). Guard (`_guard_scan`)
    -- fail-CLOSED исключение из общего fail-open этого модуля (тот же паттерн, что
    `authz_diff._guard_scan`/`runtime_harness._guard_scan_value`; второе такое место в модуле --
    `cors_capture`): если сам вызов pi_guard_lib.scan() падает, трактуем вход как заблокированный, а НЕ
    пропускаем как есть."""
    try:
        text = error_body if isinstance(error_body, str) else ("" if error_body is None else str(error_body))
    except Exception:
        text = ""

    if _guard_scan(text):
        return {"fields": ["[GUARD-BLOCKED]"], "tables": ["[GUARD-BLOCKED]"]}

    try:
        fields = []
        for pat in _FIELD_HINT_PATTERNS:
            fields.extend(pat.findall(text))
        tables = []
        for pat in _TABLE_HINT_PATTERNS:
            tables.extend(pat.findall(text))
        return {"fields": _dedup(fields), "tables": _dedup(tables)}
    except Exception:
        return {"fields": [], "tables": []}
