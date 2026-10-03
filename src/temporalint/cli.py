"""Command-line interface for temporalint."""

# The CLI's job is to write diagnostics and errors to the terminal.
# ruff: noqa: T201

import argparse
import sys
from pathlib import Path, PurePosixPath

from temporalint.checker import check_file
from temporalint.config import Config, ConfigError, load_config, resolve_enabled
from temporalint.diagnostics import Diagnostic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="temporalint",
        description="Static checks for Temporal Python SDK usage.",
    )
    _ = parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to lint (default: the current directory)",
    )
    _ = parser.add_argument(
        "--select",
        help="Comma-separated rule codes to enable (default: all rules)",
    )
    _ = parser.add_argument(
        "--ignore",
        help="Comma-separated rule codes to disable",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(Path.cwd())
        select = _parse_codes(args.select) if args.select is not None else config.select
        ignore = _parse_codes(args.ignore) if args.ignore is not None else config.ignore
        enabled = resolve_enabled(select, ignore)
        files = collect_files([Path(path) for path in args.paths] or [Path()], config)
    except (ConfigError, FileNotFoundError, OSError) as exc:
        print(f"temporalint: {exc}", file=sys.stderr)
        return 2

    diagnostics: list[Diagnostic] = []
    syntax_errors = False
    for path in files:
        try:
            diagnostics.extend(check_file(path, enabled))
        except SyntaxError as exc:
            syntax_errors = True
            location = f"{path}:{exc.lineno or 1}:{exc.offset or 1}"
            print(f"{location}: syntax error: {exc.msg}", file=sys.stderr)
        except UnicodeDecodeError as exc:
            syntax_errors = True
            print(f"temporalint: {path}: {exc}", file=sys.stderr)

    for diagnostic in diagnostics:
        print(diagnostic.format())
    if syntax_errors:
        return 2
    return 1 if diagnostics else 0


def collect_files(paths: list[Path], config: Config) -> list[Path]:
    """Return Python files to lint.

    A file path is always included. Directory contents honor ``exclude``.
    """
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"path not found: {path}")
        if path.is_file():
            if path.suffix == ".py":
                files.append(path)
            continue
        if not path.is_dir():
            raise FileNotFoundError(f"path not found: {path}")
        for file in path.rglob("*.py"):
            if "__pycache__" in file.parts:
                continue
            if _is_excluded(file, config):
                continue
            files.append(file)
    return sorted(set(files))


def _parse_codes(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def _is_excluded(path: Path, config: Config) -> bool:
    if not config.exclude:
        return False
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(config.root.resolve()).as_posix()
    except ValueError:
        relative = resolved.as_posix()
    candidate = PurePosixPath(relative)
    return any(candidate.full_match(pattern) for pattern in config.exclude)
