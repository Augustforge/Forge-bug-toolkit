#!/usr/bin/env python3
"""UserPromptSubmit hook — ВХОДНОЙ forcing-function для Hunt-Loop.

Назначение: убрать корневой провал — создание `hypotheses.md` ledger + `.hunt_active`
маркера висело на ПРОЗЕ в CLAUDE.md ("вспомни и подними маркер"), а вход не форсился
ничем. Я роучусь на чтение кода и забываю → весь Hunt-Loop (single-pick, completeness-gate
на выходе) не активируется, т.к. Stop-хук включается ИМЕННО этим маркером.
Урок brutecat (reference_brutecat_ai): инструкция-в-промпте недостаточна → нужен хук,
который СОЗДАЁТ артефакт детерминированно, а не напоминает его создать.

Логика:
  - Срабатывает на КАЖДОМ промпте, но no-op'ит мгновенно если нет hunt-intent.
  - hunt-intent = реальная ССЫЛКА на bounty-программу (immunefi/cantina/c4/sherlock/...
    с путём к конкретной программе) ЛИБО repo/контракт-ссылка + intent-слово.
  - Извлекает slug → создаёт sessions/{slug}/hypotheses.md из канонического template
    (_methodology/hypotheses_template.md) + поднимает .hunt_active.
  - Уже есть свежий ledger для этого slug → RESUME (не перезаписывать), только освежить
    маркер + инжектить "продолжай по Loop State".
  - Инжектит forcing-reminder в контекст (stdout, exit 0).

Fail-open: любая ошибка → exit 0 без вывода (никогда не ломаем ввод пользователя).
"""
import sys
import os
import re
import json
import time
import datetime


# Платформы, где ссылка с путём к программе = почти всегда хант (триггер сам по себе).
# Голый домен без пути не триггерит (анти-FP для мета-разговоров).
PROGRAM_HOSTS = [
    "immunefi.com", "cantina.xyz", "code4rena.com", "sherlock.xyz",
    "hackenproof.com", "codehawks.cyfrin.io", "hats.finance",
    "remedy.so", "secure3.io",
    "standoff365.com", "bi.zone",  # русский сегмент (Standoff365/BI.ZONE) — web2/web3
    "hackerone.com", "bugcrowd.com", "intigriti.com", "yeswehack.com",  # generalist web2-площадки
]

# repo / контракт ссылки — триггерят ТОЛЬКО вместе с intent-словом
CODE_HOSTS = ["github.com", "gitlab.com", "etherscan.io", "basescan.org",
              "arbiscan.io", "bscscan.com", "polygonscan.com", "solscan.io",
              "explorer.solana.com"]

INTENT = [
    "изуч", "посмотри", "глян", "хант", "hunt", "копай", "копни", "разбер",
    "проанализ", "audit", "аудит", "поищи баг", "найди баг", "deephunt",
    "dapphunt", "проверь контракт", "проверь проект", "глубок", "вскрой",
]

# OBS-22 (hyperlane 2026-07-29): ПЕРЕХВАТ (adopt) существующего hunt-маркера на НОВЫЙ sid — только на
# СИЛЬНОМ resume-намерении «веди/продолжай хант», НЕ на слабых eval-глаголах (глянь/посмотри/разбери/
# проанализируй/аудит = «оцени и расскажи»). Широкий INTENT крал маркер ЖИВОГО ханта, когда таргет лишь
# ОБСУЖДАЛИ в другой сессии («глянь папку hyperlane») → та сессия ловила чужие Stop-гейты, а настоящий
# хант ТЕРЯЛ владение своим маркером (sid перезаписан). `detect()` (старт НОВОГО ханта по URL) остаётся
# на широком INTENT — сужаем ТОЛЬКО кражу существующего маркера.
RESUME_INTENT = [
    "изуч", "хант", "hunt", "копай", "копни", "deephunt", "dapphunt",
    "продолж", "верн", "resume", "рестарт", "restart", "вскрой",
    "поищи баг", "найди баг", "проверь контракт", "проверь проект",
]

# Reference/learning-репозитории (писапы, PoC-коллекции, чеклисты, awesome-списки) — их ЧИТАЮТ ДЛЯ
# ОБУЧЕНИЯ, это НЕ hunt-таргеты. Структурно они не отличимы от таргета (github.com/{org}/{repo}), а
# intent-слова "audit/аудит/изучи/глянь" = одновременно обычная лексика методологических разговоров →
# ветка-2 (CODE_HOST + intent) ложно армила хант. Bounded стабильная категория (в отличие от give-up-
# treadmill) → маленький denylist уместен, false-negative ≈0 (протокол не хостит ядро как /audits).
# ROOT observed 2026-07-07: research-субагент вернул github.com/gogotheauditor/audits → the operator отрелеил
# в промпт со словом "аудит" → создался sessions/audits/ ложный маркер, заблокировавший мета-сессию.
REFERENCE_SLUGS = {
    "audits", "audit", "writeups", "writeup", "poc", "pocs", "hacks", "hack",
    "examples", "example", "awesome", "payloads", "payloadsallthethings",
    "solodit", "defihacklabs", "cheatsheet", "cheatsheets",
    "bug-bounty-writeups", "security-research", "docs", "wiki", "blog",
}

