"""
Custom Slither detector: upgradeable proxy without __gap reserved storage.

Pattern: upgradeable contract (initializer / upgradeable base) without
`__gap` array at the end. Adding new state vars in V2 would shift downstream
inheritance slots, causing storage collisions.

Detection:
- Contract uses Initializable / *Upgradeable from OpenZeppelin
- Last state var is NOT named `__gap` AND is NOT a fixed-size array
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


UPGRADEABLE_MARKERS = (
    "Initializable", "UUPSUpgradeable", "OwnableUpgradeable",
    "ReentrancyGuardUpgradeable", "ERC20Upgradeable", "ERC721Upgradeable",
    "AccessControlUpgradeable", "Pausable Upgradeable",
)


class StorageLayoutDrift(AbstractDetector):
    ARGUMENT = "storage-layout-drift"
    HELP = "Upgradeable contract missing __gap storage reserve"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://docs.openzeppelin.com/contracts-ethereum-package/2.5/writing-contracts#upgrade-considerations"
    WIKI_TITLE = "Upgradeable contract without __gap"
    WIKI_DESCRIPTION = (
        "Upgradeable contract should reserve storage slots via `__gap` array for future state additions. "
        "Missing __gap means adding state vars in V2 may shift inherited contracts' slots, causing collisions."
    )
    WIKI_RECOMMENDATION = "Add `uint256[50] private __gap;` (or appropriate size) at the end of state declarations."
    WIKI_EXPLOIT_SCENARIO = (
        "V1 has 10 state vars + __gap[40]. V2 wants to add 2 new vars. Without __gap, those would "
        "collide with derived contracts' storage."
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            # Check if upgradeable
            is_upgradeable = False
            for parent in contract.inheritance:
                if any(marker in parent.name for marker in UPGRADEABLE_MARKERS):
                    is_upgradeable = True
                    break

            if not is_upgradeable:
                continue

            # Find storage variables (skip constants/immutables)
            storage_vars = [v for v in contract.state_variables if not v.is_constant and not v.is_immutable]
            if not storage_vars:
                continue

            # Check if last var is __gap or similar
            last_var = storage_vars[-1]
            if last_var.name and (
                "__gap" in last_var.name or
                "_gap" in last_var.name or
                "reserved" in last_var.name.lower()
            ):
                continue

            info = [
                "Upgradeable contract `",
                contract,
                "` has no `__gap` storage reserve. Adding state in V2 may corrupt inherited layout.\n",
            ]
            results.append(self.generate_result(info))
        return results
