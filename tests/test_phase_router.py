"""Tests for governance.application.use_cases.phase_router routing logic."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from governance_runtime.application.use_cases.phase_router import (
    route_phase,
    _api_in_scope,
    _openapi_signal,
    _external_api_artifacts,
)
from tests.util import get_phase_api_path


@pytest.fixture(autouse=True)
def _kernel_binding_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    commands_home = cfg / "commands"
    workspaces_home = cfg / "workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "pythonCommand": sys.executable,
        },
    }
    (cfg / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    (commands_home / "phase_api.yaml").write_text(get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


def _minimal_session_state(**overrides) -> dict[str, object]:
    """Create minimal valid session state for testing."""
    return {
        "SESSION_STATE": {
            "phase": "2.1",
            "PersistenceCommitted": True,
            "workspace_ready_gate_committed": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.yml",
                "templates": "${COMMANDS_HOME}/master.md",
                "addons": {
                    "riskTiering": "${COMMANDS_HOME}/rulesets/profiles/rules.risk-tiering.yml",
                },
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.yml",
            },
            "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
            "RepoDiscovery": {
                "Completed": True,
                "RepoCacheFile": "${WORKSPACES_HOME}/repo-cache.yaml",
                "RepoMapDigestFile": "${WORKSPACES_HOME}/repo-map-digest.md",
            },
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
    def test_phase_1_2_routes_to_phase_1_3_automatically_when_workspace_ready(self):
        doc = _minimal_session_state(
            phase="1.2-ActivationIntent",
            Intent={"Path": "x", "Sha256": "y", "EffectiveScope": "repo"},
            Scope={"BusinessRules": "pending"},
        )
        result = route_phase(
            requested_phase="1.1-Bootstrap",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "1.2-ActivationIntent"
        assert result.source == "phase-transition-not-allowed"

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

    def test_phase_2_1_routes_to_1_5_when_business_rules_decision_is_execute(self):
        doc = _minimal_session_state(
            BusinessRules={"Decision": "execute"},
        )
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
            Scope={"BusinessRules": "gap-detected"},
            BusinessRules={"Outcome": "gap-detected", "ExecutionEvidence": True},
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

    def test_phase_2_1_skips_phase_1_5_when_business_rules_outcome_has_execution_evidence(self):
        doc = _minimal_session_state(
            Scope={"BusinessRules": "gap-detected"},
            BusinessRules={"Outcome": "gap-detected", "ExecutionEvidence": True},
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

    def test_phase_2_1_requires_phase_1_5_when_only_inventory_file_status_exists(self):
        doc = _minimal_session_state(
            BusinessRules={"InventoryFileStatus": "written"},
        )
        result = route_phase(
            requested_phase="2.1",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "1.5-BusinessRules"
        assert result.source == "phase-1.5-routing-required"

    def test_phase_2_1_requires_phase_1_5_when_only_p54_not_applicable_gate_exists(self):
        doc = _minimal_session_state(
            Gates={"P5.4-BusinessRules": "not-applicable"},
        )
        result = route_phase(
            requested_phase="2.1",
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "1.5-BusinessRules"
        assert result.source == "phase-1.5-routing-required"

    def test_phase_2_1_routes_to_3a_even_with_apis(self):
        """After Phase 2.1 with APIs detected, route to Phase 3A (same path, 3A decides next step)."""
        doc = _minimal_session_state(
            Scope={"BusinessRules": "gap-detected"},
            BusinessRules={"Outcome": "gap-detected", "ExecutionEvidence": True},
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
            BusinessRules={"Inventory": {"sha256": "abc123"}},
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
            BusinessRules={"Inventory": {"sha256": "abc123"}},
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
            APIInventory={"Status": "not-applicable"},
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
        assert "/continue" in result.next_gate_condition

    def test_phase_3a_with_apis_routes_to_3b1(self):
        """When Phase 3A has APIs in scope, route to Phase 3B-1 for logical validation."""
        doc = _minimal_session_state(
            phase="3A",
            AddonsEvidence={"openapi": {"detected": True}},
            APIInventory={"Status": "completed"},
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
            APIInventory={"Status": "completed"},
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
        assert "/continue" in result.next_gate_condition


@pytest.mark.governance
class TestPhase4Routing:
    def test_phase_4_stays_until_ticket_or_task_is_present(self):
        doc = _minimal_session_state(phase="4")
        result = route_phase(
            requested_phase="4",
            requested_active_gate="Ticket Input Gate",
            requested_next_gate_condition="Collect ticket",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "4"
        assert result.source == "phase-4-awaiting-ticket-intake"

    def test_phase_4_routes_to_5_when_ticket_digest_present(self):
        doc = _minimal_session_state(
            phase="4",
            TicketRecordDigest="Test Strategy: add integration coverage",
            FeatureComplexity={"Class": "STANDARD", "Reason": "ticket-provided", "PlanningDepth": "standard"},
        )
        result = route_phase(
            requested_phase="4",
            requested_active_gate="Ticket Input Gate",
            requested_next_gate_condition="Collect ticket",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "5-ArchitectureReview"
        assert result.source == "phase-4-to-5-ticket-intake"


@pytest.mark.governance
class TestPhase5Routing:
    def test_phase_5_routes_to_architecture_review_gate_when_plan_record_version_present(self):
        doc = _minimal_session_state(
            phase="5",
            plan_record_versions=1,
        )
        result = route_phase(
            requested_phase="5",
            requested_active_gate="Plan Record Preparation Gate",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "5-ArchitectureReview"
        assert result.active_gate == "Architecture Review Gate"
        assert result.plan_record_versions == 1

    def test_phase_5_stays_in_plan_prep_when_plan_record_status_active_but_version_missing(self):
        doc = _minimal_session_state(
            phase="5",
            plan_record_status="active",
        )
        result = route_phase(
            requested_phase="5",
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "5-ArchitectureReview"
        assert result.active_gate == "Plan Record Preparation Gate"

    def test_phase_5_3_routes_to_5_4_when_business_rules_executed(self):
        doc = _minimal_session_state(
            phase="5.3",
            BusinessRules={"Decision": "execute", "Inventory": {"sha256": "abc"}, "ExecutionEvidence": True},
        )
        result = route_phase(
            requested_phase="5.3",
            requested_active_gate="Test Quality Gate",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "5.4-BusinessRules"
        assert result.source == "phase-5.3-to-5.4"

    def test_phase_5_3_does_not_route_to_5_4_for_execute_decision_without_1_5_evidence(self):
        doc = _minimal_session_state(
            phase="5.3",
            BusinessRules={"Decision": "execute"},
        )
        result = route_phase(
            requested_phase="5.3",
            requested_active_gate="Test Quality Gate",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "6-PostFlight"
        assert result.source == "phase-5.3-to-6"

    def test_phase_5_3_routes_to_5_5_when_technical_debt_proposed(self):
        doc = _minimal_session_state(
            phase="5.3",
            TechnicalDebt={"Proposed": True},
        )
        result = route_phase(
            requested_phase="5.3",
            requested_active_gate="Test Quality Gate",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "5.5-TechnicalDebt"
        assert result.source == "phase-5.3-to-5.5"

    def test_phase_5_3_routes_to_6_when_optional_gates_not_required(self):
        doc = _minimal_session_state(
            phase="5.3",
        )
        result = route_phase(
            requested_phase="5.3",
            requested_active_gate="Test Quality Gate",
            requested_next_gate_condition="Continue",
            session_state_document=doc,
            repo_is_git_root=True,
        )
        assert result.phase == "6-PostFlight"
        assert result.source == "phase-5.3-to-6"


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
