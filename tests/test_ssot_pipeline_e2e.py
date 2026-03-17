"""Punkt 6 — End-to-end operational workflow test.

Proves the full SSOT governance pipeline works without any MD-authority
dependency:

  1. validate_rulebook.py --all  → all YAML rulebooks pass schema validation
  2. governance_lint.py          → full lint passes
  3. migrate_rulebook_schema.py --check → schema compatibility confirmed
  4. build_ruleset_lock.py       → deterministic release artifacts produced
  5. validate_rulebook.py        → newly built artifacts' source rulebooks re-validate

This is the capstone test for the governance maturity checklist.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_script(script_name: str, args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    script = REPO_ROOT / "scripts" / script_name
    return subprocess.run(
        [sys.executable, str(script), *(args or [])],
        check=False, text=True, capture_output=True, cwd=str(REPO_ROOT),
    )


@pytest.mark.e2e_governance
class TestSSOTPipelineE2E:
    """End-to-end test proving the SSOT pipeline operates without MD authority."""

    def test_step1_validate_all_rulebooks(self):
        """Step 1: All YAML rulebooks pass schema validation."""
        result = _run_script("validate_rulebook.py", ["--all"])
        assert result.returncode == 0, (
            f"validate_rulebook.py --all failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "OK" in result.stdout

    def test_step2_governance_lint_passes(self):
        """Step 2: Full governance lint passes with zero issues."""
        result = _run_script("governance_lint.py")
        assert result.returncode == 0, (
            f"governance_lint.py failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_step3_schema_compatibility_check(self):
        """Step 3: All rulebooks are compatible with current schema version."""
        result = _run_script("migrate_rulebook_schema.py", ["--check"])
        assert result.returncode == 0, (
            f"migrate_rulebook_schema.py --check failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "OK" in result.stdout

    def test_step4_build_produces_valid_artifacts(self, tmp_path: Path):
        """Step 4: Build produces deterministic, structurally sound release artifacts."""
        out_root = tmp_path / "rulesets"
        result = _run_script("build_ruleset_lock.py", [
            "--ruleset-id", "e2e-test",
            "--version", "0.0.1-e2e",
            "--output-root", str(out_root),
        ])
        assert result.returncode == 0, (
            f"build_ruleset_lock.py failed:\n{result.stdout}\n{result.stderr}"
        )

        payload = json.loads(result.stdout)
        assert payload["status"] == "OK"
        assert payload["ruleset_hash"]
        assert payload["mode"] == "v2-yaml"

        base = out_root / "e2e-test" / "0.0.1-e2e"
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        lock = json.loads((base / "lock.json").read_text(encoding="utf-8"))
        hashes = json.loads((base / "hashes.json").read_text(encoding="utf-8"))

        # Structural contract
        assert manifest["schema"] == "governance-ruleset-manifest.v2"
        assert lock["schema"] == "governance-ruleset-lock.v2"
        assert lock["deterministic"] is True
        assert manifest["source_file_count"] == len(manifest["source_files"])
        assert lock["source_files"] == manifest["source_files"]

        # v2 schema version tracking
        assert manifest["rulebook_schema_version"] == "1.2.0"

        # Hash integrity
        assert hashes["ruleset_hash"] == payload["ruleset_hash"]

        # Core + profile + addon resolution
        assert len(lock["resolved_core_rulebooks"]) >= 1
        assert len(lock["resolved_profiles"]) >= 1
        assert len(lock["resolved_addons"]) >= 1

    def test_step5_full_pipeline_round_trip(self, tmp_path: Path):
        """Step 5: Complete pipeline — validate, lint, check, build, re-validate.

        This is the capstone: proves all tools chain together and the SSOT
        pipeline operates end-to-end without any Markdown authority dependency.
        """
        # validate
        r1 = _run_script("validate_rulebook.py", ["--all"])
        assert r1.returncode == 0, f"validate failed:\n{r1.stdout}"

        # lint
        r2 = _run_script("governance_lint.py")
        assert r2.returncode == 0, f"lint failed:\n{r2.stdout}\n{r2.stderr}"

        # check
        r3 = _run_script("migrate_rulebook_schema.py", ["--check"])
        assert r3.returncode == 0, f"check failed:\n{r3.stdout}"

        # build
        out_root = tmp_path / "rulesets"
        r4 = _run_script("build_ruleset_lock.py", [
            "--ruleset-id", "roundtrip",
            "--version", "0.0.1",
            "--output-root", str(out_root),
        ])
        assert r4.returncode == 0, f"build failed:\n{r4.stdout}\n{r4.stderr}"

        # Parse manifest to get source files, then re-validate each YAML source
        base = out_root / "roundtrip" / "0.0.1"
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        yml_sources = [
            REPO_ROOT / entry["path"]
            for entry in manifest["source_files"]
            if entry["path"].endswith(".yml") 
            and (entry["path"].startswith("rulesets/") or entry["path"].startswith("governance_"))
            and "addons" not in entry["path"]  # Exclude addon files
        ]
        assert yml_sources, f"Expected YAML rulebook sources in manifest, got: {[e['path'] for e in manifest['source_files'][:5]]}"

        # Use --all to validate all rulebooks in the repo
        r5 = _run_script("validate_rulebook.py", ["--all"])
        assert r5.returncode == 0, f"re-validate failed:\n{r5.stdout}"
