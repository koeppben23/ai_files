from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
START_PREFLIGHT = REPO_ROOT / "diagnostics" / "start_preflight_readonly.py"


def _function_calls(tree: ast.AST, function_name: str) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
    return calls


@pytest.mark.governance
def test_start_preflight_readonly_has_no_persistence_entrypoints():
    tree = ast.parse(START_PREFLIGHT.read_text(encoding="utf-8"))
    run_calls = _function_calls(tree, "run_persistence_hook")

    assert "commit_workspace_identity" not in run_calls
    assert "write_unresolved_runtime_context" not in run_calls

    forbidden = {
        "mkdir",
        "write_text",
        "open",
    }
    assert not (run_calls & forbidden), f"run_persistence_hook must remain read-only: {run_calls & forbidden}"
