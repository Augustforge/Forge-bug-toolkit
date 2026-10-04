# -*- coding: utf-8 -*-
"""Differential Observation -- a shared primitive (§35.1, Plan 3 Task 1).

A single mechanism: "a divergence between two observation points on the same probe = a vulnerability
signal", under which three FDE instances are subsumed: web3 signature-diff (the DOM shows one thing, the
signed payload another), clone-diff (several deployments of one frontend diverged in protection),
web2 authz-diff (IDOR/BOLA/BFLA/tenant-isolation -- one account sees another's data/functions).

Core: differential(ctx_a, ctx_b, probe) runs the SAME probe through TWO named
contexts and, if the responses diverged where they should not have, returns a Divergence with a ready
ledger row (to_dnn_row()) that the REAL completeness gate recognizes
(hunt_completeness_gate._D_ROW_RE / active_divergence_unresolved / active_undup_origin_missing --
Task 3, FDE Plan 6 §48.2) -- the contract is verified by diffobs_replay.py, case 10.

NO live I/O in Task 1: Context.driver is a plugin contract (any object with a method
`.probe(probe) -> Response`). The only implementation here is MockDriver, for unit tests.
Live http/browser drivers -- Plan 4/5.

Fail-open everywhere: a driver / comparison / result-construction error -> None (differential) or
[] (differential_matrix), we never crash.
"""

import json
import re


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class Response(object):
    """Normalized response of a context to a probe."""

    def __init__(self, status=None, fields=None, headers=None, body_hash=None):
        self.status = status
        self.fields = fields if fields is not None else {}
        self.headers = headers if headers is not None else {}
        self.body_hash = body_hash

    def __repr__(self):
        return "Response(status=%r, fields=%r, headers=%r, body_hash=%r)" % (
            self.status, self.fields, self.headers, self.body_hash)


class Probe(object):
    """What we check. `kind` sets the dclass of the result and the source of attack_path_hint (see the
    table below), `target` -- what exactly we probe (endpoint/object/URL/tx), `payload` -- optional
    request data. `key()` -- a stable key for MockDriver.responses."""

    # Domain of allowed kind values (informational; the primitive does NOT validate strictly -- an unknown
    # kind simply gets the default attack_path_hint/severity_seed, see differential()).
    KINDS = (
        "signature-integrity", "object-authz", "function-authz",
        "tenant-isolation", "clone-parity", "broken-auth",
        "ai-trust",  # Plan 7 Task 1, §60 AI-surface: benign-vs-injection divergence in a production LLM feature.
    )

    def __init__(self, kind, target, payload=None):
        self.kind = kind
        self.target = target
        self.payload = payload if payload is not None else {}

    def key(self):
        try:
            payload_part = json.dumps(self.payload, sort_keys=True, default=str)
        except Exception:
            payload_part = str(self.payload)
        return "%s:%s:%s" % (self.kind, self.target, payload_part)

    def __repr__(self):
        return "Probe(kind=%r, target=%r, payload=%r)" % (self.kind, self.target, self.payload)


class Context(object):
    """A named observation point (role/deployment/signature-context). `driver` is a plugin contract:
    any object with a method `.probe(probe) -> Response`. Task 1 provides only MockDriver; live
    http-session / browser-session / deploy-host / signature-context drivers -- Plan 4/5."""

    def __init__(self, label, driver, role=None, deploy=None, sig_ctx=None, meta=None):
        self.label = label
        self.driver = driver
        self.role = role
        self.deploy = deploy
        self.sig_ctx = sig_ctx
        self.meta = meta if meta is not None else {}

    def __repr__(self):
        return "Context(label=%r, role=%r, deploy=%r)" % (self.label, self.role, self.deploy)


class MockDriver(object):
    """The only driver in Task 1. `responses` -- dict {probe.key(): response_dict|Response}.
    A missing key for the requested probe -- KeyError; this is NOT a MockDriver bug, but the standard way
    to simulate "the driver could not answer" and check fail-open in differential() (see case 11
    in diffobs_replay.py: differential() catches the exception and returns None instead of failing)."""

    def __init__(self, responses=None):
        self.responses = responses if responses is not None else {}

    def probe(self, probe):
        raw = self.responses[probe.key()]
        if isinstance(raw, Response):
            return raw
        return Response(
            status=raw.get("status"),
            fields=raw.get("fields", {}),
            headers=raw.get("headers", {}),
            body_hash=raw.get("body_hash"),
        )


