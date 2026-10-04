# -*- coding: utf-8 -*-
"""Selftest for the Cross-Clone Differential producer (FDE Plan 4, Task 3).

Proves:
 (1) asymmetry_scanner_dapp.compute_clone_diffs() finds real deltas on all four axes
     (env-diff / CSP-headers / API-authz / chain-deploy-diff) from fixture HostFingerprint
     objects — no live network involved (fixtures are constructed directly).
 (2) clone_diff_to_markdown() renders the deltas into the clone_diff.md table format, and stays
     silent (empty table, no false positives) on identical hosts.
 (3) Empty diff (single deploy / no clones) still produces a file containing
     'RESULT: N/A — single deploy' — Task 4's gate detector depends on this to tell
     "ran, nothing to diff" apart from "never ran".
 (4) write_clone_diff_md() honors the EXACT path it is given (critical session-path rule from the
     brief) — both as a direct unit call and through the real --md-out CLI wiring in main()
     (using an RFC 2606 .invalid host so the CLI test needs no reachable live service).
 (5) dapp_clone_detector.detect_clones() exposes clone_hosts (SET of clone hosts, ready to feed
     into asymmetry_scanner's --subdomains) alongside the existing clones field, and its bundle
     env-var grep (_grep_env_vars) collects VITE_*/REACT_APP_*/NEXT_PUBLIC_* literals per host —
     tested via a monkeypatched _fingerprint_host (no live network).

Run: py -3 -X utf8 scripts/dapphunt/hypothesis/clone_diff_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import copy
import json
import shutil
import tempfile
import importlib.util
import urllib.parse

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
HYPOTHESIS_DIR = os.path.join(ROOT, "scripts", "dapphunt", "hypothesis")
CORE_DIR = os.path.join(ROOT, "scripts", "dapphunt", "core")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    # Register BEFORE exec — Python 3.14's dataclasses looks up cls.__module__ in sys.modules
    # while processing @dataclass classes defined at module scope (KW_ONLY sentinel check);
    # without this, dataclass-defining modules loaded via importlib crash on this Python version.
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


asy = _load("asymmetry_scanner_dapp", os.path.join(HYPOTHESIS_DIR, "asymmetry_scanner_dapp.py"))
dc = _load("dapp_clone_detector", os.path.join(CORE_DIR, "dapp_clone_detector.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def _rows_by_axis(rows, axis):
    return [r for r in rows if r.axis == axis]


def _fp(host, **overrides):
    """Build a HostFingerprint with sane blank defaults, overridden by kwargs."""
    base = dict(
        host=host, url=f"https://{host}/", status_code=200,
        security_headers_present=[], security_headers_missing=[],
        bundle_url_pattern="/assets/index-<hash>.js", bundle_signature="sig-shared",
        privy_app_id=None, walletconnect_project_id=None, react_dapp_banner=True,
    )
    base.update(overrides)
    return asy.HostFingerprint(**base)


# ── CASE 1: CSP-headers-diff + API-authz-diff (prod hardened, clone bare) ──────────────────────
prod1 = _fp(
    "prod.example.com",
    raw_headers={
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'",
        "x-frame-options": "SAMEORIGIN",
    },
    api_probes={"/api/users": 403},
)
clone1 = _fp(
    "staging.example.com",
    raw_headers={},
    api_probes={"/api/users": 200},
)
rows1 = asy.compute_clone_diffs([prod1, clone1], "prod.example.com")
csp_rows1 = _rows_by_axis(rows1, "CSP/headers")
authz_rows1 = _rows_by_axis(rows1, "API-authz")
check("case1a compute_clone_diffs: CSP/headers row present for MISSING frame-ancestors",
      any("MISSING frame-ancestors" in r.delta for r in csp_rows1), "rows=%r" % (csp_rows1,))
check("case1b compute_clone_diffs: API-authz row present, 403->200 classified object-authz leak",
      any(r.diff_class == "object-authz" and "200" in r.delta and "(leak)" in r.delta for r in authz_rows1),
      "rows=%r" % (authz_rows1,))

md1 = asy.clone_diff_to_markdown("prod.example.com", rows1)
check("case1c clone_diff_to_markdown: rendered table contains CSP-diff line",
      "MISSING frame-ancestors" in md1, md1)
check("case1d clone_diff_to_markdown: rendered table contains API-authz leak line",
      "200 (leak)" in md1, md1)
check("case1e clone_diff_to_markdown: RESULT header reports non-zero delta count",
      md1.splitlines()[1].startswith("RESULT: ") and "N/A" not in md1.splitlines()[1],
      md1.splitlines()[1])

# ── CASE 2: env-diff (VITE_RPC mainnet vs staging) ──────────────────────────────────────────────
prod2 = _fp("prod.example.com", env_vars={"VITE_RPC": "mainnet"})
clone2 = _fp("staging.example.com", env_vars={"VITE_RPC": "staging"})
rows2 = asy.compute_clone_diffs([prod2, clone2], "prod.example.com")
env_rows2 = _rows_by_axis(rows2, "env-diff")
check("case2a compute_clone_diffs: env-diff row present for VITE_RPC mainnet->staging",
      any("VITE_RPC" in r.prod and "mainnet" in r.prod and "staging" in r.delta for r in env_rows2),
      "rows=%r" % (env_rows2,))
md2 = asy.clone_diff_to_markdown("prod.example.com", rows2)
check("case2b clone_diff_to_markdown: env-diff line present in rendered table",
      "env-diff" in md2 and "VITE_RPC" in md2, md2)

# ── CASE 3: chain-deploy-diff (different chainId + different EIP-712 verifyingContract) ─────────
prod3 = _fp("prod.example.com", chain_id="8453",
            eip712_domain="0x1111111111111111111111111111111111111111")
clone3 = _fp("staging.example.com", chain_id="1",
             eip712_domain="0x2222222222222222222222222222222222222222")
rows3 = asy.compute_clone_diffs([prod3, clone3], "prod.example.com")
chain_rows3 = _rows_by_axis(rows3, "chain-deploy-diff")
check("case3a compute_clone_diffs: chain-deploy-diff row present for chainId 8453->1",
      any("chainId=8453" in r.prod and "chainId=1" in r.delta for r in chain_rows3),
      "rows=%r" % (chain_rows3,))
check("case3b compute_clone_diffs: chain-deploy-diff row present for verifyingContract mismatch",
      any("0x1111" in r.prod and "0x2222" in r.delta for r in chain_rows3),
      "rows=%r" % (chain_rows3,))
md3 = asy.clone_diff_to_markdown("prod.example.com", rows3)
check("case3c clone_diff_to_markdown: chain-deploy-diff line present in rendered table",
      "chain-deploy-diff" in md3 and "chain-mismatch" in md3, md3)

# ── CASE 3d: negative — identical hosts on every axis produce ZERO rows (no false positives) ────
prod3n = _fp("prod.example.com",
             raw_headers={"content-security-policy": "frame-ancestors 'self'", "x-frame-options": "SAMEORIGIN"},
             env_vars={"VITE_RPC": "mainnet"}, chain_id="8453",
             eip712_domain="0x1111111111111111111111111111111111111111",
             api_probes={"/api/users": 403})
clone3n = _fp("mirror.example.com",
              raw_headers={"content-security-policy": "frame-ancestors 'self'", "x-frame-options": "SAMEORIGIN"},
              env_vars={"VITE_RPC": "mainnet"}, chain_id="8453",
              eip712_domain="0x1111111111111111111111111111111111111111",
              api_probes={"/api/users": 403})
rows3n = asy.compute_clone_diffs([prod3n, clone3n], "prod.example.com")
check("case3d compute_clone_diffs: identical hosts on all 4 axes -> zero rows (no false positive)",
      rows3n == [], "rows=%r" % (rows3n,))

# ── CASE 3e: API-authz lockdown direction (prod 200, clone 403) classified as drift, not a leak ─
prod3e = _fp("prod.example.com", api_probes={"/api/users": 200})
clone3e = _fp("locked.example.com", api_probes={"/api/users": 403})
rows3e = asy.compute_clone_diffs([prod3e, clone3e], "prod.example.com")
authz_rows3e = _rows_by_axis(rows3e, "API-authz")
check("case3e compute_clone_diffs: prod=200/clone=403 classified authz-drift (not object-authz leak)",
      len(authz_rows3e) == 1 and authz_rows3e[0].diff_class == "authz-drift",
      "rows=%r" % (authz_rows3e,))

# ── CASE 4: single-host fixture -> clone_diff.md still created, RESULT: N/A — single deploy ─────
rows4 = asy.compute_clone_diffs([prod1], "prod.example.com")
check("case4a compute_clone_diffs: single host in list -> zero rows", rows4 == [], "rows=%r" % (rows4,))
md4 = asy.clone_diff_to_markdown("prod.example.com", rows4)
check("case4b clone_diff_to_markdown: single-deploy fixture renders RESULT: N/A — single deploy",
      "RESULT: N/A — single deploy" in md4, md4)

TMP4 = tempfile.mkdtemp(prefix="clonediff-case4-")
try:
    out4 = os.path.join(TMP4, "clone_diff.md")
    ret4 = asy.write_clone_diff_md(out4, "prod.example.com", rows4)
    check("case4c write_clone_diff_md: file created even for empty diff", os.path.isfile(out4))
    with open(out4, "r", encoding="utf-8") as f:
        content4 = f.read()
    check("case4d write_clone_diff_md: on-disk content has RESULT: N/A — single deploy",
          "RESULT: N/A — single deploy" in content4, content4)
finally:
    shutil.rmtree(TMP4, ignore_errors=True)

# ── CASE 5: session-path rule — --md-out writes to the EXACT full path given, never CWD ─────────
CWD_STRAY = os.path.join(os.getcwd(), "clone_diff.md")
had_stray_before = os.path.exists(CWD_STRAY)

TMP5 = tempfile.mkdtemp(prefix="clonediff-case5-")
try:
    # Simulate a real session path: <tmp>/sessions/exampledomain/clone_diff.md
    full_path5 = os.path.join(TMP5, "sessions", "exampledomain", "clone_diff.md")
    ret5 = asy.write_clone_diff_md(full_path5, "example.com", rows1)
    check("case5a write_clone_diff_md: file landed EXACTLY at the full path passed in",
          os.path.exists(full_path5), "expected=%r" % (full_path5,))
    check("case5b write_clone_diff_md: returned path == the exact path given (no rewriting)",
          str(ret5) == full_path5 or os.path.normpath(str(ret5)) == os.path.normpath(full_path5),
          "got=%r expected=%r" % (ret5, full_path5))
    check("case5c write_clone_diff_md: did NOT also drop a stray clone_diff.md in CWD",
          os.path.exists(CWD_STRAY) == had_stray_before, "CWD stray now exists unexpectedly")

    # ── CASE 5d/5e: same rule proven through the REAL CLI entrypoint (main() --md-out) ──────────
    # RFC 2606 .invalid TLD never resolves -> fingerprint_host()/_fetch() fail fast+gracefully
    # (fail-open), so this needs no reachable live service and stays deterministic offline.
    full_path5b = os.path.join(TMP5, "sessions", "cliexample", "clone_diff.md")
    argv5 = ["--target", "http://clone-diff-selftest.invalid/", "--md-out", full_path5b, "--quiet"]
    ret_code5 = asy.main(argv5)
    check("case5d main(--md-out): CLI entrypoint wrote clone_diff.md at the EXACT full path given",
          os.path.isfile(full_path5b), "expected=%r ret=%r" % (full_path5b, ret_code5))
    if os.path.isfile(full_path5b):
        with open(full_path5b, "r", encoding="utf-8") as f:
            content5b = f.read()
        check("case5e main(--md-out): single unreachable host -> RESULT: N/A — single deploy",
              "RESULT: N/A — single deploy" in content5b, content5b)
    check("case5f main(--md-out): CLI run did NOT drop a stray clone_diff.md in CWD",
          os.path.exists(CWD_STRAY) == had_stray_before, "CWD stray now exists unexpectedly")
finally:
    shutil.rmtree(TMP5, ignore_errors=True)

# ── CASE 6: dapp_clone_detector — clone_hosts SET + per-host env-var bundle grep ─────────────────
_FAKE_CANDIDATES = {
    "prod.example.com": dc.CloneCandidate(
        host="prod.example.com", url="https://prod.example.com/", is_clone=False, reasons=[],
        privy_app_id="clzaaaaaaaaaaaaaaaaaaaaaaa", wc_project_id=None,
        bundle_pattern="/assets/index-<hash>.js", bundle_head_hash="hash-shared",
        title="MyDapp", severity_hint="low", env_vars={"VITE_RPC": "mainnet"},
    ),
    "clone1.example.com": dc.CloneCandidate(
        host="clone1.example.com", url="https://clone1.example.com/", is_clone=False, reasons=[],
        privy_app_id="clzaaaaaaaaaaaaaaaaaaaaaaa", wc_project_id=None,
        bundle_pattern="/assets/index-<hash>.js", bundle_head_hash="hash-shared",
        title="MyDapp", severity_hint="low", env_vars={"VITE_RPC": "staging"},
    ),
    "other.example.com": dc.CloneCandidate(
        host="other.example.com", url="https://other.example.com/", is_clone=False, reasons=[],
        privy_app_id=None, wc_project_id=None, bundle_pattern=None, bundle_head_hash=None,
        title=None, severity_hint="low", env_vars={},
    ),
}


def _fake_fingerprint_host(url):
    netloc = urllib.parse.urlparse(url).netloc
    return copy.deepcopy(_FAKE_CANDIDATES[netloc])


_orig_fingerprint_host = dc._fingerprint_host
try:
    dc._fingerprint_host = _fake_fingerprint_host
    report6 = dc.detect_clones(
        "https://prod.example.com/",
        ["https://clone1.example.com/", "https://other.example.com/"],
    )
    check("case6a detect_clones: shared-privy candidate classified as clone",
          "clone1.example.com" in report6.clones, "clones=%r" % (report6.clones,))
    check("case6b detect_clones: unrelated candidate NOT classified as clone",
          "other.example.com" not in report6.clones, "clones=%r" % (report6.clones,))
    check("case6c detect_clones: clone_hosts field present and mirrors clones (2-host scenario)",
          report6.clone_hosts == report6.clones and report6.clone_hosts != [],
          "clone_hosts=%r clones=%r" % (report6.clone_hosts, report6.clones))

    report6_single = dc.detect_clones("https://prod.example.com/", [])
    check("case6d detect_clones: single-host (no candidates) -> clones empty",
          report6_single.clones == [], "clones=%r" % (report6_single.clones,))
    check("case6e detect_clones: single-host (no candidates) -> clone_hosts empty",
          report6_single.clone_hosts == [], "clone_hosts=%r" % (report6_single.clone_hosts,))
finally:
    dc._fingerprint_host = _orig_fingerprint_host

# ── CASE 7: pure grep-helper correctness (env/chainId/EIP-712), independent of live fetch ───────
sample_bundle = (
    'const cfg={"VITE_RPC_URL":"https://mainnet.example.com","REACT_APP_API_KEY":"sk_live_abc"};'
    'window.NEXT_PUBLIC_FEATURE_FLAG="on";'
    'const domain={chainId:8453,verifyingContract:"0xAbCdEf1234567890AbCdEf1234567890AbCdEf12"};'
)
grepped = asy._grep_env_vars(sample_bundle)
check("case7a asymmetry_scanner._grep_env_vars: VITE_* literal captured",
      grepped.get("VITE_RPC_URL") == "https://mainnet.example.com", "got=%r" % (grepped,))
check("case7b asymmetry_scanner._grep_env_vars: REACT_APP_* literal captured",
      grepped.get("REACT_APP_API_KEY") == "sk_live_abc", "got=%r" % (grepped,))
check("case7c asymmetry_scanner._grep_env_vars: NEXT_PUBLIC_* literal captured",
      grepped.get("NEXT_PUBLIC_FEATURE_FLAG") == "on", "got=%r" % (grepped,))
check("case7d asymmetry_scanner._grep_chain_id: chainId captured",
      asy._grep_chain_id(sample_bundle) == "8453", "got=%r" % (asy._grep_chain_id(sample_bundle),))
check("case7e asymmetry_scanner._grep_eip712_domain: verifyingContract captured",
      asy._grep_eip712_domain(sample_bundle) == "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12",
      "got=%r" % (asy._grep_eip712_domain(sample_bundle),))

grepped_dc = dc._grep_env_vars(sample_bundle)
check("case7f dapp_clone_detector._grep_env_vars: same literals captured (bundle-per-host grep)",
      grepped_dc.get("VITE_RPC_URL") == "https://mainnet.example.com"
      and grepped_dc.get("REACT_APP_API_KEY") == "sk_live_abc", "got=%r" % (grepped_dc,))

# ── CASE 8: existing JSON output NOT broken (asdict + json.dumps still round-trips) ─────────────
report8 = asy.AsymmetryReport(
    target="prod.example.com", primary_host="prod.example.com",
    hosts_scanned=[prod1, clone1], asymmetries=[], hypotheses=[],
)
report8.clone_diff = rows1
import dataclasses
payload8 = json.dumps(dataclasses.asdict(report8), ensure_ascii=False, indent=2)
parsed8 = json.loads(payload8)
check("case8a JSON regression: asdict(AsymmetryReport)+json.dumps round-trips without error",
      isinstance(parsed8, dict))
check("case8b JSON regression: pre-existing keys still present unchanged",
      set(["target", "primary_host", "hosts_scanned", "asymmetries", "hypotheses"]) <= set(parsed8.keys()),
      "keys=%r" % (list(parsed8.keys()),))
check("case8c JSON regression: clone_diff is additive (present, non-empty, matches computed rows)",
      "clone_diff" in parsed8 and len(parsed8["clone_diff"]) == len(rows1),
      "got=%r" % (parsed8.get("clone_diff"),))

print("=== CLONE_DIFF SELFTEST (FDE Plan 4, Task 3) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
