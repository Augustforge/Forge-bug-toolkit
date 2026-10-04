#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent/Task/Workflow) — MODEL-FIRST (T10) scout-guard.

Назначение: закрыть промах (decentraland-next-session 2026-07-28) — инстанс входит в хант и
СРАЗУ гонит Scout Fan-Out (Agent-субагенты) в ШИРИНУ, пропустив T10 (independent model first).
Все model-гейты живут в Stop-гейте (`hunt_completeness_gate.py`) — они стреляют в КОНЦЕ turn'а,
когда breadth уже отработал «туда, куда идёт толпа», и модель можно дорисовать задним числом.
На ГРАНИЦЕ Task/Agent (момент промискуитетного действия) не было НИЧЕГО. Это дыра «хук > проза»
на уровне системы: divergence-first порядок держался прозой, а не хуком.

Механика (МЯГКИЙ reminder, НЕ блок — выбор системы 2026-07-28):
  Форма enforcement по границе: жёсткий блок уместен, где выход РОВНО ОДИН (Stop-гейт). На границе
  Agent валидных исходов МНОГО (scout / research-корпус / cold-verifier сосуществуют, а T10 ТРЕБУЕТ
  читать корпус субагентом ДО модели) → гейтить нельзя, только советовать. Слой ранний-мягкий
  (здесь) + поздний-жёсткий (`active_model_incomplete` в Stop) = защита без ложных стопов.

Fire ⇔ (a) идёт хант В ЭТОЙ сессии (свой свежий `.hunt_active`, session-скоуп) И
        (b) модель ещё НЕ начата (нет `MODEL: BUILDING` / `MODEL: N/A` / реального счётчика I-NN в
            Loop State И нет реальных `| I-NN |` строк в system_model.md) И
        (c) не debounced (пачка из 5 параллельных Agent не выдаёт 5 копий).
Silence ⇔ MODEL: BUILDING (модель строится — scout правомерно отложен, OBS-2) / MODEL: N/A (T10
          неприменим) / модель уже построена. Все три — один Edit, дёшево снять.

Бьёт по ОБЕИМ причинам промаха одним сообщением: (1) порядок (модель ДО веера); (2) подмена модели —
их `specs/invariants.md` = корпус-ПРЕДМЕТ проверки, их теги `[E]/[D]/[C]` = `pred:`, не факт.

Task 7 (§40.1 tool-output-last, 2026-08-07): этот же guard — единственная точка enforcement для
«свой D-NN/модель ПЕРВЫМ, вывод сканеров/публичных skills/фаззеров ПОЗЖЕ, как cross-check, не как
затравка» (mythos Mandate 0.9 addendum). Scout Fan-Out (Agent-субагенты) — канал, которым сканеры
обычно и гоняются, так что «модель-до-веера» уже структурно кроет «модель-до-tool-output» на этом
канале; REMINDER/AXIS_REMINDER ниже теперь называют это явно, третьей причиной промаха. Честный
предел: прямой Bash-вызов сканера в ОСНОВНОМ потоке (не через субагента) этот хук не матчит —
matcher = `Agent|Task|Workflow|Edit|Write`, без Bash (`.claude/settings.json`); там порядок держит
только проза мандата, добавление Bash-ветки в этот таск не входило (не «дёшево»: новый matcher +
разрастающийся список имён сканер-скриптов через все скиллы — отдельное решение, не эта правка).

