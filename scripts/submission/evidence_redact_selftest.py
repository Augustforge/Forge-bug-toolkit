# -*- coding: utf-8 -*-
"""Selftest for evidence_redact.py — cookie/auth/secret/PII get stripped, HAR structure stays intact, original isn't mutated."""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_redact as er  # noqa: E402

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

R = er._REDACTED
_HE = "Kx7Qw2Zr9Yt4Vb1Nm6Ps3Jd8Hf5Lc0Gg"  # high-entropy (not a placeholder)

# 1) redact_text: Cookie header line
t1 = er.redact_text("GET /x\nCookie: session=abcd1234efgh5678; theme=dark\nAccept: */*")
check("1 cookie header stripped", R in t1 and "abcd1234efgh5678" not in t1, t1)
check("1 non-sensitive header intact (Accept)", "Accept: */*" in t1)

# 2) Bearer token
t2 = er.redact_text("Authorization: Bearer eyJhbGci0iJIabcdef12345.payload.sig")
check("2 Bearer/Authorization stripped", R in t2 and "eyJhbGci0iJIabcdef12345" not in t2, t2)

# 3) session=value pair in body
t3 = er.redact_text("debug: sessionToken=Zx9Qw2Er8Ty7Ui6Op5 was set")
check("3 sessionToken=value stripped", R in t3 and "Zx9Qw2Er8Ty7Ui6Op5" not in t3, t3)

# 4) secret (sk-ant) via secret_patterns
t4 = er.redact_text("config ANTHROPIC=sk-ant-api03-" + (_HE * 3)[:95] + " loaded")
check("4 sk-ant secret stripped", R in t4 and "sk-ant-api03-" + _HE[:20] not in t4, t4[:60])

# 5) PII (email) stripped
t5 = er.redact_text("victim contact: john.doe@realvictim.com in response")
check("5 victim email (PII) stripped", "john.doe@realvictim.com" not in t5, t5)

# 6) clean text with no secrets is untouched
t6_in = "GET /api/products returned 200 with 15 items"
check("6 clean text unchanged", er.redact_text(t6_in) == t6_in)

# 7) sanitize_headers dict
h = er.sanitize_headers({"Cookie": "s=1", "Authorization": "Bearer x", "Content-Type": "application/json"})
check("7 headers: Cookie/Authorization → REDACTED", h["Cookie"] == R and h["Authorization"] == R)
check("7 headers: Content-Type intact", h["Content-Type"] == "application/json")

# 8) redact_har: full structure
har = {"log": {"entries": [{
    "request": {
        "method": "GET", "url": "https://t/x",
        "headers": [{"name": "Cookie", "value": "session=SECRET123"}, {"name": "Accept", "value": "*/*"}],
        "cookies": [{"name": "session", "value": "SECRET123"}],
        "postData": {"text": "Authorization: Bearer abcdef1234567890xyz"},
    },
    "response": {
        "status": 200,
        "headers": [{"name": "Set-Cookie", "value": "sid=TOPSECRET; HttpOnly"}, {"name": "Server", "value": "nginx"}],
        "cookies": [{"name": "sid", "value": "TOPSECRET"}],
        "content": {"text": "user email leak@victim.com and key sk-ant-api03-" + (_HE * 3)[:95]},
    },
}]}}
har_orig = copy.deepcopy(har)
red = er.redact_har(har)
e = red["log"]["entries"][0]
req_cookie = [x for x in e["request"]["headers"] if x["name"] == "Cookie"][0]["value"]
resp_setcookie = [x for x in e["response"]["headers"] if x["name"] == "Set-Cookie"][0]["value"]
check("8 HAR request Cookie-header stripped", req_cookie == R, req_cookie)
check("8 HAR response Set-Cookie stripped", resp_setcookie == R)
check("8 HAR request cookies array stripped", e["request"]["cookies"] == [R])
check("8 HAR postData Bearer stripped", "abcdef1234567890xyz" not in e["request"]["postData"]["text"])
check("8 HAR response content: PII+secret stripped",
      "leak@victim.com" not in e["response"]["content"]["text"]
      and "sk-ant-api03-" + _HE[:20] not in e["response"]["content"]["text"])
check("8 HAR non-sensitive headers intact (Accept/Server)",
      any(x["name"] == "Accept" and x["value"] == "*/*" for x in e["request"]["headers"])
      and any(x["name"] == "Server" and x["value"] == "nginx" for x in e["response"]["headers"]))
check("8 HAR structure intact (status 200)", e["response"]["status"] == 200)

# 9) original NOT mutated (deepcopy)
check("9 original HAR unchanged (immutability)", har == har_orig)

print("=== EVIDENCE_REDACT SELFTEST ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + str(detail)) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks passed" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
