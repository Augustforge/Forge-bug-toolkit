#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Proactive /deephunt target discovery + EV-scoring (Plan 9, TIER G, T12; closes blind_spots §57.4).

Analogue of the Marius observation: "80% of targets = 0 reports" — we rank CANDIDATE programs BEFORE
committing depth, so we dig where EV is highest, not where we happened to poke first.

EV = payout × freshness × (1/crowd_heat) × pattern_match

    payout       — normalized max-bounty (Critical payout), linear up to PAYOUT_CAP.
    freshness    — fresh program = fewer competitors have looked → higher (halflife-decay by age).
    1/crowd_heat — the more reports already filed / the more public = crowd → lower (Marius insight).
    pattern_match — overlap of stack/tags with our un-dup pattern library / strong classes
                    (floor PATTERN_BASE, so a mismatch does NOT zero out EV, only lowers it).

⚠️ Boundaries (Plan 9 R8, THINK≠ACT): this is READ-ONLY access to public program pages (Playwright CF-safe).
No active testing, no mass-targeting, no mutation of anyone else's state.

🔒 Anonymity precondition (fail-CLOSED). The full `opsec_preflight` does NOT fit here: it requires
test_accounts (web2) / a burner wallet (web3), which pure recon of public pages does NOT have — we don't
log in and don't send tx. But even a read-only live browser MUST be anonymous: the program operator / CF
must not fingerprint our main identity and link recon to future submissions. Therefore
`anonymity_precondition()` is a lightweight fail-closed gate (VPN/incognito/not-main-login) and it MUST
pass BEFORE any live `discover_live()` call; on failure no fetch is performed.

Scoring is fail-open (not security): a broken program record does not crash the ranking, it degrades to a
neutral factor. The anonymity branch is fail-closed (never lets anything through when unclear).

CLI (offline, read-only local JSON, no network):
    py -3 -X utf8 scripts/web3/target_discovery.py --programs programs.json
    py -3 -X utf8 scripts/web3/target_discovery.py --programs programs.json --patterns solana,amm,oracle
