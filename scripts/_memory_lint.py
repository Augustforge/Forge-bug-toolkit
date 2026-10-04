#!/usr/bin/env python3
"""Memory linter for the bug-bounty memory base.

Checks the personal memory dir (~/.claude/projects/.../memory) for:
  1. [[links]] that resolve to neither a memory file nor a toolkit file (DEAD)
  2. self-referential [[links]] (a file linking itself)
  3. MEMORY.md index drift (files not indexed / index entries with no file)

Run before ending a session:  py -3 -X utf8 scripts/_memory_lint.py
Exit 0 = clean, 1 = problems. Toolkit-file refs (e.g. [[stop_signals.md]]) are VALID and not flagged.
"""
import io, sys, re, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MEMDIR = os.path.expanduser(
    r"~/.claude/projects/c--Users--------------Desktop-Hackig-everything/memory")
# fallback to the known absolute path on this machine
if not os.path.isdir(MEMDIR):
    MEMDIR = r"<HOME>/.claude/projects/c--Users--------------Desktop-Hackig-everything/memory"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 

def norm(s): return s.replace('-', '').replace('_', '').replace('.md', '').lower()

files = [f for f in glob.glob(MEMDIR + "/*.md") if os.path.basename(f) != "MEMORY.md"]
mem_files = {os.path.splitext(os.path.basename(f))[0] for f in files}
toolkit = {norm(os.path.splitext(os.path.basename(f))[0])
           for f in glob.glob(ROOT + "/**/*.*", recursive=True)}

problems = []

# 1 + 2: link integrity
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    for l in set(re.findall(r'\[\[([^\]]+)\]\]', open(f, encoding='utf-8').read())):
        if l == stem:
            problems.append(f"SELF-LINK in {stem}.md: [[{l}]]")
        elif l in mem_files:
            continue                      # canonical memory link
        elif norm(l) in toolkit:
            continue                      # valid toolkit-file ref
        else:
            problems.append(f"DEAD link in {stem}.md: [[{l}]]")

# 3: MEMORY.md sync
idx = open(MEMDIR + "/MEMORY.md", encoding='utf-8').read()
idx_files = set(re.findall(r'\]\((\w[\w-]*)\.md\)', idx))
for x in sorted(mem_files - idx_files):
    problems.append(f"NOT in MEMORY.md index: {x}.md")
for x in sorted(idx_files - mem_files):
    problems.append(f"MEMORY.md index -> missing file: {x}.md")

print(f"memory files: {len(mem_files)}  |  indexed: {len(idx_files)}")
if problems:
    print(f"\nPROBLEMS ({len(problems)}):")
    for p in problems:
        print("  X", p)
    sys.exit(1)
print("ALL GREEN — memory base is clean.")
