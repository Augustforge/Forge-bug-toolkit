# -*- coding: utf-8 -*-
"""composition_map — trust-boundary composition graph producer (FDE План 6, Task 2, §43.1/§50/§51).

Главный un-dup-генератор плана (web-инстанс cross-thread synthesis): строит граф `граница A --доверяет-->
граница B` из инвариантов `system_model.md` (`Источник` -> `component:` на каждой I-NN/TB-NN/AC-NN
строке -- выход одной границы становится входом другой). Для КАЖДОГО ребра поле "кто валидирует на
стыке?" -- Статус этой же строки. Ребро без подтверждённого валидатора (Статус != ENFORCED), чей I-NN
ЕЩЁ НЕ материализован в `## Divergences`, выходит кандидатом `D-NN` с `undup_origin: composition-seam`.
Артефакт `composition_map.md` пишется toolkit-rooted co-located (`{session_dir}/composition_map.md`) --
его читает gate-детектор `active_composition_pass_skipped` (`hunt_completeness_gate.py`, Task 2).

Парс-контракт: 12-колоночный формат `system_model_web_template.md`/`system_model_template.md` (`## Invariants`):
    ID | Формула | check: | Ось | Источник | component: | pred: | Статус | endpoint/file:line | tests | crowd-heat | lib
переиспользован ПО ФОРМАТУ из `hunt_completeness_gate.py::_i_rows`/`_cells` (table-строки `| TB-I01 | ... |`
И буллет-форма `- **TB-I01** [class] ... component: ... status: ...`, P10-katana lesson) -- реализован
здесь ЛОКАЛЬНО (self-contained regex-парсер, без импорта hook-скрипта -- тот же паттерн, что остальные
web2-producer'ы: authz_diff.py/openapi_to_acnn.py не грузят hunt_completeness_gate.py как модуль).

Публичный контракт:
    parse_model_rows(model_text) -> list[dict]              # 12-полевые dict-строки (table+bullet)
    parse_divergence_invariants(model_text) -> set[str]      # I-NN уже материализованные в `## Divergences`
    build_composition_graph(model_rows, dnn_invariants=None) -> list[dict]   # рёбра + candidate-флаг
    run_composition_map(model_rows, session_dir, dnn_invariants=None) -> str  # пишет .md, возвращает путь

CLI:
    py -3 -X utf8 composition_map.py --session-dir sessions/example.com
    py -3 -X utf8 composition_map.py --model path/to/system_model.md --session-dir sessions/example.com

Наблюдательный примитив: composition_map.py никогда не мутирует `system_model.md` -- только читает и
пишет отдельный co-located артефакт. Fail-open на CLI-уровне не применимо (детерминированный batch-
разбор локального файла, не live-наблюдение), но producer никогда не падает на ЧАСТИЧНО заполненной
модели -- недостающие поля просто дают пустое ребро (не эксепшн).
"""
import os
import re
import argparse


# ---------------------------------------------------------------------------
# Парсер I-NN/TB-NN/AC-NN строк (12-колоночный контракт, table + bullet форма)
# ---------------------------------------------------------------------------

_INV_ID = r"(?:[A-Za-z][A-Za-z0-9]{0,3}-)?I-?\d+"
_ROW_RE = re.compile(r"^\s*\|\s*" + _INV_ID + r"\s*\|", re.I)
_BULLET_RE = re.compile(r"^\s*[-*]\s*\*\*\s*" + _INV_ID + r"\s*\*\*", re.I)
_D_ROW_RE = re.compile(r"^\s*\|\s*D-\d+\s*\|", re.I)

_B_ID_RE = re.compile(_INV_ID, re.I)
_B_CHECK_RE = re.compile(
    r"check:\s*(.+?)(?:\s+component:|\s+pred:|\s+status:|\s+enforcement:|$)", re.I | re.S)
_B_COMPONENT_RE = re.compile(
    r"component:\s*([^\s,][^\n]*?)(?:\s+pred:|\s+status:|\s+enforcement:|$)", re.I)
_B_SOURCE_RE = re.compile(
    r"(?:источник|source):\s*([^\s,][^\n]*?)(?:\s+component:|\s+pred:|\s+status:|$)", re.I)
