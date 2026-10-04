# Solana Hypothesis Scripts — Broader Classes

> ⚠️ **GLOBAL PRINCIPLE** (see `../../web3/HYPOTHESIS_GUIDE.md`): each script is a detector for a BROADER CLASS, not a template for one exploit.

## Script → Broader Class Mapping

| Script | Triggering exploit(s) | Broader class | Output classification |
|---|---|---|---|
| `signer_check_scanner.py` | Wormhole 2022 ($325M) | **Signer identity verification gaps** | `[novel_instance]` priority |
| `owner_check_scanner.py` | Cashio 2022 ($52M) | **Account owner verification gaps** | `[novel_instance]` priority |
| `account_trust_audit.py` | Loopscale 2025 ($5.8M) + Mango + Cashio + Wormhole | **Any-account spoofing** — trust audit of all external accounts | `[novel_instance]` priority |
| `state_route_analyzer.py` | Marginfi 2025 ($160M prevented) | **State machine alternative routes** — bypass via migration/close/realloc | `[novel_instance]` priority |
| `time_horizon_audit.py` | Drift 2026 ($285M) | **Attacker-controlled time horizons** — nonces/deadlines/TTLs | `[novel_instance]` priority |
| `inverse_op_symmetry.py` | Sec3 + Kamino-class | **Inverse operation asymmetry** — mint/burn, deposit/withdraw rounding | `[novel_instance]` priority |
| `pda_seed_analyzer.py` | Generic Anchor footguns | **PDA seed uniqueness/collision** | mixed |
| `cpi_authority_checker.py` | Generic CPI | **CPI signer authority gaps** | mixed |
| `cpi_program_id_validator.py` | Loopscale 2025 | (subset of account_trust_audit) | known mostly |
| `account_reinit_detector.py` | Solana 101 | **Reinit guard gaps** | mixed |
| `close_reinit_detector.py` | Emerging | **Close+reinit stale discriminator** | `[novel_instance]` priority |
| `discriminator_collision.py` | Anchor 0.30+ | **8-byte prefix collision** | mixed |
| `custom_discriminator_audit.py` | Anchor 0.30 PR#3157 | **Custom discriminator overlap** | mixed |
| `arithmetic_overflow.py` | Anchor < 0.30 | **Unchecked arithmetic** | known mostly |
| `sysvar_trust_scanner.py` | Sec3 reports | **Sysvar fake injection** | known mostly |
| `type_confusion_scanner.py` | Generic Solana | **AccountInfo cast w/o discriminator** | known mostly |
| `compute_dos_analyzer.py` | Generic | **Compute budget DoS** | known mostly |
| `callback_state_mutation.py` | Token-2022 hooks 2025 | **External callback as state mutation surface** | `[novel_instance]` priority |
| `permissionless_setup_race.py` | Anchor IDL takeover 2025 | **Permissionless one-time setup races** | `[novel_instance]` priority |
| `crypto_completeness.py` | Token-2022 ZK 2025 | **Cryptographic completeness gaps** | `[novel_instance]` priority |

## Mindset

**Don't ask**: "Did I find the Loopscale pattern?"  
**Ask**: "Did I find a NEW instance of 'any-account spoofing' class?"

**Don't ask**: "Is `transfer_to_new_account` missing state flag?"  
**Ask**: "What other instructions could bypass state machine through alternative routes?"

Each finding has a `classification` field:
- `[known_class]` — matches a specific historical exploit (valid, low novelty)
- `[novel_instance]` — new manifestation of broader class — **HIGH PRIORITY**

If all findings are `[known_class]` → you are pattern-matching, think wider.

## Related

- `../README.md` — toolkit overview
- `../threat_intel.md` — historical exploits with broader class extraction
- `../../web3/hypothesis/README.md` — EVM counterpart
- `../HIGH_VALUE_PATTERNS_SOL.md` — 35 patterns library
