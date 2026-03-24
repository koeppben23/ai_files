from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence, cast
import uuid

from governance_runtime.application.dto.phase_next_action_contract import contains_ticket_prompt
from governance_runtime.domain.strict_exit_evaluator import StrictExitResult
from governance_runtime.infrastructure.plan_record_state import resolve_plan_record_signal
from governance_runtime.domain.phase_state_machine import phase_rank, resolve_phase_output_policy
from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.logging.global_error_handler import emit_error_event
from governance_runtime.paths import get_workspace_logs_root

from governance_runtime.engine.gate_evaluator import evaluate_p6_prerequisites, can_promote_to_phase6, evaluate_strict_exit_gate
from governance_runtime.engine import reason_codes

from .phase_api_spec import PhaseApiSpec, PhaseApiSpecError, PhaseSpecEntry, load_phase_api


@dataclass(frozen=True)
class RuntimeContext:
    requested_active_gate: str
    requested_next_gate_condition: str
    repo_is_git_root: bool
    live_repo_fingerprint: str | None = None
    commands_home: Path | None = None
    config_root: Path | None = None
    workspaces_home: Path | None = None


@dataclass(frozen=True)
class KernelResult:
    phase: str
    next_token: str | None
    active_gate: str
    next_gate_condition: str
    workspace_ready: bool
    source: str
    status: str
    spec_hash: str
    spec_path: str
    spec_loaded_at: str
    log_paths: dict[str, str]
    event_id: str
    strict_exit_result: StrictExitResult | None = None
    route_strategy: str = ""
    plan_record_status: str = "unknown"
    plan_record_versions: int = 0
    transition_evidence_met: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_state(document: Mapping[str, object] | None) -> Mapping[str, object]:
    if document is None:
        return {}
    payload = document.get("SESSION_STATE")
    if isinstance(payload, Mapping):
        return payload
    return document


