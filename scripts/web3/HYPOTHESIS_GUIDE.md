# Hypothesis-Driven Hunting — Methodology Guide

Reference for `/deephunt` Phase J / Phase K (Solana) and Phase 2.5 in `/hunt`.

---

## Core Principles

### Principle 1: Hypothesis-Driven > Tool-Driven

**Tool-driven** hunting finds what the tools can see — and that is the Low/Medium stuff that thousands of hunters have already submitted.

**Hypothesis-driven** hunting finds what a human assumed and verified. That is High/Critical in 90% of cases.

> Mindset: "What hypothesis about the protocol can I test to find what nobody has thought of?"

### Principle 2: Patterns Are Seeds, Not Templates (GLOBAL, EVM + Solana)

> ⚠️ **Every known exploit (DeXe, Alchemix, Mango, Wormhole, Loopscale, etc.) is an INSTANCE of a broader class, not a template to copy.**

If scripts look specifically for the "DeXe pattern" — we will only find the same bug in DeXe forks. Every other protocol **fixes exactly this pattern** after public disclosure.

**The right approach**: generalize the exploit into a broader class, look for **new instances of the class**.

**Examples**:
- DeXe missing modifier → broader class: **"Sibling control-flow drift"** (siblings doing similar things with different checks)
- Alchemix oracle bypass → broader class: **"Paired code paths with safety asymmetry"** (fast/slow, with/without intermediate)
- Loopscale CPI ID → broader class: **"Any-account spoofing"** (program, sysvar, oracle, mint trust gaps)
- Marginfi state flag → broader class: **"State machine alternative routes"** (migration, close+reinit, realloc bypass)
- Drift durable nonce → broader class: **"Attacker-controlled time horizons"** (nonces, deadlines, oracle TTLs)

**Output tagging** (by all hypothesis scripts):
- `[known_class]` — matches a specific historical exploit pattern (valid but low novelty)
- `[novel_instance]` — a new manifestation of a broader class (**HIGH PRIORITY — where the payout lives**)

If all findings in a hunt are tagged `[known_class]` — you are pattern-matching, not hypothesis-hunting. Think wider.

See: `scripts/web3/hypothesis/README.md`, `scripts/sol/hypothesis/README.md` for the script ↔ class mapping.

---

## Hypothesis Sources (where to get them)

### 1. Code Asymmetries (HIGHEST ROI)

Pattern: **2 functions do something similar, the modifier is on one — why?**

Real example (DeXe):
- `withdrawTokens` has `ifNotStaken(payer, amount)`
- `stakeTokens` has `ifNotStaken(msg.sender, amount)`
- `delegateTokens` does NOT have `ifNotStaken` ← **bug**

Tool: `scripts/web3/hypothesis/asymmetry_scanner.py`

### 2. Code Comments (HIGH ROI)

Pattern: **the developer DOCUMENTED an invariant or limitation — check it in the code.**

Real example (Alchemix):
- Comment: `"@dev This is an oracle-independent downside guard against pathological quotes or severe frxETH depegs"`
- Hypothesis: "This guard protects the swap path. Is there a guard on the direct path?"
- Answer: no → bug

Patterns to mine:
- `@dev assumes X`, `MUST be Y`, `should never`, `always`
- TODO/FIXME/XXX/HACK
- "fixed in audit", "patched", "vulnerab"
- "edge case", "pathological", "extreme"

Tool: `scripts/web3/hypothesis/comment_miner.py`

### 3. Audit Trail (git history)

Pattern: **the commit message says "fix critical" but the diff doesn't touch .sol files — the fix is documented but not done.**

Real example (Alchemix commit `16e0882`):
- Subject: "Direct WETH-to-wstETH allocation marks down vault shares"
- Resolution: a runbook, not a code fix
- → the bug is still active

Tool: `scripts/web3/hypothesis/audit_trail_miner.py`

### 4. Audit Reports (PDFs)

Pattern: **the auditor found X, wrote "acknowledged" — the protocol knowingly left the bug.**

Sources:
- Github `/audits/` folder
- Cantina platform
- Code4rena public contests
- Trail of Bits / Hacken / OpenZeppelin reports

What to look for:
- `Severity: Informational` — often a real bug, "acknowledged" is not a fix
- `Resolved` claims — verify via git diff
- Scope OUT of — the auditors did NOT look

Tool: `scripts/web3/advanced/audit_pdf_parser.py`

### 5. Cross-Chain Drift

Pattern: **the same logic deployed on L1 and L2 — the bytecode is DIFFERENT. Why?**

Real signals:
- L1 has an extra check, L2 doesn't (or vice versa)
- Storage layout differs (proxy upgrade)
- Different oracles used

Tool: `scripts/web3/hypothesis/cross_chain_drift.py`

### 6. Audit "Approved" Rebuttal

Pattern: **the code passed 3 audits — challenge it from a fresh angle. What could they all have missed?**

Approach:
- Read with a new mental model (e.g., "this is an attacker, what would they try?")
- Look at acknowledged informationals — often missed
- Apply newer attack patterns (e.g., read-only reentrancy was new in 2022)
- Apply recent class-of-bug discoveries

Tool: `scripts/web3/longtail/audit_rebuttal_analyzer.py`

### 7. Composability Matrix

Pattern: **protocol A depends on B. B has a known issue or can be cheaply manipulated → A breaks even though A's own code is fine.**

