# -*- coding: utf-8 -*-
"""supply_chain_scan — npm supply-chain recon-producer (FDE План 7, TIER D §63, Р9).

Единственный greenfield плана. npm-SPECIFIC recon-генератор над РЕАЛЬНЫМ dependency-графом таргета
(`package.json` + `package-lock.json`/`yarn.lock` + опц. `.npmrc`). Четыре детект-класса:

  1. dependency-confusion — internal-scoped пакет (`@org/…`, не публичный scope / помечен private в
     .npmrc) резолвится из ПУБЛИЧНОГО npm ЛИБО не запинен в lock → атакующий может зашедоуить имя.
  2. typosquat — bare-имя на edit-distance 1-2 от популярного пакета (install-time confusion).
  3. unclaimed-package — dep из манифеста отсутствует в lock (резолв на install) / spec на
     non-registry источник (git/url/file/github-shorthand) / lock-entry без resolved+integrity
     (origin неверифицируем — оффлайн-суррогат «в registry нет»).
  4. lockfile-injection — resolved-host = чужой/необъявленный registry / tarball-путь именует ДРУГОЙ
     пакет (подмена) / один `name@version` несёт РАЗНЫЕ integrity-хэши (mismatch/tamper).

⚠ ОТЛИЧИЕ ОТ generic `third-party-seam` (§46.3): third-party-seam — абстрактная un-dup-ЛИНЗА доверия
(«граница A доверяет внешнему B без валидатора»), применимая к любой интеграции. ЭТОТ producer —
npm-SPECIFIC: он рассуждает над КОНКРЕТНЫМ package.json/lock-графом npm-экосистемы (scopes, registry
hosts, integrity-хэши, tarball-layout `/-/`), а не над обобщённой границей. Питает web2 `supply-chain`
AC-ось модели (`system_model_web_template.md`), а не generic third-party-seam.

Producer-паттерн (как `authz_diff.py`/`composition_map.py`): читает манифесты → пишет co-located
артефакт `{session_dir}/supply_chain.md` (toolkit-rooted session-dir — ПАРАМЕТР, не хардкод голого
`sessions/$DOMAIN`) → находки-ЛИДЫ питают supply-chain ось. Оффлайн-эвристики (без сетевого запроса к
registry) — каждая находка это ЛИД, верифицируй перед D-NN. **Fail-open:** нет манифеста / битый
JSON / любой сбой скана → пустой список, артефакт всё равно пишется, хант НЕ падает.

Публичный контракт:
    parse_package_json(text) -> {name, deps: {name: spec}, dev: set}
    parse_package_lock(text) -> {name: [entry, ...]}          # npm v1 + v2/v3
    parse_yarn_lock(text)    -> {name: [entry, ...]}          # yarn v1
    parse_npmrc(text)        -> {scopes: {@scope: url}, registries: set(host)}
    detect_dependency_confusion(deps, lock_index, npmrc=None) -> [finding]
    detect_typosquat(deps)                                    -> [finding]
    detect_unclaimed(deps, lock_index)                        -> [finding]
    detect_lockfile_injection(lock_index, allowed_registries=None) -> [finding]
    scan(package_json_text, lock_text=None, lock_kind=None, npmrc_text=None) -> [finding]
    run_supply_chain_scan(session_dir, package_json_path=None, lock_path=None, npmrc_path=None) -> str

CLI:
    py -3 -X utf8 supply_chain_scan.py --session-dir bug-bounty-toolkit/sessions/example.com \
        --target-dir path/to/cloned/target
    py -3 -X utf8 supply_chain_scan.py --session-dir <dir> --package-json a/package.json --lock a/package-lock.json
"""
import os
import re
import json
import argparse


# ---------------------------------------------------------------------------
# Корпус: публичные scopes (легитимно на public npm) + популярные пакеты (typosquat-эталон)
# ---------------------------------------------------------------------------