class StaticDriver(object):
    """A driver that returns ONE fixed Response for ANY probe (probe.key() is ignored).
    Needed for the spec-baseline context -- the response expected per the program's spec/rubric, against
    which the LIVE observation is compared. See spec_baseline_context()."""

    def __init__(self, response):
        self._response = response

    def probe(self, probe):
        return self._response


class ContractDriver(object):
    """A8 (Wave 1 2026-08-08): an adapter of contract observations to the differential primitive (like
    StaticDriver/WSResponseAdapter, but for web3). `observations` = dict, KEY = `probe.target`
    (a state boundary: storage slot name / function signature / event), value = the observation:
      * bare dict `{field: value}`  → Response(fields=...)  (storage snapshot / fork-call result)
      * response-dict `{status/fields/headers/body_hash}` → full Response
      * a ready Response → as is
    Contract probe semantics: fork-call result / storage snapshot / event-log all go into
    `fields`, then differential() compares them field-level (as for web). A missing key → an empty
    Response (not KeyError — a contract observation "boundary untouched" = empty, not "driver crashed")."""

    def __init__(self, observations=None):
        self.observations = observations if observations is not None else {}

    def probe(self, probe):
        raw = self.observations.get(getattr(probe, "target", None), {})
        if isinstance(raw, Response):
            return raw
        if isinstance(raw, dict):
            if any(k in raw for k in ("status", "fields", "headers", "body_hash")):
                return Response(status=raw.get("status"), fields=raw.get("fields", {}),
                                headers=raw.get("headers", {}), body_hash=raw.get("body_hash"))
            return Response(fields=raw)      # bare fields dict (storage/call snapshot)
        return Response(fields={})


def contract_context(label, observations, deploy=None):
    """A Context over ContractDriver (A8). `label` — what we observe (mock/prod/parent/fork/chain-A/HEAD),
    `deploy` — a deployment/chain/version label for cross-chain/upgrade-drift."""
    return Context(label=label, driver=ContractDriver(observations), role="contract", deploy=deploy)


def spec_baseline_context(label, expected_status, expected_fields=None, expected_headers=None):
    """A Context modeling the spec-EXPECTED response (baseline) for ASYMMETRIC dclasses.

    Design (Plan 3 -- closing the final review's design note). dclasses split into two kinds by the SHAPE
    of the comparison:
      * SYMMETRIC (object-authz/BOLA · tenant-isolation · clone-parity · signature-integrity):
        two LIVE peer contexts (user-A vs user-B; deploy-A vs deploy-B; DOM vs signed-payload).
        A divergence = one peer sees/signs what it should not. spec_baseline is NOT needed.
      * ASYMMETRIC (broken-auth · function-authz/BFLA): there is NO live second peer -- we must compare
        against the spec EXPECTATION. broken-auth: spec says 401 without a session, we observe 200. BFLA: spec
        says 403 for a low-priv role, we observe 200. Two LIVE 200-vs-200 would give diverged=False
        (the symmetric semantic_diff cannot tell them apart) -- hence the baseline is STATIC.

    Usage: differential(spec_baseline_context("spec-403", 403), observed_ctx, probe) --
    baseline FIRST (ctx_a = what is legitimately expected per the endpoint's rubric/spec), observed SECOND
    (ctx_b = a live context, Plan 4/5 driver); semantic_diff treats ctx_a as the norm, ctx_b as the
    one under test. severity_seed for these dclasses = high (see _SEVERITY_SEED)."""
    resp = Response(status=expected_status,
                    fields=expected_fields if expected_fields is not None else {},
                    headers=expected_headers if expected_headers is not None else {})
    return Context(label=label, driver=StaticDriver(resp), role="spec-baseline")


# ---------------------------------------------------------------------------
# attack_path_hint per dclass -- verbatim mapping from the brief (Task 1, §35.3)
# ---------------------------------------------------------------------------

