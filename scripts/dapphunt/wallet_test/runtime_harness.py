# -*- coding: utf-8 -*-
"""Runtime Harness -- Python adapter for a live browser harness on top of the existing Plan 3
primitives (FDE Plan 4, Task 1). Compares "shown to the user" (DOM) against "signed by the wallet"
(EIP-712 signed payload) via differential_observation.py, and wraps the fail-CLOSED
opsec_preflight.py gate in a fail-open fallback for the calling code (skill /dapphunt, Task 2 --
the live Playwright driver).

No live browser/network I/O here: `dom_view` and `signed_payload` are already captured snapshots
(dict) passed in by the calling code. white-hat / observational: this module only COMPARES data,
never signs or sends transactions (that is done by onchain_poc_harness.py under its own
burner-enforcement -- see Consumes in the brief).

Public contract (keep exact -- consumed by Task 2 + skill `/dapphunt`):
    signature_contexts(dom_view, signed_payload) -> (ctx_dom, ctx_signed)
    extract_signed_fields(typed_data) -> dict
    run_signature_diff(dom_view, signed_payload, target, provenance="AUTO") -> Divergence | None
    opsec_or_fallback(target, config) -> "AUTO" | "MANUAL"

Task 2 (FDE Plan 4) adds three LIVE observation capabilities (§4.2) on top of the same
differential_observation.py primitives, plus closing Task-1 concern #2 (valid-signature wiring) and
write-through for observations to disk:
    capture_headers(host_responses) -> list[Divergence]
    capture_data_source(prod_resp, staging_resp, probe_kind="object-authz", target="") -> Divergence | None
    capture_postmessage(events) -> list[dict]
    capture_exposure(sources, path_kind="runtime", enable_pii=True) -> list[dict]  # P0-2 Exposure Engine (runtime)
    valid_burner_signature(typed_data) -> str | None
    write_runtime_diff(session_dir, name, payload) -> str | None

R1 contract (§13, Task 2 -- DATA/provenance, not code): the live Playwright driver (skill
`/dapphunt`, Task 9-10) MUST inject `eip1193_mock_provider.js` BEFORE navigation (init-script /
`browser_evaluate` STRICTLY before `browser_navigate` -- otherwise the provider is set on an
already-loaded page and the dApp manages to poll `window.ethereum` before injection). If injection
before page-load is not achievable (e.g. the page was already open before the harness started) --
the calling code MUST mark the capture `provenance="MANUAL"` (not "AUTO") and explicitly note the
missed injection in its notes; the `capture_*` functions of this module themselves do NOT do live
Playwright I/O (same discipline as Task 1 -- they only compare/serialize already-passed snapshots)
and therefore do not check the injection timing programmatically -- that is the responsibility of
the calling skill.

Importing `_methodology`/`differential_observation.py` and `opsec_preflight.py`: toolkit
self-contained (`_methodology` is NOT on sys.path) -- we load both via
`importlib.util.spec_from_file_location`, resolving the path from `__file__` (NOT from
`os.getcwd()`), because this module is a reusable LIBRARY (imported by the test, by the skill, by
the future Task 2 browser driver from different cwd), not a standalone script run from the repo
root (that cwd-walk pattern used by *_replay.py does not fit here -- see the report).
"""

import os
import sys
import json
import subprocess
import importlib.util


_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(_HERE))          # .../bug-bounty-toolkit/scripts
_METHOD_DIR = os.path.join(_SCRIPTS_DIR, "_methodology")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_dobs = _load("differential_observation", os.path.join(_METHOD_DIR, "differential_observation.py"))
_opsec = _load("opsec_preflight", os.path.join(_HERE, "opsec_preflight.py"))
_pi_guard = _load("pi_guard_lib", os.path.join(_METHOD_DIR, "pi_guard_lib.py"))
_secrets = _load("secret_patterns", os.path.join(_METHOD_DIR, "secret_patterns.py"))

