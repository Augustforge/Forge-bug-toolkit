# -*- coding: utf-8 -*-
"""authz_diff — authz-differential harness (FDE План 5, Task 3).

Ядро web2-профиля `/hunt`: matrix ответов N ролей (`admin`/`user-A`/`user-B`/`unauth`, опционально
`tenant-A`/`tenant-B`) на ОДИН и тот же endpoint -> `differential_observation.py` находит расхождения
и классифицирует их как `object-authz`(BOLA) / `function-authz`(BFLA) / `tenant-isolation` /
`broken-auth`. Producer артефакта `authz_matrix.md` (toolkit-rooted `session_dir`) — его читает
gate-детектор `active_authz_matrix_skipped` (Task 9).

Наблюдение+diff, НЕ эксплуатация: этот модуль никогда не шлёт живые HTTP-запросы сам — `role_responses`
приходят от вызывающего кода (живой driver — Task 9/10) уже захваченными. Fail-open везде (унаследовано
от `differential_observation.py`), КРОМЕ guard-вызова (см. `_guard_scan`, тот же fail-CLOSED паттерн,
что `runtime_harness._guard_scan_value`).

Reuse-дисциплина (важно для isinstance-совместимости): `runtime_harness.py` уже транзитивно грузит
`differential_observation.py`/`opsec_preflight.py`/`pi_guard_lib.py` через `importlib.spec_from_file_location`
и РЕ-ЭКСПОРТИРУЕТ их символы на своём модульном уровне (`Context`/`Probe`/`Response`/`StaticDriver`/
`Divergence`/`differential`/`differential_matrix`/`spec_baseline_context`/`_as_context`/`_pi_guard`). Если
бы этот модуль грузил `differential_observation.py` ЕЩЁ РАЗ отдельным `importlib`-вызовом, классы
(`Response`/`Context`/...) оказались бы ДРУГИМИ Python-объектами, чем те, что использует
`runtime_harness._as_context` внутри своих `isinstance()`-проверок — вызовет ложные fail-open ветки.
Поэтому здесь грузится ТОЛЬКО `runtime_harness.py` (для dobs-реэкспортов + guard) и отдельно
`error_recovery.py` (`classify_http`, runtime_harness его не грузит).

Публичный контракт (держать точно — потребитель Task 9 gate + скилл `/hunt`):
    build_role_contexts(role_responses) -> dict[str, Context]
    authz_diff(endpoint, role_contexts, mode="full-matrix") -> list[Divergence]
    run_authz_matrix(endpoints, role_contexts, session_dir, mode="full-matrix") -> str
    class _BaselineCache — LRU+TTL, ts всегда параметр СНАРУЖИ (никогда time.time()/monotonic() внутри).

Raw-body convention (Response не хранит raw body text, только `fields`/`headers`/`status`/`body_hash`):
для WAF-сигнатур (`classify_http` смотрит на `body`) вызывающий код кладёт сырой текст тела под
`fields["_body"]` — `_as_context`/`_to_response` (runtime_harness.py) копируют `fields` как есть,
значение доживает до классификации нетронутым.
"""

import os
import re
import json
import hashlib
import collections
import importlib.util


# ---------------------------------------------------------------------------
# Загрузка Consumes-модулей (путь резолвится от __file__, не от os.getcwd() —
# тот же паттерн, что runtime_harness.py: этот модуль импортируется тестом/скиллом
# из разных cwd, а cwd на Windows может содержать кириллицу/длинный путь).
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)                                       # .../bug-bounty-toolkit/scripts
_METHOD_DIR = os.path.join(_SCRIPTS_DIR, "_methodology")
_WALLET_TEST_DIR = os.path.join(_SCRIPTS_DIR, "dapphunt", "wallet_test")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_rh = _load("authz_diff_runtime_harness", os.path.join(_WALLET_TEST_DIR, "runtime_harness.py"))
_error_recovery = _load("authz_diff_error_recovery", os.path.join(_METHOD_DIR, "error_recovery.py"))
# Task T4 (Plan 9): standalone Object Provenance Ledger — co-located in web2/, no cross-module class
# sharing (only plain dict records), so a direct _load is safe (no isinstance-discipline concern).
_object_registry = _load("authz_diff_object_registry", os.path.join(_HERE, "object_registry.py"))
# Task T10 (Plan 9, Tier E composite ←T4,T9): traffic-archive re-miner. Only its `remine` read-back
# is consumed (plain dict records, no cross-module class sharing) — a direct _load is safe. Its module
# import does NO network/opsec I/O (opsec is loaded lazily inside open_archive(live=True) only), so
# loading it here for offline re-mining never touches the fail-CLOSED opsec path.
_traffic_archive = _load("authz_diff_traffic_archive", os.path.join(_WALLET_TEST_DIR, "traffic_archive.py"))

# Ре-экспорты differential_observation.py -- ЧЕРЕЗ runtime_harness (см. docstring: reuse-дисциплина,
# не грузим differential_observation.py отдельно, иначе isinstance() между модулями разъедется).
Context = _rh.Context
Probe = _rh.Probe
Response = _rh.Response
StaticDriver = _rh.StaticDriver
Divergence = _rh.Divergence
differential = _rh.differential
spec_baseline_context = _rh.spec_baseline_context
_as_context = _rh._as_context
_pi_guard = _rh._pi_guard

# Task 10 (carry BS-05, ownership-baseline BOLA fix): `ownership_diff` -- НЕ в `runtime_harness.py`'s
# явном ре-экспорт-списке (Task 2/Plan 4 контракт, вне скоупа этой задачи трогать). Достаём напрямую
# из уже загруженного `_rh._dobs` (тот же живой module-объект, что `runtime_harness.py` использует
# для СВОИХ `Context`/`Divergence`/... ре-экспортов выше) -- те же классы, никакого повторного
# `importlib`-грузчика differential_observation.py и, значит, никакого isinstance-разъезда (см.
# docstring модуля, "Reuse-дисциплина").
ownership_diff = _rh._dobs.ownership_diff

classify_http = _error_recovery.classify_http

# HTTP-классы, при которых ответ роли -- НЕ authz-сигнал (WAF/rate-limit/5xx шум), см. Consumes/Produces#2.
_INCONCLUSIVE_HTTP_CLASSES = (
    _error_recovery.RATE_LIMITED,
    _error_recovery.WAF_BLOCK,
    _error_recovery.SERVER_ERR,
)

# gate-совместимый паттерн для to_dnn_row()-строк (hunt_completeness_gate._D_ROW_RE, verbatim regex) --
# ЛОКАЛЬНАЯ копия (брифом разрешено "импортни gate ИЛИ проверь формат"), не грузим тяжёлый гейт-модуль
# ради одного regex.
_D_ROW_RE = re.compile(r"^\s*\|\s*D-\d+\s*\|")
_RENUMBER_D01_RE = re.compile(r"^\|\s*D-01\s*\|")


