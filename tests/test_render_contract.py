from __future__ import annotations

from typing import Any, cast

import pytest

from governance.render.delta_renderer import build_delta_state
from governance.render.intent_router import route_intent
from governance.render.render_contract import build_two_layer_output
from governance.render.token_guard import apply_token_budget


@pytest.mark.governance
def test_intent_router_routes_fast_paths_deterministically():
    """Known intent phrases should map to stable fast-path intent keys."""

    assert route_intent("Where am I right now?") == "where_am_i"
    assert route_intent("What blocks me?") == "what_blocks_me"
    assert route_intent("what now") == "what_now"
    assert route_intent("") == "what_now"


@pytest.mark.governance
def test_delta_renderer_marks_state_unchanged_when_hashes_match():
    """Matching non-empty hashes should return no-delta output."""

    delta = build_delta_state(previous_state_hash="abc", current_state_hash="abc")
    assert delta == {"state_unchanged": True, "delta_mode": "no-delta"}


@pytest.mark.governance
def test_token_guard_truncates_in_deterministic_order():
    """Budget guard should drop verbose sections in prescribed order."""

    details = {
        "verbose_details": "x" * 500,
        "evidence_expansions": "y" * 400,
        "advisory_context": "z" * 300,
        "required_fact": "keep-me",
    }
    trimmed = apply_token_budget(mode="compact", details=details)
    assert "required_fact" in trimmed
    assert "verbose_details" not in trimmed
    assert "evidence_expansions" not in trimmed


@pytest.mark.governance
def test_render_contract_preserves_header_and_applies_budget_guard():
    """Two-layer contract must keep header fields while trimming details."""

    output = build_two_layer_output(
        status="OK",
        phase_gate="P4-Entry",
        primary_action="Run deterministic checks.",
        mode="compact",
        details={
            "verbose_details": "v" * 500,
            "required_fact": "kept",
        },
        previous_state_hash="a",
        current_state_hash="b",
    )
    output = cast(dict[str, Any], output)
    assert output["header"]["status"] == "OK"
    assert output["header"]["phase_gate"] == "P4-Entry"
    assert output["header"]["primary_next_action"] == "Run deterministic checks."
    assert output["delta"]["delta_mode"] == "delta-only"
    assert output["details"] == {"required_fact": "kept"}


@pytest.mark.governance
def test_render_contract_builds_fixed_operator_view_and_reason_action_card():
    """Operator view and reason card should use fixed keys and stable ordering."""

    output = build_two_layer_output(
        status="BLOCKED",
        phase_gate="P1.1-bootstrap.preflight",
        primary_action="Make python available.",
        mode="compact",
        details={"required_fact": "kept"},
        previous_state_hash="x",
        current_state_hash="x",
        phase="1.1",
        active_gate="bootstrap.preflight",
        phase_progress_bar="[#-----] 1/6",
        reason_code="BLOCKED-PREFLIGHT-REQUIRED-NOW-MISSING",
        next_command="python3 --version",
        missing_items=["python"],
    )
    output = cast(dict[str, Any], output)

    assert list(output["operator_view"].keys()) == [
        "PHASE_GATE",
        "STATUS",
        "PRIMARY_REASON",
        "NEXT_COMMAND",
    ]
    assert output["operator_view"]["PHASE_GATE"] == "1.1 | bootstrap.preflight | [#-----] 1/6"
    assert output["operator_view"]["STATUS"] == "BLOCKED"
    assert output["operator_view"]["PRIMARY_REASON"] == "BLOCKED-PREFLIGHT-REQUIRED-NOW-MISSING"
    assert output["reason_to_action"]["what_missing"] == ("python",)


@pytest.mark.governance
def test_render_contract_builds_diff_first_diagnostics_and_last_three_timeline_rows():
    """Diff diagnostics and timeline should be deterministic and size-bounded."""

    output = build_two_layer_output(
        status="NOT_VERIFIED",
        phase_gate="P5.3-TestQuality",
        primary_action="Provide missing evidence.",
        mode="standard",
        details={"required_fact": "kept"},
        previous_state_hash="abc",
        current_state_hash="def",
        previous_blockers=["BLOCKED-OLD"],
        current_blockers=["BLOCKED-NEW"],
        previous_stale_claims=["claim/tests-green"],
        current_stale_claims=["claim/static-clean"],
        transition_events=[
            {"phase": "1.1", "active_gate": "bootstrap", "status": "OK", "reason_code": "none", "snapshot_hash": "h1"},
            {"phase": "2.1", "active_gate": "decision", "status": "OK", "reason_code": "none", "snapshot_hash": "h2"},
            {"phase": "3A", "active_gate": "api.inventory", "status": "WARN", "reason_code": "WARN-MODE-DOWNGRADED", "snapshot_hash": "h3"},
            {"phase": "5.3", "active_gate": "test.quality", "status": "NOT_VERIFIED", "reason_code": "NOT_VERIFIED-MISSING-EVIDENCE", "snapshot_hash": "h4"},
        ],
    )
    output = cast(dict[str, Any], output)

    assert output["diagnostics_delta"] == {
        "new_blockers": ("BLOCKED-NEW",),
        "resolved_blockers": ("BLOCKED-OLD",),
        "new_stale_claims": ("claim/static-clean",),
        "resolved_stale_claims": ("claim/tests-green",),
    }
    timeline = output["timeline"]
    assert len(timeline) == 3
    assert timeline[0]["phase_gate"] == "2.1|decision"
    assert timeline[2]["snapshot_hash"] == "h4"


@pytest.mark.governance
def test_render_contract_builds_sorted_evidence_panel_with_freshness():
    """Evidence panel should be claim/evidence sorted with stable freshness values."""

    output = build_two_layer_output(
        status="OK",
        phase_gate="P5.3-TestQuality",
        primary_action="Continue.",
        details={"required_fact": "kept"},
        evidence_items=[
            {
                "claim_id": "claim/tests-green",
                "evidence_id": "ev-2",
                "observed_at": "2026-02-11T12:01:00Z",
                "is_stale": True,
            },
            {
                "claim_id": "claim/tests-green",
                "evidence_id": "ev-1",
                "observed_at": "2026-02-11T12:00:00Z",
                "freshness": "fresh",
            },
            {
                "claim_id": "claim/static-clean",
                "evidence_id": "ev-3",
                "observed_at": "2026-02-11T12:02:00Z",
            },
        ],
    )
    output = cast(dict[str, Any], output)
    panel = output["evidence_panel"]
    assert panel == (
        {
            "claim_id": "claim/static-clean",
            "evidence_id": "ev-3",
            "freshness": "fresh",
            "observed_at": "2026-02-11T12:02:00Z",
        },
        {
            "claim_id": "claim/tests-green",
            "evidence_id": "ev-1",
            "freshness": "fresh",
            "observed_at": "2026-02-11T12:00:00Z",
        },
        {
            "claim_id": "claim/tests-green",
            "evidence_id": "ev-2",
            "freshness": "stale",
            "observed_at": "2026-02-11T12:01:00Z",
        },
    )