# Известные ПУБЛИЧНЫЕ scopes — их наличие на public npm легитимно, dependency-confusion НЕ флагает.
# (не исчерпывающий — расширять по мере; неизвестный scope трактуется как «возможно internal».)
KNOWN_PUBLIC_SCOPES = {
    "@types", "@babel", "@angular", "@angular-devkit", "@vue", "@nestjs", "@storybook",
    "@testing-library", "@typescript-eslint", "@emotion", "@mui", "@material-ui", "@reduxjs",
    "@tanstack", "@octokit", "@aws-sdk", "@azure", "@google-cloud", "@sentry", "@grpc", "@apollo",
    "@graphql-tools", "@sinonjs", "@jest", "@eslint", "@rollup", "@vitejs", "@vitest", "@swc",
    "@next", "@remix-run", "@radix-ui", "@floating-ui", "@headlessui", "@heroicons", "@popperjs",
    "@open-telemetry", "@opentelemetry", "@noble", "@scure", "@ethersproject", "@solana",
    "@polkadot", "@wagmi", "@web3-react", "@openzeppelin", "@chainlink", "@nomiclabs",
    "@nomicfoundation", "@fastify", "@sveltejs", "@nuxt", "@nuxtjs", "@playwright", "@cypress",
    "@types-registry", "@fortawesome", "@react-navigation", "@expo", "@react-native-community",
    "@ledgerhq", "@walletconnect", "@trpc", "@prisma", "@supabase", "@clerk", "@auth0",
}

# Популярные bare-имена — эталон typosquat. edit-distance 1-2 от одного из них = кандидат.
POPULAR = {
    "react", "react-dom", "lodash", "express", "axios", "chalk", "commander", "debug", "moment",
    "request", "async", "bluebird", "underscore", "webpack", "jquery", "vue", "typescript",
    "eslint", "prettier", "dotenv", "uuid", "classnames", "redux", "react-redux", "next",
    "node-fetch", "cross-env", "rimraf", "glob", "yargs", "semver", "minimist", "colors", "ws",
    "mongoose", "body-parser", "cors", "jsonwebtoken", "bcrypt", "bcryptjs", "passport", "socket.io",
    "nodemon", "mocha", "chai", "jest", "sinon", "supertest", "winston", "morgan", "helmet",
    "fs-extra", "inquirer", "ora", "figlet", "qs", "form-data", "cheerio", "puppeteer", "playwright",
    "ethers", "web3", "bignumber.js", "bn.js", "elliptic", "tweetnacl", "sqlite3", "pg", "mysql2",
    "redis", "ioredis", "graphql", "apollo-server", "styled-components", "tailwindcss", "postcss",
    "babel-core", "core-js", "regenerator-runtime", "tslib", "zod", "yup", "joi", "date-fns",
    "react-router", "react-router-dom", "vite", "rollup", "esbuild", "svelte", "vitest",
}


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

PUBLIC_REGISTRIES = {"registry.npmjs.org", "registry.yarnpkg.com", "registry.npmmirror.com"}


def _host(url):
    """host из URL (`https://user@host:port/…` -> `host`). '' если не URL."""
    m = re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*://([^/]+)", url or "")
    if not m:
        return ""
    authority = m.group(1)
    if "@" in authority:
        authority = authority.split("@")[-1]
    return authority.split(":")[0].lower()


def _scope_of(name):
    """`@org/pkg` -> `@org` (lowercased); bare-имя -> ''."""
    if name.startswith("@") and "/" in name:
        return name.split("/", 1)[0].lower()
    return ""


def _f(cls, package, severity, detail, evidence):
    return {"cls": cls, "package": package, "severity": severity,
            "detail": detail, "evidence": evidence}


def _levenshtein(a, b, maxd=None):
    """edit-distance a↔b с ранним отсечением на maxd (возвращает None, если точно > maxd)."""
    la, lb = len(a), len(b)
    if maxd is not None and abs(la - lb) > maxd:
        return None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        rowmin = cur[0]
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            v = prev[j] + 1
            d = cur[j - 1] + 1
            if d < v:
                v = d
            d = prev[j - 1] + cost
            if d < v:
                v = d
            cur[j] = v
            if v < rowmin:
                rowmin = v
        if maxd is not None and rowmin > maxd:
            return None
        prev = cur
    return prev[lb]