# ---------------------------------------------------------------------------
# _BaselineCache -- LRU+TTL, dedup idempotent-baseline конструирования (unauth-GET / spec-baseline)
# ---------------------------------------------------------------------------

class _BaselineCache(object):
    """LRU (capacity) + TTL cache для idempotent baseline-объектов. `ts` -- ВСЕГДА параметр методов,
    класс НИКОГДА не зовёт `time.time()`/`time.monotonic()` сам (детерминизм в тесте: вызывающий код
    подаёт свой монотонный счётчик). `get_or_compute` -- основной вход: cache-hit внутри `ttl` от
    `put_ts` -> возвращает закэшированное значение БЕЗ вызова `compute_fn`; иначе зовёт `compute_fn()`
    ровно один раз, кладёт в кэш, возвращает. LRU-эвикция при переполнении `capacity` (списывает
    самый давно тронутый ключ)."""

    def __init__(self, capacity=32, ttl=300):
        self._capacity = capacity
        self._ttl = ttl
        self._store = collections.OrderedDict()  # key -> (value, put_ts)

    def get(self, key, ts):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, put_ts = entry
        if ts - put_ts > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def put(self, key, value, ts):
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, ts)
        while len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def get_or_compute(self, key, ts, compute_fn):
        cached = self.get(key, ts)
        if cached is not None:
            return cached
        value = compute_fn()
        self.put(key, value, ts)
        return value


# Module-level singleton -- дедуп spec-baseline конструирования ЧЕРЕЗ несколько endpoint'ов ОДНОГО
# run_authz_matrix()-прогона (spec_baseline_context("spec-401",401) идентичен для каждого endpoint'а).
# `ts` -- монотонный module-level счётчик (НЕ wall-clock), инкрементируется на каждый authz_diff()-вызов.
_BASELINE_CACHE = _BaselineCache()
_ts_counter = [0]


def _next_ts():
    _ts_counter[0] += 1
    return _ts_counter[0]


def _cached_spec_baseline(label, status):
    key = (label, status)
    return _BASELINE_CACHE.get_or_compute(key, _next_ts(), lambda: spec_baseline_context(label, status))


# ---------------------------------------------------------------------------
# Guard call-site (Consumes: pi_guard_lib.scan -- "guard-scan reflected error перед log"). Тот же
# fail-CLOSED паттерн, что runtime_harness._guard_scan_value: сбой сканера -> "[GUARD-BLOCKED]",
# НЕ пропуск непроверенного текста как есть.
# ---------------------------------------------------------------------------

def _guard_scan(text):
    try:
        verdict = _pi_guard.scan(text)
        if getattr(verdict, "blocked", False):
            return "[GUARD-BLOCKED]"
        return text
    except Exception:
        return "[GUARD-BLOCKED]"


# ---------------------------------------------------------------------------
# 1. build_role_contexts
# ---------------------------------------------------------------------------

def build_role_contexts(role_responses):
    """`{"admin": Response|dict, "user-A": …, "user-B": …, "unauth": …, ["tenant-A":…, "tenant-B":…,
    "user-B-own":…]}` -> `{role: Context(role=role)}` через `_as_context` (runtime_harness.py).
    Не-dict вход -> `{}` (fail-open). `"user-B-own"` (Task 10, carry BS-05) -- opt-in self-baseline
    (user-B's ОТВЕТ на СВОЙ собственный объект) для ownership-baseline BOLA-чека, см. `authz_diff()`.
    Task T3 (Plan 9): опциональные transition-ключи `"user-A-revoked"`/`"user-A-expired"`/
    `"user-A-downgraded"`/`"user-A-unshared"` -- ОТВЕТ того же актора на ТОТ ЖЕ объект ПОСЛЕ
    lifecycle-перехода (revocation/lifecycle staleness axis, см. `authz_diff()` / `_TRANSITION_CHECKS`)."""
    if not isinstance(role_responses, dict):
        return {}
    return {role: _as_context(resp, role) for role, resp in role_responses.items()}


# ---------------------------------------------------------------------------
# 2. authz_diff -- matrix ОДНОГО endpoint'а
# ---------------------------------------------------------------------------

def _http_class_and_body(ctx, probe):
    """`classify_http` ответа `ctx` на `probe` + сырой body (см. `_body`-конвенция в docstring модуля).
    Fail-open: любая ошибка -> (`OK`, "") -- не блокирует диф."""
    try:
        resp = ctx.driver.probe(probe)
        body = ""
        if isinstance(resp.fields, dict):
            body = resp.fields.get("_body") or ""
        cls = classify_http(resp.status, body, resp.headers)
        return cls, body
    except Exception:
        return _error_recovery.OK, ""


def _inconclusive_divergence(http_class, endpoint, ctx_pair, body):
    """Не-authz сигнал (WAF/rate-limit/5xx) -- всё равно `Divergence` (держит контракт
    `list[Divergence]`), но `dclass` промаркирован `[INCONCLUSIVE-<class>]` -- `run_authz_matrix`
    исключает такие из счётчика/нумерации `D-NN` (см. Produces#3: "НЕ считать за authz-divergence").
    `body`-сниппет (первые 60 символов) идёт через guard ПЕРЕД тем, как попасть в evidence/лог --
    reflected body может нести prompt-injection payload."""
    snippet = _guard_scan(body[:60]) if body else ""
    return Divergence(
        dclass="[INCONCLUSIVE-%s]" % http_class,
        ctx_pair=ctx_pair,
        evidence={"target": endpoint, "reason": http_class, "body_snippet": snippet},
        attack_path_hint=(
            "HTTP-классификатор пометил ответ как %s -- НЕ authz-сигнал (WAF/rate-limit/сервер-ошибка); "
            "повторить чек с backoff/иным IP/после устранения помехи, прежде чем делать вывод про authz"
        ) % http_class,
        severity_seed="info",
        provenance="AUTO",
    )


# ---------------------------------------------------------------------------
# Operation-outcome coverage (Task 2, Plan 9 hunter-parity). EXACTLY ONE outcome record per
# (operation, role) authz check REGARDLESS of outcome -- "tested & clean" must be DISTINGUISHABLE
# from "never tested". Status enum: tested-clean / divergent / inconclusive-<http_class> / excluded /
# blocked. `authz_diff` keeps its list[Divergence] contract by projecting these records; the
# producer `run_authz_matrix` iterates the full record set so it can write a row for clean/excluded
# checks too (co-located gate `active_operation_coverage_incomplete` validates every row has a status).
# ---------------------------------------------------------------------------

STATUS_TESTED_CLEAN = "tested-clean"
STATUS_DIVERGENT = "divergent"
STATUS_EXCLUDED = "excluded"
STATUS_BLOCKED = "blocked"