def _extract_fingerprint(state: Mapping[str, object]) -> str:
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_phase(state: Mapping[str, object]) -> str:
    for key in ("Phase", "phase"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _state_text(state: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _transition_has_evidence(state: Mapping[str, object]) -> bool:
    value = state.get("phase_transition_evidence")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return False


def _read_bool(state: Mapping[str, object], *keys: str) -> bool | None:
    for key in keys:
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return None


def _persistence_gate_passed(state: Mapping[str, object]) -> tuple[bool, str]:
    commit_flags = state.get("CommitFlags")
    state_view = cast(Mapping[str, object], commit_flags) if isinstance(commit_flags, Mapping) else state
    persistence_committed = _read_bool(state_view, "PersistenceCommitted", "persistence_committed", "persistenceCommitted")
    if persistence_committed is not True:
        return False, "PersistenceCommitted not true"
    workspace_ready = _read_bool(state_view, "WorkspaceReadyGateCommitted", "workspace_ready_gate_committed")
    if workspace_ready is not True:
        return False, "WorkspaceReadyGateCommitted not true"
    artifacts_committed = _read_bool(state_view, "WorkspaceArtifactsCommitted", "workspace_artifacts_committed")
    if artifacts_committed is not True:
        return False, "WorkspaceArtifactsCommitted not true"
    pointer_verified = _read_bool(state_view, "PointerVerified", "pointer_verified")
    if pointer_verified is not True:
        return False, "PointerVerified not true"
    return True, "ok"


def _rulebook_gate_passed(state: Mapping[str, object]) -> tuple[bool, str]:
    loaded_rulebooks = state.get("LoadedRulebooks")
    if not isinstance(loaded_rulebooks, Mapping):
        return False, "LoadedRulebooks not set"
    core = loaded_rulebooks.get("core")
    if not isinstance(core, str) or not core.strip():
        return False, "core rulebook not loaded"
    active_profile = state.get("ActiveProfile")
    if not isinstance(active_profile, str) or not active_profile.strip():
        return False, "active profile not set"
    profile = loaded_rulebooks.get("profile")
    if not isinstance(profile, str) or not profile.strip():
        return False, f"profile rulebook '{active_profile}' not loaded"
    addons = loaded_rulebooks.get("addons")
    if not isinstance(addons, Mapping) or not addons:
        return False, "addon rulebook not loaded"
    if not any(isinstance(value, str) and value.strip() for value in addons.values()):
        return False, "addon rulebook not loaded"
    addons_evidence = state.get("AddonsEvidence")
    if not isinstance(addons_evidence, Mapping) or not addons_evidence:
        return False, "addon evidence missing"
    return True, "ok"


def _openapi_signal(state: Mapping[str, object]) -> bool:
    addons = state.get("AddonsEvidence")
    if isinstance(addons, Mapping):
        openapi = addons.get("openapi")
        if isinstance(openapi, Mapping) and openapi.get("detected") is True:
            return True
        if openapi is True:
            return True
    repo_caps = state.get("repo_capabilities")
    if isinstance(repo_caps, list):
        normalized = {str(item).strip().lower() for item in repo_caps}
        return "openapi" in normalized
    return False


def _external_api_artifacts(state: Mapping[str, object]) -> bool:
    scope = state.get("Scope")
    if isinstance(scope, Mapping):
        external_apis = scope.get("ExternalAPIs")
        if isinstance(external_apis, list) and len(external_apis) > 0:
            return True
    artifacts = state.get("external_api_artifacts")
    if isinstance(artifacts, list) and len(artifacts) > 0:
        return True
    return artifacts is True


def api_in_scope(state: Mapping[str, object]) -> bool:
    return _openapi_signal(state) or _external_api_artifacts(state)


def _business_rules_scope(state: Mapping[str, object]) -> str:
    scope = state.get("Scope")
    if isinstance(scope, Mapping):
        value = scope.get("BusinessRules")
        if isinstance(value, str):
            return value.strip().lower()
    return ""


def _business_rules_discovery_resolved(state: Mapping[str, object]) -> bool:
    business_rules = state.get("BusinessRules")
    execution_evidence = False
    outcome = ""
    if isinstance(business_rules, Mapping):
        evidence_token = business_rules.get("ExecutionEvidence")
        execution_evidence = isinstance(evidence_token, bool) and evidence_token
        outcome_token = business_rules.get("Outcome")
        if isinstance(outcome_token, str):
            outcome = outcome_token.strip().lower()

    if execution_evidence and outcome in {"extracted", "gap-detected"}:
        return True

    br_scope = _business_rules_scope(state)
    if execution_evidence and br_scope in {"extracted", "gap-detected"}:
        return True
    if br_scope == "unresolved":
        return False
    return False


def _phase_1_5_executed(state: Mapping[str, object]) -> bool:
    business_rules = state.get("BusinessRules")
    if isinstance(business_rules, Mapping):
        execution = business_rules.get("Execution")
        if isinstance(execution, Mapping):
            completed = execution.get("Completed")
            if isinstance(completed, bool) and completed:
                return True
        executed = business_rules.get("Executed")
        if isinstance(executed, bool) and executed:
            return True
    execution_evidence = _read_nested_key(state, "BusinessRules.ExecutionEvidence")
    if isinstance(execution_evidence, bool) and execution_evidence:
        return True
    return False


def _technical_debt_proposed(state: Mapping[str, object]) -> bool:
    for key in ("TechnicalDebtProposed", "technical_debt_proposed"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    technical_debt = state.get("TechnicalDebt")
    if isinstance(technical_debt, Mapping):
        proposed = technical_debt.get("Proposed")
        if isinstance(proposed, bool):
            return proposed
    return False


def _rollback_required(state: Mapping[str, object]) -> bool:
    for key in ("RollbackRequired", "rollback_required"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    rollback = state.get("Rollback")
    if isinstance(rollback, Mapping):
        required = rollback.get("Required")
        if isinstance(required, bool):
            return required
    return False


def _rollback_safety_applies(state: Mapping[str, object]) -> bool:
    touched_surface = state.get("TouchedSurface")
    if isinstance(touched_surface, Mapping):
        schema_planned = touched_surface.get("SchemaPlanned")
        if isinstance(schema_planned, list) and len(schema_planned) > 0:
            return True
        contracts_planned = touched_surface.get("ContractsPlanned")
        if isinstance(contracts_planned, list) and len(contracts_planned) > 0:
            return True
    return _rollback_required(state)


def _normalize_token(value: str, spec: PhaseApiSpec) -> str:
    probe = str(value or "").strip().upper()
    if not probe:
        return ""
    if probe in spec.entries:
        return probe
    for token in sorted(spec.entries.keys(), key=len, reverse=True):
        if probe.startswith(token):
            return token
    return ""


def _sanitize_ticket_progression(*, phase: str, next_gate_condition: str) -> str:
    phase_token = phase.split("-", 1)[0].strip().upper()
    if not phase_token:
        return next_gate_condition
    if phase_rank(phase_token) < phase_rank("4") and contains_ticket_prompt(next_gate_condition):
        return "Proceed with current phase evidence collection; ticket input is not allowed before phase 4"
    return next_gate_condition


def _normalize_source(source: str) -> str:
    if source == "kernel":
        return "kernel"
    if source in ("spec-next", "spec"):
        return "spec"
    if source in ("transition", "not_applicable"):
        return source
    if source.startswith("phase-"):
        return "transition"
    return "kernel"


def _resolve_paths(runtime_ctx: RuntimeContext) -> tuple[Path | None, Path | None, Path | None, bool, list[str]]:
    if runtime_ctx.commands_home is not None:
        commands_home = runtime_ctx.commands_home
        workspaces_home = runtime_ctx.workspaces_home
        config_root = runtime_ctx.config_root
        return commands_home, workspaces_home, config_root, True, []
    resolver = BindingEvidenceResolver()
    evidence = getattr(resolver, "resolve")(mode="kernel")
    return evidence.commands_home, evidence.workspaces_home, evidence.config_root, evidence.binding_ok, list(evidence.issues)


def _resolve_flow_paths(commands_home: Path | None, workspaces_home: Path | None, repo_fingerprint: str) -> dict[str, Path]:
    """Resolve flow log paths - workspace-only model.
    
    Wave 25b: Only return workspace log paths, no commands/logs/ fallback.
    """
    paths: dict[str, Path] = {}
    # Workspace-only paths (Wave 25b target)
    if workspaces_home is not None and repo_fingerprint:
        paths["workspace_events"] = workspaces_home / repo_fingerprint / "events.jsonl"
        paths["workspace_flow"] = get_workspace_logs_root(repo_fingerprint) / "flow.log.jsonl"
        paths["workspace_boot"] = get_workspace_logs_root(repo_fingerprint) / "boot.log.jsonl"
        paths["workspace_error"] = get_workspace_logs_root(repo_fingerprint) / "error.log.jsonl"
    _ = commands_home
    return paths


def _append_event(path: Path, event: dict[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl_event(path, event, append=True)
        return True
    except Exception:
        return False


def _read_nested_key(state: Mapping[str, object], path: str) -> object | None:
    current: object = state
    for key in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _validate_exit(entry: PhaseSpecEntry, state: Mapping[str, object]) -> tuple[bool, str]:
    for key_path in entry.exit_required_keys:
        value = _read_nested_key(state, key_path)
        if value is None:
            return False, f"missing exit evidence key: {key_path}"
        if isinstance(value, str) and not value.strip():
            return False, f"empty exit evidence key: {key_path}"
    if entry.token == "3A":
        status = _read_nested_key(state, "APIInventory.Status")
        if isinstance(status, str) and status.strip().lower() not in {"completed", "not-applicable"}:
            return False, "APIInventory.Status must be completed|not-applicable"
    return True, "ok"


def _validate_phase_1_3_foundation(state: Mapping[str, object]) -> tuple[bool, str]:
    for key_path in (
        "LoadedRulebooks.core",
        "LoadedRulebooks.profile",
        "RulebookLoadEvidence.core",
        "RulebookLoadEvidence.profile",
        "ActiveProfile",
        "AddonsEvidence",
    ):
        value = _read_nested_key(state, key_path)
        if value is None:
            return False, f"missing phase-1.3 evidence key: {key_path}"
        if isinstance(value, str) and not value.strip():
            return False, f"empty phase-1.3 evidence key: {key_path}"
    addons = _read_nested_key(state, "LoadedRulebooks.addons")
    if not isinstance(addons, Mapping) or not addons:
        return False, "missing phase-1.3 evidence key: LoadedRulebooks.addons"
    if not any(isinstance(value, str) and value.strip() for value in addons.values()):
        return False, "empty phase-1.3 evidence key: LoadedRulebooks.addons"
    return True, "ok"


def _ticket_or_task_recorded(state: Mapping[str, object]) -> bool:
    ticket = state.get("Ticket")
    ticket_digest = state.get("TicketRecordDigest")
    task = state.get("Task")
    task_digest = state.get("TaskRecordDigest")

    has_ticket = isinstance(ticket, str) and bool(ticket.strip())
    has_ticket_digest = isinstance(ticket_digest, str) and bool(ticket_digest.strip())
    has_task = isinstance(task, str) and bool(task.strip())
    has_task_digest = isinstance(task_digest, str) and bool(task_digest.strip())

    if has_ticket and has_ticket_digest:
        return True
    if has_task and has_task_digest:
        return True

    # Legacy compatibility: digest-only states remain routable.
    if has_ticket_digest or has_task_digest:
        return True
    return False


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value >= 0 else 0
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return int(raw)
    return None


def _read_non_empty_text(state: Mapping[str, object], *key_paths: str) -> str | None:
    for key_path in key_paths:
        value = _read_nested_key(state, key_path)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _phase5_self_review_iterations(state: Mapping[str, object]) -> int:
    for key_path in (
        "Phase5Review.iteration",
        "Phase5Review.Iteration",
        "Phase5Review.rounds_completed",
        "Phase5Review.RoundsCompleted",
        "phase5_self_review_iterations",
        "phase5SelfReviewIterations",
        "self_review_iterations",
    ):
        value = _read_nested_key(state, key_path)
        parsed = _coerce_non_negative_int(value)
        if parsed is not None:
            return parsed
    return 0


def _phase5_max_review_iterations(state: Mapping[str, object]) -> int:
    for key_path in (
        "Phase5Review.max_iterations",
        "Phase5Review.MaxIterations",
        "phase5_max_review_iterations",
        "phase5MaxReviewIterations",
    ):
        value = _read_nested_key(state, key_path)
        parsed = _coerce_non_negative_int(value)
        if parsed is not None and parsed >= 1:
            return min(parsed, 3)
    return 3


def _phase5_revision_delta(state: Mapping[str, object]) -> str:
    prev_digest = _read_non_empty_text(
        state,
        "Phase5Review.prev_plan_digest",
        "Phase5Review.PrevPlanDigest",
        "phase5_prev_plan_digest",
        "phase5PrevPlanDigest",
    )
    curr_digest = _read_non_empty_text(
        state,
        "Phase5Review.curr_plan_digest",
        "Phase5Review.CurrPlanDigest",
        "phase5_curr_plan_digest",
        "phase5CurrPlanDigest",
    )
    if prev_digest and curr_digest and prev_digest == curr_digest:
        return "none"
    return "changed"


def _phase5_state_value(state: Mapping[str, object]) -> str:
    value = _read_non_empty_text(state, "phase5_state", "Phase5State", "Phase5Review.completion_status")
    return value.lower() if value else ""


def _phase5_blocker_code(state: Mapping[str, object]) -> str:
    value = _read_non_empty_text(
        state,
        "phase5_blocker_code",
        "Phase5BlockerCode",
        "Phase5Review.blocker_code",
        "Phase5Review.reason_code",
    )
    return value if value else "none"


def _phase5_completed_explicit(state: Mapping[str, object]) -> bool:
    for key_path in ("phase5_completed", "Phase5Completed", "Phase5Review.self_review_iterations_met"):
        value = _read_nested_key(state, key_path)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
    state_value = _phase5_state_value(state)
    return state_value in {"phase5_completed", "phase5-complete", "phase5-completed"}


def _phase6_review_iterations(state: Mapping[str, object]) -> int:
    for key_path in (
        "ImplementationReview.iteration",
        "ImplementationReview.Iteration",
        "phase6_review_iterations",
        "phase6ReviewIterations",
    ):
        value = _read_nested_key(state, key_path)
        parsed = _coerce_non_negative_int(value)
        if parsed is not None:
            return parsed
    return 0


_phase6_default_max_cache: int | None = None


def _get_phase6_default_max_iterations(state: Mapping[str, object]) -> int:
    """Get phase6 max review iterations default from governance config.
    
    Uses centralized governance config loader with workspace resolution from state.
    Falls back to 3 if config unavailable or workspace not determinable.
    """
    global _phase6_default_max_cache
    if _phase6_default_max_cache is not None:
        return _phase6_default_max_cache
    
    try:
        fp = _extract_fingerprint(state)
        if fp:
            evidence = BindingEvidenceResolver(env={})
            ev = getattr(evidence, "resolve")(mode="system")
            workspaces_home = ev.workspaces_home
            if workspaces_home is not None:
                workspace_dir = workspaces_home / fp
                from governance_runtime.infrastructure.governance_config_loader import get_review_iterations
                _, phase6 = get_review_iterations(workspace_dir)
                _phase6_default_max_cache = phase6
                return phase6
    except Exception:
        pass
    
    _phase6_default_max_cache = 3
    return 3


def _clear_phase6_default_max_cache() -> None:
    """Clear the phase6 default max iterations cache (for testing)."""
    global _phase6_default_max_cache
    _phase6_default_max_cache = None


def _phase6_max_review_iterations(state: Mapping[str, object]) -> int:
    default_max = _get_phase6_default_max_iterations(state)
    for key_path in (
        "ImplementationReview.max_iterations",
        "ImplementationReview.MaxIterations",
        "phase6_max_review_iterations",
        "phase6MaxReviewIterations",
    ):
        value = _read_nested_key(state, key_path)
        parsed = _coerce_non_negative_int(value)
        if parsed is not None and parsed >= 1:
            return parsed
    return default_max


def _phase6_min_review_iterations(state: Mapping[str, object]) -> int:
    for key_path in (
        "ImplementationReview.min_self_review_iterations",
        "ImplementationReview.MinSelfReviewIterations",
        "phase6_min_self_review_iterations",
        "phase6MinSelfReviewIterations",
    ):
        value = _read_nested_key(state, key_path)
        parsed = _coerce_non_negative_int(value)
        if parsed is not None and parsed >= 1:
            return min(parsed, 3)
    return 1


def _phase6_revision_delta(state: Mapping[str, object]) -> str:
    prev_digest = _read_non_empty_text(
        state,
        "ImplementationReview.prev_impl_digest",
        "ImplementationReview.PrevImplDigest",
        "phase6_prev_impl_digest",
        "phase6PrevImplDigest",
    )
    curr_digest = _read_non_empty_text(
        state,
        "ImplementationReview.curr_impl_digest",
        "ImplementationReview.CurrImplDigest",
        "phase6_curr_impl_digest",
        "phase6CurrImplDigest",
    )
    if prev_digest and curr_digest and prev_digest == curr_digest:
        return "none"
    return "changed"


def _phase5_review_loop_complete(
    *,
    entry: PhaseSpecEntry,
    state: Mapping[str, object],
    plan_record_versions: int,
) -> bool:
    if plan_record_versions < 1:
        return False

    state_value = _phase5_state_value(state)
    if state_value == "phase5_blocked":
        return False
    if _phase5_completed_explicit(state):
        return True

    iteration = _phase5_self_review_iterations(state)
    max_iterations = _phase5_max_review_iterations(state)
    min_iterations = max(1, _phase5_min_self_review_iterations(entry))
    revision_delta = _phase5_revision_delta(state)

    if iteration >= max_iterations:
        return True
    if iteration >= min_iterations and revision_delta == "none":
        return True
    return False


def _phase6_internal_review_complete(state: Mapping[str, object]) -> bool:
    iterations = _phase6_review_iterations(state)
    max_iterations = _phase6_max_review_iterations(state)
    min_iterations = _phase6_min_review_iterations(state)
    revision_delta = _phase6_revision_delta(state)

    if iterations >= max_iterations:
        return True
    if iterations >= min_iterations and revision_delta == "none":
        return True
    return False


def _user_review_decision(state: Mapping[str, object]) -> str:
    """Read the user's final review decision from SESSION_STATE.

    Returns one of ``"approve"``, ``"changes_requested"``, ``"reject"``,
    or ``""`` if no decision has been recorded.
    """
    decision = state.get("UserReviewDecision")
    if isinstance(decision, Mapping):
        value = decision.get("decision")
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"approve", "changes_requested", "reject"}:
                return normalized
    for key in ("user_review_decision", "UserReviewDecision"):
        value = state.get(key)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"approve", "changes_requested", "reject"}:
                return normalized
    return ""


def _phase6_evidence_presentation_gate_active(state: Mapping[str, object]) -> bool:
    """Return True only when Phase 6 Evidence Presentation Gate is active."""

    for key in ("active_gate", "ActiveGate", "Gate"):
        value = state.get(key)
        if isinstance(value, str) and value.strip().lower() == "evidence presentation gate":
            return True
    return False


def pipeline_auto_approve_eligible(state: Mapping[str, object]) -> bool:
    """Check if pipeline mode is eligible for auto-approve at Evidence Presentation Gate.

    Eligibility conditions (ALL must be true):
    - effective_operating_mode == "pipeline" (NOT agents_strict)
    - Internal review is complete
    - At Evidence Presentation Gate
    - No existing review decision recorded

    This function is used by the kernel to determine if a pipeline auto-approve
    transition is possible. When the kernel signals source="pipeline-auto-approve",
    the session_reader materialization path automatically consumes this signal and
    calls apply_review_decision() in review_decision_persist.py to execute
    the approval.

    Args:
        state: Current session state mapping

    Returns:
        True if eligible for pipeline auto-approve, False otherwise
    """
    effective_mode = str(state.get("effective_operating_mode", "")).strip()

    if effective_mode != "pipeline":
        return False

    if not _phase6_internal_review_complete(state):
        return False

    if not _phase6_evidence_presentation_gate_active(state):
        return False

    if _user_review_decision(state):
        return False

    if _workflow_complete(state):
        return False

    return True


def _phase6_rework_clarification_pending(state: Mapping[str, object]) -> bool:
    """Return True when Phase 6 is waiting for rework clarification."""

    consumed = state.get("rework_clarification_consumed")
    if isinstance(consumed, bool) and consumed:
        return False

    if isinstance(consumed, str) and consumed.strip().lower() in {"true", "1", "yes"}:
        return False

    phase6_state = str(state.get("phase6_state") or "").strip().lower()
    if phase6_state == "phase6_changes_requested":
        return True
    for key in ("active_gate", "ActiveGate", "Gate"):
        value = state.get(key)
        if isinstance(value, str) and value.strip().lower() == "rework clarification gate":
            return True
    return False


def _workflow_complete(state: Mapping[str, object]) -> bool:
    """Check if the workflow has been marked complete (approve decision applied)."""
    for key in ("workflow_complete", "WorkflowComplete"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _implementation_started(state: Mapping[str, object]) -> bool:
    for key in ("implementation_started", "ImplementationStarted"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _implementation_execution_in_progress(state: Mapping[str, object]) -> bool:
    status = str(
        state.get("implementation_execution_status")
        or _read_nested_key(state, "implementation_execution_status")
        or ""
    ).strip().lower()
    return status in {"in_progress", "self_review", "revision", "verification"}


def _implementation_presentation_ready(state: Mapping[str, object]) -> bool:
    gate = str(state.get("active_gate") or "").strip().lower()
    if gate == "implementation presentation gate":
        return True
    presented = state.get("implementation_package_presented")
    stable = state.get("implementation_quality_stable")
    return bool(presented) and bool(stable)


def _implementation_blocked(state: Mapping[str, object]) -> bool:
    gate = str(state.get("active_gate") or "").strip().lower()
    if gate == "implementation blocked":
        return True
    status = str(state.get("implementation_execution_status") or "").strip().lower()
    if status == "blocked":
        return True
    blockers = state.get("implementation_hard_blockers")
    return isinstance(blockers, list) and len(blockers) > 0


def _implementation_rework_clarification_pending(state: Mapping[str, object]) -> bool:
    gate = str(state.get("active_gate") or "").strip().lower()
    if gate == "implementation rework clarification gate":
        return True
    required = state.get("implementation_rework_clarification_required")
    return bool(required)


def _implementation_accepted(state: Mapping[str, object]) -> bool:
    gate = str(state.get("active_gate") or "").strip().lower()
    if gate == "implementation accepted":
        return True
    accepted = state.get("implementation_accepted")
    return bool(accepted)


def _phase5_min_self_review_iterations(entry: PhaseSpecEntry) -> int:
    policy = resolve_phase_output_policy(entry.token)
    if policy is None:
        return 0
    return max(0, int(policy.plan_discipline.min_self_review_iterations))


def _phase5_self_review_iterations_met(
    *,
    entry: PhaseSpecEntry,
    state: Mapping[str, object],
    plan_record_versions: int,
) -> bool:
    return _phase5_review_loop_complete(
        entry=entry,
        state=state,
        plan_record_versions=plan_record_versions,
    )


def _phase5_gate_condition(
    *,
    entry: PhaseSpecEntry,
    state: Mapping[str, object],
    plan_record_versions: int,
    active_gate: str,
    fallback: str,
) -> str:
    gate = active_gate.strip().lower()
    if gate == "plan record preparation gate":
        if plan_record_versions < 1:
            return (
                "Plan record v1 missing (plan_record_versions=0). "
                "Persist plan-record evidence via /plan before architecture review."
            )
        return (
            "Plan record evidence is present. Continue in the Architecture Review Gate "
            "for deterministic internal self-review."
        )

    if gate == "architecture review gate":
        state_value = _phase5_state_value(state)
        if state_value == "phase5_blocked":
            blocker_code = _phase5_blocker_code(state)
            return (
                "Phase 5 self-review is blocked. "
                f"reason_code={blocker_code}. "
                "Apply the recorded recovery action and rerun /plan."
            )

        iteration = _phase5_self_review_iterations(state)
        max_iterations = _phase5_max_review_iterations(state)
        max_iterations = max_iterations if max_iterations >= 1 else 3
        revision_delta = _phase5_revision_delta(state)
        review_met = _phase5_self_review_iterations_met(
            entry=entry,
            state=state,
            plan_record_versions=plan_record_versions,
        )
        if review_met:
            completion_status = _read_non_empty_text(
                state,
                "phase5_completion_status",
                "Phase5Review.completion_status",
            )
            completion_note = (
                f", completion_status={completion_status}" if completion_status else ""
            )
            action = "Proceed to Phase 5.3 test-quality gate."
        else:
            action = "Continue architecture self-review until completion criteria are met."
            completion_note = ""
        return (
            "Phase 5 self-review status: "
            f"iteration={iteration}/{max_iterations}, "
            f"revision_delta={revision_delta}, "
            f"self_review_iterations_met={str(review_met).lower()}{completion_note}. "
            f"{action}"
        )

    return fallback


def _select_transition(
    entry: PhaseSpecEntry,
    state: Mapping[str, object],
    *,
    plan_record_versions: int,
) -> tuple[str | None, str, str | None, str | None]:
    if entry.transitions:
        for transition in entry.transitions:
            when = transition.when.strip().lower()
            if when in {"ticket_present", "ticket_intake_complete"} and _ticket_or_task_recorded(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "business_rules_execute" and not _business_rules_discovery_resolved(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "no_apis" and not api_in_scope(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "business_rules_gate_required" and _phase_1_5_executed(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "technical_debt_proposed" and _technical_debt_proposed(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "rollback_required" and _rollback_required(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "plan_record_missing" and plan_record_versions < 1:
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "plan_record_present" and plan_record_versions >= 1:
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "self_review_iterations_pending" and not _phase5_self_review_iterations_met(
                entry=entry,
                state=state,
                plan_record_versions=plan_record_versions,
            ):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "self_review_iterations_met" and _phase5_self_review_iterations_met(
                entry=entry,
                state=state,
                plan_record_versions=plan_record_versions,
            ):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "rework_clarification_pending" and _phase6_rework_clarification_pending(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_review_pending" and not _phase6_internal_review_complete(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_accepted" and _implementation_accepted(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_blocked" and _implementation_blocked(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_rework_clarification_pending" and _implementation_rework_clarification_pending(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_presentation_ready" and _implementation_presentation_ready(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_execution_in_progress" and _implementation_execution_in_progress(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "workflow_approved" and _workflow_complete(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_started" and _implementation_started(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if (
                when == "review_changes_requested"
                and _phase6_evidence_presentation_gate_active(state)
                and _user_review_decision(state) == "changes_requested"
            ):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if (
                when == "review_rejected"
                and _phase6_evidence_presentation_gate_active(state)
                and _user_review_decision(state) == "reject"
            ):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "implementation_review_complete" and _phase6_internal_review_complete(state):
                if pipeline_auto_approve_eligible(state):
                    return (
                        transition.next_token,
                        "pipeline-auto-approve",
                        "Pipeline Auto-Approved",
                        "Workflow auto-approved in pipeline mode. Implementation authorized.",
                    )
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "default":
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
        return (entry.next_token, "spec-next", None, None)
    return (entry.next_token, "spec-next", None, None)


def _emit_phase_event(log_paths: Mapping[str, Path], event: dict[str, object]) -> tuple[bool, dict[str, str]]:
    # Canonical audit log: events.jsonl
    # Operational mirror/debug: flow.log.jsonl
    workspace_written = False
    workspace_path = log_paths.get("workspace_events")
    workspace_flow = log_paths.get("workspace_flow")
    if workspace_path is None:
        return True, {
            "phase_flow": str(workspace_flow or ""),
            "workspace_events": "",
        }
    if workspace_path is not None:
        workspace_written = _append_event(workspace_path, event)
        if workspace_flow is not None:
            _append_event(workspace_flow, event)

    if workspace_written:
        phase_flow_path = workspace_flow if workspace_flow is not None else workspace_path
        return True, {
            "phase_flow": str(phase_flow_path),
            "workspace_events": str(workspace_path),
        }
    return False, {
        "phase_flow": str(workspace_flow or workspace_path or ""),
        "workspace_events": "",
    }


@dataclass(frozen=True)
class _CriteriaDedupeResult:
    """Result of deduplicating pass_criteria by criterion_key."""

    criteria: list[Mapping[str, object]]
    conflicts: list[str]  # Human-readable conflict descriptions
    had_duplicates: bool


def _deduplicate_criteria(
    raw_criteria: Sequence[Mapping[str, object]],
) -> _CriteriaDedupeResult:
    """Deduplicate pass_criteria by ``criterion_key``, merging to strictest.

    Compatible duplicates (same ``artifact_kind``, same resolver config)
    are merged with strictest-wins semantics:
    * ``critical``: ``True`` wins over ``False``.
    * ``threshold`` (static): higher value wins (= stricter minimum).

    Incompatible duplicates (different ``artifact_kind``, different
    ``threshold_mode`` or ``threshold_resolver``) are flagged as conflicts.
    The caller decides how to handle conflicts (block vs. warn).
    """
    seen: dict[str, dict[str, object]] = {}   # criterion_key → merged entry
    conflicts: list[str] = []
    had_duplicates = False

    # Fields that must be identical for compatibility.
    _COMPAT_FIELDS = ("artifact_kind", "threshold_mode", "threshold_resolver")

    for criterion in raw_criteria:
        key = str(criterion.get("criterion_key", "")).strip()
        if not key:
            # No criterion_key → pass through unmodified (not dedup-able).
            key = f"__anonymous_{id(criterion)}"
            seen[key] = dict(criterion)
            continue

        if key not in seen:
            seen[key] = dict(criterion)
            continue

        # Duplicate detected.
        had_duplicates = True
        existing = seen[key]

        # Check compatibility on identity-fields.
        incompatible_fields: list[str] = []
        for field in _COMPAT_FIELDS:
            existing_val = existing.get(field)
            new_val = criterion.get(field)
            # Treat None/missing as equivalent.
            if existing_val is None and new_val is None:
                continue
            if existing_val != new_val:
                value_set = sorted({repr(existing_val), repr(new_val)})
                incompatible_fields.append(
                    f"{field} in {{{', '.join(value_set)}}}"
                )

        if incompatible_fields:
            detail = "; ".join(incompatible_fields)
            conflicts.append(
                f"criterion_key={key!r}: incompatible definitions — {detail}"
            )
            # Keep the existing entry; conflict is flagged for the caller.
            continue

        # Compatible duplicate → merge to strictest.
        # critical: True wins.
        if criterion.get("critical") is True:
            existing["critical"] = True

        # threshold (static): higher = stricter minimum.
        new_threshold = criterion.get("threshold")
        old_threshold = existing.get("threshold")
        if isinstance(new_threshold, (int, float)) and isinstance(old_threshold, (int, float)):
            if new_threshold > old_threshold:
                existing["threshold"] = new_threshold
        elif isinstance(new_threshold, (int, float)) and old_threshold is None:
            existing["threshold"] = new_threshold

    return _CriteriaDedupeResult(
        criteria=list(seen.values()),
        conflicts=sorted(conflicts),
        had_duplicates=had_duplicates,
    )


def evaluate_readonly(
    *,
    current_token: str,
    session_state_doc: Mapping[str, object] | None,
    runtime_ctx: RuntimeContext,
) -> KernelResult:
    """Side-effect-free kernel evaluation.

    Returns the same ``KernelResult`` as ``execute()`` but guarantees:
    - No file writes (no JSONL events, no error logs, no directory creation)
    - No global state mutations
    - Safe to call from read-only UX paths (session_reader readout)

    The ``log_paths`` field in the result may contain empty strings when
    events would normally be written but were suppressed.
    """
    return execute(
        current_token=current_token,
        session_state_doc=session_state_doc,
        runtime_ctx=runtime_ctx,
        readonly=True,
    )


def execute(
    *,
    current_token: str,
    session_state_doc: Mapping[str, object] | None,
    runtime_ctx: RuntimeContext,
    readonly: bool = False,
) -> KernelResult:
    state = _session_state(session_state_doc)
    commands_home, workspaces_home, config_root, binding_ok, binding_issues = _resolve_paths(runtime_ctx)
    repo_fingerprint = runtime_ctx.live_repo_fingerprint or _extract_fingerprint(state)
    plan_record_file = workspaces_home / repo_fingerprint / "plan-record.json" if workspaces_home is not None and repo_fingerprint else None
    plan_record_signal = resolve_plan_record_signal(state=state, plan_record_file=plan_record_file)
    event_id = uuid.uuid4().hex

    if not binding_ok:
        issue_text = ", ".join(binding_issues) if binding_issues else "binding evidence missing"
        log_paths = _resolve_flow_paths(commands_home, workspaces_home, repo_fingerprint)
        if not readonly:
            emit_error_event(
                severity="CRITICAL",
                code="BINDING_EVIDENCE_INVALID",
                message=issue_text,
                repo_fingerprint=repo_fingerprint or None,
                config_root=config_root,
                workspaces_home=workspaces_home,
                commands_home=commands_home,
                context={"issues": binding_issues},
            )
        return KernelResult(
            phase="1.1-Bootstrap",
            next_token="1.1",
            active_gate="Binding Evidence Gate",
            next_gate_condition="BLOCKED_BINDING_EVIDENCE_INVALID: commands home binding is required.",
            workspace_ready=False,
            source="binding-evidence-invalid",
            status="BLOCKED",
            spec_hash="",
            spec_path="",
            spec_loaded_at="",
            log_paths={
                "phase_flow": str(log_paths.get("workspace_flow") or ""),
                "workspace_events": str(log_paths.get("workspace_events") or ""),
            },
            event_id=event_id,
            plan_record_status=plan_record_signal.status,
            plan_record_versions=plan_record_signal.versions,
        )

    try:
        spec = load_phase_api(commands_home)
    except PhaseApiSpecError as exc:
        log_paths = _resolve_flow_paths(commands_home, workspaces_home, repo_fingerprint)
        phase_api_path = str((commands_home / "phase_api.yaml") if commands_home is not None else "")
        if not readonly:
            _emit_phase_event(
                log_paths,
                {
                    "schema": "opencode.phase-flow.v1",
                    "ts_utc": _utc_now(),
                    "event_id": event_id,
                    "event": "PHASE_BLOCKED",
                    "source": _normalize_source("phase-api-missing"),
                    "phase": "1.1-Bootstrap",
                    "phase_token": "1.1",
                    "next_token": "1.1",
                    "status": "BLOCKED",
                    "reason": str(exc),
                    "spec_path": phase_api_path,
                    "spec_hash": "",
                },
            )
            emit_error_event(
                severity="CRITICAL",
                code="PHASE_API_MISSING",
                message=str(exc),
                repo_fingerprint=repo_fingerprint or None,
                config_root=config_root,
                workspaces_home=workspaces_home,
                commands_home=commands_home,
                context={"phase_api_path": phase_api_path},
            )
        return KernelResult(
            phase="1.1-Bootstrap",
            next_token="1.1",
            active_gate="Workspace Ready Gate",
            next_gate_condition="BLOCKED_PHASE_API_MISSING: authoritative phase_api.yaml is required in governance_spec.",
            workspace_ready=False,
            source="phase-api-missing",
            status="BLOCKED",
            spec_hash="",
            spec_path=phase_api_path,
            spec_loaded_at="",
            log_paths={
                "phase_flow": str(log_paths.get("workspace_flow") or ""),
                "workspace_events": str(log_paths.get("workspace_events") or ""),
            },
            event_id=event_id,
            plan_record_status=plan_record_signal.status,
            plan_record_versions=plan_record_signal.versions,
        )

    persisted_phase = _extract_phase(state)
    persisted_token = _normalize_token(persisted_phase, spec)
    requested_token = _normalize_token(current_token, spec)
    chosen_token = persisted_token or requested_token or spec.start_token
    log_paths = _resolve_flow_paths(commands_home, workspaces_home, repo_fingerprint)

    if persisted_token and requested_token and phase_rank(requested_token) >= phase_rank(persisted_token):
        chosen_token = requested_token

    workspace_ready, workspace_reason = _persistence_gate_passed(state)

    if not readonly:
        _emit_phase_event(
            log_paths,
            {
                "schema": "opencode.phase-flow.v1",
                "ts_utc": _utc_now(),
                "event_id": event_id,
                "event": "PHASE_STARTED",
                "source": "kernel",
                "phase": spec.entries[chosen_token].phase,
                "phase_token": chosen_token,
                "status": "STARTED",
                "spec_hash": spec.stable_hash,
                "spec_path": str(spec.path),
            },
        )

    def _blocked_result(*, phase: str, token: str, active_gate: str, next_gate_condition: str, source: str, reason: str, detail: dict[str, object] | None = None) -> KernelResult:
        event_payload: dict[str, object] = {
            "schema": "opencode.phase-flow.v1",
            "ts_utc": _utc_now(),
            "event_id": event_id,
            "event": "PHASE_BLOCKED",
            "source": _normalize_source(source),
            "phase": phase,
            "phase_token": token,
            "next_token": token,
            "status": "BLOCKED",
            "reason": reason,
            "spec_hash": spec.stable_hash,
            "spec_path": str(spec.path),
        }
        if detail is not None:
            event_payload["strict_exit_detail"] = detail
        if readonly:
            # Readonly mode: skip all file writes, produce empty log paths
            result_paths: dict[str, str] = {
                "phase_flow": str(log_paths.get("workspace_flow") or ""),
                "workspace_events": str(log_paths.get("workspace_events") or ""),
            }
        else:
            written, result_paths = _emit_phase_event(
                log_paths,
                event_payload,
            )
            if not written:
                emit_error_event(
                    severity="HIGH",
                    code="PHASE_FLOW_LOG_WRITE_FAILED",
                    message="unable to write phase flow log",
                    repo_fingerprint=repo_fingerprint or None,
                    config_root=config_root,
                    workspaces_home=workspaces_home,
                    commands_home=commands_home,
                    context={"phase": phase, "source": source},
                )
            emit_error_event(
                severity="HIGH",
                code="PHASE_BLOCKED",
                message=reason,
                repo_fingerprint=repo_fingerprint or None,
                config_root=config_root,
                workspaces_home=workspaces_home,
                commands_home=commands_home,
                context={"phase": phase, "phase_token": token, "source": source, "next_gate_condition": next_gate_condition},
            )
        _blocked_entry = spec.entries.get(token)
        return KernelResult(
            phase=phase,
            next_token=token,
            active_gate=active_gate,
            next_gate_condition=next_gate_condition,
            workspace_ready=workspace_ready,
            source=source,
            status="BLOCKED",
            spec_hash=spec.stable_hash,
            spec_path=str(spec.path),
            spec_loaded_at=spec.loaded_at,
            log_paths=result_paths,
            event_id=event_id,
            strict_exit_result=strict_exit_result,
            route_strategy=_blocked_entry.route_strategy if _blocked_entry is not None else "",
            plan_record_status=plan_record_signal.status,
            plan_record_versions=plan_record_signal.versions,
            transition_evidence_met=_transition_has_evidence(state),
        )

    strict_exit_result: StrictExitResult | None = None

    if phase_rank(chosen_token or "") >= phase_rank("2") and not workspace_ready:
        return _blocked_result(
            phase="1.1-Bootstrap",
            token="1.1",
            active_gate="Workspace Ready Gate",
            next_gate_condition=f"BLOCKED_PERSISTENCE_FAILED: {workspace_reason}. Commit workspace readiness before phase progression.",
            source="workspace-ready-gate",
            reason=workspace_reason,
        )

    if (
        persisted_token
        and requested_token
        and phase_rank(requested_token) < phase_rank(persisted_token)
        and not (persisted_token == "1.2" and workspace_ready)
    ):
        entry = spec.entries[persisted_token]
        monotonic_next_token, monotonic_source, monotonic_gate, monotonic_condition = _select_transition(
            entry,
            state,
            plan_record_versions=plan_record_signal.versions,
        )

        # Spec-declared backward transition: the persisted phase's own
        # transition table produced a next_token that matches the
        # requested backward target (e.g. Phase 6 review_rejected → "4").
        # Honour the spec rather than blocking the move.
        if (
            monotonic_next_token
            and monotonic_next_token == requested_token
            and _transition_has_evidence(state)
        ):
            chosen_token = requested_token
        else:
            persisted_gate = monotonic_gate or entry.active_gate or runtime_ctx.requested_active_gate
            persisted_condition = monotonic_condition or entry.next_gate_condition or runtime_ctx.requested_next_gate_condition
            if entry.route_strategy == "next" and monotonic_next_token and monotonic_next_token in spec.entries and monotonic_gate is None:
                next_entry = spec.entries[monotonic_next_token]
                persisted_gate = next_entry.active_gate or persisted_gate
            if entry.token == "5":
                persisted_condition = _phase5_gate_condition(
                    entry=entry,
                    state=state,
                    plan_record_versions=plan_record_signal.versions,
                    active_gate=persisted_gate,
                    fallback=persisted_condition,
                )
            return KernelResult(
                phase=entry.phase,
                next_token=monotonic_next_token or persisted_token,
                active_gate=persisted_gate,
                next_gate_condition=_sanitize_ticket_progression(phase=entry.phase, next_gate_condition=persisted_condition),
                workspace_ready=workspace_ready,
                source="monotonic-session-phase",
                status="OK",
                spec_hash=spec.stable_hash,
                spec_path=str(spec.path),
                spec_loaded_at=spec.loaded_at,
                log_paths={},
                event_id=event_id,
                route_strategy=entry.route_strategy,
                plan_record_status=plan_record_signal.status,
                plan_record_versions=plan_record_signal.versions,
                transition_evidence_met=_transition_has_evidence(state),
            )

    if requested_token and persisted_token and requested_token != persisted_token:
        allowed_next_tokens = {persisted_token}
        persisted_entry = spec.entries[persisted_token]
        if persisted_entry.next_token:
            allowed_next_tokens.add(persisted_entry.next_token)
        allowed_next_tokens.update(tr.next_token for tr in persisted_entry.transitions)
        if requested_token not in allowed_next_tokens:
            return _blocked_result(
                phase=persisted_phase or persisted_entry.phase,
                token=persisted_token,
                active_gate=persisted_entry.active_gate or runtime_ctx.requested_active_gate,
                next_gate_condition="PHASE_BLOCKED: requested phase transition not allowed by phase_api.yaml",
                source="phase-transition-not-allowed",
                reason=f"requested transition {persisted_token}->{requested_token} is not in spec graph",
            )
        if phase_rank(requested_token) > phase_rank(persisted_token) and not _transition_has_evidence(state):
            return _blocked_result(
                phase=persisted_phase or persisted_entry.phase,
                token=persisted_token,
                active_gate=persisted_entry.active_gate or runtime_ctx.requested_active_gate,
                next_gate_condition="PHASE_BLOCKED: transition evidence required for requested phase jump",
                source="phase-transition-evidence-required",
                reason="phase transition evidence missing",
            )

    if phase_rank(chosen_token) < phase_rank("4") and (
        contains_ticket_prompt(runtime_ctx.requested_next_gate_condition)
        or contains_ticket_prompt(runtime_ctx.requested_active_gate)
    ):
        return _blocked_result(
            phase=spec.entries[chosen_token].phase,
            token=chosen_token,
            active_gate=spec.entries[chosen_token].active_gate,
            next_gate_condition="PHASE_BLOCKED: ticket input is forbidden before phase 4",
            source="ticket-present-pre-phase4",
            reason="ticket_present_pre_phase4",
        )

    if persisted_token and requested_token and phase_rank(requested_token) - phase_rank(persisted_token) > 1 and not _transition_has_evidence(state):
        entry = spec.entries[persisted_token]
        return _blocked_result(
            phase=persisted_phase or entry.phase,
            token=persisted_token,
            active_gate=entry.active_gate or runtime_ctx.requested_active_gate,
            next_gate_condition="Phase transition evidence required before advancing beyond next immediate phase",
            source="phase-transition-evidence-required",
            reason="phase transition evidence missing",
        )

    if phase_rank(chosen_token) >= phase_rank("2"):
        rulebooks_ok, rulebook_reason = _rulebook_gate_passed(state)
        if not rulebooks_ok:
            entry_13 = spec.entries.get("1.3")
            return _blocked_result(
                phase=entry_13.phase if entry_13 else "1.3-RulebookLoad",
                token="1.3",
                active_gate=entry_13.active_gate if entry_13 else "Rulebook Load Gate",
                next_gate_condition=f"BLOCKED_RULEBOOK_MISSING: {rulebook_reason}. Load required rulebooks before advancing.",
                source="rulebook-load-gate",
                reason=rulebook_reason,
            )
        foundation_ok, foundation_reason = _validate_phase_1_3_foundation(state)
        if not foundation_ok:
            entry_13 = spec.entries.get("1.3")
            return _blocked_result(
                phase=entry_13.phase if entry_13 else "1.3-RulebookLoad",
                token="1.3",
                active_gate=entry_13.active_gate if entry_13 else "Rulebook Load Gate",
                next_gate_condition=f"PHASE_BLOCKED: {foundation_reason}",
                source="phase-exit-evidence-missing",
                reason=foundation_reason,
            )

    entry = spec.entries[chosen_token]
    exit_ok, exit_reason = _validate_exit(entry, state)
    if not exit_ok:
        return _blocked_result(
            phase=entry.phase,
            token=chosen_token,
            active_gate=entry.active_gate,
            next_gate_condition=f"PHASE_BLOCKED: {exit_reason}",
            source="phase-exit-evidence-missing",
            reason=exit_reason,
        )

    if chosen_token == "6":
        _can_promote, _p6_prereq = can_promote_to_phase6(
            session_state=state,
            phase_1_5_executed=_phase_1_5_executed(state),
            rollback_safety_applies=_rollback_safety_applies(state),
        )
        if not _can_promote:
            # Surface the evaluator's gate-specific reason code (SSOT).
            # The evaluator already sets reason_code to the specific
            # gate-level code (e.g. BLOCKED-P5-3-TEST-QUALITY-GATE)
            # based on first_open_gate.
            _first_open = _p6_prereq.first_open_gate
            _blocking_reason_code = _p6_prereq.reason_code
            if _first_open:
                _block_detail = f"{_blocking_reason_code}: first open gate is {_first_open}"
            else:
                _block_detail = _blocking_reason_code
            return _blocked_result(
                phase=entry.phase,
                token=chosen_token,
                active_gate="Implementation QA Prerequisite Gate",
                next_gate_condition=f"PHASE_BLOCKED: {_block_detail}",
                source="p6-prerequisite-gate",
                reason=f"p6-prerequisite-gate: {_block_detail}",
                detail={
                    "p6_prerequisites": {
                        "passed": _p6_prereq.passed,
                        "reason_code": _p6_prereq.reason_code,
                        "first_open_gate": _p6_prereq.first_open_gate,
                        "p5_architecture_approved": _p6_prereq.p5_architecture_approved,
                        "p53_passed": _p6_prereq.p53_passed,
                        "p54_compliant": _p6_prereq.p54_compliant,
                        "p54_quality_reason_codes": list(_p6_prereq.p54_quality_reason_codes),
                        "p54_code_coverage_gap": _p6_prereq.p54_code_coverage_gap,
                        "p54_missing_code_surfaces": list(_p6_prereq.p54_missing_code_surfaces),
                        "p55_approved": _p6_prereq.p55_approved,
                        "p56_approved": _p6_prereq.p56_approved,
                    },
                },
            )

    # ── Strict-exit gate (principal_strict enforcement) ──────────
    _policy_mode = state.get("PolicyMode")
    _principal_strict = (
        isinstance(_policy_mode, Mapping)
        and _policy_mode.get("principal_strict") is True
    )
    _phase_exit_contract = state.get("phase_exit_contract")
    if isinstance(_phase_exit_contract, list) and _phase_exit_contract:
        # Build pass_criteria matching the current phase token
        _phase_key = f"phase_{chosen_token.replace('.', '_')}"
        _criteria: list[Mapping[str, object]] = []
        for _pec in _phase_exit_contract:
            if isinstance(_pec, Mapping) and str(_pec.get("phase", "")) == _phase_key:
                raw_criteria = _pec.get("pass_criteria")
                if isinstance(raw_criteria, list):
                    for c in raw_criteria:
                        if isinstance(c, Mapping):
                            _criteria.append(c)
        if _criteria:
            # ── Deduplicate criteria from multiple profiles ──────
            _dedup = _deduplicate_criteria(_criteria)
            if _dedup.conflicts and _principal_strict:
                # Incompatible duplicate definitions under strict mode
                # are contract conflicts → fail-closed.
                _conflict_summary = "; ".join(_dedup.conflicts)
                return _blocked_result(
                    phase=entry.phase,
                    token=chosen_token,
                    active_gate="Strict Exit Gate",
                    next_gate_condition=(
                        f"PHASE_BLOCKED: {reason_codes.BLOCKED_STRICT_CONTRACT_MISSING} "
                        f"(contract conflict: {_conflict_summary})"
                    ),
                    source="strict-exit-gate",
                    reason=(
                        f"strict-exit-gate: {reason_codes.BLOCKED_STRICT_CONTRACT_MISSING}"
                    ),
                    detail={
                        "conflict_type": "incompatible_criteria_definitions",
                        "conflicts": _dedup.conflicts,
                    },
                )
            elif _dedup.conflicts:
                # Non-strict mode: warn but continue with deduplicated set.
                if not readonly:
                    emit_error_event(
                        severity="warning",
                        code="CRITERIA_CONFLICT",
                        message=(
                            f"Duplicate criterion_key definitions with "
                            f"incompatible values (non-strict, continuing): "
                            f"{'; '.join(_dedup.conflicts)}"
                        ),
                    )
            _criteria = _dedup.criteria

            _evidence_map: dict[str, Mapping[str, object]] = {}
            _build_evidence = state.get("BuildEvidence")
            if isinstance(_build_evidence, Mapping):
                items = _build_evidence.get("items")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, Mapping):
                            ak = item.get("artifact_kind")
                            if isinstance(ak, str) and ak.strip():
                                _evidence_map[ak.strip()] = item
            _risk_tiering = state.get("RiskTiering")
            _risk_tier = "unknown"
            if isinstance(_risk_tiering, Mapping):
                _rt = _risk_tiering.get("ActiveTier")
                if isinstance(_rt, str) and _rt.strip():
                    _risk_tier = _rt.strip().lower().replace("tier-", "")
            _strict_result = evaluate_strict_exit_gate(
                pass_criteria=_criteria,
                evidence_map=_evidence_map,
                risk_tier=_risk_tier,
                principal_strict=_principal_strict,
            )
            strict_exit_result = _strict_result
            if _strict_result.blocked:
                _reason_codes_str = _strict_result.reason_codes[0] if _strict_result.reason_codes else reason_codes.BLOCKED_UNSPECIFIED
                _strict_detail = asdict(_strict_result)
                # Convert tuples to lists for JSON serialisation fidelity.
                _strict_detail["criteria"] = [asdict(c) for c in _strict_result.criteria]
                _strict_detail["reason_codes"] = list(_strict_result.reason_codes)
                return _blocked_result(
                    phase=entry.phase,
                    token=chosen_token,
                    active_gate="Strict Exit Gate",
                    next_gate_condition=f"PHASE_BLOCKED: {_strict_result.summary}",
                    source="strict-exit-gate",
                    reason=f"strict-exit-gate: {_reason_codes_str}",
                    detail=_strict_detail,
                )
        elif _principal_strict:
            # Fail-closed: principal_strict is active but no criteria
            # are defined for this phase — block the transition.
            return _blocked_result(
                phase=entry.phase,
                token=chosen_token,
                active_gate="Strict Exit Gate",
                next_gate_condition=f"PHASE_BLOCKED: {reason_codes.BLOCKED_STRICT_CONTRACT_MISSING}",
                source="strict-exit-gate",
                reason=f"strict-exit-gate: {reason_codes.BLOCKED_STRICT_CONTRACT_MISSING}",
            )

    next_token, source, override_active_gate, override_next_condition = _select_transition(
        entry,
        state,
        plan_record_versions=plan_record_signal.versions,
    )
    resolved_phase = entry.phase
    resolved_active_gate = override_active_gate or entry.active_gate or runtime_ctx.requested_active_gate
    resolved_next_condition = override_next_condition or entry.next_gate_condition or runtime_ctx.requested_next_gate_condition

    if entry.route_strategy == "next" and next_token and next_token in spec.entries:
        next_entry = spec.entries[next_token]
        resolved_phase = next_entry.phase
        if override_active_gate is None:
            resolved_active_gate = next_entry.active_gate or resolved_active_gate

    if entry.token == "5":
        resolved_next_condition = _phase5_gate_condition(
            entry=entry,
            state=state,
            plan_record_versions=plan_record_signal.versions,
            active_gate=resolved_active_gate,
            fallback=resolved_next_condition,
        )

    resolved_phase_for_event = entry.phase

    resolved_next_condition = _sanitize_ticket_progression(phase=resolved_phase, next_gate_condition=resolved_next_condition)

    event_name = "PHASE_COMPLETED"
    normalized_source = "transition"
    transition_reason = ""
    if source == "phase-3a-not-applicable-to-phase4":
        event_name = "PHASE_NOT_APPLICABLE"
        normalized_source = "not_applicable"
        transition_reason = "no_external_apis"
    elif source == "spec-next":
        normalized_source = "spec"
    elif source.startswith("phase-"):
        normalized_source = "transition"

    event_payload = {
        "schema": "opencode.phase-flow.v1",
        "ts_utc": _utc_now(),
        "event_id": event_id,
        "event": event_name,
        "source": normalized_source,
        "phase": resolved_phase_for_event,
        "phase_token": chosen_token,
        "next_token": next_token,
        "status": "OK",
        "spec_hash": spec.stable_hash,
        "spec_path": str(spec.path),
    }
    if transition_reason:
        event_payload["reason"] = transition_reason
    if source not in ("kernel", "spec-next", "transition", "not_applicable"):
        event_payload["transition_rule"] = source

    if readonly:
        result_paths = {
            "phase_flow": str(log_paths.get("workspace_flow") or ""),
            "workspace_events": str(log_paths.get("workspace_events") or ""),
        }
    else:
        written, result_paths = _emit_phase_event(
            log_paths,
            event_payload,
        )
        if not written:
            emit_error_event(
                severity="HIGH",
                code="PHASE_FLOW_LOG_WRITE_FAILED",
                message="unable to write phase flow log",
                repo_fingerprint=repo_fingerprint or None,
                config_root=config_root,
                workspaces_home=workspaces_home,
                commands_home=commands_home,
                context={"phase": resolved_phase, "source": source},
            )

    return KernelResult(
        phase=resolved_phase,
        next_token=next_token,
        active_gate=resolved_active_gate,
        next_gate_condition=resolved_next_condition,
        workspace_ready=workspace_ready,
        source=source,
        status="OK",
        spec_hash=spec.stable_hash,
        spec_path=str(spec.path),
        spec_loaded_at=spec.loaded_at,
        log_paths=result_paths,
        event_id=event_id,
        strict_exit_result=strict_exit_result,
        route_strategy=entry.route_strategy,
        plan_record_status=plan_record_signal.status,
        plan_record_versions=plan_record_signal.versions,
        transition_evidence_met=_transition_has_evidence(state),
    )


__all__ = ["KernelResult", "RuntimeContext", "api_in_scope", "evaluate_readonly", "execute"]
