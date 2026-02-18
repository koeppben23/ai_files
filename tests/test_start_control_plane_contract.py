from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
START_PREFLIGHT = REPO_ROOT / "diagnostics" / "start_preflight_persistence.py"


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
def test_start_preflight_routes_identity_through_core_use_case_only():
    tree = ast.parse(START_PREFLIGHT.read_text(encoding="utf-8"))
    bootstrap_calls = _function_calls(tree, "bootstrap_identity_if_needed")
    run_calls = _function_calls(tree, "run_persistence_hook")

    assert "evaluate_start_identity" in bootstrap_calls
    assert "evaluate_start_identity" in run_calls

    forbidden = {
        "derive_repo_fingerprint",
        "read_repo_context_fingerprint",
        "pointer_fingerprint",
        "resolve_repo_context",
    }
    assert not (bootstrap_calls & forbidden), f"bootstrap_identity_if_needed bypasses core identity use-case: {bootstrap_calls & forbidden}"
    assert not (run_calls & forbidden), f"run_persistence_hook bypasses core identity use-case: {run_calls & forbidden}"
