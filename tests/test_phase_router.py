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
class TestPhase3Routing:
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

    def test_phase_2_1_routes_to_4_when_business_rules_resolved_no_apis(self):
        """After Phase 2.1 with business rules resolved and no APIs, route to Phase 4."""
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
        assert result.phase == "4"
        assert result.source == "phase-2.1-to-4-no-api"

    def test_apis_in_scope_routes_to_3a_after_1_5_resolved(self):
        """When APIs are detected and Phase 1.5 resolved, route to Phase 3A."""
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
        assert result.phase == "3A-Activation"
        assert result.source == "api-phase-routing"

    def test_no_apis_at_phase_3a_skips_to_phase_4(self):
        """When entering Phase 3A with no APIs, skip directly to Phase 4."""
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
        assert result.source == "no-api-skip-to-phase4"
        assert "No API artifacts" in result.next_gate_condition

    def test_external_apis_route_to_3a_after_1_5_resolved(self):
        """External API artifacts should trigger Phase 3A routing after Phase 1.5 resolved."""
        doc = _minimal_session_state(
            Scope={
                "ExternalAPIs": ["order-service-api.yaml"],
                "BusinessRules": "not-applicable",
            },
        )
        result = route_phase(
            requested_phase="2.1",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "3A-Activation"

    def test_phase_1_5_to_3a_when_apis_in_scope(self):
        """After Phase 1.5, route to Phase 3A if APIs in scope."""
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
        assert result.phase == "3A-Activation"
        assert result.source == "phase-1.5-to-3a"

    def test_phase_1_5_to_4_when_no_apis(self):
        """After Phase 1.5, route to Phase 4 if no APIs in scope."""
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
        assert result.phase == "4"
        assert result.source == "phase-1.5-to-4"

    def test_phase_3a_with_apis_stays_at_3a(self):
        """When Phase 3A is requested and APIs exist, stay at 3A."""
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
        assert result.phase == "3A"
        # When requested_phase matches persisted phase, source is "requested-with-evidence"
        assert result.source == "requested-with-evidence"

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
