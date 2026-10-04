"""
Custom Slither detectors for Immunefi Top 10 gaps + recent attack patterns
(May 2026 — Halborn case studies, Blockaid alerts).

Registers as Slither plugin via slither_analyzer.plugin entry_point.
Install:  pip install -e scripts/web3/detectors/

Or run with explicit detector-path flag:
    slither . --detect <name> using PYTHONPATH=scripts/web3
"""

from .oracle_single_source import OracleSingleSource
from .missing_signature_nonce import MissingSignatureNonce
from .timelock_too_short import TimelockTooShort
from .missing_circuit_breaker import MissingCircuitBreaker
from .frontrunnable_state_change import FrontrunnableStateChange
from .transient_storage_reentrancy import TransientStorageReentrancy
from .erc4626_inflation import ERC4626Inflation
from .erc4337_issues import ERC4337Issues
# May 2026 attack patterns
from .hook_callback_unauthorized import HookCallbackUnauthorized
from .layerzero_verifier_count import LayerzeroVerifierCount
from .cpimp_proxy_init import CpimpProxyInit
from .groth16_setup_check import Groth16SetupCheck
from .signature_scope_coverage import SignatureScopeCoverage
from .erc3525_reentrancy import Erc3525Reentrancy
from .slippage_shared_intermediates import SlippageSharedIntermediates
# TrustedVolumes May 2026 pattern
from .unprotected_role_granting import UnprotectedRoleGranting


def make_plugin():
    """Slither plugin entry point — returns (detectors, printers)."""
    detectors = [
        OracleSingleSource,
        MissingSignatureNonce,
        TimelockTooShort,
        MissingCircuitBreaker,
        FrontrunnableStateChange,
        TransientStorageReentrancy,
        ERC4626Inflation,
        ERC4337Issues,
        HookCallbackUnauthorized,
        LayerzeroVerifierCount,
        CpimpProxyInit,
        Groth16SetupCheck,
        SignatureScopeCoverage,
        Erc3525Reentrancy,
        SlippageSharedIntermediates,
        UnprotectedRoleGranting,
    ]
    printers = []
    return detectors, printers