# NOTE: the first six hint strings below are compared verbatim by diffobs_replay.py
# (_EXPECTED_HINTS, case9b) -- keep both files in sync when editing them.
_ATTACK_PATH_HINTS = {
    "signature-integrity": "trace L4 signer domain-binding: compare displayed value (DOM) against signed payload",
    "object-authz": "enumerate object IDs under ctx_B token; check ownership on write paths",
    "function-authz": "check role-gate on the privileged function; try under a low-priv role",
    "tenant-isolation": "cross-tenant fetch: ctx_B pulls tenant_A resource by direct ID",
    "clone-parity": "diff security headers/authz between deployments; look for a weakened clone",
    "broken-auth": "repeat the request without a session; check reachability of the protected resource without auth",
    "ai-trust": "inject a catalog payload into the AI input (chat/metadata/RAG); observe §60.1: tool-call / "
                "context-leak / system-prompt-reveal / output->sink / cost-DoS / guardrail-bypass; "
                "benign canary-only, magnitude on a fork",
    # A8 (Wave 1 2026-08-08) contract mode of differential — a StaticDriver-class on web3 via ContractDriver:
    "contract-mock-vs-prod": "differential(mock, prod) on a fork: the mock path diverges from the deployed one "
                             "(e.g. Superform-style mock-vs-prod class) — compare storage/call-result",
    "contract-cross-chain-drift": "a config/band exists on chain A, absent on B = deployed<audited "
                                  "defense-regression → the tighter chain is the reference, the looser one = a live lead",
    "contract-upgrade-drift": "deployed impl behind the proxy != the audited HEAD (Templar class) — compare "
                              "the deployed code_hash against repo HEAD, the delta = un-audited",
    "contract-spec-vs-impl": "NatSpec/docs promise invariant X, the implementation does Y — an assumption without "
                             "enforcement (un-dup: docs-runtime-gap)",
    "contract-family-fork": "the fork deviated from the canonical parent: differential(parent, fork) → "
                            "the delta = where the fork broke the canonical invariant (T10-B family-diff)",
}
_DEFAULT_HINT = "dclass outside the known enum -- investigate probe.target/evidence manually"

# severity_seed -- a rough estimate per dclass. NOT given verbatim in the brief (unlike
# attack_path_hint) -- the implementer's judgment: direct capture of others' data/privileges/substitution of a
# signed value = high; a weakened clone by itself needs one more step for live
# exploitation (not certain the same hole sits on the live path) = med.
_SEVERITY_SEED = {
    "signature-integrity": "high",
    "object-authz": "high",
    "function-authz": "high",
    "tenant-isolation": "high",
    "clone-parity": "med",
    "broken-auth": "high",
    # ai-trust: the main §60.1 vector (injection -> privileged tool-call = BFLA/BOLA via an LLM intermediary,
    # "money") -- direct capture of privileges/data by the hands of a privileged agent = high.
    "ai-trust": "high",
    # A8 contract mode: mock/prod, cross-chain, upgrade, spec/impl, family-fork divergence = a
    # high-impact class (e.g. mock-vs-prod divergence) → high.
    "contract-mock-vs-prod": "high",
    "contract-cross-chain-drift": "high",
    "contract-upgrade-drift": "high",
    "contract-spec-vs-impl": "high",
    "contract-family-fork": "high",
}
_DEFAULT_SEVERITY = "med"


# ---------------------------------------------------------------------------
# _cell -- FIX 2 (final-review, ledger injection via to_dnn_row): `dclass`/`where`(=probe.target)
# are interpolated into the markdown row `| D-01 | ... |` WITHOUT escaping. `probe.target` is a partly
# attacker-controlled value (URL/endpoint/tx parameter of the target we observe) --
# a `|` inside forges ADDITIONAL table cells (including the LAST one -- the very one that
# active_divergence_unresolved reads as the resolution), while `\n`/`\r`/tab break the physical line --
# hunt_completeness_gate parses the model LINE BY LINE (_D_ROW_RE.match on each line separately), so
# the second "half" of a forged row is no longer recognized as the same D-NN row, while its first
# half may accidentally contain text resembling a resolution ("-> H-1"/"KILLED file:line"),
# making active_divergence_unresolved treat an OPEN divergence as RESOLVED (false-negative
# -> premature HUNT-EXIT). Applied to EVERY interpolated value in to_dnn_row.
# ---------------------------------------------------------------------------

_CELL_WS_RE = re.compile(r"\s+")
_CELL_MAX_LEN = 120