Real examples:
- Cream protocol relied on the Curve LP price — Curve had a known TWAP windowing issue — drainable
- Many vaults rely on an oracle that can be manipulated for 1 block

Tool: `scripts/web3/longtail/composability_matrix.py`

### 8. State Setup Mining

Pattern: **the bug only manifests in a rare state config. Generic fuzzing misses it, but a targeted search finds it.**

Approach:
- Identify state variables that gate behavior
- Compute possible value ranges
- Test edge configurations explicitly (e.g., what if `paused=true && pendingUpgrade != 0 && admin=zero`)

Tool: `scripts/web3/longtail/state_setup_miner.py`

### 9. Past Exploit Patterns

Pattern: **what was hacked in the industry over the last 6 months — the same bugs keep recurring. Match the pattern.**

Sources:
- `HIGH_VALUE_PATTERNS.md` (35+ patterns)
- `threat_intel.md`
- rekt.news weekly
- Solodit (30k+ audit findings)

### 10. Specialized Class-Specific Bugs

Pattern: **a protocol class has known footguns — apply a class-specific lens.**

Examples:
- **Bridge** (LayerZero/Wormhole) → DVN compromise, replay, validator collusion
- **Vault (ERC-4626)** → donation, first-depositor inflation, share rounding
- **AMM** → TWAP manipulation, sandwiching, tick math
- **Lending** → liquidation MEV, interest model, bad debt
- **Restaking** → slash race, withdrawal queue

Tools: `scripts/web3/specialized/*.py`

---

## How to Formulate a Good Hypothesis

Bad hypothesis: "Maybe there's a bug in the staking logic."

Good hypothesis:
```
H: `delegateTokens` allows user to delegate tokens that are already staked,
   because it lacks `ifNotStaken` modifier.
   
Verification: 
  1. Read `ifNotStaken` body — does it check stakedBalance?
  2. If yes — write Foundry test:
     a. Deposit 100 tokens
     b. Stake 100 tokens
     c. Try delegate 100 tokens
     d. Assert: succeeds (bug) OR reverts (no bug)
  3. If succeeds — quantify economic impact
```

Good hypothesis has:
- **Specific function/line** identified
- **Concrete failure mode** described
- **Verification plan** with executable steps
- **Expected outcome** stated

---

## Hypothesis Ranking

For each hypothesis, score:

| Dimension | Low (1) | Medium (3) | High (5) |
|-----------|---------|------------|----------|
| **Likelihood (is this real?)** | Speculative | Plausible | Direct evidence |
| **Severity if true** | Info/Low | Medium | High/Critical |
| **Effort to verify** | 1 day | 2-4h | 30 min |
| **Detection asymmetry** | Detected by basic tools | Sometimes detected | Almost no tools catch |

**Hunt sequence**: highest (sev × likelihood × asymmetry) / effort first.

---

## Anti-patterns (don't do these)

1. **"Let me run slither and see"** — tools last, hypotheses first
2. **"This looks complex, must have bugs"** — be specific
3. **"Let me grep for SafeMath"** — too narrow + already-fixed pattern
4. **Hypothesizing without reading code** — must read 200+ lines manually
5. **Hypothesis based on protocol name reputation** — bias

---

## Workflow Integration

### In `/hunt` (Phase 2.5)
```bash
python3 scripts/web3/hypothesis/asymmetry_scanner.py --target $T --output sessions/$T/hypothesis/
python3 scripts/web3/hypothesis/comment_miner.py --target $T --output sessions/$T/hypothesis/
python3 scripts/web3/hypothesis/audit_trail_miner.py --repo $T --output sessions/$T/hypothesis/
# Write 3-5 hypotheses to sessions/$T/hypotheses.md
# Tools (slither/mythril) run AFTER, with awareness of hypotheses
```

### In `/deephunt` (J0)
- Same scripts +
- `cross_protocol_invariant.py`, `code_config_drift.py`
- Specialized hunter (bridge/vault/amm/...)
- Long-undiscovered scripts (state_setup, audit_rebuttal, composability)
- AI prompts (`prompts/read_as_attacker.md`, etc.)

---

## Examples — Illustrative Hypotheses

Illustrative examples drawn from public cases; the protocol names are neutral examples of the class.

### DeXe-style (Medium, missing modifier)
- Source: asymmetry_scanner
- H: "delegateTokens lacks ifNotStaken modifier that withdrawTokens has"
- Verification: Foundry test
- Impact: same tokens earn rewards + voting power

### Alchemix WstETH/SFraxETH-style (High, oracle bypass)
- Source: comment_miner
- H: "Direct allocation path lacks oracle guard that swap path has"
- Verification: Foundry tests (class-of-bug PoCs)
- Impact: NAV loss during depeg

### Mezo PriceFeed-style (Medium, oracle cast)
- Source: manual review + code_config_drift
- H: "uint256(int256(answer)) without price>0 check silently accepts negative"
- Verification: Hardhat test
- Impact: oracle manipulation if aggregator misbehaves

---

## Reference

- `THREAT_ACTOR_MODELS.md` — feasibility scoring
- `HIGH_VALUE_PATTERNS.md` — 35+ Critical patterns library
- `COGNITIVE_FRAMEWORK.md` — phase-specific mindset prompts
- `DEFI_PRIMITIVES.md` — class-specific bugs catalogue
