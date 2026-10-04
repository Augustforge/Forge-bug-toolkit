# -*- coding: utf-8 -*-
"""web_severity -- a single severity calculator for web profiles (Task 7, §9/§35.5, FDE Plan 4).

Replaces the scattered string-based severity with ONE core: `severity(factors, platform, profile)`.
Plan 4 registers FRONTEND_PROFILE (Web3 dApp frontend: user_interaction_gate / reachability /
blast_radius). Plan 5 will add WEB2_PROFILE (its own factors, e.g. auth_required/data_sensitivity)
VIA `register_profile()`, WITHOUT touching the code below -- see the docstring of `register_profile()`.

The core does NOT hardcode factor names. `FactorProfile` is the factor-profile contract: an arbitrary set
of factors, each with an arbitrary domain of values with its own weights; the core resolves the user's factors dict
against THIS contract, sums the weights, matches the threshold table and (optionally) a `force_tier`
short-circuit (e.g. reachability="unreachable" -> Info regardless of the other
factors). Any profile with ANY factor names goes through the same path -- including the
generic rationale builder `_default_rationale`, which also does not know the profile's factor names.

Fail-open everywhere (Global Constraint of the brief): unknown `profile` -> safe default (tier=Info +
explanation in rationale), NOT a crash. An unknown/missing factor value inside a known
profile -> fail-open to the CONSERVATIVE (least severity-weighted) default of that factor -- we never
inflate severity because of leaky input data. Any unexpected exception during scoring --
the same fail-open path (second line of defense, symmetric to pi_guard_lib.scan()).
"""

import collections


# ---------------------------------------------------------------------------
# SeverityVerdict -- EXACTLY this name. `Verdict` is already taken by pi_guard_lib.Verdict (namedtuple
# score/matched/layers/blocked/suspect) -- a different domain (prompt-injection scan); a name collision
# would be pure confusion on a joint import. SeverityVerdict is a namedtuple, the same pattern
# as pi_guard_lib.Verdict (a light immutable result, comparable by ==  -- needed for the
# determinism test).
# ---------------------------------------------------------------------------

SeverityVerdict = collections.namedtuple("SeverityVerdict", ["tier", "rationale", "platform_mapping"])

TIERS = ("Critical", "High", "Medium", "Low", "Info")


# ---------------------------------------------------------------------------
# FactorProfile -- the pluggable contract of one factor-profile (frontend / web2 / ...).
# ---------------------------------------------------------------------------

class FactorProfile(object):
    """One registered factor profile.

    - `name` -- the profile id (usually matches the registry key).
    - `factors` -- {factor_name: {value: weight_int}}. The domain of allowed values of a factor = the keys
      of its inner dict; the weight is the contribution to the total score.
    - `force_tier` -- {factor_name: {value: tier}}. If the RESOLVED value of a factor lands
      here -- SHORT-CIRCUIT: the given tier is returned immediately, the score is not
      computed at all (example: reachability="unreachable" -> "Info" regardless of
      interaction/blast_radius -- "a route in code != reachable").
    - `thresholds` -- [(min_score, tier), ...] SORTED BY DESCENDING min_score; the first threshold
      that score >= min_score satisfies determines the tier.
    - `missing_defaults` -- {factor_name: default_value}. Used when a factor is absent
      from the input `factors` OR holds a value outside the domain (typo / foreign enum) -- fail-open, not
      a crash. The default MUST be the least severity-weighted value of the factor (conservative: better
      to underestimate severity on garbage input than to overestimate).
    - `default_tier` -- the final fallback if the score fell under NO threshold (protection against a
      profile with a "hole" in thresholds -- the core is never left without a tier).
    - `rationale_fn(profile_name, tier, score, resolved, factors, forced_by) -> str` -- optional;
      by default `None` -> the core uses the generic `_default_rationale` (also does NOT know the profile's
      factor names, works over `resolved`/`factors` universally). A profile may pass its own,
      more human-readable rationale -- this is the only profile-specific hook,
      and it is optional.
    """

    def __init__(self, name, factors, force_tier=None, thresholds=None,
                 missing_defaults=None, default_tier="Low", rationale_fn=None):
        self.name = name
        self.factors = factors
        self.force_tier = force_tier if force_tier is not None else {}
        self.thresholds = thresholds if thresholds is not None else []
        self.missing_defaults = missing_defaults if missing_defaults is not None else {}
        self.default_tier = default_tier
        self.rationale_fn = rationale_fn

    def __repr__(self):
        return "FactorProfile(name=%r)" % (self.name,)


