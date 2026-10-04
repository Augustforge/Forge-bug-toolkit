#!/usr/bin/env python3
"""wave_delta.py — longitudinal re-scan / delta for a repeat visit to a target.

Idea (wave/delta, adapted to our single-target deep approach):
a target is NOT "looked at once — closed forever". Over time (new release / upgrade /
redeploy) we take a current fingerprint of the code, diff it against the previous
snapshot and hunt ONLY the delta. Change = risk: fresh/touched code is rawer than
battle-tested code.

Delta classes:
  NEW            — function appeared (was not in the snapshot) → virgin surface.
  REVERSED       — a guard was removed OR visibility/payable was widened
                   (internal→public, +payable) → a reopened hole. HIGHEST priority.
  REGRESSION     — a guard was added (patched here) → a bug almost certainly sat nearby.
  PERSISTENT     — untouched → already covered, skip.
  REMOVED        — function removed FROM THE SOURCE (informational) — BUT source != deploy:
                   `legacy_alive_check` (§43.7/§52, `legacy-alive` un-dup generator,
                   `blind_spots.md` "Un-dup Generators — Pool-Seed") reminds us that a function
                   gone from HEAD may still be ALIVE (an old implementation contract behind a
                   proxy, an under-deployed upgrade, an old version of the API/bundle) — removal
                   from src does NOT equal removal from the prod surface; check deploy/wayback
                   separately.

Fingerprint = { path::func -> {sig, guards[], visibility, mutability} } + meta.
Languages: Solidity (.sol, primary), Rust (.rs, Solana), generic fallback for the rest.

CLI:
  py -3 -X utf8 wave_delta.py snapshot <slug> --src <path> [--ref <note>]
  py -3 -X utf8 wave_delta.py delta    <slug> --src <path> [--save]
  py -3 -X utf8 wave_delta.py show     <slug>

<slug> → bug-bounty-toolkit/sessions/<slug>/snapshot.json
Fail-soft: diagnostics to stderr, but we don't crash the pipeline without need.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import datetime


GUARD_KEYWORDS = [
    "nonReentrant", "onlyOwner", "onlyRole", "onlyAdmin", "onlyGovernance",
    "onlyGovernor", "onlyManager", "onlyKeeper", "onlyOperator", "onlyMinter",
    "onlyController", "onlyVault", "onlySelf", "whenNotPaused", "whenPaused",
    "requiresAuth", "restricted", "initializer", "reinitializer", "authorized",
    "checkRole", "hasRole", "onlyProxy", "onlyDelegateCall", "onlyEOA",
    # Rust/Anchor-ish
    "access_control", "has_one", "constraint", "signer", "only_admin",
]
VIS = ["external", "public", "internal", "private"]
MUT = ["view", "pure", "payable", "nonpayable"]

SKIP_DIRS = {".git", "node_modules", "lib", "out", "cache", "artifacts",
             "test", "tests", "mock", "mocks", "script", "scripts",
             "target", "build", "dist", "coverage"}

SOL_FUNC = re.compile(
    r"function\s+([A-Za-z_]\w*)\s*\(([^)]*)\)([^{;]*)", re.S)
RUST_FN = re.compile(
    r"((?:#\[[^\]]*\]\s*)*)\bpub(?:\s*\([^)]*\))?\s+fn\s+([A-Za-z_]\w*)\s*"
    r"(?:<[^>]*>)?\s*\(([^)]*)\)", re.S)
GEN_FUNC = re.compile(
    r"(?:function|def|fn|func)\s+([A-Za-z_]\w*)\s*\(", re.S)

# web/API/bundle (§61) — reserved words that syntactically shadow the JS_FUNC method-shorthand
# alternative (`if (x) {`, `for (...) {` LOOK like `name(args) {`) and must never be captured
# as a function/method name.
_JS_KEYWORDS = (
    r"(?:if|for|while|switch|catch|do|with|else|function|return|typeof|new|"
    r"delete|in|of|instanceof|void|yield|await|case|try|finally)"
)
# JS/TS fingerprint branch. Three named forms, matched as alternatives (group numbers below
# are hard-coded pairs name/params per branch — see the dispatch in fingerprint()):
#   1/2 — function declarations: `function foo(...)`, `async function foo(...)`,
#         `function foo<T>(...)` (TS generic), plus optional `export`/`export default` prefix.
#   3/4 — arrow functions assigned to const/let/var: `const f = (a,b) => ...`,
#         `const f = async () => ...`, `const f = <T,>(x: T): T => ...` (TS generic, trailing-
#         comma disambiguation form), optional `export` prefix, optional `: Type` annotations.
#   5/6 — object/class methods: `foo(args) {`, `async foo(args) {`, with optional
#         public/private/protected/static/readonly/override/get/set modifiers and optional TS
#         generic (`foo<T>(x: T) {`). Guarded by `_JS_KEYWORDS` negative lookahead so control-flow
#         constructs that look identical (`if (x) {`) are never captured, and requires the `{`
#         (or `: ReturnType {`) to sit IMMEDIATELY after the closing paren — a bare call like
#         `doThing(a, b);` or a call nested inside a condition (`if (isReady()) {`) has an extra
#         trailing char before any `{`, so it never matches. `(?<![\w$])` pins the name to a real
#         identifier START — without it `for (...) {` still matches at its OWN start position ("or"
#         reads as a bare identifier once "for" is excluded, since the engine just retries one char
#         to the right).
JS_FUNC = re.compile(
    r"(?:export\s+(?:default\s+)?)?"
    r"(?:"
    r"(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
    r"|"
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)(?:\s*:\s*[^=]+?)?\s*=\s*(?:async\s+)?"
    r"(?:<[^,>]*,?\s*>\s*)?\(([^)]*)\)(?:\s*:\s*[^=]+?)?\s*=>"
    r"|"
    r"(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|override\s+)*"
    r"(?:async\s+)?(?:get\s+|set\s+)?(?<![\w$])(?!" + _JS_KEYWORDS + r"\b)"
    r"([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?::\s*[^{;=]+?)?\s*\{"
    r")",
    re.S,
)


def _strip_js_noise(code):
    """Blank out JS/TS comments and string/template-literal bodies (chars -> spaces, newlines
    kept) so JS_FUNC never matches text sitting inside a comment or a string literal (e.g. a
    string containing a literal `=>`). Runs before JS_FUNC.finditer()."""
    out = []
    i, n = 0, len(code)
    while i < n:
        two = code[i:i + 2]
        if two == "//":
            j = code.find("\n", i)
            j = n if j == -1 else j
            out.append(re.sub(r"[^\n]", " ", code[i:j]))
            i = j
        elif two == "/*":
            j = code.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(re.sub(r"[^\n]", " ", code[i:j]))
            i = j
        elif code[i] in ("'", '"', "`"):
            quote = code[i]
            j = i + 1
            while j < n:
                if code[j] == "\\":
                    j += 2
                    continue
                if code[j] == quote:
                    j += 1
                    break
                j += 1
            out.append(re.sub(r"[^\n]", " ", code[i:j]))
            i = j
        else:
            out.append(code[i])
            i += 1
    return "".join(out)


def _root():
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(here))  # scripts -> bug-bounty-toolkit


def _sess_dir(slug):
    return os.path.join(_root(), "sessions", slug)


def _snap_path(slug):
    return os.path.join(_sess_dir(slug), "snapshot.json")


def _observer_model(slug):
    """A4: the observer model, recorded by the entry hook in sessions/<slug>/.observer_model.
    Stamped into the snapshot so that on the next visit the entry-gate catches a model CHANGE
    (a new model sees what the old one missed). Fail-soft: no file → '' (no-op)."""
    try:
        p = os.path.join(_sess_dir(slug), ".observer_model")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.readline().strip()
    except Exception:
        pass
    return ""


def _guards_in(segment):
    seg = segment or ""
    return sorted({g for g in GUARD_KEYWORDS if re.search(r"\b" + re.escape(g) + r"\b", seg)})


def _vis(segment):
    for v in VIS:
        if re.search(r"\b" + v + r"\b", segment or ""):
            return v
    return ""


def _mut(segment):
    for m in MUT:
        if re.search(r"\b" + m + r"\b", segment or ""):
            return m
    return ""


def _walk(src):
    for dp, dns, fns in os.walk(src):
        dns[:] = [d for d in dns if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for fn in fns:
            yield os.path.join(dp, fn)


def fingerprint(src):
    """Build a fingerprint of a code directory."""
    funcs = {}
    n_files = 0
    for path in _walk(src):
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".sol", ".rs", ".vy", ".cairo", ".move", ".go",
                       ".js", ".ts", ".jsx", ".tsx"):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
        except Exception:
            continue
        n_files += 1
        rel = os.path.relpath(path, src).replace("\\", "/")
        seen = {}
        if ext == ".sol":
            for m in SOL_FUNC.finditer(code):
                name, params, tail = m.group(1), m.group(2), m.group(3)
                key = _key(rel, name, seen)
                funcs[key] = {
                    "sig": "%s(%s)" % (name, re.sub(r"\s+", " ", params).strip()),
                    "guards": _guards_in(tail),
                    "visibility": _vis(tail),
                    "mutability": _mut(tail),
                }
        elif ext == ".rs":
            for m in RUST_FN.finditer(code):
                attrs, name, params = m.group(1), m.group(2), m.group(3)
                key = _key(rel, name, seen)
                funcs[key] = {
                    "sig": "%s(%s)" % (name, re.sub(r"\s+", " ", params).strip()),
                    "guards": _guards_in(attrs),
                    "visibility": "pub",
                    "mutability": "",
                }
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            clean = _strip_js_noise(code)
            for m in JS_FUNC.finditer(clean):
                if m.group(1) is not None:
                    name, params = m.group(1), m.group(2)
                elif m.group(3) is not None:
                    name, params = m.group(3), m.group(4)
                else:
                    name, params = m.group(5), m.group(6)
                key = _key(rel, name, seen)
                funcs[key] = {
                    "sig": "%s(%s)" % (name, re.sub(r"\s+", " ", params or "").strip()),
                    "guards": [],
                    "visibility": "",
                    "mutability": "",
                }
        else:
            for m in GEN_FUNC.finditer(code):
                name = m.group(1)
                key = _key(rel, name, seen)
                funcs[key] = {"sig": name + "()", "guards": [], "visibility": "", "mutability": ""}
    return funcs, n_files


def _key(rel, name, seen):
    base = "%s::%s" % (rel, name)
    if base in seen:
        seen[base] += 1
        return "%s#%d" % (base, seen[base])
    seen[base] = 0
    return base


def _git_commit(src):
    try:
        out = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def build_snapshot(slug, src, ref="", model=""):
    funcs, n_files = fingerprint(src)
    # A4: model_version = who OBSERVED the target in this snapshot. An explicit --model wins,
    # otherwise take the one recorded by the entry hook (.observer_model). A change → re-audit window.
    model = model or _observer_model(slug)
    return {
        "meta": {
            "slug": slug,
            "src": os.path.abspath(src),
            "date": datetime.date.today().isoformat(),
            "git_commit": _git_commit(src),
            "ref": ref,
            "model_version": model,
            "n_files": n_files,
            "n_functions": len(funcs),
        },
        "functions": funcs,
    }


def write_snapshot(slug, snap):
    d = _sess_dir(slug)
    os.makedirs(d, exist_ok=True)
    with open(_snap_path(slug), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)


def compute_delta(old, new):
    of, nf = old.get("functions", {}), new.get("functions", {})
    ok, nk = set(of), set(nf)
    out = {"NEW": [], "REMOVED": [], "REVERSED": [], "REGRESSION": [], "PERSISTENT": 0}
    for k in sorted(nk - ok):
        out["NEW"].append({"fn": k, "sig": nf[k]["sig"], "guards": nf[k]["guards"],
                           "visibility": nf[k]["visibility"], "mutability": nf[k]["mutability"]})
    for k in sorted(ok - nk):
        # §43.7/§52 legacy-aware: removal from src does not equal removal from the deploy — a
        # signal field, not a file on disk (`legacy-alive` un-dup generator, blind_spots.md).
        out["REMOVED"].append({"fn": k, "sig": of[k]["sig"], "legacy_alive_check": True})
    vis_rank = {"private": 0, "internal": 1, "": 1, "public": 2, "external": 2, "pub": 2}
    for k in sorted(ok & nk):
        o, n = of[k], nf[k]
        og, ng = set(o.get("guards", [])), set(n.get("guards", []))
        dropped = sorted(og - ng)
        added = sorted(ng - og)
        widened = vis_rank.get(n.get("visibility", ""), 1) > vis_rank.get(o.get("visibility", ""), 1)
        payable_added = n.get("mutability") == "payable" and o.get("mutability") != "payable"
        if dropped or widened or payable_added:
            out["REVERSED"].append({
                "fn": k, "sig": n["sig"], "dropped_guards": dropped,
                "widened": ("%s→%s" % (o.get("visibility"), n.get("visibility"))) if widened else "",
                "payable_added": payable_added,
            })
        elif added:
            out["REGRESSION"].append({"fn": k, "sig": n["sig"], "added_guards": added})
        else:
            out["PERSISTENT"] += 1
    return out


def _print_delta(old, new, delta):
    om, nm = old.get("meta", {}), new.get("meta", {})
    print("=" * 70)
    print("WAVE/DELTA  %s" % nm.get("slug", ""))
    print("  snapshot : %s  commit %s" % (om.get("date"), (om.get("git_commit") or "-")[:12]))
    print("  current  : %s  commit %s" % (nm.get("date"), (nm.get("git_commit") or "-")[:12]))
    print("  funcs    : %d → %d" % (om.get("n_functions", 0), nm.get("n_functions", 0)))
    print("=" * 70)

    def block(tag, items, prio):
        print("\n[%s] %s — %d" % (prio, tag, len(items)))
        for it in items[:60]:
            extra = ""
            if tag == "REVERSED":
                bits = []
                if it["dropped_guards"]:
                    bits.append("dropped:" + ",".join(it["dropped_guards"]))
                if it["widened"]:
                    bits.append("vis:" + it["widened"])
                if it["payable_added"]:
                    bits.append("+payable")
                extra = "  <<< " + " | ".join(bits)
            elif tag == "REGRESSION":
                extra = "  added:" + ",".join(it["added_guards"])
            elif tag == "NEW":
                g = ("[" + ",".join(it["guards"]) + "]") if it["guards"] else "[NO-GUARD]"
                extra = "  %s %s %s" % (it["visibility"], it["mutability"], g)
            print("  - %s%s" % (it.get("fn", ""), extra))
        if len(items) > 60:
            print("  ... +%d more" % (len(items) - 60))

    block("REVERSED", delta["REVERSED"], "P0")   # highest — reopened holes
    block("NEW", delta["NEW"], "P1")             # fresh surface
    block("REGRESSION", delta["REGRESSION"], "P2")  # patched → dig adjacent
    block("REMOVED", delta["REMOVED"], "P3")
    if delta["REMOVED"]:
        print("  → legacy-alive (§43.7): removed from HEAD != removed from the deploy — check "
              "whether an old impl behind a proxy / an old API version / a wayback bundle is still "
              "alive before writing it off.")
    print("\n[skip] PERSISTENT (unchanged) — %d" % delta["PERSISTENT"])
    print("\n→ H-NN: REVERSED and NEW-without-guard into Active with HIGHEST priority; "
          "REGRESSION → dig nearby; PERSISTENT → already covered.")


def cmd_snapshot(a):
    snap = build_snapshot(a.slug, a.src, a.ref, getattr(a, "model", ""))
    write_snapshot(a.slug, snap)
    print("snapshot → %s  (%d files, %d funcs, commit %s)" % (
        _snap_path(a.slug), snap["meta"]["n_files"], snap["meta"]["n_functions"],
        (snap["meta"]["git_commit"] or "-")[:12]))


def cmd_delta(a):
    sp = _snap_path(a.slug)
    if not os.path.exists(sp):
        print("NO snapshot (%s) — this is the first visit. First: snapshot." % sp, file=sys.stderr)
        sys.exit(2)
    with open(sp, "r", encoding="utf-8") as f:
        old = json.load(f)
    new = build_snapshot(a.slug, a.src, a.ref)
    delta = compute_delta(old, new)
    _print_delta(old, new, delta)
    if a.save:
        write_snapshot(a.slug, new)
        print("\nsnapshot updated (--save).")


def cmd_show(a):
    sp = _snap_path(a.slug)
    if not os.path.exists(sp):
        print("no snapshot: %s" % sp, file=sys.stderr)
        sys.exit(2)
    with open(sp, "r", encoding="utf-8") as f:
        snap = json.load(f)
    print(json.dumps(snap["meta"], indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="longitudinal wave/delta re-scan")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("snapshot", cmd_snapshot), ("delta", cmd_delta), ("show", cmd_show)):
        sp = sub.add_parser(name)
        sp.add_argument("slug")
        if name != "show":
            sp.add_argument("--src", required=True, help="path to the repo/sources")
            sp.add_argument("--ref", default="", help="version label (tag/release/note)")
        if name == "snapshot":
            sp.add_argument("--model", default="",
                            help="observer model (A4; otherwise from .observer_model)")
        if name == "delta":
            sp.add_argument("--save", action="store_true", help="update the snapshot after the delta")
        sp.set_defaults(func=fn)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
