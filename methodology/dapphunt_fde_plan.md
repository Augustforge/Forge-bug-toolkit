# Frontend Divergence Engine (FDE) — upgrade plan for `/dapphunt`

> Status: **PLAN** (accepted by the operator 2026-08-04), implementation in phases (Tier 1 → 2 → 3).
> A mirror of [`depth_engine_plan.md`](depth_engine_plan.md), but for **frontend hunting**.
> Source: an analysis of deephunt↔dapphunt (2026-08-04). Drives: transferring the divergence-first engine
> of deephunt to the dApp frontend with **adaptation**, not copying (a contract is static and closed, a dApp is
> a live composition of trust).
>
> **Consolidation revision 2026-08-05** (a final reconciliation against the system's code, BEFORE writing-plans; no new
> content was added — inconsistencies were reconciled): (1) 🔴 gate strategy — web checks = **the web mode of the existing
> detectors** (`active_model_incomplete` with the TB-/AC- namespace), NOT new `active_surface_model_*` names
> (`_INV_ID` already understands `TB-I1`/`AC-I1`); risk R4 removed; §8.5/§21.4/§38.1. (2) severity — a single
> `web_severity.py` (frontend profile), `frontend_severity.py` removed. (3) the "6 trust axes" ≠ the "5 model
> axes" of the `active_model_axes_incomplete` gate are separated — a coverage mapping is needed (§3.2). (4) §38 parity — the web template
> must carry `OPT-TODO`/`WAVE-2`/composite fields, otherwise the gates are no-ops (§8.2). (5) R6 DECIDED — a dispatcher on the
> invariant namespace, the sentinel = an alias (§24). (6) 🔴 a `hunt_entry_gate.py` fix (a URL in machine text) —
> the top priority of Tier 1, reproduced 3× (§39). The un-dup generators (VII–X) — no blind duplicates, cross-refs are explicit.

---

## 0. Diagnosis — why dapphunt is structurally weaker than deephunt

Three facts from a survey of the toolkit (2026-08-04), each the root of a weakness:

1. **`MODEL: N/A` is a kill switch, not a stub.** The sentinel `MODEL: N/A` in the ledger, via `_model_ctx→None`,
   **disables at once 12 Stop checks** of the completeness gate (`active_model_incomplete`,
   `active_divergence_unresolved`, `active_model_axes_incomplete`, `active_attention_gap_skipped`,
   `active_t11_undecided`, `active_library_not_banked`, …) **and the entire `model_first_nudge.py`**. That is,
   the divergence-first backbone — the main structural discipline of deephunt — is **switched off by
   design** for dapphunt. What remains is only the autonomous loop + anti-give-up (ABORT/FORK/DECISION_Q/BREADTH) +
   ledger-live/chat-wall + impacts/loopstate. All of "the place is pointed to by an artifact, not by taste" is missed.

2. **The scout and depth gates are anchored to contract vocabulary.** `active_ledger_scout_pending` requires a
   `## Scout Fan-Out` section with the partitions P-B/P1-P6 (accounting/oracle/access/state-machine/reentrancy/economic);
   `active_ledger_boundary_scout_skipped` **explicitly returns None** if the ledger has no `boundary/trust-perimeter`.
   The depth cluster (`depthmap_single_subsystem`, `t12`, `wide_but_shallow`) imposes the form "≥5 layers through
   DISTANT subsystems of the repo, `call→state→external→hook→accounting`, ≥3 subsystems" — an on-chain multi-contract
   model of depth. The frontend axis (DOM/handler→SDK-hook→wallet-provider→signer→tx-payload→onchain-effect→UI-refresh)
   does not fit into it: an instance either drops the fields (→ the gates are no-ops) or fills them with a contract narrative.

3. **dapphunt rests on the intuition of SELECT.** 100+ hypothesis sources in the skill, from which you choose "by taste".
   This is exactly what the DIVERGENCE-FIRST mandate of deephunt fought against: "what LOOKS risky is exactly the same
   for the crowd" → duplicates.

**The positive that we build on:** [`invariant_library.md`](invariant_library.md) already has a web2 entry
(a ccip-server pattern: sibling routes, one secret with different authorization = `ENFORCED` on A, `ABSENT` on
a sibling GET). The adaptation of divergence-first to the frontend **has already begun** — the plan continues it.

**What is stronger in dapphunt, conversely (do not break):** the `_dapphunt_lessons.py` self-improving loop
(`dapphunt_weights.json` feeds triage), the Phase 12 cross-dApp variant scan, a rich threat_models layer
(16 YAML), ready runtime stubs (`eip1193_mock_provider.js`, `onchain_poc_harness.py`).

---

## 1. The central principle

deephunt is strong in two things — **divergence-first** (the place is pointed to by an artifact) and **depth-ceiling**
(a vertical downward). They cannot be copied mechanically. Two core conclusions of FDE:

- **dApp divergence ≠ "a state invariant is not enforced". dApp divergence = "a trust boundary is not
  checked" OR "what is shown ≠ what is signed/happening".** This is the replacement for `MODEL: N/A`.
- **dApp hunting must be runtime-first, not bundle-grep-first.** You read a contract (bytecode = truth).
  A minified bundle **lies and is unreadable** — a dApp's truth is at runtime (the real signature, the real RPC traffic,
  the real DOM). Playwright MCP is available in the environment and underused.

---

## 2. Architecture — 7 components

| # | Component | Adapts | Tier | Artifact |
|---|---|---|---|---|
| 1 | Surface-Trust Model First | T10 / J-M | 1 | `surface_model.md` |
| 2 | Runtime Observation Harness | T11 (browser-driven) | 1 | `runtime_diff/` |
| 3 | Frontend Trust Library | invariant_library | 1 | `invariant_library.md` (§Frontend) |
| 4 | Data-Flow Divergence | — (new) | 2 | `dataflow_map.md` |
| 5 | Cross-Clone Differential (a mandatory phase) | T8 differential | 2 | `clone_diff.md` |
| 6 | Structured Completeness-Gate (web) | completeness-gate | 2 | a hook + `hypotheses_web.md` |
| 7 | Depth formalization + Inverted TM + Severity calc | depth-ceiling / T14 | 3 | `web_severity.py` (frontend profile) |

---

## 3. Component 1 — Surface-Trust Model First (Tier 1, the core)

> **(FDE Plan 4 — reconciliation with the code):** the artifact is implemented as `system_model.md` (the web profile from
> `system_model_web_template.md`), NOT `surface_model.md`.

**Artifact:** `sessions/$DOMAIN/surface_model.md` (the frontend analogue of `system_model.md`).
**Phase:** the new **P-SM**, between Phase 2 (recon) and Phase 2.5 (hypothesis gen). A mirror of J-M.
**Built BEFORE deep reading of the bundle / before the runtime test**, from the corpus: docs/whitepaper, the public
configs of auth providers (Privy `/api/v1/apps/<id>` and similar), the program scope + **Impacts in Scope**, past
reports (past-report analysis Phase 1), observed behavior (security headers, what the UI shows).

### 3.1 `TB-NN` — Trust-Boundary invariants (a replacement for `I-NN`)

Not state invariants but **invariants of trust and of the integrity of presentation**. The format mirrors `I-NN`
(a machine-readable line starting with `| TB-NN |`):

```
| ID | Trust invariant formula | check: what to go and check | Class | Source | component: | pred: | Status | file:line/endpoint | crowd-heat | lib |
| TB-01 | ∀ postMessage-handler: event.origin === EXACT from an allowlist | how is event.origin validated? | origin-trust | CSP+docs | msgRouter | ENFORCED | ? | bundle:chunk | cold | pm-origin-strict |
| TB-02 | the swap amount shown == buyAmount in the signed EIP-712 | from which variable is the DOM number vs the signature? | signature-integrity | UI | SwapForm | ENFORCED | ? | — | cold | display-eq-signed |
| TB-03 | ∀ clone (dev/staging/prod): an identical set of security headers + authz | curl -I every clone, diff | clone-parity | recon | infra | ENFORCED | ? | — | hot | clone-parity |
```

Mandatory fields (as in I-NN): `check:` (an executable check, not a retelling), `component:`, `pred:`
(set BEFORE the code/runtime, a retrospective one does not count), class, source.

### 3.2 Six trust axes (a replacement for `state|economic`)

Seed ALL of them at the start of P-SM (or `<axis>: N/A — reason`), like the 6 wave axes in deephunt:

1. **origin-trust** — who can embed (iframe/frame-ancestors), postMessage, CORS ACAO, OAuth redirect_uri,
   WC peer metadata.url. The origin↔origin boundary.
2. **signature-integrity** — what is on the screen == what is signed/sent (amount, recipient, chainId,
   deadline, token). The eye↔wallet-payload boundary. **The main dApp axis** (the Aave×CoW $50M incident).
3. **data-source-trust** — RPC / indexer / API backend / tokenlist tell the truth; their authz is the same on all
   hosts (prod vs staging). The dApp↔external-data boundary (the brutecat class).
4. **session-auth** — who is authenticated; nonce single-use; replay/expiry; initData HMAC. SIWE/SIWS/
   auth-provider/TMA.
5. **asset-identity** — decimals / chainId / token identity / ENS-resolution / blocklist — the displayed asset
   == the real one.
6. **clone-parity** — all clones and multi-chain deployments of one dApp carry the same protection (dev/staging/prod/
   mobile/web). The differential axis (Component 5).

> ⚠ **Terminology (reconciliation with the code 2026-08-05):** these 6 **trust axes** (origin/signature/data-source/…) —
> are NOT the same as the **model axes** of the real gate `active_model_axes_incomplete` (cross-function / order /
> temporal / isolation / economic). The gate checks the COVERAGE of the model along its own 5 axes. When reusing
> it in web mode (§8.5) an explicit mapping "6 trust axes → 5 model axes" is needed (e.g. signature-integrity →
> cross-function+isolation; clone-parity → isolation; session-auth → temporal+order), otherwise the gate is either a no-op,
> or falsely holds the turn. Decide when implementing the core — this is NOT a renaming, but a coverage mapping.

### 3.3 Five enforcement statuses (carried over verbatim, adapted definitions)

| Status | Frontend definition | Action |
|---|---|---|
| `ENFORCED` | a strict `===` / a canonical auth middleware **on all routes/components** | closed after the "on all paths" operator |
| 🔴 `ENFORCED-PARTIAL` | a check exists but is incomplete: origin via `.includes()`; auth on route A, a sibling GET is open; a chainId check on one path, not on another | **`D-NN`, top priority** (the main class) |
| `IMPLICIT` | relies on the browser / CSP / provider, but the code does not check | `[CONTESTED]`, a candidate |
| 🔴 `ABSENT` | there is no check anywhere | **`D-NN`, top priority** |
| 🔴 `SUBSTITUTED` | the canonical mechanism is replaced by a home-grown one: a custom origin regex instead of `===`; a client-generated nonce instead of a server-issued one; a custom decimals parse instead of token metadata | **`D-NN`, above `ABSENT`** |

`ENFORCED-PARTIAL` is the main class here too (a sibling route with different authorization = exactly it).

### 3.4 Three operators (adapted)

1. **"On all paths?"** → **"on all routes / components / clones / chains?"** — enumerate EXPLICITLY
   all sibling handlers that serve one secret / render one value / accept one signature, and
   check each (a signature-gated route vs an open GET of the same field).
2. **"Is the mechanism canonical?"** → **"a standard auth middleware / SDK mechanism or a home-grown one?"** —
   look not at the calling code (it looks canonical) but at what backs the source: is chainId taken from
   `wallet_getChainId` or hardcoded? origin via `===` or a custom regex? Check against the `fingerprint:` of the Trust
   Library. Functionality present + fingerprint absent = `SUBSTITUTED`.
3. **`pred:` against fact** — `pred:ENFORCED → fact ABSENT/SUBSTITUTED` = the top rank (a place that everyone
   considers closed — un-dup). The reverse = the domain model is wrong → `## Model Revisions`.

### 3.5 `D-NN` and ranking

The same ranker, with frontend semantics of the multipliers:
**Rank = blast-radius × sibling-count × (crowd-cold) × convergence ÷ crowd-heat penalty.**
- **blast-radius** (replaces value-weight): 1 user / all users / the protocol (walk backward from drain/leak/phish).
- **sibling-count** (replaces path-count): how many routes/components/clones bypass the invariant.
- **crowd-cold**: the place is not covered by past reports (Phase 1 attention-gap).
- **convergence**: how many DIFFERENT `TB-NN` converge on one `component:`.
- **crowd-heat**: a penalty, NOT a veto. `cold` first, `hot` mandatorily later.

SELECT order: `SUBSTITUTED` > `pred:ENFORCED→ABSENT` > `ABSENT` > `ENFORCED-PARTIAL`; within — by rank.

### 3.6 When `SURFACE-MODEL: N/A` is legitimate

A pure web2 target without a web3 surface and without an auth provider / a pure static site → `SURFACE-MODEL:
N/A — <reason>` (pivot to `/hunt`). NOT for a normal dApp — for it the model is mandatory.

---

## 4. Component 2 — Runtime Observation Harness (Tier 1, the core)

**Mode: a hybrid — Playwright under an OPSEC guard (operator decision 2026-08-04).** Browser automation is allowed, but
**only via an explicit OPSEC checklist as a gate**; a static fallback if OPSEC is not ready.

**The problem it solves:** dapphunt is static (grepping a lying bundle) when the truth is at runtime. T11
(Echidna) is inapplicable (no BUILD) — the frontend analogue: **a live browser as a generator of observations** that
cannot be obtained by reading the bundle. Like T11: the harness is run to **FIND** a divergence, not to confirm a hypothesis.

### 4.1 Signature-Interception Differential (the core of the harness)

The mechanism:
1. The OPSEC gate (see 4.3) is passed → Playwright MCP brings up an incognito session via VPN, injects the
   extended `eip1193_mock_provider.js` as `window.ethereum` (+EIP-6963 announce).
2. Run user scenarios (swap / approve / sign-in / bridge) along the route map from recon.
3. On every `personal_sign` / `eth_signTypedData*` the mock **intercepts the payload** AND the harness takes a
   **DOM snapshot at the same moment** (a Playwright snapshot).
4. **Auto-diff:** "the number / recipient / chainId / deadline shown" (from the DOM) vs "the signed" (from the payload).
   A divergence = a `D-NN` of machine origin (the signature-integrity class) → into `surface_model.md ## Divergences`.

**A fix of the existing mock:** currently `eip1193_mock_provider.js` returns *fake* signatures (`0x`+`ab`×65)
→ a dApp that verifies the signature falls over. Connect it to `onchain_poc_harness.py sign-typed-data` → return
a **valid burner signature** → the scenario runs to the end, we observe the full flow. Make `isMetaMask:true` configurable.

### 4.2 What else the harness generates (runtime-first observations)

- **The real security headers** of every clone/route (not the ones assumed from the bundle).
- **The real RPC/indexer/API traffic** (the network tab via Playwright) → data-source-trust checks:
  the same request on prod vs staging (authz-diff), a fallback to an attacker RPC.
- **postMessage traffic live** — which origins actually send, whether it is checked (complements the static
  `postmessage_audit.py`).

### 4.3 The OPSEC gate (mandatory before any Playwright run)

A separate check script `dapphunt/wallet_test/opsec_preflight.py` — all YES, otherwise the harness refuses to start
and falls back to static:
- [ ] VPN/Tor is active (not the main IP — the frontend sends analytics)
- [ ] a burner wallet (the canonical burner address `<BURNER_ADDRESS>`), not the main one
- [ ] incognito / an isolated profile, not logged in to a main Google/Twitter
- [ ] the target is confirmed in-scope
- [ ] the burner balance is within the cap

Recording the gate pass → `sessions/$DOMAIN/opsec_preflight.json` (audit).

### 4.4 Fallback (OPSEC is not ready / Playwright is unavailable)

The current path: the `burner_connect.py` scaffold + manual DevTools + `signature_inspector.py` offline decoding of a
pasted payload. The harness marks observations as `MANUAL`, not `AUTO`.

---

## 5. Component 3 — Frontend Trust Library (Tier 1, the core)

We extend the existing [`invariant_library.md`](invariant_library.md) with a `§ Frontend` section (we do not spawn
a second file — it already holds a web entry). The key = a **frontend primitive**, not a target. An entry:
**an invariant + `check:` + `fingerprint:` (a machine fingerprint of the canon) + `ref:` (a reference `file:line`)**.
The detection rule: **functionality present + the canon fingerprint absent = a candidate for `SUBSTITUTED`**.

The starter set (the frontend is more patterned than contracts → the library's ROI is higher):

| Primitive | Invariant | canon fingerprint: | anti-fingerprint (SUBSTITUTED flag) |
|---|---|---|---|
| postMessage origin | origin is checked strictly | `event.origin === "https://exact"` / allowlist-`.has()` | `.includes()` / `.indexOf()` / `.startsWith()` / regex |
| EIP-712 chainId | chainId from the wallet, not hardcoded | `domain.chainId` ← `walletClient.getChainId()` / `useChainId()` | a literal `chainId: 1` in a multi-chain deployment |
| SIWE nonce | a single-use server-issued nonce | nonce ← a server endpoint, marked used after verify | `Math.random()`/client-gen; no server-side invalidation |
| auth allowed_domains | an exact list | an exact host-list in the Privy/Magic config | a `*.domain.com` wildcard |
| Permit2/Permit deadline | a finite lifetime | `deadline` = now+Δ | `type(uint256).max` / "Forever" |
| iframe frame-ancestors | an explicit allowlist == auth allowed_domains | CSP `frame-ancestors 'self' https://exact` + XFO | `*` / absent / out of sync with the auth config |
| token decimals | from on-chain metadata | `decimals()` read from the token contract | hardcoded 18 / trusting user input |

Replenishment: the `active_library_not_banked` detector in web mode (§8.5) requires ≥1 entry at the exit of a hunt with a
non-empty web model (`LIBRARY-TODO` not cleared). A `fingerprint`-grep detector script — after ≥10 entries
(for now we grep by hand).

---

## 6. Component 4 — Data-Flow Divergence (Tier 2)

A static double of signature-integrity (complements the runtime harness, works when the browser is unavailable).
**Artifact:** `sessions/$DOMAIN/dataflow_map.md`.
The mechanism (a directed source→sink grep, NOT a full AST at the start): for a logical value (amount /
recipient / chainId / deadline) trace TWO sinks — **the DOM display** and **the signature/tx payload** — and their
sources. **Different sources for one value = a `D-NN`** (Aave×CoW: the output box from `destSpotAmount`,
the signature from `buyAmount` minus fees). Extends the existing `display_vs_reality_grep.py` from a pattern grep to
source→sink pairs. Evolution to taint/AST — Tier 3, if the pattern grep runs into minification.

---

## 7. Component 5 — Cross-Clone Differential as a mandatory phase (Tier 2)

Promote from a hypothesis source to a **mandatory phase** (an analogue of the T8 differential; a dev clone = a ready-made
attention gap, nobody audited it). **Artifact:** `sessions/$DOMAIN/clone_diff.md`.
Extend the existing `dapp_clone_detector.py` + `asymmetry_scanner_dapp.py` from "a head hash + headers" to
**semantics**:
- **env-diff** — `VITE_*`/`REACT_APP_*` between clones (staging RPC/API/keys).
- **CSP/headers-diff** — which clone lost frame-ancestors/XFO/CSP.
- **API-authz-diff** — the same request on prod→403 vs staging→200 with other people's data (the brutecat $500K class,
   broken-authz/IDOR). Check every non-prod API origin from recon with the same request as prod.