"""

import argparse
import json
import sys
import time


# ---------------------------------------------------------------------------
# Scoring constants (tuning points)
# ---------------------------------------------------------------------------

PAYOUT_CAP = 1_000_000          # USD, above which payout_factor saturates at 1.0
UNKNOWN_PAYOUT = 0.1            # unknown/broken payout: low but not 0 (keeps differentiation by freshness/crowd)
FRESHNESS_HALFLIFE_DAYS = 90.0  # age at which freshness = 0.5
FRESHNESS_UNKNOWN = 0.5         # no launch date → neutral
PUBLIC_CROWD_WEIGHT = 3         # public program = crowd: equivalent to +3 reports in crowd_heat
PATTERN_BASE = 0.5             # pattern_match floor at zero overlap (mismatch ≠ zero out EV)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class AnonResult(object):
    """Outcome of the anonymity precondition. ok=True → live recon allowed; otherwise failed_checks is non-empty."""

    def __init__(self, ok, failed_checks):
        self.ok = ok
        self.failed_checks = failed_checks

    def __repr__(self):
        return "AnonResult(ok=%r, failed_checks=%r)" % (self.ok, self.failed_checks)


class ProgramScore(object):
    """EV score of one program + per-factor breakdown (for ranking transparency)."""

    def __init__(self, name, ev, factors):
        self.name = name
        self.ev = ev
        self.factors = factors  # dict: payout/freshness/crowd/pattern

    def __repr__(self):
        return "ProgramScore(name=%r, ev=%.4f)" % (self.name, self.ev)

    def to_dict(self):
        return {"name": self.name, "ev": self.ev, "factors": self.factors}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _as_number(value):
    """float(value) or None (fail-open: broken field → None, the caller substitutes a default)."""
    if isinstance(value, bool):  # bool is a subtype of int, but payout=True is meaningless
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").replace("$", "").strip())
        except (ValueError, AttributeError):
            return None
    return None


# ---------------------------------------------------------------------------
# EV factors
# ---------------------------------------------------------------------------

def payout_factor(program):
    """max_payout normalized linearly to PAYOUT_CAP; unknown → UNKNOWN_PAYOUT."""
    payout = _as_number(program.get("max_payout"))
    if payout is None or payout <= 0:
        return UNKNOWN_PAYOUT
    return _clamp(payout / PAYOUT_CAP)


def freshness_factor(program, now):
    """halflife-decay: age 0 → 1.0, age=HALFLIFE → 0.5. No launched_ts → neutral."""
    launched = _as_number(program.get("launched_ts"))
    if launched is None:
        return FRESHNESS_UNKNOWN
    age_days = (now - launched) / 86400.0
    if age_days <= 0:
        return 1.0
    return FRESHNESS_HALFLIFE_DAYS / (FRESHNESS_HALFLIFE_DAYS + age_days)


def crowd_heat(program):
    """Crowd = 1 + reports_count (+ PUBLIC_CROWD_WEIGHT if public). Always >= 1."""
    reports = _as_number(program.get("reports_count"))
    if reports is None or reports < 0:
        reports = 0.0
    heat = 1.0 + reports
    if program.get("is_public") is True:
        heat += PUBLIC_CROWD_WEIGHT
    return heat


def crowd_factor(program):
    """1 / crowd_heat: 0 reports, private → 1.0 (best); crowd → →0."""
    return 1.0 / crowd_heat(program)


def pattern_match_factor(program, strong_patterns):
    """Share of the program's tags that fall into our strong un-dup classes, with floor PATTERN_BASE.

    No strong_patterns → neutral 1.0 (we don't punish the absence of a profile).
    Program has no tags → floor (mismatch ≠ zero out EV).
    """
    if not strong_patterns:
        return 1.0
    tags = program.get("tags") or []
    if not isinstance(tags, (list, tuple, set)):
        return PATTERN_BASE
    strong = {str(p).lower() for p in strong_patterns}
    tagset = {str(t).lower() for t in tags}
    if not tagset:
        return PATTERN_BASE
    overlap = len(tagset & strong) / float(len(tagset))
    return PATTERN_BASE + (1.0 - PATTERN_BASE) * overlap


# ---------------------------------------------------------------------------
# EV score + ranking
# ---------------------------------------------------------------------------

def ev_score(program, now=None, strong_patterns=None):
    """EV = payout × freshness × (1/crowd_heat) × pattern_match. fail-open on a broken record."""
    if now is None:
        now = time.time()
    try:
        pf = payout_factor(program)
        ff = freshness_factor(program, now)
        cf = crowd_factor(program)
        pm = pattern_match_factor(program, strong_patterns)
    except Exception:
        # fail-open: any unexpected record shape → zero EV, but NOT a ranking crash
        return ProgramScore(program.get("name", "?") if isinstance(program, dict) else "?", 0.0,
                            {"payout": 0.0, "freshness": 0.0, "crowd": 0.0, "pattern": 0.0})
    ev = pf * ff * cf * pm
    name = program.get("name") or program.get("url") or "?"
    return ProgramScore(name, ev, {"payout": pf, "freshness": ff, "crowd": cf, "pattern": pm})


def rank_programs(programs, now=None, strong_patterns=None):
    """List of ProgramScore sorted by descending EV. Broken records score 0, don't crash the list."""
    if now is None:
        now = time.time()
    scored = []
    for p in (programs or []):
        if not isinstance(p, dict):
            continue  # fail-open: ignore non-dict items
        scored.append(ev_score(p, now=now, strong_patterns=strong_patterns))
    scored.sort(key=lambda s: s.ev, reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Anonymity precondition (fail-CLOSED) + live-recon gateway
# ---------------------------------------------------------------------------

def anonymity_precondition(config):
    """Lightweight fail-closed gate BEFORE live recon. Requires vpn_active / incognito / not_main_login = True.

    Any ambiguity (config not a dict, missing key, value != True) → ok=False. Never crashes
    outward — returns AnonResult(ok=False, ...). This is NOT the full opsec_preflight (that one is needed for
    active/authenticated tests with test_accounts/burner; pure read-only recon is not part of them), but
    identity anonymity is mandatory even for reading public pages.
    """
    failed = []
    if not isinstance(config, dict):
        return AnonResult(False, ["config is not a dict"])
    if config.get("vpn_active") is not True:
        failed.append("VPN/Tor is not active")
    if config.get("incognito") is not True:
        failed.append("incognito profile is not active")
    if config.get("not_main_login") is not True:
        failed.append("logged in to the main account")
    return AnonResult(len(failed) == 0, failed)


def discover_live(urls, config, fetch_fn, now=None, strong_patterns=None):
    """Live recon of public program pages + EV ranking.

    ⛔ Fail-closed: FIRST anonymity_precondition(config). If not ok — fetch_fn is NOT called even once,
    returns (AnonResult, []). This is a structural guarantee of "not a single live call without anonymity".

    fetch_fn(url) -> dict|None: injected page reader (Playwright CF-safe in production; fixture in tests).
    Read-only. Exceptions/None from fetch_fn are swallowed (fail-open per-URL, don't break the whole pass).
    """
    anon = anonymity_precondition(config)
    if not anon.ok:
        return anon, []
    programs = []
    for url in (urls or []):
        try:
            data = fetch_fn(url)
        except Exception:
            data = None  # fail-open: a broken fetch of one page doesn't break recon
        if isinstance(data, dict):
            data.setdefault("url", url)
            programs.append(data)
    ranked = rank_programs(programs, now=now, strong_patterns=strong_patterns)
    return anon, ranked


# ---------------------------------------------------------------------------
# CLI (offline, read-only local JSON)
# ---------------------------------------------------------------------------

def _main(argv=None):
    ap = argparse.ArgumentParser(description="Proactive /deephunt EV-scoring of candidate programs (offline, read-only).")
    ap.add_argument("--programs", required=True, help="path to the JSON list of programs")
    ap.add_argument("--patterns", default="", help="strong classes, comma-separated (e.g. solana,amm,oracle)")
    ap.add_argument("--json", action="store_true", help="output JSON instead of a table")
    args = ap.parse_args(argv)

    try:
        with open(args.programs, "r", encoding="utf-8") as fh:
            programs = json.load(fh)
    except Exception as exc:  # fail-open CLI
        print("error reading %s: %s" % (args.programs, exc), file=sys.stderr)
        return 1

    strong = [p.strip() for p in args.patterns.split(",") if p.strip()]
    ranked = rank_programs(programs, strong_patterns=strong or None)

    if args.json:
        print(json.dumps([s.to_dict() for s in ranked], ensure_ascii=False, indent=2))
    else:
        print("EV     payout fresh crowd patt  name")
        for s in ranked:
            f = s.factors
            print("%.4f %.3f  %.3f %.3f %.3f %s" % (
                s.ev, f["payout"], f["freshness"], f["crowd"], f["pattern"], s.name))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
