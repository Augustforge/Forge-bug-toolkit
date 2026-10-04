#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pattern_replay.py — proactive un-dup compounding (FDE Plan 7, TIER B §61 · §48.1).

Entering a new target → auto-grep ALL `fingerprint`s from `undup_pattern_library.md` over the target's
codebase → report "N matched / 0" + ledger line `PRIOR-PATTERNS: N matched`. Turns the reactive
§48.1 note ("after a confirmed un-dup — grep the family") into a PROACTIVE one (on entry, automatic).
A matched pattern = the highest-priority seed hypothesis: the crowd has not closed it anywhere (un-dup by construction).

Fail-open EVERYWHERE: no library / no target / unreadable file / broken regex → 0 (not a crash, the hunt goes on).
Observational: only reads the target's code and (optionally) updates ONE ledger line. Mutates nothing else.

Run:
  py -3 -X utf8 bug-bounty-toolkit/scripts/_methodology/pattern_replay.py --src <target-repo> \
      --session-dir bug-bounty-toolkit/sessions/<slug>
Selftest:
  py -3 -X utf8 bug-bounty-toolkit/scripts/_methodology/pattern_replay_selftest.py
"""
import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLKIT = os.path.dirname(os.path.dirname(_HERE))  # bug-bounty-toolkit
DEFAULT_LIBRARY = os.path.join(_TOOLKIT, "sessions", "_methodology", "undup_pattern_library.md")

# ── library → [(name, regex_str), ...] ───────────────────────────────────────────────────────────
# fingerprint line = the CANONICAL bullet `- **fingerprint:** `<regex>`` (format fixed in
# undup_pattern_library.md, rule 2). The strict anchor (bullet + `**fingerprint:**`) deliberately does NOT catch
# prose mentions of `` `fingerprint:` `` in rules/intro (there the backtick is INSIDE bold — a different shape).
# HTML comments (the entry template stub) are stripped BEFORE parsing — otherwise a placeholder fingerprint from
# the comment would land in the pattern set.
_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_FP_RE = re.compile(r"^\s*[-*]\s*\*\*fingerprint:\*\*\s*`([^`]+)`", re.I)
_HDR_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$")


def parse_library(text):
    """[(name, regex_str), ...] from the library markdown. name = nearest preceding heading
    (`### PAT-NN — ...`); regex = the backtick span on the line with `fingerprint:`."""
    text = _COMMENT_RE.sub("", text or "")
    out = []
    cur = "unnamed"
    for line in text.splitlines():
        h = _HDR_RE.match(line)
        if h:
            cur = h.group(1).strip()
            continue
        m = _FP_RE.search(line)
        if m:
            out.append((cur, m.group(1).strip()))
    return out


def load_library(path):
    """Library text, or "" if the file is missing/unreadable (fail-open: 0 patterns → 0 matched)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# ── grep fingerprints over the target codebase ───────────────────────────────────────────────────
_SKIP_DIRS = {
    "node_modules", "dist", "build", "out", ".next", "vendor", "target",
    "__pycache__", ".venv", "venv", "coverage", "artifacts", "cache", ".cache",
    "bower_components", ".terraform",
}
_MAX_BYTES = 2_000_000  # larger files are minified bundles/artifacts, skip them


def _iter_files(root):
    """All files under root, except build/deps dirs, dot-dirs and files > _MAX_BYTES."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > _MAX_BYTES:
                    continue
            except OSError:
                continue
            yield p


def _read_text(path):
    """utf-8 text of a file (errors ignored), or None for binary/unreadable."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(_MAX_BYTES)
    except Exception:
        return None
    if b"\x00" in chunk:  # binary
        return None
    return chunk.decode("utf-8", errors="ignore")


def replay(src_root, patterns):
    """Greps each fingerprint over src_root. Returns a list of dicts:
    {name, regex, matched: bool, hit: 'rel/path:line' | None}. A single pass over files (drops a pattern
    from the active set as soon as it is found). Broken regex → matched=False, not a crash. Fail-open on I/O."""
    results = []
    for name, rx in patterns:
        try:
            cre = re.compile(rx)
        except re.error:
            cre = None
        results.append({"name": name, "regex": rx, "re": cre, "matched": False, "hit": None})
    active = [r for r in results if r["re"] is not None]
    if src_root and os.path.isdir(src_root):
        for path in _iter_files(src_root):
            if not active:
                break
            text = _read_text(path)
            if text is None:
                continue
            still = []
            for r in active:
                m = r["re"].search(text)
                if m:
                    rel = os.path.relpath(path, src_root).replace(os.sep, "/")
                    r["hit"] = "%s:%d" % (rel, text.count("\n", 0, m.start()) + 1)
                    r["matched"] = True
                else:
                    still.append(r)
            active = still
    for r in results:
        r.pop("re", None)  # do not hand the compiled object outward
    return results


