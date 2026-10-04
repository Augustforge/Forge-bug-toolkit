# Governance / Multisig Invariants — Library

For Squads-class multisig + governance flows. Drift 2026 $285M exploit class.

## Threshold invariants

### I1: Approval threshold enforcement
```
proposal.executed requires #approvals >= threshold
```

### I2: Threshold modification gated
```
update_threshold requires existing threshold to approve
```

## Timelock invariants

### I3: Timelock enforcement
```
proposal.execute_at <= now (cannot execute before timelock expires)
```

### I4: Timelock cannot be zero on critical operations
```
timelock_seconds > MINIMUM_TIMELOCK for: 
    - admin authority change
    - upgrade authority change
    - threshold change
    - mint authority change
```
Violation: instant takeover possible.

## Durable nonce invariants (Drift class)

### I5: Durable nonce single-use
```
nonce.used_for_tx[tx_hash] == false → use → set true
```

### I6: Nonce revocation on member removal
```
remove_member(M) → invalidate all durable nonces signed by M
```
Drift 2026 missed this — pre-signed durable nonces stayed valid after compromise.

## Authority transition invariants

### I7: Authority transfer requires existing authority
```
set_admin requires current_admin signs
set_upgrade_authority requires current_upgrade_authority signs
```

### I8: No re-init after admin set
```
admin field can be modified ONLY via set_admin (not init)
```

## Pre-signed transaction invariants

### I9: Pre-signed tx has expiration
```
signed_tx.expiry_timestamp must be set
signed_tx not valid after expiry
```

### I10: Pre-signed tx single execution
```
execution(signed_tx) sets executed=true → cannot re-execute
```

## Strategy hints for Trident

```rust
strategies! {
    CreateProposal(action = arbitrary),
    Approve(proposal_id, member = arbitrary),
    Execute(proposal_id),
    UpdateThreshold(new_threshold = 1..members.len()),
    AddMember(member_pubkey),
    RemoveMember(member_pubkey),
    SetTimelock(seconds = 0..86400*30),
    // Critical for Drift-class:
    SignDurableNonce(nonce_account, slot),
    UseDurableNonceAfterMemberRemoval(nonce_account, member_removed),
}
```

## Critical scenarios

1. **Threshold = 1**: any single member can execute (DoS / takeover)
2. **Zero timelock**: instant admin change → governance takeover
3. **Durable nonce + member removed**: pre-signed tx valid post-removal
4. **Member rotation race**: add+remove members fast, signed transactions in flight
