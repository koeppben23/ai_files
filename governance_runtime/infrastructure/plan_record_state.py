"""Canonical runtime plan-record state resolution utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class PlanRecordSignal:
    versions: int
    status: str
    source: str

    @property
    def ready(self) -> bool:
        return self.versions >= 1


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value >= 0 else 0
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return int(raw)
    return None


def _versions_from_state(state: Mapping[str, object]) -> int | None:
    for key in ("plan_record_versions", "PlanRecordVersions"):
        if key in state:
            parsed = _coerce_non_negative_int(state.get(key))
            if parsed is not None:
                return parsed
    return None


def _status_from_state(state: Mapping[str, object]) -> str | None:
    for key in ("plan_record_status", "PlanRecordStatus"):
        value = state.get(key)
        if isinstance(value, str):
            status = value.strip()
            if status:
                return status
    return None


def _signal_from_plan_record_file(plan_record_file: Path | None) -> PlanRecordSignal | None:
    if plan_record_file is None or not plan_record_file.is_file():
        return None
    try:
        payload = json.loads(plan_record_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PlanRecordSignal(versions=0, status="error", source="workspace-file-error")

    if not isinstance(payload, Mapping):
        return PlanRecordSignal(versions=0, status="error", source="workspace-file-error")

    versions = payload.get("versions")
    version_count = len(versions) if isinstance(versions, list) else 0
    status_raw = payload.get("status")
    status = str(status_raw).strip() if isinstance(status_raw, str) and status_raw.strip() else "unknown"
    return PlanRecordSignal(versions=version_count, status=status, source="workspace-file")


def resolve_plan_record_signal(
    *,
    state: Mapping[str, object] | None,
    plan_record_file: Path | None,
) -> PlanRecordSignal:
    root = state or {}
    workspace_signal = _signal_from_plan_record_file(plan_record_file)
    state_versions = _versions_from_state(root)
    state_status = _status_from_state(root)

    if workspace_signal is not None:
        if state_status and workspace_signal.status in {"unknown", "absent", "error"}:
            return PlanRecordSignal(
                versions=workspace_signal.versions,
                status=state_status,
                source=workspace_signal.source,
            )
        return workspace_signal

    if state_versions is not None:
        return PlanRecordSignal(
            versions=state_versions,
            status=state_status or "unknown",
            source="session-state",
        )

    if state_status:
        return PlanRecordSignal(versions=0, status=state_status, source="session-state")

    return PlanRecordSignal(versions=0, status="absent", source="default")
