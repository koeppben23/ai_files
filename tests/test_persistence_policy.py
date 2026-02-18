from __future__ import annotations

import pytest

from governance.application.policies.persistence_policy import (
    ARTIFACT_WORKSPACE_MEMORY,
    PersistencePolicyInput,
    can_write,
)


@pytest.mark.governance
def test_persistence_policy_allows_workspace_memory_when_phase5_yes_confirmation():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
            phase="5-ImplementationQA",
            mode="user",
            gate_approved=True,
            business_rules_executed=True,
            explicit_confirmation="Persist to workspace memory: YES",
        )
    )
    assert decision.allowed is True
    assert decision.reason_code == "none"


@pytest.mark.governance
def test_persistence_policy_blocks_workspace_memory_without_confirmation():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
            phase="5-ImplementationQA",
            mode="user",
            gate_approved=True,
            business_rules_executed=True,
            explicit_confirmation="",
        )
    )
    assert decision.allowed is False
    assert decision.reason_code == "PERSIST_CONFIRMATION_REQUIRED"


@pytest.mark.governance
def test_persistence_policy_blocks_workspace_memory_in_pipeline_without_confirmation():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
            phase="5-ImplementationQA",
            mode="pipeline",
            gate_approved=True,
            business_rules_executed=True,
            explicit_confirmation="",
        )
    )
    assert decision.allowed is False
    assert decision.reason_code == "PERSIST_DISALLOWED_IN_PIPELINE"
