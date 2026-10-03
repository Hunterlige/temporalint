"""Shared helpers for linting inline snippets."""

import textwrap
from pathlib import Path

from temporalint.checker import check_source
from temporalint.diagnostics import Diagnostic


def lint(source: str) -> list[Diagnostic]:
    return check_source(textwrap.dedent(source), Path("example.py"))


def hits(source: str) -> list[tuple[int, str]]:
    return [(diagnostic.line, diagnostic.code) for diagnostic in lint(source)]
