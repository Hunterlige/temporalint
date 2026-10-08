"""Deterministic checks for Temporal Python SDK usage.

Each rule reports only when the pattern is unambiguous. Calls that cannot be
resolved (dot imports, star imports, helpers defined elsewhere) are skipped.
"""

import ast
import builtins
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from temporalint.diagnostics import Diagnostic
from temporalint.imports import ImportResolver

WORKFLOW = "temporalio.workflow"
ACTIVITY = "temporalio.activity"
_RETRY_POLICY = "temporalio.common.RetryPolicy"
# Index of maximum_attempts among the positional RetryPolicy fields.
_MAX_ATTEMPTS_POSITION = 3

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

_ACTIVITY_FUNCS = {
    "execute_activity",
    "execute_activity_method",
    "execute_activity_class",
    "start_activity",
    "start_activity_method",
    "start_activity_class",
    "execute_local_activity",
    "execute_local_activity_method",
    "execute_local_activity_class",
    "start_local_activity",
    "start_local_activity_method",
    "start_local_activity_class",
}

# start_activity* returns a handle and is intentionally absent: a bare call is
# not the same mistake as discarding an activity result coroutine.
_AWAITED_FUNCS = {
    "execute_activity",
    "execute_activity_method",
    "execute_activity_class",
    "execute_local_activity",
    "execute_local_activity_method",
    "execute_local_activity_class",
    "execute_child_workflow",
    "start_child_workflow",
    "sleep",
    "wait_condition",
}

_NONDETERMINISTIC: dict[str, str] = {
    "datetime.datetime.now": "workflow.now()",
    "datetime.datetime.utcnow": "workflow.now()",
    "datetime.datetime.today": "workflow.now()",
    "datetime.date.today": "workflow.now()",
    "time.time": "workflow.now()",
    "time.time_ns": "workflow.now()",
    "time.monotonic": "workflow.now()",
    "time.perf_counter": "workflow.now()",
    "uuid.uuid1": "workflow.uuid4()",
    "uuid.uuid4": "workflow.uuid4()",
    "os.urandom": "workflow.random()",
}

_TIMEOUT_NAMES = {"start_to_close_timeout", "schedule_to_close_timeout"}

# args is keyword-only. A second positional is the single arg.
_ARG_AND_ARGS_FUNCS = _ACTIVITY_FUNCS | {
    "execute_child_workflow",
    "start_child_workflow",
}

# Local activities cannot heartbeat, so they take no heartbeat_timeout. The
# _class variants are skipped because the activity callable is not a plain def.
_HEARTBEAT_FUNCS = {
    "execute_activity",
    "execute_activity_method",
    "start_activity",
    "start_activity_method",
}


@dataclass(frozen=True)
class Rule:
    """A published temporalint check."""

    code: str
    name: str
    description: str
    default: bool = True


RULES: tuple[Rule, ...] = (
    Rule(
        "TPL001",
        "activity-timeout",
        "Activity calls need start_to_close_timeout or schedule_to_close_timeout.",
    ),
    Rule(
        "TPL002",
        "arg-and-args",
        "Activity and child-workflow calls cannot pass both arg and a non-empty args.",
    ),
    Rule(
        "TPL003",
        "activity-unlimited-retry",
        "Activity calls should bound retries with maximum_attempts or schedule_to_close_timeout.",
        default=False,
    ),
    Rule(
        "TPL004",
        "missing-heartbeat",
        "An activity started with heartbeat_timeout must call activity.heartbeat.",
    ),
    Rule(
        "TPL005",
        "workflow-defn-shape",
        "A @workflow.defn class needs exactly one async @workflow.run method.",
    ),
    Rule(
        "TPL006",
        "query-without-return",
        "A @workflow.query method must return a value.",
    ),
    Rule(
        "TPL007",
        "missing-await",
        "Async workflow APIs must be awaited.",
    ),
    Rule(
        "TPL008",
        "nondeterministic-call",
        "Workflow code must not call nondeterministic stdlib functions.",
    ),
    Rule(
        "TPL009",
        "workflow-logger",
        "Workflow code must log with workflow.logger, not print or logging.",
    ),
    Rule(
        "TPL010",
        "workflow-exception",
        "Workflow code must fail with ApplicationError, not a non-Temporal exception.",
    ),
)

