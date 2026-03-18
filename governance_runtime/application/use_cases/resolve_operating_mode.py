"""Operating mode resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from governance.domain.operating_profile import (
    MISSING_OPERATING_MODE,
    EnforcementContext,
    OperatingProfileError,
    derive_mode_evidence,
    resolve_operating_profile,
)

if TYPE_CHECKING:
    from governance_runtime.application.ports.gateways import HostAdapter, OperatingMode


_PROFILE_TO_RUNTIME_MODE: dict[str, "OperatingMode"] = {
    "solo": "user",
    "team": "pipeline",
    "regulated": "pipeline",
}

_REPO_POLICY_RELATIVE_PATH = ".opencode/governance-repo-policy.json"


@dataclass(frozen=True)
class OperatingModeResolutionResult:
    init_operating_mode: str
    repo_operating_mode: str
    requested_operating_mode: str | None
    enforced_operating_mode: str | None
    floor_operating_mode: str | None
    resolved_operating_mode: str
    effective_operating_mode: "OperatingMode"
    enforcement_source: str
    enforcement_trusted: bool
    fallback_applied: bool
    error_code: str | None
    break_glass_active: bool
    break_glass_status: str
    break_glass: dict[str, object]
    resolution_state: str
    repo_ssot_source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "initOperatingMode": self.init_operating_mode,
            "repoOperatingMode": self.repo_operating_mode,
            "requestedOperatingMode": self.requested_operating_mode,
            "enforcedOperatingMode": self.enforced_operating_mode,
            "floorOperatingMode": self.floor_operating_mode,
            "resolvedOperatingMode": self.resolved_operating_mode,
            "effectiveOperatingMode": self.effective_operating_mode,
            "enforcementSource": self.enforcement_source,
            "enforcementTrusted": self.enforcement_trusted,
            "fallbackApplied": self.fallback_applied,
            "errorCode": self.error_code,
            "breakGlassActive": self.break_glass_active,
            "breakGlassStatus": self.break_glass_status,
            "breakGlass": dict(self.break_glass),
            "resolutionState": self.resolution_state,
            "repoSsotSource": self.repo_ssot_source,
        }


def _runtime_mode_to_profile(mode: str | None) -> str | None:
    if mode is None:
        return None
    token = str(mode).strip().lower()
    if not token:
        return None
    if token in {"solo", "team", "regulated", "user", "pipeline", "agents_strict", "system"}:
        return token
    return None


def _profile_to_runtime_mode(profile: str) -> "OperatingMode":
    return _PROFILE_TO_RUNTIME_MODE.get(profile, "user")


def _truthy(token: str | None) -> bool:
    value = str(token or "").strip().lower()
    return bool(value and value not in {"0", "false", "no", "off"})


def _load_repo_operating_mode_from_policy(repo_root: str | None) -> tuple[str | None, str]:
    if not repo_root:
        return None, "missing-repo-root"
    candidate = Path(repo_root) / _REPO_POLICY_RELATIVE_PATH
    if not candidate.is_file():
        return None, "missing-policy-file"
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None, "invalid-policy-json"
    if not isinstance(payload, dict):
        return None, "invalid-policy-root"
    if str(payload.get("schema") or "").strip() != "opencode-governance-repo-policy.v1":
        return None, "invalid-policy-schema"
    token = str(payload.get("operatingMode") or "").strip().lower()
    if token not in {"solo", "team", "regulated"}:
        return None, "invalid-policy-operating-mode"
    return token, "repo-policy"


def _resolve_repo_profile(env: dict[str, str], init_profile: str | None) -> tuple[str | None, str, str | None]:
    repo_root = str(env.get("OPENCODE_REPO_ROOT", "")).strip() or None
    repo_mode, source = _load_repo_operating_mode_from_policy(repo_root)
    if repo_mode is not None:
        return repo_mode, source, None

    backfill = str(env.get("OPENCODE_REPO_OPERATING_MODE", "")).strip() or None
    if backfill:
        deadline = str(env.get("OPENCODE_REPO_OPERATING_MODE_BLOCK_AFTER_UTC", "")).strip() or ""
        now = str(env.get("OPENCODE_CURRENT_TIME_UTC", "")).strip() or ""
        if deadline and now and now >= deadline:
            return None, source, MISSING_OPERATING_MODE
        return backfill, "env-backfill", MISSING_OPERATING_MODE

    if init_profile is not None:
        deadline = str(env.get("OPENCODE_REPO_OPERATING_MODE_BLOCK_AFTER_UTC", "")).strip() or ""
        now = str(env.get("OPENCODE_CURRENT_TIME_UTC", "")).strip() or ""
        if deadline and now and now >= deadline:
            return None, source, MISSING_OPERATING_MODE
        return init_profile, "init-backfill", MISSING_OPERATING_MODE
    return None, source, MISSING_OPERATING_MODE


def resolve_operating_mode_result(
    adapter: "HostAdapter",
    requested: "OperatingMode | None",
) -> OperatingModeResolutionResult:
    if requested is not None and requested not in {"user"}:
        requested_profile = _runtime_mode_to_profile(requested)
        return OperatingModeResolutionResult(
            init_operating_mode="solo",
            repo_operating_mode="solo",
            requested_operating_mode=requested_profile,
            enforced_operating_mode=None,
            floor_operating_mode=None,
            resolved_operating_mode=str(requested_profile or "solo"),
            effective_operating_mode=requested,
            enforcement_source="unknown",
            enforcement_trusted=False,
            fallback_applied=False,
            error_code=None,
            break_glass_active=False,
            break_glass_status="inactive",
            break_glass={},
            resolution_state="resolved",
            repo_ssot_source="explicit-request",
        )

    env = dict(adapter.environment())
    if requested is None and str(adapter.default_operating_mode()) == "agents_strict":
        repo_root = str(env.get("OPENCODE_REPO_ROOT", "")).strip() or None
        repo_mode, _ = _load_repo_operating_mode_from_policy(repo_root)
        if repo_mode is None and not str(env.get("OPENCODE_REPO_OPERATING_MODE", "")).strip():
            return OperatingModeResolutionResult(
                init_operating_mode="regulated",
                repo_operating_mode="regulated",
                requested_operating_mode=None,
                enforced_operating_mode=None,
                floor_operating_mode=None,
                resolved_operating_mode="regulated",
                effective_operating_mode="agents_strict",
                enforcement_source="legacy-default",
                enforcement_trusted=False,
                fallback_applied=False,
                error_code=None,
                break_glass_active=False,
                break_glass_status="inactive",
                break_glass={},
                resolution_state="resolved",
                repo_ssot_source="legacy-init",
            )

    requested_profile = _runtime_mode_to_profile(requested)
    init_profile = _runtime_mode_to_profile(adapter.default_operating_mode())
    repo_profile, repo_source, repo_error = _resolve_repo_profile(env, init_profile)
    if repo_profile is None and repo_error == MISSING_OPERATING_MODE:
        return OperatingModeResolutionResult(
            init_operating_mode=str(init_profile or "solo"),
            repo_operating_mode=str(init_profile or "solo"),
            requested_operating_mode=requested_profile,
            enforced_operating_mode=None,
            floor_operating_mode=None,
            resolved_operating_mode="team",
            effective_operating_mode="pipeline",
            enforcement_source="unknown",
            enforcement_trusted=False,
            fallback_applied=False,
            error_code=MISSING_OPERATING_MODE,
            break_glass_active=False,
            break_glass_status="inactive",
            break_glass={},
            resolution_state="blocked",
            repo_ssot_source=repo_source,
        )

    enforced_profile = str(env.get("OPENCODE_ENFORCE_PROFILE", "")).strip() or None
    enforced_source = str(env.get("OPENCODE_ENFORCE_PROFILE_SOURCE", "")).strip() or None

    ci_active = _truthy(env.get("CI"))
    if ci_active and enforced_profile is None:
        enforced_profile = "team"
        enforced_source = enforced_source or "ci"

    floor_profile = str(env.get("OPENCODE_PROFILE_FLOOR", "")).strip() or None
    if ci_active and floor_profile is None:
        floor_profile = "team"

    context = EnforcementContext(
        ci_active=ci_active,
        protected_pipeline=_truthy(env.get("OPENCODE_PIPELINE_PROTECTED") or env.get("GITHUB_REF_PROTECTED")),
        regulated_pipeline=_truthy(env.get("OPENCODE_REGULATED_PIPELINE")),
        repo_policy_bound=_truthy(env.get("OPENCODE_REPO_POLICY_BOUND")),
        org_policy_bound=_truthy(env.get("OPENCODE_ORG_POLICY_BOUND")),
    )

    break_glass_json = str(env.get("OPENCODE_BREAK_GLASS_JSON", "")).strip()
    break_glass: dict[str, object] = {}
    if break_glass_json:
        try:
            parsed = json.loads(break_glass_json)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            break_glass = parsed

    try:
        resolved = resolve_operating_profile(
            requested_operating_mode=requested_profile,
            repo_operating_mode=repo_profile,
            init_operating_mode=init_profile,
            enforced_operating_mode=enforced_profile,
            enforced_source=enforced_source,
            enforcement_context=context,
            floor_operating_mode=floor_profile,
            break_glass_expires_at=str(break_glass.get("expires_at") or env.get("OPENCODE_BREAK_GLASS_EXPIRES_AT", "")).strip() or None,
            break_glass_reason_code=str(break_glass.get("reason_code") or env.get("OPENCODE_BREAK_GLASS_REASON_CODE", "")).strip() or None,
            break_glass_now_utc=str(env.get("OPENCODE_CURRENT_TIME_UTC", "")).strip() or None,
            break_glass_actor=str(break_glass.get("actor") or "").strip() or None,
            break_glass_timestamp=str(break_glass.get("timestamp") or env.get("OPENCODE_CURRENT_TIME_UTC", "")).strip() or None,
            break_glass_rationale=str(break_glass.get("rationale") or "").strip() or None,
            break_glass_scope=str(break_glass.get("scope") or "").strip() or None,
            break_glass_approval_context=str(break_glass.get("approval_context") or "").strip() or None,
        )
        resolved_mode = str(resolved.resolved_operating_mode)
        fallback_applied = repo_error is not None
        error_code = repo_error
        resolution_state = "resolved_with_fallback" if fallback_applied else "resolved"
        return OperatingModeResolutionResult(
            init_operating_mode=str(resolved.init_operating_mode),
            repo_operating_mode=str(resolved.repo_operating_mode),
            requested_operating_mode=str(resolved.requested_operating_mode) if resolved.requested_operating_mode else None,
            enforced_operating_mode=str(resolved.enforced_operating_mode) if resolved.enforced_operating_mode else None,
            floor_operating_mode=str(resolved.floor_operating_mode) if resolved.floor_operating_mode else None,
            resolved_operating_mode=resolved_mode,
            effective_operating_mode=_profile_to_runtime_mode(resolved_mode),
            enforcement_source=str(resolved.enforcement_source),
            enforcement_trusted=bool(resolved.enforcement_trusted),
            fallback_applied=fallback_applied,
            error_code=error_code,
            break_glass_active=bool(resolved.break_glass_active),
            break_glass_status=str(resolved.break_glass_status),
            break_glass=dict(break_glass),
            resolution_state=resolution_state,
            repo_ssot_source=repo_source,
        )
    except OperatingProfileError as exc:
        blocked = exc.code in {"UNTRUSTED_ENFORCEMENT_SOURCE", MISSING_OPERATING_MODE}
        effective = "pipeline"
        _, resolved_mode, _ = derive_mode_evidence(
            effective_operating_mode=effective,
            resolved_operating_mode=None,
            verify_policy_version="v1",
        )
        return OperatingModeResolutionResult(
            init_operating_mode=str(init_profile or "solo"),
            repo_operating_mode=str(repo_profile or init_profile or "solo"),
            requested_operating_mode=requested_profile,
            enforced_operating_mode=enforced_profile,
            floor_operating_mode=floor_profile,
            resolved_operating_mode=str(resolved_mode),
            effective_operating_mode=effective,
            enforcement_source=str(enforced_source or "unknown"),
            enforcement_trusted=False,
            fallback_applied=not blocked,
            error_code=exc.code,
            break_glass_active=False,
            break_glass_status="invalid" if exc.code.startswith("BREAK_GLASS") else "inactive",
            break_glass=dict(break_glass),
            resolution_state="blocked" if blocked else "resolved_with_fallback",
            repo_ssot_source=repo_source,
        )


def resolve_effective_operating_mode(adapter: "HostAdapter", requested: "OperatingMode | None") -> "OperatingMode":
    """Backward-compatible mode resolver returning only effective mode."""

    return resolve_operating_mode_result(adapter, requested).effective_operating_mode


def has_required_mode_capabilities(mode: "OperatingMode", caps: Any) -> bool:
    """Return True when minimal capabilities for the requested mode are satisfied."""

    if mode == "user":
        return caps.fs_read_commands_home and caps.fs_write_workspaces_home
    if mode == "system":
        return caps.exec_allowed and caps.fs_read_commands_home and caps.fs_write_workspaces_home
    return (
        caps.exec_allowed
        and caps.fs_read_commands_home
        and caps.fs_write_workspaces_home
        and caps.fs_write_commands_home
        and caps.git_available
    )
