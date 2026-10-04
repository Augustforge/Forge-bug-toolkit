"""
Custom Slither detector: economic misalignment.

Flags patterns where economic incentives can be broken by admin config:
- fee = uint256 max / 100% allowed
- unbounded multiplier on rewards
- mint > burn ratio mismatch
- protocol fee > 100%
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


FEE_VAR_PATTERNS = ("fee", "rate", "bps", "percent", "ratio", "multiplier", "bonus")


class EconomicMisalignment(AbstractDetector):
    ARGUMENT = "economic-misalignment"
    HELP = "Admin-settable economic params without bounds checks (fee/rate/multiplier)"
    IMPACT = DetectorClassification.MEDIUM
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://docs.bbt/economic-misalignment"
    WIKI_TITLE = "Economic param without bounds check"
    WIKI_DESCRIPTION = (
        "Admin-settable economic parameter (fee, rate, multiplier) without explicit upper bound. "
        "Admin can set value at extremes (e.g., fee=100%, multiplier=type(uint256).max), "
        "breaking economic invariants."
    )
    WIKI_RECOMMENDATION = "Add `require(newValue <= MAX_BOUND)` in the setter."
    WIKI_EXPLOIT_SCENARIO = (
        "Admin sets `protocolFee = 10000` (100%). User deposit results in 0 tokens received."
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.is_implemented:
                    continue
                # Skip view/pure
                if fn.view or fn.pure:
                    continue
                fn_name_low = fn.name.lower()
                # Look for setters of fee-like params
                is_setter = fn_name_low.startswith("set") or fn_name_low.startswith("update") or fn_name_low.startswith("change")
                if not is_setter:
                    continue
                if not any(pat in fn_name_low for pat in FEE_VAR_PATTERNS):
                    continue

                # Check if there's a require/if bound on the input param
                has_bound_check = False
                for node in fn.nodes:
                    if node.contains_require_or_assert():
                        # Crude: look for require expression mentioning the params
                        for expr in node.expressions:
                            expr_str = str(expr).lower()
                            if any(p in fn_name_low for p in FEE_VAR_PATTERNS) and (
                                "<=" in expr_str or "<" in expr_str or "max" in expr_str
                            ):
                                has_bound_check = True
                                break
                    if has_bound_check:
                        break

                if not has_bound_check:
                    info = [
                        "Setter `",
                        fn,
                        "` modifies an economic parameter (fee/rate/multiplier) without explicit upper bound. ",
                        "Admin can set extreme value, breaking economic invariants.\n",
                    ]
                    results.append(self.generate_result(info))
        return results