Fail-open: любая ошибка → exit 0 без вывода (никогда не ломаем выполнение).
"""
import sys
import os
import re
import json
import glob
import time


def _read_marker(marker_path):
    """(valid, sid). valid=False если пустой/битый маркер (0-байт от прерванной записи)."""
    try:
        with open(marker_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return (False, None)
    if not raw.strip():
        return (False, None)
    lines = raw.splitlines()
    sid = lines[1].strip() if len(lines) >= 2 and lines[1].strip() else None
    return (True, sid)


def _owned_markers(current_sid):
    """Свежие (<24ч) .hunt_active этой сессии — (mtime, path). Session-скоуп (единая логика с
    completeness-gate / ledger_first_nudge): битый/пустой → скип; знаем свой sid → владеем только
    своим; id не пришёл → fallback на legacy."""
    out = []
    try:
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        sessions = os.path.join(root, "sessions")
        now = time.time()
        for m in glob.glob(os.path.join(sessions, "*", ".hunt_active")):
            if now - os.path.getmtime(m) >= 24 * 3600:
                continue
            valid, sid = _read_marker(m)
            if not valid:
                continue
            if current_sid:
                if sid != current_sid:
                    continue
            elif sid is not None:
                continue
            out.append((os.path.getmtime(m), m))
    except Exception:
        return []
    return out


# Анти-FP (единая логика с completeness-gate `_MODEL_NA_RE`/`_MODEL_BUILDING_RE`): сентинел
# засчитывается ТОЛЬКО в строке без backtick'ов и без `{` — иначе его поймала бы ИНСТРУКЦИЯ о нём в
# шаблоне ledger'а (там он в backticks внутри `{...}`-плейсхолдера).
_MODEL_NA_RE = re.compile(r"MODEL[:*\s]*N/?A", re.I)
_MODEL_BUILDING_RE = re.compile(r"MODEL[:*\s]*BUILDING", re.I)
# Scout-Fan-Out Status `PENDING` — ТОЧНО как в completeness-gate `active_ledger_scout_pending`
# (status, затем только [:* \s`] и pending). `Status` СБРАСЫВАЕТСЯ в PENDING на КАЖДОЙ новой T9-оси/
# волне (протокол template: «🔄 на новой оси scout → PENDING») → этот сигнал ловит и первую волну, и
# каждую новую, тогда как «модель хоть раз построена» пропускал новые волны (модель ПРОШЛОЙ подсистемы).
_SCOUT_PENDING_RE = re.compile(r"status[:*\s]*`?\s*pending", re.I)


def _clean(txt):
    """Строки без backtick и без `{` (инструкция о сентинеле в шаблоне не считается фактом)."""
    return [ln for ln in txt.splitlines() if "`" not in ln and "{" not in ln]


def _has_clean(txt, rx):
    return any(rx.search(ln) for ln in _clean(txt))


# OBS-28-fix (granite 2026-08-04): сентинел статуса модели (`MODEL: BUILDING`/`N/A`) обязан читаться
# ТОЛЬКО из СТАТУС-строки (MODEL в начале строки), а не из ИСТОРИИ трейса («- 1 — recon …; MODEL:BUILDING
# → ожидаю…»). Строка трейса ложно глушила ВСЕ new-axis нуджи навсегда (append-only трейс не стирается).
_MODEL_STATUS_LINE_RE = re.compile(r"^\s*[-*>]*\s*\*{0,2}\s*MODEL\b", re.I)


def _model_sentinel(txt, rx):
    """rx (BUILDING/NA) в СТАТУС-строке модели, не в прозе/трейсе (backtick/`{` не в счёт — шаблон)."""
    for ln in (txt or "").splitlines():
        if "`" in ln or "{" in ln:
            continue
        if _MODEL_STATUS_LINE_RE.match(ln) and rx.search(ln):
            return True
    return False


def _should_nudge(marker):
    """True (fire) ⇔ scout-волна `PENDING` И модель НЕ строится/НЕ N/A. Зеркалит Stop-гейт
    `active_ledger_scout_pending` (+ model_na guard), но на ГРАНИЦЕ Agent, не на выходе. Per-wave:
    Status сбрасывается в PENDING на каждой оси → форсит НОВУЮ I-NN-волну, а не scout по старой модели.

      - MODEL: BUILDING (строю модель этой волны) → False (scout правомерно отложен, OBS-2);
      - MODEL: N/A (T10 неприменим) → False;
      - Scout Fan-Out Status == PENDING (первая волна ИЛИ сброшен на новой оси) → True;
      - Status DONE/N/A/DEFERRED (модель-волна отработана) → False.
    Fail-open в сторону тишины (нет ledger'а / ошибка чтения → False)."""
    ledger = os.path.join(os.path.dirname(marker), "hypotheses.md")
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return False
    if _model_sentinel(txt, _MODEL_BUILDING_RE):
        return False
    if _model_sentinel(txt, _MODEL_NA_RE):
        return False
    # FIX-1 (OBS-1, ethena-live 2026-08-12, judge-CONFIRMED): построенная модель (реальные I-NN в
    # system_model.md) УЖЕ satisfies model-first — generic REMINDER «модель НЕ начата» на scout-PENDING
    # тогда ЛОЖЕН (стрелял на HYBRID-веере при 12 готовых I-NN). Симметрия с depth-веткой `_model_built_or_na`
    # (:227) и hybrid-веткой `_manual_scout_without_hybrid`, которые модель честят — раньше только эта scout-
    # ветка была слепа (fix aca58ae применён асимметрично). Per-wave enforcement (новая ось без своей волны)
    # несёт `_new_axis_needs_wave`/`_scout_targets_unbuilt_wave` (main() раньше, :581), НЕ эта ветка.
    smd = os.path.join(os.path.dirname(marker), "system_model.md")
    if os.path.exists(smd):
        try:
            with open(smd, "r", encoding="utf-8") as f:
                if _model_has_real_invariant(f.read()):
                    return False
        except Exception:
            pass
    low = txt.lower()
    return "scout fan-out" in low and bool(_SCOUT_PENDING_RE.search(low))


def _debounced(marker, window=120, stampname=".last_model_nudge"):
    """True если уже тыкали в последние window сек (не спамим на пачке параллельных Agent/Edit)."""
    stamp = os.path.join(os.path.dirname(marker), stampname)
    now = time.time()
    try:
        if os.path.exists(stamp) and (now - os.path.getmtime(stamp)) < window:
            return True
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(str(int(now)))
    except Exception:
        return False
    return False


# --- OBS-23 (ondo 2026-07-29): mid-turn depth-guard для SOLO-режима ---------------------------------
# Дыра: без субагентов (solo) события Agent нет → scout-ветка выше слепа. Агент читает код и пишет
# Depth-Lead/`D-NN`, а I-NN в system_model.md НЕ построил (model_incomplete ловит это только на Stop —
# уже после code-first). Ловим САМ МОМЕНТ записи depth-lead/`D-NN` в Edit/Write при пустой модели.
# P1 (katana 2026-07-29): entry-хук СОЗДАЁТ system_model.md из шаблона со строкой-примером
# `| I-01 | | | state | … | cold | |` (все ячейки, кроме id/класса, ПУСТЫ). Старый `_I_ROW_RE`
# (`^\s*\|\s*I-\d`) матчил её → «модель построена» на ПУСТОМ шаблоне → solo depth-guard мёртв сразу
# после создания сессии. «Реально построена» = ≥1 I-NN с ЗАПОЛНЕННЫМИ `check:` И `pred:` (в pipe-
# таблице ИЛИ в буллете `- **I-NN** … check: … pred: …`, P10-формат). Шаблонная I-01 (пустой check) не в счёт.
# arbitrum 2026-08-04: инварианты волн namespaced (`TB-I1`/`W3-I1`) — распознаём и их, и `I-\d+`, иначе
# `_wave_sections_with_invariants` видит 0 инвариантов под `## WAVE-*` → new_axis false-fire на верной
# мультиволне (паритет с гейтовым `_I_ROW_RE`). `D-\d+` не ловится (после префикса нужен `I`).
_INV_ID = r"(?:[A-Za-z][A-Za-z0-9]{0,3}-)?I-?\d+"
_I_PIPE_RE = re.compile(r"^\s*\|\s*\**\s*" + _INV_ID + r"\s*\**\s*\|", re.I)  # \** = bold `**I-01**` (justlenddao 2026-08-18)
_I_BULLET_HDR_RE = re.compile(r"^\s*[-*]\s*\*\*\s*" + _INV_ID + r"\s*\*\*", re.I)
_B_CHECK_FILLED_RE = re.compile(r"check:\s*\S", re.I)
_B_PRED_FILLED_RE = re.compile(r"pred:\s*[A-Za-z]", re.I)


def _model_has_real_invariant(text):
    """≥1 РЕАЛЬНО заполненный I-NN — pipe-таблица ЛЮБОЙ ширины ИЛИ буллет (в т.ч. multi-line). Пустой
    шаблон → False. Fix (1inch long-run B, судья: detector-blind-spot false-fire): раньше pipe-ветка
    требовала РОВНО 7-колоночный контракт-формат (`len>6 and cells[2] and cells[6]`) → 5-колоночная модель-
    таблица `| id | invariant | pred | check | status |` (len=5) читалась как «не построена»; bullet-ветка
    требовала `check:`+`pred:` на ОДНОЙ физической строке-заголовке → pred/check на переносных строках не
    считались. Теперь: pipe = id-строка с непустым описанием (cells[1]) И ≥1 ещё непустой ячейкой
    (skeleton `| I-01 | | | state |` с пустым cells[1] отклоняется, как в gate `_model_invariant_ids`);
    bullet = заголовок `- **I-NN**` + скан БЛОКА континуаций (до след. bullet-заголовка/пустой/секции) на
    check+pred."""
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if _I_PIPE_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # id(idx0) + непустое описание(idx1) + ≥1 ещё непустая ячейка → заполненная строка (не skeleton)
            if len(cells) >= 3 and cells[1] and any(cells[2:]):
                return True
        elif _I_BULLET_HDR_RE.match(line):
            block = [line]                                  # заголовок + континуации до границы блока
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if not s or s.startswith("## ") or _I_BULLET_HDR_RE.match(nxt) or _I_PIPE_RE.match(nxt):
                    break                                   # граница: пустая / секция / след. инвариант
                block.append(nxt)
            blob = "\n".join(block)
            if _B_CHECK_FILLED_RE.search(blob) and _B_PRED_FILLED_RE.search(blob):
                return True
    return False


# enzymefinance 2026-08-19 (the operator, долгая сессия): хантер перестал строить I-NN в system_model.md ПЕРЕД
# веером — формулировал их ПРЯМО В args веера (I-48..I-64). Нарушение model-first (T10): инвариант строится
# в МОДЕЛИ первым (WAVE-N, check/component/pred), ПОТОМ веер проверяет enforcement на нём. Ловим на запуске
# Workflow/Agent: args/промпт ссылаются на I-NN, которых НЕТ реальными строками в system_model.md.
_ARG_INV_RE = re.compile(r"\bI-(\d+)\b")


def _model_invariant_ids(text):
    """Множество числовых id РЕАЛЬНО построенных инвариантов (заполненная pipe-строка ИЛИ буллет с
    check+pred) в system_model.md. Skeleton/пустой шаблон не в счёт (та же валидация, что _model_has_
    real_invariant). Для сверки «инвариант из args уже в модели?»."""
    ids = set()
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if _I_PIPE_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[1] and any(cells[2:]):
                m = re.search(r"I-?(\d+)", cells[0])
                if m:
                    ids.add(m.group(1))
        elif _I_BULLET_HDR_RE.match(line):
            block = [line]
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if not s or s.startswith("## ") or _I_BULLET_HDR_RE.match(nxt) or _I_PIPE_RE.match(nxt):
                    break
                block.append(nxt)
            blob = "\n".join(block)
            if _B_CHECK_FILLED_RE.search(blob) and _B_PRED_FILLED_RE.search(blob):
                m = re.search(r"I-?(\d+)", line)
                if m:
                    ids.add(m.group(1))
    return ids


def _invariants_inline_not_modeled(marker, prompt_text, min_missing=2):
    """True ⇔ веер-промпт/args ссылается на ≥min_missing I-NN, которых НЕТ реальными строками в
    system_model.md → инварианты сформулированы В ARGS, а не построены в модели ПЕРВЫМИ (model-first
    violation). Off: модель BUILDING/NA, <min_missing новых id, все id уже в модели. min_missing=2 —
    анти-FP на одиночную ссылку (реальная inline-волна = много новых I-NN, enzyme: I-48..I-64)."""
    if not prompt_text:
        return False
    arg_ids = set(_ARG_INV_RE.findall(prompt_text))
    if len(arg_ids) < min_missing:
        return False                                   # мало ссылок — не inline-волна
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_BUILDING_RE) or _model_sentinel(lt, _MODEL_NA_RE):
        return False                                   # строю модель / N/A → не форсим
    smd = os.path.join(sdir, "system_model.md")
    if not os.path.exists(smd):
        return False
    try:
        with open(smd, "r", encoding="utf-8") as f:
            mt = f.read()
    except Exception:
        return False
    if not _model_has_real_invariant(mt):
        return False                                   # модели ещё нет → первую волну ловит _should_nudge
    missing = arg_ids - _model_invariant_ids(mt)
    return len(missing) >= min_missing