# ---------------------------------------------------------------------------
# FRONTEND_PROFILE -- Plan 4 (web3 dApp frontend). Three factors from the brief.
# ---------------------------------------------------------------------------
#
# Weights (0..N, higher = higher severity) -- the implementer's judgment from the wording of the brief:
#
# user_interaction_gate -- "how many user actions are needed": calibrated 2026-08-05 --
# CVSS User-Interaction convention, zero-click = worst. Industry standard (CVSS UI / HackerOne):
# FEWER required user actions = HIGHER severity, not the other way around. "visit" (0 actions -- fires
# on a plain visit to a legit dApp, zero-click) = the heaviest gate; "click" (one interaction) --
# medium; "sign" (a conscious transaction signature -- the most friction, the victim explicitly consents)
# = the smallest contribution. Signature-integrity bugs do NOT lose severity entirely because of this -- they are usually
# pulled up by a high `blast_radius` (protocol/all-users), see the example under blast_radius below:
#   visit=2 (zero-click, CVSS-worst) > click=1 (baseline) > sign=0 (conscious-consent gate, min)
#
# reachability -- "a route in code != reachable": default-route (the user sees it by default) max;
# entry-exists (there is a UI path, but not the default) medium; feature-flag (a non-default flag is needed) min
# of the "still alive"; unreachable -- does NOT participate in the score, forces Info via force_tier:
#   default-route=2 > entry-exists=1 > feature-flag=0 ; unreachable -> force_tier "Info"
#
# blast_radius -- "walk backward from drain/leak/phish", the DOMINANT factor (protocol-level damage
# outweighs the interaction+reachability difference -- see test cases D vs A in web_severity_replay.py:
# click+default-route+all-users (score 6, High) <= sign+default-route+protocol (score 7, High) --
# under the new calibration both fall into the same tier, but D is never stricter than A, despite the "easier"
# click interaction gate):
#   protocol=5 > all-users=3 > one-user=1
#
# score = interaction_weight + reachability_weight + blast_weight (range 1..9 on non-forcing
# values; unreachable is forced BEFORE scoring, the score is not returned at all).
# thresholds: score>=8 Critical, >=6 High, >=4 Medium, otherwise Low.

FRONTEND_PROFILE = FactorProfile(
    name="frontend",
    factors={
        "user_interaction_gate": {"visit": 2, "click": 1, "sign": 0},
        "reachability": {"default-route": 2, "entry-exists": 1, "feature-flag": 0},
        "blast_radius": {"protocol": 5, "all-users": 3, "one-user": 1},
    },
    force_tier={
        "reachability": {"unreachable": "Info"},
    },
    thresholds=[(8, "Critical"), (6, "High"), (4, "Medium"), (0, "Low")],
    missing_defaults={
        "user_interaction_gate": "sign",       # conservative: the heaviest (0-weight) gate
        "reachability": "feature-flag",        # conservative: the least accessible of the NON-forced
        "blast_radius": "one-user",            # conservative: the smallest blast
    },
    default_tier="Low",
)


# ---------------------------------------------------------------------------
# WEB2_PROFILE -- Plan 5 (classic web2: API/backend/webapp). Three factors from the brief,
# CVSS-aligned like FRONTEND ("lower barrier = higher severity").
# ---------------------------------------------------------------------------
#
# Weights (0..N, higher = higher severity) -- the same CVSS convention as FRONTEND, applied to
# the web2 factors of the brief:
#
# auth_barrier -- CVSS Privileges Required (PR): FEWER privileges needed by the attacker = HIGHER severity.
# "unauth" (an exploit without a single valid session -- the worst case PR:None) weighs the most;
# "user" (a valid but unprivileged session is needed) -- the middle; "admin" (privileged
# credentials are needed -- the most friction, PR:High) -- the minimum:
#   unauth=2 > user=1 > admin=0
#
# blast_radius -- "walk backward from leak/takeover", the dominant factor (as with FRONTEND) --
# 4 values (one wider than FRONTEND, since web2 distinguishes per-tenant from per-instance damage):
#   full-db=4 > cross-tenant=3 > all-users=2 > one-user=1
#
# data_sensitivity -- "what exactly leaks/changes": public (already public -- minimal contribution) <
# pii (personal data) < credentials (account access) < financial (money/payment data --
# the maximum):
#   financial=3 > credentials=2 > pii=1 > public=0
#
# score = auth_weight + blast_weight + data_weight (range 1..9 -- symmetric to FRONTEND).
# thresholds are chosen so that unauth+full-db+financial (2+4+3=9) -> Critical, while
# admin+one-user+public (0+1+0=1) falls into the default (0, "Low") bucket: score>=8 Critical, >=6 High,
# >=4 Medium, otherwise Low.

