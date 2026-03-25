from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from governance_runtime.kernel.phase_api_spec import load_phase_api
from governance_runtime.kernel.phase_kernel import _select_transition
from tests.util import get_phase_api_path


ROOT_PHASE_API = get_phase_api_path()


def _commands_home_with_repo_phase_api(tmp_path: Path) -> Path:
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(ROOT_PHASE_API.read_text(encoding="utf-8"), encoding="utf-8")
    return commands_home


def _load_raw_rows() -> list[dict[str, object]]:
    payload = yaml.safe_load(ROOT_PHASE_API.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload.get("phases")
    assert isinstance(rows, list)
    return [dict(row) for row in rows if isinstance(row, dict)]


def _golden_matrix_row(row: dict[str, object]) -> tuple[str, str, str, str, tuple[tuple[str, str, str], ...]]:
    transitions_raw = row.get("transitions")
    transitions: list[tuple[str, str, str]] = []
    if isinstance(transitions_raw, list):
        for item in transitions_raw:
            if isinstance(item, dict):
                transitions.append(
                    (
                        str(item.get("when", "")),
                        str(item.get("next", "")),
                        str(item.get("source", "")),
                    )
                )
    next_token = str(row.get("next", "") or "-")
    return (
        str(row.get("token", "")),
        str(row.get("phase", "")),
        str(row.get("route_strategy", "")),
        next_token,
        tuple(transitions),
    )


def test_golden_raw_matrix_matches_canonical_source() -> None:
    rows = [_golden_matrix_row(row) for row in _load_raw_rows()]
    assert rows == [
        ("0", "0-None", "next", "1.1", ()),
        ("1.1", "1.1-Bootstrap", "stay", "1", ()),
        ("1", "1-WorkspacePersistence", "stay", "1.2", ()),
        ("1.2", "1.2-ActivationIntent", "next", "1.3", (("default", "1.3", "phase-1.2-to-1.3-auto"),)),
        ("1.3", "1.3-RulebookLoad", "stay", "2", ()),
        ("2", "2-RepoDiscovery", "stay", "2.1", ()),
        (
            "2.1",
            "2.1-DecisionPack",
            "next",
            "-",
            (
                ("business_rules_execute", "1.5", "phase-1.5-routing-required"),
                ("default", "3A", "phase-2.1-to-3a"),
            ),
        ),
        ("1.5", "1.5-BusinessRules", "next", "3A", (("default", "3A", "phase-1.5-to-3a"),)),
        (
            "3A",
            "3A-API-Inventory",
            "next",
            "-",
            (("no_apis", "4", "phase-3a-not-applicable-to-phase4"), ("default", "3B-1", "phase-3a-to-3b1")),
        ),
        ("3B-1", "3B-1", "next", "3B-2", (("default", "3B-2", "phase-3b1-to-3b2"),)),
        ("3B-2", "3B-2", "next", "4", (("default", "4", "phase-3b2-to-4"),)),
        (
            "4",
            "4",
            "next",
            "5",
            (("ticket_present", "5", "phase-4-to-5-ticket-intake"), ("default", "4", "phase-4-awaiting-ticket-intake")),
        ),
        (
            "5",
            "5-ArchitectureReview",
            "stay",
            "5.3",
            (
                ("plan_record_missing", "5", "phase-5-plan-record-prep-required"),
                ("self_review_iterations_pending", "5", "phase-5-self-review-required"),
                ("self_review_iterations_met", "5.3", "phase-5-architecture-review-ready"),
                ("default", "5", "phase-5-plan-record-prep-default"),
            ),
        ),
        (
            "5.3",
            "5.3-TestQuality",
            "next",
            "6",
            (
                ("business_rules_gate_required", "5.4", "phase-5.3-to-5.4"),
                ("technical_debt_proposed", "5.5", "phase-5.3-to-5.5"),
                ("rollback_required", "5.6", "phase-5.3-to-5.6"),
                ("default", "6", "phase-5.3-to-6"),
            ),
        ),
        (
            "5.4",
            "5.4-BusinessRules",
            "next",
            "5.5",
            (
                ("technical_debt_proposed", "5.5", "phase-5.4-to-5.5"),
                ("rollback_required", "5.6", "phase-5.4-to-5.6"),
                ("default", "6", "phase-5.4-to-6"),
            ),
        ),
        (
            "5.5",
            "5.5-TechnicalDebt",
            "next",
            "5.6",
            (("rollback_required", "5.6", "phase-5.5-to-5.6"), ("default", "6", "phase-5.5-to-6")),
        ),
        ("5.6", "5.6-RollbackSafety", "next", "6", (("default", "6", "phase-5.6-to-6"),)),
        (
            "6",
            "6-PostFlight",
            "stay",
            "-",
            (
                ("implementation_accepted", "6", "phase-6-implementation-accepted"),
                ("implementation_blocked", "6", "phase-6-implementation-blocked"),
                (
                    "implementation_rework_clarification_pending",
                    "6",
                    "phase-6-implementation-rework-clarification",
                ),
                ("implementation_presentation_ready", "6", "phase-6-implementation-presentation-ready"),
                ("implementation_execution_in_progress", "6", "phase-6-implementation-execution"),
                ("implementation_started", "6", "phase-6-implementation-started"),
                ("workflow_approved", "6", "phase-6-workflow-complete"),
                ("review_changes_requested", "6", "phase-6-changes-requested-loop-reset"),
                ("rework_clarification_pending", "6", "phase-6-rework-clarification-required"),
                ("review_rejected", "4", "phase-6-rejected-to-phase4"),
                ("implementation_review_pending", "6", "phase-6-implementation-review-required"),
                ("implementation_review_complete", "6", "phase-6-ready-for-user-review"),
                ("default", "6", "phase-6-implementation-review-required"),
            ),
        ),
    ]


def test_structure_all_tokens_and_links_are_valid(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))
    tokens = set(spec.entries)
    assert spec.start_token in tokens
    assert len(tokens) == len(spec.entries)
    for entry in spec.entries.values():
        assert entry.route_strategy in {"stay", "next"}
        if entry.next_token is not None:
            assert entry.next_token in tokens
        for transition in entry.transitions:
            assert transition.next_token in tokens
            assert transition.when.strip()
            assert transition.source.strip()