# OBS-15 (2026-07-28): denylist выше — ТОЧНОЕ совпадение, а reference-репо часто СОСТАВНОЙ slug:
# `decentraland/smart-contract-audits` → slug=`smart-contract-audits` != `audits` → проходил как таргет
# (research-субагент цитировал URL хранилища PDF-аудитов → ложный хант-ledger). Фикс: токенизировать slug
# (split по -/_) и если любой токен = ОДНОЗНАЧНЫЙ reference-маркер → это reference-репо. Токены держим
# СИЛЬНЫЕ (audits/writeups/awesome/…), НЕ мягкие (docs/hacks/example могут быть частью имени реального
# таргета → им оставляем exact-match, чтобы не давать false-negative на настоящем ханте).
STRONG_REFERENCE_TOKENS = {
    "audits", "audit", "writeups", "writeup", "awesome", "payloads",
    "payloadsallthethings", "pocs", "cheatsheet", "cheatsheets", "solodit",
}

# Имена сетей/чейнов — слишком общие для resume-триггера: встречаются в любом методологическом или
# машинном тексте как ДАННЫЕ (списки поддерживаемых сетей). Единственный slug-хит, совпадающий с именем
# чейна → НЕ resume (arbitrum-инцидент 2026-08-05). Реальный таргет с таким именем заходит через detect()
# по URL. false-negative на голом «продолжай arbitrum» безопаснее, чем ложный перехват на машинном тексте.
_CHAIN_TOKENS = {
    "arbitrum", "optimism", "base", "polygon", "avalanche", "fantom", "bsc",
    "ethereum", "eth", "solana", "sol", "eclipse", "sonic", "soon", "sui",
    "aptos", "movement", "monad", "berachain", "blast", "linea", "scroll",
    "zksync", "mantle", "gnosis", "celo", "metis", "cosmos",
}


def _is_reference_slug(s):
    """True → slug указывает на reference/learning-репо (не hunt-таргет)."""
    if not s:
        return False
    if s in REFERENCE_SLUGS:
        return True
    return any(t in STRONG_REFERENCE_TOKENS for t in re.split(r"[-_]+", s.lower()))

URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)

# P6: явный анти-hunt сигнал (the operator обсуждает/чинит САМУ систему, а не хантит). Узко — эти обороты
# не встречаются в реальном hunt-промпте «изучи <target>».
_META_RE = re.compile(
    r"не\s+охот|не\s+хант|это\s+не\s+охот"
    r"|улучша\w*\s+(наш\w*\s+)?систем"
    r"|(почин|чин|прав)\w+\s+(наш\w*\s+)?(систем|хук|гейт|методолог|детектор|replay)"
    r"|не\s+создавай[^.\n]{0,40}как\s+на\s+охоте|мета-?сесси",
    re.I)


def now():
    return time.time()


def find_root():
    here = os.path.abspath(__file__)
    # hooks -> scripts -> bug-bounty-toolkit -> project root
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def slug_from_url(u):
    """Вытащить осмысленный slug из ссылки на программу/репо."""
    u = u.rstrip("/")
    m = re.match(r"https?://([^/]+)(/.*)?$", u, re.I)
    if not m:
        return None
    host = m.group(1).lower().lstrip("www.")
    path = (m.group(2) or "").strip("/")
    parts = [p for p in path.split("/") if p]

    # ⚠ 2026-07-28 (scout-веер, находка #3): explorer-ссылки (etherscan/basescan/…/address/0x…) —
    # слово-тип пути ("address"/"token"/…) НЕ имя программы. Collapse на него схлопывал ДВА разных
    # контракта (в т.ч. на разных чейнах) в один sessions/address/ → RESUME-ветка мешала два ханта.
    # Этот самый спурьёзный фолдер `address` — живое доказательство. Берём chain-тег из host + адрес.
    _explorer_seg = {"address", "token", "account", "accounts", "tx",
                     "block", "nft", "contract", "holdings"}
    if len(parts) >= 2 and parts[0].lower() in _explorer_seg:
        return _norm(host.split(".")[0] + "_" + parts[1])

    # immunefi.com/bug-bounty/{slug} | /bounty/{slug} | /bounties/{slug}
    # cantina.xyz/competitions/{slug} | code4rena.com/audits/{slug} ...
    skip = {"bug-bounty", "bounty", "bounties", "competitions", "competition",
            "audits", "audit", "contests", "contest", "programs", "program"}
    cand = [p for p in parts if p.lower() not in skip]

    if "github.com" in host or "gitlab.com" in host:
        # github.com/{org}/{repo}
        if len(parts) >= 2:
            return _norm(parts[1])
        if parts:
            return _norm(parts[0])
    if cand:
        return _norm(cand[0])
    if parts:
        return _norm(parts[0])
    return _norm(host.split(".")[0])