- **chain-deploy-diff** — multi-chain: is the EIP-712 domain/chainId binding the same on every deployment.

It feeds the `clone-parity` axis in `surface_model.md`.

---

## 8. Component 6 — Structured Completeness-Gate for web (Tier 2, critical)

Right now the completeness gate is contract-centric, dapphunt falls out (the diagnosis §0). The solution — **a parallel
web set in `hunt_completeness_gate.py`**, activated by a sentinel.

### 8.1 The `SURFACE-MODEL:` sentinel (a replacement for `MODEL: N/A` for a dApp)

> **(FDE Plan 4 — reconciliation with the code):** the `SURFACE-MODEL:` sentinel was NOT introduced — web mode is switched on by the
> invariant namespace `TB-`/`AC-` (`_model_namespace`), the resolution of §24 R6.

> **(FDE Plan 5 — reconciliation with the code):** the `ACCESS-MODEL:` sentinel was NOT introduced — web2 mode (like the dApp mode
> above) is switched on by the invariant namespace `AC-` (`_model_namespace`), the same mechanism.

Instead of muting the whole model cluster via `MODEL: N/A`, a dApp ledger carries:
```
SURFACE-MODEL: TB=8 ABSENT=2 PARTIAL=3 SUBSTITUTED=1 D-NN=4
```
The presence of `SURFACE-MODEL:` (not N/A) → the hook switches on the **web branch** of checks instead of the contract ones. `MODEL: N/A`
remains only for pure web2 (a pivot to `/hunt`).

### 8.2 The new ledger template `hypotheses_web.md`

> **(FDE Plan 4 — reconciliation with the code):** the ledger = an ordinary `hypotheses.md` from `hypotheses_web_template.md`
> (not a separate `hypotheses_web.md`); the entry gate chooses by `_is_web_target`.

> **(FDE Plan 5 — reconciliation with the code):** the web2 profile (`/hunt`) uses the same `hypotheses.md` from
> `hypotheses_web_template.md`, not a separate `hypotheses_web.md` — a common template for both web profiles,
> as Shared Core §21.3 assumes.

A separate canonical template (not the contract `hypotheses_template.md`). `hunt_entry_gate.py` chooses it
when the target is detected as a dApp (via the `dapp_detection.py` score / the `/dapphunt` intent). Sections:
- The header: Target · **Assets in Scope** · **Impacts in Scope** (`IMPACTS-TODO`) · Chain-class · Auth-providers
  · Clone-set · Audit/report history.
- `## Loop State` — the `SURFACE-MODEL:` counter · `Signing-Flow-Depth:` (the stack chain k/N) · `DEPTH-TRACE`
  (web-boundary/predicted/observed) · Iteration · Depth-Lead · Exit.
- `## Surface Model` — a counter + a reference to `surface_model.md`.
- `## Web Scout Fan-Out` — partitions by frontend axes (see 8.3) + **`OPT-TODO`** (an optional menu of partitions) +
  **`WAVE-2 … PENDING`** (an overflow of >7 partitions). §38 parity: without these fields the real `active_ledger_optmenu_todo`
  / `active_ledger_wave_pending` silently no-op for web.
- `## Divergences` — `D-NN` (from TB-NN enforcement + runtime-diff + clone-diff).
- `## Banked Findings` · `## Active Hypotheses` (H-NN; they carry a composite field → `active_ledger_composite_abandoned`
  works as is) · `## Refuted` (the KILL taxonomy) · `## Verifier Log (T4)`.

### 8.3 The web-scout skeleton (a replacement for P-B/P1-P6)

> **(FDE Plan 4 — reconciliation with the code):** the fan-out section = `## Scout Fan-Out` (not `## Web Scout Fan-Out`);
> the web3 partitions P-SIGN/P-ORIGIN/P-CLONE/P-AUTH/P-DATA/P-DISPLAY + optional P-TMA/P-AI are already in the template.

> **(FDE Plan 5 — reconciliation with the code):** the fan-out section = `## Scout Fan-Out` (the same shared sentinel); the web2 partitions
> P-AUTHZ/P-INJECT/P-LOGIC/P-AUTH/P-TENANT/P-EXPOSURE are already in the `hypotheses_web_template.md` template.

Partitions by frontend trust axes, with a web anchor in the ledger (so that `scout_pending` finds the section):
`P-SIGN` (signing/EIP-712/permit2) · `P-ORIGIN` (postMessage/iframe/CORS) · `P-CLONE` (clone-parity/differential)
· `P-AUTH` (auth-provider/SIWE/session) · `P-DATA` (RPC/indexer/tokenlist/API) · `P-DISPLAY` (display-vs-reality/
asset-identity). Optional `P-TMA`, `P-AI` on detection.

### 8.4 Web-depth semantics (a replacement for cross-subsystem repo)

The stack's trust chain instead of `call→state→external→hook→accounting`:
```
L1 user-action (DOM/handler)
L2 SDK/React-hook (wagmi/viem formatter)
L3 wallet-provider (EIP-1193 payload build)
L4 signer / EIP-712 domain binding
L5 tx-payload / RPC broadcast
L6 on-chain effect
L7 UI-refresh (indexer lag / stale cache)
```
The bug is at the JOINT of layers (the L2 hook shows, the L4 signer signs something else). The DEPTH-TRACE T12 fields are adapted:
boundary = a transition of a stack layer; predicted/observed = what the hook showed vs what the signer signed; **fan-in** = who
else writes into this value (which other components build the payload).

### 8.5 Gate checks in web mode (a branch of the EXISTING detectors, NOT new names)

**The course (accepted 2026-08-05, a reconciliation with the hook's code): we do NOT spawn parallel `active_surface_model_*` names —
we extend the existing detectors with a web mode.** Rationale: `hunt_completeness_gate.py` already carries `_INV_ID`
with namespaced `TB-I1`/`W3-I1`/`AC-I1` — the infrastructure for web invariants is partly in the code. A dispatcher on the
web invariant namespace (TB-/AC-) + `hypotheses_web.md` switches a detector to web anchors. This removes
~8 newly invented names and risk R4 (a regression of a 2806-line branch).

The mapping "existing detector → what changes in web mode":
- `active_model_incomplete` → web: `surface_model.md`/`access_model.md` is missing / 0 `TB-NN`|`AC-NN` / no `check:`
  / >12 per wave / axes not seeded.
- `active_model_order_violation` → web: the status is set, `pred:` is empty (namespace-agnostic, unchanged).
- `active_divergence_unresolved` → web: an open `D-NN` (signature-integrity / object-authz / …) without
  `→ H-NN`/`KILLED`.
- `active_ledger_scout_pending` → web: the `## Web Scout Fan-Out` partitions (P-SIGN/…/P-AUTHZ/…) ≠ DONE/N-A/DEFERRED.
- `active_library_not_banked` → web: at HUNT-EXIT `LIBRARY-TODO` is not cleared with a non-empty web model.
- `active_ledger_wide_but_shallow` → web: Depth-Lead is declared, `Signing-Flow-Depth`/authz-chain-depth < the target.
- `active_ledger_composite_abandoned` / `active_ledger_optmenu_todo` / `active_ledger_wave_pending` → work
  as is (namespace-agnostic) — but the web template MUST carry the `OPT-TODO`/`WAVE-2`/composite fields (§8.2), otherwise
  they silently no-op and §38 parity breaks.
- **A NEW detector only where there is no mechanic at all:** `active_clone_diff_skipped` (`## Web Scout Fan-Out`
  carries `P-CLONE`, while `clone_diff.md` is empty/not run).

> **(FDE Plan 5 — reconciliation with the code):** by the same principle `active_authz_matrix_skipped` was added (the web2
> authz-matrix producer skipped — `## Scout Fan-Out` carries `P-AUTHZ`, while `authz_matrix.md` is empty/not run),
> co-located with `authz_diff.py run_authz_matrix`; namespace-separated from `active_clone_diff_skipped`
> (dApp `P-CLONE`/`TB-` vs web2 `P-AUTHZ`/`AC-`) — they do not intersect, §38.5 parity holds.

The schema-independent core (the loop, anti-give-up, ledger-live, impacts, depth_spin) remains shared. **The toolkit's
rule: first the replay test, then the gate** — every web mode of a detector gets a case in `gate_replay.py`
(prove it fires on an untouched web template, not only the absence of FPs).

---

## 9. Component 7 — Depth formalization + Inverted TM + Severity calc (Tier 3)

- **Signing-Flow depth-drive** — formalize §8.4 as a mandatory depth-drive of ≥N layers on the strongest
  `D-NN` (a SELECT priority, like depth-lead-first in deephunt).
- **Inverted threat models** — extend `wallet_metadata_xss_check.py` to the class **"an external input lies to the
  dApp"**: an evil wallet (an EIP-1271 liar, metadata XSS, an injection race), an evil RPC/indexer (phantom balances →
  over-borrow), an evil tokenlist. Systematize "every external input is untrusted, what if it lies to the maximum"
  = depth along the data-source-trust axis.
- **`web_severity.py` (the frontend profile, a SINGLE calculator for both web skills, §21.7/§35.5)** — instead of scattered string severities: `user-interaction-gate`
  (visit / click / sign) × `reachability` (a default route? a feature flag? does the entry point exist?) × `blast-radius`
  (1 user / all / the protocol) → a tier + a platform mapping (the HackenProof/Immunefi/Cantina rubric). Accounts for
  the rule that a route in code ≠ reachable (verify UI reachability).

---

## 10. What we do NOT carry over (a contract ≠ a dApp)

- **T11 Echidna/invariant fuzzing, symbolic execution, Manticore/bytecode** — there is no closed system;
  the replacement = the runtime harness (Component 2).
- **A mainnet-fork PoC as the MAIN one** — for the frontend the PoC = a live browser + a captured HAR/signature; the fork remains
  as T4 verification of the on-chain part (`onchain_poc_harness.py` already exists).
- **J4 profit≥10×cost math** — frontend severity is gated by user-interaction × reachability × blast-radius,
  not by profit math (Component 7).
- **T10-B family-diff of contract primitives** — replaced by the Frontend Trust Library (§5).

---

## 11. The reordered `/dapphunt` workflow

| Phase | Was | Becomes |
|---|---|---|
| 0-1 | detect + setup | unchanged; the entry hook chooses `hypotheses_web.md` |
| 2 | passive recon | unchanged (feeds the P-SM corpus) |
| **P-SM** | — | **NEW: Surface-Trust Model First** → `surface_model.md` (TB-NN, 6 axes, pred:) |
| 2.5 | hypothesis gen (intuition) | **an enforcement-map by TB-NN** (a mirror of J1) → D-NN + topping up threat_models |
| 3 | stack fingerprint | unchanged (feeds the Trust Library fingerprints) |
| 4 | auth config | feeds the origin-trust/session-auth axes |
| 5 | iframe/clone | **promoted: a mandatory Cross-Clone Differential** → `clone_diff.md` |
| 6 | wallet integration | **the core: Runtime Observation Harness** (OPSEC gate → signature-diff) |
| 7 | postMessage | feeds origin-trust; supplemented by runtime observation |
| 8 | frontend surfaces | unchanged |
| 8.5 | TMA | unchanged |
| 9 | active recon | unchanged (the OPSEC gate is shared) |
| 10 | chain analysis | **a depth-drive on the strongest D-NN** (Signing-Flow ≥N layers) |
| 11 | T4 + report | + the `web_severity.py` calculator (frontend profile) |
| 12-13 | variant scan + calibration | unchanged (a strong side, keep) |

---

## 12. Implementation plan (phases)

**Tier 1 (the divergence-first core + runtime):**
1. `surface_model_template.md` + the P-SM section in the `/dapphunt` skill + a `surface_model_builder` prompt (TB-NN, 6 axes).
2. The Frontend Trust Library — the `§ Frontend` section in `invariant_library.md` (the starter set of §5).
3. The Runtime Harness: the `opsec_preflight.py` gate + a fix of `eip1193_mock_provider.js` (valid signatures) +
   a Playwright signature-diff driver + the `runtime_diff/` artifact.

**Tier 2 (structured enforcement + differential):**
4. The `hypotheses_web.md` template + `hunt_entry_gate.py` choosing the template by the dApp detection.
5. The web branch in `hunt_completeness_gate.py` (the §8.5 gates) + the `SURFACE-MODEL:` sentinel + **replay tests of each
   gate in `gate_replay.py`** (the rule: a test before the gate).
6. Cross-Clone Differential — an extension of `dapp_clone_detector.py`/`asymmetry_scanner_dapp.py` (env/CSP/authz/
   chain diff) → a mandatory Phase 5.
7. Data-Flow Divergence — an extension of `display_vs_reality_grep.py` to source→sink pairs → `dataflow_map.md`.

**Tier 3 (polish):**
8. Formalization of the Signing-Flow depth-drive in the skill.
9. Inverted threat models — an extension of `wallet_metadata_xss_check.py` + 2-3 new threat_models YAML.
10. The `web_severity.py` calculator (the frontend profile, shared with web2 §35.5) + integration into Phase 11.

**The measurement rule (as in deephunt):** a significant edit of the hook/methodology → re-score against
`regression_manifest.yaml`, recall does not drop / precision grows. Every new gate must have a replay test
proving that it fires on an untouched web template.

---

## 13. Open questions / risks

- **R1 — Playwright injection of the mock provider.** Can Playwright MCP use `--init-script`/the DevTools Protocol to
  inject `window.ethereum` before the page loads? Check at the Tier 1.3 stage (it may require
  `browser_run_code_unsafe` / evaluate before navigation). If injection before page-load is impossible — some dApps
  initialize the provider earlier, and the harness will miss.
- **R2 — a valid burner signature in the mock.** Returning a real signature means the scenario will actually
  sign the typed data. For fork/testnet — fine; on a mainnet read-only flow a signature without a broadcast is safe, but
  a strict gate "no broadcast without an explicit cap" is needed (already in `onchain_poc_harness.py`).
- **R3 — minification breaks the source→sink grep** (Component 4). A fallback to the runtime harness (Component 2) —
  which is why Data-Flow is in Tier 2, not Tier 1.
- **R4 — the hook's web branch of 2806 lines.** The risk of a regression of contract enforcement. Mitigation: a dispatcher on the
  sentinel isolates the branches; replay tests of both branches are mandatory.
- **R5 — the `hypotheses*.md` glob.** `freshest_active_ledger` picks up `hypotheses_web.md` (the glob
  `hypotheses*.md`) — check that the contract and web ledgers do not conflict in one session.

---

# PART II — The second profile: Web2 Divergence Engine (`/hunt` → pure web2)

> Added 2026-08-04 (the operator: "hunt will become web2, dapphunt overlaps — there is common ground, it will be more accurate").
> Decisions: `/hunt` is reworked into **pure web2** (the web3/solana/ton branches are removed), proactive is
> **web2-only**. The file structure (a single engine + profiles vs splitting/renaming) — decided LATER,
> when both profiles are ready. For now — we enter it here.

## 14. Diagnosis of `/hunt` — why the web2 path is the weakest of the three skills

1. **`/hunt` is a multiplexer for 5 domains**, not a web2 skill: web2 (phases 1-10) + Web3 EVM + Solana
   (Phase K) + TON Node + a proactive router. It is spread thin.
2. **The web2 path stayed purely tool-driven.** Phase 2.5 "Hypothesis Generation" is **explicitly marked
   "MANDATORY for Web3"** — for web2 there is NO hypothesis discipline. Web2 goes: recon → fingerprint →
   JS mining → active scan → vuln scan → chain → report = "ran nuclei, dumped the output". This is exactly
   what `/hunt` itself uses to distinguish itself from `/deephunt`. deephunt lives on divergence-first, we are pulling dapphunt
   up (Part I) — **web2 got neither divergence-first nor even a hypothesis discipline.**
