# -*- coding: utf-8 -*-
"""Replay for web_severity.py (Task 7, §9/§35.5, FDE Plan 4).

Proves: (1) `severity()` really computes a deterministic tier on FRONTEND_PROFILE for all
4 combinations from the brief + boundary cases on every boundary of the threshold table; (2) fail-open on
an unknown `profile`, missing/garbage factor values -- NOT a crash, a safe default;
(3) `platform_mapping` is non-empty for all 5 platforms on EVERY verdict; (4) `SeverityVerdict` --
EXACTLY this type name (not `Verdict`, which collides with pi_guard_lib.Verdict); (5) extensibility: a NEW
profile is registered via `register_profile()` from OUTSIDE, without a single edit to web_severity.py, and
`severity()` dispatches it immediately -- this is the contract on which Plan 5 will add WEB2_PROFILE.
"""
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ws = _load("web_severity", os.path.join(HERE, "web_severity.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


severity = ws.severity
SeverityVerdict = ws.SeverityVerdict
_PLATFORMS = ws._PLATFORMS


def assert_platforms_complete(n_prefix, verdict):
    pm = verdict.platform_mapping
    missing = [p for p in _PLATFORMS if not pm.get(p)]
    check("%s: platform_mapping non-empty for all 5 platforms" % n_prefix, not missing,
          "missing=%r pm=%r" % (missing, pm))


# ── CASE A: sign x default-route x protocol -> Critical or High (from the brief) ───────────────
vA = severity({"user_interaction_gate": "sign", "reachability": "default-route",
               "blast_radius": "protocol"}, profile="frontend")
check("caseA sign+default-route+protocol -> Critical or High", vA.tier in ("Critical", "High"),
      "got %r" % (vA.tier,))
check("caseA type(verdict) is SeverityVerdict", isinstance(vA, SeverityVerdict))
assert_platforms_complete("caseA", vA)

# ── CASE B: visit x feature-flag x one-user -> Low (from the brief) ────────────────────────────
vB = severity({"user_interaction_gate": "visit", "reachability": "feature-flag",
               "blast_radius": "one-user"}, profile="frontend")
check("caseB visit+feature-flag+one-user -> Low", vB.tier == "Low", "got %r" % (vB.tier,))
assert_platforms_complete("caseB", vB)

# ── CASE C: unreachable (any other factors) -> Info, force_tier short-circuit ──────────────────
vC1 = severity({"user_interaction_gate": "sign", "reachability": "unreachable",
                "blast_radius": "protocol"}, profile="frontend")
vC2 = severity({"user_interaction_gate": "click", "reachability": "unreachable",
                "blast_radius": "one-user"}, profile="frontend")
check("caseC1 unreachable+sign+protocol -> Info (force_tier outweighs even protocol)",
      vC1.tier == "Info", "got %r" % (vC1.tier,))
check("caseC2 unreachable+click+one-user -> Info", vC2.tier == "Info", "got %r" % (vC2.tier,))
assert_platforms_complete("caseC1", vC1)

# ── CASE D: click x default-route x all-users -> High or Medium (from the brief) ───────────────
vD = severity({"user_interaction_gate": "click", "reachability": "default-route",
               "blast_radius": "all-users"}, profile="frontend")
check("caseD click+default-route+all-users -> High or Medium", vD.tier in ("High", "Medium"),
      "got %r" % (vD.tier,))
check("caseD tier no stricter than caseA (blast_radius dominates: under the 2026-08-05 calibration "
      "click+default-route+all-users=score6 <= sign+default-route+protocol=score7 -- "
      "both High, D never exceeds A despite the 'easier' click gate)",
      ws.TIERS.index(vD.tier) >= ws.TIERS.index(vA.tier), "vD=%r vA=%r" % (vD.tier, vA.tier))
assert_platforms_complete("caseD", vD)

# ── CASE E-J: threshold-table boundaries (8/6/4/Low) -- each exactly on the boundary ───────────
# user_interaction_gate weights calibrated 2026-08-05 (CVSS-aligned): visit=2 > click=1 > sign=0.
vE = severity({"user_interaction_gate": "visit", "reachability": "entry-exists",
               "blast_radius": "protocol"}, profile="frontend")  # 2+1+5=8
check("caseE score=8 (lower bound of Critical) -> Critical", vE.tier == "Critical",
      "got %r" % (vE.tier,))

vF = severity({"user_interaction_gate": "click", "reachability": "entry-exists",
               "blast_radius": "protocol"}, profile="frontend")  # 1+1+5=7
check("caseF score=7 -> High", vF.tier == "High", "got %r" % (vF.tier,))

vG = severity({"user_interaction_gate": "sign", "reachability": "entry-exists",
               "blast_radius": "protocol"}, profile="frontend")  # 0+1+5=6
check("caseG score=6 (lower bound of High) -> High", vG.tier == "High", "got %r" % (vG.tier,))

vH = severity({"user_interaction_gate": "sign", "reachability": "default-route",
               "blast_radius": "all-users"}, profile="frontend")  # 0+2+3=5
check("caseH score=5 -> Medium", vH.tier == "Medium", "got %r" % (vH.tier,))

vI = severity({"user_interaction_gate": "click", "reachability": "feature-flag",
               "blast_radius": "all-users"}, profile="frontend")  # 1+0+3=4
check("caseI score=4 (lower bound of Medium) -> Medium", vI.tier == "Medium", "got %r" % (vI.tier,))

vJ = severity({"user_interaction_gate": "sign", "reachability": "default-route",
               "blast_radius": "one-user"}, profile="frontend")  # 0+2+1=3
check("caseJ score=3 (upper bound of Low) -> Low", vJ.tier == "Low", "got %r" % (vJ.tier,))

# ── CASE K: missing factors -> fail-open to the conservative missing_defaults ──────────────────
vK = severity({}, profile="frontend")
check("caseK {} (all factors missing) -> Low (conservative default, NOT Critical)",
      vK.tier == "Low", "got %r" % (vK.tier,))
assert_platforms_complete("caseK", vK)

# ── CASE L: garbage/foreign factor values -> the same fail-open path, NOT a crash ──────────────
vL = severity({"user_interaction_gate": "teleport", "reachability": "quantum-tunnel",
               "blast_radius": "multiverse"}, profile="frontend")
check("caseL garbage values -> Low (fail-open to missing_defaults, not a crash)",
      vL.tier == "Low", "got %r" % (vL.tier,))
check("caseL factors=None (not a dict) -> does not crash", severity(None, profile="frontend").tier == "Low")

# ── CASE M: unknown profile (not registered) -> fail-open, NOT a crash ─────────────────────────
# NOTE: Plan 5 registers "web2" in web_severity.py (see the WEB2 CASE block below) -- it is no longer an
# unknown-profile example, so a name that is certainly unregistered is used here.
vM = severity({"anything": "goes"}, profile="profile_never_registered")
check("caseM unknown profile -> does not crash, returned a SeverityVerdict",
      isinstance(vM, SeverityVerdict))
check("caseM unknown profile -> safe default tier=Info", vM.tier == "Info",
      "got %r" % (vM.tier,))
assert_platforms_complete("caseM", vM)

# ── CASE N: determinism -- 2 boundary combinations, a repeated call = an identical verdict ─────
vN1a = severity({"user_interaction_gate": "sign", "reachability": "default-route",
                 "blast_radius": "protocol"}, profile="frontend")
vN1b = severity({"user_interaction_gate": "sign", "reachability": "default-route",
                 "blast_radius": "protocol"}, profile="frontend")
check("caseN1 determinism: repeating the caseA combination yields an identical SeverityVerdict",
      vN1a == vN1b, "a=%r b=%r" % (vN1a, vN1b))

vN2a = severity({"user_interaction_gate": "visit", "reachability": "feature-flag",
                 "blast_radius": "one-user"}, profile="frontend")
vN2b = severity({"user_interaction_gate": "visit", "reachability": "feature-flag",
                 "blast_radius": "one-user"}, profile="frontend")
check("caseN2 determinism: repeating the caseB combination yields an identical SeverityVerdict",
      vN2a == vN2b, "a=%r b=%r" % (vN2a, vN2b))

# ── CASE O: result type -- EXACTLY SeverityVerdict, not Verdict (pi_guard_lib collision) ───────
check("caseO type name == 'SeverityVerdict'", SeverityVerdict.__name__ == "SeverityVerdict",
      "got %r" % (SeverityVerdict.__name__,))
check("caseO type name != 'Verdict' (does not collide with pi_guard_lib.Verdict)",
      SeverityVerdict.__name__ != "Verdict")
check("caseO SeverityVerdict has exactly the fields tier/rationale/platform_mapping",
      SeverityVerdict._fields == ("tier", "rationale", "platform_mapping"),
      "got %r" % (SeverityVerdict._fields,))

# ── CASE P: __primary__ appears only when platform is recognized (case-insensitive) ────────────
vP1 = severity({"user_interaction_gate": "click", "reachability": "default-route",
                "blast_radius": "protocol"}, platform="Immunefi", profile="frontend")
check("caseP1 platform='Immunefi' (different case) -> __primary__ added",
      "__primary__" in vP1.platform_mapping)
vP2 = severity({"user_interaction_gate": "click", "reachability": "default-route",
                "blast_radius": "protocol"}, platform="generic", profile="frontend")
check("caseP2 platform='generic' -> __primary__ NOT added (all 5 platforms still in place)",
      "__primary__" not in vP2.platform_mapping)
assert_platforms_complete("caseP2", vP2)

# ── CASE Q: extensibility -- a NEW profile is registered from OUTSIDE, web_severity.py untouched
# Imitates what Plan 5 will do for WEB2_PROFILE: its own factors (not user_interaction_gate/
# reachability/blast_radius -- DIFFERENT names), its own force_tier/thresholds/missing_defaults.
TEST_WEB2_LIKE_PROFILE = ws.FactorProfile(
    name="test_web2_like",
    factors={
        "auth_required": {"none": 3, "session": 1},
        "data_sensitivity": {"pii": 3, "public": 0},
    },
    force_tier={"auth_required": {"out-of-scope": "Info"}},
    thresholds=[(5, "Critical"), (3, "High"), (1, "Medium"), (0, "Low")],
    missing_defaults={"auth_required": "session", "data_sensitivity": "public"},
    default_tier="Low",
)
ws.register_profile("test_web2_like", TEST_WEB2_LIKE_PROFILE)

vQ1 = severity({"auth_required": "none", "data_sensitivity": "pii"}, profile="test_web2_like")
check("caseQ1 new profile (registered from OUTSIDE core) is dispatched: score=6 -> Critical",
      vQ1.tier == "Critical", "got %r" % (vQ1.tier,))
assert_platforms_complete("caseQ1", vQ1)

vQ2 = severity({"auth_required": "out-of-scope", "data_sensitivity": "pii"}, profile="test_web2_like")
check("caseQ2 new profile: its own force_tier short-circuit (out-of-scope) -> Info",
      vQ2.tier == "Info", "got %r" % (vQ2.tier,))

vQ3 = severity({}, profile="test_web2_like")
# missing_defaults -> session(1)+public(0)=1 -- under THIS profile's thresholds (1,"Medium") that is still
# Medium, not Low (the profile's own thresholds, not FRONTEND_PROFILE) -- the very fact that the defaults
# resolve and the score is computed WITHOUT a crash on an empty {} is what this case proves.
check("caseQ3 new profile: fail-open on empty factors -> its own missing_defaults, "
      "score computed without a crash (session+public=1 -> Medium by ITS OWN thresholds)",
      vQ3.tier == "Medium", "got %r" % (vQ3.tier,))

check("caseQ4 core (severity/_REGISTRY) did not require editing web_severity.py -- the profile lives "
      "only in this process's runtime _REGISTRY", "test_web2_like" in ws._REGISTRY)


# ── WEB2 CASE 1: unauth x full-db x financial -> Critical (from the brief, score=2+4+3=9) ──────
w1 = severity({"auth_barrier": "unauth", "blast_radius": "full-db",
               "data_sensitivity": "financial"}, profile="web2")
check("web2case1 unauth+full-db+financial -> Critical", w1.tier == "Critical", "got %r" % (w1.tier,))
assert_platforms_complete("web2case1", w1)

# ── WEB2 CASE 2: admin x one-user x public -> Low/Info (from the brief, score=0+1+0=1) ─────────
w2 = severity({"auth_barrier": "admin", "blast_radius": "one-user",
               "data_sensitivity": "public"}, profile="web2")
check("web2case2 admin+one-user+public -> Low or Info", w2.tier in ("Low", "Info"),
      "got %r" % (w2.tier,))
assert_platforms_complete("web2case2", w2)

# ── WEB2 CASE 3-4: threshold-table boundaries (Medium/High) ────────────────────────────────────
w3 = severity({"auth_barrier": "user", "blast_radius": "all-users",
               "data_sensitivity": "pii"}, profile="web2")  # 1+2+1=4
check("web2case3 score=4 (lower bound of Medium) -> Medium", w3.tier == "Medium",
      "got %r" % (w3.tier,))

w4 = severity({"auth_barrier": "user", "blast_radius": "cross-tenant",
               "data_sensitivity": "credentials"}, profile="web2")  # 1+3+2=6
check("web2case4 score=6 (lower bound of High) -> High", w4.tier == "High", "got %r" % (w4.tier,))

# ── WEB2 CASE 5: missing factors -> fail-open to the conservative missing_defaults ─────────────
w5 = severity({}, profile="web2")
check("web2case5 {} (all factors missing) -> Low (conservative default, NOT Critical)",
      w5.tier == "Low", "got %r" % (w5.tier,))
assert_platforms_complete("web2case5", w5)

# ── WEB2 CASE 6: garbage/foreign factor values -> the same fail-open path, NOT a crash, NOT an overstatement
w6 = severity({"auth_barrier": "root", "blast_radius": "global-internet",
               "data_sensitivity": "top-secret"}, profile="web2")
check("web2case6 garbage values -> Low (fail-open to missing_defaults, not a crash, not an overstatement)",
      w6.tier == "Low", "got %r" % (w6.tier,))
check("web2case6b factors=None (not a dict) -> does not crash", severity(None, profile="web2").tier == "Low")

# ── WEB2 CASE 7: platform_mapping -- the same set of platforms as FRONTEND ─────────────────────
w7 = severity({"auth_barrier": "unauth", "blast_radius": "cross-tenant",
               "data_sensitivity": "credentials"}, platform="hackerone", profile="web2")
check("web2case7 __primary__ added for platform='hackerone'", "__primary__" in w7.platform_mapping)
assert_platforms_complete("web2case7", w7)

# ── WEB2 CASE 8: determinism -- a repeated call = an identical verdict ─────────────────────────
w8a = severity({"auth_barrier": "unauth", "blast_radius": "full-db",
                "data_sensitivity": "financial"}, profile="web2")
w8b = severity({"auth_barrier": "unauth", "blast_radius": "full-db",
                "data_sensitivity": "financial"}, profile="web2")
check("web2case8 determinism: repeating the web2case1 combination yields an identical SeverityVerdict",
      w8a == w8b, "a=%r b=%r" % (w8a, w8b))


print("=== WEB_SEVERITY REPLAY (Task 7, §9/§35.5, FDE Plan 4) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
