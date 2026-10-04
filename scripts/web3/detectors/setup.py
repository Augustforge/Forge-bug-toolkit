"""
Slither plugin packaging for the bug-bounty-toolkit custom detectors.

Install in dev mode:
    pip install -e scripts/web3/detectors/

After installation the detectors are available through `slither` directly without --detector-include.
"""

from setuptools import setup, find_packages

setup(
    name="bbt_slither_detectors",
    version="1.0.0",
    description="Custom Slither detectors for bug bounty hunting",
    py_modules=[
        "oracle_single_source",
        "missing_signature_nonce",
        "timelock_too_short",
        "missing_circuit_breaker",
        "frontrunnable_state_change",
        "transient_storage_reentrancy",
        "erc4626_inflation",
        "erc4337_issues",
        "hook_callback_unauthorized",
        "layerzero_verifier_count",
        "cpimp_proxy_init",
        "groth16_setup_check",
        "signature_scope_coverage",
        "erc3525_reentrancy",
        "slippage_shared_intermediates",
        "unprotected_role_granting",
        "bbt_plugin",
    ],
    install_requires=["slither-analyzer>=0.10.0"],
    entry_points={
        "slither_analyzer.plugin": ["bbt=bbt_plugin:make_plugin"],
    },
)
