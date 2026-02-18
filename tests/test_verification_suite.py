from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.application.use_cases.phase_router import route_phase
from governance.infrastructure.workspace_ready_gate import ensure_workspace_ready


@pytest.mark.governance
def test_phase_router_blocks_phase2_without_workspace_ready():
    routed = route_phase(
        requested_phase="2-Discovery",
        requested_active_gate="Discovery",
        requested_next_gate_condition="Build decision pack",
        session_state_document={"SESSION_STATE": {"workspace_ready": False}},
        repo_is_git_root=False,
    )
    assert routed.phase == "1.1-Bootstrap"
    assert routed.active_gate == "Workspace Ready Gate"
    assert routed.workspace_ready is False


@pytest.mark.governance
def test_phase_router_routes_openapi_from_phase21_to_3a():
    routed = route_phase(
        requested_phase="2.1-DecisionPack",
        requested_active_gate="Decision Pack",
        requested_next_gate_condition="Proceed",
        session_state_document={"SESSION_STATE": {"workspace_ready": True, "repo_capabilities": ["openapi"]}},
        repo_is_git_root=True,
    )
    assert routed.phase == "3A-Activation"
    assert "3A" in routed.next_gate_condition


@pytest.mark.governance
def test_workspace_ready_gate_writes_marker_evidence_and_pointer(tmp_path: Path):
    workspaces_home = tmp_path / "workspaces"
    session_state = tmp_path / "SESSION_STATE.json"
    session_state.write_text("{}\n", encoding="utf-8")
    pointer = tmp_path / "active-session-pointer.json"

    decision = ensure_workspace_ready(
        workspaces_home=workspaces_home,
        repo_fingerprint="abc123def456abc123def456",
        repo_root=tmp_path / "repo",
        session_state_file=session_state,
        session_pointer_file=pointer,
        session_id="sess-1",
        discovery_method="env:OPENCODE_REPO_ROOT:git-rev-parse",
    )

    assert decision.ok is True
    assert decision.marker_path is not None and decision.marker_path.exists()
    assert decision.pointer_path is not None and decision.pointer_path.exists()
    marker_payload = json.loads(decision.marker_path.read_text(encoding="utf-8"))
    assert marker_payload["workspace_ready"] is True


@pytest.mark.governance
def test_workspace_ready_gate_fails_closed_when_fp_missing(tmp_path: Path):
    decision = ensure_workspace_ready(
        workspaces_home=tmp_path / "workspaces",
        repo_fingerprint="",
        repo_root=tmp_path / "repo",
        session_state_file=tmp_path / "SESSION_STATE.json",
        session_pointer_file=tmp_path / "active-session-pointer.json",
        session_id="sess-1",
        discovery_method="cwd",
    )
    assert decision.ok is False
    assert decision.reason == "fingerprint-missing"
