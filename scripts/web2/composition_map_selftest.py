# -*- coding: utf-8 -*-
"""Selftest for composition_map.py (FDE Plan 6, Task 2).

Proves:
 (1) parse_model_rows: table-form `| TB-I01 | ... |` rows parsed into 12-field dicts with correct
     source(idx4)/component(idx5) extraction.
 (2) parse_model_rows: bullet-form `- **AC-I02** ... source: ... component: ... status: ...` rows
     parsed the same way (P10-katana parity with hunt_completeness_gate.py::_i_rows).
 (3) parse_divergence_invariants: `## Divergences` table rows -> set of already-materialized I-NN ids.
 (4) build_composition_graph: edge WITH validator (Статус==ENFORCED) is NOT flagged candidate.
 (5) build_composition_graph: edge WITHOUT validator (ABSENT/IMPLICIT/ENFORCED-PARTIAL/SUBSTITUTED/empty)
     IS flagged candidate with undup_origin composition-seam -- UNLESS its I-NN already appears in
     `## Divergences` (anti-dup falsifier), in which case candidate=False, already_dnn=True.
 (6) build_composition_graph: row missing source OR component builds NO edge at all (not even a
     non-candidate one).
 (7) run_composition_map: writes to EXACTLY {session_dir}/composition_map.md (co-located, toolkit-
     rooted, never CWD-relative bare sessions/); RESULT line always present, even 0-edge run.

Run: py -3 -X utf8 bug-bounty-toolkit/scripts/web2/composition_map_selftest.py
"""
import os
import sys
import shutil
import tempfile
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
WEB2_DIR = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "web2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


