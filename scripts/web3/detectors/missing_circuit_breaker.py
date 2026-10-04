"""
Custom Slither detector: critical functions without emergency pause.
Closes Immunefi V10 — Governance Attacks gap (defensive layer).

Triggers when:
- Contract has high-value functions (deposit, withdraw, mint, transfer)
- No Pausable/circuit breaker mechanism detected
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class MissingCircuitBreaker(AbstractDetector):
    ARGUMENT = "missing-circuit-breaker"
    HELP = "Critical functions without emergency pause mechanism"
    IMPACT = DetectorClassification.MEDIUM
    CONFIDENCE = DetectorClassification.LOW

    WIKI = "https://consensys.github.io/smart-contract-best-practices/development-recommendations/precautions/circuit-breakers/"
    WIKI_TITLE = "Missing circuit breaker"
    WIKI_DESCRIPTION = "Cannot pause exploit in progress; funds drain unimpeded"
    WIKI_RECOMMENDATION = "Implement OpenZeppelin Pausable; pause critical functions"
    WIKI_EXPLOIT_SCENARIO = "Active exploit cannot be halted while team responds"

    CRITICAL_FUNCTIONS = ["deposit", "withdraw", "mint", "redeem", "borrow",
                          "repay", "swap", "flashLoan"]
    PAUSE_PATTERNS = ["whenNotPaused", "Pausable", "_pause", "paused()", "stopped"]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            critical_fns = [
                fn for fn in contract.functions
                if fn.name and any(cp in fn.name.lower() for cp in self.CRITICAL_FUNCTIONS)
                and fn.visibility in ("public", "external")
            ]
            if not critical_fns:
                continue

            contract_str = str(contract)
            has_pause = any(p in contract_str for p in self.PAUSE_PATTERNS)
            if has_pause:
                continue

            unpaused_critical = []
            for fn in critical_fns:
                fn_str = str(fn) + " ".join(str(m) for m in fn.modifiers)
                if not any(p in fn_str for p in self.PAUSE_PATTERNS):
                    unpaused_critical.append(fn)

            if unpaused_critical:
                info = [contract, ": ", str(len(unpaused_critical)),
                        " critical functions lack pause modifier — ",
                        "active exploit cannot be halted. ",
                        "Functions: ", ", ".join(fn.name for fn in unpaused_critical[:5])]
                results.append(self.generate_result(info))

        return results