RULE_CODES = {rule.code for rule in RULES}
DEFAULT_CODES = {rule.code for rule in RULES if rule.default}


def _empty_classes() -> dict[str, ast.ClassDef | None]:
    return {}


def _empty_functions() -> dict[str, FunctionNode | None]:
    return {}


@dataclass
class CheckContext:
    """State shared by rules while visiting one module."""

    path: Path
    resolver: ImportResolver
    in_workflow: bool
    enabled: set[str]
    diagnostics: list[Diagnostic]
    classes: dict[str, ast.ClassDef | None] = field(default_factory=_empty_classes)
    functions: dict[str, FunctionNode | None] = field(default_factory=_empty_functions)

    def report(self, node: ast.expr | ast.stmt, code: str, message: str) -> None:
        if code not in self.enabled:
            return
        self.diagnostics.append(
            Diagnostic(
                path=self.path,
                line=node.lineno,
                col=node.col_offset + 1,
                code=code,
                message=message,
            )
        )


RuleCheck = Callable[[CheckContext, ast.AST], None]


def _workflow_call_name(resolver: ImportResolver, node: ast.expr, names: set[str]) -> str | None:
    qualified = resolver.resolve(node)
    prefix = f"{WORKFLOW}."
    if qualified is None or not qualified.startswith(prefix):
        return None
    short = qualified.removeprefix(prefix)
    if short in names:
        return short
    return None


def _decorator_qualified(resolver: ImportResolver, decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return resolver.resolve(target)


def is_workflow_defn(resolver: ImportResolver, node: ast.AST) -> bool:
    return _has_decorator(resolver, node, f"{WORKFLOW}.defn")


def _has_decorator(resolver: ImportResolver, node: ast.AST, qualified: str) -> bool:
    decorators = getattr(node, "decorator_list", [])
    return any(_decorator_qualified(resolver, decorator) == qualified for decorator in decorators)


def _has_star_kwargs(node: ast.Call) -> bool:
    return any(keyword.arg is None for keyword in node.keywords)


def check_activity_timeout(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, ast.Call):
        return
    name = _workflow_call_name(ctx.resolver, node.func, _ACTIVITY_FUNCS)
    if name is None or _has_star_kwargs(node):
        return
    provided = {keyword.arg for keyword in node.keywords}
    if provided & _TIMEOUT_NAMES:
        return
    ctx.report(
        node,
        "TPL001",
        f"{name} sets neither start_to_close_timeout nor schedule_to_close_timeout",
    )


def _keyword_value(node: ast.Call, name: str) -> ast.expr | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _passes_single_arg(node: ast.Call) -> bool:
    # The first positional is the activity or workflow. A second one is arg.
    return bool(node.args[1:]) or _keyword_value(node, "arg") is not None


def _is_nonempty_sequence_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Tuple)):
        if any(isinstance(element, ast.Starred) for element in node.elts):
            return False
        return bool(node.elts)
    return (
        isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and bool(node.value)
    )


def check_arg_and_args(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, ast.Call):
        return
    name = _workflow_call_name(ctx.resolver, node.func, _ARG_AND_ARGS_FUNCS)
    if name is None or _has_star_kwargs(node) or not _passes_single_arg(node):
        return
    args_value = _keyword_value(node, "args")
    if args_value is None or not _is_nonempty_sequence_literal(args_value):
        return
    ctx.report(node, "TPL002", f"{name} passes both arg and a non-empty args")


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_unlimited_retry_policy(resolver: ImportResolver, node: ast.expr) -> bool:
    if _is_none(node):
        return True
    if not isinstance(node, ast.Call) or resolver.resolve(node.func) != _RETRY_POLICY:
        return False
    if _has_star_kwargs(node) or any(isinstance(arg, ast.Starred) for arg in node.args):
        return False
    attempts = (
        node.args[_MAX_ATTEMPTS_POSITION]
        if len(node.args) > _MAX_ATTEMPTS_POSITION
        else _keyword_value(node, "maximum_attempts")
    )
    if attempts is None:
        return True
    return (
        isinstance(attempts, ast.Constant) and type(attempts.value) is int and attempts.value == 0
    )


