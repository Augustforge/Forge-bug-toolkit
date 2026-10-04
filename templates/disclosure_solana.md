# Solana Vulnerability Disclosure Template (Immunefi format)

<!-- WRITING DISCIPLINE (bullet-brevity — pashov report-formatting, [[reference_pashov_skills]] block I):
     The `file:line` ref + code snippet + PoC ARE the evidence. Prose must NOT re-narrate the code.
     Impact/root-cause in 1-2 sentences; steps one line each (concrete account/value/state); fix as a
     diff where possible. Reviewer grasps the bug from code-ref + one sentence — rest is support.

     🔴 AOE DISCLOSURE-STRIP (§5.5 — infohazard guard): ship ONLY the minimal on-chain bug + PoC-fact.
     Do NOT attach, paste, or summarize `sessions/{target}/actor_payoff.md` or the full multi-actor
     equilibrium recipe, and do NOT include modeled offensive links (Sybil / flood / social-eng). A ready
     multi-actor playbook is an infohazard — the team needs the single bug + fix, not the game-theory recipe. -->

## Summary

**Vulnerability Name**: <short descriptive title>
**Protocol**: <Protocol Name>
**Program ID**: `<base58 address>`
**Chain**: Solana mainnet (or eclipse/sonic/etc.)
**Severity**: Critical / High / Medium / Low
**Hypothesis class**: <broader class name, e.g. "Any-account spoofing">
**Classification**: `[novel_instance]` / `[known_class]`

## Impact

<What can be drained / who suffers / how much $ at risk>

**Funds at risk**: $<estimated USD>
**Loss type**: direct drain / permanent freezing / temporary freezing / griefing / unauthorized mint

## Attack Path

### Pre-conditions

- <state required for attack>

### Steps

1. <step 1 — what attacker does>
2. <step 2>
3. <step 3>
4. <final outcome>

### Sample Transaction Flow

```
attacker_keypair: A1...
victim_protocol:  P1...
target_account:   T1...

Tx 1: <instruction with malicious account substitution>
Tx 2: <follow-up to extract value>
```

## Root Cause

<File>: `path/to/program.rs:LINE`

```rust
// Vulnerable code
<paste relevant code>
```

**Issue**: <explain why this is broken>

**Expected behavior**: <what should be checked>

## Recommended Fix

```rust
// Patched code
<paste fix>
```

**Why this fixes**: <explain>

## PoC

Foundry-style PoC using `solana-program-test`:

```rust
// tests/exploit_test.rs
#[tokio::test]
async fn test_exploit() {
    let mut ctx = setup_test_context().await;
    // ... reproduce attack
    assert_eq!(victim_balance_after, 0);
    assert_eq!(attacker_balance_after, drained_amount);
}
```

Reproduction:
```bash
cargo test --package <pkg> test_exploit
```

## References

- Threat intel: `scripts/sol/threat_intel.md` (similar class)
- Broader class: `scripts/sol/HIGH_VALUE_PATTERNS_SOL.md#<pattern>`
- Detection tool: `scripts/sol/hypothesis/<script>.py`

## Severity Rationale (Immunefi Solana)

- **Critical**: <$X funds at risk, no preconditions, single attacker>
- Verified threat tier: <T1-T6 from THREAT_ACTOR_MODELS>

## Submission Details

- Submitted via: Immunefi / Sec3 / direct
- Date: <YYYY-MM-DD>
- Hunter: <our pseudonym>
- KYC: <yes/no>
- Wallet for payout: <separate from hunting wallet>
