# Display vs reality — checklist

The "UI says X, contract does Y" class. Often Medium severity but accumulates
into High when composed.

## Gas estimation

- [ ] UI shows "Estimated gas: X"
- [ ] Actual gas burned for the same flow?
- [ ] Nested approve+swap: estimate vs reality typically diverges 5-100x

## Token decimals

- [ ] UI displays "100 USDC" — uses 6 decimals
- [ ] Contract reads `amount` parameter — uses what decimals?
- [ ] Mismatch on non-standard tokens (WBTC = 8 dec, some stables = 18) = wrong amount signed

## ENS / SNS resolution

- [ ] User enters `vitalik.eth`, UI shows "vitalik.eth"
- [ ] Resolved address shown in confirmation?
- [ ] Same address shown in wallet popup?
- [ ] Look-alike names (`vita1ik.eth` with `1`) — does UI normalize or render raw?

## Slippage

- [ ] Default slippage = 0.5% or 1%?
- [ ] Warning when liquidity is thin and execution will exceed default?
- [ ] User can change but: is the limit honored at sign-time?

## Permit / Permit2 expiry

- [ ] UI says "Approve for 30 days"
- [ ] Signed deadline = 30 days? Or year 2038?
- [ ] "Forever" default = `MAX_UINT256` deadline = effectively eternal

## Blocklist / sanctions

- [ ] UI blocks transactions to sanctioned addresses?
- [ ] If UI shows "blocked" but user can bypass via direct contract call: UI is decorative
- [ ] Document gap between UI policy and on-chain enforcement

## Geolocation gating

- [ ] dApp blocks US users via Cloudflare worker?
- [ ] Bypass via custom headers? Direct contract call? VPN?
- [ ] OFAC compliance implications for the team

## Chain ID display

- [ ] dApp shows "Connected to Base"
- [ ] Wallet currently on Arbitrum
- [ ] Does dApp auto-switch? Reject? Show warning?

## Token approval simulator

- [ ] UI: "Estimated outcome: 100 USDC out"
- [ ] Simulation source: `eth_call` (live) or hardcoded estimate?
- [ ] Can attacker manipulate so estimate ≠ actual?

## Risk engine score

- [ ] TRM / Halliday / Witnesschain shows "Low risk"
- [ ] Decorative (UI only) or enforcing (blocks signing)?
- [ ] Document — even decorative-only is at least an Insight finding

## Approval display

- [ ] UI: "Approve 100 USDC"
- [ ] Signed `approve(spender, amount)` — `amount` is 100 USDC or max uint?
- [ ] Easy to verify: connect mock provider, observe params

## Recipient address

- [ ] UI: "Send to 0xabc...123"
- [ ] Wallet popup: same address or different?
- [ ] Address truncation: middle vs end (look-alike addresses exploit truncation)

## Severity calibration

- **High**: display difference enables user to sign for materially different amount/recipient
- **Medium**: display vs reality on warnings (slippage, blocklist, risk score)
- **Low**: cosmetic display issue (decimals, truncation aesthetics)

## How to verify

For each candidate:
1. Open dApp with mock provider (`eip1193_mock_provider.js`)
2. Perform the flow
3. Inspect actual `request({method, params})` calls
4. Compare params to UI display
5. Document divergence
