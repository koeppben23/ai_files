"""Tests for governance.domain.access_control — Role-based access control model.

Covers: Happy / Edge / Corner / Bad paths.

Contract version under test: ACCESS_CONTROL.v1
"""

from __future__ import annotations

import pytest

from governance.domain.access_control import (
    CONTRACT_VERSION,
    Role,
    Action,
    AccessDecision,
    Permission,
    AccessEvaluation,
    PERMISSIONS,
    REGULATED_MODE_BLOCKED_ACTIONS,
    REGULATED_MODE_REQUIRED_ACTIONS,
    HUMAN_APPROVAL_REQUIRED_ACTIONS,
    evaluate_access,
    evaluate_four_eyes,
    get_role_permissions,
    get_action_roles,
)


# ===================================================================
# Happy path
# ===================================================================

class TestEvaluateAccessHappy:
    """Happy: allowed operations return ALLOW."""

    def test_operator_can_read_archive(self):
        result = evaluate_access(role=Role.OPERATOR, action=Action.READ_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_operator_can_export_archive(self):
        result = evaluate_access(role=Role.OPERATOR, action=Action.EXPORT_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_operator_can_verify(self):
        result = evaluate_access(role=Role.OPERATOR, action=Action.VERIFY_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_auditor_can_read_archive(self):
        result = evaluate_access(role=Role.AUDITOR, action=Action.READ_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_auditor_can_verify(self):
        result = evaluate_access(role=Role.AUDITOR, action=Action.VERIFY_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_auditor_can_export_redacted(self):
        result = evaluate_access(role=Role.AUDITOR, action=Action.EXPORT_REDACTED)
        assert result.decision == AccessDecision.ALLOW

    def test_reviewer_can_verify(self):
        result = evaluate_access(role=Role.REVIEWER, action=Action.VERIFY_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_approver_can_approve_human_gate(self):
        result = evaluate_access(role=Role.APPROVER, action=Action.APPROVE_HUMAN_GATE, regulated_mode_active=True)
        assert result.decision == AccessDecision.ALLOW

    def test_admin_can_invalidate_run(self):
        result = evaluate_access(role=Role.ADMIN, action=Action.INVALIDATE_RUN)
        assert result.decision == AccessDecision.ALLOW

    def test_compliance_officer_can_read(self):
        result = evaluate_access(role=Role.COMPLIANCE_OFFICER,
                                 action=Action.READ_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_compliance_officer_modify_retention_in_regulated(self):
        """modify_retention requires regulated mode — should ALLOW when active."""
        result = evaluate_access(
            role=Role.COMPLIANCE_OFFICER,
            action=Action.MODIFY_RETENTION,
            regulated_mode_active=True,
        )
        assert result.decision == AccessDecision.ALLOW

    def test_compliance_officer_override_redaction_in_regulated(self):
        result = evaluate_access(
            role=Role.COMPLIANCE_OFFICER,
            action=Action.OVERRIDE_REDACTION,
            regulated_mode_active=True,
        )
        assert result.decision == AccessDecision.ALLOW

    def test_system_can_read_archive(self):
        result = evaluate_access(role=Role.SYSTEM, action=Action.READ_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_system_can_export(self):
        result = evaluate_access(role=Role.SYSTEM, action=Action.EXPORT_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_readonly_can_read(self):
        result = evaluate_access(role=Role.READONLY, action=Action.READ_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_readonly_can_verify(self):
        result = evaluate_access(role=Role.READONLY, action=Action.VERIFY_ARCHIVE)
        assert result.decision == AccessDecision.ALLOW

    def test_evaluation_result_has_correct_fields(self):
        result = evaluate_access(role=Role.OPERATOR, action=Action.READ_ARCHIVE)
        assert result.role == Role.OPERATOR
        assert result.action == Action.READ_ARCHIVE
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


class TestRegulatedModeBlockedHappy:
    """Happy: regulated mode correctly blocks actions."""

    def test_operator_purge_blocked_in_regulated(self):
        result = evaluate_access(
            role=Role.OPERATOR,
            action=Action.PURGE_ARCHIVE,
            regulated_mode_active=True,
        )
        assert result.decision == AccessDecision.DENY
        assert result.regulated_mode_active is True

    def test_operator_purge_allowed_outside_regulated(self):
        result = evaluate_access(
            role=Role.OPERATOR,
            action=Action.PURGE_ARCHIVE,
            regulated_mode_active=False,
        )
        assert result.decision == AccessDecision.ALLOW


class TestRegulatedModeRequiredHappy:
    """Happy: actions requiring regulated mode are denied without it."""

    def test_modify_retention_denied_without_regulated(self):
        result = evaluate_access(
            role=Role.COMPLIANCE_OFFICER,
            action=Action.MODIFY_RETENTION,
            regulated_mode_active=False,
        )
        assert result.decision == AccessDecision.DENY

    def test_override_redaction_denied_without_regulated(self):
        result = evaluate_access(
            role=Role.COMPLIANCE_OFFICER,
            action=Action.OVERRIDE_REDACTION,
            regulated_mode_active=False,
        )
        assert result.decision == AccessDecision.DENY


class TestGetRolePermissionsHappy:
    """Happy: role permission queries return correct sets."""

    def test_operator_has_multiple_permissions(self):
        perms = get_role_permissions(Role.OPERATOR)
        assert len(perms) >= 5
        actions = {p.action for p in perms}
        assert Action.READ_ARCHIVE in actions
        assert Action.VERIFY_ARCHIVE in actions

    def test_readonly_has_limited_permissions(self):
        perms = get_role_permissions(Role.READONLY)
        actions = {p.action for p in perms}
        assert Action.PURGE_ARCHIVE not in actions
        assert Action.EXPORT_ARCHIVE not in actions

    def test_auditor_cannot_purge(self):
        perms = get_role_permissions(Role.AUDITOR)
        actions = {p.action for p in perms}
        assert Action.PURGE_ARCHIVE not in actions


class TestGetActionRolesHappy:
    """Happy: action role queries return correct sets."""

    def test_read_archive_available_to_all_roles(self):
        roles = get_action_roles(Action.READ_ARCHIVE)
        assert Role.OPERATOR in roles
        assert Role.AUDITOR in roles
        assert Role.COMPLIANCE_OFFICER in roles
        assert Role.SYSTEM in roles
        assert Role.READONLY in roles

    def test_purge_only_operator(self):
        roles = get_action_roles(Action.PURGE_ARCHIVE)
        assert Role.OPERATOR in roles
        assert Role.ADMIN in roles
        assert Role.AUDITOR not in roles
        assert Role.READONLY not in roles

    def test_override_redaction_only_compliance_officer(self):
        roles = get_action_roles(Action.OVERRIDE_REDACTION)
        assert Role.COMPLIANCE_OFFICER in roles
        assert Role.ADMIN in roles


# ===================================================================
# Edge cases
# ===================================================================

class TestEvaluateAccessEdge:
    """Edge: boundary conditions on access evaluation."""

    def test_regulated_mode_flag_propagated(self):
        result = evaluate_access(
            role=Role.OPERATOR, action=Action.READ_ARCHIVE,
            regulated_mode_active=True,
        )
        assert result.regulated_mode_active is True

    def test_non_regulated_flag_propagated(self):
        result = evaluate_access(
            role=Role.OPERATOR, action=Action.READ_ARCHIVE,
            regulated_mode_active=False,
        )
        assert result.regulated_mode_active is False

    def test_system_role_not_blocked_in_regulated(self):
        """System operations should not be blocked by regulated mode."""
        result = evaluate_access(
            role=Role.SYSTEM, action=Action.VERIFY_ARCHIVE,
            regulated_mode_active=True,
        )
        assert result.decision == AccessDecision.ALLOW

    def test_export_requires_four_eyes_in_regulated_mode(self):
        result = evaluate_access(
            role=Role.OPERATOR,
            action=Action.EXPORT_ARCHIVE,
            regulated_mode_active=True,
        )
        assert result.decision == AccessDecision.DENY
        assert result.requires_human_approval is True
        assert result.approval_satisfied is False

    def test_export_allows_when_independent_approver_present(self):
        result = evaluate_access(
            role=Role.OPERATOR,
            action=Action.EXPORT_ARCHIVE,
            regulated_mode_active=True,
            approver_role=Role.APPROVER,
        )
        assert result.decision == AccessDecision.ALLOW
        assert result.requires_human_approval is True
        assert result.approval_satisfied is True

    def test_export_denied_when_approver_same_as_initiator(self):
        result = evaluate_access(
            role=Role.OPERATOR,
            action=Action.EXPORT_ARCHIVE,
            regulated_mode_active=True,
            approver_role=Role.OPERATOR,
        )
        assert result.decision == AccessDecision.DENY
        assert "four-eyes" in result.approval_reason


class TestPermissionTableEdge:
    """Edge: permission table consistency."""

    def test_all_permission_keys_follow_format(self):
        for key in PERMISSIONS:
            parts = key.split(":")
            assert len(parts) == 2, f"Key {key} should have exactly one colon"

    def test_permission_key_matches_role_action(self):
        for key, perm in PERMISSIONS.items():
            expected_key = f"{perm.role.value}:{perm.action.value}"
            assert key == expected_key

    def test_no_duplicate_permissions(self):
        """Each role:action pair should appear at most once."""
        keys = list(PERMISSIONS.keys())
        assert len(keys) == len(set(keys))


# ===================================================================
# Corner cases
# ===================================================================

class TestEvaluateAccessCorner:
    """Corner: unusual but valid combinations."""

    def test_all_role_action_combinations_dont_crash(self):
        """Exhaustive: every role × action combination should return a valid result."""
        for role in Role:
            for action in Action:
                for regulated in (True, False):
                    result = evaluate_access(
                        role=role, action=action,
                        regulated_mode_active=regulated,
                    )
                    assert isinstance(result, AccessEvaluation)
                    assert result.decision in (AccessDecision.ALLOW, AccessDecision.DENY)

    def test_evaluation_is_frozen(self):
        result = evaluate_access(role=Role.OPERATOR, action=Action.READ_ARCHIVE)
        with pytest.raises(AttributeError):
            result.decision = AccessDecision.DENY  # type: ignore[misc]


# ===================================================================
# Bad paths — Fail-closed
# ===================================================================

class TestFailClosedDeny:
    """Bad: undefined role-action combos are denied (fail-closed)."""

    def test_readonly_purge_denied(self):
        result = evaluate_access(role=Role.READONLY, action=Action.PURGE_ARCHIVE)
        assert result.decision == AccessDecision.DENY

    def test_readonly_export_archive_denied(self):
        result = evaluate_access(role=Role.READONLY, action=Action.EXPORT_ARCHIVE)
        assert result.decision == AccessDecision.DENY

    def test_auditor_purge_denied(self):
        result = evaluate_access(role=Role.AUDITOR, action=Action.PURGE_ARCHIVE)
        assert result.decision == AccessDecision.DENY

    def test_auditor_modify_retention_denied(self):
        result = evaluate_access(role=Role.AUDITOR, action=Action.MODIFY_RETENTION)
        assert result.decision == AccessDecision.DENY

    def test_system_purge_denied(self):
        result = evaluate_access(role=Role.SYSTEM, action=Action.PURGE_ARCHIVE)
        assert result.decision == AccessDecision.DENY

    def test_operator_override_redaction_denied(self):
        result = evaluate_access(role=Role.OPERATOR, action=Action.OVERRIDE_REDACTION)
        assert result.decision == AccessDecision.DENY

    def test_operator_modify_retention_denied(self):
        result = evaluate_access(role=Role.OPERATOR, action=Action.MODIFY_RETENTION)
        assert result.decision == AccessDecision.DENY

    def test_denied_reason_is_meaningful(self):
        result = evaluate_access(role=Role.READONLY, action=Action.PURGE_ARCHIVE)
        assert "No permission defined" in result.reason


# ===================================================================
# Contract invariants
# ===================================================================

class TestAccessControlInvariants:
    """Contract-level invariants."""

    def test_contract_version(self):
        assert CONTRACT_VERSION == "ACCESS_CONTROL.v1"

    def test_every_role_has_at_least_one_permission(self):
        for role in Role:
            perms = get_role_permissions(role)
            assert len(perms) > 0, f"Role {role.value} has zero permissions"

    def test_read_archive_is_universal(self):
        """Every role must be able to read archives."""
        for role in Role:
            result = evaluate_access(role=role, action=Action.READ_ARCHIVE)
            assert result.decision == AccessDecision.ALLOW, (
                f"Role {role.value} cannot read archives"
            )

    def test_blocked_and_required_sets_disjoint(self):
        """No action can be both blocked and required in regulated mode."""
        overlap = REGULATED_MODE_BLOCKED_ACTIONS & REGULATED_MODE_REQUIRED_ACTIONS
        assert len(overlap) == 0, f"Overlap: {overlap}"

    def test_regulated_blocked_actions_exist_in_permissions(self):
        for key in REGULATED_MODE_BLOCKED_ACTIONS:
            assert key in PERMISSIONS, f"Blocked action {key} not in PERMISSIONS"

    def test_regulated_required_actions_exist_in_permissions(self):
        for key in REGULATED_MODE_REQUIRED_ACTIONS:
            assert key in PERMISSIONS, f"Required action {key} not in PERMISSIONS"

    def test_human_approval_actions_non_empty(self):
        assert len(HUMAN_APPROVAL_REQUIRED_ACTIONS) >= 1

    def test_four_eyes_helper_requires_independent_approver(self):
        ok, _ = evaluate_four_eyes(
            initiator_role=Role.OPERATOR,
            approver_role=Role.OPERATOR,
            action=Action.EXPORT_ARCHIVE,
            regulated_mode_active=True,
        )
        assert ok is False
