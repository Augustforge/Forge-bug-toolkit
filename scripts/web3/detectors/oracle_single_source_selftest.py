#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay test for oracle_single_source.classify_oracle_fn (P0-1, SlowMist Aug-2026).

Runs the pure decision function against string fixtures — solc/slither/Docker are NOT needed.
feedback_hook_must_prove_firing discipline: the test PROVES the fix fires, not merely that
there are "no false positives". The key case is `regression guard`: it reproduces the OLD lying
heuristic `count(price_calls)>=2 -> safe` and shows that it STAYED SILENT where the new one flags.
If the fix is reverted (suppression restored), this test fails.

Run:  py -3 -X utf8 oracle_single_source_selftest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_single_source import classify_oracle_fn  # noqa: E402


# ── Fixtures: (name, expr_strings, expectation) ────────────────────────────────────
# expectation: ("contains", [flag,...]) | ("empty",)

CASES = [
    # (a) Inline-average in a SINGLE expression: 3 price-reads. Old code: count>=2 -> has_fallback
    #     -> SILENT. New: no freshness/fallback -> FLAG. Direct proof the lie is removed.
    (
        "inline_average_silenced_by_old",
        ["avgPrice = (feedA.latestAnswer() + feedB.latestAnswer() + feedC.latestAnswer()) / 3",
         "return avgPrice"],
        ("contains", ["single-source-no-validation"]),
    ),
    # (b) Median over an array of feeds WITHOUT deviation-bound -> aggregate flag (42DAO form).
    (
        "median_array_no_deviation",
        ["prices[0] = feedA.latestAnswer()",
         "prices[1] = feedB.latestAnswer()",
         "prices[2] = feedC.latestAnswer()",
         "result = median(prices)"],
        ("contains", ["aggregate-no-deviation-bound"]),
    ),
    # (c) Median WITH freshness + deviation-bound -> SILENT (anti-FP).
    (
        "median_with_deviation_and_freshness",
        ["(roundId, answer, startedAt, updatedAt, answeredInRound) = feed.latestRoundData()",
         "require(block.timestamp - updatedAt < 3600)",
         "require(deviation < maxDeviation)",
         "p = median(prices)"],
        ("empty",),
    ),
    # (d) Single Chainlink read without freshness/fallback -> FLAG (regression: old behavior ok).
    (
        "single_chainlink_no_validation",
        ["(, answer, , ,) = feed.latestRoundData()", "return uint256(answer)"],
        ("contains", ["single-source-no-validation"]),
    ),
    # (e) Chainlink with freshness + try/catch fallback -> SILENT (anti-FP).
    (
        "chainlink_freshness_plus_fallback",
        ["(, a, , updatedAt, ) = primary.latestRoundData()",
         "require(block.timestamp - updatedAt < 3600)",
         "try secondary.latestRoundData() returns (uint80 r, int256 b, uint256 s, uint256 u, uint80 ar)",
         "return uint256(a)"],
        ("empty",),
    ),
    # (f) Named fallback over 2 different feed addresses -> cross-asset verify (Solido form, Cat 5.15).
    (
        "fallback_cross_asset",
        ["primaryFeed = 0x1111111111111111111111111111111111111111",
         "fallbackFeed = 0x2222222222222222222222222222222222222222",
         "price = useFallback ? IFeed(fallbackFeed).latestAnswer() : IFeed(primaryFeed).latestAnswer()"],
        ("contains", ["fallback-cross-asset-verify"]),
    ),
    # (g) Function without oracle-read -> SILENT (anti-FP).
    (
        "no_oracle_read",
        ["x = a + b", "return x"],
        ("empty",),
    ),
    # (h) Loop over a sources array without deviation -> aggregate flag (aggregation via loop).
    (
        "loop_over_sources_no_deviation",
        ["for (uint i = 0; i < sources.length; i++)",
         "sum += IOracle(sources[i]).latestAnswer()",
         "avg = sum / sources.length"],
        ("contains", ["aggregate-no-deviation-bound"]),
    ),
    # ── cold-review fix-loop: repro of confirmed findings (fail if the fix is reverted) ──
    # FN1: `block.timestamp` (deadline) is NOT freshness; an AMM spot read is not exonerated.
    (
        "amm_spot_with_deadline_not_freshness",
        ["price = pool.slot0()", "require(block.timestamp <= deadline)"],
        ("contains", ["single-source-no-validation"]),
    ),
    # FN2: two families (chainlink+amm) NO LONGER suppress single-source (no enforced cross-check).
    (
        "two_families_no_longer_suppresses",
        ["(, int p, , ,) = feed.latestAnswer()", "(uint112 r0, uint112 r1, ) = pair.getReserves()"],
        ("contains", ["single-source-no-validation"]),
    ),
    # FP3: bare "price" (a variable) is NOT an oracle-read → silence.
    (
        "bare_price_var_no_flag",
        ["price = totalCost / quantity", "return price"],
        ("empty",),
    ),
    # FN4: `secondaryReserve` is NOT counted as fallback (word-boundary + oracle-context).
    (
        "secondaryReserve_not_fallback",
        ["p = feed.latestAnswer()", "secondaryReserve += x"],
        ("contains", ["single-source-no-validation"]),
    ),
    # FN5: `slippageTolerance` is NOT a deviation-bound → aggregate without a guard is flagged.
    (
        "slippage_tolerance_not_deviation",
        ["for (uint i; i < feeds.length; ++i) sum += IFeed(feeds[i]).latestRoundData()",
         "updatedAt = block.timestamp",
         "amountOut = amountOut * slippageTolerance / 1e4"],
        ("contains", ["aggregate-no-deviation-bound"]),
    ),
    # reverify B-1: the bare word `backup` (not oracle-context, not a fallback() call) does NOT suppress single-source.
    (
        "bare_backup_token_not_fallback",
        ["p = feed.latestAnswer()", "backup = getBackupValue()"],
        ("contains", ["single-source-no-validation"]),
    ),
    # ── cold-review round-4: repro of 8/8 confirmed B-1 defects (fail if the fix is reverted) ──
    # R1: `primaryOracle` = SOLE feed naming → NOT redundancy → single-source is flagged (`primary` removed).
    (
        "primary_oracle_not_fallback",
        ["(, int256 answer,,,) = AggregatorV3Interface(primaryOracle).latestRoundData()"],
        ("contains", ["single-source-no-validation"]),
    ),
    # R2: try/catch around an oracle-read = error-handling, NOT redundancy (`has_try` removed from has_fallback).
    (
        "try_catch_not_fallback",
        ['try AggregatorV3Interface(feed).latestRoundData() returns '
         '(uint80 r, int256 answer, uint256 s, uint256 u, uint80 ar) '
         '{ return uint256(answer); } catch { revert("stale"); }'],
        ("contains", ["single-source-no-validation"]),
    ),
    # R3: a non-oracle fallback() forwarder with 2 token addresses does NOT raise an oracle flag (exact confirmed FP).
    (
        "nonoracle_fallback_forwarder_silent",
        ["fallback() external override",
         "super.fallback()",
         "IERC20(0xC02aaa39b223FE8D0A0e5C4F27eAD9083C756Cc2).transfer(vault, wethBal)",
         "IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7).transfer(vault, usdtBal)"],
        ("empty",),
    ),
    # R4 (round-5): named fallback + 2 addresses at a config site (WITHOUT a price-read in this fn) → cross-asset FLAG
    #     (Solido Cat 5.15 hardcoded-feed site; the has_oracle_read gate was REMOVED — it cut this recall).
    (
        "cross_asset_at_config_site_flags",
        ["fallbackOracle = 0x1111111111111111111111111111111111111111",
         "backupOracle = 0x2222222222222222222222222222222222222222",
         "total = a + b"],
        ("contains", ["fallback-cross-asset-verify"]),
    ),
    # R5 (isolates removal of bare-`fallback(`): a fallback() fn that ALSO reads a single feed → single-source.
    (
        "bare_fallback_call_does_not_suppress",
        ["fallback() external override",
         "super.fallback()",
         "(, int256 answer, , ,) = feed.latestRoundData()"],
        ("contains", ["single-source-no-validation"]),
    ),
    # R6: generic `backupSource`/`primarySource` (non-oracle relayer/entropy) with 2 addresses → NOT cross-asset
    #     (`source` removed from _FALLBACK_NAME_RE; round-5 no-gate FP regression).
    (
        "generic_source_names_not_oracle_fallback",
        ["backupSource = 0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
         "primarySource = 0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"],
        ("empty",),
    ),
]


