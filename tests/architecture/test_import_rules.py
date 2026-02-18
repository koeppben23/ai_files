from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


_IO_MODULE_PREFIXES = {
    "os",
    "subprocess",
    "shutil",
    "tempfile",
    "pathlib",
}


def _iter_python_files(root: Path):
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
    return imported


def _forbidden_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        lineno = getattr(node, "lineno", 0)

        if isinstance(func, ast.Name):
            if func.id == "open":
                mode_arg = None
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    mode_arg = node.args[1].value
                if "mode" in {kw.arg for kw in node.keywords if kw.arg is not None}:
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            mode_arg = kw.value.value
                if mode_arg is not None and any(flag in mode_arg for flag in ("w", "a", "x")):
                    violations.append(f"L{lineno}:open_write_mode")

            if func.id == "Path" and any(
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "cwd"
                for arg in node.args
            ):
                violations.append(f"L{lineno}:Path.cwd")

        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                violations.append(f"L{lineno}:subprocess.{func.attr}")
            if isinstance(func.value, ast.Name) and func.value.id == "datetime" and func.attr in {"now", "utcnow"}:
                violations.append(f"L{lineno}:datetime.{func.attr}")
            if isinstance(func.value, ast.Name) and func.value.id == "Path" and func.attr == "cwd":
                violations.append(f"L{lineno}:Path.cwd")
            if func.attr in {"write_text", "resolve"}:
                violations.append(f"L{lineno}:Path.{func.attr}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr == "environ":
                lineno = getattr(node, "lineno", 0)
                violations.append(f"L{lineno}:os.environ")

    return sorted(set(violations))


@pytest.mark.governance
def test_domain_layer_has_no_direct_io_imports():
    domain_root = REPO_ROOT / "governance" / "domain"
    for file in _iter_python_files(domain_root):
        imports = _imports(file)
        bad = sorted(
            imp
            for imp in imports
            if any(imp == prefix or imp.startswith(prefix + ".") for prefix in _IO_MODULE_PREFIXES)
        )
        assert not bad, f"domain module imports io/os deps: {file}: {bad}"


@pytest.mark.governance
def test_presentation_layer_does_not_import_infrastructure():
    presentation_root = REPO_ROOT / "governance" / "presentation"
    forbidden_prefixes = (
        "governance.infrastructure",
        "governance.render",
        "governance.engine",
        "governance.context",
    )
    for file in _iter_python_files(presentation_root):
        imports = _imports(file)
        bad = sorted(i for i in imports if any(i.startswith(prefix) for prefix in forbidden_prefixes))
        assert not bad, f"presentation imports forbidden layers directly: {file}: {bad}"


@pytest.mark.governance
def test_application_layer_does_not_import_infrastructure():
    application_root = REPO_ROOT / "governance" / "application"
    for file in _iter_python_files(application_root):
        imports = _imports(file)
        bad = sorted(i for i in imports if i.startswith("governance.infrastructure"))
        assert not bad, f"application imports infrastructure directly: {file}: {bad}"


@pytest.mark.governance
def test_application_layer_does_not_import_legacy_engine_context_layers():
    application_root = REPO_ROOT / "governance" / "application"
    forbidden_prefixes = (
        "governance.engine",
        "governance.context",
        "governance.persistence",
        "governance.packs",
        "governance.render",
        "governance.presentation",
    )
    for file in _iter_python_files(application_root):
        imports = _imports(file)
        bad = sorted(i for i in imports if any(i.startswith(prefix) for prefix in forbidden_prefixes))
        assert not bad, f"application imports forbidden legacy layers: {file}: {bad}"


@pytest.mark.governance
def test_render_and_presentation_do_not_import_engine_context_or_infrastructure():
    roots = [REPO_ROOT / "governance" / "render", REPO_ROOT / "governance" / "presentation"]
    forbidden_prefixes = ("governance.engine", "governance.context", "governance.infrastructure")
    for root in roots:
        for file in _iter_python_files(root):
            imports = _imports(file)
            bad = sorted(i for i in imports if any(i.startswith(prefix) for prefix in forbidden_prefixes))
            assert not bad, f"presentation/render imports forbidden layers: {file}: {bad}"


@pytest.mark.governance
def test_domain_and_application_layers_forbid_side_effect_calls():
    roots = [REPO_ROOT / "governance" / "domain", REPO_ROOT / "governance" / "application"]
    violations: list[str] = []
    for root in roots:
        for file in _iter_python_files(root):
            bad_calls = _forbidden_calls(file)
            if bad_calls:
                violations.append(f"{file}: {bad_calls}")

    assert not violations, "forbidden side-effect calls detected in domain/application:\n" + "\n".join(violations)
