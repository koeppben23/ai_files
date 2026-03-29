from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .util import REPO_ROOT, get_phase_api_path, get_master_path, get_rules_path


@pytest.fixture(autouse=True)
def _enable_legacy_markdown_requirements_for_legacy_plan_inputs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOVERNANCE_ALLOW_LEGACY_MARKDOWN_REQUIREMENTS", "1")


def _load_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "phase5_plan_record_persist.py"
    spec = importlib.util.spec_from_file_location("phase5_plan_record_persist", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load phase5_plan_record_persist module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fixture_state(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    config_root = tmp_path / "cfg"
    commands_home = config_root / "commands"
    local_root = config_root.parent / f"{config_root.name}-local"
    spec_home = local_root / "governance_spec"
    content_home = local_root / "governance_content"
    workspaces_home = config_root / "workspaces"
    repo_fp = "abc123def456abc123def456"
    workspace = workspaces_home / repo_fp
    workspace.mkdir(parents=True, exist_ok=True)
    commands_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)
    content_home.mkdir(parents=True, exist_ok=True)

    shutil.copytree(REPO_ROOT / "governance_spec", spec_home, dirs_exist_ok=True)
    (spec_home / "phase_api.yaml").write_text(get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8")
    # Mirror SSOT content into governance_content for tests (NOT commands_home)
    try:
        master_src = get_master_path()
        rules_src = get_rules_path()
        ref_dir = content_home / "reference"
        ref_dir.mkdir(parents=True, exist_ok=True)
        if master_src.exists():
            (ref_dir / "master.md").write_text(master_src.read_text(encoding="utf-8"), encoding="utf-8")
        if rules_src.exists():
            (ref_dir / "rules.md").write_text(rules_src.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

    # Create profile and addon rulebook files under governance_content/profiles/
    try:
        profiles_dir = content_home / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        # Fallback-minimum profile - must have enough structure to generate constraints
        fallback_content = (
            "# Fallback Minimum Profile Rulebook\n\n"
            "## Intent (binding)\n"
            "Provide a mandatory baseline when no explicit standards exist.\n\n"
            "## Scope (binding)\n"
            "Applies when no stack profile can be selected.\n\n"
            "## Evidence contract (binding)\n"
            "Maintain evidence for every verification claim.\n\n"
            "## Quality heuristics (SHOULD)\n"
            "- Use repo-native tools when available.\n\n"
            "## Mandatory baseline (MUST)\n"
            "- Identify how to build and verify the project.\n\n"
            "## Anti-Patterns Catalog (Binding)\n"
            "- Do not claim verification without executed checks.\n"
        )
        (profiles_dir / "rules.fallback-minimum.md").write_text(fallback_content, encoding="utf-8")
        # Risk-tiering addon
        addon_content = (
            "# Risk Tiering Addon\n\n"
            "## Intent (binding)\n"
            "Define risk-based evidence requirements.\n\n"
            "## Scope (binding)\n"
            "Applies to all changes.\n\n"
            "## Evidence contract (binding)\n"
            "Higher risk changes require more evidence.\n\n"
            "## Quality heuristics (SHOULD)\n"
            "- Document risk rationale.\n\n"
            "## Decision Trees (Binding)\n"
            "- High risk: require additional evidence.\n\n"
            "## Anti-Patterns Catalog (Binding)\n"
            "- Do not skip risk assessment for high-impact changes.\n"
        )
        (profiles_dir / "rules.risk-tiering.md").write_text(addon_content, encoding="utf-8")
    except Exception:
        pass

    paths = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(commands_home),
            "localRoot": str(local_root),
            "specHome": str(spec_home),
            "contentHome": str(content_home),
            "profilesHome": str(content_home / "profiles"),
            "workspacesHome": str(workspaces_home),
            "configRoot": str(config_root),
            "pythonCommand": "python3",
        },
    }
    (config_root / "governance.paths.json").write_text(json.dumps(paths, indent=2), encoding="utf-8")

    session_path = workspace / "SESSION_STATE.json"
    session = {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fp,
            "phase": "5-ArchitectureReview",
            "next": "5",
            "Mode": "IN_PROGRESS",
            "session_run_id": "work-123",
            "active_gate": "Plan Record Preparation Gate",
            "next_gate_condition": "Persist plan record evidence",
            "TicketRecordDigest": "sha256:ticket-v1",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "Bootstrap": {"Satisfied": True},
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${PROFILES_HOME}/rules.fallback-minimum.md",
                "templates": "${COMMANDS_HOME}/master.md",
                "addons": {
                    "riskTiering": "${PROFILES_HOME}/rules.risk-tiering.md",
                },
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${PROFILES_HOME}/rules.fallback-minimum.md",
            },
            "AddonsEvidence": {
                "riskTiering": {"status": "loaded"},
            },
        }
    }
    session_path.write_text(json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    pointer = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": repo_fp,
        "activeSessionStateFile": str(session_path),
    }
    (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    return config_root, commands_home, session_path, repo_fp


def _write_workspace_governance_config(workspace_dir: Path, *, pipeline_mode: bool) -> None:
    payload = {
        "pipeline_mode": pipeline_mode,
        "presentation": {
            "mode": "standard",
        },
        "review": {
            "phase5_max_review_iterations": 3,
            "phase6_max_review_iterations": 3,
        },
    }
    (workspace_dir / "governance-config.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _set_pipeline_bindings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    execution: str,
    review: str,
) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_EXECUTION_BINDING", execution)
    monkeypatch.setenv("AI_GOVERNANCE_REVIEW_BINDING", review)


@pytest.mark.governance
def test_phase5_plan_persist_good_chat_text_persists_and_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")

    rc = module.main(["--plan-text", "Architecture plan v1", "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["phase"] == "5-ArchitectureReview"
    assert state["active_gate"] == "Architecture Review Gate"
    assert state["PlanRecordStatus"] == "active"
    assert state["PlanRecordVersions"] >= 1
    assert state["phase5_completed"] is True
    assert state["self_review_iterations_met"] is True
    assert state["phase5_self_review_iterations"] >= 1
    assert state["phase5_state"] == "phase5_completed"
    assert state["phase5_blocker_code"] == "none"
    assert state["phase5_review_pipeline_mode"] is False
    assert state["phase5_review_binding_role"] == "review"
    assert state["phase5_review_binding_source"] == "active_chat_binding"
    assert state["requirement_contracts_present"] is True
    assert int(state["requirement_contracts_count"]) >= 1
    assert str(state["requirement_contracts_digest"]).startswith("sha256:")
    assert Path(str(state["requirement_contracts_source"])).exists()
    assert state["requirement_contracts_source_authority"] in {
        "machine_requirements",
        "legacy_markdown_requirements",
    }
    assert int(state["machine_requirements_count"]) >= 1
    assert isinstance(state["requirement_compiler_notes"], list)

    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert plan_record["status"] == "active"
    assert len(plan_record["versions"]) >= 1
    assert plan_record["versions"][0]["trigger"] == "phase5-plan-record-rail"
    assert isinstance(plan_record["versions"][0].get("machine_requirements"), list)


@pytest.mark.governance
def test_phase5_plan_persist_fail_closed_without_structured_requirements_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")
    monkeypatch.delenv("GOVERNANCE_ALLOW_LEGACY_MARKDOWN_REQUIREMENTS", raising=False)

    rc = module.main(["--plan-text", "Plain legacy markdown input", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["reason_code"] == "REQUIREMENT_SOURCE_INVALID"


@pytest.mark.governance
def test_phase5_plan_persist_pipeline_mode_records_execution_and_review_binding_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    _write_workspace_governance_config(session_path.parent, pipeline_mode=True)

    session_payload = json.loads(session_path.read_text(encoding="utf-8"))
    session_state = session_payload.get("SESSION_STATE", {})
    session_state["Ticket"] = "AUTH-123"
    session_state["Task"] = "Implement login endpoint"
    session_path.write_text(
        json.dumps(session_payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    generated_plan = json.dumps(
        {
            "objective": "Add authentication endpoint with JWT support",
            "target_state": "New /auth/login endpoint accepts credentials and returns JWT token",
            "target_flow": "1. Add auth route. 2. Validate credentials. 3. Generate JWT. 4. Return token.",
            "state_machine": "unauthenticated -> authenticated (on valid login)",
            "blocker_taxonomy": "Credential store must be available; JWT secret must be configured",
            "audit": "Login events logged with timestamp and user id",
            "go_no_go": "JWT library available; credential store reachable; tests pass",
            "test_strategy": "Unit tests for token generation; integration test for login flow",
            "reason_code": "PLAN-AUTH-001",
        },
        ensure_ascii=True,
    )
    review_result = json.dumps({"verdict": "approve", "findings": []}, ensure_ascii=True)
    execution_binding_cmd = "EXEC_BINDING_CMD"
    review_binding_cmd = "REVIEW_BINDING_CMD"
    _set_pipeline_bindings(
        monkeypatch,
        execution=execution_binding_cmd,
        review=review_binding_cmd,
    )

    def _fake_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        token = str(cmd)
        if execution_binding_cmd in token:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=generated_plan, stderr="")
        if review_binding_cmd in token:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=review_result, stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_subprocess_run)

    rc = module.main(["--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["phase5_plan_execution_pipeline_mode"] is True
    assert state["phase5_plan_execution_binding_role"] == "execution"
    assert state["phase5_plan_execution_binding_source"] == "env:AI_GOVERNANCE_EXECUTION_BINDING"
    assert state["phase5_review_pipeline_mode"] is True
    assert state["phase5_review_binding_role"] == "review"
    assert state["phase5_review_binding_source"] == "env:AI_GOVERNANCE_REVIEW_BINDING"

    events = [
        json.loads(line)
        for line in (session_path.parent / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    persisted = [row for row in events if row.get("event") == "phase5-plan-record-persisted"]
    assert persisted
    assert persisted[-1]["plan_execution_pipeline_mode"] is True
    assert persisted[-1]["plan_execution_binding_source"] == "env:AI_GOVERNANCE_EXECUTION_BINDING"
    assert persisted[-1]["review_pipeline_mode"] is True
    assert persisted[-1]["review_binding_source"] == "env:AI_GOVERNANCE_REVIEW_BINDING"


@pytest.mark.governance
def test_phase5_plan_persist_good_file_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")

    plan_file = tmp_path / "plan.md"
    plan_file.write_text("\n\nPlan from file\n", encoding="utf-8")

    rc = module.main(["--plan-file", str(plan_file), "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["PlanRecordVersions"] >= 1
    assert state["phase5_completed"] is True
    assert state["self_review_iterations_met"] is True
    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert "Plan from file" in plan_record["versions"][0]["plan_record_text"]


@pytest.mark.governance
def test_phase5_plan_persist_bad_missing_evidence_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, _, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--quiet"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason_code"] == "BLOCKED-P5-PLAN-RECORD-PERSIST"


@pytest.mark.governance
def test_phase5_plan_persist_bad_missing_ticket_evidence_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    state.pop("TicketRecordDigest", None)
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "Architecture plan", "--quiet"])
    assert rc == 2
    blocked = json.loads(capsys.readouterr().out.strip())
    assert blocked["reason_code"] == "BLOCKED-P5-TICKET-EVIDENCE-MISSING"
    assert blocked["reason"] == "missing-ticket-intake-evidence"


@pytest.mark.governance
def test_phase5_plan_persist_bad_outside_phase5_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    payload["SESSION_STATE"]["phase"] = "4"
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "Architecture plan", "--quiet"])
    assert rc == 2
    blocked = json.loads(capsys.readouterr().out.strip())
    assert blocked["reason_code"] == "BLOCKED-P5-PHASE-MISMATCH"
    assert blocked["reason"] == "phase5-plan-persist-not-allowed-outside-phase5"


@pytest.mark.governance
def test_phase5_plan_persist_happy_consumes_rework_clarification_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    state["phase"] = "6-PostFlight"
    state["phase"] = "6-PostFlight"
    state["active_gate"] = "Rework Clarification Gate"
    state["phase6_state"] = "6.rework"
    state["next_gate_condition"] = "Clarify requested changes in chat, then run directed next rail."
    state["UserReviewDecision"] = {"decision": "changes_requested"}
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")

    rc = module.main([
        "--plan-text",
        "## Zielbild\n## Soll-Flow\n## State-Machine\n## Blocker-Taxonomie\n## Audit\n## Go/No-Go\nReason code",
        "--quiet",
    ])
    assert rc == 0

    updated = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
    assert updated["active_gate"] != "Rework Clarification Gate"
    assert updated.get("phase6_state") != "6.rework"
    assert updated.get("UserReviewDecision") is None
    assert updated["rework_clarification_consumed"] is True
    assert updated["rework_clarification_consumed_by"] == "plan"


@pytest.mark.governance
def test_phase5_plan_persist_corner_file_input_wins_over_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")

    plan_file = tmp_path / "plan.md"
    plan_file.write_text("plan from file content", encoding="utf-8")

    rc = module.main([
        "--plan-text",
        "plan from text content",
        "--plan-file",
        str(plan_file),
        "--quiet",
    ])
    assert rc == 0

    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert plan_record["versions"][0]["plan_record_text"] == "plan from file content"


@pytest.mark.governance
def test_phase5_plan_persist_edge_canonicalizes_crlf_and_blank_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")

    rc = module.main(["--plan-text", "\r\n\r\nLine A\r\nLine B\r\n\r\n", "--quiet"])
    assert rc == 0

    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert plan_record["versions"][0]["plan_record_text"] == "Line A\nLine B"


@pytest.mark.governance
def test_phase5_plan_persist_corner_force_drift_reaches_max_iterations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")

    rc = module.main(["--plan-text", "## Zielbild\n[[force-drift]]", "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["phase5_self_review_iterations"] == 3
    assert state["phase5_revision_delta"] == "changed"
    assert state["self_review_iterations_met"] is True


@pytest.mark.governance
def test_phase5_plan_persist_happy_writes_iteration_audit_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")

    rc = module.main(["--plan-text", "## Zielbild\n## Soll-Flow\n## State-Machine\n## Blocker-Taxonomie\n## Audit\n## Go/No-Go\nReason code", "--quiet"])
    assert rc == 0

    events = (session_path.parent / "logs" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    iteration_events = [json.loads(line) for line in events if '"event":"phase5-self-review-iteration"' in line]
    assert len(iteration_events) >= 1
    row = iteration_events[0]
    assert "input_digest" in row
    assert "iteration" in row
    assert "findings_summary" in row
    assert "revision_delta" in row
    assert "plan_record_version" in row
    assert "outcome" in row
    assert "completion_status" in row


@pytest.mark.governance
def test_phase5_plan_persist_bad_missing_active_repo_pointer_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, _, _ = _write_fixture_state(tmp_path)
    pointer_path = config_root / "SESSION_STATE.json"
    pointer_payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer_payload["activeRepoFingerprint"] = ""
    pointer_path.write_text(json.dumps(pointer_payload, indent=2), encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "Plan exists", "--quiet"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason_code"] == "BLOCKED-P5-PLAN-RECORD-PERSIST"


class TestReviewResponseEnforcementE2E:
    """Runtime E2E evals proving the enforcement chain is fail-closed.

    These tests prove that the full runtime path from LLM response → parsed
    → validated → blocked/proceeded is correctly enforced. They test the
    actual entrypoint's _parse_llm_review_response with real schema loading.

    The enforcement chain:
      LLM raw response
          ↓
      _parse_llm_review_response(response_text, mandates_schema)
          ↓
      JSON parse? ─no→ hard block (response-not-structured-json)
          ↓ yes
      schema validate? ─fail→ hard block (schema-violation:*)
          ↓ pass
      proceed with verdict + findings
    """

    @staticmethod
    def _load_schema() -> dict | None:
        schema_path = REPO_ROOT / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"
        if not schema_path.exists():
            return None
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def test_freetext_response_hard_blocked(self):
        module = _load_module()
        response = "Looks good overall. I reviewed the code and it seems fine. Minor suggestions but nothing blocking."
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result["validation_violations"]
        assert result["verdict"] == "changes_requested"

    def test_malformed_json_hard_blocked(self):
        module = _load_module()
        response = '{"verdict": "approve", "findings": []'  # trailing comma, unclosed
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result["validation_violations"]
        assert result["verdict"] == "changes_requested"

    def test_empty_response_hard_blocked(self):
        module = _load_module()
        result = module._parse_llm_review_response("", mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"

    def test_valid_approve_with_no_findings_proceeds(self):
        module = _load_module()
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation against plan. All steps covered.",
            "contract_check": "SSOT boundaries preserved. No contract drift.",
            "findings": [],
            "regression_assessment": "Low risk. Changes are isolated.",
            "test_assessment": "Tests cover the changed scope adequately.",
        })
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is True
        assert result["verdict"] == "approve"
        assert result["findings"] == []

    def test_valid_changes_requested_with_findings_proceeds(self):
        module = _load_module()
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Checked source against contracts.",
            "contract_check": "Minor drift in API response shape.",
            "findings": [
                {
                    "severity": "medium",
                    "type": "contract-drift",
                    "location": "src/api.py:42",
                    "evidence": "Response field 'user_id' missing",
                    "impact": "Client code relying on this field will break",
                    "fix": "Add 'user_id' to response payload",
                }
            ],
            "regression_assessment": "Existing endpoints unaffected.",
            "test_assessment": "Tests missing for new field.",
        })
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is True
        assert result["verdict"] == "changes_requested"
        assert len(result["findings"]) == 1

    def test_approve_with_critical_defect_hard_blocked(self):
        module = _load_module()
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Looks fine.",
            "contract_check": "OK.",
            "findings": [
                {
                    "severity": "critical",
                    "type": "defect",
                    "location": "src/auth.py:1",
                    "evidence": "Auth bypass via missing token check",
                    "impact": "Anyone can access protected endpoints",
                    "fix": "Add token validation",
                }
            ],
            "regression_assessment": "All endpoints affected.",
            "test_assessment": "No tests for auth.",
        })
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"
        violations = result.get("validation_violations", [])
        assert any("defect" in v.lower() for v in violations)

    def test_missing_required_field_hard_blocked(self):
        module = _load_module()
        response = json.dumps({
            "verdict": "changes_requested",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/main.py:42",
                    "evidence": "Missing null check",
                    "impact": "Crash on empty input",
                    "fix": "Add null guard",
                }
            ],
            # missing: governing_evidence, contract_check, regression_assessment, test_assessment
        })
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"
        violations = result.get("validation_violations", [])
        assert any("governing_evidence" in v or "contract_check" in v or "required" in v.lower() for v in violations)

    def test_invalid_verdict_value_hard_blocked(self):
        module = _load_module()
        response = json.dumps({
            "verdict": "looks_good_to_me",
            "governing_evidence": "Reviewed all files.",
            "contract_check": "No issues found.",
            "findings": [],
            "regression_assessment": "Minimal risk.",
            "test_assessment": "Tests sufficient.",
        })
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"  # hard-blocked: invalid verdict

    def test_json_array_response_hard_blocked(self):
        module = _load_module()
        response = json.dumps([{"verdict": "approve"}, {"note": "all good"}])
        result = module._parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result.get("validation_violations", [])

    def test_whitespace_only_response_hard_blocked(self):
        module = _load_module()
        result = module._parse_llm_review_response("   \n\n  ", mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"


class TestPhase5BlocksWhenEffectivePolicyUnavailable:
    """Phase 5 must block when effective review policy cannot be built."""

    def test_phase5_blocks_when_effective_review_policy_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_module()
        config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
        monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", "echo 'irrelevant'")

        # Clear the profile files so effective policy cannot be built
        local_root = config_root.parent / f"{config_root.name}-local"
        profiles_dir = local_root / "governance_content" / "profiles"
        if profiles_dir.exists():
            for f in profiles_dir.iterdir():
                f.unlink()

        rc = module.main(["--plan-text", "Architecture plan v1", "--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason_code"] == "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"
        assert "effective-review-policy-unavailable" in payload["reason"]

    def test_phase5_blocks_when_mandate_schema_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_module()
        config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

        # Mock _load_mandates_schema to raise MandateSchemaMissingError
        original_load = module._load_mandates_schema

        def mock_load():
            raise module.MandateSchemaMissingError("Schema missing")

        monkeypatch.setattr(module, "_load_mandates_schema", mock_load)

        rc = module.main(["--plan-text", "Architecture plan v1", "--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason"] == "mandate-schema-missing"


class TestCallLLMReviewMandateSchemaFailClosed:
    """_call_llm_review() must itself fail-closed on mandate schema errors."""

    def test_blocks_on_missing_schema(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="python3 -c \"print('{}')\"",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        def _raise_missing():
            raise module.MandateSchemaMissingError("schema file not found")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)
        result = module._call_llm_review("plan text", "mandate text", workspace_dir=tmp_path)
        assert result["llm_invoked"] is False
        assert result["verdict"] == "changes_requested"
        assert result["reason_code"] == "MANDATE-SCHEMA-MISSING"
        assert any("mandate-schema-missing" in f for f in result["findings"])

    def test_blocks_on_invalid_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        workspace_dir = tmp_path
        _write_workspace_governance_config(workspace_dir, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="python3 -c \"print('{}')\"",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        def _raise_invalid_json():
            raise module.MandateSchemaInvalidJsonError("bad json at line 5")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid_json)
        result = module._call_llm_review("plan text", "mandate text", workspace_dir=workspace_dir)
        assert result["llm_invoked"] is False
        assert result["verdict"] == "changes_requested"
        assert result["reason_code"] == "MANDATE-SCHEMA-INVALID-JSON"

    def test_blocks_on_invalid_structure(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        workspace_dir = tmp_path
        _write_workspace_governance_config(workspace_dir, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="python3 -c \"print('{}')\"",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        def _raise_invalid_structure():
            raise module.MandateSchemaInvalidStructureError("missing review_mandate")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid_structure)
        result = module._call_llm_review("plan text", "mandate text", workspace_dir=workspace_dir)
        assert result["llm_invoked"] is False
        assert result["verdict"] == "changes_requested"
        assert result["reason_code"] == "MANDATE-SCHEMA-INVALID-STRUCTURE"

    def test_blocks_on_unavailable(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        workspace_dir = tmp_path
        _write_workspace_governance_config(workspace_dir, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="python3 -c \"print('{}')\"",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        def _raise_unavailable():
            raise module.MandateSchemaUnavailableError("IO error reading schema")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_unavailable)
        result = module._call_llm_review("plan text", "mandate text", workspace_dir=workspace_dir)
        assert result["llm_invoked"] is False
        assert result["verdict"] == "changes_requested"
        assert result["reason_code"] == "MANDATE-SCHEMA-UNAVAILABLE"

    def test_happy_bridge_review_parses_ndjson_text_event(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=False)
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setattr(
            module,
            "_resolve_desktop_bridge_cmd",
            lambda **_kwargs: "echo '{\"type\":\"text\",\"part\":{\"text\":\"{\\\"verdict\\\":\\\"approve\\\",\\\"findings\\\":[\\\"ok\\\"]}\"}}'",
        )
        monkeypatch.setattr(module, "_load_mandates_schema", lambda: {"$defs": {"reviewOutputSchema": {"type": "object"}}})

        observed: dict[str, object] = {}

        def _fake_parse(response_text: str, mandates_schema=None):
            observed["response_text"] = response_text
            return {"llm_invoked": True, "verdict": "approve", "findings": ["ok"]}

        monkeypatch.setattr(module, "_parse_llm_review_response", _fake_parse)

        result = module._call_llm_review("plan text", "mandate text", workspace_dir=tmp_path)
        assert result["verdict"] == "approve"
        assert observed["response_text"] == '{"verdict":"approve","findings":["ok"]}'

    def test_bad_bridge_review_blocks_tool_use_only_events(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=False)
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        ndjson = '{"type":"tool_use","part":{"state":{"status":"completed","output":"oops"}}}'
        monkeypatch.setattr(module, "_resolve_desktop_bridge_cmd", lambda **_kwargs: f"echo '{ndjson}'")

        result = module._call_llm_review("plan text", "mandate text", workspace_dir=tmp_path)
        assert result["verdict"] == "changes_requested"
        assert result["reason_code"] == "BLOCKED-REVIEW-TOOL-USE-DISALLOWED"

    def test_corner_bridge_review_timeout_is_fail_closed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=False)
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setattr(module, "_bridge_timeout_seconds", lambda: 1)
        monkeypatch.setattr(module, "_resolve_desktop_bridge_cmd", lambda **_kwargs: "python3 -c \"import time; time.sleep(2)\"")

        result = module._call_llm_review("plan text", "mandate text", workspace_dir=tmp_path)
        assert result["verdict"] == "changes_requested"
        assert result["reason_code"] == "BLOCKED-REVIEW-EXECUTOR-TIMEOUT"

    def test_edge_self_review_short_circuits_on_review_transport_block(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        module = _load_module()
        monkeypatch.setattr(module, "_has_any_llm_executor", lambda **_kwargs: True)
        monkeypatch.setattr(module, "_build_review_mandate_text", lambda _schema: "mandate")
        monkeypatch.setattr(module, "_load_mandates_schema", lambda: {"$defs": {"reviewOutputSchema": {"type": "object"}}})
        monkeypatch.setattr(
            module,
            "_call_llm_review",
            lambda *args, **kwargs: {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": ["review-llm-timeout"],
                "reason_code": "BLOCKED-REVIEW-EXECUTOR-TIMEOUT",
            },
        )

        result = module._run_internal_phase5_self_review(
            "## Objective\nA valid objective line that is long enough\n\n## Target-State\nA valid target state statement that is long enough\n\n## Target-Flow\n1. one\n2. two\n\n## State-Machine\nA -> B\n\n## Blocker-Taxonomy\n- b\n\n## Audit\n- a\n\n## Go/No-Go\n- g\n\n## Test-Strategy\n- t\n\n### Reason Code\nRC-1\n",
            state={},
            commands_home=None,
            workspace_dir=tmp_path,
            max_iterations=3,
        )
        assert result["blocked"] is True
        assert result["reason_code"] == "BLOCKED-REVIEW-EXECUTOR-TIMEOUT"


class TestPlanGeneration:
    """Tests for LLM-based plan generation in /plan."""


class TestParseJsonEventsToText:
    """Tests for _parse_json_events_to_text parsing function.

    OpenCode CLI --format json emits NDJSON event streams.
    Our runtime contract requires a single JSON payload from the LLM.

    PRIMARY PATH: Direct 'text' event (preferred, expected behavior)
    FALLBACK PATH: Tool output extraction (degraded, tolerated, NOT official contract)
    """

    def test_primary_text_event_returns_content(self):
        """PRIMARY PATH: First 'text' event content is returned."""
        module = _load_module()
        ndjson = "\n".join([
            '{"type":"step_start","timestamp":123}',
            '{"type":"text","part":{"text":"{\\"objective\\": \\"test\\"}"}}',
            '{"type":"step_finish","timestamp":124}',
        ])
        result = module._parse_json_events_to_text(ndjson)
        assert result == '{"objective": "test"}'

    def test_fallback_tool_output_returns_combined_json(self):
        """FALLBACK PATH (degraded): Tool outputs are extracted when no text event exists.

        This is NOT the primary path. It is a tolerated compatibility layer
        for cases where OPENCODE_CONFIG_CONTENT permission overlay does not
        deterministically prevent tool usage.
        """
        module = _load_module()
        ndjson = "\n".join([
            '{"type":"step_start","timestamp":123}',
            '{"type":"tool_use","part":{"state":{"status":"completed","output":"{\\"objective\\": \\"from_tool\\"}"}}}',
            '{"type":"step_finish","timestamp":124}',
        ])
        result = module._parse_json_events_to_text(ndjson)
        # Fallback extracts tool output
        assert '"objective"' in result
        assert "from_tool" in result

    def test_fallback_ignored_when_text_event_present(self):
        """PRIMARY PATH wins: When text event exists, tool outputs are ignored."""
        module = _load_module()
        ndjson = "\n".join([
            '{"type":"step_start","timestamp":123}',
            '{"type":"tool_use","part":{"state":{"status":"completed","output":"tool_result"}}}',
            '{"type":"text","part":{"text":"{\\"objective\\": \\"from_text\\"}"}}',
            '{"type":"step_finish","timestamp":124}',
        ])
        result = module._parse_json_events_to_text(ndjson)
        # Primary path wins, tool output ignored
        assert "from_text" in result
        assert "tool_result" not in result

    def test_fallback_rejected_for_non_json_output(self):
        """FALLBACK PATH: Non-JSON tool output is not accepted."""
        module = _load_module()
        ndjson = "\n".join([
            '{"type":"step_start","timestamp":123}',
            '{"type":"tool_use","part":{"state":{"status":"completed","output":"plain text not json"}}}',
            '{"type":"step_finish","timestamp":124}',
        ])
        result = module._parse_json_events_to_text(ndjson)
        # Non-JSON tool output should NOT be accepted
        assert result == ndjson  # Returns original

    def test_empty_response_returns_original(self):
        """Empty response returns original text."""
        module = _load_module()
        assert module._parse_json_events_to_text("") == ""
        assert module._parse_json_events_to_text("   ") == "   "

    def test_malformed_json_returns_original(self):
        """Malformed JSON returns original text."""
        module = _load_module()
        result = module._parse_json_events_to_text("not valid json at all")
        assert result == "not valid json at all"

    def _valid_plan_response(self) -> str:
        return json.dumps({
            "objective": "Add authentication endpoint with JWT support",
            "target_state": "New /auth/login endpoint accepts credentials and returns JWT token",
            "target_flow": "1. Add auth route. 2. Validate credentials. 3. Generate JWT. 4. Return token.",
            "state_machine": "unauthenticated -> authenticated (on valid login)",
            "blocker_taxonomy": "Credential store must be available; JWT secret must be configured",
            "audit": "Login events logged with timestamp and user id",
            "go_no_go": "JWT library available; credential store reachable; tests pass",
            "test_strategy": "Unit tests for token generation; integration test for login flow",
            "reason_code": "PLAN-AUTH-001",
        })

    def test_blocks_when_executor_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_module()
        config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
        monkeypatch.delenv("AI_GOVERNANCE_EXECUTION_BINDING", raising=False)
        monkeypatch.delenv("AI_GOVERNANCE_REVIEW_BINDING", raising=False)
        _write_workspace_governance_config(session_path.parent, pipeline_mode=True)

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
            workspace_dir=session_path.parent,
        )
        assert result["blocked"] is True
        assert result["reason_code"] == "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_blocks_when_llm_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="echo ''",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is True
        assert "empty" in result["reason"].lower() or result["reason_code"] == "BLOCKED-PLAN-GENERATION-FAILED"

    def test_blocks_when_llm_returns_non_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="echo 'not json at all'",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is True
        assert "not-json" in result["reason"] or result["reason_code"] == "BLOCKED-PLAN-GENERATION-FAILED"

    def test_happy_coerces_plan_string_fields_before_schema_validation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        structured = {
            "objective": "Create complete e2e evidence chain for implement and review",
            "target_state": {"artifacts": ["impl-evidence", "review-evidence"]},
            "target_flow": ["run implement", "verify file diff", "run review"],
            "state_machine": {"states": ["a", "b"]},
            "blocker_taxonomy": [{"code": "X"}],
            "audit": {"required": ["diff", "logs"]},
            "go_no_go": {"go": ["all evidence present"]},
            "test_strategy": {"scope": "full e2e"},
            "reason_code": "PLAN-E2E-001",
            "language": "en",
            "presentation_contract": "evidence-first",
        }
        payload = json.dumps(structured, ensure_ascii=True).replace("'", "'\\''")
        _set_pipeline_bindings(
            monkeypatch,
            execution=f"echo '{payload}'",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is False
        structured_plan = result.get("structured_plan")
        assert isinstance(structured_plan, dict)
        assert isinstance(structured_plan.get("target_state"), str)
        assert isinstance(structured_plan.get("target_flow"), str)

    def test_blocks_when_bridge_returns_only_tool_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=False)
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        ndjson = '{"type":"tool_use","part":{"state":{"status":"completed","output":"ok"}}}'
        monkeypatch.setattr(
            module,
            "_resolve_desktop_bridge_cmd",
            lambda **_kwargs: f"echo '{ndjson}'",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is True
        assert result["reason"] == "plan-llm-tool-use-disallowed"

    def test_blocks_when_llm_returns_invalid_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        module = _load_module()
        # Response with only objective — missing all other required fields
        invalid = json.dumps({"objective": "Something"})
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution=f"echo '{invalid}'",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is True
        assert result["reason_code"] == "BLOCKED-PLAN-GENERATION-FAILED"

    def test_valid_plan_response_accepted(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        module = _load_module()
        valid = self._valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution=f"echo '{escaped}'",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth endpoint",
            task_text="Implement JWT login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is False
        assert "plan_text" in result
        plan_text = result["plan_text"]
        assert "PHASE 5 · PLAN FOR APPROVAL" in plan_text
        assert "PLAN (not implemented)" in plan_text
        assert "## Executive Summary" in plan_text
        assert "## Recommendation" in plan_text
        assert "Recommendation: " in plan_text
        assert "## Delivery Scope (Checklist)" in plan_text
        assert "## Acceptance Criteria (Measurable)" in plan_text
        assert "## What Changed Since Last Review" in plan_text
        assert "## Scope" in plan_text
        assert "## Execution Slices" in plan_text
        assert "## Risks & Mitigations (Plain Language)" in plan_text
        assert "## Release Gates" in plan_text
        assert "## Open Decisions" in plan_text
        assert "## Next Steps if Changes Requested" in plan_text
        assert "## Next Actions" in plan_text
        assert "## Technical Appendix" in plan_text
        assert "### Target-State" in plan_text
        assert "### Target-Flow" in plan_text
        assert "### Go/No-Go" in plan_text
        assert "/review-decision approve" in plan_text

        # Decision-brief blocks must appear before technical appendix.
        assert plan_text.index("## Executive Summary") < plan_text.index("## Technical Appendix")
        assert plan_text.index("## Next Actions") < plan_text.index("## Technical Appendix")
        assert plan_text.index("## Recommendation") < plan_text.index("## Technical Appendix")

    def test_blocks_when_llm_plan_text_is_non_english(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        module = _load_module()
        non_english = json.dumps(
            {
                "objective": "Implementiere einen sicheren Login mit Token.",
                "target_state": "Der Endpunkt akzeptiert Zugangsdaten und liefert ein Token zurueck.",
                "target_flow": "1. Erstelle Route. 2. Validiere Zugangsdaten. 3. Gib Token zurueck.",
                "state_machine": "Unauthenticated -> Authenticated",
                "blocker_taxonomy": "Konfiguration fehlt und Umgebung ist nicht stabil.",
                "audit": "Aenderungen werden protokolliert und mit Zeitstempel gespeichert.",
                "go_no_go": "Alle Tests muessen gruen sein und keine Blocker offen bleiben.",
                "test_strategy": "Unit-Tests und Integrationstests decken Login und Fehlerpfade ab.",
                "reason_code": "PLAN-AUTH-001",
            }
        )
        escaped = non_english.replace("'", "'\\''")
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution=f"echo '{escaped}'",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Implement auth endpoint",
            task_text="Add JWT login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is True
        assert result["reason_code"] == "BLOCKED-PLAN-GENERATION-FAILED"
        assert "plan-language-violation" in str(result.get("reason", ""))

    def test_parse_marks_re_review_delta_and_exact_decision_rails(self):
        module = _load_module()
        valid_response = self._valid_plan_response()
        parsed = module._parse_plan_generation_response(valid_response, re_review=True)

        assert parsed["blocked"] is False
        structured = parsed["structured_plan"]
        presentation = structured.get("presentation_contract", {})
        assert presentation.get("delta_since_last_review") == "Updated since last review iteration."
        assert presentation.get("next_actions") == [
            "/review-decision approve",
            "/review-decision changes_requested",
            "/review-decision reject",
        ]
        assert "## What Changed Since Last Review\nUpdated since last review iteration." in str(parsed["plan_text"])

    def test_plan_text_next_actions_block_contains_only_review_decision_commands(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        module = _load_module()
        valid = self._valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution=f"echo '{escaped}'",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth endpoint",
            task_text="Implement JWT login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is False
        plan_text = str(result["plan_text"])
        marker = "## Next Actions"
        assert marker in plan_text
        block = plan_text.split(marker, 1)[1]
        assert "/review-decision approve" in block
        assert "/review-decision changes_requested" in block
        assert "/review-decision reject" in block
        assert "/plan" not in block
        assert "/continue" not in block
        assert "/review " not in block

    def test_auto_generate_blocks_when_no_ticket(self, capsys: pytest.CaptureFixture[str]):
        module = _load_module()
        # No ticket, no task, no plan text — must block
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert "missing-plan-record-evidence" in payload["reason"] or "session-state-unreadable" in payload["reason"]

    def test_auto_generate_blocks_when_executor_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_module()
        config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
        # Add Ticket text to session so auto-generation path is reached
        doc = json.loads(session_path.read_text(encoding="utf-8"))
        doc["SESSION_STATE"]["Ticket"] = "Implement authentication endpoint"
        doc["SESSION_STATE"]["Task"] = "Add JWT login support"
        session_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason_code"] == "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_uses_user_plan_text_when_provided(self, capsys: pytest.CaptureFixture[str]):
        module = _load_module()
        # Provide explicit plan text — should skip auto-generation
        rc = module.main(["--plan-text", "Manual plan text for testing purposes here.", "--quiet"])
        # May succeed or fail depending on session state; if it fails due to missing
        # review executor, that is valid because Phase-5 review requires an LLM.
        out = capsys.readouterr().out
        if rc != 0:
            payload = json.loads(out.strip())
            assert payload.get("reason_code") in {
                "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE",
                "BLOCKED-P5-PLAN-RECORD-PERSIST",
                "MANDATE-SCHEMA-MISSING",
                "MANDATE-SCHEMA-INVALID-JSON",
                "MANDATE-SCHEMA-INVALID-STRUCTURE",
                "MANDATE-SCHEMA-UNAVAILABLE",
            }

    def test_desktop_binding_unblocks_plan_generation_without_env_executor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        module = _load_module()
        config_root, commands_home, _, _ = _write_fixture_state(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5-codex")
        valid = self._valid_plan_response().replace("'", "'\\''")
        monkeypatch.setattr(
            module,
            "_resolve_desktop_bridge_cmd",
            lambda **_kwargs: f"echo '{valid}'",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
        )
        assert result["blocked"] is False
        assert "plan_text" in result

    def test_resolve_plan_execution_binding_uses_execution_env_in_pipeline_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="plan-execution-cmd",
            review="plan-review-cmd",
        )
        pipeline_mode, binding, source = module._resolve_plan_execution_binding(
            workspace_dir=tmp_path
        )
        assert pipeline_mode is True
        assert binding == "plan-execution-cmd"
        assert source == "env:AI_GOVERNANCE_EXECUTION_BINDING"

    def test_resolve_plan_review_binding_uses_review_env_in_pipeline_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        _set_pipeline_bindings(
            monkeypatch,
            execution="plan-execution-cmd",
            review="plan-review-cmd",
        )
        pipeline_mode, binding, source = module._resolve_plan_review_binding(
            workspace_dir=tmp_path
        )
        assert pipeline_mode is True
        assert binding == "plan-review-cmd"
        assert source == "env:AI_GOVERNANCE_REVIEW_BINDING"

    def test_parse_blocks_when_plan_output_schema_missing(self, monkeypatch: pytest.MonkeyPatch):
        module = _load_module()
        valid_response = self._valid_plan_response()

        # Mock _load_mandates_schema to return schema WITHOUT planOutputSchema
        def _schema_without_plan():
            return {"$defs": {"reviewOutputSchema": {"type": "object"}}}

        monkeypatch.setattr(module, "_load_mandates_schema", _schema_without_plan)
        result = module._parse_plan_generation_response(valid_response)
        assert result["blocked"] is True
        assert "plan-output-schema-missing" in result["reason"]

    def test_parse_blocks_when_mandate_schema_unavailable_in_response(self, monkeypatch: pytest.MonkeyPatch):
        module = _load_module()
        valid_response = self._valid_plan_response()

        def _raise_missing():
            raise module.MandateSchemaMissingError("not found")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)
        result = module._parse_plan_generation_response(valid_response)
        assert result["blocked"] is True
        assert result["reason_code"] == "MANDATE-SCHEMA-UNAVAILABLE"

    def test_auto_generate_blocks_when_mandate_schema_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_module()
        config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
        doc = json.loads(session_path.read_text(encoding="utf-8"))
        doc["SESSION_STATE"]["Ticket"] = "Implement authentication"
        doc["SESSION_STATE"]["Task"] = "Add JWT login"
        session_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

        def _raise_missing():
            raise module.MandateSchemaMissingError("schema file not found")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason_code"] == "MANDATE-SCHEMA-MISSING"

    def test_edge_instruction_avoids_embedded_truncated_schema_blob(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        module = _load_module()
        _write_workspace_governance_config(tmp_path, pipeline_mode=True)
        valid = self._valid_plan_response().replace("'", "'\\''")
        _set_pipeline_bindings(
            monkeypatch,
            execution=f"echo '{valid}'",
            review="python3 -c \"print('{\\\"verdict\\\": \\\"approve\\\", \\\"findings\\\": []}')\"",
        )

        result = module._call_llm_generate_plan(
            ticket_text="Add auth",
            task_text="Implement login",
            plan_mandate="Plan mandate text",
            workspace_dir=tmp_path,
        )
        assert result["blocked"] is False

        contexts = list((tmp_path / "workspaces").rglob("llm_plan_context.json"))
        assert contexts
        payload = json.loads(contexts[0].read_text(encoding="utf-8"))
        instruction = str(payload.get("instruction") or "")
        assert "CRITICAL field constraints" in instruction
        assert "go_no_go: string, min 10 chars" in instruction
        assert '"properties"' not in instruction


class TestGetPhase5MaxReviewIterations:
    """Tests for _get_phase5_max_review_iterations helper."""

    def test_returns_fallback_when_no_workspace(self):
        """Returns fallback value 3 when no workspace provided."""
        module = _load_module()
        module._clear_phase5_max_iterations_cache()
        result = module._get_phase5_max_review_iterations(None)
        assert result == 3

    def test_returns_fallback_when_config_missing(self, tmp_path: Path):
        """Returns fallback value when governance-config.json is missing."""
        module = _load_module()
        module._clear_phase5_max_iterations_cache()
        result = module._get_phase5_max_review_iterations(tmp_path)
        assert result == 3

    def test_returns_custom_value_from_config(self, tmp_path: Path):
        """Returns custom value from governance-config.json."""
        module = _load_module()
        module._clear_phase5_max_iterations_cache()
        
        config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 7,
                "phase6_max_review_iterations": 5,
            },
        }
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")
        
        result = module._get_phase5_max_review_iterations(tmp_path)
        assert result == 7

    def test_caches_result(self, tmp_path: Path):
        """Result is cached after first call."""
        module = _load_module()
        module._clear_phase5_max_iterations_cache()
        
        config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 5,
                "phase6_max_review_iterations": 5,
            },
        }
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")
        
        result1 = module._get_phase5_max_review_iterations(tmp_path)
        result2 = module._get_phase5_max_review_iterations(tmp_path)
        assert result1 == result2 == 5