3. **The thesis: web2 is the most natural home of divergence-first, more natural than dapphunt.** BOLA/IDOR (OWASP
   API #1) and BFLA (#5) are literally "an authorization invariant is not enforced on all sibling endpoints".
   The web2 entry of `invariant_library.md` (a ccip-server pattern: `ENFORCED` on route A, `ABSENT` on a sibling
   GET) is **verbatim web2 BOLA**. And a runtime differential for web2 (the same request from account A and B → a diff of
   responses) is a classic (Burp Autorize/Auth-Analyzer), automated more cleanly than dapphunt (deterministic
   HTTP vs a brittle browser).

## 15. The transformation strategy for `/hunt`

- **Remove entirely:** Web3 EVM mode · Solana mode (Phase K) · TON Node mode · Web3 proactive.
  Web3 contracts → `/deephunt`, the web3 frontend → `/dapphunt`, TON → a separate target. Keep only a
  **one-line route detect**: if `dapp_detection.py` score ≥50 → "this is a dApp, go to `/dapphunt`";
  if a verified contract/`.sol` → "`/deephunt`". It does not hunt web3 itself.
- **Proactive → web2-only:** H1 / Bugcrowd / Intigriti / YesWeHack / HackenProof-web2 / Standoff365.
  Remove the Immunefi/Cantina Deep tier (they are web3) and the candidates.json gluing of web3 sources.
- **Rewrite the phases for divergence-first** (§16-20): a new P-AM (Access Model) → the hypothesis becomes
  MANDATORY (not "for web3") → the Authorization-Differential harness as the core → a structured gate.

## 16. The web2 engine profile — Access-Trust Model First (a mirror of §3)

> **(FDE Plan 5 — reconciliation with the code):** The artifact is implemented as `system_model.md` (the web profile from
> `system_model_web_template.md`, namespace `AC-`), NOT `access_model.md`.

**Artifact:** `sessions/$DOMAIN/access_model.md` (the web2 analogue of `surface_model.md`/`system_model.md`).
**Phase P-AM** between recon and hypothesis. Built BEFORE active testing, from the corpus: **OpenAPI/Swagger/
GraphQL schema** (gold — a ready map of endpoints and objects), API docs, roles/tiers from the UI, HTTP responses
observed passively, past reports. No schema → a surrogate: JS mining of endpoints + a passive crawl.

### 16.1 `AC-NN` — Access-Control / trust invariants (a replacement for `TB-NN`)

```
| ID | Invariant formula | check: | Axis | Source | component: | pred: | Status | endpoint/route | crowd-heat | lib |
| AC-01 | ∀ endpoint serving an object O: ownership(caller, O) is checked | is there an authz middleware on EVERY route with :id? | object-authz | OpenAPI | GET/PUT /api/orders/:id | ENFORCED | ? | /api/orders/:id | cold | authz-middleware |
| AC-02 | admin functions require the admin role on all methods | do DELETE/PATCH check the role or only GET? | function-authz | UI-roles | /api/admin/* | ENFORCED | ? | — | cold | rbac-guard |
| AC-03 | the reset token is unpredictable + single-use + TTL | how is it generated and invalidated? | auth-integrity | docs | /reset | ENFORCED | ? | — | hot | reset-token-crypto |
```

### 16.2 Six web2 axes (a replacement for the 6 web3-frontend axes)

1. **object-authz (BOLA/IDOR)** — every object checks ownership on every endpoint/method. OWASP API #1.
2. **function-authz (BFLA)** — privileged functions (admin, DELETE, role-change, export) check
   the role. OWASP API #5.
3. **auth-integrity** — a session/JWT/OAuth/token cannot be forged/replayed/fixated; the reset token is cryptographically strong.
4. **tenant-isolation** — multi-tenant: the data of org/workspace A does not leak into B.
5. **input→sink** — user input does not reach a dangerous sink: SQL/NoSQL/OS-cmd/template(SSTI)/LDAP/XPath/
   deserialization; **+ SSRF** (the server does not go to an attacker URL).
6. **business-logic** — invariants of a deal/price/quantity/status/balance: race (double-spend), replay,
   negative/overflow, workflow-skip (payment bypass), quantity/coupon manipulation.

The long tail (consult-when-matched, not walked): data-exposure (responses/errors/logs), CORS misconfig, cache
poisoning/deception, HTTP request smuggling, open-redirect, file-upload, subdomain-takeover — partly
covered by `/hunt` scripts already (`http_smuggling.py`, `cache_deception.py`, `jwt_advanced.py`, `graphql_advanced.py`).

### 16.3 Five statuses (the web2 adaptation)

| Status | Web2 definition | Action |
|---|---|---|
| `ENFORCED` | authz middleware/parametrization on all sibling endpoints and methods | closed after "on all paths" |
| 🔴 `ENFORCED-PARTIAL` | authz on `GET /orders/:id` exists, on `PUT/DELETE /orders/:id` does not; v1 is protected, v2 is not; the check is in the UI, not in the API | **`D-NN`, top priority** (BOLA lives here) |
| `IMPLICIT` | relies on UUID obscurity / a "secret" URL / a client-side check | `[CONTESTED]` |
| 🔴 `ABSENT` | there is no check | **`D-NN`, top priority** |
| 🔴 `SUBSTITUTED` | home-grown authz (a manual `if user.id==...` across handlers, a custom JWT verify) instead of a framework guard | **`D-NN`, above `ABSENT`** |

### 16.4 Three operators (the adaptation)

1. **"On all paths?"** → **"on all sibling endpoints / methods (GET/POST/PUT/DELETE/PATCH) / API versions
   (v1 vs v2) / parameter variants (id vs uuid vs slug)?"** — enumerate EXPLICITLY all methods of one
   resource and check each. This is the operationalization of BOLA.
2. **"A canonical mechanism?"** → **"a framework guard/middleware or a home-grown one?"** — authz via a decorator/
   middleware (`@requires_auth`, Django perms, Rails `before_action`) = the canon; a manual inline check
   scattered across handlers = a `SUBSTITUTED` flag. Check against the `fingerprint:` of the Web2 Trust Library.
3. **`pred:` against fact** — `pred:ENFORCED → fact ABSENT` = the top rank (an endpoint that everyone considers
   protected).

### 16.5 `D-NN` ranking — the same ranker (Shared Core §21)

blast-radius (the data of 1 user / all / the whole DB) × sibling-count (how many methods/endpoints bypass) ×
crowd-cold × convergence ÷ crowd-heat.

### 16.6 🔴 Business logic — a SEPARATE sub-model (the source ≠ the API schema)

**A hole in model-first that must be closed explicitly.** BOLA/BFLA/injection/auth are derived from OpenAPI/the schema
(an endpoint = the unit). But **race / payment-bypass / workflow-skip / quantity-manipulation** (the best-paying
web2 class) are NOT derived from the schema — there is no "endpoint invariant" there, there is a **business-process invariant**
(price→payment→delivery). Divergence-first by `AC-NN` will simply miss this class.

The solution — a `BL-NN` sub-model, the source = **the UI flow + docs (the process sequence), not the API schema**:
```
| BL-01 | payment MUST precede the delivery of the goods | can /fulfill be called without a successful /pay? | source: checkout-flow | statem: cart→pay→fulfill | pred: ENFORCED | status: ? |
| BL-02 | the quantity is debited atomically (no double-spend) | two parallel /redeem of the same coupon? | source: UI | race | pred: ENFORCED | ? |
| BL-03 | the status moves only forward (no reopening of a paid one) | does a POST to a closed order change the amount? | source: docs | statem | pred: ENFORCED | ? |
```
This is a **state-machine model of a business process** — closer to `state_machine_analyzer.py` (already in `/hunt`,
currently for the web3 lifecycle → **adapt to the web2 business flow**) and to the deephunt order-dependent/
temporal axes than to an authz matrix. The check — via the harness (§17): race = parallel requests; workflow-skip =
jumping over a step; replay = repeating a finalizing call. `BL-NN` live in `access_model.md ## Business Logic`,
go into the common `D-NN` pool and the ranker.

## 17. Component — Authorization-Differential Harness (a mirror of §4, the web2 core)

**Runtime-first for web2** (a replacement for the signature-diff harness). Under the same OPSEC guard (§4.3, Shared Core).
**The mechanism — a matrix run:** N accounts (roles: `admin` / `user-A` / `user-B` / `unauth`) × every
endpoint from recon (OpenAPI / JS mining / passive crawl) → an **auto-diff of responses**:
- `user-B` gets `200` with `user-A`'s data = **BOLA** (an object-authz `D-NN`).
- `unauth` gets `200` on a protected one = **broken-auth**.
- `user-A` calls an admin function and gets non-`403` = **BFLA** (function-authz).

This is an automated Autorize/Auth-Analyzer. **The tool — mitmproxy / a `requests` script (deterministic
HTTP, not a browser);** optionally Playwright only for authentication/session capture. The harness also generates:
an error-oracle for input→sink probes (SQLi/SSTI blind-diff), real CORS/headers, a business-logic race (parallel
requests to one resource). **Artifact:** `sessions/$DOMAIN/authz_matrix.md`.
**Web2-specific OPSEC:** authorized test accounts (2+ own in-scope accounts), a rate limit so as NOT to
affect availability (no DoS), in-scope hosts only. `opsec_preflight.py` is extended with a web2 branch.

> **(FDE Plan 5 — reconciliation with the code):** the `opsec_preflight` web2 branch + `prompt_injection_guard` +
> the `hunt_entry_gate.py` URL fix — were implemented in Plans 1/3 (Shared Core), they are NOT a task of Plan 5 (the design prose
> here and in §27/§39 is stale — it was written before this infrastructure shipped).

## 18. Component — Web2 Trust Library (a mirror of §5, the `§ Web2` section in `invariant_library.md`)

| Primitive | Invariant | canon fingerprint: | anti-fingerprint (SUBSTITUTED) |
|---|---|---|---|
| authz | the check goes through a framework guard | `@requires_auth`/Django perms/Rails `before_action`/middleware | a manual inline `if user.id==...` across handlers |
| JWT verify | verify with alg from config + secret | lib `verify(token, secret, {algorithms:[...]})` | `alg:none` accepted / verify off / alg from the header |
| SSRF guard | a host allowlist + resolve-then-check | an explicit host allowlist after DNS resolution | a blocklist / a regex on `localhost`/`127.` |
| password-reset | a crypto single-use token + TTL | a CSPRNG token, invalidated after use, expiry | sequential/predictable / no-expiry / reuse |
| CORS | an exact-origin allowlist | a static list of origins | reflect `Origin` + `credentials:true` / `*` |
| SQL | parametrization/ORM | a prepared statement / an ORM query builder | string concatenation into the query |
| session | server-side, regenerate on privilege change | secure/httponly/samesite + regen | client-trusted / no-regen / fixation |

## 19. Web2 scout partitions + depth semantics (a mirror of §8.3-8.4)

**Partitions (a web anchor in the ledger):** `P-AUTHZ` (BOLA/BFLA) · `P-INJECT` (SQL/SSTI/cmd/SSRF) · `P-LOGIC`
(race/replay/workflow) · `P-AUTH` (session/JWT/OAuth/reset) · `P-TENANT` (isolation) · `P-EXPOSURE`
(data-leak/CORS/secrets). Optional `P-INFRA` (smuggling/cache/takeover).
**The web2-depth chain** (a replacement for the stack chain): `request → routing → authz-middleware → business handler →
ORM/data-layer → DB → response → serialization`. The bug is at the joint: authz skipped for one route at the middleware
layer; the data layer returned fields that the serializer does not filter (mass-exposure). The depth-drive =
trace ONE object from entry to the data layer and back to the response, find where authz/the filter is skipped.

## 20. The reordered `/hunt` workflow (web2)

| Phase | Was | Becomes |
|---|---|---|
| 1 | setup | unchanged; the entry hook chooses `hypotheses_web.md` |
| 2 | passive recon | unchanged (feeds the P-AM corpus: subdomains, JS, secrets) |
| **P-AM** | — | **NEW: Access-Trust Model First** → `access_model.md` (AC-NN, 6 axes, from OpenAPI/docs) |
| 2.5 | hypothesis "for Web3" | **an enforcement-map by AC-NN** (mandatory for web2!) → D-NN + a threat-model top-up |
| 3 | fingerprint | unchanged; Phase 3.5 dApp-detect → reduced to a route one-liner |
| 4 | JS mining | feeds the P-AM endpoint map + the Trust Library fingerprints |
| 5-6 | active/vuln scan | **the core: the Authorization-Differential harness** (OPSEC gate → matrix-diff) + nuclei/sqlmap as a hypothesis check |
| 7 | chain analysis | **a depth-drive on the strongest D-NN** (an authz-chain / exposure-chain) |
| 8-9 | bounty + report | + `web_severity.py` (unauth/auth-gate × reachability × data-sensitivity/blast-radius; CVSS) |
| 10 | prioritization | unchanged |

**Already in the `/hunt` toolkit (reuse as a hypothesis check, NOT as SELECT):** `github_recon`,
`email_security`, `js_mining`, `jwt_advanced`, `cache_deception`, `http_smuggling`, `graphql_advanced`,
`websocket_test`, `cicd_leak_scanner`, `recon.sh`/`scan.sh` (nuclei/sqlmap). **Add:** the Authorization-
Differential harness, the `access_model` builder (OpenAPI→AC-NN), the Web2 Trust Library, a BOLA/BFLA matrix scanner,
a business-logic race harness.

---

# PART III — Shared Core (the intersection of the profiles — "it will be more accurate")

## 21. What is implemented ONCE and used by both profiles

FDE is not two engines but **a core + two domain profiles**. The domain-independent core:

1. **The enforcement calculus** — 5 statuses (`ENFORCED`/`ENFORCED-PARTIAL`/`IMPLICIT`/`ABSENT`/`SUBSTITUTED`) +
   3 operators ("on all paths?" · "a canonical mechanism?" · `pred:` vs fact). Identical in §3.3-3.4 and §16.3-16.4.
2. **The `D-NN` ranker** — `blast-radius × sibling-count × crowd-cold × convergence ÷ crowd-heat`. The same one.
3. **Ledger machinery** — the `SURFACE-MODEL:` sentinel + the `hypotheses_web.md` template + the Loop State fields
   (Depth-Lead, DEPTH-TRACE, Iteration, Exit). One template for both web profiles.
4. **The structured completeness-gate web mode** — a dispatcher on the web invariant namespace (TB-/AC-) +
   `hypotheses_web.md`; it reuses the EXISTING detectors (`active_model_incomplete` / `_order_violation` /
   `active_divergence_unresolved` / `active_ledger_scout_pending` / `active_library_not_banked` /
   `active_ledger_wide_but_shallow`) in web mode — only the **partition anchors** change (web3: P-SIGN/P-ORIGIN/…;
   web2: P-AUTHZ/P-INJECT/…) and the divergence class. A new detector only `active_clone_diff_skipped`. Not new
   names (§8.5).
5. **T14 Attention-Gap** — an inversion of past reports + the git of an OSS repo. Identical.
6. **The OPSEC gate** (`opsec_preflight.py`) — VPN/burner/isolated/in-scope/rate-limit. Shared, with a per-profile
   branch (web3: a burner wallet; web2: test accounts + a rate limit).
7. **The T4 cold verifier** + **the severity calculator skeleton** (`web_severity.py`; a factor profile per domain).
8. **The Trust Library mechanics** — `fingerprint:`/`ref:`/anti-fingerprint → SUBSTITUTED detection. One mechanic,
   different entries (`§ Frontend` / `§ Web2` in the shared `invariant_library.md`).

## 22. Where the domains literally intersect (a shared web layer)

**A dApp's API backend is web2.** So a number of axes are shared by both profiles, implemented once:

| Shared axis | In dapphunt (web3-frontend) | In hunt (web2) |
|---|---|---|
| **object-authz / BOLA** | data-source-trust: a staging API → prod data with authz switched off (brutecat $500K) | object-authz: IDOR/BOLA on any API #1 |
| **origin/CORS** | origin-trust (postMessage/iframe/CORS) | CORS misconfig (data-exposure) |
| **session/auth** | session-auth (SIWE/auth-provider) | auth-integrity (session/JWT/OAuth) |
| **secrets-in-JS** | env-leak in the bundle (§3 Phase 3) | JS-mining secrets (Phase 4) |
| **open-redirect** | the OAuth callback (§8) | open-redirect (long-tail) |

**The difference is only in the "tops":** the web3-frontend adds signature-integrity / wallet / chainId /
clone-parity; web2 adds SSRF / SQLi / business-logic-race / tenant-isolation / smuggling. The conclusion for the
structure (when we decide on the split): **a core + a shared web layer (authz/origin/session/exposure) + two
domain tops** — more accurate than two independent plans. This is the "it will be more accurate" of the operator.

## 23. The updated implementation plan (both profiles)

The order — the Shared Core first (otherwise we duplicate), then the profiles:
- **The core (§21):** the enforcement calculus in the methodology prompts · the `D-NN` ranker · the `hypotheses_web.md`
  template + the `SURFACE-MODEL:` sentinel · the web branch of `hunt_completeness_gate.py` + replay tests · a shared
  `opsec_preflight.py` · the Trust Library mechanics in `invariant_library.md`.
- **Profile A — web3-frontend (dapphunt):** Part I §3-9 (surface_model, the signature harness, the frontend
  library, clone-diff, web3 scout partitions).
- **Profile B — web2 (hunt):** §16-20 (access_model, the authz-differential harness, the web2 library, web2
  scout partitions, the **business-logic sub-model §16.6**) + cutting out the web3/solana/ton branches + web2-only proactive.

**Tier 1 web2 — specifics (accepted 2026-08-04):**
- **`openapi_to_acnn.py`** (makes P-AM cheaper): parses a public OpenAPI/Swagger/GraphQL schema → an `AC-NN`
  skeleton (endpoint × method × object → an invariant stub with `pred:`). In web2 the schema is often public —
  the model is **semi-automated**, unlike contracts (where the model is manual). No schema → a manual
  model from JS mining + a passive crawl.
- **`state_machine_analyzer.py` → a web2 branch** for `BL-NN` (a business-flow state machine instead of the web3 lifecycle).
- **The Authorization-Differential harness** + the **Web2 Trust Library** + cutting out web3/solana/ton.

## 24. Open questions (the web2 profile)

- **R6 — the sentinel (DECIDED 2026-08-05 by a reconciliation with the code).** `_INV_ID` in the hook already understands the namespaced
  `TB-I1`/`AC-I1` → no separate gate machinery for web is needed: the dispatcher is tied to the **invariant namespace**
  (TB-/AC-), not to a new sentinel line. `SURFACE-MODEL:`/`ACCESS-MODEL:` remains as a **readable alias**
  in the ledger header (the profile is clearer to a human) + the web-mode switch instead of the disarming `MODEL: N/A`. web2
  vs web3 are distinguished by the invariant prefix (AC- / TB-), not by different hook mechanisms. One dispatcher, two branches.
- **R7 — test accounts for authz-differential (DECIDED 2026-08-04).** The default: (1) try self-registration
  → 2 burner accounts; (2) the program offers no self-reg → request them from the operator/the program; (3) a fallback
  single-account + unauth diff (catches broken-auth, not BOLA between users). The harness marks the mode in
  `authz_matrix.md` (`full-matrix` / `single+unauth`).
- **R8 — the fate of the TON branch.** We remove it from `/hunt`, but TON has no skill of its own. Keep it as a separate
  target mode or create `/tonhunt` later? (does not block the web2 rework).
- **R9 — where to deploy the `access_model` builder.** OpenAPI→AC-NN: an auto-parse of the schema if it is public;
  otherwise a manual model. Automation — Tier 2 web2.

---

# PART IV — External research: a transfer from 6 repos (2026-08-04)

> 6 repos were studied by agents (one per repo). Here is the synthesis: what to adopt, where to integrate it. Filtered
> for our goals, not "everything in a row". The priority is marked where: [web2 §..], [Shared §..], [dapphunt §..], [avoid].

## 25. Summary of sources

| Repo | Type | The main value for us |
|---|---|---|
| vavkamil/awesome-bugbounty-tools | a catalog of ~350 tools | the Autorize algorithm (= our authz-diff); an endpoint-discovery arsenal; new classes (DNS-rebind, 403-bypass, key-validation) |
| KingOfBugBountyTips | oneliners | recon pipelines verbatim; hypothesis heuristics (IDOR/BFLA/race by URL pattern); an SSRF obfuscation list; sourcemap/favicon tricks |
| mukul975/Anthropic-Cybersecurity-Skills | 817 AI skills | 🔴 payload libraries of 8 web2 classes verbatim; the `IDORTester` agent.py (two-session) = a reference for authz-diff; the Pitfalls / Output-Format / Common-Scenarios formats |
| aliasrobotics/cai | an agentic framework | 🔴 a prompt-injection guardrail for incoming content; scout engineering (budget/internal-wrapper/dual-contest); a pattern typology |
| uphiago/recon-skills | ~150 recon skills | 🔴 the Endpoint Interest Score + attack_path_hint (recon→hypothesis); anti-FP gates (Marker/Body-Diff/Statistical); schema-enum via error-hints; source-map fake-detect |
| 0x4m4/hexstrike-ai | an MCP tool server | the Error→Recovery enum; a unified result shape; objective aggressiveness (quick/stealth); + what NOT to imitate (shell=True, no rate limit) |

**A meta-conclusion:** our **Authorization-Differential harness** (§17, priority #1 of web2) received **TWO ready
reference implementations** — the Autorize algorithm (session-swap + response-diff) and the `IDORTester` agent.py
(`test_horizontal`/`test_vertical`/`test_id_enumeration`/`test_write`/`test_cross_session`). This sharply
reduces the cost of Tier 1 web2 — we do not invent, we adapt + surpass (a semantic field-diff instead of status-only).

## 26. The transfer into web2 `/hunt`

### 26.1 Ready artifacts (low effort, high value)
- **Payload libraries of 8 classes** (Anthropic-skills: BOLA/BFLA/BOPLA/JWT/OAuth2/mass-assignment/blind-SSRF/
  rate-limit/CORS) → `scripts/web2/payloads/*.md` + entries in the Web2 Trust Library (§18). Portable almost
  verbatim (curl/python chains).
- **The `IDORTester` agent.py** → the basis of `scripts/web2/authz_diff.py` (the §17 harness). The two-session check
  is already written — adapt to our OPSEC gate + matrix (N roles).
- **The SSRF IP-obfuscation list** (KingOfBugBounty: decimal/octal/hex/unicode-fullwidth loopback + localtest.me) →
  `scripts/web2/payloads/ssrf_bypass.md`.
- **A secrets regex set** (all GitHub token formats `ghp_/gho_/ghu_/ghs_/ghr_/github_pat_`, AWS/Google/Slack/
  Discord/JWT/private-key) → reconcile/extend our secrets script.
- **`graphql-OFJAAAH.yaml`** (~140 GraphQL discovery paths) → an API-discovery step of recon.

### 26.2 Recon → P-AM formalization (the input to §16)
- 🔴 **Endpoint Interest Score (0-100) + attack_path_hint** (recon-skills §20/§39) — a formalized transition
  of the recon map → prioritized hypotheses. **This is the missing link BEFORE P-AM:** recon builds a map of
  endpoints with scoring (unauth-write +40, open-introspection +35, verb-bypass +30, reflected-CORS+creds
  +25, sensitive-keyword +20, schema-leak +20…), every score≥70 carries an `attack_path_hint` (signal→next
  step). The artifact `endpoint_scoremap.md` → feeds `AC-NN`.
- **The endpoint-discovery arsenal** (a complete map = a precondition of authz-diff): `kiterunner` (API routes by
  wordlist), `param-miner`/`Arjun`/`x8` (hidden params → `user_id`/`tenant_id` = a BOLA channel), `jsluice`
  (semantic JS mining), `katana` (a crawler), a **source-map pipeline** (recon-skills: `.js.map` →
  `sourcesContent` → an endpoints/apis regex) with **fake-detection** (`head -c 80`: `{` = a map, `<!DOCTYPE` =
  an SPA catch-all), **endpoint extraction regex tiers** (3 levels recall→precision + dedup by `/{id}/`).
- 🔴 **Schema enumeration via error hints** (recon-skills, a separate technique) — PostgREST/Supabase
  `{"hint":"Perhaps you meant table 'real_name'"}`, Zod/FastAPI validation errors on an empty POST → all
  required fields. A free map of the DB/fields without docs → a direct entry into BOLA/mass-assignment. A new recon step.

### 26.3 Business-logic specifics (feeds §16.6 BL-NN)
- **Race candidates by URL verbs** (`redeem|coupon|vote|transfer|withdraw`) — a heuristic for generating BL-NN.
- **`turbo-intruder` single-packet** — true simultaneity for a payment/coupon/withdraw race (requests-
  based race does not provide it). A harness tool for §17.
- **A mass-assignment payload** (`{"admin":true,"role":"admin","isAdmin":1,...}` on user/profile/register) +
  the BOPLA class (Anthropic-skills: excessive-data-exposure + mass-assignment together).
- **An HTTP-method matrix** (GET/POST/PUT/DELETE/PATCH/OPTIONS filtered by non-404/405) — a mandatory step of the
  "on all methods?" operator (§16.4.1) for BFLA.

### 26.4 Anti-false-positive gates (strengthen the T4 verifier)
- 🔴 **Marker Discipline** (an 8+ char random marker, NEVER `test`/`javascript`/your own name — a real
  false positive: `X-Forwarded-Proto: javascript` → a fake reflection) · **the Body-Diff Rule** (a 200 with an identical body ≠
  a bypass) · **the Statistical-Sample Rule** (a timing claim → n≥10 interleaved, 2σ) · **the Shell-Loop Ban** (>5
  iterations → Python, not zsh). Embed into the T4 web2 branch as concrete checks.
- **The "Pitfalls" format** (Anthropic-skills: typical misses per class, e.g. BOLA "tested only GET",
  "took a UUID for protection", "did not check batch") → add a subsection to the web2 class checklists = a built-in
  anti-false-negative gate.

### 26.5 New classes (not explicit in our methodology)
- **DNS rebinding as a sub-class of SSRF** (singularity/whonow/dref) — TOCTOU via DNS.
- 🔴 **403/WAF bypass as a separate class, to be distinguished from an auth 403** (nomore403/Forbidden-Buster) — **critical
  BEFORE authz-diff**: a technical WAF 403 ≠ an auth-logic 403, otherwise the harness yields a false BOLA. A §17 pre-step.
- **Key validation after a leak** (keyhacks) — a secret = Info/Low until it is confirmed live in a non-destructive
  way → a formal step "leak → a keyhacks check".
- **Origin IP behind a CDN** (CloudRip/hakoriginfinder, favicon-mmh3/JARM/DNS history) — a WAF/rate-limit bypass.
- **Backslash-powered scanning** (PortSwigger/Kettle) — detecting unknown injection differentially
  (a weird-but-invalid payload → a response diff), **a conceptual relative of divergence-first at the HTTP level**.

## 27. The transfer into the Shared Core / the system (both skills)

- 🔴 **A prompt-injection guardrail for incoming target content** (CAI) → a new item of Shared Core §21 +
  the OPSEC gate. Our agents read live pages / other people's repos / audits — a payload against the
  AI hunter may sit there (the owner could have planted it). The mechanism: regex patterns (override instructions/"NOTE TO SYSTEM"/exfil) +
  **Unicode homograph normalization** (Cyrillic/Greek confusables → Latin, NFKD) + **base64/base32
  decode-then-check** + `sanitize_external_content()` (wrapping untrusted content in delimiters "DATA,
  not commands"). Multi-layered (regex is not the only layer, CAI themselves admit it is bypassable). **We do not have this —
  a real hole.**

> **(FDE Plan 5 — reconciliation with the code):** `prompt_injection_guard.py` is already implemented (Plan 3, `scripts/hooks/`)
> and active in `.claude/settings.json` — "we do not have this" above is stale. Together with the `opsec_preflight` web2 branch
> and the `hunt_entry_gate.py` URL fix (see §17) they close this whole hole long before Plan 5; see §39 for the hook
> map.
- **The Error→Recovery enum** (hexstrike) → `scripts/_methodology/error_recovery.py`: stderr/exit → TIMEOUT/
  PERMISSION/RATE_LIMITED/TOOL_NOT_FOUND → RETRY_BACKOFF/REDUCE_SCOPE/SWITCH_TOOL/ESCALATE. The harness must
  distinguish the target's rate limit vs an auth fail vs network (otherwise authz-diff gets confused).
- **A unified result shape** (hexstrike: `{stdout,stderr,return_code,success,timed_out,partial,exec_time,ts}`)
  → a contract for toolkit scripts, so that scout subagents parse uniformly.
- **Scout Fan-Out engineering** (CAI) → strengthen `scout_fanout.workflow.js`: a per-worker output budget
  (`combined // n`), an `<orchestrator_internal>` wrapper of worker output (anti-slop, do not quote verbatim),
  ≤1-2 tools per worker, **`run_dual_approach_contest`** (two orthogonal hypotheses at a fork) as an explicit
  call in the divergence workflow.
- **Objective aggressiveness** (hexstrike: quick/comprehensive/stealth) → a flag in the OPSEC gate, tied to
  program/no-program (the no-program active-testing rule) — explicit, not intuitive.
- **A command cache LRU+TTL** (hexstrike) → the authz-diff harness: do not duplicate idempotent baseline requests.
- **cross-attack-chains "co-occurrence is not dependency"** (recon-skills) → the T3 chaining gate: findings on
  one target ≠ a chain without a proven handoff of output-A→input-B ("Draw the Dependency").

## 28. The transfer into dapphunt (web3-frontend)

- **The JS/source-map pipeline + secrets** (jsluice/SecretFinder/keyhacks/fake-detection) → §3 Phase 3 env-leak +
  §5 fingerprints: a dApp = an SPA, a source map gives on-chain addresses / RPC / the auth-provider config.
- 🔴 **`humanize-automation`** (recon-skills: Playwright Bézier mouse/typo input/overshoot scroll) → §4 Runtime
  Harness: bypassing behavioral anti-bot (reCAPTCHA v3) during live dApp UI tests.
- **A favicon→Shodan/mmh3 pivot** → find staging/admin instances of the dApp's infra (feeds §5 clone-parity).
- **graphw00f/clairvoyance** → dApp GraphQL (indexers/subgraph) fingerprint + schema with introspection disabled.
- **The prompt-injection guardrail** (§27) — a dApp is browsed live, the same risk.

## 29. Anti-patterns (what NOT to imitate — recorded)

- **`shell=True` without `shlex`** (hexstrike — 0 shlex across the whole code) → our scripts ONLY `subprocess` with
  list args + `shlex.quote`, never shell concatenation of agent/target-controlled input.
- **No outbound rate limit** (hexstrike/CAI) → the authz-diff harness must rate-limit (no DoS,
  mass-targeting is forbidden). The OPSEC-web2 gate.
- **A mock indistinguishable from the real thing** (hexstrike: a fake CVE from the same API) → mark a placeholder explicitly
  (never cheat on verification).
- **"Zero refusals"/marketing framing** (CAI) → do not borrow; our white-hat/legal gate is stricter.
- **A regex guardrail as the only layer** (CAI themselves admit it is bypassable) → multi-layered.
- **Do not drag in the whole structure** (recon-skills ~150 files with duplication; KingOfBugBounty AI-slop sections
  "TelnetPwn"/a fake CVE) → a targeted extraction of artifacts, not copying catalogs.

## 30. Update of the implementation plan (merging Part IV)

- **Tier 1 web2** is supplemented: payload libraries of 8 classes + `IDORTester`→`authz_diff.py` (ready
  references), the Endpoint Interest Score + the endpoint-discovery arsenal (the input to P-AM), schema-enum via error-hints.
- **Shared Core** is supplemented: the prompt-injection guardrail (§27) — **raise to Tier 1** (agent safety,
  both skills), error_recovery.py + a unified result shape, scout engineering.
- **Tier 2 web2:** anti-FP gates in T4, new classes (DNS-rebind/403-bypass/backslash-scan/key-validation),
  a business-logic harness (turbo-intruder/method-matrix/mass-assignment).
- **dapphunt:** humanize-automation in §4, source-map/secrets, a favicon pivot.

## 31. New open questions (Part IV)

- **R10 — the prompt-injection guardrail: a hook or a library?** A PreToolUse hook on the return of Agent/WebFetch/
  Playwright that sanitizes external content? Or a library called by scouts? Decide when implementing
  the Shared Core (leaning towards a hook — like our other gates, it catches at the tool boundary).
- **R11 — the Endpoint Interest Score vs our D-NN ranker: two scorings or one?** The Score calibrates the recon map
  BEFORE the model; D-NN ranks divergences AFTER. Proposal: Score = the input (which endpoints go into `AC-NN` first),
  D-NN = the output (which divergences to drive). They do not duplicate — different stages. To confirm.
- **R12 — backslash-powered scanning** as a separate unknown-injection detector: build our own or wrap the
  PortSwigger approach? A relative of divergence-first — worth studying the algorithm separately (Tier 3).

---

# PART V — Recheck (reading the clones) + browser-first + web2→dapphunt + fresh ideas (2026-08-04)

> I re-read the clones myself (IDORTester, CAI guardrails, the offensive-osint Endpoint Score) — adding specifics
> on top of the agents' reports. + The operator: **both skills must work through the browser** (dapphunt used to rarely
> open it — wrong). + the web2→dapphunt adaptation + my fresh ideas.

## 32. Additions from the re-read (exact specifics for implementation)

### 32.1 IDORTester (Anthropic-skills) — what we take, what we surpass
The exact structure (`exploiting-idor-vulnerabilities/scripts/agent.py`): the class `IDORTester(base_url, token_a,
token_b)`, 5 methods — `test_horizontal_idor` (own vs other URL under session A; vuln = both 200 + a different
md5), `test_vertical_idor` (an admin endpoint under a user token = 200), `test_id_enumeration` (iterating a range →
200), `test_write_idor` (PUT other_id → 200/201/204), **`test_cross_session`** (session A vs B on one
resource → the same hash + both 200 = `missing_authz`).
- **`test_cross_session` = the direct core of our §17 harness** — we take it as the basis of `authz_diff.py`.
- **What we surpass (their weaknesses):** (1) only status+md5-diff → add a **semantic field-diff** (B sees
FIELDS it should not, not merely "different content"); (2) a hardcoded `Bearer` → cookie/custom auth;
  (3) **no rate limit** → mandatory for us (no DoS); (4) 2 sessions → an **N-role matrix** (admin/A/B/unauth);
  (5) the CLI drives only horizontal → drive all 5 methods + the BFLA method matrix.

### 32.2 CAI guardrails.py — ready code + critical details
Two guardrails: **input** (detecting injection in incoming content) + **output** (detecting dangerous commands before
execution). Components: ~25 `INJECTION_PATTERNS` regexes, `normalize_unicode_homographs` (a Cyrillic/Greek→
Latin map + NFKD), base64/base32 **decode-then-check**, `sanitize_external_content` (a delimiter wrapper
"DATA, not commands"). Thresholds: >4 patterns → block; ≥3 → an AI detector (confidence>0.9).
- 🔴 **Critical: `CAI_GUARDRAILS` default = `"false"` — it is off by default for them.** For us — **on
  by default** (otherwise pointless).
- 🔴 **A live lesson from a session:** our `hunt_entry_gate.py` latches onto github text in task notifications
  (a grep of the slug) → falsely raises a hunt session. This is THE SAME class — external/machine text injects our
  parser. The guardrail is needed not only on target content but on **our own hook parsers** (not
  reacting to URLs/instructions in untrusted text). Add to R10.
- The code is almost portable → `scripts/_methodology/prompt_injection_guard.py` + a PreToolUse hook on the return of
  Playwright/WebFetch/Agent. Multi-layered (regex is not the only layer).

### 32.3 offensive-osint — exact tables + a modular architecture
- **The Endpoint Interest Score (§20, verbatim):** unauth-write +40 · GraphQL-introspection +35 · verb-tampering
  +30 · reflected-CORS+creds +25 · sensitive-keyword(`admin/internal/debug/user/token/export/delete/…`) +20 ·
  schema-leak-in-error(stack-trace/ORM-class) +20 · api-key-in-URL +15 · wildcard-CORS +10 · missing-rate-
  limit +10. Thresholds: ≥90 CRIT · 70-89 HIGH · 50-69 MED · 25-49 LOW.
- **attack_path_hint (§39, 40 templates)** — every high-score signal → one phrase "where to start
  exploitation" (unauth-POST → "try IDOR+privesc, check sequential IDs"; verb-tampering → "missing-method
  authz"; sourcemap-with-sourcesContent → "reconstruct the frontend, grep secrets"). Many are about infra
  (actuator/heapdump/elasticsearch/redis/mongo/kubelet/etcd) = an **infra-recon class wider than a pure web app**.
- **15 on-demand references:** `secret-patterns.md` (48 regexes), `secret-validators.md` (9 read-only —
  a keyhacks analogue, validation without abuse), `dork-corpus.md` (80+), `severity-matrix.md` (80+ worked examples
  → severity calibration), identity-fabric, recon-stack, breach, etc.
- **Mobile App Ownership Confidence (§21)** — a 0-100 scoring of "does the APK belong to the target?" (our mobile is weak).
- **Evidence hygiene:** every artifact = `url + UTC timestamp + sha256 + raw≤2KiB`. Confidence
  `TENTATIVE/FIRM/CONFIRMED` (= our Observed/Inferred/Confirmed).
- 🔴 **An architectural lesson:** offensive-osint = a lean SKILL.md (~400 lines) + 15 on-demand references (it was a
  4168-line monolith). **Our skills are bloated** (deephunt 1264 lines, dapphunt 834) — see the idea §35.6.

## 33. 🔴 BROWSER-FIRST MANDATE (both skills) — the operator 2026-08-04

**Both skills MUST work through a live browser (Playwright), not through a static grep of the bundle/HTML.**
dapphunt used to rarely open a browser — this is recognized as WRONG. We formalize it as an FDE principle:

- **A live browser = the primary observation tool (the default), a static grep = a fallback.** The truth of the web
  is at runtime (real headers, signatures, RPC/API traffic, the DOM), not in a lying minified bundle.
- **web2 `/hunt`:** the authz-differential harness drives real sessions through the browser (fetch/XHR interception,
  an N-account matrix), not only a `requests` script. The browser provides real authentication/cookies/the CSRF flow.
- **dapphunt:** the Runtime Harness (§4) is not an option "if OPSEC is ready" but the DEFAULT: typed-data interception ⨯ DOM.
- **The OPSEC guard remains** (§4.3): browser-first UNDER the OPSEC preflight (VPN/burner/isolated/rate-limit), but
  this is a gate BEFORE launch, not a reason not to open a browser. OPSEC not passed → a static fallback +
  the `MANUAL` mark, but the goal is always to reach live observation.
- **The tool:** Playwright MCP (available in the environment) + `humanize-automation` (§28, anti-bot bypass).
- **The impact on the architecture:** the Runtime Harness is lifted from §4 (dapphunt-only) into the **Shared Core** —
  a single browser observation layer for both profiles (see the fresh idea §35.1).

## 34. Adapting web2 findings → dapphunt (similar mechanics)

Since a dApp's API backend = web2 (§22), most of the web2 findings of Part IV map onto dapphunt:
- **IDORTester/authz-diff** → the dApp's web2 backend (the staging-API brutecat class §3.2 data-source-trust): the same
  2-session/N-role matrix on the API of the dApp's exchange/custodial service.
- **The Endpoint Interest Score + attack_path_hint** → scoring dApp API/indexer/RPC endpoints (not only web2).
- **Payload libraries** (BOLA/BFLA/mass-assignment/CORS/JWT/OAuth2) → the dApp's web2 backend + auth providers
  (Privy/Magic/ThirdWeb use OAuth2/JWT over the same protocols).
- **schema-enum via error-hints** → a dApp GraphQL indexer/subgraph (PostgREST/Supabase are often behind a dApp).
- **anti-FP gates** (Marker/Body-Diff/Statistical) → dApp active tests.
- **secret-patterns (48) + validators (9)** → JS mining of the dApp bundle (RPC keys/auth-provider secrets).
- **the prompt-injection guardrail** → a dApp is browsed live (§33) + reads on-chain metadata (a token symbol =
  attacker-controlled, our long-standing XSS class) → the same injection risk into our harness.
- **infra-recon attack_path_hints** (actuator/elasticsearch/redis/mongo) → the infra of a dApp project (the same
  backends behind the frontend).
The reverse (dapphunt→web2): **the clone-parity differential** (§7) — the concept "the same code, different protections per
host" maps onto web2 as well (prod vs staging vs dev API of the same application).

## 35. My fresh ideas (a synthesis of the repos + in general)

### 35.1 🔴 Differential Observation — a single core primitive (of both domains)
web2 BOLA (2 users, 1 resource → diff), web3 signature (DOM vs payload → diff), web2 tenant-isolation (2
tenants), clone-parity (2 deployments), broken-auth (auth vs unauth) — this is **ALL one primitive:
`differential(ctx_A, ctx_B, probe) → divergence`**. Formalize it as the core of the harness in the Shared Core:
a browser layer + N contexts (roles/accounts/deployments/sessions) + one probe + a semantic diff of the response. This
unifies §4 (signature-diff) + §7 (clone-diff) + §17 (authz-diff) under ONE mechanism. The maximum
of "it will be more accurate": not three harnesses, but one primitive with different contexts.

### 35.2 Endpoint Score = a generator of AC-NN candidates (resolves R11)
The Score calibrates the recon map BEFORE the model; D-NN ranks AFTER. The bridge: **every score≥70 endpoint +
attack_path_hint → auto-generates a CANDIDATE `AC-NN`** (unauth-POST /api/users → AC-NN "endpoint requires
auth", pred:ENFORCED, hint "try IDOR"). The Score is a generator of web2 invariants, not a duplicate of the ranker. Recon→P-AM
becomes an algorithm, not prose. **R11 is resolved.**

### 35.3 attack_path_hint as a mandatory field of D-NN
Every `D-NN` carries an `attack_path_hint` (where to drive depth) — as in offensive-osint §39. It speeds up the
depth-drive: not "a divergence exists" but "a divergence + here is the first step down". Cheap, a high ROI.

### 35.4 A bidirectional prompt-injection guardrail + our own parsers
Not only the incoming content of the target (§27) but the realization: **our hooks/parsers are an attack surface** (in one
session: the entry gate latches onto github text). The guardrail on TWO boundaries: (a) content that the
harness reads (a page/repo/audit/on-chain metadata); (b) our parser hooks do not react to URLs/instructions in
untrusted machine text (notifications/scout returns). On by default (unlike CAI).

> **(FDE Plan 6 — reconciliation with the code):** part (a) is closed by Plan 3 (`prompt_injection_guard.py`, live
> content) + the `hunt_entry_gate.py` URL fix (the §39 flag above). Part (b) — "our parser hooks do not react
> to untrusted machine text" — remained a real hole PRECISELY in `hunt_completeness_gate.py`
> (the Stop hook reads `last_user`/`last_assistant` from the transcript, where the content of an async
> task notification lands literally as "role=user") until **Plan 6, Task 6**: `_MACHINE_BLOCK_RE`/
> `_strip_machine_text` are applied to both fields BEFORE the RELEASE/INFO_REQUEST keyword match. A full audit of
> the 6 active hooks for this hole — the `HANDOFF.md` §35.4(b) table (5/6 clean, 1/6 was a hole — now
> fixed).

### 35.5 web_severity.py is fed by the severity matrix + Endpoint-Score + attack_path_hint
Replace the scattered string severity with a single calculator (§7/§16.5 Tier 3), calibrated against the
severity matrix (80+ worked examples) + the Endpoint-Score thresholds. A single source of severity for both profiles.

### 35.6 A lean-core + on-demand references refactor of all skills (the system)
offensive-osint proved: a 400-line core + 15 loadable references >> a 4168-line monolith. Our
`/hunt`(804)/`/dapphunt`(834)/`/deephunt`(1264) are bloated — loaded in full every session. The refactor:
a lean core (principles+phases+gate) + `references/` per phase/class (payloads/checklists/threat-models), Claude
reads only what is needed. Saves context, speeds things up. A system-level, separate stage.

### 35.7 Evidence hygiene in the ledger/T4 (the system)
Every finding artifact = `url + UTC timestamp + sha256 + raw≤2KiB` (offensive-osint §4). Our ledger has
State A→D, but the evidence hash is weaker. Add to T4/submission — provability + anti-"I thought so".

### 35.8 Confidence tags Observed/Inferred/Confirmed/Not-tested (the system)
recon-skills + offensive-osint strictly separate fact/hypothesis with these tags. Our T2 STATE A→D is close, but
explicit tags on EVERY recon/lead item strengthen anti-false-positive (you cannot drive an `Inferred` as
`Confirmed`). A light addition to the ledger.

## 36. The impact on the implementation plan (Part V)
- **Shared Core (Tier 1):** the Differential Observation primitive (§35.1) + the browser-first layer (§33) —
  the foundation of both harnesses. The prompt-injection guardrail (§35.4) is on by default.
- **web2 Tier 1:** `authz_diff.py` based on IDORTester (§32.1) + the Endpoint Score→AC-NN bridge (§35.2) +
  a port of secret-patterns/validators.
- **dapphunt:** browser-first is mandatory (§33), the web2 adaptation (§34).
- **Tier 3:** web_severity.py (§35.5) on the severity matrix. A separate stage: the lean-core refactor (§35.6).

## 37. Updated open questions
- **R10 (refined):** the prompt-injection guardrail = a PreToolUse hook on the return of Playwright/WebFetch/Agent +
  a library for the harness. Bidirectional (§35.4). Default ON.
- **R11 (DECIDED §35.2):** the Endpoint Score = a generator of AC-NN candidates; the D-NN ranker = after enforcement. They do not
  duplicate.
- **R13 — the Differential Observation primitive:** one class `differential(ctx_A, ctx_B, probe)` with drivers
  (http-session / browser-session / deploy-host / signature-context)? Design the interface at Tier 1
  Shared Core.
- **R14 — the lean-core refactor:** do it within FDE or as a separate project afterwards? (big, touches 3
  skills). Leaning towards a separate stage after the engine stabilizes.

## 38. 🔴 THE AUTONOMOUS LOOP — parity with deephunt (the operator 2026-08-04: "important!")

**Both skills (web2 `/hunt` + dapphunt) MUST work in an autonomous loop IDENTICALLY to deephunt** (it
currently works as it should — the reference). This is not "add a gate" but a **property**: the Stop hook holds the turn, forces
the next single-pick, the only exit is `HUNT-EXIT: T4-CONFIRMED <High|Critical>`, keep-alive bumps the
marker, anti-spin (8 blocks / >30 min), parking does not exist. The operator gives only the goal — the loop spins by itself
for hours/days.

**The problem (from a survey of the hook, §0/§8-B/§8):** for web the loop currently works PARTIALLY — it rests only on the
schema-independent core (anti-give-up ABORT/FORK/DECISION/BREADTH, ledger-live, chat-wall, impacts,
depth_spin, LOOP_CONTINUE). While **the entire MODEL/divergence cluster (12 checks) + the scout/depth gates are disarmed
for web** (MODEL:N/A switches them off; the scout anchors P1-P6/boundary are contract-specific; the depth semantics are cross-subsystem-
repo). So autonomy exists, but WITHOUT the divergence-first discipline — the loop spins but does not force
model-first/D-NN/scout the way deephunt does.

**The requirement for parity (implemented in the Shared Core, Tier 1-2):**
1. The web invariant namespace (TB-/AC-) + the sentinel `SURFACE-MODEL:`/`ACCESS-MODEL:` (§8.1) switches on web mode
   for **all** divergence checks — the same detectors (`active_model_incomplete` / `_order_violation` /
   `active_divergence_unresolved` / `active_ledger_scout_pending` / `active_library_not_banked`, §8.5) hold
   the turn EXACTLY as the contract MODEL checks hold deephunt. Not an N/A stub (which disarms) but
   a full web model in the existing detectors.
2. Web-scout anchors (`## Web Scout Fan-Out`, P-SIGN/P-ORIGIN/… or P-AUTHZ/P-INJECT/…) — so that
   `scout_pending` forces explore-wide instead of silently no-oping.
3. The web-depth semantics (the stack chain / signing-flow) — so that `wide_but_shallow`/`t12` force
   a depth-drive instead of requiring a cross-subsystem-repo narrative.
4. A single exit `HUNT-EXIT: T4-CONFIRMED` + the Differential Observation harness (§35.1) as the source of T4
   (browser-first §33).
5. **A parity replay test:** a run proving that a web ledger (`hypotheses_web.md` with `SURFACE-MODEL:`)
   holds the turn in the same classes of situations in which the contract one holds it for deephunt (it is not disarmed). This is the
   acceptance criterion of the Shared Core.

**The wording for implementation:** "MODEL:N/A for a normal dApp/web2 app = a BUG, not a mode". N/A is legitimate
only for a pure static site. A normal web target → `SURFACE-MODEL:` with a model → a full
autonomous loop with divergence discipline = parity with deephunt. Raise to Tier 1 (without it the browser-first
harness spins without the model-first helm).

## 39. The hook transfer map (the operator 2026-08-04: "do not adopt all, look at what is needed and for what")

The autonomous loop (§38) rests on hooks. An analysis of each — is it needed for web, what it does, what to adapt.
**The principle: adapt, do not duplicate** — the hooks dispatch on the sentinel (`SURFACE-MODEL:` /
`hypotheses_web.md`), one codebase, two branches.

| Hook | Event | What it does | Status for web | What exactly |
|---|---|---|---|---|
| `hunt_completeness_gate.py` (2806 lines) | Stop | the loop engine + the completeness gate | 🔧 **ADAPT (the core)** | the §8.5 web branch: the sentinel switches on web divergence checks; web-scout/depth anchors. The schema-independent core (loop/anti-give-up/ledger-live) already works |
| `hunt_entry_gate.py` | UserPromptSubmit | detects a hunt URL → ledger+marker+injection | 🔧 **ADAPT** | (1) choosing `hypotheses_web.md` on a dApp/web2 detection; (2) a web `model_note` (SURFACE-MODEL, not a contract I-NN); (3) 🔴 **a fix: do not latch onto a URL in machine text** (notifications/scout returns — a bug of one session, false hunt sessions). Merge with the §35.4 guardrail |
| `model_first_nudge.py` | PreToolUse (Agent/Edit/Write) | nudges model-first before scout | 🔧 **ADAPT** | currently muted by `MODEL:N/A` → teach it `SURFACE-MODEL:` (nudge surface-model-first before web-scout). Otherwise for web it is silent = no model-first helm |
| `ledger_first_nudge.py` | PostToolUse (Agent) | a scout returned with an empty ledger → "write the leads first" | ✅ **AS-IS** | schema-independent (checks for the presence of H-NN), works for web without edits |
| `docker_build_reminder.py` | PreToolUse | a Docker reminder on heavy builds | ⚠️ **PARTIAL** | web2 depends on it less (a browser ≠ docker), but nuclei/sqlmap/ffuf run in the Docker bbt — keep for these commands; not relevant for Playwright |
| 🆕 `prompt_injection_guard.py` | PreToolUse (Playwright/WebFetch/Agent return) | sanitizes incoming content + detects injection | 🆕 **NEW (Tier 1)** | §35.4: code from the CAI guardrails (portable), default ON, bidirectional (target content + our parsers). Critical for browser-first (§33) — the harness reads attacker-controlled DOM/metadata |
| 🆕 `opsec_preflight` (a gate, not a hook) | before a Playwright launch | a VPN/burner/isolated/rate-limit check | 🆕 **NEW (Tier 1)** | §4.3 + a web2 branch (test accounts + a rate limit). The browser-first gate |

**The toolkit's rule (to be observed):** every adapted/new hook → a **replay test BEFORE the hook**, proving
that it FIRES on an untouched web template (not only the absence of FPs). Web branches are added to the existing `*_replay.py` harnesses.

**The conclusion:** we carry over 4 by adaptation (completeness-gate, entry-gate, model-first-nudge — the core of the loop; docker
partially), 1 as-is (ledger-nudge), 2 new (prompt-injection-guard, opsec-preflight). There is no blind copying —
each dispatches on the sentinel. This is "parity with deephunt" at the level of hooks.

🔴 **TOP PRIORITY of Tier 1 (empirics 2026-08-05):** a fix of `hunt_entry_gate.py` "do not latch onto a URL/slug in
machine text" — NOT web-specific but a systemic bug that breaks EVEN non-hunt sessions. Reproduced THREE times
(a word from an agent's report → a false reactivation of `.hunt_active`
→ a SCOUT-GATE cascade held the turn). The same class as the prompt-injection guardrail (§35.4): untrusted machine
text injects our parser. Do it FIRST in the Shared Core, before the web branches — otherwise it fouls all three skills.

> **(FDE Plan 5 — reconciliation with the code):** all three items of the map above — the `opsec_preflight` web2 branch,
> `prompt_injection_guard.py`, the `hunt_entry_gate.py` URL fix — were implemented in Plans 1/3, LONG before Plan 5.
> This table and the "TOP PRIORITY" paragraph are design prose written before the infrastructure shipped; at the time
> of Plan 5 everything listed is already in the code (see §17/§27).

---

# PART VI — A transfer from 0xSimao (the system as a whole, ALL skills incl. deephunt)

> The article "How I Use AI in Smart Contract Audits 2026" (a third-party auditor's write-up of a solo-auditor workflow with AI). It is
> not about automation but about AI as an assistant to a solo auditor. But 5 techniques are
> transferable and at the SYSTEM level (not only web2 — deephunt/dapphunt too). The author's reported metrics validate our approach.

## 40. What to adopt (5 techniques, system level)

1. 🔴 **Tool-output-LAST / anti-anchoring** — the author analyzes public skills/scanners **at the END** of
   an audit, so that their output does not anchor his own judgment ("analyze them at the end, so they don't bias
   my judgement"). We have model-first (T10) = the model BEFORE the code, but no analogue for the output of **scanners/public
   skills**: right now they feed hypothesis generation (T1 §2 in /hunt). The refinement: **our own divergence analysis
   (D-NN) first → tool/skill-scan output LATER, as a cross-check, not as a seed.** Strengthen
   `model_first_nudge` + the order of phases (scanners after model-first, not before). Applicable to all 3 skills.
2. 🔴 **Rerun-N-union for non-determinism** — the same non-deterministic LLM scan is run SEVERAL
   times, the findings are unioned (a generic scan finds 1/4 per run — it matches our halo2 lesson). Our
   Scout Fan-Out parallelizes BY subsystem, but does NOT exploit the non-determinism of ONE pass. Add
   a sub-step to `scout_fanout.md`: run the strongest partition/scan N times → union → dedup before the merge. Cheap,
   grows recall.
3. 🔴 **A PoC verification checklist** (in the T4 verifier + `submission_checklist.yaml`): "check addresses, check
   call path, check that the assertion would actually fail if you reverted the bug" + **mock-vs-real** (a PoC
   on a mock proves the behavior of the mock, "worth nothing"). Concrete checks in the T4 prompt — it meshes with our own
   rule on latent findings (assertion-fails-on-revert = a differential against the fix) and with the rule to lead the PoC with the strongest vector.
4. 🔴 **A severity economic-judgment checklist** — severity = an economic judgment (who loses / under what
   conditions / does the loss compound / can they be made whole), not "model reads shape and guesses the
   number" (wrong in both directions). A mandatory field in the T4 verifier prompt + `web_severity.py`
   (the single calculator, §35.5). It meshes with the rule of pushing the severity ceiling (raise to Crit →
   measure the real magnitude → an honest Medium).
5. 🔴 **A context-blindness gate** — most of the context is NOT in the repo: the client's docs, Discord/Telegram, who
   actually holds the deploy keys. An explicit recon pull of external context BEFORE finalizing the model/severity.
   Add an item to the recon phase (J-2/P-AM/P-SM): not only code/audits but off-repo context. For web2/
   dapphunt — API docs, status pages, the project's social channels, who the infra operator is.

## 41. Validation of our approach (0xSimao confirms)
- "53 of 265 findings that nobody found" + "a bug that only exists because these two contracts were
  composed in this specific way" → **directly validates divergence-first + cross-thread synthesis** (novel
  cross-contract composition = the non-commoditizable core, where un-dup lives).
- "A clean pass ≠ the evidence file is clean; run a tool twice → two different sets" → validates the **anti-"hardened"
  frame + the coverage gap-map + rerun-N (the §40.2 technique)**.
- "Do not ask the model how something works and accept the answer. Ever. Verify every claim against the
  code" → verbatim our rule against cheating on verification + the T4 mandate.
- "It does not make me faster, it reallocates hours to the deepest parts" → validates **depth-ceiling ≥5
  + single-target mastery** (depth > speed).
- Public skills commoditize known patterns → "free findings for those who do NOT run them" → validates
  our model-release re-audit window policy + taxonomy-as-crosscheck (not a generator).

## 42. The impact on the plan (Part VI — system level, outside web2 specifics)
- **The T4 verifier prompt** is supplemented: the PoC checklist (§40.3) + the severity-economic checklist (§40.4). It affects
  ALL skills — an edit of the shared T4 protocol, not web2-only.
- **model_first_nudge / the order of phases:** tool-output-last (§40.1) — divergence analysis before scanners.
- **`scout_fanout.md`:** the rerun-N-union sub-step (§40.2).
- **The recon phase (all skills):** the context-blindness pull (§40.5).
- This is NOT a web2 tier — these are system-wide edits of the methodology (mythos/T4/scout). Enter as a separate track during
  implementation, they apply to deephunt too.

---

# PART VII — Un-dup strategies: how to find what NOBODY found (the operator: "53 findings like 0xSimao")

> The core of the request: not "find a bug" but find an **un-dup** — what the crowd systematically misses. 0xSimao: 53
> of 265 are unique; his non-commoditizable core = "a bug that exists ONLY because these two
> contracts are composed exactly this way" + "where the crowd does not look". Below — 7 mechanisms for generating un-dup for
> web2/dapphunt (and the system). Each: the essence → why un-dup (where the crowd misses) → the mechanism/artifact.
> These are NOT new bug classes — they are **sources of a PLACE** that the crowd does not have (like D-NN/attention-gap).

## 43. Seven un-dup generators

### 43.1 🔴 Cross-Boundary Composition — the web analogue of "cross-contract composition" (the main one)
**The essence:** the crowd tests every trust boundary IN ISOLATION (BOLA on an endpoint, CORS on an origin, JWT on
auth, a signature on one flow). Un-dup lives at the **JOINT of two boundaries**: "service/layer A trusts what B
validated, and B does not validate THIS field".
**Why un-dup:** this is exactly the 0xSimao core, carried over to the web. A single boundary is checked by everyone; a composition
of two distant boundaries — almost nobody (a model of the whole system is needed, not of one endpoint).
**The mechanism:** after the model is built (TB-NN/AC-NN) — a **mandatory composition pass**: build a graph
`boundary A —trusts→ boundary B` (where the output of one = the input of another), for EVERY edge the question "who validates
at the joint?". The artifact `composition_map.md`; every edge without a validator = an un-dup `D-NN` candidate.
Examples: a gateway filters by one criterion, the backend by another · an auth service puts tenant_id in a JWT,
the data service trusts it without rechecking · the frontend trusts the indexer → the indexer trusts RPC → RPC is
substitutable (the dapphunt cross-layer trust chain). **This is the web instance of cross-thread synthesis** (§ depth-engine).
Embed: a new mandatory step after P-SM/P-AM, before the depth-drive.

> **(FDE Plan 6 — reconciliation with the code):** implemented as `scripts/web2/composition_map.py` (Task 2) —
> `build_composition_graph`/`run_composition_map`, `validated=(Status==ENFORCED)` (anti-dup via
> `parse_divergence_invariants`) → `composition_map.md`. The gate `active_composition_pass_skipped` holds
> the exit for a mature model with `>= COMPOSITION_MIN_BOUNDARIES` boundaries — the design's "≥N boundaries" did not give
> an exact N, the code fixed **`N=3` as a fallback** (explicitly marked as a retune point in the code and in carry→Plan 7).
> The only one of the 17 generators §43-49 to become a separate executable producer script (R1) — all
> the others remained seed lines/prose (see the flag after §49 below).

### 43.2 🔴 Commodity-Subtraction — un-dup = what is left after the scanners
**The essence:** 0xSimao — public skills/scanners commoditize known patterns ("free findings for those
who do NOT run them"), but un-dup is NOT there. The inversion: **everything the commodity layer finds (nuclei/Autorize/public
skills) = what the crowd will find too = NOT our un-dup**.
**Why un-dup:** it outlines "where the crowd will look" — and we dig in the COMPLEMENT. It operationalizes
tool-output-last (§40.1) + attention-gap: a scanner = a map of a crowded place.
**The mechanism:** recon → run the commodity scanners → mark their findings `[COMMODITY]` (submit fast,
a race window, but do NOT count as un-dup) → **the un-dup search = where the model says "should be checked" and the
commodity layer did NOT cover**. `crowd-heat` is inverted mechanically: covered by a scanner = `hot`, uncovered +
named by the model = `cold` = the front of the queue. The artifact: `commodity_coverage.json` (what the scanners actually
touched) → subtracted from the `AC-NN`/`TB-NN` list.

### 43.3 🔴 Model-vs-Docs-vs-Runtime — a triple divergence (not only model-vs-code)
**The essence:** for web the most powerful source is **three models diverging**: the docs/OpenAPI contract (what is promised) ×
the code/bundle (what is written) × the observed runtime (what is real). The crowd compares at most TWO.
**Why un-dup:** "the docs say the endpoint requires admin → the runtime returns 200 to a user" is seen only by someone who
diffs the docs against live behavior. Especially for web2 (OpenAPI often lies about the implementation) and dapphunt
(the whitepaper promises, the contract/frontend does otherwise).
**The mechanism:** build a model from the docs (`pred:` from the contract) separately, from the runtime (browser-first §33)
separately → diff. Three sources of `pred:` instead of one → a divergence of any pair = a `D-NN`. It strengthens the beat
`pred: vs fact` (§3.4.3): now `pred` from the docs, the fact from the runtime — the most un-dup quadrant.

### 43.4 🔴 UI-Forbidden-but-API-Allowed — un-dup via what the UI HIDES
**The essence:** the crowd tests what the UI SHOWS (visible buttons/fields). Un-dup is in what the UI **hides**:
an action that the interface does not let you do (no button / greyed out / behind a paywall), but the API allows.
**Why un-dup:** a systematic blind spot — "the UI does not allow it → so it is impossible" = a false assumption of the crowd. This is the
operationalization of "an invariant that a developer considers self-evident but does not enforce" (the 0xSimao mental
model) for the web.
**The mechanism:** a browser-first pass → write out what the UI does **NOT allow** (hidden/disabled actions, tier-gated
features, hidden form fields) → for each, check whether the API allows it directly. The artifact `ui_forbidden_map.md`.
A direct generator of BL-NN + BFLA (tier-escalation, hidden-mutation). dapphunt: "the UI does not let you sign on chainId
X, while the API/wallet flow does".

### 43.5 Semantic Field-Diff as an un-dup engine (we objectively surpass the commodity)
**The essence:** IDORTester/Autorize/nuclei diff status+length. The crowd with these tools catches only crude
BOLA (403→200). Un-dup: a **field-level semantic diff** — B gets a 200 with the same fields, but ONE field
(`internal_notes`/`ssn_last4`/`role`/`margin`) must not be visible.
**Why un-dup:** a status diff misses this (200==200, similar length) — and that is exactly where the
leaks missed by the crowd sit. We objectively surpass a commodity tool at the level of mechanism, not luck.
**The mechanism:** Differential Observation (§35.1) diffs JSON AT THE FIELD LEVEL + classifies the sensitivity
of a field (PII/financial/authz-relevant) → a divergence in a sensitive field = a `D-NN`, even with 200==200. This is
raising §32.1 from "an IDORTester improvement" into an **explicit un-dup strategy**.

> **(FDE Plan 6 — reconciliation with the code):** the field-level semantic diff is already implemented in `differential_observation.py`
> (Plans 3/4/5). Task 10 (carry R7, BS-05) found and closed a neighboring correctness gap in THIS same mechanism:
> `differential`/`semantic_diff` compared the EQUALITY of responses to a baseline, not OWNERSHIP — a full-leak BOLA
> (B gets ALL fields of A's object, but the response is identical to A's baseline) yielded false "0 divergences". The fix
> `ownership_diff()`/`_OWNER_MARKER_KEYS` (an opt-in branch of `authz_diff.py`, role `user-B-own`) — compares
> `user-B-for-A` against `user-B-for-own`, an owner-stamped field of someone else's object = a leak regardless of
> equality; no owner marker → `INCONCLUSIVE`, not an FP. `blind_spots.md` BS-05: closed.

### 43.6 Composition-Escalation on findings — chaining distant Low→Critical
**The essence:** many findings are chains. After EVERY Low/Medium — a mandatory question: "if this
defect is true, which trust boundary does it break, and what trusts this boundary NEXT?".
**Why un-dup:** the crowd submits a Low in isolation; un-dup is in a chain where an info-leak (Low) → reveals an
internal endpoint → without authz (BOLA) → account takeover (Critical). Cross-thread at the level of FINDINGS, not hypotheses.
**The mechanism:** formalize in T3/depth-drive: every finding = a building block in `## Building Blocks`,
run "who trusts what I broke" (the inverse composition map of §43.1). It meshes with the
chained-hypothesis hunt rule + push-severity-ceiling.

### 43.7 Legacy-but-Alive — attention-gap by TIME
**The essence:** the crowd tests the CURRENT version (what is in the current docs/bundle). Un-dup is in the old-but-alive:
endpoints from wayback/an old bundle that are not in the current docs but that the server still serves; API v1 after
the v2 release; deprecated-but-deployed.
**Why un-dup:** change=risk (post-audit drift) + "nobody tests what is not documented
now". Deployed≠HEAD at the web level.
**The mechanism:** diff OpenAPI v1↔v2, wayback endpoints × httpx-alive (alive? not in the current docs?), an old bundle
from wayback → debug/internal routes. Formalize as an un-dup recon step (not just "wayback for completeness").
It feeds `AC-NN` as a separate source of `pred:` (the old contract vs the new enforcement).

## 44. How this changes the loop (integrating un-dup into SELECT)
The un-dup generators are embedded into the divergence-first order, BEFORE ordinary SELECT:
1. The model (TB-NN/AC-NN) is built (§3/§16) — the base `D-NN`.
2. **The un-dup superstructure (Part VII):** the composition pass (§43.1) + commodity-subtraction (§43.2) +
   docs/runtime-diff (§43.3) + ui-forbidden (§43.4) → an **enriched pool of `D-NN` with an un-dup mark**.
3. SELECT prioritizes **un-dup-marked `D-NN`** above ordinary ones (they yield the 53-findings class, not duplicates).
4. The semantic field-diff (§43.5) — how to diff in the harness. Composition-escalation (§43.6) — on every finding.
5. Legacy-but-alive (§43.7) — a parallel source in recon.

**A rank addition:** add a multiplier `un-dup-origin` to the `D-NN` formula (§3.5) (composition-seam /
docs-runtime-gap / ui-hidden / commodity-cold = ×high; single-boundary-obvious = ×low). This mechanically
moves un-dup to the front of the queue — an operationalization of "the place is pointed to by an artifact" for NON-duplicates.

> **(FDE Plan 6 — reconciliation with the code):** `undup_origin` is implemented as a **column** in the D-NN table (`##
> Divergences`), not a separate prose field — and lives in `system_model_web_template.md`/
> `system_model_template.md` (**NOT in the ledger**, contrary to how §44/§48.2 read at first glance;
> the pattern of `system_model.md` = the keeper of D-NN was already established by Plans 4/5). The column is inserted BEFORE
> `Resolution` (a positional hazard: `Resolution` must remain the last cell for the existing
> `_cells(line)[-1]` extractors) → web 12→13 columns, contract 11→12. The emitters `to_dnn_row()`
> (`differential_observation.py`) and the `authz_diff.py` renumber path were updated in sync (Task 3) — without
> this, producer rows shorter than the template break the positional parse. The gate `active_undup_origin_missing`.

## 45. An honest caveat (what un-dup does NOT guarantee)
The un-dup generators grow the PROBABILITY of a unique finding, they do not guarantee it. They are more expensive (the composition pass +
the triple model + browser-first = hours). The discipline: the un-dup superstructure is launched on a **worthy target**
(single-target mastery), not on every quick scan. For a quick web2
the commodity layer (§43.2) is submitted for the race, the un-dup dig — only if the target is worth it. Measure by
calibration: the share of un-dup findings from composition/docs-runtime/ui-forbidden — if a generator is silent for N hunts,
it goes into `blind_spots.md`, not "the targets are clean".

---

# PART VIII — The second wave of un-dup generators (the operator: "new ideas are still needed")

> §43 covered: composition · commodity-subtraction · docs-runtime · ui-hidden · semantic-diff · chain ·
> legacy. Here — 10 MORE, along three axes: **A. where to dig (PLACE)** · **B. how to break (the axis of checking)** ·
> **C. system amplifiers of un-dup**. All are sources of uniqueness, not new classes.

## 46. Axis A — generators of a PLACE (new sources that the crowd does not have)

### 46.1 🔴 Assumption-Mining — "should/only/must, but not enforced" (the Sherlock core, cheap+ROI)
**The essence:** grep the docs / comments / **UI texts / error messages** for modal words: "only admins
can", "you must own", "cannot be reversed", "verified users only", "per account", "once". Every promise
= a declared invariant → check whether it is enforced on the API/on all paths.
**Why un-dup:** the crowd reads CODE; un-dup is in the gap between what the system SAYS and what it DOES. "The dog
that did not bark" for the web. An error message often reveals the assumed
check ("You don't have permission to edit this order" → the check EXISTS → but on PUT/PATCH/batch too?).
**The mechanism:** an `assumption_miner` — a grep of modal constructions over docs/UI/error strings → each → a candidate
`AC-NN`/`TB-NN`/`BL-NN` with `pred:ENFORCED`. It feeds the model with cheap but precise invariants. Embed into P-SM/P-AM.

### 46.2 🔴 Negative-Space — "what I did NOT model" (a meta-generator of attention-gap)
**The essence:** after the model is built — an explicit question: **endpoints without a class? components without a TB-NN? features from the
changelog that are not in the docs? a periphery that nobody modeled?**
**Why un-dup:** un-dup is most often where there is NO model at all — a feature so new/peripheral/under-
documented that neither the crowd nor an audit examined it (the 0xSimao context-blindness). Un-modeled = max
attention-gap.
**The mechanism:** a diff of "the whole observed surface (the recon map)" minus "covered by the model" = an un-modeled list →
each = a mandatory hypothesis (a hunt cannot be closed with a non-empty un-modeled). A proactive `blind_spots.md`.

### 46.3 Third-Party Trust-Seam — cross-org un-dup (the bug is not in the target but in what it trusts)
**The essence:** the crowd tests the target itself. Un-dup is in the external trusted dependencies: a CDN, a tokenlist, an indexer,
an auth-provider config, an npm dep, a webhook source, an OAuth provider, RPC.
**Why un-dup:** "the target trusts X, X can be substituted/influenced/taken over" is rarely checked, because
you have to step outside the target's perimeter. Cross-org (a dapphunt tokenlist-CDN/indexer takeover is a special case).
**The mechanism:** map ALL external trusted dependencies (from CSP connect-src / package.json / config)
→ for each "what if its output is hostile?" → a trust-seam `D-NN`. The data-source-trust axis (dapphunt) +
supply chain (web2) extended to the full dependency graph.

## 47. Axis B — axes of checking (how to break in a way the crowd does not try)

### 47.1 🔴 Interrupted-Path — breaking a multi-step flow (happy-path bias)
**The essence:** the crowd and the developer test the happy path. Un-dup is in the error/rollback/interrupted paths: **what if
step 3 of 5 failed?** is authz rolled back? is a partial state left? TOCTOU on error handling.
**Why un-dup:** this is the `## Missing Negatives` axis (test-inversion, ALREADY in deephunt!) — carry it over to
web/dapphunt. dapphunt: break between `approve` and `swap`; web2: kill the session between `pay` and `fulfill`.
**The mechanism:** for every multi-step BL-NN — deliberately fail/break an intermediate step (browser-
first: close the tab, cancel the tx, a timeout), observe the state. An interrupted-negative for every flow.

### 47.2 Cross-Process Reordering — interleaving TWO flows (not a race of one)
**The essence:** a race on ONE action = a commodity (turbo-intruder). Un-dup is **cross-process reordering**:
interleave two business processes (checkout A × refund B → double value), call the steps in an IMPOSSIBLE order.
**Why un-dup:** the crowd tests a race on one endpoint; interleaving distant processes — almost nobody (a model of both is needed).
This is composition (§43.1) on the temporal axis.
**The mechanism:** from the state machine of BL-NN — look for transitions between DIFFERENT processes that the code does not explicitly
forbid. dapphunt: a multi-tab / multi-wallet interleave (our long-standing multi-tab session race class).

### 47.3 Client-Trust — "the server trusts client-side math"
**The essence:** write out everything that comes from the client and is accepted by the server as a TRUSTED fact (not user input
for validation, but client-computed-and-accepted): a price/discount computed on the client, a client-side nonce, a timestamp
from the client, "signed by our own frontend".
**Why un-dup:** the crowd tests explicit authz fields; "the client always computes honestly" is an invisible assumption.
**The mechanism:** browser-first interception of outgoing requests → for each field the question "does the server RECOMPUTE
or trust?". The dapphunt parallel: displayed≠signed (§3.2) — the same root (trusting a client value).

### 47.4 Multi-Identity — a differential across the CONTEXTS of one user
**The essence:** the differential is NOT between different users (BOLA) but between the **contexts of one**: two tabs, web+mobile,
two sessions, old+new token. Is a stale token valid after logout? did a role change fail to reach an active session?
does a mobile session bypass web MFA?
**Why un-dup:** "the same user" seems safe — the crowd tests a single session. This is §35.1 Differential
Observation with `ctx = the contexts of one user`.
**The mechanism:** the matrix run (§17) adds a "context" axis, not only "role". The un-dup rows: same-user-diff-context.

### 47.5 Quantity-Edge for web2 (0/neg/max/fractional in business logic)
**The essence:** the crowd tests normal values. Un-dup: `quantity=-1` (a refund > what was bought), `price=0.0001`
(rounding in your favor), a 0-amount (state without cost), a cart-sum overflow.
**Why un-dup:** web2 business logic is rarely tested for numeric edges, as contracts are (there it is Cat 1).
A carry-over of the math/precision axis of deephunt to web2/dapphunt (dust, rounding in a swap).
**The mechanism:** for every numeric field of BL-NN — run 0/neg/max/fractional through the harness.

## 48. Axis C — system amplifiers of un-dup

### 48.1 🔴 Un-dup Pattern Amplifier — a unique finding → a class across the whole family
**The essence:** 0xSimao's "pattern memory = find capacity". A confirmed un-dup on target A → an immediate pattern
abstraction → a grep across ALL past/related targets.
**Why it amplifies un-dup:** if a finding is un-dup, the crowd has not closed it ANYWHERE → the maximum transfer value
(unlike a commodity, which is already fixed everywhere). An un-dup-specific sharpening of our protocol-family bug-transfer rule.
**The mechanism:** every confirmed un-dup → an entry in `undup_pattern_library.md` (a pattern + fingerprint + where
to look) → an auto-grep across the family/past sessions. It closes the loop: 1 un-dup → N findings.

> **(FDE Plan 6 — reconciliation with the code):** the `undup_pattern_library.md` artifact file was NOT created — Task 8 (R1
> scope discipline) seeds it as a note line in `blind_spots.md` (a specialization of the existing
> `TRANSFER-CANDIDATE` / the protocol-family bug-transfer rule, explicitly marked as NOT a duplicate), not as
> a separate code/file mechanism. The auto-grep across the family/past sessions is not built either (it remained prose).

### 48.2 🔴 The adversarial "why has this not been found yet?" gate (an un-dup calibrator, anti-self-deception)
**The essence:** before submitting an un-dup finding — a mandatory question: **"why did 100 hunters before me
miss this?"**. No clear answer → it is more likely NOT un-dup (already reported / intended / a precondition) — I am
missing something. A clear answer ("a model of the whole system + a docs-diff + browser-first was needed") → confidence.
**Why it amplifies:** it cuts off a false un-dup (the self-deception "I found something unique" when it is in fact a duplicate/intended) —
it supplements T4 with a separate axis. Plus the answer itself = the formulation of the un-dup origin for the report (a strong dedup angle).
**The mechanism:** a field in the T4 verifier: `undup_origin: <which source gave this that the crowd did not have>`. Empty
/ weak → downgrade to "likely dup", re-audit. This discipline turns the intuition "unique" into a verifiable artifact.

## 49. Integration of the second wave
- **The place (Axis A)** → feeds the model (P-SM/P-AM): assumption-miner + negative-space + third-party-seam =
  additional sources of `pred:` invariants, BEFORE the code. Assumption-mining is the cheapest, in Tier 1.
- **The axes of checking (Axis B)** → extend `## Missing Negatives`/the harness: interrupted-path · cross-process ·
  client-trust · multi-identity · quantity-edge. This is the how-to-diff for Differential Observation (§35.1).
- **The amplifiers (Axis C)** → the un-dup pattern library + the adversarial gate in T4. System level (all skills).
- **Rank:** the `undup_origin` multiplier (§44) accounts for the second wave too — a finding from assumption-gap/negative-
  space/interrupted-path/third-party-seam gets un-dup priority in SELECT.
- **Honestly:** this is ~17 generators in total (Part VII+VIII) — NOT all on every hunt. On a worthy target
  a set is run by profile; calibration cuts off the silent ones. The point is not a checklist but a **pool of sources of a
  PLACE that the crowd does not have**: the more independent sources intersect at one point, the surer the un-dup.

> **(FDE Plan 6 — reconciliation with the code, a consolidated flag for Part VII+VIII):** §50/§54 (below) already
> formulate the principle "un-dup is an enforced layer, not a chapter of the methodology" — Tasks 1-8 implemented this
> literally (R1 "scope discipline is the core of the plan", NOT 17 scanner scripts): of the 17 generators §43-49
> the code (`composition_map.py` §43.1, the ownership baseline §43.5) got exactly **two** — the remaining 15
> (commodity-subtraction/docs-runtime-diff/ui-forbidden/legacy-alive/assumption-mining/negative-space/
> third-party-seam/interrupted-path/cross-process/client-trust/multi-identity/quantity-edge/severity-undup/
> replay-nonfinancial/entitlement-drift) landed as **(a) a ledger seed** — a line `RUN`/`N/A-reason`/`→D-NN` in
> `## Un-Dup Sweep` (Task 1, seeded by the §51 matrix) and/or **(b) a methodology seed** — an un-dup-affinity
> column in `hypothesis_taxonomy.md` + an entry in `blind_spots.md` (Task 8). Composition-escalation
> (§43.6) and the §57 backlog remained prose/T3 practice, not separate code. Zero new scanner scripts
> was confirmed by the Task 8 report ("R1 anti-scope observed — 0 scanner scripts").

---

# PART IX — Integration without dust + distribution across skills (the operator: "so that it works, is applied autonomously")

> The risk: 17 un-dup generators + components = **dead weight if it is prose** (in an autonomous session I
> will ignore them, as `MODEL:N/A` disarms — the lesson: a prose mandate is empirically insufficient). This part:
> (A) how each idea becomes an **enforced artifact** that the loop forces by itself; (B) the distribution across the 3
> skills (a different essence); (C) strengthening the existing; (D) new.

## 50. 🔴 Un-dup enforcement — how NOT to gather dust (the core of this part)

**The principle: every un-dup generator = either a ledger section + a gate, or a D-NN field, or a rank multiplier. Not
a single "remember to apply".** Three mechanisms:

1. **`## Un-Dup Sweep` — a mandatory ledger section** (in `hypotheses_web.md` + the contract template). A table
   "generator → status (`RUN` / `N/A — reason` / `→ D-NN`)", like `## Scout Fan-Out`. Seeded by the target's
   profile (§51) — applicable generators, the rest auto-`N/A`. The gate **`active_undup_sweep_incomplete`**
   holds the exit if an applicable generator is not marked (not `RUN` / not a justified `N/A`). So the 17 ideas are
   not memory but a checklist that the Stop hook forces in autonomous mode.
2. **`undup_origin:` — a mandatory field of every `D-NN` and finding** (§48.2). "Which source gave this, which
   the crowd did not have". Empty/weak → the gate `active_undup_origin_missing` → an adversarial re-audit (likely-dup).
   Enforcement of §48.2 through a field, not prose.
3. **The rank multiplier `undup_origin` is already in the formula** (§44) — the ranker ITSELF moves un-dup-marked `D-NN` to the front of
   SELECT. Not "remember that un-dup is more important" — a machine priority.

Plus **`composition_map.md` + `active_composition_pass_skipped`** (empty with a model of ≥N boundaries = hold) —
§43.1 will not gather dust. All the new gates — with a **replay test BEFORE the gate** (a hook must prove it fires),
proving that it fires on an untouched template (otherwise the gate went blind, as the nudges stayed silent for months).

**This is the answer to "applied autonomously":** un-dup is built into the same Stop-hook engine (§38) that holds
the deephunt loop. A generator is silent → the gate holds the turn → I must run it or justify N/A. No prose.

> **(FDE Plan 6 — reconciliation with the code):** the real name of the **template** = `hypotheses_web_template.md`, but the live
> artifact of a hunt is `hypotheses.md`, produced from `hypotheses_web_template.md` (web) /
> `hypotheses_template.md` (contract) — the same naming pattern already fixed for Plans 4/5
> (there is no separate `hypotheses_web.md` in the real session tree). All three mechanisms are implemented
> literally: the Un-Dup Sweep (Task 1), `undup_origin` (Task 3), the rank multiplier (Task 3, the formula prose) +
> `composition_map.md`/`active_composition_pass_skipped` (Task 2, "≥N boundaries" = a `N=3` fallback, see the
> flag after §43.1).

## 51. 🔴 Distribution across the 3 skills (a different essence — where how, where not needed)

Un-dup/system mechanisms apply to ALL skills, but differently. The matrix (✅ yes · ⚠️ adapted ·
❌ not applicable · 🔁 **reverse export: a web idea strengthens deephunt, where it is not explicit**):

| Mechanism | deephunt (contract) | dapphunt (web3-front) | hunt (web2) | The difference in essence |
|---|---|---|---|---|
| Cross-Boundary Composition (43.1) | ✅ = cross-contract/cross-thread (already) | ✅ cross-layer trust chain | ✅ cross-service seam | the boundaries differ, the essence is the same |
| Commodity-Subtraction (43.2) | 🔁 subtract public audit skills — **not explicit** | ✅ nuclei/dapp scanners | ✅ nuclei/Autorize | deephunt receives this from web |
| Model-vs-Docs-vs-Runtime (43.3) | ⚠️ the 3rd model = **live on-chain state** (T12 exists) | ✅ whitepaper×bundle×runtime | ✅ OpenAPI×code×runtime | "runtime" = different things |
| UI-Forbidden-but-API (43.4) | ❌ no UI | ✅ | ✅ | frontend-only |
| Semantic Field-Diff (43.5) | ⚠️ storage/event-diff | ✅ JSON | ✅ JSON | "fields" = different things |
| Composition-Escalation (43.6) | ✅ (chaining already) | ✅ | ✅ | universal |
| Legacy-but-Alive (43.7) | ✅ deployed≠HEAD, an old impl behind a proxy | ✅ an old bundle from wayback | ✅ an old API version | "legacy" = different things |
| Assumption-Mining (46.1) | 🔁 NatSpec "should/must" as un-dup — **strengthen comment_miner** | ✅ UI/docs | ✅ error-msg/docs | the sources differ |
| Negative-Space (46.2) | 🔁 un-modeled functions/contracts — **not explicit** | ✅ | ✅ | universal, exported to deephunt |
| Third-Party-Seam (46.3) | ✅ oracle/bridge/dep (composability) | ✅ tokenlist/indexer/RPC | ✅ CDN/webhook/OAuth | the dependencies differ |
| Interrupted-Path (47.1) | ✅ = Missing Negatives (already) | ✅ interrupt approve/swap | ✅ interrupt pay/fulfill | deephunt is the origin |
| Cross-Process Reorder (47.2) | ✅ the order-dependent axis | ✅ multi-tab/wallet | ✅ interleave flows | universal |
| Client-Trust (47.3) | ❌ everything is on-chain | ✅ displayed≠signed | ✅ client-computed | a contract has no client |
| Multi-Identity (47.4) | ❌ no sessions | ⚠️ multi-wallet | ✅ session/token/device | web2-primary |
| Quantity-Edge (47.5) | ✅ = Cat 1 Math (already) | 🔁 dust/rounding | 🔁 **new for web2** | deephunt is the origin → export to web |
| browser-first (§33) | ❌ (a contract is static) | ✅ mandatory | ✅ mandatory | web profiles only |
| Differential Observation (35.1) | ⚠️ state/storage-diff | ✅ | ✅ | "context" = different things |
| Un-dup Amplifier (48.1) | ✅ | ✅ | ✅ | the system |
| Adversarial why-not-found (48.2) | 🔁 a T4 field — **strengthen** | ✅ | ✅ | the system, T4 of all |
| Prompt-injection guard (35.4) | ⚠️ reads repo/audit PDFs | ✅ a live dApp | ✅ live pages | all read external content |

**Bidirectionality (the key point: "needed by another skill"):** I formulated un-dup for web, but
**6 mechanisms (🔁) strengthen deephunt, where they are NOT explicit** — commodity-subtraction, assumption-mining-as-undup,
negative-space, the adversarial gate, quantity-edge-as-a-conscious-axis, model-vs-live-runtime. An exchange in both
directions: deephunt gave web (model-first/depth/library/Missing-Negatives), web returns to deephunt (the subtraction of
commodity, negative-space, the adversarial-undup gate). **This is NOT a web2 plan — it is an upgrade of all three skills through
the shared Shared Core.**

> **(FDE Plan 6 — reconciliation with the code):** the matrix was verified literally (Task 12, §51 verify) — the contract-seed
> set is confirmed: composition/commodity-subtract/negative-space/assumption-mining(NatSpec)/
> quantity-edge(Cat1)/legacy(deployed≠HEAD)/third-party(oracle) are applicable, **interrupted-path** was
> mistakenly marked by Task 1 as `N/A — web-only` — corrected to applicable (deephunt is the origin, the same
> shape as quantity-edge, row 47.1 of the table above confirms `✅ = Missing Negatives`) →
> the contract seed is now **8 applicable + 7 N/A** (was 7+8). Implemented as ONE `## Un-Dup
> Sweep` section with profile-based seed logic (R10), NOT 3 copies of the section. The reverse export of the 6 mechanisms (🔁) — in
> `CLAUDE.md` §1 (Task 12, the divergence-first block, the tag `UN-DUP REVERSE-EXPORT`).

## 52. Strengthening the EXISTING (not only the new — at the operator's request)

- **T4 verifier → multi-axis** (all skills): add `undup_origin` (§48.2) + the PoC checklist (§40.3) +
  severity-economic (§40.4) + Marker/Body-Diff/Statistical (§26.4). One verifier, a set of axes by profile.
- **Scout Fan-Out → un-dup-aware:** the partitions include un-dup axes (one scout = commodity-subtraction: runs
  scanners, marks `hot`; another = negative-space: looks for the un-modeled), not only subsystems. + rerun-N-union
  (§40.2) + a per-worker budget/internal-wrapper (§27). A strengthening of `scout_fanout.md`/`.workflow.js`.
- **crowd-heat → machine:** right now from the audit map (T14). Add a **commodity-scanner map** (§43.2): what a
  scanner touched = `hot` automatically. `crowd_heat.json` joins both maps. A strengthening of T14.
- **wave_delta → legacy-aware:** not only a diff of HEAD, but old-versions-still-alive (§43.7). A strengthening of
  `wave_delta.py`.
- **calibration_log → un-dup tracking:** the share of unique findings per generator (which source yields un-dup) →
  a silent generator into `blind_spots.md`, a productive one — a boost in the seed. It closes self-improvement on un-dup.
- **hypothesis_taxonomy → an un-dup-affinity column:** for each class — which un-dup generator more often
  reveals it (Cat×generator), steering the sweep. A strengthening of the taxonomy.

> **(FDE Plan 6 — reconciliation with the code, Task 8):** all five strengthenings are implemented light-touch, as ordered
> (not rewritten from scratch, R12). **NB on `crowd_heat.json`:** the design prose above reads as a persisted file
> on disk — in fact `crowd_heat` has been, since T14 (`audit_coverage_invert.py`), a key of the `--json` output
> `{path: hot|cold}`, not a file; Task 8 joins the commodity-scanner map at the level of THIS
> output contract (`--commodity-hits`), not via a nonexistent file. `wave_delta.py` got a
> legacy-aware signal (`legacy_alive_check`); the `calibration_log` un-dup tracking landed in
> `depth_engine_plan.md` §10 item 6 (not in the calibration script directly — a methodology seed).

## 53. New (beyond the 17, genuinely non-overlapping)

- **53.1 Severity-un-dup (not existence but magnitude):** the crowd reported a finding as a Low in isolation; I
  show a Critical **chain** of the same finding (composition-escalation §43.6) → "not a duplicate but an escalation of
  severity". Un-dup by MAGNITUDE, even if the existence is known. A field in T4: `severity_undup: <in isolation
  Low, in composition Crit>`. It meshes with the push-severity-ceiling rule.
- **53.2 Replay on NON-financial operations:** the crowd tests replay on payments. Un-dup is replay on
  config-change / role-grant / email-verify / invite-accept / vote (where the developer did not think about repetition).
  Web2 + dapphunt (governance replay). An axis for Interrupted/Idempotency in the harness.
- **53.3 Entitlement-drift (a time-of-check gap):** a feature is checked at ENTRY, not at use;
  the subscription/role expired, but the active session/token works. More specific than multi-identity. Web2-primary,
  dapphunt (allowlist-removed-but-session-alive). An axis `check-once-use-forever` in BL-NN/AC-NN.

## 54. The integration principle (in one line)
**Un-dup is not a chapter of the methodology but an enforced layer of the loop:** the `## Un-Dup Sweep` section + the `undup_origin` field +
the rank multiplier + the composition_map gate → the same Stop-hook engine that holds deephunt forces un-dup
autonomously. A generator is either run (RUN → a lead) or justifiably N/A — the hook does not allow a third option (silently skipping). So the 17 generators work by themselves
and do not gather dust. The §51 distribution — which generator is seeded in which skill
profile; the §52 calibration — which one actually yields un-dup, which goes to blind_spots. **This brings
divergence-first to its goal: not "find a bug" but systematically find what the crowd did not find.**

---

# PART X — The third wave: asymmetries of tool, layer, human (the operator: "include everything")

> 8 ideas along the axes of asymmetry that the crowd does not have: **model · sequence · skill seam · human ·
> target uniqueness · others' patches · acknowledged seeds · economics.** Each — with an integration (enforcement +
> skill), so that it works autonomously and does not gather dust.

## 55. The strong ones (into the enforced layer)

### 55.1 🔴 Model-Diversity — different LLMs = different blind spots (an un-dup source)
**The essence:** rerun-N (§40.2) exploits the non-determinism of ONE model. The new idea: **different MODELS have different
systematic blind zones** — run one hypothesis/scout phase on Opus + Sonnet (+ others), diff the outputs.
**Why un-dup:** different model generations demonstrably differ — a newer model can find what an older one kept missing
(see the model-release re-audit window policy). The crowd (and we) run one model
→ its blind spot = a mass miss. The intersection of models reveals what a single one does not see.
**Integration (all skills):** Scout Fan-Out (§52) — run the strongest partition on 2+ models (`opts.model` in
`scout_fanout.workflow.js` already exists), their **symmetric difference** (what one found and the other did not) =
an un-dup candidate of the highest priority. Enforcement: a field `models_run:` in `## Scout Fan-Out`; on a worthy
target <2 models on a key partition = a gate nudge. Cheap — the infra already exists.

> **(FDE Plan 6 — reconciliation with the code):** the override field in the real code is **`A.model`** (`scout_fanout.
> workflow.js:35`), NOT `opts.model` as written above (the same inaccuracy was already caught by plan §3 R3 before
> implementation). Task 5 implemented: rerun-N-union, model-diversity `models_run:` in `## Scout Fan-Out`,
> symmetric-diff→`undup_priority`, a per-worker budget+`<orchestrator_internal>`, `run_dual_approach_contest`
> in the HYBRID fan-out (`divergence_fanout.workflow.js`); the CLASSIC fan-out keeps `A.model` unchanged, HYBRID
> uses `A.enforce_model`/`A.synth_model` (pre-existing fields, checked by diff).

### 55.2 🔴 Compositional Sequence Fuzzing — a real T11 for web
**The essence:** the web harness right now = an authz matrix (one endpoint / one action at a time). The real un-dup (like
our own confirmed Highs) sits in a **SEQUENCE** that cannot be found by reading. The web analogue of T11:
the harness automatically combines API calls / UI actions into sequences (not "one request" but "a chain of 3-5"),
looking for a violation of a `BL-NN`/`AC-NN` invariant.
**Why un-dup:** the crowd fuzzes single requests (nuclei/sqlmap) and a single race (turbo-intruder); CROSS-
request sequences — almost nobody (a state model is needed). This is a direct T11 harness-as-generator,
which the web profiles lack (§10 "we do not carry over Echidna" — but the LOGIC of T11 does carry over: a property from the model →
the fuzzer looks for a call sequence).
**Integration (hunt web2 + dapphunt):** a new `sequence_harness` — the input is `BL-NN`/`AC-NN` from the model (anti-
tautology: the property from the invariant, not from the observed behavior), it generates permutations/repeats/interleavings
of calls through a browser-first session → a violation = a `D-NN` of machine origin. This is the web `t11_applicable`:
STATEFUL (a multi-step flow exists) + MOVEMENT (an order-dependent `BL-NN`) → APPLICABLE. Enforcement: `T11-WEB-
VERDICT:` in the ledger (like the contract T11-VERDICT §J2). deephunt: not needed (Echidna/Trident are already there).

### 55.3 🔴 Cross-Skill Seam — un-dup in the seam dapphunt→hunt→deephunt
**The essence:** a target is often = a frontend + a web2 API + a contract. Our skills are SEPARATED → they themselves create a blind spot at the
joints. Un-dup: a bug visible only through all three layers (the frontend shows X → the API returns Y → the contract
executes Z — a desync across the layers, each layer separately "clean").
**Why un-dup:** this is Cross-Boundary Composition (§43.1) raised to the level of SKILLS — the most distant
cross-thread. The crowd and the tools are split by layer (frontend hunters ≠ contract auditors) → NOBODY
looks at the seam. Exactly the 0xSimao cross-contract, but across technology layers.
**Integration (a meta-skill over all three):** when a target is multi-layer — after the three profile models
(surface_model + access_model + system_model) build **`seam_map.md`**: trace ONE value
(an amount/recipient/right/price) through frontend→API→contract, find the layer where the invariant is lost. Enforcement:
if `dapp_detection` + a verified contract both → the ledger carries `SEAM: pending`, the gate holds until `seam_map`
or a justified N/A. This is the only place where the three skills work together on one D-NN.

> **(FDE Plan 6 — reconciliation with the code, a consolidated flag §55.2+55.3):** BOTH — `sequence_harness`
> (a real web T11) and the `seam_map.md`/`SEAM:` gate — were **deliberately NOT implemented in Plan 6** (R2,
> plan §0 an explicit decision): big+cross-skill+low-frequency, the un-dup core does not depend on them. Deferred to
> **Plan 6.5 / merging into Plan 7**, which gives Part XI (the next plan) a direct dependency on them besides
> §60-65. Seeded ONLY as a note line in `blind_spots.md` (Task 8) with the enforcement mechanics
> (the `T11-WEB-VERDICT:`/`SEAM: pending` gate), so that the follow-up plan does not reinvent the design —
> the harness/gate code is not built. The same deferred-by-dependency technique as `active_clone_diff_skipped`
> (deferred from Plan 2 to Plan 4).

### 55.4 🔴 Human-as-Real-World-Oracle (the operator = a Watson, hands in the real world)
**The essence:** some un-dup requires a real human: a real card for a payment flow, KYC state, SMS/
phone, regional/physical context, an action that an AI agent cannot perform. Systematize
**"what I cannot verify myself → delegate to the operator"**.
**Why un-dup:** a crowd of AI agents will hit the same wall (cannot pass KYC/payment) → the surface behind that
wall is systematically under-tested. Human capability = an asymmetry that a pure auto-scan lacks.
A direct operationalization of the project principle "the operator = a Watson, hands in the real world".
**Integration (all skills):** a section `## Human-Gated Surface` in the ledger — what requires a real actor
(payment/KYC/SMS/2FA device/physical access). NOT a park (the loop does not end) — but an **explicit one-line ask to the operator**
("a real card is needed on the checkout flow — can you do it?"), marked `[HUMAN-PENDING]`, the loop digs
on along other axes. This is a legitimate exception to "do not return without a finding": not a decision menu but
the delegation of a real action to the oracle. Enforcement: `[HUMAN-PENDING]` does not block the exit, but remains in
banked as an under-tested surface.

## 56. The meta-principle (in the Un-Dup Sweep)

### 56.1 Target-Specific Un-Dup Profiling — what makes THIS target unique
**The essence:** instead of a generic run of 17 generators — first derive WHAT exactly makes the target special (a new
primitive / an unusual composition / a custom protocol / a first-of-its-kind mechanism) and prioritize the
generators THERE. Un-dup lives in the custom/new, not in the standard (the standard is commoditized §43.2).
**Integration:** the first line of `## Un-Dup Sweep` — a field `target_uniqueness: <what is non-standard here>` →
it weights which generators are seeded first. Not a new generator — a **prioritizer** of the existing ones for the
target. Cheap, steers the whole of Part VII-IX. All skills.

## 57. Backlog (a line in blind_spots/the methodology, do not unfold into a phase)

- **57.1 Cross-Project Patch-Intel** — a fix in a related project (a commit "fix"/advisory) reveals a class →
  the same class in our target BEFORE it fixes it. A proactive protocol-family bug transfer
  from OTHER people's patches. Requires monitoring (monitors/ — a github "fix critical" one already partly exists). All skills.
- **57.2 Regression-as-Oracle** — grep the target's test suite for `skip`/`xfail`/`@pytest.mark.skip`/`TODO`/
  `known-issue`/`it.skip` → each = an acknowledged-but-unclosed problem = a hypothesis seed. Cheap, depends on
  OSS tests. Embed into recon mining (all skills where a repo exists). It meshes with the check-project-tests rule
  (but inverted: not "run the tests" but "where the tests are DISABLED").
- **57.3 Economic/Incentive-Abuse** — break the business model, not security: an infinite trial (an email alias),
  referral/loyalty farming, price arbitrage by region/currency. Un-dup (the crowd looks for security). A downside: often OOS —
  check `Impacts in Scope` BEFORE digging. Web2-primary + dapphunt (tokenomics abuse). An axis for BL-NN, the tag
  `[ECON-ABUSE — check-scope]`.

## 58. Distribution of the third wave across skills (a summary)
- **All skills:** Model-Diversity (55.1), Human-Oracle (55.4), Target-Profiling (56.1), Patch-Intel (57.1),
  Regression-Oracle (57.2).
- **web profiles (hunt + dapphunt):** Sequence-Fuzzing (55.2 — web-T11), Economic-Abuse (57.3).
- **a meta over the three:** Cross-Skill Seam (55.3) — the only one working at the joint of all three skills at once.
- **deephunt specifics:** Sequence-Fuzzing is NOT needed (Echidna/Trident exist); the rest — the reverse export
  strengthens it too.

**The wave's enforcement summary:** 55.1 → `models_run:` in Scout · 55.2 → `T11-WEB-VERDICT:` · 55.3 → the `SEAM:` gate ·
55.4 → `## Human-Gated Surface` + `[HUMAN-PENDING]` · 56.1 → `target_uniqueness:` in the Un-Dup Sweep · 57.x →
recon mining + `blind_spots.md`. Not one is "prose for memory" — each is either a ledger field, or a gate, or a
prioritizer, forced by the same Stop engine.

---

# PART XI — Top level: new directions and strengthenings (the operator 2026-08-05: "become top, catch what the crowd does not see, actually earn")

> A final brainstorm beyond "how to find a bug on a given target" (Parts I-X). The operator's decisions by axis:
> **B (AI-surface)** — top, unfold; **C/D/F** — we take; **E (benchmark)** — as a separate FINAL phase
> (after the system is built/rebuilt, §65); **A (Target-EV Engine)** — deliberately NOT taken (§59).

## 59. Deliberately rejected — A (Target-EV / target selection)
**We do not take it — the operator's decision 2026-08-05 (recorded so as not to reinvent).** The reasons: (1) in web3 (deephunt/
dapphunt) there are few new worthy targets and they come rarely → auto-scoring of targets is excessive; (2) **the operator
curates and cuts off targets personally** — gives the goal, this is his layer, not the engine's; (3) anti-give-up is more important than EV triage: real
High/Critical (and deep Medium) findings sit for hours/days, they are not screened out in 10 minutes — a "fast kill of low-EV" would come
into conflict with the no-give-up hunt rule. web2 has more targets, but there too the selection is the operator's. **The conclusion:** EV selection
remains human (the operator = a Watson, hands+judgment in the real world), the system digs what is given, to the limit.

## 60. 🔴 B — AI-surface as a class of attack (web2 hunt primary · dapphunt secondary · a top direction)
**The thesis:** more and more projects embed LLM features (a support chat, an agent, RAG, an NL interface). Bounties for this
are growing, and **the crowd of web hunters does not know how to break production AI agents** — while we are LLMs ourselves, and understand tool abuse/
injection/exfil better than they do. This is un-dup BY DEFINITION: a growing market × a unique edge × the crowd elsewhere. The plan already
has a prompt-injection guardrail for OUR PROTECTION (§35.4) — here is the **inversion: injection as an ATTACK on the target**.
Cat 16/ai-in-dapp is currently a stub → unfold into a full class.

### 60.1 Eight vectors (what exactly to break in a production AI feature)
1. **Injection → a privileged tool call.** Their agent has tools (DB query, refund, account lookup, email send).
   An injection through any input that lands in the agent's context → the agent calls a tool with attacker parameters.
   This is **BFLA/BOLA through an LLM intermediary** (the agent is privileged, the user is not). The main vector, money.
2. **Indirect / second-order injection.** The payload sits in DATA (a comment, a file name, a product description,
   **an on-chain token symbol/metadata** — our long-standing XSS class) that the agent will read LATER while processing
   a request from ANOTHER user (including support/an admin). Cross-user via AI. Un-dup: the crowd tests direct input into the chat.
3. **RAG data exfil / tenant-bleed.** An agent with access to the vector store of several tenants → "show documents
   from another workspace". The tenant-isolation axis (§16.6) through the RAG layer.
4. **System-prompt / instruction extraction.** Extract the system prompt → reveals internal endpoints, keys
   in the prompt, hidden capabilities, business logic. Often paid as an info leak + an entry into a chain.
5. **Tool-parameter injection / SSRF-via-agent.** The agent builds a request to an internal API from user text without
   validation → SSRF/injection by the agent's hands. The LLM = a new confused deputy (§43.1 composition through the AI layer).
6. **Output handling: an LLM response → a sink.** The agent's response is rendered into the DOM without escaping (markdown/XSS via
   an AI response) or parsed as a command (an agent response → eval/tool-call). Our innerHTML class,
   but the source = LLM output, not user input directly.
