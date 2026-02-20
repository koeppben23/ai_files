"""Tests for run summary writer and audit CLI."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governance.infrastructure.run_summary_writer import (
    compute_run_id,
    create_run_summary,
    write_run_summary,
    _load_reason_remediation,
)


@pytest.mark.governance
class TestRunIdComputation:
    def test_run_id_is_deterministic(self):
        ts = "2026-02-19T12:00:00Z"
        state = {"Phase": "4", "Mode": "user", "ruleset_hash": "abc123"}
        
        id1 = compute_run_id(state, ts)
        id2 = compute_run_id(state, ts)
        
        assert id1 == id2
        assert len(id1) == 16
    
    def test_run_id_changes_with_different_input(self):
        ts = "2026-02-19T12:00:00Z"
        state1 = {"Phase": "4", "Mode": "user"}
        state2 = {"Phase": "5", "Mode": "user"}
        
        id1 = compute_run_id(state1, ts)
        id2 = compute_run_id(state2, ts)
        
        assert id1 != id2


@pytest.mark.governance
class TestReasonRemediation:
    def test_known_reason_code_returns_fix(self):
        remediation = _load_reason_remediation("BLOCKED-MISSING-BINDING-FILE")
        
        assert "summary" in remediation
        assert "how_to_fix" in remediation
        assert remediation["how_to_fix"]
    
    def test_unknown_reason_code_returns_default(self):
        remediation = _load_reason_remediation("UNKNOWN-CODE-XYZ")
        
        assert "summary" in remediation
        assert "how_to_fix" in remediation


@pytest.mark.governance
class TestCreateRunSummary:
    def test_creates_summary_with_ok_result(self):
        state = {
            "Phase": "4",
            "Mode": "user",
            "ruleset_hash": "abc123",
        }
        
        summary = create_run_summary(state, result="OK")
        
        assert summary["schema_version"] == "1.0"
        assert summary["result"] == "OK"
        assert summary["phase"] == "4"
        assert summary["mode"] == "user"
        assert summary["reason"]["code"] == "OK"
    
    def test_creates_summary_with_blocked_result(self):
        state = {
            "Phase": "1.1",
            "Mode": "pipeline",
            "ruleset_hash": "abc123",
        }
        
        summary = create_run_summary(
            state,
            result="BLOCKED",
            reason_code="BLOCKED-MISSING-BINDING-FILE",
            reason_payload={"binding_file": "missing"},
        )
        
        assert summary["result"] == "BLOCKED"
        assert summary["reason"]["code"] == "BLOCKED-MISSING-BINDING-FILE"
        assert "how_to_fix" in summary["reason"]
        assert summary["reason"]["payload"] == {"binding_file": "missing"}
    
    def test_includes_precedence_events(self):
        state = {
            "Phase": "4",
            "Mode": "user",
            "ActivationHash": "abc123",
            "ruleset_hash": "def456",
        }
        
        summary = create_run_summary(state, result="OK")
        
        assert len(summary["precedence_events"]) >= 1
        events = [e["event"] for e in summary["precedence_events"]]
        assert "ACTIVATION_HASH_COMPUTED" in events
    
    def test_includes_prompt_budget(self):
        state = {
            "Phase": "4",
            "Mode": "user",
            "PromptBudget": {
                "used": 5,
                "allowed": 100,
                "repo_docs_used": 2,
                "repo_docs_allowed": 10,
            },
        }
        
        summary = create_run_summary(state, result="OK")
        
        assert summary["prompt_budget"]["used"] == 5
        assert summary["prompt_budget"]["allowed"] == 100


@pytest.mark.governance
class TestWriteRunSummary:
    def test_writes_summary_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspaces_home = Path(tmpdir)
            
            summary = {
                "schema_version": "1.0",
                "run_id": "abc123def456",
                "timestamp": "2026-02-19T12:00:00Z",
                "mode": "user",
                "phase": "4",
                "result": "OK",
                "reason": {"code": "OK"},
                "precedence_events": [],
                "prompt_budget": {},
                "evidence_pointers": {},
            }
            
            run_path = write_run_summary(summary, workspaces_home, "repo123")
            
            assert run_path.exists()
            assert run_path.name == "abc123def456.json"
            
            latest_link = run_path.parent / "latest.json"
            assert latest_link.exists()
    
    def test_creates_directory_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspaces_home = Path(tmpdir)
            
            summary = {
                "schema_version": "1.0",
                "run_id": "abc123",
                "timestamp": "2026-02-19T12:00:00Z",
                "mode": "user",
                "phase": "4",
                "result": "OK",
                "reason": {"code": "OK"},
                "precedence_events": [],
                "prompt_budget": {},
                "evidence_pointers": {},
            }
            
            run_path = write_run_summary(summary, workspaces_home, "newrepo")
            
            assert run_path.exists()
            expected_dir = workspaces_home / "newrepo" / "evidence" / "runs"
            assert expected_dir.exists()
