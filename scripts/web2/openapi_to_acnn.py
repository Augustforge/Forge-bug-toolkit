#!/usr/bin/env python3
"""
openapi_to_acnn — полу-автоматизация фазы P-AM web2-ханта (FDE План 5).

Из публичной OpenAPI/Swagger v2/v3 схемы, GraphQL introspection-ответа ИЛИ `.js.map`
source-map бандла генерит скелет инвариантов `AC-NN` (12-колоночный формат
`system_model_web_template.md`) + Endpoint Interest Score (`endpoint_scoremap.md`).
Агент потом достраивает модель руками.

Только stdlib, детерминированно, без сети.

Usage:
    py -3 -X utf8 openapi_to_acnn.py --schema api.json --session-dir sessions/example.com
    py -3 -X utf8 openapi_to_acnn.py --schema-kind graphql --schema introspection.json --session-dir ...
    py -3 -X utf8 openapi_to_acnn.py --sourcemap app.js.map --session-dir ...
"""

import argparse
import json
import os
import re

# --------------------------------------------------------------------------
# Канонические оси web2/`AC-` профиля (system_model_web_template.md:169-177).
# attack_path_hint ВСЕГДА одна из них — это то, что летит прямо в колонку «Ось».
# --------------------------------------------------------------------------
AXIS_OBJECT_AUTHZ = "object-authz"
AXIS_FUNCTION_AUTHZ = "function-authz"
AXIS_AUTH_INTEGRITY = "auth-integrity"
AXIS_TENANT_ISOLATION = "tenant-isolation"
AXIS_INPUT_SINK = "input-sink"
AXIS_BUSINESS_LOGIC = "business-logic"

# Доминирующий weighted-сигнал -> ось (используется, когда нет прямого object-id /
# admin-verb совпадения — приоритет см. endpoint_score).
_SIGNAL_AXIS = {
    "unauth-write": AXIS_FUNCTION_AUTHZ,
    "open-introspection": AXIS_FUNCTION_AUTHZ,
    "verb-bypass-admin": AXIS_FUNCTION_AUTHZ,
    "reflected-cors": AXIS_AUTH_INTEGRITY,
    "sensitive-keyword": AXIS_OBJECT_AUTHZ,
    "schema-leak": AXIS_INPUT_SINK,
}

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE", "MUTATION"}

_OBJECT_ID_RE = re.compile(r"(\{[\w]*id[\w]*\}|:[\w]*id[\w]*\b)", re.IGNORECASE)
_ADMIN_VERB_RE = re.compile(r"(?:^|/)(admin|internal)(?:/|$)", re.IGNORECASE)
_SENSITIVE_KW_RE = re.compile(r"\b(user|account|payment|admin|export|token)s?\b", re.IGNORECASE)


# ==========================================================================
# 1. parse_schema — OpenAPI/Swagger v2/v3 ИЛИ GraphQL introspection -> дескрипторы
# ==========================================================================

def parse_schema(schema, kind="openapi"):
    """OpenAPI/Swagger (`paths`) ИЛИ GraphQL introspection (`__schema.types`) ->
    список {method, path, params, auth_required, roles_hint}."""
    if not isinstance(schema, dict):
        return []
    if kind == "graphql":
        return _parse_graphql(schema)
    return _parse_openapi(schema)


def _parse_openapi(schema):
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        return []
    global_security = schema.get("security")
    out = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        path_level_params = item.get("parameters") if isinstance(item.get("parameters"), list) else []
        for method, op in item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            params = []
            for p in path_level_params + (op.get("parameters") or []):
                if isinstance(p, dict) and p.get("name"):
                    params.append(p["name"])
            security = op.get("security", global_security)
            auth_required = None if security is None else bool(security)
            roles_hint = None
            if _ADMIN_VERB_RE.search(path):
                roles_hint = AXIS_FUNCTION_AUTHZ
            elif _OBJECT_ID_RE.search(path) or "{" in path:
                roles_hint = AXIS_OBJECT_AUTHZ
            out.append({
                "method": method.upper(),
                "path": path,
                "params": params,
                # Task T3 (Plan 9): top-level requestBody property names -- needed for the relational
                # extractor to spot webhook/callback payloads carrying EMBEDDED foreign IDs (a foreign
                # id in a POST body is a producer of that resource's ids, just like a list endpoint).
                "body_fields": _extract_body_fields(op),
                "auth_required": auth_required,
                "roles_hint": roles_hint,
            })
    return out