# ---------------------------------------------------------------------------
# Парсеры манифестов
# ---------------------------------------------------------------------------

def parse_package_json(text):
    """`dependencies`/`optional`/`peer`/`dev` -> {name: spec}. dev-имена в set `dev`. Битый JSON ->
    пустой результат (fail-open)."""
    try:
        data = json.loads(text)
    except Exception:
        return {"name": None, "deps": {}, "dev": set()}
    if not isinstance(data, dict):
        return {"name": None, "deps": {}, "dev": set()}
    deps = {}
    dev = set()
    for field in ("dependencies", "optionalDependencies", "peerDependencies"):
        d = data.get(field)
        if isinstance(d, dict):
            for k, v in d.items():
                deps[k] = v if isinstance(v, str) else ""
    d = data.get("devDependencies")
    if isinstance(d, dict):
        for k, v in d.items():
            deps.setdefault(k, v if isinstance(v, str) else "")
            dev.add(k)
    return {"name": data.get("name"), "deps": deps, "dev": dev}


def _name_from_lock_path(path):
    """v2/v3 ключ `node_modules/@scope/name/node_modules/dep` -> имя ПОСЛЕДНЕГО сегмента (`dep`)."""
    marker = "node_modules/"
    i = path.rfind(marker)
    seg = (path[i + len(marker):] if i >= 0 else path).strip("/")
    if seg.startswith("@"):
        parts = seg.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else seg
    return seg.split("/")[0]


def parse_package_lock(text):
    """npm `package-lock.json` v1 (вложенный `dependencies`) + v2/v3 (`packages` по node_modules-пути).
    -> {name: [entry, ...]}, entry = {name, version, resolved, integrity}. Битый JSON -> {} (fail-open).
    v2/v3: читаем `packages` (legacy `dependencies` пропускаем, чтобы не двоить)."""
    index = {}
    try:
        data = json.loads(text)
    except Exception:
        return index
    if not isinstance(data, dict):
        return index

    def add(name, node):
        if not name or not isinstance(node, dict):
            return
        index.setdefault(name, []).append({
            "name": name,
            "version": node.get("version") or "",
            "resolved": node.get("resolved") or "",
            "integrity": node.get("integrity") or "",
        })

    packages = data.get("packages")
    if isinstance(packages, dict):
        for path, node in packages.items():
            if not path:  # "" = корневой проект, не зависимость
                continue
            add(_name_from_lock_path(path), node)
        return index

    def walk(depmap):
        if not isinstance(depmap, dict):
            return
        for name, node in depmap.items():
            add(name, node)
            if isinstance(node, dict):
                walk(node.get("dependencies"))

    walk(data.get("dependencies"))
    return index


def _split_yarn_specs(header):
    return [s.strip().strip('"') for s in header.split(",") if s.strip()]


def _yarn_spec_name(spec):
    """`@scope/name@^1.0.0` -> `@scope/name`; `lodash@^4.17` -> `lodash`."""
    spec = spec.strip().strip('"')
    if spec.startswith("@"):
        at = spec.rfind("@")
        return spec[:at] if at > 0 else spec
    at = spec.find("@")
    return spec[:at] if at > 0 else spec


def parse_yarn_lock(text):
    """yarn v1 lockfile -> {name: [entry, ...]}. Блок = header-строка (спеки, `:` на конце, колонка 0)
    + отступленные `version`/`resolved`/`integrity`. Fail-open (best-effort regex)."""
    index = {}
    lines = (text or "").splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if line and not line[0].isspace() and not line.lstrip().startswith("#") \
                and line.rstrip().endswith(":"):
            header = line.rstrip()[:-1]
            names = set()
            for s in _split_yarn_specs(header):
                nm = _yarn_spec_name(s)
                if nm:
                    names.add(nm)
            version = resolved = integrity = ""
            j = i + 1
            while j < n and (not lines[j] or lines[j][0].isspace()):
                body = lines[j].strip()
                m = re.match(r'version\s+"?([^"\s]+)"?', body)
                if m:
                    version = m.group(1)
                m = re.match(r'resolved\s+"?([^"\s]+)"?', body)
                if m:
                    resolved = m.group(1)
                m = re.match(r'integrity\s+([^\s"]+)', body)
                if m:
                    integrity = m.group(1)
                j += 1
            for nm in names:
                index.setdefault(nm, []).append({
                    "name": nm, "version": version,
                    "resolved": resolved, "integrity": integrity,
                })
            i = j
        else:
            i += 1
    return index


