"""Embedded reason-code -> schema registry snapshot.

This baseline allows strict schema validation in PY-only deployments where
diagnostics assets may not be mounted as sibling files.
"""

from __future__ import annotations

from typing import Final


EMBEDDED_REASON_CODE_TO_SCHEMA_REF: Final[dict[str, str]] = {
    "REPO-DOC-UNSAFE-DIRECTIVE": "diagnostics/schemas/reason_payload_repo_doc_unsafe.v1.json",
    "REPO-CONSTRAINT-WIDENING": "diagnostics/schemas/reason_payload_repo_constraint_widening.v1.json",
    "INTERACTIVE-REQUIRED-IN-PIPELINE": "diagnostics/schemas/reason_payload_interactive_pipeline.v1.json",
    "PROMPT-BUDGET-EXCEEDED": "diagnostics/schemas/reason_payload_prompt_budget.v1.json",
    "REPO-CONSTRAINT-UNSUPPORTED": "diagnostics/schemas/reason_payload_repo_constraint_unsupported.v1.json",
    "POLICY-PRECEDENCE-APPLIED": "diagnostics/schemas/reason_payload_policy_precedence.v1.json",
}