# Task T3 (Plan 9 hunter-parity): temporal / revocation-lifecycle staleness. The base matrix is
# POINT-IN-TIME -- it only ever sees one snapshot of a role's access. Real BOLA/BFLA also lives in
# TIME: a token/grant that STILL works after it was revoked/expired/downgraded/unshared. This is the
# opt-in transition->reprobe axis. The caller captures the SAME actor's response on the SAME object
# AFTER the named lifecycle transition and supplies it under a transition role-key; the post-transition
# response is compared against the spec-denial baseline (a revoked credential SHOULD get 401/403). A
# still-granted (2xx/data) response = "stale-but-still-works" = a real divergence (own status/dclass,
# never a silent skip). Opt-in: a transition key ABSENT from role_contexts emits NO row at all (unlike
# the always-present core checks) -- temporal probing only happens when the caller staged the transition.
_TEMPORAL_HINT = (
    "revocation/lifecycle staleness: credential/grant still returns access AFTER the transition "
    "(revoke/expire/downgrade/unshare) -- re-probe SAME (operation, role) post-transition; confirm the "
    "grant is not merely cached client-side and that a fresh session with the revoked credential still "
    "reaches the object (stale server-side authz state = BOLA/BFLA in time)"
)

# (transition role-key, human transition name, expected post-transition denial status). Ordered for
# deterministic row emission. Expire -> 401 (credential no longer valid); revoke/downgrade/unshare ->
# 403 (identity valid but this grant removed).
_TRANSITION_CHECKS = [
    ("user-A-revoked", "revoke", 403),
    ("user-A-expired", "expire", 401),
    ("user-A-downgraded", "downgrade", 403),
    ("user-A-unshared", "unshare", 403),
]


class _OutcomeRecord(object):
    """One (operation, role) authz check outcome. `divergence` -- произведённый `Divergence` (реальный
    ИЛИ `[INCONCLUSIVE-...]`) либо `None` (tested-clean / excluded)."""
    __slots__ = ("operation", "role", "kind", "status", "divergence")

    def __init__(self, operation, role, kind, status, divergence=None):
        self.operation = operation
        self.role = role
        self.kind = kind
        self.status = status
        self.divergence = divergence


# ---------------------------------------------------------------------------
# Object Provenance Ledger consumer (Task T4, Plan 9 hunter-parity). Marius verbatim: «the difference
# between changing a random ID and PROVING broken access control». `ownership_diff` gives a SINGLE-
# RESPONSE marker-diff (attacker's body carries an owner-marker != their own self-baseline). This
# UPGRADES that hit into a PROVEN create->access CHAIN by consulting the standalone create-event
# registry (`object_registry.py`): if the probed object_id was RECORDED as created/owned by identity
# X (the create event) and the leaked owner marker == X while the ACCESSING identity != X (the access
# event), the finding is no longer «I changed an ID and saw different data» but «I recorded who
# created this object and now observe a different identity reading it» = demonstrated broken access
# control. Annotation-only (does NOT build a new diff engine — reuses ownership_diff); no registry /
# no match / accessor-is-owner -> divergence left untouched (still a valid marker-diff, just unproven).
# Standalone (Р6): T10 later auto-fills the chain from traffic-archive; here the caller registers
# create-events explicitly. fail-open (non-security).
# ---------------------------------------------------------------------------

def _apply_provenance(div, endpoint, registry):
    try:
        if not registry:
            return div
        ev = div.evidence if isinstance(div.evidence, dict) else None
        mismatch = ev.get("owner_mismatch") if ev else None
        if not isinstance(mismatch, dict) or not mismatch:
            return div  # not an ownership owner_mismatch signal -> nothing to prove
        rec = _object_registry.lookup_by_endpoint(registry, endpoint)
        if not isinstance(rec, dict):
            return div  # object never recorded as created this run -> no chain, stay a marker-diff
        owner = rec.get("owner")
        # Leaked (target) owner value + accessing (self) value from any owner marker in the mismatch.
        target_owner = None
        self_id = None
        for _k, pair in mismatch.items():
            if isinstance(pair, dict):
                target_owner = pair.get("target")
                self_id = pair.get("self")
                break
        if owner is None or target_owner is None:
            return div
        # Proven chain requires the registered owner to MATCH the leaked owner (the object truly
        # belongs to the create-event owner) AND the accessor to genuinely differ from that owner.
        if str(owner) != str(target_owner):
            return div  # registry disagrees with the leaked owner -> do NOT fabricate a chain
        if self_id is not None and str(self_id) == str(owner):
            return div  # accessor IS the owner -> legit self-access, no chain
        ev["provenance_backed"] = True
        ev["provenance_chain"] = {
            "object_id": rec.get("object_id"),
            "created_by": rec.get("created_by"),
            "owner": owner,
            "creating_request": rec.get("creating_request"),
            "timestamp": rec.get("timestamp"),
            "accessed_by": self_id,
        }
        div.attack_path_hint = (
            "PROVEN create->access chain (object-provenance ledger): object %r was created by %r "
            "(owner=%r) via %r; identity %r now reads it -> broken access control is DEMONSTRATED "
            "(recorded create event + observed foreign read), not a single-response marker-diff / "
            "changed ID"
        ) % (rec.get("object_id"), rec.get("created_by"), owner, rec.get("creating_request"), self_id)
        return div
    except Exception:
        return div


