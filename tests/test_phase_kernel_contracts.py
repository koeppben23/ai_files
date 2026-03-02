from __future__ import annotations

from pathlib import Path
import json

import pytest

from governance.kernel.phase_kernel import RuntimeContext, execute, _deduplicate_criteria


def _write_phase_api(commands_home: Path) -> None:
    repo_spec = Path(__file__).resolve().parents[1] / "phase_api.yaml"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(repo_spec.read_text(encoding="utf-8"), encoding="utf-8")


def test_phase_api_start_token_is_bootstrap_entrypoint() -> None:
    repo_spec = Path(__file__).resolve().parents[1] / "phase_api.yaml"
    text = repo_spec.read_text(encoding="utf-8")
    assert 'start_token: "0"' in text


def test_kernel_blocks_when_phase_api_missing(tmp_path: Path) -> None:
    result = execute(
        current_token="2.1",
        session_state_doc={"SESSION_STATE": {}},
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=tmp_path / "commands",
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "phase-api-missing"


def test_kernel_routes_2_1_to_1_5_when_business_rules_unresolved(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/master.md"},
            "AddonsEvidence": {},
        }
    }
    result = execute(
        current_token="2.1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "1.5-BusinessRules"
    assert result.source == "phase-1.5-routing-required"


def test_kernel_routes_2_1_to_1_5_when_business_rules_execute_decision_set(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/master.md"},
            "AddonsEvidence": {},
            "BusinessRules": {"Decision": "execute"},
        }
    }
    result = execute(
        current_token="2.1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "1.5-BusinessRules"
    assert result.source == "phase-1.5-routing-required"


def test_kernel_blocks_phase_1_3_when_exit_evidence_missing(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "1.3-RulebookLoad",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {},
            "AddonsEvidence": {},
        }
    }
    result = execute(
        current_token="1.3",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Rulebook Load Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "phase-exit-evidence-missing"


def test_kernel_blocks_with_invalid_spec_and_writes_block_event(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(
        """
version: 1
start_token: "1.1"
phases:
  - token: "1.1"
    phase: "1.1-Bootstrap"
    active_gate: "Workspace Ready Gate"
    next_gate_condition: "Continue"
    next: "unknown"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = execute(
        current_token="1.1",
        session_state_doc={"SESSION_STATE": {}},
        runtime_ctx=RuntimeContext(
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    rows = [
        json.loads(line)
        for line in (commands_home / "logs" / "flow.log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["event"] == "PHASE_BLOCKED"


# ────────────────────────────────────────────────────────────────────
# M6 Bug #2 — Criteria deduplication unit tests
# ────────────────────────────────────────────────────────────────────


class TestDeduplicateCriteriaUnit:
    """Unit tests for _deduplicate_criteria() — pure function, no kernel."""

    def test_no_duplicates_passes_through(self) -> None:
        """Criteria with unique keys are returned unchanged."""
        criteria = [
            {"criterion_key": "A", "critical": True, "artifact_kind": "foo"},
            {"criterion_key": "B", "critical": False, "artifact_kind": "bar"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 2
        assert result.had_duplicates is False
        assert result.conflicts == []

    def test_compatible_duplicates_merge_critical_to_true(self) -> None:
        """Same key, same artifact_kind, differing critical → True wins."""
        criteria = [
            {"criterion_key": "X", "critical": False, "artifact_kind": "scorecard"},
            {"criterion_key": "X", "critical": True, "artifact_kind": "scorecard"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1, (
            f"Expected 1 deduplicated criterion, got {len(result.criteria)}"
        )
        assert result.had_duplicates is True
        assert result.conflicts == []
        merged = result.criteria[0]
        assert merged["criterion_key"] == "X"
        assert merged["critical"] is True
        assert merged["artifact_kind"] == "scorecard"

    def test_compatible_duplicates_merge_threshold_to_strictest(self) -> None:
        """Same key, same artifact_kind, different static thresholds → higher wins."""
        criteria = [
            {"criterion_key": "T", "critical": True, "artifact_kind": "tier",
             "threshold": 60},
            {"criterion_key": "T", "critical": True, "artifact_kind": "tier",
             "threshold": 80},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert result.criteria[0]["threshold"] == 80

    def test_incompatible_artifact_kind_flagged_as_conflict(self) -> None:
        """Same key but different artifact_kind = semantic conflict."""
        criteria = [
            {"criterion_key": "C", "critical": True, "artifact_kind": "foo"},
            {"criterion_key": "C", "critical": True, "artifact_kind": "bar"},
        ]
        result = _deduplicate_criteria(criteria)
        # Conflict flagged, original entry kept.
        assert len(result.criteria) == 1
        assert len(result.conflicts) == 1
        assert "artifact_kind" in result.conflicts[0]
        assert result.had_duplicates is True

    def test_incompatible_resolver_flagged_as_conflict(self) -> None:
        """Same key but different threshold_resolver = conflict."""
        criteria = [
            {"criterion_key": "R", "critical": True, "artifact_kind": "tier",
             "threshold_mode": "dynamic_by_risk_tier",
             "threshold_resolver": "dynamic_by_risk_tier"},
            {"criterion_key": "R", "critical": True, "artifact_kind": "tier",
             "threshold_mode": "static",
             "threshold_resolver": "static_resolver"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert len(result.conflicts) == 1
        assert "threshold_mode" in result.conflicts[0]

    def test_triple_duplicate_merges_to_single_entry(self) -> None:
        """Three compatible entries for the same key → one merged entry."""
        criteria = [
            {"criterion_key": "Z", "critical": False, "artifact_kind": "x"},
            {"criterion_key": "Z", "critical": False, "artifact_kind": "x"},
            {"criterion_key": "Z", "critical": True, "artifact_kind": "x"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert result.criteria[0]["critical"] is True
        assert result.had_duplicates is True

    def test_mixed_unique_and_duplicate_keys(self) -> None:
        """Mix of unique and duplicate keys: only duplicates are merged."""
        criteria = [
            {"criterion_key": "A", "critical": True, "artifact_kind": "alpha"},
            {"criterion_key": "B", "critical": False, "artifact_kind": "beta"},
            {"criterion_key": "A", "critical": False, "artifact_kind": "alpha"},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 2
        keys = [c["criterion_key"] for c in result.criteria]
        assert "A" in keys
        assert "B" in keys
        a_entry = next(c for c in result.criteria if c["criterion_key"] == "A")
        assert a_entry["critical"] is True  # Merged: True wins

    def test_threshold_added_from_second_when_first_has_none(self) -> None:
        """If the first entry has no threshold and the second does, adopt it."""
        criteria = [
            {"criterion_key": "Q", "critical": True, "artifact_kind": "q"},
            {"criterion_key": "Q", "critical": True, "artifact_kind": "q",
             "threshold": 75},
        ]
        result = _deduplicate_criteria(criteria)
        assert len(result.criteria) == 1
        assert result.criteria[0]["threshold"] == 75

    def test_empty_input_returns_empty(self) -> None:
        result = _deduplicate_criteria([])
        assert result.criteria == []
        assert result.had_duplicates is False
        assert result.conflicts == []


# ────────────────────────────────────────────────────────────────────
# M6 Bug #2 — Integration: kernel produces deduplicated strict-exit results
# ────────────────────────────────────────────────────────────────────


@pytest.mark.governance
def test_kernel_strict_exit_deduplicates_criteria(tmp_path: Path) -> None:
    """Duplicate criterion_key from multiple profiles → 1 result, not N.

    Scenario: Two phase_exit_contract entries for the same phase, each
    contributing the same criterion_key with the same artifact_kind but
    differing critical flags.  The kernel must:
    - Evaluate exactly 1 criterion (deduplicated, critical=True wins).
    - Report at most 1 reason code (not 2 duplicate codes).
    - Not inflate summary counts.
    """
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-Architecture",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/master.md"},
            "AddonsEvidence": {},
            # Phase 1.3 foundation prerequisites.
            "BusinessRules": {"Decision": "skip", "Scope": "none"},
            "ExternalApiArtifacts": {},
            "PolicyMode": {"principal_strict": True},
            # Two profiles deliver the same criterion_key for the same phase.
            "phase_exit_contract": [
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "DUP-KEY-1",
                            "critical": False,
                            "artifact_kind": "test_artifact",
                        },
                    ],
                },
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "DUP-KEY-1",
                            "critical": True,
                            "artifact_kind": "test_artifact",
                        },
                    ],
                },
            ],
            # No evidence → the criterion will fail under strict mode.
            "BuildEvidence": {"items": []},
            "RiskTiering": {"ActiveTier": "Tier-high"},
            # Satisfy phase 5 exit evidence keys so we reach the strict gate.
            "Gates": {
                "P5.3-TestQuality": "compliant",
                "P5.4-BusinessRules": "compliant",
            },
            "TestQualityEvidence": {"status": "compliant"},
        }
    }
    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    # The gate should block (missing evidence under strict mode).
    assert result.status == "BLOCKED"
    assert result.source == "strict-exit-gate"

    # Read the JSONL event log to verify deduplicated criteria.
    flow_log = commands_home / "logs" / "flow.log.jsonl"
    assert flow_log.exists(), "Flow log should have been written"
    rows = [
        json.loads(line)
        for line in flow_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    block_events = [r for r in rows if r.get("event") == "PHASE_BLOCKED"]
    assert block_events, "Expected at least one PHASE_BLOCKED event"
    last_block = block_events[-1]
    detail = last_block.get("strict_exit_detail")
    assert detail is not None, "strict_exit_detail should be present in event"

    criteria_list = detail.get("criteria", [])
    # The key assertion: exactly 1 criterion result, not 2.
    assert len(criteria_list) == 1, (
        f"Expected 1 deduplicated criterion result, got {len(criteria_list)} "
        f"(duplicate bug if 2)"
    )
    # Merged critical=True must have won.
    assert criteria_list[0]["critical"] is True

    # Exactly 1 reason code (not duplicated).
    reason_codes_list = detail.get("reason_codes", [])
    assert len(reason_codes_list) == 1, (
        f"Expected 1 reason code, got {len(reason_codes_list)} "
        f"(inflated if >1)"
    )


@pytest.mark.governance
def test_kernel_strict_exit_blocks_on_incompatible_criteria_conflict(tmp_path: Path) -> None:
    """Incompatible criterion definitions under principal_strict → block.

    Two profiles define the same criterion_key but with different
    artifact_kind — this is a semantic conflict, not a mergeable duplicate.
    Under principal_strict the kernel must fail-closed.
    """
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "5-Architecture",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/master.md"},
            "AddonsEvidence": {},
            "BusinessRules": {"Decision": "skip", "Scope": "none"},
            "ExternalApiArtifacts": {},
            "PolicyMode": {"principal_strict": True},
            "phase_exit_contract": [
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "CONFLICT-KEY",
                            "critical": True,
                            "artifact_kind": "artifact_alpha",
                        },
                    ],
                },
                {
                    "phase": "phase_5",
                    "pass_criteria": [
                        {
                            "criterion_key": "CONFLICT-KEY",
                            "critical": True,
                            "artifact_kind": "artifact_beta",
                        },
                    ],
                },
            ],
            "BuildEvidence": {"items": []},
            "RiskTiering": {"ActiveTier": "Tier-high"},
            "Gates": {
                "P5.3-TestQuality": "compliant",
                "P5.4-BusinessRules": "compliant",
            },
            "TestQualityEvidence": {"status": "compliant"},
        }
    }
    result = execute(
        current_token="5",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Architecture Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "strict-exit-gate"
    # The block reason must mention contract conflict.
    assert "contract conflict" in (result.next_gate_condition or "").lower()