Context = _dobs.Context
Probe = _dobs.Probe
Response = _dobs.Response
StaticDriver = _dobs.StaticDriver
Divergence = _dobs.Divergence
differential = _dobs.differential
differential_matrix = _dobs.differential_matrix
spec_baseline_context = _dobs.spec_baseline_context

preflight = _opsec.preflight

# CLI entrypoint for valid_burner_signature -- read-only sign-typed-data (no broadcast, see Consumes
# in the brief / policy-header onchain_poc_harness.py). Path resolved from __file__ (same pattern as
# _METHOD_DIR above), not from os.getcwd() -- this module is imported from different cwd.
_ONCHAIN_HARNESS = os.path.join(_HERE, "onchain_poc_harness.py")


# ---------------------------------------------------------------------------
# extract_signed_fields -- normalization of EIP-712 typed data
# ---------------------------------------------------------------------------

# Priority of message keys for each normalized field -- the first one found wins
# (verbatim mapping from the brief).
_AMOUNT_KEYS = ("buyAmount", "value", "amount")
_RECIPIENT_KEYS = ("to", "spender", "recipient")
_DEADLINE_KEYS = ("deadline", "validUntil")
_TOKEN_KEYS = ("token", "sellToken", "asset")

_FIELD_KEYS = (
    ("amount", _AMOUNT_KEYS),
    ("recipient", _RECIPIENT_KEYS),
    ("deadline", _DEADLINE_KEYS),
    ("token", _TOKEN_KEYS),
)


def extract_signed_fields(typed_data):
    """EIP-712 `{domain, message, ...}` -> normalized dict `{amount, recipient, chainId,
    deadline, token, ...}`. `chainId` -- ONLY from `domain.chainId`; the other four -- from
    `message` by key priority (the first match from the corresponding tuple wins).
    Unknown `message` fields are carried over into the result as-is (not lost). Deterministic
    (a pure function of the input, no hidden state). Invalid input (not a dict / broken
    sub-fields) -> `{}` (fail-open, same contract as `differential_observation.py`)."""
    if not isinstance(typed_data, dict):
        return {}
    message = typed_data.get("message")
    message = message if isinstance(message, dict) else {}
    domain = typed_data.get("domain")
    domain = domain if isinstance(domain, dict) else {}

    out = {}
    consumed = set()
    for out_key, candidate_keys in _FIELD_KEYS:
        for k in candidate_keys:
            if k in message:
                out[out_key] = message[k]
                consumed.add(k)
                break

    if "chainId" in domain:
        out["chainId"] = domain["chainId"]

    for k, v in message.items():
        if k not in consumed:
            out[k] = v

    return out


# ---------------------------------------------------------------------------
# signature_contexts / run_signature_diff
# ---------------------------------------------------------------------------

def signature_contexts(dom_view, signed_payload):
    """Builds a pair of `Context` for the signature-integrity diff: `ctx_dom` -- what is shown to
    the user in the DOM (snapshot of fields `{amount, recipient, chainId, deadline, token}`),
    `ctx_signed` -- what is actually signed (EIP-712 typed data, normalized via
    `extract_signed_fields`). Both are a `StaticDriver` over a fixed snapshot (no live I/O here)."""
    ctx_dom = Context("dom-view", StaticDriver(Response(fields=dom_view)), role="dom-view")
    ctx_signed = Context(
        "signed-payload",
        StaticDriver(Response(fields=extract_signed_fields(signed_payload))),
        role="signed-payload",
    )
    return ctx_dom, ctx_signed


def run_signature_diff(dom_view, signed_payload, target, provenance="AUTO"):
    """Runs the `signature-integrity` probe through `differential()`. On a divergence, sets
    `provenance` on the returned `Divergence` (`"AUTO"` by default -- for automatically found
    ones; `"MANUAL"` -- if the calling code is tagging a manual finding); a match -> `None`.
    Fail-open is inherited from `differential()` -- any internal error also gives `None`, it does
    not crash."""
    ctx_dom, ctx_signed = signature_contexts(dom_view, signed_payload)
    probe = Probe("signature-integrity", target)
    div = differential(ctx_dom, ctx_signed, probe)
    if div is not None:
        div.provenance = provenance
    return div


