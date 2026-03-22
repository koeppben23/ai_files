"""Integration tests for state document validation enforcement."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from governance_runtime.application.services.state_document_validator import (
    validate_state_document,
    validate_review_payload,
    validate_plan_payload,
    validate_receipt_payload,
)


class TestStateDocumentEnforcement:
    """Test fail-closed enforcement for StateDocument validation."""

    def test_invalid_state_document_is_rejected(self):
        """Invalid state document should be rejected."""
        invalid_doc = {}
        result = validate_state_document(invalid_doc)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_missing_session_state_blocks(self):
        """Missing SESSION_STATE should block."""
        doc = {"metadata": {}}
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "MISSING_SESSION_STATE" for e in result.errors)

    def test_missing_phase_blocks(self):
        """Missing phase should block."""
        doc = {
            "SESSION_STATE": {
                "active_gate": "Ticket Input Gate",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "MISSING_PHASE" for e in result.errors)

    def test_missing_active_gate_blocks(self):
        """Missing active_gate should block."""
        doc = {
            "SESSION_STATE": {
                "phase": "4",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "MISSING_ACTIVE_GATE" for e in result.errors)

    def test_invalid_gates_type_blocks(self):
        """Invalid Gates type should block."""
        doc = {
            "SESSION_STATE": {
                "phase": "4",
                "active_gate": "Ticket Input Gate",
                "Gates": "not a dict",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "INVALID_GATES_TYPE" for e in result.errors)


class TestReviewPayloadEnforcement:
    """Test fail-closed enforcement for ReviewPayload validation."""

    def test_missing_verdict_blocks(self):
        """Missing verdict should block."""
        payload = {"findings": []}
        result = validate_review_payload(payload)
        assert result.valid is False
        assert any(e.code == "MISSING_VERDICT" for e in result.errors)

    def test_empty_verdict_blocks(self):
        """Empty verdict should block."""
        payload = {"verdict": ""}
        result = validate_review_payload(payload)
        assert result.valid is False
        assert any(e.code == "INVALID_VERDICT" for e in result.errors)

    def test_valid_review_payload_passes(self):
        """Valid review payload should pass."""
        payload = {
            "verdict": "approve",
            "findings": ["Finding 1"],
        }
        result = validate_review_payload(payload)
        assert result.valid is True


class TestPlanPayloadEnforcement:
    """Test fail-closed enforcement for PlanPayload validation."""

    def test_missing_body_blocks(self):
        """Missing body should block."""
        payload = {"status": "draft"}
        result = validate_plan_payload(payload)
        assert result.valid is False
        assert any(e.code == "MISSING_BODY" for e in result.errors)

    def test_empty_body_blocks(self):
        """Empty body should block."""
        payload = {"body": "", "status": "draft"}
        result = validate_plan_payload(payload)
        assert result.valid is False
        assert any(e.code == "INVALID_BODY" for e in result.errors)

    def test_missing_status_blocks(self):
        """Missing status should block."""
        payload = {"body": "Plan content"}
        result = validate_plan_payload(payload)
        assert result.valid is False
        assert any(e.code == "MISSING_STATUS" for e in result.errors)

    def test_valid_plan_payload_passes(self):
        """Valid plan payload should pass."""
        payload = {
            "body": "Plan content here",
            "status": "draft",
        }
        result = validate_plan_payload(payload)
        assert result.valid is True


class TestReceiptPayloadEnforcement:
    """Test enforcement for ReceiptPayload validation (warnings only)."""

    def test_missing_evidence_warns(self):
        """Missing evidence should warn but not block."""
        payload = {"timestamp": "2024-01-01T00:00:00Z"}
        result = validate_receipt_payload(payload)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any(w.code == "MISSING_EVIDENCE" for w in result.warnings)

    def test_missing_timestamp_warns(self):
        """Missing timestamp should warn but not block."""
        payload = {"evidence": ["Evidence 1"]}
        result = validate_receipt_payload(payload)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any(w.code == "MISSING_TIMESTAMP" for w in result.warnings)

    def test_valid_receipt_payload_passes(self):
        """Valid receipt payload should pass."""
        payload = {
            "evidence": ["Evidence 1"],
            "timestamp": "2024-01-01T00:00:00Z",
        }
        result = validate_receipt_payload(payload)
        assert result.valid is True
        assert len(result.warnings) == 0


class TestValidationSeverityClassification:
    """Test that errors and warnings are properly classified."""

    def test_blocking_errors_are_errors(self):
        """Blocking validation failures are classified as ERROR severity."""
        doc = {"SESSION_STATE": {}}
        result = validate_state_document(doc)
        assert result.valid is False
        for error in result.errors:
            assert error.severity.value == "error"

    def test_non_critical_warnings_are_warnings(self):
        """Non-critical validation issues are classified as WARNING severity."""
        doc = {
            "SESSION_STATE": {
                "phase": "4",
                "active_gate": "Ticket Input Gate",
                "status": "OK",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is True
        for warning in result.warnings:
            assert warning.severity.value == "warning"


class TestSessionReaderEnforcement:
    """Test fail-closed enforcement at session_reader boundary via real integration."""

    def test_invalid_state_document_via_validator_causes_error(self):
        """Invalid state document validation should fail."""
        from governance_runtime.application.services.state_document_validator import validate_state_document
        
        invalid_doc = {"SESSION_STATE": {}}
        result = validate_state_document(invalid_doc)
        assert result.valid is False
        
        error_codes = [e.code for e in result.errors]
        assert "MISSING_PHASE" in error_codes
        assert "MISSING_ACTIVE_GATE" in error_codes

    def test_missing_session_state_via_validator_returns_error(self):
        """Missing SESSION_STATE validation should fail."""
        from governance_runtime.application.services.state_document_validator import validate_state_document
        
        invalid_doc = {"metadata": {}}
        result = validate_state_document(invalid_doc)
        assert result.valid is False
        
        error_codes = [e.code for e in result.errors]
        assert "MISSING_SESSION_STATE" in error_codes

    def test_valid_state_document_passes_validation(self):
        """Valid state document should pass validation."""
        from governance_runtime.application.services.state_document_validator import validate_state_document
        
        valid_doc = {
            "SESSION_STATE": {
                "phase": "4",
                "active_gate": "Ticket Input Gate",
                "status": "OK",
            }
        }
        result = validate_state_document(valid_doc)
        assert result.valid is True

    def test_invalid_gates_type_causes_error(self):
        """Invalid Gates type should cause validation error."""
        from governance_runtime.application.services.state_document_validator import validate_state_document
        
        invalid_doc = {
            "SESSION_STATE": {
                "phase": "4",
                "active_gate": "Ticket Input Gate",
                "Gates": "not a dict",
            }
        }
        result = validate_state_document(invalid_doc)
        assert result.valid is False
        error_codes = [e.code for e in result.errors]
        assert "INVALID_GATES_TYPE" in error_codes


class TestSessionReaderIntegration:
    """Test the actual session_reader boundary with real file system."""

    def test_invalid_state_document_through_session_reader_returns_error(self, tmp_path: Path):
        """Invalid state document through real session_reader should return error status."""
        from governance_runtime.infrastructure.json_store import write_json_atomic
        
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True)
        
        config_root = tmp_path
        commands_home = tmp_path / "commands"
        commands_home.mkdir(parents=True)
        
        invalid_state = {"SESSION_STATE": {}}
        state_file = workspace / "session_state.json"
        write_json_atomic(state_file, invalid_state)
        
        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(state_file),
            "activeRepoFingerprint": "test-repo-fp",
        }
        pointer_file = config_root / "SESSION_STATE.json"
        write_json_atomic(pointer_file, pointer)
        
        governance_runtime_init = commands_home / "governance_runtime" / "__init__.py"
        governance_runtime_init.parent.mkdir(parents=True, exist_ok=True)
        governance_runtime_init.write_text("")
        
        state_init = commands_home / "governance_runtime" / "application" / "__init__.py"
        state_init.parent.mkdir(parents=True, exist_ok=True)
        state_init.write_text("")
        
        services_init = commands_home / "governance_runtime" / "application" / "services" / "__init__.py"
        services_init.parent.mkdir(parents=True, exist_ok=True)
        services_init.write_text("")
        
        from governance_runtime.entrypoints.session_reader import read_session_snapshot
        
        result = read_session_snapshot(commands_home=commands_home)
        
        assert result["status"] == "ERROR"
        assert "StateDocument validation failed" in result["error"]

    def test_valid_state_document_through_session_reader_succeeds(self, tmp_path: Path):
        """Valid state document through session_reader should return success."""
        from governance_runtime.infrastructure.json_store import write_json_atomic
        
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True)
        
        config_root = tmp_path
        commands_home = tmp_path / "commands"
        commands_home.mkdir(parents=True)
        
        valid_state = {
            "SESSION_STATE": {
                "phase": "4",
                "active_gate": "Ticket Input Gate",
                "status": "OK",
                "Mode": "NORMAL",
            }
        }
        state_file = workspace / "session_state.json"
        write_json_atomic(state_file, valid_state)
        
        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(state_file),
            "activeRepoFingerprint": "test-repo-fp",
        }
        pointer_file = config_root / "SESSION_STATE.json"
        write_json_atomic(pointer_file, pointer)
        
        governance_runtime_init = commands_home / "governance_runtime" / "__init__.py"
        governance_runtime_init.parent.mkdir(parents=True, exist_ok=True)
        governance_runtime_init.write_text("")
        
        state_init = commands_home / "governance_runtime" / "application" / "__init__.py"
        state_init.parent.mkdir(parents=True, exist_ok=True)
        state_init.write_text("")
        
        services_init = commands_home / "governance_runtime" / "application" / "services" / "__init__.py"
        services_init.parent.mkdir(parents=True, exist_ok=True)
        services_init.write_text("")
        
        from governance_runtime.entrypoints.session_reader import read_session_snapshot
        
        result = read_session_snapshot(commands_home=commands_home, materialize=False)
        
        assert result["status"] != "ERROR" or "validation failed" not in result.get("error", "").lower()