def test_priority_specific_then_default_then_next(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))

    # specific > default for token 4
    token4 = spec.entries["4"]
    specific = _select_transition(token4, {"TicketRecordDigest": "sha256:abc"}, plan_record_versions=1)
    assert specific[0] == "5"
    assert specific[1] == "phase-4-to-5-ticket-intake"

    # default > next for token 4 (next=5, default->4)
    default4 = _select_transition(token4, {}, plan_record_versions=1)
    assert default4[0] == "4"
    assert default4[1] == "phase-4-awaiting-ticket-intake"

    # next fallback when no transitions exist
    token2 = spec.entries["2"]
    fallback_next = _select_transition(token2, {}, plan_record_versions=1)
    assert fallback_next[0] == "2.1"
    assert fallback_next[1] == "spec-next"


def test_phase53_multiple_specific_matches_use_first_yaml_order(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))
    entry = spec.entries["5.3"]
    state = {
        "BusinessRules": {"ExecutionEvidence": True, "Outcome": "extracted"},
        "TechnicalDebt": {"Proposed": True},
        "Rollback": {"Required": True},
    }
    resolved = _select_transition(entry, state, plan_record_versions=1)
    assert resolved[0] == "5.4"
    assert resolved[1] == "phase-5.3-to-5.4"


def test_misaligned_next_default_phases_are_explicitly_routed_by_default(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))

    r54 = _select_transition(spec.entries["5.4"], {}, plan_record_versions=1)
    assert r54[0] == "6"
    assert r54[1] == "phase-5.4-to-6"

    r55 = _select_transition(spec.entries["5.5"], {}, plan_record_versions=1)
    assert r55[0] == "6"
    assert r55[1] == "phase-5.5-to-6"


def test_phase21_specific_transition_beats_default(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))
    entry = spec.entries["2.1"]
    resolved = _select_transition(entry, {}, plan_record_versions=1)
    assert resolved[0] == "1.5"
    assert resolved[1] == "phase-1.5-routing-required"


def test_phase21_default_applies_when_specific_condition_not_met(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))
    entry = spec.entries["2.1"]
    state = {"BusinessRules": {"ExecutionEvidence": True, "Outcome": "extracted"}}
    resolved = _select_transition(entry, state, plan_record_versions=1)
    assert resolved[0] == "3A"
    assert resolved[1] == "phase-2.1-to-3a"


def test_phase3a_no_apis_specific_beats_default(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))
    entry = spec.entries["3A"]
    resolved = _select_transition(entry, {}, plan_record_versions=1)
    assert resolved[0] == "4"
    assert resolved[1] == "phase-3a-not-applicable-to-phase4"


def test_phase3a_default_applies_when_apis_are_in_scope(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))
    entry = spec.entries["3A"]
    state = {"AddonsEvidence": {"openapi": {"detected": True}}}
    resolved = _select_transition(entry, state, plan_record_versions=1)
    assert resolved[0] == "3B-1"
    assert resolved[1] == "phase-3a-to-3b1"


def test_phase6_default_fallback_is_used_when_no_specific_matches(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))
    entry = spec.entries["6"]
    resolved = _select_transition(entry, {}, plan_record_versions=1)
    assert entry.next_token is None
    assert resolved[0] == "6"
    assert resolved[1] == "phase-6-implementation-review-required"


