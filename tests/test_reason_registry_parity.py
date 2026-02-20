"""Tests for Reason Code Registry Parity Selfcheck.

Note: These tests focus on the newly added BLOCKED-PIPELINE-* codes.
Full registry parity is a separate concern tracked elsewhere.
"""

from __future__ import annotations

import pytest

from diagnostics.reason_registry_selfcheck import check_reason_registry_parity


@pytest.mark.governance
class TestPipelineReasonCodesParity:
    """Tests for BLOCKED-PIPELINE-* reason code consistency."""

    def test_pipeline_interactive_in_domain(self):
        """BLOCKED-PIPELINE-INTERACTIVE is in domain constants."""
        from governance.domain.reason_codes import BLOCKED_PIPELINE_INTERACTIVE
        assert BLOCKED_PIPELINE_INTERACTIVE == "BLOCKED-PIPELINE-INTERACTIVE"

    def test_pipeline_human_assist_in_domain(self):
        """BLOCKED-PIPELINE-HUMAN-ASSIST is in domain constants."""
        from governance.domain.reason_codes import BLOCKED_PIPELINE_HUMAN_ASSIST
        assert BLOCKED_PIPELINE_HUMAN_ASSIST == "BLOCKED-PIPELINE-HUMAN-ASSIST"

    def test_pipeline_interactive_in_registry(self):
        """BLOCKED-PIPELINE-INTERACTIVE is in registry."""
        import json
        from pathlib import Path
        repo_root = Path(__file__).parent.parent
        registry_path = repo_root / "diagnostics" / "reason_codes.registry.json"
        
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        codes = [e["code"] for e in data.get("blocked_reasons", [])]
        assert "BLOCKED-PIPELINE-INTERACTIVE" in codes

    def test_pipeline_human_assist_in_registry(self):
        """BLOCKED-PIPELINE-HUMAN-ASSIST is in registry."""
        import json
        from pathlib import Path
        repo_root = Path(__file__).parent.parent
        registry_path = repo_root / "diagnostics" / "reason_codes.registry.json"
        
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        codes = [e["code"] for e in data.get("blocked_reasons", [])]
        assert "BLOCKED-PIPELINE-HUMAN-ASSIST" in codes

    def test_pipeline_interactive_in_embedded_registry(self):
        """BLOCKED-PIPELINE-INTERACTIVE is in embedded registry."""
        from governance.engine._embedded_reason_registry import EMBEDDED_REASON_CODE_TO_SCHEMA_REF
        assert "BLOCKED-PIPELINE-INTERACTIVE" in EMBEDDED_REASON_CODE_TO_SCHEMA_REF

    def test_pipeline_human_assist_in_embedded_registry(self):
        """BLOCKED-PIPELINE-HUMAN-ASSIST is in embedded registry."""
        from governance.engine._embedded_reason_registry import EMBEDDED_REASON_CODE_TO_SCHEMA_REF
        assert "BLOCKED-PIPELINE-HUMAN-ASSIST" in EMBEDDED_REASON_CODE_TO_SCHEMA_REF


@pytest.mark.governance
class TestReasonRegistrySelfcheck:
    """Tests for the selfcheck utility itself."""

    def test_selfcheck_detects_missing_registry(self, tmp_path):
        """Selfcheck detects missing registry file."""
        is_ok, errors = check_reason_registry_parity(repo_root=tmp_path)
        assert is_ok is False
        assert any("missing" in e.lower() for e in errors)
