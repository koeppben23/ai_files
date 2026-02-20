"""Tests for phase_router.py routing logic."""

from __future__ import annotations

import pytest

from governance.application.use_cases.phase_router import (
    route_phase,
    _api_in_scope,
    _openapi_signal,
    _external_api_artifacts,
)


def _minimal_session_state(**overrides) -> dict[str, object]:
    """Create minimal valid session state for testing."""
    return {
        "SESSION_STATE": {
            "phase": "2.1",
            "workspace_ready_gate_committed": True,
            **overrides,
        }
    }


@pytest.mark.governance
class TestApiInScopeDetection:
    def test_openapi_signal_from_addons_evidence(self):
        state = {
            "AddonsEvidence": {
                "openapi": {"detected": True},
            }
        }
        assert _openapi_signal(state) is True
        assert _api_in_scope(state) is True

    def test_openapi_signal_from_repo_capabilities(self):
        state = {
            "repo_capabilities": ["openapi", "java"],
        }
        assert _openapi_signal(state) is True
        assert _api_in_scope(state) is True

    def test_external_api_artifacts_from_scope(self):
        state = {
            "Scope": {
                "ExternalAPIs": ["user-service-api.yaml"],
            }
        }
        assert _external_api_artifacts(state) is True
        assert _api_in_scope(state) is True

    def test_external_api_artifacts_from_explicit_flag(self):
        state = {
            "external_api_artifacts": True,
        }
        assert _external_api_artifacts(state) is True
        assert _api_in_scope(state) is True

    def test_no_api_signals(self):
        state: dict[str, object] = {}
        assert _openapi_signal(state) is False
        assert _external_api_artifacts(state) is False
        assert _api_in_scope(state) is False

    def test_empty_external_apis_list_means_no_apis(self):
        state = {
            "Scope": {
                "ExternalAPIs": [],
            }
        }
        assert _external_api_artifacts(state) is False
        assert _api_in_scope(state) is False


@pytest.mark.governance
class TestPhase2And1Routing:
    def test_phase_2_1_routes_to_1_5_when_business_rules_not_resolved(self):
        """After Phase 2.1, route to Phase 1.5 if business rules not resolved."""
        doc = _minimal_session_state()
        result = route_phase(
            requested_phase="2.1",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "1.5-BusinessRules"
        assert result.source == "phase-1.5-routing-required"

    def test_phase_2_1_always_routes_to_3a_after_business_rules_resolved(self):
        """After Phase 2.1 with business rules resolved, ALWAYS route to Phase 3A (per docs/phases.md)."""
        doc = _minimal_session_state(
            Scope={"BusinessRules": "not-applicable"},
        )
        result = route_phase(
            requested_phase="2.1",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3A-API-Inventory"
        assert result.source == "phase-2.1-to-3a"
        assert "3A" in result.next_gate_condition

    def test_phase_2_1_routes_to_3a_even_with_apis(self):
        """After Phase 2.1 with APIs detected, route to Phase 3A (same path, 3A decides next step)."""
        doc = _minimal_session_state(
            Scope={"BusinessRules": "not-applicable"},
            AddonsEvidence={"openapi": {"detected": True}},
        )
        result = route_phase(
            requested_phase="2.1",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3A-API-Inventory"
        assert result.source == "phase-2.1-to-3a"


@pytest.mark.governance
class TestPhase1_5Routing:
    def test_phase_1_5_always_routes_to_3a(self):
        """After Phase 1.5, ALWAYS route to Phase 3A (per docs/phases.md requirement)."""
        doc = _minimal_session_state(
            phase="1.5",
        )
        result = route_phase(
            requested_phase="1.5",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3A-API-Inventory"
        assert result.source == "phase-1.5-to-3a"

    def test_phase_1_5_routes_to_3a_with_apis(self):
        """After Phase 1.5 with APIs, route to Phase 3A."""
        doc = _minimal_session_state(
            phase="1.5",
            AddonsEvidence={"openapi": {"detected": True}},
        )
        result = route_phase(
            requested_phase="1.5",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3A-API-Inventory"
        assert result.source == "phase-1.5-to-3a"


@pytest.mark.governance
class TestPhase3ARouting:
    def test_phase_3a_no_apis_routes_to_4_with_not_applicable(self):
        """When entering Phase 3A with no APIs, record not-applicable and route to Phase 4."""
        doc = _minimal_session_state(
            phase="3A",
            Scope={"BusinessRules": "not-applicable"},
        )
        result = route_phase(
            requested_phase="3A",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "4"
        assert result.source == "phase-3a-not-applicable-to-phase4"
        assert "not-applicable" in result.next_gate_condition

    def test_phase_3a_with_apis_routes_to_3b1(self):
        """When Phase 3A has APIs in scope, route to Phase 3B-1 for logical validation."""
        doc = _minimal_session_state(
            phase="3A",
            AddonsEvidence={"openapi": {"detected": True}},
        )
        result = route_phase(
            requested_phase="3A",
            requested_active_gate="API Inventory",
            requested_next_gate_condition="Validate APIs",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3B-1"
        assert result.source == "phase-3a-to-3b1"

    def test_phase_3a_with_external_api_artifacts_routes_to_3b1(self):
        """When Phase 3A has external API artifacts, route to Phase 3B-1."""
        doc = _minimal_session_state(
            phase="3A",
            Scope={"ExternalAPIs": ["service-api.yaml"]},
        )
        result = route_phase(
            requested_phase="3A",
            requested_active_gate="API Inventory",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3B-1"


@pytest.mark.governance
class TestPhase3BRouting:
    def test_phase_3b1_routes_to_3b2(self):
        """After Phase 3B-1, route to Phase 3B-2 for contract validation."""
        doc = _minimal_session_state(
            phase="3B-1",
        )
        result = route_phase(
            requested_phase="3B-1",
            requested_active_gate="API Logical Validation",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3B-2"
        assert result.source == "phase-3b1-to-3b2"

    def test_phase_3b2_routes_to_4(self):
        """After Phase 3B-2, route to Phase 4 for ticket planning."""
        doc = _minimal_session_state(
            phase="3B-2",
        )
        result = route_phase(
            requested_phase="3B-2",
            requested_active_gate="Contract Validation",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "4"
        assert result.source == "phase-3b2-to-4"


@pytest.mark.governance
class TestWorkspaceReadyGate:
    def test_no_workspace_ready_blocks_3a_routing(self):
        """Workspace must be ready before Phase 3A routing."""
        doc: dict[str, object] = {
            "SESSION_STATE": {
                "phase": "2.1",
                "AddonsEvidence": {"openapi": {"detected": True}},
            }
        }
        result = route_phase(
            requested_phase="3A",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "1.1-Bootstrap"
        assert result.source == "workspace-ready-gate"
