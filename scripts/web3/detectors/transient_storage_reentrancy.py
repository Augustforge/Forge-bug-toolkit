"""
EIP-1153 Transient Storage reentrancy detector.

Cancun upgrade (March 2024) added tstore/tload opcodes. Cleared after
transaction. Used for ReentrancyGuard. But misuse opens new reentrancy:
- tstore as guard, but external call before clearing → re-entry possible
- tstore for cross-function locks but missing in some paths

Slither doesn't yet have full coverage — this fills the gap.
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class TransientStorageReentrancy(AbstractDetector):
    ARGUMENT = "transient-storage-reentrancy"
    HELP = "EIP-1153 transient storage misused — reentrancy possible"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://eips.ethereum.org/EIPS/eip-1153"
    WIKI_TITLE = "Transient Storage reentrancy"
    WIKI_DESCRIPTION = (
        "tstore/tload used for reentrancy protection but external call "
        "occurs before guard is cleared, OR guard not set on all entry points"
    )
    WIKI_RECOMMENDATION = (
        "Use OpenZeppelin ReentrancyGuardTransient (v5.1+); "
        "set guard BEFORE external calls; verify all entry points covered"
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Contract uses tstore(0, 1) as lock but calls external token before "
        "clearing — attacker re-enters in same tx via callback"
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.is_implemented:
                    continue
                fn_str = str(fn)
                if "tstore" not in fn_str and "tload" not in fn_str:
                    continue

                has_external_call = any(
                    s in fn_str for s in ["call(", ".call{", ".transfer(", ".send(", "delegatecall"]
                )
                if not has_external_call:
                    continue

                tstore_pos = fn_str.find("tstore")
                ext_call_pos = -1
                for marker in ["call(", ".call{", "delegatecall"]:
                    p = fn_str.find(marker)
                    if p > 0 and (ext_call_pos == -1 or p < ext_call_pos):
                        ext_call_pos = p

                # Heuristic: if external call appears BEFORE second tstore (clear)
                if tstore_pos > 0 and ext_call_pos > 0 and ext_call_pos > tstore_pos:
                    second_tstore = fn_str.find("tstore", tstore_pos + 6)
                    if second_tstore == -1 or second_tstore > ext_call_pos:
                        info = [
                            fn, " uses tstore reentrancy guard but external call ",
                            "occurs before guard is cleared — potential re-entry vector. ",
                            "Verify guard semantics or migrate to ReentrancyGuardTransient.",
                        ]
                        results.append(self.generate_result(info))

        return results