# ── ledger line PRIOR-PATTERNS: ──────────────────────────────────────────────────────────────────
# Single source of truth for the line format (parsed by the gate `active_pattern_replay_skipped`: the value
# `{TODO}`/empty holds the exit, `N matched` lifts it).
CANON_PREFIX = "- **PRIOR-PATTERNS (§48.1 — recon-producer):**"
_LEDGER_LINE_RE = re.compile(r"(?im)^.*?\bPRIOR-PATTERNS\b[^:\n]*:.*$")
_LOOP_STATE_ANCHOR = "## Loop State"


def _sanitize(detail):
    # the gate treats `{`/`}` in the value as an unfilled sentinel — strip them from detail.
    return (detail or "").replace("{", "(").replace("}", ")").strip()


def update_ledger(ledger_path, n_matched, detail=""):
    """Replaces (or inserts) the `PRIOR-PATTERNS:` line with `PRIOR-PATTERNS: N matched — <detail>`.
    Fail-open: returns False on any I/O error (the hunt does not fail because of the producer)."""
    line = "%s %d matched" % (CANON_PREFIX, n_matched)
    d = _sanitize(detail)
    if d:
        line += " — " + d
    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return False
    if _LEDGER_LINE_RE.search(txt):
        new = _LEDGER_LINE_RE.sub(lambda _m: line, txt, count=1)
    else:
        idx = txt.find(_LOOP_STATE_ANCHOR)
        if idx >= 0:
            eol = txt.find("\n", idx)
            eol = len(txt) if eol < 0 else eol
            new = txt[:eol + 1] + line + "\n" + txt[eol + 1:]
        else:
            new = txt.rstrip("\n") + "\n" + line + "\n"
    try:
        with open(ledger_path, "w", encoding="utf-8") as f:
            f.write(new)
    except Exception:
        return False
    return True


# ── T11: 2nd pass — Refuted dead-shape index (negative-knowledge compounding, Plan 9) ─────────────
# Complements the POSITIVE library (undup_pattern_library — what is ALIVE and worth driving) with a NEGATIVE one:
# refuted shapes from past hunts → a greppable bank `dead_shapes.md`, so the SAME dead pattern is not
# re-driven between hunts. We index ONLY hard `[KILLED]` (KILL TAXONOMY: only KILLED =
# impossible; CONTESTED/SCOPED-OUT/DE-MINIMIS stay ALIVE building blocks — we do NOT bury them).
# The bank uses the same canonical format `- **fingerprint:** `<re>`` → the SAME `parse_library` reads it
# (not a parallel indexer). Fail-open: no sessions / broken file → empty bank, the hunt goes on.
DEFAULT_SESSIONS = os.path.join(_TOOLKIT, "sessions")
DEFAULT_DEAD_SHAPES = os.path.join(_TOOLKIT, "sessions", "_methodology", "dead_shapes.md")

_REFUTED_HDR_RE = re.compile(r"(?im)^##\s+Refuted\b.*$")
_TOP_HDR_RE = re.compile(r"(?m)^##\s+")
_ENTRY_HDR_RE = re.compile(r"(?m)^###\s+(H-[^\s\[]+)\s*\[([^\]]*)\]\s*:\s*(.+?)\s*$")
_FALSIFIER_RE = re.compile(r"(?im)^\s*[-*]\s*\*\*Killed[ -]by[^\n]*?\*\*\s*(.+)$")
# tokens are restored from the fingerprint (source of truth) — `\bword\b` spans of the lookahead-AND.
_FP_TOKEN_RE = re.compile(r"\\b([0-9a-zA-Zа-яА-Я_]+)\\b")  # Cyrillic range kept (logic): tokens of Russian-language hypotheses

# stop words (EN + RU) — function words, carry no hypothesis "shape". The Russian words are logic data: KEEP.
_STOP = set("""a an the of to in on for and or via with without into from by is are be as at
not no it its this that these those than then so such via per out off up down over under
через без для из под над это как что не нет при или и на по от до же бе тот эта эти как""".split())


def _salient_tokens(s):
    """Salient tokens of a string: lower, alnum/underscore, no stop words, len>=3, deduped with order."""
    seen, out = set(), []
    for t in re.findall(r"[0-9a-zA-Zа-яА-Я_]+", (s or "").lower()):  # Cyrillic range kept (logic)
        if len(t) < 3 or t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _shape_tokens(title, cap=6):
    """Up to `cap` most discriminating title tokens (longer = rarer → stronger). Stable."""
    toks = _salient_tokens(title)
    return sorted(toks, key=lambda t: (-len(t), toks.index(t)))[:cap]


