"""Source scans for lint contracts that ruff cannot express."""

import re
from collections.abc import Iterable
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