def _authz_outcomes(endpoint, role_contexts, mode="full-matrix", registry=None,
                    discovered_markers=()):
    """Полный набор канонических (operation, role) чеков для ОДНОГО `endpoint` -- по одному
    `_OutcomeRecord` на КАЖДЫЙ чек, включая пропущенные (excluded, роль отсутствует) и чистые
    (tested-clean, diff вернул None). Порядок чеков фиксирован (BOLA → ownership → broken-auth →
    BFLA → tenant) -- тот же, что раньше выдавал `authz_diff`, поэтому проекция ниже сохраняет
    точный порядок/содержимое старого `list[Divergence]`-контракта.

    `authz_diff` (публичный контракт) = `[r.divergence for r in _authz_outcomes(...) if r.divergence]`.
    Семантика самих чеков (classify_http-gate, ownership-baseline, spec-baseline асимметрия,
    single+unauth → MANUAL) неизменна -- см. `authz_diff` docstring."""
    # build_role_contexts идемпотентна и на уже-Context значениях (`_as_context` возвращает Context
    # как есть) -- один и тот же вызов принимает и сырые role_responses, и готовый role_contexts.
    ctx = build_role_contexts(role_contexts)
    records = []
    # A2: per-target owner-marker словарь = default + owner-подобные из schema_hint_leak (discovered).
    _own_markers = _rh._dobs.owner_like_markers(discovered_markers)

    def _excluded(kind, role_label):
        records.append(_OutcomeRecord(endpoint, role_label, kind, STATUS_EXCLUDED))

    def _run_check(kind, role_label, ctx_a, ctx_b, roles_to_classify, diff_fn=differential,
                   severity=None, hint=None, post_div=None):
        probe = Probe(kind, endpoint)
        for role_key in roles_to_classify:
            c = ctx.get(role_key)
            if c is None:
                continue
            http_class, body = _http_class_and_body(c, probe)
            if http_class in _INCONCLUSIVE_HTTP_CLASSES:
                div = _inconclusive_divergence(http_class, endpoint, (ctx_a.label, ctx_b.label), body)
                # `blocked` != `inconclusive-<class>`: reflected body несёт prompt-injection payload,
                # guard его срезал ([GUARD-BLOCKED]) -> evidence непригоден для классификации =
                # ОТДЕЛЬНЫЙ исход `blocked` (не WAF/rate-limit шум).
                snip = div.evidence.get("body_snippet") if isinstance(div.evidence, dict) else None
                status = STATUS_BLOCKED if snip == "[GUARD-BLOCKED]" else ("inconclusive-%s" % http_class)
                records.append(_OutcomeRecord(endpoint, role_label, kind, status, div))
                return
        div = diff_fn(ctx_a, ctx_b, probe)
        if div is not None:
            if mode == "single+unauth":
                div.provenance = "MANUAL"
            # Task T3 (temporal): dclass comes from probe.kind, but severity_seed/attack_path_hint
            # default to med/generic for a kind unknown to differential_observation's maps
            # (e.g. "revocation-staleness"). Override in place so a stale-access hit reads as high,
            # without touching differential_observation.py (wave isolation).
            if severity is not None:
                div.severity_seed = severity
            if hint is not None:
                div.attack_path_hint = hint
            if post_div is not None:
                div = post_div(div) or div
            records.append(_OutcomeRecord(endpoint, role_label, kind, STATUS_DIVERGENT, div))
        else:
            records.append(_OutcomeRecord(endpoint, role_label, kind, STATUS_TESTED_CLEAN))

    # 1. object-authz / BOLA -- симметричные пиры user-B vs user-A (brief verbatim call order).
    if "user-B" in ctx and "user-A" in ctx:
        _run_check("object-authz", "user-B vs user-A", ctx["user-B"], ctx["user-A"], ["user-B", "user-A"])
    else:
        _excluded("object-authz", "user-B vs user-A")

    # 1b. ownership-baseline (Task 10, carry BS-05) -- ADDITIVE full-leak BOLA чек, независимый от
    # equality-чека выше (1.): равенство-based `differential()` структурно слепнет, когда user-B
    # получает БАЙТ-В-БАЙТ ту же копию объекта user-A (diverged=False -> None, см. BS-05). Эта ветка
    # сравнивает НЕ user-B-vs-user-A, а user-B-for-A's-object (ctx["user-B"], тот же probe объекта
    # A под тестом) против user-B-for-B's-OWN-object (opt-in role-key "user-B-own" -- caller
    # подкладывает self-baseline ответ, см. build_role_contexts docstring) и флагает owner-маркер
    # (owner_id/account/email/tenant/...) чужого объекта в теле НЕЗАВИСИМО от равенства эталону A.
    # Opt-in: без ключа "user-B-own" чек = excluded (не тестировали self-baseline, а не «чисто»).
    if "user-B" in ctx and "user-B-own" in ctx:
        _run_check("object-authz", "user-B vs user-B-own", ctx["user-B"], ctx["user-B-own"],
                   ["user-B", "user-B-own"],
                   diff_fn=lambda t, s, p: ownership_diff(t, s, p, markers=_own_markers),
                   post_div=lambda d: _apply_provenance(d, endpoint, registry))
    else:
        _excluded("object-authz", "user-B vs user-B-own")

    # 2. broken-auth -- асимметрия: spec-401 (что ожидается по спеке для unauth) vs живой unauth.
    if "unauth" in ctx:
        baseline_401 = _cached_spec_baseline("spec-401", 401)
        _run_check("broken-auth", "spec-401 vs unauth", baseline_401, ctx["unauth"], ["unauth"])
    else:
        _excluded("broken-auth", "spec-401 vs unauth")

    # 3. function-authz / BFLA -- асимметрия: spec-403 (low-priv не должен пройти) vs живой user-A.
    if "user-A" in ctx:
        baseline_403 = _cached_spec_baseline("spec-403", 403)
        _run_check("function-authz", "spec-403 vs user-A", baseline_403, ctx["user-A"], ["user-A"])
    else:
        _excluded("function-authz", "spec-403 vs user-A")

    # 4. tenant-isolation -- симметричные пиры tenant-B vs tenant-A, ТОЛЬКО если оба присутствуют
    # (отдельные ключи от user-A/user-B -- tenant-isolation это cross-org, не cross-user внутри
    # одной организации; см. Produces#2 "если есть tenant-контексты").
    if "tenant-B" in ctx and "tenant-A" in ctx:
        _run_check("tenant-isolation", "tenant-B vs tenant-A", ctx["tenant-B"], ctx["tenant-A"],
                   ["tenant-B", "tenant-A"])
    else:
        _excluded("tenant-isolation", "tenant-B vs tenant-A")

    # 5. revocation/lifecycle staleness (Task T3) -- OPT-IN temporal axis. For each staged transition
    # whose post-transition capture is present, compare it against the spec-denial baseline: a still-
    # granted response diverges from the expected 401/403 = stale-but-still-works. Absent transition key
    # -> no row (opt-in; do NOT _excluded every possible transition, that would spam every matrix).
    for tkey, tname, denial_status in _TRANSITION_CHECKS:
        if tkey in ctx:
            baseline = _cached_spec_baseline("spec-%d" % denial_status, denial_status)
            _run_check("revocation-staleness", "%s vs %s" % (tname, tkey),
                       baseline, ctx[tkey], [tkey],
                       severity="high", hint=_TEMPORAL_HINT)

    return records


