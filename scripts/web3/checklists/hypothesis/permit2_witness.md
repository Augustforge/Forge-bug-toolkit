# Hypothesis: Permit2 Witness Binding

**Trigger**: target uses Permit2 with witness (`permitWitnessTransferFrom`).

## Permit2 structure recap

```solidity
struct TokenPermissions { address token; uint256 amount; }
struct PermitTransferFrom {
    TokenPermissions permitted;
    uint256 nonce;
    uint256 deadline;
}
// Witness data appended: hash of additional protocol-specific data
```

User signs: `(permit + witness)`. Protocol verifies via `permitWitnessTransferFrom`.

## Bug patterns

### Witness type string mismatch
- User signs witness of type `OrderData(uint256 amountOut, address recipient)`
- Protocol builds typeString `OrderData(uint256 amountOut)` — different!
- Permit2 doesn't catch — signature appears valid

### Nonce reuse
- Permit2 has unordered nonces (bit-packed)
- If protocol implements its own nonce counter on top, both must align
- Check: can a permit be replayed if protocol uses different nonce tracking?

### sigDeadline vs witness deadline
- Permit deadline (top-level) controls signature expiry
- Witness may contain ITS OWN deadline (e.g., order deadline)
- Mismatch: user thinks order expires at X, but permit accepts past X

### Witness contains exploitable fields
- Witness shouldn't grant capabilities — only describe constraints
- If witness can specify "recipient = anyone", attacker can fill in recipient

### Allowance vs SignatureTransfer confusion
- Permit2 has 2 modes: AllowanceTransfer (long-lived) + SignatureTransfer (one-shot)
- Mixing them = security bug

## Verification

```solidity
function test_Permit2_TypeStringMismatch() public {
    // User signs with witnessTypeString A
    // Protocol calls permitWitnessTransferFrom with typeString B
    // Should revert if Permit2 hashing differs
    // If it passes — bug confirmed
}
```

Test with deliberately-mismatched type string. Verify Permit2 rejects.
