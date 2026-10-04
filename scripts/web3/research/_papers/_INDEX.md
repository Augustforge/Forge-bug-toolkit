# Audit-Grade Papers

Methodology layer для writing Verichains-grade vulnerability papers. Любой
serious Critical finding (>$100K bounty potential) должен сопровождаться
formal paper, не просто HackenProof report.

## Зачем

Solodit / Immunefi short-form reports OK для Low/Medium. Но для Critical:

1. **Bounty review process** — auditing team review paper, не raw PoC.
   Чем clearer paper, тем faster + higher payout
2. **Sibling-variant detection** — formal paper заставляет тебя думать про
   класс bug'а, не instance. Это feeds back в `threat_models/`
3. **Reputation** — papers signed by the operator становятся artifact'ом который
   признаётся community (samczsun-tier)
4. **Future-self** — через 2 года the operator смотрит свой paper и понимает что нашёл,
   not просто "грепнул что-то"

## Структура канонического security paper

Verichains TSSHOCK / Trail of Bits / Kudelski style:

```
1. Executive Summary          (1 abzac — что нашёл, severity, impact)
2. Background                 (что такое affected protocol/primitive)
3. Vulnerability Description  (root cause без attack chain — pure)
4. Attack Flow                (step-by-step с code references)
5. Impact Analysis            (concrete loss scenarios + worst case)
6. Affected Implementations   (что именно vulnerable + variations)
7. Sibling Variants           (что ещё может быть affected — class-level)
8. Mitigation                 (canonical fix + lessons)
9. Disclosure Timeline        (when found / when reported / when fixed)
10. References                (papers, audits, code commits)
```

## Files

```
_papers/
├── _INDEX.md                       (этот файл)
├── paper_template.md               (boilerplate с placeholder'ами)
└── thorchain_2026_tsshock.md       (worked example — как мы бы написали)
```

## Workflow

```bash
# 1. После confirmation finding (Foundry test green, PoC repro) — start paper
cp _papers/paper_template.md _papers/<target>_<year>_<class>.md

# 2. Fill sections sequentially. Не skip, не reorder.
# Каждая section имеет explicit guidance в template comments.

# 3. После draft → invoke peer_review.py с paper text как input
python3 scripts/web3/findings_db/peer_review.py --paper _papers/<file>.md

# 4. Submit к bounty platform с paper attached как PDF (export через pandoc):
pandoc _papers/<file>.md -o <file>.pdf

# 5. После disclosure period (typically 90 days) — public release
# (с redaction sensitive contact details)
```

## Cross-link

- [findings_db/peer_review.py](../../findings_db/peer_review.py) — Claude peer
  review для paper draft перед submit
- [_audit_corpus/_known_findings.jsonl](../_audit_corpus/_known_findings.jsonl) —
  после finalize paper, add entry туда
- [threat_models/](../../threat_models/) — sibling-variant section paper'а
  feeds back в threat_models YAML

## Quality bar

Paper считается ready to submit когда:

- [ ] Все 10 sections заполнены, не stub
- [ ] Attack flow имеет concrete code references (file:line)
- [ ] Sibling variants — минимум 2 hypothesized variants названы (даже если
  не confirmed)
- [ ] Peer review через Claude (adversarial + dev frame) passed consensus
- [ ] PoC test attached, reproducibility documented
- [ ] Mitigation — concrete code change suggested, не "fix the bug"
- [ ] No emojis, no marketing speak, no "interesting" / "novel" filler

## Length expectations

- Critical finding: 1500-3000 words
- High finding: 800-1500 words
- Medium: full paper НЕ обязателен, HackenProof report enough

Меньше — looks lazy / insufficient analysis. Больше — auditor team won't read all.
