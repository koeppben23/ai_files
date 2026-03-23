from __future__ import annotations

from pathlib import Path

from scripts.legacy_surface_guard import scan_legacy_surface


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_legacy_surface_guard_happy_path(tmp_path: Path) -> None:
    _write(tmp_path / "cli" / "start.py", "import sys\nprint(sys.version)\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert violations == []


def test_legacy_surface_guard_bad_import_path(tmp_path: Path) -> None:
    _write(tmp_path / "cli" / "bootstrap.py", "from governance.entrypoints.bootstrap_executor import main\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert any("forbidden governance import" in item for item in violations)


def test_legacy_surface_guard_corner_allowed_archive_prefix(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "archive" / "legacy.md", "python -m governance.entrypoints.bootstrap_executor\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=("docs/archive/",))
    assert violations == []


def test_legacy_surface_guard_edge_large_tree_performance(tmp_path: Path) -> None:
    for idx in range(500):
        _write(tmp_path / "governance_content" / "docs" / f"doc-{idx}.md", "no legacy references here\n")
    _write(tmp_path / "scripts" / "build.py", "python -m governance.entrypoints.bootstrap_executor\n")

    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert len(violations) == 1


def test_legacy_surface_guard_blocks_legacy_path_literal(tmp_path: Path) -> None:
    _write(tmp_path / "cli" / "tool.py", "path = 'governance/entrypoints/bootstrap.py'\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert any("forbidden legacy path literal" in item for item in violations)


def test_legacy_surface_guard_allows_schema_identifiers(tmp_path: Path) -> None:
    _write(tmp_path / "governance_spec" / "rules.yml", "schema: governance.customer-script-catalog.v1\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert violations == []


def test_legacy_surface_guard_scans_top_level_install_py(tmp_path: Path) -> None:
    _write(tmp_path / "install.py", "from governance import GovernanceLayer\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert any(item.startswith("install.py:") and "forbidden governance import" in item for item in violations)


def test_legacy_surface_guard_blocks_write_text_outside_allowlist(tmp_path: Path) -> None:
    _write(tmp_path / "cli" / "tool.py", "Path('x').write_text('y')\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert any("disallowed write_text usage" in item for item in violations)


def test_legacy_surface_guard_allows_write_text_in_fs_atomic(tmp_path: Path) -> None:
    _write(tmp_path / "governance_runtime" / "infrastructure" / "fs_atomic.py", "Path('x').write_text('y')\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert not any("disallowed write_text usage" in item for item in violations)


def test_legacy_surface_guard_blocks_direct_env_access_in_restricted_layers(tmp_path: Path) -> None:
    _write(tmp_path / "governance_runtime" / "application" / "service.py", "import os\nvalue = os.environ.get('X')\n")
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert any("disallowed direct env access" in item for item in violations)


def test_legacy_surface_guard_blocks_repo_identity_resolve(tmp_path: Path) -> None:
    _write(
        tmp_path / "governance_runtime" / "application" / "repo_identity_service.py",
        "def f(p):\n    return p.resolve()\n",
    )
    violations = scan_legacy_surface(tmp_path, allowed_prefixes=())
    assert any("resolve() not allowed in repo identity flow" in item for item in violations)
