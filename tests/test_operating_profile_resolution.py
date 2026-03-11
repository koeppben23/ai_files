from __future__ import annotations

from dataclasses import dataclass

import pytest

from governance.application.use_cases.resolve_operating_mode import resolve_effective_operating_mode
from governance.domain.operating_profile import (
    BREAK_GLASS_EXPIRED,
    FORBIDDEN_DOWNSHIFT,
    PROFILE_FLOOR_VIOLATION,
    UNTRUSTED_ENFORCEMENT_SOURCE,
    OperatingProfileError,
    derive_mode_evidence,
    runtime_mode_to_operating_profile,
    resolve_operating_profile,
)
from governance.engine.mode_repo_rules import canonicalize_operating_mode, resolve_env_operating_mode


@dataclass(frozen=True)
class _Adapter:
    env: dict[str, str]
    default_mode: str = "user"

    def environment(self) -> dict[str, str]:
        return self.env

    def default_operating_mode(self) -> str:
        return self.default_mode


@pytest.mark.governance
def test_resolve_operating_profile_applies_precedence_and_monotonicity():
    out = resolve_operating_profile(
        requested_operating_mode="team",
        repo_operating_mode="solo",
        init_operating_mode="solo",
        enforced_operating_mode="regulated",
        enforced_source="ci",
        floor_operating_mode="team",
    )
    assert out.resolved_operating_mode == "regulated"


@pytest.mark.governance
def test_resolve_operating_profile_blocks_downshift():
    with pytest.raises(OperatingProfileError) as exc:
        resolve_operating_profile(
            requested_operating_mode="solo",
            repo_operating_mode="team",
            init_operating_mode="solo",
            enforced_operating_mode=None,
            enforced_source=None,
            floor_operating_mode=None,
        )
    assert exc.value.code == FORBIDDEN_DOWNSHIFT


@pytest.mark.governance
def test_resolve_operating_profile_blocks_untrusted_enforcement_in_regulated_context():
    with pytest.raises(OperatingProfileError) as exc:
        resolve_operating_profile(
            requested_operating_mode=None,
            repo_operating_mode="regulated",
            init_operating_mode="solo",
            enforced_operating_mode="regulated",
            enforced_source="shell",
            floor_operating_mode="regulated",
        )
    assert exc.value.code == UNTRUSTED_ENFORCEMENT_SOURCE


@pytest.mark.governance
def test_resolve_operating_profile_enforces_floor():
    with pytest.raises(OperatingProfileError) as exc:
        resolve_operating_profile(
            requested_operating_mode="solo",
            repo_operating_mode="solo",
            init_operating_mode="solo",
            enforced_operating_mode=None,
            enforced_source=None,
            floor_operating_mode="team",
        )
    assert exc.value.code == PROFILE_FLOOR_VIOLATION


@pytest.mark.governance
def test_canonicalize_accepts_profile_aliases():
    assert canonicalize_operating_mode("solo") == "user"
    assert canonicalize_operating_mode("team") == "pipeline"
    assert canonicalize_operating_mode("regulated") == "pipeline"


@pytest.mark.governance
def test_resolve_env_operating_mode_prefers_operating_profile_aliases():
    out = resolve_env_operating_mode({"OPENCODE_OPERATING_PROFILE": "team", "OPENCODE_OPERATING_MODE": "user"})
    assert out == "pipeline"


@pytest.mark.governance
def test_resolve_effective_operating_mode_uses_profile_inputs_from_env():
    adapter = _Adapter(
        env={
            "OPENCODE_REPO_OPERATING_MODE": "solo",
            "OPENCODE_ENFORCE_PROFILE": "regulated",
            "OPENCODE_ENFORCE_PROFILE_SOURCE": "ci",
            "OPENCODE_PROFILE_FLOOR": "team",
        },
        default_mode="user",
    )
    assert resolve_effective_operating_mode(adapter, requested=None) == "pipeline"  # type: ignore[arg-type]


@pytest.mark.governance
def test_resolve_effective_operating_mode_keeps_explicit_legacy_request():
    adapter = _Adapter(env={"OPENCODE_ENFORCE_PROFILE": "regulated", "OPENCODE_ENFORCE_PROFILE_SOURCE": "ci"})
    assert resolve_effective_operating_mode(adapter, requested="agents_strict") == "agents_strict"  # type: ignore[arg-type]


@pytest.mark.governance
def test_runtime_mode_to_operating_profile_mapping_is_canonical():
    assert runtime_mode_to_operating_profile("user") == "solo"
    assert runtime_mode_to_operating_profile("pipeline") == "team"
    assert runtime_mode_to_operating_profile("agents_strict") == "regulated"


@pytest.mark.governance
def test_derive_mode_evidence_normalizes_and_defaults():
    effective, resolved, verify = derive_mode_evidence(
        effective_operating_mode="pipeline",
        resolved_operating_mode="",
        verify_policy_version="",
    )
    assert effective == "pipeline"
    assert resolved == "team"
    assert verify == "v1"


@pytest.mark.governance
def test_derive_mode_evidence_canonicalizes_explicit_resolved_alias():
    effective, resolved, verify = derive_mode_evidence(
        effective_operating_mode="unknown",
        resolved_operating_mode="agents_strict",
        verify_policy_version="v3",
    )
    assert effective == "unknown"
    assert resolved == "regulated"
    assert verify == "v3"


@pytest.mark.governance
def test_resolve_operating_profile_allows_temporary_break_glass_downshift():
    out = resolve_operating_profile(
        requested_operating_mode="solo",
        repo_operating_mode="team",
        init_operating_mode="team",
        enforced_operating_mode=None,
        enforced_source=None,
        floor_operating_mode=None,
        break_glass_reason_code="incident-mitigation",
        break_glass_expires_at="2999-01-01T00:00:00Z",
        break_glass_now_utc="2026-01-01T00:00:00Z",
    )
    assert out.resolved_operating_mode == "solo"


@pytest.mark.governance
def test_resolve_operating_profile_blocks_expired_break_glass_downshift():
    with pytest.raises(OperatingProfileError) as exc:
        resolve_operating_profile(
            requested_operating_mode="solo",
            repo_operating_mode="team",
            init_operating_mode="team",
            enforced_operating_mode=None,
            enforced_source=None,
            floor_operating_mode=None,
            break_glass_reason_code="incident-mitigation",
            break_glass_expires_at="2020-01-01T00:00:00Z",
            break_glass_now_utc="2026-01-01T00:00:00Z",
        )
    assert exc.value.code == BREAK_GLASS_EXPIRED


@pytest.mark.governance
def test_resolve_effective_operating_mode_blocks_ci_downshift_to_user():
    adapter = _Adapter(env={"CI": "true"}, default_mode="user")
    assert resolve_effective_operating_mode(adapter, requested="user") == "pipeline"  # type: ignore[arg-type]
