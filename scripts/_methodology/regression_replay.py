#!/usr/bin/env python3
"""Regression replay — a recall/precision meter of the methodology on KNOWN bugs.

Boundary (honest): this script does NOT call Claude subagents. It does only the
deterministic part:
  - `prepare`            — prepares snapshots from the manifest (local: verify | git: clone | manifest-only: skip)
  - `score <leads.json>` — compares my leads (emitted IN-SESSION by the scout phase) with the manifest's
                           bug_location → recall + precision → writes calibration_log.jsonl

The scout run itself is done by the operator in-session (scout_fanout.md), dumps leads.json, then runs `score`.
This measures the EFFECT of changes (scout-prompt / anti-slop gate): change → re-score → recall does not
drop / precision grows. Without it, changes "feel like progress" but are not proven (a lesson from a past miss).

Matching is FILE-level (line-level is noisy): a lead is credited to a case if the file token of bug_location
occurs in the lead's path (or vice versa). This is the lower honest bound of recall.

Usage:
  py -3 -X utf8 regression_replay.py prepare
  py -3 -X utf8 regression_replay.py score path/to/leads.json [--case <name>]

leads.json format:
  {"target": "<name>", "leads": [ {"file_line": "src/.../X.sol:120", "cat": "...",
                                   "prediction": "...", "falsifier": "...", "confidence": "med"}, ... ]}
"""
import sys
import os
import re
import json
import time
import subprocess


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SESSIONS = os.path.join(ROOT, "bug-bounty-toolkit", "sessions")
MANIFEST = os.path.join(SESSIONS, "_methodology", "regression_manifest.yaml")
SNAP_DIR = os.path.join(SESSIONS, "_methodology", "_regression_snapshots")
CALIB = os.path.join(SESSIONS, "_methodology", "calibration_log.jsonl")


# ---------- manifest loading (PyYAML if present, otherwise a mini-parser of our shape) ----------
def load_manifest(block="cases"):
    """Reads a top-level manifest block (`cases:` by default). The default preserves
    the earlier behavior — regression_replay sees only `cases`, as before."""
    with open(MANIFEST, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        import yaml  # noqa
        data = yaml.safe_load(raw)
        return data.get(block, []) if isinstance(data, dict) else []
    except Exception:
        return _mini_parse(raw, block)


def load_disclosed():
    """The `disclosed:` block (P8 benchmark-against-disclosed) — a sibling of `cases:`."""
    return load_manifest("disclosed")


def _mini_parse(raw, block="cases"):
    """A minimal parser of exactly our structure: <block>: → a list of `- key: value`.
    Stops at the next top-level key (col-0), so that `cases:` does not pull in the
    `disclosed:` block added below — and vice versa."""
    entries = []
    cur = None
    in_block = False
    header_re = re.compile(r"^%s:\s*$" % re.escape(block))
    for line in raw.splitlines():
        if re.match(r"^\s*#", line) or not line.strip():
            continue
        if header_re.match(line):
            in_block = True
            continue
        if not in_block:
            continue
        if re.match(r"^\S", line):  # any top-level key (col 0) ends our block
            break
        m = re.match(r"^\s*-\s+(\w[\w-]*):\s*(.*)$", line)
        if m:
            if cur:
                entries.append(cur)
            cur = {}
            k, v = m.group(1), m.group(2)
            cur[k] = _clean_val(v)
            continue
        m = re.match(r"^\s+(\w[\w-]*):\s*(.*)$", line)
        if m and cur is not None:
            cur[m.group(1)] = _clean_val(m.group(2))
    if cur:
        entries.append(cur)
    return entries


def _clean_val(v):
    v = v.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    # strip an inline comment like "value  # comment" (2+ spaces before #) for unquoted
    v = re.sub(r"\s{2,}#.*$", "", v).strip()
    # inline list [a, b, c] → python list (disclosed: expected_generators)
    # TODO(fragile): the naive split(",") will break on an element with a comma inside quotes
    # (e.g. ["a, b", c]). Currently NOT triggered — all generator ids are comma-free. If
    # quoted elements with a comma are ever needed — replace with csv/shlex parsing.
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_clean_val(x) for x in inner.split(",")] if inner else []
    return v


# ---------- file-token extraction & matching ----------
def file_tokens(s):
    """Extract file tokens (basename and path tail) from bug_location / lead file."""
    s = s or ""
    s = s.split(":")[0] if re.search(r":\d", s) else s  # cut off :line
    toks = set()
    for m in re.findall(r"[\w./\\-]+\.(?:sol|rs|ts|tsx|js|go|cairo|move|fc|cpp|py)", s):
        toks.add(m.replace("\\", "/").lower())
        toks.add(os.path.basename(m).lower())
    # directory locators (templar/source/contract/proxy-oracle)
    for m in re.findall(r"[\w./\\-]*proxy-oracle[\w./\\-]*", s, re.I):
        toks.add(m.replace("\\", "/").lower())
    return toks