_DNN_ROW_RE = re.compile(r"(?m)^\s*\|\s*\**\s*D-\d")            # реальная строка D-NN (\** = bold `**D-01**`)
_DEPTHLEAD_FIELD_RE = re.compile(                               # заполненный Depth-Lead: H/D-NN + k/5
    r"depth-lead[:*\s`]*[^\n]*\b[HD]-\d+\b[^\n]*\d\s*/\s*\d", re.I)


def _writes_depth(new):
    """True если Edit/Write вписывает РЕАЛЬНЫЙ Depth-Lead (H/D-NN + k/5) или строку `D-NN` (не плейсхолдер)."""
    if not new:
        return False
    for m in _DEPTHLEAD_FIELD_RE.finditer(new):
        if "{" not in m.group(0) and "}" not in m.group(0):   # не шаблонный `{… H-03 — 3/5 …}`
            return True
    return bool(_DNN_ROW_RE.search(new))


# jetinfosystems_tab_1 2026-08-14: на web2-потоке (Bash-пробы + Edit карты/H-NN в ledger, AC-модель
# СТРОИТСЯ НЕФОРМАЛЬНО в прозе ledger) ни scout-триггер (ветка 1), ни depth-lead-Edit (ветка 2) не
# срабатывают → формальная T10-модель (`AC-I` в system_model.md) не форсится, ранние `D-NN`-дивергенции
# упускаются. Триггер по РАСХОЖДЕНИЮ: ledger ЗРЕЛЫЙ (≥min_h уник. H-NN = реальная работа идёт), а формальная
# модель ПУСТА (not has_real_invariant) и не заявлена N/A/BUILDING. Web-template ledger несёт 0 H-NN → порог
# ≥4 чист от FP на свежем ханте. Канало-независим (любой Edit/Write ledger'а), debounce гасит спам.
_H_LEDGER_RE = re.compile(r"(?im)^\s*[-*|>#]*\s*\**\s*H-(\d+)\b")


def _ledger_mature_but_model_empty(marker, min_h=4):
    """True ⇔ ledger зрелый (≥min_h уник. H-NN), но формальная модель пуста и не N/A/BUILDING."""
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_NA_RE) or _model_sentinel(lt, _MODEL_BUILDING_RE):
        return False                                   # N/A / строю модель → не форсим
    smd = os.path.join(sdir, "system_model.md")
    if os.path.exists(smd):
        try:
            with open(smd, "r", encoding="utf-8") as f:
                if _model_has_real_invariant(f.read()):
                    return False                       # формальная модель уже построена
        except Exception:
            pass
    return len(set(_H_LEDGER_RE.findall(lt))) >= min_h


def _model_built_or_na(marker):
    """True (→ silent) если I-NN реально построены (строки в system_model.md) ИЛИ MODEL: N/A."""
    sdir = os.path.dirname(marker)
    ledger = os.path.join(sdir, "hypotheses.md")
    try:
        with open(ledger, "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return True                                            # нет ledger — не наше дело (тишина)
    if _model_sentinel(lt, _MODEL_NA_RE):
        return True
    smd = os.path.join(sdir, "system_model.md")
    if os.path.exists(smd):
        try:
            with open(smd, "r", encoding="utf-8") as f:
                if _model_has_real_invariant(f.read()):
                    return True
        except Exception:
            pass
    return False


# --- OBS-24 (gmtrade/aave/trufin/enzyme-onyx 2026-07: 4-й инстанс ПОДРЯД) — new-axis-needs-wave -----
# Промах: инстанс объявляет НОВУЮ T9-ось и СРАЗУ гонит scout по code/file-фреймингу, НЕ построив под
# неё новую волну `I-NN` (pred: до кода). Per-wave-ветка `_should_nudge` завязана на РУЧНОЙ сброс
# Scout-Status→PENDING на новой оси — но именно ЭТУ дисциплину инстансы и проваливают (enzyme-onyx
# держал Status:DONE с волны-1 → нудж молчал на axis-2/3). Циклическая зависимость: нудж полагается
# на то, что должен форсить. Фикс: триггер от СОСТОЯНИЯ модели, а не от ручного маркера — Loop State
# заявил T9-осей больше, чем построено `## WAVE-*`-волн (+явных N/A-осей). Зеркалит Stop-гейт
# active_axes_without_waves, но на ГРАНИЦЕ Agent — ловит breadth-before-wave ДО scout'а, не на выходе.
# Конвенция (как в гейте): base `## Invariants` = pre-T9 модель, НЕ волна; N restart-осей → N `## WAVE-*`.
_T9_AXES_USED_RE = re.compile(r"T9\s*restart\s*axes\s*used:?\**\s*(\d+)", re.I)
_SEC_HDR_RE = re.compile(r"^#{2,3}\s+(.*)")
_WAVE_TITLE_RE = re.compile(r"wave", re.I)
_NA_AXIS_RE = re.compile(   # verbatim из hunt_completeness_gate — паритет счёта N/A-осей
    r"(?im)^(?=.*(?:\bn/?a\b|не\s*примен|out[\s-]*of[\s-]*scope))"
    r"(?=.*(?:cross-function|cross-subsystem|order|sequence|temporal|isolation|economic)).*$")
# flow/OZ 2026-08-18: floor по СОСТОЯНИЮ, не по фразе (паритет с gate). Поля `Current pick`/`Depth-Lead`
# называют текущую ось (`AXIS-2 pivot` / `reset на axis-2` / кир. `Пивот → axis-2`); floor = max_index−1.
_CURRENT_AXIS_FIELD_RE = re.compile(r"(?im)^.*(?:current\s+pick|depth[\s\-]?lead)\b.*$")
_AXIS_IDX_RE = re.compile(r"\baxis[\s\-]?(\d+)", re.I)


def _axes_declared(ledger_text):
    """Макс. N из 'T9 restart axes used: N' (плейсхолдер `{…}`/`~~…~~` — мимо), либо floor по текущей оси
    в полях `Current pick`/`Depth-Lead` (`axis-N`, N≥2 → рестарт; floor=N−1; паритет с gate, phrase-agnostic)."""
    n = 0
    for l in (ledger_text or "").splitlines():
        if "{" in l or "~~" in l:
            continue
        m = _T9_AXES_USED_RE.search(l)
        if m:
            try:
                n = max(n, int(m.group(1)))
            except ValueError:
                pass
    max_axis = 0
    for line in _CURRENT_AXIS_FIELD_RE.findall(ledger_text or ""):
        if "{" in line:
            continue
        for am in _AXIS_IDX_RE.finditer(line):
            try:
                max_axis = max(max_axis, int(am.group(1)))
            except ValueError:
                pass
    if max_axis >= 2:
        n = max(n, max_axis - 1)
    return n


def _wave_sections_with_invariants(model_text):
    """Число секций `## …wave…` (кроме base `## Invariants`), под которыми есть ≥1 `I-NN` (pipe/буллет)."""
    cur = "(preamble)"
    waves = set()
    for l in (model_text or "").splitlines():
        h = _SEC_HDR_RE.match(l)
        if h:
            cur = h.group(1).strip()
            continue
        if _I_PIPE_RE.match(l) or _I_BULLET_HDR_RE.match(l):
            if _WAVE_TITLE_RE.search(cur):
                waves.add(cur)
    return len(waves)


def _new_axis_needs_wave(marker):
    """True (fire) ⇔ Loop State заявил T9-осей > (построенных WAVE-волн + явных N/A-осей), и модель НЕ
    строится / НЕ N/A. Ловит смену оси без новой I-NN-волны на границе Agent, независимо от Scout-Status."""
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_BUILDING_RE) or _model_sentinel(lt, _MODEL_NA_RE):
        return False                                   # строю волну / T10 неприменим → тишина
    n = _axes_declared(lt)
    if n < 1:
        return False                                   # T9-осей ещё нет → первую волну ловит _should_nudge
    mt = ""
    smd = os.path.join(sdir, "system_model.md")
    if os.path.exists(smd):
        try:
            with open(smd, "r", encoding="utf-8") as f:
                mt = f.read()
        except Exception:
            mt = ""
    return _wave_sections_with_invariants(mt) + len(_NA_AXIS_RE.findall(mt)) < n