def _cell(s):
    """Sanitizer for a single markdown cell: `|` -> `/` (cannot forge a column boundary), any
    run of whitespace characters (incl. `\\r`/`\\n`/tab -- the row MUST remain a single physical
    line) -> a single space, `.strip()`, truncation to _CELL_MAX_LEN characters (+ a "..." truncation
    marker). A non-string is coerced to str(); total coercion/regex failure -> "?" (fail-safe, the same
    contract as the rest of the primitive -- building a ledger row must not fail)."""
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return "?"
    try:
        safe = s.replace("|", "/")
        safe = _CELL_WS_RE.sub(" ", safe).strip()
    except Exception:
        return "?"
    if len(safe) > _CELL_MAX_LEN:
        safe = safe[:_CELL_MAX_LEN].rstrip() + "..."
    return safe


class Divergence(object):
    """The result of a divergence between ctx_a and ctx_b on one probe. The primitive always sets
    `provenance` to "AUTO" (a human edit/manual finding -- "MANUAL", outside Task 1)."""

    def __init__(self, dclass, ctx_pair, evidence, attack_path_hint, severity_seed, provenance="AUTO"):
        self.dclass = dclass
        self.ctx_pair = ctx_pair
        self.evidence = evidence if evidence is not None else {}
        self.attack_path_hint = attack_path_hint
        self.severity_seed = severity_seed
        self.provenance = provenance

    def __repr__(self):
        return "Divergence(dclass=%r, ctx_pair=%r, severity_seed=%r)" % (
            self.dclass, self.ctx_pair, self.severity_seed)

    def to_dnn_row(self):
        """A `## Divergences` row (format sessions/_methodology/
        system_model_web_template.md) that hunt_completeness_gate._D_ROW_RE matches and that
        active_divergence_unresolved keeps OPEN (the last resolution cell is always empty -- no
        `-> H-NN` / `KILLED file:line`). 12 columns (Task 3, FDE Plan 6 §48.2/§44/§50.3 -- was 11):
        ID | Inv(I-NN) | Where | Status | blast-radius | sibling-count | crowd-cold | convergence |
        crowd-heat | Rank | undup_origin | Resolution.

        Design decisions (there is no correct value in the Divergence interface -- see the report):
        - The ID is hardcoded as `D-01`: the primitive observes ONE divergence at a time and does not own
          the numbering of the system's overall ledger -- the agent merging the row into system_model.md
          renumbers to the real D-NN counter in place (the same pattern as the manual merge of
          Scout Fan-Out findings in scout_fanout.md).
        - "Violated I-NN" -- Divergence does not store a reference to a specific I-NN (that linkage
          is made by a human/agent when merging into the model), so the column carries the dclass --
          the closest machine-known classification of the divergence.
        - "Status" -- ABSENT: a divergence by construction means the invariant did NOT hold
          in at least one of the two observed contexts; this is the closest of the five canonical
          enforcement statuses (ENFORCED/ENFORCED-PARTIAL/IMPLICIT/ABSENT/SUBSTITUTED).
        - blast-radius/sibling-count/crowd-cold/convergence/crowd-heat/Rank require judgment in place
          within the REAL model (walk-backward, past reports, dedup check) -- the primitive does not know them and
          honestly marks them `?` rather than inventing a number.
        - undup_origin (Task 3, the SECOND-TO-LAST cell, `c[-2]` -- BEFORE Resolution `c[-1]`, positional-
          hazard R5) -- default `{TODO}`, not `single-boundary-obvious`: the primitive observes a MECHANICAL
          divergence (a differential probe), not an adversarial judgment "why the crowd missed this" --
          inventing an origin = lying; `{TODO}` honestly gives `active_undup_origin_missing` work --
          the agent merging the row must fill it in place.
        WARNING, ISOLATION FOR Task 10: this method is the only place in the file where Task 3 touches
        the emission contract (the row format itself + the 12th cell). Task 10 (ownership-baseline) edits
        differential_observation.py AFTER Task 3 in other place(s) of this file -- not in the body of
        to_dnn_row() -- see task-3-report.md.
        """
        where = None
        if isinstance(self.evidence, dict):
            where = self.evidence.get("target")
        if not where:
            where = "%s vs %s" % self.ctx_pair if self.ctx_pair else "?"
        return "| D-01 | %s | %s | ABSENT | ? | ? | ? | ? | ? | ? | {TODO} |  |" % (
            _cell(self.dclass), _cell(where))


# ---------------------------------------------------------------------------
# semantic_diff / differential / differential_matrix
# ---------------------------------------------------------------------------

