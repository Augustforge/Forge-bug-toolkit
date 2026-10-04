# Hypothesis Generation — Methodology

**When to use this prompt:** before deep-diving into a target. Generate 5-10 candidate
composite hypotheses, then prioritize by exploitability × severity × verifiability.

**Output format:** structured hypothesis list, NOT free-form analysis.

---

## The 7 hypothesis categories

Use these as generation lenses. Walk each lens against the target; produce candidates.

### 1. **Composite chain-of-threats**
Two or more threat_models compose into a complete attack primitive.
- *Lens question*: "Which point surfaces does this target combine, and does combining them produce a drain/takeover?"
- *Examples*: H1 (Unconstrained Minter + Fake Collateral), H2 (Clone + Permit2), H6 (Validator + Mint Authority + No Pauser)
- *Strength*: most real-world incidents are chains, not single bugs

### 2. **Behavioral / OPSEC**
Properties of the team, not the code.
- *Lens question*: "What about how this team operates (key custody, audit cadence, doxxing, rotation) creates risk?"
- *Examples*:
  - "Single key for admin role + team publicly anonymous + no key rotation in 2 years"
  - "Audit 8 months old, 40 commits since, scope explicitly limited to old commit hash"
  - "Bug bounty program excludes 'centralization risks' but admin is EOA — scope omission"
- *Strength*: not findable via static analysis; ROI for hunters who do OSINT

### 3. **Cross-chain / cross-deployment / multi-version**
Same code / same key / same pattern across multiple deployments. Also: multi-version
contracts within same protocol (V1/V2/V3 history).
- *Lens question*: "Where else is this protocol deployed? Same code? Same admins? Same wrapped assets? **Any deprecated versions still alive with user approvals?**"
- *Examples*:
  - "Same EOA admin across 4 chains" (Echo could have been worse with mature chains)
  - "Bridge wrapper on chain X mints ≠ locked on chain Y (parity drift)"
  - "Signature replay between forks (chainId not bound)"
  - "Protocol V1 deployed on TRON in 2022, deprecated but never killed, still has user approvals" (Transit Finance 2026 pattern)
  - "V3 launched on Ethereum but V1 still active on Fantom — only one chain pause-migrated"
- *Strength*: scales single finding across multiple programs/payouts
- *Sub-routine — Multi-Version Enumeration*:
  1. List ALL chains protocol operates on (docs + DefiLlama)
  2. For each chain: pull ALL historical contract addresses (Etherscan deploy tx history)
  3. For each historical contract: check bytecode present + paused() + owner()
  4. For each ALIVE deprecated contract: sample allowance() across top token holders
  5. Quantify total drainable surface (sum of approved-but-vulnerable)
  6. Score: any single chain × any single version with surface > $100K = High candidate

### 4. **Economic / game-theoretic**
Math + incentives, not pure code.
- *Lens question*: "Are there incentives or numbers that don't add up — profitability of an attack vs cost?"
- *Examples*:
  - "Liquidation discount > stability fee → attacker profits by triggering own liquidation"
  - "Governance attack cost (cost to buy 51% voting power) < what can be extracted"
  - "MEV sandwich on this AMM more profitable than fee revenue → market manipulation primitive"
  - "Bond size < what attacker can steal in single epoch"
- *Strength*: harder for traditional auditors; high-bounty class

### 5. **Side-channel / infra**
Off-chain dependencies that affect on-chain assumptions.
- *Lens question*: "What does this protocol trust off-chain, and what happens if that's compromised?"
- *Examples*:
  - "Indexer (Goldsky / Subgraph) returns balance — frontend uses it for display; off-chain manipulation = UI lies (display_vs_reality already covers this)"
  - "Oracle data source manipulation (single Chainlink node, custom poller)"
  - "Mempool exposure on sensitive ops (private RPC vs public)"
  - "DNS / SSL trust chain (cert expiration, registrar compromise)"
- *Strength*: novel surface, often underexplored

### 6. **Pattern-mining (data-driven)**
Look at the corpus of recent incidents → identify common substrate → check target for it.
- *Lens question*: "What pattern has recurred 3+ times in the past 12 months that nobody's checking on this target?"
- *Examples*:
  - "Empty cToken market in Compound v2 forks (Hundred 2023 + 5 others)"
  - "Uninitialized UUPS implementation (Wormhole pattern, many smaller hits)"
  - "Bridge admin EOA on fresh chains (Echo pattern + likely more on Berachain, Monad)"
- *Strength*: pre-emptive — hunt the pattern before next incident

### 7. **Pre-mortem / red team**
Mentally execute as the attacker — what would YOU do?
- *Lens question*: "If I had to drain this protocol in a week, where would I start?"
- *Examples*:
  - "I'd phish the deployer's social media → key compromise → mint"
  - "I'd front-run the next governance proposal with a malicious one"
  - "I'd register the dApp's misspelled clone, run a Privy wildcard import"
  - "I'd find an unaudited admin function that wasn't in the audit scope"
- *Strength*: catches things that don't fit existing categories