def _extract_body_fields(op):
    """Top-level property names of an OpenAPI operation's requestBody schema (all media types
    merged). Only names -- no type walking. Empty list on any missing/malformed piece (fail-open).
    Used by the relational extractor to detect webhook/callback payloads carrying foreign IDs."""
    out = []
    try:
        rb = op.get("requestBody")
        content = rb.get("content") if isinstance(rb, dict) else None
        if not isinstance(content, dict):
            return out
        for media in content.values():
            schema = media.get("schema") if isinstance(media, dict) else None
            props = schema.get("properties") if isinstance(schema, dict) else None
            if isinstance(props, dict):
                out.extend(k for k in props.keys() if isinstance(k, str))
    except Exception:
        pass
    return out


def _parse_graphql(schema):
    root = schema.get("__schema")
    if not isinstance(root, dict):
        root = schema.get("data", {}).get("__schema") if isinstance(schema.get("data"), dict) else None
    if not isinstance(root, dict):
        return []
    types = root.get("types") if isinstance(root.get("types"), list) else []
    query_type = (root.get("queryType") or {}).get("name") if isinstance(root.get("queryType"), dict) else "Query"
    mutation_type = (root.get("mutationType") or {}).get("name") if isinstance(root.get("mutationType"), dict) else "Mutation"

    out = []
    saw_operation_type = False
    for t in types:
        if not isinstance(t, dict):
            continue
        tname = t.get("name")
        if tname == query_type:
            op_method = "QUERY"
        elif tname == mutation_type:
            op_method = "MUTATION"
        else:
            continue
        saw_operation_type = True
        for field in t.get("fields") or []:
            if not isinstance(field, dict) or not field.get("name"):
                continue
            fname = field["name"]
            args = [a.get("name") for a in (field.get("args") or []) if isinstance(a, dict) and a.get("name")]
            roles_hint = AXIS_FUNCTION_AUTHZ if _ADMIN_VERB_RE.search(fname) or re.search(r"(?i)admin", fname) else None
            out.append({
                "method": op_method,
                "path": "/graphql#" + fname,
                "params": args,
                "auth_required": None,
                "roles_hint": roles_hint,
            })

    # Само наличие валидного introspection-ответа = introspection открыт на /graphql.
    if saw_operation_type:
        out.append({
            "method": "QUERY",
            "path": "/graphql",
            "params": [],
            "auth_required": False,
            "roles_hint": None,
            "open_introspection": True,
        })
    return out


# ==========================================================================
# 2. extract_from_sourcemap — .js.map -> endpoints (fake-detect + tiered regex + dedup)
# ==========================================================================

def extract_from_sourcemap(js_map_text):
    """`.js.map` -> [{path, method, tier}]. Пустой список на SPA-заглушку / битый JSON."""
    if not js_map_text or not isinstance(js_map_text, str):
        return []

    head = js_map_text[:80].lstrip()
    head_lower = head.lower()
    if head_lower.startswith("<!doctype") or head_lower.startswith("<html"):
        return []
    if not head.startswith("{"):
        return []

    try:
        data = json.loads(js_map_text)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []

    sources_content = data.get("sourcesContent")
    if not isinstance(sources_content, list):
        return []
    blob = "\n".join(s for s in sources_content if isinstance(s, str))
    if not blob:
        return []

    found = {}  # normalized path -> {"path", "method", "tier"}

    def add(raw_path, tier):
        raw_path = raw_path.strip()
        if not raw_path or raw_path == "/":
            return
        norm = _normalize_path(raw_path)
        cur = found.get(norm)
        if cur is None or tier < cur["tier"]:
            found[norm] = {"path": norm, "method": None, "tier": tier}

    # Tier-1: строгий /api/... или /v\d+/...
    for m in re.finditer(r"(/api/[A-Za-z0-9_\-/{}:.$]+)", blob):
        add(m.group(1), 1)
    for m in re.finditer(r"(/v\d+/[A-Za-z0-9_\-/{}:.$]+)", blob):
        add(m.group(1), 1)

    # Tier-2: любой quoted relative-path
    for m in re.finditer(r"""["'](/[a-z][\w/\-]*)["']""", blob):
        add(m.group(1), 2)

    # Tier-3: template-literal (backtick, может содержать ${...})
    for m in re.finditer(r"`(/[\w\-/${}.]+)`", blob):
        add(m.group(1), 3)

    return sorted(found.values(), key=lambda e: (e["tier"], e["path"]))


