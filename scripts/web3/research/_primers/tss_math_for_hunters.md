# TSS/MPC Math for Bug Bounty Hunters

Цель: за 30 минут чтения дать non-cryptographer hunter'у достаточно intuition
чтобы понять Verichains TSSHOCK paper и видеть похожие классы в новых TSS
implementations. Это не replacement за PhD-cryptography, но достаточно для:

1. Понимания writeups типа TSSHOCK
2. Audit'а кода и видения "вот тут проверка отсутствует"
3. Discussion с cryptographer'ом на их языке когда нужна validation

---

## 1. Что такое TSS / threshold signature

Обычная signature: один private key `d`, владелец подписывает.

TSS: private key `d = d_1 + d_2 + d_3 + ... + d_n mod q` (split across n parties).
Никто не знает `d` целиком. Чтобы подписать transaction нужно threshold-of-n
parties кооперироваться. После ceremony появляется valid ECDSA/EdDSA signature.

**Important**: ceremony не reconstructs `d` ever. Если bug позволяет одной party
recover `d` или другую `d_i` — это **catastrophic** (worth bounty $500K-$10M).

Protocols используемые в practice:
- **GG18** (Gennaro-Goldfeder 2018) — ECDSA threshold, foundational
- **GG20** — GG18 с improvements (proactive refresh, simpler abort handling)
- **CGGMP21** — современный variant, лучше security proofs
- **FROST** — Ed25519/Schnorr threshold, не ECDSA

---

## 2. Paillier cryptosystem (heart of GG18/GG20)

Paillier = additively homomorphic encryption. Key property:
```
Enc(a) * Enc(b) = Enc(a + b)
```

Это позволяет parties суммировать encrypted shares **не раскрывая** значений.
Используется в **MtA** round signature ceremony (Multiplicative-to-Additive
conversion) — там где multiplication `k * gamma` нужно превратить в sum
без disclosure individual shares.

### Setup Paillier key

```
1. Choose two large primes p, q (~1024 bits каждый)
2. N = p * q                              (~2048 bits)
3. λ = lcm(p-1, q-1)
4. Public: (N, g=N+1)
5. Private: (λ, μ)
```

### Critical safety property: BIPRIME

