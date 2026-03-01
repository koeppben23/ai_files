"""Tests for scripts/validate_rulebook.py — operator validation CLI."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_rulebook.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False, text=True, capture_output=True, cwd=str(REPO_ROOT),
    )


def _import_validate():
    spec = importlib.util.spec_from_file_location(
        "validate_rulebook", str(SCRIPT)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_yml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_schema(root: Path, version: str = "1.0.0") -> None:
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "schemas" / "rulebook.schema.json").write_text(
        json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "version": version,
            "type": "object",
            "required": ["kind", "metadata"],
            "additionalProperties": True,
            "properties": {
                "kind": {"type": "string", "enum": ["core", "profile"]},
                "metadata": {
                    "type": "object",
                    "required": ["id", "name", "version", "status", "schema_version"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "version": {"type": "string"},
                        "status": {"type": "string"},
                        "schema_version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
                    },
                },
            },
        }),
        encoding="utf-8",
    )


def _valid_yml(kind: str = "profile", schema_version: str = "1.0.0") -> str:
    return (
        f"kind: {kind}\n"
        "metadata:\n"
        f"  id: {kind}.test\n"
        "  name: Test\n"
        "  version: '1.0'\n"
        f"  schema_version: '{schema_version}'\n"
        "  status: active\n"
    )


# ---------------------------------------------------------------------------
# CLI integration tests (subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_validate_all_passes_on_real_repo():
    """--all on the real repo passes with exit 0."""
    result = _run(["--all"])
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK" in result.stdout
    assert "21 file(s)" in result.stdout


@pytest.mark.governance
def test_validate_single_valid_file():
    """Validating a single known-good file passes."""
    result = _run(["rulesets/core/rules.yml"])
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


@pytest.mark.governance
def test_validate_invalid_file(tmp_path: Path):
    """Validating a bad file returns exit 1 with clear errors."""
    bad = tmp_path / "bad.yml"
    bad.write_text("kind: 999\nmetadata:\n  id: bad\n", encoding="utf-8")
    result = _run([str(bad)])
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "FAILED" in result.stdout


@pytest.mark.governance
def test_validate_nonexistent_file():
    """Validating a nonexistent file reports file not found."""
    result = _run(["/nonexistent/path/foo.yml"])
    assert result.returncode == 1
    assert "File not found" in result.stdout or "not found" in result.stdout.lower()


@pytest.mark.governance
def test_validate_no_args_shows_error():
    """No files and no --all exits with code 2."""
    result = _run([])
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Unit-level tests (validate_file function)
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_validate_file_valid(tmp_path: Path):
    """validate_file returns empty list for a valid rulebook."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root)
    schema = json.loads((root / "schemas" / "rulebook.schema.json").read_text())

    yml = root / "test.yml"
    _write_yml(yml, _valid_yml())
    issues = mod.validate_file(yml, schema)
    assert issues == [], f"Expected no issues, got: {issues}"


@pytest.mark.governance
def test_validate_file_wrong_kind(tmp_path: Path):
    """validate_file catches wrong kind type."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root)
    schema = json.loads((root / "schemas" / "rulebook.schema.json").read_text())

    yml = root / "bad.yml"
    _write_yml(yml, "kind: 999\nmetadata:\n  id: core.test\n  name: Test\n  version: '1.0'\n  schema_version: '1.0.0'\n  status: active\n")
    issues = mod.validate_file(yml, schema)
    assert any("kind" in i for i in issues)


@pytest.mark.governance
def test_validate_file_missing_schema_version(tmp_path: Path):
    """validate_file catches missing schema_version."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root)
    schema = json.loads((root / "schemas" / "rulebook.schema.json").read_text())

    yml = root / "missing.yml"
    _write_yml(yml, "kind: profile\nmetadata:\n  id: profile.test\n  name: Test\n  version: '1.0'\n  status: active\n")
    issues = mod.validate_file(yml, schema)
    assert any("schema_version" in i for i in issues)


@pytest.mark.governance
def test_validate_file_major_version_mismatch(tmp_path: Path):
    """validate_file catches schema_version major mismatch."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root, version="1.0.0")
    schema = json.loads((root / "schemas" / "rulebook.schema.json").read_text())

    yml = root / "mismatch.yml"
    _write_yml(yml, _valid_yml(schema_version="2.0.0"))
    issues = mod.validate_file(yml, schema)
    assert any("incompatible major version" in i for i in issues)


@pytest.mark.governance
def test_validate_file_unparseable_yaml(tmp_path: Path):
    """validate_file catches unparseable YAML."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root)
    schema = json.loads((root / "schemas" / "rulebook.schema.json").read_text())

    yml = root / "broken.yml"
    _write_yml(yml, ":\n  - [\n  invalid: yaml: content\n")
    issues = mod.validate_file(yml, schema)
    assert any("parse error" in i.lower() or "failed" in i.lower() for i in issues)


@pytest.mark.governance
def test_validate_file_not_yaml_extension(tmp_path: Path):
    """validate_file rejects non-YAML files."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root)
    schema = json.loads((root / "schemas" / "rulebook.schema.json").read_text())

    txt = root / "readme.txt"
    _write_yml(txt, "kind: profile\n")
    issues = mod.validate_file(txt, schema)
    assert any("Not a YAML file" in i for i in issues)


@pytest.mark.governance
def test_validate_file_nonexistent(tmp_path: Path):
    """validate_file reports file not found."""
    mod = _import_validate()
    schema = {"type": "object"}
    issues = mod.validate_file(tmp_path / "nonexistent.yml", schema)
    assert any("not found" in i.lower() for i in issues)


# ---------------------------------------------------------------------------
# main() unit tests with --repo-root for isolation
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_main_all_in_isolated_repo(tmp_path: Path):
    """main --all --repo-root validates all YMLs in an isolated repo."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root)
    _write_yml(root / "rulesets" / "profiles" / "a.yml", _valid_yml())
    _write_yml(root / "rulesets" / "profiles" / "b.yml", _valid_yml())

    exit_code = mod.main(["--all", "--repo-root", str(root)])
    assert exit_code == 0


@pytest.mark.governance
def test_main_all_with_invalid_fails(tmp_path: Path):
    """main --all returns 1 when any file is invalid."""
    mod = _import_validate()
    root = tmp_path / "repo"
    _write_schema(root)
    _write_yml(root / "rulesets" / "profiles" / "good.yml", _valid_yml())
    _write_yml(root / "rulesets" / "profiles" / "bad.yml", "kind: 999\nmetadata: {}\n")

    exit_code = mod.main(["--all", "--repo-root", str(root)])
    assert exit_code == 1
