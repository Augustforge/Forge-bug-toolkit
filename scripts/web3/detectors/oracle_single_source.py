"""
Custom Slither detector: oracle reads without proper validation.
Closes Immunefi V03 — Oracle/Price Manipulation gap.

P0-fix (SlowMist Aug-2026 ingest, reference_slowmist_aug2026_ingest):
The old heuristic `count(price_calls) >= 2 -> has_fallback -> safe` was a STRUCTURAL
INVERSION — median/aggregate/multi-read forms (the MOST dangerous ones) read price
several times, so the detector silenced its flag exactly where the bug lives (42DAO /
Solido / LULA, ~$1.5M). It also `.count()`ed within a SINGLE expression string, so the
"fallback" branch was near-dead anyway. Both removed.

New (class-based, NOT signature-based — we detect the MECHANISM, not the hack):
  1. N price-reads is NOT safety. The suppression is gone.
  2. Aggregation (median/sort/prices[]/loop-over-feeds) WITHOUT a deviation-bound or
     quorum check is a FLAG, not an indulgence (Cat 5.2 / 5.x).
  3. A named fallback that references >=2 distinct feed addresses = "verify feed-ID /
     asset parity" flag (Cat 5.15 — Solido fallback resolved a LIVE feed of a DIFFERENT
     asset).
  4. Freshness (updatedAt/timestamp) is ONE of several conditions, never the sole
     exoneration.

Honest limitation: Slither exposes expressions as strings here, so this stays a
heuristic SIGNAL (surface a place to look), not a dataflow proof. The decision logic is
factored into the pure, solc-free `classify_oracle_fn()` so it is unit-testable
(oracle_single_source_selftest.py) — the test proves firing and fails if the fix regresses.

Run via:
    slither <target> --detect oracle-single-source --config-file slither.config.json
"""

import re

try:  # guarded so the module (and classify_oracle_fn) imports without slither installed
    from slither.detectors.abstract_detector import (
        AbstractDetector,
        DetectorClassification,
    )
    _HAVE_SLITHER = True
except Exception:  # pragma: no cover - exercised only in bare test env
    _HAVE_SLITHER = False

    class AbstractDetector:  # minimal stub; class body below only needs attribute access
        pass

    class DetectorClassification:
        HIGH = MEDIUM = LOW = INFORMATIONAL = OPTIMIZATION = None


# ── Pure detection logic (no slither, no solc — unit-testable) ──────────────────────

# Concrete oracle/price reads. Bare "price" removed — it substring-matched any var named
# price/basePrice/pricePerShare (cold-review FP); call-forms `.price(`/`getPrice` cover custom getters.
ORACLE_READ_PATTERNS = [
    "latestRoundData", "latestAnswer", "getRoundData",
    "getReserves", "slot0", "observe", "getPrice", ".price(", "consult(",
]
# Chainlink-style pull feed vs AMM-style spot read — two families present = cross-source.
_CHAINLINK_FAMILY = ["latestrounddata", "latestanswer", "getrounddata"]
_AMM_FAMILY = ["getreserves", "slot0", "observe"]

# Freshness = oracle-RETURN fields only. `timestamp`/`stale` dropped: `block.timestamp` (deadlines/
# cooldowns) is ubiquitous and falsely exonerated raw spot reads (the P0 lie via a different door,
# cold-review FN). AMM reads have no updatedAt at all — handled by fam_amm rule below.
_FRESHNESS_TOKENS = ["updatedat", "answeredinround", "roundid", "heartbeat"]

# Aggregation shapes: explicit combinators OR a loop over a feed collection.
_AGGREGATE_TOKENS = ["median(", "sort(", "prices[", "aggregate", "average(", "mean("]
_LOOP_TOKENS = ["for ", "for(", "while "]
_FEED_COLLECTION_TOKENS = ["feeds", "oracles", "sources", "pricefeeds", "aggregators"]