# --- OBS-27 (granite-protocol 2026-08-04, 6-й инстанс) — scout ЯВНО назван «WAVE-N», а волны нет -----
# Новая форма evasion: инстанс держит `T9 restart axes used: 0` (WAVE-2 = НОРМАЛЬНАЯ мультиволна, не
# T9-cold-restart) и гонит «2 WAVE-2 cold-скаута» ДО построения I-13..I-17. OBS-24 слеп (n=0). Прямой
# сигнал вместо счётчика: сам scout-ПРОМПТ ссылается на `WAVE-N` (N≥2), а секции этой волны с `I-NN` в
# модели ещё нет → bug-hunt по оси до модели. Не зависит ни от T9-счётчика, ни от ручного Scout-Status.
_WAVE_REF_RE = re.compile(r"wave[\s\-_]*([2-9]|1\d)", re.I)     # WAVE-2..WAVE-19 (wave-1 = база, не в счёт)


def _built_wave_numbers(model_text):
    """Множество N, для которых секция `## WAVE-N`/`### WAVE-N` содержит ≥1 `I-NN` (pipe/буллет)."""
    cur_n = None
    built = set()
    for l in (model_text or "").splitlines():
        h = _SEC_HDR_RE.match(l)
        if h:
            m = re.search(r"wave[\s\-_]*(\d+)", h.group(1), re.I)
            cur_n = int(m.group(1)) if m else None
            continue
        if cur_n is not None and (_I_PIPE_RE.match(l) or _I_BULLET_HDR_RE.match(l)):
            built.add(cur_n)
    return built


def _scout_targets_unbuilt_wave(marker, prompt_text):
    """True ⇔ scout-промпт ссылается на `WAVE-N` (N≥2), а этой волны с `I-NN` в модели НЕТ, и модель не
    BUILDING/NA. Прямой per-axis сигнал, независим от T9-счётчика (granite: normal WAVE-2, счётчик=0)."""
    refs = set(int(x) for x in _WAVE_REF_RE.findall(prompt_text or ""))
    if not refs:
        return False
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_BUILDING_RE) or _model_sentinel(lt, _MODEL_NA_RE):
        return False
    mt = ""
    smd = os.path.join(sdir, "system_model.md")
    if os.path.exists(smd):
        try:
            with open(smd, "r", encoding="utf-8") as f:
                mt = f.read()
        except Exception:
            mt = ""
    built = _built_wave_numbers(mt)
    return any(n not in built for n in refs)


# --- OBS-28 (granite-protocol 2026-08-04) — scout называет `unmodeled` подсистему (обобщение OBS-27) --
# iter-6 «governance-v1+meta-gov scout» НЕ помечен `WAVE-N` → OBS-27 мимо, но это тот же промах: bug-hunt
# по подсистеме, которую модель НЕ покрыла. Прямой сигнал по СУЩЕСТВУ: scout-промпт называет подсистему,
# которую `## Subsystem Model Coverage` держит `unmodeled`+in-scope. Матчим по значимым словам (≥5 симв.)
# имени подсистемы — слова коррелируют с целью скаута, поэтому scout по УЖЕ смоделированной оси (её слов
# в unmodeled-строках нет) не ложно-срабатывает (granite: economic-sequence scout молчит, governance — нет).
_COVERAGE_HDR = "## Subsystem Model Coverage"


def _unmodeled_subsystems(model_text):
    """Имена in-scope подсистем со статусом `unmodeled` из ## Subsystem Model Coverage."""
    txt = model_text or ""
    i = txt.find(_COVERAGE_HDR)
    if i < 0:
        return []
    j = txt.find("\n## ", i + 1)
    out = []
    for l in txt[i:(j if j > 0 else len(txt))].splitlines():
        if not l.strip().startswith("|"):
            continue
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(c) >= 3 and c[0] and not c[0].startswith("{") and "subsystem" not in c[0].lower():
            if c[1].lower().startswith("y") and "unmodeled" in c[2].lower():
                out.append(c[0])
    return out


def _scout_targets_unmodeled_subsystem(marker, prompt_text):
    """True ⇔ scout-промпт называет in-scope `unmodeled` подсистему (по слову ≥5 симв. из её имени), и
    модель не BUILDING/NA. Ловит bug-hunt по НЕ-смоделированной подсистеме без WAVE-N-метки (granite iter-6)."""
    if not prompt_text:
        return False
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_BUILDING_RE) or _model_sentinel(lt, _MODEL_NA_RE):
        return False
    smd = os.path.join(sdir, "system_model.md")
    if not os.path.exists(smd):
        return False
    try:
        with open(smd, "r", encoding="utf-8") as f:
            mt = f.read()
    except Exception:
        return False
    plow = prompt_text.lower()
    for name in _unmodeled_subsystems(mt):
        words = [w for w in re.split(r"[^0-9a-zа-яё]+", name.lower()) if len(w) >= 5]
        if any(w in plow for w in words):
            return True
    return False


# --- enzymefinance 2026-08-19 (the operator, продолжение ханта в новой сессии) — new-axis/T9-restart scout ------
# Промах: на КОНТИНУАЦИИ (resume) хантер объявляет «COLD RESTART (T9) на новой оси» и СРАЗУ спавлит 2 plain
# cold-скаута, минуя entry-дисциплину: (1) pop/populate axis-queue, (2) построить I-NN новой оси, (3) HYBRID
# веер. `_new_axis_needs_wave` слеп: `T9 restart axes used` = плейсхолдер `{…}`, оси именованы `A66` (не
# `axis-6`) → `_axes_declared`=0. Robust-сигнал от НАМЕРЕНИЯ в промпте (не от ledger-счётчика): промпт
# СИГНАЛИТ новую ось / cold-restart, а гонятся plain Agent-скауты (не HYBRID Workflow) при построенной модели.
_NEW_AXIS_SIGNAL_RE = re.compile(
    r"cold[\s\-]*restart|\bt9\b|нов\w*\s+ос[ьяию]|new\s+ax(?:is|es)|свеж\w*\s+ос[ьяию]|"
    r"смен\w*\s+ос[ьяию]|fresh\s+ax(?:is|es)|на\s+нов\w*\s+оси", re.I)


