#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""secret_patterns.py — shared detection core for the Exposure Engine (P0-2).

A single source of patterns/decoders/classifiers for ALL surfaces that search for secrets and
sensitive data: the static scanner (`secret_exposure_scanner.py`), the runtime sweep
(`runtime_harness.py`), the CI scanner (`cicd_leak_scanner.py`). One core → two+ callers.

Philosophy (Cat 4.10):
  - Detect the MECHANISM (a secret / data-in-code / on-the-client), NOT the signatures of specific hacks (anti-overfit).
  - Look EVERYWHERE and in ENCODED form (a decode layer before matching) — a key on a page is often base64.
  - Anti-FP takes priority over recall on noisy classes: over-flagging (an analyst will check) is safer than a silent
    miss on production code. vendored — hard-skipped entirely; test — anvil keys + PII + financial are muted
    (fixtures/examples), but real crypto keys/secrets in test STILL surface (they may be a genuine
    leak); placeholder/low-entropy/example values are muted on all paths.
  - White-hat: `redact()` NEVER returns a secret in full (no-exfil, idea J).

Main API:
    scan_blob(text, path_kind=None, source="file", enable_pii=True, enable_decode=True) -> list[dict]
Returns findings: {cls, kind, severity, redacted, evidence, decoded_via}. PII clustering and
key-verify are done by the CALLER (scanner), not this core.
"""
import base64
import binascii
import gzip
import hashlib
import json
import math
import os
import re
import urllib.parse

# ── Path classification (context decides the test-vs-prod nuance) ───────────────────
_VENDOR_RE = re.compile(
    r"(^|[\\/])(node_modules|vendor|dependencies|third[_-]?party|\.git|dist[\\/]vendor|"
    r"bower_components|site-packages|\.venv|venv)([\\/]|$)", re.I)
_TEST_RE = re.compile(
    r"(^|[\\/])(tests?|spec|specs|__tests__|__mocks__|fixtures?|mocks?|e2e|testdata|examples?|"
    r"samples?)([\\/]|$)|[._-](test|spec|mock|fixture|example)\.", re.I)
_DEPLOY_RE = re.compile(
    r"(^|[\\/])(deploy|deployment|deployments|scripts?|migrations?|infra|ops|ci|\.github|"
    r"docker|k8s|helm|terraform)([\\/]|$)|deploy[^\\/]*\.(js|ts|py|sh|sol)$|\.env", re.I)


def classify_path(path):
    """Path → one of: 'vendor' | 'test' | 'deploy' | 'prod'. None/empty → 'prod' (production default)."""
    if not path:
        return "prod"
    p = str(path)
    if _VENDOR_RE.search(p):
        return "vendor"
    # test BEATS deploy when both match (cold-review FP: `test/scripts/`, `deploy.test.js` —
    # these are fixtures, an anvil key is muted there). A pure deploy with no test ancestor → 'deploy' (anvil = finding).
    if _TEST_RE.search(p):
        return "test"
    if _DEPLOY_RE.search(p):
        return "deploy"
    return "prod"


# ── Redaction (no-exfil, idea J) ─────────────────────────────────────────────────────
def redact(value, keep=4):
    """Masks a value — NEVER returns it in full (no-exfil). `keep` scales with length:
    short secrets/PII (SSN 9-11 chars) are NOT half-revealed (cold-review under-mask fix)."""
    if value is None:
        return ""
    v = str(value)
    n = len(v)
    k = 4 if n >= 20 else (2 if n >= 10 else 1)
    if n <= k * 2:
        return v[:1] + "…" + v[-1:] if n > 2 else "…"
    return f"{v[:k]}…{v[-k:]} ({n} chars)"


# ── Placeholder / allowlist (mute pseudo-secrets) ───────────────────────────────────
_PLACEHOLDER_TOKENS = (
    "your_", "yourkey", "example", "changeme", "placeholder", "dummy", "sample",
    "xxxxx", "<", "insert", "todo", "fixme", "replace", "notreal", "fake",
)


def is_placeholder(value):
    if value is None:
        return True
    v = str(value).strip().strip("'\"")
    low = v.lower()
    hexbody = low[2:] if low.startswith("0x") else low
    # all-same-char (0x000../0xfff..) = a true placeholder
    if hexbody and len(set(hexbody)) <= 1:
        return True
    if hexbody and all(c in "0f" for c in hexbody) and len(hexbody) >= 8:
        return True
    # low-entropy body (a repeating pattern) = placeholder. NOT prefix-based: `0x0000f3a2…` with a real
    # (high-entropy) body is no longer muted — cold-review FN (a valid key with 2 zero bytes was being lost).
    if hexbody and len(hexbody) >= 16 and shannon_entropy(hexbody) < 2.0:
        return True
    for t in _PLACEHOLDER_TOKENS:
        if t in low:
            return True
    return False


# ── Shannon entropy ──────────────────────────────────────────────────────────────────
def shannon_entropy(s):
    if not s:
        return 0.0
    counts = {}
    for c in s:
        counts[c] = counts.get(c, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


# ── Luhn (CC validation, cuts PII FPs) ───────────────────────────────────────────────
def luhn_valid(number):
    digits = [int(d) for d in str(number) if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ── anvil / hardhat default private keys (PUBLIC — flag only outside test) ───────────
ANVIL_KEYS = {
    "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
    "dbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
    "2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
}

# ── Secret regexes ───────────────────────────────────────────────────────────────────
# proximity-context: tokens near which a bare hex/base58 = a private key, not a hash.
_KEY_CONTEXT = re.compile(
    r"(signer|private[_-]?key|privatekey|\bpk\b|\bsk\b|mnemonic|seed[_-]?phrase|"
    r"secret[_-]?key|deployer[_-]?key|owner[_-]?key|wallet[_-]?key|keypair)", re.I)

_EVM_HEX64 = re.compile(r"(?<![0-9a-fA-F])(0x)?([a-fA-F0-9]{64})(?![0-9a-fA-F])")
_BASE58_KEY = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{43,88}(?![1-9A-HJ-NP-Za-km-z])")
_SOLANA_JSON_KEY = re.compile(r"\[\s*\d{1,3}\s*(?:,\s*\d{1,3}\s*){31,63}\]")

# secp256k1 curve order — a real EVM private key is in [1, n). Used by the CONTEXT-FREE (nameless) candidate
# path: a bare 64-hex with NO key-name nearby is emitted as an `evm_key_candidate` only if in valid range; the
# static scanner then CONFIRMS it by deriving the address and checking it appears in the code / is funded
# on-chain (derive-correlate) — so a real key with NO telltale name is still caught, at near-zero FP (a random
# hash's derived address colliding with a referenced address is ~2^-160).
_SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _evm_key_in_range(hexbody):
    try:
        k = int(hexbody, 16)
    except ValueError:
        return False
    return 1 <= k < _SECP256K1_N


_SIMPLE_SECRETS = {
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "aws_secret_key": re.compile(r"(?i)aws_secret[_a-z]*\s*[=:]\s*['\"]?([a-zA-Z0-9/+=]{40})"),
    "slack_token": re.compile(r"xox[baprs]-[0-9a-zA-Z\-]{10,48}"),
    "google_api": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "stripe_live": re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
    "discord_token": re.compile(r"[MN][A-Za-z0-9_-]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}"),
    "pem_private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "generic_secret": re.compile(
        r"(?i)(secret|password|passwd|token|api[_-]?key|access[_-]?key|auth[_-]?token)"
        r"\s*[=:]\s*['\"]([^'\"\s]{16,})['\"]"),
    "supabase_url": re.compile(r"https://[a-z0-9]{20}\.supabase\.co"),
    "supabase_sb_secret": re.compile(r"sb_secret_[A-Za-z0-9_-]{20,}"),

    # Modern AI / package-registry / SaaS API keys (recon-skills 48-catalog gap, 2026-08-14). Only
    # HIGH-SIGNAL uniquely-prefixed patterns (anti-FP > recall — our core values precision): noisy
    # bare patterns (Mailgun `key-`, ngrok, Twilio bare SK/AC — would match random hex) are NOT taken.
    "anthropic_api": re.compile(r"sk-ant-(?:api03|admin01)-[A-Za-z0-9_\-]{93,}"),
    "openai_project": re.compile(r"sk-proj-[A-Za-z0-9_\-]{40,}T3BlbkFJ[A-Za-z0-9_\-]{20,}"),
    "openai_legacy": re.compile(r"sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}"),
    "openai_session": re.compile(r"sess-[A-Za-z0-9]{40}"),
    "huggingface": re.compile(r"hf_[A-Za-z0-9]{34,}"),
    "npm_token": re.compile(r"npm_[A-Za-z0-9]{36}"),
    "pypi_token": re.compile(r"pypi-AgENdGV[A-Za-z0-9_\-]{16,}"),
    "docker_pat": re.compile(r"dckr_pat_[A-Za-z0-9_\-]{27,}"),
    "atlassian_token": re.compile(r"ATATT3xFfGF0[A-Za-z0-9_\-]{180,}"),
    "digitalocean_pat": re.compile(r"dop_v1_[a-f0-9]{64}"),
    "linear_api": re.compile(r"lin_api_[A-Za-z0-9]{40}"),
    "sendgrid": re.compile(r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}"),
    "cloudflare_api": re.compile(r"(?i)cf[_\-]?api[_\-]?key['\"\s:=]+[a-f0-9]{37}"),
    "datadog_api": re.compile(r"(?i)dd[_\-]?api[_\-]?key['\"\s:=]+[a-f0-9]{32}"),
    "newrelic_key": re.compile(r"(?:NRAK|NRAA|NRBR)-[A-F0-9]{27}"),
    "telegram_bot": re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{32,34}"),
}

# JWT (the payload is decoded separately for deep-inspect / supabase role).
# 3rd section uses `*` (not `{6,}`): alg:none tokens come with an EMPTY signature (`header.payload.`).
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*")

# Encrypted-blob markers (idea D) — not decoded, but flagged as "an encrypted secret shipped to the client".
_ENCRYPTED_MARKERS = {
    "openssl_salted": re.compile(r"U2FsdGVkX1|Salted__"),      # OpenSSL enc
    "pgp_message": re.compile(r"-----BEGIN PGP MESSAGE-----"),
    "ansible_vault": re.compile(r"\$ANSIBLE_VAULT;"),
    "fernet_token": re.compile(r"\bgAAAAA[A-Za-z0-9_\-]{20,}"),
    "age_encryption": re.compile(r"-----BEGIN AGE ENCRYPTED FILE-----|age1[a-z0-9]{58}"),
}

# BaaS misconfig (idea F): apiKey + projectId together = a Firebase config in the client.
_FIREBASE_APIKEY = re.compile(r"AIza[0-9A-Za-z\-_]{35}")
_FIREBASE_MARKERS = re.compile(r"(?i)(firebaseConfig|projectId|authDomain|databaseURL|appId)")

# ── PII ───────────────────────────────────────────────────────────────────────────────
# phone/credit_card do NOT catch a bare digit run (code/CHANGELOGs are full of them — live run: 28502 phone +
# 3513 CC FPs on versions/hashes). phone = only E.164 (`+` + code + separators); credit_card = brand
# patterns (Visa/MC/Amex/Discover) + Luhn validation (in scan_blob) — a random 16-digit hash almost
# never matches a brand AND passes Luhn.
_PII = {
    # the email domain is split into explicit labels (no overlap `[.\-]+` vs `\.`) — removes polynomial backtracking (cold-review ReDoS)
    "email": re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,}\b"),
    "phone": re.compile(r"(?<!\w)\+\d{1,3}[\s.\-]?\(?\d{2,4}\)?[\s.\-]?\d{3}[\s.\-]?\d{2,4}(?!\d)"),
    "credit_card": re.compile(
        r"(?<!\d)(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|2[2-7]\d{14}|3[47]\d{13}|6(?:011|5\d{2})\d{12})(?!\d)"),
    "us_ssn": re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
}
# email domains that are almost always a placeholder/example → not PII.
_PII_EMAIL_NOISE = ("example.com", "example.org", "test.com", "email.com", "domain.com",
                    "sentry.io", "localhost", "@2x", "@3x")
# Canonical example/placeholder PII → not a finding even in prod (cold-review: PII without a placeholder guard).
_PII_EXAMPLES = frozenset({"000-00-0000", "111-11-1111", "123-45-6789", "999-99-9999", "078-05-1120"})

# BIP-39 mnemonic / seed phrase — CANONICAL wordlist+checksum. Round-5 redesign after 8 confirmed defects in
# the round-4 version (early-return swallowed adjacent/multiple seeds; the 60-run-cap skipped a 6-seed
# seeds.txt — the single highest-value leak; checksum-OR-context flagged benign wordlist listings, alphabetical
# fragments, repeated-filler placeholders, and public spec vectors even in test dirs). New rule per
# NON-OVERLAPPING window of 12/15/18/21/24 consecutive wordlist tokens:
#   • forward scan advancing past each hit → EVERY seed in a multi-seed file surfaces (no swallow);
#   • checksum-valid is REQUIRED (drops non-checksum prose/docs — context is no longer used, it was FP-prone);
#   • ascending word-INDICES are dropped (an alphabetical wordlist fragment, never a random seed);
#   • low word-diversity is dropped (repeated-filler placeholder like all-abandon);
#   • well-known public/test vectors are suppressed in test dirs, surfaced as reuse in prod.
# Validated: the checksum path found 54/54 real seeds with 0 prose-FP on a 117M crypto codebase.
_WORD_TOKEN_RE = re.compile(r"[A-Za-z]+")
# smallest-first (round-6 fix): a real 12-word seed matches at size 12 (correct alignment) BEFORE a coincidental
# 15/18/21-word checksum-valid window can over-span and swallow the NEXT seed; a real 24-word seed still matches
# at 24 because its first 12 words carry no valid 12-checksum. NO run-length cap (round-6 FN): the old 512 cap
# DROPPED the whole run — missing a bulk seed-dump AND letting an attacker hide one seed among >512 filler words;
# the sorted-index + diversity guards already make dictionary runs skip cheaply, and _MAX_SCAN_BYTES bounds work.
_MNEMONIC_LENS = (12, 15, 18, 21, 24)
_MNEMONIC_MIN_DISTINCT = 0.6            # < this fraction distinct = repeated-filler placeholder, not a seed
_MNEMONIC_MAX_RUN = 4096                # per-run SCAN-length bound (round-7 perf): a 2MB shuffled all-BIP-39
                                        # blob else costs ~35s (attacker-plantable DoS); the guards do NOT
                                        # short-circuit shuffled runs. SLICE (not drop — round-6 FN dropped
                                        # the whole run) — realistic seed dumps are far smaller; first N surface.

# Zero-value phrases suppressed in test dirs (surfaced as reuse in prod): public BIP-39 spec vectors + default
# dev seeds. Low-diversity ones (all-abandon, all-zoo) are ALSO caught by the diversity guard; diverse public
# vectors need this explicit list. Extensible — add spec vectors seen flagged as noise.
_TEST_MNEMONICS = frozenset({
    "test test test test test test test test test test test junk",                     # hardhat default
    "myth like bonus scare over problem client lizard pioneer submit female collect",  # ganache default
    "legal winner thank year wave sausage worth useful legal winner thank yellow",     # BIP-39 EN spec vector
    "letter advice cage absurd amount doctor acoustic avoid letter advice cage above", # BIP-39 EN spec vector
    "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",  # zero vector
})


def _load_bip39_wordlist():
    """Bundled BIP-39 English list (self-contained; copied from eth_account). Returns (set, index-dict).
    Missing/short file → ({}, {}) and the caller degrades to no-op (fail-open, never crashes a scan)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bip39_english.txt")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            words = [w.strip() for w in fh if w.strip()]
        if len(words) != 2048:
            return set(), {}
        return set(words), {w: i for i, w in enumerate(words)}
    except Exception:
        return set(), {}


