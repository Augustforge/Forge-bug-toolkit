#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""secret_exposure_scanner.py — the STATIC half of the Exposure Engine (P0-2).

A cross-engine (web3/web2/dapphunt) pre-T1 grep pass over the target's CLONE: code, deploy scripts,
configs, .env, minified bundles, source maps (`sourcesContent`), git history. Looks for secrets,
crypto keys, PII, financial/confidential data — EVERYWHERE and in ENCODED form (decode layer
in `secret_patterns`). The runtime half (live page/app/network/storage) is in `runtime_harness.py`.

Discipline: anti-FP (vendored/test/placeholder), no-exfil (redact), anti-overfit (mechanism, not a hack).

Usage:
  py -3 -X utf8 secret_exposure_scanner.py --target <clone_dir> --session-dir <sessions/{target}> \\
      [--no-pii] [--git-history] [--verify-rpc <rpc_url>] [--json]

Producer: `{session-dir}/exposure_scan.md` + ledger line `EXPOSURE-SCAN: N secrets / M pii / K data / 0`.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import secret_patterns as sp  # noqa: E402

# derive / correlate primitives live in the SHARED core (secret_patterns) — used by BOTH the static scanner
# and the runtime capture_exposure (ONE implementation, two callers). Aliased for back-compat: the selftest
# and producer reference `ses.derive_evm_address` / `ses._strip_secret_runs` / `ses.correlate_keys_to_roles`.
derive_evm_address = sp.derive_evm_address
_strip_secret_runs = sp._strip_secret_runs
correlate_keys_to_roles = sp.correlate_key_candidates

SCAN_EXTS = {
    ".sol", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".java",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".sh", ".bash",
    ".txt", ".md", ".html", ".htm", ".xml", ".properties", ".map",
    # private-key / cert files — where private keys most often live (cold-review FN: previously not read)
    ".pem", ".key", ".crt", ".cer", ".pub", ".asc", ".gpg", ".ppk", ".p12", ".pfx", ".jks", ".keystore",
}
ALWAYS_SCAN_NAMES = {".env", ".env.local", ".env.production", ".npmrc", ".netrc",
                     "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"}
MAX_FILE_BYTES = 3_000_000
PII_CLUSTER_THRESHOLD = 5   # <N single PII of one kind = noise


# ── File iteration ───────────────────────────────────────────────────────────────────
def _read_text(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return None
        with open(path, "rb") as fh:
            raw = fh.read()
        if b"\x00" in raw[:4096]:      # binary
            return None
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return None


def iter_files(target):
    """Yields (relpath, path_kind, text). Vendored is skipped BEFORE reading."""
    for root, dirs, files in os.walk(target):
        # prune vendored directories at the entry (do not descend)
        dirs[:] = [d for d in dirs
                   if sp.classify_path(os.path.relpath(os.path.join(root, d), target)) != "vendor"]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, target)
            ext = os.path.splitext(name)[1].lower()
            if ext not in SCAN_EXTS and name not in ALWAYS_SCAN_NAMES and not name.startswith(".env"):
                continue
            kind = sp.classify_path(rel)
            if kind == "vendor":
                continue
            text = _read_text(full)
            if text is None:
                continue
            yield rel, kind, text


# ── Source-map (sourcesContent restores the original) ────────────────────────────────
def _scan_sourcemap(rel, kind, text):
    """Restore originals from `sourcesContent` and scan each. Returns (findings, corpus_pieces): the restored
    sources ALSO feed the derive-correlate corpus, so a nameless key restored from one source is confirmed by a
    derived address referenced in ANOTHER restored source (a pure-bundle target has NO plain files in corpus →
    without this the context-free candidate could never be confirmed and would always drop). `emit_key_candidates`
    surfaces bare in-range 64-hex with NO key-name — the original variable name is often gone in a restored source."""
    import json
    findings, corpus_pieces = [], []
    try:
        data = json.loads(text)
    except Exception:
        return findings, corpus_pieces
    if not isinstance(data, dict):     # a .map with non-object JSON ([]/null/42) → do not crash the whole scan (cold-review)
        return findings, corpus_pieces
    for i, content in enumerate(data.get("sourcesContent") or []):
        if not content:
            continue
        src_name = ""
        try:
            src_name = (data.get("sources") or [])[i]
        except Exception:
            pass
        sub_kind = sp.classify_path(src_name) if src_name else kind
        if sub_kind == "vendor":
            continue
        corpus_pieces.append(content)   # restored source → corpus (context-free cross-source confirmation)
        for f in sp.scan_blob(content, path_kind=sub_kind, source="sourcemap", emit_key_candidates=True):
            f["file"] = f"{rel}::{src_name or i}"
            findings.append(f)
    return findings, corpus_pieces


