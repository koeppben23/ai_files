"""Tests for verify_setup.py"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest


@pytest.mark.governance
class TestVerifySetup:
    def test_check_command_finds_git(self):
        from scripts.verify_setup import check_command
        
        passed, message = check_command("git")
        assert passed is True
        assert message != "not found"
    
    def test_check_command_missing(self):
        from scripts.verify_setup import check_command
        
        passed, message = check_command("nonexistent_command_xyz")
        assert passed is False
        assert message == "not found"
    
    def test_detect_profile_python(self):
        from scripts.verify_setup import detect_profile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "requirements.txt").touch()
            
            with mock.patch.object(Path, "cwd", return_value=tmpdir):
                profile = detect_profile()
                assert profile == "backend-python"
    
    def test_detect_profile_java(self):
        from scripts.verify_setup import detect_profile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "pom.xml").touch()
            
            with mock.patch.object(Path, "cwd", return_value=tmpdir):
                profile = detect_profile()
                assert profile == "backend-java"
    
    def test_detect_profile_fallback(self):
        from scripts.verify_setup import detect_profile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            with mock.patch.object(Path, "cwd", return_value=tmpdir):
                profile = detect_profile()
                assert profile == "fallback-minimum"
    
    def test_run_verification_returns_structure(self):
        from scripts.verify_setup import run_verification
        
        results = run_verification()
        
        assert "overall" in results
        assert "checks" in results
        assert "detected_profile" in results
        assert isinstance(results["checks"], list)
        
        check_names = [c["name"] for c in results["checks"]]
        assert "Python version" in check_names
        assert "Git available" in check_names
        assert "Binding file" in check_names