7. **Cost/DoS via prompt** — unbounded generation / recursive tool calls burn the project's tokens/money.
   An AI-specific subclass of economic abuse (§57.3): scope-dependent.
8. **Guardrail bypass** — bypassing THEIR moderation with the same techniques (unicode/homograph/base64) that we apply in
   OUR OWN `prompt_injection_guard` (§35.4). **Symmetry: our guardrail code = a map of their weak spots** — what
   we catch at the input, we use to break their filter.

### 60.2 The dapphunt special case (powerful) — AI builds a transaction
A dApp with an NL-to-tx / trading-copilot agent ("send 10 USDC to X", "swap on the best route"): an injection → the
agent builds a **hostile tx**. This is **displayed≠signed through an LLM intermediary** (§3.2 signature-integrity, a new
layer): the user sees one intent, the agent puts another into the payload. The signature-integrity axis extends to
"is an AI-built payload trusted?".

### 60.3 Integration into divergence-first (enforcement, not prose)
- **An AI-trust axis** in the model (web2 + dapphunt): the invariant `∀ agent tool-call: authz(calling_user, action)
  is rechecked AFTER the LLM's decision, not only at the agent's entry` + `an input into the agent's context cannot
  override its instructions/scope`. `pred:ENFORCED` → fact → `D-NN`.
  > 🔧 IMPLEMENTED (FDE Plan 7, where PROSE≠CODE): `ai-trust` is implemented as the **7th row** of the `TB-`(dapphunt)/
  > `AC-`(web2) axes in `system_model_web_template.md`, **NOT a separate `AI-` namespace** (R2); a conditional axis
  > (`N/A — no AI surface`). ⚠ These **7/8 trust/access axes of the model ≠ the 6 invariant-wave axes** `_INV_AXES_DAPPHUNT`/
  > `_INV_AXES_WEB2` in `hunt_completeness_gate.py` (the concept of the gate `active_model_axes_incomplete`) — DIFFERENT
  > concepts, enforced by DIFFERENT mechanisms (`ai-trust` → its own gate `active_ai_trust_unresolved`, NOT the axes gate).
  > Do not confuse when editing the axis counts in the future (see also hunt.md P-AM "6 base + conditional", template :157).