def check_activity_retry(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, ast.Call):
        return
    name = _workflow_call_name(ctx.resolver, node.func, _ACTIVITY_FUNCS)
    if name is None or _has_star_kwargs(node):
        return
    deadline = _keyword_value(node, "schedule_to_close_timeout")
    if deadline is not None and not _is_none(deadline):
        return
    policy = _keyword_value(node, "retry_policy")
    if policy is None:
        ctx.report(
            node,
            "TPL003",
            f"{name} sets no retry_policy; activities retry without limit by default",
        )
    elif _is_unlimited_retry_policy(ctx.resolver, policy):
        ctx.report(
            node,
            "TPL003",
            f"{name} retry_policy sets no maximum_attempts; the activity retries without limit",
        )


def _own_nodes(function: FunctionNode) -> Iterator[ast.AST]:
    pending: list[ast.AST] = list(function.body)
    while pending:
        current = pending.pop()
        yield current
        if not isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            pending.extend(ast.iter_child_nodes(current))


def _is_stub(body: list[ast.stmt]) -> bool:
    for statement in body:
        if isinstance(statement, (ast.Pass, ast.Raise)):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue
        return False
    return True


def check_query_return(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return
    if not _has_decorator(ctx.resolver, node, f"{WORKFLOW}.query") or _is_stub(node.body):
        return
    for child in _own_nodes(node):
        if isinstance(child, (ast.Yield, ast.YieldFrom)):
            return
        if isinstance(child, ast.Return) and child.value is not None and not _is_none(child.value):
            return
    ctx.report(node, "TPL006", f'query "{node.name}" returns no value')


def _class_method(definition: ast.ClassDef, name: str) -> FunctionNode | None:
    found = [
        statement
        for statement in definition.body
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name == name
    ]
    return found[0] if len(found) == 1 else None


def _activity_target(
    ctx: CheckContext, name: str, node: ast.Call
) -> tuple[FunctionNode, ast.ClassDef | None] | None:
    target = node.args[0] if node.args else _keyword_value(node, "activity")
    if name.endswith("_method"):
        if not isinstance(target, ast.Attribute) or not isinstance(target.value, ast.Name):
            return None
        if ctx.resolver.resolve(target.value) is not None:
            return None
        owner = ctx.classes.get(target.value.id)
        method = None if owner is None else _class_method(owner, target.attr)
        return None if method is None else (method, owner)
    if not isinstance(target, ast.Name) or ctx.resolver.resolve(target) is not None:
        return None
    function = ctx.functions.get(target.id)
    return None if function is None else (function, None)


def _call_heartbeats(
    ctx: CheckContext,
    func: ast.expr,
    owner: ast.ClassDef | None,
    nested: set[str],
    seen: set[int],
) -> bool | None:
    qualified = ctx.resolver.resolve(func)
    if qualified is not None:
        root = qualified.split(".", 1)[0]
        return False if root in sys.stdlib_module_names or root == "temporalio" else None
    if isinstance(func, ast.Name):
        if func.id in nested:
            return False
        local = ctx.functions.get(func.id)
        if local is not None:
            return _heartbeats(ctx, local, None, seen)
        if func.id in ctx.classes or func.id not in vars(builtins):
            return None
        return False
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Call):
            return None
        if isinstance(func.value, ast.Name) and func.value.id in {"self", "cls"} and owner:
            method = _class_method(owner, func.attr)
            return None if method is None else _heartbeats(ctx, method, owner, seen)
        # Methods on other objects are assumed not to heartbeat.
        return False
    return None


