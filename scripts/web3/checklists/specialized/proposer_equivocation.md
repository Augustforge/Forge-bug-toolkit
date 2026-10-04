# Checklist: Proposer Equivocation / Commitment-Binding Gap (MEV relay)

**Class:** taxonomy Cat 18.4. **Source:** asymmetric.re "Corrupt Commitments: Helix MEV Relay".
**Targets:** mev-boost / PBS relays (Helix, custom relays), builder↔proposer flow. **Severity:** Critical for a trusted proposer/validator.

## The bug in one line
The relay unblinds a block payload after the proposer signs a header that does **not bind** all
execution-critical fields — specifically the EIP-4844 **KZG blob commitments**. A trusted proposer
submits `submitBlindedBlock` with forged commitments (same length, different values), the relay's
equality check passes, the relay reveals the builder's private transactions, and the proposer
rebuilds a more profitable block / reorders / front-runs.

## Why it exists
`ExecutionPayloadHeader` (the thing the proposer signs) predates Deneb and has no `kzg_commitments`
field. A naive `validate_header_equality` compares the standard header fields but never compares the
submitted blob commitments against what the builder originally provided. Flashbots added this check
after the April 2023 incident; forks/reimplementations (Helix) did not.

## Review steps
1. Find the `submitBlindedBlock` / `getPayload` handler in the relay.
2. Locate the equality/validation function (`validateHeaderEquality`, `ValidateSubmission`, etc.).
3. **Check:** does it compare the submitted `blob_kzg_commitments` (and `blob count`) against the
   builder's stored submission? Length-only check (`len(blobs) == len(commitments)`) is INSUFFICIENT —
   values must match the originally-submitted commitments.
4. Check the trust model: does the relay treat some proposers as "trusted" and skip checks for them?
   Trusted-proposer path is exactly where this is exploitable.
5. Cross-check beacon-node behavior: forged commitments are rejected by beacon nodes, so the attack
   path is "unblind → learn txs → publish alternative block with correct commitments but reordered".

## Confirmation / PoC angle
- Diff the relay's validation against the Flashbots post-2023 patch (which added the commitment binding).
- A relay missing the commitment-equality check on the trusted-proposer path = finding.

## Severity calibration
- Critical if the relay serves trusted proposers (staking pools, large validators) and lacks the bind.
- Down-rate if every proposer is untrusted AND untrusted path already enforces the check.

## Detection signal (grep)
`submitBlindedBlock` / `getPayload` handler whose validation never references
`blob_kzg_commitments` / `BlobsBundle.Commitments` equality vs the stored builder submission.