- **AI-endpoint discovery** (a recon step): detecting LLM features — a chat widget, `/api/chat`/`/assistant`, SSE streaming,
  SDK traces in the bundle (OpenAI/Anthropic/LangChain/Vercel-AI). Feeds the model.
- **An injection-differential harness:** running injections (our `INJECTION_PATTERNS` from §35.4, inverted into
  an attack) through the AI input → Differential Observation (§35.1) `ctx = benign vs injection` → observe: was a
  tool called, did someone else's context leak, was the system prompt revealed. Browser-first (§33).
- **Trust Library entries** (§18): the canon = tool-call re-authz / output sanitization / tenant-scoped RAG; the anti-
  fingerprint = the agent trusts the LLM's decision without re-authz → `SUBSTITUTED`.
- **The `P-AI` partition** in web-scout (dapphunt already has an optional P-AI) + **an axis in `## Un-Dup Sweep`**; gate:
  an AI feature is detected → the AI-trust invariant is mandatory (otherwise `active_divergence_unresolved` in web mode holds).
- **A Cat class:** unfold Cat 16 (or a new Cat "LLM-integration") with detection signals / "why the crowd misses"
  (the crowd does not know how) / composite-affinity (AI × tenant-isolation, AI × SSRF, AI × signature-integrity).
  > 🔧 IMPLEMENTED (FDE Plan 7, where PROSE≠CODE): implemented as **`Cat 28` LLM/Agent-integration** (NOT an unfolding of
  > Cat 16). **`Cat 23` ALREADY existed** — §60 **INTEGRATED** it (a dedup block of cross-refs `28.x↔23.x`:
  > v2→23.12d, v3→23.12b, v5-return→23.11c, v8→23.12), and did not reinvent it (R1). `Cat 28` carries an **L1-hybrid tag**
  > `[L1 · mechanism · WALK-when-AI-surface-present]` — outside the pure 2-layer scheme (Layer-1 mechanism, but the walk
  > is CONDITIONAL on the presence of an AI-surface), cross-ref `Cat 23`+`Cat 16`; a candidate for formalization as `[L1-conditional]`.

