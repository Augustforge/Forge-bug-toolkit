#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay test for the 8th paraphrase-bypass (live hunt transcripts, 2026-08-09) — _paraphrase_giveup.

Root cause: the instance does NOT write "abort/I give up/pivot" (caught by ABORT/FORK/DECISION_Q), but gives an "honest FINAL
report" with the forbidden frames in new words — "target really hardened / Un-dup surface cleaned /
pass is exhaustive / further EV only in a multi-day fork-PoC / wait for the next release" + handing the wheel back
to the operator. BREADTH_RE requires "whole scope", these phrases bypassed it → give-up was not flagged is_giveup → the circuit
breaker let it through. Fix: a cluster detector (>=2 give-up categories) + continuation-override.

System rule: the test proves FIRING on REAL give-ups + 0 FP on legit continuations.
Run: py -3 -X utf8 bug-bounty-toolkit/scripts/_methodology/paraphrase_giveup_replay.py
"""
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GATE = os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate_pg", GATE)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

# (name, text, expect_fires) — FIRES = real give-ups from transcripts; silent = legit continuations/statuses (the Russian text inputs are kept verbatim: the detector regexes match Russian)
CASES = [
    # ── FIRES: real give-ups (transcripts 0516eeea, 916b2917) + an operator quote ──
    ("operator quote: hardened+cleaned+EV-only+wait-release",
     "Честный вывод: таргет реально захардён. Un-dup поверхность вычищена. Дальше EV только в "
     "многодневной fork-PoC кампании или single-target mastery — ждать следующий релиз/upgrade и "
     "хантить дельту потом.", True),
    ("livepeer rec370: final+exhaustive+EV-only",
     "Бро, закрыл последние нити — проход исчерпывающий и честный. Финал по Livepeer. Честный вывод: "
     "таргет реально захардён. Un-dup поверхность вычищена. Дальше EV только в многодневной fork-PoC.", True),
    ("livepeer rec352: honest status+target hardened",
     "Бро, честный статус после полного divergence-first прохода по Livepeer. Итог по нитям — таргет "
     "реально захардён, все ENFORCED.", True),
    ("rocketpool rec227: honest result+all clean",
     "Бро, честный итог глубокого прохода по Rocket Pool Saturn. Всё чисто/защищено. "
     "Подтверждённого High нет.", True),
    ("bad-EV+decision: EV only + what to do",
     "Таргет захардён, дальше EV только в fork-PoC. Что делать?", True),
    ("park-exit: wait for release + final",
     "Финал по таргету: ждать следующий upgrade, когда #657 задеплоят — вернусь на дельту.", True),
    # ── lombard-audit 2026-08-13 (9th bypass, operator items 3/7): "target clean" + "depth exhausted" + "you decide" ──
    ("lombard chat: depth exhausted + target clean + you decide",
     "in-scope глубина исчерпана с on-chain пруфом. таргет реально чистый по текущему деплою. "
     "решай, Бро, уходим.", True),
    ("lombard iter5+chat: protocol hardened + target clean + you decide",
     "4 оси deep clean, протокол исключительно захарден. таргет реально чистый, решай.", True),
    ("lombard: target clean + up to you",
     "Дальше варианты: T9 cold-restart, или ждать деплоев. Таргет чистый по деплою — тебе решать.", True),
    # ── SILENT: legit continuations (instance CONTINUES) + invariant descriptions + a finding ──
    ("anti-FP rec361: hardened BUT the loop continues",
     "Все нити закрыты — таргет захардён. Петля продолжается: следующая ось — treasury governance "
     "lifecycle. Строю wave-3 модель. Читаю LivepeerGovernor.", False),
    ("anti-FP rec206: core hardened as expected, continuing",
     "Ядро (treasury+reward) захардено как ожидалось. Высший EV = bridge. Записываю ledger, потом гоню "
     "bridge conservation сам.", False),
    ("anti-FP: single I-NN ENFORCED status",
     "H-03 ENFORCED: guard на 930 keyed на _transcoder. Записываю в ledger, гоню нить вглубь на слой 4.", False),
    ("anti-FP: finding + HUNT-EXIT",
     "Нашёл реальный баг H-05, T4-подтверждаю. Пишу HUNT-EXIT: T4-CONFIRMED High.", False),
    ("anti-FP: continuation 'pushing on' even with exhaustion vocabulary",
     "Эта ось выглядит чистой, но гоню дальше вглубь — следующая нить bridge-conservation, строю wave-2.", False),
    ("anti-FP: empty text", "", False),
    ("anti-FP: neutral status",
     "Обновил ledger, scout вернулись, мержу лиды. Депт-трейс 3/5 по нити H-01.", False),
    # lombard-audit anti-FP: "target clean" BUT continuing — not a give-up (continuation override preserved).
    ("anti-FP lombard: target clean at layer 3, but pushing on",
     "Таргет выглядит чистым по деплою на слое 3, но гоню нить AX-08b глубже — строю wave-6 модель.", False),
    ("anti-FP lombard: you decide whether to, but I continue myself",
     "Решай сам, стоит ли пушить severity — а я продолжаю копать, следующая ось mintWithFee replay.", False),
]


def run():
    ok = fail = 0
    for name, text, expect in CASES:
        r = G._paraphrase_giveup(text)
        if r == expect:
            ok += 1
            print("  [PASS] %s" % name)
        else:
            fail += 1
            print("  [FAIL] %s  (fires=%s expect=%s)" % (name, r, expect))
    print("\n%d/%d paraphrase-giveup (8th bypass) cases green" % (ok, ok + fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
