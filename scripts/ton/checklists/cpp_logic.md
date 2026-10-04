# TON C++ Node — Logic Bug Checklist
# Brute-force and simple approach: Claude reads the module's code and walks through each item explicitly.
# Scope source: https://github.com/ton-blockchain/bug-bounty

## How to use

For each HIGH finding from ton_summary.json:
1. Open the file + ±50 lines of context around the finding
2. Walk through the relevant section of this checklist
3. If confirmed — write a PoC / reproducer
4. If not — mark as false positive and move to the next one

---

## 1. Catchain Consensus (the most valuable bugs)

**What it is:** TON's consensus protocol, a BFT analogue. Logic bugs here = network halt or double signing.

For each function in `catchain/`:
- [ ] Are all fields of an incoming block checked before processing?
      (who could have sent this block? is a signature required?)
- [ ] Is there a check that the sender's `source_id` is in the current validator set?
- [ ] Are out-of-order messages handled correctly?
      (a message with `round=future` should not affect current state)
- [ ] Can an attacker trigger a replay attack — send an old signed message?
      (check for a nonce / height check)
- [ ] What happens on `height overflow`? (td::int32 vs td::uint64 mismatch)
- [ ] Locks: is the mutex acquired and released on the same thread?
      (deadlock if an exception occurs between lock and unlock)

---

## 2. Validator Logic (`validator/`)

**What it is:** block processing, transaction verification, shard state management.

- [ ] Is the signature of every external message verified before execution?
- [ ] What happens when a block with `seqno` lower than current is received?
      (it should be dropped, not processed)
- [ ] Is the `workchain_id` checked against the expected one?
- [ ] Are all `BlockIdExt` fields validated before being used as a key?
- [ ] `compute_phase` and `action_phase` — are gas limits correct at edge values?
- [ ] Can a malformed Merkle proof cause a panic/abort instead of a graceful error?

---

## 3. Crypto (`crypto/`)

**The most valuable category in bug bounty — bugs here = stolen funds.**

- [ ] Are all `Ed25519_verify()` / `check_signature()` return values checked?
      CRITICAL: `if (verify(...))` vs just `verify(...)` with no check
- [ ] Signature comparison — is a constant-time compare used?
      (plain `memcmp` is vulnerable to timing attacks)
- [ ] Nonce generation for signatures — is a CSPRNG used?
      (not `rand()` and not a deterministic source)
- [ ] TL-B serialization/deserialization — is length checked before reading?
      (`fetch_bytes(n)` without checking `n <= remaining`)
- [ ] Cell loading — what happens on `load_ref()` on a cell with no refs? graceful error or crash?

---

## 4. TonLib (`tonlib/`)

**Integration library. Bugs here = bugs in clients (wallets, exchanges).**

- [ ] Are all `td::Status` results propagated? Not `status.ensure()` without a return?
- [ ] Account state validation — what happens on an empty/null account state?
- [ ] `lite_client` requests — is there a timeout? What happens on a hung response?
- [ ] Deserialization of node responses — is the format validated before use?
- [ ] `send_query` — is a dropped connection before the response handled?

---

## 5. ADNL / DHT / Overlay (P2P network)

**Network layer. Bugs = node network isolation, Sybil attacks.**

- [ ] Is the ADNL `pub_key` validated before being used as an identifier?
- [ ] DHT: is there protection against Sybil attack (entry limit per IP)?
- [ ] Overlay: what happens on a duplicate `broadcast_id`?
      (should be deduplicated, not processed twice)
- [ ] Is message size checked before buffer allocation?
      (malicious peer with a huge `size` field)

---

## 6. General C++ patterns (applicable everywhere)

- [ ] Is `std::shared_ptr` dereferenced without a nullptr check in an async callback?
      (the object may have been deleted while the callback was waiting)
- [ ] `static_cast<int32>` on a value that could be > INT32_MAX?
- [ ] `std::vector::operator[]` without a bounds check on a user-controlled index?
- [ ] Exception in a destructor (`~ClassName()` with code that can throw)?
- [ ] `td::actor` sent a message to itself — infinite loop?

---

## How to submit if you found something

1. Telegram: @ton_bugs_bot
2. Frontend: https://hackenproof.com/ton (HackenProof)
3. Report template: `templates/disclosure_web3.md` (adapt for the C++ node)
4. Severity: Critical $2k-$5k, High $800-$2k (HackenProof tier) + up to $100k Toncoin (TON Core direct)
5. A PoC is mandatory — a minimal reproducible test case or unit test

---

## Module priorities (top to bottom)

1. `catchain/` — consensus, the most valuable
2. `crypto/` — signatures and verification
3. `validator/` — block logic
4. `tonlib/` — client library
5. `adnl/dht/overlay/` — network layer