_NPMRC_SCOPE_RE = re.compile(r"^\s*(@[^:=\s]+):registry\s*=\s*(\S+)", re.I)
_NPMRC_DEFAULT_RE = re.compile(r"^\s*registry\s*=\s*(\S+)", re.I)


def parse_npmrc(text):
    """.npmrc -> {scopes: {@scope: registry-url}, registries: set(host)}. `@scope:registry=` даёт
    private-scope сигнал (dependency-confusion elevate); `registry=`/scope-registry hosts идут в
    allowed-set (lockfile-injection не флагает объявленный private registry как чужой)."""
    scopes = {}
    registries = set()
    for line in (text or "").splitlines():
        m = _NPMRC_SCOPE_RE.match(line)
        if m:
            scopes[m.group(1).lower()] = m.group(2)
            h = _host(m.group(2))
            if h:
                registries.add(h)
            continue
        m = _NPMRC_DEFAULT_RE.match(line)
        if m:
            h = _host(m.group(1))
            if h:
                registries.add(h)
    return {"scopes": scopes, "registries": registries}


# ---------------------------------------------------------------------------
# Детекторы (4 класса)
# ---------------------------------------------------------------------------

def detect_dependency_confusion(deps, lock_index, npmrc=None):
    """Internal-scoped пакет резолвится из ПУБЛИЧНОГО npm / не запинен → shadowing-кандидат.
    Internal = scope помечен private в .npmrc ЛИБО scope не в KNOWN_PUBLIC_SCOPES. Публичный scope
    без private-объявления пропускается (легитимен). Bare-имена вне класса (их кроют typosquat/
    unclaimed)."""
    npmrc = npmrc or {"scopes": {}, "registries": set()}
    private_scopes = npmrc.get("scopes", {})
    findings = []
    for name in sorted(deps):
        scope = _scope_of(name)
        if not scope:
            continue
        private_declared = scope in private_scopes
        known_public = scope in KNOWN_PUBLIC_SCOPES
        internal = private_declared or (not known_public)
        if not internal:
            continue
        entries = lock_index.get(name, [])
        pub_hosts = sorted({_host(e.get("resolved", "")) for e in entries
                            if _host(e.get("resolved", "")) in PUBLIC_REGISTRIES})
        resolved_public = bool(pub_hosts)
        no_lock = len(entries) == 0
        if private_declared and resolved_public:
            findings.append(_f(
                "dependency-confusion", name, "high",
                "scope %s declared PRIVATE in .npmrc but the lockfile resolves it from PUBLIC npm (%s) "
                "-> public shadowing / hijack: an attacker who owns the public name wins install"
                % (scope, ", ".join(pub_hosts)),
                "npmrc:%s=private; lock.resolved=public" % scope))
        elif private_declared and no_lock:
            findings.append(_f(
                "dependency-confusion", name, "high",
                "scope %s declared PRIVATE in .npmrc but the package is NOT pinned in the lockfile "
                "-> resolved fresh at install; attacker can shadow the name on public npm" % scope,
                "npmrc:%s=private; absent from lock" % scope))
        elif resolved_public:
            findings.append(_f(
                "dependency-confusion", name, "med",
                "internal-looking scope %s (not a known public scope) resolves from PUBLIC npm -> if "
                "the org treats %s as private, an attacker can register/shadow the name publicly"
                % (scope, scope),
                "scope not in public allowlist; lock.resolved=public"))
        elif no_lock:
            findings.append(_f(
                "dependency-confusion", name, "med",
                "internal-looking scope %s (not a known public scope) is not pinned in the lockfile "
                "-> resolved at install, dependency-confusion candidate" % scope,
                "scope not in public allowlist; absent from lock"))
    return findings