# ---------------------------------------------------------------------------
# opsec_or_fallback
# ---------------------------------------------------------------------------

def opsec_or_fallback(target, config):
    """Fail-open wrapper around the fail-CLOSED OPSEC gate (`opsec_preflight.preflight`).

    `target` -- string identifier of the target (domain/slug, see `sessions/$DOMAIN/`).
    `config` -- a SINGLE flat dict with the common + web3 checks expected by `preflight()`
    (see `opsec_preflight._common_checks`/`_web3_checks`): `vpn_active`, `incognito`,
    `not_logged_main`, `in_scope`, `rate_limit`, `objective`, `wallet_address`, `balance`,
    `balance_cap`.

    Design decision (there is no direct 1:1 between this signature and
    `preflight(profile, target, config)` -- see the report): `preflight()` reads `in_scope` from
    ITS OWN `target` parameter (dict), not from `config`. Here `target` is a bare string, so
    `in_scope` is part of this adapter's flat `config` (a single config for the calling code) and
    gets wrapped into the `target` dict that `preflight()` expects. A missing key / `False` ->
    fail-closed default (do not auto-trust an unverified target).

    Returns `"AUTO"` (gate `ok=True`) or `"MANUAL"` (gate `ok=False` OR any exception --
    `preflight()` is itself already fail-closed and should not raise, but this wrapper still
    never crashes the calling code)."""
    try:
        cfg = config if isinstance(config, dict) else {}
        target_obj = {"slug": target, "in_scope": cfg.get("in_scope", False)}
        result = preflight("web3", target_obj, config)
        return "AUTO" if result.ok else "MANUAL"
    except Exception:
        return "MANUAL"


# ---------------------------------------------------------------------------
# Task 2 -- shared helpers: normalize a live snapshot (Response|dict|Context) into a Context
# ---------------------------------------------------------------------------

def _to_response(x):
    """`Response` as-is; `dict` (`{status, fields, headers, body_hash}`, all optional) ->
    `Response`; anything else (None / broken input) -> empty `Response()` (fail-open)."""
    if isinstance(x, Response):
        return x
    if isinstance(x, dict):
        return Response(
            status=x.get("status"),
            fields=x.get("fields") or {},
            headers=x.get("headers") or {},
            body_hash=x.get("body_hash"),
        )
    return Response()


def _as_context(x, label):
    """`Context` as-is (needed for `spec_baseline_context(...)` passed directly as the first/second
    argument -- see `capture_data_source`); otherwise wraps `Response|dict` in a `StaticDriver`."""
    if isinstance(x, Context):
        return x
    return Context(label, StaticDriver(_to_response(x)), role=label)


# ---------------------------------------------------------------------------
# capture_headers -- live capture #1 (§4.2): security headers of a route/clone, prod vs staging (N-way)
# ---------------------------------------------------------------------------

def capture_headers(host_responses):
    """`host_responses` = `{host: Response|dict}` -- real security headers of the same route,
    captured from different hosts (prod/staging/clone-deploy). Runs `differential_matrix` (all
    pairwise i<j combinations, not just the first pair -- N hosts give N*(N-1)/2 comparisons) through
    a single `Probe("clone-parity", target)`, `target` = sorted host names joined with `|` (there is
    no separate `route` argument in `host_responses` -- this is the closest traceable substitute:
    `Divergence.to_dnn_row()` shows WHICH hosts diverged). Returns a list of `Divergence` (empty if
    there is no pair -- fewer than 2 hosts -- or there are no divergences). Fail-open:
    `host_responses` not a dict / anything broken -> `[]`."""
    try:
        if not isinstance(host_responses, dict) or len(host_responses) < 2:
            return []
        hosts = sorted(host_responses)
        contexts = [_as_context(host_responses[h], h) for h in hosts]
        probe = Probe("clone-parity", "|".join(hosts))
        return differential_matrix(contexts, probe)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# capture_data_source -- live capture #2 (§4.2): prod vs staging authz-diff + guard call-site (P6)
