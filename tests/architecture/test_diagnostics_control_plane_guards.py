from __future__ import annotations

from pathlib import Path
import re
import ast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


DIAGNOSTICS_ROOT = REPO_ROOT / "diagnostics"
CRITICAL_FILES = (
    DIAGNOSTICS_ROOT / "start_preflight_readonly.py",
    DIAGNOSTICS_ROOT / "persist_workspace_artifacts.py",
    DIAGNOSTICS_ROOT / "bootstrap_session_state.py",
    DIAGNOSTICS_ROOT / "start_binding_evidence.py",
    DIAGNOSTICS_ROOT / "error_logs.py",
)


@pytest.mark.governance
def test_diagnostics_forbid_unresolved_workspace_writes():
    hits: list[str] = []
    for path in CRITICAL_FILES:
        text = path.read_text(encoding="utf-8")
        if "/_unresolved" in text or '"_unresolved/' in text or "'_unresolved/" in text:
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert not hits, f"diagnostics must not write unresolved workspace paths: {hits}"


@pytest.mark.governance
def test_diagnostics_forbid_shell_resplit_and_direct_write_calls():
    bad: list[str] = []
    pattern = re.compile(r"shlex\.split\(|\.write_text\(")
    for path in CRITICAL_FILES:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            bad.append(str(path.relative_to(REPO_ROOT)))
    assert not bad, f"diagnostics contain forbidden shell/direct-write patterns: {bad}"


@pytest.mark.governance
def test_diagnostics_forbid_write_primitives_outside_error_logger():
    allowed_open_writer = DIAGNOSTICS_ROOT / "error_logs.py"
    allowed_atomic_writers = {
        DIAGNOSTICS_ROOT / "error_logs.py",
        DIAGNOSTICS_ROOT / "bootstrap_session_state.py",
        DIAGNOSTICS_ROOT / "persist_workspace_artifacts.py",
    }
    bad: list[str] = []

    for path in CRITICAL_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func

            if isinstance(func, ast.Name) and func.id == "open":
                mode_literal = None
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    mode_literal = node.args[1].value
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        mode_literal = kw.value.value
                if mode_literal and any(flag in mode_literal for flag in ("w", "a", "x")) and path != allowed_open_writer:
                    bad.append(f"{path.relative_to(REPO_ROOT)}:L{getattr(node, 'lineno', 0)}")

            if isinstance(func, ast.Name) and func.id == "atomic_write_text" and path not in allowed_atomic_writers:
                bad.append(f"{path.relative_to(REPO_ROOT)}:L{getattr(node, 'lineno', 0)}")

    assert not bad, f"diagnostics write primitives only allowed in diagnostics/error_logs.py: {bad}"


@pytest.mark.governance
def test_error_logger_defaults_to_read_only_fail_closed():
    text = (DIAGNOSTICS_ROOT / "error_logs.py").read_text(encoding="utf-8")
    assert "OPENCODE_DIAGNOSTICS_ALLOW_WRITE\", \"0\"" in text
    assert 'return {"status": "read-only"}' in text


@pytest.mark.governance
def test_diagnostics_forbid_resolve_in_identity_binding_workspace_paths():
    bad: list[str] = []
    for path in CRITICAL_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "resolve":
                continue
            if isinstance(func.value, ast.Name) and func.value.id.endswith("resolver"):
                continue
            if isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id.endswith("Resolver"):
                continue
            bad.append(f"{path.relative_to(REPO_ROOT)}:L{getattr(node, 'lineno', 0)}")
    assert not bad, f"diagnostics contain forbidden Path.resolve usage: {bad}"