_B_PRED_RE = re.compile(r"pred:\s*([A-Za-z][A-Za-z-]*)", re.I)
_B_STATUS_RE = re.compile(
    r"(?:(?:status|enforcement)\s*[:=]\s*|→\s*)"
    r"(ENFORCED-PARTIAL|SUBSTITUTED|ENFORCED|IMPLICIT|ABSENT)\b", re.I)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _bullet_to_cells(line):
    """`- **TB-I01** [class] ... check: ... component: ... pred: ... status: ...` -> 12-cell вид
    (пусто там, где буллет не несёт поле -- тот же best-effort контракт, что
    hunt_completeness_gate.py::_bullet_to_cells)."""
    c = [""] * 12
    mid = _B_ID_RE.search(line)
    c[0] = mid.group(0).upper() if mid else ""
    c[1] = line.strip()[:80]
    mc = _B_CHECK_RE.search(line)
    if mc:
        c[2] = mc.group(1).strip()
    msrc = _B_SOURCE_RE.search(line)
    if msrc:
        c[4] = msrc.group(1).strip()
    mcomp = _B_COMPONENT_RE.search(line)
    if mcomp:
        c[5] = mcomp.group(1).strip()
    mp = _B_PRED_RE.search(line)
    if mp:
        c[6] = mp.group(1).upper()
    ms = _B_STATUS_RE.search(line)
    if ms:
        c[7] = ms.group(1).upper()
    return c


def parse_model_rows(model_text):
    """`## Invariants` I-NN/TB-NN/AC-NN строки (table `| TB-I01 | ... |` И буллет `- **TB-I01** ...`)
    -> список 12-полевых dict'ов: id/formula/check/axis/source/component/pred/status/loc/tests/
    crowd_heat/lib. Строки вне обоих форматов игнорируются."""
    rows = []
    for line in (model_text or "").splitlines():
        if _ROW_RE.match(line):
            c = _cells(line)
        elif _BULLET_RE.match(line):
            c = _bullet_to_cells(line)
        else:
            continue
        c = (c + [""] * 12)[:12]
        rows.append({
            "id": c[0], "formula": c[1], "check": c[2], "axis": c[3],
            "source": c[4], "component": c[5], "pred": c[6], "status": c[7],
            "loc": c[8], "tests": c[9], "crowd_heat": c[10], "lib": c[11],
        })
    return rows


def parse_divergence_invariants(model_text):
    """Множество `I-NN` из колонки "Нарушенный I-NN" уже материализованных строк `## Divergences`
    (anti-dup falsifier: composition_map НЕ дублирует уже занесённые в модель дивергенции)."""
    out = set()
    txt = model_text or ""
    i = txt.find("## Divergences")
    if i < 0:
        return out
    j = txt.find("\n## ", i + 1)
    block = txt[i:j if j > 0 else len(txt)]
    for line in block.splitlines():
        if _D_ROW_RE.match(line):
            c = _cells(line)
            if len(c) > 1:
                inv = c[1].strip().upper()
                if inv and "{" not in inv:
                    out.add(inv)
    return out


# ---------------------------------------------------------------------------
# Граф: source -> component, "кто валидирует на стыке?"
# ---------------------------------------------------------------------------

_PLACEHOLDER_VALUES = {"", "-", "—", "n/a", "na"}


def _is_real(v):
    v = (v or "").strip()
    if not v or "{" in v:
        return False
    return v.lower() not in _PLACEHOLDER_VALUES


