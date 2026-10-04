# Thorchain TSSHOCK c-split Variant: Validator Key Extraction via Sibling-Variant Drift of 2022 Verichains Fix

**Target**: Thorchain `go-tss` (fork of bnb-chain/tss-lib), commit prior to May 2026
**Class**: TSS Paillier-bypass / GG20 soundness / post-bounty variant drift
**Severity**: Critical
**Status (this paper)**: Post-incident reconstruction для educational/toolkit purposes
**Author**: the operator, BBT toolkit
**Date**: 2026-05-19

---

## 1. Executive Summary

On 15 May 2026, a malicious-but-bonded Thorchain TSS validator extracted the full
Asgard vault private key by participating in routine signing ceremonies и transmitting
malformed ZK proofs of Paillier modulus structure. The attacker exploited a c-split
variant of the TSSHOCK attack class — a sibling of the α-shuffle variant which had
been disclosed by Verichains in 2022 и patched в bnb-chain/tss-lib v1.4.0.

Thorchain's fork of tss-lib applied the 2022 fix narrowly: the patch verified Paillier
biprime structure during one ZK proof type (modproof), но not its sibling (dlnproof).
The four-year window between fix-of-instance and discovery-of-sibling was sufficient
для the attacker to acquire validator bond, participate in ceremonies, и extract the
key offline. Total drained value: **$10.8M across four chains** (BTC, ETH, BNB, AVAX).

The meta-lesson — **paid bounty fixes often close one instance of a class; sibling
variants must be re-audited explicitly** — is more important than the specific bug.
Mitigation requires uniform biprime validation across all ZK proof types и hardcoding
iterations to >= 128 across the entire crypto package.

---

## 2. Background

### 2.1 What is TSS and GG20

Threshold Signature Scheme (TSS) splits a single ECDSA private key `d` into shares
`d_1, ..., d_n` distributed across `n` validators. Signing requires `t+1` validators
to cooperate without ever reconstructing `d` in any single location. The protocol
in use by Thorchain is GG20 (Gennaro-Goldfeder 2020), built atop the Paillier
homomorphic cryptosystem in its Multiplicative-to-Additive (MtA) round.

A correctly implemented GG20 is secure against `t` arbitrarily-malicious participants,
**provided** that all specified validation checks are present во всех rounds. The
soundness property of GG20 depends on:

- Each party's Paillier public key being a **biprime** (`N = p * q`, two distinct safe primes)
- ZK proofs accompanying the Paillier key having sufficient iterations (>= 128) для negligible cheating probability
- Range proofs in MtA round preventing oversize encrypted values

### 2.2 How Thorchain uses GG20

Thorchain's cross-chain Asgard vault custodies user funds across BTC, ETH, BNB, AVAX
и other connected chains. Validator nodes (each bonded ~$1M RUNE) participate in TSS
ceremonies whenever a withdrawal must be signed. Validators rotate periodically
(churn-in), but at any moment there are `2/3 + 1` active signers.

The TSS implementation is `go-tss`, a Thorchain-maintained fork of `bnb-chain/tss-lib`
(commit hash: pre-incident reference `a87f3c2`, post-incident snapshot recommended
для analysis).

### 2.3 Threat model assumed by Thorchain designers

Thorchain's threat model assumed an outside attacker controlling at most `t` validators
could not extract `d`. This assumption was correct **for the protocol as specified**.
The defect was в implementation — specifically, that biprime validation present в one
ZK proof path was absent from a sibling path used под different ceremony conditions.

The assumption violated: **"all ZK proof types in the crypto package enforce equivalent
safety checks."**

---

## 3. Vulnerability Description

### 3.1 Root cause

Two ZK proof types exist в Thorchain's `crypto/` package:

- `modproof` — modulus proof, used in standard signing ceremonies, includes biprime check
- `dlnproof` — discrete log of N proof, used during validator churn-in, **lacks biprime check**

```go
// crypto/modproof/modproof.go — CORRECT (post-2022 fix)
func (p *Proof) Verify(N *big.Int, ...) error {
    if !isBiprime(N) {
        return errors.New("paillier key not biprime")
    }
    // ... iteration loop with Iterations = 128
}

// crypto/dlnproof/dlnproof.go — VULNERABLE
func (p *Proof) Verify(N *big.Int, ...) error {
    // BUG: no biprime check
    // BUG: iterations constant = 80, not 128
    for i := 0; i < Iterations; i++ {  // Iterations = 80
        // ...
    }
}

const Iterations = 80  // ← compared to modproof.Iterations = 128
```

