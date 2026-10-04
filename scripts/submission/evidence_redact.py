# -*- coding: utf-8 -*-
"""evidence_redact.py — PoC-evidence sanitizer before submission (recon-skills evidence-hygiene port, 2026-08-14).

Closes a gap: we only had a "Screenshot/Recording" heading in the disclosure template, NO actual
redaction protocol. Every live web2/dapphunt PoC (HAR export, request log, DevTools screenshot) carries TWO risks:
  (a) OUR secrets — burner-session cookie / Authorization Bearer / CSRF-token → submitting them to the triager =
      compromise of our test session (and potentially an OPSEC deanon of the burner account);
  (b) VICTIM-PII — someone else's email/SSN/CC/tokens that accidentally ended up in the response → we have NO right
      to distribute them (white-hat: minimize collection/disclosure of other people's data).

This module scrubs BOTH from the HAR / text log / headers BEFORE attaching it to the report.
Reuses the shared `secret_patterns` (secret/PII detection) + hard-strip of sensitive headers.

API:
    redact_text(text) -> str                      # masks secrets/PII/Cookie/Auth in raw text
    sanitize_headers(headers: dict) -> dict        # hard-strip Cookie/Authorization/Set-Cookie/CSRF
    redact_har(har: dict) -> dict                  # cleans all HAR entries (headers/cookies/postData/content)

CLI: py -3 evidence_redact.py capture.har   # → capture.redacted.har next to it
"""
import copy
import json
import os
import re
import importlib.util

# self-contained: load the shared secret-core by file-path (don't rely on sys.path / cwd).
_METHOD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_methodology")


def _load_secret_patterns():
    path = os.path.join(_METHOD_DIR, "secret_patterns.py")
    try:
        spec = importlib.util.spec_from_file_location("secret_patterns", path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except Exception:
        return None


_SP = _load_secret_patterns()

# Sensitive headers — hard-strip ENTIRELY (value → [REDACTED]), we don't try to partially mask them.
_SENSITIVE_HEADERS = frozenset({
    "cookie", "set-cookie", "authorization", "proxy-authorization", "x-api-key", "x-auth-token",
    "x-csrf-token", "x-xsrf-token", "csrf-token", "x-session-token", "x-access-token",
    "authentication", "api-key", "x-amz-security-token", "x-goog-api-key",
})
_REDACTED = "[REDACTED]"

# Cookie/Bearer in RAW text (log/response, where there's no header structure).
_COOKIE_LINE_RE = re.compile(r"(?im)^(cookie|set-cookie)\s*:\s*.+$")
_AUTH_LINE_RE = re.compile(r"(?im)^(authorization|proxy-authorization)\s*:\s*.+$")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}")
_COOKIE_KV_RE = re.compile(r"(?i)\b(session|sess|sid|token|csrf|xsrf|auth|jwt|access_token|refresh_token)"
                           r"[a-z0-9_\-]*\s*=\s*[^;\s&\"']{8,}")


def redact_text(text):
    """Masks in raw text: (1) secrets/crypto-keys/PII via secret_patterns, (2) Cookie/Auth
    header lines, (3) Bearer tokens, (4) session/token=value pairs. Returns the cleaned text."""
    if not text or not isinstance(text, str):
        return text
    out = text
    # 1) secrets + PII via the shared core (mask each found RAW value)
    if _SP is not None:
        try:
            for f in _SP.scan_blob(out, path_kind="runtime", enable_pii=True):
                raw = f.get("_match")
                if raw and isinstance(raw, str) and len(raw) >= 6 and raw in out:
                    out = out.replace(raw, _REDACTED)
        except Exception:
            pass
    # 2-4) headers/tokens (structurally, not relying on secret_patterns)
    out = _COOKIE_LINE_RE.sub(lambda m: "%s: %s" % (m.group(1), _REDACTED), out)
    out = _AUTH_LINE_RE.sub(lambda m: "%s: %s" % (m.group(1), _REDACTED), out)
    out = _BEARER_RE.sub("Bearer " + _REDACTED, out)
    out = _COOKIE_KV_RE.sub(lambda m: m.group(0).split("=")[0] + "=" + _REDACTED, out)
    return out


def sanitize_headers(headers):
    """Headers dict → a copy with sensitive values hard-stripped. Case-insensitive by name."""
    if not isinstance(headers, dict):
        return headers
    out = {}
    for k, v in headers.items():
        out[k] = _REDACTED if str(k).lower() in _SENSITIVE_HEADERS else v
    return out


def _sanitize_har_headers_list(headers):
    """HAR format: list of [{name, value}]. Returns a copy with sensitive entries stripped."""
    if not isinstance(headers, list):
        return headers
    out = []
    for h in headers:
        if isinstance(h, dict) and str(h.get("name", "")).lower() in _SENSITIVE_HEADERS:
            out.append({**h, "value": _REDACTED})
        else:
            out.append(h)
    return out


def redact_har(har):
    """Cleans a HAR object (dict): for each entry — request/response headers, cookie arrays,
    postData.text, response.content.text. Returns a NEW object (the original is not mutated)."""
    if not isinstance(har, dict):
        return har
    h = copy.deepcopy(har)
    entries = (((h.get("log") or {}).get("entries")) if isinstance(h.get("log"), dict) else None) or []
    for e in entries:
        if not isinstance(e, dict):
            continue
        req, resp = e.get("request"), e.get("response")
        if isinstance(req, dict):
            req["headers"] = _sanitize_har_headers_list(req.get("headers"))
            req["cookies"] = [_REDACTED] if req.get("cookies") else req.get("cookies")
            if isinstance(req.get("postData"), dict) and isinstance(req["postData"].get("text"), str):
                req["postData"]["text"] = redact_text(req["postData"]["text"])
        if isinstance(resp, dict):
            resp["headers"] = _sanitize_har_headers_list(resp.get("headers"))
            resp["cookies"] = [_REDACTED] if resp.get("cookies") else resp.get("cookies")
            content = resp.get("content")
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                content["text"] = redact_text(content["text"])
    return h


def _main():
    import sys
    if len(sys.argv) < 2:
        print("usage: evidence_redact.py <capture.har>  →  <capture.redacted.har>")
        sys.exit(2)
    src = sys.argv[1]
    with open(src, "r", encoding="utf-8") as f:
        har = json.load(f)
    out = redact_har(har)
    dst = re.sub(r"\.har$", "", src, flags=re.I) + ".redacted.har"
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("redacted → %s" % dst)


if __name__ == "__main__":
    _main()
