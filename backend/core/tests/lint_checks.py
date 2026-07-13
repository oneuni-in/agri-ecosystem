"""Source scans for lint contracts that ruff cannot express."""

import re
from collections.abc import Container, Iterable
from pathlib import Path

# .offset( catches SQLAlchemy/queryset style; the uppercase word form catches
# raw SQL. Lowercase prose ("byte offset") stays legal.
_OFFSET_PATTERNS = (re.compile(r"\.offset\s*\("), re.compile(r"\bOFFSET\b"))


def check_offset_ban(paths: Iterable[Path]) -> list[str]:
    """Return 'file:line: source' for every banned OFFSET use under paths."""
    violations: list[str] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for file in files:
            for lineno, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if any(pattern.search(line) for pattern in _OFFSET_PATTERNS):
                    violations.append(f"{file}:{lineno}: {line.strip()}")
    return violations


# Two write shapes: ORM instantiation of the ledger model, and raw INSERT into
# the ledger table. The migration that CREATEs the table is exempt via `allow`.
_LEDGER_PATTERNS = (
    re.compile(r"\bLedgerEntry\s*\("),
    re.compile(r"INSERT\s+INTO\s+coins\.ledger_entries", re.IGNORECASE),
)


def check_ledger_writes(paths: Iterable[Path], *, allow: Container[Path]) -> list[str]:
    """Return 'file:line: source' for ledger writes outside allowlisted files."""
    violations: list[str] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        files += [] if root.is_file() else sorted(root.rglob("*.py.txt"))
        for file in files:
            if file in allow:
                continue
            for lineno, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if any(pattern.search(line) for pattern in _LEDGER_PATTERNS):
                    violations.append(f"{file}:{lineno}: {line.strip()}")
    return violations
