"""Resolve local names introduced by imports to qualified module paths.

Only module-level imports (including those nested in ``if`` / ``try`` / ``with``)
are tracked. Star imports and relative imports are ignored, because they cannot
be resolved without importing the module.
"""

import ast


class ImportResolver:
    """Map local names from module-level imports to qualified paths."""

    def __init__(self) -> None:
        self._bindings: dict[str, str] = {}

    def collect(self, tree: ast.AST) -> None:
        if isinstance(tree, ast.Module):
            for statement in tree.body:
                self._collect_statement(statement)

    def resolve(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return self._bindings.get(node.id)
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            if base is None:
                return None
            return f"{base}.{node.attr}"
        return None

    def _collect_statement(self, statement: ast.stmt) -> None:
        if isinstance(statement, ast.Import):
            self._add_import(statement)
        elif isinstance(statement, ast.ImportFrom):
            self._add_import_from(statement)
        elif isinstance(statement, ast.If):
            for child in (*statement.body, *statement.orelse):
                self._collect_statement(child)
        elif isinstance(statement, (ast.Try, ast.TryStar)):
            handlers: list[ast.stmt] = []
            for handler in statement.handlers:
                handlers.extend(handler.body)
            for child in (*statement.body, *handlers, *statement.orelse, *statement.finalbody):
                self._collect_statement(child)
        elif isinstance(statement, ast.With):
            for child in statement.body:
                self._collect_statement(child)

    def _add_import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self._bindings[alias.asname] = alias.name
            else:
                root = alias.name.split(".", 1)[0]
                self._bindings[root] = root

    def _add_import_from(self, node: ast.ImportFrom) -> None:
        if node.level or node.module is None:
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self._bindings[local] = f"{node.module}.{alias.name}"
