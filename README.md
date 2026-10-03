# temporalint

[![PyPI](https://img.shields.io/pypi/v/temporalint.svg)](https://pypi.org/project/temporalint/)
[![License](https://img.shields.io/pypi/l/temporalint.svg)](https://github.com/Hunterlige/temporalint/blob/main/LICENSE)
[![Python versions](https://img.shields.io/pypi/pyversions/temporalint.svg)](https://pypi.org/project/temporalint/)
[![CI](https://github.com/Hunterlige/temporalint/actions/workflows/ci.yml/badge.svg)](https://github.com/Hunterlige/temporalint/actions)

> [!WARNING]
> This README was written by a human, but all code changes, PR summaries, and additional documentation were authored entirely by AI in Cursor.

Static checks for [Temporal](https://docs.temporal.io/) Python SDK code. Temporal's workflow APIs fail at runtime for mistakes Python will not catch: a missing activity timeout, a discarded coroutine, a workflow class the worker will reject, or a nondeterministic call that breaks replay.

`temporalint` reports only patterns that are unambiguous. If it cannot resolve a call (a star import, a dot import, `**kwargs`, or a helper defined outside the workflow), it stays quiet.

The linter uses the standard library only. It does not import `temporalio` and does not run the code it checks.

## Install

```sh
pip install temporalint
```

## Usage

```sh
temporalint [paths...] [--select TPL001,TPL002] [--ignore TPL005]
```

Output is one finding per line:

```text
workflow.py:14:5: TPL001 execute_activity sets neither start_to_close_timeout nor schedule_to_close_timeout
```

## Rules

| Code | Name | What it flags |
| --- | --- | --- |
| TPL001 | activity-timeout | `execute_activity`, `start_activity`, `execute_local_activity`, `start_local_activity`, and their `_method` / `_class` variants, when neither `start_to_close_timeout` nor `schedule_to_close_timeout` is passed. The SDK raises `ValueError` at runtime. Calls that pass `**kwargs` are skipped, because the timeout may be in that mapping. |
| TPL002 | missing-await | A bare statement that calls `execute_activity*`, `execute_local_activity*`, `execute_child_workflow`, `start_child_workflow`, `sleep`, or `wait_condition` without `await`. The coroutine is discarded. `start_activity*` is not included. Assigning the call (`handle = workflow.execute_activity(...)`) is not reported. |
| TPL003 | workflow-defn-shape | A `@workflow.defn` class with zero `@workflow.run` methods, more than one, or a `@workflow.run` method that is not `async def`. The worker rejects these at registration. Decorators may be called (`@workflow.defn(name="...")`) or imported by name (`@defn`). |
| TPL004 | nondeterministic-call | Inside a `@workflow.defn` class: `datetime.now` / `utcnow` / `today`, `date.today`, `time.time` / `time_ns` / `monotonic` / `perf_counter`, any `random.*` call, `uuid.uuid1` / `uuid.uuid4`, `os.urandom`, and any `secrets.*` call. Use `workflow.now()`, `workflow.random()`, or `workflow.uuid4()`. |
| TPL005 | workflow-logger | Inside a `@workflow.defn` class: `print(...)`, `logging.debug` / `info` / `warning` / `warn` / `error` / `critical` / `exception` / `log` / `fatal`, and the same methods on a direct `logging.getLogger(...).info(...)` call. Use `workflow.logger`. A logger stored in a variable is not resolved. |
| TPL015 | arg-and-args | `execute_activity*`, `start_activity*`, `execute_local_activity*`, `start_local_activity*`, `execute_child_workflow`, or `start_child_workflow` passes both a single `arg` and a non-empty `args` sequence. The SDK raises `ValueError`. An empty literal `args` is valid. A non-literal `args` may be empty, so it is skipped. `**kwargs` skips the call. |
| TPL018 | workflow-exception | Inside a `@workflow.defn` class, a `raise` of an exception that does not extend `temporalio.exceptions.FailureError`, or an `assert`. The workflow task fails and retries until the execution timeout, which is unlimited by default, so the execution never fails. Raise `ApplicationError` to fail the execution. An imported type whose qualified name resolved, and that is not a Temporal failure or control-flow exception, is flagged. A same-module class is included when its bases are known and do not include a Temporal failure type, including `self.MyError()` or `Workflow.MyError()` for a class defined on the workflow. Not flagged: a `@workflow.query` method, an `@update.validator` (any exception rejects the update), a bare `raise`, a `raise` of a variable, a name that does not resolve, a same-module class with an unknown base, `ContinueAsNewError`, and `asyncio.CancelledError`. Also not flagged when `@workflow.defn(failure_exception_types=...)` lists that type or a base of it, including `Exception`. A type listed only on the worker's `workflow_failure_exception_types` is not visible and is still flagged. |

Workflow scope for TPL004 and TPL005 is the body of a `@workflow.defn` class, including nested functions and lambdas. Calls inside helpers defined outside that class are not inspected.

## Candidate rules

These are not implemented. Each one is a pattern the SDK rejects, or a default sandbox restriction, that is visible in the AST. A non-literal name, `**kwargs`, an unresolved import, or a helper defined outside the workflow class stays quiet.

### Extensions

| Rule | Also flag |
| --- | --- |
| TPL002 | A bare `workflow.wait(...)`. A bare `workflow.create_nexus_client(...).execute_operation(...)` or `.start_operation(...)`. A Nexus client stored in a variable is not resolved. `continue_as_new` is not a coroutine. |
| TPL004 | Inside a `@workflow.defn` class, the remaining default sandbox restrictions: `time.sleep`, `time.monotonic_ns`, `time.perf_counter_ns`, `time.process_time`, `time.process_time_ns`, `time.thread_time`, `time.thread_time_ns`, `time.localtime`, `time.tzset`, and `time.get_clock_info`; any `os` call other than `os.stat` and `os.path`; `open(...)` and `input(...)`; `asyncio.wait` and `asyncio.as_completed` (use `workflow.wait` and `workflow.as_completed`); any call on `threading`, `multiprocessing`, `subprocess`, `socket`, `tempfile`, `glob`, `locale`, `platform`, `concurrent.futures`, `http.client`, `http.server`, or `urllib.request`; and the filesystem methods on `pathlib.Path` (`cwd`, `home`, `exists`, `is_file`, `is_dir`, `iterdir`, `glob`, `rglob`, `resolve`, `stat`, `mkdir`, `open`, `read_text`, `read_bytes`, `write_text`, `write_bytes`, `unlink`, `rename`, and the other methods in the default sandbox matcher). `random.Random(...)` and `secrets.compare_digest` are allowed by the sandbox, so they are not candidates. |

### New rules

| Code | Name | What it would flag |
| --- | --- | --- |
| TPL006 | activity-keyword-only | An `@activity.defn` function with a keyword-only parameter. The SDK raises `TypeError` when the decorator runs. |
| TPL007 | dynamic-activity-signature | `@activity.defn(dynamic=True)` whose callable does not take exactly one argument annotated `Sequence[temporalio.common.RawValue]` (`self` plus that argument on a method). The SDK raises `TypeError`. Skip the check when `dynamic` is not a literal. |
| TPL008 | workflow-init | `@workflow.init` on a method other than `__init__`, or an `__init__` whose parameter list differs from `@workflow.run` in kind, order, defaults, or annotations. Parameter names are ignored. The SDK raises `ValueError`. |
| TPL009 | duplicate-handler | Two `@workflow.signal`, `@workflow.query`, or `@workflow.update` methods on one class with the same name. The name is the `name` string literal, or the method name when `name` is omitted. A second `dynamic=True` handler is a duplicate. Also flag a decorator call that passes both `name` and `dynamic`: the SDK raises `RuntimeError`. Skip a handler whose `name` is not a literal. |
| TPL010 | dynamic-handler-signature | `@workflow.defn(dynamic=True)` whose `@workflow.run` does not take a single `Sequence[temporalio.common.RawValue]`. A `dynamic=True` signal, query, or update whose parameters are not `(self, name: str, args: Sequence[temporalio.common.RawValue])`. A dynamic update that takes `*args` instead. The SDK raises `TypeError` or `RuntimeError`. The older `*args` form on a dynamic signal or query is only a deprecation warning, so it is not included. |
| TPL011 | dynamic-config | `@workflow.dynamic_config` that is `async def`, takes more than `self`, appears twice, or is used on a class that is not `@workflow.defn(dynamic=True)`. The SDK raises `ValueError`. |
| TPL012 | local-workflow-class | `@workflow.defn` on a class defined inside a function. The SDK raises `ValueError` because the class cannot be named for replay. |
| TPL013 | handler-override | A method that overrides a same-module base method decorated with `@workflow.signal`, `@workflow.query`, or `@workflow.update`, and the override omits that decorator. The SDK raises `ValueError`. An imported base is not inspected. A missing `@workflow.run` on the subclass is already TPL003. |
| TPL014 | duplicate-registration-name | Two `@workflow.defn` classes, or two `@activity.defn` callables, in the same module with the same registration name. The name is the `name` string literal, or the class or function name when `name` is omitted. `dynamic=True` has no name and is not part of this check. |
| TPL016 | query-workflow-call | Inside a `@workflow.query` method: `execute_activity*`, `start_activity*`, `execute_local_activity*`, `start_local_activity*`, `execute_child_workflow`, `start_child_workflow`, `sleep`, `wait_condition`, or `wait`. A query cannot schedule work or wait. `workflow.now()`, `workflow.random()`, and reads of workflow state are fine. An `async def` query with none of these calls is only a deprecation warning, so the `async def` itself is not flagged. |
| TPL017 | update-validator | An `@update.validator` method that is `async def`, whose parameter list differs from the update handler, or a second validator on the same update. The validator runs synchronously, must return `None`, and must match the handler's parameters apart from names. |

## Configuration

Settings can live in `temporalint.toml`, `.temporalint.toml`, or `pyproject.toml`. Discovery starts at the working directory and walks toward the filesystem root. In each directory, `temporalint.toml` wins over `.temporalint.toml`, which wins over `pyproject.toml`. Every rule is enabled when `select` and `ignore` are omitted.

`temporalint.toml` and `.temporalint.toml` put the keys at the top level:

```toml
select = ["TPL001", "TPL002", "TPL003", "TPL004", "TPL005", "TPL015", "TPL018"]
ignore = ["TPL005"]
exclude = ["tests/**", "**/migrations/**"]
```

The same settings in `pyproject.toml` sit under `[tool.temporalint]`:

```toml
[tool.temporalint]
select = ["TPL001", "TPL002", "TPL003", "TPL004", "TPL005", "TPL015", "TPL018"]
ignore = ["TPL005"]
exclude = ["tests/**", "**/migrations/**"]
```

`--select` and `--ignore` replace the corresponding config values when you pass them. `exclude` is a list of glob patterns matched against the path relative to the config file's directory. An explicit file argument is still linted when it matches an exclude pattern.

## Limitations

- Helper functions called from a workflow are not analyzed. Keep determinism-sensitive code in the workflow class, or review helpers separately.
- `from temporalio.workflow import *` and relative imports are not resolved.
- The timeout check looks for the keyword, not the value. `start_to_close_timeout=None` is not reported, and `**kwargs` suppresses TPL001.
- Argument counts, payload types, and activity names passed as strings are not checked yet.
- TPL018 cannot see `workflow_failure_exception_types` on the worker. A type allowed only there is still reported.
