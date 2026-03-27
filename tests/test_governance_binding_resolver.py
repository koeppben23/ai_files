from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_runtime.infrastructure.governance_binding_resolver import (
    GovernanceBindingResolutionError,
    resolve_governance_binding,
)


def _write_governance_config(workspace_dir: Path, *, pipeline_mode: bool) -> None:
    payload = {
        "pipeline_mode": pipeline_mode,
        "review": {
            "phase5_max_review_iterations": 3,
            "phase6_max_review_iterations": 3,
        },
    }
    (workspace_dir / "governance-config.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def test_direct_mode_ignores_env_bindings(tmp_path: Path) -> None:
    _write_governance_config(tmp_path, pipeline_mode=False)
    env = {
        "AI_GOVERNANCE_EXECUTION_BINDING": "execution-cmd",
        "AI_GOVERNANCE_REVIEW_BINDING": "review-cmd",
    }

    resolution = resolve_governance_binding(
        role="execution",
        workspace_root=tmp_path,
        env_reader=lambda key: env.get(key),
        has_active_chat_binding=True,
    )

    assert resolution.pipeline_mode is False
    assert resolution.binding_value == "active_chat_binding"
    assert resolution.source == "active_chat_binding"


def test_direct_mode_requires_active_chat_even_when_env_present(tmp_path: Path) -> None:
    _write_governance_config(tmp_path, pipeline_mode=False)
    env = {
        "AI_GOVERNANCE_EXECUTION_BINDING": "execution-cmd",
        "AI_GOVERNANCE_REVIEW_BINDING": "review-cmd",
    }

    with pytest.raises(GovernanceBindingResolutionError, match="active OpenCode chat binding"):
        resolve_governance_binding(
            role="execution",
            workspace_root=tmp_path,
            env_reader=lambda key: env.get(key),
            has_active_chat_binding=False,
        )


def test_pipeline_mode_fails_closed_without_env_even_with_active_chat(tmp_path: Path) -> None:
    _write_governance_config(tmp_path, pipeline_mode=True)

    with pytest.raises(GovernanceBindingResolutionError, match="AI_GOVERNANCE_EXECUTION_BINDING"):
        resolve_governance_binding(
            role="execution",
            workspace_root=tmp_path,
            env_reader=lambda _key: None,
            has_active_chat_binding=True,
        )


def test_pipeline_mode_uses_role_specific_bindings(tmp_path: Path) -> None:
    _write_governance_config(tmp_path, pipeline_mode=True)
    env = {
        "AI_GOVERNANCE_EXECUTION_BINDING": "execution-cmd",
        "AI_GOVERNANCE_REVIEW_BINDING": "review-cmd",
    }

    execution = resolve_governance_binding(
        role="execution",
        workspace_root=tmp_path,
        env_reader=lambda key: env.get(key),
        has_active_chat_binding=False,
    )
    review = resolve_governance_binding(
        role="review",
        workspace_root=tmp_path,
        env_reader=lambda key: env.get(key),
        has_active_chat_binding=False,
    )

    assert execution.pipeline_mode is True
    assert execution.binding_value == "execution-cmd"
    assert execution.source == "env:AI_GOVERNANCE_EXECUTION_BINDING"
    assert review.pipeline_mode is True
    assert review.binding_value == "review-cmd"
    assert review.source == "env:AI_GOVERNANCE_REVIEW_BINDING"
