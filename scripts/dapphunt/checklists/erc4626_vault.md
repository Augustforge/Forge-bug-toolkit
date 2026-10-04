# ERC-4626 vault — checklist

Use when target is a tokenized vault (ERC-4626), Yearn-style strategy, LP vault,
liquid staking wrapper, or Compound v2 cToken-fork.

**Why this checklist exists:** First-depositor inflation attack (Hundred Finance,
$7M, 2023). Audited code still ships this class. OpenZeppelin added `_decimalsOffset()`
in v4.9 but defaults are still attackable without protection.

## Identify the vault type

- [ ] Standard ERC-4626 (has `deposit`/`mint`/`withdraw`/`redeem` + `totalAssets`)?
- [ ] Compound v2 cToken fork (has `mint`/`redeem` + `exchangeRateCurrent`)?
- [ ] Yearn v2/v3 vault (has `deposit`/`withdraw` + `pricePerShare`)?
- [ ] Custom — read source carefully

## First-deposit protection

- [ ] Does the contract burn dead shares (e.g., 1e3) on first deposit?
- [ ] Does the constructor / initializer pre-mint shares to address(0)?
- [ ] Is there a minimum first deposit enforced?
- [ ] Is the initialDeposit locked / unwithdrawable?
- [ ] If using OZ v4.9+: what's `_decimalsOffset()`? Default 0 = still vulnerable without other protection

## Donation surface

- [ ] Does `totalAssets()` return `IERC20(asset).balanceOf(address(this))`?
- [ ] If YES → vulnerable to direct-transfer donation
- [ ] If internal accounting (e.g., `_totalAssets` variable updated on deposit/withdraw) → donation-immune
- [ ] Check for "skim" or "sweep" functions that might re-introduce balanceOf dependency

## Share math rounding

- [ ] `_convertToShares` rounds DOWN (Math.Rounding.Down or Floor)?
- [ ] `_convertToAssets` for `withdraw` rounds UP (Math.Rounding.Up or Ceiling)?
- [ ] `deposit`: user supplies assets → shares = down (favors protocol)
- [ ] `mint`: user supplies share-count → assets = up (favors protocol)
- [ ] `withdraw`: user requests assets → shares = up (favors protocol)
- [ ] `redeem`: user supplies shares → assets = down (favors protocol)
- [ ] **Any inversion = arbitrage primitive**

## Rebasing / fee-on-transfer underlying

- [ ] Underlying asset properties:
  - Rebasing? (stETH, USDR, aToken)
  - Fee-on-transfer? (STA, certain reflection tokens)
  - Inflationary? (auto-mint over time)
  - Pausable? (does it have its own pause that breaks vault?)
- [ ] If rebasing — does vault accounting handle rebase events safely?
- [ ] If FoT — does deposit() check actual received amount, not requested?

## Initialization race (cToken / market patterns)

- [ ] If Compound v2 fork: enumerate all markets via Comptroller
- [ ] For each cToken: `totalSupply()` and `getCash()`
- [ ] Markets with totalSupply == 0 and listed in Comptroller → race vulnerable
- [ ] Even non-empty markets: did anyone deposit the dead share float?

## Hooks / strategies

- [ ] If vault has a strategy: can strategy lose all funds in single tx?
- [ ] beforeWithdraw / afterDeposit hooks — reentrant?
- [ ] Strategy migration: who can call? Atomic vs delayed?

## Off-chain accounting drift

- [ ] If the protocol displays pricePerShare from off-chain: does it match on-chain?
- [ ] Slippage display vs actual withdraw amount?
- [ ] APY display based on what data source?

## Severity rubric

- balanceOf-based totalAssets + no first-deposit protection + active deposits open → **Critical**
- balanceOf-based + has v4.9 offset (default 0) + low decimals (≤6) → **High**
- Wrong rounding direction (off by ULP per op) → **High** (cumulative drain)
- Empty Compound v2 market still listed → **Critical**
- Rebasing underlying without rebase-aware accounting → **High**

## Tools

- `dapphunt/hypothesis/erc4626_donation_scanner.py` — detects vulnerable accounting patterns
- Foundry fork test for reproducer:
  ```
  forge create --rpc-url $RPC --private-key $BURNER \
      test/Erc4626Donation.t.sol --constructor-args $VAULT_ADDR
  ```
- Tenderly fork simulation for share math edge cases

## References

- ERC-4626 spec: https://eips.ethereum.org/EIPS/eip-4626
- OpenZeppelin ERC4626 implementation: github.com/OpenZeppelin/openzeppelin-contracts/blob/master/contracts/token/ERC20/extensions/ERC4626.sol
- t11s mitigation article: https://www.rileyholterhus.com/writing/erc4626
- Hundred Finance post-mortem: https://hundred-finance.medium.com/hundred-finance-hack-post-mortem-aaa6c5ebe55b
