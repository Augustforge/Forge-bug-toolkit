#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""commit_archaeology.py — T14-B: git as a pointer to HASTE (attention gap, phase 1b).

Idea (depth_engine_plan.md §5-bis): a bug lives where nobody looked. An audit shows where the AUDITOR did not
look (that is T14-A). Git shows where the AUTHOR did not look. Both are machine-computable and both are
orthogonal to the T10 model — they work even where there is no corpus.

Difference from wave_delta.py: that one answers "what changed since MY last visit" (re-visit).
This one answers "where in the project history are the traces of haste" (works on the FIRST visit).

Signals per file:
  post_audit  — edits AFTER the audit date (a generalization of our `deployed != audited` to the whole repo)
  haste       — commit messages like quick fix / temp / hotfix / wip / revert / TODO
  churn       — many edits in a short time = unstable logic
  untested    — the commit changed the file and did NOT touch a single test
  pre_release — the file landed in the last commits before a tag (the classic unchecked edit)

Usage:
  py -3 -X utf8 commit_archaeology.py <repo> [--audit-date YYYY-MM-DD] [--since YYYY-MM-DD]
                                            [--ext .sol,.rs] [--top 25] [--json]

IMPORTANT: this is a PLACE GENERATOR, not a finding. The signal is noisy on its own (an active file may be
just the core of the product) — per the plan, use it in INTERSECTION with another source (§6), not alone.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

HASTE_RE = re.compile(
    r"\b(quick\s*fix|quickfix|hotfix|hot\s*fix|temp(orary)?|tmp|wip|work in progress|"
    r"todo|fixme|hack|revert|rollback|oops|typo fix|forgot|missed|asap|last minute|"
    r"костыл|времен|быстр|фикс на скорую)\b",  # Cyrillic alternatives kept: match Russian commit messages ("kludge|temp|quick|quick-and-dirty fix")
    re.I,
)

TEST_RE = re.compile(r"(^|/)(tests?|spec|__tests__|it|e2e)/|[._-](test|spec)\.|test_[^/]*$", re.I)

# Weights are chosen so that a single signal does NOT push a file to the top: either a very strong
# post-audit/haste, or a coincidence of several axes, is needed. This is a direct requirement of §9 (churn is noisy).
WEIGHTS = {"post_audit": 3.0, "haste": 2.5, "untested": 1.5, "pre_release": 2.0, "churn": 0.4}


