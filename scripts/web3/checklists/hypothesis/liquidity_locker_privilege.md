# Liquidity Locker / Vesting / Escrow — Privileged Unlock Checklist

Pattern: a pooled-custody contract holds MANY users' LP/tokens under a "locked /
immutable" promise, but exposes owner-controlled lock parameters → owner (or whoever
inherits/compromises ownership) releases everyone's funds.

Reference: **DxSale/DxLock $7.3M (28-29.05.2026)** — `setFee(1 wei)` + lock expiration
backdated to 68s after Unix epoch → batch withdrawal of 1,400 LPs. Decurity reported the
SAME class in 2023 (paid $500; "fix" = raise fee = configurational, bypassed via setFee).
→ **This class is findable AND reportable.**

Tool: `scripts/web3/hypothesis/liquidity_locker_privilege_scanner.py`
Threat model: `scripts/web3/threat_models/liquidity_locker_privileged_unlock.yaml`

## When to apply
Target is a liquidity locker, LP locker, token vesting/escrow, launchpad lock, or any
contract holding third-party tokens with time-based release. Tags: `locker`,
`liquidity_lock`, `vesting`, `escrow`, `custody`.

## Checklist
1. [ ] **Custody model:** pooled (one contract holds many projects' LP) or isolated per-lock? Pooled = blast radius = ALL deposits.
2. [ ] **Mutable lock params:** owner-only `setFee` / `setLockTime` / `setUnlockTime` / `extendLock` / `relock`? Do they affect ALREADY-created locks, not just new ones?
3. [ ] **Timestamp validation:** is `unlockTime` validated as future at creation? Can owner set it to the past / epoch? (DxSale: 68s after epoch)
4. [ ] **Emergency/migrate path:** `emergencyWithdraw` / `adminWithdraw` / `rescue` / `migrate` that moves locked assets out, bypassing per-user lock records?
5. [ ] **Owner classification:** EOA / Safe(threshold) / Timelock? Run scanner `--rpc --contract`. EOA over pooled custody = Nakamoto 1.
6. [ ] **Timelock/multisig on admin ops:** any `TimelockController` gating the setters? (absence = instant param mutation)
7. [ ] **Ownership history (leading indicator):** read `OwnershipTransferred` events. Silent transfer + dead project + live TVL = DxSale precondition. (Cross-ref `ownership_transfer_monitor.py`.)

## Confirmation
- Trace one user's lock record → show owner can mutate fee/timestamp → unlock becomes satisfiable → withdraw reachable for an account that is not the depositor.
- Foundry fork: deposit as victim → as owner call `setUnlockTime(past)` / `setFee(1)` → withdraw victim's LP.

## Severity rubric
| Finding | Default |
|---|---|
| Owner can mutate existing locks' unlock time / fee → release others' funds | Critical |
| Privileged emergency-withdraw of pooled custody | Critical |
| unlockTime backdatable to past/epoch | High-Critical |
| EOA owner over pooled custody (no timelock) | High *(centralization; program-dependent — see triage monetization)* |
| Low-threshold Safe owner | Medium-High |

## Cross-refs
- `compromised_admin_unconstrained_mint.yaml` (token mint, different surface)
- `ghost_contract_legacy_approvals.yaml` (abandoned + approvals; sibling for legacy lockers — H11)
- triage: `dapphunt/prompts/hypothesis_triage_dapp.md` (custody pre-mortem + monetization routing)
