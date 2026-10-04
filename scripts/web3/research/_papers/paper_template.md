# [Vulnerability Title]: [One-line technical descriptor]

**Target**: [Protocol/library name + version/commit SHA]
**Class**: [Bug class taxonomy, e.g., "TSS Paillier biprime bypass"]
**Severity**: [Critical | High | Medium]
**Discovered by**: [Hunter name + handle]
**Disclosed to**: [Bounty platform + protocol team]
**Disclosure date**: [YYYY-MM-DD]
**Public release**: [YYYY-MM-DD or "embargoed until fix landed"]

---

## 1. Executive Summary

[1 paragraph, 3-5 sentences. Must answer: what bug, what impact ($X loss possible),
how exploited (one sentence), what mitigation. Reader должен decide в 30 seconds
relevant ли это им.]

**Example**:
> A malicious threshold-bonded validator in [PROTOCOL]'s TSS network can extract
> the full Asgard vault private key after participating in 1-2 signing ceremonies,
> via a c-split variant of the TSSHOCK attack class. The Paillier key biprime
> validation introduced in 2022 was applied to one ZK proof variant but not its
> sibling, leaving a 4-year regression window. Estimated maximum loss equals
> the full vault TVL ($X). Mitigation requires applying biprime check uniformly
> across all ZK proof types и hardcoding iterations >= 128.

---

## 2. Background

[2-4 paragraphs. Explain the affected primitive для reader who is general
security engineer but not specialist в этом domain. Cite seminal papers где
relevant.]

Subsections:
- 2.1 What is [primitive]
- 2.2 How [protocol] uses [primitive]
- 2.3 Threat model assumed by protocol designers

[Goal: by end of section, reader понимает enough контекста to evaluate Section 3.]

---

## 3. Vulnerability Description

[Pure description root cause. No attack chain yet. Reader должен понять "вот
эта строка / эта проверка / это design choice = bug" в isolation.]

### 3.1 Root cause

[Concrete code reference: `file.go:LINE` showing missing/incorrect check.]

```go
// VULNERABLE code (lines NN-MM в file.go):
func ValidatePeerPaillierKey(pubKey *PublicKey) error {
    if pubKey.N.BitLen() < 2048 {
        return ErrKeyTooSmall
    }
    // BUG: no biprime check. Adversary submits N = p*q*r (3 primes)
    return nil
}
```

### 3.2 Why this is unsafe

[Math/logic explanation. Если adversary submits malformed input X, what
property breaks. Не attack chain yet — just "the protocol invariant violated is Y".]

### 3.3 What the protocol designers assumed

[Часто bug = silent assumption. State it explicitly.]

---

## 4. Attack Flow

[Step-by-step. Каждый step с code references + what attacker sees.]

### Setup
- [Required attacker resources: bonded stake amount, hardware, network access]
- [Required victim state: configuration, balances]

### Steps

1. **[Step name]** ([code reference])
   - What attacker does: [...]
   - What honest parties see: [...]
   - What goes wrong: [...]

2. **[Step name]** ([code reference])
   - ...

[Continue до full exploit.]

### PoC

```
# Reproduction
git clone <target-repo>
cd <target-repo>
git checkout <commit-sha>
# Apply diff from poc.go (attached)
go test -run TestPoC -v

# Expected output if bug present:
# [exact output snippet]
```

---

## 5. Impact Analysis

[Quantify worst case. Not just "$X loss" — also reputational, ecosystem.]

### 5.1 Direct financial impact

| Component | Value at risk |
|---|---|
| [Component A] | $XXM |
| [Component B] | $YYM |
| **Total** | **$ZZM** |

### 5.2 Indirect impact

- [Confidence in protocol после disclosure]
- [Affected downstream protocols using same primitive]
- [Regulatory / legal exposure]

### 5.3 Likelihood

[Concrete: какие preconditions attacker needs? Stake $5M? Network access? Specific
timing? Estimate exploit cost vs potential payout.]

---

## 6. Affected Implementations

[Not just "version X has bug". List every fork / variant which inherits.]

| Implementation | Affected? | Verified | Notes |
|---|---|---|---|
| Reference implementation | YES | confirmed | Lines NN-MM |
| Fork A | YES | confirmed | Inherited без modification |
| Fork B | LIKELY | not tested | Used same parent commit |
| Fork C | NO | confirmed | Already patched in commit XYZ |

---

## 7. Sibling Variants

[**Critical section** — это где paper distinguishes itself from short reports.
Каждое bug — instance of class. List sibling variants which should be checked,
even if не confirmed.]

### 7.1 Variant A: [name]

Pattern: [if THIS bug present, then SIBLING pattern likely exists in module Y]

How to check: [`grep -r "pattern" target/module_y/`]

### 7.2 Variant B: [name]

...

### 7.3 Class-level recommendation

[For protocols using same primitive: re-audit holistically, не just patch this specific.]

---

## 8. Mitigation

### 8.1 Immediate patch

[Concrete code suggestion. Diff format где possible.]

```diff
 func ValidatePeerPaillierKey(pubKey *PublicKey) error {
     if pubKey.N.BitLen() < 2048 {
         return ErrKeyTooSmall
     }
+    if !pubKey.IsBiprime() {
+        return ErrNotBiprime
+    }
     return nil
 }
```

### 8.2 Defensive depth

[Beyond minimum patch: what additional safeguards reduce future class regression risk?]

### 8.3 Process recommendations

[For protocol team: testing/audit process changes preventing this class.]

---

## 9. Disclosure Timeline

| Date | Event |
|---|---|
| YYYY-MM-DD | Vulnerability discovered via [method] |
| YYYY-MM-DD | Reproduction PoC complete |
| YYYY-MM-DD | Reported to protocol team via [channel] |
| YYYY-MM-DD | Protocol team acknowledged |
| YYYY-MM-DD | Patch deployed in commit [SHA] |
| YYYY-MM-DD | Bounty awarded ($X) |
| YYYY-MM-DD | Public disclosure |

---

## 10. References

### Code

- [Vulnerable repository @ commit]
- [Reference safe implementation @ commit]
- [Patch commit]

### Academic

- [Original cryptographic paper if primitive bug]
- [Related auditor writeups]

### Cross-link to BBT corpus

- threat_models/[matched_model].yaml
- _audit_corpus/_known_findings.jsonl entry: [id]
- _crypto_corpus/repos/[reference_impl]

---

## Appendix A: Full PoC code

[Attach poc.go / poc.sol with все imports / setup / assertions.]

## Appendix B: Network observations

[Если applicable: on-chain tx, addresses, timing patterns observed.]

---

*Generated using BBT paper methodology. See _papers/_INDEX.md.*
