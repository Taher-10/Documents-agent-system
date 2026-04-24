from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_READ_METHODS = {"count", "scroll", "search", "query_points", "retrieve"}
ALLOWED_READ_CALLERS = {Path("ingestion/qhse_reader.py")}


def _module_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    modules: list[Path] = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if "tests" in rel.parts:
            continue
        if "__pycache__" in rel.parts:
            continue
        modules.append(path)
    return sorted(modules)


def _looks_like_qdrant_target(expr: ast.AST) -> bool:
    if isinstance(expr, ast.Name):
        return "qdrant" in expr.id.lower()
    if isinstance(expr, ast.Attribute):
        if "qdrant" in expr.attr.lower():
            return True
        return _looks_like_qdrant_target(expr.value)
    if isinstance(expr, ast.Call):
        if isinstance(expr.func, ast.Name) and "qdrant" in expr.func.id.lower():
            return True
        if isinstance(expr.func, ast.Attribute):
            return _looks_like_qdrant_target(expr.func)
    return "qdrant" in ast.unparse(expr).lower()


def test_qdrant_reads_are_guarded_by_qhse_reader() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []

    for module in _module_paths():
        rel = module.relative_to(root)
        if rel in ALLOWED_READ_CALLERS:
            continue

        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in FORBIDDEN_READ_METHODS:
                continue
            if not _looks_like_qdrant_target(node.func.value):
                continue

            target = ast.unparse(node.func.value)
            violations.append(f"{rel}:{node.lineno} uses '{target}.{node.func.attr}(...)'")

    assert not violations, (
        "Direct Qdrant read calls are forbidden outside "
        "agent_compliance/ingestion/qhse_reader.py:\n" + "\n".join(violations)
    )
