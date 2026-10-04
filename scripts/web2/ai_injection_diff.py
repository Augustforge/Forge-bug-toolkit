# -*- coding: utf-8 -*-
"""ai_injection_diff — AI-surface injection-differential harness (web2 engine, TIER A).

An ADAPTER on top of the existing stack, not a new engine. It reuses:
  * `scripts/dapphunt/core/ai_prompt_injection_probe.py` — SCAN (detect the LLM feature +
    attacker-controlled sources). NOTE: in the public release the probe's sendable payload
    catalog is WITHHELD (see that module's docstring), so `build_payloads()` returns nothing
    here; the differential/oracle half below is fully functional.
  * `differential_observation.py` (via `runtime_harness` re-exports) — the
    `differential(ctx_a, ctx_b, probe)` primitive; a new `ai-trust` dclass.
  * `pi_guard_lib.INJECTION_PATTERNS` (via `runtime_harness._pi_guard`) — the GUARDRAIL-ORACLE.
  * `opsec_preflight.preflight` (via `runtime_harness`) — the fail-CLOSED OPSEC gate for the
    live path.

ROLE SEPARATION (critical — different functions, different sources):
  * PAYLOAD-SOURCE = `ai_prompt_injection_probe.build_payloads()` — what would be SENT to the
    target's AI input in an authorized engagement. Withheld in the public release (stub).
    Functions: `build_ai_payloads()`, `payload_catalog()`.
  * GUARDRAIL-ORACLE = `pi_guard_lib.INJECTION_PATTERNS` (via `.scan()`) — DETECTION regexes we
    NEVER send. Vector v8 asks: "did the target's filter catch what OUR pi_guard would catch?"
    Functions: `injection_patterns()`, `guard_would_catch()`, `guardrail_bypass()`.
  Mixing the two is a bug: a payload string must not be matched as a detection regex, or vice
  versa.

Observation + diff, NOT exploitation: the OFFLINE path (default) compares ALREADY-captured
responses (benign vs injection), with no live I/O. The LIVE path (`live_preflight`) MUST pass
a fail-CLOSED OPSEC gate BEFORE any run against a real agent; the live browser capture itself
is done by `runtime_harness.py` (we do not build a new Playwright driver). THINK≠ACT: the
harness builds a MODEL and hypotheses; a live exploit against a real agent is a separate,
per-vector human authorization, benign-canary only, with magnitude measured on a fork only.
Fail-open everywhere EXCEPT the OPSEC gate (fail-closed) and the guard call.

Reuse discipline (isinstance compatibility, same pattern as `authz_diff.py`): load ONLY
`runtime_harness.py` for the differential_observation primitives (it already loads and
re-exports them on its own module object) + `pi_guard` (via `_rh._pi_guard`) + `preflight`. A
separate `importlib` load of differential_observation.py would create DIFFERENT Python classes
for `Context`/`Response`/... → false fail-open branches in isinstance checks. We load only the
probe itself separately (its own tables/catalog).

Public contract (hold exactly — consumed by the selftest + the `/hunt`/`/dapphunt` skills):
    scan_ai_surface(target) -> ProbeReport                         # LIVE recon (network)
    scan_ai_surface_offline(bundles) -> ProbeReport                # OFFLINE recon (reuse probe tables)
    build_ai_payloads(canary, collector) -> list[dict]            # PAYLOAD-SOURCE (withheld -> [])
    payload_catalog() -> list[tuple]                              # PAYLOAD-SOURCE (withheld -> [])
    injection_patterns() -> list[regex]                          # GUARDRAIL-ORACLE
    guard_would_catch(text) -> bool                              # GUARDRAIL-ORACLE
    guardrail_bypass(payload_text, target_obeyed) -> bool        # GUARDRAIL-ORACLE (vector v8)
    ai_injection_diff(target, ctx_benign, ctx_injection) -> Divergence | None
    observed_vectors(div) -> list[(field, desc)]
    run_ai_trust_matrix(target, observations, session_dir, mode="offline") -> str   # producer
    live_preflight(target, config, profile="web2") -> "AUTO" | "MANUAL"             # OPSEC fail-closed
"""

import os
import re
import sys
import importlib.util