def build_composition_graph(model_rows, dnn_invariants=None):
    """Для каждой I-NN строки с непустыми `Источник`+`component:` строит ребро `source -> component`
    (выход границы-источника = вход границы-компонента, §43.1). "Кто валидирует на стыке?" = Статус
    ЭТОЙ ЖЕ строки: `validated` только при `ENFORCED` (единственный из 5 статусов template, означающий
    "явная проверка на ВСЕХ путях" -- остальные 4 уже собственный D-NN-класс модели). Ребро без
    валидатора становится `candidate` (composition-seam), ТОЛЬКО если его `I-NN` ещё НЕ материализован
    в `## Divergences` (anti-scope: не плодить дубли уже занесённых дивергенций). Строки без
    source/component (нет графового ребра) молча пропускаются -- НЕ candidate (нечего валидировать)."""
    dnn_invariants = dnn_invariants or set()
    edges = []
    for r in model_rows or []:
        src = r.get("source", "")
        comp = r.get("component", "")
        if not _is_real(src) or not _is_real(comp):
            continue
        status = (r.get("status") or "").replace("*", "").replace("`", "").strip().upper()
        validated = status == "ENFORCED"
        inv_id = (r.get("id") or "").strip().upper()
        already_dnn = bool(inv_id) and inv_id in dnn_invariants
        candidate = (not validated) and (not already_dnn)
        edges.append({
            "id": r.get("id", ""),
            "source": src.strip(),
            "component": comp.strip(),
            "axis": r.get("axis", ""),
            "check": r.get("check", ""),
            "status": status or "(empty)",
            "validated": validated,
            "already_dnn": already_dnn,
            "candidate": candidate,
        })
    return edges


# ---------------------------------------------------------------------------
# A7 (Волна 1 2026-08-08): transitive closure -- longest UNVALIDATED chain
# ---------------------------------------------------------------------------
# Одиночное ребро без валидатора = composition-seam (выше). Транзитивное замыкание по НЕвалидированным
# рёбрам даёт ЦЕПОЧКУ A->B->C->D->E, где НИ ОДНО звено не валидирует доверие = длинная неохраняемая
# цепь = буквально depth-ceiling («человек слепнет на 4-5 уровнях, крит живёт ниже»). Граф САМ
# показывает самую длинную/ценную неохраняемую цепь → туда копать. Ранг = число рёбер × число
# un-validated звеньев (в чистой цепи они равны) × value-at-end (терминальная граница).

def longest_unvalidated_chains(edges, min_edges=3):
    """Транзитивное замыкание по candidate-рёбрам (unvalidated И не-already-D-NN). Возвращает
    МАКСИМАЛЬНЫЕ цепи из ≥`min_edges` рёбер (список dict: nodes/edges/ids/rank/value_at_end),
    отсортированные по rank убыв. Валидированное ребро в середине РВЁТ цепь (его нет в candidate-графе).
    Циклы обрезаются (visited-guard). Пустой граф / нет длинных цепей → []."""
    adj = {}
    indeg = {}
    for e in edges or []:
        if not e.get("candidate"):
            continue                                     # только неохраняемые рёбра
        adj.setdefault(e["source"], []).append(e)
        indeg[e["component"]] = indeg.get(e["component"], 0) + 1
        indeg.setdefault(e["source"], indeg.get(e["source"], 0))
    if not adj:
        return []
    # корни candidate-графа (in-degree 0) → из них растут МАКСИМАЛЬНЫЕ цепи; если все узлы в цикле —
    # fallback на все узлы (visited-guard всё равно оборвёт).
    roots = [n for n in adj if indeg.get(n, 0) == 0] or list(adj.keys())
    chains = []

    def dfs(node, path, visited):
        extended = False
        for e in adj.get(node, []):
            nxt = e["component"]
            if nxt in visited:
                continue                                 # cycle-guard
            extended = True
            dfs(nxt, path + [e], visited | {nxt})
        if not extended and len(path) >= min_edges:      # терминал ветви → максимальная цепь
            nodes = [path[0]["source"]] + [e["component"] for e in path]
            chains.append({
                "nodes": nodes,
                "ids": [e["id"] for e in path],
                "edges": len(path),
                "unvalidated": len(path),                # в candidate-цепи все звенья неохраняемы
                "value_at_end": nodes[-1],
                "rank": len(path) * len(path),           # длина × un-validated (value-at-end = tie-break)
            })

    for r in roots:
        dfs(r, [], {r})
    chains.sort(key=lambda c: c["rank"], reverse=True)
    return chains


# ---------------------------------------------------------------------------
# Writer -- composition_map.md (toolkit-rooted co-located)
# ---------------------------------------------------------------------------

