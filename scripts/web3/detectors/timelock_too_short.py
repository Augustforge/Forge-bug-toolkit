"""
Custom Slither detector: timelock with delay < 48 hours.
Closes Immunefi V10 — Governance Attacks gap.

Triggers when:
- Contract is Timelock-style (has delay state variable)
- Default delay < 48 hours (172800 seconds) for high-impact governance
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification

MIN_SAFE_DELAY = 172800  # 48 hours


class TimelockTooShort(AbstractDetector):
    ARGUMENT = "timelock-too-short"
    HELP = "Timelock with insufficient delay for governance (<48h)"
    IMPACT = DetectorClassification.MEDIUM
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://immunefi.com/immunefi-top-10/"
    WIKI_TITLE = "Insufficient timelock delay"
    WIKI_DESCRIPTION = "Governance timelock < 48h does not give users enough time to react"
    WIKI_RECOMMENDATION = "Set MIN_DELAY ≥ 48 hours; 7 days for high-TVL protocols"
    WIKI_EXPLOIT_SCENARIO = "Compromised governance executes malicious proposal before users can exit"

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            name_lower = contract.name.lower()
            if "timelock" not in name_lower and "governor" not in name_lower:
                continue

            for var in contract.state_variables:
                if not var.name or "delay" not in var.name.lower():
                    continue
                value = getattr(var, "expression", None)
                if value is None:
                    continue
                value_str = str(value)
                try:
                    if "minutes" in value_str or "hours" in value_str:
                        if "minutes" in value_str:
                            n = int("".join(c for c in value_str if c.isdigit()) or "0")
                            if n * 60 < MIN_SAFE_DELAY:
                                results.append(self.generate_result([
                                    var, f" — timelock delay {n} minutes < 48 hours. ",
                                    "Insufficient for users to react to malicious proposals.",
                                ]))
                        elif "hours" in value_str:
                            n = int("".join(c for c in value_str if c.isdigit()) or "0")
                            if n * 3600 < MIN_SAFE_DELAY:
                                results.append(self.generate_result([
                                    var, f" — timelock delay {n} hours < 48 hours.",
                                ]))
                    else:
                        try:
                            n = int(value_str)
                            if 0 < n < MIN_SAFE_DELAY:
                                results.append(self.generate_result([
                                    var, f" — timelock delay {n} seconds < 48 hours.",
                                ]))
                        except ValueError:
                            pass
                except Exception:
                    continue

        return results
