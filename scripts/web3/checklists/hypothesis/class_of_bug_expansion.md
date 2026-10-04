# Hypothesis: Class-of-Bug Expansion

**Trigger**: bug confirmed in FunctionA. Same pattern likely exists elsewhere.

## Why class expansion matters

- 2× the report value: 1 research → 2 PoCs → 2 findings
- Convinces triager — pattern not isolated mistake
- Forces team to fix systemically, not patch single instance

## Real example

### Alchemix
- Bug #1: `WstETHStrategy._allocate()` lacks oracle guard
- Class-of-bug scan: same architecture exists for SFraxETH
- Bug #2: `SFraxETHStrategy._allocate()` lacks oracle guard
- Result: 2 PoCs in single report, doubled severity argument

## Scan dimensions

### Within target codebase
- Same modifier missing on similar functions
- Same architectural pattern in N contracts
- Same composability dependency

### Cross-protocol (forks/derivatives)
- Protocol forked from X → check X for same bug → check other forks
- Same auditor's other projects (auditor blind spot pattern)
- Same architectural template (e.g., all ERC-4626 vaults)

## Verification per variant

For each candidate variant:
1. Confirm same root cause (not just same symptom)
2. Build minimal PoC (often reuses base PoC structure)
3. Verify pattern present in code

## Tool

`scripts/web3/hypothesis/variant_scanner.py`:
```bash
python3 variant_scanner.py \
    --target $TARGET \
    --pattern-function _allocate \
    --pattern-missing-modifier oracleGuard \
    --output sessions/$TARGET/variants/
```

## Report structure for class

```markdown
# Bug Report: Class-of-X in Protocol Y

## Pattern
[describe class]

## Instances
1. **Function A** — [file:line]
2. **Function B** — [file:line]
3. **Function C** — [file:line]

## Per-instance PoC
[link to each fork test]

## Severity argument
This is not isolated. Same architecture has N instances. Fix must be systemic.
```
