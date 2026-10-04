"""
Custom Slither detector: multi-step swap slippage check with shared intermediate tokens.

Pattern from Rhea Finance (April 2026, $18.4M):
- Slippage algo summed expected outputs across all steps
- Did not account for reuse of intermediate tokens between steps
- Double-counting: same liquidity counted multiple times → false slippage tolerance
- 2 days prep: 423 wallets, fake pools

Triggers when:
- Function does multi-step swap (loop over path / steps array)
- Computes total expected output as sum of step outputs
- Does NOT track unique tokens / detect circular paths
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class SlippageSharedIntermediates(AbstractDetector):
    ARGUMENT = "slippage-shared-intermediates"
    HELP = "Multi-step swap slippage without unique-path validation (Rhea pattern)"
    IMPACT = DetectorClassification.MEDIUM
    CONFIDENCE = DetectorClassification.LOW

    WIKI = "https://ambcrypto.com/rhea-finance-revises-exploit-losses-to-18-4m-confirms-slippage-flaw-as-funds-partially-recovered/"
    WIKI_TITLE = "Slippage check vulnerable to circular intermediate tokens"
    WIKI_DESCRIPTION = (
        "Multi-step swap aggregator sums step-level expected outputs. If path contains "
        "shared/circular tokens, same liquidity contributes to slippage tolerance multiple "
        "times → attacker can drain pools while passing slippage check."
    )
    WIKI_RECOMMENDATION = (
        "Track unique tokens encountered in path. Reject paths with duplicate intermediate "
        "tokens or detect circular cycles. Validate end-to-end (tokenIn → tokenOut) net "
        "amount, not sum of step deltas."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Rhea Finance (Apr 2026): aggregator algorithm summed each step's expected output. "
        "Attacker constructed path with shared intermediates, same liquidity counted in "
        "multiple steps. $18.4M drained passing slippage check."
    )

    SWAP_MARKERS = [
        "multiSwap", "swapExactInputMultihop", "swapMulti",
        "executePath", "executeSwaps", "_executeSwap",
        "for (uint", "for(uint", "while (",
        "steps", "path[", "swaps[", "routes[",
    ]

    SLIPPAGE_MARKERS = [
        "minOut", "amountOutMin", "minAmountOut",
        "expectedOut", "totalExpected",
        "+= amountOut", "+= expectedAmount",
        "slippage", "slippageTolerance",
    ]

    UNIQUENESS_MARKERS = [
        "uniqueTokens", "seenTokens", "visited",
        "tokenSet", "_tokenSeen",
        "circular", "duplicate",
    ]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.expressions:
                    continue
                if fn.visibility not in ("external", "public", "internal"):
                    continue

                fn_str = " ".join(str(e) for e in fn.expressions)
                fn_name = fn.name or ""

                is_swap_loop = any(m in fn_str or m in fn_name for m in self.SWAP_MARKERS)
                if not is_swap_loop:
                    continue

                has_slippage = any(m in fn_str for m in self.SLIPPAGE_MARKERS)
                if not has_slippage:
                    continue

                has_uniqueness_check = any(m in fn_str for m in self.UNIQUENESS_MARKERS)
                if has_uniqueness_check:
                    continue

                info = [
                    fn, " performs multi-step swap with slippage aggregation but does ",
                    "not track unique intermediate tokens. Circular/shared paths bypass ",
                    "slippage check (Rhea $18.4M, Apr 2026).",
                ]
                results.append(self.generate_result(info))

        return results
