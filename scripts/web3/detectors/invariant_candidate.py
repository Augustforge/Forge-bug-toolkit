"""
Custom Slither detector: comments declaring invariants.

When a developer writes `@dev MUST be true` or "should always" — they've
documented an invariant. Worth testing if it actually holds.

Output flags lines for invariant-test generation via
scripts/web3/hypothesis/invariant_generator.py
"""

import re

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


INVARIANT_PATTERNS = [
    re.compile(r"\bMUST\b", re.IGNORECASE),
    re.compile(r"\b(should\s+(always|never))\b", re.IGNORECASE),
    re.compile(r"\binvariant[s]?\b", re.IGNORECASE),
    re.compile(r"\b(always|never)\s+holds?\b", re.IGNORECASE),
    re.compile(r"@dev.*assumes?\b", re.IGNORECASE),
    re.compile(r"\bcannot\s+(happen|be|exceed)\b", re.IGNORECASE),
]


class InvariantCandidate(AbstractDetector):
    ARGUMENT = "invariant-candidate"
    HELP = "Comments declaring invariants — flag for invariant testing"
    IMPACT = DetectorClassification.INFORMATIONAL
    CONFIDENCE = DetectorClassification.HIGH

    WIKI = "https://docs.bbt/invariant-candidate"
    WIKI_TITLE = "Invariant declared in comment"
    WIKI_DESCRIPTION = (
        "Function carries a comment claiming an invariant or assumption. "
        "Verify that the invariant actually holds via Foundry `invariant_*` test."
    )
    WIKI_RECOMMENDATION = "Generate Foundry invariant test using scripts/web3/hypothesis/invariant_generator.py"
    WIKI_EXPLOIT_SCENARIO = "If developer-documented invariant fails to hold, bug class follows."

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                # Look at NatSpec / inline comments
                # Slither's documentation property holds NatSpec
                doc = getattr(fn, "documentation", None) or ""
                if not doc and hasattr(fn, "natspec"):
                    doc = str(getattr(fn, "natspec", ""))
                if not doc:
                    continue
                for pattern in INVARIANT_PATTERNS:
                    if pattern.search(doc):
                        info = [
                            "Function `",
                            fn,
                            "` documents an invariant in comments: \"",
                            doc[:200].replace("\n", " "),
                            "\". Flag for invariant testing.\n",
                        ]
                        results.append(self.generate_result(info))
                        break  # one finding per fn
        return results
