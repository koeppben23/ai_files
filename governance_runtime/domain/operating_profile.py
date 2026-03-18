"""Canonical operating-profile resolution for governance runtime.

Profiles are monotonic and represent governance hardness:
``solo < team < regulated``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Literal


OperatingProfile = Literal["solo", "team", "regulated"]

UNKNOWN_PROFILE = "UNKNOWN_PROFILE"
INVALID_PROFILE_CONFLICT = "INVALID_PROFILE_CONFLICT"
FORBIDDEN_DOWNSHIFT = "FORBIDDEN_DOWNSHIFT"
UNTRUSTED_ENFORCEMENT_SOURCE = "UNTRUSTED_ENFORCEMENT_SOURCE"
MISSING_OPERATING_MODE = "MISSING_OPERATING_MODE"
PROFILE_FLOOR_VIOLATION = "PROFILE_FLOOR_VIOLATION"
BREAK_GLASS_EXPIRED = "BREAK_GLASS_EXPIRED"
BREAK_GLASS_INVALID = "BREAK_GLASS_INVALID"

_PROFILE_ORDER: dict[OperatingProfile, int] = {
    "solo": 1,
    "team": 2,
    "regulated": 3,
}

_PROFILE_ALIASES: dict[str, OperatingProfile] = {
    "solo": "solo",
    "team": "team",
    "regulated": "regulated",
    # backward-compatible aliases
    "user": "solo",
    "pipeline": "team",
    "agents_strict": "regulated",
    "system": "team",
}

_RUNTIME_MODE_TO_PROFILE: dict[str, OperatingProfile] = {
    "user": "solo",
    "pipeline": "team",
    "agents_strict": "regulated",
    "system": "team",
}

EnforcementSource = Literal[
    "local-runtime",
    "ci",
    "protected-pipeline",
    "regulated-pipeline",
    "repo-policy",
    "org-policy",
    "unknown",
]


@dataclass(frozen=True)
class EnforcementContext:
    ci_active: bool
    protected_pipeline: bool
    regulated_pipeline: bool
    repo_policy_bound: bool
    org_policy_bound: bool


@dataclass(frozen=True)
class EnforcementTrustDecision:
    source: EnforcementSource
    trusted: bool
    reason: str


@dataclass(frozen=True)
class BreakGlassRecord:
    actor: str
    timestamp: str
    reason_code: str
    rationale: str
    scope: str
    expires_at: str
    approval_context: str | None = None


class OperatingProfileError(ValueError):
    """Raised when operating-profile resolution fails closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OperatingProfileResolution:
    requested_operating_mode: OperatingProfile | None
    repo_operating_mode: OperatingProfile
    init_operating_mode: OperatingProfile
    enforced_operating_mode: OperatingProfile | None
    enforcement_source: EnforcementSource
    enforcement_trusted: bool
    resolved_operating_mode: OperatingProfile
    floor_operating_mode: OperatingProfile | None
    break_glass_active: bool
    break_glass_status: str


def normalize_operating_profile(mode: str | None) -> OperatingProfile | None:
    if mode is None:
        return None
    token = str(mode).strip().lower()
    if not token:
        return None
    return _PROFILE_ALIASES.get(token)


def runtime_mode_to_operating_profile(mode: str) -> OperatingProfile:
    token = str(mode).strip().lower()
    normalized = normalize_operating_profile(token)
    if normalized is not None:
        return normalized
    return _RUNTIME_MODE_TO_PROFILE.get(token, "solo")


def derive_mode_evidence(
    *,
    effective_operating_mode: str | None,
    resolved_operating_mode: str | None,
    verify_policy_version: str | None,
) -> tuple[str, OperatingProfile, str]:
    effective = str(effective_operating_mode or "").strip().lower() or "unknown"

    resolved_token = str(resolved_operating_mode or "").strip().lower()
    if resolved_token:
        normalized_resolved = normalize_operating_profile(resolved_token)
        if normalized_resolved is None:
            normalized_resolved = runtime_mode_to_operating_profile(resolved_token)
    else:
        normalized_resolved = runtime_mode_to_operating_profile(effective)

    if effective == "unknown" and normalized_resolved in {"solo", "team", "regulated"}:
        effective = normalized_resolved

    verify_policy = str(verify_policy_version or "").strip() or "v1"
    return effective, normalized_resolved, verify_policy


