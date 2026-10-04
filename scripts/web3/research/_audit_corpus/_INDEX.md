# Audit Report Corpus

Локальный grep'абельный кэш public audit reports для cross-reference findings.

## Зачем

Auditors (Verichains, Kudelski, Trail of Bits, OpenZeppelin, ChainSecurity)
публикуют detailed reports после major engagements. Эти reports содержат:

1. **Concrete attack chains** — step-by-step exploits на real code
2. **Mitigation recommendations** — что считается canonical safe pattern
3. **CVE-mapping** — для known cryptographic primitives
4. **Sibling-variant warnings** — auditors часто отмечают "fixed THIS variant, but similar pattern в X module worth re-checking"

Без этого corpus каждое finding hunter переоткрывает заново. С corpus —
`grep -r "Paillier" _audit_corpus/` за 1 секунду показывает 15 historic reports
с similar pattern.

## Структура

```
_audit_corpus/
├── _INDEX.md                      (этот файл)
├── fetch.py                       (downloader)
├── _known_findings.jsonl          (structured extraction)
└── reports/
    ├── verichains/
    │   ├── 2022-tsshock-binance-gg18.pdf
    │   ├── 2022-tsshock-supplement.md
    │   └── 2026-thorchain-postmortem.pdf      (если появится после фикса)
    ├── kudelski/
    │   ├── 2023-gg20-multiparty-review.pdf
    │   └── 2024-frost-ed25519-audit.pdf
    ├── trail-of-bits/
    │   ├── 2024-eigenlayer-avs-audit.pdf
    │   ├── 2023-celestia-da-audit.pdf
    │   └── 2025-zksync-prover-audit.pdf
    ├── openzeppelin/
    │   └── ...
    └── chainsecurity/
        └── ...
```

## Workflow

```bash
# 1. Initial fetch
python3 fetch.py

# 2. Grep specific class
grep -ri "biprime" reports/         # все references на Paillier safety
grep -ri "TSSHOCK" reports/

# 3. После каждого нового finding — добавить запись в _known_findings.jsonl
python3 fetch.py --add-finding \
    --auditor verichains --year 2022 \
    --class "tss-paillier-biprime-bypass" \
    --severity critical \
    --target binance-tss-lib \
    --source-url "..."
```

## _known_findings.jsonl формат

One JSON object per line:
```json
{
  "id": "tsshock-2022-alpha-shuffle",
  "auditor": "verichains",
  "year": 2022,
  "severity": "critical",
  "class": ["tss-paillier-bypass", "key-extraction"],
  "target": "binance-tss-lib",
  "source_url": "https://verichains.io/tsshock/",
  "fix_commit": "abc123...",
  "sibling_variants_warned": ["c-split", "c-guess"],
  "summary": "α-shuffle attack: malicious party submits Paillier key violating biprime structure, gains ability to factor MtA encrypted shares."
}
```

## Cross-link

- [threat_models/post_bounty_variant_drift.yaml](../../threat_models/post_bounty_variant_drift.yaml) —
  meta-pattern: paid bounty fix → check sibling variants. `_known_findings.jsonl` =
  source data для этой проверки
- [longtail/bounty_regression.py](../../longtail/bounty_regression.py) — reads
  `_known_findings.jsonl` для seed input
- [_crypto_corpus/](../_crypto_corpus/) — code that these audits reviewed

## Legal posture

Все reports = **publicly disclosed by auditors themselves**. Reuse под Fair Use
для educational/security research. Не для resale, не для derivative obscuring
attribution. Если у tier-1 auditor specific report под NDA — exclude.
