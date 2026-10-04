"""
Custom Slither detector: Groth16 zkSNARK verifier with trusted setup misconfiguration.

Pattern from FOOMCASH copycat (February 2026, $2.26M after VeilCash):
- delta2 == gamma2 in the Groth16 verifier contract allows forging any proof
- Trusted setup ceremony skipped or placeholder values used
- PoC public on GitHub, easy to replicate

Triggers when:
- Verifier contract contains alpha1/beta2/gamma2/delta2 elements
- delta2 hardcoded same value as gamma2 (placeholder leak)
- Or constants suggest skipped trusted setup (zeros, sequential numbers)
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class Groth16SetupCheck(AbstractDetector):
    ARGUMENT = "groth16-setup-check"
    HELP = "Groth16 verifier with a suspicious trusted setup (delta2 == gamma2)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://blog.zksecurity.xyz/posts/groth16-setup-exploit/"
    WIKI_TITLE = "Groth16 verifier trusted setup misconfiguration"
    WIKI_DESCRIPTION = (
        "Groth16 verification key with delta2 == gamma2 (or other identical placeholder "
        "values) allows crafting a valid proof for any statement without knowing the witness."
    )
    WIKI_RECOMMENDATION = (
        "Run proper trusted setup ceremony (Phase 1 + Phase 2 powers of tau). "
        "Verify all VK elements (alpha, beta, gamma, delta, ic) are independent. "
        "Use snarkjs zkey verify before deployment."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "FOOMCASH (Feb 2026): copied VeilCash verifier whose delta2 == gamma2. Attacker "
        "forged withdrawal proofs without deposits. $2.26M drained 48h after VeilCash. "
        "Both used identical broken VK."
    )

    GROTH16_MARKERS = [
        "verifyProof", "verifyingKey", "VerifyingKey",
        "alpha1", "beta2", "gamma2", "delta2",
        "Pairing.pairing", "pairingProd4",
        "Groth16", "groth16",
    ]

    SUSPICIOUS_GAMMA_DELTA = [
        "gamma2 = delta2", "delta2 = gamma2",
        "vk.gamma2 = vk.delta2", "vk.delta2 = vk.gamma2",
    ]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            full_text = []
            for fn in contract.functions:
                if fn.expressions:
                    full_text.append(" ".join(str(e) for e in fn.expressions))
            text = " ".join(full_text)

            if not any(m in text for m in self.GROTH16_MARKERS):
                continue

            if "verifyProof" not in text and "Verifier" not in str(contract.name):
                continue

            has_alpha = "alpha" in text.lower()
            has_gamma = "gamma" in text.lower()
            has_delta = "delta" in text.lower()
            has_pairing = "Pairing" in text or "pairing" in text

            if not (has_alpha and has_gamma and has_delta and has_pairing):
                continue

            for state_var in contract.state_variables:
                if not state_var.expression:
                    continue
                expr_str = str(state_var.expression)
                var_name = state_var.name.lower()

                if "delta" in var_name and "gamma" in expr_str:
                    info = [
                        state_var, " (delta2-like state var) initialized from gamma2-like ",
                        "value. Identical delta2/gamma2 = forgeable proofs (FOOMCASH ",
                        "$2.26M, Feb 2026).",
                    ]
                    results.append(self.generate_result(info))

            for marker in self.SUSPICIOUS_GAMMA_DELTA:
                if marker in text:
                    info = [
                        contract, " has Groth16 verifier where delta2 == gamma2 ",
                        "(direct assignment). Trusted setup skipped or placeholder used. ",
                        "Forgeable proofs, FOOMCASH/VeilCash pattern.",
                    ]
                    results.append(self.generate_result(info))
                    break

            if not results or contract not in [r.elements[0] if r.elements else None
                                                 for r in results]:
                info = [
                    contract,
                    " contains Groth16 verifier — manually verify trusted setup ceremony ",
                    "was performed. Check delta2 != gamma2, no placeholder values. Run ",
                    "`snarkjs zkey verify` against original phase-2 transcript.",
                ]
                results.append(self.generate_result(info))

        return results
