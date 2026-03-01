"""Tests for scripts/migrate_rulebook_schema.py — migration framework and --check mode."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _import_migrate():
    """Import migrate_rulebook_schema.py as a module."""
    spec = importlib.util.spec_from_file_location(
        "migrate_rulebook_schema",
        str(REPO_ROOT / "scripts" / "migrate_rulebook_schema.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_schema(root: Path, version: str = "1.0.0") -> None:
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "schemas" / "rulebook.schema.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )


def _write_yml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _valid_yml(schema_version: str = "1.0.0") -> str:
    return (
        "kind: profile\n"
        "metadata:\n"
        "  id: profile.test\n"
        "  name: Test\n"
        "  version: '1.0'\n"
        f"  schema_version: '{schema_version}'\n"
        "  status: active\n"
    )


# ---------------------------------------------------------------------------
# check_all() — --check mode tests
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_check_all_passes_compatible_rulebooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--check returns 0 when all rulebooks have compatible schema_version."""
    mod = _import_migrate()
    fake_root = tmp_path / "repo"
    _write_schema(fake_root, "1.0.0")
    _write_yml(fake_root / "rulesets" / "profiles" / "a.yml", _valid_yml("1.0.0"))
    _write_yml(fake_root / "rulesets" / "profiles" / "b.yml", _valid_yml("1.2.0"))
    monkeypatch.setattr(mod, "ROOT", fake_root)

    assert mod.check_all() == 0


@pytest.mark.governance
def test_check_all_fails_missing_schema_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--check returns 1 when a rulebook is missing schema_version."""
    mod = _import_migrate()
    fake_root = tmp_path / "repo"
    _write_schema(fake_root, "1.0.0")
    _write_yml(
        fake_root / "rulesets" / "core" / "rules.yml",
        "kind: core\nmetadata:\n  id: core.rules\n  name: Core\n  version: '1.0'\n  status: active\n",
    )
    monkeypatch.setattr(mod, "ROOT", fake_root)

    assert mod.check_all() == 1


@pytest.mark.governance
def test_check_all_fails_major_version_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--check returns 1 when a rulebook has incompatible major version."""
    mod = _import_migrate()
    fake_root = tmp_path / "repo"
    _write_schema(fake_root, "1.0.0")
    _write_yml(fake_root / "rulesets" / "profiles" / "a.yml", _valid_yml("2.0.0"))
    monkeypatch.setattr(mod, "ROOT", fake_root)

    assert mod.check_all() == 1