WEB2_PROFILE = FactorProfile(
    name="web2",
    factors={
        "auth_barrier": {"unauth": 2, "user": 1, "admin": 0},
        "blast_radius": {"one-user": 1, "all-users": 2, "cross-tenant": 3, "full-db": 4},
        "data_sensitivity": {"public": 0, "pii": 1, "credentials": 2, "financial": 3},
    },
    thresholds=[(8, "Critical"), (6, "High"), (4, "Medium"), (0, "Low")],
    missing_defaults={
        "auth_barrier": "admin",           # conservative: the heaviest (0-weight) barrier
        "blast_radius": "one-user",        # conservative: the smallest blast
        "data_sensitivity": "public",      # conservative: the least sensitive data
    },
    default_tier="Low",
)


# ---------------------------------------------------------------------------
# Factor-profile registry -- the pluggable extension point for Plan 5.
# ---------------------------------------------------------------------------

_REGISTRY = {"frontend": FRONTEND_PROFILE}


def register_profile(name, profile_def):
    """Registers a factor profile under `name` in the shared registry. Plan 5 calls EXACTLY this:
    `register_profile("web2", WEB2_PROFILE)` -- `severity()` below does NOT change, the dispatch on
    `profile` already reads from `_REGISTRY` dynamically. `profile_def` is any `FactorProfile` with
    ITS OWN factor names (the core is not tied to user_interaction_gate/reachability/blast_radius --
    that is specific ONLY to FRONTEND_PROFILE)."""
    _REGISTRY[name] = profile_def


register_profile("web2", WEB2_PROFILE)


# ---------------------------------------------------------------------------
# platform_mapping -- per-platform rubrics. Source: .claude/commands/dapphunt.md:583-587
# ("Severity rubrics (per platform)"). Info is NOT in the skill's original text (it describes in prose
# only 4 tiers) -- extended by the implementer to a 5th tier with an honest "informational / outside the
# payout range" label per platform, rather than an invented number/slang.
# ---------------------------------------------------------------------------

_PLATFORMS = ("hackenproof", "immunefi", "cantina", "hackerone", "bugcrowd")

_TIER_PLATFORM_TEXT = {
    "Critical": {
        "hackenproof": "Critical -- no user action / private key leak",
        "immunefi": "Critical -- direct fund loss (scope-defined max)",
        "cantina": "Critical -- loss w/o user interaction",
        "hackerone": "Critical -- CVSS 9.0-10.0",
        "bugcrowd": "P1 -- VRT Critical",
    },
    "High": {
        "hackenproof": "High -- user-click + significant loss (SynFutures class)",
        "immunefi": "High -- $10-50k tier",
        "cantina": "High -- loss + minor friction",
        "hackerone": "High -- CVSS 7.0-8.9",
        "bugcrowd": "P2 -- VRT High",
    },
    "Medium": {
        "hackenproof": "Medium -- social eng + impact",
        "immunefi": "Medium -- $1-10k tier",
        "cantina": "Medium -- loss + significant friction",
        "hackerone": "Medium -- CVSS 4.0-6.9",
        "bugcrowd": "P3 -- VRT Medium",
    },
    "Low": {
        "hackenproof": "Low -- PII / hygiene / UX DoS",
        "immunefi": "Low -- Insight tier",
        "cantina": "Low -- degraded UX",
        "hackerone": "Low -- CVSS 0.1-3.9",
        "bugcrowd": "P4 -- VRT Low",
    },
    "Info": {
        "hackenproof": "Informational -- below Low, no payout tier",
        "immunefi": "N/A -- below Insight, informational only",
        "cantina": "Info -- Cantina's own informational category (separate from Gas)",
        "hackerone": "None -- CVSS 0.0 (informational)",
        "bugcrowd": "P5 / Informational -- below VRT P4",
    },
}


