from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.engine.business_rules_hydration import (
    POINTER_AS_SESSION_STATE_ERROR,
    hydrate_business_rules_state_from_artifacts,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_happy_hydration_accepts_materialized_session_state(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inventory = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(inventory, "- BR-001: Access must be checked\n")
    state: dict[str, object] = {"Scope": {}, "BusinessRules": {}}

    applied = hydrate_business_rules_state_from_artifacts(
        state=state,
        status_path=status,
        inventory_path=inventory,
    )

    assert applied is True
    assert state["BusinessRules"]["Outcome"] == "extracted"  # type: ignore[index]


def test_bad_hydration_rejects_canonical_pointer_shaped_state(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inventory = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(inventory, "- BR-001: Access must be checked\n")

    with pytest.raises(ValueError, match=POINTER_AS_SESSION_STATE_ERROR):
        hydrate_business_rules_state_from_artifacts(
            state={
                "schema": "opencode-session-pointer.v1",
                "activeSessionStateFile": str(tmp_path / "SESSION_STATE.json"),
            },
            status_path=status,
            inventory_path=inventory,
        )


def test_corner_hydration_rejects_legacy_pointer_shaped_state(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inventory = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(inventory, "- BR-001: Access must be checked\n")

    with pytest.raises(ValueError, match=POINTER_AS_SESSION_STATE_ERROR):
        hydrate_business_rules_state_from_artifacts(
            state={
                "schema": "active-session-pointer.v1",
                "active_session_state_relative_path": "workspaces/abc123/SESSION_STATE.json",
            },
            status_path=status,
            inventory_path=inventory,
        )


def test_edge_hydration_keeps_non_pointer_empty_state_behavior(tmp_path: Path) -> None:
    applied = hydrate_business_rules_state_from_artifacts(
        state={},
        status_path=tmp_path / "missing-status.md",
        inventory_path=tmp_path / "missing-inventory.md",
    )

    assert applied is False
