"""Tests for profile resolution and regulated activation fixes.

Tests cover:
- Bug #1: regulated profile maps to agents_strict runtime mode
- Bug #2: --profile regulated creates governance-mode.json
- Regulated mode detection and fail-safe behavior

Happy / Negative / Corner / Edge coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_runtime.application.use_cases.repo_policy_setup import (
    write_governance_mode_config,
)
from governance_runtime.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    RegulatedModeState,
)
from governance_runtime.infrastructure.governance_hooks import detect_regulated_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW_UTC = "2026-03-23T12:00:00Z"


# ---------------------------------------------------------------------------
# Bug #1: regulated profile maps to agents_strict
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRegulatedProfileMapping:
    """Tests for Bug #1: regulated profile should map to agents_strict."""

    def test_regulated_profile_maps_to_agents_strict_in_resolution(self):
        """regulated profile resolves to agents_strict runtime mode, not pipeline."""
        from governance_runtime.application.use_cases.resolve_operating_mode import (
            _PROFILE_TO_RUNTIME_MODE,
        )

        assert _PROFILE_TO_RUNTIME_MODE["regulated"] == "agents_strict"

    def test_team_profile_maps_to_pipeline(self):
        """team profile should map to pipeline runtime mode."""
        from governance_runtime.application.use_cases.resolve_operating_mode import (
            _PROFILE_TO_RUNTIME_MODE,
        )

        assert _PROFILE_TO_RUNTIME_MODE["team"] == "pipeline"

    def test_solo_profile_maps_to_user(self):
        """solo profile should map to user runtime mode."""
        from governance_runtime.application.use_cases.resolve_operating_mode import (
            _PROFILE_TO_RUNTIME_MODE,
        )

        assert _PROFILE_TO_RUNTIME_MODE["solo"] == "user"


# ---------------------------------------------------------------------------
# Bug #2: governance-mode.json creation
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestGovernanceModeJsonCreation:
    """Tests for Bug #2: governance-mode.json creation for regulated profile."""

    def test_regulated_init_creates_governance_mode_json(self, tmp_path: Path):
        """--profile regulated creates governance-mode.json at repo root."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_governance_mode_config(
            repo_root=repo_root,
            profile="regulated",
            now_utc=_NOW_UTC,
        )

        assert result is not None
        mode_path = repo_root / "governance-mode.json"
        assert mode_path.exists()

        payload = json.loads(mode_path.read_text(encoding="utf-8"))
        assert payload["state"] == "active"
        assert payload["schema"] == "governance-mode.v1"
        assert payload["activated_by"] == "bootstrap-cli"

    def test_regulated_init_sets_correct_minimum_retention_days(self, tmp_path: Path):
        """governance-mode.json uses existing default 3650, not 365."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        write_governance_mode_config(
            repo_root=repo_root,
            profile="regulated",
            now_utc=_NOW_UTC,
        )

        mode_path = repo_root / "governance-mode.json"
        payload = json.loads(mode_path.read_text(encoding="utf-8"))

        assert payload["minimum_retention_days"] == 3650

    def test_regulated_init_with_custom_compliance_framework(self, tmp_path: Path):
        """governance-mode.json respects --compliance-framework parameter."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        write_governance_mode_config(
            repo_root=repo_root,
            profile="regulated",
            now_utc=_NOW_UTC,
            compliance_framework="DATEV",
        )

        mode_path = repo_root / "governance-mode.json"
        payload = json.loads(mode_path.read_text(encoding="utf-8"))

        assert payload["compliance_framework"] == "DATEV"

    def test_regulated_init_preserves_existing_activated_at(self, tmp_path: Path):
        """Re-running regulated init preserves original activated_at timestamp."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        original_timestamp = "2025-01-01T00:00:00Z"
        mode_path = repo_root / "governance-mode.json"
        mode_path.write_text(
            json.dumps({"state": "active", "activated_at": original_timestamp}),
            encoding="utf-8",
        )

        write_governance_mode_config(
            repo_root=repo_root,
            profile="regulated",
            now_utc=_NOW_UTC,
        )

        payload = json.loads(mode_path.read_text(encoding="utf-8"))
        assert payload["activated_at"] == original_timestamp

    def test_solo_init_does_not_create_governance_mode_json(self, tmp_path: Path):
        """--profile solo does not create governance-mode.json."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_governance_mode_config(
            repo_root=repo_root,
            profile="solo",
            now_utc=_NOW_UTC,
        )

        assert result is None
        mode_path = repo_root / "governance-mode.json"
        assert not mode_path.exists()

    def test_team_init_does_not_create_governance_mode_json(self, tmp_path: Path):
        """--profile team does not create governance-mode.json."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = write_governance_mode_config(
            repo_root=repo_root,
            profile="team",
            now_utc=_NOW_UTC,
        )

        assert result is None
        mode_path = repo_root / "governance-mode.json"
        assert not mode_path.exists()


