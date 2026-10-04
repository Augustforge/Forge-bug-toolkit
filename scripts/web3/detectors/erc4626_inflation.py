"""
ERC-4626 vault inflation attack detector.

First-depositor attack pattern: attacker deposits 1 wei, donates large amount
directly to vault, next depositor's shares round to 0 → loses entire deposit.

Mitigations checked:
- OpenZeppelin v5+ virtual shares (decimals offset)
- Dead shares (initial mint to address(0) or burn)
- minDeposit threshold
- Internal accounting separate from balanceOf
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class ERC4626Inflation(AbstractDetector):
    ARGUMENT = "erc4626-inflation"
    HELP = "ERC-4626 vault vulnerable to inflation/donation attack"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://docs.openzeppelin.com/contracts/5.x/erc4626"
    WIKI_TITLE = "ERC-4626 inflation attack"
    WIKI_DESCRIPTION = (
        "Vault calculates shares = assets * totalSupply / totalAssets. "
        "First depositor with 1 wei + direct donation manipulates exchange rate "
        "so subsequent depositors get 0 shares for non-trivial deposits"
    )
    WIKI_RECOMMENDATION = (
        "Use OpenZeppelin v5+ ERC4626 (built-in virtual shares + decimals offset), "
        "OR mint dead shares on first deposit, OR enforce minimum first deposit"
    )
    WIKI_EXPLOIT_SCENARIO = (
        "1. Attacker deposits 1 wei (gets 1 share). "
        "2. Attacker transfers 1000 USDC directly to vault contract. "
        "3. Victim deposits 999 USDC → shares = 999 * 1 / 1000 = 0 → 999 lost."
    )

    ERC4626_FUNCTIONS = {"deposit", "mint", "withdraw", "redeem",
                          "convertToShares", "convertToAssets",
                          "previewDeposit", "previewMint",
                          "previewWithdraw", "previewRedeem",
                          "totalAssets", "asset"}

    PROTECTION_PATTERNS = [
        "_decimalsOffset",
        "virtualShares",
        "DEAD_SHARES",
        "MIN_DEPOSIT",
        "_initialDeposit",
        "internal_balance",
        "totalAssets_internal",
    ]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            fn_names = {fn.name for fn in contract.functions}
            erc4626_score = len(self.ERC4626_FUNCTIONS & fn_names)
            if erc4626_score < 4:
                continue  # not an ERC4626 vault

            contract_str = str(contract)

            # Check OpenZeppelin v5+ inheritance
            if "ERC4626" in [str(p) for p in contract.inheritance]:
                if any("v5" in str(c) or "5.0" in str(c) or "_decimalsOffset" in str(c)
                       for c in contract.inheritance + [contract]):
                    continue  # likely safe v5+ implementation

            has_protection = any(p in contract_str for p in self.PROTECTION_PATTERNS)
            uses_balance_of = "balanceOf(address(this))" in contract_str
            uses_internal_accounting = any(
                p in contract_str for p in ["_totalAssets", "totalDeposited", "internal_assets"]
            )

            if not has_protection and uses_balance_of and not uses_internal_accounting:
                info = [
                    contract,
                    " is ERC-4626 vault (",
                    str(erc4626_score),
                    " ERC4626 functions) without inflation attack protection. ",
                    "Uses balanceOf for totalAssets and lacks virtual shares / dead shares / min deposit. ",
                    "First-depositor donation attack feasible.",
                ]
                results.append(self.generate_result(info))

        return results
