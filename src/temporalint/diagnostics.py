"""Diagnostics reported by temporalint."""

import re
from dataclasses import dataclass
from pathlib import Path

_NOQA_RE = re.compile(r"#\s*noqa\b(?::\s*([A-Za-z0-9_,\s]+))?")


@dataclass(frozen=True)
class Diagnostic:
    """One finding at a source location."""

    path: Path
    line: int
    col: int
    code: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.code} {self.message}"


def noqa_codes(line: str) -> set[str] | None:
    """Return the codes suppressed on this source line.

    ``None`` means the line has no noqa comment. An empty set means a bare
    ``# noqa``, which suppresses every code on the line.
    """
    match = _NOQA_RE.search(line)
    if match is None:
        return None
    if match.group(1) is None:
        return set()
    return {code.strip() for code in match.group(1).split(",") if code.strip()}


def is_suppressed(lines: list[str], diagnostic: Diagnostic) -> bool:
    if diagnostic.line < 1 or diagnostic.line > len(lines):
        return False
    codes = noqa_codes(lines[diagnostic.line - 1])
    if codes is None:
        return False
    return len(codes) == 0 or diagnostic.code in codes