def _build_fingerprint(tokens):
    """tokens → order-independent lookahead-AND regex (the same format parse_library reads)."""
    return "(?i)" + "".join(r"(?=.*\b%s\b)" % re.escape(t) for t in tokens)


def _tokens_from_fp(rx):
    """Recover tokens back from a fingerprint (for heading-vs-shape matching)."""
    return _FP_TOKEN_RE.findall(rx or "")


def parse_refuted(text):
    """Entries of the Refuted section of hypotheses.md → [{origin, status, title, falsifier, tokens}, ...].
    Section = from `## Refuted` to the next top-level `## `. Template placeholders `{...}` and
    KILL-TAXONOMY blockquote prose (lines `> - `[KILLED]`…`) are not caught (the `^###` anchor is required)."""
    text = _COMMENT_RE.sub("", text or "")
    m = _REFUTED_HDR_RE.search(text)
    if not m:
        return []
    nxt = _TOP_HDR_RE.search(text, m.end())
    section = text[m.end():(nxt.start() if nxt else len(text))]
    entries = list(_ENTRY_HDR_RE.finditer(section))
    out = []
    for i, em in enumerate(entries):
        oid, status, title = em.group(1), em.group(2).strip(), em.group(3).strip()
        if "{" in oid or "{" in title or "}" in title:  # template stub
            continue
        body_end = entries[i + 1].start() if i + 1 < len(entries) else len(section)
        body = section[em.end():body_end]
        fm = _FALSIFIER_RE.search(body)
        out.append({
            "origin": oid, "status": status, "title": title,
            "falsifier": (fm.group(1).strip() if fm else ""),
            "tokens": _shape_tokens(title),
        })
    return out


def _iter_session_ledgers(sessions_root):
    """`sessions/<slug>/hypotheses.md` (one level), except `_`/`.` dirs (methodology/inbox)."""
    try:
        names = sorted(os.listdir(sessions_root))
    except OSError:
        return
    for name in names:
        if name.startswith("_") or name.startswith("."):
            continue
        p = os.path.join(sessions_root, name, "hypotheses.md")
        if os.path.isfile(p):
            yield name, p


def index_refuted(sessions_root=DEFAULT_SESSIONS, out_path=DEFAULT_DEAD_SHAPES, write=True):
    """2nd pass: collects hard `[KILLED]` shapes from all Refuted sections → the dead-shapes bank.
    Dedup by token set. Returns a list of shape dicts. Fail-open on I/O."""
    shapes, seen = [], set()
    for slug, path in _iter_session_ledgers(sessions_root):
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
        except Exception:
            continue
        for e in parse_refuted(txt):
            if "KILLED" not in e["status"].upper():   # only a hard falsifier — the rest is alive
                continue
            if len(e["tokens"]) < 3:                  # < 3 tokens = unreliable shape, do not bury
                continue
            key = frozenset(e["tokens"])
            if key in seen:
                continue
            seen.add(key)
            e["source"] = "sessions/%s/hypotheses.md#%s" % (slug, e["origin"])
            shapes.append(e)
    if write:
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(_render_dead_bank(shapes))
        except Exception:
            pass
    return shapes


def _render_dead_bank(shapes):
    """Markdown bank in the canonical fingerprint format (read by the same parse_library)."""
    head = (
        "# dead_shapes.md — bank of refuted dead shapes (negative-knowledge compounding, Plan 9 T11)\n\n"
        "> **Auto-generated** by `pattern_replay.py --index-refuted` from the `## Refuted` sections of all\n"
        "> `sessions/*/hypotheses.md`. Only hard `[KILLED]` (impossible by falsifier) — NOT\n"
        "> CONTESTED/SCOPED-OUT/DE-MINIMIS (those are alive). Why: the same DEAD pattern is not re-driven between\n"
        "> hunts. Positive companion — `undup_pattern_library.md` (what is ALIVE and worth driving).\n"
        "> Checking a fresh hypothesis: `pattern_replay.py --check \"<text>\"`. NO NEED TO EDIT BY HAND —\n"
        "> it is regenerated.\n\n---\n\n"
    )
    if not shapes:
        return head + "_Empty for now: no `[KILLED]` shape has been indexed._\n"
    out = [head]
    for i, sh in enumerate(shapes, 1):
        fp = _build_fingerprint(sh["tokens"])
        out.append("### DEAD-%02d — %s" % (i, sh["title"][:100]))
        out.append("- **fingerprint:** `%s`" % fp)
        out.append("- **shape-tokens:** %s" % " ".join(sh["tokens"]))
        out.append("- **falsifier:** %s" % (sh["falsifier"][:220] if sh["falsifier"] else "—"))
        out.append("- **source:** %s\n" % sh["source"])
    return "\n".join(out) + "\n"


