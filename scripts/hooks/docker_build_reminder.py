#!/usr/bin/env python3
"""PreToolUse hook — DOCKER-FIRST reminder for heavy builds.

Purpose: remove a recurring miss — an instance tries to build a heavy target
(submodule hell, forge build, recurse-clone) on NATIVE Windows and drowns in
yak-shaving (long-path limits, Cyrillic in the <HOME> path, submodule pinning
3-4 levels deep, remapping conflicts). The feedback_docker_for_builds memory
says "Docker bbt FIRST", but prose does not catch the moment.

Lesson of this system (brutecat / hunt_entry_gate): an in-prompt instruction is
not enough — you need a hook that catches the MOMENT of the command and injects
the reminder straight into context.

Mechanics (the operator's choice — a SOFT reminder, NOT a block):
  - PreToolUse on Bash/PowerShell.
  - Detect a heavy build command -> permissionDecision "allow" (the command runs) +
    additionalContext (I read the reminder and decide on my own to move to Docker).
  - Command already about docker -> no-op (already in a container).

Fail-open: any error -> exit 0 with no output (never break execution).
"""
import sys
import re
import json


# Heavy patterns that reliably break on native Windows.
HEAVY = [
    # recurse / depth clone breaks submodule pinning
    r"git\s+clone\b[^\n|;&]*--recurse-submodules",
    r"git\s+clone\b[^\n|;&]*--recursive",
    r"git\s+clone\b[^\n|;&]*--depth",
    # submodule init/update — the very 3-4-level bottom
    r"git\b[^\n|;&]*\bsubmodule\b",
    # foundry heavy subcommands (lightweight forge --version/fmt do NOT trigger)
    r"\bforge\s+(build|test|install|script|coverage|snapshot|verify-bytecode)\b",
]
HEAVY_RE = re.compile("|".join(HEAVY), re.I)

# If the command is already about docker, the build is ALREADY in a container; do not remind.
DOCKER_RE = re.compile(r"\bdocker\b", re.I)

REMINDER = (
    "DOCKER-FIRST (hook, feedback_docker_for_builds). This command (submodule / "
    "forge build / recurse-clone) reliably drowns in yak-shaving on NATIVE Windows: "
    "long-path limits, Cyrillic in the <HOME> path, submodule pinning "
    "3-4 levels deep, remapping conflicts (OZ v4 vs v5). Do NOT fight Windows. "
    "Run this build/clone INSIDE the `bbt` Docker image (docker/Dockerfile). "
    "Docker is usually NOT running — bring it up yourself: `docker build -t bbt -f docker/Dockerfile bug-bounty-toolkit` "
    "(if the image is missing), then `docker run --rm -v <repo>:/work -w /work bbt <command>`, "
    "mounting the repository into the container's Linux FS (NOT via a Windows path with Cyrillic). "
    "If the command is genuinely lightweight and Windows is fine here — ignore this and continue."
)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name") or ""
    if tool not in ("Bash", "PowerShell"):
        sys.exit(0)

    tin = data.get("tool_input") or {}
    cmd = tin.get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        sys.exit(0)

    try:
        if DOCKER_RE.search(cmd):
            sys.exit(0)  # already in docker
        if not HEAVY_RE.search(cmd):
            sys.exit(0)  # not a heavy command
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "additionalContext": REMINDER,
            }
        }))
    except Exception:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