def _normalize_path(p):
    """Числовые/UUID/шаблонные сегменты -> /{id} для дедупа."""
    p = re.sub(r"/\$\{[^{}]+\}", "/{id}", p)
    p = re.sub(r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "/{id}", p)
    p = re.sub(r"/:[A-Za-z_][A-Za-z0-9_]*", "/{id}", p)
    p = re.sub(r"/\{[^{}/]+\}", "/{id}", p)
    p = re.sub(r"/\d+(?=/|$)", "/{id}", p)
    p = re.sub(r"/{2,}", "/", p)
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


# ==========================================================================
# 3. endpoint_score — Endpoint Interest Score 0-100 + attack_path_hint
# ==========================================================================

def endpoint_score(ep):
    """0-100 score + attack_path_hint (одна из 6 канонических AC-осей)."""
    method = str(ep.get("method") or "").upper()
    path = str(ep.get("path") or "")
    auth_required = ep.get("auth_required")

    signals = {}
    if method in _WRITE_METHODS and auth_required is False:
        signals["unauth-write"] = 40
    if ep.get("open_introspection"):
        signals["open-introspection"] = 35
    admin_verb = bool(_ADMIN_VERB_RE.search(path))
    if admin_verb:
        signals["verb-bypass-admin"] = 30
    if ep.get("cors_reflected"):
        signals["reflected-cors"] = 25
    if _SENSITIVE_KW_RE.search(path):
        signals["sensitive-keyword"] = 20
    if ep.get("schema_leak"):
        signals["schema-leak"] = 20

    score = min(sum(signals.values()), 100)

    object_id = bool(_OBJECT_ID_RE.search(path))
    if object_id:
        hint = AXIS_OBJECT_AUTHZ
    elif admin_verb:
        hint = AXIS_FUNCTION_AUTHZ
    elif signals:
        dominant = max(signals, key=signals.get)
        hint = _SIGNAL_AXIS.get(dominant, AXIS_BUSINESS_LOGIC)
    else:
        hint = AXIS_BUSINESS_LOGIC

    return score, hint


# ==========================================================================
# 4. to_acnn_skeleton — score>=70 -> AC-NN скелет-строки (12 колонок)
# ==========================================================================

def to_acnn_skeleton(endpoints):
    """Для endpoint'ов со score>=70 -> строки 12-колоночного AC-NN формата.
    Статус = {TODO} (скелет; gate НЕ считает за реальный инвариант).

    A7b (Волна 1 2026-08-08): раньше колонки `Источник`/`component:` были заглушкой (`_source_label`
    в Источник, component = ""), и вычисленная schema producer->consumer связь ВЫБРАСЫВАЛАСЬ ровно
    перед теми двумя колонками, что нужны composition-графу (A7). Теперь для consumer-эндпоинта
    мульти-хоп-связи кладём `producer -> consumer` в `Источник`/`component:` → composition_map строит
    ребро producer->consumer автоматически (webhook/nested/export-хопы — самые незаметные классы).
    Прямой-ID эндпоинт (нет producer'а) → старое поведение (schema-label в Источник, component пуст)."""
    relations = build_relations(endpoints)
    # consumer-label -> producer-label (первый; несколько producer'ов на один consumer редки, берём топ)
    producer_of = {}
    for rel in relations:
        producer_of.setdefault(rel["consumer"], rel["producer"])
    rows = []
    n = 0
    for ep in endpoints or []:
        score, hint = endpoint_score(ep)
        method = ep.get("method") or ""
        path = ep.get("path") or ""
        endpoint_label = (method + " " + path).strip()
        producer = producer_of.get(endpoint_label)
        # A7b: multi-hop consumer = высокоценный deep-target, которого плоский score НЕ ловит (reachability
        # ≠ высокий флаг). Эмитим строку, если score>=70 ИЛИ эндпоинт — consumer в producer->consumer связи.
        if score < 70 and not producer:
            continue
        n += 1
        ac_id = "AC-I%02d" % n
        if producer:
            source = producer                 # граница-источник foreign-id (producer)
            component = endpoint_label         # граница-потребитель (consumer) = это ребро A7
            if score < 70:
                hint = (hint + "; " if hint else "") + "multi-hop consumer (producer->consumer reachability)"
        else:
            source = _source_label(ep)         # прямой-ID / не multi-hop → schema-label, component пуст
            component = ""
        fields = [ac_id, "", "", hint, source, component, "", "{TODO}", endpoint_label, "", "cold", ""]
        rows.append("| " + " | ".join(fields) + " |")
    return "\n".join(rows)


