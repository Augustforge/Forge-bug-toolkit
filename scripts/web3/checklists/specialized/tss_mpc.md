# Specialized Checklist: TSS / MPC threshold signatures

> **When to apply**: the protocol uses a threshold signature scheme (TSS), MPC, threshold ECDSA/BLS, GG18/GG20/GG24, FROST, or a derivative tss-lib fork. Examples: Thorchain, Maya, Multichain, Threshold Network, Swingby, io.Finnet, Fireblocks legacy, ZenGo.
>
> **Canonical case**: Thorchain May 2026 ($10.8M) — TSSHOCK c-split/c-guess variant. The Verichains 2022 fix was narrow for α-shuffle, sibling variants stayed alive for 4 years.

---

## tss-lib version / patch matrix

- [ ] Check the exact tss-lib version (fork and commit hash)
- [ ] α-shuffle (Verichains 2022) — fixed in Binance tss-lib v0.71.0+? If the fork diverged — separately
- [ ] c-split — Verichains classifies "Won't fix" for ZenGo; **check custom forks**
- [ ] c-guess — partial patches; verify if fully addressed
- [ ] CVE-2022-47931 (io.Finnet) — GG20 derivative key extraction
- [ ] CVE-2023-33241 (Fireblocks BitForge) — Paillier modulus validation

## Paillier modulus validation (CRITICAL)

This is where the c-split and BitForge attacks live:

- [ ] `PaillierSK.N` generation — biprime check (N = p × q, both prime, ~equal length)
- [ ] Small-factor sieve applied (sieve over primes up to 2^16 minimum)
- [ ] The modulus check is performed in keygen, in re-sharing, AND in signing — NOT only in one
- [ ] No bypass via a config flag (`SkipPaillierValidation = false` should not be possible)

Without these checks — an attacker with an adversarial Paillier modulus can extract shards in ~16 iterations.

## ZK proof verification

- [ ] Proof iteration count is hardcoded ≥ 128 (RFC recommends 128 for the security level)
- [ ] Iteration count is NOT configurable via env var / config file
- [ ] dlnproof verification rejects malformed α values (α-shuffle attack vector)
- [ ] All proof checks are performed strictly — no "warning + continue" path

## Churn-in / validator entry threat model

- [ ] Is there a minimum cool-down period between joining the signing set and first signing participation? (Without it — instant key acquisition)
- [ ] Is the bond amount sufficient so that attack cost > expected gain?
- [ ] Behavioral baseline — how much is the signing pattern monitored for anomalies?
- [ ] Removed validators — proper key resharing, not reuse of old shares?

## Insider threat model

- [ ] Sum of legitimate signings + permitted outbounds — is there an on-chain invariant that checks that vault outflow matches authorized inflow + scheduled outflows?
- [ ] Can a single validator extract value if they participate in N ceremonies offline? (If "can" — there is no mitigation, fundamentally vulnerable)
- [ ] Ceremony abort rate per node — is a suspicious "always-honest" pattern flagged (the exact TSSHOCK behaviour)?

## Adjacent attack vectors

- [ ] **Frost** (Schnorr threshold) — different math, but the same insider class. Verify nonce generation is deterministic
- [ ] **GG24** (emerging) — a newer GG20 variant, fewer audits, fewer detections
- [ ] **Threshold BLS** (Drand, Chainlink VRF) — same insider model, different crypto

## On-chain invariants for TSS-secured vaults

- [ ] `vault_balance(t) == vault_balance(t-1) + Σ(authorized_inflows) - Σ(authorized_outflows)` — for every block
- [ ] Any outbound tx must trace to the pending outbound queue + swap memo + LP withdrawal — no additional outflows
- [ ] Pause mechanism — is there an automatic trigger on invariant violation? Manual in Thorchain took 8 minutes — that is lost time

## Sources / references

- [Verichains TSSHOCK research](https://verichains.io/tsshock/)
- [Fireblocks GG18/GG20 Paillier CVE-2023-33241](https://www.fireblocks.com/blog/gg18-and-gg20-paillier-key-vulnerability-technical-report)
- [Thorchain May 2026 post-mortem (pending) — see threat_intel.md case study](../../threat_intel.md)
- threat_model: `scripts/web3/threat_models/tss_validator_extraction.yaml`