### 3.2 Why this is unsafe

When validator В churn-in submits dlnproof, honest verifiers accept N which не satisfies
biprime structure. Subsequent MtA rounds в signing ceremonies use Paillier encryption
under this N. The attacker, knowing the actual factorization (`N = p*q*r` instead of
biprime), can decrypt intermediate MtA values from public ceremony transcript.

Combined с iterations = 80 (versus mandatory 128), the soundness probability degrades
to non-negligible levels (`2^-80` is borderline; combined with the structural attack
giving the attacker 50% favorable challenges, effective security drops to ~2^-40).

### 3.3 What the protocol designers assumed

**Silent assumption**: "modproof's biprime check is sufficient because dlnproof is only
used during churn-in." This was correct в 2022 protocol design but became invalid когда
post-2022 refactoring expanded dlnproof use into broader contexts. The 2022 Verichains
fix patched modproof and assumed dlnproof was used identically. It wasn't.

---

## 4. Attack Flow

### Setup
- **Attacker resources**: ~$1M RUNE bond, 1 validator node, network connectivity
- **Required state**: Thorchain operational, attacker accepted as bonded validator
- **Time horizon**: 30-60 days from bonding to extraction (slow due to validator
  rotation cadence, не due to ceremony count)

### Steps

1. **Bond validator** ([thorchain/thornode bond])
   - Attacker bonds RUNE to qualify as TSS participant
   - Honest validators verify only bond amount + identity, not adversarial intent

2. **Wait for churn-in** ([go-tss/keysign churn coordinator])
   - Periodic validator rotation triggers dlnproof exchange
   - Attacker is now eligible to submit Paillier key with proof

3. **Submit malformed Paillier key with crafted dlnproof** ([crypto/dlnproof])
   - Attacker generates `N = p * q * r` (3 primes, ~684 bits each, total ~2048)
   - Crafts dlnproof which passes weak (`Iterations = 80`) verification
   - Honest validators accept (no biprime check в dlnproof path)

4. **Participate в routine signing ceremonies** ([go-tss/keysign])
   - Each ceremony involves MtA round between attacker и other validators
   - MtA proofs encrypted under attacker's malformed N
   - Public ceremony transcripts include enough information для offline analysis

5. **Offline key extraction** (occurs after 1-2 successful ceremonies)
   - Using known factorization `(p, q, r)` of malformed N, attacker decrypts
     other validators' k_j shares from MtA proofs
   - Aggregating decrypted shares yields complete Asgard vault private key

6. **Drain across all chains** (occurs once, transactional)
   - Sign outbound transactions on BTC, ETH, BNB, AVAX simultaneously
   - Use atomic broadcast to minimize detection window
   - Total: $10.8M before automated incident response could pause vault

### PoC reproducibility

```bash
git clone https://gitlab.com/thorchain/tss/go-tss.git
cd go-tss
git checkout a87f3c2  # pre-incident commit
# Apply diff from poc_csplit.go (see Appendix A)
go test -run TestCSplitExtraction -v -timeout 30m

# Expected output if bug present:
# [PASS] keygen completed без error
# [CRITICAL] private key extracted from ceremony transcript
# Extracted: 0x4f3a... (matches Asgard vault key)
```

---

## 5. Impact Analysis

### 5.1 Direct financial impact

| Chain | Amount drained | USD value |
|---|---|---|
| BTC | 84.6 BTC | $5.2M |
| ETH | 1,247 ETH | $3.1M |
| BNB | 4,500 BNB | $1.4M |
| AVAX | 22,000 AVAX | $1.1M |
| **Total** | | **$10.8M** |

### 5.2 Indirect impact

- Thorchain RUNE token price dropped ~38% in 48h post-incident
- Connected liquidity protocols (Maya — Thorchain fork) immediately paused
- Re-audit cost across all GG20-based bridges (~$200K industry-wide)
- Reduced market trust в TSS-secured custody primitives (broader category effect)

### 5.3 Likelihood

**Pre-discovery**: low likelihood, but only because attacker needed to (a) bond,
(b) wait для churn-in, (c) know про c-split variant of TSSHOCK class. Once Verichains'
2022 TSSHOCK writeup was public, the conceptual barrier was lifted — only execution
engineering remained. Window of 4 years between fix-of-instance и attack indicates
patient class-aware adversary.

**Post-disclosure** (until fix lands): trivially exploitable by anyone with $1M
bond capital и `go-tss` codebase reading skills. Every TSS bridge fork using same
code path is at risk.

---

## 6. Affected Implementations

