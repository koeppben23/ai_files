"""Application-facing gateway bindings.

This file centralizes infrastructure wiring for use-cases.
"""

from governance.infrastructure.error_reason_router import canonicalize_reason_payload_failure
from governance.infrastructure.host_adapter import HostAdapter, HostCapabilities, OperatingMode
from governance.infrastructure.interaction_gate import evaluate_interaction_gate
from governance.infrastructure.mode_repo_rules import (
    RepoDocEvidence,
    classify_repo_doc,
    compute_repo_doc_hash,
    resolve_prompt_budget,
    summarize_classification,
)
from governance.infrastructure.pack_lock import resolve_pack_lock
from governance.infrastructure.reason_payload import (
    ReasonPayload,
    build_reason_payload,
    validate_reason_payload,
)
from governance.infrastructure.repo_root_resolver import RepoRootResolutionResult, resolve_repo_root
from governance.infrastructure.runtime_activation import (
    EngineDeviation,
    EngineRuntimeDecision,
    LiveEnablePolicy,
    evaluate_runtime_activation,
    golden_parity_fields,
)
from governance.infrastructure.selfcheck import run_engine_selfcheck
from governance.infrastructure.surface_policy import (
    capability_satisfies_requirement,
    mode_satisfies_requirement,
    resolve_surface_policy,
)
from governance.infrastructure.write_policy import WriteTargetPolicyResult, evaluate_target_path
