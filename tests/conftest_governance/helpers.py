"""
helpers.py — Shared fixtures and helpers for governance E2E truth tests.

All governance E2E test files import from here. This ensures all tests
use the same fixture architecture and canonical layout.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from tests.util import REPO_ROOT, get_phase_api_path, write_governance_paths


def _load_module(name: str, filename: str):
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / filename
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {name} module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_phase5():
    return _load_module("phase5_plan_record_persist", "phase5_plan_record_persist.py")


def _load_session_reader():
    return _load_module("session_reader", "session_reader.py")


def _load_review_decision():
    return _load_module("review_decision_persist", "review_decision_persist.py")


def _load_implement():
    return _load_module("implement_start", "implement_start.py")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_state(session_path: Path) -> dict[str, Any]:
    return _read_json(session_path).get("SESSION_STATE", {})


def _write_rulebooks(local_root: Path) -> None:
    """Write profile rulebooks to governance_content/profiles/ (canonical layout).

    canonical layout (per install.py):
      commands_home/         = ONLY the 8 command files
      governance_content/     = profiles/, templates/, docs/, reference/
    """
    profiles_dir = local_root / "governance_content" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / "rules.fallback-minimum.md").write_text(
        "# Fallback Minimum\n\n"
        "## Intent (binding)\nBaseline governance intent.\n\n"
        "## Scope (binding)\nAll changes.\n\n"
        "## Evidence contract (binding)\nMaintain evidence.\n\n"
        "## Quality heuristics (SHOULD)\n- Use repo-native tools.\n\n"
        "## Mandatory baseline (MUST)\n- Identify build/verify.\n"
        "- Claims require evidence.\n\n"
        "## Anti-Patterns Catalog (Binding)\n- Do not claim without checks.\n",
        encoding="utf-8",
    )
    (profiles_dir / "rules.risk-tiering.md").write_text(
        "# Risk Tiering\n\n"
        "## Intent (binding)\nRisk-tiered evidence.\n\n"
        "## Scope (binding)\nAll changes.\n\n"
        "## Evidence contract (binding)\nHigher risk = more evidence.\n\n"
        "## Decision Trees (Binding)\n- High risk: additional evidence required.\n\n"
        "## Anti-Patterns Catalog (Binding)\n- Do not skip risk assessment.\n",
        encoding="utf-8",
    )


def _write_e2e_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, Path]:
    """Write canonical test fixture matching install.py layout.

    canonical layout (per install.py):
      commands_home/      = ONLY the 8 command files
      governance_content/  = profiles/, templates/, docs/, reference/
      governance_spec/    = phase_api.yaml
    """
    config_root = tmp_path / "cfg"
    commands_home = config_root / "commands"
    local_root = config_root.parent / f"{config_root.name}-local"
    spec_home = local_root / "governance_spec"
    content_home = local_root / "governance_content"
    workspaces_home = config_root / "workspaces"
    repo_fp = "e2e1234567890abc12345678"
    workspace = workspaces_home / repo_fp

    config_root.mkdir(parents=True, exist_ok=True)
    commands_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)
    content_home.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)

    (spec_home / "phase_api.yaml").write_text(
        get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8"
    )

    _write_rulebooks(local_root)
    write_governance_paths(config_root, local_root=local_root)

    session_path = workspace / "SESSION_STATE.json"
    session = {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fp,
            "Phase": "5-ArchitectureReview",
            "Next": "5",
            "Mode": "IN_PROGRESS",
            "session_run_id": "e2e-workflow-test",
            "active_gate": "Plan Record Preparation Gate",
            "next_gate_condition": "Persist plan record evidence",
            "Ticket": "Implement JWT authentication endpoint",
            "TicketRecordDigest": "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
            "Task": "Add /auth/login route that validates credentials and returns JWT",
            "TaskRecordDigest": "sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "Bootstrap": {"Satisfied": True},
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "profile": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "templates": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "addons": {"riskTiering": "${PROFILES_HOME}/rules.risk-tiering.md"},
            },
            "RulebookLoadEvidence": {
                "core": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "profile": "${PROFILES_HOME}/rules.fallback-minimum.md",
            },
            "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
        }
    }
    session_path.write_text(json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    pointer = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": repo_fp,
        "activeSessionStateFile": str(session_path),
    }
    (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer, indent=2), encoding="utf-8")

    return config_root, commands_home, session_path, repo_fp, workspace


def _set_env(monkeypatch: pytest.MonkeyPatch, config_root: Path, commands_home: Path) -> None:
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))


def _mock_llm_cmd(json_data: str) -> str:
    """Create a platform-specific mock LLM command that outputs JSON.

    On Unix: uses echo with single quotes
    On Windows: uses python -c with single quotes (works in cmd.exe)
    """
    import platform
    if platform.system() == "Windows":
        # On Windows, subprocess.run with shell=True uses cmd.exe
        # Use python -c with single quotes to avoid quoting issues
        # Python accepts both single and double quotes for strings
        return f"python -c 'print({repr(json_data)})'"
    else:
        return f"echo '{json_data}'"


def _write_phase6_session(
    session_path: Path,
    workspace: Path,
    repo_fp: str,
    review_object: str = "Final Phase-6 implementation review decision",
    ticket: str = "Implement JWT authentication endpoint",
    plan_summary: str = "Add /auth/login route with JWT support",
    plan_body: str = "Plan body for JWT auth implementation",
    implementation_scope: str = "",
    constraints: str = "",
    decision_semantics: str = "approve | changes_requested | reject",
) -> None:
    source = "|".join(
        [review_object, ticket, plan_summary, plan_body, implementation_scope, constraints, decision_semantics]
    )
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    state_change_ts = "2026-03-21T12:00:00Z"
    rendered_ts = "2026-03-21T12:00:01Z"
    doc = {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fp,
            "Phase": "6-PostFlight",
            "Next": "6",
            "Mode": "IN_PROGRESS",
            "session_run_id": "e2e-workflow-test",
            "active_gate": "Evidence Presentation Gate",
            "next_gate_condition": "Awaiting final review decision.",
            "implementation_review_complete": True,
            "ImplementationReview": {
                "implementation_review_complete": True,
                "completion_status": "phase6-completed",
                "iteration": 3,
                "min_self_review_iterations": 1,
                "revision_delta": "none",
            },
            "review_package_presented": True,
            "review_package_plan_body_present": True,
            "review_package_review_object": review_object,
            "review_package_ticket": ticket,
            "review_package_approved_plan_summary": plan_summary,
            "review_package_plan_body": plan_body,
            "review_package_implementation_scope": implementation_scope,
            "review_package_constraints": constraints,
            "review_package_evidence_summary": "All acceptance tests pass",
            "review_package_decision_semantics": decision_semantics,
            "review_package_loop_status": "completed",
            "session_materialization_event_id": "evt-phase6-001",
            "session_state_revision": 1,
            "session_materialized_at": rendered_ts,
            "review_package_last_state_change_at": state_change_ts,
            "review_package_presentation_receipt": {
                "receipt_type": "governance_review_presentation_receipt",
                "requirement_scope": "R-REVIEW-DECISION-001",
                "content_digest": digest,
                "rendered_at": rendered_ts,
                "render_event_id": "evt-phase6-001",
                "gate": "Evidence Presentation Gate",
                "session_id": "e2e-workflow-test",
                "state_revision": "1",
                "source_command": "/continue",
                "digest": digest,
                "presented_at": rendered_ts,
                "contract": "guided-ui.v1",
                "materialization_event_id": "evt-phase6-001",
            },
            "phase5_completed": True,
            "PlanRecordVersions": 1,
            "requirement_contracts_present": True,
            "requirement_contracts_count": 1,
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "profile": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "templates": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "addons": {"riskTiering": "${PROFILES_HOME}/rules.risk-tiering.md"},
            },
            "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
        }
    }
    session_path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_phase6_approved_session(session_path: Path) -> None:
    doc = _read_json(session_path)
    state = doc["SESSION_STATE"]
    state["active_gate"] = "Workflow Complete"
    state["next_gate_condition"] = (
        "Workflow approved. Governance is complete and implementation is authorized. "
        "Run /implement to start the implementation phase."
    )
    state["workflow_complete"] = True
    state["WorkflowComplete"] = True
    state["governance_status"] = "complete"
    state["implementation_status"] = "authorized"
    state["implementation_authorized"] = True
    state["next_action_command"] = "/implement"
    state["implementation_review_complete"] = True
    state["phase6_state"] = "phase6_completed"
    state["UserReviewDecision"] = {"decision": "approve", "timestamp": "2026-03-21T12:00:00Z"}
    session_path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
