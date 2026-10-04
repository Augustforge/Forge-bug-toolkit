# -*- coding: utf-8 -*-
"""Selftest for openapi_to_acnn.py (FDE Plan 5, Task 5).

Proves:
 (1) parse_schema(openapi v3) -> 2 descriptors for a mini fixture (GET /users/{id}, POST /admin/export).
 (2) endpoint_score: /users/{id} -> hint object-authz (object-id in path wins priority); /admin/export
     (unauth write on an admin path) -> score >=70 + hint function-authz.
 (3) extract_from_sourcemap: valid .js.map (sourcesContent containing /api/orders/<id>) yields
     non-empty, tier-1-tagged, deduped-by-{id} endpoints; SPA <!DOCTYPE html> stub -> [].
 (4) to_acnn_skeleton: rows start with "| AC-I", have exactly 12 pipe-delimited columns, and the
     Статус column is the literal skeleton sentinel "{TODO}".
 (5) parse_schema(kind="graphql") on an introspection fixture -> non-empty endpoint list.
 (6) process() boundary: no schema AND no sourcemap -> literal "RESULT: no-schema" line.
 (7) write_scoremap(endpoints, session_dir=<tmp toolkit-rooted>) writes to EXACTLY
     os.path.join(session_dir, "endpoint_scoremap.md") — never CWD-relative. Cleaned up in finally.

Run: py -3 -X utf8 scripts/web2/openapi_to_acnn_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import json
import shutil
import tempfile
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
WEB2_DIR = os.path.join(ROOT, "scripts", "web2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


ac = _load("openapi_to_acnn", os.path.join(WEB2_DIR, "openapi_to_acnn.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


# ── CASE 1: parse_schema(openapi v3) — 2 endpoints ──────────────────────────────────────────
MINI_OPENAPI_V3 = {
    "openapi": "3.0.0",
    "security": [],  # global: no default auth scheme (public-by-default fixture)
    "paths": {
        "/users/{id}": {
            "get": {
                "summary": "Get user by id",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "OK"}},
            }
        },
        "/admin/export": {
            "post": {
                "summary": "Export all user data (admin)",
                "responses": {"200": {"description": "OK"}},
            }
        },
    },
}

descriptors = ac.parse_schema(MINI_OPENAPI_V3, kind="openapi")
check("case1a parse_schema(openapi v3): returns 2 descriptors for the 2-endpoint fixture",
      len(descriptors) == 2, "got=%r" % (descriptors,))
by_path = {d["path"]: d for d in descriptors}
check("case1b parse_schema: GET /users/{id} descriptor present with method GET",
      by_path.get("/users/{id}", {}).get("method") == "GET")
check("case1c parse_schema: POST /admin/export descriptor present with method POST",
      by_path.get("/admin/export", {}).get("method") == "POST")

# ── CASE 2: endpoint_score + attack_path_hint ────────────────────────────────────────────────
users_ep = by_path["/users/{id}"]
admin_ep = by_path["/admin/export"]

score_users, hint_users = ac.endpoint_score(users_ep)
score_admin, hint_admin = ac.endpoint_score(admin_ep)

check("case2a endpoint_score(/users/{id}): hint == object-authz (object-id-in-path priority)",
      hint_users == "object-authz", "hint=%r score=%r" % (hint_users, score_users))
check("case2b endpoint_score(/users/{id}): score is elevated (sensitive-keyword 'user' matched, >0)",
      score_users > 0, "score=%r" % (score_users,))
check("case2c endpoint_score(/admin/export): hint == function-authz (admin-verb path)",
      hint_admin == "function-authz", "hint=%r score=%r" % (hint_admin, score_admin))
check("case2d endpoint_score(/admin/export): score >=70 (unauth-write 40 + admin-path 30 + sensitive-kw 20, capped 100)",
      score_admin >= 70, "score=%r" % (score_admin,))

# ── CASE 3: extract_from_sourcemap ───────────────────────────────────────────────────────────
VALID_MAP = json.dumps({
    "version": 3,
    "sources": ["app.js"],
    "sourcesContent": [
        "fetch('/api/orders/123'); fetch('/api/orders/456'); "
        "axios.get(\"/settings\"); fetch(`/api/orders/${id}/items`);"
    ],
})
sm_endpoints = ac.extract_from_sourcemap(VALID_MAP)
check("case3a extract_from_sourcemap(valid .js.map): non-empty endpoint list",
      len(sm_endpoints) > 0, "got=%r" % (sm_endpoints,))

orders_entries = [e for e in sm_endpoints if e["path"] == "/api/orders/{id}"]
check("case3b extract_from_sourcemap: /api/orders/123 and /api/orders/456 dedup into ONE {id}-normalized entry",
      len(orders_entries) == 1, "got=%r (all=%r)" % (orders_entries, sm_endpoints))
check("case3c extract_from_sourcemap: /api/orders/{id} entry tagged tier-1 (strict /api/... pattern)",
      bool(orders_entries) and orders_entries[0]["tier"] == 1, "got=%r" % (orders_entries,))
check("case3d extract_from_sourcemap: normalized dedup path collapses numeric segment to {id}",
      bool(orders_entries) and "{id}" in orders_entries[0]["path"], "got=%r" % (orders_entries,))
check("case3f extract_from_sourcemap: distinct sibling endpoint /api/orders/{id}/items also present (NOT merged)",
      any(e["path"] == "/api/orders/{id}/items" for e in sm_endpoints), "all=%r" % (sm_endpoints,))

FAKE_MAP = "<!DOCTYPE html><html><head><title>SPA shell</title></head><body></body></html>"
check("case3e extract_from_sourcemap: SPA <!DOCTYPE html> stub -> [] (fake-detect)",
      ac.extract_from_sourcemap(FAKE_MAP) == [])

# ── CASE 4: to_acnn_skeleton — 12-column skeleton rows, Статус == {TODO} ────────────────────
skeleton = ac.to_acnn_skeleton(descriptors)
skeleton_lines = [ln for ln in skeleton.splitlines() if ln.strip()]
check("case4a to_acnn_skeleton: at least one row generated (score>=70 endpoint present)",
      len(skeleton_lines) >= 1, "skeleton=%r" % (skeleton,))
check("case4b to_acnn_skeleton: row starts with '| AC-I'",
      all(ln.startswith("| AC-I") for ln in skeleton_lines), "lines=%r" % (skeleton_lines,))

for ln in skeleton_lines:
    fields = [f.strip() for f in ln.split("|")[1:-1]]
    check("case4c to_acnn_skeleton: row %r has exactly 12 pipe-delimited columns" % (ln,),
          len(fields) == 12, "fields=%r (n=%d)" % (fields, len(fields)))
    check("case4d to_acnn_skeleton: row %r Статус column (8th field) == literal '{TODO}'" % (ln,),
          len(fields) >= 8 and fields[7] == "{TODO}", "fields=%r" % (fields,))

# ── CASE 5: GraphQL introspection ────────────────────────────────────────────────────────────
GRAPHQL_INTROSPECTION = {
    "__schema": {
        "queryType": {"name": "Query"},
        "mutationType": {"name": "Mutation"},
        "types": [
            {"name": "Query", "fields": [
                {"name": "getUser", "args": [{"name": "id"}]},
                {"name": "adminListUsers", "args": []},
            ]},
            {"name": "Mutation", "fields": [
                {"name": "deleteAccount", "args": [{"name": "id"}]},
            ]},
            {"name": "User", "fields": [{"name": "email", "args": []}]},
        ],
    }
}
gql_endpoints = ac.parse_schema(GRAPHQL_INTROSPECTION, kind="graphql")
check("case5a parse_schema(kind=graphql): non-empty endpoint list from introspection fixture",
      len(gql_endpoints) > 0, "got=%r" % (gql_endpoints,))
check("case5b parse_schema(kind=graphql): Query/Mutation fields captured (getUser, deleteAccount)",
      any(e["path"].endswith("#getUser") for e in gql_endpoints)
      and any(e["path"].endswith("#deleteAccount") and e["method"] == "MUTATION" for e in gql_endpoints),
      "got=%r" % (gql_endpoints,))
check("case5c parse_schema(kind=graphql): non-operation type 'User' fields NOT captured",
      not any(e["path"].endswith("#email") for e in gql_endpoints), "got=%r" % (gql_endpoints,))

# ── CASE 6: process() boundary — no schema and no sourcemap ────────────────────────────────
no_schema_result = ac.process()
check("case6a process(): no schema + no sourcemap -> literal RESULT: no-schema boundary line",
      no_schema_result == ac.NO_SCHEMA_RESULT, "got=%r" % (no_schema_result,))
check("case6b process(): boundary string matches brief wording exactly",
      no_schema_result == "RESULT: no-schema — P-AM manual from js_mining/passive-crawl",
      "got=%r" % (no_schema_result,))

# ── CASE 7: write_scoremap — writes to EXACT session_dir, not CWD ──────────────────────────
TMP_SESSION_DIR = os.path.join(ROOT, "sessions", "_selftest_tmp_web2_acnn")
try:
    if os.path.exists(TMP_SESSION_DIR):
        shutil.rmtree(TMP_SESSION_DIR)
    written_path = ac.write_scoremap(descriptors, session_dir=TMP_SESSION_DIR)
    expected_path = os.path.join(TMP_SESSION_DIR, "endpoint_scoremap.md")
    check("case7a write_scoremap: returns exactly os.path.join(session_dir, 'endpoint_scoremap.md')",
          written_path == expected_path, "got=%r expected=%r" % (written_path, expected_path))
    check("case7b write_scoremap: file physically exists at that exact path",
          os.path.isfile(expected_path), "path=%r" % (expected_path,))
    check("case7c write_scoremap: nothing written under bare CWD-relative sessions/ (toolkit-rooted only)",
          not os.path.exists(os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_acnn")))
    with open(expected_path, "r", encoding="utf-8") as f:
        content = f.read()
    check("case7d write_scoremap: scoremap table header present",
          "attack_path_hint" in content and "AC-NN?" in content, "content=%r" % (content,))
    check("case7e write_scoremap: high-score /admin/export row flagged Y for -> AC-NN?",
          any(ln.startswith("| POST /admin/export |") and ln.rstrip("|").rstrip().endswith("Y")
              for ln in content.splitlines()),
          "content=%r" % (content,))
finally:
    shutil.rmtree(TMP_SESSION_DIR, ignore_errors=True)
    stray = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_acnn")
    if os.path.exists(stray):
        shutil.rmtree(stray, ignore_errors=True)

# ── CASE 8 (A7b, Волна 1): openapi → composition авто-наполнение (Источник/component из relations) ──
# producer (GET /users list) + consumer (GET /users/{id}) → relation resource "user". Раньше skeleton
# выбрасывал связь: source=schema-label, component="". Теперь consumer-строка несёт producer->consumer.
A7B_EPS = [
    {"method": "GET", "path": "/users", "params": []},            # producer (list) → "user"
    {"method": "GET", "path": "/users/{id}", "params": []},       # consumer (bare id → "user")
]
_rels = ac.build_relations(A7B_EPS)
check("case8a A7b build_relations: producer->consumer для resource 'user' построен",
      any(r["resource"] == "user" and r["producer"] == "GET /users"
          and r["consumer"] == "GET /users/{id}" for r in _rels), "got=%r" % (_rels,))
_mh = ac.multihop_endpoints(A7B_EPS)
check("case8b A7b multihop_endpoints: consumer в наборе deep-probe",
      "GET /users/{id}" in _mh, "got=%r" % (_mh,))
_a7b_skel = ac.to_acnn_skeleton(A7B_EPS)
_consumer_rows = [ln for ln in _a7b_skel.splitlines() if "GET /users/{id}" in ln]
check("case8c A7b to_acnn_skeleton: consumer-строка несёт непустые Источник(4)+component(5) = producer->consumer",
      bool(_consumer_rows) and (lambda c: c[4] == "GET /users" and c[5] == "GET /users/{id}")(
          [x.strip() for x in _consumer_rows[0].strip().strip("|").split("|")]),
      "rows=%r" % (_consumer_rows,))
# А7b: run_multihop_authz РЕАЛЬНО зовёт run_authz_matrix на multihop-эндпоинтах (исполнение обещания).
A7B_SESSION = os.path.join(ROOT, "sessions", "_selftest_tmp_web2_a7b")
try:
    if os.path.exists(A7B_SESSION):
        shutil.rmtree(A7B_SESSION)
    _roles = {"user-A": {"status": 200, "fields": {}}, "user-B": {"status": 200, "fields": {}}}
    _mpath = ac.run_multihop_authz(A7B_EPS, _roles, A7B_SESSION)
    check("case8d A7b run_multihop_authz: реально вызывает run_authz_matrix → authz_matrix.md записан",
          bool(_mpath) and os.path.isfile(_mpath), "got=%r" % (_mpath,))
finally:
    shutil.rmtree(A7B_SESSION, ignore_errors=True)


print("=== OPENAPI_TO_ACNN SELFTEST (FDE Plan 5, Task 5) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d зелёные" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
