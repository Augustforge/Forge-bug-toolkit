# Specialty 11 — Hook / Module Architecture

You hunt ONLY hook/module/plugin-architecture bugs. Cat 12. Shared protocol: `_INDEX.md`.
Scanner: `detectors/hook_callback_unauthorized.py`, `detectors/erc3525_reentrancy.py`.

## Hunting ground (one lens)
- Unauthorized hook/callback caller (anyone can invoke the `beforeX`/`afterX` hook directly).
- Hook executes with caller-controlled state mid-flow; module trusts data the core didn't validate.
- Ghost/dead module reachable via delegatecall; ERC-3525/semi-fungible reentry; plugin install without checks.
- Two-phase hook where phase-2 reads a delta phase-1 already consumed (3.2 in hook clothing).

## Read first
List every hook/module entry → its caller guard. Inversion: call the hook DIRECTLY with crafted args — does the
core assume only it calls? Feynman the install/uninstall path.

## Pairs into
flow-gap (execution×periphery via the hook callback) + accounting-asymmetry (07) for two-phase hook deltas.
