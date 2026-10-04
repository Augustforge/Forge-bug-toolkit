# -*- coding: utf-8 -*-
"""Replay for differential_observation.py (Plan 3 Task 1, §35.1).

Proves: (1) the primitive differential()/differential_matrix()/semantic_diff() really catches a
divergence on all 6 dclass (BOLA/signature/clone-parity/broken-auth/BFLA/tenant-isolation) +
an N-context matrix + a negative (identical ctx -> None) + fail-open on a driver exception; (2)
to_dnn_row() — the consumer contract: the row is REALLY recognized by the live hunt_completeness_gate.py
(_D_ROW_RE matches + active_divergence_unresolved holds the turn on a temp session). The pattern `_load` +
ROOT-walk + unique SID + finally-cleanup is copied from web_parity_replay.py.
"""
import os
import sys
import shutil
import time
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
METHOD = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "_methodology")
HOOKS = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks")
SESSIONS = os.path.join(ROOT, "bug-bounty-toolkit", "sessions")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


dobs = _load("differential_observation", os.path.join(METHOD, "differential_observation.py"))
gate = _load("hunt_completeness_gate", os.path.join(HOOKS, "hunt_completeness_gate.py"))

SID = "DIFFOBS-TESTSID-Q7"       # unique sid -> _owned_markers isolates from real .hunt_active
SESS = os.path.join(SESSIONS, "diffobstest")

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


Context = dobs.Context
Probe = dobs.Probe
Response = dobs.Response
MockDriver = dobs.MockDriver
differential = dobs.differential
differential_matrix = dobs.differential_matrix
semantic_diff = dobs.semantic_diff
ownership_diff = dobs.ownership_diff

# Pool of Divergence from cases 1-7 -- on it case 9 (attack_path_hint is non-empty on EACH).
pool_1_7 = []

# ── CASE 1: BOLA (object-authz) ─────────────────────────────────────────────
p1 = Probe(kind="object-authz", target="/api/users/A/profile")
ctxA1 = Context(label="user-A", driver=MockDriver({
    p1.key(): {"status": 200, "fields": {"id": "A", "name": "Alice"}}}))
ctxB1 = Context(label="user-B", driver=MockDriver({
    p1.key(): {"status": 200, "fields": {
        "id": "A", "name": "Alice", "ssn": "111-22-3333", "email": "alice@example.com"}}}))
div1 = differential(ctxA1, ctxB1, p1)
check("case1 BOLA: differential() returned a Divergence (not None)", div1 is not None)
if div1 is not None:
    pool_1_7.append(div1)
    check("case1 BOLA: dclass == object-authz", div1.dclass == "object-authz")
    check("case1 BOLA: field_leak contains the leaked private fields of user-A",
          "ssn" in div1.evidence.get("field_leak", []) and "email" in div1.evidence.get("field_leak", []),
          "field_leak=%r" % (div1.evidence.get("field_leak"),))

# ── CASE 2: signature-integrity (DOM vs signed payload) ─────────────────────
p2 = Probe(kind="signature-integrity", target="tx:transfer")
ctxA2 = Context(label="dom-displayed", driver=MockDriver({
    p2.key(): {"status": 200, "fields": {"amount": 100, "to": "0xAAA"}}}))
ctxB2 = Context(label="signed-payload", driver=MockDriver({
    p2.key(): {"status": 200, "fields": {"amount": 9900, "to": "0xAAA"}}}))
div2 = differential(ctxA2, ctxB2, p2)
check("case2 signature-integrity: differential() returned a Divergence", div2 is not None)
if div2 is not None:
    pool_1_7.append(div2)
    check("case2 signature-integrity: dclass correct", div2.dclass == "signature-integrity")
    check("case2 signature-integrity: field_leak caught the amount mismatch (100 vs 9900)",
          "amount" in div2.evidence.get("field_leak", []))

# ── CASE 3: clone-parity (2 deploys, B lost the CSP header) ─────────────────
p3 = Probe(kind="clone-parity", target="deploy-security-headers")
ctxA3 = Context(label="deploy-1-prod", driver=MockDriver({
    p3.key(): {"status": 200, "fields": {},
               "headers": {"Content-Security-Policy": "default-src 'self'", "X-Frame-Options": "DENY"}}}))
ctxB3 = Context(label="deploy-2-staging-clone", driver=MockDriver({
    p3.key(): {"status": 200, "fields": {}, "headers": {"X-Frame-Options": "DENY"}}}))
div3 = differential(ctxA3, ctxB3, p3)
check("case3 clone-parity: differential() returned a Divergence", div3 is not None)
if div3 is not None:
    pool_1_7.append(div3)
    check("case3 clone-parity: dclass correct", div3.dclass == "clone-parity")
    check("case3 clone-parity: header_diff caught the lost CSP",
          "Content-Security-Policy" in div3.evidence.get("header_diff", {}))