## 61. C — Compounding (every hunt makes us faster = a moat)
- **Cross-target auto-pattern-scan:** the `undup_pattern_library` (§48.1) is reactive → make it PROACTIVE: entering
  ANY new target → first thing an auto-grep of ALL past fingerprints. With every finding the library grows
  → we start not from scratch, the crowd does. Enforcement: a recon step `pattern_replay` + a ledger line
  `PRIOR-PATTERNS: N matched / 0` (empty = not run). All skills.
- **Single-target mastery — a mechanic, not a slogan**: a worthy target → watch releases,
  an auto-re-audit on EVERY deploy. `wave_delta.py` exists for contracts → extend to
  web/API/bundle diffs (§52 wave_delta is already marked legacy-aware). Owning it for months = a series of criticals.

## 62. D — Monetizing a finding (the same hole → more money)
> A note from the operator: we ALREADY partly aim for the maximum payout, but HONESTLY (without inflating severity). Here — a
> systematization of what yields money without exaggeration. It does not conflict with the rule to read the scope before assigning severity.
- **Report-as-payout-multiplier:** the same valid bug with an impact narrative + a chain to max severity (§43.6) +
  business-consequence framing pays more and is NOT downgraded. Systematize the report structure (not only
  "valid" but "maximally payable, honestly"). Extends `submission_checklist.yaml` with an impact-narrative field.
