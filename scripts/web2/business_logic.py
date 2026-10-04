# -*- coding: utf-8 -*-
"""business_logic.py -- business-logic sub-model for the web2 profile (FDE Plan 5, Task 6).

Business-logic ("BL-") is the 6th web2 axis (`system_model_web_template.md` §Invariant Wave Axes,
namespace `AC-`): race / replay / workflow-skip / quantity-abuse. Its source is the UI-flow +
docs SEQUENCE, NOT an API schema (that is the `openapi_to_acnn.py` / object-authz world) -- two
requests can each be individually authz-correct and still let an attacker skip a step, replay a
one-shot action, or win a TOCTOU race.

Everything here is a PLAN / CANDIDATE generator, deterministic and offline (stdlib-only, no
network). It never issues a request. Actual concurrent-probe EXECUTION belongs to an agent running
under `opsec_preflight.preflight("web2", ...)` (fail-closed OPSEC gate) -- white-hat boundary: a
race harness targets the tester's OWN idempotent-safe resource, never live money-movement on a
victim account. Post-execution outcome comparison is `differential_observation.differential` /
`semantic_diff`, also out of scope for this module.

Usage:
    py -3 -X utf8 business_logic.py   # (library; no CLI -- imported by state_machine_analyzer.py
                                       # web2 branch and by the agent doing the hunt)
"""
import re

# ── 1. race_candidates ──────────────────────────────────────────────────────────────────────────
# One-shot verbs: an endpoint whose name suggests "this can happen exactly once" is a TOCTOU race
# candidate (redeem-twice / vote-twice / withdraw-twice class).
_RACE_VERBS = ("redeem", "coupon", "vote", "transfer", "withdraw", "apply", "claim")
_RACE_VERB_RE = re.compile(r"\b(" + "|".join(_RACE_VERBS) + r")\b", re.IGNORECASE)
# Static/asset paths are never one-shot business actions -- excluded even if a verb coincidentally
# matched (defense-in-depth; none of _RACE_VERBS collides with a common asset name today).
_STATIC_ASSET_RE = re.compile(r"(?:^|/)static/|\.(?:png|jpe?g|gif|svg|css|js|ico|woff2?|map)$", re.IGNORECASE)


def race_candidates(urls):
    """List of endpoints matching a one-shot verb -> TOCTOU race candidates.

    `urls`: list[str]. Returns list[dict]: {"url", "verb", "why"}. `/static/logo` etc are never
    candidates (no one-shot verb, and explicitly excluded as a static-asset path)."""
    out = []
    for u in urls or []:
        if not isinstance(u, str) or not u:
            continue
        if _STATIC_ASSET_RE.search(u):
            continue
        m = _RACE_VERB_RE.search(u)
        if not m:
            continue
        verb = m.group(1).lower()
        out.append({
            "url": u,
            "verb": verb,
            "why": "one-shot verb '%s' on the path -> TOCTOU race candidate (redeem-twice / "
                   "vote-twice / over-withdraw class)" % verb,
        })
    return out


# ── 2. race_probe_plan ──────────────────────────────────────────────────────────────────────────
def race_probe_plan(endpoint, n=20):
    """PLAN of N concurrent idempotent-safe probes against `endpoint` -- single-packet / last-byte
    sync semantics (turbo-intruder-style TRUE concurrency, not a naive for-loop, which serialises
    and hides the race window). Every probe is marked `idempotent_safe`: the plan targets the
    tester's OWN disposable resource (e.g. tester's own single-use coupon), never a live
    money-movement action against a third party.

    Returns a dict describing the plan; it does NOT execute anything (`execution` field says so
    explicitly -- an agent runs it under `opsec_preflight.preflight("web2", ...)`, then diffs the
    N outcomes with `differential_observation.differential`/`semantic_diff`)."""
    try:
        n = max(1, int(n))
    except (TypeError, ValueError):
        n = 20
    return {
        "endpoint": endpoint,
        "n": n,
        "technique": "single-packet (turbo-intruder-style true concurrency / last-byte sync) -- "
                      "NOT a sequential for-loop, which serialises requests and closes the race window",
        "probes": [{"idx": i, "method": "POST", "idempotent_safe": True} for i in range(n)],
        "idempotent_safe": True,
        "execution": "NOT HERE -- agent runs the plan under opsec_preflight.preflight('web2', ...) "
                      "(fail-closed gate); this function only describes the plan",
        "diff": "post-execution: differential_observation.differential(...)/semantic_diff over the "
                "N response outcomes -- did more than one probe succeed where only one should have?",
    }


# ── 3. method_matrix ────────────────────────────────────────────────────────────────────────────
_METHOD_MATRIX = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")


def method_matrix(endpoint):
    """HTTP-method matrix for `endpoint` -- operator question: 'is authz enforced identically on
    EVERY method, or does one verb (HEAD/OPTIONS-adjacent, PUT-instead-of-POST) skip the check?'
    `endpoint` is accepted for call-site symmetry with the rest of the module; the matrix itself is
    method-universal (fixed 6 verbs), not endpoint-specific."""
    return list(_METHOD_MATRIX)


# ── 4. mass_assignment_fields ───────────────────────────────────────────────────────────────────
# BOPLA/mass-assignment candidate fields: anything that looks like a privilege/value knob a client
# should never be able to set directly (vs. a display-only field like "name").
_MASS_ASSIGN_RE = re.compile(r"role|admin|balance|verified", re.IGNORECASE)


