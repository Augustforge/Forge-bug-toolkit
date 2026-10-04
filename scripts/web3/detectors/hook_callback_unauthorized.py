"""
Custom Slither detector: hook/callback functions without caller validation.

Pattern from real exploits:
- Ekubo Protocol (May 2026, $1.4M) — payment callback allowed anyone to call
  transferFrom on behalf of a user that had an allowance.
- Cork Protocol (May 2025, $11M) — Uniswap v4 hook without onlyPoolManager;
  attacker called the hook directly and manipulated state.

Triggers when:
- Function name contains callback/locked/hook/lock signatures
- External / public visibility
- Contains transferFrom/safeTransferFrom/transfer
- No require(msg.sender == ...) / onlyXxx modifier at the start
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class HookCallbackUnauthorized(AbstractDetector):
    ARGUMENT = "hook-callback-unauthorized"
    HELP = "Hook/callback function without caller validation (Ekubo/Cork pattern)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://swcregistry.io/docs/SWC-105"
    WIKI_TITLE = "Unprotected hook/callback function"
    WIKI_DESCRIPTION = (
        "External callback/hook is callable by anyone — attacker invokes directly, "
        "drains funds via transferFrom against pre-existing allowances."
    )
    WIKI_RECOMMENDATION = (
        "Add require(msg.sender == trustedCaller) or onlyPoolManager/onlyCore modifier. "
        "Verify lock-context: only execute when called from authorized lock-initiator flow."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Ekubo (May 2026): attacker called payment callback directly with victim address "
        "as payer. Contract executed transferFrom(victim, attacker, amount) since victim "
        "had allowance to the contract. $1.4M drained."
    )

    CALLBACK_NAME_PATTERNS = [
        "callback", "Callback",
        "locked", "Locked",
        "lockacquired", "lockAcquired", "LockAcquired",
        "unlockcallback", "unlockCallback",
        "beforeswap", "beforeSwap", "afterswap", "afterSwap",
        "beforemodify", "beforeModify", "aftermodify", "afterModify",
        "beforeinit", "beforeInit", "afterinit", "afterInit",
        "beforeadd", "beforeAdd", "afteradd", "afterAdd",
        "beforeremove", "beforeRemove", "afterremove", "afterRemove",
        "hook", "Hook",
        "paymentCallback", "payment_callback",
        "flashloan", "flashLoan", "executeOperation",
        "ondonate", "onDonate",
        "onerc721received", "onERC721Received",
        "onerc1155received", "onERC1155Received",
    ]

    TRANSFER_PATTERNS = [
        "transferFrom", "safeTransferFrom",
        "_transferFrom", "_safeTransferFrom",
        ".transfer(", ".send(",
        "settle", "take", "_settle", "_take",
        "mint", "burn",
    ]

    AUTH_PATTERNS = [
        "msg.sender ==",
        "msg.sender !=",
        "_msgSender() ==",
        "onlyOwner",
        "onlyAdmin",
        "onlyRole",
        "onlyPoolManager",
        "onlyCore",
        "onlyManager",
        "onlyVault",
        "onlyAuthorized",
        "onlyHook",
        "onlySelf",
        "_checkOwner",
        "_checkRole",
        "AccessControl",
        "isAuthorized",
        "isTrusted",
        "require(authorized",
        "require(trusted",
    ]

    def _is_callback_name(self, fn_name: str) -> bool:
        return any(p.lower() in fn_name.lower() for p in self.CALLBACK_NAME_PATTERNS)

    def _has_transfer(self, fn_str: str) -> bool:
        return any(p in fn_str for p in self.TRANSFER_PATTERNS)

    def _has_auth_check(self, fn, fn_str: str) -> bool:
        if fn.modifiers:
            for mod in fn.modifiers:
                mod_name = str(mod.name) if hasattr(mod, "name") else str(mod)
                if any(a.lower() in mod_name.lower() for a in self.AUTH_PATTERNS):
                    return True
        return any(p in fn_str for p in self.AUTH_PATTERNS)

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.expressions:
                    continue
                if fn.visibility not in ("external", "public"):
                    continue
                if fn.is_constructor or fn.view or fn.pure:
                    continue

                fn_name = fn.name or ""
                if not self._is_callback_name(fn_name):
                    continue

                fn_str = " ".join(str(e) for e in fn.expressions)

                if not self._has_transfer(fn_str):
                    continue

                if self._has_auth_check(fn, fn_str):
                    continue

                info = [
                    fn,
                    " is a callback/hook with token movement but no caller validation. ",
                    "Anyone can invoke it — same pattern as Ekubo ($1.4M, May 2026) and ",
                    "Cork Protocol ($11M, May 2025). Add onlyPoolManager/onlyCore or ",
                    "require(msg.sender == trustedCaller).",
                ]
                results.append(self.generate_result(info))
        return results
