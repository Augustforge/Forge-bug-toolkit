"""
Custom Slither detector: read-only reentrancy candidate.

Curve 2023 attack class. View functions returning a price/state can be called
mid-tx during external callback in another function, while the callbacked
function's state writes are not yet committed.

Detection heuristic:
- View function exists that returns a derived value (price, share, etc.)
- Another non-view function does state writes BETWEEN external calls
- AND those state writes affect the view function's calculation
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


VIEW_RETURN_PATTERNS = (
    "getPrice", "price", "rate", "share", "value", "balance",
    "virtual_price", "convertToAssets", "convertToShares",
    "totalAssets", "totalSupply", "previewWithdraw", "previewRedeem",
    "previewDeposit", "previewMint",
)


class ReadonlyReentrancy(AbstractDetector):
    ARGUMENT = "readonly-reentrancy"
    HELP = "View function may return stale state during external callback (Curve pattern)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.LOW  # heuristic, requires manual verification

    WIKI = "https://www.chainsecurity.com/blog/curve-lp-oracle-manipulation-post-mortem"
    WIKI_TITLE = "Read-only reentrancy candidate"
    WIKI_DESCRIPTION = (
        "View function returns derived value (price/share/rate). If non-view function modifies "
        "state between external calls, attacker callback during that window can read stale value."
    )
    WIKI_RECOMMENDATION = "Add nonReentrant modifier to view function OR ensure consistent state before external calls."
    WIKI_EXPLOIT_SCENARIO = (
        "Curve LP token oracle reads via get_virtual_price(). During pool.remove_liquidity, "
        "balances are reduced before lp_token.burn. Attacker callback reads inflated virtual_price."
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            # Find candidate view functions
            view_fns = [
                f for f in contract.functions
                if f.is_implemented and f.view
                and any(pat.lower() in f.name.lower() for pat in VIEW_RETURN_PATTERNS)
            ]
            if not view_fns:
                continue

            # Find non-view functions that make external calls AND modify state
            for fn in contract.functions:
                if not fn.is_implemented or fn.view or fn.pure:
                    continue
                external_calls_count = sum(1 for n in fn.nodes for _ in n.external_calls_as_expressions)
                writes_state = bool(fn.state_variables_written)
                if external_calls_count >= 1 and writes_state:
                    # Heuristic match — flag pairing
                    for view_fn in view_fns:
                        # Check if state vars written by fn are read by view_fn
                        if any(v in view_fn.state_variables_read for v in fn.state_variables_written):
                            info = [
                                "Function `",
                                fn,
                                "` modifies state used by view function `",
                                view_fn,
                                "` while making external calls. Potential read-only reentrancy.\n",
                            ]
                            results.append(self.generate_result(info))
                            break
        return results
