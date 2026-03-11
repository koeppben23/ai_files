"""Comprehensive phase transition and lifecycle audit coverage.

This module audits ALL mapped phase transitions in the governance workflow
and all run-lifecycle resets.  It is organised into clearly separated
test classes that mirror the three mechanism layers:

    1. In-Run Phase Transitions (kernel-level)
    2. Run-Lifecycle Operations (entrypoint-level)
    3. Robustness / Determinism

Design constraints (see SSOT hierarchy):
- Tests verify that phase_api.yaml-defined transitions, monotonic
  enforcement, and P6 prerequisite gates produce deterministic results
  for identical inputs — regardless of which LLM model generates text.
- UI-trigger integration (plugin, desktop) is OUT OF SCOPE.
  Only the non-UI lifecycle entrypoint contract is verified here.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Mapping

import pytest

from governance.kernel.phase_kernel import KernelResult, RuntimeContext, execute
from governance.entrypoints import new_work_session
from governance.infrastructure.workspace_paths import run_dir

# ────────────────────────────────────────────────────────────────────
# Shared fixtures and helpers
# ────────────────────────────────────────────────────────────────────

RULEBOOK_BASE: dict[str, object] = {
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
    repo_spec = Path(__file__).resolve().parents[1] / "phase_api.yaml"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(
        repo_spec.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _runtime(tmp_path: Path) -> RuntimeContext:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)
    return RuntimeContext(
        requested_active_gate="",
        requested_next_gate_condition="Continue",
        repo_is_git_root=True,
        commands_home=commands_home,
        workspaces_home=tmp_path / "workspaces",
        config_root=tmp_path / "cfg",
    )


def _workspace_ready_state(**overrides: object) -> dict[str, object]:
    """Minimal session state that passes workspace-ready and rulebook gates."""
    base: dict[str, object] = {
        "PersistenceCommitted": True,
        "WorkspaceReadyGateCommitted": True,
        "WorkspaceArtifactsCommitted": True,
        "PointerVerified": True,
        **RULEBOOK_BASE,
    }
    base.update(overrides)
    return base


def _doc(**state_overrides: object) -> dict[str, object]:
    return {"SESSION_STATE": _workspace_ready_state(**state_overrides)}


def _exec(
    tmp_path: Path,
    *,
    token: str,
    active_gate: str = "",
    next_gate_condition: str = "Continue",
    **state_overrides: object,
) -> KernelResult:
    """Shorthand: run kernel execute() with workspace-ready state + overrides."""
    ctx = _runtime(tmp_path)
    ctx_with_gate = RuntimeContext(
        requested_active_gate=active_gate,
        requested_next_gate_condition=next_gate_condition,
        repo_is_git_root=True,
        commands_home=ctx.commands_home,
        workspaces_home=ctx.workspaces_home,
        config_root=ctx.config_root,
    )
    return execute(
        current_token=token,
        session_state_doc=_doc(**state_overrides),
        runtime_ctx=ctx_with_gate,
    )


# ────────────────────────────────────────────────────────────────────
# 1A — Phase 5 Sub-Graph transitions
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestPhase5SubGraph:
    """In-run transitions within the Phase 5.x sub-graph.

    Covers stay behaviour, manual 5→5.3 re-entry, and ALL outbound
    edges from tokens 5.3, 5.4, 5.5, 5.6 toward Phase 6.
    """

    # ── Token 5 stay ──────────────────────────────────────────────

    def test_token5_stay_returns_same_phase_on_repeated_calls(self, tmp_path: Path) -> None:
        """Happy: Token 5 with route_strategy='stay' never auto-advances."""
        result = _exec(tmp_path, token="5", Phase="5-ArchitectureReview")
        assert result.status == "OK"
        assert result.phase == "5-ArchitectureReview"

    def test_token5_stay_does_not_resolve_to_53(self, tmp_path: Path) -> None:
        """Edge: Even with phase_transition_evidence, stay token doesn't jump."""
        result = _exec(
            tmp_path,
            token="5",
            Phase="5-ArchitectureReview",
            phase_transition_evidence=True,
        )
        assert result.phase == "5-ArchitectureReview"

    # ── Token 5 → 5.3 (manual re-entry with evidence) ────────────

    def test_token5_to_53_with_evidence_advances(self, tmp_path: Path) -> None:
        """Happy: Caller requests token=5.3 with phase_transition_evidence → advance."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5-ArchitectureReview",
            phase_transition_evidence=True,
        )
        assert result.status == "OK"
        assert result.phase in ("5.3-TestQuality", "6-PostFlight")
        # If no conditional triggers fire, default is 6

    def test_token5_to_53_without_evidence_blocked(self, tmp_path: Path) -> None:
        """Bad: Caller requests 5.3 without evidence → blocked."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5-ArchitectureReview",
            phase_transition_evidence=False,
        )
        assert result.source == "phase-transition-evidence-required"

    def test_token5_to_53_with_string_evidence(self, tmp_path: Path) -> None:
        """Edge: phase_transition_evidence as non-empty string counts."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5-ArchitectureReview",
            phase_transition_evidence="architecture-approved",
        )
        assert result.status == "OK"

    def test_token5_to_53_with_empty_string_evidence_blocked(self, tmp_path: Path) -> None:
        """Corner: Empty string evidence is falsy → blocked."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5-ArchitectureReview",
            phase_transition_evidence="",
        )
        assert result.source == "phase-transition-evidence-required"

    def test_token5_to_53_with_list_evidence(self, tmp_path: Path) -> None:
        """Edge: phase_transition_evidence as non-empty list counts."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5-ArchitectureReview",
            phase_transition_evidence=["review-passed"],
        )
        assert result.status == "OK"

    def test_token5_to_53_with_empty_list_evidence_blocked(self, tmp_path: Path) -> None:
        """Corner: Empty list evidence is falsy → blocked."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5-ArchitectureReview",
            phase_transition_evidence=[],
        )
        assert result.source == "phase-transition-evidence-required"

    # ── 5.3 → 5.4 (business_rules_gate_required) ─────────────────

    def test_53_to_54_when_phase15_executed(self, tmp_path: Path) -> None:
        """Happy: 5.3 routes to 5.4 when Phase 1.5 was executed."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5.3-TestQuality",
            BusinessRules={
                "Decision": "execute",
                "Inventory": {"sha256": "abc"},
                "ExecutionEvidence": True,
            },
        )
        assert result.phase == "5.4-BusinessRules"
        assert result.source == "phase-5.3-to-5.4"

    # ── 5.3 → 5.5 (technical_debt_proposed) ───────────────────────

    def test_53_to_55_when_technical_debt_proposed(self, tmp_path: Path) -> None:
        """Happy: 5.3 routes to 5.5 when TechnicalDebt.Proposed=True."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5.3-TestQuality",
            TechnicalDebt={"Proposed": True},
        )
        assert result.phase == "5.5-TechnicalDebt"
        assert result.source == "phase-5.3-to-5.5"

    # ── 5.3 → 5.6 (rollback_required) — previously ZERO coverage ─

    def test_53_to_56_when_rollback_required(self, tmp_path: Path) -> None:
        """Happy: 5.3 routes to 5.6 when RollbackRequired=True."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5.3-TestQuality",
            RollbackRequired=True,
        )
        assert result.phase == "5.6-RollbackSafety"
        assert result.source == "phase-5.3-to-5.6"

    def test_53_to_56_via_rollback_mapping(self, tmp_path: Path) -> None:
        """Edge: Rollback.Required=True also triggers 5.3→5.6."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5.3-TestQuality",
            Rollback={"Required": True},
        )
        assert result.phase == "5.6-RollbackSafety"
        assert result.source == "phase-5.3-to-5.6"

    # ── 5.3 → 6 (default, no optional gates) ─────────────────────

    def test_53_to_6_default_path(self, tmp_path: Path) -> None:
        """Happy: 5.3 routes to 6 when no optional gates required."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5.3-TestQuality",
        )
        assert result.phase == "6-PostFlight"
        assert result.source == "phase-5.3-to-6"

    # ── 5.4 → 5.5 (technical_debt_proposed) — previously ZERO coverage ─

    def test_54_to_55_when_technical_debt_proposed(self, tmp_path: Path) -> None:
        """Happy: 5.4 routes to 5.5 when TechnicalDebt.Proposed=True."""
        result = _exec(
            tmp_path,
            token="5.4",
            Phase="5.4-BusinessRules",
            TechnicalDebt={"Proposed": True},
        )
        assert result.phase == "5.5-TechnicalDebt"
        assert result.source == "phase-5.4-to-5.5"

    # ── 5.4 → 5.6 (rollback_required) — previously ZERO coverage ─

    def test_54_to_56_when_rollback_required(self, tmp_path: Path) -> None:
        """Happy: 5.4 routes to 5.6 when RollbackRequired=True."""
        result = _exec(
            tmp_path,
            token="5.4",
            Phase="5.4-BusinessRules",
            RollbackRequired=True,
        )
        assert result.phase == "5.6-RollbackSafety"
        assert result.source == "phase-5.4-to-5.6"

    # ── 5.4 → 6 (default) — previously ZERO coverage ─────────────

    def test_54_to_6_default_path(self, tmp_path: Path) -> None:
        """Happy: 5.4 routes to 6 when no optional gates required."""
        result = _exec(
            tmp_path,
            token="5.4",
            Phase="5.4-BusinessRules",
        )
        assert result.phase == "6-PostFlight"
        assert result.source == "phase-5.4-to-6"

    # ── 5.5 → 5.6 (rollback_required) — previously ZERO coverage ─

    def test_55_to_56_when_rollback_required(self, tmp_path: Path) -> None:
        """Happy: 5.5 routes to 5.6 when RollbackRequired=True."""
        result = _exec(
            tmp_path,
            token="5.5",
            Phase="5.5-TechnicalDebt",
            RollbackRequired=True,
        )
        assert result.phase == "5.6-RollbackSafety"
        assert result.source == "phase-5.5-to-5.6"

    # ── 5.5 → 6 (default) — previously ZERO coverage ─────────────

    def test_55_to_6_default_path(self, tmp_path: Path) -> None:
        """Happy: 5.5 routes to 6 when no rollback required."""
        result = _exec(
            tmp_path,
            token="5.5",
            Phase="5.5-TechnicalDebt",
        )
        assert result.phase == "6-PostFlight"
        assert result.source == "phase-5.5-to-6"

    # ── 5.6 → 6 (default) — previously ZERO coverage ─────────────

    def test_56_to_6_default_path(self, tmp_path: Path) -> None:
        """Happy: 5.6 always routes to 6."""
        result = _exec(
            tmp_path,
            token="5.6",
            Phase="5.6-RollbackSafety",
        )
        assert result.phase == "6-PostFlight"
        assert result.source == "phase-5.6-to-6"

    # ── Phase 6 terminal stay — previously ZERO coverage ──────────

    def test_phase6_terminal_stay_with_prerequisites_met(self, tmp_path: Path) -> None:
        """Happy: Phase 6 with all prerequisites met stays at Phase 6."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        )
        assert result.status == "OK"
        assert result.phase == "6-PostFlight"

    def test_phase6_terminal_stay_blocks_without_prerequisites(self, tmp_path: Path) -> None:
        """Bad: Phase 6 with missing prerequisites is blocked."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pending",
            },
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"

    # ── 5.3 priority: business_rules_gate > technical_debt > rollback ─

    def test_53_business_rules_takes_priority_over_technical_debt(self, tmp_path: Path) -> None:
        """Edge: When both phase_1_5_executed and technical_debt_proposed,
        business_rules_gate_required fires first (higher priority in spec)."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5.3-TestQuality",
            BusinessRules={
                "Decision": "execute",
                "Inventory": {"sha256": "abc"},
                "ExecutionEvidence": True,
            },
            TechnicalDebt={"Proposed": True},
        )
        assert result.phase == "5.4-BusinessRules"
        assert result.source == "phase-5.3-to-5.4"

    def test_53_technical_debt_takes_priority_over_rollback(self, tmp_path: Path) -> None:
        """Edge: When both technical_debt_proposed and rollback_required,
        technical_debt fires first (higher position in transitions list)."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="5.3-TestQuality",
            TechnicalDebt={"Proposed": True},
            RollbackRequired=True,
        )
        assert result.phase == "5.5-TechnicalDebt"
        assert result.source == "phase-5.3-to-5.5"


# ────────────────────────────────────────────────────────────────────
# 1B — Monotonic enforcement
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestMonotonicEnforcement:
    """Kernel monotonic guard: backward requests are silently refused,
    forward jumps require evidence, unreachable tokens are blocked."""

    def test_backward_5_to_4_silently_refused(self, tmp_path: Path) -> None:
        """Happy (guard works): Requesting token 4 when persisted at 5."""
        result = _exec(
            tmp_path,
            token="4",
            Phase="5-ArchitectureReview",
        )
        assert result.phase == "5-ArchitectureReview"
        assert result.source == "monotonic-session-phase"

    def test_backward_6_to_5_silently_refused(self, tmp_path: Path) -> None:
        """Happy (guard works): Requesting token 5 when persisted at 6."""
        result = _exec(
            tmp_path,
            token="5",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
            },
        )
        assert result.phase == "6-PostFlight"
        assert result.source == "monotonic-session-phase"

    def test_backward_3a_to_2_silently_refused(self, tmp_path: Path) -> None:
        """Edge: Backward from 3A to 2."""
        result = _exec(
            tmp_path,
            token="2",
            Phase="3A-API-Inventory",
            APIInventory={"Status": "completed"},
            RepoDiscovery={"Completed": True, "RepoCacheFile": "c", "RepoMapDigestFile": "d"},
        )
        assert result.phase == "3A-API-Inventory"
        assert result.source == "monotonic-session-phase"

    def test_12_backward_exception_with_workspace_ready(self, tmp_path: Path) -> None:
        """Corner: Token 1.2 backward exception — allowed when workspace_ready=True.

        The monotonic guard has a single hardcoded exception: if persisted
        token is '1.2' and workspace is ready, backward requests pass through.
        This test verifies the kernel does NOT block with monotonic-session-phase.
        """
        result = _exec(
            tmp_path,
            token="1.1",
            Phase="1.2-ActivationIntent",
            Intent={"Path": "x", "Sha256": "y", "EffectiveScope": "repo"},
        )
        # Should NOT be blocked by monotonic guard.
        # (May be blocked/routed by other guards, but not monotonic.)
        assert result.source != "monotonic-session-phase"

    def test_12_backward_without_workspace_ready_is_blocked(self, tmp_path: Path) -> None:
        """Bad: Without workspace_ready, 1.2 backward exception does NOT fire."""
        ctx = _runtime(tmp_path)
        ctx_with_gate = RuntimeContext(
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=ctx.commands_home,
            workspaces_home=ctx.workspaces_home,
            config_root=ctx.config_root,
        )
        # State without PersistenceCommitted → workspace not ready
        result = execute(
            current_token="1.1",
            session_state_doc={
                "SESSION_STATE": {
                    "Phase": "1.2-ActivationIntent",
                    "PersistenceCommitted": False,
                    "WorkspaceReadyGateCommitted": False,
                    "WorkspaceArtifactsCommitted": False,
                    "PointerVerified": False,
                }
            },
            runtime_ctx=ctx_with_gate,
        )
        assert result.source == "monotonic-session-phase"

    def test_forward_jump_without_evidence_blocked(self, tmp_path: Path) -> None:
        """Bad: Forward jump from 4→5 without ticket evidence is blocked."""
        result = _exec(
            tmp_path,
            token="5",
            Phase="4",
        )
        # Token 5 is in the allowed_next_tokens for 4, but rank gap + no evidence
        assert result.source in (
            "phase-transition-evidence-required",
            "phase-4-awaiting-ticket-intake",
        )

    def test_forward_jump_to_unreachable_token_blocked(self, tmp_path: Path) -> None:
        """Bad: Requesting token 6 when persisted at 4 — not in transition graph."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="4",
        )
        assert result.source == "phase-transition-not-allowed"

    def test_forward_jump_to_unreachable_53_from_4_blocked(self, tmp_path: Path) -> None:
        """Corner: Requesting 5.3 from persisted 4 — 5.3 is not a direct edge."""
        result = _exec(
            tmp_path,
            token="5.3",
            Phase="4",
        )
        assert result.source == "phase-transition-not-allowed"


