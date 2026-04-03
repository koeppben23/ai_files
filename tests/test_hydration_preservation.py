"""Tests for hydration state preservation across bootstrap cycles.

Patch 19 — Bug 1: SessionHydration.status = "hydrated" must survive
bootstrap persistence merges and kernel continuation resets.

Two overwrite paths existed before the fix:
  Path A: _merge_final_session_state() in bootstrap_persistence.py
          did not preserve SessionHydration from existing on-disk state.
  Path B: run_kernel_continuation() in bootstrap_preflight_readonly.py
          explicitly reset SessionHydration when phase == "4" and no
          ticket/task data.

Coverage: happy path, bad path, corner cases, edge cases.
"""

from __future__ import annotations

import json

import pytest

from governance_runtime.application.use_cases.bootstrap_persistence import (
    _merge_final_session_state,
    _session_state_payload,
)


# ── Fixtures ─────────────────────────────────────────────────────────

def _make_hydrated_session_state(**overrides: object) -> dict:
    """Build a SESSION_STATE dict with hydrated SessionHydration."""
    state: dict = {
        "SESSION_STATE": {
            "phase": "4",
            "next": "5",
            "Mode": "IN_PROGRESS",
            "OutputMode": "ARCHITECT",
            "RepoFingerprint": "abc123",
            "session_hydrated": True,
            "SessionHydration": {
                "hydrated_session_id": "sess-42",
                "hydrated_at": "2026-04-01T12:00:00Z",
                "digest": "sha256:aaa",
                "artifact_digest": "sha256:bbb",
                "status": "hydrated",
            },
            "Bootstrap": {"Present": True, "Satisfied": True, "Evidence": "done"},
            "ActivationIntent": {},
            "Intent": {},
            "writePolicy": {"mode": "user", "reasons": []},
            "CommitFlags": {},
        }
    }
    state["SESSION_STATE"].update(overrides)
    return state


def _make_not_hydrated_session_state(**overrides: object) -> dict:
    """Build a SESSION_STATE dict with not_hydrated SessionHydration."""
    state: dict = {
        "SESSION_STATE": {
            "phase": "1.2-ActivationIntent",
            "next": "1.3",
            "Mode": "IN_PROGRESS",
            "OutputMode": "ARCHITECT",
            "RepoFingerprint": "abc123",
            "session_hydrated": False,
            "SessionHydration": {
                "status": "not_hydrated",
                "source": "bootstrap-persistence",
            },
            "Bootstrap": {"Present": True, "Satisfied": True, "Evidence": "done"},
            "ActivationIntent": {},
            "Intent": {},
            "writePolicy": {"mode": "user", "reasons": []},
            "CommitFlags": {},
        }
    }
    state["SESSION_STATE"].update(overrides)
    return state


def _fallback_state() -> dict:
    """Build a fallback state from _session_state_payload() — always not_hydrated."""
    return _session_state_payload(
        repo_fingerprint="abc123",
        repo_name="test-repo",
        persistence_committed=True,
        workspace_ready_committed=True,
        workspace_artifacts_committed=True,
        effective_mode="user",
        write_policy_reasons=(),
        created_at="2026-04-01T10:00:00Z",
        pointer_verified=True,
        activation_intent_valid=True,
        intent_path="${CONFIG_ROOT}/activation-intent.yaml",
        intent_sha256="sha256:ccc",
        intent_effective_scope="full",
    )


_MERGE_DEFAULTS = dict(
    repo_fingerprint="abc123",
    persistence_committed=True,
    workspace_ready_committed=True,
    workspace_artifacts_committed=True,
    pointer_verified=True,
    bootstrap_present=True,
    bootstrap_satisfied=True,
    bootstrap_evidence="bootstrap-completed",
    effective_mode="user",
    write_policy_reasons=(),
    activation_intent_valid=True,
    intent_path="${CONFIG_ROOT}/activation-intent.yaml",
    intent_sha256="sha256:ccc",
    intent_effective_scope="full",
)