def _source_label(ep):
    if "tier" in ep:
        return "source-map"
    if str(ep.get("method") or "").upper() in ("QUERY", "MUTATION"):
        return "GraphQL"
    return "OpenAPI"


# ==========================================================================
# 5. write_scoremap — endpoint_scoremap.md в toolkit-rooted session_dir
# ==========================================================================

def write_scoremap(endpoints, session_dir):
    """Пишет `{session_dir}/endpoint_scoremap.md` (session_dir — toolkit-rooted,
    ПЕРЕДАЁТСЯ, не хардкодится). Возвращает путь записанного файла."""
    os.makedirs(session_dir, exist_ok=True)
    out_path = os.path.join(session_dir, "endpoint_scoremap.md")

    lines = ["| endpoint | score | attack_path_hint | → AC-NN? |", "|---|---|---|---|"]
    for ep in endpoints or []:
        score, hint = endpoint_score(ep)
        method = ep.get("method") or ""
        path = ep.get("path") or ""
        endpoint_label = (method + " " + path).strip()
        acnn_flag = "Y" if score >= 70 else ""
        lines.append("| %s | %d | %s | %s |" % (endpoint_label, score, hint, acnn_flag))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


# ==========================================================================
# 6. Relational / indirect IDOR extractor (Task T3, Plan 9 hunter-parity).
#
# Direct-ID swap ("change the {id} in /orders/{id}") is the shallow authz probe. The DEEP probe is
# MULTI-HOP: endpoint P *produces* a foreign resource-id (a list/nested/export response, or a webhook
# payload that embeds someone else's id) which endpoint C then *consumes* as a path/query param. If C
# never re-checks ownership, an attacker who never guesses an id -- they READ it out of P's response --
# reaches C's object cross-account. This extractor runs over the parsed openapi_to_acnn descriptors,
# builds producer->consumer relations by matching resource names, and yields the consumer endpoints as
# multi-hop authz probe targets (fed straight into authz_diff.run_authz_matrix).
#
# Pure stdlib, deterministic, no network -- same contract as the rest of this module. Fail-open:
# malformed descriptor -> skipped, never raises.
# ==========================================================================

# Typed foreign-id token: "userId" / "user_id" / "orderID" -> resource "user"/"order".  Bare "id"
# does NOT match (that is the DIRECT id; its resource comes from the preceding path segment instead).
_FK_TOKEN_RE = re.compile(r"^(?P<res>[A-Za-z][A-Za-z0-9]*?)(?:_id|Id|_ID|ID)$")
_BARE_ID_RE = re.compile(r"^(id|ID|Id)$")
_PATH_PARAM_RE = re.compile(r"\{([^{}/]+)\}|:([A-Za-z_][A-Za-z0-9_]*)")
_WEBHOOK_SEG_RE = re.compile(r"(?i)^(webhooks?|callbacks?|hooks?)$")
_EXPORT_SEG_RE = re.compile(r"(?i)^exports?$")


def _singularize(seg):
    """Naive plural->singular for resource matching ('orders'->'order', 'categories'->'category',
    'addresses'->'address'). Lowercased. Not linguistically complete -- just enough to match a
    collection segment against a typed id token."""
    s = str(seg or "").lower()
    if len(s) > 3 and s.endswith("ies"):
        return s[:-3] + "y"
    if len(s) > 3 and (s.endswith("ses") or s.endswith("xes") or s.endswith("ches") or s.endswith("shes")):
        return s[:-2]
    if len(s) > 1 and s.endswith("s") and not s.endswith("ss"):
        return s[:-1]
    return s


def _fk_resource(tok):
    """Foreign-id token -> singular resource name, or None if `tok` is not a typed foreign id."""
    if not isinstance(tok, str):
        return None
    m = _FK_TOKEN_RE.match(tok)
    if not m or not m.group("res"):
        return None
    return _singularize(m.group("res"))


def _path_segments(path):
    return [s for s in str(path or "").split("/") if s]