_BIP39_WORDS, _BIP39_INDEX = _load_bip39_wordlist()


def _bip39_checksum_ok(words):
    """True iff `words` (each in the wordlist) form a checksum-valid BIP-39 mnemonic (SHA-256 of entropy)."""
    if not _BIP39_INDEX:
        return False
    try:
        idxs = [_BIP39_INDEX[w] for w in words]
    except KeyError:
        return False
    bits = "".join(format(x, "011b") for x in idxs)
    ent_len = len(bits) * 32 // 33
    if ent_len == 0 or ent_len % 8 != 0:
        return False
    cs_len = len(bits) - ent_len
    ent_bytes = int(bits[:ent_len], 2).to_bytes(ent_len // 8, "big")
    check_bits = "".join(format(b, "08b") for b in hashlib.sha256(ent_bytes).digest())[:cs_len]
    return check_bits == bits[ent_len:]


def _mnemonic_diverse(words):
    """Real seeds are ~all-distinct; a repeated-filler placeholder (all-abandon, word word word…) is not."""
    return len(set(words)) >= max(3, int(len(words) * _MNEMONIC_MIN_DISTINCT))


def _scan_mnemonic_run(run, variant, path_kind, out):
    """Forward, NON-OVERLAPPING scan over one maximal run of consecutive wordlist tokens: emits EVERY seed
    (multi-seed files surface all), advancing past each hit. A window flags only if checksum-valid, diverse,
    and NOT an ascending wordlist fragment; public/test vectors are suppressed in test dirs."""
    length = len(run)
    if length > _MNEMONIC_MAX_RUN:      # round-7 perf: SLICE, do NOT drop (round-6 FN dropped the whole run).
        run = run[:_MNEMONIC_MAX_RUN]   # bounds a pathological shuffled all-BIP-39 blob; realistic dumps << cap.
        length = _MNEMONIC_MAX_RUN
    pos = 0
    while pos < length:
        step = 1
        for size in _MNEMONIC_LENS:
            if pos + size > length:
                continue
            window = run[pos:pos + size]
            words = [w for (w, a, b) in window]
            start, end = window[0][1], window[-1][2]
            phrase = variant[start:end]
            if " ".join(words) in _TEST_MNEMONICS:           # public/test spec vector
                if path_kind != "test":
                    out.append((phrase, "test_mnemonic_in_prod", "high",
                                "well-known test/public mnemonic outside test dir"))
                step = size
                break
            idxs = [_BIP39_INDEX[w] for w in words]           # all in wordlist by construction of the run
            if idxs == sorted(idxs):                          # alphabetical wordlist fragment, not a random seed
                continue
            if not _mnemonic_diverse(words):                  # repeated-filler placeholder
                continue
            if not _bip39_checksum_ok(words):                 # REQUIRED — no context fallback (round-5)
                continue
            out.append((phrase, "mnemonic_phrase", "critical", "BIP-39 %d-word checksum-valid" % size))
            step = size
            break
        pos += step


def _mnemonic_findings(variant, path_kind):
    """Find BIP-39 mnemonics in one text variant → list[(phrase, kind, severity, why)]. Fail-open on no list."""
    if not _BIP39_WORDS:
        return []
    toks = [(m.group(0).lower(), m.start(), m.end()) for m in _WORD_TOKEN_RE.finditer(variant)]
    if len(toks) < 12:
        return []
    out, i, n = [], 0, len(toks)
    while i < n:
        if toks[i][0] not in _BIP39_WORDS:
            i += 1
            continue
        j = i
        while j < n and toks[j][0] in _BIP39_WORDS:
            j += 1
        _scan_mnemonic_run(toks[i:j], variant, path_kind, out)   # run-cap now enforced inside _scan
        i = j
    return out

# Anti-DoS caps (cold-review ReDoS): input truncation + skipping giant decode blobs.
_MAX_SCAN_BYTES = 2_000_000
_MAX_DECODE_BLOB = 20_000
_CORPUS_MAX = 4_000_000        # ceiling on the runtime derive-correlate corpus (bounded, no live I/O)

# ── Code-symbol / schema-type guard (anti-FP for field-name / type-declaration noise, Juice Shop live-drive) ──
# A field like `cardnumber:String` (type annotation) or `apiToken:"HttpXsrfTokenExtractor"` (Angular/DI symbol
# NAME used as a string value) is a TYPE/schema declaration or a code reference — NOT leaked data or a literal
# secret. This guard tells a code symbol from real data/secret. Recall-safe BY CONSTRUCTION: anything carrying
# a digit or a secret charset (+/=, hex/base58 body) is not a pure identifier → returns False → real keys /
# tokens / card-numbers / IBANs / all-caps SWIFT codes never match here and stay flagged.
_SCHEMA_TYPE_WORDS = frozenset({
    "string", "number", "boolean", "bool", "int", "integer", "float", "double", "decimal", "numeric",
    "bigint", "serial", "date", "datetime", "time", "timestamp", "text", "char", "varchar", "nvarchar",
    "nchar", "uuid", "guid", "object", "array", "buffer", "blob", "json", "jsonb", "any", "void", "null",
    "undefined", "true", "false", "mixed", "map", "set", "enum", "binary", "real", "money", "clob", "xml",
    "bytes", "list", "dict", "tuple", "str", "long", "short", "byte", "geometry", "point",
})
_CODE_REF_RE = re.compile(r"(?:^|[^\w$])(?:process\.env|import\.meta|globalThis|window|require|module|exports)\b")
_DOTTED_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+$")   # DataTypes.STRING, req.body.x, a.b.C
_ALPHA_IDENT_RE = re.compile(r"^[A-Za-z]+$")
_CAMEL_BOUNDARY_RE = re.compile(r"[a-z][A-Z]")                                # camelCase/PascalCase word boundary


def _looks_like_code_symbol(value):
    """True iff `value` is a code identifier / type / reference, not literal data or a secret. See header:
    recall-safe — digits or secret charset ⇒ not a pure identifier ⇒ False (real secrets/data stay flagged)."""
    if not value:
        return False
    v = str(value).strip().strip("'\"").strip()
    if not v:
        return False
    if v.lower() in _SCHEMA_TYPE_WORDS:                                # bare schema/type keyword (String, Int…)
        return True
    if v.startswith("${") or v.startswith("{{"):                       # template / interpolation reference
        return True
    if _CODE_REF_RE.search(v):                                         # process.env.X / window.* / require reference
        return True
    if _DOTTED_IDENT_RE.match(v):                                      # dotted identifier path (all-ident segments)
        return True
    if _ALPHA_IDENT_RE.match(v) and _CAMEL_BOUNDARY_RE.search(v):      # camelCase/PascalCase symbol (InjectionToken)
        return True
    return False


# ── Financial / confidential (web2 "valuable data", idea) ───────────────────────────
# We require a DATA form (`key [:=] value`), NOT a bare word: `balance` in .sol code (`balanceOf`/
# `_balance`) = logic, not a data leak (live run: a bare list gave 216 FPs). Bare generic words
# (balance/salary/invoice/credit_limit/transaction_history) were removed — high-signal PII/financial
# identifiers were kept, and only when a real value follows them (a JSON key / key=value in data/a response).
# group(2) = value → post-filtered by _looks_like_code_symbol (type-decl `cardnumber:String` = not a leak).
_FINANCIAL_MARKERS = re.compile(
    r"(?i)[\"']?\b(account[_-]?number|routing[_-]?number|iban|swift[_-]?code|card[_-]?number|"
    r"cvv|kyc|passport[_-]?number|tax[_-]?id|ssn|national[_-]?id|bank[_-]?account)\b[\"']?\s*[:=]\s*"
    r"[\"']?([A-Za-z0-9][\w\-. ]{1,})")
_BACKUP_EXT = re.compile(r"\.(sql|bak|dump|backup|old|save|swp|~|tar\.gz|zip|db|sqlite)$", re.I)


# ── Decode layer (idea: a key on a page may be encoded) ──────────────────────────────
def _try_b64(s):
    try:
        raw = base64.b64decode(s + "=" * (-len(s) % 4), validate=False)
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _try_b32(s):
    try:
        raw = base64.b32decode(s + "=" * (-len(s) % 8), casefold=True)
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _try_hex(s):
    try:
        return binascii.unhexlify(s[2:] if s.lower().startswith("0x") else s).decode("utf-8", errors="ignore")
    except Exception:
        return ""


_B64_BLOB = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_B32_BLOB = re.compile(r"[A-Z2-7]{32,}={0,6}")
_HEX_BLOB = re.compile(r"(?:0x)?[a-fA-F0-9]{40,}")


def try_decode(text, depth=2):
    """Returns a list of decoded variants (base64/base32/hex/url/gzip/JWT-payload),
    recursively up to `depth`. For a re-scan: a secret is often encoded."""
    if depth <= 0 or not text or len(text) > _MAX_SCAN_BYTES:
        return []
    out = []
    # URL-decode the whole text if there is a %XX
    if "%" in text:
        try:
            dec = urllib.parse.unquote(text)
            if dec != text:
                out.append(dec)
        except Exception:
            pass
    # blob candidates (a giant blob is skipped — cold-review DoS: one greedy match over the whole input)
    for m in _B64_BLOB.findall(text)[:40]:
        if len(m) > _MAX_DECODE_BLOB:
            continue
        d = _try_b64(m)
        if d and d.isprintable() and len(d) >= 8:
            out.append(d)
    for m in _B32_BLOB.findall(text)[:20]:
        if len(m) > _MAX_DECODE_BLOB:
            continue
        d = _try_b32(m)
        if d and d.isprintable() and len(d) >= 8:
            out.append(d)
    for m in _HEX_BLOB.findall(text)[:40]:
        if len(m) > _MAX_DECODE_BLOB:
            continue
        d = _try_hex(m)
        if d and d.isprintable() and len(d) >= 8:
            out.append(d)
    # gzip (if the text is raw bytes, skipped here; we work with strings)
    # JWT payload
    for j in _JWT.findall(text)[:10]:
        payload = decode_jwt(j)
        if payload:
            out.append(json.dumps(payload))
    # recursion on the first decode level
    nested = []
    for o in out[:10]:
        nested.extend(try_decode(o, depth - 1))
    return out + nested


def decode_jwt(token):
    """Decodes a JWT header+payload (without signature verification) → dict|None."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        def _seg(p):
            return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)).decode("utf-8", "ignore"))
        return {"header": _seg(parts[0]), "payload": _seg(parts[1])}
    except Exception:
        return None


def inspect_jwt(token):
    """JWT deep-inspect (idea G): alg:none / service_role / eternal expiry / sensitive claims."""
    decoded = decode_jwt(token)
    if not decoded:
        return None
    hdr, pl = decoded.get("header", {}), decoded.get("payload", {})
    issues = []
    sev = "low"
    if str(hdr.get("alg", "")).lower() in ("none", ""):
        issues.append("alg:none (forgeable)")
        sev = "high"
    role = str(pl.get("role", "")).lower()
    if role in ("service_role", "admin", "root"):
        issues.append(f"privileged role claim: {role}")
        sev = "critical"
    if "exp" not in pl:
        issues.append("no expiry")
    for k in ("email", "ssn", "password", "user_id", "phone"):
        if k in pl:
            issues.append(f"sensitive claim: {k}")
    return {"issues": issues, "severity": sev, "role": role} if issues else None


# ── Central scan ─────────────────────────────────────────────────────────────────────
def _finding(cls, kind, value, severity, evidence, decoded_via=None):
    return {
        "cls": cls, "kind": kind, "severity": severity,
        "redacted": redact(value), "evidence": evidence[:120],
        "decoded_via": decoded_via,
        # hash of the RAW value for dedup (not redacted — different PII are redacted identically); no-exfil: this is a hash
        "_dedup": hashlib.sha1(str(value).encode("utf-8", "ignore")).hexdigest()[:12],
        # the RAW value — ONLY for local verification (derive / cluster-dedup) in scan_target and
        # capture_exposure; BOTH consumers MUST strip it before output (no-exfil). It does not go to the producer/log.
        "_match": str(value),
    }


def scan_blob(text, path_kind=None, source="file", enable_pii=True, enable_decode=True,
              emit_key_candidates=False):
    """Scan of one text blob (file / DOM / response / storage value).

    path_kind: 'vendor'|'test'|'deploy'|'prod'|'runtime'|None. 'vendor' → skipped entirely.
    Returns list[finding]. PII clustering and key-verify are done by the caller.
    """
    if not text or not isinstance(text, str):
        return []
    if path_kind == "vendor":
        return []
    if len(text) > _MAX_SCAN_BYTES:
        text = text[:_MAX_SCAN_BYTES]   # input truncation (cold-review DoS: unbounded length)

    findings = []
    variants = [(text, None)]
    if enable_decode:
        for d in try_decode(text):
            variants.append((d, "decoded"))

    seen = set()  # dedup by (kind, redacted)

    def add(f):
        key = (f["kind"], f.pop("_dedup", f["redacted"]))
        if key not in seen:
            seen.add(key)
            findings.append(f)

    for variant, via in variants:
        low = variant.lower()

        # crypto EVM privkey — near context OR an anvil key
        for m in _EVM_HEX64.finditer(variant):
            hexbody = m.group(2).lower()
            full = m.group(0)
            if is_placeholder(full):
                continue
            is_anvil = hexbody in ANVIL_KEYS
            near = _KEY_CONTEXT.search(variant[max(0, m.start() - 60):m.end() + 60])
            if is_anvil:
                # a public test key: a finding ONLY outside test (deploy/prod/runtime)
                if path_kind == "test":
                    continue
                add(_finding("crypto-key", "anvil_test_key_in_prod", full, "high",
                             "anvil/hardhat default privkey outside test dir", via))
            elif near:
                add(_finding("crypto-key", "evm_privkey", full, "critical",
                             f"64-hex near '{near.group(0)}'", via))
            elif emit_key_candidates and _evm_key_in_range(hexbody):
                # CONTEXT-FREE (nameless) candidate: a bare in-range 64-hex with NO key-name nearby. Most are
                # hashes/bytes32 — emitted as a low-signal candidate that the scanner CONFIRMS via
                # derive-correlate (derived address referenced in code / funded on-chain) and DROPS otherwise
                # (no flood). This catches a real leaked key that carries no telltale variable name.
                add(_finding("crypto-key", "evm_key_candidate", full, "info",
                             "context-free 64-hex in secp256k1 range — pending derive-correlation", via))

        # Solana base58 privkey — near context
        for m in _BASE58_KEY.finditer(variant):
            val = m.group(0)
            # near-hex (incl. the 'x' of the 0x prefix of an EVM key) → this is EVM/hash, not solana base58.
            # A real base58 key carries DOZENS of non-hex chars; near-hex has 0..1. Threshold >=2.
            if sum(1 for c in val if c not in "0123456789abcdefABCDEF") < 2:
                continue
            if is_placeholder(val):
                continue
            near = _KEY_CONTEXT.search(variant[max(0, m.start() - 60):m.end() + 60])
            # ONLY a 64-byte secret key (~80-88 base58). A 32-byte PUBLIC key (~43-44) is public
            # by design → NOT a secret (cold-review FP: a pubkey near signer was flagged as a CRITICAL privkey).
            if near and len(val) >= 80:
                add(_finding("crypto-key", "solana_privkey_b58", val, "critical",
                             f"base58 near '{near.group(0)}'", via))
        for m in _SOLANA_JSON_KEY.finditer(variant):
            add(_finding("crypto-key", "solana_keypair_json", m.group(0), "critical",
                         "solana byte-array keypair", via))

        # BIP-39 mnemonic / seed phrase — wordlist+checksum canonical mechanism (see _mnemonic_findings).
        for phrase, kind, sev, why in _mnemonic_findings(variant, path_kind):
            add(_finding("crypto-key", kind, phrase, sev, why, via))

        # simple secret patterns
        _has_fb = _FIREBASE_MARKERS.search(variant)
        for kind, rx in _SIMPLE_SECRETS.items():
            # an AIza key alongside Firebase markers = a Firebase Web API key (public by design) → NOT a HIGH
            # google_api secret, covered by the firebase_config finding below (cold-review double-flag).
            if kind == "google_api" and _has_fb:
                continue
            for m in rx.finditer(variant):
                val = m.group(0)
                if is_placeholder(val):
                    continue
                # generic_secret token/key-family keys flood on Angular/DI symbol NAMES used as string VALUES
                # (InjectionToken / HttpXsrfTokenExtractor / platformBrowserDynamic — "Token…" strings).
                # Skip when the captured value (group 2) is a code symbol, not a literal secret. password/secret/
                # passwd keys carry strong secret-intent → NOT filtered (a hardcoded weak password may be a
                # pure-alpha camelCase word); anything with digits/secret-charset already survives the guard.
                if kind == "generic_secret":
                    kw = (m.group(1) or "").lower()
                    if ("token" in kw or "key" in kw) and _looks_like_code_symbol(m.group(2)):
                        continue
                sev = "high"
                if kind in ("pem_private_key", "stripe_live", "aws_secret_key",
                            "anthropic_api", "openai_project", "openai_legacy", "cloudflare_api"):
                    sev = "critical"     # direct $$$ access (paid AI / infra) = critical
                add(_finding("secret", kind, val, sev, kind, via))

        # JWT deep-inspect
        for j in _JWT.finditer(variant):
            info = inspect_jwt(j.group(0))
            if info:
                add(_finding("secret", "jwt_" + (info["role"] or "issue"), j.group(0),
                             info["severity"], "; ".join(info["issues"]), via))

        # encrypted blobs
        for kind, rx in _ENCRYPTED_MARKERS.items():
            if rx.search(variant):
                m = rx.search(variant)
                add(_finding("secret", "encrypted_" + kind, m.group(0), "medium",
                             "encrypted secret shipped to client", via))

        # Firebase config (apiKey + markers together)
        if _FIREBASE_APIKEY.search(variant) and _FIREBASE_MARKERS.search(variant):
            m = _FIREBASE_APIKEY.search(variant)
            add(_finding("secret", "firebase_config", m.group(0), "medium",
                         "Firebase config in client (verify DB rules world-readable)", via))

        # Financial / confidential markers (in test paths — fixtures/examples, not a data leak). Skip a match
        # whose VALUE is a type/schema decl or code ref (`cardnumber:String`, `card_number=req.body.x`) — a
        # field-name/type-annotation, not leaked DATA (live-drive FP on a public demo app). finditer (not search): skip
        # the type-decl FP yet still surface a REAL financial marker later in the same blob; report first real.
        if path_kind != "test":
            for m in _FINANCIAL_MARKERS.finditer(variant):
                if _looks_like_code_symbol(m.group(2)):
                    continue
                add(_finding("financial", "confidential_marker", m.group(0), "medium",
                             f"financial/confidential field: {m.group(0)}", via))
                break

        # PII (clustering — on the caller). In test paths PII is muted (fixtures/examples, not real data).
        if enable_pii and path_kind != "test":
            for kind, rx in _PII.items():
                for m in rx.finditer(variant):
                    val = m.group(0)
                    if val in _PII_EXAMPLES:                       # canonical example values → not a finding
                        continue
                    if kind == "email" and any(n in val.lower() for n in _PII_EMAIL_NOISE):
                        continue
                    if kind == "credit_card" and not luhn_valid(val):
                        continue
                    if kind == "phone" and len(re.sub(r"\D", "", val)) < 10:
                        continue
                    add(_finding("pii", kind, val, "low", kind, via))

    return findings


# ── Context-free key confirmation: derive address → correlate against a corpus (shared by static scanner
#    and runtime capture). A nameless in-range 64-hex `evm_key_candidate` is CONFIRMED as a real key iff its
#    DERIVED address appears in the corpus (~2^-160 collision for a random hash) — NO variable name needed. ──
def derive_evm_address(privkey_hex):
    """secp256k1 privkey-hex → checksummed EVM address, or None (lib absent / malformed key). Lazy import:
    the engine never hard-depends on eth-libs; without them the derive-correlate path degrades to no-op."""
    pk = str(privkey_hex).lower().removeprefix("0x")
    if len(pk) != 64:
        return None
    try:
        from eth_account import Account
        return Account.from_key(bytes.fromhex(pk)).address
    except Exception:
        pass
    try:
        from eth_keys import keys
        return keys.PrivateKey(bytes.fromhex(pk)).public_key.to_checksum_address()
    except Exception:
        return None


_ROLE_TOKENS = re.compile(r"(?i)(owner|admin|signer|governance|guardian|operator|treasury|deployer)")
# long hex/base58 runs = a partial key → cut from role_proof before storing (no-exfil)
_SECRET_RUN_RE = re.compile(r"[a-f0-9]{16,}|[1-9A-HJ-NP-Za-km-z]{32,}", re.I)


def _strip_secret_runs(s):
    return _SECRET_RUN_RE.sub("…", s)


def correlate_key_candidates(findings, corpus):
    """derived address occurs in the corpus → CONFIRM a nameless candidate + escalate role-adjacent keys.
    Uses the per-finding `_match` (the raw value from scan_blob), NOT a corpus-wide re.search (that would take
    SOMEONE ELSE'S bytes and derive on them). Mutates + returns `findings`; the caller DROPS the remaining
    `evm_key_candidate` (unconfirmed) and strips `_match` (no-exfil). Shared: static scanner + runtime."""
    low_corpus = (corpus or "").lower()
    for f in findings:
        if f.get("cls") != "crypto-key" or not f.get("_match"):
            continue
        kind = f.get("kind", "")
        addr = derive_evm_address(f["_match"]) if (kind.startswith("evm") or kind.startswith("anvil")) else None
        if not addr:
            continue
        f["derived_address"] = addr
        idx = low_corpus.find(addr.lower())
        if idx >= 0:
            # a nameless candidate whose DERIVED address is referenced anywhere in the corpus is a real key —
            # confirm with NO reliance on a variable name. A role-token nearby is extra proof / severity.
            if kind == "evm_key_candidate":
                f["kind"] = "evm_privkey"
                f["severity"] = "critical"
                f["evidence"] = "nameless key CONFIRMED — derived address referenced in corpus"
            window = low_corpus[max(0, idx - 80):idx + 80]
            if _ROLE_TOKENS.search(window):
                f["severity"] = "critical"
                f["role_proof"] = "role-token near derived address: " + _strip_secret_runs(window)
    return findings


def capture_exposure(sources, path_kind="runtime", enable_pii=True, source="runtime"):
    """Runtime exposure sweep over ALREADY-CAPTURED live artifacts (rendered DOM / JS chunks / response
    bodies / localStorage-sessionStorage values / window globals). SHARED core for both web-runtime
    harnesses — dapphunt `runtime_harness.capture_exposure` and web2 `web2_exposure.capture_exposure`
    delegate here (parallel-profile pattern: ONE implementation, two callers).

    `sources`: dict {label: text} | list[(label, text)] | list[str]. Each blob = raw text of one artifact
    (innerHTML, chunk body, `localStorage[key]`, JSON response body). Non-str (dict/list snapshot of a
    window global / JSON storage) is JSON-serialized before scanning.

    Context-free (nameless) keys: `emit_key_candidates=True` surfaces bare in-range 64-hex with NO key-name,
    then confirms each via derive-correlate against the CAPTURED corpus (a leaked key's derived address may
    appear in any artifact — DOM showing the account, a response echoing it, a config global). Corpus-only,
    NO RPC — capture_exposure never does live I/O (mirrors the scanner's offline confirmation; the scanner
    additionally RPC-verifies, this does not). Unconfirmed candidates are dropped (no flood).

    OPSEC/white-hat: NO live I/O here — only scans passed snapshots. The caller does the live browser
    capture ONLY after a fail-closed opsec_preflight == ok. no-exfil: the raw value (`_match`) is STRIPPED
    before return. Returns list[finding] (+ `source`=label). Fail-open: bad input -> []."""
    out, corpus_parts, corpus_len = [], [], 0
    try:
        if isinstance(sources, dict):
            items = list(sources.items())
        elif isinstance(sources, list):
            items = [(x[0], x[1]) if isinstance(x, (list, tuple)) and len(x) == 2
                     else ("blob", x) for x in sources]
        else:
            return []
        for label, text in items:
            if not isinstance(text, str):
                try:
                    text = json.dumps(text, ensure_ascii=False)
                except Exception:
                    continue
            # Runtime KV stores (localStorage/sessionStorage/window globals) carry their context in the KEY
            # NAME, not the value — a bare `0x…` under localStorage['privateKey'] has NO near-context in the
            # value alone, so name-gated detectors (evm_privkey etc.) would miss it. Prepend the label so the
            # key name travels with the value. (live-drive found this on ShapeShift: planted key under a
            # signerKey-named storage slot was missed until the label was scanned.)
            scan_text = str(label) + "\n" + text
            if corpus_len < _CORPUS_MAX:                        # bounded corpus for context-free confirmation
                corpus_parts.append(scan_text)
                corpus_len += len(scan_text)
            for f in scan_blob(scan_text, path_kind=path_kind, source=source,
                               enable_pii=enable_pii, emit_key_candidates=True):
                f["source"] = str(label)                        # keep `_match` for correlate; stripped below
                out.append(f)
        # confirm nameless candidates against the captured corpus (best-effort; corpus-only, no live I/O)
        correlate_key_candidates(out, "\n".join(corpus_parts))
    except Exception:
        pass
    # finalize (always): drop unconfirmed nameless candidates (no flood) + strip raw value (no-exfil)
    out = [f for f in out if f.get("kind") != "evm_key_candidate"]
    for f in out:
        f.pop("_match", None)
    return out
