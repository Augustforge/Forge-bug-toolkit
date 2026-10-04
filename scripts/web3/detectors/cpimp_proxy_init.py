"""
Custom Slither detector: proxy deploy without atomic initialization (CPIMP risk).

Pattern from USPD hack (December 2025, $1M):
- Clandestine Proxy-In-the-Middle of Proxy
- Attacker frontrun init via Multicall3, inject malicious proxy layer
- Waited 78 days silently, then minted 98M USPD
- Concealment: Etherscan showed original contract, but proxy pointed to backdoor

Triggers when:
- Contract uses Initializable / __Init pattern (UUPS / Transparent / Beacon)
- Has external initialize() function
- Lacks initialization_check / immediate-init pattern
- OR has unprotected initialize() callable by anyone

Also flags contracts whose initialize() lacks onlyOwner / require(deployer).
"""

from slither.detectors.abstract_detector import AbstractDetector, DetectorClassification


class CpimpProxyInit(AbstractDetector):
    ARGUMENT = "cpimp-proxy-init"
    HELP = "Proxy with non-atomic init or unprotected initialize (CPIMP attack)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://www.halborn.com/blog/post/what-is-a-cpimp-attack-in-defi-smart-contracts"
    WIKI_TITLE = "Vulnerable proxy initialization (CPIMP)"
    WIKI_DESCRIPTION = (
        "Initializable proxy whose initialize() is not protected (deployer-only check) "
        "or not called atomically with deploy. Attacker frontrun init via Multicall3 "
        "and injects a clandestine proxy-in-the-middle layer."
    )
    WIKI_RECOMMENDATION = (
        "Use deployment that calls initialize() in same transaction (factory pattern, "
        "create2 with init data) OR add `require(msg.sender == deployer)` in initialize. "
        "Use `disableInitializers()` in constructor of implementation."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "USPD (Dec 2025): proxy deployed without atomic init. Attacker via Multicall3 inserted "
        "a malicious wrapper proxy between the legitimate proxy and the implementation. 78 days silent, "
        "then minted 98M USPD. $1M drained."
    )

    INIT_PATTERNS = ["initialize", "__Init", "__init"]
    PROXY_INHERITANCE = [
        "Initializable", "ERC1967Proxy", "TransparentUpgradeableProxy",
        "BeaconProxy", "UUPSUpgradeable", "Proxy",
    ]
    INIT_GUARDS = [
        "initializer", "onlyInitializing", "reinitializer",
        "msg.sender == deployer", "msg.sender == owner",
        "require(_initialized", "_disableInitializers",
    ]

    def _has_proxy_inheritance(self, contract) -> bool:
        for inh in contract.inheritance:
            inh_name = str(inh.name) if hasattr(inh, "name") else str(inh)
            if any(p in inh_name for p in self.PROXY_INHERITANCE):
                return True
        return False

    def _is_init_function(self, fn_name: str) -> bool:
        return any(p in fn_name for p in self.INIT_PATTERNS)

    def _has_init_guard(self, fn, fn_str: str) -> bool:
        if fn.modifiers:
            for mod in fn.modifiers:
                mod_name = str(mod.name) if hasattr(mod, "name") else str(mod)
                if any(g in mod_name for g in self.INIT_GUARDS):
                    return True
        return any(g in fn_str for g in self.INIT_GUARDS)

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            if not self._has_proxy_inheritance(contract):
                continue

            init_fns = []
            has_disable_in_constructor = False

            for fn in contract.functions:
                if fn.is_constructor and fn.expressions:
                    cstr = " ".join(str(e) for e in fn.expressions)
                    if "_disableInitializers" in cstr:
                        has_disable_in_constructor = True

                if not fn.name or not self._is_init_function(fn.name):
                    continue
                if fn.visibility not in ("external", "public"):
                    continue
                init_fns.append(fn)

            if not init_fns:
                continue

            if not has_disable_in_constructor:
                info = [
                    contract,
                    " is upgradeable but constructor does not call _disableInitializers(). ",
                    "Implementation contract can be initialized by anyone via direct call. ",
                    "Add `_disableInitializers()` in constructor (USPD/CPIMP pattern).",
                ]
                results.append(self.generate_result(info))

            for fn in init_fns:
                fn_str = " ".join(str(e) for e in fn.expressions)
                if not self._has_init_guard(fn, fn_str):
                    info = [
                        fn, " is initialize-style function without guard (initializer modifier ",
                        "or deployer check). Frontrunnable via Multicall3 (CPIMP, USPD $1M).",
                    ]
                    results.append(self.generate_result(info))

        return results