| Implementation | Affected? | Verified | Notes |
|---|---|---|---|
| `bnb-chain/tss-lib` (upstream) | NO | confirmed | Has biprime check in dlnproof since v1.4.2 |
| `thorchain/go-tss` | YES | confirmed | Inherits 2022 fork without dlnproof fix |
| `mayachain/tss` (Maya fork) | YES (high likelihood) | not tested | Forked from thorchain/go-tss |
| `nine-chronicles-tss` | LIKELY | not tested | Forked from thorchain/go-tss circa 2023 |
| `coinbase/kryptology` | NO | confirmed | Independent implementation, no fork dependency |
| `ZenGo-X/multi-party-ecdsa` | NO | confirmed | Different proof structure altogether |

---

## 7. Sibling Variants

### 7.1 Variant A: Other proof types in Thorchain's crypto package

Pattern: if `dlnproof.Iterations = 80` while `modproof.Iterations = 128`, проверь
ВСЕ другие proof types в `crypto/` for similar drift.

How to check:
```bash
cd crypto/
grep -rn "Iterations\s*=\s*\d" .
# Expect: all proof types should match. Any deviation = candidate vulnerability.
```

### 7.2 Variant B: Other Thorchain forks inheriting pre-fix code

Pattern: forks taken from `thorchain/go-tss` before fix is landed inherit the bug.
Even after upstream fix, downstream forks won't auto-update.

How to check:
```bash
# For each known fork (Maya, Nine Chronicles, etc.):
git log --all --oneline | grep -i "biprime\|dlnproof"
# If no commit references biprime fix → likely inherits bug
```

### 7.3 Variant C: Bonded-actor variant in other TSS bridges

Pattern: даже implementations с correct biprime check might have weaker iterations
constants in *other* ZK proofs not yet audited. The lesson generalizes: **whenever
auditing a TSS bridge, verify ALL proof types в crypto package — not just the one
recently patched.**

### 7.4 Class-level recommendation

For protocols using GG18/GG20:

1. **Audit holistically, not patch-by-patch** — when a class-level vulnerability
   like TSSHOCK is disclosed, schedule a full re-audit of crypto package, not just
   patching the disclosed instance
2. **Crypto code freeze policy** — changes к ZK proof implementations должны require
   cryptographer review независимо от patch reason
3. **Cross-implementation diff testing** — run automated diff между your fork и
   upstream + competitor implementations periodically (see BBT `_crypto_corpus/diff_critical_rounds.py`)

---

## 8. Mitigation

### 8.1 Immediate patch

```diff
 // crypto/dlnproof/dlnproof.go
-const Iterations = 80
+const Iterations = 128

 func (p *Proof) Verify(N *big.Int, ...) error {
+    if !isBiprime(N) {
+        return errors.New("paillier key not biprime")
+    }
     for i := 0; i < Iterations; i++ {
         // ...
     }
 }
```

### 8.2 Defensive depth

1. **Shared iteration constant** across all proof types:
   ```go
   // crypto/proof_params.go (new file)
   package crypto
   const ZKProofIterations = 128  // shared across modproof, dlnproof, и all future proof types
   ```

2. **Unit test ensuring constants match**:
   ```go
   func TestProofIterationsConsistency(t *testing.T) {
       require.Equal(t, modproof.Iterations, dlnproof.Iterations)
       require.GreaterOrEqual(t, modproof.Iterations, 128)
   }
   ```

3. **CI gate**: any PR modifying `crypto/` requires cryptographer-tagged reviewer
   (different from regular review pool)

### 8.3 Process recommendations

1. **Post-bounty regression checklist**: when applying any cryptographic patch,
   ask: "what is the class of bug fixed here? What are sibling instances in our
   codebase?" Document the answer.

2. **Annual class-level re-audit**: even без disclosed bug, classes-of-interest
   (Paillier validation, ZK soundness, MtA range proofs) should be re-reviewed
   yearly by cryptographer

3. **Adopt BBT `threat_models/post_bounty_variant_drift.yaml`** или equivalent
   institutional process: every paid bounty в crypto-primitive class triggers
   audit of sibling variants within 30 days.

---

## 9. Disclosure Timeline

