# Specialized Checklist: DEX Aggregators (1inch, Paraswap, Cowswap, Dirol)

## Routing trust
- [ ] minOut computed by contract, not just trusted from API
- [ ] OR: user sees final minOut in calldata before signing
- [ ] User-visible slippage matches actual on-chain enforcement

## Per-hop slippage
- [ ] Each hop has its own slippage check OR
- [ ] Final-only check is adequate (math verified)
- [ ] Multi-hop atomic — fail if any hop reverts

## Calldata injection
- [ ] User-provided routes validated (no arbitrary call)
- [ ] If "smart wallet" mode — strict allowlist of callable contracts

## Fee accrual
- [ ] Protocol fee transparent in user-facing quote
- [ ] No hidden slippage absorbed as fee
- [ ] No double-fee (protocol + spread)

## Recipient handling
- [ ] Recipient != 0x0
- [ ] Recipient != contract itself (UX shoot-foot prevention)
- [ ] Recipient signed by user

## Native token handling
- [ ] WETH wrap/unwrap correctly
- [ ] msg.value matches expected
- [ ] No double-spend if reverts mid-flow
