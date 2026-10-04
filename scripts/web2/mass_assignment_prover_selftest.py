# -*- coding: utf-8 -*-
"""Selftest for the write-side BOPLA / mass-assignment prover (Plan 9, Task T1).

Turns the static field-name matcher (business_logic.mass_assignment_fields) into an ACTIVE prover:
compose the existing probe + semantic_diff into a WRITE-then-READ-BACK loop on two accounts --
inject a privileged field on WRITE, read the object back, semantic_diff prover-vs-baseline. A
change that PERSISTS = a NEW finding class (mass-assignment / BOPLA), mirroring ownership_diff on
the read-side.

Proves FIRING (not just absence of FP):
 (1) business_logic.mass_assignment_write_plan builds a write payload that INJECTS the privileged
     candidate field(s) and describes the write->read-back loop (execution NOT here).
 (2) differential_observation.mass_assignment_diff:
     (a) injected privileged field REFLECTED on read-back (server persisted it) -> DETECTED as an
         object-authz Divergence (the FIRING case).
     (b) injected field IGNORED/normalized by server (read-back == baseline default) -> NOT a
         finding (None) -- the key falsifier: a rejected field must not fire.
     (c) injected field NOT reflected in read-back body at all -> INCONCLUSIVE Divergence
         (cannot prove persistence != no leak), not a silent pass and not a FP.
     (d) field injected that is NOT privileged persists -> still fires only on the fields caller
         passed as injected_fields (scoping proof).
 (3) End-to-end: candidate fields from mass_assignment_fields() -> write_plan -> mass_assignment_diff
     detects the persisted privileged field.

Run: py -3 -X utf8 bug-bounty-toolkit/scripts/web2/mass_assignment_prover_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
WEB2_DIR = os.path.join(ROOT, "scripts", "web2")
METH_DIR = os.path.join(ROOT, "scripts", "_methodology")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


dobs = _load("differential_observation", os.path.join(METH_DIR, "differential_observation.py"))
bl = _load("business_logic", os.path.join(WEB2_DIR, "business_logic.py"))

Response = dobs.Response
Probe = dobs.Probe
Context = dobs.Context
MockDriver = dobs.MockDriver

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def _ctx(label, responses):
    """Context wrapping a MockDriver keyed by probe.key()."""
    return Context(label=label, driver=MockDriver(responses), role=label)


# ── CASE 1: write-plan injects the privileged field ──────────────────────────────────────────────
plan = bl.mass_assignment_write_plan("/api/users/me", ["is_admin", "role"])
payload = plan.get("inject_payload", {})
check("1a write_plan injects is_admin", "is_admin" in payload, str(payload))
check("1b write_plan injects role", "role" in payload, str(payload))
check("1c write_plan records injected_fields", set(plan.get("injected_fields", [])) == {"is_admin", "role"},
      str(plan.get("injected_fields")))
check("1d write_plan execution NOT performed here", "not here" in str(plan.get("execution", "")).lower(),
      str(plan.get("execution")))
check("1e write_plan describes read-back step", "read" in str(plan.get("readback", "")).lower(),
      str(plan.get("readback")))

# ── CASE 2a: FIRING -- injected privileged field PERSISTS on read-back ────────────────────────────
# prover: WRITE (any recorded response) then READ-BACK showing is_admin=True (server persisted it).
# baseline: control object read-back showing the safe default is_admin=False.
write_probe = Probe("object-authz", "/api/users/me", payload={"is_admin": True})
readback = Probe("object-authz", "/api/users/me", payload={})

prover_resp = {
    write_probe.key(): {"status": 200, "fields": {"id": 1, "name": "eve"}},
    readback.key(): {"status": 200, "fields": {"id": 1, "name": "eve", "is_admin": True}},
}
baseline_resp = {
    readback.key(): {"status": 200, "fields": {"id": 2, "name": "control", "is_admin": False}},
}
ctx_prover = _ctx("prover", prover_resp)
ctx_baseline = _ctx("baseline", baseline_resp)

div = dobs.mass_assignment_diff(ctx_prover, ctx_baseline, write_probe, readback, ["is_admin"])
check("2a-i persisted privileged field FIRES a Divergence", div is not None, repr(div))
check("2a-ii dclass == object-authz", div is not None and div.dclass == "object-authz",
      div.dclass if div else None)
check("2a-iii severity high", div is not None and div.severity_seed == "high",
      div.severity_seed if div else None)
check("2a-iv evidence names the persisted field",
      div is not None and "is_admin" in str(div.evidence.get("mass_assignment", {})),
      str(div.evidence) if div else None)

# ── CASE 2b: FALSIFIER -- server IGNORED the injected field (read-back == safe default) ───────────
prover_ignored = {
    write_probe.key(): {"status": 200, "fields": {"id": 1, "name": "eve"}},
    readback.key(): {"status": 200, "fields": {"id": 1, "name": "eve", "is_admin": False}},
}
ctx_prover_ig = _ctx("prover", prover_ignored)
div_ig = dobs.mass_assignment_diff(ctx_prover_ig, ctx_baseline, write_probe, readback, ["is_admin"])
check("2b rejected/ignored field does NOT fire (None)", div_ig is None, repr(div_ig))

# ── CASE 2c: INCONCLUSIVE -- injected field not reflected in read-back body ───────────────────────
prover_absent = {
    write_probe.key(): {"status": 200, "fields": {"id": 1, "name": "eve"}},
    readback.key(): {"status": 200, "fields": {"id": 1, "name": "eve"}},
}
ctx_prover_ab = _ctx("prover", prover_absent)
div_ab = dobs.mass_assignment_diff(ctx_prover_ab, ctx_baseline, write_probe, readback, ["is_admin"])
check("2c-i field-not-reflected -> a Divergence (not silent None)", div_ab is not None, repr(div_ab))
check("2c-ii dclass is INCONCLUSIVE marker",
      div_ab is not None and "INCONCLUSIVE" in div_ab.dclass, div_ab.dclass if div_ab else None)

# ── CASE 2d: scoping -- only caller-declared injected_fields count ────────────────────────────────
# read-back diverges on 'is_admin' AND an incidental 'last_login' timestamp; caller only declared
# is_admin -> fires (is_admin persisted); if caller declares only a NON-persisted field -> None.
prover_scoped = {
    write_probe.key(): {"status": 200, "fields": {}},
    readback.key(): {"status": 200, "fields": {"id": 1, "is_admin": True, "last_login": "t2"}},
}
baseline_scoped = {
    readback.key(): {"status": 200, "fields": {"id": 2, "is_admin": False, "last_login": "t1"}},
}
csp = _ctx("prover", prover_scoped)
csb = _ctx("baseline", baseline_scoped)
d_scoped = dobs.mass_assignment_diff(csp, csb, write_probe, readback, ["is_admin"])
check("2d-i declared privileged field is_admin persisted -> fires", d_scoped is not None, repr(d_scoped))
# declaring only 'balance' (which prover did NOT set / not present) -> inconclusive, not a false fire
d_wrongfield = dobs.mass_assignment_diff(csp, csb, write_probe, readback, ["balance"])
check("2d-ii undeclared/absent field 'balance' -> does NOT fire as object-authz",
      d_wrongfield is None or "INCONCLUSIVE" in getattr(d_wrongfield, "dclass", ""),
      repr(d_wrongfield))

# ── CASE 3: end-to-end from mass_assignment_fields candidate generator ────────────────────────────
cands = bl.mass_assignment_fields({"fields": ["name", "is_admin"]})
check("3a candidates from schema hint == [is_admin]", cands == ["is_admin"], str(cands))
e2e_plan = bl.mass_assignment_write_plan("/api/users/me", cands)
e2e_div = dobs.mass_assignment_diff(ctx_prover, ctx_baseline, write_probe, readback,
                                    e2e_plan.get("injected_fields", []))
check("3b end-to-end: candidate -> write_plan -> diff detects persisted BOPLA", e2e_div is not None,
      repr(e2e_div))

# ── CASE 4: fail-open (driver raises) ─────────────────────────────────────────────────────────────
class _Boom(object):
    def probe(self, p):
        raise RuntimeError("boom")


boom_ctx = Context(label="boom", driver=_Boom())
check("4 fail-open: driver exception -> None (never crash)",
      dobs.mass_assignment_diff(boom_ctx, ctx_baseline, write_probe, readback, ["is_admin"]) is None)

print("=== mass_assignment_prover (Plan 9 T1) SELFTEST ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