# ── git history: secret added → removed (needs the FULL history) ─────────────────────
def scan_git_history(target, max_commits=400):
    findings, warn = [], None
    def git(*a):
        try:
            r = subprocess.run(["git", "-C", target, *a], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=120)
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""
    if not os.path.isdir(os.path.join(target, ".git")):
        return findings, "not-a-git-repo"
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        warn = "SHALLOW repo (--depth 1) — git-history signal LOST; re-clone with full history"
    log = git("log", "-p", "--all", f"--max-count={max_commits}",
              "--", ".")
    for line in log.splitlines():
        if not (line.startswith("+") or line.startswith("-")):
            continue
        payload = line[1:]
        for f in sp.scan_blob(payload, path_kind="prod", enable_pii=False):
            if f["cls"] in ("crypto-key", "secret"):
                f["file"] = "git-history"
                f["evidence"] = f"in git diff ({'added' if line[0]=='+' else 'removed'}): " + f["evidence"]
                findings.append(f)
    return findings, warn


# ── Offline key-derive + keypair→role correlation + passive RPC ─────────────────────
# derive_evm_address / correlate_keys_to_roles / _strip_secret_runs are aliased from the shared core above.
def passive_rpc_balance(address, rpc):
    try:
        import json as _j
        import urllib.request
        req = urllib.request.Request(
            rpc, method="POST", headers={"Content-Type": "application/json"},
            data=_j.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance",
                           "params": [address, "latest"]}).encode())
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _j.loads(resp.read()).get("result")
    except Exception:
        return None


# ── Aggregate ────────────────────────────────────────────────────────────────────────
def cluster_pii(findings):
    """Cluster PII by the number of DISTINCT values (cold-review FP: one email in 5 files != bulk leak; and
    conversely — 5 different values in one file = leak). Dedup by the raw `_match`, fallback to redacted.
    <threshold distinct = noise → dropped; a cluster → one finding with a count."""
    pii = [f for f in findings if f["cls"] == "pii"]
    rest = [f for f in findings if f["cls"] != "pii"]
    by_kind = {}
    for f in pii:
        by_kind.setdefault(f["kind"], {})[f.get("_match", f["redacted"])] = f
    clustered = []
    for kind, uniq in by_kind.items():
        group = list(uniq.values())
        if len(group) >= PII_CLUSTER_THRESHOLD:
            g = group[0]
            clustered.append({
                "cls": "pii", "kind": f"{kind}_cluster", "severity": "medium",
                "redacted": f"{len(group)} distinct × {kind}",
                "evidence": f"bulk PII exposure ({len(group)} distinct {kind})",
                "file": g.get("file", "?"), "decoded_via": None,
            })
    return rest + clustered


# ── A6 (Wave 1): attention-gap × exposure — secrets live in cold zones ───────────────
# T14 (audit_coverage_invert → cold zones, commit_archaeology → haste files) STEERS the scanner:
# secrets are systematically in the scaffolding (deploy/CI/.env.example/migrations/tests) that auditors and
# the crowd do not read. A finding in a cold zone = a DOUBLE un-dup (nobody looked + a cheap crit); a key
# in a rushed commit (haste) = top priority. Implemented as a TAG + output rank (cold/haste FIRST),
# the detection itself is unchanged. Fail-soft: no maps → behavior as before.
def _norm_rel(p):
    return str(p or "").replace("\\", "/").lstrip("./").strip()


def _match_attention(rel, entries):
    """rel is in the set if it is an exact match, a path suffix or a dir prefix."""
    for e in entries:
        if not e:
            continue
        if rel == e or rel.endswith("/" + e) or rel.startswith(e.rstrip("/") + "/"):
            return True
    return False


def _tag_attention(findings, cold_files, haste_files):
    cold = {_norm_rel(x) for x in (cold_files or []) if x}
    haste = {_norm_rel(x) for x in (haste_files or []) if x}
    for f in findings:
        rel = _norm_rel(f.get("file", ""))
        if cold and _match_attention(rel, cold):
            f["attention_zone"] = "cold"
            f["undup"] = "cold-zone"          # nobody looked + a cheap crit
        else:
            f.setdefault("attention_zone", "hot")
        if haste and _match_attention(rel, haste):
            f["haste"] = True                 # a key in a rushed commit = top priority
    return findings


