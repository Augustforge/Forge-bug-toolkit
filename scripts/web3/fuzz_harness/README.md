# Fuzzing engines — dispatcher (pick by target shape)

This dir holds **two complementary fuzzing engines**. On any fuzz-worthy target, pick by shape —
they don't overlap:

| Engine | Use when | Path |
|--------|----------|------|
| **fizz** (Echidna/Medusa stateful) | EVM/Solidity protocol, **invariant-heavy** (vault/AMM/lending/staking, Cat 1/3/8), and the target is **thin on its own fuzz/invariant tests** → you want an engine that *searches for the call sequence that breaks an invariant* (explore-wide layer ABOVE targeted fork-PoC). | `fizz/` (cloned pashov skill) |
| **Differential / Involution (T8, libafl/Rust)** | **Two implementations parse one wire format** — multi-client L1/L2 (Prysm/Lighthouse, geth/reth), or one client importing two crates for the same format (SSZ/RLP/borsh/BCS). A divergence = consensus fork. | `differential_harness.rs.template` (below) |

**Decision rule (mirrors the T1-trigger in `methodology/mythos_techniques.md`):** Solidity + invariant-class
bug suspected + no in-repo fuzz → **fizz**. Cross-client/parser format → **differential**. Targeted check
of a KNOWN hypothesis → neither; use the Foundry fork-PoC (`poc_scaffold.py`). Solana → `scripts/sol/fuzzing`
(Trident). **Harness is always built per-target** — fizz reads the target's contracts and generates the
suite under it; nothing to pre-build beyond having the skill on hand (now cloned).

## fizz — how to use (per-target)
`fizz/SKILL.md` is the entrypoint (11-step pipeline: protocol-analyze → 5 parallel invariant-discovery
agents → synthesizer → implementers → run Echidna/Medusa). Templates in `fizz/templates/`
(Base→Snapshots→Properties→Handlers→FuzzTester), Node drivers in `fizz/scripts/`. Sub-skills `fizz-convert`
(PROPERTIES.md → Solidity) and `fizz-sync` (drift-detect src→harness). **Env gotcha:** if `foundry.toml`
has `via_ir = true`, Medusa coverage is deflated → add `[profile.fuzz] via_ir = false` ([[reference_toolkit_env]]).
Build/run heavy steps in Docker `bbt`. Ingest notes + the 4 wired techniques: [[reference_pashov_fizz]].

---

# Differential / Involution Fuzz Harness (T8)

Template harness for **cross-client / cross-parser divergence** hunting — taxonomy Cat 18.1/18.2.
Implements T8 in `methodology/mythos_techniques.md`. Source: asymmetric.re "Finding Fractures"
(github.com/asymmetric-research/blogpost-fuzzer-101).

## When to use
A target where **two implementations parse one wire format** — Ethereum CL clients (Prysm/Lighthouse),
geth/reth, any L1/L2 with multiple clients, or even one client importing two crates for the same
format (SSZ, RLP, borsh, BCS, JSON, protobuf, TL-B). A divergence = consensus fork / chain split.

## Files
- `differential_harness.rs.template` — fill the 3 TODO slots (parse_a, parse_b, corpus paths), build.
- `corpus_seeds.md` — the edge inputs that historically trigger divergence; seed `./corpus` with these.

## Quick start
1. New crate: `cargo new diff_fuzz && cd diff_fuzz`; add `libafl`, `libafl_bolts`, and the two
   target parsers to `Cargo.toml`. Toolchain: Ubuntu 24.04 + LLVM-18 + `rustup default nightly`.
2. Copy the template to `src/main.rs`, implement `parse_a` / `parse_b` for your format (each returns
   `Ok(canonical_bytes)` on accept, `Err(())` on reject).
3. Seed `./corpus` from `corpus_seeds.md`. `cargo run --release`.
4. Any assert failure = saved to `./crashes` = an input where A and B disagree (or A breaks
   round-trip). Triage → confirm on a multi-node devnet → that's the finding.

## Properties checked
- **P1 differential:** `accept_A(x) == accept_B(x)`, and equal canonical form when both accept.
- **P2 involution:** `deser(ser(deser(x))) == deser(x)` for impl A (round-trip stability).

## Note
This is a **template**, not a CI target — it intentionally won't build until the TODO slots are
filled for a concrete target. Full toolchain (Ubuntu/LLVM-18/nightly) is set up per-hunt.