# ────────────────────────────────────────────────────────────────────
# 1C — P6 Prerequisite Gate
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestP6PrerequisiteGate:
    """Kernel-level P6 prerequisite gate:
    P5-Architecture=approved AND P5.3-TestQuality=pass are ALWAYS required.
    P5.4 and P5.6 are conditional."""

    def test_all_gates_approved_allows_p6(self, tmp_path: Path) -> None:
        """Happy: All mandatory and optional gates approved."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "approved",
                "P5.6-RollbackSafety": "approved",
            },
        )
        assert result.status == "OK"
        assert result.phase == "6-PostFlight"

    def test_p5_architecture_missing_blocks_p6(self, tmp_path: Path) -> None:
        """Bad: P5-Architecture=pending → P6 blocked."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pass",
            },
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"

    def test_p53_test_quality_missing_blocks_p6(self, tmp_path: Path) -> None:
        """Bad: P5.3-TestQuality=pending → P6 blocked."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pending",
            },
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"

    def test_p53_pass_with_exceptions_allows_p6(self, tmp_path: Path) -> None:
        """Edge: P5.3-TestQuality='pass-with-exceptions' is accepted."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass-with-exceptions",
                "P5.5-TechnicalDebt": "approved",
            },
        )
        assert result.status == "OK"

    def test_p54_required_when_phase15_executed(self, tmp_path: Path) -> None:
        """Edge: P5.4 is required when Phase 1.5 was executed (ExecutionEvidence=True)."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            BusinessRules={
                "ExecutionEvidence": True,
                "Inventory": {"sha256": "abc"},
            },
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "pending",
            },
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"

    def test_p56_required_when_rollback_safety_applies(self, tmp_path: Path) -> None:
        """Edge: P5.6 is required when rollback safety conditions exist."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            RollbackRequired=True,
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.6-RollbackSafety": "pending",
            },
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"

    def test_p56_not_required_when_no_rollback(self, tmp_path: Path) -> None:
        """Happy: P5.6 is irrelevant when rollback safety does not apply."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.5-TechnicalDebt": "approved",
                "P5.6-RollbackSafety": "pending",
            },
        )
        assert result.status == "OK"

    def test_no_gates_mapping_blocks_p6(self, tmp_path: Path) -> None:
        """Corner: No Gates mapping at all → P6 blocked."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"


