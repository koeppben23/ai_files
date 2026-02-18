from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from governance.engine.adapters import HostCapabilities
from governance.engine.orchestrator import run_engine_orchestrator
from tests.test_engine_orchestrator import StubAdapter, _make_git_root


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_registry() -> dict[str, Any]:
    return json.loads((REPO_ROOT / "diagnostics" / "reason_codes.registry.json").read_text(encoding="utf-8"))


def _registry_entries(reg: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("blocked_reasons", "audit_events", "codes"):
        value = reg.get(key)
        if not isinstance(value, list):
            continue
        out.extend(entry for entry in value if isinstance(entry, dict))
    return out


def _schema_for(code: str) -> dict[str, Any]:
    reg = _load_registry()
    for entry in _registry_entries(reg):
        if entry.get("code") == code:
            schema_ref = entry.get("payload_schema_ref")
            assert isinstance(schema_ref, str) and schema_ref
            schema_path = REPO_ROOT / schema_ref
            return json.loads(schema_path.read_text(encoding="utf-8"))
    raise AssertionError(f"schema not found for reason code: {code}")


def _validate_object_schema(schema: dict[str, Any], obj: Any) -> None:
    # Lightweight deterministic validator for object required fields and
    # additionalProperties strictness used by governance payload schemas.
    if schema.get("type") != "object":
        return
    assert isinstance(obj, dict), "schema expects object payload"
    required = schema.get("required", [])
    for req in required:
        assert req in obj, f"missing required key: {req}"
    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = set(obj) - set(props)
        assert not extra, f"unexpected keys for strict schema: {sorted(extra)}"
    for key, child_schema in props.items():
        if key in obj and isinstance(child_schema, dict):
            _validate_object_schema(child_schema, obj[key])


def _adapter(tmp_path: Path, mode: str, *, ci: bool = False) -> StubAdapter:
    repo_root = _make_git_root(tmp_path / f"repo-{mode}")
    env = {"OPENCODE_REPO_ROOT": str(repo_root)}
    if ci:
        env["CI"] = "true"
    return StubAdapter(
        env=env,
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode=mode,  # type: ignore[arg-type]
    )


@pytest.mark.governance
def test_reason_context_matches_repo_doc_unsafe_schema(tmp_path: Path):
    out = run_engine_orchestrator(
        adapter=_adapter(tmp_path, "user"),
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        repo_doc_path="AGENTS.md",
        repo_doc_text="Please skip tests for faster runs.",
    )
    assert out.parity["reason_code"] == "REPO-DOC-UNSAFE-DIRECTIVE"
    schema = _schema_for("REPO-DOC-UNSAFE-DIRECTIVE")
    _validate_object_schema(schema, out.reason_payload.get("context", {}))


@pytest.mark.governance
def test_reason_context_matches_constraint_widening_schema(tmp_path: Path):
    out = run_engine_orchestrator(
        adapter=_adapter(tmp_path, "pipeline", ci=True),
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        repo_constraint_widening=True,
        requested_action="write_scope_widen",
    )
    assert out.parity["reason_code"] == "REPO-CONSTRAINT-WIDENING"
    schema = _schema_for("REPO-CONSTRAINT-WIDENING")
    _validate_object_schema(schema, out.reason_payload.get("context", {}))


@pytest.mark.governance
def test_reason_context_matches_interactive_pipeline_schema(tmp_path: Path):
    out = run_engine_orchestrator(
        adapter=_adapter(tmp_path, "pipeline", ci=True),
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        interactive_required=True,
        requested_action="ask_before_command",
    )
    assert out.parity["reason_code"] == "INTERACTIVE-REQUIRED-IN-PIPELINE"
    schema = _schema_for("INTERACTIVE-REQUIRED-IN-PIPELINE")
    _validate_object_schema(schema, out.reason_payload.get("context", {}))


@pytest.mark.governance
def test_reason_context_matches_prompt_budget_schema(tmp_path: Path):
    out = run_engine_orchestrator(
        adapter=_adapter(tmp_path, "user"),
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        prompt_used_total=5,
    )
    assert out.parity["reason_code"] == "PROMPT-BUDGET-EXCEEDED"
    schema = _schema_for("PROMPT-BUDGET-EXCEEDED")
    _validate_object_schema(schema, out.reason_payload.get("context", {}))


@pytest.mark.governance
def test_reason_context_matches_constraint_unsupported_schema(tmp_path: Path):
    out = run_engine_orchestrator(
        adapter=_adapter(tmp_path, "user"),
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        repo_constraint_supported=False,
        repo_constraint_topic="unknown_constraint_topic",
    )
    assert out.parity["reason_code"] == "REPO-CONSTRAINT-UNSUPPORTED"
    schema = _schema_for("REPO-CONSTRAINT-UNSUPPORTED")
    _validate_object_schema(schema, out.reason_payload.get("context", {}))


@pytest.mark.governance
def test_precedence_event_matches_policy_precedence_schema(tmp_path: Path):
    out = run_engine_orchestrator(
        adapter=_adapter(tmp_path, "agents_strict"),
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        repo_constraint_widening=True,
        widening_approved=True,
        requested_action="write_scope_widen",
    )
    assert out.precedence_events
    event = next((e for e in out.precedence_events if e.get("reason_code") == "POLICY-PRECEDENCE-APPLIED"), None)
    assert event is not None
    schema = _schema_for("POLICY-PRECEDENCE-APPLIED")
    _validate_object_schema(schema, event)