def git(repo, *args):
    """git with a fixed cwd. Returns stdout, or '' on any error (fail-open)."""
    try:
        out = subprocess.run(
            ["git", "-C", repo] + list(args),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def is_repo(repo):
    return bool(git(repo, "rev-parse", "--is-inside-work-tree").strip())


def collect(repo, since, exts):
    """One pass over the history: (sha, date, subject, [files]) -> per-file signals."""
    sep = "\x1e"
    fmt = "%H%x1f%ad%x1f%s"
    args = ["log", "--date=short", "--name-only", "--no-merges", "--pretty=format:" + sep + fmt]
    if since:
        args.append("--since=" + since)
    raw = git(repo, *args)
    commits = []
    for block in raw.split(sep):
        block = block.strip("\n")
        if not block:
            continue
        head, _, tail = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        sha, date, subject = parts[0], parts[1], parts[2]
        files = [f.strip() for f in tail.splitlines() if f.strip()]
        commits.append((sha, date, subject, files))
    return commits


def wanted(path, exts):
    if not exts:
        return True
    return any(path.lower().endswith(e) for e in exts)


def pre_release_files(repo, depth=3):
    """Files from the last `depth` commits before EACH tag — the place of an unchecked edit."""
    tags = [t for t in git(repo, "tag", "--sort=-creatordate").splitlines() if t.strip()][:10]
    out = set()
    for t in tags:
        raw = git(repo, "log", "--name-only", "--no-merges", "--pretty=format:", "-n", str(depth), t)
        for line in raw.splitlines():
            if line.strip():
                out.add(line.strip())
    return out


def analyze(repo, audit_date, since, exts, top):
    commits = collect(repo, since, exts)
    if not commits:
        return None

    sig = defaultdict(lambda: defaultdict(float))
    evid = defaultdict(lambda: defaultdict(list))
    prerel = pre_release_files(repo)

    for sha, date, subject, files in commits:
        touched = [f for f in files if wanted(f, exts)]
        if not touched:
            continue
        has_test = any(TEST_RE.search(f) for f in files)
        haste = bool(HASTE_RE.search(subject))
        post = bool(audit_date and date > audit_date)

        for f in touched:
            if TEST_RE.search(f):
                continue                      # a test itself is not a hunt target
            sig[f]["churn"] += 1
            if haste:
                sig[f]["haste"] += 1
                evid[f]["haste"].append("%s %s — %s" % (sha[:8], date, subject[:70]))
            if post:
                sig[f]["post_audit"] += 1
                evid[f]["post_audit"].append("%s %s — %s" % (sha[:8], date, subject[:70]))
            if not has_test:
                sig[f]["untested"] += 1

    for f in list(sig):
        if f in prerel:
            sig[f]["pre_release"] = 1
            evid[f]["pre_release"].append("file is in the last commits before a tag")

    rows = []
    for f, s in sig.items():
        # churn is dampened: 40 edits must not outweigh a single post-audit commit 40 times over
        churn_component = WEIGHTS["churn"] * min(s.get("churn", 0), 30) ** 0.5
        score = churn_component + sum(
            WEIGHTS[k] * s.get(k, 0) for k in ("post_audit", "haste", "untested", "pre_release")
        )
        rows.append({
            "file": f,
            "score": round(score, 2),
            "signals": {k: int(v) for k, v in s.items()},
            "evidence": {k: v[:3] for k, v in evid[f].items()},
        })
    rows.sort(key=lambda r: -r["score"])

    # A degenerate history MUST be reported, rather than producing a confident ranking out of nothing.
    # A typical bug-bounty case: a public repo published as ONE squash commit ("publishing to
    # public repo") — then all files have the same score, the ranking is meaningless but looks
    # authoritative. Silently handing over such a list = exactly the "silent cap" that we forbid.
    degenerate = None
    if len(commits) < 5:
        degenerate = "the history has only %d commit(s) — there is nowhere for haste signals to come from" % len(commits)
    elif rows:
        top_score = rows[0]["score"]
        same = sum(1 for r in rows if abs(r["score"] - top_score) < 1e-9)
        if same >= max(10, 0.7 * len(rows)):
            degenerate = ("%d of %d files have an IDENTICAL score — the history is collapsed (squash/import), "
                          "the ranking carries no information" % (same, len(rows)))

    return {"repo": repo, "commits_scanned": len(commits), "audit_date": audit_date,
            "degenerate": degenerate, "rows": rows[:top]}


def main():
    ap = argparse.ArgumentParser(description="T14-B: git haste signals as a PLACE generator")
    ap.add_argument("repo")
    ap.add_argument("--audit-date", help="YYYY-MM-DD — edits after this date were not seen by the auditor")
    ap.add_argument("--since", help="YYYY-MM-DD — do not look at history earlier than this")
    ap.add_argument("--ext", default="", help="comma-separated extension filter: .sol,.rs,.go")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    repo = os.path.abspath(a.repo)
    if not is_repo(repo):
        print("NOT a git repository: %s" % repo)
        sys.exit(2)

    exts = [e.strip().lower() for e in a.ext.split(",") if e.strip()]
    res = analyze(repo, a.audit_date, a.since, exts, a.top)
    if not res:
        print("History is empty (or filtered down to nothing).")
        sys.exit(1)

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    print("=== COMMIT ARCHAEOLOGY (T14-B) — %s" % repo)
    print("commits scanned: %d%s" % (
        res["commits_scanned"],
        (" · audit date: " + a.audit_date) if a.audit_date else " · audit date not set (--audit-date will strengthen the signal)",
    ))
    if res["degenerate"]:
        print()
        print("⛔ HISTORY UNUSABLE: %s." % res["degenerate"])
        print("   T14-B gives NO SIGNAL on this repo — do not pass the list below off as a source of PLACE.")
        print("   What to do: (a) look for an upstream repo with a real history (fork/mirror/monorepo")
        print("   it was published from); (b) rely on T14-A (audit-map inversion) and on the T10 model.")
    print()
    for i, r in enumerate(res["rows"], 1):
        s = r["signals"]
        flags = " ".join(
            "%s=%d" % (k, s[k]) for k in ("post_audit", "haste", "untested", "pre_release", "churn") if s.get(k)
        )
        print("%2d. [%5.2f] %s" % (i, r["score"], r["file"]))
        print("        %s" % flags)
        for kind, items in r["evidence"].items():
            for it in items:
                print("        └ %s: %s" % (kind, it))
    print()
    print("⚠ This is a PLACE GENERATOR, not a finding. The signal is noisy: an active file may be just the core")
    print("  of the product. Per plan §6, take it in INTERSECTION with another source (D-NN or an audit-map hole).")


if __name__ == "__main__":
    main()
