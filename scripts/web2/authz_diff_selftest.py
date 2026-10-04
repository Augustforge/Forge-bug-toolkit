# -*- coding: utf-8 -*-
"""Selftest for authz_diff.py (FDE Plan 5, Task 3).

Proves:
 (1) build_role_contexts: dict of Response/dict -> dict of Context, role set correctly.
 (2) authz_diff: user-B's response diverges from user-A's own baseline on the same object endpoint ->
     Divergence with dclass "object-authz" (BOLA raw signal; see task-3-report.md Concerns for the
     documented blind-spot on byte-identical mirrored leaks -- differential() only fires on inequality).
 (3) authz_diff: unauth gets 200 where spec expects 401 -> Divergence dclass "broken-auth".
 (4) authz_diff: user-A gets 200 on an admin-only function where spec expects 403 -> Divergence
     dclass "function-authz".
 (5) authz_diff: all roles correctly gated (unauth->401 spec-matching, userA/userB->403 spec/peer-
     matching) -> empty list (properly secured, nothing to flag).
 (6) authz_diff: role response with status 429 -> Divergence dclass "[INCONCLUSIVE-RATE_LIMITED]", NOT
     counted as a BOLA/broken-auth/etc divergence.
 (7) authz_diff: role response 403 with a WAF signature in body (via fields["_body"]) -> Divergence
     dclass "[INCONCLUSIVE-WAF_BLOCK]", NOT AUTH_DENIED/BOLA.
 (8) run_authz_matrix(session_dir=<tmp toolkit-rooted>) writes authz_matrix.md to EXACTLY
     os.path.join(session_dir, "authz_matrix.md") -- never CWD-relative, never bare "sessions/...".
     Cleaned up in finally.
 (9) run_authz_matrix on an empty endpoint list still writes the file with the literal
     "RESULT: matrix-run, 0 divergences" line.
 (10) A real (non-inconclusive) Divergence's to_dnn_row() output matches the gate-compatible
      _D_ROW_RE pattern (^\\s*\\|\\s*D-\\d+\\s*\\|); run_authz_matrix renumbers it (D-01 -> D-01/D-02/...)
      and the renumbered line still matches.
 (11) _BaselineCache.get_or_compute does NOT call compute_fn twice for the same key within TTL
      (call-counter proof); a second distinct key DOES trigger a second compute_fn call.
 (12) R7: mode="single+unauth" forces provenance="MANUAL" on a real (non-inconclusive) Divergence,
      both on the in-memory object AND visibly in the written authz_matrix.md ("provenance=MANUAL"
      text + "MODE: single+unauth" line); contrapoint -- mode="full-matrix" on the same fixture does
      NOT mark provenance MANUAL.
 (13) Task 10 (carry BS-05, ownership-baseline): FIRING -- full-leak BOLA where user-B's response on
      user-A's object is BYTE-IDENTICAL to user-A's own baseline (case2-style equality check would
      report 0 divergences, see BS-05) still produces a Divergence dclass "object-authz" once the
      opt-in "user-B-own" self-baseline role is supplied, because the owner-marker in the leaked
      body differs from user-B's own owner-marker.
 (14) Task 10: own-object NEGATIVE -- user-B's "for A's object" response IS user-B's own object
      (owner-marker matches "user-B-own" self-baseline exactly) -> no ownership Divergence (legit
      self-access must NOT be flagged).
 (15) Task 10: no-owner-field INCONCLUSIVE -- object body carries no known owner-marker key at all
      -> Divergence dclass "[INCONCLUSIVE-NO-OWNER-MARKER]", NOT a real "object-authz" BOLA.
 (16) Task 10 (FDE Plan 7 §63): WSResponseAdapter -- a Context.driver (`.probe->Response`) speaking
      WebSocket (reuses websocket_test.py connection logic; mock ws_exchange here, no real socket) --
      returns a runtime_harness Response, and authz_diff runs an authz-differential over a wss://
      endpoint exactly as over HTTP (user-B's WS session on user-A's object -> object-authz Divergence);
      a raising ws_exchange fails open to an empty Response.
 (17-20) Task T3 (Plan 9) -- revocation/lifecycle STALENESS (opt-in temporal axis): a transition
      role-key ("user-A-revoked"/"user-A-expired"/"user-A-downgraded"/"user-A-unshared") carrying the
      SAME actor's post-transition response on the SAME object is compared to the spec-denial baseline.
      (17) still-200 after revoke -> "revocation-staleness" Divergence, severity high (FIRING). (18)
      properly-denied post-transition -> explicit tested-clean outcome row, not a silent skip. (19)
      post-transition 429 -> INCONCLUSIVE, not a staleness claim. (20) the staleness hit flows into
      run_authz_matrix as a real 'divergent' row + gate-compatible D-NN row.
 (21-24) Task T3 (Plan 9) -- indirect/relational IDOR extractor over openapi_to_acnn output: producer
      (list/nested/export/webhook-payload embedding a foreign id) -> consumer (path/query foreign id)
      relations matched by resource, yielding multi-hop authz probe endpoints beyond direct-ID swap.
      (21) order/account/customer chains DETECTED. (22) webhook payload carrying customer_id is a
      producer. (23) a surfaced multi-hop endpoint feeds an authz_diff object-authz probe. (24)
      NEGATIVE: a consumer whose id has no producer (invoice) / an id-less endpoint (profile) is not
      claimed as multi-hop.
 (25-29) Task T4 (Plan 9) -- Object Provenance Ledger (standalone create-event registry ->
      PROVEN create->access chain, not a single-response marker-diff). (25) object_registry writer:
      a create-event is registered to sessions/{target}/object_registry.json, load/lookup return it,
      owner defaults to created_by, lookup_by_endpoint maps a probed endpoint back to the record. (26)
      FIRING: a foreign-account (user-B) access to a REGISTERED object (created/owned by user-A) is
      flagged provenance-backed with a create->access chain (object_id/created_by/accessed_by). (27)
      NEGATIVE: user-B's access to their OWN registered object is NOT provenance-flagged (accessor is
      owner). (28) registry-gated: the SAME foreign fixture WITHOUT a registry stays an unproven
      ownership marker-diff (no provenance_backed) -- proves the ledger is what upgrades it. (29)
      run_authz_matrix auto-consults a co-located object_registry.json -> the written matrix marks the
      row PROVEN-CHAIN and emits a gate-compatible D-NN row; and a registry whose recorded owner
      DISAGREES with the leaked owner does NOT fabricate a chain (anti-FP).

Run: py -3 -X utf8 bug-bounty-toolkit/scripts/web2/authz_diff_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import re
import shutil
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


ad = _load("authz_diff", os.path.join(WEB2_DIR, "authz_diff.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


# Gate-compatible D-NN row pattern (verbatim from hunt_completeness_gate._D_ROW_RE -- brief allows
# checking format instead of importing the (heavy) gate module).
_D_ROW_RE = re.compile(r"^\s*\|\s*D-\d+\s*\|")


# ── CASE 1: build_role_contexts ─────────────────────────────────────────────────────────────────
role_responses_1 = {
    "admin": {"status": 200, "fields": {"role": "admin"}},
    "user-A": ad.Response(status=200, fields={"owner": "user-A"}),
}
role_contexts_1 = ad.build_role_contexts(role_responses_1)
check("case1a build_role_contexts: returns dict with same keys as input",
      set(role_contexts_1.keys()) == {"admin", "user-A"}, "got=%r" % (role_contexts_1,))
check("case1b build_role_contexts: values are Context instances",
      all(isinstance(v, ad.Context) for v in role_contexts_1.values()), "got=%r" % (role_contexts_1,))
check("case1c build_role_contexts: Context.role set to the role key",
      role_contexts_1["admin"].role == "admin" and role_contexts_1["user-A"].role == "user-A",
      "got=%r" % (role_contexts_1,))
check("case1d build_role_contexts: non-dict input -> {} (fail-open)",
      ad.build_role_contexts("not-a-dict") == {})


# ── CASE 2: object-authz (BOLA) ──────────────────────────────────────────────────────────────────
# user-A's own reference view of object A (canonical: full balance).
# user-B (attacker) probes the SAME endpoint (object A, not theirs) and gets back a response that
# diverges from user-A's own baseline (partial-leak scenario: stale/truncated balance field) --
# raw object-authz signal for human triage.
BOLA_ROLES = {
    "user-A": {"status": 200, "fields": {"owner_id": "user-A", "balance": 999}},
    "user-B": {"status": 200, "fields": {"owner_id": "user-A", "balance": 500}},
}
divs_bola = ad.authz_diff("/objects/A", BOLA_ROLES)
check("case2a authz_diff(BOLA fixture): produces at least one Divergence",
      len(divs_bola) >= 1, "got=%r" % (divs_bola,))
check("case2b authz_diff(BOLA fixture): a Divergence has dclass 'object-authz'",
      any(d.dclass == "object-authz" for d in divs_bola), "got=%r" % ([d.dclass for d in divs_bola],))


# ── CASE 3: broken-auth ──────────────────────────────────────────────────────────────────────────
BROKEN_AUTH_ROLES = {
    "unauth": {"status": 200, "fields": {"secret": "leaked-without-auth"}},
}
divs_broken = ad.authz_diff("/admin/export", BROKEN_AUTH_ROLES)
check("case3a authz_diff(unauth->200): produces a Divergence dclass 'broken-auth'",
      any(d.dclass == "broken-auth" for d in divs_broken), "got=%r" % ([d.dclass for d in divs_broken],))


# ── CASE 4: function-authz (BFLA) ────────────────────────────────────────────────────────────────
BFLA_ROLES = {
    "user-A": {"status": 200, "fields": {"result": "admin-only-data"}},
}
divs_bfla = ad.authz_diff("/admin/users", BFLA_ROLES)
check("case4a authz_diff(user-A->200 on admin func): produces a Divergence dclass 'function-authz'",
      any(d.dclass == "function-authz" for d in divs_bfla), "got=%r" % ([d.dclass for d in divs_bfla],))


# ── CASE 5: all properly gated -> empty ──────────────────────────────────────────────────────────
SECURED_ROLES = {
    "unauth": {"status": 401, "fields": {}},
    "user-A": {"status": 403, "fields": {}},
    "user-B": {"status": 403, "fields": {}},
}
divs_secured = ad.authz_diff("/objects/A", SECURED_ROLES)
check("case5a authz_diff(all properly gated): empty list (nothing to flag)",
      divs_secured == [], "got=%r" % (divs_secured,))


# ── CASE 6: classify_http integration -- RATE_LIMITED ────────────────────────────────────────────
RATE_LIMITED_ROLES = {
    "user-A": {"status": 200, "fields": {"owner_id": "user-A", "balance": 999}},
    "user-B": {"status": 429, "fields": {}},
}
divs_rl = ad.authz_diff("/objects/A", RATE_LIMITED_ROLES)
check("case6a authz_diff(user-B 429): produces Divergence dclass '[INCONCLUSIVE-RATE_LIMITED]'",
      any(d.dclass == "[INCONCLUSIVE-RATE_LIMITED]" for d in divs_rl), "got=%r" % ([d.dclass for d in divs_rl],))
check("case6b authz_diff(user-B 429): does NOT produce a real 'object-authz' divergence",
      not any(d.dclass == "object-authz" for d in divs_rl), "got=%r" % ([d.dclass for d in divs_rl],))


# ── CASE 7: classify_http integration -- WAF_BLOCK (403 + WAF body signature) ───────────────────
WAF_ROLES = {
    "unauth": {"status": 403, "fields": {"_body": "Request blocked by mod_security rule 12345"}},
}
divs_waf = ad.authz_diff("/admin/export", WAF_ROLES)
check("case7a authz_diff(unauth 403+WAF body): produces Divergence dclass '[INCONCLUSIVE-WAF_BLOCK]'",
      any(d.dclass == "[INCONCLUSIVE-WAF_BLOCK]" for d in divs_waf), "got=%r" % ([d.dclass for d in divs_waf],))
check("case7b authz_diff(unauth 403+WAF body): does NOT produce a real 'broken-auth' divergence",
      not any(d.dclass == "broken-auth" for d in divs_waf), "got=%r" % ([d.dclass for d in divs_waf],))


# ── CASE 8: run_authz_matrix writes to EXACT session_dir ────────────────────────────────────────
TMP_SESSION_DIR = os.path.join(ROOT, "sessions", "_selftest_tmp_web2_authz")
try:
    if os.path.exists(TMP_SESSION_DIR):
        shutil.rmtree(TMP_SESSION_DIR)
    written_path = ad.run_authz_matrix(["/objects/A"], BOLA_ROLES, session_dir=TMP_SESSION_DIR)
    expected_path = os.path.join(TMP_SESSION_DIR, "authz_matrix.md")
    check("case8a run_authz_matrix: returns exactly os.path.join(session_dir, 'authz_matrix.md')",
          written_path == expected_path, "got=%r expected=%r" % (written_path, expected_path))
    check("case8b run_authz_matrix: file physically exists at that exact path",
          os.path.isfile(expected_path), "path=%r" % (expected_path,))
    # CWD-independent: from repo root, the bare CWD-relative dir differs from TMP_SESSION_DIR (the
    # toolkit-rooted dir), so finding it absent proves nothing landed there. From bug-bounty-toolkit/
    # itself, the bare CWD-relative dir IS TMP_SESSION_DIR (os.getcwd() == .../bug-bounty-toolkit) --
    # in that case the two coincide and the check is vacuously true (nothing bare-vs-toolkit-rooted
    # left to distinguish; the file legitimately exists at the one true toolkit-rooted location).
    bare_stray_dir = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_authz")
    check("case8c run_authz_matrix: nothing written under bare CWD-relative sessions/ (toolkit-rooted only)",
          bare_stray_dir == TMP_SESSION_DIR or not os.path.exists(bare_stray_dir),
          "bare_stray_dir=%r TMP_SESSION_DIR=%r" % (bare_stray_dir, TMP_SESSION_DIR))
    with open(expected_path, "r", encoding="utf-8") as f:
        matrix_content = f.read()
    check("case8d run_authz_matrix: MODE line present",
          "MODE: full-matrix" in matrix_content, "content=%r" % (matrix_content,))
    check("case8e run_authz_matrix: summary table header present",
          "divergence-класс" in matrix_content and "D-NN" in matrix_content, "content=%r" % (matrix_content,))

    # ── CASE 9: empty endpoints -> still writes RESULT line ────────────────────────────────────
    empty_path = ad.run_authz_matrix([], BOLA_ROLES, session_dir=TMP_SESSION_DIR)
    with open(empty_path, "r", encoding="utf-8") as f:
        empty_content = f.read()
    check("case9a run_authz_matrix([]): RESULT line literal 'RESULT: matrix-run, 0 divergences' present",
          "RESULT: matrix-run, 0 divergences" in empty_content, "content=%r" % (empty_content,))

    # ── CASE 10: to_dnn_row() -> gate-compatible D-NN row, renumbered by run_authz_matrix ───────
    real_div = [d for d in divs_bola if d.dclass == "object-authz"][0]
    raw_row = real_div.to_dnn_row()
    check("case10a Divergence.to_dnn_row(): raw output matches gate _D_ROW_RE pattern",
          bool(_D_ROW_RE.match(raw_row)), "raw_row=%r" % (raw_row,))

    matrix_path_2 = ad.run_authz_matrix(["/objects/A"], BOLA_ROLES, session_dir=TMP_SESSION_DIR)
    with open(matrix_path_2, "r", encoding="utf-8") as f:
        matrix_2_lines = f.read().splitlines()
    d_rows = [ln for ln in matrix_2_lines if _D_ROW_RE.match(ln)]
    check("case10b run_authz_matrix: at least one renumbered D-NN row present, matching gate pattern",
          len(d_rows) >= 1, "lines=%r" % (matrix_2_lines,))
    check("case10c run_authz_matrix: renumbered D-NN row is D-01 (first real divergence in this run)",
          any(ln.strip().startswith("| D-01 |") for ln in d_rows), "d_rows=%r" % (d_rows,))
finally:
    shutil.rmtree(TMP_SESSION_DIR, ignore_errors=True)
    stray = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_authz")
    if os.path.exists(stray):
        shutil.rmtree(stray, ignore_errors=True)


# ── CASE 12: R7 -- mode="single+unauth" forces provenance="MANUAL" on real divergences ──────────
# opsec-critical: <2 test_accounts means opsec_preflight._web2_checks fails-closed and the live
# harness never runs -- the ONLY legitimate path to a "single+unauth" result is manual input, and it
# must never be mistaken for an AUTO harness-verified finding under the opsec gate.
SINGLE_UNAUTH_ROLES = {
    "unauth": {"status": 200, "fields": {"secret": "leaked-without-auth"}},
}
divs_single = ad.authz_diff("/admin/export", SINGLE_UNAUTH_ROLES, mode="single+unauth")
real_single = [d for d in divs_single if d.dclass == "broken-auth"]
check("case12a authz_diff(mode='single+unauth'): produces a real broken-auth divergence",
      len(real_single) >= 1, "got=%r" % (divs_single,))
check("case12b authz_diff(mode='single+unauth'): real divergence has provenance == 'MANUAL'",
      bool(real_single) and real_single[0].provenance == "MANUAL", "got=%r" % (real_single,))

# Contrapoint: full-matrix (default) mode on the SAME fixture -> provenance NOT MANUAL (AUTO/default).
divs_full_cp = ad.authz_diff("/admin/export", SINGLE_UNAUTH_ROLES, mode="full-matrix")
real_full_cp = [d for d in divs_full_cp if d.dclass == "broken-auth"]
check("case12c authz_diff(mode='full-matrix', contrapoint): real divergence provenance is NOT 'MANUAL'",
      bool(real_full_cp) and real_full_cp[0].provenance != "MANUAL", "got=%r" % (real_full_cp,))

R7_TMP_SESSION_DIR = os.path.join(ROOT, "sessions", "_selftest_tmp_web2_authz_r7")
try:
    if os.path.exists(R7_TMP_SESSION_DIR):
        shutil.rmtree(R7_TMP_SESSION_DIR)
    r7_path = ad.run_authz_matrix(["/admin/export"], SINGLE_UNAUTH_ROLES, session_dir=R7_TMP_SESSION_DIR,
                                   mode="single+unauth")
    with open(r7_path, "r", encoding="utf-8") as f:
        r7_content = f.read()
    check("case12d run_authz_matrix(mode='single+unauth'): file has literal 'MODE: single+unauth' line",
          "MODE: single+unauth" in r7_content, "content=%r" % (r7_content,))
    check("case12e run_authz_matrix(mode='single+unauth'): written file marks the real divergence "
          "'provenance=MANUAL' (visible to a human/gate reading the file, not just in-memory)",
          "provenance=MANUAL" in r7_content, "content=%r" % (r7_content,))
finally:
    shutil.rmtree(R7_TMP_SESSION_DIR, ignore_errors=True)
    stray_r7 = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_authz_r7")
    if os.path.exists(stray_r7):
        shutil.rmtree(stray_r7, ignore_errors=True)


# ── CASE 11: _BaselineCache dedup (call-counter) ────────────────────────────────────────────────
cache = ad._BaselineCache(capacity=8, ttl=300)
calls = {"n": 0}


def _compute():
    calls["n"] += 1
    return "baseline-value-%d" % calls["n"]


v1 = cache.get_or_compute("spec-401", 0, _compute)
v2 = cache.get_or_compute("spec-401", 1, _compute)
check("case11a _BaselineCache.get_or_compute: same key within TTL -> compute_fn called exactly once",
      calls["n"] == 1, "calls=%r v1=%r v2=%r" % (calls["n"], v1, v2))
check("case11b _BaselineCache.get_or_compute: same key within TTL -> returns the SAME cached value",
      v1 == v2, "v1=%r v2=%r" % (v1, v2))

v3 = cache.get_or_compute("spec-403", 2, _compute)
check("case11c _BaselineCache.get_or_compute: a DIFFERENT key triggers a second compute_fn call",
      calls["n"] == 2, "calls=%r v3=%r" % (calls["n"], v3))

v4 = cache.get_or_compute("spec-401", 9999, _compute)  # ts far beyond ttl -> expired -> recompute
check("case11d _BaselineCache.get_or_compute: expired TTL (ts - put_ts > ttl) -> recomputes",
      calls["n"] == 3, "calls=%r v4=%r" % (calls["n"], v4))


# ── CASE 13: Task 10 (carry BS-05) -- ownership-baseline FIRING on full-leak BOLA ────────────────
# user-B's response probing user-A's object is BYTE-IDENTICAL to user-A's own baseline (same status,
# same fields, including owner_id="user-A") -- the equality-based check (block 1., case2-style)
# would report "0 divergences" here (that IS the BS-05 gap: diverged=False on a mirrored leak). The
# opt-in "user-B-own" self-baseline (user-B's REAL own object, owner_id="user-B") lets the new
# ownership-baseline branch catch it: owner_id in the "for A" body ("user-A") != owner_id in
# user-B's own baseline ("user-B") -> flagged regardless of the equality-check's blindness.
FULL_LEAK_ROLES = {
    "user-A": {"status": 200, "fields": {"owner_id": "user-A", "balance": 999}},
    "user-B": {"status": 200, "fields": {"owner_id": "user-A", "balance": 999}},  # byte-identical to A
    "user-B-own": {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}},
}
divs_full_leak = ad.authz_diff("/objects/A", FULL_LEAK_ROLES)
check("case13a Task10 full-leak BOLA: equality check (1.) alone would miss it -- confirm B==A byte-identical",
      FULL_LEAK_ROLES["user-A"]["fields"] == FULL_LEAK_ROLES["user-B"]["fields"])
check("case13b Task10 ownership-baseline FIRING: produces a Divergence dclass 'object-authz' via owner-marker mismatch",
      any(d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {}) for d in divs_full_leak),
      "got=%r" % ([(d.dclass, d.evidence) for d in divs_full_leak],))
_ownership_div = [d for d in divs_full_leak if d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {})]
check("case13c Task10 ownership-baseline FIRING: owner_mismatch evidence names owner_id (self='user-B', target='user-A')",
      bool(_ownership_div) and _ownership_div[0].evidence["owner_mismatch"].get("owner_id") ==
      {"self": "user-B", "target": "user-A"},
      "got=%r" % (_ownership_div[0].evidence if _ownership_div else None,))
check("case13d Task10 ownership-baseline FIRING: severity_seed is 'high'",
      bool(_ownership_div) and _ownership_div[0].severity_seed == "high")


# ── CASE 14: Task 10 -- own-object NEGATIVE (B-for-B must NOT be flagged) ───────────────────────
# user-B's "for A's object" slot here is ACTUALLY user-B's own object (owner_id="user-B", matches
# the "user-B-own" self-baseline exactly) -- legit self-access, falsifier requires NO flag.
OWN_OBJECT_ROLES = {
    "user-B": {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}},
    "user-B-own": {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}},
}
divs_own = ad.authz_diff("/objects/B-own", OWN_OBJECT_ROLES)
check("case14a Task10 own-object NEGATIVE: no ownership 'object-authz' Divergence for legit self-access",
      not any(d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {}) for d in divs_own),
      "got=%r" % ([(d.dclass, d.evidence) for d in divs_own],))


# ── CASE 15: Task 10 -- no-owner-field INCONCLUSIVE (not a silent miss, not a false positive) ────
NO_OWNER_FIELD_ROLES = {
    "user-B": {"status": 200, "fields": {"data": "some-payload", "count": 3}},
    "user-B-own": {"status": 200, "fields": {"data": "other-payload", "count": 1}},
}
divs_no_owner = ad.authz_diff("/objects/opaque", NO_OWNER_FIELD_ROLES)
check("case15a Task10 no-owner-field: produces Divergence dclass '[INCONCLUSIVE-NO-OWNER-MARKER]'",
      any(d.dclass == "[INCONCLUSIVE-NO-OWNER-MARKER]" for d in divs_no_owner),
      "got=%r" % ([d.dclass for d in divs_no_owner],))
check("case15b Task10 no-owner-field: does NOT produce a real 'object-authz' ownership Divergence",
      not any(d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {}) for d in divs_no_owner),
      "got=%r" % ([(d.dclass, d.evidence) for d in divs_no_owner],))


# ── CASE 16: Task 10 (FDE Plan 7 §63) -- WS→Response adapter feeds authz_diff over a WebSocket ──────
# WSResponseAdapter is a Context.driver (`.probe(probe) -> Response`) that talks WebSocket by reusing
# websocket_test.py's connection logic. Here we inject a MOCK ws_exchange (no real socket) proving the
# adapter's normalization (raw ws frame -> runtime_harness Response) and that authz_diff runs an authz-
# differential over a wss:// endpoint exactly as it does over HTTP. user-B's WS session on user-A's
# subscribed object returns A's data (partial-leak balance) -> object-authz Divergence.
def _fake_ws_exchange_A(url, headers, message, timeout):
    return 101, '{"owner_id": "user-A", "balance": 999}'


def _fake_ws_exchange_B(url, headers, message, timeout):
    return 101, '{"owner_id": "user-A", "balance": 500}'  # user-B sees A's object over WS -> leak


WS_URL = "wss://api.example.com/graphql-ws"
_ws_sub = '{"type":"subscribe","id":"1","payload":{"query":"subscription{order(id:\\"A\\"){balance}}"}}'
ws_driver_A = ad.WSResponseAdapter(WS_URL, headers={"Authorization": "sess-A"}, message=_ws_sub,
                                   ws_exchange=_fake_ws_exchange_A)
ws_driver_B = ad.WSResponseAdapter(WS_URL, headers={"Authorization": "sess-B"}, message=_ws_sub,
                                   ws_exchange=_fake_ws_exchange_B)

_probe_ws = ad.Probe("object-authz", WS_URL)
_resp_ws = ws_driver_A.probe(_probe_ws)
check("case16a WSResponseAdapter.probe returns a runtime_harness Response (isinstance ad.Response)",
      isinstance(_resp_ws, ad.Response), "got type=%r" % (type(_resp_ws),))
check("case16b WSResponseAdapter.probe: ws JSON body parsed into fields + _body convention + status 101",
      isinstance(_resp_ws.fields, dict) and _resp_ws.fields.get("owner_id") == "user-A"
      and "_body" in _resp_ws.fields and _resp_ws.status == 101,
      "got status=%r fields=%r" % (_resp_ws.status, _resp_ws.fields))

_ws_contexts = {
    "user-A": ad.Context("user-A", ws_driver_A, role="user-A"),
    "user-B": ad.Context("user-B", ws_driver_B, role="user-B"),
}
divs_ws = ad.authz_diff(WS_URL, _ws_contexts)
check("case16c authz_diff over a wss:// endpoint: produces an 'object-authz' Divergence (BOLA via WS)",
      any(d.dclass == "object-authz" for d in divs_ws),
      "got=%r" % ([d.dclass for d in divs_ws],))
# fail-open discipline: a ws_exchange that raises must yield an empty Response, never crash the probe.
def _boom_exchange(url, headers, message, timeout):
    raise RuntimeError("socket blew up")


_resp_boom = ad.WSResponseAdapter(WS_URL, message=_ws_sub, ws_exchange=_boom_exchange).probe(_probe_ws)
check("case16d WSResponseAdapter.probe fail-open: raising ws_exchange -> empty ad.Response (no crash)",
      isinstance(_resp_boom, ad.Response) and _resp_boom.status is None,
      "got=%r" % (_resp_boom,))


# ── CASE 17: Task T3 (Plan 9) -- revocation/lifecycle staleness FIRING (stale-but-still-works) ─────
# The base matrix is point-in-time. Here the caller staged a REVOKE and re-captured the SAME actor's
# response on the SAME object under transition role-key "user-A-revoked": it STILL returns 200 + data.
# A revoked credential SHOULD get 401/403 -> the post-transition grant diverges from the spec-denial
# baseline -> revocation-staleness Divergence, severity high.
STALE_REVOKE_ROLES = {
    "user-A-revoked": {"status": 200, "fields": {"owner_id": "user-A", "secret": "still-reachable"}},
}
divs_stale = ad.authz_diff("/objects/A", STALE_REVOKE_ROLES)
check("case17a Task T3 temporal FIRING: revoked credential still 200 -> Divergence dclass 'revocation-staleness'",
      any(d.dclass == "revocation-staleness" for d in divs_stale),
      "got=%r" % ([d.dclass for d in divs_stale],))
_stale_div = [d for d in divs_stale if d.dclass == "revocation-staleness"]
check("case17b Task T3 temporal FIRING: revocation-staleness severity_seed is 'high'",
      bool(_stale_div) and _stale_div[0].severity_seed == "high",
      "got=%r" % ([(d.dclass, d.severity_seed) for d in divs_stale],))

# ── CASE 18: Task T3 -- NEGATIVE: properly revoked (post-transition 403) -> tested-clean, no div ────
REVOKED_CLEAN_ROLES = {"user-A-expired": {"status": 401, "fields": {}}}
divs_rev_clean = ad.authz_diff("/objects/A", REVOKED_CLEAN_ROLES)
check("case18a Task T3 temporal NEGATIVE: post-transition 401 (properly denied) -> no revocation-staleness div",
      not any(d.dclass == "revocation-staleness" for d in divs_rev_clean),
      "got=%r" % ([d.dclass for d in divs_rev_clean],))
# the outcome is not a SILENT skip -- it is recorded as an explicit tested-clean row (T2 model).
_recs_clean = ad._authz_outcomes("/objects/A", REVOKED_CLEAN_ROLES)
check("case18b Task T3 temporal NEGATIVE: emits an explicit tested-clean revocation-staleness outcome row (not silent)",
      any(r.kind == "revocation-staleness" and r.status == ad.STATUS_TESTED_CLEAN for r in _recs_clean),
      "got=%r" % ([(r.kind, r.status) for r in _recs_clean],))

# ── CASE 19: Task T3 -- inconclusive: post-transition 429 -> INCONCLUSIVE, not a staleness claim ────
STALE_RL_ROLES = {"user-A-downgraded": {"status": 429, "fields": {}}}
divs_stale_rl = ad.authz_diff("/objects/A", STALE_RL_ROLES)
check("case19a Task T3 temporal inconclusive: post-transition 429 -> Divergence dclass '[INCONCLUSIVE-RATE_LIMITED]'",
      any(d.dclass == "[INCONCLUSIVE-RATE_LIMITED]" for d in divs_stale_rl),
      "got=%r" % ([d.dclass for d in divs_stale_rl],))
check("case19b Task T3 temporal inconclusive: does NOT produce a real 'revocation-staleness' divergence",
      not any(d.dclass == "revocation-staleness" for d in divs_stale_rl),
      "got=%r" % ([d.dclass for d in divs_stale_rl],))

# ── CASE 20: Task T3 -- temporal outcome flows into run_authz_matrix as a real D-NN row ─────────────
T3_TMP_SESSION_DIR = os.path.join(ROOT, "sessions", "_selftest_tmp_web2_authz_t3")
try:
    if os.path.exists(T3_TMP_SESSION_DIR):
        shutil.rmtree(T3_TMP_SESSION_DIR)
    t3_path = ad.run_authz_matrix(["/objects/A"], STALE_REVOKE_ROLES, session_dir=T3_TMP_SESSION_DIR)
    with open(t3_path, "r", encoding="utf-8") as f:
        t3_content = f.read()
    check("case20a run_authz_matrix(temporal): 'revocation-staleness' row present with status 'divergent'",
          "revocation-staleness" in t3_content and "divergent" in t3_content, "content=%r" % (t3_content,))
    t3_d_rows = [ln for ln in t3_content.splitlines() if _D_ROW_RE.match(ln)]
    check("case20b run_authz_matrix(temporal): at least one gate-compatible D-NN row emitted for the staleness hit",
          len(t3_d_rows) >= 1, "lines=%r" % (t3_content.splitlines(),))
finally:
    shutil.rmtree(T3_TMP_SESSION_DIR, ignore_errors=True)
    stray_t3 = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_authz_t3")
    if os.path.exists(stray_t3):
        shutil.rmtree(stray_t3, ignore_errors=True)


# ── CASE 21-24: Task T3 (b) -- indirect/relational IDOR extractor over openapi_to_acnn output ───────
oa = _load("openapi_to_acnn", os.path.join(WEB2_DIR, "openapi_to_acnn.py"))

REL_SCHEMA = {
    "paths": {
        "/users/{userId}/orders": {"get": {}},        # list producer of "order" (+ nested "user")
        "/orders/{orderId}": {"get": {}},             # consumer of "order"
        "/account/export": {"get": {}},               # export producer of "account"
        "/accounts/{accountId}": {"get": {}},         # consumer of "account"
        # webhook producer of "customer" (embedded fk in the POST payload)
        "/webhooks/payment": {
            "post": {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"properties": {"customer_id": {}, "amount": {}}}
                        }
                    }
                }
            }
        },
        "/customers/{customerId}": {"get": {}},       # consumer of "customer"
        "/profile": {"get": {}},                      # neither producer nor consumer
        "/invoices/{invoiceId}": {"get": {}},         # consumer of "invoice" -- NO producer (direct-only)
    }
}
rel_endpoints = oa.parse_schema(REL_SCHEMA, kind="openapi")
rels = oa.build_relations(rel_endpoints)
mh = oa.multihop_endpoints(rel_endpoints)

check("case21a relational extractor: multi-hop reachable consumers DETECTED across endpoints "
      "(orders/accounts/customers via list/export/webhook producers)",
      mh == ["GET /accounts/{accountId}", "GET /customers/{customerId}", "GET /orders/{orderId}"],
      "got=%r" % (mh,))
check("case21b relational extractor: an order relation links the nested-list producer to the "
      "direct-id consumer (multi-hop, not direct-ID swap)",
      any(r["resource"] == "order" and r["producer"] == "GET /users/{userId}/orders"
          and r["consumer"] == "GET /orders/{orderId}" for r in rels),
      "got=%r" % (rels,))
check("case21c relational extractor: an export producer feeds the account consumer",
      any(r["resource"] == "account" and r["producer_hop"] == "export"
          and r["consumer"] == "GET /accounts/{accountId}" for r in rels),
      "got=%r" % (rels,))

# CASE 22: webhook payload carrying an embedded foreign id is a producer.
check("case22a relational extractor: webhook payload embedding customer_id -> producer of 'customer' "
      "consumed by /customers/{customerId}",
      any(r["resource"] == "customer" and r["producer_hop"] == "webhook"
          and r["producer"] == "POST /webhooks/payment"
          and r["consumer"] == "GET /customers/{customerId}" for r in rels),
      "got=%r" % (rels,))

# CASE 23: the multi-hop endpoint the extractor surfaced feeds straight into an authz probe.
_mh_target = "GET /orders/{orderId}"
divs_mh = ad.authz_diff(_mh_target, BOLA_ROLES)  # cross-account fixture on the relationally-reached ep
check("case23a relational -> authz probe: a multi-hop endpoint from the extractor drives an "
      "authz_diff object-authz divergence (beyond direct-ID swap)",
      _mh_target in mh and any(d.dclass == "object-authz" for d in divs_mh),
      "mh=%r got=%r" % (_mh_target in mh, [d.dclass for d in divs_mh],))

# CASE 24: NEGATIVE -- a consumer whose id has NO producer elsewhere is direct-only, not multi-hop.
check("case24a relational extractor NEGATIVE: /invoices/{invoiceId} (no producer of 'invoice') is "
      "NOT claimed as a multi-hop endpoint",
      "GET /invoices/{invoiceId}" not in mh, "mh=%r" % (mh,))
check("case24b relational extractor NEGATIVE: /profile (no foreign id at all) is not in relations",
      not any(r["consumer"] == "GET /profile" or r["producer"] == "GET /profile" for r in rels),
      "got=%r" % (rels,))


# ── CASE 25-29: Task T4 (Plan 9) -- Object Provenance Ledger ────────────────────────────────────────
oreg = _load("object_registry", os.path.join(WEB2_DIR, "object_registry.py"))

T4_SESSION_DIR = os.path.join(ROOT, "sessions", "_selftest_tmp_web2_authz_t4")
try:
    if os.path.exists(T4_SESSION_DIR):
        shutil.rmtree(T4_SESSION_DIR)

    # CASE 25: registry writer standalone (register / load / lookup / owner-default / by-endpoint).
    rec_A = oreg.register_object(T4_SESSION_DIR, "A", created_by="user-A",
                                 creating_request="POST /objects {name:'x'}", owner="user-A",
                                 timestamp="2026-01-01T00:00:00Z")
    rec_Bown = oreg.register_object(T4_SESSION_DIR, "Bown", created_by="user-B",
                                    creating_request="POST /objects {name:'y'}",  # owner omitted
                                    timestamp="2026-01-01T00:05:00Z")
    check("case25a object_registry.register_object: create-event written, returns the record dict",
          isinstance(rec_A, dict) and rec_A.get("object_id") == "A" and rec_A.get("created_by") == "user-A",
          "got=%r" % (rec_A,))
    check("case25b object_registry: JSON file physically created at sessions/{target}/object_registry.json",
          os.path.isfile(os.path.join(T4_SESSION_DIR, "object_registry.json")))
    reg_loaded = oreg.load_registry(T4_SESSION_DIR)
    check("case25c object_registry.load_registry: both append-only create-events present",
          isinstance(reg_loaded.get("records"), list) and len(reg_loaded["records"]) == 2,
          "got=%r" % (reg_loaded,))
    check("case25d object_registry.lookup('A'): returns the create-event record for A",
          (oreg.lookup(reg_loaded, "A") or {}).get("created_by") == "user-A",
          "got=%r" % (oreg.lookup(reg_loaded, "A"),))
    check("case25e object_registry.register_object: owner defaults to created_by when omitted",
          (oreg.lookup(reg_loaded, "Bown") or {}).get("owner") == "user-B",
          "got=%r" % (oreg.lookup(reg_loaded, "Bown"),))
    check("case25f object_registry.lookup_by_endpoint('/objects/A'): maps endpoint segment -> record A",
          (oreg.lookup_by_endpoint(reg_loaded, "/objects/A") or {}).get("object_id") == "A",
          "got=%r" % (oreg.lookup_by_endpoint(reg_loaded, "/objects/A"),))
    check("case25g object_registry.lookup_by_endpoint: unregistered endpoint -> None",
          oreg.lookup_by_endpoint(reg_loaded, "/objects/ZZZ") is None,
          "got=%r" % (oreg.lookup_by_endpoint(reg_loaded, "/objects/ZZZ"),))

    # CASE 26: FIRING -- foreign access to a REGISTERED object -> proven create->access chain.
    # user-B probes object A (owner_id 'user-A' leaked in body); user-B-own self-baseline shows their
    # OWN owner_id 'user-B'. ownership_diff fires owner_mismatch; the registry (A created/owned by
    # user-A, accessor user-B != owner) UPGRADES it to a proven chain.
    PROV_FOREIGN_ROLES = {
        "user-B": {"status": 200, "fields": {"owner_id": "user-A", "balance": 999}},
        "user-B-own": {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}},
    }
    divs_prov = ad.authz_diff("/objects/A", PROV_FOREIGN_ROLES, registry=reg_loaded)
    _prov = [d for d in divs_prov if d.dclass == "object-authz" and (d.evidence or {}).get("provenance_backed")]
    check("case26a Task T4 FIRING: foreign access to registered object -> provenance_backed object-authz Divergence",
          len(_prov) >= 1, "got=%r" % ([(d.dclass, sorted((d.evidence or {}).keys())) for d in divs_prov],))
    _chain = _prov[0].evidence.get("provenance_chain") if _prov else None
    check("case26b Task T4 FIRING: provenance_chain names object_id='A', created_by='user-A', accessed_by='user-B'",
          isinstance(_chain, dict) and _chain.get("object_id") == "A"
          and _chain.get("created_by") == "user-A" and _chain.get("accessed_by") == "user-B",
          "got=%r" % (_chain,))
    check("case26c Task T4 FIRING: attack_path_hint reads as a PROVEN create->access chain (not marker-diff)",
          bool(_prov) and "PROVEN create->access chain" in (_prov[0].attack_path_hint or ""),
          "got=%r" % (_prov[0].attack_path_hint if _prov else None,))

    # CASE 27: NEGATIVE -- user-B accesses their OWN registered object -> NOT provenance-flagged.
    # Object 'Bown' is registered as owned by user-B; user-B reads it (owner_id 'user-B' == self-
    # baseline). ownership_diff returns None (markers match) -> no chain. Legit self-access must not flag.
    PROV_SELF_ROLES = {
        "user-B": {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}},
        "user-B-own": {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}},
    }
    divs_self = ad.authz_diff("/objects/Bown", PROV_SELF_ROLES, registry=reg_loaded)
    check("case27a Task T4 NEGATIVE: self-access to own registered object -> NO provenance_backed Divergence",
          not any((d.evidence or {}).get("provenance_backed") for d in divs_self),
          "got=%r" % ([(d.dclass, (d.evidence or {}).get("provenance_backed")) for d in divs_self],))

    # CASE 28: registry-gated -- SAME foreign fixture WITHOUT a registry stays an unproven marker-diff.
    divs_noreg = ad.authz_diff("/objects/A", PROV_FOREIGN_ROLES)  # registry=None (default)
    _marker = [d for d in divs_noreg if d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {})]
    check("case28a Task T4 registry-gated: without a registry the ownership hit still fires (marker-diff)",
          len(_marker) >= 1, "got=%r" % ([(d.dclass, sorted((d.evidence or {}).keys())) for d in divs_noreg],))
    check("case28b Task T4 registry-gated: but it is NOT provenance_backed (the ledger is what proves the chain)",
          bool(_marker) and not _marker[0].evidence.get("provenance_backed"),
          "got=%r" % (_marker[0].evidence if _marker else None,))

    # CASE 29a: run_authz_matrix AUTO-consults the co-located object_registry.json (no registry arg) ->
    # PROVEN-CHAIN marker + gate-compatible D-NN row in the written matrix.
    t4_path = ad.run_authz_matrix(["/objects/A"], PROV_FOREIGN_ROLES, session_dir=T4_SESSION_DIR)
    with open(t4_path, "r", encoding="utf-8") as f:
        t4_content = f.read()
    check("case29a run_authz_matrix auto-consult: written matrix marks the row 'PROVEN-CHAIN'",
          "PROVEN-CHAIN" in t4_content, "content=%r" % (t4_content,))
    t4_d_rows = [ln for ln in t4_content.splitlines() if _D_ROW_RE.match(ln)]
    check("case29b run_authz_matrix auto-consult: at least one gate-compatible D-NN row emitted",
          len(t4_d_rows) >= 1, "lines=%r" % (t4_content.splitlines(),))

    # CASE 29c: anti-FP -- a registry whose recorded owner DISAGREES with the leaked owner marker must
    # NOT fabricate a chain (object 'A' registered owner 'user-A', but the leaked body says owner 'user-Q').
    MISMATCH_ROLES = {
        "user-B": {"status": 200, "fields": {"owner_id": "user-Q", "balance": 999}},
        "user-B-own": {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}},
    }
    divs_mismatch = ad.authz_diff("/objects/A", MISMATCH_ROLES, registry=reg_loaded)
    check("case29c Task T4 anti-FP: registered owner != leaked owner -> ownership hit but NO fabricated chain",
          any(d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {}) for d in divs_mismatch)
          and not any((d.evidence or {}).get("provenance_backed") for d in divs_mismatch),
          "got=%r" % ([(d.dclass, (d.evidence or {}).get("provenance_backed")) for d in divs_mismatch],))
finally:
    shutil.rmtree(T4_SESSION_DIR, ignore_errors=True)
    stray_t4 = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_authz_t4")
    if os.path.exists(stray_t4):
        shutil.rmtree(stray_t4, ignore_errors=True)


# ── CASE 30 (A2, Волна 1): schema_hint × ownership_diff(markers=) — «розетка есть, вилки нет» ─────
# Таргет с НЕСТАНДАРТНЫМ owner-полем `workspace_owner` (нет в default `_OWNER_MARKER_KEYS`). Full-leak
# BOLA: user-B видит объект user-A байт-в-байт → equality-чек слеп, а ownership-baseline на default-
# словаре МОЛЧИТ `[INCONCLUSIVE]` (имя поля не угадано). schema_hint_leak даёт РЕАЛЬНОЕ имя →
# discovered_markers → BOLA ловится. Откат прокидки markers= роняет case30b.
NONSTD_OWNER_ROLES = {
    "user-A": {"status": 200, "fields": {"workspace_owner": "user-A", "balance": 999}},
    "user-B": {"status": 200, "fields": {"workspace_owner": "user-A", "balance": 999}},
    "user-B-own": {"status": 200, "fields": {"workspace_owner": "user-B", "balance": 10}},
}
# 30a — БЕЗ discovered: default словарь не знает `workspace_owner` → INCONCLUSIVE, реального BOLA нет.
divs_nostd_default = ad.authz_diff("/ws/A", NONSTD_OWNER_ROLES)
check("case30a A2 baseline: нестандартное owner-поле + default-словарь → INCONCLUSIVE (не object-authz)",
      any(d.dclass == "[INCONCLUSIVE-NO-OWNER-MARKER]" for d in divs_nostd_default)
      and not any(d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {})
                  for d in divs_nostd_default),
      "got=%r" % ([d.dclass for d in divs_nostd_default],))
# 30b — schema_hint вытянул имена полей таргета → discovered_markers → BOLA ДЕТЕКТИТСЯ (FIRING).
divs_nostd_disc = ad.authz_diff("/ws/A", NONSTD_OWNER_ROLES,
                                discovered_markers=["workspace_owner", "belongs_to"])
check("case30b A2 FIRING: discovered owner-поле → markers= расширен → full-leak BOLA ловится (object-authz)",
      any(d.dclass == "object-authz" and (d.evidence or {}).get("owner_mismatch", {}).get("workspace_owner")
          == {"self": "user-B", "target": "user-A"} for d in divs_nostd_disc),
      "got=%r" % ([(d.dclass, d.evidence) for d in divs_nostd_disc],))
# 30c — anti-FP: non-owner discovered поле (`created_at`), отличное на self-baseline, НЕ даёт ложный BOLA.
ANTIFP_ROLES = {
    "user-B": {"status": 200, "fields": {"owner_id": "user-B", "created_at": "2026-05-01"}},
    "user-B-own": {"status": 200, "fields": {"owner_id": "user-B", "created_at": "2026-01-01"}},
}
divs_antifp = ad.authz_diff("/objects/self", ANTIFP_ROLES, discovered_markers=["created_at", "title"])
check("case30c A2 anti-FP: non-owner discovered-поле (created_at) отличается, но owner совпал → НЕ BOLA",
      not any(d.dclass == "object-authz" and "owner_mismatch" in (d.evidence or {}) for d in divs_antifp),
      "got=%r" % ([(d.dclass, d.evidence) for d in divs_antifp],))
# 30d — owner_like_markers unit: owner-подобные добавляются, мусор отбрасывается.
_olm = ad._rh._dobs.owner_like_markers(["workspace_owner", "created_at", "belongs_to", "title"])
check("case30d A2 owner_like_markers: owner-подобные вошли, non-owner отброшены",
      "workspace_owner" in _olm and "belongs_to" in _olm
      and "created_at" not in _olm and "title" not in _olm,
      "got=%r" % (_olm,))


print("=== AUTHZ_DIFF SELFTEST (FDE Plan 5, Task 3) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d зелёные" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