# Deviation / quorum guards. Deliberately explicit tokens only: an over-flag (analyst
# verifies) is safer than a silent suppression, so we do NOT infer safety from a bare
# `abs()`+`<`. These are the canonical aggregation guards.
# `tolerance` dropped — matched `slippageTolerance` (unrelated to feed-deviation, cold-review FN);
# "deviation" substring already covers maxDeviation/priceDeviation/deviationTolerance.
_DEVIATION_TOKENS = ["deviation", "quorum", "minanswers", "minanswer", "maxdev", "mindev"]

# Fallback naming — a REDUNDANT/BACKUP source must be named for suppression to be legitimate. Only
# `fallback`/`backup` qualify (cold-review round-4 FN): `primary`/`secondary` name a POSITION in a feed set,
# not proof a redundant source is read+compared — `primaryOracle` is the SOLE feed => single-source, NOT
# redundancy (the ubiquitous naming silenced a large real class). Standalone `fallback(` dropped too: it
# matched the Solidity `fallback()`/`super.fallback()` FUNCTION (proxies/forwarders), unrelated to oracle
# redundancy. Oracle-context-qualified so `backupBuffer`/`secondaryReserve` (substring FP) don't count.
# `source` DROPPED from the context words (cold-review round-6 FP): `backupSource`/`fallbackSource`/`dataSource`/
# `entropySource` are routine NON-oracle names (relayers, VRF/entropy providers, data-source registries) and were
# raising the cross-asset flag. The remaining words (oracle/feed/price/aggregator) are oracle-domain-specific.
_FALLBACK_NAME_RE = re.compile(
    r"(?:fallback|backup)[_ ]?(?:oracle|feed|price|aggregator)"
    r"|(?:oracle|feed|price|aggregator)[_ ]?(?:fallback|backup)",
    re.I)

_ADDR_RE = re.compile(r"0x[a-f0-9]{40}")


def classify_oracle_fn(expr_strings):
    """Classify a function's stringified expressions for oracle-validation weakness.

    Input: list[str] — `str(expr)` for each expression in a Slither function.
    Output: dict with boolean signals + `flags` (list of raised flag ids). Empty
    `flags` = nothing to report.

    Flags:
      single-source-no-validation  — reads a price with neither freshness nor fallback.
      aggregate-no-deviation-bound — aggregates feeds without a deviation/quorum guard.
      fallback-cross-asset-verify  — named fallback over >=2 feed addresses (Cat 5.15).
    """
    joined = "\n".join(expr_strings)
    low = joined.lower()

    reads = [p for p in ORACLE_READ_PATTERNS if p.lower() in low]
    has_oracle_read = bool(reads)
    has_freshness = any(t in low for t in _FRESHNESS_TOKENS)
    has_deviation_bound = any(t in low for t in _DEVIATION_TOKENS)

    is_aggregate = any(t in low for t in _AGGREGATE_TOKENS) or (
        any(l in low for l in _LOOP_TOKENS)
        and any(f in low for f in _FEED_COLLECTION_TOKENS)
    )

    fam_chainlink = any(t in low for t in _CHAINLINK_FAMILY)
    fam_amm = any(t in low for t in _AMM_FAMILY)
    two_families = fam_chainlink and fam_amm  # informational ONLY — 2 kinds ≠ enforced cross-check

    named_fallback = bool(_FALLBACK_NAME_RE.search(low))
    # has_fallback = a REDUNDANT source is NAMED. try/catch DROPPED (cold-review round-4 FN): a Solidity
    # try/catch around an oracle read is error-handling, not redundancy — `catch { revert(); }` (or a catch
    # returning a cached/stale value or re-reading the SAME feed) is a single independent source. Treating
    # try as fallback re-created the old "multiple reads ⇒ safe" suppression via a side door. two_families
    # also stays OUT (nothing enforces a comparison). Over-flag on a genuine try/catch fallback is acceptable.
    has_fallback = named_fallback

    distinct_addrs = set(_ADDR_RE.findall(low))
    # cross-asset flag = named fallback over >=2 distinct addresses (the Solido/Cat 5.15 hardcoded-feed site).
    # NO has_oracle_read gate (cold-review round-5 FN): the config/setter/constructor that HARDCODES the feed
    # addresses usually does NOT read a price in the SAME function — and that IS the site the flag targets. The
    # bare `fallback()` token-forwarder FP is already killed by _FALLBACK_NAME_RE requiring oracle-context, so
    # the gate was redundant and only cost recall. _ADDR_RE counts any 40-hex literal — the message says "addresses".
    fallback_cross_asset = named_fallback and len(distinct_addrs) >= 2

    # AMM-family spot reads (slot0/getReserves) have NO updatedAt — a freshness token near them is
    # about something else (a deadline), so freshness must NEVER exonerate an AMM spot read (cold-review FN).
    freshness_exonerates = has_freshness and not fam_amm

    flags = []
    # 1) Single source, no validation. Not suppressed by multiple reads NOR by AMM-adjacent freshness.
    if has_oracle_read and not freshness_exonerates and not has_fallback:
        flags.append("single-source-no-validation")
    # 2) Aggregation WITHOUT deviation/quorum guard — the form the old code silenced.
    if is_aggregate and not has_deviation_bound:
        flags.append("aggregate-no-deviation-bound")
    # 3) Named fallback across >=2 feeds — verify they resolve the SAME asset (Solido).
    if fallback_cross_asset:
        flags.append("fallback-cross-asset-verify")

    return {
        "has_oracle_read": has_oracle_read,
        "has_freshness": has_freshness,
        "has_deviation_bound": has_deviation_bound,
        "is_aggregate": is_aggregate,
        "has_fallback": has_fallback,
        "two_families": two_families,
        "fallback_cross_asset": fallback_cross_asset,
        "reads": reads,
        "flags": flags,
    }


