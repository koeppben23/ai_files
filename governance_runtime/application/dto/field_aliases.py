"""Legacy field name mappings for session state.

This module contains ONLY mapping tables - no logic.
Used by state_normalizer.py to resolve legacy field names to canonical ones.

ARCHITECTURE RULE: Alias resolution must only happen in state_normalizer.py
and explicitly allowed compatibility modules (legacy_compat.py).
Kernel code MUST use canonical field names.
"""

from __future__ import annotations


# Top-level field aliases: canonical -> list of legacy names
FIELD_ALIASES: dict[str, list[str]] = {
    # Core workflow
    "phase": ["Phase"],
    "next_action": ["Next", "next"],
    "active_gate": [],
    "next_gate_condition": [],
    "status": [],
    "workflow_complete": ["WorkflowComplete"],
    "gates_blocked": [],
    # Mode
    "mode": ["Mode"],
    "effective_operating_mode": [],
    "resolved_operating_mode": [],
    # Ticket
    "ticket": ["Ticket"],
    "task": ["Task"],
    # Phase 5
    "phase5_completed": [],
    "phase5_state": ["Phase5State"],
    "phase5_completion_status": [],
    "phase5_plan_record_digest": [],
    # Plan record
    "plan_record_status": ["PlanRecordStatus"],
    "plan_record_versions": ["PlanRecordVersions"],
    # Phase 6 review
    "phase6_review_iterations": [],
    "phase6_max_review_iterations": [],
    "phase6_min_review_iterations": ["phase6_min_self_review_iterations", "phase6MinReviewIterations"],
    "phase6_revision_delta": [],
    "phase6_state": [],
    "implementation_reason_codes": [],
    "implementation_review_complete": ["ImplementationReviewComplete"],
    # Implementation
    "implementation_changed_files": [],
    "implementation_domain_changed_files": [],
    "implementation_execution_summary": [],
    "implementation_executor_invoked": [],
    "implementation_authorized": ["ImplementationAuthorized"],
    "implementation_blocked": ["ImplementationBlocked"],
    "rework_clarification_input": ["reworkClarificationInput", "ReworkClarificationInput"],
    # Kernel
    "kernel": ["Kernel"],
    "log_paths": [],
    # Rulebooks
    "loaded_rulebooks": ["LoadedRulebooks"],
    "addons_evidence": ["AddonsEvidence"],
    "active_profile": ["ActiveProfile"],
    # Session metadata
    "session_run_id": [],
    "session_state_revision": [],
    "session_materialized_at": [],
    "session_materialization_event_id": [],
    "repo_fingerprint": ["RepoFingerprint"],
    "phase_transition_evidence": [],
}

# Gate key aliases: persisted format -> canonical format
# Persisted: "P5.3-TestQuality" (hyphens/dots)
# Canonical: "P5_3_TestQuality" (underscores)
GATE_KEY_ALIASES: dict[str, str] = {
    "P5-Architecture": "P5_Architecture",
    "P5.3-TestQuality": "P5_3_TestQuality",
    "P5.4-BusinessRules": "P5_4_BusinessRules",
    "P5.5-TechnicalDebt": "P5_5_TechnicalDebt",
    "P5.6-RollbackSafety": "P5_6_RollbackSafety",
    "P6-ImplementationQA": "P6_ImplementationQA",
}

# Reverse lookup for persistence: canonical -> persisted
CANONICAL_GATE_KEYS: dict[str, str] = {v: k for k, v in GATE_KEY_ALIASES.items()}


# Nested field aliases (for blocks that are flattened in legacy state)
IMPLEMENTATION_REVIEW_ALIASES: dict[str, list[str]] = {
    "iteration": [],
    "max_iterations": [],
    "min_self_review_iterations": [],
    "implementation_review_complete": [],
    "prev_impl_digest": [],
    "curr_impl_digest": [],
    "revision_delta": [],
    "llm_review_valid": [],
    "llm_review_verdict": [],
    "llm_review_findings": [],
    "llm_review_executor_available": [],
}

P54_ALIASES: dict[str, list[str]] = {
    "evaluated_status": [],
    "invalid_rules": [],
    "dropped_candidates": [],
    "code_candidate_count": [],
    "code_surface_count": [],
    "quality_reason_codes": [],
    "has_code_extraction": [],
    "code_coverage_sufficient": [],
    "missing_code_surfaces": [],
    "reason_code": [],
}

REVIEW_PACKAGE_ALIASES: dict[str, list[str]] = {
    "review_object": ["review_package_review_object"],
    "ticket": ["review_package_ticket"],
    "approved_plan_summary": ["review_package_approved_plan_summary"],
    "plan_body": ["review_package_plan_body"],
    "implementation_scope": ["review_package_implementation_scope"],
    "constraints": ["review_package_constraints"],
    "decision_semantics": ["review_package_decision_semantics"],
    "presented": ["review_package_presented"],
    "plan_body_present": ["review_package_plan_body_present"],
    "evidence_summary": ["review_package_evidence_summary"],
    "last_state_change_at": ["review_package_last_state_change_at"],
    "presentation_receipt": ["review_package_presentation_receipt"],
}

IMPLEMENTATION_PACKAGE_ALIASES: dict[str, list[str]] = {
    "review_object": ["implementation_package_review_object"],
    "plan_reference": ["implementation_package_plan_reference"],
    "changed_files": ["implementation_package_changed_files"],
    "findings_fixed": ["implementation_package_findings_fixed"],
    "findings_open": ["implementation_package_findings_open"],
    "checks": ["implementation_package_checks"],
    "stability": ["implementation_package_stability"],
    "presented": ["implementation_package_presented"],
    "last_state_change_at": ["implementation_package_last_state_change_at"],
    "presentation_receipt": ["implementation_package_presentation_receipt"],
}

KERNEL_ALIASES: dict[str, list[str]] = {
    "phase_api_path": ["PhaseApiPath"],
    "phase_api_sha256": ["PhaseApiSha256"],
    "phase_api_loaded_at": ["PhaseApiLoadedAt"],
    "last_phase_event_id": ["LastPhaseEventId"],
}

LOADED_RULEBOOKS_ALIASES: dict[str, list[str]] = {
    "core": [],
    "profile": [],
}
