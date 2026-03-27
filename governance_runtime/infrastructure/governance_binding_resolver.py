from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from governance_runtime.infrastructure.governance_config_loader import get_pipeline_mode

AI_GOVERNANCE_EXECUTION_BINDING = "AI_GOVERNANCE_EXECUTION_BINDING"
AI_GOVERNANCE_REVIEW_BINDING = "AI_GOVERNANCE_REVIEW_BINDING"


class GovernanceBindingResolutionError(RuntimeError):
    """Raised when governance binding resolution fails for active mode."""


@dataclass(frozen=True)
class BindingResolution:
    role: str
    pipeline_mode: bool
    binding_value: str
    source: str


def _env_value(
    key: str,
    *,
    env_reader: Callable[[str], str | None],
) -> str:
    return str(env_reader(key) or "").strip()


def _require_pipeline_bindings(*, env_reader: Callable[[str], str | None]) -> tuple[str, str]:
    execution = _env_value(AI_GOVERNANCE_EXECUTION_BINDING, env_reader=env_reader)
    review = _env_value(AI_GOVERNANCE_REVIEW_BINDING, env_reader=env_reader)
    if not execution:
        raise GovernanceBindingResolutionError(
            f"missing required pipeline binding: {AI_GOVERNANCE_EXECUTION_BINDING}"
        )
    if not review:
        raise GovernanceBindingResolutionError(
            f"missing required pipeline binding: {AI_GOVERNANCE_REVIEW_BINDING}"
        )
    return execution, review


def resolve_governance_binding(
    *,
    role: str,
    workspace_root: Path | None,
    env_reader: Callable[[str], str | None],
    has_active_chat_binding: bool,
) -> BindingResolution:
    """Resolve role-scoped governance binding by mode.

    Direct mode (`pipeline_mode=false`):
    - Uses active OpenCode chat binding
    - Ignores environment bindings

    Pipeline mode (`pipeline_mode=true`):
    - Requires both env bindings
    - Uses role-specific env binding
    - Does not fall back to active chat binding
    """
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in {"execution", "review"}:
        raise GovernanceBindingResolutionError(f"invalid governance binding role: {role}")

    is_pipeline = get_pipeline_mode(workspace_root)
    if not is_pipeline:
        if not has_active_chat_binding:
            raise GovernanceBindingResolutionError(
                "active OpenCode chat binding is required in direct mode"
            )
        return BindingResolution(
            role=normalized_role,
            pipeline_mode=False,
            binding_value="active_chat_binding",
            source="active_chat_binding",
        )

    execution, review = _require_pipeline_bindings(env_reader=env_reader)
    value = execution if normalized_role == "execution" else review
    source = (
        f"env:{AI_GOVERNANCE_EXECUTION_BINDING}"
        if normalized_role == "execution"
        else f"env:{AI_GOVERNANCE_REVIEW_BINDING}"
    )
    return BindingResolution(
        role=normalized_role,
        pipeline_mode=True,
        binding_value=value,
        source=source,
    )