def _scout_signals_new_axis(marker, prompt_text):
    """True ⇔ scout-промпт СИГНАЛИТ новую ось / T9 cold-restart, модель построена, не BUILDING/NA. Ловит
    «T9-рестарт → plain cold-скауты» БЕЗ I-NN+HYBRID, независимо от плейсхолдерного T9-счётчика / A-NN-нейминга
    (на которых слепнет _new_axis_needs_wave). Вызывать ТОЛЬКО на plain Agent/Task (не Workflow=hybrid)."""
    if not prompt_text or not _NEW_AXIS_SIGNAL_RE.search(prompt_text):
        return False
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_BUILDING_RE) or _model_sentinel(lt, _MODEL_NA_RE):
        return False                                   # строю волну оси / T10 неприменим → тишина
    smd = os.path.join(sdir, "system_model.md")
    if not os.path.exists(smd):
        return False
    try:
        with open(smd, "r", encoding="utf-8") as f:
            if not _model_has_real_invariant(f.read()):
                return False                           # модели нет → первую волну ловит _should_nudge
    except Exception:
        return False
    return True


# --- OBS-29 (granite + gmtrade 2026-08-04) — модель есть → веер ОБЯЗАН быть HYBRID Workflow, не ручной --
# Диагноз инстанса (granite, фактами): Workflow ДОСТУПЕН (запустился, упал на своём arg-гварде), мандат
# «модель есть → ОБЯЗАТЕЛЬНО HYBRID `divergence_fanout.workflow.js`, НЕ CLASSIC» ВИДЕЛ (deephunt.md:469-472),
# но `(d) не связал мандат с действием` → свалился в ручной by-invariant веер (Agent-скауты). Тот же класс,
# что model-first: проза в скиле не enforced хуком → систематически пропускается. `model_first_nudge` тыкал
# только MODEL-FIRST на ПУСТОЙ модели; при ГОТОВОЙ модели не проверял ФОРМУ веера. Фикс: на границе Agent —
# если модель построена, промпт = by-invariant scout, а HYBRID-запуск в ledger не логирован → мягкий тычок
# «запусти HYBRID Workflow (args:{slug}), не руками». Мягкий (Workflow может быть не opt-in в части сессий →
# жёсткий блок дедлочил бы; скил сам пишет «если доступен»). Гасится, как только HYBRID залогирован.
# FIX-3 (ethena-live 2026-08-12, judge): `divergence[-_ ]?fan-?out` — раньше матчило ТОЛЬКО underscore-форму
# `divergence_fanout` → inline-Workflow с дефисным именем (`ethena-divergence-fanout`) НЕ распознавался как
# HYBRID, мандат держался ручной прозой «HYBRID Scout Fan-Out». Теперь ловит hyphen/space-варианты реального
# inline-запуска. (Честный предел: проза всё ещё может сфабриковать фразу без запуска — как T4-integrity,
# статика не докажет факт вызова; но легит inline-hybrid теперь не получает ложный nag.)
_SCOUT_WORD_RE = re.compile(r"\bscout|scout[\s-]*fan-?out|партици|partition|веер|falsif|опроверг", re.I)
_INV_REF_RE = re.compile(r"\bI-\d|\b[A-Z]{1,3}\d?-I\d|\bP-B\b|\bP[1-9]\b|на всех путях|enforced", re.I)
# enzymefinance 2026-08-19: PER-WAVE счёт прогонов веера (зеркалит Stop-гейт `_fanout_run_count`) вместо
# глобального `_hybrid_logged`. Раньше «hybrid залогирован ХОТЬ РАЗ» (волна-1) гасил нудж НАВСЕГДА → на
# волнах 2-3 хантер гнал ручные cold-скауты, а HYBRID_REMINDER молчал. Теперь: runs < waves → веер отстал
# от волн на ГРАНИЦЕ Agent (превентив, до plain-скаута), не только реактивно на Stop.
_FANOUT_WF_RE = re.compile(r"wf_[a-z0-9]{4,}", re.I)                  # Workflow runId (уникален per прогон)
# enzymefinance 2026-08-19: голый runId в WAVE-MERGE заголовке (`### WAVE-16 MERGE (HYBRID-веер wz9twjv1b,
# 8 агентов)`) — зеркало Stop-гейтового `_FANOUT_RUNID_CTX_RE`. Тугой сепаратор — без FP на `workflow`.
_FANOUT_RUNID_CTX_RE = re.compile(
    r"(?i)(?:hybrid[-\s]*веер|hybrid[-\s]*fan-?out|\bfanout\b|\bвеер\b)[\s:,—()\-]{0,4}\b(w[a-z0-9]{6,20})\b")
_FANOUT_FIELD_RE = re.compile(r"^\s*[-*]?\s*\*{0,2}\s*hybrid[-\s]*fanout\s*[:=]", re.I)  # структурная запись прогона
_FANOUT_MENTION_RE = re.compile(r"divergence[-_\s]?fan-?out|HYBRID\s+Scout\s+Fan-?Out", re.I)  # прозо-лог прогона (FIX-3)


def _fanout_runs(ledger_text):
    """Число DISTINCT прогонов HYBRID-веера (per-line): wf_-runId ИЛИ `HYBRID-fanout:` field ИЛИ прозо-
    упоминание `divergence-fanout`/`HYBRID Scout Fan-Out` (FIX-3 inline-лог hyphen/space-формы). НЕ из
    инструкции (backtick/`{`/blockquote `>` → floor=0 на нетронутом ledger'е: script-имена шаблона в
    backticks не в счёт). Наследует толерантность старого `_hybrid_logged` (считал упоминание) + per-wave
    (distinct-строки = distinct прогоны). Нудж мягче Stop-гейтового `_fanout_run_count` (тот прозу не
    считает) — soft-превентив, Stop-гейт бэкстопит строго."""
    keys = set()
    for ln in (ledger_text or "").splitlines():
        s = ln.lstrip()
        if "`" in ln or "{" in ln or s.startswith(">"):
            continue
        wf = _FANOUT_WF_RE.search(ln)
        if wf:
            keys.add(wf.group(0).lower())
            continue
        rids = _FANOUT_RUNID_CTX_RE.findall(ln)        # голый runId в WAVE-MERGE заголовке (enzyme)
        if rids:
            for r in rids:
                keys.add("rid:" + r.lower())
            continue
        if _FANOUT_FIELD_RE.match(ln) or _FANOUT_MENTION_RE.search(ln):
            keys.add("hf:" + re.sub(r"\s+", " ", ln.strip().lower())[:60])
    return len(keys)


def _manual_scout_without_hybrid(marker, prompt_text):
    """True ⇔ модель построена, промпт = by-invariant scout (scout-слово + инвариант/партиция-реф), а
    HYBRID в ledger НЕ логирован → инстанс гонит ручной веер вместо HYBRID Workflow (granite (d))."""
    if not prompt_text:
        return False
    if not (_SCOUT_WORD_RE.search(prompt_text) and _INV_REF_RE.search(prompt_text)):
        return False
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_NA_RE) or _model_sentinel(lt, _MODEL_BUILDING_RE):
        return False                                   # N/A → CLASSIC ok; BUILDING → веер ещё рано
    smd = os.path.join(sdir, "system_model.md")
    if not os.path.exists(smd):
        return False
    try:
        with open(smd, "r", encoding="utf-8") as f:
            mt = f.read()
    except Exception:
        return False
    if not _model_has_real_invariant(mt):
        return False                                   # модели ещё нет → первую волну ловит _should_nudge
    # PER-WAVE (enzymefinance 2026-08-19): веер отстал от волн (runs < waves) → на ЭТОЙ волне HYBRID ещё не
    # прогнан → нудж. runs >= waves → веер успевает, ручной follow-up на текущей волне легитимен. Раньше
    # `_hybrid_logged` (глобальный) гасил после волны-1 навсегда → волны 2-3 гнались ручными скаутами молча.
    runs = _fanout_runs(lt)
    waves = _wave_sections_with_invariants(mt) + 1     # base `## Invariants` + `## WAVE-*` секции
    if runs >= waves:
        return False
    return True