def lead_file(lead):
    if isinstance(lead, dict):
        return lead.get("file_line") or lead.get("file") or ""
    return str(lead)


def matches(lead_path, bug_location):
    lt = file_tokens(lead_path)
    bt = file_tokens(bug_location)
    if lt and bt:
        for a in lt:
            for b in bt:
                if a and b and (a in b or b in a):
                    return True
    # fallback: basename substring (for coarse locations like "src (... pin ...)")
    lp = (lead_path or "").lower()
    bl = (bug_location or "").lower()
    base = re.findall(r"[\w-]+\.(?:sol|rs|ts|tsx|js|go)", lp)
    return any(b in bl for b in base)


# ---------- commands ----------
def cmd_prepare():
    cases = load_manifest()
    os.makedirs(SNAP_DIR, exist_ok=True)
    ready, skipped, failed = [], [], []
    for c in cases:
        name = c.get("name", "?")
        ref = c.get("snapshot_ref", "manifest-only")
        if ref.startswith("local:"):
            path = os.path.join(SESSIONS, ref[len("local:"):])
            (ready if os.path.exists(path) else failed).append((name, ref))
        elif ref.startswith("git:"):
            spec = ref[len("git:"):]
            repo, _, commit = spec.partition("@")
            dest = os.path.join(SNAP_DIR, name)
            if os.path.exists(dest):
                ready.append((name, ref))
                continue
            url = repo if repo.startswith("http") else "https://github.com/%s" % repo
            try:
                subprocess.run(["git", "clone", "--depth", "50", url, dest],
                               check=True, capture_output=True, text=True)
                if commit:
                    subprocess.run(["git", "-C", dest, "checkout", commit],
                                   check=True, capture_output=True, text=True)
                ready.append((name, ref))
            except Exception as e:
                failed.append((name, "%s (%s)" % (ref, str(e)[:80])))
        else:
            skipped.append((name, ref))
    print("=== regression prepare ===")
    print("READY (%d):" % len(ready))
    for n, r in ready:
        print("  +", n, "—", r)
    print("SKIPPED manifest-only (%d):" % len(skipped))
    for n, r in skipped:
        print("  ·", n)
    if failed:
        print("FAILED (%d):" % len(failed))
        for n, r in failed:
            print("  !", n, "—", r)
    print("\nReproducible now: %d / %d cases." % (len(ready), len(cases)))


def cmd_score(leads_path, only_case=None):
    cases = load_manifest()
    if only_case:
        cases = [c for c in cases if c.get("name") == only_case]
        if not cases:
            print("No such case:", only_case)
            sys.exit(1)
    with open(leads_path, "r", encoding="utf-8") as f:
        blob = json.load(f)
    leads = blob.get("leads", blob if isinstance(blob, list) else [])
    lead_paths = [lead_file(x) for x in leads]

    per_case = []
    hit_leads = set()
    for c in cases:
        bl = c.get("bug_location", "")
        case_hits = [i for i, lp in enumerate(lead_paths) if matches(lp, bl)]
        per_case.append((c.get("name"), bool(case_hits)))
        hit_leads.update(case_hits)

    scored = len(cases)
    found = sum(1 for _, ok in per_case if ok)
    recall = found / scored if scored else 0.0
    precision = (len(hit_leads) / len(lead_paths)) if lead_paths else 0.0

    print("=== regression score ===")
    print("target:", blob.get("target", "?"), "| leads:", len(lead_paths))
    for name, ok in per_case:
        print("  %s %s" % ("[HIT]" if ok else "[miss]", name))
    print("recall    = %d/%d = %.2f" % (found, scored, recall))
    print("precision = %d/%d = %.2f (leads that landed on a known bug)" % (len(hit_leads), len(lead_paths), precision))

    rec = {
        "ts": int(time.time()),
        "type": "regression",
        "target": blob.get("target", "?"),
        "cases_scored": scored,
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "leads_total": len(lead_paths),
        "case_results": {n: ok for n, ok in per_case},
    }
    try:
        with open(CALIB, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("→ appended to", os.path.relpath(CALIB, ROOT))
    except Exception as e:
        print("WARN: could not write calibration_log:", e)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "prepare":
        cmd_prepare()
    elif cmd == "score":
        if len(sys.argv) < 3:
            print("Path to leads.json is required")
            sys.exit(1)
        only = None
        if "--case" in sys.argv:
            i = sys.argv.index("--case")
            only = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        cmd_score(sys.argv[2], only)
    else:
        print("Unknown command:", cmd, "\n", __doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