def _endpoint_label(ep):
    method = str(ep.get("method") or "").strip()
    path = str(ep.get("path") or "").strip()
    return (method + " " + path).strip()


def _consumer_resources(ep):
    """Resources this endpoint CONSUMES via a foreign id (path param / query|body filter param).
    Bare `{id}`/`:id` in a path resolves its resource from the preceding collection segment
    ('/orders/{id}' -> 'order'). Returns a set of (resource, hop_kind) tuples."""
    out = set()
    path = str(ep.get("path") or "")
    segs = _path_segments(path)
    # path params (positional -> can look back a segment for the bare-id case)
    for idx, seg in enumerate(segs):
        pm = _PATH_PARAM_RE.match(seg)
        if not pm:
            continue
        tok = pm.group(1) or pm.group(2) or ""
        res = _fk_resource(tok)
        if res:
            out.add((res, "path-param"))
        elif _BARE_ID_RE.match(tok) and idx > 0:
            prev = segs[idx - 1]
            if not _PATH_PARAM_RE.match(prev):
                out.add((_singularize(prev), "path-param"))
    # query / body params that are typed foreign ids -> list/filter consumer
    for p in (ep.get("params") or []):
        res = _fk_resource(p)
        if res:
            out.add((res, "list-filter"))
    return out


def _producer_resources(ep):
    """Resources this endpoint PRODUCES foreign ids for. Signals: list (GET/QUERY ending in a plural
    collection segment), nested (a parent id-param followed by more path), export, webhook/callback
    (path segment OR a foreign id embedded in the request body). Returns set of (resource, hop_kind)."""
    out = set()
    method = str(ep.get("method") or "").upper()
    path = str(ep.get("path") or "")
    segs = _path_segments(path)
    read_like = method in ("GET", "QUERY", "") or method not in _WRITE_METHODS

    # webhook / callback -- foreign ids embedded in the payload it carries/delivers.
    is_webhook = any(_WEBHOOK_SEG_RE.match(s) for s in segs)
    body_fk = set()
    for f in (ep.get("body_fields") or []):
        res = _fk_resource(f)
        if res:
            body_fk.add(res)
    if is_webhook or body_fk:
        for res in body_fk:
            out.add((res, "webhook"))
        # webhook path with no typed body field still produces the resource named in its path tail
        if is_webhook and not body_fk:
            tail = [s for s in segs if not _PATH_PARAM_RE.match(s) and not _WEBHOOK_SEG_RE.match(s)]
            if tail:
                out.add((_singularize(tail[-1]), "webhook"))

    # export -- the resource adjacent to the 'export' segment.
    for idx, seg in enumerate(segs):
        if _EXPORT_SEG_RE.match(seg):
            for j in range(idx - 1, -1, -1):
                if not _PATH_PARAM_RE.match(segs[j]):
                    out.add((_singularize(segs[j]), "export"))
                    break

    # list -- collection read whose last segment is a plural non-param noun.
    if read_like and segs:
        last = segs[-1]
        if not _PATH_PARAM_RE.match(last) and not _WEBHOOK_SEG_RE.match(last) and not _EXPORT_SEG_RE.match(last):
            out.add((_singularize(last), "list"))

    # nested -- a parent id-param with further path after it: the PARENT resource is a relational
    # pivot (swap the parent id to reach a sibling's children).
    for idx, seg in enumerate(segs[:-1]):
        pm = _PATH_PARAM_RE.match(seg)
        if pm:
            tok = pm.group(1) or pm.group(2) or ""
            res = _fk_resource(tok)
            if not res and _BARE_ID_RE.match(tok) and idx > 0 and not _PATH_PARAM_RE.match(segs[idx - 1]):
                res = _singularize(segs[idx - 1])
            if res:
                out.add((res, "nested"))
    return out


def build_relations(endpoints):
    """Producer->consumer relations across `endpoints`, matched by resource name. Returns a list of
    dicts {resource, producer, consumer, producer_hop, consumer_hop} (producer != consumer endpoint).
    This is the multi-hop reachability graph beyond direct-ID swap."""
    producers = {}   # resource -> list of (label, hop_kind)
    consumers = {}   # resource -> list of (label, hop_kind)
    for ep in (endpoints or []):
        if not isinstance(ep, dict):
            continue
        label = _endpoint_label(ep)
        for res, hop in _producer_resources(ep):
            producers.setdefault(res, []).append((label, hop))
        for res, hop in _consumer_resources(ep):
            consumers.setdefault(res, []).append((label, hop))

    relations = []
    for res in sorted(set(producers) & set(consumers)):
        for c_label, c_hop in consumers[res]:
            for p_label, p_hop in producers[res]:
                if p_label == c_label:
                    continue  # a single endpoint that both lists and takes an id -> not a cross-hop
                relations.append({
                    "resource": res,
                    "producer": p_label,
                    "producer_hop": p_hop,
                    "consumer": c_label,
                    "consumer_hop": c_hop,
                })
    return relations


