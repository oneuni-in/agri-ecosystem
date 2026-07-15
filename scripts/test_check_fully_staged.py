#!/usr/bin/env python3
"""Self-contained test for check_fully_staged.py.
Run manually: python scripts/test_check_fully_staged.py

This test creates real AM-state files and verifies the check catches them.
"""

import subprocess
import sys
import tempfile
import os
from pathlib import Path


def run_check():
    """Run the check_fully_staged script and return exit code + output."""
    result = subprocess.run(
        [sys.executable, "scripts/check_fully_staged.py"],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_detects_am_state():
    """Test that the script detects staged-then-modified files."""
    print("Test 1: Detecting AM state (staged-then-modified)...")

    # Create a test file in docs
    test_file = Path("docs/superpowers/plans/2026-07-14-d14-sprint1-hardening.md")

    # Stage it
    subprocess.run(["git", "add", str(test_file)], check=True, capture_output=True)

    # Modify it further
    with open(test_file, "a") as f:
        f.write("\ntest modification\n")

    # Run the check
    exit_code, stdout, stderr = run_check()

    # Verify it caught the AM state
    assert exit_code == 1, f"Expected exit code 1, got {exit_code}"
    assert "STAGED-THEN-MODIFIED" in stdout, f"Expected warning in output, got: {stdout}"
    assert str(test_file) in stdout or "2026-07-14" in stdout, f"Expected file path in output, got: {stdout}"

    print(f"  [PASS] Script correctly detected AM state")
    print(f"    Output: {stdout.strip()}")

    # Clean up the test
    subprocess.run(["git", "checkout", "--", str(test_file)], check=True, capture_output=True)
    subprocess.run(["git", "reset", str(test_file)], check=True, capture_output=True)


def test_clean_state():
    """Test that the script passes on clean state."""
    print("Test 2: Clean state (no AM files)...")

    # Run the check
    exit_code, stdout, stderr = run_check()

    # Verify it passes
    assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
    assert "OK" in stdout, f"Expected OK message in output, got: {stdout}"

    print(f"  [PASS] Script correctly passed clean state")
    print(f"    Output: {stdout.strip()}")


if __name__ == "__main__":
    try:
        test_detects_am_state()
        test_clean_state()
        print("\n[PASS] All tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
