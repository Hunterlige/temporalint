# temporalint

[![PyPI](https://img.shields.io/pypi/v/temporalint)](https://pypi.org/project/temporalint/)
[![License](https://img.shields.io/pypi/l/temporalint)](https://github.com/Hunterlige/temporalint/blob/main/LICENSE)
[![Python versions](https://img.shields.io/pypi/pyversions/temporalint)](https://pypi.org/project/temporalint/)
[![CI](https://github.com/Hunterlige/temporalint/actions/workflows/ci.yml/badge.svg)](https://github.com/Hunterlige/temporalint/actions)

Static checks for [Temporal](https://docs.temporal.io/) Python SDK code. Temporal's workflow APIs fail at runtime for mistakes Python will not catch: a missing activity timeout, a discarded coroutine, a workflow class the worker will reject, or a nondeterministic call that breaks replay.

> [!WARNING]
> This README was written by a human, but all code changes, PR summaries, and additional documentation were authored entirely by AI in Cursor.

## Install

```sh
pip install temporalint
```

## Usage

```sh
temporalint [paths...] [--select TPL001,TPL007] [--ignore TPL009]
```

## Rules

| ID | Name | Description |
| --- | --- | --- |
| TPL001 | activity-timeout | Activity call without `start_to_close_timeout` or `schedule_to_close_timeout`. |
| TPL002 | arg-and-args | Activity or child workflow call passing both `arg` and a non-empty `args`. |
| TPL003 | activity-unlimited-retry | Activity call whose retries are unbounded: no `maximum_attempts` in its `retry_policy` and no `schedule_to_close_timeout`. Off by default. |
| TPL004 | missing-heartbeat | Activity started with `heartbeat_timeout` whose same-module definition never calls `activity.heartbeat`. |
| TPL005 | workflow-defn-shape | `@workflow.defn` class without exactly one `async` `@workflow.run` method. |
| TPL006 | query-without-return | `@workflow.query` method that never returns a value. |
| TPL007 | missing-await | Async workflow API called without `await`. |
| TPL008 | nondeterministic-call | Nondeterministic call such as `datetime.now()`, `random.*`, or `uuid.uuid4()` in workflow code. |
| TPL009 | workflow-logger | `print` or `logging` in workflow code instead of `workflow.logger`. |
| TPL010 | workflow-exception | Workflow uses `assert` or raises an exception other than a Temporal failure such as `ApplicationError`. |


## Configuration

Settings can live in `temporalint.toml`, `.temporalint.toml`, or `pyproject.toml`. Discovery starts at the working directory and walks toward the filesystem root. In each directory, `temporalint.toml` wins over `.temporalint.toml`, which wins over `pyproject.toml`. Every rule except TPL003 is enabled when `select` and `ignore` are omitted. List TPL003 in `select` to turn it on.

`temporalint.toml` and `.temporalint.toml` put the keys at the top level:

```toml
select = ["TPL001", "TPL002", "TPL003", "TPL004", "TPL005", "TPL006", "TPL007", "TPL008", "TPL009", "TPL010"]
ignore = ["TPL009"]
exclude = ["tests/**", "**/migrations/**"]
```

The same settings in `pyproject.toml` sit under `[tool.temporalint]`:

```toml
[tool.temporalint]
select = ["TPL001", "TPL002", "TPL003", "TPL004", "TPL005", "TPL006", "TPL007", "TPL008", "TPL009", "TPL010"]
ignore = ["TPL009"]
exclude = ["tests/**", "**/migrations/**"]
```

`--select` and `--ignore` replace the corresponding config values when you pass them. `exclude` is a list of glob patterns matched against the path relative to the config file's directory. An explicit file argument is still linted when it matches an exclude pattern.

## Limitations

- Helper functions called from a workflow are not analyzed. Keep determinism-sensitive code in the workflow class, or review helpers separately.
- `from temporalio.workflow import *` and relative imports are not resolved.
- The timeout check looks for the keyword, not the value. `start_to_close_timeout=None` is not reported, and `**kwargs` suppresses TPL001.
- Argument counts, payload types, and activity names passed as strings are not checked yet.
- TPL004 only follows activities and helpers defined in the same module. It stays quiet when the activity has another decorator or calls an imported non-stdlib function or an unknown name, because those may heartbeat. Method calls on objects other than `self` are assumed not to heartbeat.
- TPL010 cannot see `workflow_failure_exception_types` on the worker. A type allowed only there is still reported.