def max_operating_profile(*modes: OperatingProfile | None) -> OperatingProfile:
    present: list[OperatingProfile] = [m for m in modes if m is not None]
    if not present:
        raise OperatingProfileError(MISSING_OPERATING_MODE, "No operating profile inputs provided")
    winner = present[0]
    for candidate in present[1:]:
        if _PROFILE_ORDER[candidate] > _PROFILE_ORDER[winner]:
            winner = candidate
    return winner


def is_downshift(current: OperatingProfile, requested: OperatingProfile) -> bool:
    return _PROFILE_ORDER[requested] < _PROFILE_ORDER[current]


def meets_floor(resolved: OperatingProfile, floor: OperatingProfile | None) -> bool:
    if floor is None:
        return True
    return _PROFILE_ORDER[resolved] >= _PROFILE_ORDER[floor]


def normalize_enforcement_source(source: str | None) -> EnforcementSource:
    token = str(source or "").strip().lower()
    mapping: dict[str, EnforcementSource] = {
        "": "unknown",
        "local": "local-runtime",
        "local-runtime": "local-runtime",
        "ci": "ci",
        "pipeline": "ci",
        "protected-pipeline": "protected-pipeline",
        "regulated-pipeline": "regulated-pipeline",
        "repo-policy": "repo-policy",
        "org-policy": "org-policy",
    }
    return mapping.get(token, "unknown")


def assess_enforcement_trust(*, source: str | None, context: EnforcementContext) -> EnforcementTrustDecision:
    normalized = normalize_enforcement_source(source)
    if normalized == "ci":
        trusted = context.ci_active
        return EnforcementTrustDecision(source=normalized, trusted=trusted, reason="ci-active" if trusted else "ci-signal-missing")
    if normalized == "protected-pipeline":
        trusted = context.ci_active and context.protected_pipeline
        return EnforcementTrustDecision(
            source=normalized,
            trusted=trusted,
            reason="protected-pipeline-signals-valid" if trusted else "protected-pipeline-signals-missing",
        )
    if normalized == "regulated-pipeline":
        trusted = context.ci_active and context.regulated_pipeline
        return EnforcementTrustDecision(
            source=normalized,
            trusted=trusted,
            reason="regulated-pipeline-signals-valid" if trusted else "regulated-pipeline-signals-missing",
        )
    if normalized == "repo-policy":
        trusted = context.repo_policy_bound
        return EnforcementTrustDecision(source=normalized, trusted=trusted, reason="repo-policy-bound" if trusted else "repo-policy-unbound")
    if normalized == "org-policy":
        trusted = context.org_policy_bound
        return EnforcementTrustDecision(source=normalized, trusted=trusted, reason="org-policy-bound" if trusted else "org-policy-unbound")
    return EnforcementTrustDecision(source=normalized, trusted=False, reason="untrusted-source")