# ── CASE 4: broken-auth ──────────────────────────────────────────────────────
# Design decision (see the report): for a kind where the bug = PARITY of the illegitimate side with the legitimate one (not
# a divergence), the primitive compares ctx_a = expected/spec-baseline ("what it SHOULD return without a session")
# against ctx_b = the actually observed response. This way status_diff (401 expected vs 200 actual) is detected by a
# CLEAN pairwise diff without a special case in semantic_diff. attack_path_hint for broken-auth ("repeat the
# request without a session; check reachability of the protected resource without auth") directly confirms this comparison pair.
p4 = Probe(kind="broken-auth", target="/api/account/balance")
ctxA4 = Context(label="expected-unauth-401", driver=MockDriver({
    p4.key(): {"status": 401, "fields": {}}}))
ctxB4 = Context(label="actual-unauth-request", driver=MockDriver({
    p4.key(): {"status": 200, "fields": {"balance": 500}}}))
div4 = differential(ctxA4, ctxB4, p4)
check("case4 broken-auth: differential() returned a Divergence", div4 is not None)
if div4 is not None:
    pool_1_7.append(div4)
    check("case4 broken-auth: dclass correct", div4.dclass == "broken-auth")
    check("case4 broken-auth: status_diff caught 401 (expected) vs 200 (actual)",
          div4.evidence.get("status_diff") is not None)

# ── CASE 5: BFLA (function-authz) ────────────────────────────────────────────
# The same trick as in case 4 (see the comment above): ctx_a = the expected 403 under a low-priv role,
# ctx_b = the actually observed 200 (the privileged function worked under a user role).
p5 = Probe(kind="function-authz", target="/api/admin/deleteUser")
ctxA5 = Context(label="expected-lowpriv-403", driver=MockDriver({
    p5.key(): {"status": 403, "fields": {}}}))
ctxB5 = Context(label="actual-lowpriv-request", driver=MockDriver({
    p5.key(): {"status": 200, "fields": {"result": "deleted"}}}))
div5 = differential(ctxA5, ctxB5, p5)
check("case5 BFLA: differential() returned a Divergence", div5 is not None)
if div5 is not None:
    pool_1_7.append(div5)
    check("case5 BFLA: dclass correct", div5.dclass == "function-authz")
    check("case5 BFLA: status_diff caught 403 (expected) vs 200 (actual, not 403)",
          div5.evidence.get("status_diff") is not None)

# ── CASE 6: tenant-isolation ─────────────────────────────────────────────────
p6 = Probe(kind="tenant-isolation", target="/api/org/tenantA/invoices/9")
ctxA6 = Context(label="tenant-A", driver=MockDriver({
    p6.key(): {"status": 200, "fields": {"invoice_id": 9, "amount": 250}}}))
ctxB6 = Context(label="tenant-B-cross-fetch", driver=MockDriver({
    p6.key(): {"status": 200, "fields": {
        "invoice_id": 9, "amount": 250, "customer_ssn": "999-00-1111"}}}))
div6 = differential(ctxA6, ctxB6, p6)
check("case6 tenant-isolation: differential() returned a Divergence", div6 is not None)
if div6 is not None:
    pool_1_7.append(div6)
    check("case6 tenant-isolation: dclass correct", div6.dclass == "tenant-isolation")
    check("case6 tenant-isolation: field_leak caught the cross-tenant leak",
          "customer_ssn" in div6.evidence.get("field_leak", []))

# ── CASE 7: N-context matrix (admin/userA/userB/unauth) ─────────────────────
p7 = Probe(kind="object-authz", target="/api/resource/A")
leaked_fields = {"id": "A", "owner": "userA", "secret": "s3cr3t"}
ctx_admin = Context(label="admin", driver=MockDriver({p7.key(): {"status": 200, "fields": leaked_fields}}))
ctx_userA = Context(label="userA", driver=MockDriver({p7.key(): {"status": 200, "fields": leaked_fields}}))
ctx_userB = Context(label="userB", driver=MockDriver({p7.key(): {"status": 200, "fields": leaked_fields}}))
ctx_unauth = Context(label="unauth", driver=MockDriver({p7.key(): {"status": 401, "fields": {}}}))
divs7 = differential_matrix([ctx_admin, ctx_userA, ctx_userB, ctx_unauth], p7)
check("case7 N-context matrix: >=1 Divergence out of 6 pairs", len(divs7) >= 1, "len=%d" % len(divs7))
check("case7 N-context matrix: each Divergence carries the label of its pair (ctx_pair of 2 different labels)",
      all(isinstance(d.ctx_pair, tuple) and len(d.ctx_pair) == 2 and d.ctx_pair[0] != d.ctx_pair[1]
          for d in divs7))
pool_1_7.extend(divs7)

