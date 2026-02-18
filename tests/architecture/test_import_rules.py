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
    for file in _iter_python_files(presentation_root):
        imports = _imports(file)
        bad = sorted(i for i in imports if i.startswith("governance.infrastructure"))
        assert not bad, f"presentation imports infrastructure directly: {file}: {bad}"


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
