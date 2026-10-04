# Solana Hypothesis Checklists Index

Each checklist describes a hypothesis class, signals, and verification steps.

| Checklist | Class | Trigger script |
|---|---|---|
| [signer_check.md](signer_check.md) | Signer identity gaps | `hypothesis/signer_check_scanner.py` |
| [owner_check.md](owner_check.md) | Account owner gaps | `hypothesis/owner_check_scanner.py` |
| [pda_seed_uniqueness.md](pda_seed_uniqueness.md) | PDA seed collision | `hypothesis/pda_seed_analyzer.py` |
| [cpi_authority.md](cpi_authority.md) | CPI auth + program ID gaps | `hypothesis/cpi_authority_checker.py`, `cpi_program_id_validator.py` |
| [account_reinit.md](account_reinit.md) | Reinit + close+reinit | `hypothesis/account_reinit_detector.py`, `close_reinit_detector.py` |
| [discriminator_safety.md](discriminator_safety.md) | Discriminator collision | `hypothesis/discriminator_collision.py`, `custom_discriminator_audit.py` |
| [sysvar_trust.md](sysvar_trust.md) | Sysvar fake injection | `hypothesis/sysvar_trust_scanner.py` |
| [type_confusion.md](type_confusion.md) | AccountInfo cast gaps | `hypothesis/type_confusion_scanner.py` |
| [compute_budget.md](compute_budget.md) | CU DoS | `hypothesis/compute_dos_analyzer.py` |
| [rust_unsafe_blocks.md](rust_unsafe_blocks.md) | Unsafe code review | `detectors/cargo_geiger_wrapper.py` |

## Workflow

1. Run all hypothesis scripts via `scan.sh`
2. For each finding, open relevant checklist
3. Run through manual verification steps
4. Filter `[known_class]` (lower priority) and `[novel_instance]` (HIGH priority)
5. Build PoC for novel instances
