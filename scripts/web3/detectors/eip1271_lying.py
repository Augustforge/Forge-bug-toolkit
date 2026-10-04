"""
Custom Slither detector: EIP-1271 signature trust without ECDSA fallback.

Pattern: contract calls `IERC1271(signer).isValidSignature(hash, sig)` and trusts
the magic value return. Malicious contract wallet returns magic value for any
input → bypasses sig check.

Mitigation: prefer ECDSA recovery for EOAs, only fall back to 1271 when signer is verified contract.
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class Eip1271Lying(AbstractDetector):
    ARGUMENT = "eip1271-lying"
    HELP = "EIP-1271 isValidSignature trusted without ECDSA fallback for EOA case"
    IMPACT = DetectorClassification.MEDIUM
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://eips.ethereum.org/EIPS/eip-1271"
    WIKI_TITLE = "EIP-1271 signature trust"
    WIKI_DESCRIPTION = (
        "Contract uses ERC-1271 isValidSignature for signature verification. Malicious "
        "smart-contract wallet returns the magic value `0x1626ba7e` for any input."
    )
    WIKI_RECOMMENDATION = (
        "Use OpenZeppelin's SignatureChecker which combines ECDSA + 1271 with proper checks, "
        "OR verify signer.code.length first to distinguish EOA vs contract."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "User attempts to sign approval. Attacker provides their malicious wallet as signer. "
        "Wallet's isValidSignature always returns true. Protocol accepts arbitrary 'signature'."
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.is_implemented:
                    continue
                uses_1271 = False
                uses_ecrecover = False
                for node in fn.nodes:
                    for call_expr in node.external_calls_as_expressions:
                        call_str = str(call_expr)
                        if "isValidSignature" in call_str:
                            uses_1271 = True
                    for ir in node.irs:
                        ir_str = str(ir)
                        if "ecrecover" in ir_str.lower() or "ECDSA" in ir_str:
                            uses_ecrecover = True
                if uses_1271 and not uses_ecrecover:
                    info = [
                        "Function `",
                        fn,
                        "` calls `isValidSignature` (EIP-1271) without ECDSA fallback. "
                        "Smart-contract wallets can lie about validity.\n",
                    ]
                    results.append(self.generate_result(info))
        return results
