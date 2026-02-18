"""Embedded reason-code -> schema registry snapshot.

This baseline allows strict schema validation in PY-only deployments where
diagnostics assets may not be mounted as sibling files.
"""

from __future__ import annotations

from typing import Final


EMBEDDED_REASON_CODE_TO_SCHEMA_REF: Final[dict[str, str]] = {
    "BLOCKED-MISSING-BINDING-FILE": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-VARIABLE-RESOLUTION": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-WORKSPACE-PERSISTENCE": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-ENGINE-SELFCHECK": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-REPO-IDENTITY-RESOLUTION": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-SYSTEM-MODE-REQUIRED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-OPERATING-MODE-REQUIRED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-STATE-OUTDATED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-PACK-LOCK-REQUIRED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-PACK-LOCK-INVALID": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-PACK-LOCK-MISMATCH": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-SURFACE-CONFLICT": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-RULESET-HASH-MISMATCH": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-ACTIVATION-HASH-MISMATCH": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-RELEASE-HYGIENE": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-SESSION-STATE-LEGACY-UNSUPPORTED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-UNSPECIFIED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-PERSISTENCE-TARGET-DEGENERATE": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-PERSISTENCE-PATH-VIOLATION": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-INSTALL-PRECHECK-MISSING-SOURCE": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-INSTALL-VERSION-MISSING": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-INSTALL-CONFIG-ROOT-INVALID": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-PERMISSION-DENIED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "BLOCKED-EXEC-DISALLOWED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "REPO-DOC-UNSAFE-DIRECTIVE": "diagnostics/schemas/reason_payload_repo_doc_unsafe.v1.json",
    "REPO-CONSTRAINT-WIDENING": "diagnostics/schemas/reason_payload_repo_constraint_widening.v1.json",
    "INTERACTIVE-REQUIRED-IN-PIPELINE": "diagnostics/schemas/reason_payload_interactive_pipeline.v1.json",
    "PROMPT-BUDGET-EXCEEDED": "diagnostics/schemas/reason_payload_prompt_budget.v1.json",
    "PERSIST_CONFIRMATION_REQUIRED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "PERSIST_CONFIRMATION_INVALID": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "PERSIST_DISALLOWED_IN_PIPELINE": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "PERSIST_PHASE_MISMATCH": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "PERSIST_GATE_NOT_APPROVED": "diagnostics/schemas/reason_payload_blocked_core.v1.json",
    "WARN-UNMAPPED-AUDIT-REASON": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "WARN-WORKSPACE-PERSISTENCE": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "WARN-ENGINE-LIVE-DENIED": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "WARN-MODE-DOWNGRADED": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "WARN-PERMISSION-LIMITED": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "WARN-SESSION-STATE-LEGACY-COMPAT-MODE": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "NOT_VERIFIED-MISSING-EVIDENCE": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "NOT_VERIFIED-EVIDENCE-STALE": "diagnostics/schemas/reason_payload_advisory.v1.json",
    "REPO-CONSTRAINT-UNSUPPORTED": "diagnostics/schemas/reason_payload_repo_constraint_unsupported.v1.json",
    "POLICY-PRECEDENCE-APPLIED": "diagnostics/schemas/reason_payload_policy_precedence.v1.json",
}
