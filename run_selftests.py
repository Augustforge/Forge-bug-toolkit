#!/usr/bin/env python3
"""Run the toolkit's self-test suite.

Each `*_selftest.py` is run from its own directory so the toolkit root is located
correctly and the toolkit-rooted-vs-CWD write checks hold. A small set of tests
exercises the private benchmark/calibration corpus (per-hunt calibration logs, the
regression manifest, model-eval data, production templates) that is intentionally
NOT shipped in the public release — those are reported as SKIPPED, not failed.

Usage:
    python run_selftests.py          # run everything
    python run_selftests.py -v       # also print each test's output

Exit code 0 if every non-skipped test passes.
"""
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# Self-tests that depend on the private benchmark/calibration corpus
# (sessions/_methodology/*), which is not part of the public release.
CORPUS_DEPENDENT = {
    "disclosed_corpus_selftest.py",
    "hunt_quality_score_selftest.py",
    "model_eval_reader_selftest.py",
    "yield_rollup_selftest.py",
}


def main():
    verbose = "-v" in sys.argv
    tests = sorted(glob.glob(os.path.join(ROOT, "**", "*_selftest.py"), recursive=True))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

    passed, skipped, failed = [], [], []
    for t in tests:
        name = os.path.basename(t)
        rel = os.path.relpath(t, ROOT).replace(os.sep, "/")
        r = subprocess.run([sys.executable, name], cwd=os.path.dirname(t),
                           env=env, capture_output=True, text=True)
        if r.returncode == 0:
            passed.append(rel)
            print(f"  PASS  {rel}")
        elif name in CORPUS_DEPENDENT:
            skipped.append(rel)
            print(f"  SKIP  {rel}  (needs the private benchmark corpus — not in the public release)")
        else:
            failed.append(rel)
            print(f"  FAIL  {rel}")
            for line in (r.stdout + r.stderr).strip().splitlines()[-8:]:
                print(f"        | {line}")
        if verbose and r.returncode == 0:
            for line in r.stdout.strip().splitlines()[-3:]:
                print(f"        | {line}")

    print(f"\n{len(passed)} passed, {len(skipped)} skipped, {len(failed)} failed "
          f"(of {len(tests)} self-tests)")
    if skipped:
        print("Skipped tests need the private benchmark corpus; everything else runs "
              "on a fresh clone.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
