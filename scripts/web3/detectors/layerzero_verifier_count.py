"""
Custom Slither detector: LayerZero v2 config with requiredDVNCount < 2.

Pattern from KelpDAO hack (April 2026, $292M):
- 1-of-1 verifier setup, single RPC dependency
- Attacker DDoS'd the legitimate RPC and injected a fraudulent message
- 116,500 rsETH stolen, $13B TVL exodus

Triggers when:
- Contract calls setConfig / setSendLibrary / setReceiveLibrary
- UlnConfig struct literal with requiredDVNCount hardcoded to 0 or 1
- Or a requiredDVNs array literal contains < 2 elements

NB: for an onchain audit (when the config is set by an EOA transaction, not in code)
use scripts/web3/layerzero_dvn_audit.py — this detector catches only code.
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class LayerzeroVerifierCount(AbstractDetector):
    ARGUMENT = "layerzero-verifier-count"
    HELP = "LayerZero v2 config with requiredDVNCount < 2 (KelpDAO pattern)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://docs.layerzero.network/v2/developers/evm/configuration/dvn-required"
    WIKI_TITLE = "Insufficient LayerZero DVN diversity"
    WIKI_DESCRIPTION = (
        "LayerZero v2 ULN config with requiredDVNCount < 2 means single point of failure. "
        "Compromised/DDoS'd verifier permits fraudulent cross-chain message injection."
    )
    WIKI_RECOMMENDATION = (
        "Configure at least 2 required DVNs (e.g. LayerZero Labs + independent DVN like "
        "Polyhedra/Nethermind/Google Cloud). Add optional DVNs with threshold ≥ 1."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "KelpDAO (April 2026): 1-of-1 verifier, Lazarus compromised the single DVN's "
        "infrastructure → injected fraudulent rsETH mint message on destination chain. "
        "$292M drained, $13B TVL exodus."
    )

    LZ_CONFIG_FUNCTIONS = [
        "setConfig", "setSendLibrary", "setReceiveLibrary",
        "setUlnConfig", "_setConfig",
    ]

    DVN_FIELDS = [
        "requiredDVNCount", "requiredDVNs",
        "optionalDVNCount", "optionalDVNs",
    ]

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.expressions:
                    continue

                fn_str = " ".join(str(e) for e in fn.expressions)

                calls_lz_config = any(c in fn_str for c in self.LZ_CONFIG_FUNCTIONS)
                touches_dvn = any(d in fn_str for d in self.DVN_FIELDS)

                if not (calls_lz_config or touches_dvn):
                    continue

                suspicious = False
                if "requiredDVNCount" in fn_str:
                    for marker in ["requiredDVNCount: 0", "requiredDVNCount: 1",
                                   "requiredDVNCount=0", "requiredDVNCount=1",
                                   "requiredDVNCount,0", "requiredDVNCount,1"]:
                        if marker.replace(" ", "") in fn_str.replace(" ", ""):
                            suspicious = True
                            break

                if calls_lz_config and not touches_dvn:
                    suspicious = True

                if not suspicious:
                    continue

                info = [
                    fn,
                    " configures LayerZero with weak DVN setup (requiredDVNCount < 2 ",
                    "or no explicit DVN config — defaults are unsafe). KelpDAO ($292M, ",
                    "April 2026) was drained through this exact pattern. Use ≥2 ",
                    "independent DVNs.",
                ]
                results.append(self.generate_result(info))
        return results
