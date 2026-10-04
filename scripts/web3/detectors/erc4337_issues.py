"""
ERC-4337 (Account Abstraction) detector.

New attack surface introduced by EIP-4337:
- Paymaster validation issues (sponsor unauthorized userOps)
- Bundler ordering manipulation
- UserOperation malformation in validateUserOp
- Storage access violations during validation phase
- Time-range bypass (validUntil/validAfter)

Most existing tooling doesn't cover this — it's a fresh attack class.
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class ERC4337Issues(AbstractDetector):
    ARGUMENT = "erc4337-issues"
    HELP = "ERC-4337 paymaster/wallet validation issues"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.LOW

    WIKI = "https://eips.ethereum.org/EIPS/eip-4337"
    WIKI_TITLE = "ERC-4337 validation issue"
    WIKI_DESCRIPTION = (
        "validateUserOp / validatePaymasterUserOp must obey storage access rules "
        "(EREP-010, OP-031). Time-range fields validUntil/validAfter must be enforced."
    )
    WIKI_RECOMMENDATION = (
        "Follow ERC-7562 storage rules; enforce time-range; validate signature "
        "before any external interaction; restrict paymaster sponsorship logic"
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Paymaster validates userOp without signature check or external call before "
        "validation completes. Attacker submits crafted userOp; bundler picks up; "
        "paymaster sponsors malicious operation, attacker drains paymaster deposit."
    )

    AA_FUNCTIONS = {"validateUserOp", "validatePaymasterUserOp", "_validateSignature"}

    DANGEROUS_PATTERNS_IN_VALIDATION = [
        ".call(", ".staticcall(", "external(",
        "block.timestamp",
        "transfer(",
        "delegatecall",
    ]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if fn.name not in self.AA_FUNCTIONS:
                    continue

                fn_str = str(fn)
                issues = []

                if fn.name == "validateUserOp" or fn.name == "validatePaymasterUserOp":
                    has_validation = any(
                        p in fn_str for p in ["ECDSA.recover", "ecrecover", "_validateSignature"]
                    )
                    if not has_validation:
                        issues.append("missing signature validation")

                    if "validUntil" not in fn_str and "validAfter" not in fn_str:
                        issues.append("time-range fields not enforced (validUntil/validAfter)")

                    dangerous = [p for p in self.DANGEROUS_PATTERNS_IN_VALIDATION if p in fn_str]
                    if dangerous:
                        issues.append(
                            f"violates storage access rules: {', '.join(dangerous[:3])}"
                        )

                    if fn.name == "validatePaymasterUserOp":
                        if "msg.sender" not in fn_str:
                            issues.append("paymaster does not verify caller is EntryPoint")

                if issues:
                    info = [
                        fn, " (ERC-4337) has issues: ",
                        "; ".join(issues),
                        ". Reference EIP-4337 / ERC-7562 storage rules.",
                    ]
                    results.append(self.generate_result(info))

        return results
