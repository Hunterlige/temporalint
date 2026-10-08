"""Load temporalint settings from the nearest config file.

Discovery walks from the start path toward the filesystem root. In each
directory the first existing file wins, in this order:

* ``temporalint.toml`` (settings at the top level)
* ``.temporalint.toml`` (same shape)
* ``pyproject.toml`` (``[tool.temporalint]``)
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from temporalint.rules import DEFAULT_CODES, RULE_CODES

_CONFIG_FILES = ("temporalint.toml", ".temporalint.toml", "pyproject.toml")


class ConfigError(Exception):
    """The project config or a CLI code list is not valid."""


@dataclass(frozen=True)
class Config:
    """Resolved temporalint settings for one project."""

    root: Path
    select: frozenset[str] | None = None
    ignore: frozenset[str] = frozenset()
    exclude: tuple[str, ...] = ()


def load_config(start: Path) -> Config:
    """Find the nearest temporalint config at or above ``start``."""
    current = start.resolve()
    if not current.is_dir():
        current = current.parent
    for directory in (current, *current.parents):
        for name in _CONFIG_FILES:
            candidate = directory / name
            if candidate.is_file():
                return _read_config(candidate)
    return Config(root=current)


def resolve_enabled(select: frozenset[str] | None, ignore: frozenset[str]) -> set[str]:
    enabled = set(DEFAULT_CODES) if select is None else set(select)
    unknown = (enabled | set(ignore)) - RULE_CODES
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"unknown rule code: {names}")
    return enabled - set(ignore)


def _read_config(path: Path) -> Config:
    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    data = _as_table(loaded, path, path.name)
    section = _settings(path, data)
    return Config(
        root=path.parent,
        select=_code_set(path, section.get("select"), "select", allow_missing=True),
        ignore=_code_set(path, section.get("ignore", []), "ignore") or frozenset(),
        exclude=_string_tuple(path, section.get("exclude", []), "exclude"),
    )


def _settings(path: Path, data: dict[str, object]) -> dict[str, object]:
    if path.name == "pyproject.toml":
        tool = _as_table(data.get("tool", {}), path, "[tool]")
        return _as_table(tool.get("temporalint", {}), path, "[tool.temporalint]")
    return data


def _as_table(value: object, path: Path, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: {label} must be a table")
    table: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            raise ConfigError(f"{path}: {label} keys must be strings")
        table[key] = item
    return table


def _code_set(
    path: Path,
    value: object,
    field: str,
    *,
    allow_missing: bool = False,
) -> frozenset[str] | None:
    if value is None and allow_missing:
        return None
    codes = _string_tuple(path, value, field)
    return frozenset(codes)


def _string_tuple(path: Path, value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{path}: {field} must be an array of strings")
    items: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ConfigError(f"{path}: {field} must be an array of strings")
        items.append(item)
    return tuple(items)