_FLAG_MESSAGES = {
    "single-source-no-validation": (
        "reads a price oracle with neither staleness check nor fallback — single point of failure"
    ),
    "aggregate-no-deviation-bound": (
        "aggregates multiple price feeds WITHOUT a deviation-bound / quorum guard "
        "(median/sort/loop) — a compromised or manipulated feed skews the aggregate (Cat 5.2)"
    ),
    "fallback-cross-asset-verify": (
        "named fallback over >=2 distinct addresses — verify the fallback resolves the SAME asset "
        "as primary (Cat 5.15 cross-asset substitution, e.g. Solido)"
    ),
}


# ── Slither detector wrapper ────────────────────────────────────────────────────────

class OracleSingleSource(AbstractDetector):
    ARGUMENT = "oracle-single-source"
    HELP = "Oracle read without validation / aggregation without deviation-bound (Immunefi V03)"
    IMPACT = DetectorClassification.HIGH
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = "https://immunefi.com/immunefi-top-10/"
    WIKI_TITLE = "Oracle read without validation"
    WIKI_DESCRIPTION = (
        "Contract reads a price without freshness/fallback, or aggregates feeds without a "
        "deviation-bound / quorum guard, or falls back to a feed of a different asset."
    )
    WIKI_RECOMMENDATION = (
        "Add a staleness check, cross-validate against a second source, and on aggregation "
        "enforce a deviation-bound / minimum quorum; verify fallback feeds match the primary asset."
    )
    WIKI_EXPLOIT_SCENARIO = (
        "Attacker manipulates one feed within an unguarded median/aggregate → skews the reported "
        "price → drains the protocol."
    )

    def _detect(self):
        results = []
        for contract in self.compilation_unit.contracts_derived:
            for fn in contract.functions:
                if not fn.expressions:
                    continue
                expr_strings = [str(e) for e in fn.expressions]
                verdict = classify_oracle_fn(expr_strings)
                if not verdict["flags"]:
                    continue
                for flag in verdict["flags"]:
                    info = [fn, " ", _FLAG_MESSAGES[flag], ". Patterns: ",
                            ", ".join(verdict["reads"]) or "(aggregation)", "\n"]
                    results.append(self.generate_result(info))
        return results