def detect_typosquat(deps):
    """bare-имя на edit-distance 1-2 от популярного пакета (не равное ему) → typosquat-кандидат."""
    findings = []
    for name in sorted(deps):
        if _scope_of(name):
            continue
        low = name.lower()
        if low in POPULAR or len(low) < 3:
            continue
        best = None
        for pop in POPULAR:
            if abs(len(pop) - len(low)) > 2:
                continue
            d = _levenshtein(low, pop, maxd=2)
            if d is not None and 1 <= d <= 2:
                if best is None or d < best[1]:
                    best = (pop, d)
        if best:
            findings.append(_f(
                "typosquat", name, "high" if best[1] == 1 else "med",
                "name '%s' is edit-distance %d from popular package '%s' -> possible typosquat / "
                "install-time confusion (a wrong char installs the attacker's package)"
                % (name, best[1], best[0]),
                "levenshtein('%s','%s')=%d" % (low, best[0], best[1])))
    return findings


_GIT_RE = re.compile(r"^(git\+|git://|github:|gitlab:|bitbucket:)", re.I)
_URL_RE = re.compile(r"^https?://", re.I)
_FILE_RE = re.compile(r"^(file:|link:|portal:)", re.I)
_SHORTHAND_RE = re.compile(r"^[\w.-]+/[\w.-]+(#.+)?$")


def _nonregistry_source(spec):
    """spec из package.json на non-registry источник -> тип; иначе ''."""
    s = (spec or "").strip()
    if not s:
        return ""
    if _GIT_RE.match(s):
        return "git"
    if _URL_RE.match(s):
        return "url-tarball"
    if _FILE_RE.match(s):
        return "local/link"
    if not s.startswith("@") and _SHORTHAND_RE.match(s) and not s.startswith("npm:"):
        return "github-shorthand"
    return ""


def detect_unclaimed(deps, lock_index):
    """Оффлайн-суррогат «в registry нет / подозрительный»: non-registry источник в spec; dep из
    манифеста отсутствует в lock (резолв на install); lock-entry без resolved+integrity (origin
    неверифицируем). «Отсутствует в lock» флагаем ТОЛЬКО когда lockfile реально дан (иначе тишина)."""
    findings = []
    have_lock = bool(lock_index)
    for name in sorted(deps):
        src = _nonregistry_source(deps.get(name, ""))
        if src:
            findings.append(_f(
                "unclaimed-package", name, "med",
                "dependency '%s' points at a non-registry source (%s) -> not a published/pinned npm "
                "tarball; origin is unverified and may be attacker-controlled" % (name, src),
                "spec=%r" % (deps.get(name, ""),)))
            continue
        entries = lock_index.get(name)
        if have_lock and entries is None:
            findings.append(_f(
                "unclaimed-package", name, "med",
                "dependency '%s' is declared in the manifest but MISSING from the lockfile -> resolved "
                "fresh at install (unpinned); hijackable if the name is unpublished/reclaimable" % name,
                "absent from lock index"))
            continue
        if entries:
            unverifiable = [e for e in entries
                            if not e.get("integrity") and not e.get("resolved")]
            if unverifiable and len(unverifiable) == len(entries):
                findings.append(_f(
                    "unclaimed-package", name, "low",
                    "lock entry for '%s' has neither `resolved` nor `integrity` -> origin unverifiable "
                    "(never fetched from a registry with a checksum)" % name,
                    "no resolved + no integrity"))
    return findings


def _resolved_name_mismatch(name, resolved):
    """npm tarball-layout `https://host/<pkg>/-/<file>.tgz`: имя из пути != ключ lock -> подмена."""
    if not resolved:
        return ""
    m = re.match(r"https?://[^/]+/(.+?)/-/", resolved)
    if not m:
        return ""
    path_name = m.group(1)
    if path_name.lower() != name.lower():
        return path_name
    return ""