# ────────────────────────────────────────────────────────────────────
# 1D — Early chain transitions (bootstrap → phase 4)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestEarlyChainTransitions:
    """Cold-start from token 0 and the bootstrap chain
    0 → 1.1 → 1 → 1.2 → 1.3 → 2 → 2.1."""

    def test_cold_start_token0_resolves_to_11_bootstrap(self, tmp_path: Path) -> None:
        """Happy: Token 0 with route_strategy='next' immediately resolves to 1.1-Bootstrap."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="0",
            session_state_doc={"SESSION_STATE": {}},
            runtime_ctx=ctx,
        )
        assert result.phase == "1.1-Bootstrap"

    def test_token11_stays_at_bootstrap(self, tmp_path: Path) -> None:
        """Happy: Token 1.1 with route_strategy='stay' stays at 1.1-Bootstrap."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="1.1",
            session_state_doc={"SESSION_STATE": {}},
            runtime_ctx=ctx,
        )
        assert result.phase == "1.1-Bootstrap"

    def test_token1_stays_at_workspace_persistence(self, tmp_path: Path) -> None:
        """Happy: Token 1 (workspace persistence) stays."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="1",
            session_state_doc={"SESSION_STATE": {}},
            runtime_ctx=ctx,
        )
        # Without workspace ready, may bounce to 1.1-Bootstrap
        assert result.phase in ("1-WorkspacePersistence", "1.1-Bootstrap")

    def test_token12_routes_to_13_when_workspace_ready(self, tmp_path: Path) -> None:
        """Happy: Token 1.2 with route_strategy='next' and default transition
        resolves to 1.3-RulebookLoad."""
        result = _exec(
            tmp_path,
            token="1.2",
            Phase="1.2-ActivationIntent",
            Intent={"Path": "x", "Sha256": "y", "EffectiveScope": "repo"},
        )
        assert result.phase == "1.3-RulebookLoad"
        assert result.source == "phase-1.2-to-1.3-auto"

    def test_token12_blocked_without_exit_evidence(self, tmp_path: Path) -> None:
        """Bad: Token 1.2 without exit_required_keys (Intent) → blocked."""
        result = _exec(
            tmp_path,
            token="1.2",
            Phase="1.2-ActivationIntent",
        )
        assert result.status == "BLOCKED"
        assert result.source == "phase-exit-evidence-missing"

    def test_token13_blocked_without_rulebook_evidence(self, tmp_path: Path) -> None:
        """Bad: Token 1.3 without required rulebook keys → blocked."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="1.3",
            session_state_doc={
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
            },
            runtime_ctx=ctx,
        )
        assert result.status == "BLOCKED"
        assert result.source == "phase-exit-evidence-missing"