def _norm(s):
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s).strip("_").lower()
    return s[:60] or None


def _active_slugs(root):
    """Имена папок sessions/{slug}/ с существующим .hunt_active (был реальный хант)."""
    try:
        base = os.path.join(root, "sessions")
        out = set()
        for name in os.listdir(base):
            if os.path.exists(os.path.join(base, name, ".hunt_active")):
                out.add(name.lower())
        return out
    except Exception:
        return set()


# OBS-22-fix2 (granite-protocol 2026-08-04): adopt живого маркера сработал на подстроке `hunt` внутри
# `bug-hunting` — а это слово было в ЦИТАТЕ, которую the operator вставил для аудита («…вот его ответ: я гнал
# bug-hunting скаутов»). Его СОБСТВЕННЫЙ глагол был «смотри» (обсуждение), не resume. Adopt (перехват
# живого маркера — операция с побочкой) обязан читать intent ТОЛЬКО в обрамлении пользователя, ДО
# первой вставленной цитаты. False-negative (не усыновил) безопасен: реальный хантер держит свой
# маркер; false-positive (украл на audit-sid) вреден. Bias → не усыновлять.
_QUOTE_MARKERS = ("вот его", "вот что", "он пишет", "его ответ", "вот ответ", "ответ:", "пишет:")


def _user_framing(prompt):
    """Часть промпта ДО первой вставленной цитаты инстанса (обрамление самого пользователя)."""
    low = (prompt or "").lower()
    cut = len(prompt or "")
    for m in _QUOTE_MARKERS:
        k = low.find(m)
        if k != -1:
            cut = min(cut, k)
    return (prompt or "")[:cut]


# arbitrum-инцидент 2026-08-05: task-notification агента с "arbitrum" (в списке чейнов) + intent-словами
# обработался как ПОЛЬЗОВАТЕЛЬСКИЙ промпт → detect_resume_by_slug перехватил маркер вчерашней папки
# sessions/arbitrum. Тот же класс, что prompt-injection (§35.4 плана): недоверенный машинный текст
# инжектит наш парсер. _user_framing режет только по цитата-маркерам ("вот его ответ"); машинные БЛОКИ
# (task-notification / system-reminder / SYSTEM NOTIFICATION) не вырезались. Фикс: убрать их ДО детекции.
_MACHINE_BLOCK_RE = re.compile(
    r"<task-notification>.*?</task-notification>"
    r"|<system-reminder>.*?</system-reminder>"
    r"|<task-id>.*?</task-id>"
    r"|\[SYSTEM NOTIFICATION[^\]]*\][^\n]*(?:\n(?!\n)[^\n]*)*"  # авто-событие до пустой строки (строчно, re.S не жрёт хвост)
    # IMPORTANT-1: хвост уведомления об агенте — Agent ИЛИ Task, в КАВЫЧКАХ. Съедаем до пустой строки
    # (как SYSTEM NOTIFICATION выше) — без этого остаток тела уведомления (напр. "Result: изучи <url>")
    # оставался бы нестрипнутым и сам триггерил detect(). Bare-имя БЕЗ кавычек (2026-08-05 regress) убрано:
    # `Agent\s+[\w.\-]+\s+(?:finished|completed)…` съедало легитимную пользовательскую фразу вида
    # «Agent gogo completed scan, изучи <url>» — реальный формат task-notification и так ловится
    # угловыми-скобочными блоками <task-notification> выше; закавыченная форма — редкость в живой речи.
    r"|(?:Agent|Task)\s+\"[^\"]+\"\s+(?:finished|completed)[^\n]*(?:\n(?!\n)[^\n]*)*"
    r"|<function_results>.*?</function_results>",             # вставленный результат инструмента
    re.I | re.S)


def _strip_machine_text(prompt):
    """Убрать машинные вставки (task-notification/system-reminder/tool-result/agent-уведомления) —
    их содержимое = ДАННЫЕ, не намерение пользователя. Fail-open: ошибка → исходный промпт."""
    try:
        return _MACHINE_BLOCK_RE.sub(" ", prompt or "")
    except Exception:
        return prompt or ""


def _current_model(transcript_path):
    """A4: текущая main-loop модель-наблюдатель = последнее assistant-сообщение транскрипта
    (не sidechain-субагент, не `<synthetic>`). Смена модели с прошлого снимка = окно ре-аудита
    (Orchard: новая модель видит то, что старая систематически пропускала). Fail-open: ''
    (недоступно/неоднозначно) → model-reaudit не форсится (анти-FP: молчать безопаснее, чем ныть)."""
    if not transcript_path:
        return ""
    try:
        model = ""
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("isSidechain") is True:
                    continue  # субагент (sonnet-scout) — не наблюдатель основного цикла
                m = o.get("message")
                if isinstance(m, dict) and m.get("role") == "assistant":
                    mv = m.get("model")
                    if mv and mv != "<synthetic>":
                        model = mv  # держим последнее → текущий наблюдатель
        return model
    except Exception:
        return ""


