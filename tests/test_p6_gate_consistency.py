"""Tests for Phase 6 gate consistency, P5.5 prerequisite, and review decision rail.

Covers:
1. P5.5 TechnicalDebt gate blocks Phase 6 when pending/rejected
2. P5.5 not-applicable / approved allows Phase 6 promotion
3. can_promote_to_phase6() is SSOT wrapper
4. /review-decision approve → workflow_complete terminal state
5. /review-decision changes_requested → Rework Clarification Gate in Phase 6
6. /review-decision reject → Phase 4 return
7. /review-decision invalid input → error
8. /review-decision outside Phase 6 → error
9. Evidence Presentation Gate guidance points to /review-decision
10. _normalize_phase6_p5_state() patches missing gates
11. Kernel routes workflow_approved / review_changes_requested / review_rejected transitions
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from governance.kernel.phase_kernel import RuntimeContext, execute
from governance.engine.gate_evaluator import (
    evaluate_p54_business_rules_gate,
    evaluate_p55_technical_debt_gate,
    evaluate_p6_prerequisites,
    can_promote_to_phase6,
    P55GateEvaluation,
    P6PrerequisiteEvaluation,
)
from governance.entrypoints.review_decision_persist import (
    apply_review_decision,
    VALID_DECISIONS,
)
from governance.entrypoints.session_reader import (
    _canonicalize_legacy_p5x_surface,
    _sync_conditional_p5_gate_states,
    _normalize_phase6_p5_state,
    _resolve_next_action_line,
    _should_emit_continue_next_action,
)


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

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

PERSISTENCE_BASE = {
    "PersistenceCommitted": True,
    "WorkspaceReadyGateCommitted": True,
    "WorkspaceArtifactsCommitted": True,
    "PointerVerified": True,
}

ALL_P5_GATES_PASSED = {
    "P5-Architecture": "approved",
    "P5.3-TestQuality": "pass",
    "P5.4-BusinessRules": "compliant",
    "P5.5-TechnicalDebt": "approved",
}


def _write_phase_api(commands_home: Path) -> None:
    repo_spec = Path(__file__).resolve().parents[1] / "phase_api.yaml"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(
        repo_spec.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _write_plan_record(workspaces_home: Path, fingerprint: str) -> None:
    workspace = workspaces_home / fingerprint
    workspace.mkdir(parents=True, exist_ok=True)
    payload = {"status": "persisted", "versions": [{"version": 1}]}
    (workspace / "plan-record.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _make_phase6_state(*, gates: dict | None = None, extra: dict | None = None) -> dict:
    """Build a SESSION_STATE document already in Phase 6."""
    review_object = "Final Phase-6 implementation review decision"
    review_ticket = "TASK-1"
    review_summary = "Approved plan summary"
    review_plan_body = "Approved plan body"
    review_scope = "Implement the approved plan record in this repository."
    review_constraints = "Governance guards remain active; implementation must follow the approved plan scope."
    review_semantics = (
        "approve=governance complete + implementation authorized; "
        "changes_requested=enter rework clarification gate; "
        "reject=return to phase 4 ticket input gate"
    )
    digest_source = "|".join(
        [
            review_object,
            review_ticket,
            review_summary,
            review_plan_body,
            review_scope,
            review_constraints,
            review_semantics,
        ]
    )

    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        **PERSISTENCE_BASE,
        **RULEBOOK_BASE,
        "Gates": gates or dict(ALL_P5_GATES_PASSED),
        "phase_transition_evidence": True,
        "TicketRecordDigest": "sha256:abc",
        "Ticket": "TASK-1",
        "Intent.Path": "/intent",
        "Intent.Sha256": "sha256:intent",
        "Intent.EffectiveScope": "full",
        "RepoDiscovery.Completed": True,
        "RepoDiscovery.RepoCacheFile": "/cache",
        "RepoDiscovery.RepoMapDigestFile": "/digest",
        "APIInventory.Status": "not-applicable",
        "BusinessRules": {
            "ExecutionEvidence": True,
            "Outcome": "not-applicable",
        },
        "ImplementationReview": {
            "iteration": 2,
            "max_iterations": 3,
            "min_self_review_iterations": 1,
            "revision_delta": "none",
        },
        "review_package_presented": True,
        "review_package_plan_body_present": True,
        "session_materialization_event_id": "mat-abc",
        "session_state_revision": 1,
        "session_materialized_at": "2026-03-12T00:00:00Z",
        "session_run_id": "sess-abc",
        "review_package_last_state_change_at": "2026-03-12T00:00:00Z",
        "review_package_review_object": review_object,
        "review_package_ticket": review_ticket,
        "review_package_approved_plan_summary": review_summary,
        "review_package_plan_body": review_plan_body,
        "review_package_implementation_scope": review_scope,
        "review_package_constraints": review_constraints,
        "review_package_decision_semantics": review_semantics,
        "review_package_presentation_receipt": {
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "content_digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
            "rendered_at": "2026-03-12T00:00:01Z",
            "render_event_id": "mat-abc",
            "gate": "Evidence Presentation Gate",
            "session_id": "sess-abc",
            "state_revision": "1",
            "source_command": "/continue",
            "digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
            "presented_at": "2026-03-12T00:00:00Z",
            "contract": "guided-ui.v1",
            "materialization_event_id": "mat-abc",
        },
    }
    if extra:
        state.update(extra)
    return state


def _make_ctx(tmp_path: Path, fingerprint: str = "fp-test") -> RuntimeContext:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)
    workspaces_home = tmp_path / "workspaces"
    _write_plan_record(workspaces_home, fingerprint)
    return RuntimeContext(
        requested_active_gate="Post Flight",
        requested_next_gate_condition="Continue",
        repo_is_git_root=True,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        config_root=tmp_path / "cfg",
        live_repo_fingerprint=fingerprint,
    )


def _write_session(tmp_path: Path, state: dict) -> Path:
    """Write a SESSION_STATE.json file and return its path."""
    session_path = tmp_path / "SESSION_STATE.json"
    doc = {"SESSION_STATE": state}
    session_path.write_text(json.dumps(doc), encoding="utf-8")
    return session_path


# ===========================================================================
# 1. P5.5 Technical Debt Gate — evaluate_p55_technical_debt_gate()
# ===========================================================================

class TestP55TechnicalDebtGate:
    """Tests for the standalone P5.5 gate evaluator."""

    def test_approved_gate_passes(self) -> None:
        state = {"Gates": {"P5.5-TechnicalDebt": "approved"}}
        result = evaluate_p55_technical_debt_gate(session_state=state)
        assert result.status == "approved"
        assert result.reason_code == "none"

    def test_not_applicable_gate_passes(self) -> None:
        state = {"Gates": {"P5.5-TechnicalDebt": "not-applicable"}}
        result = evaluate_p55_technical_debt_gate(session_state=state)
        assert result.status == "not-applicable"
        assert result.reason_code == "none"

    def test_rejected_gate_blocks(self) -> None:
        state = {"Gates": {"P5.5-TechnicalDebt": "rejected"}}
        result = evaluate_p55_technical_debt_gate(session_state=state)
        assert result.status == "rejected"
        assert result.reason_code == "BLOCKED-P5-5-TECHNICAL-DEBT-GATE"

    def test_no_gate_no_debt_proposed_is_not_applicable(self) -> None:
        state: dict = {"Gates": {}}
        result = evaluate_p55_technical_debt_gate(session_state=state)
        assert result.status == "not-applicable"
        assert result.technical_debt_proposed is False

    def test_no_gate_debt_proposed_is_pending(self) -> None:
        state = {"Gates": {}, "TechnicalDebtProposed": True}
        result = evaluate_p55_technical_debt_gate(session_state=state)
        assert result.status == "pending"
        assert result.technical_debt_proposed is True

    def test_no_gates_dict_at_all(self) -> None:
        """Edge case: Gates key missing entirely."""
        state = {"TechnicalDebt": {"Proposed": True}}
        result = evaluate_p55_technical_debt_gate(session_state=state)
        assert result.status == "pending"
        assert result.technical_debt_proposed is True

    def test_technical_debt_nested_proposed(self) -> None:
        """TechnicalDebt.Proposed=True variant."""
        state: dict = {"Gates": {}, "TechnicalDebt": {"Proposed": True}}
        result = evaluate_p55_technical_debt_gate(session_state=state)
        assert result.status == "pending"
        assert result.technical_debt_proposed is True


# ===========================================================================
# 2. P6 Prerequisites — P5.5 now always checked
# ===========================================================================

class TestP6PrerequisitesWithP55:
    """Verify that evaluate_p6_prerequisites() checks P5.5."""

    def test_all_gates_passed_including_p55(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "approved",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state,
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert result.passed is True
        assert result.p55_approved is True

    def test_p55_missing_blocks_p6(self) -> None:
        """P5.5 not set → p55_approved=False → blocks."""
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state,
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert result.passed is False
        assert result.p55_approved is False
        # P5.5 is the first open gate → gate-specific reason code (Fix 2 SSOT).
        assert result.reason_code == "BLOCKED-P5-5-TECHNICAL-DEBT-GATE"

    def test_p55_not_applicable_allows_p6(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass-with-exceptions",
            "P5.5-TechnicalDebt": "not-applicable",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state,
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert result.passed is True
        assert result.p55_approved is True

    def test_p55_rejected_blocks_p6(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "rejected",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state,
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert result.passed is False
        assert result.p55_approved is False

    def test_no_gates_mapping_blocks(self) -> None:
        """Edge: Gates key is not a mapping."""
        result = evaluate_p6_prerequisites(
            session_state={"Gates": "invalid"},
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert result.passed is False
        assert result.p55_approved is False


# ===========================================================================
# 3. can_promote_to_phase6() wrapper
# ===========================================================================

class TestCanPromoteToPhase6:
    """can_promote_to_phase6() is the single source of truth wrapper."""

    def test_returns_tuple(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "approved",
        }}
        can_promote, evaluation = can_promote_to_phase6(
            session_state=state,
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert can_promote is True
        assert isinstance(evaluation, P6PrerequisiteEvaluation)

    def test_blocked_returns_false(self) -> None:
        state = {"Gates": {"P5-Architecture": "approved"}}
        can_promote, evaluation = can_promote_to_phase6(
            session_state=state,
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert can_promote is False
        assert evaluation.passed is False


# ===========================================================================
# 4. Kernel: P5.5 blocks Phase 6 entry
# ===========================================================================

class TestKernelP55BlocksPhase6:
    """The kernel blocks Phase 6 when P5.5 is missing/rejected."""

    def test_kernel_blocks_phase6_without_p55(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(
            gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",  # satisfy P5.4 (fixture has ExecutionEvidence)
                # P5.5 missing!
            }
        )
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "BLOCKED"
        # P5.5 is the first open gate → gate-specific reason code in condition.
        assert "BLOCKED-P5-5-TECHNICAL-DEBT-GATE" in result.next_gate_condition

    def test_kernel_allows_phase6_with_p55_approved(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state()
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"


# ===========================================================================
# 5. Review Decision Entrypoint — apply_review_decision()
# ===========================================================================

class TestReviewDecisionApprove:
    """approve → workflow_complete terminal state."""

    def test_approve_sets_workflow_complete(self, tmp_path: Path) -> None:
        state = _make_phase6_state()
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )
        assert result["status"] == "ok"
        assert result["decision"] == "approve"

        # Verify persisted state
        doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = doc["SESSION_STATE"]
        assert ss["workflow_complete"] is True
        assert ss["WorkflowComplete"] is True
        assert ss["implementation_review_complete"] is True
        assert ss["UserReviewDecision"]["decision"] == "approve"

    def test_approve_writes_audit_event(self, tmp_path: Path) -> None:
        state = _make_phase6_state()
        session_path = _write_session(tmp_path, state)
        events_path = tmp_path / "events.jsonl"
        apply_review_decision(
            decision="approve",
            session_path=session_path,
            events_path=events_path,
            rationale="Looks good",
        )
        assert events_path.exists()
        event = json.loads(events_path.read_text(encoding="utf-8").strip())
        assert event["event"] == "REVIEW_DECISION"
        assert event["decision"] == "approve"
        assert event["rationale"] == "Looks good"


class TestReviewDecisionChangesRequested:
    """changes_requested → Rework Clarification Gate."""

    def test_changes_requested_resets_review(self, tmp_path: Path) -> None:
        state = _make_phase6_state(extra={"implementation_review_complete": True})
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="changes_requested",
            session_path=session_path,
        )
        assert result["status"] == "ok"
        assert "describe the requested changes" in str(result.get("next_action", ""))

        doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = doc["SESSION_STATE"]
        assert ss["implementation_review_complete"] is False
        assert ss["phase6_review_iterations"] == 0
        assert ss["active_gate"] == "Rework Clarification Gate"
        assert ss["phase6_state"] == "phase6_changes_requested"
        assert "Clarify requested changes" in ss["next_gate_condition"]
        assert ss["rework_clarification_consumed"] is False
        assert ss.get("workflow_complete") is None
        assert ss["UserReviewDecision"]["decision"] == "changes_requested"


class TestReviewDecisionReject:
    """reject → back to Phase 4."""

    def test_reject_returns_to_phase4(self, tmp_path: Path) -> None:
        state = _make_phase6_state()
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="reject",
            session_path=session_path,
        )
        assert result["status"] == "ok"
        assert "run /ticket" in str(result.get("next_action", ""))

        doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = doc["SESSION_STATE"]
        assert ss["Phase"] == "4"
        assert ss["phase"] == "4"
        assert ss["Next"] == "4"
        assert ss["next"] == "4"
        assert ss["phase_transition_evidence"] is False
        assert ss.get("workflow_complete") is None
        # Fix 4: reject sets active_gate and next_gate_condition, clears phase6_state.
        assert ss["active_gate"] == "Ticket Input Gate"
        assert "rejected" in ss["next_gate_condition"].lower()
        assert "phase6_state" not in ss

    def test_reject_overwrites_stale_lowercase_phase_to_4(self, tmp_path: Path) -> None:
        state = _make_phase6_state(extra={"phase": "6-PostFlight", "next": "6"})
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="reject",
            session_path=session_path,
        )
        assert result["status"] == "ok"

        doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = doc["SESSION_STATE"]
        assert ss["Phase"] == "4"
        assert ss["phase"] == "4"
        assert ss["Next"] == "4"
        assert ss["next"] == "4"


class TestReviewDecisionBadPaths:
    """Invalid decision, wrong phase, missing session."""

    def test_invalid_decision_rejected(self, tmp_path: Path) -> None:
        state = _make_phase6_state()
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="maybe",
            session_path=session_path,
        )
        assert result["status"] == "error"
        assert "BLOCKED-REVIEW-DECISION-INVALID" in str(result.get("reason_code", ""))

    def test_wrong_phase_rejected(self, tmp_path: Path) -> None:
        state = {
            "Phase": "5-ArchitectureReview",
            **PERSISTENCE_BASE,
            **RULEBOOK_BASE,
        }
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )
        assert result["status"] == "error"
        assert "Phase 6" in str(result.get("message", ""))

    def test_missing_session_file(self, tmp_path: Path) -> None:
        result = apply_review_decision(
            decision="approve",
            session_path=tmp_path / "does_not_exist.json",
        )
        assert result["status"] == "error"

    def test_empty_decision_string(self, tmp_path: Path) -> None:
        state = _make_phase6_state()
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="  ",
            session_path=session_path,
        )
        assert result["status"] == "error"

    def test_phase6_without_evidence_presentation_gate_rejected(self, tmp_path: Path) -> None:
        state = _make_phase6_state(extra={"active_gate": "Post Flight"})
        session_path = _write_session(tmp_path, state)
        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )
        assert result["status"] == "error"
        assert "Evidence Presentation Gate" in str(result.get("message", ""))


# ===========================================================================
# 6. Kernel: review decision routing transitions
# ===========================================================================

class TestKernelReviewDecisionRouting:
    """Kernel routes based on UserReviewDecision and workflow_complete."""

    def test_workflow_approved_routes_to_workflow_complete(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(extra={
            "workflow_complete": True,
            "WorkflowComplete": True,
            "UserReviewDecision": {"decision": "approve"},
        })
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"
        assert result.active_gate == "Workflow Complete"

    def test_changes_requested_routes_to_rework_clarification_gate(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(extra={
            "active_gate": "Evidence Presentation Gate",
            "phase6_state": "phase6_changes_requested",
            "UserReviewDecision": {"decision": "changes_requested"},
            "implementation_review_complete": False,
            "ImplementationReview": {
                "iteration": 0,
                "max_iterations": 3,
                "min_self_review_iterations": 1,
                "revision_delta": "changed",
                "implementation_review_complete": False,
            },
        })
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"
        assert result.active_gate == "Rework Clarification Gate"

    def test_reject_routes_to_phase4(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(extra={
            "UserReviewDecision": {"decision": "reject"},
        })
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"
        # reject transition routes to Phase 4
        assert result.next_token == "4"

    def test_edge_stale_reject_in_non_evidence_gate_does_not_reroute_to_phase4(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(extra={
            "active_gate": "Implementation Internal Review",
            "UserReviewDecision": {"decision": "reject"},
            "implementation_review_complete": False,
            "ImplementationReview": {
                "iteration": 0,
                "max_iterations": 3,
                "min_self_review_iterations": 1,
                "revision_delta": "changed",
                "implementation_review_complete": False,
            },
        })
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"
        assert result.next_token == "6"
        assert result.active_gate == "Implementation Internal Review"

    def test_corner_stale_changes_requested_in_non_evidence_gate_keeps_phase6_progression(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(extra={
            "active_gate": "Post Flight",
            "UserReviewDecision": {"decision": "changes_requested"},
            "implementation_review_complete": True,
            "ImplementationReview": {
                "iteration": 3,
                "max_iterations": 3,
                "min_self_review_iterations": 1,
                "revision_delta": "none",
                "implementation_review_complete": True,
            },
        })
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"
        assert result.next_token == "6"
        assert result.active_gate == "Evidence Presentation Gate"

    def test_happy_rework_pending_state_keeps_clarification_gate(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(extra={
            "active_gate": "Rework Clarification Gate",
            "phase6_state": "phase6_changes_requested",
            "implementation_review_complete": False,
            "UserReviewDecision": {"decision": "changes_requested"},
        })
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"
        assert result.active_gate == "Rework Clarification Gate"

    def test_edge_consumed_rework_state_does_not_reenter_clarification_gate(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(extra={
            "active_gate": "Post Flight",
            "phase6_state": "phase6_changes_requested",
            "rework_clarification_consumed": True,
            "implementation_review_complete": False,
            "ImplementationReview": {
                "iteration": 0,
                "max_iterations": 3,
                "min_self_review_iterations": 1,
                "revision_delta": "changed",
                "implementation_review_complete": False,
            },
        })
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "OK"
        assert result.active_gate == "Implementation Internal Review"


# ===========================================================================
# 7. Session Reader: _normalize_phase6_p5_state
# ===========================================================================

class TestNormalizePhase6P5State:
    """_normalize_phase6_p5_state() patches missing gate values."""

    def test_patches_missing_p55_gate(self) -> None:
        """When P5.5 is absent, the gate is not in Gates dict at all —
        normalization skips absent gates (they're conditionally not-applicable).
        Only gates PRESENT with non-terminal values are flagged."""
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                # P5.5 absent — normalization skips absent gates
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        # Absent gates are NOT patched — only present non-terminal gates are flagged.
        assert "P5.5-TechnicalDebt" not in state_doc["SESSION_STATE"]["Gates"]
        # No inconsistency flagged because all present gates are terminal.
        assert "_p6_state_normalization" not in state_doc["SESSION_STATE"]

    def test_does_not_patch_when_gates_present(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        assert "_p6_state_normalization" not in state_doc["SESSION_STATE"]

    def test_no_op_for_non_phase6(self) -> None:
        state_doc = {"SESSION_STATE": {"Phase": "5-ArchitectureReview", "Gates": {}}}
        _normalize_phase6_p5_state(state_doc=state_doc)
        assert "P5.5-TechnicalDebt" not in state_doc["SESSION_STATE"].get("Gates", {})

    def test_creates_gates_dict_if_missing(self) -> None:
        """When Gates key is missing entirely, normalization creates
        the dict but does NOT populate absent gates.  The empty Gates dict
        has no present non-terminal values to flag."""
        state_doc = {"SESSION_STATE": {"Phase": "6-PostFlight"}}
        _normalize_phase6_p5_state(state_doc=state_doc)
        assert "Gates" in state_doc["SESSION_STATE"]
        gates = state_doc["SESSION_STATE"]["Gates"]
        # Empty dict — no gates were present, so nothing to flag.
        assert len(gates) == 0
        assert "_p6_state_normalization" not in state_doc["SESSION_STATE"]


# ===========================================================================
# 8. Session Reader: Evidence Presentation Gate guidance
# ===========================================================================

class TestEvidencePresentationGateGuidance:
    """_resolve_next_action_line directs to /review-decision at Evidence Presentation Gate."""

    def test_evidence_gate_recommends_review_decision(self) -> None:
        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "status": "OK",
            "next_gate_condition": "Present evidence and submit via /review-decision.",
            "implementation_review_complete": True,
        }
        line = _resolve_next_action_line(snapshot)
        assert "/review-decision" in line

    def test_workflow_complete_returns_terminal_next_action(self) -> None:
        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Workflow Complete",
            "status": "OK",
            "next_gate_condition": "Workflow approved.",
        }
        line = _resolve_next_action_line(snapshot)
        assert line == (
            "Next action: run /implement."
        )

    def test_should_not_emit_continue_for_review_decision(self) -> None:
        snapshot = {
            "status": "OK",
            "next_gate_condition": "Submit final review decision via /review-decision (approve | changes_requested | reject).",
        }
        assert _should_emit_continue_next_action(snapshot) is False


# ===========================================================================
# 9. REGRESSION: _normalize_phase6_p5_state() fail-closed semantics
# ===========================================================================

class TestNormalizePhase6P5StateFailClosed:
    """Verify fail-closed normalization: present non-terminal gates are
    flagged (not silently back-filled to not-applicable)."""

    def test_present_non_terminal_gate_is_flagged_and_state_reset(self) -> None:
        """A gate with a non-terminal value (e.g. 'pending') triggers
        fail-closed reset: phase6_state, implementation_review_complete,
        active_gate are written; workflow_complete is removed."""
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "phase6_state": "implementation_review_pending",
            "implementation_review_complete": True,
            "workflow_complete": True,
            "WorkflowComplete": True,
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pending",  # non-terminal
                "P5.5-TechnicalDebt": "approved",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        norm = ss["_p6_state_normalization"]
        assert "P5.3-TestQuality" in norm["open_gates"]
        assert norm["first_open_gate"] == "P5.3-TestQuality"
        assert norm["blocking_reason_code"] == "BLOCKED-P5-3-TEST-QUALITY-GATE"
        assert norm["action"] == "fail-closed-reset-to-p5"
        # Gate value is NOT overwritten.
        assert ss["Gates"]["P5.3-TestQuality"] == "pending"
        # Fail-closed reset fields:
        assert ss["Phase"] == "5.3-TestQuality"
        assert ss["Next"] == "5.3"
        assert ss["phase6_state"] == "phase5_in_progress"
        assert ss["implementation_review_complete"] is False
        assert ss["active_gate"] == "Test Quality Gate"
        assert "Test Quality Gate" in ss["next_gate_condition"]
        assert "workflow_complete" not in ss
        assert "WorkflowComplete" not in ss

    def test_multiple_open_gates_reported_in_order(self) -> None:
        """All non-terminal gates are listed; first_open_gate is deterministic.
        Fail-closed reset active_gate matches first_open_gate."""
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "fail",
                "P5.4-BusinessRules": "gap-detected",
                "P5.5-TechnicalDebt": "rejected",
                "P5.6-RollbackSafety": "rejected",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        norm = ss["_p6_state_normalization"]
        assert norm["first_open_gate"] == "P5-Architecture"
        assert len(norm["open_gates"]) >= 4
        # P5-Architecture has no gate-specific code — falls back to generic.
        assert norm["blocking_reason_code"] == "BLOCKED-P6-PREREQUISITES-NOT-MET"
        assert norm["action"] == "fail-closed-reset-to-p5"
        # Fail-closed reset:
        assert ss["Phase"] == "5-ArchitectureReview"
        assert ss["Next"] == "5"
        assert ss["phase6_state"] == "phase5_in_progress"
        assert ss["active_gate"] == "Architecture Review Gate"

    def test_normalization_writes_context_fields(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pending",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        norm = state_doc["SESSION_STATE"]["_p6_state_normalization"]
        assert norm["reason"] == "WARN-P6-STATE-INCONSISTENCY"
        assert norm["original_phase"] == "6-PostFlight"
        assert norm["original_next"] == "6"
        assert norm["corrected_phase"] == "5.3-TestQuality"
        assert norm["corrected_next"] == "5.3"
        assert norm["corrected_active_gate"] == "Test Quality Gate"

    def test_normalization_writes_warning_event_when_events_path_provided(self, tmp_path: Path) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.5-TechnicalDebt": "rejected",
            },
        }}
        events_path = tmp_path / "events.jsonl"
        _normalize_phase6_p5_state(state_doc=state_doc, events_path=events_path)
        assert events_path.exists()
        event = json.loads(events_path.read_text(encoding="utf-8").splitlines()[-1])
        assert event["event"] == "P6_STATE_NORMALIZED"
        assert event["reason_code"] == "WARN-P6-STATE-INCONSISTENCY"
        assert event["first_open_gate"] == "P5.5-TechnicalDebt"
        assert event["corrected_phase"] == "5.5-TechnicalDebt"
        assert event["corrected_next"] == "5.5"

    def test_fail_closed_routes_p54_to_canonical_phase(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "pending",
                "P5.5-TechnicalDebt": "approved",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5.4-BusinessRules"
        assert ss["Next"] == "5.4"
        assert ss["active_gate"] == "Business Rules Validation"

    def test_fail_closed_routes_p56_to_canonical_phase(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "approved",
                "P5.6-RollbackSafety": "pending",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5.6-RollbackSafety"
        assert ss["Next"] == "5.6"
        assert ss["active_gate"] == "Rollback Safety Review"

    def test_all_gates_terminal_no_flag(self) -> None:
        """When every present gate is terminal, no normalization flag."""
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass-with-exceptions",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "not-applicable",
                "P5.6-RollbackSafety": "approved",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        assert "_p6_state_normalization" not in state_doc["SESSION_STATE"]

    def test_fail_closed_uses_p54_evaluator_even_when_gate_is_stale_compliant(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 2,
                "InvalidRuleCount": 1,
                "DroppedCandidateCount": 0,
                "ValidationReasonCodes": ["BUSINESS_RULES_INVALID_CONTENT"],
                "ValidationReport": {
                    "is_compliant": False,
                    "has_invalid_rules": True,
                    "has_render_mismatch": False,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "invalid_rule_count": 1,
                    "dropped_candidate_count": 0,
                    "count_consistent": True,
                },
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",  # stale
                "P5.5-TechnicalDebt": "approved",
            },
        }}

        _normalize_phase6_p5_state(state_doc=state_doc)

        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5.4-BusinessRules"
        assert ss["Next"] == "5.4"
        assert ss["active_gate"] == "Business Rules Validation"
        assert ss["phase6_state"] == "phase5_in_progress"

    def test_rework_state_does_not_bypass_p54_failure(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Next": "6",
            "phase6_state": "phase6_changes_requested",
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 2,
                "InvalidRuleCount": 1,
                "DroppedCandidateCount": 1,
                "ValidationReasonCodes": [
                    "BUSINESS_RULES_INVALID_CONTENT",
                    "BUSINESS_RULES_RENDER_MISMATCH",
                ],
                "ValidationReport": {
                    "is_compliant": False,
                    "has_invalid_rules": True,
                    "has_render_mismatch": True,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "invalid_rule_count": 1,
                    "dropped_candidate_count": 1,
                    "count_consistent": False,
                },
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",  # stale
                "P5.5-TechnicalDebt": "approved",
            },
        }}

        _normalize_phase6_p5_state(state_doc=state_doc)

        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5.4-BusinessRules"
        assert ss["phase6_state"] == "phase5_in_progress"
        assert "BLOCKED-P5-4-BUSINESS-RULES-GATE" in ss["next_gate_condition"]


class TestConditionalP5GateSync:
    def test_happy_sync_p54_pending_to_compliant(self) -> None:
        state_doc = {"SESSION_STATE": {
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 5,
                "ValidationReport": {
                    "is_compliant": True,
                    "has_invalid_rules": False,
                    "has_render_mismatch": False,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "has_code_extraction": True,
                    "code_extraction_sufficient": True,
                    "has_code_coverage_gap": False,
                    "has_code_doc_conflict": False,
                },
            },
            "Gates": {
                "P5.4-BusinessRules": "pending",
                "P5.5-TechnicalDebt": "pending",
                "P5.6-RollbackSafety": "pending",
            },
        }}
        _sync_conditional_p5_gate_states(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        assert ss["Gates"]["P5.4-BusinessRules"] == "compliant"
        assert ss["Gates"]["P5.5-TechnicalDebt"] == "not-applicable"
        assert ss["Gates"]["P5.6-RollbackSafety"] == "not-applicable"

    def test_edge_sync_keeps_non_pending_value(self) -> None:
        state_doc = {"SESSION_STATE": {
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 2,
            },
            "Gates": {
                "P5.4-BusinessRules": "rejected",
            },
        }}
        _sync_conditional_p5_gate_states(state_doc=state_doc)
        assert state_doc["SESSION_STATE"]["Gates"]["P5.4-BusinessRules"] == "rejected"

    def test_corner_sync_without_gates_dict_is_noop(self) -> None:
        state_doc = {"SESSION_STATE": {"BusinessRules": {"Outcome": "extracted"}}}
        _sync_conditional_p5_gate_states(state_doc=state_doc)
        assert "Gates" not in state_doc["SESSION_STATE"]

    def test_bad_sync_p54_pending_to_gap_detected(self) -> None:
        state_doc = {"SESSION_STATE": {
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": False,
                "ExtractedCount": 0,
            },
            "Gates": {
                "P5.4-BusinessRules": "pending",
            },
        }}
        _sync_conditional_p5_gate_states(state_doc=state_doc)
        assert state_doc["SESSION_STATE"]["Gates"]["P5.4-BusinessRules"] == "gap-detected"

    def test_fail_closed_resets_phase5_completed_when_p54_fails(self) -> None:
        state_doc = {"SESSION_STATE": {
            "phase5_completed": True,
            "phase5_state": "phase5_completed",
            "Phase5State": "phase5_completed",
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 2,
                "InvalidRuleCount": 1,
                "DroppedCandidateCount": 0,
                "ValidationReasonCodes": ["BUSINESS_RULES_INVALID_CONTENT"],
                "ValidationReport": {
                    "is_compliant": False,
                    "has_invalid_rules": True,
                    "has_render_mismatch": False,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "invalid_rule_count": 1,
                    "dropped_candidate_count": 0,
                    "count_consistent": True,
                },
            },
            "Gates": {
                "P5.4-BusinessRules": "pending",
                "P5.5-TechnicalDebt": "pending",
                "P5.6-RollbackSafety": "pending",
            },
        }}

        _sync_conditional_p5_gate_states(state_doc=state_doc)

        ss = state_doc["SESSION_STATE"]
        assert ss["Gates"]["P5.4-BusinessRules"] == "gap-detected"
        assert ss["phase5_completed"] is False
        assert ss["phase5_state"] == "phase5-in-progress"


class TestCanonicalizeLegacyP5xSurface:
    def test_happy_p54_legacy_surface_is_canonicalized(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "phase": "5-ArchitectureReview",
            "Next": "5.4",
            "active_gate": "Business Rules Compliance Gate",
            "next_gate_condition": "Phase 6 promotion blocked: BLOCKED-P5-4-BUSINESS-RULES-GATE",
        }}
        _canonicalize_legacy_p5x_surface(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5.4-BusinessRules"
        assert ss["Next"] == "5.4"
        assert ss["active_gate"] == "Business Rules Validation"

    def test_edge_p55_legacy_surface_is_canonicalized(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "Next": "5.5",
            "active_gate": "Technical Debt Gate",
        }}
        _canonicalize_legacy_p5x_surface(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5.5-TechnicalDebt"
        assert ss["Next"] == "5.5"
        assert ss["active_gate"] == "Technical Debt Review"

    def test_corner_non_legacy_phase_unchanged(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "5.4-BusinessRules",
            "Next": "5.4",
            "active_gate": "Business Rules Validation",
        }}
        _canonicalize_legacy_p5x_surface(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5.4-BusinessRules"
        assert ss["active_gate"] == "Business Rules Validation"

    def test_bad_unknown_legacy_gate_keeps_architecture_surface(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "5-ArchitectureReview",
            "Next": "5",
            "active_gate": "Architecture Review Gate",
        }}
        _canonicalize_legacy_p5x_surface(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        assert ss["Phase"] == "5-ArchitectureReview"
        assert ss["active_gate"] == "Architecture Review Gate"

    def test_p54_not_applicable_is_terminal(self) -> None:
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "not-applicable",
                "P5.5-TechnicalDebt": "approved",
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        assert "_p6_state_normalization" not in state_doc["SESSION_STATE"]


# ===========================================================================
# 10. REGRESSION: evaluate_p6_prerequisites() first-open-gate
# ===========================================================================

class TestP6PrerequisitesFirstOpenGate:
    """Verify deterministic first-open-gate extraction."""

    def test_first_open_gate_is_p53(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "fail",
            "P5.5-TechnicalDebt": "rejected",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=False,
        )
        assert result.first_open_gate == "P5.3-TestQuality"

    def test_first_open_gate_is_p54(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.4-BusinessRules": "gap-detected",
            "P5.5-TechnicalDebt": "approved",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=True, rollback_safety_applies=False,
        )
        assert result.first_open_gate == "P5.4-BusinessRules"

    def test_first_open_gate_is_p55(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "rejected",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=False,
        )
        assert result.first_open_gate == "P5.5-TechnicalDebt"

    def test_first_open_gate_is_p56(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "approved",
            "P5.6-RollbackSafety": "rejected",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=True,
        )
        assert result.first_open_gate == "P5.6-RollbackSafety"

    def test_first_open_gate_is_p5_architecture(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "pending",
            "P5.3-TestQuality": "fail",
            "P5.5-TechnicalDebt": "rejected",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=False,
        )
        assert result.first_open_gate == "P5-Architecture"

    def test_all_passed_no_first_open_gate(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "approved",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=False,
        )
        assert result.passed is True
        assert result.first_open_gate is None


# ===========================================================================
# 11. REGRESSION: phase_kernel surfaces specific first open gate
# ===========================================================================

class TestKernelSurfacesFirstOpenGate:
    """Kernel P6 blocking message includes the specific first open gate."""

    def test_kernel_p6_block_includes_first_open_gate(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(
            gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "fail",  # first open gate
                "P5.5-TechnicalDebt": "approved",
            }
        )
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "BLOCKED"
        assert "P5.3-TestQuality" in result.next_gate_condition

    def test_kernel_p6_block_p55_specific(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(
            gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "rejected",
            }
        )
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "BLOCKED"
        assert "P5.5-TechnicalDebt" in result.next_gate_condition


# ===========================================================================
# 12. REGRESSION: review_decision_persist approve writes terminal fields
# ===========================================================================

class TestReviewDecisionApproveTerminalFields:
    """approve writes active_gate and next_gate_condition into state."""

    def test_approve_writes_active_gate(self, tmp_path: Path) -> None:
        state = _make_phase6_state()
        session_path = _write_session(tmp_path, state)
        apply_review_decision(decision="approve", session_path=session_path)

        doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = doc["SESSION_STATE"]
        assert ss["active_gate"] == "Workflow Complete"
        assert "implementation is authorized" in ss["next_gate_condition"]
        assert ss["phase6_state"] == "phase6_completed"
        # Fix 4: approve also writes implementation_review_complete and
        # syncs ImplementationReview block.
        assert ss["implementation_review_complete"] is True
        review_block = ss.get("ImplementationReview")
        assert isinstance(review_block, dict)
        assert review_block["implementation_review_complete"] is True
        assert review_block["completion_status"] == "phase6-completed"

    def test_changes_requested_does_not_write_terminal_fields(self, tmp_path: Path) -> None:
        state = _make_phase6_state()
        session_path = _write_session(tmp_path, state)
        apply_review_decision(decision="changes_requested", session_path=session_path)

        doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = doc["SESSION_STATE"]
        assert ss.get("active_gate") != "Workflow Complete"


# ===========================================================================
# 13. Gate-specific reason codes (Fix 2 / Fix 3)
# ===========================================================================

class TestGateSpecificReasonCodes:
    """evaluate_p6_prerequisites() returns gate-specific reason_code based
    on first_open_gate, not generic BLOCKED-P6-PREREQUISITES-NOT-MET."""

    def test_p53_specific_reason_code(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "fail",
            "P5.5-TechnicalDebt": "approved",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=False,
        )
        assert result.reason_code == "BLOCKED-P5-3-TEST-QUALITY-GATE"

    def test_p54_specific_reason_code(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.4-BusinessRules": "gap-detected",
            "P5.5-TechnicalDebt": "approved",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=True, rollback_safety_applies=False,
        )
        assert result.reason_code == "BLOCKED-P5-4-BUSINESS-RULES-GATE"

    def test_p55_specific_reason_code(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "rejected",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=False,
        )
        assert result.reason_code == "BLOCKED-P5-5-TECHNICAL-DEBT-GATE"


class TestP54BusinessRulesGateWiring:
    """P5.4 should derive from hydrated BusinessRules state, not stale gates."""

    def test_happy_extracted_hydrated_state_is_compliant(self) -> None:
        state = {
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 3,
                "ValidationReport": {
                    "is_compliant": True,
                    "has_invalid_rules": False,
                    "has_render_mismatch": False,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "has_code_extraction": True,
                    "code_extraction_sufficient": True,
                    "has_code_coverage_gap": False,
                    "has_code_doc_conflict": False,
                },
            },
            "Gates": {"P5.4-BusinessRules": "pending"},
        }
        result = evaluate_p54_business_rules_gate(
            session_state=state,
            phase_1_5_executed=True,
        )
        assert result.status == "compliant"
        assert result.reason_code == "none"

    def test_corner_not_applicable_with_evidence_passes(self) -> None:
        state = {
            "BusinessRules": {
                "Outcome": "not-applicable",
                "ExecutionEvidence": True,
                "InventoryLoaded": False,
                "ExtractedCount": 0,
            }
        }
        result = evaluate_p54_business_rules_gate(
            session_state=state,
            phase_1_5_executed=True,
        )
        assert result.status == "not-applicable"

    def test_edge_phase_1_5_not_executed_is_not_applicable(self) -> None:
        state = {"BusinessRules": {"Outcome": "extracted", "ExecutionEvidence": True, "InventoryLoaded": True, "ExtractedCount": 2}}
        result = evaluate_p54_business_rules_gate(
            session_state=state,
            phase_1_5_executed=False,
        )
        assert result.status == "not-applicable"

    def test_bad_extracted_without_inventory_is_gap_detected(self) -> None:
        state = {
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": False,
                "ExtractedCount": 0,
            }
        }
        result = evaluate_p54_business_rules_gate(
            session_state=state,
            phase_1_5_executed=True,
        )
        assert result.status == "gap-detected"
        assert result.reason_code == "BLOCKED-P5-4-BUSINESS-RULES-GATE"

    def test_p6_prerequisites_use_evaluated_p54_over_stale_gate(self) -> None:
        state = {
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "pending",
                "P5.5-TechnicalDebt": "approved",
            },
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 2,
                "ValidationReport": {
                    "is_compliant": True,
                    "has_invalid_rules": False,
                    "has_render_mismatch": False,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "has_code_extraction": True,
                    "code_extraction_sufficient": True,
                    "has_code_coverage_gap": False,
                    "has_code_doc_conflict": False,
                },
            },
        }
        result = evaluate_p6_prerequisites(
            session_state=state,
            phase_1_5_executed=True,
            rollback_safety_applies=False,
        )
        assert result.p54_compliant is True
        assert result.passed is True

    def test_p56_specific_reason_code(self) -> None:
        state = {"Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "approved",
            "P5.6-RollbackSafety": "rejected",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=True,
        )
        assert result.reason_code == "BLOCKED-P5-6-ROLLBACK-SAFETY-GATE"

    def test_p5_architecture_falls_back_to_generic(self) -> None:
        """P5-Architecture has no gate-specific code — uses the generic fallback."""
        state = {"Gates": {
            "P5-Architecture": "pending",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "approved",
        }}
        result = evaluate_p6_prerequisites(
            session_state=state, phase_1_5_executed=False, rollback_safety_applies=False,
        )
        assert result.reason_code == "BLOCKED-P6-PREREQUISITES-NOT-MET"


# ===========================================================================
# 14. Kernel surfaces gate-specific reason code (Fix 3)
# ===========================================================================

class TestKernelGateSpecificReasonCode:
    """Kernel P6 blocking uses the evaluator's gate-specific reason code."""

    def test_kernel_p53_gate_specific_in_condition(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(
            gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "fail",
                "P5.5-TechnicalDebt": "approved",
            }
        )
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "BLOCKED"
        assert "BLOCKED-P5-3-TEST-QUALITY-GATE" in result.next_gate_condition

    def test_kernel_architecture_uses_generic(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        state = _make_phase6_state(
            gates={
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            }
        )
        result = execute(
            current_token="6",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
        )
        assert result.status == "BLOCKED"
        assert "BLOCKED-P6-PREREQUISITES-NOT-MET" in result.next_gate_condition


# ===========================================================================
# 15. SSOT: normalization imports from gate_evaluator (cross-cutting)
# ===========================================================================

class TestNormalizationSSOT:
    """Verify normalization uses the same gate ordering and terminal values
    as evaluate_p6_prerequisites() (SSOT cross-cutting constraint)."""

    def test_normalization_uses_gate_evaluator_ordering(self) -> None:
        """P5-Architecture is checked before P5.3 in normalization
        (matching evaluator priority order)."""
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "pending",  # non-terminal
                "P5.3-TestQuality": "fail",     # also non-terminal
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        ss = state_doc["SESSION_STATE"]
        # First open gate should be P5-Architecture (comes first in SSOT ordering).
        assert ss["_p6_state_normalization"]["first_open_gate"] == "P5-Architecture"
        assert ss["active_gate"] == "Architecture Review Gate"

    def test_normalization_reason_code_matches_evaluator(self) -> None:
        """The blocking_reason_code from normalization matches what the
        evaluator would produce for the same first_open_gate."""
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "rejected",  # first open
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        norm = state_doc["SESSION_STATE"]["_p6_state_normalization"]
        # Both normalization and evaluator should use BLOCKED-P5-5-TECHNICAL-DEBT-GATE.
        eval_result = evaluate_p6_prerequisites(
            session_state=state_doc["SESSION_STATE"],
            phase_1_5_executed=False,
            rollback_safety_applies=False,
        )
        assert norm["blocking_reason_code"] == eval_result.reason_code

    def test_normalization_cleans_implementation_review_block(self) -> None:
        """Fail-closed reset also cleans the ImplementationReview block."""
        state_doc = {"SESSION_STATE": {
            "Phase": "6-PostFlight",
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pending",
            },
            "ImplementationReview": {
                "iteration": 3,
                "implementation_review_complete": True,
            },
        }}
        _normalize_phase6_p5_state(state_doc=state_doc)
        review = state_doc["SESSION_STATE"]["ImplementationReview"]
        assert review["implementation_review_complete"] is False


# ===========================================================================
# 16. Reject terminal surface (Fix 4)
# ===========================================================================

class TestReviewDecisionRejectTerminalSurface:
    """reject writes active_gate, next_gate_condition, clears phase6_state."""

    def test_reject_sets_active_gate_and_condition(self, tmp_path: Path) -> None:
        state = _make_phase6_state(extra={"phase6_state": "implementation_review_pending"})
        session_path = _write_session(tmp_path, state)
        apply_review_decision(decision="reject", session_path=session_path)

        doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = doc["SESSION_STATE"]
        assert ss["active_gate"] == "Ticket Input Gate"
        assert "rejected" in ss["next_gate_condition"].lower()
        assert "phase6_state" not in ss
        assert ss.get("implementation_review_complete") is None