**N MUST be product of exactly 2 safe primes.** Если adversary submits
`N = p*q*r` (3 primes) или `N = p^2 * q` (composite power) — Paillier
arithmetic still "works" в narrow sense (encryption/decryption don't error),
**но** discrete-log subgroup structure меняется. Adversary позже может factor
encrypted values из MtA proofs.

### Что искать в коде

```go
// CORRECT (Binance tss-lib post-fix):
func (sk *PrivateKey) IsBiprime() bool {
    // Probabilistic check: N has exactly 2 prime factors
    // Standard approach: compute gcd, do trial divisions, etc.
}

// VULNERABLE (если эта функция не вызывается на keygen round 1):
func ValidatePeerPaillierKey(pubKey *PublicKey) error {
    if pubKey.N.BitLen() < 2048 { return error }
    // ↑ ТОЛЬКО bitlen check, нет biprime check → TSSHOCK class
}
```

**Hunting tip**: `grep -ri "biprime\|safe.*prime\|p\*q" target-tss/`. Если 0
matches в keygen package — это **immediate critical hypothesis**.

---

## 3. ZK proofs of knowledge (где iterations важны)

В TSS parties доказывают друг-другу разные statements without disclosing
witnesses. Например: "Я знаю factorization N" (without revealing p,q).

Большинство ZK protocols имеют structure:
```
Prover:    выбирает t случайных witnesses w_1, ..., w_t
           публикует commitments C_1, ..., C_t
Verifier:  посылает random challenges c_1, ..., c_t
Prover:    отвечает r_1, ..., r_t (using witnesses + challenges + secret)
Verifier:  checks all (C_i, c_i, r_i) tuples valid
```

**Soundness**: probability что cheating prover convinces honest verifier =
`(1/2)^t`. Чтобы это было negligible нужно `t >= 80` (Fiat-Shamir transform)
или `t >= 128` (more conservative).

### TSSHOCK class attack

В Verichains 2022 finding: Binance tss-lib had `modproof.Iterations = 80`
и `dlnproof.Iterations = 128`. Adversary крафтит modproof с `iterations = 80`
**но** в специфическом structural way — multiproof construction позволяет
adversary "достроить" 48 missing iterations offline. Effective soundness = 50%.
После 20-30 signing ceremonies adversary имеет full key.

### Что искать

```go
// VULNERABLE:
const Iterations = 80
// или ещё хуже:
const Iterations = 1
// или (most insidious):
iterations := config.GetInt("zk_iterations", 80)  // user-configurable!

// CORRECT:
const ZKProofIterations = 128  // hardcoded, не configurable
```

Grep: `grep -rn "Iterations\s*=" target-tss/`. Всё ниже 80 — critical. Всё
configurable — high (kennt as a config bug).

---

## 4. Fiat-Shamir transform (challenge derivation)

Interactive ZK protocols (см. выше) делают non-interactive через Fiat-Shamir:
```
challenge = Hash(public_inputs || commitments || party_ids || session_id)
```

**Critical**: hash MUST include **all** public context. Если только commitments
hashed (forgotten session_id или party_ids) — adversary может replay challenges
across sessions / pre-compute responses.

### Что искать

```go
// VULNERABLE (challenge без session binding):
challenge := sha256.Sum256(commitments)

// CORRECT:
hasher := sha256.New()
hasher.Write(sessionID[:])
hasher.Write(partyID[:])
hasher.Write(commitments)
hasher.Write(otherPublicInputs)
challenge := hasher.Sum(nil)
```

Grep: `grep -rn "Hash\|sha256\|fiatShamir" target-tss/ZK*/` and verify каждый
hash включает session/party context.

---

## 5. MtA — где critical attacks происходят

Most TSS attacks (incl. TSSHOCK) случаются в **Multiplicative-to-Additive**
round signing ceremony. Setup:
- Alice has share α
- Bob has share β
- Они хотят compute α*β без disclosure

```
Alice: encrypts α via Paillier → ciphertext c_α = Enc(α)
       sends c_α to Bob
Bob:   chooses random β', computes c_β = c_α^β * Enc(β') = Enc(αβ + β')
       sends c_β back to Alice + ZK range proof for β
Alice: decrypts → gets αβ + β' = "additive share" of αβ
       Bob keeps β' = другая "additive share"
       Sum α'  + β' = αβ (sum across parties = product)
```

### Где attacks происходят

1. **Bob's range proof on β** — если weak/missing, Alice не может verify что
   β was "small". Bob может submit huge β → Alice's decryption переполнит,
   leak structure.

2. **Alice's Paillier key biprime** — если N malformed, Bob's encryption
   produces ciphertext который adversary потом factor'ит offline → recover α.

3. **Modular reduction missing** — share aggregation `α + β'` MUST be `mod q`
   (curve order). Без mod операции — leak high bits.

### Grep patterns

```bash
grep -rn "MtA\|mta\|MtAwc" target-tss/        # MtA implementations
grep -rn "range.*proof" target-tss/             # range proof presence
grep -rn "\.Mod(" target-tss/sign*/              # modular reductions
```

---

## 6. Honest-but-curious vs malicious-but-bonded

Standard cryptography assumes "honest-but-curious" adversary — follows protocol
honestly, tries to learn additional info. **Real-world TSS**: bonded validators
могут быть **fully malicious** — deviate from protocol arbitrarily, submit
malformed messages.

GG18/GG20 papers prove security under malicious model **только если** все
specified checks implemented. Если implementation skips a check (because
"it never happens in practice") — security proof не applicable.

### Hunting heuristic

Для каждой function в keygen/signing rounds задайся вопросом:
> "Если этот input came from malicious actor — что worst case?"

Если ответ "validation у нас есть в строке X" — окей.
Если ответ "ну, не должно такого быть" — **likely vulnerability**.

---

## 7. Concrete hunting recipe

Given a TSS implementation `path/to/target/`:

```bash
# Step 1. Find all critical guards
cd path/to/target
grep -rn "biprime\|safe.*prime"  > biprime_checks.txt
grep -rn "Iterations\s*=\s*\d"   > iterations_constants.txt
grep -rn "RangeProof\|range_proof" > range_proofs.txt
grep -rn "MtA\|mta"              > mta_usage.txt

# Step 2. Cross-diff vs reference implementations
cd $BBT/scripts/web3/research/_crypto_corpus
python3 fetch.py
python3 diff_critical_rounds.py --output diff.md
# Open diff.md — look for asymmetries

# Step 3. Map findings to known classes
cd $BBT/scripts/web3/research/_audit_corpus
python3 fetch.py --list
# Match grep'ed gaps против _known_findings.jsonl

# Step 4. For each candidate vulnerability:
cp $BBT/scripts/web3/foundry_corpus/crypto_tss/<TEMPLATE>.go.template ./poc.go
# Replace placeholders, run `go test`
# Если test fails как ожидается if-vulnerable — submit
```

---

## 8. Что НЕ делаем без cryptographer review

- **Custom Paillier implementation** — никогда не "fix самостоятельно", всегда use
  well-vetted lib. Reverse: если target uses custom Paillier — что-то tier-1 audited?
- **New ZK protocol claims** — если protocol claims novel ZK scheme, не trust
  без external academic review
- **Modified GG20 variants** — fork с "optimizations" = red flag. Optimizations
  often break security proofs

---

## 9. Дальнейшее чтение (when serious about TSS)

Mandatory papers (читать после этого primer):

1. **Gennaro & Goldfeder 2018** — "Fast Multiparty Threshold ECDSA with Fast Trustless Setup"
2. **Verichains TSSHOCK writeup** (2022) — full attack chain explanation
3. **Lindell 2017** — "Fast Secure Two-Party ECDSA Signing"
4. **CGGMP21** — "UC Non-Interactive, Proactive, Threshold ECDSA with Identifiable Aborts"

Books:
- Boneh & Shoup, **A Graduate Course in Applied Cryptography** (free online)

Codebases для reading:
- Binance tss-lib (Go, well-commented)
- Coinbase Kryptology (Go, modern style)

---

## Cross-link

- [checklists/specialized/tss_mpc.md](../../checklists/specialized/tss_mpc.md) —
  manual checklist для actual review
- [threat_models/tss_validator_extraction.yaml](../../threat_models/tss_validator_extraction.yaml) —
  machine-checkable patterns
- [foundry_corpus/crypto_tss/](../../foundry_corpus/crypto_tss/) — PoC templates
- [_crypto_corpus/](../_crypto_corpus/) — implementations для cross-diff
- [_audit_corpus/_known_findings.jsonl](../_audit_corpus/_known_findings.jsonl) — historic findings
- [_papers/thorchain_2026_tsshock.md](../_papers/thorchain_2026_tsshock.md) — worked case study