def _platform_mapping_for_tier(tier, platform):
    """ALWAYS returns all 5 canonical platforms (non-empty strings), regardless of `platform`.
    If `platform` (case-insensitive) is recognized as one of the 5 -- adds a convenience key
    `__primary__` duplicating its label. An unknown tier (should not happen, but fail-open) ->
    the Info table."""
    table = _TIER_PLATFORM_TEXT.get(tier, _TIER_PLATFORM_TEXT["Info"])
    mapping = dict(table)
    key = platform.strip().lower() if isinstance(platform, str) else ""
    if key in mapping:
        mapping["__primary__"] = mapping[key]
    return mapping


# ---------------------------------------------------------------------------
# Generic rationale -- does NOT know the factor names of a specific profile, works over resolved/factors.
# ---------------------------------------------------------------------------

def _default_rationale(profile_name, tier, score, resolved, factors, forced_by):
    if forced_by is not None:
        fname, val, forced_tier = forced_by
        return ("profile=%s tier=%s -- %s=%s forces %s regardless of the other factors "
                "(force_tier short-circuit)." % (profile_name, tier, fname, val, forced_tier))
    parts = []
    for fname in sorted(resolved):
        val = resolved[fname]
        weight = factors.get(fname, {}).get(val, 0)
        parts.append("%s=%s(+%d)" % (fname, val, weight))
    return "profile=%s tier=%s score=%d [%s]" % (profile_name, tier, score, ", ".join(parts))


# ---------------------------------------------------------------------------
# Core -- _score_profile + severity()
# ---------------------------------------------------------------------------

def _score_profile(profile_def, factors):
    """Resolves `factors` against `profile_def` (fail-open on unknown/missing values), checks the
    force_tier short-circuit, otherwise computes the score and matches thresholds.

    Returns (tier, score_or_None, resolved, forced_by_or_None). `score` == None exactly when
    force_tier fired (see forced_by)."""
    resolved = {}
    for fname, weight_map in profile_def.factors.items():
        valid = set(weight_map) | set(profile_def.force_tier.get(fname, {}))
        val = factors.get(fname) if isinstance(factors, dict) else None
        if val not in valid:
            val = profile_def.missing_defaults.get(fname)
        resolved[fname] = val

    for fname, val in resolved.items():
        overrides = profile_def.force_tier.get(fname, {})
        if val in overrides:
            return overrides[val], None, resolved, (fname, val, overrides[val])

    score = 0
    for fname, val in resolved.items():
        score += profile_def.factors.get(fname, {}).get(val, 0)

    tier = profile_def.default_tier
    for min_score, t in profile_def.thresholds:
        if score >= min_score:
            tier = t
            break

    return tier, score, resolved, None


def severity(factors: dict, platform: str = "generic", profile: str = "frontend") -> SeverityVerdict:
    """The single entry point. `factors` -- a dict of the profile's factors (see FRONTEND_PROFILE for Plan 4, keys
    `user_interaction_gate`/`reachability`/`blast_radius`). `platform` -- an optional hint
    (hackenproof/immunefi/cantina/hackerone/bugcrowd/generic); does NOT filter platform_mapping (it
    ALWAYS carries all 5 platforms) -- it only adds the convenience key `__primary__` if platform is
    recognized. `profile` -- an id in the registry (see `register_profile()`); an unknown profile ->
    fail-open default (tier=Info, rationale explains the reason), NOT a crash."""
    profile_def = _REGISTRY.get(profile)
    if profile_def is None:
        tier = "Info"
        rationale = ("profile=%r is not registered (registry: %s) -- fail-open default %s, severity "
                     "NOT computed. Register it via register_profile() before calling."
                     % (profile, sorted(_REGISTRY), tier))
        return SeverityVerdict(tier=tier, rationale=rationale,
                                platform_mapping=_platform_mapping_for_tier(tier, platform))

    try:
        tier, score, resolved, forced_by = _score_profile(profile_def, factors)
        rationale_fn = profile_def.rationale_fn or _default_rationale
        rationale = rationale_fn(profile_def.name, tier, score, resolved, profile_def.factors, forced_by)
    except Exception as exc:
        tier = "Info"
        rationale = "profile=%r failed during scoring (%r) -- fail-open default %s." % (profile, exc, tier)

    return SeverityVerdict(tier=tier, rationale=rationale,
                            platform_mapping=_platform_mapping_for_tier(tier, platform))