# ---------------------------------------------------------------------------

# Keys treated as on-chain/indexer metadata strings (P6 in the brief, verbatim list).
_METADATA_KEYS = ("symbol", "name", "tokenURI")


def _guard_scan_value(value):
    """Runs `value` through `pi_guard_lib.scan()`; `blocked` -> replaced with
    `"[GUARD-BLOCKED]"` (we do not render a potential prompt-injection payload from on-chain
    metadata as-is).

    Guard -- the ONE exception to the brief's global fail-open constraint (guard ON, fail-
    CLOSED): if the `pi_guard_lib.scan()` call itself fails (scanner unavailable/broken), we do NOT
    pass the value through as-is (that would be a fail-open hole exactly where a fail-closed is
    needed) -- an unscanned input is treated as unsafe by default and `"[GUARD-BLOCKED]"` is
    returned. Does not crash `capture_data_source` (the exception does not escape this function),
    but also does not let an unverified value reach the evidence."""
    try:
        verdict = _pi_guard.scan(value)
        if getattr(verdict, "blocked", False):
            return "[GUARD-BLOCKED]"
        return value
    except Exception:
        return "[GUARD-BLOCKED]"


def capture_data_source(prod_resp, staging_resp, probe_kind="object-authz", target=""):
    """The same API request/object, captured from two observation points -- `prod_resp` (ctx_a, the
    "legitimate" baseline) vs `staging_resp` (ctx_b, the "tested" one). Both accept
    `Response|dict|Context` -- for ASYMMETRIC dclass (`broken-auth`/`function-authz`) `prod_resp` =
    a live `spec_baseline_context("spec-403", 403)` directly (see Consumes/differential_observation.py),
    for SYMMETRIC ones (`object-authz`/`tenant-isolation`/`clone-parity`) both are plain
    `Response|dict` snapshots. `probe_kind` defaults to `"object-authz"` (sets the dclass via
    `Probe.kind`), `target` -- the endpoint/object that was probed.

    Guard call-site (P6, brief verbatim): BEFORE a divergence goes into the evidence, scans the
    on-chain/indexer metadata fields (`symbol`/`name`/`tokenURI`) of both sides via
    `pi_guard_lib.scan()` and puts a SANITIZED copy into `evidence["metadata"][key] = {"a":
    ..., "b": ...}` (the raw value NEVER reaches the evidence without passing the guard --
    `blocked` -> `"[GUARD-BLOCKED]"`). Guard ON per the brief's global constraint; the guard call
    itself is fail-CLOSED (see `_guard_scan_value` -- scanner failure -> `"[GUARD-BLOCKED]"`, NOT
    passing the value through as-is), but it does not crash the whole `capture_data_source`
    (the exception is caught at this level too).

    Returns a `Divergence` (not None -- i.e. there really is a divergence) or `None` (match / any
    internal error, fail-open)."""
    try:
        ctx_a = _as_context(prod_resp, "prod")
        ctx_b = _as_context(staging_resp, "staging")
        probe = Probe(probe_kind, target)
        div = differential(ctx_a, ctx_b, probe)
        if div is None:
            return None
        try:
            fields_a = ctx_a.driver.probe(probe).fields
            fields_b = ctx_b.driver.probe(probe).fields
            fields_a = fields_a if isinstance(fields_a, dict) else {}
            fields_b = fields_b if isinstance(fields_b, dict) else {}
            metadata = {}
            for k in _METADATA_KEYS:
                has_a, has_b = k in fields_a, k in fields_b
                if has_a or has_b:
                    metadata[k] = {
                        "a": _guard_scan_value(fields_a[k]) if has_a else None,
                        "b": _guard_scan_value(fields_b[k]) if has_b else None,
                    }
            if metadata:
                div.evidence["metadata"] = metadata
        except Exception:
            pass
        return div
    except Exception:
        return None


