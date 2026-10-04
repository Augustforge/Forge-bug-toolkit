# Hypothesis: Non-Obvious Low/Medium Findings

**Trigger**: target is well-audited (3+ audits). Surface-level bugs already reported. Need to find Low/Medium that **aren't caught by nuclei templates or basic scanners**.

**Why this matters**: most "duplicate" rejections on Immunefi come from obvious Lows. Non-obvious Lows = paid reports.

---

## Categories of non-obvious findings

### 1. First-depositor edge cases
- ERC-4626 share inflation (already known, but check virtual shares config)
- First user pays gas for storage warm-up of subsequent users (cost asymmetry)
- First action sets state value that constrains all future actions

### 2. Approve race conditions
- Classic ERC-20 `approve(0)` race (often missed because using `increaseAllowance`/`decreaseAllowance` not enough)
- Permit-based approvals with edge nonce handling
- Approve to contract that calls back

### 3. Time-of-check vs use (ToCToU)
- `view` function returns X
- User uses X to compute amount
- By time of execution, X changed
- Specific subset: pool reserves, oracle price, governance state

### 4. Rounding direction bugs
- Vault redeem should round in favor of vault (not user)
- Borrow should round up debt
- Repay should round down credit
- Per-share calculations rounding away from invariant

### 5. Token compatibility quirks
- Fee-on-transfer: protocol assumes received = sent
- Rebasing: balance changes without transfer
- Blacklisting: blocked address breaks accounting
- ERC-777 callbacks
- Tokens with 0 decimals (USDT-like)
- Tokens with extreme decimals (Shibu Inu-likes, 18+ decimals)

### 6. Block.timestamp dependencies
- Lock unlock at exact second
- Reward calc per-second accumulating rounding
- Time-weighted vote with edge timestamps

### 7. View function lying
- `maxDeposit()` / `maxWithdraw()` returns higher than actually allowed
- `getQuote()` doesn't match real swap execution

### 8. Storage uninitialized
- `mapping(...) memory` returns zero — caller may think "default user"
- Default uint = 0 — treated as "all" in some contexts

### 9. Integer truncation
- Division rounds down; reverse direction multiplication doesn't
- `amount / 100 * 100 != amount` for non-multiples-of-100

### 10. Reentrancy across "safe" boundaries
- `nonReentrant` per-function but cross-function reentrancy via separate functions
- Read-only reentrancy (Curve pattern)
- Reentrancy via callbacks in unusual flows (NFT transfer, ERC-777, ERC-4626 hooks)

### 11. Permit2 edge cases
- Witness binding type string mismatch
- Nonce reuse across permit types
- sigDeadline vs witness deadline differ

### 12. Cross-function state inconsistency  
- FunctionA writes state[X] = 5
- FunctionB reads state[X]
- Race: FunctionA can reset before FunctionB reads if attacker controls ordering

### 13. Sequencer downtime (L2 specific)
- Liquidations rely on price feed during sequencer pause → can't liquidate
- Or: position rolls over with stale price

### 14. Init function with public + repeated init
- Initialize callable multiple times if check is weak

### 15. Modifier order
- Cross-modifier reentrancy via modifier ordering
- e.g., updateRate → nonReentrant — but updateRate calls external

---

## Approach for hunt

For each category above:
1. Search target code for indicators (regex/grep)
2. If pattern present, formulate specific hypothesis
3. Build minimal PoC

---

## Specific grep patterns

```bash
# Category 1: First depositor
grep -rn "_decimalsOffset\|_initialShares\|virtualShares" --include="*.sol"
grep -rn "totalSupply() == 0" --include="*.sol"

# Category 4: Rounding
grep -rn "Math.Rounding\|MulDiv\|mulDiv" --include="*.sol"

# Category 5: Token quirks
grep -rn "balanceBefore\|balanceAfter" --include="*.sol"  # signals fee-on-transfer aware
grep -rn "safeTransfer" --include="*.sol"  # ERC-777 callback surface

# Category 8: Storage default
grep -rn "mapping(" --include="*.sol"  # all mappings — check default-zero handling

# Category 10: Reentrancy
grep -rn "nonReentrant\|ReentrancyGuard" --include="*.sol"  # check coverage

# Category 13: Sequencer
grep -rn "sequencer\|chainlink.*L2\|0xFdB631F5EE196F0ed6FAa767959853A9F217697D" --include="*.sol"
```

---

## Past examples (Lows that paid)

### Various: ERC-4626 missing virtual shares offset
- $2k-5k Medium on Immunefi
- Specific to vault implementations without OZ pattern

### Various: Sequencer downtime not checked
- $1k-3k Medium on L2 lending protocols

### Various: Permit nonce reuse across contracts
- $2k-10k Medium when multiple permits used

---

## Output format

```markdown
## Non-Obvious Low H<N>: <category> in `<file:line>`

### Pattern
<Specific pattern from list above>

### Why missed previously
- Not in nuclei templates: <reason>
- Not in standard auditor checklists: <reason>
- Requires context: <what context>

### Severity
<Low/Medium> — <reason>

### Verification
- [ ] Foundry test demonstrating: `verify/H<N>.t.sol`
- [ ] Real-world impact described in numbers
```