def authz_diff(endpoint, role_contexts, mode="full-matrix", registry=None, discovered_markers=()):
    """Matrix ролей на ОДНОМ `endpoint`: BOLA (user-B vs user-A) / ownership-baseline BOLA (user-B
    vs user-B's OWN object, opt-in `"user-B-own"`, Task 10 carry BS-05) / broken-auth (spec-401 vs
    unauth) / BFLA (spec-403 vs user-A) / tenant-isolation (tenant-B vs tenant-A, если есть
    tenant-контексты). Каждый чек пропускается тихо (fail-open), если нужной роли нет в
    `role_contexts` -- партиальный role-набор (напр. `mode="single+unauth"`, R7: только `unauth` +
    один аккаунт) даёт партиальный результат, не падает.

    ПЕРЕД каждым diff -- `classify_http` РЕАЛЬНОГО (не-synthetic-baseline) ответа роли(ей),
    участвующей(их) в чеке: `RATE_LIMITED`/`WAF_BLOCK`/`SERVER_ERR` -> `[INCONCLUSIVE-<class>]`
    вместо authz-diff (WAF-403 != auth-403, иначе ложный BOLA/broken-auth).

    Ownership-baseline (Task 10, carry BS-05): BOLA-чек #1 (`differential(user-B, user-A)`) --
    РАВЕНСТВО-based -- структурно слепнет на full-leak (user-B получает БАЙТ-В-БАЙТ ту же копию
    объекта user-A -> diverged=False -> `differential()` возвращает None, "0 divergences" ложно).
    Ownership-baseline (`ownership_diff`, opt-in role-key `"user-B-own"`) сравнивает
    user-B-for-A's-object против user-B-for-B's-OWN-object по owner-маркерам тела (field-level,
    §43.5) НЕЗАВИСИМО от равенства эталону -- ловит именно этот класс, не заменяя чек #1.

    `mode="single+unauth"` (R7): opsec-гейт (`_web2_checks`, ≥2 test_accounts) НЕ пропустит живой
    harness с <2 аккаунтами -- единственный легитимный путь сюда с урезанным role-набором ЭТО ручной
    ввод. Продюсируемые (не-inconclusive) `Divergence` в этом режиме -- ВСЕГДА `provenance="MANUAL"`
    (никогда не выдаём `single+unauth` за AUTO harness-выход под opsec).

    Task 2 (Plan 9): контракт-неизменен -- возвращает `list[Divergence]` (real + `[INCONCLUSIVE-...]`
    в порядке чеков). Внутри делегирует `_authz_outcomes` (полный per-check outcome-набор) и
    проецирует только произведённые `Divergence` -- coverage-строки (tested-clean/excluded) видит
    только producer `run_authz_matrix`.

    Task T3 (Plan 9, revocation/lifecycle staleness -- ОПЦИОНАЛЬНАЯ temporal-ось): если в
    `role_contexts` присутствует transition-ключ (`user-A-revoked`/`user-A-expired`/
    `user-A-downgraded`/`user-A-unshared`) -- post-transition ответ того же актора на ТОТ ЖЕ объект --
    он сравнивается со spec-denial baseline (revoked credential ДОЛЖЕН получить 401/403). Всё ещё
    выданный доступ (2xx/data) => `Divergence` dclass="revocation-staleness", severity high
    (stale-but-still-works). Opt-in: transition-ключа нет -> temporal-строк нет (не point-in-time
    only). classify_http-gate (WAF/rate-limit/guard) применяется как к любому чеку.

    Task T4 (Plan 9, Object Provenance Ledger -- ОПЦИОНАЛЬНЫЙ `registry`): передан загруженный
    create-event реестр (`object_registry.load_registry(session_dir)` / dict / records-list) -- и
    ownership-baseline BOLA-хит (owner_mismatch) на объекте, чей create-event ЗАПИСАН в реестре
    (owner == leaked owner marker, accessor != owner) АПГРЕЙДИТСЯ в ДОКАЗАННУЮ create->access цепочку
    (`evidence["provenance_backed"]=True` + `evidence["provenance_chain"]`), а не «сменил random ID».
    Реестр не передан / объект не записан / accessor == owner -> хит остаётся marker-diff'ом
    (annotation-only, ownership_diff НЕ переписан). Standalone (Р6): create-события пишет caller через
    `object_registry.register_object`; T10 позже автозаполнит цепочку из traffic-archive."""
    return [r.divergence for r in _authz_outcomes(endpoint, role_contexts, mode=mode, registry=registry,
                                                  discovered_markers=discovered_markers)
            if r.divergence is not None]


# ---------------------------------------------------------------------------
# 3. run_authz_matrix -- прогон по endpoint'ам, producer authz_matrix.md
# ---------------------------------------------------------------------------

def _safe_cell(s):
    """Минимальный markdown-cell санитайзер (свой, не тянем private `_cell` из
    differential_observation.py -- не задокументирован в Consumes): `|` -> `/` (не форжит колонку),
    прогоны пробельных символов -> один пробел, `.strip()`. Пустая строка -> "-" (видимый placeholder,
    не пустая ячейка, которую легко принять за отсутствие данных)."""
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return "?"
    s = s.replace("|", "/")
    s = re.sub(r"\s+", " ", s).strip()
    return s or "-"


def _status_cell(div):
    ev = div.evidence if isinstance(div.evidence, dict) else {}
    dclass = div.dclass if isinstance(div.dclass, str) else ""
    if dclass.startswith("[INCONCLUSIVE"):
        reason = ev.get("reason", "?")
        snippet = ev.get("body_snippet")
        base = "%s [%s]" % (reason, snippet) if snippet else str(reason)
    else:
        status_diff = ev.get("status_diff")
        if status_diff:
            base = "%s->%s" % (status_diff.get("a"), status_diff.get("b"))
        else:
            field_leak = ev.get("field_leak")
            base = ("fields:" + ",".join(str(x) for x in field_leak)) if field_leak else "-"
    # R7 (single+unauth): a real divergence forced to provenance="MANUAL" must be VISIBLY marked in
    # the written file, not just carried silently on the in-memory Divergence -- otherwise a reader
    # of authz_matrix.md has no way to tell a MANUAL-mode row from a live AUTO harness finding
    # (opsec-critical: MANUAL must never read as AUTO-verified under the opsec gate).
    if getattr(div, "provenance", None) == "MANUAL":
        base = "%s provenance=MANUAL" % base
    # Task T4 (Plan 9): a provenance-backed ownership hit is a PROVEN create->access chain, not a
    # single-response marker-diff -- mark it VISIBLY in the written matrix so a human/gate reading
    # authz_matrix.md sees the finding is demonstrated (create event + foreign read), not «changed ID».
    if isinstance(ev, dict) and ev.get("provenance_backed"):
        base = "%s PROVEN-CHAIN" % base
    return base


