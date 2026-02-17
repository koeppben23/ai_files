from __future__ import annotations

from governance.engine.interaction_gate import evaluate_interaction_gate


def test_interaction_gate_blocks_pipeline_prompt_attempts():
    decision = evaluate_interaction_gate(
        effective_mode="pipeline",
        interactive_required=False,
        prompt_used_total=1,
        prompt_used_repo_docs=0,
        requested_action="ApproveWidening",
    )
    assert decision.blocked is True
    assert decision.event is not None
    assert decision.event["event"] == "PROMPT_REQUESTED"


def test_interaction_gate_allows_non_pipeline_prompt_usage():
    decision = evaluate_interaction_gate(
        effective_mode="user",
        interactive_required=True,
        prompt_used_total=1,
        prompt_used_repo_docs=1,
        requested_action="ask",
    )
    assert decision.blocked is False
    assert decision.event is None