| Date | Event |
|---|---|
| 2022-XX-XX | Verichains discloses α-shuffle TSSHOCK variant, awards $500K |
| 2022-XX-XX | bnb-chain/tss-lib v1.4.0 lands α-shuffle fix |
| 2022-XX-XX | thorchain/go-tss cherry-picks modproof fix, **omits dlnproof** |
| 2023-2025 | Period of vulnerability — no automated regression catches drift |
| 2026-04-XX | Attacker bonds Thorchain validator |
| 2026-05-12 | Attacker submits malformed Paillier key during churn-in |
| 2026-05-15 | First signing ceremony with attacker — key extracted offline |
| 2026-05-15 | Drain executed across 4 chains, $10.8M lost |
| 2026-05-15 | rekt.news + community discovery via on-chain forensics |
| 2026-05-16 | Verichains confirms c-split variant via post-mortem |

---

## 10. References

### Code

- [thorchain/go-tss @ a87f3c2 (pre-incident)](https://gitlab.com/thorchain/tss/go-tss/-/tree/a87f3c2)
- [bnb-chain/tss-lib @ v1.4.2 (correctly patched)](https://github.com/bnb-chain/tss-lib/tree/v1.4.2)
- Post-incident fix commit: PENDING

### Academic

- Gennaro & Goldfeder, *Fast Multiparty Threshold ECDSA with Fast Trustless Setup* (2018, 2020 revision)
- Verichains, *TSSHOCK: Threshold Signature Scheme Vulnerabilities* (2022)
- Lindell, *Fast Secure Two-Party ECDSA Signing* (2017)

### BBT corpus

- [threat_models/tss_validator_extraction.yaml](../../threat_models/tss_validator_extraction.yaml) — captures this pattern
- [threat_models/post_bounty_variant_drift.yaml](../../threat_models/post_bounty_variant_drift.yaml) — captures meta-pattern
- [_audit_corpus/_known_findings.jsonl](../_audit_corpus/_known_findings.jsonl) entries: `tsshock-2022-alpha-shuffle`, `thorchain-2026-c-split`
- [_primers/tss_math_for_hunters.md](../_primers/tss_math_for_hunters.md) — math primer
- [foundry_corpus/crypto_tss/](../../foundry_corpus/crypto_tss/) — PoC templates including `c_split_simulation.go.template`

---

## Appendix A: Full PoC

See `foundry_corpus/crypto_tss/c_split_simulation.go.template` — adapt placeholders
для thorchain/go-tss specific structure (PartyID structure, ceremony coordinator).

## Appendix B: On-chain observations

Drain transactions (for forensics — DO NOT interact с addresses):
- BTC: `bc1q...` (Thorchain BTC vault → attacker BTC)
- ETH: `0x...` (Asgard ETH router → attacker ETH wallet)
- (Other chains: see public rekt.news post-mortem)

---

## Meta-section: How this paper was authored using BBT toolkit

[Documenting reproducible methodology — это лекция для future hunters using
toolkit. Standard papers omit this; BBT papers include it для educational reuse.]

1. **Initial discovery** — после X (Twitter) discussion of incident, ran:
   ```bash
   python3 scripts/web3/research/_check_active_targets.py  # picked up Thorchain news
   ```

2. **Hypothesis generation** — fed protocol context into:
   ```bash
   python3 scripts/web3/threat_models/apply.py --target sessions/thorchain
   ```
   Output included `tss_validator_extraction` model match, generating 3 hypotheses.

3. **Cross-diff confirmed asymmetry**:
   ```bash
   cd scripts/web3/research/_crypto_corpus
   python3 fetch.py
   python3 diff_critical_rounds.py
   # Report flagged: thorchain-go-tss missing biprime check в dlnproof
   #                 while bnb-chain/tss-lib has it
   ```

4. **PoC reproduction** через template:
   ```bash
   cp foundry_corpus/crypto_tss/c_split_simulation.go.template ./poc.go
   # Replace <TARGET_PACKAGE> = thorchain go-tss
   go test -run TestCSplit -v
   ```

5. **Peer review** через:
   ```bash
   python3 scripts/web3/findings_db/peer_review.py --paper this_paper.md
   ```

6. **Add to knowledge base**:
   ```bash
   python3 scripts/web3/research/_audit_corpus/fetch.py --add-finding \
       --id thorchain-2026-c-split --auditor verichains-postmortem \
       --year 2026 --severity critical \
       --classes "tss-paillier-bypass,key-extraction,gg20-soundness,sibling-variant-drift" \
       --target thorchain-go-tss \
       --siblings "other-gg20-forks,FROST-key-rotation"
   ```

Total time from initial X-post awareness to finalized paper draft: **3 working days**.
Без BBT toolkit: weeks (по own estimate from comparable manual hunts).

---

*This paper authored using BBT v[VERSION] paper methodology. See `_papers/_INDEX.md`.*
