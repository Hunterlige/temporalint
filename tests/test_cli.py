"""The temporalint command-line interface."""

from pathlib import Path

import pytest

from temporalint.cli import main


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(source, encoding="utf-8")


BARE_ACTIVITY = "from temporalio import workflow\nawait workflow.execute_activity(greet)\n"


def test_reports_findings_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "workflow.py"
    _write(
        path,
        "from temporalio import workflow\nworkflow.execute_activity(greet)\n",
    )
    monkeypatch.chdir(tmp_path)
    assert main([str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        f"{path}:2:1: TPL001 execute_activity sets neither "
        + "start_to_close_timeout nor schedule_to_close_timeout",
        f"{path}:2:1: TPL002 execute_activity returns a coroutine that is not awaited",
    ]


def test_clean_file_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "ok.py"
    _write(path, "value = 1\n")
    monkeypatch.chdir(tmp_path)
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == ""


def test_syntax_error_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "bad.py"
    _write(path, "def (\n")
    monkeypatch.chdir(tmp_path)
    assert main([str(path)]) == 2
    assert "syntax error" in capsys.readouterr().err


def test_missing_path_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["does-not-exist.py"]) == 2
    assert "path not found" in capsys.readouterr().err


def test_unknown_rule_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--select", "NOPE"]) == 2
    assert "unknown rule code: NOPE" in capsys.readouterr().err


def test_usage_error_exits_2() -> None:
    with pytest.raises(SystemExit) as exc_info:
        _ = main(["--not-a-flag"])
    assert exc_info.value.code == 2


def test_select_and_ignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "workflow.py"
    _write(path, BARE_ACTIVITY)
    monkeypatch.chdir(tmp_path)
    assert main([str(path), "--ignore", "TPL001"]) == 0
    assert main([str(path), "--select", "TPL004"]) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        ("pyproject.toml", '[tool.temporalint]\nignore = ["TPL004"]\nexclude = ["skip/**"]\n'),
        ("temporalint.toml", 'ignore = ["TPL004"]\nexclude = ["skip/**"]\n'),
        (".temporalint.toml", 'ignore = ["TPL004"]\nexclude = ["skip/**"]\n'),
    ],
)
def test_config_ignore_exclude_and_explicit_file(
    filename: str,
    body: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path / filename, body)
    _write(tmp_path / "keep" / "workflow.py", BARE_ACTIVITY)
    _write(tmp_path / "skip" / "workflow.py", BARE_ACTIVITY)
    monkeypatch.chdir(tmp_path)

    assert main([]) == 1
    output = capsys.readouterr().out
    assert "keep/workflow.py:" in output
    assert "skip/workflow.py:" not in output

    assert main([str(tmp_path / "skip" / "workflow.py")]) == 1
    assert str(tmp_path / "skip" / "workflow.py") in capsys.readouterr().out


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        ("pyproject.toml", "[tool.temporalint]\nselect = 1\n"),
        ("temporalint.toml", "select = 1\n"),
    ],
)
def test_invalid_config_exits_2(
    filename: str,
    body: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path / filename, body)
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    assert "select must be an array of strings" in capsys.readouterr().err


def test_temporalint_toml_overrides_pyproject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path / "pyproject.toml", '[tool.temporalint]\nignore = ["TPL001"]\n')
    _write(tmp_path / "temporalint.toml", 'ignore = ["TPL001", "TPL002"]\n')
    _write(tmp_path / "workflow.py", BARE_ACTIVITY)
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert capsys.readouterr().out == ""
