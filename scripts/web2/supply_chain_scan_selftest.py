# -*- coding: utf-8 -*-
"""Selftest for supply_chain_scan.py (FDE Plan 7, TIER D §63).

Proves each of the 4 npm-specific detect classes REALLY fires (no stub), a clean manifest yields 0,
the producer writes a co-located toolkit-rooted artifact with a RESULT line, and the scan is fail-open
+ isolated (never touches real data / real sessions).

 (1) dependency-confusion: internal-scoped `@internal-corp/utils` resolving from PUBLIC npm is flagged;
     a known public scope (`@types/node`) is NOT.
 (2) typosquat: `expres` (edit-distance 1 from `express`) is flagged; exact `lodash` is NOT.
 (3) lockfile-injection: same `left-pad@1.3.0` carrying two DIFFERENT integrity hashes is flagged
     (integrity-mismatch); also a foreign/undeclared registry host is flagged, and an .npmrc-declared
     private registry is NOT.
 (4) unclaimed-package: dep declared in manifest but MISSING from lock, and a git/url source spec.
 (5) clean manifest+lock -> 0 findings (all classes).
 (6) yarn.lock path parses and drives the same detectors.
 (7) fail-open: broken JSON / missing files never raise; run_supply_chain_scan always writes artifact.
 (8) isolation: artifact written to EXACT {session_dir}/supply_chain.md, nothing under bare CWD sessions/.

Run: py -3 -X utf8 bug-bounty-toolkit/scripts/web2/supply_chain_scan_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import json
import shutil
import tempfile
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
WEB2_DIR = os.path.join(ROOT, "scripts", "web2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


sc = _load("supply_chain_scan", os.path.join(WEB2_DIR, "supply_chain_scan.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def by_class(findings):
    out = {}
    for f in findings:
        out.setdefault(f["cls"], []).append(f["package"])
    return out


# ─── Fixtures ────────────────────────────────────────────────────────────────────────────────
DIRTY_PJ = json.dumps({
    "name": "victim-app",
    "dependencies": {
        "@internal-corp/utils": "^1.0.0",   # internal scope, resolves from public npm -> DC
        "expres": "^4.18.0",                # typosquat of express (dist 1)
        "lodash": "^4.17.21",               # clean popular, exact -> NOT typosquat
        "@types/node": "^20.0.0",           # public scope -> NOT DC
        "left-pad": "^1.3.0",               # two integrity hashes in lock -> lockfile-injection
    },
})
DIRTY_LOCK = json.dumps({
    "name": "victim-app",
    "lockfileVersion": 3,
    "packages": {
        "": {"name": "victim-app"},
        "node_modules/@internal-corp/utils": {
            "version": "1.0.0",
            "resolved": "https://registry.npmjs.org/@internal-corp/utils/-/utils-1.0.0.tgz",
            "integrity": "sha512-AAA"},
        "node_modules/expres": {
            "version": "4.18.0",
            "resolved": "https://registry.npmjs.org/expres/-/expres-4.18.0.tgz",
            "integrity": "sha512-BBB"},
        "node_modules/lodash": {
            "version": "4.17.21",
            "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
            "integrity": "sha512-CCC"},
        "node_modules/@types/node": {
            "version": "20.0.0",
            "resolved": "https://registry.npmjs.org/@types/node/-/node-20.0.0.tgz",
            "integrity": "sha512-DDD"},
        "node_modules/left-pad": {
            "version": "1.3.0",
            "resolved": "https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz",
            "integrity": "sha512-XXX"},
        # hoisted duplicate at same version but DIFFERENT integrity -> tamper signal
        "node_modules/some-dep/node_modules/left-pad": {
            "version": "1.3.0",
            "resolved": "https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz",
            "integrity": "sha512-YYY"},
    },
})

CLEAN_PJ = json.dumps({
    "name": "clean-app",
    "dependencies": {
        "lodash": "^4.17.21",
        "react": "^18.2.0",
        "@types/node": "^20.0.0",
    },
})
CLEAN_LOCK = json.dumps({
    "name": "clean-app",
    "lockfileVersion": 3,
    "packages": {
        "": {"name": "clean-app"},
        "node_modules/lodash": {
            "version": "4.17.21",
            "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
            "integrity": "sha512-C1"},
        "node_modules/react": {
            "version": "18.2.0",
            "resolved": "https://registry.npmjs.org/react/-/react-18.2.0.tgz",
            "integrity": "sha512-R1"},
        "node_modules/@types/node": {
            "version": "20.0.0",
            "resolved": "https://registry.npmjs.org/@types/node/-/node-20.0.0.tgz",
            "integrity": "sha512-N1"},
    },
})


# ─── CASE 1-3+: dirty manifest, all core classes fire ────────────────────────────────────────
dirty = sc.scan(DIRTY_PJ, DIRTY_LOCK)
dc = by_class(dirty)

check("case1a dependency-confusion flags internal @internal-corp/utils (public-npm resolve)",
      "@internal-corp/utils" in dc.get("dependency-confusion", []), "got=%r" % (dc,))
check("case1b dependency-confusion does NOT flag public scope @types/node",
      "@types/node" not in dc.get("dependency-confusion", []), "got=%r" % (dc,))

check("case2a typosquat flags 'expres' (dist 1 from express)",
      "expres" in dc.get("typosquat", []), "got=%r" % (dc,))
check("case2b typosquat does NOT flag exact popular 'lodash'",
      "lodash" not in dc.get("typosquat", []), "got=%r" % (dc,))

check("case3a lockfile-injection flags 'left-pad' (integrity mismatch, same name@version)",
      "left-pad" in dc.get("lockfile-injection", []), "got=%r" % (dc,))
_lp = [f for f in dirty if f["cls"] == "lockfile-injection" and f["package"] == "left-pad"]
check("case3b left-pad lockfile-injection detail names integrity mismatch",
      any("integrity mismatch" in f["detail"] for f in _lp), "got=%r" % (_lp,))


# ─── CASE 3c/3d: foreign registry host + .npmrc-declared private registry ─────────────────────
FOREIGN_LOCK = {
    "evil-pkg": [{"name": "evil-pkg", "version": "1.0.0",
                  "resolved": "https://evil.registry.example/evil-pkg/-/evil-pkg-1.0.0.tgz",
                  "integrity": "sha512-Z"}],
    "corp-lib": [{"name": "corp-lib", "version": "2.0.0",
                  "resolved": "https://npm.corp.internal/corp-lib/-/corp-lib-2.0.0.tgz",
                  "integrity": "sha512-Q"}],
}
foreign = sc.detect_lockfile_injection(FOREIGN_LOCK, allowed_registries=set())
fc = by_class(foreign)
check("case3c lockfile-injection flags foreign host evil.registry.example",
      "evil-pkg" in fc.get("lockfile-injection", []), "got=%r" % (fc,))
check("case3c (no npmrc) also flags the internal host as undeclared",
      "corp-lib" in fc.get("lockfile-injection", []), "got=%r" % (fc,))
# with npm.corp.internal declared allowed, corp-lib is NOT flagged (evil still is)
foreign2 = sc.detect_lockfile_injection(FOREIGN_LOCK, allowed_registries={"npm.corp.internal"})
fc2 = by_class(foreign2)
check("case3d .npmrc-declared private registry NOT flagged as foreign",
      "corp-lib" not in fc2.get("lockfile-injection", []) and
      "evil-pkg" in fc2.get("lockfile-injection", []), "got=%r" % (fc2,))


# ─── CASE 4: unclaimed-package (missing-from-lock + non-registry source) ──────────────────────
UNCLAIMED_PJ = json.dumps({
    "name": "u-app",
    "dependencies": {
        "ghost-pkg": "^1.0.0",                       # declared, absent from lock -> unclaimed
        "from-git": "git+https://github.com/x/y.git",  # non-registry source
        "lodash": "^4.17.21",                        # present in lock -> not unclaimed
    },
})
UNCLAIMED_LOCK = json.dumps({
    "name": "u-app", "lockfileVersion": 3,
    "packages": {
        "": {"name": "u-app"},
        "node_modules/lodash": {"version": "4.17.21",
                                 "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
                                 "integrity": "sha512-L"},
    },
})
unclaimed = sc.scan(UNCLAIMED_PJ, UNCLAIMED_LOCK)
uc = by_class(unclaimed)
check("case4a unclaimed flags 'ghost-pkg' (declared, missing from lock)",
      "ghost-pkg" in uc.get("unclaimed-package", []), "got=%r" % (uc,))
check("case4b unclaimed flags 'from-git' (non-registry git source)",
      "from-git" in uc.get("unclaimed-package", []), "got=%r" % (uc,))
check("case4c unclaimed does NOT flag 'lodash' (present in lock w/ integrity)",
      "lodash" not in uc.get("unclaimed-package", []), "got=%r" % (uc,))
# without any lockfile, 'missing from lock' must stay SILENT (no lock context -> no spam)
nolockscan = sc.scan(UNCLAIMED_PJ, None)
un2 = by_class(nolockscan)
check("case4d unclaimed 'missing-from-lock' SILENT when no lockfile given (only git-source fires)",
      "ghost-pkg" not in un2.get("unclaimed-package", []) and
      "from-git" in un2.get("unclaimed-package", []), "got=%r" % (un2,))


# ─── CASE 5: clean manifest -> ZERO findings ─────────────────────────────────────────────────
clean = sc.scan(CLEAN_PJ, CLEAN_LOCK)
check("case5 clean manifest+lock -> 0 findings (all 4 classes silent)",
      clean == [], "got=%r" % (clean,))


# ─── CASE 6: yarn.lock drives the same detectors ─────────────────────────────────────────────
YARN_LOCK = (
    "# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.\n"
    "# yarn lockfile v1\n"
    "\n"
    '"@internal-corp/utils@^1.0.0":\n'
    '  version "1.0.0"\n'
    '  resolved "https://registry.yarnpkg.com/@internal-corp/utils/-/utils-1.0.0.tgz#abc"\n'
    "  integrity sha512-AAA\n"
    "\n"
    '"expres@^4.18.0":\n'
    '  version "4.18.0"\n'
    '  resolved "https://registry.yarnpkg.com/expres/-/expres-4.18.0.tgz#def"\n'
    "  integrity sha512-BBB\n"
    "\n"
    '"lodash@^4.17.21":\n'
    '  version "4.17.21"\n'
    '  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz#ghi"\n'
    "  integrity sha512-CCC\n"
)
YARN_PJ = json.dumps({"name": "y-app", "dependencies": {
    "@internal-corp/utils": "^1.0.0", "expres": "^4.18.0", "lodash": "^4.17.21"}})
yarn_idx = sc.parse_yarn_lock(YARN_LOCK)
check("case6a parse_yarn_lock indexes @internal-corp/utils + expres + lodash",
      all(k in yarn_idx for k in ("@internal-corp/utils", "expres", "lodash")),
      "got=%r" % (list(yarn_idx.keys()),))
yarn_scan = sc.scan(YARN_PJ, YARN_LOCK)
yc = by_class(yarn_scan)
check("case6b yarn path: dependency-confusion + typosquat both fire",
      "@internal-corp/utils" in yc.get("dependency-confusion", []) and
      "expres" in yc.get("typosquat", []), "got=%r" % (yc,))


# ─── CASE 7: fail-open (broken JSON / missing files never raise) ──────────────────────────────
try:
    broken = sc.scan("{ this is not json", "{ also broken", None)
    check("case7a scan() on broken JSON -> [] no raise", broken == [], "got=%r" % (broken,))
except Exception as e:
    check("case7a scan() on broken JSON -> [] no raise", False, "RAISED %r" % (e,))

try:
    empty = sc.scan(None, None, None)
    check("case7b scan(None,None) -> [] no raise", empty == [])
except Exception as e:
    check("case7b scan(None,None) -> [] no raise", False, "RAISED %r" % (e,))


# ─── CASE 8: producer writes co-located toolkit-rooted artifact; isolation ────────────────────
TMP_SESSION = os.path.join(ROOT, "sessions", "_selftest_tmp_web2_supply_chain")
TMP_TARGET = tempfile.mkdtemp(prefix="sc_target_")
try:
    if os.path.exists(TMP_SESSION):
        shutil.rmtree(TMP_SESSION)
    pj_path = os.path.join(TMP_TARGET, "package.json")
    lock_path = os.path.join(TMP_TARGET, "package-lock.json")
    open(pj_path, "w", encoding="utf-8").write(DIRTY_PJ)
    open(lock_path, "w", encoding="utf-8").write(DIRTY_LOCK)

    out = sc.run_supply_chain_scan(TMP_SESSION, package_json_path=pj_path, lock_path=lock_path)
    expected = os.path.join(TMP_SESSION, "supply_chain.md")
    check("case8a run returns exactly {session_dir}/supply_chain.md", out == expected,
          "got=%r expected=%r" % (out, expected))
    check("case8b artifact physically exists", os.path.isfile(expected))
    check("case8c nothing written under bare CWD-relative sessions/ (toolkit-rooted only)",
          not os.path.exists(os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_supply_chain")))
    content = open(expected, encoding="utf-8").read()
    check("case8d RESULT line present with per-class counts",
          "RESULT: supply-chain-scan" in content and "dc=" in content, "content=%r" % (content[:400],))
    check("case8e artifact lists dependency-confusion + typosquat + lockfile-injection rows",
          all(cls in content for cls in ("dependency-confusion", "typosquat", "lockfile-injection")))
    check("case8f artifact explicitly distinguishes itself from generic third-party-seam",
          "third-party-seam" in content, "npm-specific vs generic distinction must be in the artifact")

    # missing input files -> fail-open, artifact still written with 0 findings + RESULT
    out2 = sc.run_supply_chain_scan(TMP_SESSION, package_json_path=os.path.join(TMP_TARGET, "nope.json"))
    c2 = open(out2, encoding="utf-8").read()
    check("case8g missing manifest -> artifact still written, RESULT 0 findings (fail-open)",
          "RESULT: supply-chain-scan, 0 findings" in c2, "content=%r" % (c2[:300],))
finally:
    shutil.rmtree(TMP_SESSION, ignore_errors=True)
    shutil.rmtree(TMP_TARGET, ignore_errors=True)
    stray = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_supply_chain")
    if os.path.exists(stray):
        shutil.rmtree(stray, ignore_errors=True)


print("=== SUPPLY_CHAIN_SCAN SELFTEST (FDE Plan 7, TIER D §63) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
