# -*- coding: utf-8 -*-
"""Replay: Trust Library web sections (`## § Frontend` / `## § Web2`, Plan 3 Task 5a) + browser-first
mandate §33 (Task 5b) + references to it from hunt.md/dapphunt.md. Proves that the lint REALLY detects
the ABSENCE of the sections (case 1b: the same headers cut out of the real file -> False), is not a no-op, then
confirms the presence of the `ref:` column, non-empty seed rows and both skill references.

+ Plan 4 Task 6: `## § Frontend` 7-primitive starter set (postMessage origin, EIP-712 chainId,
SIWE nonce, auth allowed_domains, Permit/Permit2 deadline, iframe frame-ancestors, token decimals) --
each row carries a non-empty `fingerprint:` AND anti-fingerprint. Section 6 proves FIRING against
`.sdd/backups/invariant_library.md.orig` (pre-Task-6 state: 2 rows) -- the gate must FAIL there and
PASS on the current file.

+ Plan 5 Task 8: `## § Web2` completed 2/7 -> 7/7 (authz, JWT verify, SSRF guard, password-reset,
CORS, SQL/parametrized, session) -- symmetric to section 6, each row carries a non-empty `fingerprint:`
AND anti-fingerprint (`ref:` MAY be `[UNPINNED]`, this is a legit escape allowed by the brief). Section 7
proves FIRING against `.sdd/backups/invariant_library.md.pretask8.orig` (pre-Task-8 state:
2 rows) -- the gate must FAIL there and PASS on the current file."""
import os, sys, re

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT: break
    ROOT = nxt

LIB = os.path.join(ROOT, "bug-bounty-toolkit", "methodology", "invariant_library.md")
LIB_ORIG = os.path.join(ROOT, "bug-bounty-toolkit", "methodology", "plans", ".sdd", "backups",
                         "invariant_library.md.orig")
LIB_ORIG_PRETASK8 = os.path.join(ROOT, "bug-bounty-toolkit", "methodology", "plans", ".sdd", "backups",
                                  "invariant_library.md.pretask8.orig")
MANDATE = os.path.join(ROOT, "bug-bounty-toolkit", "sessions", "_methodology", "browser_first_mandate.md")
HUNT_MD = os.path.join(ROOT, ".claude", "commands", "hunt.md")
DAPPHUNT_MD = os.path.join(ROOT, ".claude", "commands", "dapphunt.md")

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def _has_web_sections(text):
    """True <=> text carries BOTH headers `## § Frontend` and `## § Web2`."""
    return ("## § Frontend" in text) and ("## § Web2" in text)


def _section_text(text, header_prefix):
    """Section text from `## § <header_prefix>` to the next `## ` header (or end of file)."""
    m = re.search(r'(^## § ' + re.escape(header_prefix) + r'.*?)(?=^## |\Z)', text, flags=re.M | re.S)
    return m.group(1) if m else ""


def _table_rows(section_text):
    """Data rows of the section table (list of cells), skipping the header row (the Russian word for
    "Primitive" below is the header marker in invariant_library.md -- kept verbatim) and the
    separator row (`---|---|...`)."""
    rows = []
    for line in section_text.splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        if "Примитив" in s:  # KEPT: Russian header cell "Примитив" ("Primitive") is parser input
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r'-+', c) for c in cells):
            continue
        rows.append(cells)
    return rows


# --- 1) library detection (prove firing, not a no-op) -----------------------------------------
lib_text = open(LIB, encoding="utf-8").read() if os.path.exists(LIB) else ""
check("1a _has_web_sections(real invariant_library.md) -> True", _has_web_sections(lib_text))

# 1b: the same real text with the two section headers CUT OUT -> the detector must return False.
stripped = re.sub(r'^## § Frontend.*$', '', lib_text, flags=re.M)
stripped = re.sub(r'^## § Web2.*$', '', stripped, flags=re.M)
check("1b _has_web_sections(file with the § Frontend/§ Web2 headers cut out) -> False (absence detected)",
      not _has_web_sections(stripped))

# --- 2) both web sections carry a `ref:` column in the table header ---------------------------
frontend_sec = _section_text(lib_text, "Frontend")
web2_sec = _section_text(lib_text, "Web2")
check("2a § Frontend exists as a section", bool(frontend_sec))
check("2b § Web2 exists as a section", bool(web2_sec))
check("2c § Frontend carries `| ref: |` in the table header", "| ref: |" in frontend_sec)
check("2d § Web2 carries `| ref: |` in the table header", "| ref: |" in web2_sec)

# --- 3) each web section carries >=1 seed row with non-empty Invariant + fingerprint ----------
fr_rows = _table_rows(frontend_sec)
w2_rows = _table_rows(web2_sec)
check("3a § Frontend >=1 seed data row (not only the header)", len(fr_rows) >= 1, "rows=%d" % len(fr_rows))
check("3b § Frontend seed rows carry non-empty Invariant(1)+fingerprint(3)",
      len(fr_rows) >= 1 and all(len(r) >= 4 and r[1] and r[3] for r in fr_rows))
check("3c § Web2 >=1 seed data row (not only the header)", len(w2_rows) >= 1, "rows=%d" % len(w2_rows))
check("3d § Web2 seed rows carry non-empty Invariant(1)+fingerprint(3)",
      len(w2_rows) >= 1 and all(len(r) >= 4 and r[1] and r[3] for r in w2_rows))

