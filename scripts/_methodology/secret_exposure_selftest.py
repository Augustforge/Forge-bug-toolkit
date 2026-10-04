#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay test for secret_exposure_scanner (P0-2 static).

Builds a fixture tree, runs scan_target, checks:
  proof-of-firing — Swan-shape key / anvil-in-deploy / decode layer / supabase-JWT / source-map /
                    PII cluster / financial are CAUGHT (fails if a detect class is removed);
  anti-FP        — vendored / test-dir anvil / placeholder / a single PII stay SILENT.
No solc/network needed. Run: py -3 -X utf8 secret_exposure_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import base64
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import secret_exposure_scanner as ses  # noqa: E402

_HE = "Kx7Qw2Zr9Yt4Vb1Nm6Ps3Jd8Hf5Lc0Gg"      # high-entropy body for modern-key test values (not a placeholder)
SIGNER_KEY = "0x" + "a1b2c3d4" * 8              # 64-hex, not anvil, not a placeholder
ANVIL = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
GH_TOKEN = "ghp_" + "0123456789" * 4            # ghp_ + 40

# round-5: real BIP-39 seeds — checksum-valid, diverse, NON-sequential indices, NOT public spec vectors.
SEED1 = "absurd avoid scissors anxiety gather lottery category door army half long camera"
SEED2 = "baby mountain shallow clay gesture metal good drop bright trophy march domain"
SEED3 = "cancel baby simple engage give neglect pigeon earth club harvest mesh ghost"
SEED4 = "couple muscle snack heavy gloom orchard top electric destroy try more library"
SEED5 = "donor bamboo speed melody good picnic cement enact era heavy need peace"
SEED6 = "eyebrow myth steak primary grace promote grace enter fox turtle oak scan"
SEED_INVALID = "camera absurd avoid scissors anxiety gather lottery category door army half long"  # diverse, non-sorted, checksum-INVALID
# context-free (nameless) EVM key + its derived address (for the derive-correlate path):
CTXFREE_KEY = "0x4a7f4a7f4a7f4a7fb91cb91cb91cb91cd3e8d3e8d3e8d3e85f2a5f2a5f2a5f2a"
CTXFREE_ADDR = "0xAe3618dF729b975D92d1752222B20Ec785102D96"


def _jwt_service_role():
    h = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    p = base64.urlsafe_b64encode(b'{"role":"service_role","iss":"supabase"}').decode().rstrip("=")
    return f"{h}.{p}.c2lnbmF0dXJlZGF0YQ"


def build_fixture(root):
    def w(rel, content):
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)

    # proof-of-firing
    w("src/Treasury.sol", f"contract T {{ bytes32 private signerKey = {SIGNER_KEY}; }}")   # evm_privkey crit
    w("script/deploy.js", f'const pk = "{ANVIL}"; // deployer')                              # anvil in deploy
    w("public/index.html",
      "<script>var c='" + base64.b64encode(f"signerPrivateKey={SIGNER_KEY}".encode()).decode() + "'</script>")  # decode
    w("dist/bundle.js", f'const supa="{_jwt_service_role()}";')                              # supabase jwt crit
    w("data/users.json", "\n".join(f'"email":"user{i}@corp.io"' for i in range(10)))         # PII cluster
    w("data/records.txt", "account_number: 111 routing_number: 222 balance: 999 kyc: yes")   # financial
    # source-map with a secret in sourcesContent
    w("app.js.map",
      '{"version":3,"sources":["app.ts"],"sourcesContent":["const key=\'' + GH_TOKEN + '\'"]}')

    # cold-review scanner locks
    w("certs/prod.pem",                                                                       # FN12: .pem is read
      "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEAxyz0123456789abcdef\n-----END RSA PRIVATE KEY-----\n")
    w("deploy/multi.js",                                                                      # FN13: 2 hex, _match per-finding
      f'bytes32 SALT = 0x{"a1b2c3d4" * 8};\nconst deployerKey = "{ANVIL}";\n')
    w("build/bad.js.map", "[]")                                                               # FN14: non-dict .map does not crash

    # anti-FP (must stay SILENT)
    w("test/foo.test.js", f'const pk = "{ANVIL}"; // fixture')                               # test-dir anvil → silent
    w("node_modules/pkg/leak.env", f"PRIVATE_KEY={SIGNER_KEY}")                              # vendored → skip
    w("config/app.js", "const k = '0x0000000000000000000000000000000000000000000000000000000000000000'")  # placeholder
    w("data/one.txt", "email: solo@corp.io")                                                # single PII → drop

    # context-free (nameless) EVM key: bare key, NO key-name nearby → candidate; derived address referenced as
    # owner in ANOTHER file → derive-correlate CONFIRMS it critical. Random hash w/o address ref → dropped.
    w("deploy/nameless.js", 'const relayer = "' + CTXFREE_KEY + '";')                        # bare key (no name)
    w("config/owners.json", '{"owner":"' + CTXFREE_ADDR + '","role":"admin"}')               # derived addr = owner
    w("build/hashes.txt",                                                                    # random hash → drop
      "root = 0x1f9d8c3b6e4a2f70d5c8b1a4e7f0293d6c5b8a1f4e7d0c3b6a9f2e5d8c1b4a7f")