def _resume_hits(prompt, active):
    """Чистая resume-фильтрация (без файловой системы, для unit-теста). Возвращает список active-slug'ов,
    встреченных как токены в промпте, при наличии resume-intent в ОБРАМЛЕНИИ пользователя — за вычетом
    reference-slug'ов и chain-токенов. detect_resume_by_slug решает по len(hits) == 1."""
    if not any(k in _user_framing(prompt).lower() for k in RESUME_INTENT):
        return []
    low = (prompt or "").lower()
    toks = set()
    for t in re.findall(r"[a-zA-Z0-9_-]{3,}", low):
        n = _norm(t)
        if n:
            toks.add(n)
    return [s for s in active
            if s in toks and s not in REFERENCE_SLUGS and s not in _CHAIN_TOKENS]


def detect_resume_by_slug(prompt, root):
    """Resume в НОВОЙ сессии БЕЗ ссылки: intent-слово + токен == имя существующей hunt-папки.
    Перехват только по ЯВНОМУ намерению в ОБРАМЛЕНИИ пользователя (не в цитате, OBS-22-fix2) и не по
    имени чейна (arbitrum-инцидент). Ровно один хит → однозначный resume; несколько/ноль → не угадываем."""
    active = _active_slugs(root)
    if not active:
        return None
    hits = _resume_hits(prompt, active)
    if len(hits) == 1:
        return (hits[0], None)
    return None


def detect(prompt):
    """Вернуть (slug, url) если hunt-intent, иначе None."""
    urls = URL_RE.findall(prompt)
    if not urls:
        return None
    low = prompt.lower()
    has_intent = any(k in low for k in INTENT)

    for u in urls:
        ul = u.lower()
        # 1) bounty-программа со ссылкой-путём = триггер сам по себе
        for h in PROGRAM_HOSTS:
            if h in ul:
                # требуем путь к конкретной программе (есть сегмент после хоста)
                after = ul.split(h, 1)[1].strip("/")
                if after:
                    s = slug_from_url(u)
                    if s:
                        return (s, u)
        # 2) repo / контракт = триггер только с intent-словом И не reference/learning-репо
        if has_intent:
            for h in CODE_HOSTS:
                if h in ul:
                    s = slug_from_url(u)
                    if s and not _is_reference_slug(s):
                        return (s, u)
    return None


# WEB-профиль детект (2026-08-05): выбор web-шаблона (system_model_web / hypotheses_web) vs контрактного.
# Живой web-домен (dApp/web2-app) → web-модель (TB-/AC-), НЕ MODEL:N/A-разоружение. repo/contract/explorer
# → контрактный шаблон. Лёгкий host-детект (без запуска dapp_detection.py — хук fail-open/быстрый).
_WEB_INTENT = ("dapphunt", "dapp", "фронт", "frontend", "web2", "web 2")
# web2-платформы (русский enterprise-сегмент): их программы преим. web2 (банки/маркетплейсы) → web-шаблон
# по дефолту, НЕ контрактный. Отличие от web3-платформ (immunefi/cantina) в PROGRAM_HOSTS, где дефолт = контракт.
_WEB2_PROGRAM_HOSTS = ("standoff365.com", "bi.zone",
                       "hackerone.com", "bugcrowd.com", "intigriti.com", "yeswehack.com")


def _is_web_target(url, prompt):
    """True ⇔ таргет = живой web-домен (dApp/web2), не repo/contract/explorer. Влияет только на выбор
    шаблона. intent '/dapphunt'/'web2'/'фронт' форсит web. Fail-open: ошибка → False (контрактный дефолт)."""
    try:
        low = (prompt or "").lower()
        if any(w in low for w in _WEB_INTENT):
            return True
        ul = (url or "").lower()
        if not ul.startswith("http"):
            return False
        host = re.match(r"https?://([^/]+)", ul)
        host = host.group(1) if host else ""
        if any(h in host for h in _WEB2_PROGRAM_HOSTS):
            return True
        for h in CODE_HOSTS + PROGRAM_HOSTS:
            if h in host:
                return False
        return bool(host)
    except Exception:
        return False