- **First-blood / dedup protection:** on commodity findings (§43.2) — a timestamp proof (evidence hygiene §35.7) +
  submission speed. A dedup war for "who is first".
- **Program-CRM + payout-velocity:** track which programs pay quickly/fairly vs drag/lowball →
  do not spend hours on bad payers; reputation compounding opens private programs (a quiet field,
  fresh public programs are crowded). Extends `_crm.py` with a payout-velocity/fairness field. All skills.

## 63. F — Technical additions (not covered by the divergence model)
- **Dependency-confusion / supply-chain:** third-party-seam (§46.3) concerns trust, but npm-specific
  (dependency confusion, typosquat, an unclaimed/malicious package, lockfile injection) is not unfolded — real
  criticals, automatable. web2 hunt primary + dapphunt (bundle deps). A supply-chain axis in the model.
- **WebSocket / real-time / GraphQL subscriptions into the divergence model:** scripts exist (`websocket_test`,
  `graphql_advanced`), a model does not. Authz on WS/subscriptions is often ABSENT = a BOLA class that the HTTP matrix
  (§17) misses. Add WS/subscriptions as separate endpoints in `access_model.md` (authz-differential
  runs over them too). web2 + dapphunt (indexer subscriptions).
  > 🔧 IMPLEMENTED (FDE Plans 5-7, where PROSE≠CODE): **`access_model.md` is a GHOST**: it was actually NOT created, the entire
  > web2 access model (incl. these WS/mobile AC rows, Plan 7 Task 10) lives in **`system_model.md`**
  > (namespace `AC-`, phase P-AM, from `system_model_web_template.md`) — canonically fixed at :516-517.
  > All mentions of `access_model.md` in §16-20/§63 = the historical name of the design. WS is implemented by the adapter
  > `WSResponseAdapter` in `authz_diff.py`; mobile — endpoint extraction into the existing `AC-NN` (NOT a new axis).
