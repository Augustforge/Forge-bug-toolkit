#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Presence-lint: web2 payload-справочники (FDE План 5, Task 7).

Проверяет:
  (a)/(b) в `scripts/web2/payloads/` лежат все 10 ожидаемых .md файлов (bola,
      bfla, bopla, jwt, oauth2, mass_assignment, blind_ssrf, rate_limit, cors, ssrf_bypass)
  (c) каждый несёт секцию `## Detection Signal`
  (d)-(m) secrets-regex (владелец: `scripts/cicd_leak_scanner.py`,
      `SECRET_REGEXES` dict) матчит все 6 форматов GitHub-токенов + AWS/Google/Slack/JWT/
      private-key/Discord, и НЕ матчит чистую строку без секретов.

Доказывает FIRING (не no-op): те же directory-проверки прогоняются против СИНТЕТИЧЕСКОГО неполного
temp-каталога (3 файла вместо 10, один без `## Detection Signal`) — обязаны FAIL хотя бы часть
проверок. Прогон против реального `payloads/` — обязаны PASS все. Без этого сравнения тест был бы
vacuous (грепнул бы 10 файлов один раз и не доказал, что умеет ловить регресс).

Запуск: py -3 -X utf8 scripts/web2/web2_payloads_lint.py
"""
import glob
import os
import sys
import tempfile

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt

PAYLOADS_DIR = os.path.join(ROOT, "scripts", "web2", "payloads")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")

EXPECTED_FILES = [
    "bola.md", "bfla.md", "bopla.md", "jwt.md", "oauth2.md", "mass_assignment.md",
    "blind_ssrf.md", "rate_limit.md", "cors.md", "ssrf_bypass.md",
]

sys.path.insert(0, SCRIPTS_DIR)
from cicd_leak_scanner import SECRET_REGEXES  # noqa: E402 — владелец secrets-regex


def check(results, name, cond, detail=""):
    results.append((name, bool(cond), detail))


def lint_payload_dir(directory, label):
    """Directory-level presence-проверки (a)-(c). Возвращает список (name, bool, detail)."""
    results = []

    files = sorted(glob.glob(os.path.join(directory, "*.md"))) if os.path.isdir(directory) else []
    check(results, "(a) [%s] >=10 .md файлов в %s" % (label, directory), len(files) >= 10,
          "найдено %d" % len(files))

    missing_expected = [f for f in EXPECTED_FILES
                         if not os.path.exists(os.path.join(directory, f))]
    check(results, "(b) [%s] все 10 ожидаемых файлов присутствуют" % label,
          len(missing_expected) == 0,
          ("отсутствуют: %s" % ", ".join(missing_expected)) if missing_expected else "")

    no_detection = []
    for f in files:
        text = open(f, encoding="utf-8").read()
        if "## Detection Signal" not in text:
            no_detection.append(os.path.basename(f))
    check(results, "(c) [%s] каждый .md несёт '## Detection Signal'" % label,
          len(no_detection) == 0,
          ("без секции: %s" % ", ".join(no_detection)) if no_detection else "")

    return results


def make_incomplete_dir():
    """Синтетический неполный каталог для доказательства FIRING: 3 файла (не 10), один без
    '## Detection Signal'. Directory-проверки (a)-(c) обязаны FAIL здесь."""
    d = tempfile.mkdtemp(prefix="web2_payloads_incomplete_")
    with open(os.path.join(d, "bola.md"), "w", encoding="utf-8") as f:
        f.write("# BOLA\n\n## Payloads\n...\n\n## Detection Signal\n...\n\n## Anti-FP\n...\n")
    with open(os.path.join(d, "jwt.md"), "w", encoding="utf-8") as f:
        f.write("# JWT\n\n## Payloads\n...\n")  # намеренно без '## Detection Signal'
    with open(os.path.join(d, "cors.md"), "w", encoding="utf-8") as f:
        f.write("# CORS\n\n## Payloads\n...\n\n## Detection Signal\n...\n")
    return d


def secrets_checks():
    """Юнит-проверки на SECRET_REGEXES (владелец cicd_leak_scanner.py)."""
    results = []
    gh = SECRET_REGEXES["github_token"]

    github_samples = {
        "ghp_": "ghp_1234567890abcdef1234567890abcdef1234",
        "gho_": "gho_1234567890abcdef1234567890abcdef1234",
        "ghu_": "ghu_1234567890abcdef1234567890abcdef1234",
        "ghs_": "ghs_1234567890abcdef1234567890abcdef1234",
        "ghr_": "ghr_1234567890abcdef1234567890abcdef1234",
        "github_pat_": "github_pat_11ABCDEFG0123456789abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    }
    for label, sample in github_samples.items():
        check(results, "(d) github_token матчит формат '%s' (все 6 GitHub-форматов)" % label,
              gh.search(sample) is not None, sample)

    check(results, "(e) github_token НЕ матчит чистую строку 'hello world'",
          gh.search("hello world") is None)

    check(results, "(f) aws_access_key матчит AKIA-строку",
          SECRET_REGEXES["aws_access_key"].search("AKIAABCDEFGHIJKLMNOP") is not None)

    check(results, "(g) google_api матчит AIza-строку",
          SECRET_REGEXES["google_api"].search("AIza" + "A" * 35) is not None)

    check(results, "(h) slack_token матчит xoxb-строку",
          SECRET_REGEXES["slack_token"].search("xoxb-1234567890-abcdefghij") is not None)

    check(results, "(i) jwt-регекс матчит eyJ...-строку",
          SECRET_REGEXES["jwt"].search(
              "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
              "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
          ) is not None)

    check(results, "(j) private_key-регекс матчит BEGIN-строку",
          SECRET_REGEXES["private_key"].search("-----BEGIN RSA PRIVATE KEY-----") is not None)

    check(results, "(k) discord_token присутствует в SECRET_REGEXES и матчит",
          "discord_token" in SECRET_REGEXES
          and SECRET_REGEXES["discord_token"].search(
              "N" + "A" * 23 + "." + "B" * 6 + "." + "C" * 27
          ) is not None)

    check(results, "(l) discord_token НЕ матчит чистую строку 'hello world'",
          "discord_token" in SECRET_REGEXES
          and SECRET_REGEXES["discord_token"].search("hello world") is None)

    return results


def _print_results(results):
    ok = sum(1 for _, p, _ in results if p)
    for n, p, d in results:
        print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
    print("  %d/%d\n" % (ok, len(results)))
    return ok, len(results)


def main():
    print("=== WEB2 PAYLOADS LINT (FDE План 5, Task 7) ===\n")

    print("-- РЕАЛЬНЫЙ payloads/ (directory-проверки обязаны PASS) --")
    real_results = lint_payload_dir(PAYLOADS_DIR, "real")
    real_ok, real_total = _print_results(real_results)
    real_all_pass = real_ok == real_total

    print("-- СИНТЕТИЧЕСКИЙ неполный каталог (обязан FAIL — доказывает FIRING) --")
    incomplete_dir = make_incomplete_dir()
    try:
        incomplete_results = lint_payload_dir(incomplete_dir, "incomplete")
        inc_ok, inc_total = _print_results(incomplete_results)
        firing_proved = inc_ok < inc_total
        print(("  [PASS] " if firing_proved else "  [FAIL] ")
              + "FIRING доказан: синтетический каталог проваливает хотя бы одну проверку\n")
    finally:
        for fn in os.listdir(incomplete_dir):
            os.remove(os.path.join(incomplete_dir, fn))
        os.rmdir(incomplete_dir)

    print("-- SECRETS-REGEX юнит-проверки (владелец cicd_leak_scanner.py) --")
    sec_results = secrets_checks()
    sec_ok, sec_total = _print_results(sec_results)
    sec_all_pass = sec_ok == sec_total

    total_ok = real_ok + sec_ok
    total_all = real_total + sec_total
    overall_ok = real_all_pass and firing_proved and sec_all_pass

    print("=== ИТОГ: %d/%d зелёные (+ FIRING %s) — %s ===" % (
        total_ok, total_all,
        "доказан" if firing_proved else "НЕ доказан",
        "PASS" if overall_ok else "FAIL",
    ))
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
