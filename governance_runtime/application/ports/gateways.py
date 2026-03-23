"""Application ports for orchestrator use-case.

This module defines pure contracts and dispatch wrappers. Concrete bindings are
installed by infrastructure wiring at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

OperatingMode = Literal["user", "system", "pipeline", "agents_strict"]
LiveEnablePolicy = Literal["ci_strict", "auto_degrade"]


class HostCapabilities(Protocol):
    cwd_trust: str
    fs_read_commands_home: bool
    fs_write_config_root: bool
    fs_write_commands_home: bool
    fs_write_workspaces_home: bool
    fs_write_repo_root: bool
    exec_allowed: bool
    git_available: bool

    def stable_hash(self) -> str: ...


class HostAdapter(Protocol):
    def capabilities(self) -> HostCapabilities: ...
    def environment(self) -> Mapping[str, str]: ...
    def cwd(self): ...
    def now_utc(self) -> datetime: ...
    def exec_argv(self, argv: Sequence[str], *, cwd: Path | None = None, timeout_seconds: int = 10) -> Any: ...
    def default_operating_mode(self) -> OperatingMode: ...


@dataclass(frozen=True)
class RepoDocEvidence:
    doc_path: str
    doc_hash: str
    classification_summary: dict[str, int]


@dataclass(frozen=True)
class GatewayRegistry:
    resolve_repo_root: Callable[..., Any]
    evaluate_target_path: Callable[..., Any]
    resolve_pack_lock: Callable[..., Any]
    classify_repo_doc: Callable[..., Any]
    compute_repo_doc_hash: Callable[..., Any]
    resolve_prompt_budget: Callable[..., Any]
    summarize_classification: Callable[..., Any]
    evaluate_interaction_gate: Callable[..., Any]
    evaluate_runtime_activation: Callable[..., Any]
    golden_parity_fields: Callable[..., Any]
    run_engine_selfcheck: Callable[..., Any]
    resolve_surface_policy: Callable[..., Any]
    mode_satisfies_requirement: Callable[..., Any]
    capability_satisfies_requirement: Callable[..., Any]
    build_reason_payload: Callable[..., Any]
    validate_reason_payload: Callable[..., Any]
    canonicalize_reason_payload_failure: Callable[..., Any]
    ensure_workspace_ready: Callable[..., Any]
    load_persist_confirmation_evidence: Callable[..., Any]


_REGISTRY: GatewayRegistry | None = None
_SEALED: bool = False


def set_gateway_registry(registry: GatewayRegistry) -> None:
    """Install the gateway registry.  Idempotent: once sealed, subsequent
    calls are silently ignored so that ``configure_gateway_registry()`` can
    be invoked from multiple entry-points without raising."""
    global _REGISTRY, _SEALED
    if _SEALED:
        return  # already configured — idempotent no-op
    _REGISTRY = registry
    _SEALED = True


def _unseal_gateway_registry_for_testing() -> None:
    """Test-only helper — resets seal so tests can re-configure gateways."""
    global _REGISTRY, _SEALED
    _SEALED = False
    _REGISTRY = None


def _gateway() -> GatewayRegistry:
    if _REGISTRY is None:
        raise RuntimeError("gateway registry not configured")
    return _REGISTRY


def resolve_repo_root(*args: Any, **kwargs: Any) -> Any:
    return _gateway().resolve_repo_root(*args, **kwargs)


def evaluate_target_path(*args: Any, **kwargs: Any) -> Any:
    return _gateway().evaluate_target_path(*args, **kwargs)


def resolve_pack_lock(*args: Any, **kwargs: Any) -> Any:
    return _gateway().resolve_pack_lock(*args, **kwargs)


def classify_repo_doc(*args: Any, **kwargs: Any) -> Any:
    return _gateway().classify_repo_doc(*args, **kwargs)


def compute_repo_doc_hash(*args: Any, **kwargs: Any) -> Any:
    return _gateway().compute_repo_doc_hash(*args, **kwargs)


def resolve_prompt_budget(*args: Any, **kwargs: Any) -> Any:
    return _gateway().resolve_prompt_budget(*args, **kwargs)


def summarize_classification(*args: Any, **kwargs: Any) -> Any:
    return _gateway().summarize_classification(*args, **kwargs)


def evaluate_interaction_gate(*args: Any, **kwargs: Any) -> Any:
    return _gateway().evaluate_interaction_gate(*args, **kwargs)


def evaluate_runtime_activation(*args: Any, **kwargs: Any) -> Any:
    return _gateway().evaluate_runtime_activation(*args, **kwargs)


def golden_parity_fields(*args: Any, **kwargs: Any) -> Any:
    return _gateway().golden_parity_fields(*args, **kwargs)


def run_engine_selfcheck(*args: Any, **kwargs: Any) -> Any:
    return _gateway().run_engine_selfcheck(*args, **kwargs)


def resolve_surface_policy(*args: Any, **kwargs: Any) -> Any:
    return _gateway().resolve_surface_policy(*args, **kwargs)


def mode_satisfies_requirement(*args: Any, **kwargs: Any) -> Any:
    return _gateway().mode_satisfies_requirement(*args, **kwargs)


def capability_satisfies_requirement(*args: Any, **kwargs: Any) -> Any:
    return _gateway().capability_satisfies_requirement(*args, **kwargs)


def build_reason_payload(*args: Any, **kwargs: Any) -> Any:
    return _gateway().build_reason_payload(*args, **kwargs)


def validate_reason_payload(*args: Any, **kwargs: Any) -> Any:
    return _gateway().validate_reason_payload(*args, **kwargs)


def canonicalize_reason_payload_failure(*args: Any, **kwargs: Any) -> Any:
    return _gateway().canonicalize_reason_payload_failure(*args, **kwargs)


def ensure_workspace_ready(*args: Any, **kwargs: Any) -> Any:
    return _gateway().ensure_workspace_ready(*args, **kwargs)


def load_persist_confirmation_evidence(*args: Any, **kwargs: Any) -> Any:
    return _gateway().load_persist_confirmation_evidence(*args, **kwargs)