# ── CASE 8: negative — identical ctx ─────────────────────────────────────────
p8 = Probe(kind="object-authz", target="/api/same")
same_resp = {"status": 200, "fields": {"a": 1}, "headers": {"H": "1"}, "body_hash": "deadbeef"}
ctxA8 = Context(label="x1", driver=MockDriver({p8.key(): dict(same_resp)}))
ctxB8 = Context(label="x2", driver=MockDriver({p8.key(): dict(same_resp)}))
div8 = differential(ctxA8, ctxB8, p8)
check("case8 negative: differential() on identical ctx returned None", div8 is None)

ra8 = Response(status=200, fields={"a": 1}, headers={"H": "1"}, body_hash="deadbeef")
rb8 = Response(status=200, fields={"a": 1}, headers={"H": "1"}, body_hash="deadbeef")
sd8 = semantic_diff(ra8, rb8)
check("case8 negative: semantic_diff(identical Response) -> diverged=False",
      sd8.get("diverged") is False, "sd8=%r" % (sd8,))

# ── CASE 9: attack_path_hint is non-empty on EACH Divergence from cases 1-7 ───────
check("case9: the pool of cases 1-7 is non-empty (there is something to check)", len(pool_1_7) >= 7,
      "len(pool_1_7)=%d" % len(pool_1_7))
check("case9: attack_path_hint is non-empty (str) on EACH of the %d Divergence of cases 1-7" % len(pool_1_7),
      all(isinstance(d.attack_path_hint, str) and d.attack_path_hint.strip() for d in pool_1_7))

# The hint values below are compared by == with what differential_observation.py emits (_ATTACK_PATH_HINTS).
# Extra check (not part of the count of 10, but cheap and catches a typo in the mapping): hint verbatim from the brief.
_EXPECTED_HINTS = {
    "signature-integrity": "trace L4 signer domain-binding: compare displayed value (DOM) against signed payload",
    "object-authz": "enumerate object IDs under ctx_B token; check ownership on write paths",
    "function-authz": "check role-gate on the privileged function; try under a low-priv role",
    "tenant-isolation": "cross-tenant fetch: ctx_B pulls tenant_A resource by direct ID",
    "clone-parity": "diff security headers/authz between deployments; look for a weakened clone",
    "broken-auth": "repeat the request without a session; check reachability of the protected resource without auth",
}
check("case9b: attack_path_hint verbatim matches the brief's mapping table on all 6 dclass",
      all(d.attack_path_hint == _EXPECTED_HINTS.get(d.dclass) for d in pool_1_7
          if d.dclass in _EXPECTED_HINTS))

# ── CASE 10: to_dnn_row() -- consumer contract with the REAL gate ────────────
row = div1.to_dnn_row()
check("case10a: gate._D_ROW_RE matches to_dnn_row()", bool(gate._D_ROW_RE.search(row)), "row=%r" % row)

# NOTE: the Russian table header rows below and the Loop State text are KEPT verbatim: they are the
# model-file format parsed by the live gate (hunt_completeness_gate.py). English gloss of the column
# headers: formula, Status, Axis, Source, Inv, Where, Rank, Resolution (the last column); Loop State text:
# "AC total" / "open D-NN" / "current".
MODEL_MD = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| TB-I01 | ∀ object fetch: ownership(caller,O) is verified | authz-mw on every method? "
    "| object-authz | OpenAPI | usersApi | ENFORCED | ABSENT | api:users | 0 | cold | authz-mw |\n"
    "## Divergences\n"
    "| ID | Инв | Где | Статус | vw | pc | t0 | conv | heat | Ранг | undup_origin | Резолюция |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    + row + "\n"
)