def detect_lockfile_injection(lock_index, allowed_registries=None):
    """resolved-host чужой/необъявленный registry / tarball-путь именует ДРУГОЙ пакет / один
    name@version с РАЗНЫМИ integrity-хэшами. allowed_registries — hosts из .npmrc (объявленный private
    registry не флагается как чужой)."""
    allowed = set(PUBLIC_REGISTRIES)
    if allowed_registries:
        allowed |= {r for r in allowed_registries if r}
    findings = []
    for name in sorted(lock_index):
        entries = lock_index[name]
        for e in entries:
            resolved = e.get("resolved", "")
            host = _host(resolved)
            if host and host not in allowed:
                findings.append(_f(
                    "lockfile-injection", name, "high",
                    "lock entry for '%s' resolves from an undeclared registry host '%s' (not public "
                    "npm, not an .npmrc-declared private registry) -> tarball redirect / lockfile "
                    "injection candidate" % (name, host),
                    "resolved host=%s" % host))
            mism = _resolved_name_mismatch(name, resolved)
            if mism:
                findings.append(_f(
                    "lockfile-injection", name, "high",
                    "lock key '%s' resolves to a tarball whose path names a DIFFERENT package (%s) "
                    "-> substituted tarball" % (name, mism),
                    "resolved=%s" % resolved))
        byver = {}
        for e in entries:
            v = e.get("version", "")
            ig = e.get("integrity", "")
            if v and ig:
                byver.setdefault(v, set()).add(ig)
        for v, igs in byver.items():
            if len(igs) > 1:
                findings.append(_f(
                    "lockfile-injection", name, "high",
                    "package '%s@%s' appears with %d DIFFERENT integrity hashes in the lockfile -> "
                    "integrity mismatch / tampering" % (name, v, len(igs)),
                    "integrities=%s" % ", ".join(sorted(igs))))
    return findings


# ---------------------------------------------------------------------------
# Агрегатор
# ---------------------------------------------------------------------------

def _looks_like_yarn(text):
    """yarn.lock не JSON: если lstrip не начинается с `{` — трактуем как yarn."""
    return not (text or "").lstrip().startswith("{")


def scan(package_json_text=None, lock_text=None, lock_kind=None, npmrc_text=None):
    """Полный проход: парс манифестов -> 4 детектора -> список находок. Любой отдельный сбой парса
    fail-open (пустой вклад), скан не падает."""
    pj = parse_package_json(package_json_text) if package_json_text else {"deps": {}, "dev": set()}
    deps = pj.get("deps", {})
    npmrc = parse_npmrc(npmrc_text) if npmrc_text else {"scopes": {}, "registries": set()}
    lock_index = {}
    if lock_text:
        kind = lock_kind or ("yarn" if _looks_like_yarn(lock_text) else "npm")
        lock_index = parse_yarn_lock(lock_text) if kind == "yarn" else parse_package_lock(lock_text)
    findings = []
    findings += detect_dependency_confusion(deps, lock_index, npmrc)
    findings += detect_typosquat(deps)
    findings += detect_unclaimed(deps, lock_index)
    findings += detect_lockfile_injection(lock_index, allowed_registries=npmrc.get("registries"))
    return findings


# ---------------------------------------------------------------------------
# Writer — supply_chain.md (toolkit-rooted co-located)
# ---------------------------------------------------------------------------

_CLASSES = ["dependency-confusion", "typosquat", "unclaimed-package", "lockfile-injection"]
_SEV_ORDER = {"high": 0, "med": 1, "low": 2}


def _cell(s):
    return str(s).replace("|", "/").replace("\n", " ").strip()