### 8. **Custody extraction** (unifying lens)
Any contract that HOLDS third-party assets (bridge locked funds, LP locker, vault,
escrow, staking-lock). Seeds: Gravity Bridge ($5.4M, 2026), DxSale/DxLock ($7.3M, 2026).
- *Lens question*: "Enumerate EVERY code path and EVERY privileged actor that can move
  assets OUT of this custody contract. For each, which lacks a timelock / guardian /
  quorum-integrity check?"
- *Examples*:
  - "Bridge: who/what can pass `submitBatch` besides the honest 2/3 quorum? (dedup/replace/replay)"
  - "Locker: owner-only `setFee`/`setUnlockTime` mutates EXISTING locks → release others' funds"
  - "Vault/escrow: emergency/migrate path bypasses per-user accounting"
- *Strength*: collapses bridge/locker/vault/escrow into one checklist; happy-path may be
  fine while an exit-path is unguarded. Detectors emit the `custody` tag → auto-matches
  `validator_set_quorum_integrity.yaml` + `liquidity_locker_privileged_unlock.yaml`.

### 9. **Promise-vs-Code gap**
The discrepancy between what the protocol PROMISES (landing page / docs: "immutable",
"locked", "no admin keys", "trustless") and what the CODE actually guarantees.
- *Lens question*: "Pull the marketing/doc claims, then check each against the code —
  where does the code NOT enforce the promise?"
- *Examples*:
  - DxSale: "immutable locker" — but `setFee` is owner-mutable → lock voidable
  - Gravity: "no admin keys" — but 2/3 validator keys = de-facto admin (concentration)
  - "Funds are safe / non-custodial" — but an emergency-withdraw moves user assets
- *Strength*: highly monetizable (centralization/false-claim findings); a NEW angle —
  read what they sell, then prove the code doesn't back it.

### 10. **Liveness / activity-gated exit** (mirror of Lens 8)
Lens 8 asks "can someone pull funds OUT improperly?". This is the inverse: "can funds
get PERMANENTLY STUCK?". Capital is lost just as surely when the exit can never fire.
On Immunefi/Cantina "permanent freezing of funds" is its own Critical/High class — no
theft required. Seed: HONG ICO ($2M, 1003 ETH trapped 9 years, white-hatted 2026).
- *Lens question*: "Is EVERY withdraw / refund / claim / redeem / exit reachable on its
  own, or does it depend on a state TRANSITION that can stop firing or be blocked? Who/what
  drives that transition, and what happens if they go away, run out of gas, or refuse?"
- *Two sub-classes* (keep them distinct):
  - **Forgotten / activity-gated transition** (HONG): the exit-enabling state change is
    reachable ONLY through an activity that ceases. HONG's `tryToLockFund()` is `internal`,
    driven solely by `createTokenProxy()` (token purchases); the ICO missed its minimum,
    buying stopped in 2016, the fund parked in a non-terminal state, and `refundMyIcoInvestment`
    sat dormant for 9 years. Smell: `internal` state-machine driver called from ONE path;
    terminal/release state needs `now >= deadline` AND a fresh call nobody makes.
  - **Adversary-blockable transition / freeze** (DoS-to-freeze): a single revert, an
    unbounded loop, a force-send balance break, a blacklisted recipient, or a withheld
    keeper/quorum/oracle step makes the exit transition unreachable for everyone.
- *Lens checks*:
  - List every state var that GUARDS an exit (`isReleased`, `isFinalized`, `unlocked`,
    `distributionReady`, `phase == X`). For each: enumerate ALL writers. If the only writer
    is `internal`/`onlyOwner`/quorum-gated and reachable from a path that can stop → flag.
  - Is the exit's success conditional on a downstream external call (sub-wallet, child
    contract, token transfer, sweep) that can permanently revert? (HONG refund pulls from
    `extraBalanceWallet` before paying out.)
  - Time-locked vesting/escrow/auction: does the "claim after T" path also require an
    `advance()`/`finalize()`/`settle()` that no incentivized party will ever call?
- *Strength*: drain-blind; auditors and the drain-centric corpus under-cover it. Mirror
  Lens 8 on every custody target. Detectors emit `liveness` → auto-matches
  `fund_liveness_terminal_state.yaml`. (Separate the FINDABLE liveness bug from a
  designed pause/guardian freeze — see anti-patterns + `[[feedback_ton_self_destructive_severity]]`.)

---

## Generation procedure

For a new target, run this in order:

### Step 1: Tag the target
- Chain, protocol category, age, audit status, dependencies
- Match against `applies_when` of existing threat models in `dapphunt/threat_models/`
- Run `apply_dapp.py --target sessions/$DOMAIN` to auto-generate baseline

### Step 2: Walk the 7 lenses
For each of the 7 categories above, generate 1-3 hypotheses specific to this target.
Result: 7-21 candidate hypotheses.