# --- OBS-31 (capyfi 2026-08-25) — STATE-based веер-due на границе Agent, НЕ по словам промпта -----------
# Диагноз (capyfi, measured): на WAVE-2 Cold Restart (новые оси 4-5) хантер заспавнил per-axis cold-агенты
# промптом-ЗАДАЧЕЙ («verify deployed Comptroller vs repo HEAD for bytecode divergence») вместо HYBRID-веера.
# ВСЕ phrase-keyed детекторы молчали (_scout_signals_new_axis / _manual_scout_without_hybrid требуют
# scout/new-axis-СЛОВА+I-NN в промпте; их там нет), _new_axis_needs_wave слеп (T9-счётчик = плейсхолдер).
# Stop-гейт active_hybrid_fanout_stale ловил (runs<waves), но на КОНЦЕ turn'а — cold-агенты уже отработали.
# Корень: enforcement ключевался на СЛОВА промпта, а анти-паттерн задан СОСТОЯНИЕМ ledger'а (веер ДОЛЖЕН:
# runs<waves) + спавном Agent (не Workflow). Фикс: STATE-детектор — fire на Agent/Task при runs<waves +
# модель есть, НЕЗАВИСИМО от слов промпта; промпт юзается ТОЛЬКО для НЕГАТИВНОГО фильтра (research / T4-
# верификатор НАХОДКИ — не scout). Ловит task-only cold-scout; исключает явный research/T4. Зеркалит
# Stop-гейт на PreToolUse = превентивно (ДО того как cold-агенты отработают). Стоит ПОСЛЕ _manual_scout_
# without_hybrid в main (proper scout ловится там; сюда доходит только НЕ-scout ad-hoc агент).
_NONSCOUT_AGENT_RE = re.compile(
    r"(?i)\b(?:research|web[\s-]?search|web[\s-]?fetch|summari[sz]|перевед|translate|docs?[\s-]?read)\b"
    r"|(?:verif\w+|re-?deriv\w+|refut\w+|adversarial|maker|опроверг\w*|перепровер\w*)\b[^\n]{0,30}"
    r"\b(?:finding|H-?\d|D-?\d|poc|report|наход\w*|claim)\b")


def _agent_while_fanout_due(marker, prompt_text):
    """True ⇔ Agent/Task спавнится, пока веер/scout-fanout ДОЛЖЕН на текущей волне (runs<waves), модель есть,
    и это НЕ явный research/T4-верификатор находки. STATE-based (capyfi 2026-08-25): анти-паттерн — не слова
    промпта, а состояние ledger'а «волна без веера» + спавн Agent (cold-scout вместо HYBRID). Промпт → только
    негативный фильтр (не триггер), поэтому task-only cold-агент («verify deployed-vs-repo») больше не молчит."""
    if prompt_text and _NONSCOUT_AGENT_RE.search(prompt_text):
        return False                                   # явный research / T4-верификатор находки — не scout
    sdir = os.path.dirname(marker)
    try:
        with open(os.path.join(sdir, "hypotheses.md"), "r", encoding="utf-8") as f:
            lt = f.read()
    except Exception:
        return False
    if _model_sentinel(lt, _MODEL_NA_RE) or _model_sentinel(lt, _MODEL_BUILDING_RE):
        return False                                   # N/A → CLASSIC ok; BUILDING → веер ещё рано
    smd = os.path.join(sdir, "system_model.md")
    if not os.path.exists(smd):
        return False
    try:
        with open(smd, "r", encoding="utf-8") as f:
            mt = f.read()
    except Exception:
        return False
    if not _model_has_real_invariant(mt):
        return False                                   # модели нет → первую волну ловит _should_nudge
    runs = _fanout_runs(lt)
    waves = _wave_sections_with_invariants(mt) + 1
    return runs < waves


AXIS_REMINDER = (
    "MODEL-FIRST на НОВОЙ T9-ОСИ (T9 × T10 divergence-first, PreToolUse-guard — OBS-24). В Loop State "
    "заявлено T9-осей БОЛЬШЕ, чем построено волн `## WAVE-*` с `I-NN` в system_model.md. Ты запускаешь "
    "scout/веер, НЕ построив под новую ось новую волну инвариантов. Смена оси = сперва НОВАЯ волна "
    "`I-NN` (формулами, `pred:` от НАЗНАЧЕНИЯ/exclusions оси ДО чтения кода), ПОТОМ scout нарезает "
    "партиции по ЭТИМ инвариантам («найди, где I-NN не enforced»). Breadth-scout по новой оси БЕЗ "
    "волны = code/file-фрейминг — ровно повторяющийся промах (gmtrade / aave / trufin / enzyme-onyx, "
    "4-й подряд). Построй `## WAVE-N` в system_model.md (или пометь ось `N/A — <причина>`, если T10 к "
    "ней неприменим — напр. ось = чистый T11-харнесс поверх уже построенных I-NN: тогда пиши "
    "`T11-VERDICT:` вместо новой волны), затем запускай scout. Пока строишь — `MODEL: BUILDING`. "
    "TOOL-OUTPUT-LAST (§40.1): та же волна инвариантов — твой D-NN на НОВОЙ оси, не вывод сканера/"
    "публичного skill'а, прогнанного по этой оси раньше модели; сканер читаешь ПОЗЖЕ, как cross-check."
)


REMINDER = (
    "MODEL-FIRST (T10 divergence-first, PreToolUse-guard). Ты запускаешь субагента (scout/веер?), а "
    "модель системы ещё НЕ начата в Loop State. Divergence-first порядок: НЕЗАВИСИМАЯ модель `I-NN` "
    "(с `pred:` ДО чтения кода) ПЕРВОЙ → потом scout нарезает партиции ПО ИНВАРИАНТАМ («найди, где "
    "I-03 не enforced»), а не по файлам. Сейчас: либо построй модель-волну (T10, `system_model.md`), "
    "либо поставь в Loop State `MODEL: BUILDING` (пока строишь) / `MODEL: N/A — <причина>` (мелкий "
    "контракт <300 LOC / чистый статический сайт без auth/web3 — НО НЕ нормальный dApp/web2-app: "
    "там `MODEL: N/A` = БАГ, а не режим (строй web-модель TB-/AC-, §38)) — тогда я замолчу. "
    "⚠ ПОДМЕНА МОДЕЛИ: чужой `specs/invariants.md` / audit-каталог инвариантов = КОРПУС-ПРЕДМЕТ "
    "проверки, а НЕ твоя модель. Он по построению доказывает, что код прав, и его читает вся толпа — "
    "искать по нему = идти туда же. Их теги `[E]/[D]/[C]` = `pred:`, НЕ факт. Ценность T10 в "
    "РАСХОЖДЕНИИ твоей независимой модели с их описанием/кодом, а не в согласии. "
    "Если этот Agent — не scout, а research-чтение корпуса ДЛЯ модели / cold-verifier — продолжай, "
    "это и есть model-first (потом впиши `MODEL: BUILDING`). "
    "⚠ TOOL-OUTPUT-LAST (§40.1, anti-anchoring, 0xSimao): если этот субагент/веер запускает сканер, "
    "публичный skill или фаззер — его ВЫВОД читается ПОСЛЕ твоего собственного D-NN/гипотезы по этому "
    "куску кода, как cross-check, НЕ как затравка. Чужой вывод первым = анкор на «то, что и так все "
    "находят» — теряется un-dup."
)