def _write_report(out_path, findings, have_pj, have_lock):
    counts = {c: 0 for c in _CLASSES}
    for f in findings:
        counts[f["cls"]] = counts.get(f["cls"], 0) + 1
    ordered = sorted(findings, key=lambda f: (_CLASSES.index(f["cls"]) if f["cls"] in _CLASSES else 9,
                                              _SEV_ORDER.get(f["severity"], 9), f["package"]))
    lines = [
        "# supply_chain.md — npm supply-chain recon (scripts/web2/supply_chain_scan.py, §63)",
        "",
        "> npm-SPECIFIC producer (dependency-confusion / typosquat / unclaimed-package / "
        "lockfile-injection). ОТЛИЧИЕ ОТ generic `third-party-seam` (§46.3): третий — абстрактная",
        "> un-dup-линза доверия к любой внешней границе; ЭТОТ рассуждает над КОНКРЕТНЫМ npm-графом "
        "(scopes / registry hosts / integrity-хэши / tarball-layout). Питает web2 `supply-chain` AC-ось.",
        "> Оффлайн-эвристики (без сетевого запроса к registry) — каждая находка это ЛИД, верифицируй "
        "перед D-NN. Пусто = нет npm-surface / ничего не сработало, НЕ доказательство безопасности.",
        "",
        "Inputs: package.json=%s, lockfile=%s" % ("yes" if have_pj else "no",
                                                   "yes" if have_lock else "no"),
        "",
        "| Класс | Пакет | Severity | Что (лид) | Evidence |",
        "|---|---|---|---|---|",
    ]
    for f in ordered:
        lines.append("| %s | %s | %s | %s | %s |" % (
            f["cls"], _cell(f["package"]), f["severity"], _cell(f["detail"]), _cell(f["evidence"])))
    if not ordered:
        lines.append("| — | — | — | (нет находок) | — |")
    lines += [
        "",
        "## Per-class counts",
        "- dependency-confusion: %d" % counts["dependency-confusion"],
        "- typosquat: %d" % counts["typosquat"],
        "- unclaimed-package: %d" % counts["unclaimed-package"],
        "- lockfile-injection: %d" % counts["lockfile-injection"],
        "",
        "RESULT: supply-chain-scan, %d findings (dc=%d typo=%d unclaimed=%d lockinj=%d)" % (
            len(findings), counts["dependency-confusion"], counts["typosquat"],
            counts["unclaimed-package"], counts["lockfile-injection"]),
    ]
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _safe_read(path):
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def run_supply_chain_scan(session_dir, package_json_path=None, lock_path=None, npmrc_path=None):
    """Читает манифесты (fail-open), сканит, пишет `{session_dir}/supply_chain.md`. Возвращает путь.
    Нет ни одного манифеста / любой сбой -> артефакт с 0 находок ВСЁ РАВНО пишется (producer никогда
    не крашит хант)."""
    session_dir = str(session_dir)
    os.makedirs(session_dir, exist_ok=True)
    out_path = os.path.join(session_dir, "supply_chain.md")
    pj_text = _safe_read(package_json_path)
    lock_text = _safe_read(lock_path)
    npmrc_text = _safe_read(npmrc_path)
    try:
        findings = scan(pj_text, lock_text, None, npmrc_text)
    except Exception:
        findings = []  # fail-open — никогда не роняем хант
    _write_report(out_path, findings, pj_text is not None, lock_text is not None)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _first_existing(target_dir, names):
    for nm in names:
        p = os.path.join(target_dir, nm)
        if os.path.isfile(p):
            return p
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="supply_chain_scan — npm dependency-confusion/typosquat/unclaimed/lockfile-injection "
                    "recon-producer (FDE Plan 7, §63)")
    ap.add_argument("--session-dir", required=True,
                    help="toolkit-rooted session dir, e.g. bug-bounty-toolkit/sessions/example.com")
    ap.add_argument("--package-json", help="path to target package.json")
    ap.add_argument("--lock", help="path to target package-lock.json / npm-shrinkwrap.json / yarn.lock")
    ap.add_argument("--npmrc", help="path to target .npmrc (optional — sharpens dependency-confusion)")
    ap.add_argument("--target-dir",
                    help="dir to auto-discover package.json / lockfile / .npmrc (explicit flags win)")
    args = ap.parse_args(argv)

    pj, lock, npmrc = args.package_json, args.lock, args.npmrc
    if args.target_dir:
        pj = pj or _first_existing(args.target_dir, ["package.json"])
        lock = lock or _first_existing(
            args.target_dir, ["package-lock.json", "npm-shrinkwrap.json", "yarn.lock"])
        npmrc = npmrc or _first_existing(args.target_dir, [".npmrc"])

    out_path = run_supply_chain_scan(args.session_dir, pj, lock, npmrc)
    print("wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
