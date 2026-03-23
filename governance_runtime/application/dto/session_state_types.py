"""TypedDict definitions for governance session state.

These types provide structural typing for the session state document,
enabling static analysis and IDE autocompletion when working with
session state data.

All TypedDicts use total=False by default since session state fields
are often optional or conditionally present.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ImplementationReviewBlock(TypedDict, total=False):
    """Implementation review tracking block."""

    iteration: int
    max_iterations: int
    min_self_review_iterations: int
    implementation_review_complete: bool
    prev_impl_digest: str
    curr_impl_digest: str
    revision_delta: str
    llm_review_valid: bool
    llm_review_verdict: str
    llm_review_findings: list[str]
    llm_review_executor_available: bool


class GatesBlock(TypedDict, total=False):
    """P5 gate states."""

    P5_Architecture: str
    P5_3_TestQuality: str
    P5_4_BusinessRules: str
    P5_5_TechnicalDebt: str
    P5_6_RollbackSafety: str


class ReviewPackageBlock(TypedDict, total=False):
    """Review package presentation data."""

    review_package_review_object: str
    review_package_ticket: str
    review_package_approved_plan_summary: str
    review_package_plan_body: str
    review_package_implementation_scope: str
    review_package_constraints: str
    review_package_decision_semantics: str
    review_package_presented: bool
    review_package_plan_body_present: bool
    review_package_evidence_summary: str
    review_package_last_state_change_at: str
    review_package_presentation_receipt: dict[str, Any]


class ImplementationPackageBlock(TypedDict, total=False):
    """Implementation package presentation data."""

    implementation_package_review_object: str
    implementation_package_plan_reference: str
    implementation_package_changed_files: list[str]
    implementation_package_findings_fixed: list[str]
    implementation_package_findings_open: list[str]
    implementation_package_checks: list[str]
    implementation_package_stability: str
    implementation_package_presented: bool
    implementation_package_last_state_change_at: str
    implementation_package_presentation_receipt: dict[str, Any]


class KernelBlock(TypedDict, total=False):
    """Kernel metadata."""

    PhaseApiPath: str
    PhaseApiSha256: str
    PhaseApiLoadedAt: str
    LastPhaseEventId: str


class LoadedRulebooksBlock(TypedDict, total=False):
    """Loaded rulebooks references."""

    core: str
    profile: str


class SessionState(TypedDict, total=False):
    """Core session state fields.

    This is the nested SESSION_STATE dict within the state document.
    Fields use both PascalCase and snake_case for compatibility.
    """

    # Phase tracking
    Phase: str
    phase: str
    Next: str
    next: str
    active_gate: str
    next_gate_condition: str
    status: str

    # Mode
    Mode: str
    mode: str
    effective_operating_mode: str
    resolved_operating_mode: str

    # Ticket
    Ticket: str
    ticket: str
    Task: str
    task: str

    # Review tracking
    ImplementationReview: ImplementationReviewBlock
    phase6_review_iterations: int
    phase6_max_review_iterations: int
    phase6_min_self_review_iterations: int
    phase6_revision_delta: str
    phase6_state: str
    implementation_review_complete: bool
    implementation_reason_codes: list[str]

    # Phase 5
    phase5_completed: bool
    phase5_state: str
    Phase5State: str
    phase5_completion_status: str
    Gates: GatesBlock

    # Workflow
    workflow_complete: bool
    WorkflowComplete: bool
    gates_blocked: list[str]

    # Plan record
    plan_record_status: str
    PlanRecordStatus: str
    plan_record_versions: int
    PlanRecordVersions: int
    phase5_plan_record_digest: str

    # Implementation
    implementation_changed_files: list[str]
    implementation_domain_changed_files: list[str]
    implementation_execution_summary: str
    implementation_executor_invoked: bool

    # P5.4 Business Rules
    p54_evaluated_status: str
    p54_invalid_rules: int
    p54_dropped_candidates: int
    p54_code_candidate_count: int
    p54_code_surface_count: int
    p54_quality_reason_codes: list[str]
    p54_has_code_extraction: bool
    p54_code_coverage_sufficient: bool
    p54_missing_code_surfaces: list[str]
    p54_reason_code: str

    # Presentation packages
    review_package_review_object: str
    review_package_ticket: str
    review_package_approved_plan_summary: str
    review_package_plan_body: str
    review_package_implementation_scope: str
    review_package_constraints: str
    review_package_decision_semantics: str
    review_package_presented: bool
    review_package_plan_body_present: bool
    review_package_evidence_summary: str
    review_package_last_state_change_at: str
    review_package_presentation_receipt: dict[str, Any]
    implementation_package_review_object: str
    implementation_package_plan_reference: str
    implementation_package_changed_files: list[str]
    implementation_package_findings_fixed: list[str]
    implementation_package_findings_open: list[str]
    implementation_package_checks: list[str]
    implementation_package_stability: str
    implementation_package_presented: bool
    implementation_package_last_state_change_at: str
    implementation_package_presentation_receipt: dict[str, Any]
    implementation_review_summary: str

    # Kernel
    Kernel: KernelBlock
    log_paths: dict[str, str]

    # Rulebooks
    LoadedRulebooks: LoadedRulebooksBlock
    AddonsEvidence: dict[str, Any]
    ActiveProfile: str

    # Normalization markers
    _p6_state_normalization: dict[str, Any]
    session_run_id: str
    session_state_revision: str
    session_materialized_at: str
    session_materialization_event_id: str
    RepoFingerprint: str
    repo_fingerprint: str
    phase_transition_evidence: bool | str


class StateDocument(TypedDict, total=False):
    """Top-level state document structure."""

    SESSION_STATE: SessionState
    schema: str
    status: str
    error: str


class Snapshot(TypedDict, total=False):
    """Render source payload for snapshot formatting.

    This is the data structure returned by read_session_snapshot
    and consumed by format_snapshot/format_guided_snapshot.
    """

    schema: str
    status: str
    error: str
    phase: str
    active_gate: str
    next_gate_condition: str
    mode: str
    output_mode: str
    ticket: str
    task: str
    ticket_intake_ready: str
    rework_clarification_input: str
    implementation_rework_clarification_input: str
    plan_record_versions: int
    implementation_review_complete: bool
    phase6_review_iterations: int
    phase6_max_review_iterations: int
    phase6_min_review_iterations: int
    phase6_revision_delta: str
    phase6_decision_availability: str
    gates_blocked: list[str]
    # Review package fields
    review_package_review_object: str
    review_package_ticket: str
    review_package_approved_plan_summary: str
    review_package_plan_body: str
    review_package_evidence_summary: str
    # Implementation package fields
    implementation_package_review_object: str
    implementation_package_plan_reference: str
    implementation_package_changed_files: list[str]
    implementation_package_findings_fixed: list[str]
    implementation_package_findings_open: list[str]
    implementation_package_checks: list[str]
    implementation_package_stability: str
    # P5.4 fields
    p54_evaluated_status: str
    p54_invalid_rules: int
    p54_dropped_candidates: int
    p54_code_candidate_count: int
    p54_code_surface_count: int
    p54_quality_reason_codes: list[str]
    p54_has_code_extraction: bool
    p54_code_coverage_sufficient: bool
    p54_missing_code_surfaces: list[str]
    p54_reason_code: str
    # Implementation fields
    implementation_changed_files: list[str]
    implementation_domain_changed_files: list[str]
    implementation_execution_summary: str
    implementation_reason_codes: list[str]
    implementation_executor_invoked: bool
