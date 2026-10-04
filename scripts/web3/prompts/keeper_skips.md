# Prompt: Keeper Skips / Bot Inaction

Lens: protocol assumes external keeper/bot/cron triggers calls. What if keeper never calls? Calls late? Picks-and-chooses?

> Examples: Compound v3 liquidation timing, Yearn harvest delays, GMX keeper monopoly.

## Questions

1. **Who calls liquidation / harvest / update / settle?** Specific bonded keeper? Permissionless? Owner-only?
2. **What if keeper never calls?** Bad debt accumulates? Yield evaporates? Users stuck in expired positions?
3. **What if keeper calls late?** Liquidation at unfavourable price for borrower / lender?
4. **What if keeper calls only profitable?** Cherry-picks high-fee positions, leaves losing ones?
5. **What if keeper colludes with user?** Delays liquidation against user's competitor, accelerates own?
6. **Fallback**: permissionless emergency call after N hours of keeper inaction?
7. **Incentive alignment**: keeper paid in protocol token (subject to price collapse)? Keeper bond at stake?

## Keeper systems

- **Chainlink Automation (was Keepers)**: external network, paid in LINK
- **Gelato Network**: similar external
- **Self-keepers**: protocol-deployed bot (centralization)
- **Permissionless**: anyone can call (rare, often missing)

## Specific bug classes

- **Compound v3 class**: liquidator must call before bad debt — assumes keeper economically motivated. What if liquidation gas > reward?
- **Yearn harvest**: yield uncompounded if harvest skipped — losses accrue
- **GMX/perps**: funding rate updates — what if skipped during volatility?
- **Auction settlement**: what if settlement bot never calls? Auction stuck forever?
- **Position expiry**: option expiry settlement — keeper must call, what if doesn't?

## Output

1. **Function**: which keeper-callable function
2. **Keeper inaction scenario**: never / late / cherry-picked
3. **Loss accrual**: who loses funds and how fast
4. **Permissionless fallback**: exists? after how long?
5. **Severity**: usually Medium (slow loss) or High (fast cascade like cascading liquidations)

## Anti-pattern

Don't accept "Chainlink Keeper will call it" — what if the LINK price collapses and keeper economics break? What if the protocol's specific job is deprioritized?

---

## Source:

(paste protocol contracts with `external` keeper-callable functions — liquidations, harvests, updates, settlements)