# ---------------------------------------------------------------------------
# capture_postmessage -- live capture #3 (§4.2): window.postMessage origin-trust
# ---------------------------------------------------------------------------

def capture_postmessage(events):
    """`events` = `[{origin, data, expected_origin, strict}]` -- each item is one captured
    `message`-listener call/config of the live page: `origin` -- the REAL origin the message came
    from; `expected_origin` -- what the dApp checks it against; `strict` (bool, default `True` when
    the key is absent -- fail-open towards "assume a strict check", fewer false findings) --
    whether the check was `===` (strict) or weakened/missing (`.includes()`, wildcard, no-op).

    An origin-trust observation is raised if `origin != expected_origin` (the real sender is NOT the
    one the dApp should have checked against) OR `strict` is False (the check itself is weak -- a
    finding regardless of whether the origin happened to match in THIS sample: a weak checker would
    also let a spoofed origin through). A matching origin WITH a strict check -> NOT raised (safe).

    Returns a list of dict `{origin, expected_origin, class:"origin-trust", note}`. Fail-open:
    `events` not a list / item not a dict / any error -> skip the item, never crashes."""
    out = []
    if not isinstance(events, list):
        return out
    for ev in events:
        try:
            if not isinstance(ev, dict):
                continue
            origin = ev.get("origin")
            expected = ev.get("expected_origin")
            strict = ev.get("strict", True)
            mismatched = origin != expected
            weak_check = not strict
            if not (mismatched or weak_check):
                continue
            notes = []
            if mismatched:
                notes.append("observed origin != expected_origin")
            if weak_check:
                notes.append("non-strict origin check")
            out.append({
                "origin": origin,
                "expected_origin": expected,
                "class": "origin-trust",
                "note": "; ".join(notes),
            })
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# capture_exposure -- runtime half of the Exposure Engine (P0-2, SlowMist Aug-2026)
# ---------------------------------------------------------------------------

def capture_exposure(sources, path_kind="runtime", enable_pii=True):
    """Runtime exposure sweep: scans ALREADY CAPTURED live artifacts (rendered DOM, JS chunks,
    response bodies, localStorage/sessionStorage/IndexedDB storage values, window globals, SW cache)
    for secrets / crypto keys / PII / financial data via `secret_patterns.scan_blob(
    path_kind="runtime")` + a decode layer (a key on the page may be base64/hex).

    `sources`: `dict {label: text}` | `list[(label, text)]` | `list[str]`. Each blob is the raw text
    of one artifact (innerHTML, chunk contents, `localStorage[key]`, JSON response body). `_body`
    convention (CLAUDE.md §7): the response body is passed by the caller as text directly; a
    non-string (dict/list snapshot of a window global / JSON storage) is serialized to JSON before
    scanning.

    OPSEC (same discipline as `capture_headers`/`capture_data_source`): this module does NOT do live
    I/O -- it only scans passed-in snapshots. The calling skill (`/hunt` web2, `/dapphunt`) does the
    live capture ONLY after `opsec_or_fallback(...) == "AUTO"` (fail-closed preflight). white-hat:
    values are REDACTED (`secret_patterns.redact`), no-exfil -- the raw secret never leaves.

    Returns `list[finding]` (shape `secret_patterns.scan_blob`) + a `source`=label field. PII
    clustering is done by the caller (`secret_exposure_scanner.cluster_pii`). Fail-open: broken
    input -> `[]`."""
    # Delegates to the shared core (secret_patterns.capture_exposure) — ONE implementation, shared with the
    # web2 runtime harness (web2_exposure.capture_exposure). `_match` stripped there (no-exfil); fail-open kept.
    return _secrets.capture_exposure(sources, path_kind=path_kind, enable_pii=enable_pii)


# ---------------------------------------------------------------------------
# valid_burner_signature -- closes Task-1 concern #2 (onchain CLI -> mock RESPONSE_TABLE wiring)
# ---------------------------------------------------------------------------

