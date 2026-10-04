"""
Custom Slither detector: ERC-3525 in a vault without reentrancy guard.

Pattern from Solv Protocol (March 2026, $2.7M):
- ERC-3525 token = also an ERC-721 (semi-fungible)
- doSafeTransferIn → mint → onERC721Received callback → re-enter mint before completion
- 22 reentrancy iterations: 135 BRO → 567M BRO

Triggers when:
- Contract integrates ERC-3525 (slot/value transfers)
- vault/mint function contains safeTransfer / doSafeTransferIn
- Mint state update AFTER external call (not CEI)
- No nonReentrant modifier
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class Erc3525Reentrancy(AbstractDetector):
    ARGUMENT = "erc3525-reentrancy"
    HELP = "ERC-3525 integration without reentrancy guard (Solv pattern)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://www.halborn.com/blog/post/explained-the-solv-hack-march-2026"
    WIKI_TITLE = "ERC-3525 vault double-mint via reentrancy"
    WIKI_DESCRIPTION = (
        "ERC-3525 tokens implement ERC-721 receiver hooks. doSafeTransferIn triggers "
        "onERC721Received callback that can re-enter mint/deposit before state update, "
        "leading to double-mint."
    )
    WIKI_RECOMMENDATION = (
        "Apply CEI pattern: update state before any external call. Add ReentrancyGuard "
        "(nonReentrant modifier) to all functions doing safeTransferFrom on ERC-3525."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Solv (March 2026): doSafeTransferIn → mint → onERC721Received in attacker "
        "contract → re-enter mint. 22 iterations. 135 BRO → 567M BRO. $2.7M drained."
    )

    ERC3525_MARKERS = [
        "IERC3525", "ERC3525", "erc3525",
        "transferFromValue", "transferValue",
        "doSafeTransferIn", "doSafeTransferOut",
        "_mintValue", "mintValue",
        "slot()", "valueOf",
        "onERC3525Received",
    ]

    EXTERNAL_CALL_PATTERNS = [
        "safeTransferFrom", "safeTransfer",
        "doSafeTransferIn", "doSafeTransferOut",
        "onERC721Received", "onERC1155Received",
        ".call(", ".transfer(", ".send(",
    ]

    GUARD_PATTERNS = [
        "nonReentrant", "ReentrancyGuard",
        "_reentrancyGuard", "_status == _NOT_ENTERED",
        "lock()", "_locked",
    ]

    def _is_erc3525_context(self, contract) -> bool:
        all_text = []
        for inh in contract.inheritance:
            all_text.append(str(inh.name) if hasattr(inh, "name") else str(inh))
        for fn in contract.functions:
            if fn.expressions:
                all_text.append(" ".join(str(e) for e in fn.expressions))
            all_text.append(fn.name or "")
        text = " ".join(all_text)
        return any(m in text for m in self.ERC3525_MARKERS)

    def _has_guard(self, fn, fn_str: str) -> bool:
        if fn.modifiers:
            for mod in fn.modifiers:
                mod_name = str(mod.name) if hasattr(mod, "name") else str(mod)
                if any(g in mod_name for g in self.GUARD_PATTERNS):
                    return True
        return any(g in fn_str for g in self.GUARD_PATTERNS)

    def _has_external_call(self, fn_str: str) -> bool:
        return any(p in fn_str for p in self.EXTERNAL_CALL_PATTERNS)

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            if not self._is_erc3525_context(contract):
                continue

            for fn in contract.functions:
                if not fn.expressions:
                    continue
                if fn.visibility not in ("external", "public"):
                    continue
                if fn.is_constructor or fn.view or fn.pure:
                    continue

                fn_str = " ".join(str(e) for e in fn.expressions)

                if not self._has_external_call(fn_str):
                    continue

                does_state_change = any(s in fn_str for s in
                                          ["mint", "deposit", "balance", "totalSupply",
                                           "+ =", "-=", "+=", "= "])
                if not does_state_change:
                    continue

                if self._has_guard(fn, fn_str):
                    continue

                info = [
                    fn, " interacts with ERC-3525 token, makes external call, modifies ",
                    "state, but lacks nonReentrant guard. Solv ($2.7M, Mar 2026) drained ",
                    "via this exact pattern (22-iteration reentrancy through onERC721Received).",
                ]
                results.append(self.generate_result(info))

        return results
