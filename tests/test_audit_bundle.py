"""Tests for audit bundle CLI."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import pytest


@pytest.mark.governance
class TestAuditBundle:
    def test_export_creates_bundle(self):
        from scripts.audit_bundle import export_bundle, _find_workspaces_home
        
        workspaces_home = _find_workspaces_home()
        
        # Find a run to export
        run_files = list(workspaces_home.glob("*/evidence/runs/*.json"))
        run_files = [f for f in run_files if f.name != "latest.json"]
        
        if not run_files:
            pytest.skip("No runs available to export")
        
        run_id = run_files[0].stem
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / f"bundle_{run_id}.zip"
            
            success, message = export_bundle(workspaces_home, run_id, output_path)
            
            assert success is True
            assert output_path.exists()
            
            # Verify bundle structure
            with zipfile.ZipFile(output_path, "r") as zf:
                assert "manifest.json" in zf.namelist()
                assert "run_summary.json" in zf.namelist()
                
                manifest_data = json.loads(zf.read("manifest.json"))
                assert manifest_data["run_id"] == run_id
                assert manifest_data["version"] == "1.0"
    
    def test_export_fails_for_nonexistent_run(self):
        from scripts.audit_bundle import export_bundle, _find_workspaces_home
        
        workspaces_home = _find_workspaces_home()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "bundle_nonexistent.zip"
            
            success, message = export_bundle(workspaces_home, "nonexistent-run-id", output_path)
            
            assert success is False
            assert "not found" in message.lower()
    
    def test_verify_valid_bundle(self):
        from scripts.audit_bundle import export_bundle, verify_bundle, _find_workspaces_home
        
        workspaces_home = _find_workspaces_home()
        
        # Create a valid bundle first
        run_files = list(workspaces_home.glob("*/evidence/runs/*.json"))
        run_files = [f for f in run_files if f.name != "latest.json"]
        
        if not run_files:
            pytest.skip("No runs available")
        
        run_id = run_files[0].stem
        
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "test_bundle.zip"
            
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