cm = _load("composition_map", os.path.join(WEB2_DIR, "composition_map.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


# ── CASE 1: parse_model_rows — table form ───────────────────────────────────────────────────
TABLE_MODEL = (
    "## Invariants\n"
    "| ID | Формула | check: | Ось | Источник | component: | pred: | Статус | file:line | tests | crowd-heat | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| TB-I01 | f1 | c1 | origin-trust | CSP | msgRouter | ENFORCED | ENFORCED | a.js:1 | 0 | cold | |\n"
    "| TB-I02 | f2 | c2 | data-source-trust | msgRouter | priceOracle | ABSENT | ABSENT | b.js:5 | 0 | cold | |\n"
    "| TB-I03 | f3 | c3 | asset-identity | priceOracle | vaultCore | | | c.js:9 | 0 | cold | |\n"
)
rows = cm.parse_model_rows(TABLE_MODEL)
check("case1a parse_model_rows(table): 3 rows extracted", len(rows) == 3, "got=%r" % (rows,))
check("case1b parse_model_rows(table): row 0 id == TB-I01", rows[0]["id"] == "TB-I01", "got=%r" % (rows[0],))
check("case1c parse_model_rows(table): row 0 source == CSP (idx4)", rows[0]["source"] == "CSP", "got=%r" % (rows[0],))
check("case1d parse_model_rows(table): row 0 component == msgRouter (idx5)",
      rows[0]["component"] == "msgRouter", "got=%r" % (rows[0],))
check("case1e parse_model_rows(table): row 1 status == ABSENT", rows[1]["status"] == "ABSENT", "got=%r" % (rows[1],))
check("case1f parse_model_rows(table): row 2 source==priceOracle chains from row 1 component",
      rows[2]["source"] == "priceOracle" and rows[1]["component"] == "priceOracle")

# ── CASE 2: parse_model_rows — bullet form ──────────────────────────────────────────────────
BULLET_MODEL = (
    "## Invariants\n"
    "- **AC-I05** [state] ownership check: authz-mw on every method source: JWT component: ordersAPI "
    "pred: ENFORCED status: ENFORCED\n"
    "- **AC-I06** [state] tenant isolation check: workspace scoping source: ordersAPI component: billingDB "
    "pred: ENFORCED status: SUBSTITUTED\n"
)
brows = cm.parse_model_rows(BULLET_MODEL)
check("case2a parse_model_rows(bullet): 2 rows extracted", len(brows) == 2, "got=%r" % (brows,))
check("case2b parse_model_rows(bullet): row 0 id == AC-I05", brows[0]["id"] == "AC-I05", "got=%r" % (brows[0],))
check("case2c parse_model_rows(bullet): row 0 source == JWT", brows[0]["source"] == "JWT", "got=%r" % (brows[0],))
check("case2d parse_model_rows(bullet): row 0 component == ordersAPI",
      brows[0]["component"] == "ordersAPI", "got=%r" % (brows[0],))
check("case2e parse_model_rows(bullet): row 1 status == SUBSTITUTED",
      brows[1]["status"] == "SUBSTITUTED", "got=%r" % (brows[1],))
check("case2f parse_model_rows(bullet): row 1 source==ordersAPI chains from row 0 component (cross-boundary)",
      brows[1]["source"] == "ordersAPI" and brows[0]["component"] == "ordersAPI")

# ── CASE 3: parse_divergence_invariants ─────────────────────────────────────────────────────
DIV_MODEL = (
    "## Divergences\n"
    "| ID | Нарушенный I-NN | Где | Статус | value | paths | crowd-cold | conv | crowd-heat | Ранг | Резолюция |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| D-01 | TB-I02 | b.js:5 | ABSENT | high | 3 | yes | 2 | cold | 9 | -> H-04 |\n"
)
dnn_set = cm.parse_divergence_invariants(DIV_MODEL)
check("case3a parse_divergence_invariants: TB-I02 already materialized", "TB-I02" in dnn_set, "got=%r" % (dnn_set,))
check("case3b parse_divergence_invariants: no section -> empty set",
      cm.parse_divergence_invariants("no divergences here") == set())

# ── CASE 4: build_composition_graph — validated edge NOT a candidate ───────────────────────
edges = cm.build_composition_graph(rows, dnn_invariants=set())
e_tb01 = next(e for e in edges if e["id"] == "TB-I01")
check("case4a build_composition_graph: TB-I01 (Статус=ENFORCED) validated=True",
      e_tb01["validated"] is True, "got=%r" % (e_tb01,))
check("case4b build_composition_graph: TB-I01 (validator present) NOT flagged candidate (anti-slop falsifier)",
      e_tb01["candidate"] is False, "got=%r" % (e_tb01,))
check("case4c build_composition_graph: TB-I01 edge label CSP -> msgRouter",
      e_tb01["source"] == "CSP" and e_tb01["component"] == "msgRouter")

# ── CASE 5: build_composition_graph — un-validated edge IS a candidate, unless already-D-NN ─
e_tb02 = next(e for e in edges if e["id"] == "TB-I02")
check("case5a build_composition_graph: TB-I02 (Статус=ABSENT) validated=False",
      e_tb02["validated"] is False, "got=%r" % (e_tb02,))
check("case5b build_composition_graph: TB-I02 (no validator, not yet in Divergences) -> candidate=True",
      e_tb02["candidate"] is True, "got=%r" % (e_tb02,))

edges_dedup = cm.build_composition_graph(rows, dnn_invariants={"TB-I02"})
e_tb02_dedup = next(e for e in edges_dedup if e["id"] == "TB-I02")
check("case5c build_composition_graph: TB-I02 ALREADY in `## Divergences` -> candidate=False (anti-dup falsifier)",
      e_tb02_dedup["candidate"] is False and e_tb02_dedup["already_dnn"] is True,
      "got=%r" % (e_tb02_dedup,))

e_tb03 = next(e for e in edges if e["id"] == "TB-I03")
check("case5d build_composition_graph: TB-I03 (empty Статус) treated as un-validated -> candidate=True",
      e_tb03["validated"] is False and e_tb03["candidate"] is True, "got=%r" % (e_tb03,))

# ── CASE 6: rows missing source/component build NO edge ────────────────────────────────────
INCOMPLETE_MODEL = (
    "## Invariants\n"
    "| ID | Формула | check: | Ось | Источник | component: | pred: | Статус | file:line | tests | crowd-heat | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| AC-I09 | f9 | c9 | object-authz | | ordersAPI | ABSENT | ABSENT | z.py:1 | 0 | cold | |\n"
    "| AC-I10 | f10 | c10 | object-authz | JWT | | ABSENT | ABSENT | z.py:2 | 0 | cold | |\n"
    "| AC-I11 | f11 | c11 | object-authz | {TODO} | {TODO} | | | z.py:3 | 0 | cold | |\n"
)
incomplete_rows = cm.parse_model_rows(INCOMPLETE_MODEL)
incomplete_edges = cm.build_composition_graph(incomplete_rows)
check("case6a build_composition_graph: 3 model rows, ALL missing source or component -> 0 edges",
      len(incomplete_edges) == 0, "got=%r" % (incomplete_edges,))

# ── CASE 7: run_composition_map — writes to EXACT session_dir, co-located, RESULT always present ──
TMP_SESSION_DIR = os.path.join(ROOT, "bug-bounty-toolkit", "sessions", "_selftest_tmp_web2_composition")
try:
    if os.path.exists(TMP_SESSION_DIR):
        shutil.rmtree(TMP_SESSION_DIR)

    written_path = cm.run_composition_map(rows, TMP_SESSION_DIR, dnn_invariants=set())
    expected_path = os.path.join(TMP_SESSION_DIR, "composition_map.md")
    check("case7a run_composition_map: returns exactly os.path.join(session_dir, 'composition_map.md')",
          written_path == expected_path, "got=%r expected=%r" % (written_path, expected_path))
    check("case7b run_composition_map: file physically exists at that exact path",
          os.path.isfile(expected_path), "path=%r" % (expected_path,))
    check("case7c run_composition_map: nothing written under bare CWD-relative sessions/ (toolkit-rooted only)",
          not os.path.exists(os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_composition")))

    with open(expected_path, "r", encoding="utf-8") as f:
        content = f.read()
    check("case7d run_composition_map: RESULT line present", "RESULT: composition-map-run" in content,
          "content=%r" % (content,))
    check("case7e run_composition_map: TB-I01 edge (validated) marked '-' or 'already-D-NN', never composition-seam",
          not any(ln for ln in content.splitlines() if "TB-I01" in ln and "composition-seam" in ln),
          "content=%r" % (content,))
    check("case7f run_composition_map: TB-I02 un-validated edge surfaces as composition-seam candidate",
          any("composition-seam" in ln and "TB-I02" in ln for ln in content.splitlines()),
          "content=%r" % (content,))
    check("case7g run_composition_map: Composition-Seam Candidates section present (non-empty candidate list)",
          "## Composition-Seam Candidates" in content, "content=%r" % (content,))

    # 0-edge run still writes a RESULT line (gate checks existence/non-empty, not candidate count)
    empty_path = cm.run_composition_map([], TMP_SESSION_DIR, dnn_invariants=set())
    with open(empty_path, "r", encoding="utf-8") as f:
        empty_content = f.read()
    check("case7h run_composition_map([]): 0-edge run still writes non-empty RESULT line",
          "RESULT: composition-map-run, 0 edges" in empty_content, "content=%r" % (empty_content,))
    # ── A7 (Волна 1): transitive closure — longest UNVALIDATED chain ──
    # Цепь A->B->C->D->E, все звенья без валидатора (ABSENT) → chain-D-NN длиной ≥3. Откат замыкания роняет.
    def _edge(iid, src, comp, status):
        return {"id": iid, "source": src, "component": comp, "axis": "trust",
                "check": "", "status": status, "validated": status == "ENFORCED",
                "already_dnn": False, "candidate": status != "ENFORCED"}
    CHAIN5 = [_edge("I-01", "A", "B", "ABSENT"), _edge("I-02", "B", "C", "ABSENT"),
              _edge("I-03", "C", "D", "IMPLICIT"), _edge("I-04", "D", "E", "ABSENT")]
    chains = cm.longest_unvalidated_chains(CHAIN5)
    check("case A7a transitive: 5-node all-unvalidated → 1 chain length>=3",
          bool(chains) and chains[0]["edges"] >= 3 and chains[0]["nodes"] == ["A", "B", "C", "D", "E"],
          "got=%r" % (chains,))
    # валидатор в СЕРЕДИНЕ (C->D ENFORCED) → цепь рвётся, нет цепи ≥3 рёбер.
    CHAIN_BROKEN = [_edge("I-01", "A", "B", "ABSENT"), _edge("I-02", "B", "C", "ABSENT"),
                    _edge("I-03", "C", "D", "ENFORCED"), _edge("I-04", "D", "E", "ABSENT")]
    broken = cm.longest_unvalidated_chains(CHAIN_BROKEN)
    check("case A7b transitive: validator mid-chain → NO chain>=3 (рвётся на валидаторе)",
          not any(c["edges"] >= 3 for c in broken), "got=%r" % (broken,))
    # producer'ит секцию в composition_map.md
    a7_path = cm.run_composition_map(
        [{"id": "I-%02d" % (i + 1), "source": s, "component": c, "axis": "trust",
          "check": "", "status": "ABSENT"} for i, (s, c) in
         enumerate([("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")])],
        TMP_SESSION_DIR, dnn_invariants=set())
    with open(a7_path, "r", encoding="utf-8") as f:
        a7_content = f.read()
    check("case A7c run_composition_map: Longest Unvalidated Chains section emitted",
          "## Longest Unvalidated Chains" in a7_content and "CHAIN-01" in a7_content,
          "content=%r" % (a7_content,))
finally:
    shutil.rmtree(TMP_SESSION_DIR, ignore_errors=True)
    stray = os.path.join(os.getcwd(), "sessions", "_selftest_tmp_web2_composition")
    if os.path.exists(stray):
        shutil.rmtree(stray, ignore_errors=True)

print("=== COMPOSITION_MAP SELFTEST (FDE Plan 6, Task 2) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d зелёные" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
