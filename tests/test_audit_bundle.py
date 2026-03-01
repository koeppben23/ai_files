"""Tests for audit bundle CLI."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import pytest


def _create_synthetic_run(workspaces_home: Path) -> str:
    """Create a minimal synthetic run in the workspaces directory and return the run_id."""
    run_id = "synthetic-test-run-001"
    repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
    runs_dir = workspaces_home / repo_fp / "evidence" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_data = {
        "run_id": run_id,
        "status": "completed",
        "evidence_pointers": {},
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(run_data), encoding="utf-8")
    return run_id


@pytest.mark.governance
class TestAuditBundle:
    def test_export_creates_bundle(self, tmp_path: Path):
        from scripts.audit_bundle import export_bundle

        workspaces_home = tmp_path / "workspaces"
        run_id = _create_synthetic_run(workspaces_home)

        output_path = tmp_path / f"bundle_{run_id}.zip"

        success, message = export_bundle(workspaces_home, run_id, output_path)

        assert success is True, f"export_bundle failed: {message}"
        assert output_path.exists()

        # Verify bundle structure
        with zipfile.ZipFile(output_path, "r") as zf:
            assert "manifest.json" in zf.namelist()
            assert "run_summary.json" in zf.namelist()

            manifest_data = json.loads(zf.read("manifest.json"))
            assert manifest_data["run_id"] == run_id
            assert manifest_data["version"] == "1.0"

    def test_export_fails_for_nonexistent_run(self, tmp_path: Path):
        from scripts.audit_bundle import export_bundle

        workspaces_home = tmp_path / "workspaces"
        workspaces_home.mkdir(parents=True, exist_ok=True)

        output_path = tmp_path / "bundle_nonexistent.zip"

        success, message = export_bundle(workspaces_home, "nonexistent-run-id", output_path)

        assert success is False
        assert "not found" in message.lower()

    def test_verify_valid_bundle(self, tmp_path: Path):
        from scripts.audit_bundle import export_bundle, verify_bundle

        workspaces_home = tmp_path / "workspaces"
        run_id = _create_synthetic_run(workspaces_home)

        bundle_path = tmp_path / "test_bundle.zip"

        success, _ = export_bundle(workspaces_home, run_id, bundle_path)
        assert success

        valid, issues = verify_bundle(bundle_path)

        assert valid is True
        assert len(issues) == 0

    def test_verify_fails_for_missing_bundle(self):
        from scripts.audit_bundle import verify_bundle

        valid, issues = verify_bundle(Path("/nonexistent/bundle.zip"))

        assert valid is False
        assert any("not found" in i.lower() for i in issues)

    def test_verify_fails_for_missing_manifest(self):
        from scripts.audit_bundle import verify_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "bad_bundle.zip"

            # Create a zip without manifest
            with zipfile.ZipFile(bundle_path, "w") as zf:
                zf.writestr("dummy.json", "{}")

            valid, issues = verify_bundle(bundle_path)

            assert valid is False
            assert any("manifest" in i.lower() for i in issues)

    def test_verify_detects_hash_mismatch(self):
        from scripts.audit_bundle import verify_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "tampered_bundle.zip"

            # Create bundle with wrong hash
            manifest = {
                "version": "1.0",
                "run_id": "test",
                "files": {
                    "test.json": {
                        "hash": "wronghash123",
                        "source": "/path/to/test.json",
                    }
                },
            }

            with zipfile.ZipFile(bundle_path, "w") as zf:
                zf.writestr("manifest.json", json.dumps(manifest))
                zf.writestr("test.json", json.dumps({"data": "test"}))

            valid, issues = verify_bundle(bundle_path)

            assert valid is False
            assert any("Hash mismatch" in i for i in issues)