def _heartbeats(
    ctx: CheckContext, function: FunctionNode, owner: ast.ClassDef | None, seen: set[int]
) -> bool | None:
    if id(function) in seen:
        return False
    seen.add(id(function))
    nested = {
        child.name
        for child in ast.walk(function)
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not function
    }
    unknown = False
    for child in ast.walk(function):
        if (
            isinstance(child, (ast.Name, ast.Attribute))
            and ctx.resolver.resolve(child) == f"{ACTIVITY}.heartbeat"
        ):
            return True
        if not isinstance(child, ast.Call):
            continue
        result = _call_heartbeats(ctx, child.func, owner, nested, seen)
        if result:
            return True
        if result is None:
            unknown = True
    return None if unknown else False


def check_missing_heartbeat(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, ast.Call):
        return
    name = _workflow_call_name(ctx.resolver, node.func, _HEARTBEAT_FUNCS)
    if name is None:
        return
    timeout = _keyword_value(node, "heartbeat_timeout")
    if timeout is None or _is_none(timeout):
        return
    target = _activity_target(ctx, name, node)
    if target is None:
        return
    function, owner = target
    # Any other decorator, such as an auto-heartbeat wrapper, may heartbeat.
    decorators = function.decorator_list
    if (
        len(decorators) != 1
        or _decorator_qualified(ctx.resolver, decorators[0]) != f"{ACTIVITY}.defn"
    ):
        return
    if _heartbeats(ctx, function, owner, set()) is not False:
        return
    label = function.name if owner is None else f"{owner.name}.{function.name}"
    ctx.report(
        node,
        "TPL004",
        f'{name} sets heartbeat_timeout but activity "{label}" never calls activity.heartbeat',
    )


def check_missing_await(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return
    name = _workflow_call_name(ctx.resolver, node.value.func, _AWAITED_FUNCS)
    if name is None:
        return
    ctx.report(node.value, "TPL007", f"{name} returns a coroutine that is not awaited")


def check_workflow_defn_shape(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, ast.ClassDef):
        return
    if not _has_decorator(ctx.resolver, node, f"{WORKFLOW}.defn"):
        return
    run_methods = [
        statement
        for statement in node.body
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _has_decorator(ctx.resolver, statement, f"{WORKFLOW}.run")
    ]
    if len(run_methods) == 0:
        ctx.report(node, "TPL005", f'workflow class "{node.name}" has no @workflow.run method')
        return
    if len(run_methods) > 1:
        ctx.report(
            node,
            "TPL005",
            f'workflow class "{node.name}" has {len(run_methods)} @workflow.run methods, want exactly one',
        )
    for method in run_methods:
        if isinstance(method, ast.FunctionDef):
            ctx.report(
                method,
                "TPL005",
                f'@workflow.run method "{method.name}" of workflow class "{node.name}" must be async',
            )


def _nondeterministic_suggestion(qualified: str) -> str | None:
    if qualified in _NONDETERMINISTIC:
        return _NONDETERMINISTIC[qualified]
    if qualified == "random" or qualified.startswith("random."):
        return "workflow.random()"
    if qualified == "secrets" or qualified.startswith("secrets."):
        return "workflow.random()"
    return None


def check_nondeterministic_call(ctx: CheckContext, node: ast.AST) -> None:
    if not ctx.in_workflow or not isinstance(node, ast.Call):
        return
    qualified = ctx.resolver.resolve(node.func)
    if qualified is None:
        return
    suggestion = _nondeterministic_suggestion(qualified)
    if suggestion is None:
        return
    ctx.report(
        node,
        "TPL008",
        f"nondeterministic {qualified} in workflow code; use {suggestion}",
    )


_LOG_CALLS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "critical",
    "exception",
    "log",
    "fatal",
}


def _is_logging_call(resolver: ImportResolver, node: ast.Call) -> bool:
    qualified = resolver.resolve(node.func)
    if (
        qualified is not None
        and qualified.startswith("logging.")
        and qualified.removeprefix("logging.") in _LOG_CALLS
    ):
        return True
    func = node.func
    if (
        isinstance(func, ast.Attribute)
        and func.attr in _LOG_CALLS
        and isinstance(func.value, ast.Call)
    ):
        return resolver.resolve(func.value.func) == "logging.getLogger"
    return False


