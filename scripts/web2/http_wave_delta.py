# -*- coding: utf-8 -*-
"""http_wave_delta.py — behavioral wave-delta для ЖИВОГО web-таргета (recon-skills cross-wave-delta port, 2026-08-14).

Наш `scripts/wave_delta.py` диффит ИСХОДНЫЙ КОД (fingerprint функций/guard'ов репо) — для deephunt.
Этот модуль — параллель для web2/dapphunt: диффит НАБЛЮДАЕМОЕ ПОВЕДЕНИЕ живого таргета (HTTP-статусы /
CORS / sensitive-заголовки / доступность путей) между recon-ВОЛНАМИ. Оба несут категорию REVERSED, но
на разных уровнях: код (guard пропал в src) vs live (защита откачена на боевом хосте).

Категории (recon-skills):
  NEW         — endpoint/поле появилось (не было в прошлой волне) → свежая surface.
  REGRESSION  — было слабо, стало защищено (200→403 / cors-reflect→no-headers) → копай РЯДОМ (там боялись).
  PERSISTENT  — не менялось → уже покрыто, skip.
  CHANGE      — изменилось, но не в оси weak↔safe (напр. кол-во WP-юзеров) → мониторь.
  REVERSED    — защита была ПРИМЕНЕНА и потом ОТКАЧЕНА (safe→weak ПОСЛЕ бывшего weak→safe) = **P0**:
                security-team либо не знает, либо не следит → ненадёжная защита = high-priority target.

Read-only: НЕ делает live I/O сам — принимает УЖЕ снятые наблюдения (как secret_patterns.capture_exposure).
Live-капча волн — за вызывающим (под opsec_preflight fail-closed), сюда передаются снимки.

API:
    observe(target, **fields) -> dict                 # нормализованное наблюдение одного endpoint
    weak_of(field, value) -> bool|None                # слабое ли значение (None = нет семантики поля)
    wave_delta(series) -> dict                        # series = хронологич. список снимков → per-key категория
    format_delta(delta) -> str                        # печать с приоритетами (P0 REVERSED → P1 NEW → …)
"""


# ── weak↔safe семантика известных recon-полей (weak = слабее/эксплуатабельнее) ──────────
def _weak_status(v):
    """HTTP-статус пути: 200 (доступен) = weak; 401/403/404/405 (закрыт) = safe."""
    try:
        s = int(v)
    except (TypeError, ValueError):
        return None
    if s == 200:
        return True
    if s in (401, 403, 404, 405, 451):
        return False
    return None


def _weak_cors(v):
    """CORS: 'reflect'/'*'/'null'/wildcard = weak; 'none'/'' = safe."""
    s = str(v).strip().lower()
    if s in ("reflect", "reflected", "*", "null", "wildcard", "any"):
        return True
    if s in ("none", "", "same-origin", "strict"):
        return False
    return None


def _weak_bool_exposed(v):
    """Булев 'exposed/open' флаг: True/'open'/'exposed'/'enabled' = weak."""
    s = str(v).strip().lower()
    if s in ("true", "open", "exposed", "enabled", "yes", "1", "on"):
        return True
    if s in ("false", "closed", "hardened", "disabled", "no", "0", "off"):
        return False
    return None


# field-имя (или суффикс) → weak-детектор. Порядок: точное имя → суффикс-эвристика.
_WEAK_RULES = {
    "status": _weak_status,
    "http_status": _weak_status,
    "path_status": _weak_status,
    "xmlrpc": _weak_status,           # 200=open→weak, 405=hardened→safe
    "cors": _weak_cors,
    "cors_acao": _weak_cors,
    "acao": _weak_cors,
    "exposed": _weak_bool_exposed,
    "open": _weak_bool_exposed,
    "auth_required": lambda v: _neg(_weak_bool_exposed(v)),   # auth_required=True → safe (инвертируем)
}


def _neg(x):
    return None if x is None else (not x)


def weak_of(field, value):
    """Слабое ли значение поля. Известное recon-поле → bool; неизвестное → None (нет weak↔safe оси,
    delta ограничится NEW/CHANGE/PERSISTENT). Суффикс-эвристика: `*_status`→статус, `*_cors`→cors."""
    f = str(field).lower()
    if f in _WEAK_RULES:
        return _WEAK_RULES[f](value)
    if f.endswith("_status") or f.endswith("status"):
        return _weak_status(value)
    if f.endswith("cors") or f.endswith("acao"):
        return _weak_cors(value)
    if f.endswith("exposed") or f.endswith("open"):
        return _weak_bool_exposed(value)
    return None