def _merge(existing_state: dict, fallback: dict | None = None, **kw: object) -> dict:
    """Helper to call _merge_final_session_state with defaults."""
    fb = fallback or _fallback_state()
    params = dict(_MERGE_DEFAULTS)
    params.update(kw)
    return _merge_final_session_state(
        existing_text=json.dumps(existing_state),
        fallback_state=fb,
        **params,  # type: ignore[arg-type]
    )


# ── Path A: _merge_final_session_state — Happy path ─────────────────

@pytest.mark.governance
class TestMergePreservesHydratedSession:
    """When the existing on-disk state has SessionHydration.status == 'hydrated',
    the merge must preserve it intact after a bootstrap cycle."""

    def test_preserves_hydrated_status(self) -> None:
        existing = _make_hydrated_session_state()
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "hydrated"
        assert ss["session_hydrated"] is True

    def test_preserves_hydrated_session_id(self) -> None:
        existing = _make_hydrated_session_state()
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["hydrated_session_id"] == "sess-42"

    def test_preserves_hydrated_at_timestamp(self) -> None:
        existing = _make_hydrated_session_state()
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["hydrated_at"] == "2026-04-01T12:00:00Z"

    def test_preserves_digest_fields(self) -> None:
        existing = _make_hydrated_session_state()
        result = _merge(existing)
        hydration = result["SESSION_STATE"]["SessionHydration"]
        assert hydration["digest"] == "sha256:aaa"
        assert hydration["artifact_digest"] == "sha256:bbb"

    def test_hydration_survives_multiple_merges(self) -> None:
        """Simulate three consecutive bootstrap cycles."""
        state = _make_hydrated_session_state()
        for _ in range(3):
            state = _merge(state)
        ss = state["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "hydrated"
        assert ss["session_hydrated"] is True
        assert ss["SessionHydration"]["hydrated_session_id"] == "sess-42"

    def test_bootstrap_fields_still_updated_when_hydrated(self) -> None:
        """Bootstrap-owned fields (CommitFlags, writePolicy, etc.) must
        still be updated even when hydration is preserved."""
        existing = _make_hydrated_session_state()
        result = _merge(existing, persistence_committed=True, pointer_verified=True)
        ss = result["SESSION_STATE"]
        assert ss["CommitFlags"]["PersistenceCommitted"] is True
        assert ss["CommitFlags"]["PointerVerified"] is True
        assert ss["SessionHydration"]["status"] == "hydrated"

    def test_phase_and_next_updated_when_hydrated(self) -> None:
        """Phase/next are bootstrap-owned — they must update even when
        hydration is preserved."""
        existing = _make_hydrated_session_state()
        fb = _fallback_state()
        fb["SESSION_STATE"]["phase"] = "1.3-CoreRules"
        fb["SESSION_STATE"]["next"] = "2"
        result = _merge(existing, fallback=fb)
        ss = result["SESSION_STATE"]
        assert ss["phase"] == "1.3-CoreRules"
        assert ss["next"] == "2"
        # But hydration still intact
        assert ss["SessionHydration"]["status"] == "hydrated"


# ── Path A: _merge_final_session_state — Not-hydrated path ──────────

@pytest.mark.governance
class TestMergeAppliesFallbackWhenNotHydrated:
    """When the existing state has SessionHydration.status != 'hydrated',
    the merge must apply the fallback (bootstrap default)."""

    def test_fallback_applied_for_not_hydrated(self) -> None:
        existing = _make_not_hydrated_session_state()
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "not_hydrated"
        assert ss["session_hydrated"] is False

    def test_fallback_applied_when_no_session_hydration_key(self) -> None:
        """If the existing state has no SessionHydration key at all."""
        existing = _make_not_hydrated_session_state()
        del existing["SESSION_STATE"]["SessionHydration"]
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "not_hydrated"
        assert ss["session_hydrated"] is False

    def test_fallback_applied_when_session_hydration_is_not_dict(self) -> None:
        """Edge case: SessionHydration is a string or None."""
        existing = _make_not_hydrated_session_state(SessionHydration="broken")
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert isinstance(ss["SessionHydration"], dict)
        assert ss["SessionHydration"]["status"] == "not_hydrated"

    def test_fallback_applied_when_status_empty(self) -> None:
        existing = _make_not_hydrated_session_state(
            SessionHydration={"status": "", "source": "test"}
        )
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["session_hydrated"] is False

    def test_fallback_applied_when_status_none(self) -> None:
        existing = _make_not_hydrated_session_state(
            SessionHydration={"status": None, "source": "test"}
        )
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["session_hydrated"] is False


# ── Path A: Edge cases ───────────────────────────────────────────────

@pytest.mark.governance
class TestMergeEdgeCases:
    """Edge and corner cases for hydration preservation in merge."""

    def test_invalid_json_returns_fallback(self) -> None:
        """Corrupted on-disk state → returns fallback state (not_hydrated)."""
        fb = _fallback_state()
        result = _merge_final_session_state(
            existing_text="NOT-JSON",
            fallback_state=fb,
            **_MERGE_DEFAULTS,  # type: ignore[arg-type]
        )
        assert result["SESSION_STATE"]["SessionHydration"]["status"] == "not_hydrated"

    def test_missing_session_state_key_returns_fallback(self) -> None:
        """On-disk state is valid JSON but has no SESSION_STATE key."""
        fb = _fallback_state()
        result = _merge_final_session_state(
            existing_text=json.dumps({"other": "data"}),
            fallback_state=fb,
            **_MERGE_DEFAULTS,  # type: ignore[arg-type]
        )
        assert result is fb

    def test_hydrated_status_case_insensitive(self) -> None:
        """Status comparison must be case-insensitive."""
        existing = _make_hydrated_session_state()
        existing["SESSION_STATE"]["SessionHydration"]["status"] = "HYDRATED"
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["session_hydrated"] is True

    def test_hydrated_status_with_whitespace(self) -> None:
        """Status with leading/trailing whitespace still matches."""
        existing = _make_hydrated_session_state()
        existing["SESSION_STATE"]["SessionHydration"]["status"] = "  hydrated  "
        result = _merge(existing)
        ss = result["SESSION_STATE"]
        assert ss["session_hydrated"] is True

    def test_partial_hydration_status_not_preserved(self) -> None:
        """Status values like 'hydrating' or 'partial' must NOT be treated
        as hydrated — only the literal 'hydrated' is valid."""
        for bad_status in ("hydrating", "partial", "in_progress", "pending"):
            existing = _make_hydrated_session_state()
            existing["SESSION_STATE"]["SessionHydration"]["status"] = bad_status
            result = _merge(existing)
            ss = result["SESSION_STATE"]
            assert ss["session_hydrated"] is False, f"Status '{bad_status}' should not be treated as hydrated"

    def test_hydration_with_extra_fields_preserved(self) -> None:
        """If SessionHydration has extra fields (future-proofing), they
        must survive the merge."""
        existing = _make_hydrated_session_state()
        existing["SESSION_STATE"]["SessionHydration"]["project_path"] = "/repo"
        existing["SESSION_STATE"]["SessionHydration"]["custom_field"] = 42
        result = _merge(existing)
        hydration = result["SESSION_STATE"]["SessionHydration"]
        assert hydration["project_path"] == "/repo"
        assert hydration["custom_field"] == 42
        assert hydration["status"] == "hydrated"


# ── Path A: _session_state_payload always starts not_hydrated ────────

@pytest.mark.governance
class TestSessionStatePayloadDefaultHydration:
    """_session_state_payload() must always produce not_hydrated — this is
    the initial template that bootstrap writes BEFORE the merge."""

    def test_payload_default_not_hydrated(self) -> None:
        payload = _session_state_payload(
            repo_fingerprint="test123",
            repo_name="test",
            persistence_committed=False,
            workspace_ready_committed=False,
            workspace_artifacts_committed=False,
            effective_mode="user",
            write_policy_reasons=(),
            created_at="2026-04-01T00:00:00Z",
        )
        ss = payload["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "not_hydrated"
        assert ss["session_hydrated"] is False

    def test_payload_hydration_source_is_bootstrap_persistence(self) -> None:
        payload = _session_state_payload(
            repo_fingerprint="test123",
            repo_name="test",
            persistence_committed=True,
            workspace_ready_committed=True,
            workspace_artifacts_committed=True,
            effective_mode="user",
            write_policy_reasons=(),
            created_at="2026-04-01T00:00:00Z",
            pointer_verified=True,
            activation_intent_valid=True,
        )
        ss = payload["SESSION_STATE"]
        assert ss["SessionHydration"]["source"] == "bootstrap-persistence"


# ── Path B: run_kernel_continuation guard ────────────────────────────
# These tests target the _session_hydrated() helper and the guard logic
# in run_kernel_continuation().  The actual run_kernel_continuation() is
# hard to test in isolation (requires full kernel context), so we test
# the helper that drives the guard decision.

@pytest.mark.governance
class TestSessionHydratedHelper:
    """Tests for _session_hydrated() from bootstrap_preflight_readonly.py
    which guards the hydration-reset block in run_kernel_continuation()."""

    def test_hydrated_returns_true(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        state = {
            "SessionHydration": {
                "status": "hydrated",
                "hydrated_session_id": "s1",
            }
        }
        assert _session_hydrated(state) is True

    def test_not_hydrated_returns_false(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        state = {
            "SessionHydration": {
                "status": "not_hydrated",
                "source": "bootstrap",
            }
        }
        assert _session_hydrated(state) is False

    def test_missing_key_returns_false(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        assert _session_hydrated({}) is False

    def test_non_dict_returns_false(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        assert _session_hydrated({"SessionHydration": "garbage"}) is False

    def test_none_status_returns_false(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        assert _session_hydrated({"SessionHydration": {"status": None}}) is False

    def test_empty_status_returns_false(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        assert _session_hydrated({"SessionHydration": {"status": ""}}) is False

    def test_case_insensitive(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        assert _session_hydrated({"SessionHydration": {"status": "HYDRATED"}}) is True
        assert _session_hydrated({"SessionHydration": {"status": "Hydrated"}}) is True

    def test_whitespace_tolerant(self) -> None:
        from governance_runtime.entrypoints.bootstrap_preflight_readonly import (
            _session_hydrated,
        )
        assert _session_hydrated({"SessionHydration": {"status": "  hydrated  "}}) is True


# ── Integration-style: full merge cycle simulating hydrate → bootstrap

@pytest.mark.governance
class TestHydrationSurvivesFullBootstrapCycle:
    """Simulate the real flow: hydration writes to SESSION_STATE, then
    bootstrap runs _merge_final_session_state, then kernel continuation
    runs.  Hydration must survive."""

    def test_hydrate_then_merge_preserves(self) -> None:
        """Step 1: hydration writes status=hydrated.
        Step 2: bootstrap merge runs.
        Result: hydration intact."""
        # Simulate what session_hydration.py writes
        on_disk = _make_hydrated_session_state()
        # Simulate what bootstrap merge does
        result = _merge(on_disk)
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "hydrated"
        assert ss["SessionHydration"]["hydrated_session_id"] == "sess-42"
        assert ss["session_hydrated"] is True

    def test_fresh_bootstrap_then_merge_stays_not_hydrated(self) -> None:
        """When no prior hydration exists, merge correctly stays not_hydrated."""
        on_disk = _make_not_hydrated_session_state()
        result = _merge(on_disk)
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "not_hydrated"
        assert ss["session_hydrated"] is False

    def test_two_sequential_merges_after_hydration(self) -> None:
        """Bootstrap runs twice after hydration — both must preserve."""
        state = _make_hydrated_session_state()
        state = _merge(state)
        state = _merge(state)
        ss = state["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "hydrated"
        assert ss["session_hydrated"] is True

    def test_hydration_preserved_even_with_different_bootstrap_params(self) -> None:
        """Bootstrap may run with different parameters (e.g. different
        effective_mode) — hydration must still survive."""
        state = _make_hydrated_session_state()
        result = _merge(
            state,
            effective_mode="admin",
            write_policy_reasons=("force-admin",),
            pointer_verified=False,
        )
        ss = result["SESSION_STATE"]
        assert ss["SessionHydration"]["status"] == "hydrated"
        assert ss["session_hydrated"] is True
        # But bootstrap-owned fields reflect new params
        assert ss["writePolicy"]["mode"] == "admin"
        assert ss["CommitFlags"]["PointerVerified"] is False
