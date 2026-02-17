from __future__ import annotations

import json
from pathlib import Path

import pytest

import governance.engine.reason_payload as reason_payload
from governance.engine.reason_codes import (
    BLOCKED_EXEC_DISALLOWED,
    INTERACTIVE_REQUIRED_IN_PIPELINE,
    POLICY_PRECEDENCE_APPLIED,
    PROMPT_BUDGET_EXCEEDED,
    REPO_CONSTRAINT_UNSUPPORTED,
    REPO_CONSTRAINT_WIDENING,
    REPO_DOC_UNSAFE_DIRECTIVE,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "diagnostics" / "schemas"


def test_reason_payload_schemas_are_strict():
    schema_files = sorted(SCHEMA_DIR.glob("reason_payload_*.json"))
    assert schema_files, "expected reason payload schema files"
    for path in schema_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("additionalProperties") is False, f"schema must be strict: {path.name}"


@pytest.mark.parametrize(
    "reason_code,context",
    [
        (
            REPO_DOC_UNSAFE_DIRECTIVE,
            {
                "doc_path": "AGENTS.md",
                "doc_hash": "sha256:abc",
                "directive_excerpt": "skip tests",
                "classification_rule_id": "repo_doc_unsafe_skip_tests",
                "pointers": ["AGENTS.md:12"],
            },
        ),
        (
            REPO_CONSTRAINT_WIDENING,
            {
                "requested_widening": {"type": "write_scope", "from": "src/**", "to": ".github/**"},
                "doc_path": "AGENTS.md",
                "doc_hash": "sha256:def",
                "winner_layer": "mode_policy",
                "loser_layer": "repo_doc_constraints",
            },
        ),
        (
            REPO_CONSTRAINT_UNSUPPORTED,
            {
                "constraint_topic": "unknown_constraint",
                "doc_path": "AGENTS.md",
                "doc_hash": "sha256:ghi",
            },
        ),
        (
            PROMPT_BUDGET_EXCEEDED,
            {
                "mode": "user",
                "budget": {
                    "max_total": 3,
                    "max_repo_docs": 0,
                    "used_total": 4,
                    "used_repo_docs": 0,
                },
                "last_prompt": {"source": "governance", "topic": "WideningApproval"},
            },
        ),
        (
            POLICY_PRECEDENCE_APPLIED,
            {
                "event": "POLICY_PRECEDENCE_APPLIED",
                "reason_code": "POLICY-PRECEDENCE-APPLIED",
                "winner_layer": "mode_policy",
                "loser_layer": "repo_doc_constraints",
                "requested_action": "write_scope_widen",
                "decision": "deny",
                "refs": {
                    "policy_hash": "sha256:p",
                    "pack_hash": "sha256:k",
                    "mode_hash": "sha256:m",
                    "host_perm_hash": "sha256:h",
                    "doc_hash": "sha256:d",
                },
            },
        ),
        (
            INTERACTIVE_REQUIRED_IN_PIPELINE,
            {
                "requested_action": "widening_approval",
                "why_interactive_required": "widening_approval_required",
                "pointers": ["policy:write_scope"],
            },
        ),
    ],
)
def test_reason_context_validates_against_registered_schema(reason_code: str, context: dict[str, object]):
    assert reason_payload.validate_reason_context_schema(reason_code, context) == ()


@pytest.mark.parametrize(
    "reason_code,context",
    [
        (REPO_DOC_UNSAFE_DIRECTIVE, {"doc_path": "AGENTS.md"}),
        (PROMPT_BUDGET_EXCEEDED, {"mode": "user"}),
        (
            POLICY_PRECEDENCE_APPLIED,
            {
                "winner_layer": "mode_policy",
                "loser_layer": "repo_doc_constraints",
                "requested_action": "write_scope_widen",
                "decision": "maybe",
                "refs": {
                    "policy_hash": "sha256:p",
                    "pack_hash": "sha256:k",
                    "mode_hash": "sha256:m",
                    "host_perm_hash": "sha256:h",
                    "doc_hash": "sha256:d",
                },
            },
        ),
    ],
)
def test_reason_context_invalid_payload_fails_schema(reason_code: str, context: dict[str, object]):
    errors = reason_payload.validate_reason_context_schema(reason_code, context)
    assert errors


def test_reason_context_uses_embedded_schema_when_registry_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(reason_payload, "_REASON_REGISTRY_PATH", Path("/tmp/does-not-exist.registry.json"))
    monkeypatch.setattr(reason_payload, "_REASON_SCHEMA_REF_CACHE", None)

    errors = reason_payload.validate_reason_context_schema(
        REPO_DOC_UNSAFE_DIRECTIVE,
        {
            "doc_path": "AGENTS.md",
            "doc_hash": "sha256:abc",
            "directive_excerpt": "skip tests",
            "classification_rule_id": "repo_doc_unsafe_skip_tests",
            "pointers": ["AGENTS.md:12"],
        },
    )
    assert errors == ()


def test_reason_context_skips_unmapped_codes_without_registry_lookup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(reason_payload, "_REASON_REGISTRY_PATH", Path("/tmp/does-not-exist.registry.json"))
    monkeypatch.setattr(reason_payload, "_REASON_SCHEMA_REF_CACHE", None)

    errors = reason_payload.validate_reason_context_schema(
        BLOCKED_EXEC_DISALLOWED,
        {"arbitrary": "context"},
    )
    assert errors == ()
