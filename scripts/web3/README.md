# Web3 Module

Smart contract audit for EVM-compatible blockchains. Focus on Immunefi programs.

**Scope:** EVM only (Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Avalanche, Fantom).
Solana / Cosmos / Move — not supported in v1.

## Module files

| File | Purpose |
|------|---------|
| `scan.sh` | Main orchestrator — runs all analyzers |
| `fetch_source.py` | Downloads source from Etherscan V2 / Sourcify, detects EIP-1967 proxy |
| `correlate.py` | Merges findings, dedup, severity scoring |
| `tvl_check.py` | DeFiLlama API — TVL for impact calculation |
| `immunefi_scope.py` | Scope check via community JSON |
| `poc_scaffold.py` | Foundry test stubs for high/critical findings |
| `test_regression.sh` | Runs the pipeline on Damn Vulnerable DeFi for regression |

## How to use

### Target mode — onchain contract

```bash
bash scan.sh \
  --onchain eth:0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D \
  --output sessions/uniswap-v2-router \
  --mode quick
```

### Target mode — local repo

```bash
bash scan.sh \
  --repo /path/to/contracts \
  --output sessions/myproject \
  --mode deep
```

### Modes

- `--mode quick` (default, 5-30 sec): Slither + Aderyn + Wake + Semgrep
- `--mode deep` (hours): + Mythril + Echidna + Halmos

### TVL and Immunefi scope

```bash
python3 tvl_check.py --protocol uniswap
python3 immunefi_scope.py --address 0x7a25...
python3 immunefi_scope.py --list-new          # programs from the last 7 days
```

### PoC scaffolding

```bash
python3 poc_scaffold.py \
  --summary sessions/myproject/web3_summary.json \
  --output sessions/myproject/poc
```

## What is covered (Vulnerability categories)

| Category | Slither | Mythril | Aderyn | Wake | Echidna | Halmos |
|-----------|:-:|:-:|:-:|:-:|:-:|:-:|
| Reentrancy (classic) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Reentrancy (read-only) | hint | — | — | ✅ | ✅ | ✅ |
| Access control | ✅ | hint | ✅ | ✅ | — | — |
| Arbitrary send (ETH/ERC20) | ✅ | ✅ | ✅ | ✅ | — | — |
| Unprotected upgrade / suicidal | ✅ | ✅ | ✅ | ✅ | — | — |
| Uninitialized storage | ✅ | ✅ | ✅ | ✅ | — | — |
| Integer over/underflow | ✅ pre-0.8 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Unchecked external calls | ✅ | ✅ | ✅ | ✅ | — | — |
| Delegatecall to untrusted | ✅ | ✅ | ✅ | ✅ | — | — |
| Timestamp dependence | ✅ | ✅ | ✅ | ✅ | — | — |
| DoS via gas | ✅ | hint | ✅ | ✅ | — | — |
| Bad randomness | ✅ | ✅ | hint | ✅ | — | — |
| Oracle manipulation | manual | — | hint | hint | ✅ inv | ✅ |
| Flash loan attacks | manual | — | manual | hint | ✅ inv | ✅ |
| Logic errors | — | hint | — | hint | ✅ | ✅ |

`manual` = Claude helps interpret via chain analysis.

## Output

Each scan creates:
```
output_dir/
├── fetch_summary.json         # if --onchain
├── foundry-project/           # if --onchain and source verified
│   ├── src/
│   └── foundry.toml
├── slither.json
├── aderyn.json
├── wake.json
├── semgrep.json
├── mythril.jsonl              # deep mode only
├── echidna.json               # if there are property tests
├── halmos.json                # if a foundry project
├── gitleaks.json              # if there is .git
├── web3_summary.json          # ←── main merged output
└── poc/
    ├── F001_reentrancy_eth.t.sol
    └── ...
```

## Immunefi Top 10 — coverage by our tools

Source: [immunefi.com/immunefi-top-10](https://immunefi.com/immunefi-top-10/)

| # | Vulnerability | Coverage | What covers it / gap |
|---|---|---|---|
| V01 | Improper Input Validation | Partial | Slither/Wake — partial; business logic — manual review |
| V02 | Incorrect Calculation | Weak | **Echidna/Foundry invariants** in deep mode |
| V03 | Oracle / Price Manipulation | **GAP** | Manual only. Echidna invariants may catch it. AiRacleX (academic) |
| V04 | Weak Access Control | Good | Slither (`unprotected-upgrade`, `suicidal`), Wake, Aderyn |
| V05 | Replay Attacks / Sig Malleability | Weak | Wake partial; custom Slither/Semgrep rules needed |
| V06 | Rounding Error | **GAP** | Fuzzing only (Echidna/Foundry invariants) |
| V07 | Reentrancy | Good | Slither (`reentrancy-eth/-balance`), Mythril, Wake, Echidna |
| V08 | Frontrunning | **GAP** | Manual + Semgrep patterns. No auto-detector |
| V09 | Uninitialized Proxy | Good | Slither (`uninitialized-state`), Wake, Aderyn |
| V10 | Governance Attacks | **GAP** | Manual: timelock delay, multisig threshold, circuit breakers |

**Main gaps (3):** Oracle manipulation (V03), Frontrunning (V08), Governance (V10) — **AI synthesis** in `/hunt` via manual analysis + threat_intel.md patterns is critical here.

See [threat_intel.md](./threat_intel.md) — manual checks for V03/V08/V10 and recent real attacks.

---

## Severity calculation

Every finding is assigned an Immunefi V2.3 severity (4 levels):

```
loss_percent = realistic_max_loss / tvl_at_risk × 100
≥ 20% AND attack_complexity=low → Critical
≥ 5%  OR significant_funds_freezable → High
≥ 1%  OR temporary_loss → Medium
griefing/informational → Low

reward ≈ min(affected_funds × 10%, project_cap)
```

Stored in `web3_summary.json` under the field `findings[].estimated_bounty`.

## Tools versions (verified via research)

| Tool | Version | Installed in Docker as |
|-----|--------|-------------------------|
| Slither | 0.11.5 | `pip install slither-analyzer` |
| Mythril | 0.24.8 | isolated venv Python 3.10 |
| Aderyn | 0.6.8 | Cyfrin installer |
| Echidna | 2.3.2 | binary download |
| Foundry | rolling | `foundryup` |
| Wake | latest | `pip install eth-wake` |
| Halmos | 0.3.3 | `pip install halmos` |
| 4naly3er | latest | git + yarn |

## Resources

- [Immunefi V2.3 Severity](https://immunefi.com/immunefi-vulnerability-severity-classification-system-v2-3/)
- [Immunefi Programs JSON (unofficial)](https://github.com/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial)
- [Slither detectors](https://github.com/crytic/slither/wiki/Detector-Documentation)
- [Mythril docs](https://mythril-classic.readthedocs.io/)
- [Echidna guide](https://github.com/crytic/echidna)
- [Damn Vulnerable DeFi v4](https://github.com/theredguild/damn-vulnerable-defi)
- [Etherscan V2 API](https://docs.etherscan.io/etherscan-v2)
- [Sourcify](https://sourcify.dev/)
- [DeFiLlama API](https://api-docs.defillama.com/)

## Roadmap (defer)

- [ ] Solana / Anchor — separate phase
- [ ] Cosmos / CosmWasm — separate phase
- [ ] Move (Aptos / Sui) — separate phase
- [ ] Auto-submission to Immunefi
- [ ] Vyper support (slither-vyper)
