"""Tests for state_document_validator module."""

from __future__ import annotations

import pytest

from governance_runtime.application.services.state_document_validator import (
    validate_state_document,
    validate_review_payload,
    validate_plan_payload,
    validate_receipt_payload,
    ValidationSeverity,
)


class TestValidateStateDocument:
    def test_valid_state_document(self):
        doc = {
            "SESSION_STATE": {
                "phase": "4",
                "active_gate": "Ticket Input Gate",
                "status": "OK",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_missing_session_state(self):
        doc = {}
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "MISSING_SESSION_STATE" for e in result.errors)

    def test_session_state_not_dict(self):
        doc = {"SESSION_STATE": "not a dict"}
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "INVALID_SESSION_STATE_TYPE" for e in result.errors)

    def test_missing_phase(self):
        doc = {
            "SESSION_STATE": {
                "active_gate": "Ticket Input Gate",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is True
        assert any(e.code == "MISSING_PHASE" for e in result.warnings)

    def test_empty_phase(self):
        doc = {
            "SESSION_STATE": {
                "phase": "",
                "active_gate": "Ticket Input Gate",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "INVALID_PHASE" for e in result.errors)

    def test_unknown_phase_token_warns(self):
        doc = {
            "SESSION_STATE": {
                "phase": "99",
                "active_gate": "Ticket Input Gate",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is True
        assert any(e.code == "UNKNOWN_PHASE_TOKEN" for e in result.warnings)

    def test_missing_active_gate(self):
        doc = {
            "SESSION_STATE": {
                "phase": "4",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is True
        assert any(e.code == "MISSING_ACTIVE_GATE" for e in result.warnings)

    def test_empty_active_gate(self):
        doc = {
            "SESSION_STATE": {
                "phase": "4",
                "active_gate": "",
            }
        }
        result = validate_state_document(doc)
        assert result.valid is False
        assert any(e.code == "INVALID_ACTIVE_GATE" for e in result.errors)

    def test_invalid_gates_type(self):
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

    def test_known_phase_token_passes(self):
        for phase in ["1", "2", "3A", "4", "5", "5.3", "5.4", "5.5", "5.6", "6"]:
            doc = {
                "SESSION_STATE": {
                    "phase": phase,
                    "active_gate": "Ticket Input Gate",
                }
            }
            result = validate_state_document(doc)
            assert result.valid is True, f"Phase {phase} should be valid"

    def test_non_dict_input(self):
        result = validate_state_document("not a dict")
        assert result.valid is False
        assert any(e.code == "INVALID_TYPE" for e in result.errors)


class TestValidateReviewPayload:
    def test_valid_review_payload(self):
        payload = {
            "verdict": "approve",
            "findings": ["Finding 1", "Finding 2"],
        }
        result = validate_review_payload(payload)
        assert result.valid is True

    def test_missing_verdict(self):
        payload = {"findings": []}
        result = validate_review_payload(payload)
        assert result.valid is False
        assert any(e.code == "MISSING_VERDICT" for e in result.errors)

    def test_empty_verdict(self):
        payload = {"verdict": ""}
        result = validate_review_payload(payload)
        assert result.valid is False
        assert any(e.code == "INVALID_VERDICT" for e in result.errors)

    def test_missing_findings_warns(self):
        payload = {"verdict": "approve"}
        result = validate_review_payload(payload)
        assert result.valid is True
        assert any(e.code == "MISSING_FINDINGS" for e in result.warnings)

    def test_non_dict_input(self):
        result = validate_review_payload("not a dict")
        assert result.valid is False


class TestValidatePlanPayload:
    def test_valid_plan_payload(self):
        payload = {
            "body": "Plan content here",
            "status": "draft",
        }
        result = validate_plan_payload(payload)
        assert result.valid is True

    def test_missing_body(self):
        payload = {"status": "draft"}
        result = validate_plan_payload(payload)
        assert result.valid is False
        assert any(e.code == "MISSING_BODY" for e in result.errors)

    def test_empty_body(self):
        payload = {"body": "", "status": "draft"}
        result = validate_plan_payload(payload)
        assert result.valid is False
        assert any(e.code == "INVALID_BODY" for e in result.errors)

    def test_missing_status(self):
        payload = {"body": "Plan content"}
        result = validate_plan_payload(payload)
        assert result.valid is False
        assert any(e.code == "MISSING_STATUS" for e in result.errors)

    def test_non_dict_input(self):
        result = validate_plan_payload("not a dict")
        assert result.valid is False


class TestValidateReceiptPayload:
    def test_valid_receipt_payload(self):
        payload = {
            "evidence": ["Evidence 1"],
            "timestamp": "2024-01-01T00:00:00Z",
        }
        result = validate_receipt_payload(payload)
        assert result.valid is True

    def test_missing_evidence_warns(self):
        payload = {"timestamp": "2024-01-01T00:00:00Z"}
        result = validate_receipt_payload(payload)
        assert result.valid is True
        assert any(e.code == "MISSING_EVIDENCE" for e in result.warnings)

    def test_missing_timestamp_warns(self):
        payload = {"evidence": ["Evidence 1"]}
        result = validate_receipt_payload(payload)
        assert result.valid is True
        assert any(e.code == "MISSING_TIMESTAMP" for e in result.warnings)

    def test_non_dict_input(self):
        result = validate_receipt_payload("not a dict")
        assert result.valid is False