def _write_temp_session():
    os.makedirs(SESS, exist_ok=True)
    with open(os.path.join(SESS, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(MODEL_MD)
    with open(os.path.join(SESS, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write("## Loop State\n- Iteration #: 1\n"
                 "- **MODEL (WEB):** AC всего: 1 / ABSENT: 1 / открытых D-NN: 1 / текущий: D-01\n")  # KEPT: gate-parsed Russian text
    with open(os.path.join(SESS, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), SID))


try:
    _write_temp_session()
    result10b = gate.active_divergence_unresolved(SID)
    check("case10b: active_divergence_unresolved(SID) is NOT None -- an open D-NN from to_dnn_row() holds the turn",
          result10b is not None, "got %r" % (result10b,))
finally:
    shutil.rmtree(SESS, ignore_errors=True)

# ── CASE 11 (bonus, beyond the mandatory 10): fail-open on a driver exception ─
p11 = Probe(kind="object-authz", target="/no/such/mapped/key")
ctxA11 = Context(label="a11", driver=MockDriver({}))   # empty responses -> KeyError inside .probe()
ctxB11 = Context(label="b11", driver=MockDriver({}))
div11 = differential(ctxA11, ctxB11, p11)
check("case11 fail-open: differential() on a driver that raises an exception returned None (did not crash)",
      div11 is None)

divs11b = differential_matrix(None, p11)
check("case11b fail-open: differential_matrix(None, probe) returned [] (did not crash)",
      divs11b == [])

# ── CASE 12 (FINAL-REVIEW FIX 2 -- permanent regression, to_dnn_row() ledger injection) ──────
# Root: BEFORE the fix `dclass`/`where`(=probe.target) were interpolated into the ledger row WITHOUT
# escaping -- `|` forges extra cells (including the LAST one, which active_divergence_unresolved
# reads as the resolution), `\n` breaks the physical line so that the FIRST half (which still
# matches _D_ROW_RE) gets a random "last cell" that looks like a resolution -- the gate considers an
# OPEN divergence RESOLVED (false-negative -> premature HUNT-EXIT). Confirmed
# BEFORE the fix by the same chain: to_dnn_row() gave '| D-01 | object-authz | obj -> H-1' as the FIRST
# physical line -- _D_ROW_RE matched it, the last cell 'obj -> H-1' matched
# _DIV_RESOLVED_RE (arrow + H-NN) -> falsely RESOLVED.
MALICIOUS_TARGET = "obj -> H-1\nrow2 | KILLED file.py:1 | a|b|c"
p12 = Probe(kind="object-authz", target=MALICIOUS_TARGET)
ctxA12 = Context(label="a12", driver=MockDriver({
    p12.key(): {"status": 200, "fields": {"id": "A"}}}))
ctxB12 = Context(label="b12", driver=MockDriver({
    p12.key(): {"status": 200, "fields": {"id": "A", "leak": "x"}}}))
div12 = differential(ctxA12, ctxB12, p12)
check("case12 setup: differential() on a forged probe.target returned a Divergence (not None)",
      div12 is not None)

row12 = div12.to_dnn_row() if div12 is not None else ""
check("case12a FIX-2 regression: to_dnn_row() -- ONE physical line (no \\n/\\r inside, "
      "even when probe.target carried a line break)",
      ("\n" not in row12) and ("\r" not in row12), "row=%r" % row12)
check("case12b FIX-2 regression: gate._D_ROW_RE still matches the forged (and now sanitized) row",
      bool(gate._D_ROW_RE.search(row12)), "row=%r" % row12)
_cells12 = gate._cells(row12)
check("case12c FIX-2 regression: the row split into EXACTLY 12 template columns (Task 3: +undup_origin "
      "-- was 11, no extra cells forged via '|' inside probe.target)",
      len(_cells12) == 12, "cells=%r" % (_cells12,))
check("case12d FIX-2 regression: the LAST cell (Resolution) is empty -- NOT forged into a 'resolved' one "
      "('-> H-NN'/'KILLED file:line' from the probe.target content no longer reaches the "
      "gate's last-cell parsing)",
      not gate._DIV_RESOLVED_RE.search(_cells12[-1] if _cells12 else "x"),
      "last_cell=%r row=%r" % (_cells12[-1] if _cells12 else None, row12))

# NOTE: Russian table headers kept verbatim (gate-parsed format; see the glossary above MODEL_MD).
MODEL_MD12 = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| TB-I01 | ∀ object fetch: ownership(caller,O) is verified | authz-mw on every method? "
    "| object-authz | OpenAPI | usersApi | ENFORCED | ABSENT | api:users | 0 | cold | authz-mw |\n"
    "## Divergences\n"
    "| ID | Инв | Где | Статус | vw | pc | t0 | conv | heat | Ранг | undup_origin | Резолюция |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    + row12 + "\n"
)

SID12 = "DIFFOBS-TESTSID-Q7-FORGE"
SESS12 = os.path.join(SESSIONS, "diffobstest_forge")


def _write_temp_session_forge():
    os.makedirs(SESS12, exist_ok=True)
    with open(os.path.join(SESS12, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(MODEL_MD12)
    with open(os.path.join(SESS12, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write("## Loop State\n- Iteration #: 1\n"
                 "- **MODEL (WEB):** AC всего: 1 / ABSENT: 1 / открытых D-NN: 1 / текущий: D-01\n")  # KEPT: gate-parsed Russian text
    with open(os.path.join(SESS12, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), SID12))


try:
    _write_temp_session_forge()
    result12e = gate.active_divergence_unresolved(SID12)
    check("case12e FIX-2 regression: active_divergence_unresolved(SID12) is NOT None -- the gate STILL "
          "sees the divergence as OPEN (forge blocked; BEFORE the fix this was None -- falsely "
          "'resolved', HUNT-EXIT could pass prematurely)",
          result12e is not None, "got %r" % (result12e,))
finally:
    shutil.rmtree(SESS12, ignore_errors=True)

# ── bonus FIX 2: _cell() -- direct contract (the sanitizer, not only via to_dnn_row) ─────────
check("bonus _cell: '|' -> '/'", dobs._cell("a|b|c") == "a/b/c", "got %r" % dobs._cell("a|b|c"))
check("bonus _cell: \\n/\\r/tab collapse into a single space",
      dobs._cell("a\nb\r\nc\td") == "a b c d", "got %r" % dobs._cell("a\nb\r\nc\td"))
check("bonus _cell: a long value is truncated to _CELL_MAX_LEN (+truncation marker)",
      len(dobs._cell("X" * 500)) <= dobs._CELL_MAX_LEN + 3, "len=%d" % len(dobs._cell("X" * 500)))
check("bonus _cell(None): does not crash, coerces to str", dobs._cell(None) == "None",
      "got %r" % dobs._cell(None))

# ── CASE 13 (design-note closure: spec_baseline_context for ASYMMETRIC dclass) ────────────
# broken-auth / function-authz(BFLA) have no two live peers -- we compare the spec EXPECTATION
# (401/403) against the observed (200). spec_baseline_context() does this first-class (closing the
# final review's design-note: the primitive now natively supports both forms of comparison).
p13ba = Probe(kind="broken-auth", target="/api/admin/secret")
spec401 = dobs.spec_baseline_context("spec-401", 401)
observed200 = Context(label="observed", driver=MockDriver({
    p13ba.key(): {"status": 200, "fields": {"secret": "x"}}}))
div13ba = differential(spec401, observed200, p13ba)
check("case13a spec_baseline: broken-auth (spec 401 vs observed 200) -> Divergence dclass=broken-auth",
      div13ba is not None and div13ba.dclass == "broken-auth", "got %r" % (div13ba,))
check("case13a2 spec_baseline: the STATUS divergence is recorded (401 vs 200)",
      div13ba is not None and isinstance(div13ba.evidence, dict)
      and div13ba.evidence.get("status_diff") == {"a": 401, "b": 200},
      "evidence=%r" % (div13ba.evidence if div13ba else None,))

p13bfla = Probe(kind="function-authz", target="/api/admin/deleteUser")
spec403 = dobs.spec_baseline_context("spec-403", 403)
observed200b = Context(label="low-priv", driver=MockDriver({p13bfla.key(): {"status": 200}}))
div13bfla = differential(spec403, observed200b, p13bfla)
check("case13b spec_baseline: function-authz/BFLA (spec 403 vs low-priv 200) -> Divergence dclass=function-authz",
      div13bfla is not None and div13bfla.dclass == "function-authz", "got %r" % (div13bfla,))

check("case13c spec_baseline_context() -> Context with StaticDriver (role=spec-baseline)",
      isinstance(spec401, dobs.Context) and isinstance(spec401.driver, dobs.StaticDriver)
      and spec401.role == "spec-baseline")
_probe_any = Probe(kind="broken-auth", target="/whatever/else")
check("case13d StaticDriver: a fixed Response on ANY probe (probe.key() is ignored)",
      spec401.driver.probe(_probe_any).status == 401)

# ── CASE 14 (Task 3, FDE Plan 6 §48.2/§44/§50.3): to_dnn_row() undup_origin -- gate-integration ──
# to_dnn_row() emits the default `{TODO}` in the 11th cell (BEFORE the empty Resolution) -- active_undup_origin_missing
# must count this as "missing" on a MATURE model (>=3 statused I-NN), identical to the same pattern as
# case10b (active_divergence_unresolved) for the same row.
row14 = div1.to_dnn_row()
check("case14a: to_dnn_row() carries '{TODO}' as the second-to-last cell (undup_origin default)",
      gate._cells(row14)[-2] == "{TODO}", "cells=%r" % (gate._cells(row14),))

# NOTE: Russian table headers kept verbatim (gate-parsed format; see the glossary above MODEL_MD).
MODEL_MD14_TODO = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| TB-I01 | f1 | c1 | object-authz | docs | c1 | ENFORCED | ENFORCED | a:1 | 0 | cold | |\n"
    "| TB-I02 | f2 | c2 | object-authz | docs | c2 | ENFORCED | ENFORCED | a:2 | 0 | cold | |\n"
    "| TB-I03 | f3 | c3 | object-authz | docs | c3 | ENFORCED | ENFORCED | a:3 | 0 | cold | |\n"
    "## Divergences\n"
    "| ID | Инв | Где | Статус | vw | pc | t0 | conv | heat | Ранг | undup_origin | Резолюция |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    + row14 + "\n"
)

SID14 = "DIFFOBS-TESTSID-Q7-UNDUP"
SESS14 = os.path.join(SESSIONS, "diffobstest_undup")


def _write_temp_session14(model_txt):
    os.makedirs(SESS14, exist_ok=True)
    with open(os.path.join(SESS14, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(model_txt)
    with open(os.path.join(SESS14, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write("## Loop State\n- Iteration #: 1\n"
                 "- **MODEL (WEB):** AC всего: 3 / ABSENT: 1 / открытых D-NN: 1 / текущий: D-01\n")  # KEPT: gate-parsed Russian text
    with open(os.path.join(SESS14, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), SID14))


try:
    _write_temp_session14(MODEL_MD14_TODO)
    result14b = gate.active_undup_origin_missing(SID14)
    check("case14b: active_undup_origin_missing(SID14) is NOT None -- the default '{TODO}' from to_dnn_row() "
          "holds the turn on a mature (>=3 statused) model", result14b is not None, "got %r" % (result14b,))
finally:
    shutil.rmtree(SESS14, ignore_errors=True)

MODEL_MD14_FILLED = MODEL_MD14_TODO.replace(
    gate._cells(row14)[-2], "composition-seam", 1)
try:
    _write_temp_session14(MODEL_MD14_FILLED)
    result14c = gate.active_undup_origin_missing(SID14)
    check("case14c: undup_origin filled in manually ('composition-seam') -> active_undup_origin_missing "
          "is silent (the agent filled in the source of the PLACE)", result14c is None, "got %r" % (result14c,))
finally:
    shutil.rmtree(SESS14, ignore_errors=True)

# ── CASE 15 (Task 10, carry BS-05): ownership_diff() -- full-leak BOLA FIRING ────────────────────
# The BS-05 gap in one shot: ctxB-for-A's-object is BYTE-IDENTICAL to ctxA's own response
# (semantic_diff(ctxA, ctxB) would report diverged=False -- 0 divergences, the exact false-negative
# BS-05 documents). ownership_diff() compares it instead against ctxB's OWN object self-baseline
# (owner_id="user-B") -- the owner_id in the "for A" body ("user-A") mismatches -> flagged.
p15 = Probe(kind="object-authz", target="/api/objects/A")
ctx_b_for_a = Context(label="user-B", driver=MockDriver({
    p15.key(): {"status": 200, "fields": {"owner_id": "user-A", "balance": 999}}}))
ctx_b_own = Context(label="user-B-own", driver=MockDriver({
    p15.key(): {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}}}))
div15 = ownership_diff(ctx_b_for_a, ctx_b_own, p15)
check("case15a ownership_diff FIRING: returns a Divergence (not None) on full-leak (byte-identical to A's own baseline)",
      div15 is not None, "got=%r" % (div15,))
if div15 is not None:
    check("case15b ownership_diff FIRING: dclass == 'object-authz'", div15.dclass == "object-authz")
    check("case15c ownership_diff FIRING: severity_seed == 'high'", div15.severity_seed == "high")
    check("case15d ownership_diff FIRING: evidence.owner_mismatch names owner_id (self='user-B', target='user-A')",
          isinstance(div15.evidence, dict) and
          div15.evidence.get("owner_mismatch", {}).get("owner_id") == {"self": "user-B", "target": "user-A"},
          "evidence=%r" % (div15.evidence,))

# Cross-check against the equality-based primitive on the SAME fixture: this is the exact BS-05
# false-negative -- differential() sees no divergence at all on the byte-identical mirror.
div15_equality = differential(
    Context(label="user-A", driver=MockDriver({p15.key(): {"status": 200, "fields": {"owner_id": "user-A", "balance": 999}}})),
    ctx_b_for_a, p15)
check("case15e BS-05 cross-check: equality-based differential() on the SAME byte-identical mirror returns None "
      "(confirms the gap ownership_diff() closes)", div15_equality is None, "got=%r" % (div15_equality,))

# ── CASE 16 (Task 10): ownership_diff() -- own-object NEGATIVE (B-for-B must NOT be flagged) ─────
ctx_b_for_own_object = Context(label="user-B", driver=MockDriver({
    p15.key(): {"status": 200, "fields": {"owner_id": "user-B", "balance": 10}}}))
div16 = ownership_diff(ctx_b_for_own_object, ctx_b_own, p15)
check("case16a ownership_diff NEGATIVE: legit self-access (owner matches self-baseline) -> None (no FP)",
      div16 is None, "got=%r" % (div16,))

# ── CASE 17 (Task 10): ownership_diff() -- no-owner-field INCONCLUSIVE ────────────────────────────
ctx_no_owner_target = Context(label="user-B", driver=MockDriver({
    p15.key(): {"status": 200, "fields": {"data": "opaque-payload"}}}))
ctx_no_owner_self = Context(label="user-B-own", driver=MockDriver({
    p15.key(): {"status": 200, "fields": {"data": "other-opaque-payload"}}}))
div17 = ownership_diff(ctx_no_owner_target, ctx_no_owner_self, p15)
check("case17a ownership_diff INCONCLUSIVE: no known owner-marker field in body -> Divergence, not None",
      div17 is not None, "got=%r" % (div17,))
check("case17b ownership_diff INCONCLUSIVE: dclass == '[INCONCLUSIVE-NO-OWNER-MARKER]' (not a silent miss, not a FP)",
      div17 is not None and div17.dclass == "[INCONCLUSIVE-NO-OWNER-MARKER]", "got=%r" % (div17,))
check("case17c ownership_diff INCONCLUSIVE: severity_seed == 'info' (not high -- no confirmed leak)",
      div17 is not None and div17.severity_seed == "info")

# ── CASE 18 (Task 10): ownership_diff() -- comparable-key-missing also INCONCLUSIVE, not a false negative ──
# Owner-marker key IS present in the target body, but self-baseline lacks that specific key -> no
# value to compare against -> INCONCLUSIVE, not silently swallowed as None.
ctx_target_has_marker = Context(label="user-B", driver=MockDriver({
    p15.key(): {"status": 200, "fields": {"owner_id": "user-A"}}}))
ctx_self_missing_marker = Context(label="user-B-own", driver=MockDriver({
    p15.key(): {"status": 200, "fields": {"data": "no-owner-key-here"}}}))
div18 = ownership_diff(ctx_target_has_marker, ctx_self_missing_marker, p15)
check("case18a ownership_diff INCONCLUSIVE (no comparable key): dclass == '[INCONCLUSIVE-NO-OWNER-MARKER]'",
      div18 is not None and div18.dclass == "[INCONCLUSIVE-NO-OWNER-MARKER]", "got=%r" % (div18,))

# ── CASE 19 (Task 10): ownership_diff() -- fail-open on driver exception ─────────────────────────
ctx_broken = Context(label="broken", driver=MockDriver({}))  # empty responses -> KeyError inside .probe()
div19 = ownership_diff(ctx_broken, ctx_broken, p15)
check("case19a ownership_diff fail-open: driver exception -> None (no crash)", div19 is None)

# ── CASE 20 (Plan 7 Task 1, §60 AI-surface): ai-trust dclass -- 3 registration points + to_dnn_row is generic ──
# Task 1 registers the new dclass `ai-trust` in THREE places (Probe.KINDS / _ATTACK_PATH_HINTS /
# _SEVERITY_SEED) and does NOT touch the to_dnn_row() emitter -- it must serve ai-trust generically, like
# the 6 original dclass. Below: (a-c) the three registration points; (d-h) differential catches an ai-trust
# divergence with the correct hint/severity/fields; (i-l) to_dnn_row is generic (matches the gate, 12 columns).
check("case20a ai-trust registered in Probe.KINDS", "ai-trust" in dobs.Probe.KINDS)
check("case20b ai-trust has attack_path_hint (mapped, not default)",
      "ai-trust" in dobs._ATTACK_PATH_HINTS and bool(dobs._ATTACK_PATH_HINTS["ai-trust"].strip()))
check("case20c ai-trust severity_seed == 'high' (the main vector of §60.1)",
      dobs._SEVERITY_SEED.get("ai-trust") == "high", "got %r" % (dobs._SEVERITY_SEED.get("ai-trust"),))

p20 = Probe(kind="ai-trust", target="/api/assistant/chat")
ctx_benign20 = Context(label="benign", driver=MockDriver({
    p20.key(): {"status": 200, "fields": {"answer": "Here is your balance."}}}))
ctx_inj20 = Context(label="injection", driver=MockDriver({
    p20.key(): {"status": 200, "fields": {
        "answer": "Here is your balance.",
        "tool_called": "refund",
        "system_prompt_revealed": "You are the support agent...",
        "canary_echoed": True}}}))
div20 = differential(ctx_benign20, ctx_inj20, p20)
check("case20d ai-trust: differential() returned a Divergence", div20 is not None)
if div20 is not None:
    check("case20e ai-trust: dclass == 'ai-trust'", div20.dclass == "ai-trust")
    check("case20f ai-trust: severity_seed == 'high' (from _SEVERITY_SEED, not _DEFAULT_SEVERITY)",
          div20.severity_seed == "high", "got %r" % (div20.severity_seed,))
    check("case20g ai-trust: attack_path_hint == mapped hint (not _DEFAULT_HINT)",
          div20.attack_path_hint == dobs._ATTACK_PATH_HINTS["ai-trust"]
          and div20.attack_path_hint != dobs._DEFAULT_HINT)
    check("case20h ai-trust: field_leak names the injected observable vectors (v1/v4/v8)",
          {"tool_called", "system_prompt_revealed", "canary_echoed"}.issubset(
              set(div20.evidence.get("field_leak", []))),
          "field_leak=%r" % (div20.evidence.get("field_leak"),))
    row20 = div20.to_dnn_row()
    check("case20i ai-trust: to_dnn_row() matches gate._D_ROW_RE (the emitter is generic, NOT touched by Task 1)",
          bool(gate._D_ROW_RE.search(row20)), "row=%r" % row20)
    cells20 = gate._cells(row20)
    check("case20j ai-trust: to_dnn_row() -> EXACTLY 12 columns (generic 12-col format)",
          len(cells20) == 12, "cells=%r" % (cells20,))
    check("case20k ai-trust: the dclass cell carries 'ai-trust'", cells20[1] == "ai-trust", "cells=%r" % (cells20,))
    check("case20l ai-trust: the last cell (Resolution) is empty -- an open divergence holds the turn",
          not gate._DIV_RESOLVED_RE.search(cells20[-1]), "last=%r" % (cells20[-1],))

# Negative/default branch: an unknown dclass still falls back to _DEFAULT_HINT/_DEFAULT_SEVERITY (Task 1
# added ai-trust to the enum, but did NOT break the generic fallback for a kind outside the enum).
p20u = Probe(kind="totally-unknown-kind", target="/x")
div20u = differential(
    Context(label="a", driver=MockDriver({p20u.key(): {"status": 200, "fields": {"a": 1}}})),
    Context(label="b", driver=MockDriver({p20u.key(): {"status": 200, "fields": {"a": 1, "b": 2}}})),
    p20u)
check("case20m unknown-kind: fallback to _DEFAULT_HINT/_DEFAULT_SEVERITY preserved (ai-trust did not break generic)",
      div20u is not None and div20u.attack_path_hint == dobs._DEFAULT_HINT
      and div20u.severity_seed == dobs._DEFAULT_SEVERITY)

# ── CASE 21 (A8, Wave 1): differential → contract mode (ContractDriver) + family-fork-diff ──
ContractDriver = dobs.ContractDriver
contract_context = dobs.contract_context
family_fork_diff = dobs.family_fork_diff
identify_parent = dobs.identify_parent

# 21a — ContractDriver: a bare fields-dict observation → Response(fields=...).
_cd = ContractDriver({"slot:totalAssets": {"rate": 100, "src": "balanceOf"}})
_r = _cd.probe(Probe("contract-mock-vs-prod", "slot:totalAssets"))
check("case21a ContractDriver: bare-dict observation → Response.fields",
      isinstance(_r, Response) and _r.fields.get("src") == "balanceOf", "got=%r" % (_r,))
# 21a2 — a missing key → an empty Response (not KeyError, contract semantics "boundary not touched").
_r0 = _cd.probe(Probe("contract-mock-vs-prod", "slot:missing"))
check("case21a2 ContractDriver: no key → empty Response (no crash)",
      isinstance(_r0, Response) and _r0.fields == {})

# 21b — mock != prod → Divergence (the mock-vs-prod class).
mock = contract_context("mock", {"call:previewRedeem": {"assets": 100}})
prod = contract_context("prod", {"call:previewRedeem": {"assets": 95}})
div21b = differential(mock, prod, Probe("contract-mock-vs-prod", "call:previewRedeem"))
check("case21b contract mock≠prod → Divergence (dclass contract-mock-vs-prod, severity high)",
      div21b is not None and div21b.dclass == "contract-mock-vs-prod" and div21b.severity_seed == "high",
      "got=%r" % (div21b,))

# 21c — parent ≡ fork on copied code → None (no delta).
parent = contract_context("canonical-parent", {"call:swap": {"kCheck": "1000**2", "scale": 1000}})
fork_copy = contract_context("fork-copied", {"call:swap": {"kCheck": "1000**2", "scale": 1000}})
div21c = family_fork_diff(parent, fork_copy, "call:swap")
check("case21c family-fork parent≡fork (copied unchanged) → None (no delta)",
      div21c is None, "got=%r" % (div21c,))

# 21d — parent != fork in a modified function → Divergence-on-delta.
fork_mod = contract_context("fork-modified", {"call:swap": {"kCheck": "10000", "scale": 1000}})
div21d = family_fork_diff(parent, fork_mod, "call:swap")
check("case21d family-fork parent≠fork (the fork broke the k scale) → Divergence-on-delta",
      div21d is not None and div21d.dclass == "contract-family-fork"
      and "kCheck" in (div21d.evidence or {}).get("field_leak", []),
      "got=%r" % (div21d,))

# 21e — identify_parent: the canonical fingerprint in the fork's code → the parent is identified.
_fps = [("UniswapV2-fork k-check", r"balance0Adjusted\s*\*\s*balance1Adjusted"),
        ("ReentrancyGuard", r"\bnonReentrant\b")]
_fork_src = "function swap(...) { require(balance0Adjusted * balance1Adjusted >= k); }"
_parents = identify_parent(_fps, _fork_src)
check("case21e identify_parent: canonical fingerprint in the fork's code → parent identified (UniswapV2), the unrelated one is not",
      any(n.startswith("UniswapV2") for n, _ in _parents) and not any("Reentrancy" in n for n, _ in _parents),
      "got=%r" % (_parents,))

# 21f — a contract Divergence emits a valid D-NN row (the same to_dnn_row contract).
check("case21f contract Divergence.to_dnn_row(): a valid 12-column D-NN row",
      div21d.to_dnn_row().count("|") == 13 and "contract-family-fork" in div21d.to_dnn_row(),
      "got=%r" % (div21d.to_dnn_row(),))


print("=== DIFFERENTIAL OBSERVATION REPLAY (Plan 3 Task 1, §35.1) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
