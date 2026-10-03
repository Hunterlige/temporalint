"""Walk a module and apply the enabled Temporal rules."""

import ast
from pathlib import Path

from temporalint.diagnostics import Diagnostic, is_suppressed
from temporalint.imports import ImportResolver
from temporalint.rules import (
    CALL_RULES,
    CLASS_RULES,
    EXPR_RULES,
    RULE_CODES,
    CheckContext,
    is_workflow_defn,
    module_classes,
)


def check_source(
    source: str,
    path: Path | None = None,
    enabled: set[str] | None = None,
) -> list[Diagnostic]:
    """Lint one module. Raises ``SyntaxError`` if the source does not parse."""
    if path is None:
        path = Path("example.py")
    tree = ast.parse(source)
    resolver = ImportResolver()
    resolver.collect(tree)
    context = CheckContext(
        path=path,
        resolver=resolver,
        in_workflow=False,
        enabled=RULE_CODES if enabled is None else enabled,
        diagnostics=[],
        classes=module_classes(tree),
    )
    Checker(context).visit(tree)
    lines = source.splitlines()
    diagnostics = [item for item in context.diagnostics if not is_suppressed(lines, item)]
    diagnostics.sort(key=lambda item: (item.line, item.col, item.code))
    return diagnostics


def check_file(path: Path, enabled: set[str] | None = None) -> list[Diagnostic]:
    source = path.read_text(encoding="utf-8")
    return check_source(source, path, enabled)


class Checker(ast.NodeVisitor):
    """Visit a module AST and apply the enabled rules."""

    def __init__(self, context: CheckContext) -> None:
        self.context = context
        self._workflow_depth = 0

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for rule in CLASS_RULES:
            rule(self.context, node)
        entered = is_workflow_defn(self.context.resolver, node)
        if entered:
            self._workflow_depth += 1
            self.context.in_workflow = True
        self.generic_visit(node)
        if entered:
            self._workflow_depth -= 1
            self.context.in_workflow = self._workflow_depth > 0

    def visit_Expr(self, node: ast.Expr) -> None:
        for rule in EXPR_RULES:
            rule(self.context, node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for rule in CALL_RULES:
            rule(self.context, node)
        self.generic_visit(node)