def _old_lying_heuristic_flags(expr_strings):
    """Reproduces the OLD detector (before the P0 fix) — for the regression guard.

    Old logic (oracle_single_source.py:51-54 orig):
        for expr: if expr.count("latestAnswer")+expr.count("getReserves") >= 2: has_fallback=True
        if oracle_calls and not has_freshness and not has_fallback: FLAG
    """
    ORACLE = ["latestRoundData", "latestAnswer", "getRoundData",
              "getReserves", "slot0", "observe", "price"]
    oracle_calls, has_freshness, has_fallback = [], False, False
    for expr in expr_strings:
        for p in ORACLE:
            if p in expr:
                oracle_calls.append(p)
        if "updatedAt" in expr or "timestamp" in expr:
            has_freshness = True
        if expr.count("latestAnswer") + expr.count("getReserves") >= 2:
            has_fallback = True
    return bool(oracle_calls and not has_freshness and not has_fallback)


def run():
    passed = failed = 0
    for name, exprs, expect in CASES:
        got = classify_oracle_fn(exprs)["flags"]
        if expect[0] == "empty":
            ok = (len(got) == 0)
        else:  # contains
            ok = all(f in got for f in expect[1])
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {name:40s} flags={got} expect={expect}")

    # ── Regression guard: the old heuristic STAYED SILENT on inline-average, the new one flags ──
    print("\n  regression guard (old lying heuristic vs new):")
    inline = CASES[0][1]
    old_flagged = _old_lying_heuristic_flags(inline)
    new_flags = classify_oracle_fn(inline)["flags"]
    guard_ok = (old_flagged is False) and (len(new_flags) > 0)
    gstatus = "PASS" if guard_ok else "FAIL"
    print(f"  [{gstatus}] old_silenced={not old_flagged} new_flags={new_flags} "
          f"(fix removes the lie)")
    if guard_ok:
        passed += 1
    else:
        failed += 1

    total = passed + failed
    print(f"\noracle_single_source_selftest: {passed}/{total} passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
