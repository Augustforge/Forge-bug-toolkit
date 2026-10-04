# Checklist: Cross-Client Serialization / Parser Divergence

**Class:** taxonomy Cat 18.1 (involution/injective) + 18.2 (parser divergence).
**Source:** asymmetric.re "Ghost in the Block" (SSZ Prysm vs Lighthouse) + "Finding Fractures" (JSON differential fuzz).
**Primary technique:** T8 Differential / Involution Fuzzing (`methodology/mythos_techniques.md`, harness in `scripts/web3/fuzz_harness/`).
**Targets:** multi-client L1/L2 (Ethereum CL clients, geth/reth), any network where 2+ implementations parse one wire format (SSZ, RLP, borsh, BCS, JSON, protobuf, TL-B). **Severity:** Critical (chain split / block-production halt).

## Two soundness properties to break
1. **Involution:** `deserialize(serialize(X)) == X`. Broken → a decoder accepts a byte stream and
   re-encodes it differently (ghost regions, padding, alternate offsets).
2. **Injective:** `serialize(A) == serialize(B)` only if `A == B`. Broken → two different objects
   collide to one encoding, or one object has two valid encodings.

If either breaks across two clients/parsers → consensus fork.

## Ghost-region pattern (SSZ, "Ghost in the Block")
- SSZ variable-length fields are addressed by offsets. A lenient `UnmarshalSSZ` accepts a block whose
  offsets are coherent **relative to each other** but leave unused gaps ("ghost regions") between objects.
- The ghost region does NOT change `hash_tree_root` → the block's **signature stays valid**.
- Attacker takes an already-signed block, inserts a gap (shift `ExtraData`/`Transactions`/… offsets),
  resubmits: lenient client accepts, strict client (`OffsetSkipsVariableBytes`) rejects → halt.
- **Check:** does the decoder validate `sum(variable_field_lengths) == total_variable_section_size`,
  or only relative offset coherence? Only-relative = ghost regions possible.

## Parser divergence pattern (JSON, "Finding Fractures")
- Two parsers of one format have different strictness (e.g. `json-rust` accepts the `0x0B` vertical
  tab inside strings, `serde_json` rejects it per RFC 8259).
- **Check:** does the same network use two parsers of one format (different crates, or client A vs B)?
  If yes → they will diverge on edge bytes.

## Review steps
1. Enumerate every serialization/deserialization implementation for each wire format in scope.
2. Identify where 2+ implementations parse the SAME format (across clients, or libs within one client).
3. For each, run **T8 differential fuzzing**: `accept_A(x) == accept_B(x)` and `deser(ser(x)) == x`.
4. Seed corpus with the usual divergence triggers: `0x0B`/control bytes, negative numbers, empty
   strings, leading zeros, max-depth nesting, trailing bytes, oversized/duplicate offsets, NaN.
5. Any input where the two disagree (one accepts, one rejects, or they decode to different objects)
   = consensus-divergence candidate → confirm on a multi-node devnet.

## Detection signal (static, pre-fuzz)
- SSZ/RLP/borsh/TL-B decoder validating relative offsets only (no total-size invariant).
- Same repo/network importing two parsers of one format (e.g. `serde_json` + `json::parse`).