def load_dead_shapes(path=DEFAULT_DEAD_SHAPES):
    """Bank → [{name, regex, tokens}, ...] via the SAME parse_library (not a separate parser)."""
    out = []
    for name, rx in parse_library(load_library(path)):
        out.append({"name": name, "regex": rx, "tokens": _tokens_from_fp(rx)})
    return out


def match_dead_shape(candidate_text, dead_shapes, min_shared=3, min_ratio=0.4):
    """A hypothesis heading/text against the dead-shape bank. Returns the best matched shape (with
    shared/ratio fields) or None. Threshold: >=min_shared shared tokens AND shape coverage >=min_ratio —
    a single shared term does NOT resurrect a dead shape (anti-over-flag)."""
    cand = set(_salient_tokens(candidate_text))
    best = None
    for sh in dead_shapes:
        stoks = set(sh.get("tokens") or [])
        if not stoks:
            continue
        shared = cand & stoks
        ratio = len(shared) / len(stoks)
        if len(shared) >= min_shared and ratio >= min_ratio:
            if best is None or ratio > best["ratio"]:
                best = dict(sh, shared=sorted(shared), ratio=ratio)
    return best


def check_hypothesis(candidate_text, dead_shapes_path=DEFAULT_DEAD_SHAPES):
    """Is a fresh hypothesis already dead? Loads the bank → match. None = not a dead shape (drive as usual)."""
    return match_dead_shape(candidate_text, load_dead_shapes(dead_shapes_path))


def _pat_id(name):
    """`PAT-01 — i18n innerHTML XSS (...)` → `PAT-01`; otherwise the first words up to `—`/`(`."""
    head = re.split(r"[—(]", name, maxsplit=1)[0].strip()
    return head or name


def _detail(matched):
    if not matched:
        return "no matches"
    return "; ".join("%s@%s" % (_pat_id(r["name"]), r["hit"]) for r in matched)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Auto-grep un-dup fingerprints over the target → PRIOR-PATTERNS: N matched")
    ap.add_argument("--src", default=None,
                    help="root of the target codebase (missing/unreachable → 0 matched, fail-open)")
    ap.add_argument("--session-dir", default=None,
                    help="session folder with hypotheses.md (for updating the ledger line)")
    ap.add_argument("--library", default=DEFAULT_LIBRARY,
                    help="path to undup_pattern_library.md (default — the canonical one)")
    ap.add_argument("--index-refuted", action="store_true",
                    help="2nd pass: index [KILLED] shapes from all Refuted sections → dead_shapes.md")
    ap.add_argument("--check", default=None,
                    help="check the text of a fresh hypothesis against the dead-shape bank (dead shape?)")
    ap.add_argument("--sessions", default=DEFAULT_SESSIONS,
                    help="root of sessions/ (for --index-refuted)")
    ap.add_argument("--dead-shapes", default=DEFAULT_DEAD_SHAPES,
                    help="path to the dead_shapes.md bank (--index-refuted writes, --check reads)")
    args = ap.parse_args(argv)

    if args.index_refuted:
        shapes = index_refuted(args.sessions, args.dead_shapes)
        print("DEAD-SHAPES: %d indexed → %s" % (len(shapes), args.dead_shapes))
        for i, sh in enumerate(shapes, 1):
            print("  DEAD-%02d  %s  [%s]" % (i, sh["title"][:70], sh["source"]))
        return 0

    if args.check is not None:
        m = check_hypothesis(args.check, args.dead_shapes)
        if m:
            print("DEAD-SHAPE MATCH: %s (shared tokens: %s; coverage %.0f%%)"
                  % (m["name"], ", ".join(m["shared"]), m["ratio"] * 100))
            print("  → this shape was already REFUTED earlier. Re-read the falsifier BEFORE re-driving.")
        else:
            print("no dead-shape match — fresh shape, drive as usual.")
        return 0

    patterns = parse_library(load_library(args.library))
    results = replay(args.src, patterns)
    matched = [r for r in results if r["matched"]]
    n = len(matched)

    print("PRIOR-PATTERNS: %d matched  (library: %d patterns, target: %s)"
          % (n, len(results), args.src or "—"))
    for r in results:
        mark = "x" if r["matched"] else " "
        print("  [%s] %s  (fp: %s)" % (mark, r["name"], r["regex"]))
        if r["matched"]:
            print("        -> %s" % r["hit"])

    if args.session_dir:
        ledger = os.path.join(args.session_dir, "hypotheses.md")
        ok = update_ledger(ledger, n, _detail(matched))
        print("ledger %s: %s" % (ledger, "updated" if ok else "NOT updated (fail-open)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
