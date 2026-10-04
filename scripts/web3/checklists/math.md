# Math Vulnerabilities Checklist (9 patterns) — Immunefi V02 + V06

## 1. Integer over/underflow (pre-0.8.0)
- [ ] Solidity version < 0.8.0 without SafeMath
- [ ] `unchecked { }` blocks in Solidity ≥ 0.8 (they disable the auto-check)
- [ ] Cast int256 → uint256 of a negative value → huge positive

## 2. Precision loss (division before multiplication)
- [ ] `(x / y) * z` instead of `(x * z) / y`
- [ ] Loss grows when y > x
- **Pattern in code:**
  ```solidity
  fee = (amount / FEE_DENOM) * FEE_NUMER;  // ❌ precision loss
  fee = amount * FEE_NUMER / FEE_DENOM;    // ✅ correct
  ```

## 3. Rounding direction
- [ ] When calculating shares for a user → round **down** (favor protocol)
- [ ] When calculating debts owed to the protocol → round **up**
- [ ] Mistake = the protocol loses dust → accumulates into large sums
- **Real case:** Compound rounding errors cost millions

## 4. Decimals mismatch (8 vs 18 vs 6)
- [ ] WBTC = 8 decimals, USDC = 6, ETH = 18
- [ ] The contract scales assets incorrectly
- **Pattern:** `wbtcAmount * usdcAmount` without normalization → off-by-1e10/12

## 5. Fixed-point math
- [ ] FixedPointMathLib / PRBMath / custom is used
- [ ] `mulDiv(a, b, c)` vs naive `a * b / c` — overflow protection
- [ ] FixedPoint96 vs FixedPoint128 — Uniswap V3 specifics

## 6. Signed vs unsigned conversions
- [ ] `int256(uint256_value)` — a large uint becomes negative
- [ ] `uint256(int256_value)` — a negative becomes huge
- [ ] Slither sometimes detects `cast.uint256-int256`

## 7. Multiplication overflow in unchecked
- [ ] `unchecked { x * y }` without a bounds check
- [ ] Slither: `incorrect-shift` for bitshift overflow
- [ ] `2**256` overflow scenarios

## 8. Zero division
- [ ] `x / 0` reverts in Solidity, but the check should be **before**
- [ ] When totalSupply == 0 — DOS (if it depends on totalSupply > 0)
- [ ] Edge case in lending pools at 0 deposits

## 9. Round-trip rounding (deposit-withdraw)
- [ ] Deposit computes `shares = amount * totalShares / totalAssets`
- [ ] Withdraw computes `amount = shares * totalAssets / totalShares`
- [ ] If both round down → an attacker deposits → withdraws → loses 1 wei
- [ ] **Inflation attack** — the first depositor can skew the rate
- **Real case:** ERC4626 vault inflation attacks

---

## Property-based tests (Foundry/Echidna)

```solidity
// Inflation attack property
function invariant_FirstDepositorCannotInflate() public {
    // if the first depositor deposits 1 wei,
    // the next depositor with 1 ether must not lose > 1 wei
}

// Round-trip property
function invariant_DepositWithdrawRoundTrip(uint256 amount) public {
    uint256 shares = vault.deposit(amount);
    uint256 redeemed = vault.redeem(shares);
    assertGe(amount, redeemed);  // user doesn't get more than they put in
    assertLe(amount - redeemed, 1);  // loss at most 1 wei
}
```

## Solodit search keywords
`rounding`, `precision`, `inflation attack`, `division before multiplication`, `decimals`, `fixed-point`, `ERC4626 vault`