def semantic_diff(a, b):
    """Field-level comparison of two Responses (we go beyond the status/md5-only IDORTester -- §32.1).
    `a` -- the base context (what is legitimately visible), `b` -- the one under test (must not see more/different).

    Returns {diverged, status_diff, field_leak, header_diff, hash_diff}.
    field_leak = fields B should not have (extra relative to A) UNIONED with fields
    that differ in value between A and B -- exactly the brief's wording: "fields B has but
    should not / that differ". ("For the test: mock B returns extra fields".)
    """
    a_fields = a.fields if isinstance(a.fields, dict) else {}
    b_fields = b.fields if isinstance(b.fields, dict) else {}

    status_diff = None
    if a.status != b.status:
        status_diff = {"a": a.status, "b": b.status}

    extra = [k for k in b_fields if k not in a_fields]
    differing = [k for k in b_fields if k in a_fields and a_fields[k] != b_fields[k]]
    field_leak = sorted(set(extra) | set(differing))

    a_headers = a.headers if isinstance(a.headers, dict) else {}
    b_headers = b.headers if isinstance(b.headers, dict) else {}
    header_diff = {}
    for k in set(a_headers) | set(b_headers):
        if a_headers.get(k) != b_headers.get(k):
            header_diff[k] = {"a": a_headers.get(k), "b": b_headers.get(k)}

    hash_diff = None
    if a.body_hash != b.body_hash:
        hash_diff = {"a": a.body_hash, "b": b.body_hash}

    diverged = bool(status_diff) or bool(field_leak) or bool(header_diff) or bool(hash_diff)
    return {
        "diverged": diverged,
        "status_diff": status_diff,
        "field_leak": field_leak,
        "header_diff": header_diff,
        "hash_diff": hash_diff,
    }


def differential(ctx_a, ctx_b, probe):
    """A paired unit of observation. Fail-open: ANY error (the driver raised an exception, the response is
    broken, the comparison failed, Divergence construction failed) -> None, we never crash."""
    try:
        ra = ctx_a.driver.probe(probe)
        rb = ctx_b.driver.probe(probe)
        d = semantic_diff(ra, rb)
        if not d.get("diverged"):
            return None
        d = dict(d)
        d["target"] = getattr(probe, "target", None)
        dclass = probe.kind
        return Divergence(
            dclass=dclass,
            ctx_pair=(ctx_a.label, ctx_b.label),
            evidence=d,
            attack_path_hint=_ATTACK_PATH_HINTS.get(dclass, _DEFAULT_HINT),
            severity_seed=_SEVERITY_SEED.get(dclass, _DEFAULT_SEVERITY),
            provenance="AUTO",
        )
    except Exception:
        return None


def differential_matrix(contexts, probe):
    """Pairwise (i<j) over all unique pairs of `contexts` -> a list of non-empty Divergences, each
    carrying its pair's label in ctx_pair. Fail-open: an error (e.g. `contexts` not iterable) ->
    whatever has been collected so far (in the worst case an empty list), we do not crash."""
    out = []
    try:
        ctxs = list(contexts)
        for i in range(len(ctxs)):
            for j in range(i + 1, len(ctxs)):
                div = differential(ctxs[i], ctxs[j], probe)
                if div is not None:
                    out.append(div)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# A8 (Wave 1 2026-08-08): family-fork-diff — a mature differential primitive in web3.
# Killer app (a triple intersection of differential × T10-B family-diff × invariant_library): most
# DeFi = forks; the bug is NOT in the copied audited code, but in the DELTA from the reference. Flow: (1) identify the
# parent/primitive by fingerprint (identify_parent over the invariant_library machine-bank); (2)
# differential(canonical_parent, target_fork) via ContractDriver; (3) delta = where the fork broke the
# canonical invariant = the bug surface. Hits squarely at forks.
# ---------------------------------------------------------------------------

def family_fork_diff(parent_ctx, fork_ctx, target, kind="contract-family-fork"):
    """differential(parent, fork) at the `target` boundary. Code copied unchanged → identical
    observations → None (no delta). A function modified by the fork → Divergence-on-the-delta (dclass
    contract-family-fork, severity high). A thin wrapper over differential() (a single primitive, not a new
    engine) — probe.kind sets the contract dclass. Fail-open is inherited from differential()."""
    return differential(parent_ctx, fork_ctx, Probe(kind, target))