# ---------------------------------------------------------------------------
# Loading the Consumes modules (path resolved from __file__, not os.getcwd() — same pattern as
# authz_diff.py/runtime_harness.py: the module is imported by the test/skill from different
# cwds, and the cwd on Windows may contain non-ASCII chars or a long path).
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)                                       # .../scripts
_WALLET_TEST_DIR = os.path.join(_SCRIPTS_DIR, "dapphunt", "wallet_test")
_AIPROBE_PATH = os.path.join(_SCRIPTS_DIR, "dapphunt", "core", "ai_prompt_injection_probe.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec_module: `ai_prompt_injection_probe.py` declares
    # module-level `@dataclass`es, and `dataclasses` resolves `sys.modules.get(cls.__module__)`
    # during decoration — without the sys.modules entry this is None -> AttributeError.
    # (differential_observation/runtime_harness have no dataclasses, so their loaders did not
    # need this.)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


# runtime_harness re-exports the differential_observation.py primitives + pi_guard + preflight
# (see the docstring: reuse discipline — we do not load differential_observation.py separately,
# or isinstance between modules drifts, as documented in authz_diff.py).
_rh = _load("ai_injection_diff_runtime_harness", os.path.join(_WALLET_TEST_DIR, "runtime_harness.py"))
# The AI-attack probe stack (SCAN) — a separate module object (its own tables, not the
# differential_observation primitives, so there is no isinstance drift here).
_aiprobe = _load("ai_prompt_injection_probe", _AIPROBE_PATH)

# differential_observation.py re-exports — VIA runtime_harness (isinstance discipline).
Context = _rh.Context
Probe = _rh.Probe
Response = _rh.Response
StaticDriver = _rh.StaticDriver
Divergence = _rh.Divergence
differential = _rh.differential
differential_matrix = _rh.differential_matrix
spec_baseline_context = _rh.spec_baseline_context
_as_context = _rh._as_context

# pi_guard_lib module (INJECTION_PATTERNS + scan) — the GUARDRAIL-ORACLE source.
_pi_guard = _rh._pi_guard
# opsec_preflight.preflight — the fail-CLOSED OPSEC gate for the live path.
preflight = _rh.preflight

# gate-compatible pattern for to_dnn_row() rows (hunt_completeness_gate._D_ROW_RE, verbatim) — a
# LOCAL copy (same trick as authz_diff.py: do not pull the heavy gate module for one regex).
_D_ROW_RE = re.compile(r"^\s*\|\s*D-\d+\s*\|")
_RENUMBER_D01_RE = re.compile(r"^\|\s*D-01\s*\|")


# ---------------------------------------------------------------------------
# The eight observable vectors — which production AI-feature behavior diverges under injection.
# These are the NAMES OF FIELDS the calling code puts into each context's Response.fields
# (benign vs injection); a field-level divergence = the injection changed the agent's behavior.
# Not to be confused with INJECTION_PATTERNS (detection regex) or the payload catalog.
# ---------------------------------------------------------------------------

_AI_VECTORS = (
    ("tool_called",            "v1 injection -> privileged tool-call (BFLA/BOLA via the LLM intermediary)"),
    ("indirect_injection",     "v2 indirect/second-order injection (payload in data, read later; cross-user)"),
    ("rag_tenant_leak",        "v3 RAG data-exfil / tenant-bleed (documents from another workspace)"),
    ("system_prompt_revealed", "v4 system-prompt / instruction extraction"),
    ("tool_param_ssrf",        "v5 tool-parameter injection / SSRF-via-agent (confused deputy)"),
    ("output_sink",            "v6 LLM output -> sink (unescaped DOM / eval / tool-call)"),
    ("cost_dos",               "v7 cost/DoS via prompt (unbounded generation / recursive tool-calls)"),
    ("guardrail_bypassed",     "v8 guardrail-bypass (the target's moderation is weaker than our input-guard)"),
)


# ---------------------------------------------------------------------------
# SCAN reuse (recon: detect the LLM feature + attacker-controlled sources). Delegate to probe.
# ---------------------------------------------------------------------------

def scan_ai_surface(target):
    """LIVE recon delegator: `ai_prompt_injection_probe.scan(target)` verbatim (network I/O —
    fetch HTML+bundles, detect the AI feature/provider/untrusted sources/agentic sinks). We do
    not reinvent detection — full reuse of the probe. Returns a `ProbeReport`.

    If a calling skill makes this the entry point of an active session against a live target,
    run `live_preflight` first (fail-closed OPSEC), as before any other live request."""
    return _aiprobe.scan(target)


def scan_ai_surface_offline(bundles):
    """OFFLINE recon adapter: runs the probe's OWN detection tables
    (`_AI_FEATURE_SIGNALS`/`_UNTRUSTED_SOURCES`/`_AGENTIC_SINKS` + `_find_lines`) over
    ALREADY-captured content `bundles = {name: text}` — with NO network (live recon =
    `scan_ai_surface`). Reuses the probe tables and its `_find_lines`/`ProbeReport` — no
    detection logic is rewritten here. A non-dict input -> an empty `ProbeReport` (fail-open)."""
    rep = _aiprobe.ProbeReport(target="<captured-offline>")
    if not isinstance(bundles, dict):
        return rep
    rep.bundles_scanned = list(bundles.keys())
    for url, content in bundles.items():
        if not isinstance(content, str):
            continue
        for pat, provider, desc in _aiprobe._AI_FEATURE_SIGNALS:
            for ln, txt in _aiprobe._find_lines(content, pat):
                rep.ai_feature_hits.append({"bundle": url, "line": ln, "signal": desc,
                                            "provider": provider, "excerpt": txt})
                if provider in ("anthropic", "openai") and not rep.provider_guess:
                    rep.provider_guess = provider
        for pat, desc in _aiprobe._UNTRUSTED_SOURCES:
            for ln, txt in _aiprobe._find_lines(content, pat):
                rep.untrusted_source_hits.append({"bundle": url, "line": ln, "source": desc, "excerpt": txt})
        for pat, desc in _aiprobe._AGENTIC_SINKS:
            for ln, txt in _aiprobe._find_lines(content, pat):
                rep.agentic_sink_hits.append({"bundle": url, "line": ln, "sink": desc, "excerpt": txt})
    rep.has_ai_feature = bool(rep.ai_feature_hits)
    rep.agentic_risk = bool(rep.ai_feature_hits and rep.agentic_sink_hits)
    return rep


# ---------------------------------------------------------------------------
# PAYLOAD-SOURCE: what would be SENT. Delegates to the probe catalog (WITHHELD in public -> []).
# ---------------------------------------------------------------------------

def build_ai_payloads(canary="CANARY-OK", collector=None):
    """PAYLOAD-SOURCE: delegates to `ai_prompt_injection_probe.build_payloads()`. In the public
    release the probe's sendable payload catalog is withheld, so this returns an empty list; the
    differential/oracle half of the harness is unaffected. Supply your own scoped, benign-canary
    payloads in an authorized engagement."""
    return _aiprobe.build_payloads(canary, collector)


def payload_catalog():
    """PAYLOAD-SOURCE: the raw `_PAYLOAD_CATALOG` (withheld in the public release -> empty). Its
    role differs from `injection_patterns()` (DETECTION regex): the catalog is what we send to a
    target's input."""
    return _aiprobe._PAYLOAD_CATALOG


# ---------------------------------------------------------------------------
# GUARDRAIL-ORACLE: what we VERIFY the target's filter with. INJECTION_PATTERNS = detection, not
# payload.
# ---------------------------------------------------------------------------

def injection_patterns():
    """GUARDRAIL-ORACLE: `pi_guard_lib.INJECTION_PATTERNS` — the compiled DETECTION regexes we
    NEVER send to a target. Role differs from `payload_catalog()` (sendable payloads)."""
    return _pi_guard.INJECTION_PATTERNS


def guard_would_catch(text):
    """True if OUR input-guard (`INJECTION_PATTERNS` via `pi_guard_lib.scan`) flags `text` as
    `blocked` OR `suspect`. GUARDRAIL-ORACLE role: this is DETECTION, not a payload. Vector v8
    asks with it: "would our guard have caught what the target's filter let through?" Fail-open
    -> False (never raises)."""
    try:
        v = _pi_guard.scan(text)
        return bool(getattr(v, "blocked", False) or getattr(v, "suspect", False))
    except Exception:
        return False


def guardrail_bypass(payload_text, target_obeyed):
    """Vector v8 (guardrail-bypass) verdict: OUR guard WOULD HAVE caught `payload_text`
    (`guard_would_catch`) AND the target OBEYED it (`target_obeyed` — benign canary echoed /
    injected instruction executed). True => the target's moderation is WEAKER than our
    input-guard (the bypass class is proven)."""
    return bool(guard_would_catch(payload_text) and target_obeyed)


# ---------------------------------------------------------------------------
# ANTI-CONFABULATION GATE (hunt-llm-ai false-positive gate).
# An LLM target is NON-DETERMINISTIC: the model may INVENT a "system-prompt leak" / "someone
# else's data" that does not exist — and the differential above does NOT catch this (a
# benign-vs-injection divergence exists, but what "leaked" may be a hallucination). This gate is
# a T4 filter BEFORE submitting an AI finding: it cuts confabulations the harness (differential +
# guardrail-oracle) did not. A separate axis in submission_checklist quality_required. Five
# hunt-llm-ai rules:
#   (1) run-twice verbatim — a real leak reproduces token-for-token across 2 runs; if it varies = confab.
#   (2) anchor-to-known-secret — proof anchors on an UNGUESSABLE secret/canary (not something the LLM could invent).
#   (3) exfil = OOB-callback-or-didn't-happen — exfil is proven ONLY by an out-of-band callback, not a model assertion.
#   (4) cross-tenant = verifiable-artifact — someone else's data = a verifiable artifact, not "the model said so".
#   (5) refusal != secure — the target REFUSED != protected (it may have refused for another reason); likewise confab != finding.
# ---------------------------------------------------------------------------
def confabulation_gate(evidence):
    """T4 anti-confabulation filter for an AI finding. `evidence` (dict), fields (all optional):
        claim_type:   "leak" | "exfil" | "cross_tenant" | "bypass" | ...  (what is claimed)
        run1, run2:   str — the target's output on TWO identical runs (for the verbatim leak check)
        anchor:       str|None — an UNGUESSABLE anchor (a planted canary / known non-guessable secret)
        anchor_in_output: bool — the anchor actually appeared in the target output
        exfil_channel:    "oob_callback" | "assertion" | None — how exfil was "proven"
        target_refused:   bool — the target refused to comply (for refusal != secure)
    Returns {"verdict": "confirmed"|"confabulation_suspected"|"insufficient", "reasons": [...]}.
    Fail-closed TOWARD skepticism: incomplete proof -> NOT confirmed."""
    ev = evidence if isinstance(evidence, dict) else {}
    claim = str(ev.get("claim_type") or "").lower()
    reasons = []

    # refusal != secure: a target refusal is not, by itself, a finding or proof of protection.
    if ev.get("target_refused") and not (ev.get("anchor_in_output") or ev.get("exfil_channel") == "oob_callback"):
        return {"verdict": "insufficient", "reasons": ["refusal != secure: the target refused, but that proves neither a bug nor protection"]}

    # (1) run-twice verbatim for leak/cross_tenant (non-determinism = confabulation)
    if claim in ("leak", "cross_tenant"):
        r1, r2 = ev.get("run1"), ev.get("run2")
        if r1 is None or r2 is None:
            reasons.append("no two runs (run1/run2) for the verbatim check — a non-deterministic target requires run-twice")
        elif r1 != r2:
            return {"verdict": "confabulation_suspected",
                    "reasons": ["run1 != run2 (not token-for-token): output varies -> likely hallucination, not a stable leak"]}

    # (2) anchor-to-known-secret: leak/cross_tenant without an anchor = could have been invented by the model
    if claim in ("leak", "cross_tenant"):
        if not ev.get("anchor"):
            reasons.append("no anchor (unguessable canary/secret): what 'leaked' could have been invented by the LLM")
        elif not ev.get("anchor_in_output"):
            reasons.append("anchor did not appear in the output: the leak is not confirmed by an anchor")

    # (3) exfil = OOB-callback-or-didn't-happen
    if claim == "exfil":
        if ev.get("exfil_channel") != "oob_callback":
            return {"verdict": "insufficient",
                    "reasons": ["exfil claimed without an OOB callback (a model assertion != exfil): either OOB proof, or it didn't happen"]}

    # (4) cross_tenant = verifiable-artifact (not "the model said so")
    if claim == "cross_tenant" and not (ev.get("anchor_in_output") or ev.get("exfil_channel") == "oob_callback"):
        reasons.append("cross-tenant without a verifiable artifact (anchor/OOB): an assertion is not enough")

    if reasons:
        return {"verdict": "insufficient", "reasons": reasons}
    return {"verdict": "confirmed", "reasons": ["anti-confabulation passed"]}


# ---------------------------------------------------------------------------
# DIFFERENTIAL: ai-trust probe, benign vs injection (the 8 vectors).
# ---------------------------------------------------------------------------

def ai_injection_diff(target, ctx_benign, ctx_injection):
    """ONE `ai-trust` probe via `differential()`: a benign input (no injection, ctx_a-baseline)
    vs an injection input (a catalog payload delivered, ctx_b-under-test). A field-level
    divergence => the injection changed the agent's behavior (a tool fired / context leaked / the
    system prompt was revealed / ...). Both arguments accept `Response|dict|Context` (wrapped by
    `_as_context`). Returns an `ai-trust` Divergence (its `.to_dnn_row()` is generic — the
    differential_observation emitter is untouched) or `None` (fail-open, inherited from
    `differential()`)."""
    probe = Probe("ai-trust", target)
    a = _as_context(ctx_benign, "benign")
    b = _as_context(ctx_injection, "injection")
    return differential(a, b, probe)


def observed_vectors(div):
    """Maps a divergence's MECHANICAL `evidence.field_leak` onto the NAMED vectors that fired.
    Returns `list[(field, description)]` in the canonical `_AI_VECTORS` order. `None`/no
    evidence -> `[]`."""
    if div is None or not isinstance(getattr(div, "evidence", None), dict):
        return []
    leaked = set(div.evidence.get("field_leak") or [])
    return [(f, d) for (f, d) in _AI_VECTORS if f in leaked]


# ---------------------------------------------------------------------------
# PRODUCER: ai_trust_matrix.md (co-located, toolkit-rooted session_dir — like authz_matrix.md).
# ---------------------------------------------------------------------------

def _safe_cell(s):
    """A minimal markdown-cell sanitizer (local, as in authz_diff.py): `|` -> `/` (do not forge
    a column), runs of whitespace -> one space, `.strip()`; empty -> `-`."""
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return "?"
    s = s.replace("|", "/")
    s = re.sub(r"\s+", " ", s).strip()
    return s or "-"


def run_ai_trust_matrix(target, observations, session_dir, mode="offline"):
    """Runs the injection-differential over `observations` and writes `{session_dir}/ai_trust_matrix.md`
    (session_dir is a toolkit-rooted PARAMETER, NOT a hardcoded bare `sessions/$DOMAIN` — otherwise
    the gate detector, which looks for the file in `dirname(ledger)`, would miss it; same contract
    as `authz_matrix.md`).

    `observations` = `list[dict]`, each element:
        {"payload_id":…, "intent_class":…, "benign": Response|dict, "injection": Response|dict,
         ["target": endpoint-override, "payload_text": <what was sent>, "target_obeyed": bool]}
    For each: (1) the DIFFERENTIAL `ai_injection_diff` (benign vs injection) -> an `ai-trust`
    Divergence + the vectors that fired; (2) SEPARATELY the GUARDRAIL-ORACLE
    (`guard_would_catch(payload_text)`) — annotates whether OUR guard would have caught the sent
    payload (the payload-source role is separated from the guardrail-oracle role: one is the
    `injection` snapshot, the other is `payload_text` through `INJECTION_PATTERNS`). The oracle
    result is placed into `evidence["guardrail_oracle"]` (visible in the ledger next to the raw
    divergence).

    Format: header + `TARGET`/`MODE` + source annotations (payload-source vs guardrail-oracle) +
    a summary table (one row per observation) + a `## Divergences` block with RENUMBERED
    `to_dnn_row()` rows (`D-01`->`D-NN`, each on its OWN physical line, matching `_D_ROW_RE`). An
    empty run (0 divergences) -> STILL writes the file with `RESULT: … 0 divergences`. Returns the
    path."""
    session_dir = str(session_dir)
    os.makedirs(session_dir, exist_ok=True)
    out_path = os.path.join(session_dir, "ai_trust_matrix.md")

    summary_rows = []
    dnn_blocks = []
    real_count = 0

    for obs in (observations or []):
        if not isinstance(obs, dict):
            continue
        pid = obs.get("payload_id", "?")
        intent = obs.get("intent_class", "?")
        ep = obs.get("target", target)
        a = _as_context(obs.get("benign"), "benign")
        b = _as_context(obs.get("injection"), "injection")
        probe = Probe("ai-trust", ep)
        div = differential(a, b, probe)

        # GUARDRAIL-ORACLE side (a SEPARATE role from payload-source): would our guard have caught the sent payload?
        ptext = obs.get("payload_text", "") or ""
        obeyed = bool(obs.get("target_obeyed", False))
        guard_catch = guard_would_catch(ptext) if ptext else False
        bypass = bool(guard_catch and obeyed)

        if div is None and not bypass:
            summary_rows.append("| %s | %s | %s | %s | %s | %s |" % (
                _safe_cell(pid), _safe_cell(intent), _safe_cell(str(ep)),
                "-", ("caught" if guard_catch else "n/a"), "-"))
            continue

        real_count += 1
        dnn_id = "D-%02d" % real_count
        vecs = [f for (f, _d) in observed_vectors(div)]
        if bypass and "guardrail_bypassed" not in vecs:
            vecs.append("guardrail_bypassed")
        vec_names = ",".join(vecs) if vecs else "-"

        if div is not None:
            if isinstance(div.evidence, dict):
                div.evidence["guardrail_oracle"] = {
                    "our_guard_would_catch": guard_catch,
                    "target_obeyed": obeyed,
                    "bypass": bypass,
                }
            row = div.to_dnn_row()
            row = _RENUMBER_D01_RE.sub("| %s |" % dnn_id, row, count=1)
            dnn_blocks.append(row)

        summary_rows.append("| %s | %s | %s | %s | %s | %s |" % (
            _safe_cell(pid), _safe_cell(intent), _safe_cell(str(ep)),
            _safe_cell(vec_names), ("caught" if guard_catch else "passed"),
            dnn_id if div is not None else "-"))

    lines = [
        "# ai_trust_matrix.md — AI-surface injection-differential harness run",
        "",
        "TARGET: %s" % _safe_cell(str(target)),
        "MODE: %s" % _safe_cell(str(mode)),
        "",
        "# payload-source: ai_prompt_injection_probe.build_payloads (withheld in public release)",
        "# guardrail-oracle: pi_guard_lib.INJECTION_PATTERNS (detection-regex — did OUR guard catch it?)",
        "",
        "| payload | intent | input | vectors | our-guard | D-NN |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(summary_rows)
    if dnn_blocks:
        lines.append("")
        lines.append("## Divergences")
        lines.extend(dnn_blocks)
    lines.append("")
    lines.append("RESULT: ai-trust matrix-run, %d divergences" % real_count)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


# ---------------------------------------------------------------------------
# LIVE-path OPSEC gate (fail-CLOSED, parity with runtime_harness.opsec_or_fallback).
# ---------------------------------------------------------------------------

def live_preflight(target, config, profile="web2"):
    """The fail-CLOSED OPSEC gate for the LIVE injection-differential path — MUST be called
    BEFORE any live run against a real agent target (parity with
    `runtime_harness.opsec_or_fallback`). Reuses `opsec_preflight.preflight` (via the
    runtime_harness re-export). Returns `"AUTO"` (gate passed: a live benign-canary-only run is
    allowed; magnitude fork-only; per-vector human authorization) or `"MANUAL"` (gate NOT passed
    OR any exception — fail-closed: do NOT auto-trust). THINK≠ACT: this gate only DECIDES, it
    NEVER runs a live exploit itself. `profile` is `"web2"` (primary for `/hunt`) or `"web3"`
    (for `/dapphunt`).

    `target` is a string slug (see `sessions/$DOMAIN/`); `config` is a flat dict of OPSEC checks
    (`vpn_active`/`incognito`/`not_logged_main`/`in_scope`/`rate_limit`/`objective` + web2:
    `test_accounts`>=2/`hosts_all_in_scope`, web3: `wallet_address`/`balance`/`balance_cap`).
    `in_scope` is wrapped into the `target`-dict that `preflight()` expects (same trick as
    `opsec_or_fallback`)."""
    try:
        cfg = config if isinstance(config, dict) else {}
        target_obj = {"slug": target, "in_scope": cfg.get("in_scope", False)}
        result = preflight(profile, target_obj, cfg)
        return "AUTO" if getattr(result, "ok", False) else "MANUAL"
    except Exception:
        return "MANUAL"