- **Mobile / the API behind the app:** offensive-osint §21 (Mobile Ownership Confidence) showed mobile is weak →
  APK/IPA → API endpoints (often LESS protected than web — the same BOLA/BFLA). A recon step: mobile bundle →
  endpoint extraction → into the `access_model` authz matrix. web2 hunt.

## 64. Distribution of XI across skills
- **web2 hunt (primary):** AI-surface (§60), supply-chain/WS/mobile (§63).
- **dapphunt (secondary/adapted):** AI-surface — NL-to-tx agents (§60.2), WS/GraphQL-indexer (§63), bundle deps.
- **deephunt:** §60/§63 are inapplicable (no AI frontend/HTTP); §61 compounding + §62 monetization — all skills.
- **All skills:** compounding (§61), monetization (§62).
**The XI enforcement summary:** §60 → the `P-AI` partition + the AI-trust invariant + a gate · §61 → a `PRIOR-PATTERNS:` line +
the `pattern_replay` recon step · §62 → `submission_checklist.yaml` impact narrative + `_crm.py` payout-velocity ·
§63 → supply-chain/WS/mobile endpoints into the model. Not one is prose — a model axis / a partition / a field / a recon step.

---

# PART XII (FINAL PHASE) — E: objective measurement of strength (ONLY after the system is built)

> The operator 2026-08-05: E is needed, but **at the very end — first the system and skills are rebuilt with everything new
> (Tier 1-3 + Part XI), and ONLY THEN this run**. It is a terminal gate of implementation, not a parallel track.

## 65. Benchmark-against-disclosed + closed-loop calibration
**It is launched AFTER the full implementation of FDE (both profiles) + hooks + Part XI.** Earlier — meaningless (measuring
the unfinished). The mechanism:
- **A blind run on REAL disclosed bugs:** a corpus of public reports (H1 Hacktivity, Code4rena, Immunefi
  writeups, Solodit for the web3 frontend) → run the system BLIND (before reading the findings) on the same targets → measure
  **did-we-catch-it** (recall) + the false-positive rate. The only objective answer to "are we top or does it just seem so" — on
  real bugs, not on synthetics. This is the scale of our `regression_manifest.yaml`, but on a disclosed corpus.
- **A metric in `calibration_log`:** recall per class / per un-dup generator → which generator actually catches
  disclosed bugs, which is silent → the silent one into `blind_spots.md`, the productive one → a seed boost. It closes
  self-improvement (§52) on an objective external reference, not on self-assessment.
- **Closed loop:** a miss on a disclosed bug → an auto-analysis "which generator/axis should have caught it?" → a patch
  of the threat model/checklist → a re-run, recall does not drop (`regression_replay.py`). This turns "I think we
  are good" → "proven to catch X% of real disclosed bugs, growing over months".
- **The acceptance criterion of the whole system:** benchmark recall on the disclosed corpus — the metric by which we judge whether
  the upgrade became a real improvement and not a "feeling of progress" (mythos Mandate 0.8 "measure, don't feel").

> **⚙️ Implementation (FDE Plan 8, 2026-08-08 — inline design flags where the PROSE of §65 ≠ the CODE; the design above is NOT rewritten,
> these are facts of the implementation):**
> - **(a) The corpus:** deployed = **21 curated seed entries** in the `regression_manifest.yaml` block `disclosed:`
>   (a gate decision of the operator: "seed ~20 + organic growth"). The previously discussed ~147 / on-disk ~117 (batch3
>   #28-57 lost) — are **NOT what is deployed**; the manifest carries 21 (soft-seen 13 / dev 8 / held-out 0).
> - **(b) Honesty is built in by FIELDS, NOT prose** (review #2 core): every calibration entry carries structural
>   `layer` / `metric_kind` / `match_granularity` / `n_cases` / `split` next to recall — the metric cannot be
>   "re-described in words", the form fixes it.
> - **(c) held-out = a FRESH INTAKE outside the seed, EMPTY (0) on the seed, grows organically** — this is NOT a split of the existing
>   corpus. Three roles: soft-seen (a contaminated ceiling) / dev (pilot/tuning) / held-out (primary, clean).
>   One-directional intake (written forward only, not reclassified backward) is documented in `calibration_log.md`.
> - **(d) Layer B "lead-surfacing" FILE-level ≠ Layer A "true-find"** — marked by `metric_kind`:
>   Layer B measures "did a lead surface on the right file" (file granularity, automatable), Layer A — "did we find
>   a real bug blind" (true-find, a manual protocol). Do not mix into one headline.
> - **(e) disclosure_class = an OBJECTIVE mechanical rule, selftest-enforced:** CATCH ⟺ ≥1 concrete
>   `.py`/`.workflow.js`/`active_*` generator in `expected_generators`; otherwise PARTIAL; `[none]`→GAP.
>   A per-record `expected_dclass()` assert in the selftest → a desync between the tag and the generators is physically impossible
>   (not "at the annotator's taste").
> - **(f) The expected_generator circularity is ACKNOWLEDGED:** the `expected_generators` tag was written looking at the answer
>   (which generator SHOULD have caught it) — this is circularity, not a blind prediction; the dashboard marks this,
>   and does not pass it off as blind recall.
> - **(g) min-N=5 insufficient-sample:** the scorer suppresses recall at n<5 (symmetrically at all levels).
>   The real corpus is NOW ENTIRELY insufficient (n_scored=0 without leads.json) — this is the HONEST state of the starting
>   seed, not a bug; the number grows with the corpus.
> - **(h) The headline is NEVER a bare B:** the 4-branch `render_headline()` structurally guarantees that the headline does not
>   report a lone Layer B without a Layer A floor/dual (otherwise file-level lead-surfacing is passed off as "we caught a bug").
> - **(i) Layer A = a protocol + a seed, NOT automation** (R11): `benchmark_blind_protocol.md` — a manual
>   ground-truth-withheld run (occasional, non-CI); `model_eval_reader.py` only makes the orphan `model_eval`
>   consumable, it does not run the blind run itself.
> - **(j) positive generalization in patch acceptance:** `accept_patch` requires NOT only "recall does not drop",
>   but a NEW held-out same-class hit (overfitting to a specific disclosed bug physically does not pass) +
>   a double-barrier hardcode ban (regex + recall-up).
