# -*- coding: utf-8 -*-
"""Selftest for wallet_metadata_xss_check.py's generalization to inverted external-input
trust (FDE Plan 4, Task 8).

Proves:
 (1) malicious_rpc_indexer: an indexer-response marker co-located with a balance-gated
     decision sink (`if (bal >= ...)`) produces a composed hit for that source family.
 (2) malicious_tokenlist: a tokenlist-fetch marker co-located with decimals-driven scaling
     math produces a composed hit for that source family.
 (3) eip1271_liar: isValidSignature()/magic-value co-located with a decision sink that
     gates access on the comparison result produces a composed hit for that source family
     (proves the family added in the "What to do" item 1 actually fires, not just declared).
 (4) Anti-FP: code that reads decimals() on-chain (no tokenlist marker) and code that
     verifies a signature via ecrecover (no isValidSignature/1271 marker) produce ZERO
     composed hits — the detector does not fire on legitimately-verified data.
 (5) inverted_external_input.yaml parses with yaml.safe_load, has >=2 hypothesis records,
     and each carries the schema fields the brief asked for (source/sink/detection/severity
     via source_family/sink_kind/detection_signal/severity_estimate) plus the sibling-schema
     fields apply_dapp.py's matcher needs (id/applies_when/severity_ceiling/hypotheses).
 (6) Regression: the ORIGINAL wallet-metadata x display-XSS co-location path (WalletConnect
     peer.metadata / EIP-6963 detail.info -> innerHTML) still fires unchanged.
 (7) JSON regression: WalletXSSReport's top-level keys (bundles_scanned,
     metadata_references_found, sinks_found, composed_hits, notes) are unchanged so any
     existing consumer of wallet_metadata_xss.json is not broken by the source-family split.

Run: py -3 -X utf8 bug-bounty-toolkit/scripts/dapphunt/core/wallet_metadata_xss_selftest.py
"""
import os
import sys
import json
import dataclasses
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
CORE_DIR = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "dapphunt", "core")
THREAT_MODELS_DIR = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "dapphunt", "threat_models")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    # Register BEFORE exec — Python 3.14's dataclasses looks up cls.__module__ in
    # sys.modules while processing @dataclass classes defined at module scope; without
    # this, dataclass-defining modules loaded via importlib crash on this Python version.
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