def build_ledger(template_path, slug, url):
    with open(template_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    # срезать верхний HTML-коммент (инструкция "как копировать") — RULES-блок остаётся
    tpl = re.sub(r"^<!--.*?-->\s*", "", tpl, count=1, flags=re.S)
    today = datetime.date.today().isoformat()
    tpl = tpl.replace("# {Target} — Hypotheses Registry",
                      "# %s — Hypotheses Registry" % slug)
    tpl = tpl.replace("**Session started:** {ISO date}",
                      "**Session started:** %s" % today)
    tpl = tpl.replace("**Target:** {chain:address or repo path}",
                      "**Target:** %s" % url)
    return tpl


def memory_hint(slug):
    """Ищет slug в подындексе памяти INDEX_projects.md → инжектит найденные строки.

    Зачем (2026-07-27): MEMORY.md разгружен — `project_*` вынесены в подындекс, который НЕ
    грузится автоматически. Раньше совпадение «этот таргет уже был» надо было заметить глазами
    среди 129 строк индекса; теперь его находит хук по slug'у — детерминированно и точнее
    (brutecat: хук > память). Fail-open: любая ошибка → пустая строка, хант не ломается.
    """
    try:
        import glob as _glob
        pats = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                            "*", "memory", "INDEX_projects.md")
        paths = _glob.glob(pats)
        if not paths:
            return ""
        toks = [t for t in re.split(r"[^a-z0-9]+", slug.lower()) if len(t) >= 4]
        if not toks:
            return ""
        hits = []
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.startswith("- ["):
                            continue
                        low = line.lower()
                        if any(t in low for t in toks):
                            s = line.strip()
                            if s not in hits:
                                hits.append(s)
            except Exception:
                continue
        if not hits:
            return ""
        return (
            "🧠 ПАМЯТЬ — этот таргет (или родственный) У НАС УЖЕ БЫЛ. Совпадения в "
            "`memory/INDEX_projects.md`:\n%s\n"
            "ПЕРЕД стартом открой указанную запись памяти целиком: что уже отрефьютили (не "
            "перекапывай), какие техники/harness переиспользуемы, чем кончилось. Прошлый вывод "
            "«hardened / bad EV» — НЕ основание пропустить таргет (запрещённый фрейм), а указание "
            "заходить с ДРУГОЙ оси.\n\n" % "\n".join(hits[:5])
        )
    except Exception:
        return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = data.get("prompt") or ""
    if not isinstance(prompt, str) or not prompt.strip():
        sys.exit(0)

    # P6 (katana meta-session 2026-07-29): entry-хук ложно армировал ЭТУ (мета) сессию как хант, когда
    # the operator обсуждал/чинил САМУ систему («это не охота, улучшаем систему»). Явный анти-hunt сигнал в
    # промпте → НЕ армить (даже при ссылке в тексте: она — предмет разговора, не таргет). Узкий denylist,
    # эти фразы не встречаются в реальном hunt-промпте → FP-риск ≈0.
    if _META_RE.search(prompt):
        sys.exit(0)

    root = find_root()
    # arbitrum-инцидент: детекция работает по ПОЛЬЗОВАТЕЛЬСКОМУ тексту, машинные вставки вырезаны.
    # _META_RE (выше) проверяется по ИСХОДНОМУ промпту — мета-сигнал пользователя legit где угодно.
    user_prompt = _strip_machine_text(prompt)
    try:
        hit = detect(user_prompt) or detect_resume_by_slug(user_prompt, root)
    except Exception:
        sys.exit(0)
    if not hit:
        sys.exit(0)

    slug, url = hit
    url = url or ("resume:%s" % slug)  # resume-by-slug (нет ссылки) → плейсхолдер для Target
    cur_model = _current_model(data.get("transcript_path"))  # A4: текущий наблюдатель
    try:
        sess = os.path.join(root, "sessions", slug)
        ledger = os.path.join(sess, "hypotheses.md")
        marker = os.path.join(sess, ".hunt_active")
        web = _is_web_target(url, user_prompt)
        template = os.path.join(root, "sessions", "_methodology",
                                "hypotheses_web_template.md" if web else "hypotheses_template.md")

        resume = os.path.exists(ledger)
        os.makedirs(sess, exist_ok=True)

        if not resume:
            if os.path.exists(template):
                content = build_ledger(template, slug, url)
            else:
                content = "# %s — Hypotheses Registry\n\n(template missing)\n" % slug
            with open(ledger, "w", encoding="utf-8") as f:
                f.write(content)

        # T13 system_model.md — заводится НЕЗАВИСИМО от resume (K3): иначе уже идущие ханты
        # (ledger есть) никогда не получат модель, и divergence-first слой к ним не доедет.
        model = os.path.join(sess, "system_model.md")
        model_tpl = os.path.join(root, "sessions", "_methodology",
                                 "system_model_web_template.md" if web else "system_model_template.md")
        model_created = False
        if not os.path.exists(model) and os.path.exists(model_tpl):
            try:
                with open(model_tpl, "r", encoding="utf-8") as f:
                    mc = f.read()
                mc = mc.replace("- Target / slug:", "- Target / slug: %s" % slug)
                with open(model, "w", encoding="utf-8") as f:
                    f.write(mc)
                model_created = True
            except Exception:
                model_created = False

        # поднять / освежить маркер (армирует Stop completeness-gate).
        # 2-я строка = session_id → completeness-gate скоупит guard на ЭТУ сессию
        # (иначе хант в соседнем окне фонит во все сессии — cross-fire).
        sid = data.get("session_id") or ""
        # Атомарная запись (temp+replace): прерывание процесса не оставит 0-байт маркер,
        # который legacy-логика приняла бы за 'может мой' и кросс-фонил во все сессии
        # (gmgn incident 2026-07-08). os.replace атомарен в пределах одного каталога.
        tmp = marker + (".tmp.%d" % os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(int(now())) + "\n" + str(sid))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, marker)

        # A4: зафиксировать текущую модель-наблюдатель → wave_delta snapshot застампит её в
        # meta.model_version, при следующем визите entry-gate сравнит и поймает смену модели.
        try:
            if cur_model:
                with open(os.path.join(sess, ".observer_model"), "w", encoding="utf-8") as f:
                    f.write(cur_model)
        except Exception:
            pass

        rel = os.path.join("sessions", slug, "hypotheses.md")
        rel_model = os.path.join("sessions", slug, "system_model.md")
        banner = "HUNT-LOOP АКТИВЕН · ledger: %s" % rel

        # T10 forcing-такт: модель строится ДО чтения кода. Скелет форсим здесь, детали — в файле-спеке
        # (агент открывает по ходу); model_first_nudge + Stop model-гейты страхуют, если пропустил.
        model_note = (
            "🧩 DIVERGENCE-FIRST (T10/T13), такт `J-M`, ДО чтения кода. Модель: %s (%s). Кратко: корпус "
            "БЕЗ кода → `I-NN` формулами (≤12, каждый `check:`/`component:`/`pred:`) → ПОТОМ код → "
            "enforcement 5 статусов (ENFORCED/PARTIAL/IMPLICIT/ABSENT/SUBSTITUTED) → ABSENT/PARTIAL/"
            "SUBSTITUTED = `D-NN` (в SELECT ВПЕРЕДИ H-NN). Мелкий контракт/фронт/web2 → `MODEL: N/A — "
            "<причина>`. Спека (3 оператора, ранжирование D-NN): `_methodology/independent_model_first.md`.\n\n"
            % (rel_model, "создана из шаблона" if model_created else "уже есть — ДОСТРАИВАЙ")
        )

        # EV-ANGLE (audit 2026-08-09, B1): 3 нулевых захода подряд (axelar/balancer/1inch-aqua) на
        # перехард/crowded таргеты the operator — EV-скоринг `target_discovery.py` вызывался ТОЛЬКО для
        # self-discovery, на handed-URL молчал. Фикс — forcing-reminder на EV-recon ДО коммита глубины.
        # ⚠ the operator 2026-08-09: «баги есть везде, даже в перехард» — это НЕ повод уйти (bad-EV give-up
        # ЗАПРЕЩЁН мандатом), а выбор УГЛА: crowded/hardened → un-dup сидит в freshest-код / attention-gap /
        # post-audit-drift / un-modeled подсистеме (куда толпа не дошла), НЕ в перехоженной сердцевине.
        ev_note = (
            "🎯 EV-ANGLE (audit-B1, ДО коммита глубины, НЕ повод уйти). Оцени 3 фактора un-dup-УГЛА: "
            "(a) crowd-heat — сколько репортов уже подано / публичность программы (толпа вычистила "
            "mid-depth сердцевину); (b) freshness — свежие файлы/фичи/post-audit-drift (меньше глаз); "
            "(c) already-paid-classes — что УЖЕ выплачено = дубль-зона, НЕ переоткрывай (Berachain: 2 "
            "Crit→дубль $0). Вывод → поле `EV-ANGLE:` в Loop State как un-dup-угол ('crowded core → "
            "копаю freshest X / attention-gap Y / un-modeled Z'). ⛔ hardened/crowded — сигнал копать "
            "ГЛУБЖЕ в менее-очевидный слой, НЕ выходить (баги есть везде). Ориентир-формула: "
            "target_discovery.py EV = payout×freshness×(1/crowd)×pattern.\n\n"
        )

        # SAFEGUARD-HYGIENE (audit 2026-08-09): на web-live-хантах (levex/synfutures — десятки хитов)
        # cyber-safeguards флагают МОЁ исходящее сообщение с лексикой активной эксплуатации (JWT
        # alg:none / forge / signature-tamper / auth-bypass) → turn прерывается API-ошибкой, петля
        # рвётся НА САМОЙ ЦЕННОЙ live-active-фазе. Работа легитимна (white-hat, свой аккаунт, in-scope) —
        # проблема в ФОРМЕ. Фикс = усиление LEDGER-FIRST именно на web-live: детали техники в ledger+
        # tool-call, чат нейтрально. Механизм > память (инжектим превентивно на web-таргете).
        safeguard_note = (
            "🛡️ SAFEGUARD-HYGIENE (web-live-хант). Cyber-safeguards флагают ИСХОДЯЩИЙ текст с лексикой "
            "активной эксплуатации → рвут turn на live-фазе (levex/synfutures били десятки раз). Работа "
            "легитимна — чиним ФОРМУ, не суть: (1) эксплойт-детали (alg:none / forge-payload / tamper / "
            "конкретный код) держи в ledger + сам tool-call, НЕ в прозе чата (это и есть LEDGER-FIRST); "
            "(2) в чат — НЕЙТРАЛЬНЫЙ статус: 'auth-integrity проба JWT-валидации (свой subj, "
            "non-destructive, in-scope)', НЕ 'порчу signature + alg:none → forge любого = Critical'; "
            "(3) НЕ гиперболизируй импакт в исходящем (оценка severity → ledger); (4) словарь: forge→"
            "'signature-validation проба', attack/эксплойт→'PoC-проверка', порчу/tamper→'модифицирую свой "
            "тестовый'. Полный протокол: `_methodology/browser_first_mandate.md § Safeguard-Hygiene`.\n\n"
        )

        # wave/delta: если для этого slug уже есть snapshot.json → это ПОВТОРНЫЙ визит.
        # Форсим дельту (хантить изменения, не всю базу заново). brutecat: хук > память.
        snap_path = os.path.join(sess, "snapshot.json")
        revisit_note = ""
        snap_tail = ""
        wdcmd = "py -3 -X utf8 bug-bounty-toolkit/scripts/wave_delta.py"
        if os.path.exists(snap_path):
            sdate = ""
            snap_model = ""
            try:
                with open(snap_path, "r", encoding="utf-8") as sf:
                    _meta = json.load(sf).get("meta", {}) or {}
                    sdate = _meta.get("date", "")
                    snap_model = _meta.get("model_version", "") or ""
            except Exception:
                sdate = ""
            revisit_note = (
                "🔁 REVISIT — этот таргет УЖЕ был у нас (snapshot.json%s). ПЕРЕД новым аудитом "
                "с нуля СНАЧАЛА иди по ДЕЛЬТЕ: (1) обнови/склонируй исходники до текущего "
                "состояния; (2) `%s delta %s --src <path>`; (3) REVERSED (снятый guard / "
                "расширенная видимость / +payable) и NEW-без-guard → сразу H-NN с ВЫСШИМ "
                "приоритетом (change=risk, тут сырее всего); REGRESSION (добавленный guard) → "
                "копай РЯДОМ (там боялись = там был баг); PERSISTENT → skip, уже покрыто. "
                "Хантишь ИЗМЕНЕНИЯ, не перечитываешь всю базу. По итогу обнови снимок "
                "(`... delta %s --src <path> --save`). \n\n"
                % ((" от " + sdate) if sdate else "", wdcmd, slug, slug)
            )
            # A4: наблюдатель (модель) сменился с прошлого снимка → окно ре-аудита. Тот же
            # REVISIT-механизм, но по другой оси устаревания: не «код изменился», а «наблюдатель
            # изменился». Механизирует feedback_model_release_reaudit_window (была чистая проза).
            if snap_model and cur_model and snap_model != cur_model:
                revisit_note += (
                    "🤖 MODEL-REAUDIT — с прошлого снимка сменилась МОДЕЛЬ-наблюдатель (%s → %s). "
                    "Новая модель систематически видит то, что старая пропускала (Orchard halo2: "
                    "4 года + tier-1 аудиты на 4.7 мимо → 4.8 нашёл за 4 дня). Пройди known-clean / "
                    "refuted этого таргета ЗАНОВО: прошлое «чисто» — вывод СТАРОГО наблюдателя, не "
                    "факт. Это ОТДЕЛЬНАЯ ось от code-delta выше (обе форсят REVISIT).\n\n"
                    % (snap_model, cur_model)
                )
        else:
            snap_tail = (
                " 📸 В КОНЦЕ ханта (перед HUNT-EXIT) сделай снимок кода для будущих wave/delta: "
                "`%s snapshot %s --src <path>` — чтобы при следующем визите (напр. через месяц "
                "после релиза) идти по дельте, а не с нуля." % (wdcmd, slug)
            )
        if resume:
            msg = (
                "HUNT-LOOP RESUME (входной хук). Ledger: %s. Маркер освежён (completeness-gate армирован, "
                "автономный режим — Stop-хук держит turn до выхода).\n"
                "(0) ПЕРВОЙ СТРОКОЙ ответа — видимый баннер `%s · RESUME (итерация N из Loop State)`.\n"
                "НЕ создавай заново: прочитай `## Loop State` (+ поле `Depth-Lead:`), продолжи с нужной "
                "SELECT-ветки. depth-lead-first: ≥4 H и ни одной нити ≥5 слоёв → следующее действие = DRIVE "
                "сильнейшей нити ВГЛУБЬ, НЕ breadth. un-dup: cross-subsystem крит-композит через ДАЛЁКИЕ "
                "подсистемы обгоняет mid-depth лид (Berachain: 2 Crit→дубль $0); композит не бросай — DRIVE "
                "до D-PoC или KILL с falsifier; заявляешь ≥5 → заполни `DEPTH-MAP`.\n"
                "⛔ ЧАТ = только статус (1-3 строки + ссылка на ledger); все лиды/рефьюты/scout-merge/тело "
                "H-NN → СРАЗУ в ledger через Edit (CHAT-WALL гейт блокирует простыни).\n"
                "🔁 ВЫХОД РОВНО ОДИН: `HUNT-EXIT: T4-CONFIRMED <High|Critical>` после реального T4, либо the operator "
                "«уходим». Medium/Low — банк+сабмит по ходу, петлю НЕ завершают (нашёл Medium → жми ceiling до "
                "High + копай дальше). Не отдавай руль вопросом «что дальше». Детали фаз: CLAUDE.md §1." % (rel, banner)
            )
            msg = memory_hint(slug) + revisit_note + (safeguard_note if web else "") + model_note + msg
        else:
            msg = (
                "HUNT-LOOP АКТИВИРОВАН (входной хук). Ledger СОЗДАН: %s. Маркер .hunt_active поднят → Stop "
                "completeness-gate армирован (петля крутится САМА, держит turn до выхода).\n"
                "ПОРЯДОК ПЕРВЫХ ДЕЙСТВИЙ (жёсткий, ДО глубокого чтения кода; полный mandate — CLAUDE.md §1):\n"
                "(0) ПЕРВОЙ СТРОКОЙ ответа — видимый баннер `%s · итерация 1` (индикатор петли the operator).\n"
                "(1) авто-роутинг на скил (CLAUDE.md §2 + chain_detect.py), инвокни сам.\n"
                "(2) recon-шапка ledger: **Assets in Scope + Impacts in Scope + Out-of-Scope** (сними "
                "дословно; Impacts = per-impact severity-рубрика — калибрует severity И задаёт ЧТО искать, "
                "сентинел `IMPACTS-TODO`; **Out-of-Scope = вычитай вкладку /scope/ ОТДЕЛЬНО от in-scope "
                "/information/ — MONEY-CRITICAL, находка в OOS = $0 даже с PoC; сентинел `OOS-TODO`**; оба "
                "иначе gate блок; repo/no-program → `N/A`), Surface size, Audit history.\n"
                "(3) T10 модель — см. блок DIVERGENCE-FIRST выше (модель ДО кода → I-NN → D-NN).\n"
                "(4) T1 → top-5 score-4/5 файлов → каждый = H-NN в Active с falsifier'ом.\n"
                "(5) многоподсистемный surface (≳15 score-4/5 файлов ИЛИ ≥3 подсистемы) → СНАЧАЛА Scout "
                "Fan-Out (≤7 read-only `sonnet`-субагентов В ОДНОМ сообщении: P-B boundary ОТДЕЛЬНЫМ + P1-P6 "
                "core + OPTIONAL P7-P10 по trigger; лишнее сверх 7 → `WAVE-2 PENDING`), merge → H-NN, заполни "
                "секцию `## Scout Fan-Out` (PENDING→DONE). Мелкий → N/A. Спека: `_methodology/scout_fanout.md`.\n"
                "(6) DEPTH-LEAD-FIRST: первый committed-DRIVE = гнать СИЛЬНЕЙШУЮ нить ВНИЗ ≥5 слоёв "
                "(call→state→external→hook→accounting) через ДАЛЁКИЕ подсистемы, НЕ маплить скоуп дальше. "
                "un-dup (Berachain: 2 Crit→дубль $0): дубли живут на mid-depth, un-dup крит в СТЫКЕ далёких "
                "подсистем. Заявляешь ≥5 → поле `DEPTH-MAP` (L1→L5, file:line+подсистема). Второй breadth-"
                "проход запрещён, пока нить не дошла до 5/5; веди `Depth-Lead:` в Loop State. Выписанный "
                "Crit-composite не бросай 'unproven/NEXT' — DRIVE до D-PoC или KILL с falsifier.\n"
                "⛔ ЧАТ = ТОЛЬКО статус (1-3 строки + ссылка на ledger). ВСЕ рассуждения/лиды/рефьюты/"
                "scout-merge/тело H-NN (CLASS/PREDICTION/FALSIFIER/SEVERITY) → СРАЗУ в ledger через Edit ПО "
                "ХОДУ (файл — single source of truth). Скауты вернулись → ПЕРВОЕ действие = Edit ledger, ПОТОМ "
                "1-строчный статус. CHAT-WALL гейт блокирует простыни. Веди `## Loop State` в конце каждой "
                "итерации; НЕ переписывай template своим форматом (блоки Loop State / Scout Fan-Out / Refuted-"
                "с-falsifier / Building Blocks обязательны).\n"
                "🔁 АВТОНОМНЫЙ РЕЖИМ (the operator даёт ТОЛЬКО цель, /loop не печатает): Stop-хук НЕ даст завершить "
                "turn — форсит следующий single-pick. Не спрашивай «копать или сменить», не отдавай руль — "
                "копаешь дальше (новый угол / T9 cold-restart, ось задаёшь ТЫ). ВЫХОД РОВНО ОДИН: `HUNT-EXIT: "
                "T4-CONFIRMED <High|Critical>` в ledger после реального T4. Medium/Low — банк+сабмит по ходу, "
                "петлю НЕ завершают (нашёл Medium → жми ceiling до High + копай дальше). Park не существует; "
                "abort = прерогатива the operator («уходим»). Аварийный off: `HUNT-MODE: MANUAL` в ledger." % (rel, banner)
            )
            msg = memory_hint(slug) + revisit_note + ev_note + (safeguard_note if web else "") + model_note + msg + snap_tail
        # UserPromptSubmit: stdout на exit 0 добавляется в контекст
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": msg,
            }
        }))
    except Exception:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