# ────────────────────────────────────────────────────────────────────
# 2 — Run-Lifecycle Reset (new_work_session entrypoint)
# ────────────────────────────────────────────────────────────────────

# Reuse setup helper from the existing test module.
from .test_new_work_session_entrypoint import _setup_workspace, _write_json


@pytest.mark.governance
class TestRunLifecycleReset:
    """Tests that new_work_session.main() correctly resets to Phase 4
    from any source phase and performs all required cleanup.

    This is a run-lifecycle operation, NOT a kernel transition edge.
    new_work_session bypasses the kernel entirely — it directly
    overwrites SESSION_STATE.json.
    """

    def test_new_session_from_phase6_resets_to_phase4(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: Most common real-world case — Phase 6 → new session → Phase 4."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="6-PostFlight")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-p6", "--quiet"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-created"

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"
        assert state["phase"] == "4"
        assert state["Next"] == "4"
        assert state["Ticket"] is None
        assert state["Task"] is None

    def test_new_session_from_phase5_resets_to_phase4(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: Phase 5 → new session → Phase 4."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="5-ArchitectureReview")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"

    def test_new_session_from_phase4_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: Phase 4 → new session → Phase 4 (idempotent)."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="4")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-p4", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"
        assert state["Ticket"] is None
        assert state["Gates"]["P5-Architecture"] == "pending"

    def test_new_session_from_bootstrap_phase1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Corner: Phase 1 → new session → Phase 4.

        Even from an early bootstrap phase, new_work_session resets to 4.
        """
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="1-WorkspacePersistence")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"

    def test_new_session_archives_previous_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: Previous run is archived to runs/<run_id>/ before reset."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="6-PostFlight")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-archive", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        archived = run_dir(session_path.parent.parent, session_path.parent.name, "run-old-001") / "SESSION_STATE.json"
        assert archived.is_file(), "previous run snapshot must be archived"
        archived_payload = json.loads(archived.read_text(encoding="utf-8"))
        assert archived_payload["SESSION_STATE"]["session_run_id"] == "run-old-001"

    def test_new_session_clears_all_artifacts_and_gates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: All gates reset to 'pending', stale artifacts deleted."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="6-PostFlight")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        # All gates must be pending
        for gate in ("P5-Architecture", "P5.3-TestQuality", "P5.4-BusinessRules",
                      "P5.5-TechnicalDebt", "P5.6-RollbackSafety", "P6-ImplementationQA"):
            assert state["Gates"][gate] == "pending", f"Gate {gate} should be 'pending'"
        # Stale artifacts must be deleted
        for artifact in ("ArchitectureDecisions", "TestQualityAssessment",
                         "BusinessRulesCompliance", "TechnicalDebtRegister",
                         "RollbackPlan", "ReviewFindings", "GateArtifacts",
                         "FeatureComplexity"):
            assert artifact not in state, f"Artifact {artifact} should be deleted"

    def test_new_session_assigns_new_run_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: A new session_run_id is assigned."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="5-ArchitectureReview")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["session_run_id"] != "run-old-001"
        assert state["session_run_id"].startswith("work-")


# ────────────────────────────────────────────────────────────────────
# 2.5 — Post-Reset Kernel Integration
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestPostResetKernelIntegration:
    """After new_work_session resets to Phase 4, the kernel must
    correctly pick up Phase 4 and behave normally on the next execute() call."""

    def test_kernel_execute_after_reset_resolves_phase4_correctly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: Reset → kernel execute() → Phase 4 awaiting ticket intake."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="6-PostFlight")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        # Step 1: Reset to Phase 4
        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        # Step 2: Load the reset state and feed it to the kernel.
        # _setup_workspace (from test_new_work_session_entrypoint) represents a minimal
        # workspace for the lifecycle entrypoint — it omits WorkspaceArtifactsCommitted,
        # PointerVerified, and RULEBOOK_BASE fields because the entrypoint never checks them.
        # The kernel, however, requires all persistence flags + loaded rulebooks for any
        # token at rank >= 2.  In production these survive the reset (new_work_session never
        # touches them).  We inject them here to model a fully-provisioned workspace.
        reset_doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = reset_doc["SESSION_STATE"]
        ss["WorkspaceArtifactsCommitted"] = True
        ss["PointerVerified"] = True
        ss.update(RULEBOOK_BASE)
        commands_home = tmp_path / "k_commands"
        _write_phase_api(commands_home)

        result = execute(
            current_token="4",
            session_state_doc=reset_doc,
            runtime_ctx=RuntimeContext(
                requested_active_gate="Ticket Input Gate",
                requested_next_gate_condition="Collect ticket",
                repo_is_git_root=True,
                commands_home=commands_home,
                workspaces_home=tmp_path / "k_workspaces",
                config_root=tmp_path / "k_cfg",
            ),
        )

        assert result.status == "OK"
        assert result.phase == "4"
        assert result.source == "phase-4-awaiting-ticket-intake"

    def test_kernel_after_reset_can_advance_to_5_with_ticket(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: After reset, adding ticket evidence → kernel advances to Phase 5."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="6-PostFlight")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        # Step 1: Reset
        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        # Step 2: Inject ticket evidence into the reset state.
        # Also inject missing persistence flags (see first test in this class for rationale).
        reset_doc = json.loads(session_path.read_text(encoding="utf-8"))
        ss = reset_doc["SESSION_STATE"]
        ss["WorkspaceArtifactsCommitted"] = True
        ss["PointerVerified"] = True
        ss.update(RULEBOOK_BASE)
        ss["Ticket"] = "Fix bug #123"
        ss["TicketRecordDigest"] = "Context: bug fix\nTest Strategy: unit tests"
        ss["FeatureComplexity"] = {"Class": "STANDARD", "Reason": "ticket", "PlanningDepth": "standard"}

        commands_home = tmp_path / "k_commands"
        _write_phase_api(commands_home)

        result = execute(
            current_token="4",
            session_state_doc=reset_doc,
            runtime_ctx=RuntimeContext(
                requested_active_gate="Ticket Input Gate",
                requested_next_gate_condition="Collect ticket",
                repo_is_git_root=True,
                commands_home=commands_home,
                workspaces_home=tmp_path / "k_workspaces",
                config_root=tmp_path / "k_cfg",
            ),
        )

        assert result.status == "OK"
        assert result.phase == "5-ArchitectureReview"
        assert result.source == "phase-4-to-5-ticket-intake"


# ────────────────────────────────────────────────────────────────────
# 3 — Corrupted State Recovery
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestCorruptedStateRecovery:
    """Kernel behaviour with corrupted or malformed session state.

    The kernel must fail-closed or recover deterministically
    (e.g., fall back to start_token / workspace-ready-gate)."""

    def test_missing_phase_key_falls_back_to_start(self, tmp_path: Path) -> None:
        """Bad: No 'Phase' or 'phase' key at all."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="4",
            session_state_doc={"SESSION_STATE": {
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                **RULEBOOK_BASE,
            }},
            runtime_ctx=ctx,
        )
        # No persisted_token, so kernel uses requested_token "4"
        assert result.status == "OK"
        assert result.phase == "4"

    def test_empty_session_state_uses_start_token(self, tmp_path: Path) -> None:
        """Corner: Completely empty SESSION_STATE → falls back."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="0",
            session_state_doc={"SESSION_STATE": {}},
            runtime_ctx=ctx,
        )
        # Token 0 has route_strategy="next" → resolves to 1.1-Bootstrap
        assert result.phase == "1.1-Bootstrap"

    def test_none_session_state_doc_handles_gracefully(self, tmp_path: Path) -> None:
        """Corner: None session_state_doc → empty state."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="0",
            session_state_doc=None,
            runtime_ctx=ctx,
        )
        assert result.phase == "1.1-Bootstrap"

    def test_unknown_token_in_persisted_phase_falls_back(self, tmp_path: Path) -> None:
        """Bad: Persisted phase contains an unknown token string."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="4",
            session_state_doc={"SESSION_STATE": {
                "Phase": "99-Unknown",
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                **RULEBOOK_BASE,
            }},
            runtime_ctx=ctx,
        )
        # Unknown persisted token → normalized to "", so kernel falls to requested_token "4"
        assert result.status == "OK"
        assert result.phase == "4"

    def test_wrong_type_for_phase_field(self, tmp_path: Path) -> None:
        """Corner: Phase field is an integer instead of string."""
        ctx = _runtime(tmp_path)
        result = execute(
            current_token="4",
            session_state_doc={"SESSION_STATE": {
                "Phase": 5,
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                **RULEBOOK_BASE,
            }},
            runtime_ctx=ctx,
        )
        # _extract_phase checks isinstance(value, str) → int fails → empty
        # Falls to requested_token "4"
        assert result.status == "OK"
        assert result.phase == "4"

    def test_malformed_gates_dict_at_p6(self, tmp_path: Path) -> None:
        """Corner: Gates is a string instead of dict → P6 prerequisite gate blocks."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates="malformed",
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"

    def test_gates_as_empty_dict_blocks_p6(self, tmp_path: Path) -> None:
        """Edge: Gates is an empty dict → P6 blocked (no approved gates)."""
        result = _exec(
            tmp_path,
            token="6",
            Phase="6-PostFlight",
            Gates={},
        )
        assert result.status == "BLOCKED"
        assert result.source == "p6-prerequisite-gate"


