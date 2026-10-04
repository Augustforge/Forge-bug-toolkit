#!/usr/bin/env python3
"""
Shared helper for boundary-lens scanners (verifier_binding_audit / bls_pairing_zero_input).

Scopes analysis to the ENCLOSING FUNCTION body rather than a flat +/-N line window, so
guards/tokens from a NEIGHBOURING function don't bleed in (which caused both false
positives — flagging a guarded fn — and false negatives — suppressing a real bug because
an adjacent fn had a guard). Brace-based, language-agnostic (Solidity/Rust/Go/Cairo/Move).
Falls back to a line window for indent-based files (Vyper/Python) or top-level code.
"""

import os
import re

FUNC_DECL = re.compile(r"\b(function|fn|func|def|modifier|impl|method)\b")


def func_spans(lines):
    """Return [(start_idx, end_idx)] line spans of brace-delimited function bodies."""
    spans = []
    n = len(lines)
    i = 0
    while i < n:
        if FUNC_DECL.search(lines[i]):
            j = i
            depth = 0
            started = False
            while j < n:
                depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    started = True
                if started and depth <= 0:
                    break
                j += 1
            if started and j < n:
                spans.append((i, j))
                i = j + 1
                continue
        i += 1
    return spans


def enclosing_block(lines, idx, spans, ctx=8):
    """Block scoped to the function containing idx; else a +/-ctx window."""
    for (s, e) in spans:
        if s <= idx <= e:
            return "\n".join(lines[s:e + 1])
    lo = max(0, idx - ctx)
    hi = min(len(lines), idx + ctx + 1)
    return "\n".join(lines[lo:hi])


def iter_source_files(src, exts, extra_skip=()):
    """Yield source files under src (or src itself if a file), skipping deps/tests."""
    skip = ("node_modules", ".git", "lib/forge-std", "__pycache__") + tuple(extra_skip)
    if os.path.isfile(src):
        yield src
        return
    for root, _dirs, files in os.walk(src):
        if any(s in root for s in skip):
            continue
        for f in files:
            if f.endswith(exts):
                yield os.path.join(root, f)
