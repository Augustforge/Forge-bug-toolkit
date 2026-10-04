"""
Custom Slither detector: unprotected role/allowlist granting.

Pattern from real exploit:
- TrustedVolumes / 1inch resolver (May 2026, $5.87M) — public function
  `addAllowedOrderSigner(address)` had no access control. Attacker called it
  to add himself as a trusted signer, then used pre-existing token approvals
  to drain user funds.

Triggers when:
- Function is public/external
- Function writes `true` (or non-zero) into a mapping keyed by an address
- That mapping name suggests privilege (allowed, signer, whitelist, trusted,
  operator, authorized, role, admin, keeper, resolver)
- No require(msg.sender == owner/admin) / onlyOwner / onlyRole modifier
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


PRIVILEGE_PATTERNS = [
    "allowed", "signer", "whitelist", "trusted", "operator",
    "authorized", "role", "admin", "keeper", "resolver",
    "approved", "permitted", "granted",
]

OWNER_PATTERNS = [
    "onlyOwner", "onlyAdmin", "onlyRole", "onlyOperator",
    "onlyGovernance", "onlyDAO", "onlyManager", "onlyKeeper",
    "requiresAuth", "requireAuth", "onlyAuthorized", "restricted",
    "onlyStrategist", "onlyMultisig", "onlyGuardian",
    "require(msg.sender", "require(_msgSender",
]


class UnprotectedRoleGranting(AbstractDetector):
    ARGUMENT = "unprotected-role-granting"
    HELP = "Public function grants privileged role without access control (TrustedVolumes pattern)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://swcregistry.io/docs/SWC-106"
    WIKI_TITLE = "Unprotected role/allowlist granting"
    WIKI_DESCRIPTION = (
        "A public or external function writes to a privileged mapping "
        "(allowed, signer, whitelist, trusted, operator, etc.) without "
        "requiring msg.sender == owner or an access control modifier. "
        "Anyone can grant themselves elevated privileges."
    )
    WIKI_RECOMMENDATION = (
        "Add onlyOwner / onlyRole modifier or require(msg.sender == owner) "
        "to every function that grants privileged roles or modifies allowlists."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Contract stores isAllowedSigner[addr] mapping. Function addSigner(address) "
        "is public with no access control. Attacker calls addSigner(attacker). "
        "Contract now trusts attacker's signatures. Attacker submits signed orders "
        "and drains all token approvals users have given to the contract. "
        "Real case: TrustedVolumes/1inch resolver, May 2026, $5.87M."
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if fn.visibility not in ("public", "external"):
                    continue
                if fn.is_constructor or fn.is_fallback or fn.is_receive:
                    continue

                fn_str = str(fn)

                # Check if function writes to a privilege-related mapping
                writes_privilege_mapping = False
                for sv in fn.state_variables_written:
                    sv_name = (sv.name or "").lower()
                    if any(p in sv_name for p in PRIVILEGE_PATTERNS):
                        writes_privilege_mapping = True
                        break

                if not writes_privilege_mapping:
                    continue

                # Check if there is any access control
                has_access_control = any(p in fn_str for p in OWNER_PATTERNS)
                if fn.modifiers:
                    mod_names = " ".join(m.name for m in fn.modifiers if m.name)
                    has_access_control = has_access_control or any(
                        p.lower() in mod_names.lower() for p in OWNER_PATTERNS
                    )

                if has_access_control:
                    continue

                info = [
                    fn,
                    " grants a privileged role (writes to '",
                    ", ".join(
                        sv.name for sv in fn.state_variables_written
                        if any(p in (sv.name or "").lower() for p in PRIVILEGE_PATTERNS)
                    ),
                    "') without access control. "
                    "Anyone can call this and grant themselves elevated privileges. "
                    "Pattern: TrustedVolumes/1inch May 2026 ($5.87M).",
                ]
                results.append(self.generate_result(info))

        return results