def check_workflow_logger(ctx: CheckContext, node: ast.AST) -> None:
    if not ctx.in_workflow or not isinstance(node, ast.Call):
        return
    if isinstance(node.func, ast.Name) and node.func.id == "print":
        if ctx.resolver.resolve(node.func) is None:
            ctx.report(node, "TPL009", "print in workflow code; use workflow.logger")
        return
    if _is_logging_call(ctx.resolver, node):
        ctx.report(node, "TPL009", "logging in workflow code; use workflow.logger")


# Builtin exception bases. IOError and EnvironmentError are OSError aliases.
_BUILTIN_BASES: dict[str, tuple[str, ...]] = {
    "ArithmeticError": ("Exception",),
    "AssertionError": ("Exception",),
    "AttributeError": ("Exception",),
    "BaseException": (),
    "BaseExceptionGroup": ("BaseException",),
    "BlockingIOError": ("OSError",),
    "BrokenPipeError": ("ConnectionError",),
    "BufferError": ("Exception",),
    "BytesWarning": ("Warning",),
    "ChildProcessError": ("OSError",),
    "ConnectionAbortedError": ("ConnectionError",),
    "ConnectionError": ("OSError",),
    "ConnectionRefusedError": ("ConnectionError",),
    "ConnectionResetError": ("ConnectionError",),
    "DeprecationWarning": ("Warning",),
    "EOFError": ("Exception",),
    "EncodingWarning": ("Warning",),
    "EnvironmentError": ("OSError",),
    "Exception": ("BaseException",),
    "ExceptionGroup": ("BaseExceptionGroup", "Exception"),
    "FileExistsError": ("OSError",),
    "FileNotFoundError": ("OSError",),
    "FloatingPointError": ("ArithmeticError",),
    "FutureWarning": ("Warning",),
    "GeneratorExit": ("BaseException",),
    "IOError": ("OSError",),
    "ImportError": ("Exception",),
    "ImportWarning": ("Warning",),
    "IndentationError": ("SyntaxError",),
    "IndexError": ("LookupError",),
    "InterruptedError": ("OSError",),
    "IsADirectoryError": ("OSError",),
    "KeyError": ("LookupError",),
    "KeyboardInterrupt": ("BaseException",),
    "LookupError": ("Exception",),
    "MemoryError": ("Exception",),
    "ModuleNotFoundError": ("ImportError",),
    "NameError": ("Exception",),
    "NotADirectoryError": ("OSError",),
    "NotImplementedError": ("RuntimeError",),
    "OSError": ("Exception",),
    "OverflowError": ("ArithmeticError",),
    "PendingDeprecationWarning": ("Warning",),
    "PermissionError": ("OSError",),
    "ProcessLookupError": ("OSError",),
    "PythonFinalizationError": ("RuntimeError",),
    "RecursionError": ("RuntimeError",),
    "ReferenceError": ("Exception",),
    "ResourceWarning": ("Warning",),
    "RuntimeError": ("Exception",),
    "RuntimeWarning": ("Warning",),
    "StopAsyncIteration": ("Exception",),
    "StopIteration": ("Exception",),
    "SyntaxError": ("Exception",),
    "SyntaxWarning": ("Warning",),
    "SystemError": ("Exception",),
    "SystemExit": ("BaseException",),
    "TabError": ("IndentationError",),
    "TimeoutError": ("OSError",),
    "TypeError": ("Exception",),
    "UnboundLocalError": ("NameError",),
    "UnicodeDecodeError": ("UnicodeError",),
    "UnicodeEncodeError": ("UnicodeError",),
    "UnicodeError": ("ValueError",),
    "UnicodeTranslateError": ("UnicodeError",),
    "UnicodeWarning": ("Warning",),
    "UserWarning": ("Warning",),
    "ValueError": ("Exception",),
    "Warning": ("Exception",),
    "ZeroDivisionError": ("ArithmeticError",),
    "_IncompleteInputError": ("SyntaxError",),
}