# ---------------------------------------------------------------------------
# Regulated mode detection (read path)
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestDetectRegulatedMode:
    """Tests for detect_regulated_mode() reading governance-mode.json."""

    def test_detect_reads_produced_file_correctly(self, tmp_path: Path):
        """detect_regulated_mode reads governance-mode.json produced by write function."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        write_governance_mode_config(
            repo_root=repo_root,
            profile="regulated",
            now_utc=_NOW_UTC,
        )

        config = detect_regulated_mode(repo_root)

        assert config.state == RegulatedModeState.ACTIVE
        assert config.minimum_retention_days == 3650

    def test_detect_returns_inactive_when_no_file(self, tmp_path: Path):
        """Missing governance-mode.json defaults to inactive (fail-safe)."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        config = detect_regulated_mode(repo_root)

        assert config == DEFAULT_CONFIG
        assert config.state == RegulatedModeState.INACTIVE

    def test_detect_returns_inactive_for_empty_dir(self, tmp_path: Path):
        """Empty directory without governance-mode.json returns inactive."""
        repo_root = tmp_path / "empty_repo"
        repo_root.mkdir()

        config = detect_regulated_mode(repo_root)

        assert config.state == RegulatedModeState.INACTIVE

    def test_detect_handles_invalid_json(self, tmp_path: Path):
        """Invalid JSON in governance-mode.json returns default (fail-safe)."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mode_path = repo_root / "governance-mode.json"
        mode_path.write_text("not valid json{{{", encoding="utf-8")

        config = detect_regulated_mode(repo_root)

        assert config == DEFAULT_CONFIG

    def test_detect_handles_non_dict_root(self, tmp_path: Path):
        """governance-mode.json with non-dict root returns default (fail-safe)."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mode_path = repo_root / "governance-mode.json"
        mode_path.write_text('["array", "not", "dict"]', encoding="utf-8")

        config = detect_regulated_mode(repo_root)

        assert config == DEFAULT_CONFIG

    def test_detect_handles_unknown_state(self, tmp_path: Path):
        """Unknown state value in governance-mode.json returns inactive (fail-safe)."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mode_path = repo_root / "governance-mode.json"
        mode_path.write_text(
            json.dumps({"state": "unknown_state_value"}),
            encoding="utf-8",
        )

        config = detect_regulated_mode(repo_root)

        assert config.state == RegulatedModeState.INACTIVE


# ---------------------------------------------------------------------------
# Round-trip: write -> read consistency
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRoundTripWriteRead:
    """Tests for write -> detect round-trip consistency."""

    @pytest.mark.parametrize(
        "compliance_framework,expected_min_retention",
        [
            ("DEFAULT", 3650),
            ("DATEV", 3650),
            ("GoBD", 3650),
            ("BaFin", 3650),
            ("SOX", 3650),
            ("GDPR", 3650),
        ],
    )
    def test_round_trip_with_various_frameworks(
        self,
        tmp_path: Path,
        compliance_framework: str,
        expected_min_retention: int,
    ):
        """Write governance-mode.json and detect_regulated_mode returns correct config."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        write_governance_mode_config(
            repo_root=repo_root,
            profile="regulated",
            now_utc=_NOW_UTC,
            compliance_framework=compliance_framework,
        )

        config = detect_regulated_mode(repo_root)

        assert config.state == RegulatedModeState.ACTIVE
        assert config.compliance_framework == compliance_framework
        assert config.minimum_retention_days == expected_min_retention
