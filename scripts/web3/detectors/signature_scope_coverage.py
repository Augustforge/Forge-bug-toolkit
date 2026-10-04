"""
Custom Slither detector: signature digest does not cover all execution-affecting params.

Pattern from GiddyDeFi (April 2026, $1.3M):
- Backend signed only the swap.data field
- Contract accepted unsigned wrapper fields: target, token, amount, approval target
- Attacker took valid signature, replaced unsigned fields with their own values
- transfer-to-self executed against any user

Triggers when:
- Function uses ECDSA.recover / ecrecover / _hashTypedDataV4
- Function has parameters NOT included in signed digest
- Specifically: target/to/recipient/amount/token not in abi.encode(...)
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class SignatureScopeCoverage(AbstractDetector):
    ARGUMENT = "signature-scope-coverage"
    HELP = "Signature does not cover all execution-affecting params (Giddy pattern)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.LOW

    WIKI = "https://www.halborn.com/blog/post/month-in-review-top-defi-hacks-of-april-2026"
    WIKI_TITLE = "Partial signature scope coverage"
    WIKI_DESCRIPTION = (
        "Signature digest covers only a subset of the function parameters. Attacker "
        "takes a valid signature and substitutes their own values for the unsigned fields, "
        "redirecting funds, changing recipients, or escalating privileges."
    )
    WIKI_RECOMMENDATION = (
        "Include ALL execution-affecting params in the signed digest: recipient, token, "
        "amount, target, approval spender, deadline, nonce. Use EIP-712 typed struct."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Giddy (Apr 2026): backend signed only swap.data. Contract accepted target/"
        "amount/token as unsigned params. Attacker reused valid signature with "
        "modified target/amount. $1.3M drained from approving users."
    )

    SIG_RECOVERY = [
        "ecrecover", "ECDSA.recover", "_hashTypedDataV4",
        "_recoverTypedSignature", "tryRecover",
    ]

    SENSITIVE_PARAMS = [
        "to", "target", "recipient", "receiver", "destination",
        "amount", "value", "amountIn", "amountOut",
        "token", "tokenIn", "tokenOut", "asset",
        "spender", "approvedSpender",
        "data", "callData", "payload",
    ]

    DIGEST_BUILDERS = [
        "abi.encode", "keccak256", "abi.encodePacked",
        "_hashTypedDataV4", "_buildDomainSeparator",
    ]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.expressions:
                    continue
                if fn.visibility not in ("external", "public"):
                    continue

                fn_str = " ".join(str(e) for e in fn.expressions)
                if not any(s in fn_str for s in self.SIG_RECOVERY):
                    continue

                params = [p.name for p in fn.parameters if p.name]
                if not params:
                    continue

                sensitive_in_params = [p for p in params
                                       if any(s.lower() in p.lower()
                                              for s in self.SENSITIVE_PARAMS)]
                if not sensitive_in_params:
                    continue

                digest_section = ""
                for builder in self.DIGEST_BUILDERS:
                    if builder in fn_str:
                        idx = fn_str.find(builder)
                        end_idx = fn_str.find(")", idx)
                        if end_idx > idx:
                            digest_section += fn_str[idx:end_idx]

                if not digest_section:
                    continue

                missing = []
                for p in sensitive_in_params:
                    if p not in digest_section:
                        missing.append(p)

                if missing:
                    info = [
                        fn, f" recovers signature but params [{', '.join(missing)}] are ",
                        "NOT included in digest. Attacker can substitute these values ",
                        "while reusing valid signature (Giddy $1.3M, Apr 2026).",
                    ]
                    results.append(self.generate_result(info))

        return results
