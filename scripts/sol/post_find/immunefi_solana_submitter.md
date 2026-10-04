# Immunefi Solana Submission Guide

Solana submissions on Immunefi differ from EVM. This is a checklist + template.

## Pre-Submission Checklist

- [ ] **Severity calculation done** — TVL-at-risk numbers, not subjective
- [ ] **PoC verifies on local fork** — `solana-test-validator --clone PROGRAM_ID --url mainnet-beta`
- [ ] **Bytecode hash matches** — verified program bytecode on mainnet identical to your testing target
- [ ] **Anchor IDL accounted for** — if protocol uses Anchor, attach IDL to submission (helps triager)
- [ ] **No mainnet exploitation** — all tests on localnet/devnet only
- [ ] **OPSEC** — submission handle != on-chain payout wallet
- [ ] **Time-to-fix estimated** — `disclosure_timeline.py` output attached

## Solana-Specific Fields Immunefi Expects

| Field | EVM equivalent | Solana value |
|---|---|---|
| Smart contract address | Contract address | **Program ID** (44 chars, base58) |
| Network | Mainnet/Goerli/etc | Mainnet/Devnet/Testnet |
| Function | Solidity function | **Instruction discriminator** (8-byte) + handler name |
| Caller | msg.sender | **First signer account** OR PDA via `invoke_signed` |
| Affected funds | Token contract addr | **Token mint** (44 chars) + **vault PDA** |
| Compiler version | Solidity 0.8.x | **Anchor 0.30.x / 0.31.x** + Rust version |

## Severity Argument Template

**For Critical (>$50k typical):**

```
Severity: Critical
TVL at risk: $X.X M (verified via `tvl_check.py --protocol PROGRAM_ID --chain Solana`)
Attack cost: $X (verified via `economic_analysis.py --chain solana`)
Profit margin: X× (attack_cost vs at_risk)
Time to fix: X hours (single instruction, isolated change)
Race window: X hours (other hunters' likely discovery time)

Threat actor required: [Script kiddie / MEV searcher / Sophisticated]
Capital required: $X (flash loan source: Kamino/Marginfi/Solend)
Reproducibility: 100% on fork at slot Y
```

## PoC Format Immunefi Prefers

1. **solana-program-test Rust file** (not just description) — sufficient for triage
2. **Foundry test in equivalent EVM** if cross-chain bug
3. **Step-by-step ProgramTest** — load mainnet state, execute exploit, assert drain
4. **Numeric assertions** in test — `assert!(vault_balance_after < vault_balance_before - drain_amount);`

Example PoC structure:
```rust
#[tokio::test]
async fn exploit_loopscale_cpi_program_id() {
    let mut pt = ProgramTest::new("loopscale", LOOPSCALE_PROGRAM_ID, processor!(...));
    pt.add_account(victim_pda, mainnet_state_account);
    let (mut banks, payer, blockhash) = pt.start().await;

    let exploit_tx = build_exploit_tx(&payer, FAKE_RATE_X_PROGRAM, victim_pda);
    let result = banks.process_transaction(exploit_tx).await;
    assert!(result.is_ok(), "Exploit should succeed pre-fix");

    let final_balance = banks.get_account(VAULT).await.unwrap().lamports;
    assert!(final_balance < initial_balance, "Vault drained");
}
```

## Fix Recommendation Format

Always include:
1. **Diff format** — `- bad line` / `+ good line` style
2. **Rationale** — why fix works, what invariant it restores
3. **Coverage check** — same pattern in other instructions? List all that need same fix
4. **Test recommendation** — invariant test that would have caught this

Example:
```rust
// In loopscale src/lib.rs:get_pt_price()
- let rate_x_state = RateXState::try_from_slice(&accounts[3].data.borrow())?;
+ require_keys_eq!(*accounts[3].owner, RATE_X_PROGRAM_ID, ErrorCode::InvalidProgramOwner);
+ let rate_x_state = RateXState::try_from_slice(&accounts[3].data.borrow())?;
```

## Disclosure Timeline (attach to submission)

```
Day 0  - Discovery (date+slot)
Day 0  - PoC verified on fork (date+commit)
Day 0  - Severity calculated (TVL snapshot date)
Day 0  - Submission to Immunefi (this submission)
Day 1  - Expected triage response
Day 7  - Expected severity confirmation
Day 21 - Expected fix deployment
Day 30 - Coordinated public disclosure
Day 90 - Full disclosure regardless of fix status (per Immunefi rules)
```

## Common Mistakes To Avoid

- **Posting program ID + bug class on Twitter** — disclosure violation, kills payout
- **Submitting before PoC works** — triager will close as unconfirmed
- **Asking for severity confirmation first** — submit with severity argument, not "what do you think"
- **Including main wallet in writeup** — even as "non-attacker" mention, links your identity
- **Speculating about fix in code** — Immunefi triagers don't want unsolicited code review
- **Cross-posting to Sec3** during Immunefi triage — double-dipping violates ToS

## Reputation Building

Track on `sessions/_methodology/reputation.md`:
- Immunefi Whitehat Level (1-5)
- Sec3 audit comp finishes (rank + winnings)
- Acknowledged-but-unpaid disclosures (still counts for rep)
- Time-to-triage average (your submission quality signal)