# --- 4) browser-first mandate doc: exists + carries Playwright + humanize + both skills -------
mandate_exists = os.path.exists(MANDATE)
check("4a browser_first_mandate.md created", mandate_exists)
mandate_text = open(MANDATE, encoding="utf-8").read() if mandate_exists else ""
check("4b mandate contains 'Playwright'", "Playwright" in mandate_text)
check("4c mandate contains 'humanize'", "humanize" in mandate_text.lower())
check("4d mandate mentions /hunt (per-skill instance)", "/hunt" in mandate_text)
check("4e mandate mentions /dapphunt (per-skill instance)", "/dapphunt" in mandate_text)

# --- 5) hunt.md AND dapphunt.md reference browser_first_mandate -------------------------------
hunt_text = open(HUNT_MD, encoding="utf-8").read() if os.path.exists(HUNT_MD) else ""
dapphunt_text = open(DAPPHUNT_MD, encoding="utf-8").read() if os.path.exists(DAPPHUNT_MD) else ""
check("5a hunt.md references browser_first_mandate", "browser_first_mandate" in hunt_text)
check("5b dapphunt.md references browser_first_mandate", "browser_first_mandate" in dapphunt_text)

# --- 6) Task 6: § Frontend carries the 7-primitive starter set, each row with non-empty --------
#        fingerprint(3) AND anti-fingerprint(5). We prove FIRING against the pre-Task-6 .orig backup.
def _frontend_seven_complete(text):
    """True <=> `## § Frontend` carries >=7 data rows, EACH with non-empty Invariant(1)/
    fingerprint(3)/anti-fingerprint(5) and NO fingerprint cell is a bare `[UNPINNED]` placeholder."""
    sec = _section_text(text, "Frontend")
    rows = _table_rows(sec)
    if len(rows) < 7:
        return False
    for r in rows:
        if len(r) < 6:
            return False
        if not r[1].strip() or not r[3].strip() or not r[5].strip():
            return False
        if r[3].strip() == "[UNPINNED]":
            return False
    return True

check("6a § Frontend (current invariant_library.md) >=7 rows, all with fingerprint+anti-fingerprint",
      _frontend_seven_complete(lib_text), "rows=%d" % len(_table_rows(_section_text(lib_text, "Frontend"))))

lib_orig_exists = os.path.exists(LIB_ORIG)
check("6b .sdd/backups/invariant_library.md.orig exists (the implementer backs up as the first step)", lib_orig_exists)
if lib_orig_exists:
    lib_orig_text = open(LIB_ORIG, encoding="utf-8").read()
    check("6c § Frontend (.orig, BEFORE Task 6) does NOT pass the 7-row gate -- proof of FIRING",
          not _frontend_seven_complete(lib_orig_text),
          "rows=%d" % len(_table_rows(_section_text(lib_orig_text, "Frontend"))))
else:
    check("6c .orig backup missing -- FIRING not proven", False, "backup missing")

# --- 7) Task 8: § Web2 carries the full 7-primitive set, each row with non-empty --------------
#        fingerprint(3) AND anti-fingerprint(5). `ref:`(4) MAY be `[UNPINNED]` (legit escape, not
#        part of the fingerprint check) -- unlike §6, where the fingerprint column cannot be a placeholder.
#        We prove FIRING against the pre-Task-8 .pretask8.orig backup (2 rows: authz, JWT verify).
def _web2_seven_complete(text):
    """True <=> `## § Web2` carries >=7 data rows, EACH with non-empty Invariant(1)/fingerprint(3)/
    anti-fingerprint(5) and NO fingerprint cell is a bare `[UNPINNED]` placeholder (`ref:`(4) may
    be `[UNPINNED]` -- this is an escape allowed by the brief, not checked)."""
    sec = _section_text(text, "Web2")
    rows = _table_rows(sec)
    if len(rows) < 7:
        return False
    for r in rows:
        if len(r) < 6:
            return False
        if not r[1].strip() or not r[3].strip() or not r[5].strip():
            return False
        if r[3].strip() == "[UNPINNED]":
            return False
    return True

check("7a § Web2 (current invariant_library.md) >=7 rows, all with fingerprint+anti-fingerprint",
      _web2_seven_complete(lib_text), "rows=%d" % len(_table_rows(_section_text(lib_text, "Web2"))))

lib_orig_pretask8_exists = os.path.exists(LIB_ORIG_PRETASK8)
check("7b .sdd/backups/invariant_library.md.pretask8.orig exists (the implementer backs up as the first step)",
      lib_orig_pretask8_exists)
if lib_orig_pretask8_exists:
    lib_orig_pretask8_text = open(LIB_ORIG_PRETASK8, encoding="utf-8").read()
    check("7c § Web2 (.pretask8.orig, BEFORE Task 8) does NOT pass the 7-row gate -- proof of FIRING",
          not _web2_seven_complete(lib_orig_pretask8_text),
          "rows=%d" % len(_table_rows(_section_text(lib_orig_pretask8_text, "Web2"))))
else:
    check("7c .pretask8.orig backup missing -- FIRING not proven", False, "backup missing")

print("=== LIBRARY + BROWSER-FIRST REPLAY (Plan 3 Task 5 + Plan 4 Task 6 + Plan 5 Task 8) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