def observe(target, **fields):
    """Нормализованное наблюдение одного endpoint/таргета: {'target': ..., **fields}. Волна = список таких."""
    d = {"target": target}
    d.update(fields)
    return d


def _key(obs):
    return str(obs.get("target"))


def _classify_series(field, values):
    """Категория поля из ХРОНОЛОГИЧЕСКОГО списка его значений [v0..vn] (≥1). weak↔safe семантика
    (weak_of) даёт REGRESSION/REVERSED; без неё — NEW/CHANGE/PERSISTENT."""
    if len(values) == 1:
        return "NEW"
    if all(v == values[0] for v in values):
        return "PERSISTENT"

    # есть изменения. Смотрим weak-траекторию, если поле семантическое.
    weak_traj = [weak_of(field, v) for v in values]
    if any(w is not None for w in weak_traj):
        # переходы safe→weak (защита снята) и weak→safe (защита добавлена)
        had_hardening = False   # был weak→safe где-то в прошлом
        for i in range(1, len(weak_traj)):
            prev, cur = weak_traj[i - 1], weak_traj[i]
            if prev is False and cur is True:      # safe→weak = защита откачена
                if had_hardening:
                    return "REVERSED"              # откат ПОСЛЕ бывшего усиления = P0
            if prev is True and cur is False:      # weak→safe = усиление
                had_hardening = True
        # нет реверса, но последнее изменение определяет:
        last_prev, last_cur = weak_traj[-2], weak_traj[-1]
        if last_prev is True and last_cur is False:
            return "REGRESSION"                    # стало защищено → копай рядом
        if last_prev is False and last_cur is True:
            return "REVERSED" if had_hardening else "NEW"   # защита снята (без прошлого усиления = свежее ослабление≈NEW-surface)
    return "CHANGE"


_PRIORITY = {"REVERSED": "P0", "NEW": "P1", "REGRESSION": "P2", "CHANGE": "P3", "PERSISTENT": "skip"}


def wave_delta(series):
    """series = ХРОНОЛОГИЧЕСКИЙ список волн, каждая = список наблюдений (observe(...)). Возвращает
    {category: [ {target, field, values, priority} ]} по всем target×field. target/field, появившийся
    не в первой волне, корректно => NEW (его values начинаются позже)."""
    # собрать историю значений per (target, field)
    hist = {}          # (target, field) -> list[value] по волнам, где поле присутствовало
    seen_first = {}    # (target, field) -> индекс волны первого появления
    n_waves = len(series)
    for wi, wave in enumerate(series or []):
        for obs in wave or []:
            if not isinstance(obs, dict):
                continue
            k = _key(obs)
            for field, value in obs.items():
                if field == "target":
                    continue
                kf = (k, field)
                hist.setdefault(kf, []).append(value)
                seen_first.setdefault(kf, wi)

    out = {"NEW": [], "REGRESSION": [], "PERSISTENT": [], "CHANGE": [], "REVERSED": []}
    for (target, field), values in hist.items():
        # появился позже первой волны И присутствует только в поздних → NEW (свежая surface)
        if seen_first[(target, field)] > 0 and len(values) < n_waves:
            cat = "NEW"
        else:
            cat = _classify_series(field, values)
        out[cat].append({"target": target, "field": field, "values": values,
                         "priority": _PRIORITY[cat]})
    return out


def format_delta(delta):
    """Печать по приоритету (P0 REVERSED → P1 NEW → P2 REGRESSION → P3 CHANGE → skip PERSISTENT)."""
    lines = []
    order = [("REVERSED", "P0 — защита откачена (ненадёжная security-team)"),
             ("NEW", "P1 — свежая surface"),
             ("REGRESSION", "P2 — стало защищено → копай РЯДОМ"),
             ("CHANGE", "P3 — изменилось (мониторь)"),
             ("PERSISTENT", "skip — не менялось")]
    for cat, label in order:
        items = delta.get(cat) or []
        if not items:
            continue
        lines.append("[%s] %s — %d" % (_PRIORITY[cat], label, len(items)))
        if cat != "PERSISTENT":
            for it in items:
                lines.append("   %s.%s: %s" % (it["target"], it["field"], " → ".join(map(str, it["values"]))))
    lines.append("\n→ H-NN: REVERSED и NEW в Active с ВЫСШИМ приоритетом; REGRESSION → рядом; PERSISTENT → skip.")
    return "\n".join(lines)