### Step 3: Score each candidate
Use 4 dimensions (1-5 each):
- **Exploitability**: how concrete is the attack path? (5 = stepwise reproducer; 1 = "might be possible")
- **Severity**: realized loss if exploited (5 = Critical+ funds; 1 = Info)
- **Verifiability**: can I confirm/refute in a hunting session? (5 = scanner output; 1 = needs internal team docs)
- **Novelty**: is this already in public knowledge / reports? (5 = original angle; 1 = "everyone knows")

Total = (E × S × V × N). Threshold: keep top 40% by total.

### Step 4: Compose into chains
For each kept hypothesis, ask: "what else must be true for this to compose into a primitive?"
If you can answer with 2-4 additional checks → write it up as a composite hypothesis
(add to `hypothesis/HYPOTHESES.md`).

### Step 5: Generate reproducer plan per top-3
For the top 3 by score, write:
- Exact verification command sequence
- Expected outputs at each step
- Foundry / Tenderly fork plan if active testing needed
- Severity claim (with rubric citation)

---

## Anti-patterns to avoid

When generating, don't:

- **Wishful thinking**: "if there's a reentrancy bug somewhere" — be concrete or skip
- **Audit recitation**: re-finding what auditors already reported — read audit report first
- **Theoretical impossibilities**: "if attacker controls Chainlink" → unverifiable
- **Stacked uncertainty**: "if X and if Y and if Z" each unverified → combinatorial nonsense
- **Vibes-based concern**: "feels centralized" → either it IS (cite roles + threshold) or it isn't
- **Pattern hammering**: "Hundred-pattern!" when target uses internal accounting not balanceOf
- **Designed-trust compromise as a "bug"**: theft of ≥quorum signing keys / a malicious
  majority (Gravity 2026, Ronin 2022) is the protocol's DECLARED trust model — NOT a
  findable vuln. Do NOT submit "if 2/3 keys are stolen, funds drain" unless the program
  explicitly pays for centralization/key-custody. FINDABLE = a LOGIC flaw that lets a
  SUB-quorum / replayed / forged set pass verification. Filter every custody hypothesis
  through this gate. (See `[[feedback_ton_self_destructive_severity]]`; for monetizing the
  centralization angle where accepted, see triage `hypothesis_triage_dapp.md`.)

---

## Output format

```yaml
target: <domain or contract>
chain: <chain name>
tags: [list]
session_date: <ISO>
generated: <count> candidates

top_3:
  - id: <slug>
    name: <human-readable name>
    category: <one of 7 lenses>
    chain_of_threats:
      - threat_model: <existing yaml id>
        check: <concrete verification step>
      - threat_model: <existing yaml id>
        check: <concrete verification step>
    score:
      exploitability: <1-5>
      severity: <1-5>
      verifiability: <1-5>
      novelty: <1-5>
      total: <product>
    reproducer_outline:
      - <step 1>
      - <step 2>
      - <step 3>
    severity_claim: <Critical / High / Medium / Low>
    severity_rubric_reference: <which threat model's rubric>

# … keep all candidates (not just top 3) for later passes
candidates:
  - id: ...
```

---

## How this prompt evolves

Track which lens produces winning hypotheses (confirmed bugs, paid bounties).
Periodically re-weight lenses based on signal. Add new lenses if new incident
categories emerge (e.g., AI-integrated dApp manipulation, ZK verifier bugs).

Update `_dapphunt_lessons.py` `_CLASS_KEYWORDS` with new category tags so lessons
aggregator picks them up.

## When to use which lens — quick guide

| Target profile | Which lens to start with |
|---|---|
| Fresh deploy on new chain (≤6mo) | 2 (Behavioral) + 6 (Pattern-mining) |
| Mature audited protocol | 8 (drift — Audit Drift) + 5 (Side-channel) |
| Token launch / fair launch | 4 (Economic) + 1 (Composite) |
| Bridge or cross-chain | 3 (Cross-chain) + 1 (Composite) |
| Lending / vault | 4 (Economic) + 6 (Pattern-mining) |
| dApp frontend with auth | 1 (Composite via auth+sign chains) |
| AA / smart wallet stack | 5 (Side-channel) + 7 (Pre-mortem) |
| **DEX aggregator / router / multi-version protocol** | **3 (Cross-chain → multi-version sub-routine) + 1 (Composite H11/H12)** |
| **Protocol with multi-year history** | **3 (multi-version) + 6 (pattern-mining historical incidents)** |
| **Bridge / locker / vault / escrow (holds 3rd-party funds)** | **8 (Custody extraction) + 9 (Promise-vs-Code) + 1 (Composite)** |
| **Liquidity locker / launchpad / vesting** | **8 (Custody) + 2 (Behavioral: abandoned/ownership-transferred) + 9 (Promise-vs-Code) + 10 (Liveness)** |
| **ICO / crowdsale / DAO-fund / auction / phased lifecycle** | **10 (Liveness: activity-gated exit) + 9 (Promise-vs-Code) + 6 (Pattern-mining)** |
| **Time-locked vesting / escrow with `finalize`/`settle` step** | **10 (Liveness: who calls the transition?) + 4 (Economic: who's incentivized to)** |
