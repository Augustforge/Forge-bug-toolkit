# Specialized Checklist: Governance

## Proposal
- [ ] Proposal threshold > 0 (anti-spam)
- [ ] Proposal data validated at creation
- [ ] Proposal can't include malicious calldata bypassing review

## Voting
- [ ] Snapshot at proposal creation, not vote time (anti-flashloan)
- [ ] Vote weight = balance at snapshot block (not current)
- [ ] Quorum derived from snapshot supply (not current — anti-mint manipulation)
- [ ] Delegation snapshot included

## Timelock
- [ ] Minimum delay enforced (typically 2-7 days)
- [ ] Cancel function restricted to admin/governance
- [ ] Queued ops can't be modified

## Upgrade path via governance
- [ ] Upgrade proposals visible during timelock
- [ ] Upgrade calldata clear in proposal
- [ ] No emergency bypass that skips timelock

## Quorum manipulation
- [ ] Cannot inflate quorum via mint manipulation
- [ ] Burned tokens excluded from quorum base
- [ ] Vote against / abstain counted correctly

## Multi-sig backstop
- [ ] If multi-sig admin can act, it's documented
- [ ] Multi-sig key holders publicly known
- [ ] Multi-sig threshold > 50%

## Cheap majority + atomic execution (TOP 2026 class)
Snapshot/anti-flashloan (Voting §) catches BORROWED votes. This block is about a cheaply BOUGHT majority
+ atomic execution, without a flash loan.
- [ ] **Cost-to-acquire-majority << drainable-value** — calculate the market cost of 51%/quorum vs what
      the proposal can reach (treasury/mint/AMM exit). Tiny/illiquid `totalSupply()` = cheap.
- [ ] **Atomic create→vote→execute** — `votingDelay==0 && executionDelay==0 / no separate Timelock`
      → the whole cycle in one block (Aragon v1 Voting App). No reaction window.
- [ ] **Proposal can reach uncapped mint / treasury** (Cat 4.7) with an **AMM exit** (Balancer V1 /
      UniV2 without a circuit-breaker) → governance-capture → mint → drain.
- **Threat model:** [`threat_models/governance_capture_mint_drain.yaml`](../../threat_models/governance_capture_mint_drain.yaml)
  (apply.py instantiates per-target). Full checklist: [`checklists/governance.md` §6](../governance.md).
- **Cases:** Token of Power 2026 ($1.585M, cheap-buy); Beanstalk 2022 ($182M, flash-loan variant).
