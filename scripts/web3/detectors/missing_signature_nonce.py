"""
Custom Slither detector: signature verification without nonce.
Closes Immunefi V05 — Signature Replay gap.

Triggers when:
- Function uses ecrecover/EIP-712 signature recovery
- No nonce/deadline parameter — signed message can be replayed
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class MissingSignatureNonce(AbstractDetector):
    ARGUMENT = "missing-signature-nonce"
    HELP = "Signature verification without nonce (replay attack possible)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://swcregistry.io/docs/SWC-121"
    WIKI_TITLE = "Missing protection against signature replay"
    WIKI_DESCRIPTION = "ecrecover used without nonce permits replay attacks"
    WIKI_RECOMMENDATION = "Add monotonic nonce per address; include nonce + chainId in signed digest"
    WIKI_EXPLOIT_SCENARIO = "Attacker captures valid signature, replays it indefinitely"

    SIG_PATTERNS = ["ecrecover", "ECDSA.recover", "_hashTypedDataV4", "_recoverTypedSignature"]
    NONCE_PATTERNS = ["nonce", "_nonces", "deadline", "expir"]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.expressions:
                    continue
                fn_str = str(fn) + " " + " ".join(str(e) for e in fn.expressions)
                has_sig = any(p in fn_str for p in self.SIG_PATTERNS)
                has_nonce = any(p.lower() in fn_str.lower() for p in self.NONCE_PATTERNS)

                if has_sig and not has_nonce:
                    info = [
                        fn, " recovers signature without nonce/deadline. ",
                        "Replay attacks possible — captured signature can be reused.",
                    ]
                    results.append(self.generate_result(info))
        return results
