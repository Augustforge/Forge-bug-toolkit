# -*- coding: utf-8 -*-
"""Selftest for the Data-Flow Divergence Map producer (FDE Plan 4, Task 5).

Proves:
 (1) trace_dataflow() pairs a display-source variable with a reality-sink variable for the
     "amount" logical value and correctly flags DIVERGENCE when they are different variables
     (Aave×CoW class: output-box reads `destSpotAmount`, signTypedData payload reads `buyAmount`).
 (2) trace_dataflow() reports NO divergence (same_var == "Y") when the SAME variable feeds both
     the DOM-display sink and the signing/tx-payload sink.
 (3) R3 (minification): when the bundle is minified (identifiers erased, few very-long lines) and
     no display/sink pair can be resolved, trace_dataflow() still returns a row carrying
     "INCONCLUSIVE (minified)" — never a silently-empty result — and dataflow_map_to_markdown()
     renders that string into the artifact.
 (4) write_dataflow_map_md() — and the real --md-out CLI wiring in main() — write dataflow_map.md
     to the EXACT full path given, never CWD-relative or rewritten (session-path rule).
 (5) Regression: the pre-existing flat 14-pattern grep (scan_bundle / _PATTERNS) and its JSON
     output (asdict + json.dumps) still work unchanged, and main() without --md-out does NOT
     write a dataflow_map.md anywhere.

Run: py -3 -X utf8 scripts/dapphunt/hypothesis/dataflow_map_selftest.py
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
import dataclasses

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
HYPOTHESIS_DIR = os.path.join(ROOT, "scripts", "dapphunt", "hypothesis")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    # Register BEFORE exec — Python 3.14's dataclasses looks up cls.__module__ in sys.modules
    # while processing @dataclass classes defined at module scope (KW_ONLY sentinel check);
    # without this, dataclass-defining modules loaded via importlib crash on this Python version.
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


dvr = _load("display_vs_reality_grep", os.path.join(HYPOTHESIS_DIR, "display_vs_reality_grep.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def _rows_by_logical_value(rows, logical_value):
    return [r for r in rows if r.logical_value == logical_value]


# ── CASE 1: DIVERGENCE — display reads destSpotAmount, signed payload reads buyAmount ───────────
FIXTURE_DIVERGENCE = (
    "function renderQuote(quote) {\n"
    "  const displayAmt = destSpotAmount;\n"
    "  outputBox.textContent = displayAmt;\n"
    "}\n"
    "\n"
    "async function signOrder(order) {\n"
    "  const buyAmount = destSpotAmount - fees;\n"
    "  return wallet.signTypedData({\n"
    "    domain,\n"
    "    types,\n"
    "    message: { buyAmount: buyAmount, sellToken: order.sellToken },\n"
    "  });\n"
    "}\n"
)
rows1 = dvr.trace_dataflow(FIXTURE_DIVERGENCE)
amount_rows1 = _rows_by_logical_value(rows1, "amount")
check("case1a trace_dataflow: exactly one 'amount' row produced for the divergence fixture",
      len(amount_rows1) == 1, "rows=%r" % (rows1,))
if amount_rows1:
    r1 = amount_rows1[0]
    check("case1b trace_dataflow: display-source resolved to destSpotAmount",
          r1.display_source == "destSpotAmount", "row=%r" % (r1,))
    check("case1c trace_dataflow: reality-sink resolved to buyAmount",
          r1.reality_sink == "buyAmount", "row=%r" % (r1,))
    check("case1d trace_dataflow: same_var flagged N (different source variables)",
          r1.same_var == "N", "row=%r" % (r1,))
    check("case1e trace_dataflow: divergence text is non-empty for an N row",
          bool(r1.divergence), "row=%r" % (r1,))

md1 = dvr.dataflow_map_to_markdown("example.com", rows1)
check("case1f dataflow_map_to_markdown: table contains the amount/destSpotAmount/buyAmount/N row",
      "| amount | destSpotAmount | buyAmount | N |" in md1, md1)
check("case1g dataflow_map_to_markdown: header matches the brief's 5-column format",
      "| logical-value | display-source | reality-sink | same-var?(Y/N) | divergence |" in md1,
      md1)

# ── CASE 2: NO-DIVERGENCE — the SAME variable `amt` feeds both display and signing sink ─────────
FIXTURE_NO_DIVERGENCE = (
    "function renderQuote(quote) {\n"
    "  const displayAmt = amt;\n"
    "  outputBox.textContent = displayAmt;\n"
    "}\n"
    "\n"
    "async function signOrder(order) {\n"
    "  return wallet.signTypedData({\n"
    "    domain,\n"
    "    types,\n"
    "    message: { buyAmount: amt, sellToken: order.sellToken },\n"
    "  });\n"
    "}\n"
)
rows2 = dvr.trace_dataflow(FIXTURE_NO_DIVERGENCE)
amount_rows2 = _rows_by_logical_value(rows2, "amount")
check("case2a trace_dataflow: exactly one 'amount' row produced for the no-divergence fixture",
      len(amount_rows2) == 1, "rows=%r" % (rows2,))
if amount_rows2:
    r2 = amount_rows2[0]
    check("case2b trace_dataflow: display-source and reality-sink both resolve to the same var 'amt'",
          r2.display_source == "amt" and r2.reality_sink == "amt", "row=%r" % (r2,))
    check("case2c trace_dataflow: same_var flagged Y (identical source variable)",
          r2.same_var == "Y", "row=%r" % (r2,))
    check("case2d trace_dataflow: divergence text is empty for a Y row",
          r2.divergence == "", "row=%r" % (r2,))

md2 = dvr.dataflow_map_to_markdown("example.com", rows2)
check("case2e dataflow_map_to_markdown: table contains the amount/amt/amt/Y row",
      "| amount | amt | amt | Y |" in md2, md2)
check("case2f dataflow_map_to_markdown: no 'N' verdict leaked into the no-divergence render",
      "| N |" not in md2, md2)

# ── CASE 3: R3 minification — identifiers erased, pairing impossible -> INCONCLUSIVE, not silent ─
FIXTURE_MINIFIED = (
    "var a=b.c,d=e.f;function g(h){i.textContent=a;j.signTypedData({k:d,l:{m:a,n:h.o}})}"
    "async function p(q){return r.signTypedData({s:t,u:{m:d,v:q.w}})}"
    "var z0=1,z1=2,z2=3,z3=4,z4=5,z5=6,z6=7,z7=8,z8=9,z9=10;"
)
check("case3-fixture-sanity: minified fixture is a single line over 150 chars (heuristic input)",
      "\n" not in FIXTURE_MINIFIED and len(FIXTURE_MINIFIED) > 150,
      "len=%d" % (len(FIXTURE_MINIFIED),))
rows3 = dvr.trace_dataflow(FIXTURE_MINIFIED)
check("case3a trace_dataflow: minified bundle with zero resolvable pairs still returns a row (not empty)",
      len(rows3) >= 1, "rows=%r" % (rows3,))
check("case3b trace_dataflow: the row is explicitly marked INCONCLUSIVE (minified)",
      any(r.same_var == "INCONCLUSIVE (minified)" for r in rows3), "rows=%r" % (rows3,))

md3 = dvr.dataflow_map_to_markdown("example.com", rows3)
check("case3c dataflow_map_to_markdown: rendered artifact contains the literal string "
      "'INCONCLUSIVE (minified)' (R3 requirement — never silently empty)",
      "INCONCLUSIVE (minified)" in md3, md3)

# ── CASE 4: session-path rule — --md-out writes to the EXACT full path given, never CWD ─────────
CWD_STRAY = os.path.join(os.getcwd(), "dataflow_map.md")
had_stray_before = os.path.exists(CWD_STRAY)

TMP4 = tempfile.mkdtemp(prefix="dataflowmap-case4-")
try:
    # 4a/4b: direct unit call
    full_path4 = os.path.join(TMP4, "sessions", "exampledomain", "dataflow_map.md")
    ret4 = dvr.write_dataflow_map_md(full_path4, "example.com", rows1)
    check("case4a write_dataflow_map_md: file landed EXACTLY at the full path passed in",
          os.path.exists(full_path4), "expected=%r" % (full_path4,))
    check("case4b write_dataflow_map_md: returned path == the exact path given (no rewriting)",
          str(ret4) == full_path4 or os.path.normpath(str(ret4)) == os.path.normpath(full_path4),
          "got=%r expected=%r" % (ret4, full_path4))
    check("case4c write_dataflow_map_md: did NOT also drop a stray dataflow_map.md in CWD",
          os.path.exists(CWD_STRAY) == had_stray_before, "CWD stray now exists unexpectedly")

    # 4d-4f: same rule through the REAL CLI entrypoint (main() --md-out)
    bundle_path4 = os.path.join(TMP4, "bundle-main.js")
    with open(bundle_path4, "w", encoding="utf-8") as f:
        f.write(FIXTURE_DIVERGENCE)
    full_path4b = os.path.join(TMP4, "sessions", "cliexample", "dataflow_map.md")
    argv4 = ["--bundle", bundle_path4, "--target", "cli.example.com", "--md-out", full_path4b, "--quiet"]
    ret_code4 = dvr.main(argv4)
    check("case4d main(--md-out): CLI entrypoint wrote dataflow_map.md at the EXACT full path given",
          os.path.isfile(full_path4b), "expected=%r ret=%r" % (full_path4b, ret_code4))
    if os.path.isfile(full_path4b):
        with open(full_path4b, "r", encoding="utf-8") as f:
            content4b = f.read()
        check("case4e main(--md-out): CLI-driven artifact contains the same divergence row as the unit call",
              "| amount | destSpotAmount | buyAmount | N |" in content4b, content4b)
    check("case4f main(--md-out): CLI run did NOT drop a stray dataflow_map.md in CWD",
          os.path.exists(CWD_STRAY) == had_stray_before, "CWD stray now exists unexpectedly")
finally:
    shutil.rmtree(TMP4, ignore_errors=True)

# ── CASE 5: regression — pre-existing flat pattern-grep + JSON output still work unchanged ──────
FIXTURE_REGRESSION = "Default slippage: '0.5'% applied automatically. Expires in 30 days."
report5 = dvr.scan_bundle(FIXTURE_REGRESSION, "regression.example.com")
check("case5a scan_bundle: pre-existing flat-pattern grep still finds the slippage surface",
      any(m.surface == "slippage" for m in report5.mismatches), "mismatches=%r" % (report5.mismatches,))
check("case5b scan_bundle: pre-existing flat-pattern grep still finds the expiry surface",
      any(m.surface == "expiry" for m in report5.mismatches), "mismatches=%r" % (report5.mismatches,))

payload5 = json.dumps(dataclasses.asdict(report5), ensure_ascii=False, indent=2)
parsed5 = json.loads(payload5)
check("case5c JSON regression: asdict(DisplayReport)+json.dumps round-trips without error",
      isinstance(parsed5, dict))
check("case5d JSON regression: pre-existing keys still present unchanged",
      set(["target", "mismatches", "hypotheses"]) <= set(parsed5.keys()), "keys=%r" % (list(parsed5.keys()),))

check("case5e regression: flat pattern table (_PATTERNS) count unchanged by this task (14 entries)",
      len(dvr._PATTERNS) == 14, "count=%d" % (len(dvr._PATTERNS),))

# main() without --md-out must NOT produce a dataflow_map.md anywhere touched by the run
TMP5 = tempfile.mkdtemp(prefix="dataflowmap-case5-")
try:
    bundle_path5 = os.path.join(TMP5, "bundle-main.js")
    with open(bundle_path5, "w", encoding="utf-8") as f:
        f.write(FIXTURE_REGRESSION)
    out_path5 = os.path.join(TMP5, "display_vs_reality.json")
    argv5 = ["--bundle", bundle_path5, "--target", "regression.example.com", "--output", out_path5, "--quiet"]
    ret_code5 = dvr.main(argv5)
    check("case5f main(no --md-out): existing JSON --output path still written",
          os.path.isfile(out_path5), "expected=%r" % (out_path5,))
    check("case5g main(no --md-out): exit code reflects mismatches found (non-zero), unchanged contract",
          ret_code5 == 1, "ret=%r" % (ret_code5,))
    stray_dataflow5 = os.path.join(TMP5, "dataflow_map.md")
    check("case5h main(no --md-out): dataflow_map.md is NOT created when --md-out is omitted",
          not os.path.exists(stray_dataflow5), "unexpectedly exists=%r" % (stray_dataflow5,))
finally:
    shutil.rmtree(TMP5, ignore_errors=True)

print("=== DATAFLOW_MAP SELFTEST (FDE Plan 4, Task 5) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