def multihop_endpoints(endpoints):
    """Consumer endpoint labels reachable via a relational (multi-hop) foreign id -- the deep authz
    probe set to feed authz_diff.run_authz_matrix (beyond the direct-ID-swap surface). Sorted, deduped.
    An endpoint whose only id has NO producer elsewhere is direct-only and is NOT included (no false
    relational claim)."""
    seen = set()
    for rel in build_relations(endpoints):
        seen.add(rel["consumer"])
    return sorted(seen)


def run_multihop_authz(endpoints, role_contexts, session_dir, **kw):
    """A7b (Волна 1 2026-08-08): ИСПОЛНЯЕТ обещание докстринга выше — реально зовёт
    `authz_diff.run_authz_matrix` на МУЛЬТИ-ХОП consumer-эндпоинтах (deep authz-проба сверх
    direct-ID-swap). Раньше вызова НЕ было (греп подтвердил — неисполненное обещание). Lazy-import
    authz_diff (тяжёлые зависимости не тянем на уровне модуля). Нет multi-hop эндпоинтов → None
    (нечего пробить, файл не пишем). Возвращает путь authz_matrix.md либо None."""
    eps = multihop_endpoints(endpoints)
    if not eps:
        return None
    import importlib.util as _ilu
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "authz_diff.py")
    _s = _ilu.spec_from_file_location("authz_diff", _p)
    _ad = _ilu.module_from_spec(_s)
    _s.loader.exec_module(_ad)
    return _ad.run_authz_matrix(eps, role_contexts, session_dir, **kw)


# ==========================================================================
# Orchestrator (граница "нет схемы и нет source-map") + CLI
# ==========================================================================

NO_SCHEMA_RESULT = "RESULT: no-schema — P-AM manual from js_mining/passive-crawl"


def process(schema=None, kind="openapi", sourcemap_text=None, session_dir=None):
    """Склеивает 1-5: нет schema и нет sourcemap -> boundary RESULT: no-schema.
    Иначе парсит доступные источники, пишет scoremap (если дан session_dir) и
    возвращает summary + AC-NN скелет."""
    if not schema and not sourcemap_text:
        return NO_SCHEMA_RESULT

    endpoints = []
    if schema:
        endpoints.extend(parse_schema(schema, kind=kind))
    if sourcemap_text:
        endpoints.extend(extract_from_sourcemap(sourcemap_text))

    skeleton = to_acnn_skeleton(endpoints)
    if session_dir:
        scoremap_path = write_scoremap(endpoints, session_dir)
        summary = "RESULT: ok — %d endpoints, scoremap=%s" % (len(endpoints), scoremap_path)
    else:
        summary = "RESULT: ok — %d endpoints (no session_dir, scoremap not written)" % len(endpoints)
    return summary + ("\n" + skeleton if skeleton else "")


def _main():
    ap = argparse.ArgumentParser(description="OpenAPI/GraphQL/source-map -> AC-NN skeleton + endpoint_scoremap")
    ap.add_argument("--schema", help="path to OpenAPI/Swagger or GraphQL introspection JSON")
    ap.add_argument("--schema-kind", default="openapi", choices=["openapi", "graphql"])
    ap.add_argument("--sourcemap", help="path to .js.map file")
    ap.add_argument("--session-dir", help="toolkit-rooted session dir, e.g. sessions/example.com")
    args = ap.parse_args()

    schema = None
    if args.schema:
        with open(args.schema, "r", encoding="utf-8") as f:
            schema = json.load(f)
    sourcemap_text = None
    if args.sourcemap:
        with open(args.sourcemap, "r", encoding="utf-8") as f:
            sourcemap_text = f.read()

    print(process(schema=schema, kind=args.schema_kind, sourcemap_text=sourcemap_text, session_dir=args.session_dir))


if __name__ == "__main__":
    _main()