@pytest.mark.governance
def test_check_all_fails_no_rulesets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--check returns 1 when rulesets directory is missing entirely."""
    mod = _import_migrate()
    fake_root = tmp_path / "repo"
    _write_schema(fake_root, "1.0.0")
    # No rulesets/ directory created
    monkeypatch.setattr(mod, "ROOT", fake_root)

    assert mod.check_all() == 1


# ---------------------------------------------------------------------------
# migrate_rulebook() — core migration logic
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_migrate_skips_missing_schema_version():
    """migrate_rulebook returns SKIP when schema_version is absent."""
    mod = _import_migrate()
    rb = {"kind": "profile", "metadata": {"id": "profile.test"}}
    result, log = mod.migrate_rulebook(rb, "2.0.0")
    assert result is rb  # unchanged
    assert any("SKIP" in msg for msg in log)


@pytest.mark.governance
def test_migrate_already_at_target():
    """migrate_rulebook returns 'already at' when versions match."""
    mod = _import_migrate()
    rb = {"kind": "profile", "metadata": {"schema_version": "1.0.0"}}
    result, log = mod.migrate_rulebook(rb, "1.0.0")
    assert result is rb
    assert any("already at 1.0.0" in msg for msg in log)


@pytest.mark.governance
def test_migrate_no_path_found():
    """migrate_rulebook returns ERROR when no migration path exists."""
    mod = _import_migrate()
    rb = {"kind": "profile", "metadata": {"schema_version": "1.0.0"}}
    result, log = mod.migrate_rulebook(rb, "99.0.0")
    assert result is rb  # unchanged
    assert any("ERROR" in msg and "no migration path" in msg for msg in log)


@pytest.mark.governance
def test_migrate_applies_registered_migration(monkeypatch: pytest.MonkeyPatch):
    """migrate_rulebook applies a registered migration step correctly."""
    mod = _import_migrate()

    def _fake_migration(rb: dict) -> dict:
        rb = dict(rb)
        rb["metadata"] = dict(rb["metadata"])
        rb["metadata"]["schema_version"] = "2.0.0"
        rb["_migrated"] = True
        return rb

    # Temporarily register a migration
    original_migrations = dict(mod.MIGRATIONS)
    mod.MIGRATIONS[("1.0.0", "2.0.0")] = _fake_migration
    try:
        rb = {"kind": "profile", "metadata": {"schema_version": "1.0.0"}}
        result, log = mod.migrate_rulebook(rb, "2.0.0")
        assert result["_migrated"] is True
        assert result["metadata"]["schema_version"] == "2.0.0"
        assert any("migrated 1.0.0 -> 2.0.0" in msg for msg in log)
    finally:
        mod.MIGRATIONS.clear()
        mod.MIGRATIONS.update(original_migrations)


# ---------------------------------------------------------------------------
# _find_migration_path() — BFS path finding
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_find_migration_path_empty_for_same_version():
    """BFS returns [] when from == to."""
    mod = _import_migrate()
    assert mod._find_migration_path("1.0.0", "1.0.0") == []


@pytest.mark.governance
def test_find_migration_path_empty_when_no_migrations():
    """BFS returns [] when no migrations are registered."""
    mod = _import_migrate()
    assert mod._find_migration_path("1.0.0", "2.0.0") == []


@pytest.mark.governance
def test_find_migration_path_multi_hop(monkeypatch: pytest.MonkeyPatch):
    """BFS finds a multi-hop path through registered migrations."""
    mod = _import_migrate()
    original_migrations = dict(mod.MIGRATIONS)
    mod.MIGRATIONS[("1.0.0", "1.1.0")] = lambda rb: rb
    mod.MIGRATIONS[("1.1.0", "2.0.0")] = lambda rb: rb
    try:
        path = mod._find_migration_path("1.0.0", "2.0.0")
        assert path == [("1.0.0", "1.1.0"), ("1.1.0", "2.0.0")]
    finally:
        mod.MIGRATIONS.clear()
        mod.MIGRATIONS.update(original_migrations)


# ---------------------------------------------------------------------------
# main() — CLI integration
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_main_check_mode_on_real_repo():
    """--check on the real repository passes (all rulebooks at schema_version 1.0.0)."""
    mod = _import_migrate()
    assert mod.main(["--check"]) == 0


@pytest.mark.governance
def test_main_dry_run_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--dry-run does not modify any files."""
    mod = _import_migrate()
    fake_root = tmp_path / "repo"
    _write_schema(fake_root, "1.0.0")
    yml_path = fake_root / "rulesets" / "profiles" / "a.yml"
    _write_yml(yml_path, _valid_yml("1.0.0"))
    original_content = yml_path.read_text()
    monkeypatch.setattr(mod, "ROOT", fake_root)

    # Even with a target, dry-run should not write (and no migration needed here)
    exit_code = mod.main(["--target-version", "1.0.0", "--dry-run"])
    assert exit_code == 0
    assert yml_path.read_text() == original_content


@pytest.mark.governance
def test_main_target_version_required_without_check():
    """main() errors when neither --check nor --target-version is provided."""
    mod = _import_migrate()
    # argparse should raise SystemExit(2) for missing required arg
    with pytest.raises(SystemExit) as exc_info:
        mod.main([])
    assert exc_info.value.code == 2
