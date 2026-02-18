"""Application DTOs for governance response envelopes."""

from __future__ import annotations

from typing import Any, TypedDict


class NextActionDto(TypedDict, total=False):
    status: str
    next: str
    why: str
    command: str
    type: str


class SnapshotDto(TypedDict, total=False):
    Confidence: str
    Risk: str
    Scope: str


class GovernanceResponseEnvelope(TypedDict, total=False):
    status: str
    mode: str
    next_action: NextActionDto
    session_state: dict[str, Any]
    snapshot: SnapshotDto
    reason_payload: dict[str, Any]
    session_state_full: dict[str, Any]
    phase: str
    active_gate: str
    reason_code: str
