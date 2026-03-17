from __future__ import annotations

from pathlib import Path
import json

import pytest

from governance.kernel.phase_kernel import RuntimeContext, execute, _deduplicate_criteria
from tests.util import get_phase_api_path


RULEBOOK_BASE = {
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
    "AddonsEvidence": {
        "riskTiering": {"status": "loaded"},
    },
}


def _write_phase_api(commands_home: Path) -> None:
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8")


def _write_plan_record(workspaces_home: Path, repo_fingerprint: str, *, status: str, versions: int) -> None:
    workspace = workspaces_home / repo_fingerprint
    workspace.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "versions": [{"version": idx + 1} for idx in range(max(0, versions))],
    }
    (workspace / "plan-record.json").write_text(json.dumps(payload), encoding="utf-8")


def test_phase_api_start_token_is_bootstrap_entrypoint() -> None:
    text = get_phase_api_path().read_text(encoding="utf-8")
    assert 'start_token: "0"' in text


def test_kernel_blocks_when_phase_api_missing(tmp_path: Path) -> None:
    result = execute(
        current_token="2.1",
        session_state_doc={"SESSION_STATE": {}},
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=tmp_path / "commands",
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "phase-api-missing"


def test_kernel_routes_2_1_to_1_5_when_business_rules_unresolved(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
        }
    }
    result = execute(
        current_token="2.1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "1.5-BusinessRules"
    assert result.source == "phase-1.5-routing-required"


def test_kernel_routes_2_1_to_1_5_when_business_rules_execute_decision_set(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "BusinessRules": {"Decision": "execute"},
        }
    }
    result = execute(
        current_token="2.1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "1.5-BusinessRules"
    assert result.source == "phase-1.5-routing-required"


def test_kernel_routes_2_1_to_1_5_when_business_rules_scope_unresolved(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "Scope": {"BusinessRules": "unresolved"},
            "BusinessRules": {
                "Inventory": {"sha256": "synthetic-hash"},
                "ExecutionEvidence": False,
            },
        }
    }
    result = execute(
        current_token="2.1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "1.5-BusinessRules"
    assert result.source == "phase-1.5-routing-required"


def test_kernel_phase4_does_not_route_with_intake_metadata_only(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "phase4_intake_evidence": True,
            "phase4_intake_source": "phase4-intake-bridge",
        }
    }
    result = execute(
        current_token="4",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Ticket Input Gate",
            requested_next_gate_condition="Collect ticket",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "4"
    assert result.source == "phase-4-awaiting-ticket-intake"


def test_kernel_phase4_does_not_route_with_feature_complexity_only(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "FeatureComplexity": {
                "Class": "STANDARD",
                "Reason": "classified",
                "PlanningDepth": "standard",
            },
        }
    }
    result = execute(
        current_token="4",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Ticket Input Gate",
            requested_next_gate_condition="Collect ticket",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "4"
    assert result.source == "phase-4-awaiting-ticket-intake"


def test_kernel_blocks_phase_1_3_when_exit_evidence_missing(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "1.3-RulebookLoad",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {},
            "AddonsEvidence": {},
        }
    }
    result = execute(
        current_token="1.3",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Rulebook Load Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "phase-exit-evidence-missing"


def test_kernel_blocks_with_invalid_spec_and_writes_block_event(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(
        """
version: 1
start_token: "1.1"
phases:
  - token: "1.1"
    phase: "1.1-Bootstrap"
    active_gate: "Workspace Ready Gate"
    next_gate_condition: "Continue"
    next: "unknown"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = execute(
        current_token="1.1",
        session_state_doc={"SESSION_STATE": {}},
        runtime_ctx=RuntimeContext(
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    rows = [
        json.loads(line)
        for line in (commands_home / "logs" / "flow.log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["event"] == "PHASE_BLOCKED"


@pytest.mark.governance
def test_kernel_blocks_phase_6_when_p6_prerequisites_fail(tmp_path: Path) -> None:
    """Phase 6 entry is blocked when P6 prerequisites are not met."""
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "Gates": {
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pending",
            },
        }
    }

    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Post Flight",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "p6-prerequisite-gate"
    assert "BLOCKED-P6-PREREQUISITES-NOT-MET" in result.next_gate_condition


@pytest.mark.governance
def test_kernel_allows_phase_6_when_p6_prerequisites_pass(tmp_path: Path) -> None:
    """Phase 6 entry continues when all wired P6 prerequisites are satisfied."""
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "BusinessRules": {"Inventory": {"sha256": "abc123"}},
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Post Flight",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "6-PostFlight"


@pytest.mark.governance
def test_kernel_phase_4_advances_to_5_when_ticket_evidence_present(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "Context: user-provided task\nTest Strategy: add regression coverage",
            "FeatureComplexity": {"Class": "STANDARD", "Reason": "ticket-present", "PlanningDepth": "standard"},
        }
    }

    result = execute(
        current_token="4",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Ticket Input Gate",
            requested_next_gate_condition="Collect ticket and planning constraints.",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "5-ArchitectureReview"
    assert result.source == "phase-4-to-5-ticket-intake"
    assert result.active_gate == "Plan Record Preparation Gate"


@pytest.mark.governance
def test_kernel_edge_normalizes_legacy_5_implementation_label_to_review_phase(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-Implementation",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "Gates": {
                "P5-Architecture": "pending",
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Implementation Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "5-ArchitectureReview"


@pytest.mark.governance
def test_kernel_phase5_requires_plan_record_before_architecture_review(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 0,
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "5-ArchitectureReview"
    assert result.next_token == "5"
    assert result.active_gate == "Plan Record Preparation Gate"
    assert result.source == "phase-5-plan-record-prep-required"


@pytest.mark.governance
def test_kernel_phase5_routes_to_architecture_review_when_plan_record_present(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Plan Record Preparation Gate",
            requested_next_gate_condition="Create plan",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "5-ArchitectureReview"
    assert result.next_token == "5"
    assert result.active_gate == "Architecture Review Gate"
    assert result.source == "phase-5-self-review-required"


@pytest.mark.governance
def test_kernel_phase5_uses_workspace_plan_record_when_state_versions_are_stale(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    workspaces_home = tmp_path / "workspaces"
    _write_phase_api(commands_home)
    repo_fingerprint = "abc123def456abc123def456"
    _write_plan_record(workspaces_home, repo_fingerprint, status="active", versions=1)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "RepoFingerprint": repo_fingerprint,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 0,
            "plan_record_status": "active",
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Plan Record Preparation Gate",
            requested_next_gate_condition="Create plan",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=workspaces_home,
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.active_gate == "Architecture Review Gate"
    assert result.plan_record_versions == 1
    assert result.plan_record_status == "active"


@pytest.mark.governance
def test_kernel_phase5_replaces_stale_phase4_condition_after_plan_record_persist(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    stale_phase4_condition = (
        "Ticket/task evidence captured; continue to Phase 5 plan-record preparation before architecture review"
    )
    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "active_gate": "Architecture Review Gate",
            "next_gate_condition": stale_phase4_condition,
            "Phase5Review": {
                "iteration": 0,
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition=stale_phase4_condition,
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.active_gate == "Architecture Review Gate"
    assert "iteration=0/3" in result.next_gate_condition
    assert "self_review_iterations_met=false" in result.next_gate_condition
    assert "Ticket/task evidence captured" not in result.next_gate_condition


@pytest.mark.governance
def test_kernel_phase5_prep_gate_condition_explicitly_requires_plan_persist(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 0,
            "Phase5Review": {
                "iteration": 0,
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Plan Record Preparation Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.active_gate == "Plan Record Preparation Gate"
    assert "Persist plan-record evidence via /plan" in result.next_gate_condition


@pytest.mark.governance
def test_kernel_phase5_ignores_stale_requested_gate_fields_and_recomputes_current_round(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    stale_phase4_condition = (
        "Ticket/task evidence captured; continue to Phase 5 plan-record preparation before architecture review"
    )
    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 0,
            # stale persisted fields from a previous run
            "active_gate": "Architecture Review Gate",
            "next_gate_condition": stale_phase4_condition,
            "Phase5Review": {"iteration": 0},
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition=stale_phase4_condition,
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.next_token == "5"
    assert result.active_gate == "Plan Record Preparation Gate"
    assert "Persist plan-record evidence via /plan" in result.next_gate_condition
    assert "Ticket/task evidence captured" not in result.next_gate_condition


@pytest.mark.governance
def test_kernel_phase5_status_active_without_valid_versions_stays_in_plan_prep(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_status": "active",
            "plan_record_versions": "invalid",
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.active_gate == "Plan Record Preparation Gate"
    assert result.plan_record_versions == 0


@pytest.mark.governance
def test_kernel_phase5_accepts_string_plan_record_versions(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": "1",
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Plan Record Preparation Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.active_gate == "Architecture Review Gate"
    assert result.plan_record_versions == 1


@pytest.mark.governance
def test_kernel_phase5_routing_is_deterministic_for_identical_input(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 2,
            "Phase5Review": {
                "iteration": 0,
            },
        }
    }
    runtime = RuntimeContext(
        requested_active_gate="Plan Record Preparation Gate",
        requested_next_gate_condition="Continue",
        repo_is_git_root=True,
        commands_home=commands_home,
        workspaces_home=tmp_path / "workspaces",
        config_root=tmp_path / "cfg",
    )

    first = execute(current_token="5", session_state_doc=doc, runtime_ctx=runtime)
    second = execute(current_token="5", session_state_doc=doc, runtime_ctx=runtime)

    assert first.active_gate == second.active_gate
    assert first.next_gate_condition == second.next_gate_condition
    assert first.next_token == second.next_token
    assert first.source == second.source


@pytest.mark.governance
def test_happy_phase5_early_stop_on_unchanged_plan_digest_after_first_iteration(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "Phase5Review": {
                "iteration": 1,
                "prev_plan_digest": "sha256:plan-v1",
                "curr_plan_digest": "sha256:plan-v1",
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "5-ArchitectureReview"
    assert result.next_token == "5.3"
    assert result.active_gate == "Architecture Review Gate"
    assert result.source == "phase-5-architecture-review-ready"


@pytest.mark.governance
def test_edge_phase5_hard_stop_on_max_iterations_even_when_digest_changes(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "Phase5Review": {
                "iteration": 3,
                "prev_plan_digest": "sha256:plan-v2",
                "curr_plan_digest": "sha256:plan-v3",
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "5-ArchitectureReview"
    assert result.next_token == "5.3"
    assert result.source == "phase-5-architecture-review-ready"


@pytest.mark.governance
def test_bad_phase5_first_iteration_without_previous_digest_cannot_early_stop(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "Phase5Review": {
                "iteration": 1,
                "curr_plan_digest": "sha256:plan-v1",
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "5-ArchitectureReview"
    assert result.next_token == "5"
    assert result.source == "phase-5-self-review-required"


@pytest.mark.governance
def test_phase5_explicit_completed_state_advances_even_without_iteration_digests(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "phase5_completed": True,
            "phase5_state": "phase5_completed",
            "phase5_completion_status": "phase5-completed",
            "Phase5Review": {
                "iteration": 0,
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.next_token == "5.3"
    assert result.source == "phase-5-architecture-review-ready"
    assert "completion_status=phase5-completed" in result.next_gate_condition


@pytest.mark.governance
def test_phase5_blocked_state_stays_in_architecture_review_and_emits_reason_code(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "phase5_state": "phase5_blocked",
            "phase5_blocker_code": "BLOCKED-P5-TICKET-EVIDENCE-MISSING",
            "Phase5Review": {
                "iteration": 1,
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.next_token == "5"
    assert result.source == "phase-5-self-review-required"
    assert "reason_code=BLOCKED-P5-TICKET-EVIDENCE-MISSING" in result.next_gate_condition


@pytest.mark.governance
def test_kernel_phase6_stays_until_implementation_review_complete(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "ImplementationReview": {
                "iteration": 0,
                "max_iterations": 3,
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Post Flight",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "6-PostFlight"
    assert result.next_token == "6"
    assert result.source == "phase-6-implementation-review-required"


@pytest.mark.governance
def test_kernel_phase6_ready_for_user_review_after_three_iterations(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "ImplementationReview": {
                "iteration": 3,
                "prev_impl_digest": "sha256:impl-v2",
                "curr_impl_digest": "sha256:impl-v3",
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Post Flight",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "6-PostFlight"
    assert result.next_token == "6"
    assert result.source == "phase-6-ready-for-user-review"


@pytest.mark.governance
def test_corner_phase6_allows_early_stop_on_unchanged_implementation_digest(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "ImplementationReview": {
                "iteration": 1,
                "prev_impl_digest": "sha256:impl-v1",
                "curr_impl_digest": "sha256:impl-v1",
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Post Flight",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "6-PostFlight"
    assert result.source == "phase-6-ready-for-user-review"


@pytest.mark.governance
def test_bad_phase6_first_iteration_without_previous_digest_cannot_early_stop(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "ImplementationReview": {
                "iteration": 1,
                "curr_impl_digest": "sha256:impl-v1",
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Post Flight",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.phase == "6-PostFlight"
    assert result.source == "phase-6-implementation-review-required"


@pytest.mark.governance
def test_edge_phase5_iteration_above_max_is_treated_as_hard_stop(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "Phase5Review": {
                "iteration": 99,
                "max_iterations": 3,
                "prev_plan_digest": "sha256:plan-v9",
                "curr_plan_digest": "sha256:plan-v10",
            },
        }
    }

    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.next_token == "5.3"
    assert result.source == "phase-5-architecture-review-ready"


@pytest.mark.governance
def test_edge_phase6_iteration_above_max_is_treated_as_hard_stop(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "ImplementationReview": {
                "iteration": 99,
                "max_iterations": 3,
                "prev_impl_digest": "sha256:impl-v9",
                "curr_impl_digest": "sha256:impl-v10",
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Post Flight",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    assert result.next_token == "6"
    assert result.source == "phase-6-ready-for-user-review"


@pytest.mark.governance
def test_replay_determinism_for_digest_based_review_decision(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "ticket-digest",
            "plan_record_versions": 1,
            "Phase5Review": {
                "iteration": 1,
                "prev_plan_digest": "sha256:plan-v1",
                "curr_plan_digest": "sha256:plan-v1",
            },
        }
    }

    first = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )
    second = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Review Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert first.phase == second.phase
    assert first.next_token == second.next_token
    assert first.active_gate == second.active_gate
    assert first.next_gate_condition == second.next_gate_condition
    assert first.source == second.source


@pytest.mark.governance
def test_e2eish_phase_path_from_ticket_to_phase6_review_ready(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)
    runtime = RuntimeContext(
        requested_active_gate="",
        requested_next_gate_condition="Continue",
        repo_is_git_root=True,
        commands_home=commands_home,
        workspaces_home=tmp_path / "workspaces",
        config_root=tmp_path / "cfg",
    )

    phase4_doc = {
        "SESSION_STATE": {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "Ticket": "Implement deterministic review loops",
            "TicketRecordDigest": "sha256:ticket-v1",
        }
    }
    r4 = execute(current_token="4", session_state_doc=phase4_doc, runtime_ctx=runtime)
    assert r4.source == "phase-4-to-5-ticket-intake"
    assert r4.next_token == "5"

    phase5_prep_doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "sha256:ticket-v1",
            "plan_record_versions": 0,
        }
    }
    r5prep = execute(current_token="5", session_state_doc=phase5_prep_doc, runtime_ctx=runtime)
    assert r5prep.source == "phase-5-plan-record-prep-required"
    assert r5prep.active_gate == "Plan Record Preparation Gate"

    phase5_review_done_doc = {
        "SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TicketRecordDigest": "sha256:ticket-v1",
            "plan_record_versions": 1,
            "Phase5Review": {
                "iteration": 1,
                "prev_plan_digest": "sha256:plan-v1",
                "curr_plan_digest": "sha256:plan-v1",
            },
        }
    }
    r5done = execute(current_token="5", session_state_doc=phase5_review_done_doc, runtime_ctx=runtime)
    assert r5done.source == "phase-5-architecture-review-ready"
    assert r5done.next_token == "5.3"

    phase53_doc = {
        "SESSION_STATE": {
            "Phase": "5.3-TestQuality",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "TechnicalDebt": {"Proposed": False},
            "RollbackRequired": False,
        }
    }
    r53 = execute(current_token="5.3", session_state_doc=phase53_doc, runtime_ctx=runtime)
    assert r53.source == "phase-5.3-to-6"
    assert r53.next_token == "6"

    phase6_doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
            "ImplementationReview": {
                "iteration": 1,
                "prev_impl_digest": "sha256:impl-v1",
                "curr_impl_digest": "sha256:impl-v1",
            },
        }
    }
    r6 = execute(current_token="6", session_state_doc=phase6_doc, runtime_ctx=runtime)
    assert r6.source == "phase-6-ready-for-user-review"
    assert r6.active_gate == "Evidence Presentation Gate"


# ────────────────────────────────────────────────────────────────────
# M6 Bug #2 — Criteria deduplication unit tests
# ────────────────────────────────────────────────────────────────────


class TestDeduplicateCriteriaUnit:
    """Unit tests for _deduplicate_criteria() — pure function, no kernel."""

    def test_no_duplicates_passes_through(self) -> None:
        """Criteria with unique keys are returned unchanged."""
        criteria = [
            {"criterion_key": "A", "critical": True, "artifact_kind": "foo"},
            {"criterion_key": "B", "critical": False, "artifact_kind": "bar"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 2
        assert result.had_duplicates is False
        assert result.conflicts == []

    def test_compatible_duplicates_merge_critical_to_true(self) -> None:
        """Same key, same artifact_kind, differing critical → True wins."""
        criteria = [
            {"criterion_key": "X", "critical": False, "artifact_kind": "scorecard"},
            {"criterion_key": "X", "critical": True, "artifact_kind": "scorecard"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1, (
            f"Expected 1 deduplicated criterion, got {len(result.criteria)}"
        )
        assert result.had_duplicates is True
        assert result.conflicts == []
        merged = result.criteria[0]
        assert merged["criterion_key"] == "X"
        assert merged["critical"] is True
        assert merged["artifact_kind"] == "scorecard"

    def test_compatible_duplicates_merge_threshold_to_strictest(self) -> None:
        """Same key, same artifact_kind, different static thresholds → higher wins."""
        criteria = [
            {"criterion_key": "T", "critical": True, "artifact_kind": "tier",
             "threshold": 60},
            {"criterion_key": "T", "critical": True, "artifact_kind": "tier",
             "threshold": 80},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert result.criteria[0]["threshold"] == 80

    def test_incompatible_artifact_kind_flagged_as_conflict(self) -> None:
        """Same key but different artifact_kind = semantic conflict."""
        criteria = [
            {"criterion_key": "C", "critical": True, "artifact_kind": "foo"},
            {"criterion_key": "C", "critical": True, "artifact_kind": "bar"},
        ]
        result = _deduplicate_criteria(criteria)
        # Conflict flagged, original entry kept.
        assert len(result.criteria) == 1
        assert len(result.conflicts) == 1
        assert "artifact_kind" in result.conflicts[0]
        assert result.had_duplicates is True

    def test_conflict_text_is_order_invariant(self) -> None:
        """Conflict description must be deterministic independent of input order."""
        a_then_b = [
            {"criterion_key": "C", "critical": True, "artifact_kind": "alpha"},
            {"criterion_key": "C", "critical": True, "artifact_kind": "beta"},
        ]
        b_then_a = [
            {"criterion_key": "C", "critical": True, "artifact_kind": "beta"},
            {"criterion_key": "C", "critical": True, "artifact_kind": "alpha"},
        ]

        result_a_then_b = _deduplicate_criteria(a_then_b)
        result_b_then_a = _deduplicate_criteria(b_then_a)

        assert result_a_then_b.conflicts == result_b_then_a.conflicts

    def test_incompatible_resolver_flagged_as_conflict(self) -> None:
        """Same key but different threshold_resolver = conflict."""
        criteria = [
            {"criterion_key": "R", "critical": True, "artifact_kind": "tier",
             "threshold_mode": "dynamic_by_risk_tier",
             "threshold_resolver": "dynamic_by_risk_tier"},
            {"criterion_key": "R", "critical": True, "artifact_kind": "tier",
             "threshold_mode": "static",
             "threshold_resolver": "static_resolver"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert len(result.conflicts) == 1
        assert "threshold_mode" in result.conflicts[0]

    def test_triple_duplicate_merges_to_single_entry(self) -> None:
        """Three compatible entries for the same key → one merged entry."""
        criteria = [
            {"criterion_key": "Z", "critical": False, "artifact_kind": "x"},
            {"criterion_key": "Z", "critical": False, "artifact_kind": "x"},
            {"criterion_key": "Z", "critical": True, "artifact_kind": "x"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert result.criteria[0]["critical"] is True
        assert result.had_duplicates is True

    def test_mixed_unique_and_duplicate_keys(self) -> None:
        """Mix of unique and duplicate keys: only duplicates are merged."""
        criteria = [
            {"criterion_key": "A", "critical": True, "artifact_kind": "alpha"},
            {"criterion_key": "B", "critical": False, "artifact_kind": "beta"},
            {"criterion_key": "A", "critical": False, "artifact_kind": "alpha"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 2
        keys = [c["criterion_key"] for c in result.criteria]
        assert "A" in keys
        assert "B" in keys
        a_entry = next(c for c in result.criteria if c["criterion_key"] == "A")
        assert a_entry["critical"] is True  # Merged: True wins

    def test_threshold_added_from_second_when_first_has_none(self) -> None:
        """If the first entry has no threshold and the second does, adopt it."""
        criteria = [
            {"criterion_key": "Q", "critical": True, "artifact_kind": "q"},
            {"criterion_key": "Q", "critical": True, "artifact_kind": "q",
             "threshold": 75},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert result.criteria[0]["threshold"] == 75

    def test_empty_input_returns_empty(self) -> None:
        result = _deduplicate_criteria([])
        assert result.criteria == []
        assert result.had_duplicates is False
        assert result.conflicts == []


# ────────────────────────────────────────────────────────────────────
# M6 Bug #2 — Integration: kernel produces deduplicated strict-exit results
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
def test_kernel_strict_exit_deduplicates_criteria(tmp_path: Path) -> None:
    """Duplicate criterion_key from multiple profiles → 1 result, not N.

    Scenario: Two phase_exit_contract entries for the same phase, each
    contributing the same criterion_key with the same artifact_kind but
    differing critical flags.  The kernel must:
    - Evaluate exactly 1 criterion (deduplicated, critical=True wins).
    - Report at most 1 reason code (not 2 duplicate codes).
    - Not inflate summary counts.
    """
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-Architecture",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            # Phase 1.3 foundation prerequisites.
            "BusinessRules": {"Decision": "skip", "Scope": "none"},
            "ExternalApiArtifacts": {},
            "PolicyMode": {"principal_strict": True},
            # Two profiles deliver the same criterion_key for the same phase.
            "phase_exit_contract": [
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "DUP-KEY-1",
                            "critical": False,
                            "artifact_kind": "test_artifact",
                        },
                    ],
                },
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "DUP-KEY-1",
                            "critical": True,
                            "artifact_kind": "test_artifact",
                        },
                    ],
                },
            ],
            # No evidence → the criterion will fail under strict mode.
            "BuildEvidence": {"items": []},
            "RiskTiering": {"ActiveTier": "Tier-high"},
            # Satisfy phase 5 exit evidence keys so we reach the strict gate.
            "Gates": {
                "P5.3-TestQuality": "compliant",
                "P5.4-BusinessRules": "compliant",
            },
            "TestQualityEvidence": {"status": "compliant"},
        }
    }
    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    # The gate should block (missing evidence under strict mode).
    assert result.status == "BLOCKED"
    assert result.source == "strict-exit-gate"

    # Read the JSONL event log to verify deduplicated criteria.
    flow_log = commands_home / "logs" / "flow.log.jsonl"
    assert flow_log.exists(), "Flow log should have been written"
    rows = [
        json.loads(line)
        for line in flow_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    block_events = [r for r in rows if r.get("event") == "PHASE_BLOCKED"]
    assert block_events, "Expected at least one PHASE_BLOCKED event"
    last_block = block_events[-1]
    detail = last_block.get("strict_exit_detail")
    assert detail is not None, "strict_exit_detail should be present in event"

    criteria_list = detail.get("criteria", [])
    # The key assertion: exactly 1 criterion result, not 2.
    assert len(criteria_list) == 1, (
        f"Expected 1 deduplicated criterion result, got {len(criteria_list)} "
        f"(duplicate bug if 2)"
    )
    # Merged critical=True must have won.
    assert criteria_list[0]["critical"] is True

    # Exactly 1 reason code (not duplicated).
    reason_codes_list = detail.get("reason_codes", [])
    assert len(reason_codes_list) == 1, (
        f"Expected 1 reason code, got {len(reason_codes_list)} "
        f"(inflated if >1)"
    )


@pytest.mark.governance
def test_kernel_strict_exit_blocks_on_incompatible_criteria_conflict(tmp_path: Path) -> None:
    """Incompatible criterion definitions under principal_strict → block.

    Two profiles define the same criterion_key but with different
    artifact_kind — this is a semantic conflict, not a mergeable duplicate.
    Under principal_strict the kernel must fail-closed.
    """
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-Architecture",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            **RULEBOOK_BASE,
            "BusinessRules": {"Decision": "skip", "Scope": "none"},
            "ExternalApiArtifacts": {},
            "PolicyMode": {"principal_strict": True},
            "phase_exit_contract": [
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "CONFLICT-KEY",
                            "critical": True,
                            "artifact_kind": "artifact_alpha",
                        },
                    ],
                },
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "CONFLICT-KEY",
                            "critical": True,
                            "artifact_kind": "artifact_beta",
                        },
                    ],
                },
            ],
            "BuildEvidence": {"items": []},
            "RiskTiering": {"ActiveTier": "Tier-high"},
            "Gates": {
                "P5.3-TestQuality": "compliant",
                "P5.4-BusinessRules": "compliant",
            },
            "TestQualityEvidence": {"status": "compliant"},
        }
    }
    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "strict-exit-gate"
    # The block reason must mention contract conflict.
    assert "contract conflict" in (result.next_gate_condition or "").lower()


# ---------------------------------------------------------------------------
# route_strategy surfacing on KernelResult
# ---------------------------------------------------------------------------

class TestKernelResultRouteStrategy:
    """Verify that KernelResult surfaces route_strategy from phase_api.yaml."""

    def test_phase_5_stay_strategy_surfaced(self, tmp_path: Path) -> None:
        """Happy: Phase 5 (route_strategy=stay) is surfaced on KernelResult."""
        commands_home = tmp_path / "commands"
        _write_phase_api(commands_home)
        doc = {
            "SESSION_STATE": {
                "Phase": "5-Review",
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                **RULEBOOK_BASE,
            }
        }
        result = execute(
            current_token="5",
            session_state_doc=doc,
            runtime_ctx=RuntimeContext(
                requested_active_gate="Architecture Gate",
                requested_next_gate_condition="Continue",
                repo_is_git_root=True,
                commands_home=commands_home,
                workspaces_home=tmp_path / "workspaces",
                config_root=tmp_path / "cfg",
            ),
        )
        assert result.route_strategy == "stay"

    def test_phase_4_next_strategy_surfaced(self, tmp_path: Path) -> None:
        """Happy: Phase 4 (route_strategy=next) is surfaced on KernelResult."""
        commands_home = tmp_path / "commands"
        _write_phase_api(commands_home)
        doc = {
            "SESSION_STATE": {
                "Phase": "4-Intake",
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                **RULEBOOK_BASE,
            }
        }
        result = execute(
            current_token="4",
            session_state_doc=doc,
            runtime_ctx=RuntimeContext(
                requested_active_gate="Entry Gate",
                requested_next_gate_condition="pick a ticket",
                repo_is_git_root=True,
                commands_home=commands_home,
                workspaces_home=tmp_path / "workspaces",
                config_root=tmp_path / "cfg",
            ),
        )
        assert result.route_strategy == "next"

    def test_blocked_early_returns_empty_route_strategy(self, tmp_path: Path) -> None:
        """Edge: Blocked result before spec load → route_strategy is empty string."""
        result = execute(
            current_token="2.1",
            session_state_doc={"SESSION_STATE": {}},
            runtime_ctx=RuntimeContext(
                requested_active_gate="Decision Pack",
                requested_next_gate_condition="Continue",
                repo_is_git_root=True,
                commands_home=tmp_path / "commands",
                workspaces_home=tmp_path / "workspaces",
                config_root=tmp_path / "cfg",
            ),
        )
        assert result.status == "BLOCKED"
        assert result.route_strategy == ""

    def test_route_strategy_is_string_type(self, tmp_path: Path) -> None:
        """Corner: route_strategy is always a string, never None."""
        commands_home = tmp_path / "commands"
        _write_phase_api(commands_home)
        doc = {
            "SESSION_STATE": {
                "Phase": "4-Intake",
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                **RULEBOOK_BASE,
            }
        }
        result = execute(
            current_token="4",
            session_state_doc=doc,
            runtime_ctx=RuntimeContext(
                requested_active_gate="Entry Gate",
                requested_next_gate_condition="pick a ticket",
                repo_is_git_root=True,
                commands_home=commands_home,
                workspaces_home=tmp_path / "workspaces",
                config_root=tmp_path / "cfg",
            ),
        )
        assert isinstance(result.route_strategy, str)


def test_phase6_routes_to_implementation_presentation_gate_when_package_ready(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)
    repo = "repo-impl-package"
    _write_plan_record(tmp_path / "workspaces", repo, status="active", versions=2)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "RepoFingerprint": repo,
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
            "implementation_package_presented": True,
            "implementation_quality_stable": True,
            "implementation_execution_status": "review_complete",
            "implementation_changed_files": [".governance/implementation/execution_patch.py"],
            **RULEBOOK_BASE,
        }
    }
    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Implementation Internal Review",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.active_gate == "Implementation Presentation Gate"
    assert result.source == "phase-6-implementation-presentation-ready"


def test_phase6_routes_to_implementation_blocked_when_blockers_present(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)
    repo = "repo-impl-blocked"
    _write_plan_record(tmp_path / "workspaces", repo, status="active", versions=2)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "RepoFingerprint": repo,
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
            "implementation_execution_status": "blocked",
            "implementation_hard_blockers": ["critical:IMPLEMENTATION-FOO:blocked"],
            **RULEBOOK_BASE,
        }
    }
    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Implementation Internal Review",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.active_gate == "Implementation Blocked"
    assert result.source == "phase-6-implementation-blocked"


def test_phase6_routes_to_implementation_accepted_after_external_decision(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)
    repo = "repo-impl-accepted"
    _write_plan_record(tmp_path / "workspaces", repo, status="active", versions=2)

    doc = {
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "RepoFingerprint": repo,
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
            "implementation_accepted": True,
            "implementation_status": "accepted",
            **RULEBOOK_BASE,
        }
    }
    result = execute(
        current_token="6",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Implementation Internal Review",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.active_gate == "Implementation Accepted"
    assert result.source == "phase-6-implementation-accepted"