HYBRID_REMINDER = (
    "HYBRID SCOUT FAN-OUT (T10 × open-kritt, PreToolUse-guard — OBS-29). У тебя ПОСТРОЕНА модель "
    "(`I-NN` в system_model.md), а ты запускаешь РУЧНОЙ by-invariant scout (Agent). Мандат "
    "(deephunt.md:469-472): МОДЕЛЬ ЕСТЬ → ОБЯЗАТЕЛЬНО **HYBRID Scout Fan-Out** "
    "(`divergence_fanout.workflow.js` через `Workflow`), НЕ CLASSIC/ручной веер. Уникальная ценность "
    "HYBRID — механизированный **reduce=synthesis**: старший агент над ВСЕМ батчем наблюдений ищет пары "
    "ДАЛЁКИХ улик (cross-thread), которых одиночный scout структурно не выражает (ручной merge это "
    "проваливал: strata, impossible-cloud). Запусти: "
    "`Workflow({scriptPath:'bug-bounty-toolkit/scripts/_methodology/divergence_fanout.workflow.js', "
    "args:{slug:'<target-slug>'}})` (arg `slug` ОБЯЗАТЕЛЕН — иначе скрипт падает на своём гварде). В чате "
    "произнеси «HYBRID Scout Fan-Out». Если `Workflow` реально НЕ доступен в этой сессии — тогда ручной "
    "by-invariant веер = легитимный фолбэк (скил: «если доступен»), продолжай."
)


INLINE_INV_REMINDER = (
    "MODEL-FIRST: ИНВАРИАНТЫ В ARGS, НЕ В МОДЕЛИ (T10, enzymefinance 2026-08-19). Ты запускаешь веер с "
    "инвариантами `I-NN`, сформулированными ПРЯМО В ARGS/промпте, которых НЕТ реальными строками в "
    "`system_model.md`. Порядок model-first: инвариант строится в МОДЕЛИ ПЕРВЫМ (секция `## WAVE-N`: "
    "`check:` / `component:` / `pred:` ДО кода + `status:`), и ТОЛЬКО ПОТОМ веер проверяет его enforcement "
    "по коду. Инвариант, живущий лишь в args, — не сверенная модель: нет артефакта для дельты/ре-визита, "
    "теряется `D-NN`-трек (pred≠факт), веер гоняется по формулировке, а не по модели. СЕЙЧАС: бэкфилль "
    "эти `I-NN` в `system_model.md` новой волной `## WAVE-N` (check/component/pred/status для отработанных, "
    "pred-only для in-flight), затем запускай веер с `args:{slug}` — он читает инварианты ИЗ модели. "
    "Пока строишь волну — `MODEL: BUILDING`."
)


NEW_AXIS_SCOUT_REMINDER = (
    "НОВАЯ ОСЬ / T9-RESTART — ПО СИСТЕМЕ, НЕ PLAIN-СКАУТЫ (enzymefinance 2026-08-19, the operator: «продолжение "
    "= как вход»). Ты сигналишь новую ось / cold-restart и спавлишь plain cold-Agent-скауты. Continuation "
    "ханта идёт по ТОЙ ЖЕ entry-дисциплине, что и первый вход: (1) **Axis-Queue** — pop голову ranked-очереди "
    "(пуста → сперва РЕГЕНЕРИРУЙ её: 3 режима — gap-map / cold-axis / refuted→T6, засей ranked); (2) **построй "
    "I-NN новой оси** в `system_model.md` новой волной `## WAVE-N` (формулами, `pred:` от назначения/exclusions "
    "оси ДО кода) — НЕ формулируй их в args/промпте; (3) **HYBRID `divergence_fanout.workflow.js`** (`Workflow`, "
    "args:{slug}) по этим `I-NN` — механизированный reduce=synthesis cross-thread, а НЕ 2 ad-hoc cold-Agent-"
    "скаута (те дают breadth без синтеза далёких пар). T9 cold-restart = смена ЯКОРЯ, но порядок model-first "
    "держится: очередь → I-NN → HYBRID. Если этот Agent — research-чтение корпуса ДЛЯ модели (не bug-scout) — "
    "продолжай (потом впиши `MODEL: BUILDING`). ⚠ Плейсхолдер `T9 restart axes used: {…}` в ledger не заполнен "
    "— обнови счётчик/`Axes-Closed`, иначе axis-гейты слепнут."
)


FANOUT_DUE_BLOCK = (
    "⛔ HARD-BLOCK (OBS-32, debridge 2026-08-25 — 3-й рецидив cold-Agent-на-новой-оси; soft-reminder не "
    "стопил). Ты спавнишь plain cold-Agent, а HYBRID-веер ДОЛЖЕН на текущей волне (runs<waves): модель "
    "построена, но веер по ней НЕ прогнан. Это РОВНО повторяющийся промах (enzyme/capyfi/debridge): новая "
    "ось → cold-скауты ВМЕСТО «новые I-NN → HYBRID-веер». ПОРЯДОК (не обходить): (1) pop голову ranked "
    "`Axis-Queue`; (2) построй `I-NN` новой волны `## WAVE-N` в system_model.md (pred: от назначения/"
    "exclusions ДО кода); (3) запусти HYBRID `divergence_fanout.workflow.js` (`Workflow`, args:{slug}) по "
    "этим I-NN — reduce=synthesis ищет cross-thread пары. cold-Agent = смена ЯКОРЯ ПОВЕРХ веера, НЕ вместо. "
    "ВЫХОД ИЗ БЛОКА (переоформи и повтори): • proper scout-fanout worker? оформи промпт scout+I-NN "
    "(партиция по инварианту) — тогда не блокирую (получишь soft HYBRID-nudge). • research-чтение корпуса "
    "ДЛЯ модели / T4-верификатор НАХОДКИ? назови явно (research / verify finding H-NN|D-NN). • `Workflow` "
    "реально недоступен? запусти CLASSIC scout-fanout (scout+I-NN промпт). • ось мелкая, T10 неприменим? "
    "пометь `fanout N/A — <причина>` в Loop State. Проза «исправляю» без реального веера/N/A = снова обход."
)


DEPTH_REMINDER = (
    "MODEL-FIRST (T10, mid-turn depth-guard — OBS-23). Ты пишешь Depth-Lead / `D-NN`, но I-NN в "
    "`system_model.md` ещё НЕ построены (ноль строк модели). Divergence-first порядок: I-NN ПЕРВЫМИ "
    "(формулами, с `pred:` ДО кода) → enforcement по коду → `D-NN` рождается из pred≠факт → ТОЛЬКО ПОТОМ "
    "depth-lead высшего `D-NN`. Depth-lead БЕЗ модели = code-first (тот самый промах, что T10 лечит): нить "
    "взята из чтения кода, а не из сверенной дивергенции. Построй `I-NN` в `system_model.md` (или "
    "`MODEL: N/A — <причина>` для мелкого контракта / чистого статического сайта — НЕ для нормального dApp/web2, там N/A = БАГ, §38). ⚠ SOLO-режим (без субагентов) НЕ отменяет "
    "model-first — scout лишь ПАРАЛЛЕЛИТ explore-wide, но I-NN обязательны в ЛЮБОМ режиме; если субагенты "
    "запрещены сессией — строй I-NN сам в основном потоке ПЕРЕД depth-lead."
)


MODEL_GAP_REMINDER = (
    "MODEL-FIRST (T10 formal-model gap — jetinfosystems 2026-08-14). Ledger ЗРЕЛЫЙ (≥4 H-NN — реальная "
    "работа идёт), но формальная T10-модель в `system_model.md` ПУСТА (ноль реальных `AC-I`/`TB-I`/`I-NN`). "
    "Ты моделишь НЕФОРМАЛЬНО в прозе ledger — а это ровно то, что теряет un-dup: формальная "
    "independent-model (инвариант формулой + `pred:` ДО кода → сверка enforcement) вскрывает `D-NN`-"
    "дивергенции, которых неформальная карта эндпоинтов НЕ даёт. Останови breadth, ЗАПОЛНИ "
    "`system_model.md`: инварианты с `check:`/`pred:` (web2 = `AC-I01…` оси доступа; dapphunt = `TB-I01…` "
    "границы доверия) → сверь по коду → `D-NN` в SELECT ВПЕРЕДИ H-NN. Мелкий статический сайт → "
    "`MODEL: N/A — <причина>` (для нормального web2/dApp N/A = баг). Спека: "
    "`_methodology/independent_model_first.md`."
)