def valid_burner_signature(typed_data):
    """Shells out to `onchain_poc_harness.py sign-typed-data --json <typed_data as ONE JSON string>`
    -- a read-only EIP-712 signature WITHOUT broadcast (see Consumes: `cmd_sign_typed_data`, never
    sends a transaction), under the harness's own burner-enforcement (`_enforce_burner` -- refuses on
    a non-burner key). Returns the parsed signature (last non-empty stdout line, `0x...`) to populate
    the mock `RESPONSE_TABLE.signatures` in the Playwright flow (see `eip1193_mock_provider.js`
    `_lookupSignature`). Error / no burner key / harness unavailable -> `None` (fail-open) -- the
    calling code falls back to the mock's old fake signature (`"0x" + "ab"*65`).

    subprocess: argument list (`sys.executable` -- follows the same convention as
    `pi_guard_replay.py`/`entry_gate_e2e_smoke.py` elsewhere in this repo, NOT a hardcoded `"py"`),
    NEVER builds a shell string from `typed_data` -- the whole payload goes as ONE list element via
    `json.dumps(...)` (`shlex.quote` is not needed for the list form, brief verbatim). The
    subprocess shell flag is NOT used (list-args launch form). No `--session` is passed (this
    function's contract -- 1 argument,
    `typed_data`) -- on a REAL successful signing the harness itself will create
    `bug-bounty-toolkit/sessions/_scratch/onchain/` (its own fallback when
    `--session` is absent, see `onchain_poc_harness._session_dir`) -- the calling skill, if it wants
    to write into a specific target's session folder, must call the CLI directly with `--session`;
    this function does not provide that option (see the report, concern)."""
    try:
        payload = json.dumps(typed_data if isinstance(typed_data, dict) else {})
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", _ONCHAIN_HARNESS, "sign-typed-data", "--json", payload],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return None
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        if not lines:
            return None
        sig = lines[-1]
        if sig.startswith("0x") and len(sig) > 2:
            return sig
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# write_runtime_diff -- serialization of an observation to disk (sessions/$DOMAIN/runtime_diff/<name>.json)
# ---------------------------------------------------------------------------

def _serialize_runtime_item(item):
    """One payload item -> JSON-compatible form. `Divergence` (has `to_dnn_row`) ->
    dict with all fields + the ready ledger row; everything else (dict/list/str/...) stays as-is
    (already JSON-compatible by how `capture_*` builds it)."""
    if hasattr(item, "to_dnn_row"):
        try:
            row = item.to_dnn_row()
        except Exception:
            row = None
        return {
            "dclass": getattr(item, "dclass", None),
            "ctx_pair": list(getattr(item, "ctx_pair", None) or []),
            "evidence": getattr(item, "evidence", None),
            "attack_path_hint": getattr(item, "attack_path_hint", None),
            "severity_seed": getattr(item, "severity_seed", None),
            "provenance": getattr(item, "provenance", None),
            "to_dnn_row": row,
        }
    return item


def write_runtime_diff(session_dir, name, payload):
    """Serializes `payload` (`Divergence` / `list[Divergence]` / an arbitrary JSON-compatible
    dict/list -- any `capture_*` output of this module) into
    `<session_dir>/runtime_diff/<name>.json` (creates the folder if missing). `Divergence` items
    carry the `to_dnn_row()` string inside the serialized JSON (see `_serialize_runtime_item`) --
    the ready ledger row sits next to the raw evidence, so the calling code does not need to call
    `to_dnn_row()` again when merging into `system_model.md`.

    Returns the ABSOLUTE/as-passed path to the written file or `None` (fail-open: broken
    `session_dir` / write error / anything -- does not crash the calling capture flow)."""
    try:
        out_dir = os.path.join(str(session_dir), "runtime_diff")
        os.makedirs(out_dir, exist_ok=True)
        safe_name = os.path.basename(str(name)) or "runtime_diff"
        path = os.path.join(out_dir, "%s.json" % safe_name)
        if isinstance(payload, list):
            data = [_serialize_runtime_item(p) for p in payload]
        else:
            data = _serialize_runtime_item(payload)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None
