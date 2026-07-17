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


# Write shapes covered: ORM instantiation of the ledger model, raw INSERT into
# the ledger table, and the SQLAlchemy Core bypasses (insert()/bulk_insert_
# mappings()/bulk_save_objects() called directly against LedgerEntry). The
# migration that CREATEs the table is exempt via `allow`.
#
# Known limitation (accepted trade-off): these are regexes over source text,
# not an AST/import-aware check, so an aliased import - e.g.
# `from modules.coins.models import LedgerEntry as LE` followed by `LE(...)`
# or `insert(LE)` - is NOT caught. Closing that gap needs an AST walk that
# resolves the alias back to modules.coins.models.LedgerEntry, which is more
# machinery than this lint gate is worth; documented here instead.
_LEDGER_PATTERNS = (
    re.compile(r"\bLedgerEntry\s*\("),
    re.compile(r"INSERT\s+INTO\s+coins\.ledger_entries", re.IGNORECASE),
    re.compile(r"\binsert\s*\(\s*LedgerEntry\b"),
    re.compile(r"\bbulk_insert_mappings\s*\(\s*LedgerEntry\b"),
    re.compile(r"\bbulk_save_objects\s*\(\s*LedgerEntry\b"),
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


# Any PIL usage outside shared/media.py is a fork of the ONE media helper
# (Sprint-2 rule A5). Matches imports and direct calls; tests/fixtures are
# outside the scanned scope and may build images freely.
_MEDIA_FORK_PATTERNS = (
    re.compile(r"^\s*(from PIL|import PIL)\b"),
    re.compile(r"\bImage\.open\s*\("),
)


def check_media_fork(paths: Iterable[Path], *, allow: Container[Path]) -> list[str]:
    """Return 'file:line: source' for PIL use outside the shared media helper."""
    violations: list[str] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for file in files:
            if file in allow:
                continue
            for lineno, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if any(pattern.search(line) for pattern in _MEDIA_FORK_PATTERNS):
                    violations.append(f"{file}:{lineno}: {line.strip()}")
    return violations
