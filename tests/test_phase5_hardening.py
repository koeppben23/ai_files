"""Phase 5 review-gate hardening tests.

Guards the two behavioral fixes:
  Bug 1: Phase 5 allowed implementation-intent language.
  Bug 2: Phase 5 had no mandatory self-review before presenting a plan.

Test coverage: SSOT-first, Happy, Bad, Edge, Corner cases across 5 groups.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from tests.util import REPO_ROOT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PHASE_API_PATH = REPO_ROOT / "phase_api.yaml"


def _load_phase_api() -> dict[str, Any]:
    assert yaml is not None, "PyYAML is required for these tests"
    raw = PHASE_API_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    assert isinstance(data, dict), "phase_api.yaml must be a mapping"
    return data


def _find_phase_entry(token: str) -> dict[str, Any]:
    data = _load_phase_api()
    for entry in data.get("phases", []):
        if str(entry.get("token", "")).strip() == token:
            return entry
    pytest.fail(f"phase_api.yaml has no entry for token '{token}'")


def _read(relpath: str) -> str:
    p = REPO_ROOT / relpath
    assert p.exists(), f"Expected file not found: {relpath}"
    return p.read_text(encoding="utf-8")


# ===================================================================
# Group 1: SSOT — phase_api.yaml has output_policy on token "5"
# ===================================================================


class TestSSOTOutputPolicyExists:
    """phase_api.yaml token '5' must define output_policy."""

    def test_token_5_has_output_policy(self) -> None:
        entry = _find_phase_entry("5")
        assert "output_policy" in entry, (
            "phase_api.yaml token '5' must define output_policy block"
        )
        assert isinstance(entry["output_policy"], dict)

    def test_output_policy_has_allowed_classes(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "allowed_output_classes" in policy
        assert isinstance(policy["allowed_output_classes"], list)
        assert len(policy["allowed_output_classes"]) > 0

    def test_output_policy_has_forbidden_classes(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "forbidden_output_classes" in policy
        assert isinstance(policy["forbidden_output_classes"], list)
        assert len(policy["forbidden_output_classes"]) > 0

    def test_forbidden_contains_implementation(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        forbidden = policy["forbidden_output_classes"]
        assert "implementation" in forbidden, (
            "output_policy.forbidden_output_classes must include 'implementation'"
        )

    def test_forbidden_contains_patch(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "patch" in policy["forbidden_output_classes"]

    def test_forbidden_contains_diff(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "diff" in policy["forbidden_output_classes"]

    def test_forbidden_contains_code_delivery(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "code_delivery" in policy["forbidden_output_classes"]

    def test_plan_discipline_exists(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "plan_discipline" in policy
        pd = policy["plan_discipline"]
        assert isinstance(pd, dict)

    def test_min_self_review_iterations_at_least_1(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        pd = policy["plan_discipline"]
        assert pd.get("min_self_review_iterations", 0) >= 1, (
            "plan_discipline.min_self_review_iterations must be >= 1"
        )


# ===================================================================
# Group 2: Doc consistency — master.md/review.md reference the rules
# ===================================================================


class TestDocConsistencyHappy:
    """master.md and review.md must reference Rule A/B and phase_api.yaml."""

    def test_master_md_rule_a_present(self) -> None:
        content = _read("master.md")
        assert "Rule A" in content, (
            "master.md must define 'Rule A' for implementation-intent prohibition"
        )
        assert "implementation-intent" in content.lower() or "implementation" in content.lower()

    def test_master_md_rule_b_present(self) -> None:
        content = _read("master.md")
        assert "Rule B" in content, (
            "master.md must define 'Rule B' for plan self-review requirement"
        )
        assert "self-review" in content.lower()

    def test_master_md_references_phase_api_output_policy(self) -> None:
        content = _read("master.md")
        assert "output_policy" in content, (
            "master.md must reference phase_api.yaml output_policy"
        )

    def test_review_md_references_output_policy(self) -> None:
        content = _read("review.md")
        assert "output_policy" in content or "Rule A" in content, (
            "review.md must reference output_policy or Rule A/B"
        )

    def test_review_md_no_full_policy_duplication(self) -> None:
        """review.md should NOT duplicate the full allowed/forbidden lists."""
        content = _read("review.md")
        # Should NOT enumerate all 8 allowed classes
        assert "consolidated_review_plan" not in content, (
            "review.md must not duplicate the full allowed_output_classes list — "
            "it should reference phase_api.yaml instead"
        )


# ===================================================================
# Group 3: Runtime enforcement — build_strict_response rejects/allows
# ===================================================================


class TestRuntimeEnforcementHappy:
    """build_strict_response rejects forbidden output classes in Phase 5."""

    def _make_session_state(self, phase: str) -> dict[str, object]:
        return {
            "phase": phase,
            "effective_operating_mode": "ARCHITECT",
            "activation_hash": "abc123deadbeef" * 4,
            "repo_fingerprint": "test-repo",
        }

    def _make_kwargs(self, phase: str, requested_action: str | None = None) -> dict[str, Any]:
        from governance.engine.response_contract import NextAction, Snapshot
        return {
            "status": "OK",
            "session_state": self._make_session_state(phase),
            "next_action": NextAction(type="command", command="review architecture plan"),
            "snapshot": Snapshot(confidence="high", risk="low", scope="architecture"),
            "reason_payload": {"reason_code": "none"},
            "requested_action": requested_action,
        }

    def test_phase5_rejects_implementation(self) -> None:
        from governance.engine.response_contract import build_strict_response
        from governance.domain.phase_state_machine import clear_phase_output_policy_cache
        clear_phase_output_policy_cache()
        kwargs = self._make_kwargs("5-ArchitectureReview", requested_action="implement the feature")
        with pytest.raises(ValueError, match="forbidden"):
            build_strict_response(**kwargs)

    def test_phase5_rejects_code_delivery(self) -> None:
        from governance.engine.response_contract import build_strict_response
        from governance.domain.phase_state_machine import clear_phase_output_policy_cache
        clear_phase_output_policy_cache()
        kwargs = self._make_kwargs("5-ArchitectureReview", requested_action="deliver code to user")
        with pytest.raises(ValueError, match="forbidden"):
            build_strict_response(**kwargs)

    def test_phase5_allows_review(self) -> None:
        from governance.engine.response_contract import build_strict_response
        from governance.domain.phase_state_machine import clear_phase_output_policy_cache
        clear_phase_output_policy_cache()
        kwargs = self._make_kwargs("5-ArchitectureReview", requested_action="review architecture plan")
        # Should not raise
        result = build_strict_response(**kwargs)
        assert result["mode"] == "STRICT"

    def test_phase5_allows_plan(self) -> None:
        from governance.engine.response_contract import build_strict_response
        from governance.domain.phase_state_machine import clear_phase_output_policy_cache
        clear_phase_output_policy_cache()
        kwargs = self._make_kwargs("5-ArchitectureReview", requested_action="plan the architecture approach")
        result = build_strict_response(**kwargs)
        assert result["mode"] == "STRICT"


# ===================================================================
# Group 4: Allowed outputs — plan, risk, test_strategy, gate_check
# ===================================================================


class TestAllowedOutputsHappy:
    """Phase 5 must allow all review-phase output classes."""

    def test_allowed_includes_plan(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "plan" in policy["allowed_output_classes"]

    def test_allowed_includes_risk_analysis(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "risk_analysis" in policy["allowed_output_classes"]

    def test_allowed_includes_test_strategy(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "test_strategy" in policy["allowed_output_classes"]

    def test_allowed_includes_gate_check(self) -> None:
        policy = _find_phase_entry("5")["output_policy"]
        assert "gate_check" in policy["allowed_output_classes"]


# ===================================================================
# Group 5: Phase 6 transition — restrictions only apply to Phase 5
# ===================================================================


class TestPhase6TransitionHappy:
    """Implementation must be allowed after Phase 6 transition."""

    def test_phase6_no_output_policy(self) -> None:
        """Token '6' must NOT have output_policy (no restrictions)."""
        entry = _find_phase_entry("6")
        assert "output_policy" not in entry, (
            "phase_api.yaml token '6' must NOT define output_policy — "
            "implementation is allowed after Phase 5 gates pass"
        )

    def test_phase5_subtokens_inherit_policy(self) -> None:
        """5.* sub-tokens inherit output_policy from token '5'."""
        from governance.domain.phase_state_machine import (
            resolve_phase_output_policy,
            clear_phase_output_policy_cache,
        )
        clear_phase_output_policy_cache()
        policy = resolve_phase_output_policy("5.3")
        assert policy is not None, "5.3 must inherit output_policy from token '5'"
        assert "implementation" in policy.forbidden_output_classes

    def test_phase4_no_output_policy(self) -> None:
        """Token '4' must NOT have output_policy (different gating)."""
        from governance.domain.phase_state_machine import (
            resolve_phase_output_policy,
            clear_phase_output_policy_cache,
        )
        clear_phase_output_policy_cache()
        policy = resolve_phase_output_policy("4")
        assert policy is None, (
            "Token '4' should not have output_policy — "
            "Phase 4 uses different gating (ticket input)"
        )


# ===================================================================
# Additional: classify_output_class coverage
# ===================================================================


class TestClassifyOutputClass:
    """Verify structural classification of requested actions."""

    def test_implement_classified_as_implementation(self) -> None:
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("implement the feature") == "implementation"

    def test_review_classified_as_review(self) -> None:
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("review architecture") == "review"

    def test_plan_classified_as_plan(self) -> None:
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("plan the approach") == "plan"

    def test_patch_classified_as_patch(self) -> None:
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("apply patch to module") == "patch"

    def test_diff_classified_as_diff(self) -> None:
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("generate diff for changes") == "diff"

    def test_risk_classified_as_risk_analysis(self) -> None:
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("risk analysis of migration") == "risk_analysis"

    def test_empty_defaults_to_safe_review_class(self) -> None:
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("") == "review"
        assert classify_output_class(None) == "review"

    def test_unrecognized_action_fails_closed(self) -> None:
        """Unrecognized actions must fail-closed to 'implementation'."""
        from governance.application.use_cases.target_path_helpers import classify_output_class
        assert classify_output_class("xyzzy frobulate the thing") == "implementation"
