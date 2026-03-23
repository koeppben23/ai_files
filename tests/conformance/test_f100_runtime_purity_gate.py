from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = REPO_ROOT / "governance_runtime"


def _runtime_py_files() -> list[Path]:
    return sorted(RUNTIME_ROOT.rglob("*.py"))


def _runtime_launcher_files() -> list[Path]:
    patterns = ["*.sh", "*.cmd", "opencode-governance-bootstrap"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend((RUNTIME_ROOT / "bin").glob(pattern))
    return sorted(dict.fromkeys(files))


def _is_legacy_module(name: str | None) -> bool:
    token = str(name or "").strip()
    return token == "governance" or token.startswith("governance.")


def test_runtime_python_imports_do_not_depend_on_legacy_governance_package() -> None:
    violations: list[str] = []
    for path in _runtime_py_files():
        if path.as_posix().endswith("governance_runtime/install/install.py"):
            # Installer-core still imports the consolidated layer classifier API.
            # PR3 (installer single-source canonization) removes this exception.
            continue
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path}: syntax-error:{exc.lineno}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_legacy_module(alias.name):
                        violations.append(f"{path}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if _is_legacy_module(node.module):
                    violations.append(f"{path}:{node.lineno} from {node.module} import ...")

    assert not violations, "Runtime purity violation (legacy imports):\n" + "\n".join(violations)


def test_runtime_execution_paths_do_not_call_legacy_entrypoints() -> None:
    violations: list[str] = []
    py_files = _runtime_py_files()
    launcher_files = _runtime_launcher_files()

    for path in [*py_files, *launcher_files]:
        text = path.read_text(encoding="utf-8")
        if "-m governance.entrypoints." in text:
            violations.append(f"{path}: contains '-m governance.entrypoints.'")
        if "governance.entrypoints." in text:
            if path.as_posix().endswith("governance_runtime/infrastructure/io_verify.py"):
                # Compatibility verification may accept legacy provenance launcher
                # values from archived historical runs.
                pass
            else:
                violations.append(f"{path}: contains 'governance.entrypoints.'")
        if "importlib.import_module(\"governance." in text or "importlib.import_module('governance." in text:
            violations.append(f"{path}: contains dynamic legacy import")

    assert not violations, "Runtime execution purity violation:\n" + "\n".join(violations)