def run_authz_matrix(endpoints, role_contexts, session_dir, mode="full-matrix", registry=None,
                     discovered_markers=()):
    """Прогоняет `authz_diff` по каждому `endpoint` из `endpoints`, сериализует в
    `{session_dir}/authz_matrix.md` (🔴 `session_dir` -- toolkit-rooted ПАРАМЕТР, НЕ хардкод bare
    `sessions/$DOMAIN` -- иначе gate-детектор Task 9, ищущий файл в `dirname(ledger)`, промахнётся).

    Формат: header + `MODE: <mode>` + summary-таблица `| endpoint | роль | исход | статус |
    divergence-класс | D-NN |` (Task 2, Plan 9: РОВНО ОДНА строка на КАЖДЫЙ (operation, role) чек,
    НЕЗАВИСИМО от исхода -- колонка `исход` несёт status-enum `tested-clean`/`divergent`/
    `inconclusive-<class>`/`excluded`/`blocked`, так «проверено-чисто» отличимо от «не тестили»;
    только `divergent`-строки получают `D-NN`, `[INCONCLUSIVE-...]`/`blocked`/clean/excluded → `-`,
    не считаются за authz-divergence) + `## Divergences` блок с ПЕРЕНУМЕРОВАННЫМИ
    `to_dnn_row()`-строками (`D-01`->`D-01`/`D-02`/... сквозная нумерация прогона; `Divergence.to_dnn_row()`
    сам хардкодит `D-01` -- см. его docstring: "агент, вливающий строку... перенумерует под реальный
    счётчик" -- это тот агент) -- КАЖДАЯ такая строка сама по себе матчит `hunt_completeness_gate._D_ROW_RE`
    (`^\\s*\\|\\s*D-\\d+\\s*\\|`), т.к. живёт на СВОЕЙ физической строке, а не вложена внутрь ячейки
    summary-таблицы (вложенность сломала бы построчный regex-парсинг гейта нежным способом).

    Task 3 (FDE План 6 §48.2/§44/§50.3): `to_dnn_row()` эмитит 12-ю ячейку `undup_origin` (дефолт
    `{TODO}`) ПЕРЕД Резолюция -- этот renumber-путь строит строку ЦЕЛИКОМ через
    `d.to_dnn_row()` (только regex-подменяет первую ячейку-ID), поэтому колонка приезжает сюда
    централизованно, без отдельной правки cell-сборки в этом файле.

    Пустой прогон (0 divergences) -> ВСЁ РАВНО пишет файл с `RESULT: matrix-run, 0 divergences` (Produces#3).
    Возвращает путь записанного файла."""
    session_dir = str(session_dir)
    os.makedirs(session_dir, exist_ok=True)
    out_path = os.path.join(session_dir, "authz_matrix.md")

    # Task T4 (Plan 9): standalone auto-consult -- if the caller did not pass a registry, load the
    # co-located create-event ledger `{session_dir}/object_registry.json` (missing -> empty registry,
    # no provenance, harmless). So dropping an object_registry.json next to the ledger is enough to
    # upgrade ownership hits into proven create->access chains, no extra wiring.
    if registry is None:
        registry = _object_registry.load_registry(session_dir)

    summary_rows = []
    dnn_blocks = []
    real_count = 0

    for endpoint in (endpoints or []):
        # Task 2 (Plan 9): итерируем ПОЛНЫЙ per-check outcome-набор (не только произведённые
        # Divergence) -- так каждая (operation, role) пара получает строку со статусом.
        for rec in _authz_outcomes(endpoint, role_contexts, mode=mode, registry=registry,
                                   discovered_markers=discovered_markers):
            d = rec.divergence
            dclass = "-"
            status_detail = "-"
            dnn_cell = "-"
            if d is not None:
                dclass = d.dclass if isinstance(d.dclass, str) else str(d.dclass)
                status_detail = _status_cell(d)
                if rec.status == STATUS_DIVERGENT:      # только реальный divergence -> D-NN + счётчик
                    real_count += 1
                    dnn_id = "D-%02d" % real_count
                    row = d.to_dnn_row()
                    row = _RENUMBER_D01_RE.sub("| %s |" % dnn_id, row, count=1)
                    dnn_blocks.append(row)
                    dnn_cell = dnn_id
            summary_rows.append("| %s | %s | %s | %s | %s | %s |" % (
                _safe_cell(rec.operation), _safe_cell(rec.role), _safe_cell(rec.status),
                _safe_cell(status_detail), _safe_cell(dclass), dnn_cell,
            ))

    lines = [
        "# authz_matrix.md — authz-differential harness run",
        "",
        "MODE: %s" % mode,
        "",
        "| endpoint | роль | исход | статус | divergence-класс | D-NN |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(summary_rows)
    if dnn_blocks:
        lines.append("")
        lines.append("## Divergences")
        lines.extend(dnn_blocks)
    lines.append("")
    lines.append("RESULT: matrix-run, %d divergences" % real_count)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


# ---------------------------------------------------------------------------
# 4. WS→Response adapter (Task 10, FDE План 7 §63 — WS/GraphQL-subscription в authz-модель).
#
# `authz_diff` сам соединений НЕ открывает — probe идёт через `ctx.driver.probe(probe) -> Response`.
# Этот driver ГОВОРИТ по WebSocket, ПЕРЕИСПОЛЬЗУЯ connection-логику `scripts/websocket_test.py` (НЕ
# переписывая раннер — грузим его лениво и обёрнуто, шлём probe как ws-сообщение subscription/query,
# нормализуем ответ в `Response`).
#
# 🔴 isinstance-дисциплина (та же, что в docstring модуля, «Reuse-дисциплина»): адаптер отдаёт
# module-level `Response` = `_rh.Response` — ТОТ ЖЕ живой класс, что использует `differential` внутри
# своих сравнений и `authz_diff` во всём остальном файле. Именно поэтому адаптер живёт ЗДЕСЬ, в
# `authz_diff.py`, а не в отдельном модуле со СВОИМ `_load(runtime_harness)`: отдельная загрузка дала
# бы ДРУГОЙ Python-объект `Response`, и `isinstance(resp, Response)` у потребителя разъехался бы.
#
# `websocket_test.py` на module-level делает `sys.exit(1)`, если не установлен пакет `websockets` —
# поэтому раннер грузится ТОЛЬКО лениво (в живом ws-обмене / `discover_ws`) и под `except BaseException`
# (SystemExit не наследует Exception): нет `websockets` в окружении → раннер недоступен → адаптер
# отдаёт пустой `Response()` (fail-open), но САМ модуль `authz_diff` при импорте не падает.
# ---------------------------------------------------------------------------

_WS_UPGRADE_STATUS = 101  # WebSocket handshake success (101 Switching Protocols) = «connected & got data».


def _load_websocket_test():
    """Лениво грузит раннер `scripts/websocket_test.py`, возвращает module или `None`. Ловим
    `BaseException`, т.к. раннер делает `sys.exit(1)` (→ SystemExit, вне `Exception`) при отсутствии
    пакета `websockets`. Fail-open: не загрузился → `None` (живой ws-probe недоступен). НЕ переписываем
    раннер — только оборачиваем его connection-логику."""
    try:
        return _load("authz_diff_websocket_test", os.path.join(_SCRIPTS_DIR, "websocket_test.py"))
    except BaseException:
        return None


def discover_ws(url):
    """Тонкая обёртка над `websocket_test.discover_ws(url)` (endpoint-discovery для mobile/recon-шага —
    извлекает `ws://`/`wss://` URL из HTML/JS страницы). Раннер недоступен → `[]` (fail-open). Найденные
    ws-эндпоинты заводятся как `AC-NN` и гоняются `authz_diff` через `WSResponseAdapter`."""
    wst = _load_websocket_test()
    if wst is None:
        return []
    try:
        return list(wst.discover_ws(url))
    except Exception:
        return []


def _default_ws_message(probe):
    """Дефолтный ws-фрейм, если caller не задал `message`: graphql-ws-подобный `subscribe` по
    `probe.payload`/`probe.target`. Обычно caller задаёт `message` явно (реальный subscription/query)."""
    try:
        payload = probe.payload if isinstance(getattr(probe, "payload", None), dict) else {}
        return json.dumps({"type": "subscribe", "id": "1",
                           "payload": payload or {"query": getattr(probe, "target", "")}})
    except Exception:
        return "{}"


def _normalize_ws_response(raw):
    """Сырой ws-ответ (str/bytes JSON-фрейма) → `fields` dict для `Response`. JSON-dict → поля как есть
    (для `semantic_diff`/`ownership_diff`); сырой текст ВСЕГДА кладётся в `fields["_body"]` (`_body`-
    конвенция — `classify_http` читает WAF/error-сигнатуры оттуда). Непарсибельный ответ → только
    `_body`."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    raw = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
    fields = {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            fields = dict(parsed)
    except Exception:
        pass
    fields["_body"] = raw
    return fields


def _ws_body_hash(raw):
    """Стабильный body_hash сырого ws-ответа (`semantic_diff` сравнивает `body_hash`). Ошибка → `None`."""
    try:
        if isinstance(raw, str):
            data = raw.encode("utf-8", "replace")
        elif isinstance(raw, (bytes, bytearray)):
            data = bytes(raw)
        else:
            data = str(raw).encode("utf-8", "replace")
        return hashlib.md5(data).hexdigest()
    except Exception:
        return None


def _live_ws_exchange(url, headers, message, timeout):
    """Живой ws-обмен: connect (с auth/Origin-заголовками роли) → `send(message)` → `recv` одного фрейма.
    Переиспользует `websockets`-хэндл раннера `websocket_test` (тот же `websockets.connect(...,
    additional_headers=...)` паттерн, что `test_origin_validation`/`test_auth_bypass`). Возвращает
    `(status, raw_text)`: успех → `(101, <recv>)`; recv-timeout → `(101, "")` (connected, no frame).
    Раннер/`websockets` недоступен или ошибка соединения → пробрасывает исключение (адаптер ловит →
    пустой `Response`, fail-open)."""
    import asyncio
    wst = _load_websocket_test()
    ws_mod = getattr(wst, "websockets", None) if wst is not None else None
    if ws_mod is None:
        raise RuntimeError("websockets unavailable (websocket_test runner not loadable)")

    async def _run():
        connect_kwargs = {}
        if headers:
            connect_kwargs["additional_headers"] = dict(headers)
        async with ws_mod.connect(url, **connect_kwargs) as ws:
            if message:
                await ws.send(message)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                raw = ""
            return _WS_UPGRADE_STATUS, ("" if raw is None else str(raw))

    return asyncio.run(_run())


class WSResponseAdapter(object):
    """`Context.driver`-контракт (`.probe(probe) -> Response`) поверх WebSocket. Один экземпляр = одна
    роль (свои auth-`headers` сессии). `.probe()` шлёт `message` (subscription/query-фрейм; `None` →
    `_default_ws_message(probe)`) и нормализует ws-ответ в `Response` ИЗ `runtime_harness` (module-level
    `Response` = `_rh.Response` — тот же класс, что использует `differential`/`authz_diff`, isinstance-
    дисциплина). `ws_exchange` инъектируем `(url, headers, message, timeout) -> (status, raw_text)` — для
    теста подкладывается mock БЕЗ реального соединения; дефолт `_live_ws_exchange` переиспользует
    connection-логику `websocket_test.py`. Fail-open: любая ошибка probe → пустой `Response()`
    (`differential` вернёт `None`, не крашится).

    Использование (authz-differential по WS как по HTTP):
        role_ctx = {
          "user-A": Context("user-A", WSResponseAdapter(url, headers=hdrs_A, message=sub), role="user-A"),
          "user-B": Context("user-B", WSResponseAdapter(url, headers=hdrs_B, message=sub), role="user-B"),
        }
        divs = authz_diff("wss://api.example.com/graphql-ws", role_ctx)   # BOLA по subscription-фрейму
    """

    def __init__(self, url, headers=None, message=None, ws_exchange=None, recv_timeout=5):
        self.url = url
        self.headers = headers if isinstance(headers, dict) else {}
        self.message = message
        self._ws_exchange = ws_exchange if callable(ws_exchange) else _live_ws_exchange
        self._recv_timeout = recv_timeout

    def probe(self, probe):
        try:
            msg = self.message if self.message is not None else _default_ws_message(probe)
            status, raw = self._ws_exchange(self.url, self.headers, msg, self._recv_timeout)
            return Response(status=status, fields=_normalize_ws_response(raw),
                            headers={}, body_hash=_ws_body_hash(raw))
        except Exception:
            return Response()


# ---------------------------------------------------------------------------
# 5. Provenance-from-traffic (Task T10, Plan 9 Tier E composite — cross-thread fusion ←T4, T9).
#
# T4 gave a STANDALONE create-event ledger (`object_registry.py`) whose create->access chain the
# caller had to populate MANUALLY (register each create at the moment it was observed). T9 gave a
# session-scoped traffic-archive (`traffic_archive.py`) that logs EVERY request/response independently
# of any probe. This is the fusion (Р6): re-mining the ALREADY-CAPTURED archive AUTO-populates the T4
# ledger — ZERO extra probes/network — turning a BOLA from «plausible» (I changed a random ID) into
# «proven» (I recorded who created this object and now observe a different account reading it).
#
# Two passes over the re-mined records (`traffic_archive.remine`):
#   (a) create-events (POST/PUT that mint a resource id, 2xx) -> `object_registry.register_object` into
#       `{session_dir}/object_registry.json` (the SAME ledger the caller/`run_authz_matrix` consult).
#   (b) later accesses of a registered id by a DIFFERENT account -> synthesize the ownership-baseline
#       Divergence via `ownership_diff` (accessor-self-baseline = the accessor's OWN owner-marker) and
#       run it through the EXISTING `_apply_provenance` so the hit is upgraded to a PROVEN create->access
#       chain sourced from real traffic. No new diff/registry engine — reuses ownership_diff +
#       object_registry + _apply_provenance + traffic_archive.remine.
#
# Anti-fabrication (mirrors _apply_provenance's own guards): an access to an id with NO recorded create
# yields nothing; a self-owned access (accessor == owner) yields nothing; a leaked owner-marker that
# disagrees with the registered owner is left unproven by _apply_provenance. fail-open (non-security).
# ---------------------------------------------------------------------------

_CREATE_METHODS = ("POST", "PUT")
# Actor-identity keys looked up in a record's meta first (harness sets these explicitly), then falling
# back to request auth headers (the captured session token stands in for the account identity).
_ACTOR_META_KEYS = ("actor", "account", "account_id", "actor_id", "user", "user_id")
_ACTOR_HEADER_KEYS = ("Authorization", "authorization", "X-Account", "x-account", "X-Actor", "x-actor")
# Response-body fields that carry a freshly-minted object id on a create.
_ID_FIELDS = ("id", "object_id", "_id", "uuid", "resource_id")


def _to_int(v):
    try:
        return int(v)
    except Exception:
        return None


def _read_archive(archive):
    """Re-mine a T9 traffic-archive to a list of records. Accepts a JSONL path (str -> `remine`), a
    `TrafficArchive` handle (has `.remine`), or an already-loaded records list. fail-open -> []."""
    try:
        if isinstance(archive, str):
            return _traffic_archive.remine(archive)
        if hasattr(archive, "remine"):
            return archive.remine()
        if isinstance(archive, list):
            return archive
    except Exception:
        pass
    return []


def _record_parts(rec):
    request = rec.get("request") if isinstance(rec, dict) else None
    response = rec.get("response") if isinstance(rec, dict) else None
    meta = rec.get("meta") if isinstance(rec, dict) else None
    return (request if isinstance(request, dict) else {},
            response if isinstance(response, dict) else {},
            meta if isinstance(meta, dict) else {})


def _extract_actor(request, meta):
    """Identity of the account behind a captured request: meta actor-keys first (harness-set), then a
    request auth header (the captured token stands in for identity). None if neither present."""
    for k in _ACTOR_META_KEYS:
        v = meta.get(k)
        if v not in (None, ""):
            return str(v)
    headers = request.get("headers")
    if isinstance(headers, dict):
        for hk in _ACTOR_HEADER_KEYS:
            v = headers.get(hk)
            if v not in (None, ""):
                return str(v)
    return None


def _response_body_fields(response):
    """Owner/field dict from a captured response body (dict as-is, or JSON-string parsed). Non-JSON /
    non-dict body -> {} (fail-open)."""
    body = response.get("body")
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _last_path_segment(url):
    """Concrete last path segment of a URL (query/fragment stripped, trailing slash removed). Templated
    (`{id}`) or empty segment -> None."""
    if not isinstance(url, str) or not url:
        return None
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if not path:
        return None
    seg = path.split("/")[-1]
    if not seg or (seg.startswith("{") and seg.endswith("}")):
        return None
    return seg


def _extract_created_id(request, response, method):
    """Minted resource id from a create: response-body id-field first, then a Location header segment,
    then (PUT only) the client-specified id in the request URL. None if none found."""
    fields = _response_body_fields(response)
    for k in _ID_FIELDS:
        v = fields.get(k)
        if v not in (None, ""):
            return str(v)
    headers = response.get("headers")
    if isinstance(headers, dict):
        seg = _last_path_segment(headers.get("Location") or headers.get("location"))
        if seg:
            return seg
    if method == "PUT":
        seg = _last_path_segment(request.get("url"))
        if seg:
            return seg
    return None


def _extract_owner(response):
    """Owner-marker value from a create response body (owner_id/account/email/... — the SAME marker
    keys `ownership_diff` compares on later reads). None -> caller defaults owner to the creator."""
    fields = _response_body_fields(response)
    for k in _rh._dobs._OWNER_MARKER_KEYS:
        v = fields.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _register_creates_from_traffic(records, session_dir):
    """Pass (a): register every create-event (POST/PUT minting an id, 2xx) from the re-mined records
    into `{session_dir}/object_registry.json`. Returns the list of written record dicts."""
    registered = []
    for rec in records:
        request, response, meta = _record_parts(rec)
        method = str(request.get("method", "")).upper()
        if method not in _CREATE_METHODS:
            continue
        status = _to_int(response.get("status"))
        if status is not None and not (200 <= status < 300):
            continue  # a failed create mints nothing
        obj_id = _extract_created_id(request, response, method)
        if not obj_id:
            continue
        actor = _extract_actor(request, meta)
        owner = _extract_owner(response) or actor
        written = _object_registry.register_object(
            session_dir, obj_id, created_by=actor,
            creating_request="%s %s" % (method, request.get("url", "")),
            owner=owner, timestamp=rec.get("ts"),
        )
        if written:
            registered.append(written)
    return registered


def _ownership_div_from_access(response, accessor_id, url):
    """Synthesize the ownership-baseline `Divergence` for a captured foreign read WITHOUT any new
    probe: ctx_target = the accessor's response on the victim object (body carries the owner marker);
    ctx_self = a synthetic self-baseline where every owner marker present holds the ACCESSOR's OWN id
    (what the accessor's own object would show). `ownership_diff` (REUSED, not reimplemented) fires
    `object-authz` with `owner_mismatch` when the body's owner marker != the accessor. Returns the
    Divergence, or None (no owner marker / marker already the accessor's own = legit self-read)."""
    tgt_fields = _response_body_fields(response)
    if not tgt_fields:
        return None
    present = [k for k in _rh._dobs._OWNER_MARKER_KEYS if k in tgt_fields]
    if not present:
        return None
    self_fields = {k: accessor_id for k in present}
    ctx_target = Context("traffic-access", StaticDriver(Response(fields=tgt_fields)), role="accessor")
    ctx_self = Context("accessor-self-baseline", StaticDriver(Response(fields=self_fields)),
                       role="accessor-own")
    div = ownership_diff(ctx_target, ctx_self, Probe("object-authz", url))
    if div is None or div.dclass != "object-authz":
        return None  # no mismatch (self-read) or inconclusive -> nothing to prove
    return div


def _detect_foreign_accesses(records, registry):
    """Pass (b): for each non-create record whose URL carries a registered object id accessed by a
    DIFFERENT account, build the ownership Divergence and upgrade it via `_apply_provenance`. Returns
    only the PROVEN create->access chains (`evidence["provenance_backed"]`)."""
    proven = []
    for rec in records:
        request, response, meta = _record_parts(rec)
        method = str(request.get("method", "")).upper()
        if method in _CREATE_METHODS:
            continue  # a create is not a foreign read of itself
        url = request.get("url")
        obj_rec = _object_registry.lookup_by_endpoint(registry, url)
        if not isinstance(obj_rec, dict):
            continue  # id never recorded as created this run -> no chain, no fabrication
        accessor = _extract_actor(request, meta)
        owner = obj_rec.get("owner")
        if accessor is None or owner is None or str(accessor) == str(owner):
            continue  # self-access (or unknown actor) -> not a foreign read
        div = _ownership_div_from_access(response, accessor, url)
        if div is None:
            continue
        div = _apply_provenance(div, url, registry) or div
        ev = div.evidence if isinstance(div.evidence, dict) else {}
        if ev.get("provenance_backed"):
            proven.append(div)
    return proven


def provenance_from_traffic(archive, session_dir, register=True):
    """Cross-thread fusion (Task T10 ←T4, T9): re-mine an ALREADY-CAPTURED T9 traffic-archive to
    AUTO-populate the T4 object-provenance ledger and surface PROVEN create->access BOLA chains — ZERO
    extra probes/network.

    `archive` -- a JSONL path (str), a `TrafficArchive` handle, or an already-loaded records list.
    `session_dir` -- toolkit-rooted; the create-events are written to `{session_dir}/object_registry.json`
        (the SAME ledger `authz_diff(registry=...)` / `run_authz_matrix` auto-consult).
    `register` -- True (default): run pass (a) (write create-events); False: skip registration and only
        detect foreign accesses against the EXISTING on-disk ledger.

    Returns `list[Divergence]` — only the proven create->access chains (each carries
    `evidence["provenance_backed"]=True` + `evidence["provenance_chain"]`). An archive with no
    create-event fabricates nothing (empty list, empty/untouched ledger); a self-owned access is not
    flagged. fail-open (non-security): any read/parse error -> []."""
    try:
        records = _read_archive(archive)
        if register:
            _register_creates_from_traffic(records, session_dir)
        registry = _object_registry.load_registry(session_dir)
        return _detect_foreign_accesses(records, registry)
    except Exception:
        return []
