# Specialized Checklist: AMM (Uniswap V2/V3/V4, Curve, Balancer)

## V2 (constant product)
- [ ] TWAP window > 30 minutes
- [ ] Reserves read via `getReserves()`, NOT `balanceOf(this)` (donation attack)
- [ ] No same-token pairs allowed

## V3 (concentrated liquidity)
- [ ] Observation cardinality > 1 if used as oracle
- [ ] Tick math: `TickMath.MIN_TICK` / `MAX_TICK` bounds checked
- [ ] sqrtPriceX96 overflow handled
- [ ] JIT liquidity: fee model accommodates
- [ ] Single-tick liquidity manipulation defended

## V4 (hooks)
- [ ] Hook callbacks authorized (`onlyPoolManager`)
- [ ] Hook can't drain user funds via callbacks
- [ ] BalanceDelta math verified

## Curve
- [ ] Read-only reentrancy: `get_virtual_price` after `remove_liquidity` lock
- [ ] A coefficient transitions handled
- [ ] Removal slippage favors LP not attacker

## Balancer
- [ ] Same as Curve r/o reentrancy
- [ ] WeightedPool math verified
- [ ] PoolManager auth strict

## Generic
- [ ] Slippage tolerance enforced
- [ ] Deadline checked
- [ ] No oracle from single shallow pool
