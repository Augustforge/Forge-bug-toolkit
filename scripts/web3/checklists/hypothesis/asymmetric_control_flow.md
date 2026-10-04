# Hypothesis: Asymmetric Control Flow

**Trigger**: `asymmetry_scanner.py` flagged a modifier present in N functions, absent in M (where N ≥ 2 and M ≥ 1).

**Real example**: DeXe Protocol's `delegateTokens` missed `ifNotStaken` modifier present in `withdrawTokens` and `stakeTokens`. Result: same tokens earn staking rewards AND grant voting power simultaneously.

---

## Checklist (apply per asymmetry signal)

### 1. Modifier semantics
- [ ] Read modifier body. What state does it check?
- [ ] What invariant does it enforce?
- [ ] Is invariant **business-logic** (need everywhere) or **mode-specific** (only some functions)?

### 2. Should-have analysis  
- [ ] For each function MISSING the modifier — does it mutate state that invariant cares about?
- [ ] If yes → strong bug signal
- [ ] If no → false positive, document why

### 3. Difference between siblings
- [ ] What's the SEMANTIC difference between the function-with-modifier and function-without?
- [ ] Is the difference real (e.g., view vs mutating) or accidental (e.g., one was added later, modifier forgotten)?

### 4. Bypass impact
- [ ] If missing modifier is the bug, what can attacker do?
- [ ] User-facing: can attacker call directly? Or via privileged caller?
- [ ] What invariant breaks?

### 5. Verification
- [ ] Write Foundry test:
  - setup state where modifier WOULD fail (e.g., user has staked tokens)
  - call the function-without-modifier
  - assert it succeeds (bug) or reverts (no bug)

### 6. Severity
- [ ] If user can execute without precondition → **at least Medium**
- [ ] If economic profit > $1k → **High**
- [ ] If it allows double-use of capital → **Critical** (DeXe class)

---

## Past examples

### DeXe `delegateTokens`
- Asymmetric: `withdrawTokens(payer, amount) external override onlyOwner withSupportedToken ifNotStaken(payer, amount)`
- Missing: `delegateTokens(...) external override onlyOwner withSupportedToken` (no ifNotStaken)
- Result: tokens both stake (earn rewards) and delegate (give voting power)
- Severity: Medium-High

### Hypothetical: lending protocol
- `borrow()` has `whenNotPaused`
- `repay()` has `whenNotPaused`
- `liquidate()` MISSING `whenNotPaused`
- Result: during pause, attacker can still liquidate vulnerable positions
- Severity: depends on context

---

## False positive heuristics

- View functions don't need state-mutation modifiers (e.g., `nonReentrant` on view = unnecessary)
- Constructor / initializer typically has different modifier set
- `internal` helper functions often skip access-control (caller is trusted contract code)
- Modifier may be inherited from base contract; check inheritance tree

---

## Output format

After this checklist applied:

```markdown
## Asymmetry H<N>: <modifier> in <FunctionA, FunctionB>, missing in <FunctionC>

### Hypothesis
The modifier `<name>` enforces invariant `<description>` in <FunctionA>. 
<FunctionC> mutates the same state but skips this check.

### Verification result
- [ ] CONFIRMED: PoC at `verify/H<N>.t.sol`
- [ ] FALSE_POSITIVE: <reason>
- [ ] NEEDS_DEEP: <what's unclear>

### Severity
<Low/Medium/High/Critical> — <numeric argument>
```
