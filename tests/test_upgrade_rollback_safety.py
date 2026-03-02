"""Punkt 4 — Upgrade/Rollback safety tests.

Verifies:
  - Existing governance release artifacts remain loadable and structurally valid
  - Release artifact SHA256 hashes are self-consistent
  - Forward-incompatible schema_version changes are rejected by the build pipeline
  - migrate_rulebook_schema --check serves as a reliable CI gate
  - Newly built artifacts preserve backward-compatible structure
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_BUILD = REPO_ROOT / "scripts" / "build_ruleset_lock.py"
SCRIPT_MIGRATE = REPO_ROOT / "scripts" / "migrate_rulebook_schema.py"
GOVERNANCE_RELEASES = REPO_ROOT / "rulesets" / "governance"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _import_migrate():
    spec = importlib.util.spec_from_file_location(
        "migrate_rulebook_schema",
        str(REPO_ROOT / "scripts" / "migrate_rulebook_schema.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_build(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_BUILD), *args],
        check=False, text=True, capture_output=True, cwd=str(REPO_ROOT),
    )


def _run_migrate(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_MIGRATE), *args],
        check=False, text=True, capture_output=True, cwd=str(REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# 4a: Existing release artifacts remain loadable and hash-consistent
# ---------------------------------------------------------------------------

EXPECTED_VERSIONS = ["0.1.0", "0.2.0", "0.3.0", "0.4.0"]


@pytest.mark.governance
@pytest.mark.parametrize("version", EXPECTED_VERSIONS)
def test_release_artifact_structure_is_loadable(version: str):
    """Each release version has valid JSON manifest/lock/hashes files."""
    base = GOVERNANCE_RELEASES / version
    assert base.exists(), f"Release directory missing: {base}"

    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((base / "lock.json").read_text(encoding="utf-8"))
    hashes = json.loads((base / "hashes.json").read_text(encoding="utf-8"))

    assert manifest["schema"] == "governance-ruleset-manifest.v2"
    assert lock["schema"] == "governance-ruleset-lock.v2"
    assert lock["deterministic"] is True
    assert "ruleset_hash" in hashes


@pytest.mark.governance
@pytest.mark.parametrize("version", EXPECTED_VERSIONS)
def test_release_artifact_hashes_are_self_consistent(version: str):
    """SHA256 hashes in hashes.json match the actual file checksums."""
    base = GOVERNANCE_RELEASES / version
    hashes = json.loads((base / "hashes.json").read_text(encoding="utf-8"))

    actual_manifest_hash = _sha256(base / "manifest.json")
    actual_lock_hash = _sha256(base / "lock.json")

    assert hashes["manifest.json"] == actual_manifest_hash, (
        f"manifest.json hash mismatch in {version}"
    )
    assert hashes["lock.json"] == actual_lock_hash, (
        f"lock.json hash mismatch in {version}"
    )


@pytest.mark.governance
@pytest.mark.parametrize("version", EXPECTED_VERSIONS)
def test_release_artifact_source_files_are_consistent(version: str):
    """manifest.source_files count matches source_file_count."""
    base = GOVERNANCE_RELEASES / version
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((base / "lock.json").read_text(encoding="utf-8"))

    assert manifest["source_file_count"] == len(manifest["source_files"])
    assert lock["source_files"] == manifest["source_files"]


# ---------------------------------------------------------------------------
# 4b: Forward-incompatible schema versions rejected by build pipeline
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_build_rejects_future_schema_version_rulebook(tmp_path: Path):
    """Building against rulebooks targeting a future schema major version fails."""
    # Build an isolated repo where the schema is 1.0.0 but a rulebook says 2.0.0
    repo = tmp_path / "repo"
    (repo / "schemas").mkdir(parents=True)
    (repo / "schemas" / "rulebook.schema.json").write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "version": "1.0.0",
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
    }))

    (repo / "rulesets" / "core").mkdir(parents=True)
    (repo / "rulesets" / "core" / "rules.yml").write_text(
        "kind: core\nmetadata:\n  id: core.rules\n  name: Core\n"
        "  version: '1.0'\n  schema_version: '2.0.0'\n  status: active\n"
    )
    (repo / "rulesets" / "profiles").mkdir(parents=True)
    (repo / "rulesets" / "profiles" / "test.yml").write_text(
        "kind: profile\nmetadata:\n  id: profile.test\n  name: Test\n"
        "  version: '1.0'\n  schema_version: '2.0.0'\n  status: active\n"
    )
    (repo / "profiles" / "addons").mkdir(parents=True)
    (repo / "profiles" / "addons" / "test.addon.yml").write_text(
        "addon_key: testAddon\naddon_class: required\nmanifest_version: 1\n"
        "path_roots:\n  - src/test\nowns_surfaces:\n  - test\ntouches_surfaces:\n  - test\n"
    )

    result = _run_build([
        "--ruleset-id", "default", "--version", "1.0.0",
        "--repo-root", str(repo), "--output-root", str(tmp_path / "out"),
    ])
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert "schema_version mismatch" in payload["message"] or "major" in payload["message"].lower()


# ---------------------------------------------------------------------------
# 4c: migrate_rulebook_schema --check as CI gate
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_migrate_check_passes_on_current_repo():
    """--check on the real repo passes — all rulebooks compatible with current schema."""
    result = _run_migrate(["--check"])
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK" in result.stdout


@pytest.mark.governance
def test_migrate_check_detects_incompatible_rulebook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--check correctly reports incompatible rulebooks as a gate failure."""
    mod = _import_migrate()
    fake_root = tmp_path / "repo"
    (fake_root / "schemas").mkdir(parents=True)
    (fake_root / "schemas" / "rulebook.schema.json").write_text(
        json.dumps({"version": "1.0.0"}), encoding="utf-8"
    )

    (fake_root / "rulesets" / "profiles").mkdir(parents=True)
    (fake_root / "rulesets" / "profiles" / "bad.yml").write_text(
        "kind: profile\nmetadata:\n  id: profile.bad\n  name: Bad\n"
        "  version: '1.0'\n  schema_version: '2.0.0'\n  status: active\n"
    )
    monkeypatch.setattr(mod, "ROOT", fake_root)

    exit_code = mod.check_all()
    assert exit_code == 1, "Expected check_all to fail for incompatible rulebook"