def _emit(text):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": text,
        }
    }))


def _deny(text):
    """HARD-BLOCK: PreToolUse DENY — отклоняет вызов тула с reason'ом (в отличие от `_emit`=allow+context).
    the operator 2026-08-25 (debridge, 3-й рецидив): soft-reminder не стопит cold-Agent-на-новой-оси → нужен блок."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": text,
        }
    }))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name") or ""
    current_sid = data.get("session_id") or ""

    if tool not in ("Agent", "Task", "Workflow", "Edit", "Write"):
        sys.exit(0)
    owned = _owned_markers(current_sid)
    if not owned:
        sys.exit(0)
    _, marker = max(owned)

    # ⛔ HARD-BLOCK (OBS-32, debridge 2026-08-25, the operator: 3-й рецидив, soft-reminder не стопит) — ДО всех soft-
    # веток (в т.ч. _new_axis_needs_wave, что exit'ит первым). Узко: Agent/Task (веер=Workflow НЕ блокируется),
    # НЕ proper scout-worker (scout+I-NN → soft HYBRID-nudge ниже), НЕ research/T4 (нег-фильтр в
    # _agent_while_fanout_due), при веер-DUE (runs<waves) + модель есть → DENY плейн cold-Agent. БЕЗ debounce
    # (блок обязан блокировать — заодно чинит «reminder подавился debounce'ом на самом спавне»).
    if tool in ("Agent", "Task"):
        try:
            _tin = data.get("tool_input") or {}
            _pt = " ".join(str(_tin.get(k, "")) for k in ("prompt", "description"))
            # Узко: НЕ-пустой промпт (реальный cold-Agent всегда с промптом; пустой → soft AXIS_REMINDER)
            # + БЕЗ scout-слова вообще (scout-framed, даже без inv → soft build-wave/HYBRID nudge ниже, не блок)
            # + _agent_while_fanout_due (модель+веер-due, нег-фильтр research/T4). = чистый ad-hoc cold-Agent.
            if _pt.strip() and not _SCOUT_WORD_RE.search(_pt) and _agent_while_fanout_due(marker, _pt):
                _deny(FANOUT_DUE_BLOCK)
                sys.exit(0)
        except Exception:
            pass

    # OBS-24 (folksfinance 2026-08-01, 5-й инстанс) — new-axis-needs-wave на ВСЕХ каналах, ПЕРВЫМ.
    # Промах случается и через scout (Agent), И в SOLO (instance читает код новой оси сам, пишет
    # ledger Edit'ом — событие субагента отсутствует). Триггер model-state (`_new_axis_needs_wave`)
    # канало-независим → проверяем на любом хук-туле ДО веток «первой волны». Debounce гасит спам на
    # пачке правок. Гасится, как только волна оси построена (wave_sections≥axes) / `MODEL: BUILDING`/`N/A`.
    try:
        prompt_text = ""
        if tool in ("Agent", "Task", "Workflow"):     # OBS-27: сам scout-промпт называет WAVE-N
            tin = data.get("tool_input") or {}
            prompt_text = " ".join(str(tin.get(k, "")) for k in ("prompt", "description"))
        if (_new_axis_needs_wave(marker)
                or (prompt_text and _scout_targets_unbuilt_wave(marker, prompt_text))
                or (prompt_text and _scout_targets_unmodeled_subsystem(marker, prompt_text))):
            if not _debounced(marker):
                _emit(AXIS_REMINDER)
            sys.exit(0)
    except Exception:
        sys.exit(0)

    # Ветка 1 — scout-before-model, ПЕРВАЯ волна (граница субагента). Субагентный инструмент = **Agent**
    # (Task=0, Agent=970 по транскриптам); Workflow — веер scout_fanout.workflow.js.
    if tool in ("Agent", "Task", "Workflow"):
        try:
            # enzymefinance 2026-08-19: инварианты сформулированы В ARGS веера, а не построены в модели.
            # Стоит ПЕРВЫМ в ветке (более фундаментально, чем «ручной vs hybrid»: сам предмет веера не в модели).
            if prompt_text and _invariants_inline_not_modeled(marker, prompt_text):
                if not _debounced(marker):
                    _emit(INLINE_INV_REMINDER)
                sys.exit(0)
            # enzymefinance 2026-08-19: new-axis/T9-restart СИГНАЛ в промпте + plain Agent/Task (НЕ Workflow=
            # hybrid) → continuation по entry-дисциплине (axis-queue → I-NN → HYBRID), не ad-hoc plain-скауты.
            # Robust к плейсхолдерному T9-счётчику / A-NN-неймингу (на них слепнет _new_axis_needs_wave).
            if tool in ("Agent", "Task") and prompt_text and _scout_signals_new_axis(marker, prompt_text):
                if not _debounced(marker):
                    _emit(NEW_AXIS_SCOUT_REMINDER)
                sys.exit(0)
            # OBS-29: модель ПОСТРОЕНА, но гонишь РУЧНОЙ by-invariant scout вместо HYBRID Workflow.
            if prompt_text and _manual_scout_without_hybrid(marker, prompt_text):
                if not _debounced(marker):
                    _emit(HYBRID_REMINDER)
                sys.exit(0)
            # OBS-31 (capyfi 2026-08-25): STATE-based — Agent спавнится при веер-DUE (runs<waves), модель есть,
            # промпт НЕ scout/new-axis-словами (task-only cold-агент «verify deployed-vs-repo») и НЕ research/T4.
            # Phrase-keyed ветки выше молчат → тот же NEW_AXIS_SCOUT_REMINDER (очередь→I-NN→HYBRID, не ad-hoc
            # cold-скауты), но по СОСТОЯНИЮ ledger'а, не по словам промпта. Превентив-зеркало Stop-гейта.
            if tool in ("Agent", "Task") and _agent_while_fanout_due(marker, prompt_text):
                if not _debounced(marker):
                    _emit(NEW_AXIS_SCOUT_REMINDER)
                sys.exit(0)
            if not _should_nudge(marker):
                sys.exit(0)     # модель строится/N/A или scout-волна отработана → без шума
            if _debounced(marker):
                sys.exit(0)
            _emit(REMINDER)
        except Exception:
            sys.exit(0)
        sys.exit(0)

    # Ветка 2 — depth-lead-before-model, ПЕРВАЯ волна (mid-turn SOLO — событие субагента не нужно).
    if tool in ("Edit", "Write"):
        tin = data.get("tool_input") or {}
        new = tin.get("new_string") or tin.get("content") or ""
        # Ветка 2b (jetinfosystems 2026-08-14) — formal-model gap: ledger ЗРЕЛЫЙ, формальная модель ПУСТА.
        # Канало-независима от depth-контента правки (ловит web2-Bash-поток, где охотник моделит неформально
        # в ledger и не пишет явный depth-lead/D-NN → ветки 1/2 молчат). Своя debounce-марка.
        try:
            if _ledger_mature_but_model_empty(marker):
                if not _debounced(marker, stampname=".last_modelgap_nudge"):
                    _emit(MODEL_GAP_REMINDER)
                sys.exit(0)
        except Exception:
            pass
        if not _writes_depth(new):
            sys.exit(0)         # Edit не про depth-lead/D-NN → не наше дело
        try:
            if _model_built_or_na(marker):
                sys.exit(0)     # I-NN построены / N/A → depth-lead легитимен
            if _debounced(marker, stampname=".last_depth_nudge"):
                sys.exit(0)
            _emit(DEPTH_REMINDER)
        except Exception:
            sys.exit(0)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
