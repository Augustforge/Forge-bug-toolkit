# Bridge / Cross-chain Checklist (8 patterns)

Bridges = the most expensive bugs historically. $600M Ronin, $320M Wormhole, $292M KelpDAO/LayerZero, $100M Harmony.

## 1. Message replay attack
- [ ] Monotonic nonce enforcement (per source chain, per sender)
- [ ] messageId uniqueness — the hash includes chainId + nonce + payload
- [ ] Storage of processed messages (Merkle tree?) — replay impossible
- **Check:** is there a `processedMessages` mapping
- **Real case:** Nomad bridge ($190M) — the message wasn't verified

## 2. Validator/Guardian set diversity
- [ ] The bridge requires N-of-M signatures
- [ ] Validators not all owned by the same entity
- [ ] Geographic distribution
- [ ] Wormhole: 13 guardians, 13/19 threshold
- [ ] LayerZero V2: configurable DVN count
- **Threshold for Critical:** N/M >= 51% AND M >= 5 diverse parties

## 3. Source chain finality
- [ ] The bridge waits for finality before minting on the dst chain
- [ ] Polygon ~ 256 blocks, BSC ~ 15 blocks, Ethereum ~ 32 blocks (post-Merge)
- [ ] A reorg on the src chain after bridging = double-spend on dst
- **Real case:** Polygon zkEVM bridge issues during reorgs

## 4. Proof verification (Merkle/SMT)
- [ ] The verifier checks the Merkle proof correctly
- [ ] Hash function consistent between chains (keccak vs sha256)
- [ ] Padding doesn't allow collision attacks
- **Real case:** Wormhole — signature verification skipped via a bug in the Solana program

## 5. Decimals normalization across chains
- [ ] Token has 6 decimals on chain A, 18 on chain B?
- [ ] Does the bridge scale correctly?
- [ ] Loss of precision doesn't permit free tokens

## 6. Chain ID validation
- [ ] dst chain checks that `block.chainid` matches the expected one
- [ ] Pre/post EIP-155 transactions cross-chain replay
- **Pattern:** require(srcChainId == LZ_CHAIN_ID_ETH);

## 7. Gas attack (forced revert on dst chain)
- [ ] dst chain executor — can it run out of gas?
- [ ] If the executor revert is not atomic — funds locked / double-spend
- [ ] LayerZero retry logic — is the retry exploitable

## 8. LayerZero DVN single-point-of-failure (KelpDAO $292M)
- [ ] `requiredDVNCount == 1` ← CRITICAL
- [ ] `optionalDVNCount` — for additional protection
- **Check on-chain:**
  ```bash
  cast call $endpoint "getConfig(uint32,address,uint32)" $eid $oapp 2 \
      --rpc-url $RPC
  # Decode UlnConfig — if requiredDVNCount = 1 → CRITICAL
  ```

---

## Bridge-specific automated tests

See `scripts/web3/bridge_tests/` — we write tests for each pattern:
- `layerzero_dvn_check.sh`
- `wormhole_guardian_check.sh`
- `axelar_validator_check.sh`
- `cctp_attestation_check.sh`
- `bridge_replay_test.sol` (Foundry template)
- `bridge_finality_test.sol`

## Severity for bridge findings

| Pattern | Default severity |
|---------|------------------|
| DVN single-point | Critical |
| Replay possible | Critical |
| Validator threshold <50% | Critical |
| Finality not waited | High |
| Decimals mismatch | High |
| Chain ID missing | Medium |
| Gas attack possible | Medium-High |

## Solodit search keywords
`cross-chain`, `bridge`, `replay`, `LayerZero`, `Wormhole`, `Axelar`, `validator`, `guardian`, `Merkle proof`, `finality`
