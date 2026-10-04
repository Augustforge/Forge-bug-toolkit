"""
Custom Slither detector: asymmetric modifier on sibling functions.

DeXe pattern: 3 sibling functions (withdraw/stake/delegate Tokens), 2 have
`ifNotStaken` modifier, 1 doesn't. Missing one = bug.

Sibling detection: functions with similar names (common prefix/suffix) AND
similar param signature. Asymmetry: a modifier present in 2+ siblings but
absent in 1 or more.

Note: this is the static-analysis counterpart of
scripts/web3/hypothesis/asymmetry_scanner.py — Slither plugin form for
batched scans within the main /hunt pipeline.
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


def _common_suffix(a: str, b: str) -> int:
    i = 0
    while i < len(a) and i < len(b) and a[-1 - i].lower() == b[-1 - i].lower():
        i += 1
    return i


def _common_prefix(a: str, b: str) -> int:
    i = 0
    while i < len(a) and i < len(b) and a[i].lower() == b[i].lower():
        i += 1
    return i


def _is_sibling(name_a: str, name_b: str) -> bool:
    if name_a == name_b:
        return False
    if name_a.startswith("_") != name_b.startswith("_"):
        # _internal vs external — possibly sibling but skip
        return False
    cs = _common_suffix(name_a, name_b)
    cp = _common_prefix(name_a, name_b)
    if cs >= 4 and cs >= min(len(name_a), len(name_b)) * 0.4:
        return True
    if cp >= 4 and cp >= min(len(name_a), len(name_b)) * 0.4:
        return True
    return False


# Security-flavoured modifier names
SECURITY_KEYWORDS = (
    "if", "only", "when", "require", "ensure",
    "nonreentrant", "whennotpaused", "whenpaused",
    "check", "verify", "valid", "protect", "guard",
    "locked", "unlocked", "notstaked", "notstaken",
    "hasrole",
)


def _is_security_flavoured(name: str) -> bool:
    nlow = name.lower()
    return any(nlow.startswith(kw) for kw in SECURITY_KEYWORDS) or any(kw in nlow for kw in ("role", "auth"))


class AsymmetricModifier(AbstractDetector):
    ARGUMENT = "asymmetric-modifier"
    HELP = "Sibling functions where some have a security modifier and others don't"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://github.com/dexe-network/DeXe-Protocol/pull/missing-ifnotstaken"
    WIKI_TITLE = "Asymmetric modifier on sibling functions"
    WIKI_DESCRIPTION = (
        "Sibling functions (similar names + similar signatures) where a security-flavoured "
        "modifier is present in some but missing from another. Indicates likely forgotten check."
    )
    WIKI_RECOMMENDATION = "Audit the function lacking the modifier. If it mutates same state, add the modifier."
    WIKI_EXPLOIT_SCENARIO = (
        "DeXe Protocol: `withdrawTokens` and `stakeTokens` had `ifNotStaken` modifier preventing "
        "double-use of staked tokens. `delegateTokens` lacked it — same tokens earned staking rewards "
        "AND granted voting power via delegation."
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            # Collect external/public functions only
            funcs = [
                f for f in contract.functions
                if f.is_implemented and f.visibility in ("public", "external")
                and not f.is_constructor and not f.is_fallback
            ]
            for i, fn_a in enumerate(funcs):
                for fn_b in funcs[i + 1:]:
                    if not _is_sibling(fn_a.name, fn_b.name):
                        continue
                    mods_a = {m.name for m in fn_a.modifiers}
                    mods_b = {m.name for m in fn_b.modifiers}
                    only_in_a = mods_a - mods_b
                    only_in_b = mods_b - mods_a
                    for mod_name in only_in_a:
                        if not _is_security_flavoured(mod_name):
                            continue
                        info = [
                            f"Asymmetric modifier `{mod_name}`: present in `",
                            fn_a,
                            "` but missing from `",
                            fn_b,
                            f"` (sibling). Check if `{fn_b.name}` should also enforce this guard.\n",
                        ]
                        results.append(self.generate_result(info))
                    for mod_name in only_in_b:
                        if not _is_security_flavoured(mod_name):
                            continue
                        info = [
                            f"Asymmetric modifier `{mod_name}`: present in `",
                            fn_b,
                            "` but missing from `",
                            fn_a,
                            f"` (sibling). Check if `{fn_a.name}` should also enforce this guard.\n",
                        ]
                        results.append(self.generate_result(info))
        return results
