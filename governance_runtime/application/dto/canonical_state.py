"""Canonical session state types - snake_case only.

This module defines the canonical field names for session state.
All kernel code should use these types, not raw dict access.

Legacy field names are mapped via field_aliases.py and resolved
by state_normalizer.py at the boundary.
"""

from __future__ import annotations

from typing import TypedDict


class CanonicalGates(TypedDict, total=False):
    """Gate states as status flags.

    Keys use underscores (Python idiom). Persisted format uses
    hyphens/dots - see GATE_KEY_ALIASES for mapping.
    """

    P5_Architecture: str
    P5_3_TestQuality: str
    P5_4_BusinessRules: str
    P5_5_TechnicalDebt: str
    P5_6_RollbackSafety: str
    P6_ImplementationQA: str


class CanonicalImplementationReview(TypedDict, total=False):
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


class CanonicalReviewPackage(TypedDict, total=False):
    """Review package presentation data."""

    review_object: str
    ticket: str
    approved_plan_summary: str
    plan_body: str
    implementation_scope: str
    constraints: str
    decision_semantics: str
    presented: bool
    plan_body_present: bool
    evidence_summary: str
    loop_status: str
    last_state_change_at: str
    presentation_receipt: dict[str, object]


class CanonicalImplementationPackage(TypedDict, total=False):
    """Implementation package presentation data."""

    review_object: str
    plan_reference: str
    changed_files: list[str]
    findings_fixed: list[str]
    findings_open: list[str]
    checks: list[str]
    stability: str
    presented: bool
    last_state_change_at: str
    presentation_receipt: dict[str, object]


class CanonicalKernel(TypedDict, total=False):
    """Kernel metadata."""

    phase_api_path: str
    phase_api_sha256: str
    phase_api_loaded_at: str
    last_phase_event_id: str


class CanonicalLoadedRulebooks(TypedDict, total=False):
    """Loaded rulebooks references."""

    core: str
    profile: str


class CanonicalP54BusinessRules(TypedDict, total=False):
    """P5.4 Business Rules evaluation data."""

    evaluated_status: str
    invalid_rules: int
    dropped_candidates: int
    code_candidate_count: int
    code_surface_count: int
    quality_reason_codes: list[str]
    has_code_extraction: bool
    code_coverage_sufficient: bool
    missing_code_surfaces: list[str]
    reason_code: str


class CanonicalSessionState(TypedDict, total=False):
    """Canonical session state - snake_case only, no aliases.

    This is the SINGLE SOURCE OF TRUTH for field names in kernel code.
    All access should go through StateNormalizer to resolve legacy names.
    """

    # Core workflow
    phase: str
    next_action: str
    active_gate: str
    next_gate_condition: str
    workflow_complete: bool
    gates_blocked: list[str]

    # Mode
    mode: str
    effective_operating_mode: str
    resolved_operating_mode: str

    # Ticket
    ticket: str
    task: str

    # Gates
    gates: CanonicalGates

    # Phase 5
    phase5_completed: bool
    phase5_state: str
    phase5_completion_status: str
    phase5_plan_record_digest: str

    # Plan record
    plan_record_status: str
    plan_record_versions: int

    # Phase 6 review
    implementation_review: CanonicalImplementationReview
    phase6_review_iterations: int
    phase6_max_review_iterations: int
    phase6_min_self_review_iterations: int
    phase6_revision_delta: str
    phase6_state: str
    implementation_reason_codes: list[str]

    # Implementation
    implementation_changed_files: list[str]
    implementation_domain_changed_files: list[str]
    implementation_execution_summary: str
    implementation_executor_invoked: bool

    # P5.4 Business Rules
    p54: CanonicalP54BusinessRules

    # Presentation packages
    review_package: CanonicalReviewPackage
    implementation_package: CanonicalImplementationPackage
    implementation_review_summary: str

    # Kernel
    kernel: CanonicalKernel
    log_paths: dict[str, str]

    # Rulebooks
    loaded_rulebooks: CanonicalLoadedRulebooks
    addons_evidence: dict[str, object]
    active_profile: str

    # Session metadata
    session_run_id: str
    session_state_revision: str
    session_materialized_at: str
    session_materialization_event_id: str
    repo_fingerprint: str
    phase_transition_evidence: bool | str


class CanonicalStateDocument(TypedDict, total=False):
    """Top-level canonical state document."""

    session_state: CanonicalSessionState
    schema: str
    status: str
    error: str


class ConflictDetail(TypedDict):
    """Details of a single field conflict."""

    field: str
    flat_value: object
    nested_value: object


class NormalizationResult(TypedDict):
    """Result of state normalization with conflict tracking.

    Attributes:
        canonical: The normalized canonical state.
        conflicts: List of conflicting fields detected during normalization.
        warnings: List of non-critical warnings.
    """

    canonical: CanonicalSessionState
    conflicts: list[ConflictDetail]
    warnings: list[str]
