# -*- coding: utf-8 -*-
"""Selftest for wave_delta.py web/API/bundle extension (FDE Plan 7, Part XI §61, Task 6).

No prior selftest for wave_delta.py existed in the repo (grep-confirmed before writing this) —
this file covers BOTH the new JS/TS fingerprint branch AND a regression check on the existing
.sol/.rs branches + legacy_alive_check (Plan 6 §52), per the task-6 brief's Test section.

Proves:
 (1) Extension whitelist now reaches .js/.ts/.jsx/.tsx end-to-end via fingerprint() (not just
     structurally) -- before this task these extensions were skipped before the dispatcher ever
     ran (review #1-L1: unreachable branch without the whitelist edit).
 (2) JS_FUNC extracts EVERY required form (review #6 -- not a trivial copy of RUST_FN):
     arrow fn assigned to const (plain + async), object method, class method (plain + async),
     export function / export async function / export default function, TS generic function
     declaration (`function foo<T>(...)`,  TS generic arrow with trailing-comma disambiguation
     (`const f = <T,>(...) =>`).
 (3) JS_FUNC does NOT produce spurious entries on: line comments, block comments, a string
     literal containing a literal `=>`, a non-function statement (object literal / TS type
     alias), and JS control-flow keywords that syntactically shadow the method-shorthand form
     (`if (x) {`, `for (...) {`, `while (x) {`) -- including the substring trap where excluding
     "for" alone still lets a naive regex re-match starting at "or" one character in.
 (4) Regression: .sol fingerprinting (guards/visibility extraction) is byte-for-byte unchanged.
 (5) Regression: .rs fingerprinting (guards from attrs) is byte-for-byte unchanged.
 (6) Regression: compute_delta() classification (NEW/REVERSED/REGRESSION/PERSISTENT) and the
     REMOVED `legacy_alive_check: True` field (Plan 6 §43.7/§52) are unchanged -- this task did
     not touch compute_delta() at all, verified behaviorally.

Run: py -3 -X utf8 scripts/wave_delta_web_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import shutil
import tempfile
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
SCRIPTS_DIR = os.path.join(ROOT, "scripts")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


wd = _load("wave_delta", os.path.join(SCRIPTS_DIR, "wave_delta.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def _names(funcs):
    """path::func -> bare func name set (drop path prefix + #N dedup suffix)."""
    out = set()
    for k in funcs:
        base = k.rsplit("#", 1)[0] if k.rsplit("#", 1)[-1].isdigit() and "#" in k else k
        out.add(base.split("::", 1)[1])
    return out


def _write(dirpath, fname, content):
    p = os.path.join(dirpath, fname)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


TMP = tempfile.mkdtemp(prefix="wave_delta_web_selftest_")
try:
    # ── CASE 1: JS positive + negative forms, end-to-end via fingerprint() ─────────────────
    js_dir = os.path.join(TMP, "js1")
    os.makedirs(js_dir)
    JS_SRC = (
        "// line comment: const notReal = (a) => a;\n"
        "/* block comment\n"
        "   function commentedOut(a) { return a; }\n"
        "*/\n"
        "const s = \"not a function => nope\";\n"
        "\n"
        "const add = (a, b) => a + b;\n"
        "\n"
        "const fetchData = async () => {\n"
        "  return await fetch('/api');\n"
        "};\n"
        "\n"
        "export function sum(a, b) {\n"
        "  return a + b;\n"
        "}\n"
        "\n"
        "export async function loadUser(id) {\n"
        "  return await db.get(id);\n"
        "}\n"
        "\n"
        "export default function handler(req, res) {\n"
        "  res.end();\n"
        "}\n"
        "\n"
        "class Foo {\n"
        "  bar(x, y) {\n"
        "    return x + y;\n"
        "  }\n"
        "\n"
        "  async baz(x) {\n"
        "    return x;\n"
        "  }\n"
        "}\n"
        "\n"
        "const obj = {\n"
        "  greet(name) {\n"
        "    return \"hi \" + name;\n"
        "  }\n"
        "};\n"
        "\n"
        "if (add(1, 2)) {\n"
        "  console.log(\"truthy\");\n"
        "}\n"
        "\n"
        "for (let i = 0; i < 10; i++) {\n"
        "  console.log(i);\n"
        "}\n"
        "\n"
        "while (isReady()) {\n"
        "  tick();\n"
        "}\n"
        "\n"
        "const config = { timeout: 5000 };\n"
        "\n"
        "doSomething(a, b);\n"
    )
    _write(js_dir, "app.js", JS_SRC)
    js_funcs, js_nfiles = wd.fingerprint(js_dir)
    js_names = _names(js_funcs)

    check("case1a fingerprint(.js dir): n_files == 1 (extension reached the dispatcher)",
          js_nfiles == 1, "got=%r" % (js_nfiles,))

    EXPECTED_JS = {"add", "fetchData", "sum", "loadUser", "handler", "bar", "baz", "greet"}
    for want in EXPECTED_JS:
        check("case1b positive form present: %r" % want, want in js_names, "js_names=%r" % (js_names,))
    check("case1c exactly the 8 expected positive names, nothing else",
          js_names == EXPECTED_JS, "got=%r expected=%r" % (js_names, EXPECTED_JS))

    NEGATIVE_JS = {"notReal", "commentedOut", "s", "if", "for", "or", "while", "isReady",
                   "config", "doSomething", "Foo", "obj"}
    for bad in NEGATIVE_JS:
        check("case1d negative NOT captured: %r" % bad, bad not in js_names, "js_names=%r" % (js_names,))

    # signature spot-checks (params captured correctly per form)
    sig_by_name = {k.split("::", 1)[1]: v["sig"] for k, v in js_funcs.items()}
    check("case1e arrow sig: add(a, b)", sig_by_name.get("add") == "add(a, b)", "got=%r" % (sig_by_name.get("add"),))
    check("case1f async-arrow sig: fetchData()", sig_by_name.get("fetchData") == "fetchData()",
          "got=%r" % (sig_by_name.get("fetchData"),))
    check("case1g export-async-function sig: loadUser(id)", sig_by_name.get("loadUser") == "loadUser(id)",
          "got=%r" % (sig_by_name.get("loadUser"),))
    check("case1h export-default-function sig: handler(req, res)",
          sig_by_name.get("handler") == "handler(req, res)", "got=%r" % (sig_by_name.get("handler"),))
    check("case1i class-method sig: bar(x, y)", sig_by_name.get("bar") == "bar(x, y)",
          "got=%r" % (sig_by_name.get("bar"),))
    check("case1j async-class-method sig: baz(x)", sig_by_name.get("baz") == "baz(x)",
          "got=%r" % (sig_by_name.get("baz"),))
    check("case1k object-method sig: greet(name)", sig_by_name.get("greet") == "greet(name)",
          "got=%r" % (sig_by_name.get("greet"),))

    # ── CASE 2: TS generics (.ts) ────────────────────────────────────────────────────────────
    ts_dir = os.path.join(TMP, "ts1")
    os.makedirs(ts_dir)
    TS_SRC = (
        "function identityFn<T>(x: T): T {\n"
        "  return x;\n"
        "}\n"
        "\n"
        "const identity = <T,>(x: T): T => x;\n"
        "\n"
        "export async function loadItem<T>(id: string): Promise<T> {\n"
        "  return fetch(id) as unknown as T;\n"
        "}\n"
        "\n"
        "// const fake = <T,>(x: T) => x;  -- comment, must NOT be captured\n"
        "\n"
        "type Mapper<T> = (x: T) => T;\n"
    )
    _write(ts_dir, "app.ts", TS_SRC)
    ts_funcs, ts_nfiles = wd.fingerprint(ts_dir)
    ts_names = _names(ts_funcs)
    check("case2a fingerprint(.ts dir): n_files == 1", ts_nfiles == 1, "got=%r" % (ts_nfiles,))
    check("case2b function<T> generic form: identityFn", "identityFn" in ts_names, "ts_names=%r" % (ts_names,))
    check("case2c arrow <T,> generic form: identity", "identity" in ts_names, "ts_names=%r" % (ts_names,))
    check("case2d export async function<T> generic: loadItem", "loadItem" in ts_names, "ts_names=%r" % (ts_names,))
    check("case2e exactly 3 names, no extras", ts_names == {"identityFn", "identity", "loadItem"},
          "got=%r" % (ts_names,))
    check("case2f commented-out generic arrow NOT captured: fake", "fake" not in ts_names, "ts_names=%r" % (ts_names,))
    check("case2g TS type alias NOT captured as function: Mapper", "Mapper" not in ts_names,
          "ts_names=%r" % (ts_names,))

    # ── CASE 3: .jsx / .tsx reachability (whitelist req (a), remaining 2 of 4 extensions) ────
    jsx_dir = os.path.join(TMP, "jsx1")
    os.makedirs(jsx_dir)
    _write(jsx_dir, "Widget.jsx", "export const Widget = (props) => {\n  return null;\n};\n")
    _write(jsx_dir, "Panel.tsx", "export const Panel = <T,>(props: T): T => props;\n")
    jsx_funcs, jsx_nfiles = wd.fingerprint(jsx_dir)
    jsx_names = _names(jsx_funcs)
    check("case3a fingerprint(.jsx+.tsx dir): n_files == 2", jsx_nfiles == 2, "got=%r" % (jsx_nfiles,))
    check("case3b .jsx arrow component reached: Widget", "Widget" in jsx_names, "jsx_names=%r" % (jsx_names,))
    check("case3c .tsx generic arrow component reached: Panel", "Panel" in jsx_names, "jsx_names=%r" % (jsx_names,))

    # ── CASE 4: regression -- .sol branch untouched ─────────────────────────────────────────
    sol_dir = os.path.join(TMP, "sol1")
    os.makedirs(sol_dir)
    SOL_SRC = (
        "pragma solidity ^0.8.0;\n"
        "contract C {\n"
        "    function safeOp(uint x) external onlyOwner {\n"
        "    }\n"
        "    function openOp(uint x) public {\n"
        "    }\n"
        "}\n"
    )
    _write(sol_dir, "C.sol", SOL_SRC)
    sol_funcs, sol_nfiles = wd.fingerprint(sol_dir)
    sol_by_name = {k.split("::", 1)[1]: v for k, v in sol_funcs.items()}
    check("case4a .sol fingerprint unchanged: n_files == 1", sol_nfiles == 1, "got=%r" % (sol_nfiles,))
    check("case4b .sol safeOp guards == [onlyOwner]",
          sol_by_name.get("safeOp", {}).get("guards") == ["onlyOwner"], "got=%r" % (sol_by_name.get("safeOp"),))
    check("case4c .sol safeOp visibility == external",
          sol_by_name.get("safeOp", {}).get("visibility") == "external", "got=%r" % (sol_by_name.get("safeOp"),))
    check("case4d .sol openOp guards == [] (no guard)",
          sol_by_name.get("openOp", {}).get("guards") == [], "got=%r" % (sol_by_name.get("openOp"),))
    check("case4e .sol openOp visibility == public",
          sol_by_name.get("openOp", {}).get("visibility") == "public", "got=%r" % (sol_by_name.get("openOp"),))

    # ── CASE 5: regression -- .rs branch untouched ──────────────────────────────────────────
    rs_dir = os.path.join(TMP, "rs1")
    os.makedirs(rs_dir)
    RS_SRC = (
        "#[access_control(only_admin)]\n"
        "pub fn safe_transfer(ctx: Context<Transfer>) -> Result<()> {\n"
        "    Ok(())\n"
        "}\n"
        "\n"
        "pub fn open_transfer(ctx: Context<Transfer>) -> Result<()> {\n"
        "    Ok(())\n"
        "}\n"
    )
    _write(rs_dir, "lib.rs", RS_SRC)
    rs_funcs, rs_nfiles = wd.fingerprint(rs_dir)
    rs_by_name = {k.split("::", 1)[1]: v for k, v in rs_funcs.items()}
    check("case5a .rs fingerprint unchanged: n_files == 1", rs_nfiles == 1, "got=%r" % (rs_nfiles,))
    check("case5b .rs safe_transfer guards include access_control+only_admin",
          set(rs_by_name.get("safe_transfer", {}).get("guards", [])) >= {"access_control", "only_admin"},
          "got=%r" % (rs_by_name.get("safe_transfer"),))
    check("case5c .rs open_transfer guards == [] (no attrs)",
          rs_by_name.get("open_transfer", {}).get("guards") == [], "got=%r" % (rs_by_name.get("open_transfer"),))
    check("case5d .rs visibility == pub for both",
          rs_by_name.get("safe_transfer", {}).get("visibility") == "pub"
          and rs_by_name.get("open_transfer", {}).get("visibility") == "pub")

    # ── CASE 6: regression -- compute_delta() classification + legacy_alive_check untouched ─
    old_funcs = {
        "a.sol::stableOp": {"sig": "stableOp()", "guards": [], "visibility": "public", "mutability": ""},
        "a.sol::safeOp": {"sig": "safeOp()", "guards": ["onlyOwner"], "visibility": "external", "mutability": ""},
        "a.sol::hardenOp": {"sig": "hardenOp()", "guards": [], "visibility": "external", "mutability": ""},
        "a.sol::legacyOp": {"sig": "legacyOp()", "guards": [], "visibility": "public", "mutability": ""},
    }
    new_funcs = {
        "a.sol::stableOp": {"sig": "stableOp()", "guards": [], "visibility": "public", "mutability": ""},
        "a.sol::safeOp": {"sig": "safeOp()", "guards": [], "visibility": "external", "mutability": ""},
        "a.sol::hardenOp": {"sig": "hardenOp()", "guards": ["onlyOwner"], "visibility": "external", "mutability": ""},
        "a.sol::freshOp": {"sig": "freshOp()", "guards": [], "visibility": "external", "mutability": ""},
    }
    old_snap = {"meta": {"slug": "t6-regress"}, "functions": old_funcs}
    new_snap = {"meta": {"slug": "t6-regress"}, "functions": new_funcs}
    delta = wd.compute_delta(old_snap, new_snap)

    check("case6a NEW picks up freshOp", any(it["fn"] == "a.sol::freshOp" for it in delta["NEW"]),
          "got=%r" % (delta["NEW"],))
    check("case6b REVERSED picks up safeOp (dropped onlyOwner)",
          any(it["fn"] == "a.sol::safeOp" and "onlyOwner" in it["dropped_guards"] for it in delta["REVERSED"]),
          "got=%r" % (delta["REVERSED"],))
    check("case6c REGRESSION picks up hardenOp (added onlyOwner)",
          any(it["fn"] == "a.sol::hardenOp" and "onlyOwner" in it["added_guards"] for it in delta["REGRESSION"]),
          "got=%r" % (delta["REGRESSION"],))
    check("case6d PERSISTENT counts stableOp (unchanged)", delta["PERSISTENT"] == 1, "got=%r" % (delta["PERSISTENT"],))
    removed_legacy = [it for it in delta["REMOVED"] if it["fn"] == "a.sol::legacyOp"]
    check("case6e REMOVED picks up legacyOp", len(removed_legacy) == 1, "got=%r" % (delta["REMOVED"],))
    check("case6f REMOVED legacyOp carries legacy_alive_check: True (§43.7/§52, untouched by this task)",
          bool(removed_legacy) and removed_legacy[0].get("legacy_alive_check") is True,
          "got=%r" % (removed_legacy,))

finally:
    shutil.rmtree(TMP, ignore_errors=True)

print("=== WAVE_DELTA WEB/JS-TS SELFTEST (FDE Plan 7, Part XI, Task 6) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
