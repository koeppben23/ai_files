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


def rulebook_gate(*, target_phase: str, loaded_rulebooks: dict[str, Any],
                  active_profile: str | None = None,
                  addons_evidence: dict[str, Any] | None = None) -> GateResult:
    """Check whether the rulebook gate is satisfied for *target_phase*.

    For phases with major number >= 4 the gate requires:
    * ``core`` and ``profile`` rulebooks loaded (non-empty strings)
    * ``addons`` mapping with at least one real value
    * ``active_profile`` set (non-empty string)
    * ``addons_evidence`` populated (non-empty mapping)

    This mirrors the kernel's ``_rulebook_gate_passed`` so that all
    code-paths enforce the same contract.
    """
    major_token = str(target_phase).split(".", 1)[0].strip()
    try:
        major_phase = int(major_token)
    except ValueError:
        major_phase = 0
    if major_phase < 4:
        return GateResult(ok=True, code="OK", reason="rulebook gate not required")
    if not isinstance(loaded_rulebooks, dict):
        return GateResult(ok=False, code="RULEBOOKS_MISSING", reason="loaded rulebooks missing")
    if loaded_rulebooks.get("anchors_ok") is False:
        return GateResult(ok=False, code="RULEBOOK_ANCHOR_MISSING", reason="rulebook anchors missing")
    if not loaded_rulebooks.get("core") or not loaded_rulebooks.get("profile"):
        return GateResult(ok=False, code="RULEBOOKS_INCOMPLETE", reason="core/profile rulebooks required")
    # -- addon + evidence alignment (mirrors kernel _rulebook_gate_passed) --
    addons = loaded_rulebooks.get("addons")
    if not isinstance(addons, dict) or not any(
        isinstance(v, str) and v.strip() for v in addons.values()
    ):
        return GateResult(ok=False, code="RULEBOOKS_INCOMPLETE", reason="addon rulebooks required")
    if not isinstance(active_profile, str) or not active_profile.strip():
        return GateResult(ok=False, code="RULEBOOKS_INCOMPLETE", reason="active profile required")
    if not isinstance(addons_evidence, dict) or not addons_evidence:
        return GateResult(ok=False, code="RULEBOOKS_INCOMPLETE", reason="addon evidence required")
    return GateResult(ok=True, code="OK", reason="rulebook gate satisfied")