@pytest.mark.governance
def test_migrate_check_detects_missing_schema_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--check correctly flags rulebooks missing schema_version."""
    mod = _import_migrate()
    fake_root = tmp_path / "repo"
    (fake_root / "schemas").mkdir(parents=True)
    (fake_root / "schemas" / "rulebook.schema.json").write_text(
        json.dumps({"version": "1.0.0"}), encoding="utf-8"
    )

    (fake_root / "rulesets" / "core").mkdir(parents=True)
    (fake_root / "rulesets" / "core" / "rules.yml").write_text(
        "kind: core\nmetadata:\n  id: core.rules\n  name: Core\n"
        "  version: '1.0'\n  status: active\n"
    )
    monkeypatch.setattr(mod, "ROOT", fake_root)

    exit_code = mod.check_all()
    assert exit_code == 1, "Expected check_all to fail for missing schema_version"


# ---------------------------------------------------------------------------
# New artifact builds preserve backward-compatible structure
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_new_build_produces_backward_compatible_artifact_structure(tmp_path: Path):
    """A fresh build produces artifacts with the same structural contract as existing releases."""
    out_root = tmp_path / "rulesets"
    result = _run_build([
        "--ruleset-id", "default",
        "--version", "99.0.0",
        "--output-root", str(out_root),
    ])
    assert result.returncode == 0, f"Build failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"

    base = out_root / "default" / "99.0.0"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((base / "lock.json").read_text(encoding="utf-8"))
    hashes = json.loads((base / "hashes.json").read_text(encoding="utf-8"))

    # Same structural contract as all existing releases
    assert manifest["schema"] == "governance-ruleset-manifest.v2"
    assert lock["schema"] == "governance-ruleset-lock.v2"
    assert lock["deterministic"] is True
    assert "ruleset_hash" in hashes
    assert hashes["manifest.json"] == _sha256(base / "manifest.json")
    assert hashes["lock.json"] == _sha256(base / "lock.json")
    assert manifest["source_file_count"] == len(manifest["source_files"])
    assert lock["source_files"] == manifest["source_files"]

    # New builds also include rulebook_schema_version (upgrade from older releases)
    assert "rulebook_schema_version" in manifest
    assert manifest["rulebook_schema_version"] == "1.1.0"
