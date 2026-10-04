"""Long-undiscovered bug detection scripts.

Targets bugs which evaded multiple audits because:
- Rare state setup required (state_setup_miner)
- Auditors trusted the code at "approved" level (audit_rebuttal_analyzer)
- Manifest only via composability with other protocols (composability_matrix)
- Trigger only after reorg / specific block ordering (reorg_safety, block_ordering)
- Underconstrained ZK circuit (zk_circuit_audit)
- Specific to chain quirks (handled by chain_quirks/)
- Historical state matters (historical_state_analyzer)
- Edge value range (edge_case_generator)
"""