def run():
    root = tempfile.mkdtemp(prefix="expo_selftest_")
    try:
        build_fixture(root)
        findings, warnings = ses.scan_target(root, enable_pii=True, git_history=False)
        kinds = {f["kind"] for f in findings}
        files = [f.get("file", "") for f in findings]

        # ── isolated source-map target: ONLY a .map, NO plain files — so a context-free key restored from
        #    sourcesContent can be confirmed ONLY via the cross-source corpus WITHIN the .map itself. Proves
        #    BOTH wirings at once: emit_key_candidates in _scan_sourcemap AND restored-sources-into-corpus.
        #    (Revert either and the confirm check below fails: no candidate emitted, or empty corpus.) ──
        import json as _json
        sm_root = tempfile.mkdtemp(prefix="expo_sm_")
        try:
            sm_map = _json.dumps({
                "version": 3,
                "sources": ["src/relay.ts", "src/config.ts", "src/tree.ts"],
                "sourcesContent": [
                    "const relayer = '" + CTXFREE_KEY + "';",        # bare key, NO key-name → candidate
                    "export const owner = '" + CTXFREE_ADDR + "';",  # derived addr in ANOTHER restored source
                    "const merkleRoot = '0x1f9d8c3b6e4a2f70d5c8b1a4e7f0293d6c5b8a1f4e7d0c3b6a9f2e5d8c1b4a7f';",
                ],
            })
            with open(os.path.join(sm_root, "bundle.js.map"), "w", encoding="utf-8") as fh:
                fh.write(sm_map)
            sm_findings, _ = ses.scan_target(sm_root, enable_pii=False, git_history=False)
        finally:
            shutil.rmtree(sm_root, ignore_errors=True)

        # ── A6 (Wave 1): attention-gap × exposure — cold zones/haste files steer the scanner ──
        # cold_files (audit_coverage_invert) → tag attention_zone=cold + undup=cold-zone (double un-dup);
        # haste_files (commit_archaeology) → haste=True (top priority). Reverting _tag_attention breaks it.
        a6_findings, _ = ses.scan_target(root, enable_pii=False, git_history=False,
                                         cold_files=["certs/prod.pem"],
                                         haste_files=["script/deploy.js"])
        a6_base, _ = ses.scan_target(root, enable_pii=False, git_history=False)   # no maps → no tags
        def _find(fs, suffix):
            return [f for f in fs if str(f.get("file", "")).replace("\\", "/").endswith(suffix)]

        checks = [
            # proof-of-firing
            ("evm_privkey (Swan-shape)",        "evm_privkey" in kinds),
            ("anvil_test_key_in_prod (deploy)", "anvil_test_key_in_prod" in kinds),
            ("decode-layer (base64 page)",      any(f["kind"] == "evm_privkey" and f.get("decoded_via")
                                                    for f in findings)),
            ("jwt_service_role",                "jwt_service_role" in kinds),
            ("source-map github_token",         any("github_token" == f["kind"] and "::" in f.get("file", "")
                                                    for f in findings)),
            ("pii email_cluster",               "email_cluster" in kinds),
            ("financial confidential_marker",   "confidential_marker" in kinds),
            # anti-FP
            ("anti-FP: no test-dir finding",    not any(fl.startswith("test") and "::" not in fl for fl in files)),
            ("anti-FP: no node_modules finding", not any("node_modules" in fl for fl in files)),
            ("anti-FP: no placeholder finding", not any(f.get("file", "").startswith("config") for f in findings)),
            ("anti-FP: singleton PII dropped",  "email" not in kinds),
            ("anti-FP: no spurious solana on EVM key", "solana_privkey_b58" not in kinds),
            # live-run regression: number-soup (versions/hashes/PR#) must NOT yield phone/CC (was 28502+3513 FP)
            ("anti-FP: number-soup no phone/cc",
             not any(f["kind"] in ("phone", "credit_card") for f in ses.sp.scan_blob(
                 "v1.2.3 released, PR #28502, commit 1234567890123456, build 987654321012", path_kind="prod"))),
            ("real E.164 phone still detected",
             any(f["kind"] == "phone" for f in ses.sp.scan_blob("contact support at +14155551234", path_kind="prod"))),
            ("real Visa card (Luhn) still detected",
             any(f["kind"] == "credit_card" for f in ses.sp.scan_blob('{"pan":"4111111111111111"}', path_kind="prod"))),
            # ── modern SaaS/AI/registry key catalog (recon-skills 48-gap, 2026-08-14) ──
            # high-entropy bodies (a low-entropy `aaa…` is correctly muted by the placeholder guard — a feature, not a bug)
            ("Anthropic sk-ant key → critical",
             any(f["kind"] == "anthropic_api" and f["severity"] == "critical" for f in ses.sp.scan_blob(
                 "ANTHROPIC_API_KEY=sk-ant-api03-" + (_HE * 3)[:95], path_kind="prod"))),
            ("OpenAI project key → critical",
             any(f["kind"] == "openai_project" and f["severity"] == "critical" for f in ses.sp.scan_blob(
                 "sk-proj-" + (_HE * 2)[:45] + "T3BlbkFJ" + (_HE * 2)[:25], path_kind="prod"))),
            ("HuggingFace hf_ token detected",
             any(f["kind"] == "huggingface" for f in ses.sp.scan_blob("hf_" + (_HE * 2)[:36], path_kind="prod"))),
            ("npm token detected",
             any(f["kind"] == "npm_token" for f in ses.sp.scan_blob("npm_" + (_HE * 2)[:36], path_kind="prod"))),
            ("Docker Hub PAT detected",
             any(f["kind"] == "docker_pat" for f in ses.sp.scan_blob("dckr_pat_" + _HE[:30], path_kind="prod"))),
            ("DigitalOcean dop_v1 detected",
             any(f["kind"] == "digitalocean_pat" for f in ses.sp.scan_blob(
                 "dop_v1_" + ("a1b2c3d4e5f6" * 6)[:64], path_kind="prod"))),
            ("SendGrid key detected",
             any(f["kind"] == "sendgrid" for f in ses.sp.scan_blob(
                 "SG." + _HE[:22] + "." + (_HE * 2)[:43], path_kind="prod"))),
            ("Telegram bot token detected",
             any(f["kind"] == "telegram_bot" for f in ses.sp.scan_blob("123456789:AA" + _HE[:33], path_kind="prod"))),
            # anti-FP: a bare ID:hex without the AA prefix is NOT a telegram bot (random `12345678:deadbeef…`)
            ("anti-FP: bare id:hex not telegram bot",
             not any(f["kind"] == "telegram_bot" for f in ses.sp.scan_blob(
                 "build 12345678:0123456789abcdef0123456789abcdef01", path_kind="prod"))),
            ("modern secret surfaces even in TEST dir (real key = leak, not fixture)",
             any(f["kind"] == "anthropic_api" for f in ses.sp.scan_blob(
                 "sk-ant-api03-" + (_HE * 3)[:95], path_kind="test"))),
            # ── cold-review secret_patterns fix-loop locks ──
            ("FN6 BIP-39 mnemonic (real checksum-valid seed) detected",
             any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "const mnemonic = '" + SEED1 + "';", path_kind="prod"))),
            ("FN6 mnemonic-length prose WITHOUT context → silent",
             not any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "the quick brown fox jumps over lazy dog while happy cats play near",  path_kind="prod"))),
            ("B2 word-run near 'random seed' (bare seed dropped) → silent",
             not any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "random seed value apple table chair mouse plant water light stone cloud river ocean forest",
                 path_kind="prod"))),
            ("B2 newline column near 'Seeds:' → silent (run does not span newlines)",
             not any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "Seeds:\n" + "\n".join(["apple", "table", "chair", "mouse", "plant", "water", "light",
                                          "stone", "cloud", "river", "ocean", "forest", "maple", "cedar",
                                          "birch", "aspen", "elder", "hazel", "rowan", "olive", "lemon",
                                          "mango", "peach", "grape"]), path_kind="prod"))),
            # ── cold-review round-4: wordlist+checksum mnemonic redesign (8/8 B-2 defects locked) ──
            ("B2r4 proximity FP: benign prose near 'passphrase' → no mnemonic (wordlist kills it)",
             not any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 '# passphrase prompt shown to the user\n'
                 'msg = "please enter your account number before you submit this online order form"',
                 path_kind="prod"))),
            ("B2r4 Title-Case real seed detected (case-insensitive tokenizer)",
             any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 '// mnemonic backup\n"' + SEED1.title() + '"', path_kind="prod"))),
            ("B2r4 real seed with adjacent wordlist filler detected (forward scan)",
             any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "recovery_phrase = baby " + SEED1, path_kind="prod"))),
            ("B2r4 JSON-array real seed detected (delimiter-agnostic tokenizer)",
             any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 '{"mnemonic":["' + '","'.join(SEED1.split()) + '"]}', path_kind="prod"))),
            # ── cold-review round-5: forward-scan / checksum-required / sorted+diversity guards (8/8 locked) ──
            ("R5 multi-seed: BOTH adjacent seeds detected (no early-return swallow)",
             len([f for f in ses.sp.scan_blob(SEED1 + "\n" + SEED2, path_kind="prod")
                  if f["kind"] == "mnemonic_phrase"]) >= 2),
            ("R5 seeds.txt 6 seeds all detected (no run-cap skip)",
             len([f for f in ses.sp.scan_blob("\n".join([SEED1, SEED2, SEED3, SEED4, SEED5, SEED6]),
                  path_kind="prod") if f["kind"] == "mnemonic_phrase"]) >= 6),
            ("R5 real seed in TEST dir STILL surfaces (secrets-in-test guarantee)",
             any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "const seed = '" + SEED1 + "'", path_kind="test"))),
            ("R5 alphabetical wordlist fragment NOT flagged (sorted-index guard)",
             not any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "mnemonic words: abandon ability able about above absent absorb abstract absurd abuse access account",
                 path_kind="prod"))),
            ("R5 all-abandon zero vector NOT critical (diversity + public-vector)",
             not any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 '"mnemonic":"' + "abandon " * 11 + 'about"', path_kind="prod"))),
            ("R5 public spec vector in TEST dir suppressed (no crypto-key finding)",
             not any(f["cls"] == "crypto-key" for f in ses.sp.scan_blob(
                 "legal winner thank year wave sausage worth useful legal winner thank yellow",
                 path_kind="test"))),
            ("R5 diverse NON-checksum phrase near 'mnemonic' NOT flagged (checksum required)",
             not any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 "mnemonic example: " + SEED_INVALID, path_kind="prod"))),
            # ── cold-review round-6: run-cap removed (bulk dump / evasion) + smallest-first (mis-span) ──
            ("R6 seed hidden among >512 BIP-39 filler words STILL detected (no run-cap drop)",
             any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 SEED1 + " " + ("zoo " * 520), path_kind="prod"))),
            ("R6 seeds-dump: 6 back-to-back seeds all detected (forward-scan)",
             len([f for f in ses.sp.scan_blob(" ".join([SEED1, SEED2, SEED3, SEED4, SEED5, SEED6]),
                  path_kind="prod") if f["kind"] == "mnemonic_phrase"]) >= 6),
            # ── cold-review round-7: run-scan bound SLICES (not drops) → seed in a >4096-token run still surfaces ──
            ("R7 seed in run >4096 tokens still detected (cap slices, not drops)",
             any(f["kind"] == "mnemonic_phrase" for f in ses.sp.scan_blob(
                 SEED1 + " " + ("zoo " * 5000), path_kind="prod"))),
            ("B2r4 hardhat test mnemonic in test dir → suppressed",
             not any(f["cls"] == "crypto-key" for f in ses.sp.scan_blob(
                 'mnemonic: "test test test test test test test test test test test junk"',
                 path_kind="test"))),
            ("FP7 solana PUBLIC key (44) not flagged as privkey",
             not any(f["kind"] == "solana_privkey_b58" for f in ses.sp.scan_blob(
                 'const signer = new PublicKey("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM");', path_kind="prod"))),
            ("FP7 solana 64-byte privkey (88) still detected",
             any(f["kind"] == "solana_privkey_b58" for f in ses.sp.scan_blob(
                 'const signerKey = "' + ("5J3mBbAH58CpQ3Y5RNJpUKPE62SQ5tfcvU2JpbnkeyhfsYB1Jcn" * 2)[:88] + '";',
                 path_kind="prod"))),
            ("FN9 key with 0x0000 prefix (real body) detected",
             any(f["kind"] == "evm_privkey" for f in ses.sp.scan_blob(
                 "PRIVATE_KEY=0x0000f3a2b1c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e", path_kind="prod"))),
            ("FP10 SSN in test path suppressed",
             not any(f["cls"] == "pii" for f in ses.sp.scan_blob("user SSN 415-22-8899", path_kind="test"))),
            ("FP10 example SSN in prod suppressed",
             not any(f["cls"] == "pii" for f in ses.sp.scan_blob("user_ssn = 000-00-0000", path_kind="prod"))),
            ("D2 firebase key not double-flagged as google_api",
             (lambda fs: any(f["kind"] == "firebase_config" for f in fs)
              and not any(f["kind"] == "google_api" for f in fs))(
                 ses.sp.scan_blob('const firebaseConfig={apiKey:"AIzaSyDummyDummyDummyDummyDummyDummyDum",projectId:"x"}',
                                  path_kind="prod"))),
            ("no-exfil: short SSN middle masked (not half-revealed)",
             "345" not in ses.sp.redact("123-45-6789") and "678" not in ses.sp.redact("123-45-6789")),
            # ── cold-review scanner fix-loop locks ──
            ("FN12 .pem private-key file scanned", "pem_private_key" in kinds),
            ("FN13 _match per-finding: anvil derives OWN address (not SALT)",
             (lambda dv: dv is None or any(  # dv None = eth lib missing → test not applicable
                 f["kind"] == "anvil_test_key_in_prod" and str(f.get("derived_address", "")).endswith("2266")
                 for f in findings))(ses.derive_evm_address(ANVIL))),
            ("FN14 non-dict .map does not abort the scan (Swan key still found)", "evm_privkey" in kinds),
            ("FP15 cluster dedup: 6x the SAME value → no cluster",
             not any(f["kind"] == "email_cluster" for f in ses.cluster_pii(
                 [{"cls": "pii", "kind": "email", "redacted": "a", "_match": "same@corp.io", "file": f"f{i}.js"}
                  for i in range(6)]))),
            ("FP15 cluster: 6 DIFFERENT values → cluster",
             any(f["kind"] == "email_cluster" for f in ses.cluster_pii(
                 [{"cls": "pii", "kind": "email", "redacted": "x", "_match": f"u{i}@corp.io", "file": "f"}
                  for i in range(6)]))),
            ("FP16 classify_path: test beats deploy",
             ses.sp.classify_path("test/scripts/setup.js") == "test"
             and ses.sp.classify_path("scripts/deploy.js") == "deploy"),
            ("no-exfil17 role_proof strips hex-runs",
             "…" in ses._strip_secret_runs("owner " + ANVIL) and ANVIL[2:] not in ses._strip_secret_runs("owner " + ANVIL)),
            # ── context-free (nameless) EVM key via derive-correlate (operator requirement: look for keys WITHOUT names too) ──
            ("nameless key CONFIRMED via derived-address correlation (no name needed)",
             (any(f["kind"] == "evm_privkey" and str(f.get("derived_address", "")).lower() == CTXFREE_ADDR.lower()
                  and str(f.get("file", "")).replace("\\", "/").endswith("deploy/nameless.js") for f in findings))
             if ses.derive_evm_address(CTXFREE_KEY) else True),
            ("context-free hash with NO address reference → dropped (no flood)",
             not any(str(f.get("file", "")).replace("\\", "/").endswith("build/hashes.txt")
                     and f["kind"] in ("evm_privkey", "evm_key_candidate") for f in findings)),
            # ── FP-tune: field-name / type-declaration noise (live drive of a public demo app; operator: "carefully") ──
            # Each pair PROVES firing: the FP is silenced AND a real datum of the same class still fires
            # (falls if the guard over-drops → recall regression, or under-drops → FP returns).
            ("FP-fin: cardnumber:String (type annotation) → NOT financial",
             not any(f["cls"] == "financial" for f in ses.sp.scan_blob("cardnumber:String", path_kind="prod"))),
            ("FP-fin: card_number = req.body.cardNumber (code ref) → NOT financial",
             not any(f["cls"] == "financial" for f in ses.sp.scan_blob(
                 "card_number = req.body.cardNumber", path_kind="prod"))),
            ("recall-fin: account_number: 111 (real digits) → STILL financial",
             any(f["cls"] == "financial" for f in ses.sp.scan_blob(
                 "account_number: 111 routing_number: 222", path_kind="prod"))),
            ("recall-fin: swift_code: DEUTDEFF (real all-caps SWIFT, no camel boundary) → STILL financial",
             any(f["cls"] == "financial" for f in ses.sp.scan_blob("swift_code: DEUTDEFF", path_kind="prod"))),
            ("recall-fin: card_number quoted digits → STILL financial",
             any(f["cls"] == "financial" for f in ses.sp.scan_blob(
                 'card_number: "4111111111111111"', path_kind="prod"))),
            ("FP-gen: apiToken:'HttpXsrfTokenExtractor' (Angular DI symbol) → NOT generic_secret",
             not any(f["kind"] == "generic_secret" for f in ses.sp.scan_blob(
                 'apiToken: "HttpXsrfTokenExtractor"', path_kind="prod"))),
            ("FP-gen: access_token:'platformBrowserDynamicElement' (symbol) → NOT generic_secret",
             not any(f["kind"] == "generic_secret" for f in ses.sp.scan_blob(
                 'access_token: "platformBrowserDynamicElement"', path_kind="prod"))),
            ("recall-gen: password:'SuperSecretValueHere' (weak pwd, high-intent key) → STILL generic_secret",
             any(f["kind"] == "generic_secret" for f in ses.sp.scan_blob(
                 'password: "SuperSecretValueHere"', path_kind="prod"))),
            ("recall-gen: token with digits (real opaque token) → STILL generic_secret",
             any(f["kind"] == "generic_secret" for f in ses.sp.scan_blob(
                 'token: "a1b2c3d4e5f6a7b8c9d0e1f2"', path_kind="prod"))),
            # ── source-map context-free (isolated pure-bundle target; see sm_findings block above) ──
            ("source-map context-free: nameless key restored from .map CONFIRMED via cross-source derived addr",
             (any(f["kind"] == "evm_privkey"
                  and str(f.get("derived_address", "")).lower() == CTXFREE_ADDR.lower()
                  and ".map::" in str(f.get("file", "")) for f in sm_findings))
             if ses.derive_evm_address(CTXFREE_KEY) else True),
            ("source-map context-free: random merkle-root in .map (addr not in corpus) → dropped",
             not any(f["kind"] in ("evm_privkey", "evm_key_candidate")
                     and "tree.ts" in str(f.get("file", "")) for f in sm_findings)),
            # ── A6: attention-gap × exposure ──
            ("A6 FIRING: a secret in a cold file is tagged attention_zone=cold + undup=cold-zone",
             bool(_find(a6_findings, "certs/prod.pem"))
             and all(f.get("attention_zone") == "cold" and f.get("undup") == "cold-zone"
                     for f in _find(a6_findings, "certs/prod.pem"))),
            ("A6 FIRING: a secret in a haste file is tagged haste=True (top priority)",
             bool(_find(a6_findings, "script/deploy.js"))
             and all(f.get("haste") is True for f in _find(a6_findings, "script/deploy.js"))),
            ("A6 non-cold finding → attention_zone=hot, no cold/haste tag",
             bool(_find(a6_findings, "src/Treasury.sol"))
             and all(f.get("attention_zone") == "hot" and not f.get("haste")
                     for f in _find(a6_findings, "src/Treasury.sol"))),
            ("A6 baseline: without attention maps → no cold/haste marks at all (behavior as before)",
             not any(f.get("attention_zone") == "cold" or f.get("haste") for f in a6_base)),
        ]

        passed = failed = 0
        for name, ok in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
            passed += ok
            failed += (not ok)

        # no-exfil: no redacted field contains the full SIGNER_KEY / ANVIL
        leak = any(SIGNER_KEY in f["redacted"] or ANVIL in f["redacted"] for f in findings)
        print(f"  [{'PASS' if not leak else 'FAIL'}] no-exfil: the full value did not leak into redacted")
        passed += (not leak)
        failed += leak

        total = passed + failed
        print(f"\nsecret_exposure_selftest: {passed}/{total} passed")
        return failed == 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
