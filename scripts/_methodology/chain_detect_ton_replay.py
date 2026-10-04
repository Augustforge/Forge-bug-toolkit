# -*- coding: utf-8 -*-
"""chain_detect TON-hookup replay. Proves: (a) ton: prefix -> chain ton; (b) FunC/Tact/Tolk
contract repo -> chain ton subchain contract (+ton_note, NOT a node-tool); (c) C++ node repo with >=2
marker dirs -> chain ton subchain node (+ton_tool scan.sh); (d) does NOT match on 1 marker / arbitrary
C++ / pure web2; (e) Move is not broken (regression); (f) contract files take priority over package.json.
proof-of-firing: before the hookup all of this returned unknown/web2 (see the revert-check in the report)."""
import os, sys, json, tempfile, shutil, importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT: break
    ROOT = nxt
MODPATH = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "chain_detect.py")

spec = importlib.util.spec_from_file_location("chain_detect", MODPATH)
cd = importlib.util.module_from_spec(spec); spec.loader.exec_module(cd)

results = []
def check(n, c, d=""):
    results.append((n, bool(c), d))

def mkrepo():
    return tempfile.mkdtemp(prefix="cdton_")

def touch(root, rel):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("x")

tmpdirs = []
try:
    # (a) ton: prefix
    r = cd.detect("ton:EQxxxxAddress")
    check("a ton: prefix -> chain ton", r.get("chain") == "ton", repr(r))
    r2 = cd.detect("toncoin:EQ123")
    check("a toncoin: prefix -> chain ton", r2.get("chain") == "ton", repr(r2))

    # (b) FunC contract repo
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "contracts/jetton-minter.fc")
    touch(d, "package.json")  # blueprint frontend — must not override
    r = cd.detect(d)
    check("b .fc contract -> chain ton", r.get("chain") == "ton", repr(r))
    check("b .fc -> subchain contract", r.get("subchain") == "contract", repr(r.get("subchain")))
    check("b .fc -> framework func", r.get("framework") == "func")
    check("b .fc -> has ton_note, NO ton_tool (no node engine for contracts)",
          ("ton_note" in r) and ("ton_tool" not in r), repr(list(r.keys())))
    check("f contract takes priority over package.json (not web2)", r.get("chain") == "ton")

    # (b2) Tact
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "src/wallet.tact")
    r = cd.detect(d)
    check("b2 .tact -> chain ton framework tact", r.get("chain") == "ton" and r.get("framework") == "tact", repr(r))

    # (b3) Tolk
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "storage.tolk")
    r = cd.detect(d)
    check("b3 .tolk -> chain ton framework tolk", r.get("chain") == "ton" and r.get("framework") == "tolk", repr(r))

    # (c) C++ node core — >=2 marker dirs
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "validator/manager.cpp")
    touch(d, "catchain/catchain.cpp")
    touch(d, "CMakeLists.txt")
    r = cd.detect(d)
    check("c node core (validator+catchain) -> chain ton subchain node",
          r.get("chain") == "ton" and r.get("subchain") == "node", repr(r))
    check("c node -> ton_tool = scan.sh", r.get("ton_tool", "").endswith("scan.sh"), repr(r.get("ton_tool")))
    check("c node -> framework cpp", r.get("framework") == "cpp")

    # (d1) one marker dir -> NOT ton node (falls through the chain)
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "validator/x.cpp")   # only 1 marker
    touch(d, "package.json")
    r = cd.detect(d)
    check("d1 one node marker -> NOT ton (need >=2)", r.get("chain") != "ton", repr(r))

    # (d2) arbitrary C++ without markers -> NOT ton
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "src/main.cpp")
    touch(d, "lib/util.cpp")
    r = cd.detect(d)
    check("d2 arbitrary C++ -> NOT ton", r.get("chain") != "ton", repr(r))

    # (d3) pure web2 -> web2, not ton
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "package.json")
    r = cd.detect(d)
    check("d3 pure package.json -> web2", r.get("chain") == "web2", repr(r))

    # (e) Move regression — not broken
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "sources/pool.move")
    touch(d, "Move.toml")
    with open(os.path.join(d, "Move.toml"), "w", encoding="utf-8") as f:
        f.write("[package]\nname='x'\n[dependencies]\nSui = { git='https://github.com/MystenLabs/sui' }\n")
    r = cd.detect(d)
    check("e Move/Sui regression -> chain move subchain sui", r.get("chain") == "move" and r.get("subchain") == "sui", repr(r))

    # (e2) EVM regression
    d = mkrepo(); tmpdirs.append(d)
    touch(d, "src/Vault.sol")
    r = cd.detect(d)
    check("e2 .sol regression -> chain evm", r.get("chain") == "evm", repr(r))

    # (g) Stacks/Clarity — prefix + repo (.clar / Clarinet.toml)
    r = cd.detect("stacks:SP123")
    check("g stacks: prefix -> chain stacks framework clarity",
          r.get("chain") == "stacks" and r.get("framework") == "clarity", repr(r))
    r = cd.detect("clarity:SP123")
    check("g clarity: prefix -> chain stacks", r.get("chain") == "stacks", repr(r))

    d = mkrepo(); tmpdirs.append(d)
    touch(d, "contracts/pool.clar")
    touch(d, "package.json")  # Stacks dApp frontend — must not override
    r = cd.detect(d)
    check("g .clar -> chain stacks subchain contract (not web2)",
          r.get("chain") == "stacks" and r.get("subchain") == "contract", repr(r))
    check("g .clar -> clarity_note present", "clarity_note" in r, repr(list(r.keys())))

    d = mkrepo(); tmpdirs.append(d)
    touch(d, "Clarinet.toml")
    r = cd.detect(d)
    check("g Clarinet.toml -> chain stacks", r.get("chain") == "stacks", repr(r))

finally:
    for d in tmpdirs:
        shutil.rmtree(d, ignore_errors=True)

print("=== CHAIN_DETECT TON HOOKUP REPLAY ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
