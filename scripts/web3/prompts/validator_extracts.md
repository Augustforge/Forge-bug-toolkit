# Prompt: Validator Extracts (TSS / MPC / Threshold Schemes)

Specialized lens for **cryptographic validator extraction** — a different threat model than `bonded_actor_threat.md`. Here the focus is specifically on crypto-layer vulnerability classes where a validator participates legitimately in ceremonies but leaks key material offline.

> Canonical: Thorchain May 2026 ($10.8M, TSSHOCK c-split variant). Class: GG18/GG20 TSS via malformed ZK proofs or unchecked Paillier moduli.

## Cryptographic primitive identification

1. **Which threshold scheme**: GG18 / GG20 / GG24 / FROST / threshold BLS / Schnorr-MuSig?
2. **Library used**: tss-lib (Binance), forks (THORChain, Multichain), io.Finnet, custom implementation?
3. **Version + patch matrix**: post-α-shuffle fix? post-Paillier CVE-2023-33241?

## Attack class checklist (apply each)

### GG20 TSSHOCK family
- **α-shuffle**: malformed α-value in dlnproof — fixed in tss-lib v0.71.0, **check forks**
- **c-split**: classified "Won't fix" for ZenGo, partial fix for others
- **c-guess**: similar to c-split, sibling class
- Active for Threshold Network, Swingby, Axelar tofn, io.Finnet

### Paillier modulus (CVE-2023-33241)
- N has small factor → ~16-iteration key extraction
- Biprime check required
- Validation must be in ALL paths: keygen + signing + re-sharing

### ZK proof iterations
- Hardcoded ≥128 (RFC)
- Not configurable via env / config

### Insider participation
- Single malicious node can extract key over N ceremonies?
- Churn-in latency exists?
- Ceremony abort rate monitored?

## Cross-protocol applicability

These are **direct sibling protocols** to Thorchain — apply this lens when target = bonded MPC custody with GG family:
- Maya Protocol (THORChain fork)
- Threshold Network
- Swingby
- Multichain (defunct, but illustrative)
- io.Finnet
- Fireblocks legacy (pre-BitForge fix)
- ZenGo (multi-party-ecdsa)
- Qredo

## Output

For each hypothesis:
1. **Library + version**: exact identification
2. **Attack class**: α-shuffle / c-split / c-guess / Paillier / ZK iterations / churn
3. **Code location**: where validation is missing
4. **Required attacker capability**: bond size, ceremonies participated
5. **Severity**: Critical (full vault drain via key extraction)

## Tool reference

- Checklist: `checklists/specialized/tss_mpc.md`
- Threat model: `threat_models/tss_validator_extraction.yaml`
- Case study: `threat_intel.md` section 7 (Thorchain 2026)

## Anti-pattern

Don't only check "is TSS used?" — check "which exact crypto primitives, what's their patch status, can adversarial input leak material?"

---

## Source:

(paste TSS implementation code — Go/Rust typically, look for `tss-lib`, `PaillierSK`, `dlnproof`, `GG20`)