def identify_parent(fingerprints, code_text):
    """T10-B: identify the canonical parent/primitive of a fork by the machine-bank fingerprints
    of invariant_library. `fingerprints` = [(name, regex), ...] (from `pattern_replay.parse_library`);
    `code_text` = the fork's source. Returns [(name, regex), ...] of those whose canonical fingerprint
    is PRESENT in the code → candidate parents for family_fork_diff. A broken regex is skipped (fail-soft)."""
    out = []
    for name, rx in (fingerprints or []):
        try:
            if re.search(rx, code_text or ""):
                out.append((name, rx))
        except re.error:
            continue
    return out


# ---------------------------------------------------------------------------
# ownership_diff -- Task 10 (FDE Plan 6 §48.2, carry BS-05): ownership-baseline BOLA fix.
#
# BS-05 gap (sessions/_methodology/blind_spots.md): semantic_diff()/differential() -- an EQUALITY-
# based comparison -- is structurally blind to full-leak BOLA: the attacker (user-B) gets a BYTE-FOR-BYTE
# IDENTICAL copy of another user's (user-A) object -> status_diff=None, field_leak=[], hash_diff=None ->
# diverged=False -> differential() returns None -- NOT A SINGLE Divergence, although the leak is total.
# This branch is ADDITIVE, it does NOT replace differential()/semantic_diff (that equality logic remains
# correct for partial-leak/403-asymmetry scenarios, where diverged=True -- it catches them as before).
#
# Mechanism: a field-level (§43.5, NOT status+length) comparison of owner markers BETWEEN the response for ANOTHER's
# object (ctx_target) and the response of the SAME user for their OWN object (ctx_self,
# self-baseline). If an owner marker in ctx_target differs from the same marker in ctx_self -- the body
# contains owner data that is NOT self -> BOLA, REGARDLESS of equality to any external
# reference (including a byte-for-byte match with the observation of the legitimate owner, see the case above).
# ---------------------------------------------------------------------------

_OWNER_MARKER_KEYS = (
    "owner_id", "owner", "account_id", "account",
    "user_id", "userId", "email", "tenant_id", "tenant",
)

# A2 (Wave 1 2026-08-08): owner-semantic tokens. The static `_OWNER_MARKER_KEYS` guesses
# STANDARD names; on a target with a non-standard field (`workspace_owner`/`belongs_to`/`acct_uuid`)
# ownership_diff stays silent with `[INCONCLUSIVE]` not because there is no leak, but because the name is not in the dictionary.
# `schema_hint_leak` pulls the target's REAL field names out of verbose errors → `owner_like_markers`
# picks the owner-like ones from them and EXTENDS the dictionary per-target. WARNING: the filter is mandatory (anti-FP): on a
# REAL self-baseline (user-B-own) any differing non-owner field (created_at/title) would give a
# false BOLA. We take ONLY fields with owner semantics → a mismatch = a real owner, not noise.
_OWNER_LIKE_TOKENS = (
    "owner", "account", "acct", "user", "uid", "tenant", "org",
    "workspace", "belongs", "created_by", "creator", "author", "email",
)


def owner_like_markers(discovered_fields, base=_OWNER_MARKER_KEYS):
    """A2: union(base, owner-like ones from discovered). discovered_fields — a list of field names (usually
    `schema_hint_leak(body)['fields']`). Non-owner names are discarded (anti-FP on the self-baseline).
    Duplicates (already in base) are not added. Fail-soft: garbage input → base unchanged."""
    try:
        out = list(base)
        seen = {m.lower() for m in out}
        for f in (discovered_fields or []):
            if not isinstance(f, str):
                continue
            fl = f.strip()
            if not fl or fl.lower() in seen:
                continue
            if any(tok in fl.lower() for tok in _OWNER_LIKE_TOKENS):
                out.append(fl)
                seen.add(fl.lower())
        return tuple(out)
    except Exception:
        return tuple(base)