_FAILURE_SUBCLASSES = frozenset(
    {
        "WorkflowAlreadyStartedError",
        "ActivityAlreadyStartedError",
        "NexusOperationAlreadyStartedError",
        "ApplicationError",
        "CancelledError",
        "TerminatedError",
        "TimeoutError",
        "ServerError",
        "ActivityError",
        "ChildWorkflowError",
        "NexusOperationError",
    }
)

# Caught by the workflow runtime, so they do not fail the task.
_CONTROL_FLOW = frozenset(
    {
        "temporalio.workflow.ContinueAsNewError",
        "asyncio.CancelledError",
        "asyncio.exceptions.CancelledError",
    }
)

_EXTRA_BASES: dict[str, tuple[str, ...]] = {
    "temporalio.exceptions.TemporalError": ("builtins.Exception",),
    "temporalio.workflow.NondeterminismError": ("temporalio.exceptions.TemporalError",),
    "temporalio.workflow.ReadOnlyContextError": ("temporalio.exceptions.TemporalError",),
    "temporalio.workflow.ContinueAsNewError": ("builtins.BaseException",),
    "asyncio.CancelledError": ("builtins.BaseException",),
    "asyncio.exceptions.CancelledError": ("builtins.BaseException",),
}

_TEMPORAL_EXCEPTIONS = "temporalio.exceptions"


def module_classes(tree: ast.AST) -> dict[str, ast.ClassDef | None]:
    """Map module-level class names to their definitions.

    A name defined more than once maps to ``None`` so later checks stay quiet.
    """
    found: dict[str, ast.ClassDef | None] = {}
    if isinstance(tree, ast.Module):
        _collect_classes(tree.body, found)
    return found


def module_functions(tree: ast.AST) -> dict[str, FunctionNode | None]:
    found: dict[str, FunctionNode | None] = {}
    if isinstance(tree, ast.Module):
        _collect_functions(tree.body, found)
    return found


def _collect_functions(statements: list[ast.stmt], found: dict[str, FunctionNode | None]) -> None:
    for statement in statements:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[statement.name] = None if statement.name in found else statement
        else:
            for block in _nested_blocks(statement):
                _collect_functions(block, found)


def _collect_classes(
    statements: list[ast.stmt],
    found: dict[str, ast.ClassDef | None],
    prefix: str | None = None,
) -> None:
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            key = f"{prefix}.{statement.name}" if prefix else statement.name
            found[key] = None if key in found else statement
            _collect_classes(statement.body, found, key)
        else:
            for block in _nested_blocks(statement):
                _collect_classes(block, found, prefix)


