# Crypto TSS/MPC PoC Templates

Concrete PoC scaffolds for TSS/MPC vulnerability reproduction. This is not Solidity
Foundry tests — TSS implementations are usually in Go/Rust, so the templates here =
Go test files (`*.go.template`).

## Files

| Template | Class | Cite |
|---|---|---|
| `paillier_biprime_bypass.go.template` | Malformed Paillier key submission during keygen | TSSHOCK Verichains 2022, c-split variant 2026 |
| `zk_iterations_truncation.go.template` | Adversary submits ZK proof with an understated iterations counter | GG18 weak ZK proof family |
| `c_split_simulation.go.template` | Adversarial validator hijacks signing ceremony to extract share | Thorchain 2026 root cause |

## Usage

1. Copy the template into the target repo: `cp paillier_biprime_bypass.go.template /path/to/target-tss/poc_paillier.go`
2. Replace the placeholders:
   - `<TARGET_PACKAGE>` — Go package we connect to (e.g., `tss "github.com/bnb-chain/tss-lib/ecdsa/keygen"`)
   - `<HONEST_PARTY_IDS>` — array of party IDs other than the adversary
   - `<ADVERSARY_INDEX>` — index of bonded malicious party
3. Run as a regular Go test: `go test -run TestPoC -v`
4. Expected outcome — a comment in the template explains what should happen if the bug is present vs absent

## Cross-link

- [checklists/specialized/tss_mpc.md](../../checklists/specialized/tss_mpc.md) —
  manual review checklist showing where to look for these classes
- [threat_models/tss_validator_extraction.yaml](../../threat_models/tss_validator_extraction.yaml) —
  threat model describing when to apply
- [research/_crypto_corpus/](../../research/_crypto_corpus/) — reference implementations for context
