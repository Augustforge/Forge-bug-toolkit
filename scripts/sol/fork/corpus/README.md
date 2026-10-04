# Exploit Replay Corpus

Each subdirectory = one historical exploit for regression testing. `replay_corpus.sh` loads them and tests the automated PoC.

## Structure per exploit

```
<exploit_name>/
├── clone_config.json     # JSON: {programs: [...], accounts: [...], slot: N}
├── tx.bin                # Binary signed transaction reproducing exploit
├── watch_accounts.txt    # One pubkey per line — accounts to diff
├── invariants.json       # Success invariants (e.g., vault_lamports_decrease)
└── notes.md              # Exploit details, source links
```

## Format Examples

### clone_config.json
```json
{
  "programs": [
    "MarinadeAcdgyfqGB4uHV1JJzd9bMc8Hk93dD2g4PiZ",
    "Stake11111111111111111111111111111111111111"
  ],
  "accounts": [
    "8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC",
    "1234..."
  ],
  "slot": null
}
```

### invariants.json
```json
[
  {
    "account": "VAULT_PUBKEY",
    "require": "lamport_decrease",
    "max_delta": -1000000
  },
  {
    "account": "ATTACKER_PUBKEY",
    "require": "lamport_increase",
    "min_delta": 1000000
  }
]
```

### watch_accounts.txt
```
VAULT_PUBKEY
TREASURY_PUBKEY
ATTACKER_PUBKEY
```

## Adding A New Exploit

1. Identify exploit (rekt.news, post-mortem)
2. Find pre-fix commit OR mainnet slot just before fix deployed
3. Determine which programs/accounts need cloning
4. Build attacker tx (use `exploit_harness.py --print-template <class>`)
5. Sign with funded keypair
6. Define invariants
7. Test: `bash ../replay_corpus.sh --exploit <name>`

## Target Corpus (Phase K validation)

These 8 exploits = production-readiness benchmark. Need >= 5 PASS:

| Slot | Exploit | Class | Status |
|---|---|---|---|
| 1 | cashio_2022 | owner_check | PENDING |
| 2 | wormhole_2022 | signature_verify | PENDING |
| 3 | mango_2022 | oracle_manipulation | PENDING |
| 4 | crema_2022 | tick_array | PENDING |
| 5 | raydium_2024 | remaining_accounts | PENDING |
| 6 | loopscale_2025 | cpi_program_id | PENDING |
| 7 | marginfi_2025 | state_route | PENDING |
| 8 | drift_2026 | durable_nonce | PENDING |

Status: 0/8 corpus entries built. Building them is **the** validation work — each takes 2-4h of finding pre-fix state + crafting attack tx.