def _nested_blocks(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return []
    if isinstance(statement, ast.If):
        return [statement.body, statement.orelse]
    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
        return [statement.body, statement.orelse]
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return [statement.body]
    if isinstance(statement, (ast.Try, ast.TryStar)):
        return [
            statement.body,
            statement.orelse,
            statement.finalbody,
            *[handler.body for handler in statement.handlers],
        ]
    if isinstance(statement, ast.Match):
        return [case.body for case in statement.cases]
    return []


def _local_key(ctx: CheckContext, name: str) -> str | None:
    if name not in ctx.classes:
        return None
    if ctx.classes[name] is None:
        return None
    return f"local:{name}"


def _type_key(
    ctx: CheckContext,
    expr: ast.expr,
    *,
    scope: str | None = None,
    instance_class: str | None = None,
) -> str | None:
    if isinstance(expr, ast.Name):
        # A name written in a class body can see an earlier class in that body.
        # A name written in a method cannot, so raises leave scope unset.
        if scope is not None and f"{scope}.{expr.id}" in ctx.classes:
            return _local_key(ctx, f"{scope}.{expr.id}")
        if expr.id in ctx.classes and ctx.classes[expr.id] is None:
            return None
        local = _local_key(ctx, expr.id)
        if local is not None:
            return local
        qualified = ctx.resolver.resolve(expr)
        if qualified is not None:
            return qualified
        if expr.id in _BUILTIN_BASES:
            return f"builtins.{expr.id}"
        return None
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        base = expr.value.id
        if base in {"self", "cls"} and instance_class is not None:
            base = instance_class
        local = _local_key(ctx, f"{base}.{expr.attr}")
        if local is not None:
            return local
    if isinstance(expr, ast.Attribute):
        return ctx.resolver.resolve(expr)
    return None


def _parents(ctx: CheckContext, key: str) -> tuple[str, ...] | None:
    extra = _EXTRA_BASES.get(key)
    if extra is not None:
        return extra
    if key.startswith("builtins."):
        bases = _BUILTIN_BASES.get(key.removeprefix("builtins."))
        if bases is None:
            return None
        return tuple(f"builtins.{base}" for base in bases)
    if key.startswith(f"{_TEMPORAL_EXCEPTIONS}."):
        name = key.removeprefix(f"{_TEMPORAL_EXCEPTIONS}.")
        if name in _FAILURE_SUBCLASSES:
            return (f"{_TEMPORAL_EXCEPTIONS}.FailureError",)
        if name == "FailureError":
            return (f"{_TEMPORAL_EXCEPTIONS}.TemporalError",)
        return None
    if key.startswith("local:"):
        name = key.removeprefix("local:")
        definition = ctx.classes.get(name)
        if not isinstance(definition, ast.ClassDef):
            return None
        scope = name.rsplit(".", 1)[0] if "." in name else None
        parents: list[str] = []
        for base in definition.bases:
            parent = _type_key(ctx, base, scope=scope)
            if parent is None:
                return None
            parents.append(parent)
        return tuple(parents)
    return None


def _is_failure_key(key: str) -> bool:
    prefix = f"{_TEMPORAL_EXCEPTIONS}."
    if not key.startswith(prefix):
        return False
    name = key.removeprefix(prefix)
    return name == "FailureError" or name in _FAILURE_SUBCLASSES


def _is_subclass(ctx: CheckContext, key: str, ancestor: str, visiting: set[str]) -> bool | None:
    if key == ancestor:
        return True
    if key in visiting:
        return False
    parents = _parents(ctx, key)
    if parents is None:
        return None
    visiting.add(key)
    unknown = False
    for parent in parents:
        result = _is_subclass(ctx, parent, ancestor, visiting)
        if result is True:
            visiting.remove(key)
            return True
        if result is None:
            unknown = True
    visiting.remove(key)
    if unknown:
        return None
    return False


def _is_exempt(ctx: CheckContext, key: str, visiting: set[str]) -> bool | None:
    if key in _CONTROL_FLOW or _is_failure_key(key):
        return True
    if not key.startswith("local:"):
        # A resolved qualified name is not a Temporal failure. Its bases are
        # not walked, so a same-module subclass of it stays unknown.
        return False
    if key in visiting:
        return None
    parents = _parents(ctx, key)
    if parents is None:
        return None
    visiting.add(key)
    unknown = False
    for parent in parents:
        result = _is_exempt(ctx, parent, visiting)
        if result is True:
            visiting.remove(key)
            return True
        if result is None or _parents(ctx, parent) is None:
            unknown = True
    visiting.remove(key)
    if unknown:
        return None
    return False


def _is_covered(ctx: CheckContext, key: str, allowed: frozenset[str]) -> bool | None:
    unknown = False
    for ancestor in allowed:
        result = _is_subclass(ctx, key, ancestor, set())
        if result is True:
            return True
        if result is None:
            unknown = True
    if unknown:
        return None
    return False


def _is_non_temporal(ctx: CheckContext, key: str, allowed: frozenset[str]) -> bool:
    exempt = _is_exempt(ctx, key, set())
    if exempt is None or exempt:
        return False
    return _is_covered(ctx, key, allowed) is False


def _parse_type_list(ctx: CheckContext, node: ast.expr) -> frozenset[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    keys: set[str] = set()
    for element in node.elts:
        if isinstance(element, ast.Starred):
            return None
        key = _type_key(ctx, element)
        if key is None:
            return None
        keys.add(key)
    return frozenset(keys)


def _configured_failure_types(ctx: CheckContext, node: ast.ClassDef) -> frozenset[str] | None:
    configured: frozenset[str] = frozenset()
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if _decorator_qualified(ctx.resolver, decorator) != f"{WORKFLOW}.defn":
            continue
        value = _keyword_value(decorator, "failure_exception_types")
        if value is None:
            continue
        parsed = _parse_type_list(ctx, value)
        if parsed is None:
            return None
        configured = parsed
    return configured


def _update_handler_names(resolver: ImportResolver, node: ast.ClassDef) -> frozenset[str]:
    names: set[str] = set()

    def visit(statements: list[ast.stmt]) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and _has_decorator(
                resolver, statement, f"{WORKFLOW}.update"
            ):
                names.add(statement.name)
            else:
                for block in _nested_blocks(statement):
                    visit(block)

    visit(node.body)
    return frozenset(names)


def _is_update_validator(
    node: ast.FunctionDef | ast.AsyncFunctionDef, handlers: frozenset[str]
) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "validator"
            and isinstance(target.value, ast.Name)
            and target.value.id in handlers
        ):
            return True
    return False


def _raised_type_expr(node: ast.Raise) -> ast.expr | None:
    exc = node.exc
    if isinstance(exc, ast.Call):
        return exc.func
    if isinstance(exc, (ast.Name, ast.Attribute)):
        return exc
    return None


def _exception_name(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return "exception"


class _WorkflowExceptionScanner(ast.NodeVisitor):
    def __init__(
        self,
        ctx: CheckContext,
        allowed: frozenset[str],
        handlers: frozenset[str],
        class_name: str,
    ) -> None:
        self._ctx = ctx
        self._allowed = allowed
        self._handlers = handlers
        self._class_stack = [class_name]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if is_workflow_defn(self._ctx.resolver, node):
            return
        self._class_stack.append(f"{self._class_stack[-1]}.{node.name}")
        self.generic_visit(node)
        del self._class_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if _has_decorator(self._ctx.resolver, node, f"{WORKFLOW}.query"):
            return
        if _is_update_validator(node, self._handlers):
            return
        for statement in node.body:
            self.visit(statement)

    def visit_Raise(self, node: ast.Raise) -> None:
        expr = _raised_type_expr(node)
        if expr is None:
            return
        key = _type_key(self._ctx, expr, instance_class=self._class_stack[-1])
        if key is None or not _is_non_temporal(self._ctx, key, self._allowed):
            return
        self._ctx.report(
            node,
            "TPL010",
            f"raise {_exception_name(expr)} in workflow code; "
            + "raise ApplicationError to fail the workflow",
        )

    def visit_Assert(self, node: ast.Assert) -> None:
        if not _is_non_temporal(self._ctx, "builtins.AssertionError", self._allowed):
            return
        self._ctx.report(
            node,
            "TPL010",
            "assert in workflow code raises AssertionError; "
            + "raise ApplicationError to fail the workflow",
        )


def check_workflow_exception(ctx: CheckContext, node: ast.AST) -> None:
    if not isinstance(node, ast.ClassDef) or not is_workflow_defn(ctx.resolver, node):
        return
    allowed = _configured_failure_types(ctx, node)
    if allowed is None:
        return
    scanner = _WorkflowExceptionScanner(
        ctx,
        allowed,
        _update_handler_names(ctx.resolver, node),
        node.name,
    )
    for statement in node.body:
        scanner.visit(statement)


CALL_RULES: tuple[RuleCheck, ...] = (
    check_activity_timeout,
    check_activity_retry,
    check_arg_and_args,
    check_missing_heartbeat,
    check_nondeterministic_call,
    check_workflow_logger,
)
EXPR_RULES: tuple[RuleCheck, ...] = (check_missing_await,)
FUNCTION_RULES: tuple[RuleCheck, ...] = (check_query_return,)
CLASS_RULES: tuple[RuleCheck, ...] = (check_workflow_defn_shape, check_workflow_exception)