# ────────────────────────────────────────────────────────────────────
# CLI Lifecycle Entrypoint
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestCLILifecycleEntrypoint:
    """Tests that the CLI entrypoint correctly delegates to new_work_session.main().

    UI-trigger integration (plugin, desktop) is OUT OF SCOPE — only the
    non-UI lifecycle entrypoint contract is verified here.
    """

    def test_cli_from_phase6_produces_phase4(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Happy: CLI path from Phase 6 → Phase 4."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="6-PostFlight")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "pipeline", "--quiet"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-created"

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"
        assert state["Next"] == "4"

    def test_cli_entrypoint_returns_exit_code_2_without_pointer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bad: No valid session pointer → exit code 2."""
        config_root = tmp_path / "config"
        commands_home = config_root / "commands"
        _write_json(
            commands_home / "governance.paths.json",
            {
                "schema": "opencode-governance.paths.v1",
                "paths": {
                    "configRoot": str(config_root),
                    "commandsHome": str(commands_home),
                    "workspacesHome": str(config_root / "workspaces"),
                    "pythonCommand": "/usr/bin/python3",
                },
            },
        )
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--quiet"])
        assert code == 2

    def test_cli_from_phase53_produces_phase4(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: CLI path from sub-phase 5.3 → Phase 4."""
        config_root, session_path, _ = _setup_workspace(tmp_path, phase="5.3-TestQuality")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = capsys.readouterr()

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"


# ────────────────────────────────────────────────────────────────────
# Determinism Replay
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
class TestDeterminismReplay:
    """Replay-based determinism verification.

    For selected critical transitions, the same input is executed twice
    and the results must be field-identical on all contract-relevant
    fields (phase, source, status, next_token).  This strengthens the
    claim that execution is deterministic and model-agnostic: the rails
    produce identical outputs for identical inputs.
    """

    @staticmethod
    def _assert_deterministic(r1: KernelResult, r2: KernelResult) -> None:
        assert r1.phase == r2.phase, f"phase mismatch: {r1.phase} vs {r2.phase}"
        assert r1.source == r2.source, f"source mismatch: {r1.source} vs {r2.source}"
        assert r1.status == r2.status, f"status mismatch: {r1.status} vs {r2.status}"
        assert r1.next_token == r2.next_token, f"next_token mismatch: {r1.next_token} vs {r2.next_token}"
        assert r1.active_gate == r2.active_gate, f"active_gate mismatch: {r1.active_gate} vs {r2.active_gate}"

    def test_replay_token5_stay_identical(self, tmp_path: Path) -> None:
        """Happy: Token 5 stay — two identical calls → identical results."""
        r1 = _exec(tmp_path, token="5", Phase="5-ArchitectureReview")
        r2 = _exec(tmp_path, token="5", Phase="5-ArchitectureReview")
        self._assert_deterministic(r1, r2)

    def test_replay_token5_to_53_with_evidence_identical(self, tmp_path: Path) -> None:
        """Happy: 5 → 5.3 with evidence — two identical calls → identical results."""
        r1 = _exec(tmp_path, token="5.3", Phase="5-ArchitectureReview", phase_transition_evidence=True)
        r2 = _exec(tmp_path, token="5.3", Phase="5-ArchitectureReview", phase_transition_evidence=True)
        self._assert_deterministic(r1, r2)

    def test_replay_token5_to_53_without_evidence_identical(self, tmp_path: Path) -> None:
        """Edge: 5 → 5.3 without evidence (blocked) — two identical calls → identical results."""
        r1 = _exec(tmp_path, token="5.3", Phase="5-ArchitectureReview", phase_transition_evidence=False)
        r2 = _exec(tmp_path, token="5.3", Phase="5-ArchitectureReview", phase_transition_evidence=False)
        self._assert_deterministic(r1, r2)

    def test_replay_53_to_6_default_identical(self, tmp_path: Path) -> None:
        """Happy: 5.3 → 6 default path — two identical calls → identical results."""
        r1 = _exec(tmp_path, token="5.3", Phase="5.3-TestQuality")
        r2 = _exec(tmp_path, token="5.3", Phase="5.3-TestQuality")
        self._assert_deterministic(r1, r2)

    def test_replay_monotonic_backward_identical(self, tmp_path: Path) -> None:
        """Bad: Monotonic backward refusal — two identical calls → identical results."""
        r1 = _exec(tmp_path, token="4", Phase="5-ArchitectureReview")
        r2 = _exec(tmp_path, token="4", Phase="5-ArchitectureReview")
        self._assert_deterministic(r1, r2)

    def test_replay_p6_prerequisite_block_identical(self, tmp_path: Path) -> None:
        """Bad: P6 prerequisite block — two identical calls → identical blocked result."""
        gates: dict[str, str] = {"P5-Architecture": "pending", "P5.3-TestQuality": "pending"}
        r1 = _exec(tmp_path, token="6", Phase="6-PostFlight", Gates=gates)
        r2 = _exec(tmp_path, token="6", Phase="6-PostFlight", Gates=gates)
        self._assert_deterministic(r1, r2)