def _read_list(path):
    """List of relpaths (one per line) from an attention-map file. Fail-soft: no file → []."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    except Exception:
        return []


def scan_target(target, enable_pii=True, git_history=False, verify_rpc=None,
                cold_files=None, haste_files=None):
    findings, corpus_parts, warnings = [], [], []
    for rel, kind, text in iter_files(target):
        if rel.lower().endswith(".map"):
            sm_findings, sm_corpus = _scan_sourcemap(rel, kind, text)
            findings.extend(sm_findings)
            if len(corpus_parts) < 4000:            # restored sources join the corpus (context-free cross-source)
                corpus_parts.extend(sm_corpus)
            continue
        fs = sp.scan_blob(text, path_kind=kind, enable_pii=enable_pii, emit_key_candidates=True)
        for f in fs:
            f["file"] = rel
        findings.extend(fs)
        if len(corpus_parts) < 4000:
            corpus_parts.append(text)

    corpus = "\n".join(corpus_parts)
    # correlate uses the per-finding `_match` (the raw value from scan_blob), NOT a file-global re.search
    findings = correlate_keys_to_roles(findings, corpus)

    if verify_rpc:
        for f in findings:
            if f.get("derived_address"):
                bal = passive_rpc_balance(f["derived_address"], verify_rpc)
                if bal and bal not in ("0x0", "0x"):
                    f["severity"] = "critical"
                    f["funded"] = bal
                    if f["kind"] == "evm_key_candidate":   # funded nameless candidate = confirmed key
                        f["kind"] = "evm_privkey"
                        f["evidence"] = "nameless key CONFIRMED — derived address funded on-chain"

    # Drop context-free candidates NOT confirmed (derived address neither referenced in corpus nor funded) —
    # almost all are hashes/bytes32; surfacing them would flood. Confirmed ones were renamed to evm_privkey.
    findings = [f for f in findings if f["kind"] != "evm_key_candidate"]

    if git_history:
        gh, warn = scan_git_history(target)
        findings.extend(gh)
        if warn:
            warnings.append(warn)

    findings = cluster_pii(findings)          # dedup PII by value (needs `_match`) BEFORE the strip

    findings = _tag_attention(findings, cold_files, haste_files)   # A6: cold/haste tags + rank

    for f in findings:                        # no-exfil: strip the RAW value before returning
        f.pop("_match", None)
        f.pop("_raw", None)
    return findings, warnings


# ── Producer + ledger ───────────────────────────────────────────────────────────────
_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def summarize(findings):
    n_secret = sum(1 for f in findings if f["cls"] in ("secret", "crypto-key"))
    n_pii = sum(1 for f in findings if f["cls"] == "pii")
    n_data = sum(1 for f in findings if f["cls"] == "financial")
    return n_secret, n_pii, n_data


def write_producer(findings, session_dir, warnings):
    n_secret, n_pii, n_data = summarize(findings)
    lines = ["# Exposure Scan — secrets / keys / PII / confidential data", "",
             "_Producer `secret_exposure_scanner.py`. No-exfil: values are REDACTED (first/last 4)._",
             "", f"**Ledger line:** `EXPOSURE-SCAN: {n_secret} secrets / {n_pii} pii / {n_data} data / 0`", ""]
    if warnings:
        lines += ["**Warnings:** " + "; ".join(warnings), ""]
    if not findings:
        lines += ["No findings (surface pass done; see the runtime half for a live target)."]
    else:
        lines += ["| sev | class | kind | file | redacted | evidence |",
                  "|---|---|---|---|---|---|"]
        # A6: within a severity — haste files FIRST, then the cold zone (attention-gap rank).
        for f in sorted(findings, key=lambda x: (_SEV_ORDER.get(x["severity"], 9),
                                                 0 if x.get("haste") else 1,
                                                 0 if x.get("attention_zone") == "cold" else 1)):
            extra = ""
            if f.get("derived_address"):
                extra = f" · addr={f['derived_address']}"
            if f.get("role_proof"):
                extra += " · ROLE-MATCH"
            if f.get("funded"):
                extra += f" · FUNDED={f['funded']}"
            if f.get("attention_zone") == "cold":
                extra += " · COLD-ZONE(un-dup)"
            if f.get("haste"):
                extra += " · HASTE-COMMIT"
            lines.append(f"| {f['severity']} | {f['cls']} | {f['kind']} | {f.get('file','?')} | "
                         f"{f['redacted']} | {f['evidence']}{extra} |")
    out = os.path.join(session_dir, "exposure_scan.md")
    os.makedirs(session_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return out, (n_secret, n_pii, n_data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="clone dir of the target")
    ap.add_argument("--session-dir", help="where to write exposure_scan.md")
    ap.add_argument("--no-pii", action="store_true")
    ap.add_argument("--git-history", action="store_true", help="scan git log -p (needs the FULL history)")
    ap.add_argument("--verify-rpc", help="passive RPC for the balance check of derived addresses")
    ap.add_argument("--cold-files", help="A6: file with a list of cold zones (audit_coverage_invert) — rank priority")
    ap.add_argument("--haste-files", help="A6: file with a list of haste files (commit_archaeology) — top priority")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.target):
        print(f"[!] target not a dir: {args.target}", file=sys.stderr)
        sys.exit(2)

    findings, warnings = scan_target(args.target, enable_pii=not args.no_pii,
                                     git_history=args.git_history, verify_rpc=args.verify_rpc,
                                     cold_files=_read_list(args.cold_files) if args.cold_files else None,
                                     haste_files=_read_list(args.haste_files) if args.haste_files else None)
    n_secret, n_pii, n_data = summarize(findings)
    ledger = f"EXPOSURE-SCAN: {n_secret} secrets / {n_pii} pii / {n_data} data / 0"

    if args.json:
        import json as _j
        print(_j.dumps({"findings": findings, "warnings": warnings, "ledger": ledger}, ensure_ascii=False, indent=2))
    if args.session_dir:
        out, _ = write_producer(findings, args.session_dir, warnings)
        print(f"[+] producer: {out}")
    print(f"[+] {ledger}")
    for w in warnings:
        print(f"[!] {w}")
    # always exit 0 (the scanner is a PLACE generator, not a gate)


if __name__ == "__main__":
    main()