def test_all_defined_transitions_can_be_triggered_once(tmp_path: Path) -> None:
    spec = load_phase_api(_commands_home_with_repo_phase_api(tmp_path))

    cases = [
        ("1.2", {"Intent": {"Path": "x", "Sha256": "y", "EffectiveScope": "repo"}}, 1, "phase-1.2-to-1.3-auto"),
        ("2.1", {}, 1, "phase-1.5-routing-required"),
        ("2.1", {"BusinessRules": {"ExecutionEvidence": True, "Outcome": "extracted"}}, 1, "phase-2.1-to-3a"),
        ("3A", {}, 1, "phase-3a-not-applicable-to-phase4"),
        ("3A", {"AddonsEvidence": {"openapi": {"detected": True}}}, 1, "phase-3a-to-3b1"),
        ("4", {"TicketRecordDigest": "sha256:abc"}, 1, "phase-4-to-5-ticket-intake"),
        ("4", {}, 1, "phase-4-awaiting-ticket-intake"),
        ("5", {}, 0, "phase-5-plan-record-prep-required"),
        ("5", {"phase5_self_review_iterations": 0}, 1, "phase-5-self-review-required"),
        (
            "5",
            {"phase5_self_review_iterations": 1, "Phase5Review": {"prev_plan_digest": "x", "curr_plan_digest": "x"}},
            1,
            "phase-5-architecture-review-ready",
        ),
        ("5.3", {"BusinessRules": {"ExecutionEvidence": True, "Outcome": "extracted"}}, 1, "phase-5.3-to-5.4"),
        ("5.3", {"TechnicalDebt": {"Proposed": True}}, 1, "phase-5.3-to-5.5"),
        ("5.3", {"Rollback": {"Required": True}}, 1, "phase-5.3-to-5.6"),
        ("5.3", {}, 1, "phase-5.3-to-6"),
        ("5.4", {"TechnicalDebt": {"Proposed": True}}, 1, "phase-5.4-to-5.5"),
        ("5.4", {"Rollback": {"Required": True}}, 1, "phase-5.4-to-5.6"),
        ("5.4", {}, 1, "phase-5.4-to-6"),
        ("5.5", {"Rollback": {"Required": True}}, 1, "phase-5.5-to-5.6"),
        ("5.5", {}, 1, "phase-5.5-to-6"),
        ("5.6", {}, 1, "phase-5.6-to-6"),
        ("6", {"implementation_accepted": True}, 1, "phase-6-implementation-accepted"),
        (
            "6",
            {"implementation_execution_status": "blocked", "implementation_hard_blockers": ["blocked"]},
            1,
            "phase-6-implementation-blocked",
        ),
        (
            "6",
            {"implementation_rework_clarification_required": True},
            1,
            "phase-6-implementation-rework-clarification",
        ),
        ("6", {"active_gate": "Implementation Presentation Gate"}, 1, "phase-6-implementation-presentation-ready"),
        ("6", {"implementation_execution_status": "in_progress"}, 1, "phase-6-implementation-execution"),
        ("6", {"implementation_started": True}, 1, "phase-6-implementation-started"),
        ("6", {"workflow_complete": True}, 1, "phase-6-workflow-complete"),
        (
            "6",
            {"active_gate": "Evidence Presentation Gate", "UserReviewDecision": {"decision": "changes_requested"}},
            1,
            "phase-6-changes-requested-loop-reset",
        ),
        ("6", {"phase6_state": "6.rework"}, 1, "phase-6-rework-clarification-required"),
        (
            "6",
            {"active_gate": "Evidence Presentation Gate", "UserReviewDecision": {"decision": "reject"}},
            1,
            "phase-6-rejected-to-phase4",
        ),
        ("6", {"ImplementationReview": {"iteration": 0, "max_iterations": 3, "min_self_review_iterations": 1}}, 1, "phase-6-implementation-review-required"),
        ("6", {"ImplementationReview": {"iteration": 3, "max_iterations": 3, "min_self_review_iterations": 1}}, 1, "phase-6-ready-for-user-review"),
    ]

    for token, state, plan_versions, expected_source in cases:
        resolved = _select_transition(spec.entries[token], state, plan_record_versions=plan_versions)
        assert resolved[1] == expected_source


def test_no_default_and_no_next_returns_no_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "cfg"
    commands_home = cfg / "commands"
    spec_home = tmp_path / "governance_spec"
    commands_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)
    spec_text = (
        """
version: 1
start_token: "X"
phases:
  - token: "X"
    phase: "X-Terminal"
    active_gate: "Terminal"
    next_gate_condition: "Stop"
    route_strategy: "stay"
""".strip()
        + "\n"
    )
    (spec_home / "phase_api.yaml").write_text(spec_text, encoding="utf-8")
    (cfg / "governance.paths.json").write_text(
        json.dumps({
            "schema": "opencode-governance.paths.v1",
            "paths": {
                "configRoot": str(cfg),
                "commandsHome": str(commands_home),
                "workspacesHome": str(cfg / "workspaces"),
                "specHome": str(spec_home),
                "pythonCommand": sys.executable,
            },
        }),
        encoding="utf-8",
    )
    spec = load_phase_api(commands_home)
    entry = spec.entries["X"]
    resolved = _select_transition(entry, {}, plan_record_versions=1)
    assert resolved[0] is None
    assert resolved[1] == "spec-next"
