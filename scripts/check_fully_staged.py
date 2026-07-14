#!/usr/bin/env python3
"""Fail if any tracked path is staged AND has further unstaged edits (AM
state in `git status --porcelain`). This is the exact failure class from the
D13 near-miss: content edited after `git add`, so the commit held a stale
version while the working tree (and CI) saw something else.

Run before every commit: python scripts/check_fully_staged.py
"""

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    bad = [
        line
        for line in result.stdout.splitlines()
        if len(line) >= 2 and line[0] != " " and line[0] != "?" and line[1] != " "
    ]
    if bad:
        print("STAGED-THEN-MODIFIED files found (git add again before committing):")
        for line in bad:
            print(f"  {line}")
        return 1
    print("check_fully_staged: OK — no staged-then-modified files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