def validate_break_glass(record: BreakGlassRecord | None, *, now_utc: str | None) -> tuple[bool, str]:
    if record is None:
        return False, "inactive"
    if not record.reason_code.strip() or not record.actor.strip() or not record.scope.strip() or not record.rationale.strip():
        raise OperatingProfileError(BREAK_GLASS_INVALID, "Break-glass record missing required fields")
    if not record.expires_at.strip():
        raise OperatingProfileError(BREAK_GLASS_EXPIRED, "Break-glass override requires expires_at")
    try:
        expiry = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperatingProfileError(BREAK_GLASS_EXPIRED, "Break-glass expires_at is invalid") from exc
    current_token = str(now_utc or "").strip()
    if not current_token:
        raise OperatingProfileError(BREAK_GLASS_EXPIRED, "Break-glass override requires current UTC timestamp")
    try:
        now = datetime.fromisoformat(current_token.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperatingProfileError(BREAK_GLASS_EXPIRED, "Break-glass current UTC timestamp is invalid") from exc
    if expiry.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
        raise OperatingProfileError(BREAK_GLASS_EXPIRED, "Break-glass override has expired")
    return True, "active"


def resolve_operating_profile(
    *,
    requested_operating_mode: str | None,
    repo_operating_mode: str | None,
    init_operating_mode: str | None,
    enforced_operating_mode: str | None,
    enforced_source: str | None,
    enforcement_context: EnforcementContext | None = None,
    floor_operating_mode: str | None,
    break_glass_expires_at: str | None = None,
    break_glass_reason_code: str | None = None,
    break_glass_now_utc: str | None = None,
    break_glass_actor: str | None = None,
    break_glass_timestamp: str | None = None,
    break_glass_rationale: str | None = None,
    break_glass_scope: str | None = None,
    break_glass_approval_context: str | None = None,
) -> OperatingProfileResolution:
    requested = normalize_operating_profile(requested_operating_mode)
    repo_default = normalize_operating_profile(repo_operating_mode)
    init_default = normalize_operating_profile(init_operating_mode)
    enforced = normalize_operating_profile(enforced_operating_mode)
    floor = normalize_operating_profile(floor_operating_mode)

    if requested_operating_mode and requested is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown requested profile: {requested_operating_mode}")
    if repo_operating_mode and repo_default is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown repo profile: {repo_operating_mode}")
    if init_operating_mode and init_default is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown init profile: {init_operating_mode}")
    if enforced_operating_mode and enforced is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown enforced profile: {enforced_operating_mode}")
    if floor_operating_mode and floor is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown floor profile: {floor_operating_mode}")

    if repo_default is None and init_default is None:
        raise OperatingProfileError(MISSING_OPERATING_MODE, "Repo/init defaults missing")

    trust = assess_enforcement_trust(
        source=enforced_source,
        context=enforcement_context
        if enforcement_context is not None
        else EnforcementContext(
            ci_active=False,
            protected_pipeline=False,
            regulated_pipeline=False,
            repo_policy_bound=False,
            org_policy_bound=False,
        ),
    )
    trusted_enforcement = enforced if (enforced is not None and trust.trusted) else None
    if enforced is not None and trusted_enforcement is None:
        strict_mode = max_operating_profile(repo_default, init_default, floor) == "regulated"
        if strict_mode:
            raise OperatingProfileError(
                UNTRUSTED_ENFORCEMENT_SOURCE,
                "Regulated profile requires trusted enforcement source",
            )

    base = max_operating_profile(repo_default, init_default)

    break_glass_record: BreakGlassRecord | None = None
    if break_glass_reason_code and str(break_glass_reason_code).strip():
        break_glass_record = BreakGlassRecord(
            actor=str(break_glass_actor or "").strip(),
            timestamp=str(break_glass_timestamp or break_glass_now_utc or "").strip(),
            reason_code=str(break_glass_reason_code).strip(),
            rationale=str(break_glass_rationale or "").strip(),
            scope=str(break_glass_scope or "").strip(),
            expires_at=str(break_glass_expires_at or "").strip(),
            approval_context=str(break_glass_approval_context).strip() if break_glass_approval_context is not None else None,
        )
    break_glass_active, break_glass_status = validate_break_glass(break_glass_record, now_utc=break_glass_now_utc)

    resolved = max_operating_profile(base, trusted_enforcement, requested)
    if break_glass_active and requested is not None and is_downshift(base, requested):
        resolved = requested

    if requested is not None and is_downshift(base, requested) and not break_glass_active:
        raise OperatingProfileError(FORBIDDEN_DOWNSHIFT, "Requested profile downshifts below baseline")

    if floor is not None and not meets_floor(resolved, floor):
        raise OperatingProfileError(
            PROFILE_FLOOR_VIOLATION,
            f"Resolved profile {resolved} does not meet floor {floor}",
        )

    if trusted_enforcement is not None and is_downshift(trusted_enforcement, resolved):
        raise OperatingProfileError(INVALID_PROFILE_CONFLICT, "Resolved profile conflicts with enforced profile")

    resolved_repo_mode = repo_default if repo_default is not None else init_default
    resolved_init_mode = init_default if init_default is not None else repo_default
    if resolved_repo_mode is None or resolved_init_mode is None:
        raise OperatingProfileError(MISSING_OPERATING_MODE, "Repo/init defaults missing")

    return OperatingProfileResolution(
        requested_operating_mode=requested,
        repo_operating_mode=resolved_repo_mode,
        init_operating_mode=resolved_init_mode,
        enforced_operating_mode=trusted_enforcement,
        enforcement_source=trust.source,
        enforcement_trusted=trust.trusted,
        resolved_operating_mode=resolved,
        floor_operating_mode=floor,
        break_glass_active=break_glass_active,
        break_glass_status=break_glass_status,
    )
