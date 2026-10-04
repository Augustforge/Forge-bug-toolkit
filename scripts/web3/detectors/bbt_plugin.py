"""
Slither plugin entry module — the sole purpose of this file is to provide a
named module for the entry_point in setup.py.

See __init__.py for the make_plugin() logic.
"""

from oracle_single_source import OracleSingleSource
from missing_signature_nonce import MissingSignatureNonce
from timelock_too_short import TimelockTooShort
from missing_circuit_breaker import MissingCircuitBreaker
from frontrunnable_state_change import FrontrunnableStateChange
from transient_storage_reentrancy import TransientStorageReentrancy
from erc4626_inflation import ERC4626Inflation
from erc4337_issues import ERC4337Issues
from hook_callback_unauthorized import HookCallbackUnauthorized
from layerzero_verifier_count import LayerzeroVerifierCount
from cpimp_proxy_init import CpimpProxyInit
from groth16_setup_check import Groth16SetupCheck
from signature_scope_coverage import SignatureScopeCoverage
from erc3525_reentrancy import Erc3525Reentrancy
from slippage_shared_intermediates import SlippageSharedIntermediates
from unprotected_role_granting import UnprotectedRoleGranting
# Phase J additions (deephunt v2)
from asymmetric_modifier import AsymmetricModifier
from economic_misalignment import EconomicMisalignment
from composable_external_calls import ComposableExternalCalls
from invariant_candidate import InvariantCandidate
from storage_layout_drift import StorageLayoutDrift
from readonly_reentrancy import ReadonlyReentrancy
from eip1271_lying import Eip1271Lying


def make_plugin():
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
        # Phase J additions
        AsymmetricModifier,
        EconomicMisalignment,
        ComposableExternalCalls,
        InvariantCandidate,
        StorageLayoutDrift,
        ReadonlyReentrancy,
        Eip1271Lying,
    ]
    printers = []
    return detectors, printers
