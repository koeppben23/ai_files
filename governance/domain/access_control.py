"""Access Control — Domain model for role-based access to audit artifacts.

Defines roles, permissions, and access evaluation for regulated audit artifacts.
Enables regulated customers to enforce who can read, export, or purge audit data.

Contract version: ACCESS_CONTROL.v1

Design:
    - Frozen dataclasses for immutable role/permission records
    - Pure functions for access evaluation (no I/O)
    - Fail-closed: unknown roles/actions are denied
    - Zero external dependencies (stdlib only)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "ACCESS_CONTROL.v1"


class Role(Enum):
    """Roles that can interact with the governance audit system."""
    OPERATOR = "operator"
    AUDITOR = "auditor"
    COMPLIANCE_OFFICER = "compliance_officer"
    SYSTEM = "system"
    READONLY = "readonly"


class Action(Enum):
    """Actions that can be performed on audit artifacts."""
    READ_ARCHIVE = "read_archive"
    EXPORT_ARCHIVE = "export_archive"
    VERIFY_ARCHIVE = "verify_archive"
    PURGE_ARCHIVE = "purge_archive"
    READ_FAILURE_REPORT = "read_failure_report"
    EXPORT_REDACTED = "export_redacted"
    MODIFY_RETENTION = "modify_retention"
    VIEW_CLASSIFICATION = "view_classification"
    OVERRIDE_REDACTION = "override_redaction"


class AccessDecision(Enum):
    """Result of an access evaluation."""
    ALLOW = "allow"
    DENY = "deny"


# ---------------------------------------------------------------------------
# Permission model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Permission:
    """A single permission: role + action + optional constraints."""
    role: Role
    action: Action
    requires_regulated_mode: bool = False
    requires_audit_log: bool = True
    description: str = ""


@dataclass(frozen=True)
class AccessEvaluation:
    """Result of evaluating an access request."""
    decision: AccessDecision
    role: Role
    action: Action
    reason: str
    regulated_mode_active: bool = False


# ---------------------------------------------------------------------------
# Permission table — SSOT
# ---------------------------------------------------------------------------

#: Master permission table defining all allowed role-action combinations
PERMISSIONS: Mapping[str, Permission] = {
    # Operator — full access in non-regulated mode, restricted in regulated mode
    "operator:read_archive": Permission(
        role=Role.OPERATOR, action=Action.READ_ARCHIVE,
        description="Operator can read raw archive data",
    ),
    "operator:export_archive": Permission(
        role=Role.OPERATOR, action=Action.EXPORT_ARCHIVE,
        description="Operator can export full archives",
    ),
    "operator:verify_archive": Permission(
        role=Role.OPERATOR, action=Action.VERIFY_ARCHIVE,
        description="Operator can run integrity verification",
    ),
    "operator:purge_archive": Permission(
        role=Role.OPERATOR, action=Action.PURGE_ARCHIVE,
        requires_regulated_mode=False,
        description="Operator can purge archives (blocked in regulated mode)",
    ),
    "operator:read_failure_report": Permission(
        role=Role.OPERATOR, action=Action.READ_FAILURE_REPORT,
        description="Operator can read failure reports",
    ),
    "operator:export_redacted": Permission(
        role=Role.OPERATOR, action=Action.EXPORT_REDACTED,
        description="Operator can export redacted archives",
    ),
    "operator:view_classification": Permission(
        role=Role.OPERATOR, action=Action.VIEW_CLASSIFICATION,
        description="Operator can view field classifications",
    ),

    # Auditor — read + verify + export (redacted)
    "auditor:read_archive": Permission(
        role=Role.AUDITOR, action=Action.READ_ARCHIVE,
        description="Auditor can read archive data",
    ),
    "auditor:verify_archive": Permission(
        role=Role.AUDITOR, action=Action.VERIFY_ARCHIVE,
        description="Auditor can verify archive integrity",
    ),
    "auditor:export_redacted": Permission(
        role=Role.AUDITOR, action=Action.EXPORT_REDACTED,
        description="Auditor can export redacted archives",
    ),
    "auditor:read_failure_report": Permission(
        role=Role.AUDITOR, action=Action.READ_FAILURE_REPORT,
        description="Auditor can read failure reports",
    ),
    "auditor:view_classification": Permission(
        role=Role.AUDITOR, action=Action.VIEW_CLASSIFICATION,
        description="Auditor can view field classifications",
    ),

    # Compliance Officer — full read + export + retention management
    "compliance_officer:read_archive": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.READ_ARCHIVE,
        description="Compliance officer can read archive data",
    ),
    "compliance_officer:export_archive": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.EXPORT_ARCHIVE,
        description="Compliance officer can export full archives",
    ),
    "compliance_officer:verify_archive": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.VERIFY_ARCHIVE,
        description="Compliance officer can verify integrity",
    ),
    "compliance_officer:export_redacted": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.EXPORT_REDACTED,
        description="Compliance officer can export redacted archives",
    ),
    "compliance_officer:read_failure_report": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.READ_FAILURE_REPORT,
        description="Compliance officer can read failure reports",
    ),
    "compliance_officer:modify_retention": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.MODIFY_RETENTION,
        requires_regulated_mode=True,
        description="Compliance officer can modify retention policies",
    ),
    "compliance_officer:view_classification": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.VIEW_CLASSIFICATION,
        description="Compliance officer can view field classifications",
    ),
    "compliance_officer:override_redaction": Permission(
        role=Role.COMPLIANCE_OFFICER, action=Action.OVERRIDE_REDACTION,
        requires_regulated_mode=True, requires_audit_log=True,
        description="Compliance officer can override redaction (audit-logged)",
    ),

    # System — automated operations
    "system:read_archive": Permission(
        role=Role.SYSTEM, action=Action.READ_ARCHIVE,
        description="System can read archives for automated processing",
    ),
    "system:verify_archive": Permission(
        role=Role.SYSTEM, action=Action.VERIFY_ARCHIVE,
        description="System can verify archives",
    ),
    "system:export_archive": Permission(
        role=Role.SYSTEM, action=Action.EXPORT_ARCHIVE,
        description="System can export archives for automated pipelines",
    ),

    # Readonly — limited read access
    "readonly:read_archive": Permission(
        role=Role.READONLY, action=Action.READ_ARCHIVE,
        description="Readonly user can view archive metadata",
    ),
    "readonly:verify_archive": Permission(
        role=Role.READONLY, action=Action.VERIFY_ARCHIVE,
        description="Readonly user can verify archive integrity",
    ),
    "readonly:view_classification": Permission(
        role=Role.READONLY, action=Action.VIEW_CLASSIFICATION,
        description="Readonly user can view field classifications",
    ),
}


# ---------------------------------------------------------------------------
# Actions blocked in regulated mode
# ---------------------------------------------------------------------------

#: Actions that are forbidden when regulated mode is active
REGULATED_MODE_BLOCKED_ACTIONS: FrozenSet[str] = frozenset({
    "operator:purge_archive",
})

#: Actions that require regulated mode to be active
REGULATED_MODE_REQUIRED_ACTIONS: FrozenSet[str] = frozenset({
    "compliance_officer:modify_retention",
    "compliance_officer:override_redaction",
})


# ---------------------------------------------------------------------------
# Pure evaluation functions
# ---------------------------------------------------------------------------

def evaluate_access(
    *,
    role: Role,
    action: Action,
    regulated_mode_active: bool = False,
) -> AccessEvaluation:
    """Evaluate whether a role is allowed to perform an action.

    Fail-closed: unknown role-action combinations are denied.

    Args:
        role: The role requesting access
        action: The action being attempted
        regulated_mode_active: Whether regulated mode is currently active

    Returns:
        AccessEvaluation with decision, reason, and context.
    """
    key = f"{role.value}:{action.value}"

    permission = PERMISSIONS.get(key)
    if permission is None:
        return AccessEvaluation(
            decision=AccessDecision.DENY,
            role=role,
            action=action,
            reason=f"No permission defined for {key}",
            regulated_mode_active=regulated_mode_active,
        )

    # Check regulated-mode-blocked actions
    if regulated_mode_active and key in REGULATED_MODE_BLOCKED_ACTIONS:
        return AccessEvaluation(
            decision=AccessDecision.DENY,
            role=role,
            action=action,
            reason=f"Action {action.value} blocked in regulated mode for {role.value}",
            regulated_mode_active=regulated_mode_active,
        )

    # Check regulated-mode-required actions
    if key in REGULATED_MODE_REQUIRED_ACTIONS and not regulated_mode_active:
        return AccessEvaluation(
            decision=AccessDecision.DENY,
            role=role,
            action=action,
            reason=f"Action {action.value} requires regulated mode for {role.value}",
            regulated_mode_active=regulated_mode_active,
        )

    return AccessEvaluation(
        decision=AccessDecision.ALLOW,
        role=role,
        action=action,
        reason=f"Allowed by permission {key}",
        regulated_mode_active=regulated_mode_active,
    )


def get_role_permissions(role: Role) -> list[Permission]:
    """Get all permissions for a given role."""
    return [p for p in PERMISSIONS.values() if p.role == role]


def get_action_roles(action: Action) -> list[Role]:
    """Get all roles that have a given permission."""
    return [p.role for p in PERMISSIONS.values() if p.action == action]


__all__ = [
    "CONTRACT_VERSION",
    "Role",
    "Action",
    "AccessDecision",
    "Permission",
    "AccessEvaluation",
    "PERMISSIONS",
    "REGULATED_MODE_BLOCKED_ACTIONS",
    "REGULATED_MODE_REQUIRED_ACTIONS",
    "evaluate_access",
    "get_role_permissions",
    "get_action_roles",
]
