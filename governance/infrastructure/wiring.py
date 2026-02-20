"""Composition root wiring for application gateway ports."""

from __future__ import annotations

import os

from governance.application.ports.gateways import GatewayRegistry, set_gateway_registry
from governance.infrastructure.error_reason_router import canonicalize_reason_payload_failure
from governance.infrastructure.phase4_config_resolver import configure_phase4_self_review_resolver
from governance.infrastructure.phase5_config_resolver import configure_phase5_review_resolver
from governance.infrastructure.policy_bundle_loader import ensure_policy_bundle_loaded
from governance.infrastructure.interaction_gate import evaluate_interaction_gate
from governance.infrastructure.mode_repo_rules import (
    classify_repo_doc,
    compute_repo_doc_hash,
    resolve_prompt_budget,
    summarize_classification,
)
from governance.infrastructure.pack_lock import resolve_pack_lock
from governance.infrastructure.reason_payload import build_reason_payload, validate_reason_payload
from governance.infrastructure.persist_confirmation_store import load_persist_confirmation_evidence
from governance.infrastructure.repo_root_resolver import resolve_repo_root
from governance.infrastructure.runtime_activation import evaluate_runtime_activation, golden_parity_fields
from governance.infrastructure.selfcheck import run_engine_selfcheck
from governance.infrastructure.workspace_ready_gate import ensure_workspace_ready
from governance.infrastructure.surface_policy import (
    capability_satisfies_requirement,
    mode_satisfies_requirement,
    resolve_surface_policy,
)
from governance.infrastructure.write_policy import evaluate_target_path


def configure_gateway_registry() -> None:
    effective_mode = str(os.environ.get("OPENCODE_OPERATING_MODE", "user")).strip() or "user"

    # Runtime startup wiring for policy-bound config resolvers.
    configure_phase4_self_review_resolver(mode=effective_mode)
    configure_phase5_review_resolver(mode=effective_mode)
    ensure_policy_bundle_loaded(mode=effective_mode)

    set_gateway_registry(
        GatewayRegistry(
            resolve_repo_root=resolve_repo_root,
            evaluate_target_path=evaluate_target_path,
            resolve_pack_lock=resolve_pack_lock,
            classify_repo_doc=classify_repo_doc,
            compute_repo_doc_hash=compute_repo_doc_hash,
            resolve_prompt_budget=resolve_prompt_budget,
            summarize_classification=summarize_classification,
            evaluate_interaction_gate=evaluate_interaction_gate,
            evaluate_runtime_activation=evaluate_runtime_activation,
            golden_parity_fields=golden_parity_fields,
            run_engine_selfcheck=run_engine_selfcheck,
            resolve_surface_policy=resolve_surface_policy,
            mode_satisfies_requirement=mode_satisfies_requirement,
            capability_satisfies_requirement=capability_satisfies_requirement,
            build_reason_payload=build_reason_payload,
            validate_reason_payload=validate_reason_payload,
            canonicalize_reason_payload_failure=canonicalize_reason_payload_failure,
            ensure_workspace_ready=ensure_workspace_ready,
            load_persist_confirmation_evidence=load_persist_confirmation_evidence,
        )
    )