wmx = _load("wallet_metadata_xss_check", os.path.join(CORE_DIR, "wallet_metadata_xss_check.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def _families(report):
    return {hit.source_family for hit in report.composed_hits}


def _kinds(report):
    return {hit.sink_kind for hit in report.composed_hits}


# ── CASE 1: malicious_rpc_indexer -> decision sink `if (bal >= ...)` without verification ──
bundle1 = {
    "https://evil-dapp.example/bundle.js": (
        "const res = await indexerClient.query(GET_BALANCE);\n"
        "const bal = res.data.balance;\n"
        "if (bal >= requiredAmount) {\n"
        "  allowWithdrawal();\n"
        "}\n"
    )
}
rep1 = wmx._analyze_bundles(bundle1)
check("case1a malicious_rpc_indexer: composed hit produced for indexer + balance decision sink",
      "malicious_rpc_indexer" in _families(rep1), "families=%r" % (_families(rep1),))
check("case1b malicious_rpc_indexer: composed hit classified as a DECISION sink (not display)",
      any(h.source_family == "malicious_rpc_indexer" and h.sink_kind == "decision" for h in rep1.composed_hits),
      "hits=%r" % (rep1.composed_hits,))

# ── CASE 2: malicious_tokenlist -> decimals feeds scaling math without on-chain read ────────
bundle2 = {
    "https://evil-dapp.example/bundle.js": (
        "const list = await fetch(TOKENLIST_URL).then(r => r.json());\n"
        "const entry = list.tokens[0];\n"
        "const scaledAmount = amountIn * entry.decimals;\n"
    )
}
rep2 = wmx._analyze_bundles(bundle2)
check("case2a malicious_tokenlist: composed hit produced for tokenlist fetch + decimals math",
      "malicious_tokenlist" in _families(rep2), "families=%r" % (_families(rep2),))
check("case2b malicious_tokenlist: composed hit classified as a DECISION sink (not display)",
      any(h.source_family == "malicious_tokenlist" and h.sink_kind == "decision" for h in rep2.composed_hits),
      "hits=%r" % (rep2.composed_hits,))

# ── CASE 3: eip1271_liar -> access decision gated on isValidSignature()/magic-value result ──
bundle3 = {
    "https://evil-dapp.example/bundle.js": (
        "const isValid = wallet.isValidSignature(hash, sig) === 0x1626ba7e;\n"
        "if (isValid) {\n"
        "  grantAccess();\n"
        "}\n"
    )
}
rep3 = wmx._analyze_bundles(bundle3)
check("case3a eip1271_liar: composed hit produced for isValidSignature()/magic-value + decision sink",
      "eip1271_liar" in _families(rep3), "families=%r" % (_families(rep3),))
check("case3b eip1271_liar: composed hit classified as a DECISION sink (not display)",
      any(h.source_family == "eip1271_liar" and h.sink_kind == "decision" for h in rep3.composed_hits),
      "hits=%r" % (rep3.composed_hits,))

# ── CASE 4: anti-FP — legitimately-verified data produces ZERO composed hits ────────────────
bundle4a = {  # decimals genuinely read on-chain, no tokenlist fetch anywhere
    "https://clean-dapp.example/bundle.js": (
        "const decimals = await tokenContract.decimals();\n"
        "const scaledAmount = amountIn * decimals;\n"
    )
}
rep4a = wmx._analyze_bundles(bundle4a)
check("case4a anti-FP: on-chain decimals() read (no tokenlist marker) -> zero composed hits",
      rep4a.composed_hits == [], "hits=%r" % (rep4a.composed_hits,))

bundle4b = {  # signature genuinely verified via ecrecover, no isValidSignature/1271 marker
    "https://clean-dapp.example/bundle.js": (
        "const recovered = ecrecover(hash, v, r, s);\n"
        "if (recovered === signer) {\n"
        "  proceed();\n"
        "}\n"
    )
}
rep4b = wmx._analyze_bundles(bundle4b)
check("case4b anti-FP: ecrecover-verified signature (no eip1271 marker) -> zero composed hits",
      rep4b.composed_hits == [], "hits=%r" % (rep4b.composed_hits,))

# ── CASE 5: inverted_external_input.yaml parses + schema fields present ─────────────────────
YAML_PATH = os.path.join(THREAT_MODELS_DIR, "inverted_external_input.yaml")
try:
    import yaml as _pyyaml
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        tm = _pyyaml.safe_load(f)
    check("case5a inverted_external_input.yaml: yaml.safe_load parses without error",
          isinstance(tm, dict))
    check("case5b inverted_external_input.yaml: top-level sibling-schema fields present",
          {"id", "title", "class", "applies_when", "severity_ceiling", "severity_floor",
           "hypotheses", "mitigation", "evidence_sources"} <= set(tm.keys()),
          "keys=%r" % (list(tm.keys()) if isinstance(tm, dict) else tm,))
    hyps = tm.get("hypotheses") if isinstance(tm, dict) else []
    check("case5c inverted_external_input.yaml: >=2 hypothesis records",
          isinstance(hyps, list) and len(hyps) >= 2, "count=%r" % (len(hyps) if isinstance(hyps, list) else hyps,))
    required_hyp_fields = {"id", "source_family", "sink_kind", "text", "detection_signal",
                            "verification", "severity_estimate"}
    check("case5d inverted_external_input.yaml: every hypothesis has source/sink/detection/severity fields",
          isinstance(hyps, list) and all(required_hyp_fields <= set(h.keys()) for h in hyps),
          "hyps=%r" % (hyps,))
    families_declared = {h.get("source_family") for h in hyps} if isinstance(hyps, list) else set()
    check("case5e inverted_external_input.yaml: covers the 3 script source families (not orphan)",
          families_declared == {"eip1271_liar", "malicious_rpc_indexer", "malicious_tokenlist"},
          "families=%r" % (families_declared,))
except ImportError:
    check("case5a inverted_external_input.yaml: yaml.safe_load parses without error", False,
          "PyYAML not installed — cannot validate")

# ── CASE 6: regression — original wallet-metadata x display-XSS path still fires ────────────
bundle6 = {
    "https://oyster.synfutures.com/bundle.js": (
        "const name = detail.info.name;\n"
        "element.innerHTML = name;\n"
    )
}
rep6 = wmx._analyze_bundles(bundle6)
check("case6a regression: wallet_metadata composed hit still produced (detail.info.name)",
      "wallet_metadata" in _families(rep6), "families=%r" % (_families(rep6),))
check("case6b regression: wallet_metadata composed hit still classified as a DISPLAY sink",
      any(h.source_family == "wallet_metadata" and h.sink_kind == "display" for h in rep6.composed_hits),
      "hits=%r" % (rep6.composed_hits,))
check("case6c regression: severity boosted to high (metadata + sink adjacent lines)",
      any(h.source_family == "wallet_metadata" and h.severity == "high" for h in rep6.composed_hits),
      "hits=%r" % (rep6.composed_hits,))

# ── CASE 7: JSON regression — top-level report keys unchanged for existing consumers ────────
payload7 = json.dumps(dataclasses.asdict(rep6), ensure_ascii=False, indent=2)
parsed7 = json.loads(payload7)
check("case7a JSON regression: asdict(WalletXSSReport)+json.dumps round-trips without error",
      isinstance(parsed7, dict))
check("case7b JSON regression: pre-existing top-level keys still present unchanged",
      {"target", "bundles_scanned", "metadata_references_found", "sinks_found",
       "composed_hits", "notes"} <= set(parsed7.keys()),
      "keys=%r" % (list(parsed7.keys()),))
check("case7c JSON regression: composed_hits entries still carry the pre-existing XSSHit fields",
      all({"field_pattern", "sink_pattern", "severity", "sink_description", "bundle_url",
           "line_no", "context_excerpt"} <= set(h.keys()) for h in parsed7["composed_hits"]),
      "composed_hits=%r" % (parsed7["composed_hits"],))

print("=== WALLET_METADATA_XSS SELFTEST (FDE Plan 4, Task 8) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