def ownership_diff(ctx_target, ctx_self, probe, markers=_OWNER_MARKER_KEYS):
    """`ctx_target` -- the context answering `probe` about the object UNDER TEST (potentially another's)
    (e.g. `user-B` requests an object of `user-A`). `ctx_self` -- the SAME user answering
    `probe` about their OWN object (self-baseline; in a live harness -- a separate real
    request to their own resource; in tests/StaticDriver-wrapped contexts -- a pre-captured
    response, see `_as_context`/`spec_baseline_context`).

    Three outcomes (the brief's anti-FP falsifier -- `ownership of one's OWN object is NOT flagged`, `no marker ->
    INCONCLUSIVE, not FP`):
      1. NO `marker` key is found in the `ctx_target` body (or none found is comparable --
         absent from `ctx_self`) -> Divergence dclass="[INCONCLUSIVE-NO-OWNER-MARKER]" (no
         ownership signal != no leak; NOT a FP, NOT a silent skip -- the same principle as
         `authz_diff._inconclusive_divergence` for WAF/rate-limit noise).
      2. The found markers are comparable (present in BOTH responses), and at least one DIFFERS ->
         Divergence dclass="object-authz", severity high -- an owner marker of another's object in
         the body -- BOLA, REGARDLESS of status/full equality to any external reference.
      3. The found markers are comparable and ALL match -> None (legit self-access, B-for-B is NOT
         flagged -- the brief's falsifier).

    Comparability per key requires a value IN BOTH responses -- a key absent from `ctx_self` does not
    participate in the comparison (no self-baseline value -> nothing to compare for THIS key, rather than
    failing the whole check if a comparable key is found in another marker).

    Fail-open: any error (the driver raised / fields are broken) -> None, the same contract as
    differential()."""
    try:
        r_target = ctx_target.driver.probe(probe)
        r_self = ctx_self.driver.probe(probe)
        fields_target = r_target.fields if isinstance(r_target.fields, dict) else {}
        fields_self = r_self.fields if isinstance(r_self.fields, dict) else {}

        present = [k for k in markers if k in fields_target]
        comparable = [k for k in present if k in fields_self]

        if not present or not comparable:
            return Divergence(
                dclass="[INCONCLUSIVE-NO-OWNER-MARKER]",
                ctx_pair=(ctx_target.label, ctx_self.label),
                evidence={
                    "target": getattr(probe, "target", None),
                    "reason": "no comparable owner-marker field in body",
                },
                attack_path_hint=(
                    "the response body contains no known owner markers (%s) comparable with the "
                    "self-baseline -- ownership-baseline is not applicable to this endpoint; "
                    "check manually using domain specifics (e.g. a nested object/a non-standard "
                    "field name)"
                ) % ", ".join(markers),
                severity_seed="info",
                provenance="AUTO",
            )

        mismatched = {
            k: {"self": fields_self[k], "target": fields_target[k]}
            for k in comparable if fields_self[k] != fields_target[k]
        }
        if not mismatched:
            return None

        return Divergence(
            dclass="object-authz",
            ctx_pair=(ctx_target.label, ctx_self.label),
            evidence={
                "target": getattr(probe, "target", None),
                "owner_mismatch": mismatched,
            },
            attack_path_hint=(
                "ownership-baseline: the body of the object under test contains owner marker(s) %s "
                "that differ from the same user's self-baseline -- full-leak BOLA regardless of "
                "equality to any external reference (see BS-05)"
            ) % ", ".join(sorted(mismatched)),
            severity_seed="high",
            provenance="AUTO",
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# mass_assignment_diff -- Plan 9 Task T1: write-side BOPLA / mass-assignment prover.
#
# Mirror of ownership_diff on the WRITE path. ownership_diff proves a READ-side leak (attacker sees
# an owner-marker that is not theirs). mass_assignment_diff proves the WRITE-side dual: attacker
# INJECTS a privileged/value field (role/is_admin/balance/verified -- the BOPLA candidates from
# business_logic.mass_assignment_fields) into a write/create/update request, then the object is READ
# BACK and compared to a baseline "should-be" state. If the injected field PERSISTED (present in the
# read-back and diverging from baseline) the server accepted a client-supplied privileged field =
# mass-assignment / BOPLA -- a NEW finding class our static field-name matcher could only guess at.
#
# This is the ACTIVE prover: a 200 on the write proves nothing (servers silently drop unknown/
# unauthorized fields all the time); ONLY the read-back proves persistence. It reuses semantic_diff
# (the equality primitive) -- it does NOT build a new diff engine.
#
# Two contexts, mirroring ownership_diff's (ctx_target, ctx_self):
#   * ctx_prover   -- the attacker session that issues the WRITE (write_probe carries the injected
#                     field in its payload) AND the READ-BACK of its own object.
#   * ctx_baseline -- the "should-be" control: a read-back of a control object created WITHOUT the
#                     injection (or the object's pristine default state) -- the safe default the
#                     privileged field is supposed to hold.
# ---------------------------------------------------------------------------

def mass_assignment_diff(ctx_prover, ctx_baseline, write_probe, readback_probe, injected_fields):
    """Prove (or refute) that a client-supplied privileged field persisted through a write.

    Flow: WRITE (ctx_prover, write_probe -- carries the injected field) -> READ-BACK (ctx_prover,
    readback_probe) vs READ-BACK (ctx_baseline, readback_probe) via semantic_diff.

    `injected_fields`: iterable[str] -- the privileged field names injected on WRITE that must NOT
    persist (role/is_admin/balance/verified class; feed it business_logic.mass_assignment_fields()).

    Three outcomes (symmetry with ownership_diff's anti-FP contract):
      1. No injected field is observable in the prover read-back body ->
         Divergence dclass="[INCONCLUSIVE-FIELD-NOT-REFLECTED]" (cannot prove persistence, but the
         object may not echo the field on read -- NOT a silent pass, NOT a false positive; the agent
         must confirm the field is read-back-observable, e.g. via a sibling admin view).
      2. An injected field IS present in the prover read-back AND diverges from the baseline
         read-back (present-and-different, or present-in-prover-absent-in-baseline) ->
         Divergence dclass="object-authz", severity high -- BOPLA proven: the server persisted a
         client-supplied privileged field.
      3. Injected fields are present but match the baseline (server ignored/normalized the injection)
         -> None -- the KEY FALSIFIER: a rejected/ignored field is NOT a finding.

    The WRITE response itself is fired-and-observed but deliberately NOT used as proof (a 200 write
    can silently drop the field). Only the read-back divergence counts.

    Fail-open: any error (driver raised / bodies malformed) -> None, same contract as differential()
    / ownership_diff().
    """
    try:
        injected = [f for f in (injected_fields or []) if isinstance(f, str)]
        if not injected:
            return None

        # 1. WRITE with the injected privileged field(s). Response captured for evidence only --
        #    persistence is proven by the READ-BACK, never by the write's status code.
        write_resp = ctx_prover.driver.probe(write_probe)

        # 2. READ-BACK: prover's object and the baseline "should-be" control object.
        r_prover = ctx_prover.driver.probe(readback_probe)
        r_baseline = ctx_baseline.driver.probe(readback_probe)
        f_prover = r_prover.fields if isinstance(r_prover.fields, dict) else {}

        present = [f for f in injected if f in f_prover]
        if not present:
            return Divergence(
                dclass="[INCONCLUSIVE-FIELD-NOT-REFLECTED]",
                ctx_pair=(ctx_prover.label, ctx_baseline.label),
                evidence={
                    "target": getattr(readback_probe, "target", None),
                    "injected_fields": injected,
                    "reason": "injected privileged field(s) not echoed in the read-back body",
                },
                attack_path_hint=(
                    "the read-back body contains none of the injected fields (%s) -- persistence is not "
                    "observable via this read endpoint; check a sibling view (admin/list) "
                    "where the privileged field is returned, before refuting"
                ) % ", ".join(injected),
                severity_seed="info",
                provenance="AUTO",
            )

        # 3. semantic_diff baseline (should-be) vs prover (observed) -- REUSE the equality primitive.
        #    field_leak = fields extra in prover OR differing between baseline and prover. Intersect
        #    with the injected privileged fields so incidental diffs (timestamps/ids) don't fire.
        diff = semantic_diff(r_baseline, r_prover)
        leaked = diff.get("field_leak") or []
        persisted = sorted(set(present) & set(leaked))
        if not persisted:
            return None  # server ignored/normalized the injected field -> NOT a finding (falsifier)

        mass_assignment = {
            k: {"baseline": (r_baseline.fields or {}).get(k) if isinstance(r_baseline.fields, dict)
                else None,
                "prover": f_prover.get(k)}
            for k in persisted
        }
        return Divergence(
            dclass="object-authz",
            ctx_pair=(ctx_prover.label, ctx_baseline.label),
            evidence={
                "target": getattr(readback_probe, "target", None),
                "mass_assignment": mass_assignment,
                "write_status": getattr(write_resp, "status", None),
            },
            attack_path_hint=(
                "write-side BOPLA: client-supplied privileged field(s) %s persisted through the "
                "write and diverge from the baseline should-be state -- server mass-assigned an "
                "attacker-controlled privilege/value knob (mirror of ownership_diff on the write "
                "path)"
            ) % ", ".join(persisted),
            severity_seed="high",
            provenance="AUTO",
        )
    except Exception:
        return None