def run_composition_map(model_rows, session_dir, dnn_invariants=None):
    """Строит composition-граф из `model_rows` (см. `parse_model_rows`) и пишет
    `{session_dir}/composition_map.md` (`session_dir` -- toolkit-rooted ПАРАМЕТР, НЕ хардкод голого
    `sessions/$DOMAIN` -- иначе `active_composition_pass_skipped`, ищущий файл в `dirname(ledger)`,
    промахнётся, тот же co-located контракт, что `run_authz_matrix`/`write_scoremap`). Пустой прогон
    (0 рёбер/0 кандидатов) ВСЁ РАВНО пишет файл с `RESULT: ...` -- гейт держит на отсутствии/пустоте
    файла, а не на нуле кандидатов. Возвращает путь записанного файла."""
    session_dir = str(session_dir)
    os.makedirs(session_dir, exist_ok=True)
    out_path = os.path.join(session_dir, "composition_map.md")

    edges = build_composition_graph(model_rows, dnn_invariants=dnn_invariants)
    candidates = [e for e in edges if e["candidate"]]
    already_count = sum(1 for e in edges if e["already_dnn"])

    lines = [
        "# composition_map.md -- trust-boundary composition graph (§43.1 composition-seam generator)",
        "",
        "| Ребро (граница A -> граница B) | I-NN | Ось | Валидатор? (Статус) | undup_origin |",
        "|---|---|---|---|---|",
    ]
    for e in edges:
        edge_label = "%s -> %s" % (e["source"], e["component"])
        val_cell = ("yes (%s)" % e["status"]) if e["validated"] else ("no (%s)" % e["status"])
        if e["candidate"]:
            origin = "composition-seam"
        elif e["already_dnn"]:
            origin = "already-D-NN"
        else:
            origin = "-"
        lines.append("| %s | %s | %s | %s | %s |" % (
            edge_label, e["id"] or "?", e["axis"] or "-", val_cell, origin))

    if candidates:
        lines.append("")
        lines.append("## Composition-Seam Candidates (D-NN)")
        lines.append("| Candidate | Нарушенный I-NN | Ребро | undup_origin | check: |")
        lines.append("|---|---|---|---|---|")
        for n, e in enumerate(candidates, 1):
            lines.append("| CAND-%02d | %s | %s -> %s | composition-seam | %s |" % (
                n, e["id"] or "?", e["source"], e["component"], e["check"] or "-"))

    # A7: транзитивные цепи неохраняемого доверия (depth-ceiling механизирован)
    chains = longest_unvalidated_chains(edges)
    if chains:
        lines.append("")
        lines.append("## Longest Unvalidated Chains (A7 transitive — depth-ceiling)")
        lines.append("| Chain-D-NN | Цепь (границы) | Звеньев | I-NN | value-at-end | rank |")
        lines.append("|---|---|---|---|---|---|")
        for n, c in enumerate(chains, 1):
            lines.append("| CHAIN-%02d | %s | %d | %s | %s | %d |" % (
                n, " -> ".join(c["nodes"]), c["edges"],
                ", ".join(i for i in c["ids"] if i) or "?", c["value_at_end"], c["rank"]))

    lines.append("")
    lines.append(
        "RESULT: composition-map-run, %d edges, %d un-validated candidates (%d already-materialized skipped)"
        % (len(edges), len(candidates), already_count)
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="composition_map -- trust-boundary graph from system_model.md (FDE Plan 6, §43.1)")
    ap.add_argument("--model", help="path to system_model.md (default: <session-dir>/system_model.md)")
    ap.add_argument("--session-dir", required=True,
                     help="toolkit-rooted session dir, e.g. sessions/example.com")
    args = ap.parse_args(argv)

    model_path = args.model or os.path.join(args.session_dir, "system_model.md")
    with open(model_path, "r", encoding="utf-8") as f:
        model_text = f.read()

    model_rows = parse_model_rows(model_text)
    dnn_invariants = parse_divergence_invariants(model_text)
    out_path = run_composition_map(model_rows, args.session_dir, dnn_invariants=dnn_invariants)
    print("wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
