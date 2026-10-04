# Crypto Implementation Corpus

Локальный кэш public TSS/MPC/threshold-crypto implementations для cross-diff
hunting. Идея — Verichains нашла TSSHOCK именно через diff между tss-lib и
reference paper. Drift между implementations часто = candidate vulnerability.

## Что лежит

После `python3 fetch.py` создаётся структура:

```
_crypto_corpus/
├── _INDEX.md                       (этот файл)
├── fetch.py                        (cloner)
├── diff_critical_rounds.py         (cross-diff engine)
├── _last_fetch.json                (когда обновляли + commit SHAs)
└── repos/
    ├── binance-tss-lib/            (GG18/GG20 GoLang, эталон)
    ├── coinbase-kryptology/        (Coinbase TSS, Go)
    ├── zengo-multi-party-ecdsa/    (ZenGo GG18, Rust)
    ├── thorchain-go-tss/           (Thorchain fork, Go — pre-fix snapshot)
    ├── nomad-tss-engine/           (Nomad, Rust)
    └── icon-tss/                   (ICON BTP, Go)
```

## Critical round functions для cross-diff

`diff_critical_rounds.py` сравнивает эти функции/identifiers между всеми
реализациями. Если N-1 implementations имеют check X, а N'я не имеет —
candidate vulnerability:

| Round | Function/check | Что искать |
|---|---|---|
| KeyGen round 1 | `paillier.GenerateKey` / `Paillier.SafeKeyGen` | biprime check (произведение двух safe primes) |
| KeyGen round 2 | `ProveDLog` / `proofOfKnowledge` | iterations >= 128, hash-to-challenge protocol |
| KeyGen round 3 | `VerifySchnorr` / `verifyProof` | challenge derivation order |
| Sign round 1 | `MtA` / `MultiplyToAdd` | range proof verification |
| Sign round 5 | `ZKProof.Verify` | iterations counter validation |
| Sign round 6 | `s_i delta` aggregation | overflow check / modular reduction |

## Workflow

```bash
# 1. Fetch (запускать раз в неделю или после major incident)
python3 fetch.py

# 2. Cross-diff critical rounds across all repos
python3 diff_critical_rounds.py --output diff_report.md

# 3. Если diff показал N-1 vs 1 — открыть файлы вручную, понять почему
# (legitimate optimization OR forgotten safety check?)
```

## Ethics / OPSEC

Все repos — **public open-source code**. Это публично доступная информация,
никаких prohibited mirror'ов. Forks Thorchain/Nomad берутся в pre-incident
snapshot где это релевантно (чтобы видеть код до фикса).

## Cross-link

- [threat_models/tss_validator_extraction.yaml](../../threat_models/tss_validator_extraction.yaml) —
  executable_checks ссылаются на этот corpus для контекста
- [checklists/specialized/tss_mpc.md](../../checklists/specialized/tss_mpc.md) —
  manual review checklist
- [research/mpc_threshold.md](../mpc_threshold.md) — research catalog entry
- [_primers/tss_math_for_hunters.md](../_primers/tss_math_for_hunters.md) —
  что именно эти функции делают
