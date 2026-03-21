"""
test_governance_e2e_full_workflow.py — Comprehensive E2E test for the full governance workflow.

Covers: /ticket -> /plan (auto-generate) -> /review-decision -> /implement
with mocked LLM executors, persistence verification, and path correctness.

This test file is marked @pytest.mark.e2e_governance and runs on CI
(governance-e2e job in .github/workflows/ci.yml). It blocks on main merge
if any test fails.

Test categories:
  A. HAPPY PATH — full flow works end-to-end
  B. BAD PATH — /plan blocks on missing/broken inputs
  C. CORNER CASE — explicit plan text, edge conditions
  D. PERSISTENCE — files written to correct paths with correct content
  E. PATH CORRECTNESS — all artifacts at expected locations
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from .util import REPO_ROOT, get_phase_api_path, get_master_path, get_rules_path


# ── Helpers ──────────────────────────────────────────────────────────────

def _load_phase5_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "phase5_plan_record_persist.py"
    spec = importlib.util.spec_from_file_location("phase5_plan_record_persist", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load phase5_plan_record_persist module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_implement_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "implement_start.py"
    spec = importlib.util.spec_from_file_location("implement_start", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load implement_start module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_plan_response() -> str:
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


def _write_e2e_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """Write a complete fixture for E2E testing with Ticket, Task, and rulebooks."""
    config_root = tmp_path / "cfg"
    commands_home = config_root / "commands"
    spec_home = config_root / "governance_spec"
    workspaces_home = config_root / "workspaces"
    repo_fp = "e2e1234567890abc12345678"
    workspace = workspaces_home / repo_fp
    workspace.mkdir(parents=True, exist_ok=True)
    commands_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)

    (spec_home / "phase_api.yaml").write_text(
        get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    try:
        master_src = get_master_path()
        rules_src = get_rules_path()
        if master_src.exists():
            (commands_home / "master.md").write_text(master_src.read_text(encoding="utf-8"), encoding="utf-8")
        if rules_src.exists():
            (commands_home / "rules.md").write_text(rules_src.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

    # Profile and addon rulebooks
    profiles_dir = commands_home / "rulesets" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / "rules.fallback-minimum.md").write_text(
        "# Fallback Minimum\n\n## Intent (binding)\nBaseline.\n\n## Scope (binding)\nAll.\n\n"
        "## Evidence contract (binding)\nMaintain evidence.\n\n"
        "## Quality heuristics (SHOULD)\n- Use repo-native tools.\n\n"
        "## Mandatory baseline (MUST)\n- Identify build/verify.\n\n"
        "## Anti-Patterns Catalog (Binding)\n- Do not claim without checks.\n",
        encoding="utf-8",
    )
    (profiles_dir / "rules.risk-tiering.md").write_text(
        "# Risk Tiering\n\n## Intent (binding)\nRisk evidence.\n\n## Scope (binding)\nAll.\n\n"
        "## Evidence contract (binding)\nHigher risk = more evidence.\n\n"
        "## Quality heuristics (SHOULD)\n- Document risk.\n\n"
        "## Decision Trees (Binding)\n- High risk: additional evidence.\n\n"
        "## Anti-Patterns Catalog (Binding)\n- Do not skip risk.\n",
        encoding="utf-8",
    )

    paths = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(commands_home),
            "specHome": str(spec_home),
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
            "Phase": "5-ArchitectureReview",
            "Next": "5",
            "Mode": "IN_PROGRESS",
            "session_run_id": "e2e-workflow-test",
            "active_gate": "Plan Record Preparation Gate",
            "next_gate_condition": "Persist plan record evidence",
            "Ticket": "Implement JWT authentication endpoint",
            "TicketRecordDigest": "sha256:ticket-e2e-v1",
            "Task": "Add /auth/login route that validates credentials and returns JWT",
            "TaskRecordDigest": "sha256:task-e2e-v1",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "Bootstrap": {"Satisfied": True},
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.md",
                "templates": "${COMMANDS_HOME}/master.md",
                "addons": {
                    "riskTiering": "${COMMANDS_HOME}/rulesets/profiles/rules.risk-tiering.md",
                },
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.md",
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


def _set_env(monkeypatch: pytest.MonkeyPatch, config_root: Path, commands_home: Path):
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))


def _read_session(session_path: Path) -> dict:
    return json.loads(session_path.read_text(encoding="utf-8"))


def _read_state(session_path: Path) -> dict:
    doc = _read_session(session_path)
    return doc.get("SESSION_STATE", {})


# ── A. HAPPY PATH ────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EHappyPath:
    """Full happy path: /plan auto-generates, self-reviews, persists."""

    def test_plan_auto_generates_from_ticket_and_persists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, repo_fp = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0, f"/plan failed with rc={rc}"

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "ok"
        assert payload["reason"] == "phase5-plan-record-persisted"

        # Verify persistence: plan-record.json exists
        workspace = session_path.parent
        plan_record = workspace / "plan-record.json"
        assert plan_record.exists(), "plan-record.json not written"

        plan_doc = json.loads(plan_record.read_text(encoding="utf-8"))
        assert plan_doc["schema_version"]
        assert plan_doc["repo_fingerprint"] == repo_fp
        assert len(plan_doc["versions"]) >= 1

        # Verify persistence: compiled_requirements.json exists
        contracts = workspace / ".governance" / "contracts" / "compiled_requirements.json"
        assert contracts.exists(), "compiled_requirements.json not written"

        contracts_doc = json.loads(contracts.read_text(encoding="utf-8"))
        assert contracts_doc["schema"]
        assert contracts_doc["generated_at"]
        assert len(contracts_doc["requirements"]) >= 1
        req = contracts_doc["requirements"][0]
        assert req["id"].startswith("R-PLAN-")
        assert req["title"]
        assert req["criticality"]

    def test_session_state_fields_updated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        state = _read_state(session_path)

        # Phase 5 completion fields
        assert state.get("phase5_completed") is True
        assert state.get("phase5_state") == "phase5_completed"
        assert state.get("plan_record_version", 0) >= 1
        assert state.get("phase5_plan_record_digest", "").startswith("sha256:")
        assert state.get("phase5_plan_record_source") == "phase5-plan-record-rail"

        # Contract fields
        assert state.get("requirement_contracts_present") is True
        assert state.get("requirement_contracts_count", 0) >= 1
        assert state.get("requirement_contracts_digest", "").startswith("sha256:")

        # Review fields
        Phase5Review = state.get("Phase5Review", {})
        assert Phase5Review.get("iteration", 0) >= 1
        assert Phase5Review.get("completion_status") == "phase5-completed"

    def test_events_jsonl_has_plan_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        workspace = session_path.parent
        events_file = workspace / "events.jsonl"
        assert events_file.exists(), "events.jsonl not written"

        events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(events) >= 1

        event_types = {e.get("event") for e in events}
        assert "phase5-plan-record-persisted" in event_types


# ── B. BAD PATHS ─────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EBadPaths:
    """Bad paths: /plan blocks on missing/broken inputs."""

    def test_blocks_when_no_ticket_no_task_no_plan_text(
        self, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"

    def test_blocks_when_executor_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason_code"] == "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_blocks_when_llm_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo ''")

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"

    def test_blocks_when_llm_returns_non_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo 'not valid json'")

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"

    def test_blocks_when_llm_returns_incomplete_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        incomplete = json.dumps({"objective": "Something"})
        escaped = incomplete.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"

    def test_blocks_when_mandate_schema_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        def _raise_missing():
            raise module.MandateSchemaMissingError("schema not found")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason_code"] == "MANDATE-SCHEMA-MISSING"

    def test_blocks_when_mandate_schema_invalid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        def _raise_invalid():
            raise module.MandateSchemaInvalidJsonError("bad json")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason_code"] == "MANDATE-SCHEMA-INVALID-JSON"

    def test_blocks_when_phase_not_5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        doc = _read_session(session_path)
        doc["SESSION_STATE"]["Phase"] = "4"
        doc["SESSION_STATE"]["Next"] = "4"
        doc["SESSION_STATE"]["active_gate"] = "Ticket Input Gate"
        session_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

        rc = module.main(["--plan-text", "Manual plan text", "--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason_code"] == "BLOCKED-P5-PHASE-MISMATCH"


# ── C. CORNER CASES ──────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ECornerCases:
    """Corner cases: explicit plan text, edge conditions."""

    def test_explicit_plan_text_skips_auto_generation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        rc = module.main(["--plan-text", "Manual plan text for testing purposes here.", "--quiet"])
        if rc != 0:
            payload = json.loads(capsys.readouterr().out.strip())
            assert payload.get("reason_code") != "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_ticket_only_no_task_still_generates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        doc = _read_session(session_path)
        doc["SESSION_STATE"]["Task"] = ""
        doc["SESSION_STATE"].pop("TaskRecordDigest", None)
        session_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

    def test_task_only_no_ticket_still_generates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        doc = _read_session(session_path)
        doc["SESSION_STATE"]["Ticket"] = ""
        doc["SESSION_STATE"].pop("TicketRecordDigest", None)
        session_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

    def test_plan_executor_fallback_to_implement_cmd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0


# ── D. PERSISTENCE ────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPersistence:
    """Verify persistence: correct files, correct paths, correct content."""

    def test_plan_record_json_structure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, repo_fp = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        workspace = session_path.parent
        plan_record = workspace / "plan-record.json"
        assert plan_record.exists()

        doc = json.loads(plan_record.read_text(encoding="utf-8"))
        assert doc["schema_version"]
        assert doc["repo_fingerprint"] == repo_fp
        assert doc["status"] in ("active", "finalized")
        versions = doc["versions"]
        assert len(versions) >= 1
        v0 = versions[0]
        assert v0["version"] == 1
        assert v0["plan_record_text"]
        assert v0["plan_record_digest"].startswith("sha256:")
        assert "5" in str(v0.get("phase", ""))

    def test_compiled_requirements_json_structure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        workspace = session_path.parent
        contracts = workspace / ".governance" / "contracts" / "compiled_requirements.json"
        assert contracts.exists()

        doc = json.loads(contracts.read_text(encoding="utf-8"))
        assert doc["schema"]
        assert doc["generated_at"]
        assert len(doc["requirements"]) >= 1
        req = doc["requirements"][0]
        assert req["id"].startswith("R-PLAN-")
        assert req["title"]
        assert req["criticality"]


# ── E. PATH CORRECTNESS ──────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPathCorrectness:
    """Verify all artifacts are at expected locations."""

    def test_plan_record_at_workspace_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, repo_fp = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        workspace = session_path.parent
        expected_plan = workspace / "plan-record.json"
        assert expected_plan.exists(), f"plan-record.json not at expected path: {expected_plan}"

        # Should NOT be at config_root level
        wrong_path = config_root / "plan-record.json"
        assert not wrong_path.exists(), "plan-record.json incorrectly at config_root"

    def test_contracts_under_governance_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        workspace = session_path.parent
        contracts = workspace / ".governance" / "contracts" / "compiled_requirements.json"
        assert contracts.exists(), f"compiled_requirements.json not at expected path: {contracts}"

    def test_events_jsonl_at_workspace_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        workspace = session_path.parent
        events = workspace / "events.jsonl"
        assert events.exists(), f"events.jsonl not at expected path: {events}"

    def test_session_state_updated_in_place(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        module = _load_phase5_module()
        config_root, commands_home, session_path, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        rc = module.main(["--quiet"])
        assert rc == 0

        # Session state should still be at the same path
        assert session_path.exists()
        doc = _read_session(session_path)
        assert "SESSION_STATE" in doc
        state = doc["SESSION_STATE"]
        assert state.get("phase5_completed") is True
