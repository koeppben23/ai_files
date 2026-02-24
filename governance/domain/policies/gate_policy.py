from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateResult:
    ok: bool
    code: str
    reason: str


def persistence_gate(state: dict[str, Any]) -> GateResult:
    flags = state.get("CommitFlags") if isinstance(state, dict) else None
    if not isinstance(flags, dict):
        return GateResult(ok=False, code="PERSISTENCE_FLAGS_MISSING", reason="commit flags missing")
    if flags.get("PersistenceCommitted") is not True:
        return GateResult(ok=False, code="PERSISTENCE_NOT_COMMITTED", reason="persistence not committed")
    if flags.get("WorkspaceArtifactsCommitted") is not True:
        return GateResult(ok=False, code="ARTIFACTS_NOT_COMMITTED", reason="workspace artifacts not committed")
    return GateResult(ok=True, code="OK", reason="persistence gate satisfied")


def rulebook_gate(*, target_phase: str, loaded_rulebooks: dict[str, Any]) -> GateResult:
    major_token = str(target_phase).split(".", 1)[0].strip()
    try:
        major_phase = int(major_token)
    except ValueError:
        major_phase = 0
    if major_phase < 4:
        return GateResult(ok=True, code="OK", reason="rulebook gate not required")
    if not isinstance(loaded_rulebooks, dict):
        return GateResult(ok=False, code="RULEBOOKS_MISSING", reason="loaded rulebooks missing")
    if not loaded_rulebooks.get("core") or not loaded_rulebooks.get("profile"):
        return GateResult(ok=False, code="RULEBOOKS_INCOMPLETE", reason="core/profile rulebooks required")
    return GateResult(ok=True, code="OK", reason="rulebook gate satisfied")
