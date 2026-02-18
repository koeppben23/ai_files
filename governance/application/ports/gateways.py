"""Application ports for orchestrator use-case.

This module defines pure contracts and dispatch wrappers. Concrete bindings are
installed by infrastructure wiring at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal, Mapping, Protocol

OperatingMode = Literal["user", "system", "pipeline"]
LiveEnablePolicy = Literal["ci_strict", "always", "never"]


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


_REGISTRY: GatewayRegistry | None = None


def set_gateway_registry(registry: GatewayRegistry) -> None:
    global _REGISTRY
    _REGISTRY = registry


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
