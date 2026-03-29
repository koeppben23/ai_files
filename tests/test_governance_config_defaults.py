"""Tests for governance-config.json canonical defaults.

Verifies that the default governance config asset matches the loader defaults
and is schema-conform. This prevents drift between:
- Hardcoded loader defaults
- Installer asset
- Documentation

V1 only includes review iteration knobs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestGovernanceConfigCanonicalDefaults:
    """Tests verifying canonical V1 defaults are consistent across codebase."""

    def test_default_config_matches_loader_defaults(self) -> None:
        """Asset defaults must match hardcoded loader defaults.
        
        Note: Asset may include $schema but loader defaults do not.
        """
        from governance_runtime.domain.default_governance_config import get_default_governance_config
        
        loader_defaults = get_default_governance_config()
        
        asset_path = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "config" / "governance-config.json"
        assert asset_path.exists(), f"governance-config.json asset not found at {asset_path}"
        
        asset_content = json.loads(asset_path.read_text(encoding="utf-8"))
        
        asset_content.pop("$schema", None)
        
        assert asset_content == loader_defaults

    def test_default_config_schema_valid(self) -> None:
        """Asset must be valid against governance-config schema."""
        from governance_runtime.infrastructure.governance_config_loader import validate_governance_config
        
        asset_path = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "config" / "governance-config.json"
        assert asset_path.exists(), f"governance-config.json asset not found at {asset_path}"
        
        asset_content = json.loads(asset_path.read_text(encoding="utf-8"))
        errors = validate_governance_config(asset_content)
        
        assert not errors, f"Asset validation failed: {errors}"

    def test_default_config_has_all_required_v1_keys(self) -> None:
        """Asset must contain all V1 configuration keys (review section only)."""
        asset_path = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "config" / "governance-config.json"
        assert asset_path.exists(), f"governance-config.json asset not found at {asset_path}"
        
        asset_content = json.loads(asset_path.read_text(encoding="utf-8"))
        
        assert "presentation" in asset_content
        assert asset_content["presentation"]["mode"] == "narrative"
        assert "review" in asset_content
        assert "phase5_max_review_iterations" in asset_content["review"]
        assert "phase6_max_review_iterations" in asset_content["review"]

    def test_default_config_values_within_bounds(self) -> None:
        """Default values must be within schema bounds."""
        asset_path = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "config" / "governance-config.json"
        assert asset_path.exists(), f"governance-config.json asset not found at {asset_path}"
        
        asset_content = json.loads(asset_path.read_text(encoding="utf-8"))
        
        assert 1 <= asset_content["review"]["phase5_max_review_iterations"] <= 100
        assert 1 <= asset_content["review"]["phase6_max_review_iterations"] <= 100


class TestGovernanceConfigLoaderDefaults:
    """Tests verifying loader handles missing config correctly."""

    def test_missing_config_returns_defaults(self, tmp_path: Path) -> None:
        """Missing governance-config.json returns hardcoded defaults."""
        from governance_runtime.infrastructure.governance_config_loader import load_governance_config
        from governance_runtime.domain.default_governance_config import get_default_governance_config
        
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        result = load_governance_config(workspace_dir)
        expected = get_default_governance_config()
        
        assert result == expected

    def test_missing_workspace_root_returns_defaults(self) -> None:
        """None workspace_dir returns defaults."""
        from governance_runtime.infrastructure.governance_config_loader import load_governance_config
        from governance_runtime.domain.default_governance_config import get_default_governance_config
        
        result = load_governance_config(None)
        expected = get_default_governance_config()
        
        assert result == expected

    def test_invalid_json_fails_closed(self, tmp_path: Path) -> None:
        """Invalid JSON raises RuntimeError (fail-closed)."""
        from governance_runtime.infrastructure.governance_config_loader import load_governance_config
        
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        (workspace_dir / "governance-config.json").write_text('{"invalid json"', encoding="utf-8")
        
        with pytest.raises(RuntimeError, match="governance-config.json.*unreadable"):
            load_governance_config(workspace_dir)

    def test_invalid_schema_fails_closed(self, tmp_path: Path) -> None:
        """Invalid schema (missing required fields) raises RuntimeError."""
        from governance_runtime.infrastructure.governance_config_loader import load_governance_config
        
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        invalid_config = {
            "review": {
                "phase5_max_review_iterations": 3,
            },
        }
        (workspace_dir / "governance-config.json").write_text(json.dumps(invalid_config), encoding="utf-8")
        
        with pytest.raises(RuntimeError, match="governance-config.json.*invalid"):
            load_governance_config(workspace_dir)

    def test_unknown_keys_fails_closed(self, tmp_path: Path) -> None:
        """Unknown keys raise RuntimeError (fail-closed)."""
        from governance_runtime.infrastructure.governance_config_loader import load_governance_config
        
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        config_with_unknown = {
            "review": {
                "phase5_max_review_iterations": 3,
                "phase6_max_review_iterations": 3,
            },
            "unknown_key": "should fail",
        }
        (workspace_dir / "governance-config.json").write_text(json.dumps(config_with_unknown), encoding="utf-8")
        
        with pytest.raises(RuntimeError, match="governance-config.json.*invalid"):
            load_governance_config(workspace_dir)

    def test_valid_custom_config_loaded(self, tmp_path: Path) -> None:
        """Valid custom config is loaded correctly."""
        from governance_runtime.infrastructure.governance_config_loader import load_governance_config
        
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        custom_config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 7,
                "phase6_max_review_iterations": 5,
            },
        }
        (workspace_dir / "governance-config.json").write_text(json.dumps(custom_config), encoding="utf-8")
        
        result = load_governance_config(workspace_dir)
        
        assert result["review"]["phase5_max_review_iterations"] == 7
        assert result["review"]["phase6_max_review_iterations"] == 5


class TestGetReviewIterationsDefaults:
    """Tests for get_review_iterations helper function."""

    def test_returns_defaults_when_none_workspace(self) -> None:
        """None workspace returns (3, 3)."""
        from governance_runtime.infrastructure.governance_config_loader import get_review_iterations
        
        phase5, phase6 = get_review_iterations(None)
        
        assert phase5 == 3
        assert phase6 == 3

    def test_returns_defaults_when_config_missing(self, tmp_path: Path) -> None:
        """Missing config file returns (3, 3)."""
        from governance_runtime.infrastructure.governance_config_loader import get_review_iterations
        
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        phase5, phase6 = get_review_iterations(workspace_dir)
        
        assert phase5 == 3
        assert phase6 == 3

    def test_returns_custom_values_from_config(self, tmp_path: Path) -> None:
        """Custom values from config are returned."""
        from governance_runtime.infrastructure.governance_config_loader import get_review_iterations
        
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        custom_config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 5,
                "phase6_max_review_iterations": 7,
            },
        }
        (workspace_dir / "governance-config.json").write_text(json.dumps(custom_config), encoding="utf-8")
        
        phase5, phase6 = get_review_iterations(workspace_dir)
        
        assert phase5 == 5
        assert phase6 == 7
