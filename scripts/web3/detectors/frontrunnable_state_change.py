"""
Custom Slither detector: frontrunnable state changes without commit-reveal.
Closes Immunefi V08 — Frontrunning gap.

Triggers when:
- Function changes critical state (price, fee, ownership, tier)
- No commit-reveal scheme, no batch auction, no threshold/min-stake
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class FrontrunnableStateChange(AbstractDetector):
    ARGUMENT = "frontrunnable-state-change"
    HELP = "State changes susceptible to frontrunning (Immunefi V08 gap)"
    IMPACT = DetectorClassification.MEDIUM
    CONFIDENCE = DetectorClassification.LOW

    WIKI = "https://immunefi.com/immunefi-top-10/"
    WIKI_TITLE = "Frontrunnable state change"
    WIKI_DESCRIPTION = "MEV bots can sandwich/frontrun the operation"
    WIKI_RECOMMENDATION = "Use commit-reveal, deadline + slippage, batch auction, or private mempool"
    WIKI_EXPLOIT_SCENARIO = (
        "MEV bot observes pending tx in mempool, submits same operation with higher "
        "gas to execute first (frontrun) or wraps victim's tx (sandwich). Result: "
        "user receives worse price, attacker captures the difference."
    )

    SENSITIVE_PATTERNS = ["setPrice", "setFee", "setReward", "claim", "harvest",
                          "exchange", "swap", "auction", "bid", "register"]
    PROTECTION_PATTERNS = ["commitHash", "reveal", "deadline", "slippage",
                           "minOut", "minAmountOut", "amountOutMin", "_commit"]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.name or fn.visibility not in ("public", "external"):
                    continue
                if not any(sp in fn.name.lower() for sp in self.SENSITIVE_PATTERNS):
                    continue

                fn_str = str(fn) + " ".join(str(p) for p in fn.parameters)
                params_str = " ".join(p.name or "" for p in fn.parameters)

                has_protection = (
                    any(pp in fn_str for pp in self.PROTECTION_PATTERNS)
                    or any(pp.lower() in params_str.lower() for pp in self.PROTECTION_PATTERNS)
                )
                if has_protection:
                    continue

                info = [
                    fn, " is sensitive to frontrunning (no commit-reveal/slippage/deadline). ",
                    "MEV bots can sandwich or copy this transaction. ",
                ]
                results.append(self.generate_result(info))

        return results