def mass_assignment_fields(schema_hint):
    """BOPLA/mass-assignment candidates out of a `schema_hint_leak`-shaped dict (`error_oracle.py`,
    Task 4: `{"fields": [...], "tables": [...]}`). Returns the subset of `fields` that look like a
    privilege/value knob (role/is_admin/balance/verified), not a schema of their own."""
    if not isinstance(schema_hint, dict):
        return []
    fields = schema_hint.get("fields") or []
    return [f for f in fields if isinstance(f, str) and _MASS_ASSIGN_RE.search(f)]


def mass_assignment_write_plan(endpoint, fields, value=True):
    """PLAN for the ACTIVE write-side BOPLA prover (Plan 9 Task T1) -- turns the static field-name
    candidates from `mass_assignment_fields` into a write-then-read-back loop, mirroring how
    `race_probe_plan` turns `race_candidates` into a concurrency plan.

    `fields`: iterable of privileged field names to INJECT on the write (feed it the output of
    `mass_assignment_fields`). `value`: the privileged value to attempt (default True; caller can
    pass a role string / an over-large balance for the value-knob class).

    Returns a dict describing: the write payload that injects the privileged field(s), the read-back
    step, and the diff step -- it does NOT execute anything. Execution + the actual prove/refute is
    `differential_observation.mass_assignment_diff(ctx_prover, ctx_baseline, write_probe,
    readback_probe, injected_fields)`, run by an agent under `opsec_preflight.preflight('web2', ...)`
    (fail-closed OPSEC gate) against the tester's OWN account (never mutating a victim's state)."""
    injected = [f for f in (fields or []) if isinstance(f, str) and f]
    return {
        "endpoint": endpoint,
        "injected_fields": injected,
        "inject_payload": {f: value for f in injected},
        "readback": "GET the object back after the write -- a 200 on the write proves NOTHING "
                    "(servers silently drop unknown/unauthorized fields); ONLY the read-back proves "
                    "the privileged field persisted",
        "execution": "NOT HERE -- agent runs write+read-back under opsec_preflight.preflight('web2', "
                     "...) against the tester's OWN object; this function only describes the plan",
        "diff": "differential_observation.mass_assignment_diff(ctx_prover, ctx_baseline, "
                "write_probe, readback_probe, injected_fields) -- read-back vs baseline should-be "
                "state; a persisted injected field = mass-assignment/BOPLA (mirror of ownership_diff "
                "on the write path)",
    }


# ── 5. analyze_business_flow -- statem/replay/skip candidates from a UI-flow sequence ─────────────
# Re-exported (same logic) as `analyze_business_flow` in
# scripts/web3/advanced/state_machine_analyzer.py's web2 branch -- see that file's module docstring.
_REPLAY_VERBS = ("checkout", "purchase", "apply_coupon", "apply", "redeem", "submit", "pay", "claim",
                  "vote", "transfer")
_SKIP_GATE_VERBS = ("pay", "payment", "verify", "confirm", "authenticate", "2fa", "otp", "approve")
_SKIP_TARGET_VERBS = ("ship", "fulfill", "grant", "unlock", "activate", "deliver", "withdraw",
                        "release", "download")


def _step_name(step):
    if isinstance(step, dict):
        return str(step.get("action") or step.get("name") or step.get("step") or step)
    return str(step)


def _bl_row(n, flow, invariant, vector, check):
    """One BL-NN candidate -- matches `system_model_web_template.md` `## Business Logic` table:
    `| BL-NN | flow | invariant | vector (race/replay/skip) | check: | Status |`. Status is always
    the skeleton sentinel `{TODO}` here -- this module only GENERATES candidates; the agent
    triages/confirms them during the hunt (mirrors `openapi_to_acnn.to_acnn_skeleton`'s contract)."""
    return {
        "id": "BL-%02d" % n,
        "flow": flow,
        "invariant": invariant,
        "vector": vector,  # race | replay | skip
        "check": check,
        "status": "{TODO}",
    }


def analyze_business_flow(flow_steps):
    """UI-flow step sequence -> list[dict] of BL-NN candidates (race/replay/skip).

    `flow_steps`: list of str OR dict (`{"action"|"name"|"step": ...}`), in UI-observed order.
    Source = UI-flow + docs SEQUENCE, NOT an API schema -- two authz-correct requests can still
    let an attacker skip a step or replay a one-shot one."""
    steps = flow_steps or []
    names = [_step_name(s) for s in steps]
    lowered = [n.lower() for n in names]

    rows = []
    n = 0

    for name, low in zip(names, lowered):
        if _RACE_VERB_RE.search(low):
            n += 1
            rows.append(_bl_row(
                n, name, "one-shot action applies at most once",
                "race",
                "fire N concurrent requests at this step (race_probe_plan) -- does the "
                "one-shot effect apply more than once?"))
        if any(v in low for v in _REPLAY_VERBS):
            n += 1
            rows.append(_bl_row(
                n, name, "step effect is not re-appliable by resubmitting the same request",
                "replay",
                "replay the exact same request after the step already completed -- does the "
                "server re-apply it (double-discount / double-ship / double-vote)?"))

    gate_idxs = [i for i, low in enumerate(lowered) if any(v in low for v in _SKIP_GATE_VERBS)]
    target_idxs = [i for i, low in enumerate(lowered) if any(v in low for v in _SKIP_TARGET_VERBS)]
    for ti in target_idxs:
        if any(gi < ti for gi in gate_idxs):
            n += 1
            rows.append(_bl_row(
                n, names[ti],
                "the privileged step is reachable only AFTER its gating step completed",
                "skip",
                "call this step's endpoint directly, skipping the earlier gate step -- does the "
                "server re-check gate state, or only the client-side flow order?"))

    return rows
