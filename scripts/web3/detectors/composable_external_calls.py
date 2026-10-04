"""
Custom Slither detector: function with 5+ external calls.

High composability surface = harder to reason about reentrancy, state consistency,
gas griefing, oracle staleness propagation. Flag for manual review.
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class ComposableExternalCalls(AbstractDetector):
    ARGUMENT = "composable-external-calls"
    HELP = "Function makes 5+ external calls (high composability risk)"
    IMPACT = DetectorClassification.MEDIUM
    CONFIDENCE = DetectorClassification.HIGH

    WIKI = "https://docs.bbt/composable-calls"
    WIKI_TITLE = "Highly composable function"
    WIKI_DESCRIPTION = (
        "Function makes many external calls in single tx. Each call is a potential reentrancy/"
        "revert/state-inconsistency point. Bugs at the seam between protocols often live here."
    )
    WIKI_RECOMMENDATION = "Review composability — verify reentrancy guards, validate intermediate state, consider checks-effects-interactions ordering."
    WIKI_EXPLOIT_SCENARIO = "Protocol A calls B, then C, then D. If C reverts or returns unexpected, state of A may be inconsistent."

    THRESHOLD = 5

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.is_implemented or fn.view or fn.pure:
                    continue
                external_call_count = 0
                seen_calls = set()
                for node in fn.nodes:
                    for call in node.external_calls_as_expressions:
                        # Use string repr to dedupe identical call patterns
                        key = str(call)
                        if key in seen_calls:
                            continue
                        seen_calls.add(key)
                        external_call_count += 1
                if external_call_count >= self.THRESHOLD:
                    info = [
                        "Function `",
                        fn,
                        f"` makes {external_call_count} external calls. ",
                        "High composability — review for reentrancy, state consistency at each call boundary.\n",
                    ]
                    results.append(self.generate_result(info))
        return results
