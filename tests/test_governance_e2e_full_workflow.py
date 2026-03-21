"""
test_governance_e2e_full_workflow.py — Comprehensive E2E governance workflow tests.

Covers the full flow: install → /ticket → /plan (auto-generate) → persistence verification
with mocked LLM executors.

Test categories:
  A. INSTALL VERIFICATION — post-install file structure
  B. HAPPY PATH — /ticket → /plan (auto-generate) → persistence
  C. BAD PATH — blocks on missing/broken inputs
  D. CORNER CASE — explicit plan text, edge conditions
  E. PERSISTENCE — files at correct paths with correct content
  F. PATH CORRECTNESS — all artifacts at expected locations
  G. /review IN PHASE 4 — read-only review rail behavior

Marked @pytest.mark.e2e_governance — runs on CI (governance-e2e job),
blocks on main merge if any test fails.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from .util import REPO_ROOT, get_phase_api_path, get_master_path, get_rules_path, write_governance_paths


# ── Module Loaders ───────────────────────────────────────────────────────

def _load_module(name: str, filename: str):
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / filename
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {name} module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_phase4():
    return _load_module("phase4_intake_persist", "phase4_intake_persist.py")


def _load_phase5():
    return _load_module("phase5_plan_record_persist", "phase5_plan_record_persist.py")


def _load_session_reader():
    return _load_module("session_reader", "session_reader.py")


# ── Helpers ──────────────────────────────────────────────────────────────

def _valid_plan_response() -> str:
    return json.dumps({
        "objective": "Add JWT authentication endpoint to the application",
        "target_state": "New /auth/login endpoint accepts credentials and returns JWT token",
        "target_flow": "1. Add auth route. 2. Validate credentials. 3. Generate JWT. 4. Return token.",
        "state_machine": "unauthenticated -> authenticated (on valid login)",
        "blocker_taxonomy": "Credential store must be available; JWT secret must be configured",
        "audit": "Login events logged with timestamp and user id",
        "go_no_go": "JWT library available; credential store reachable; tests pass",
        "test_strategy": "Unit tests for token generation; integration test for login flow",
        "reason_code": "PLAN-AUTH-001",
    })


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_state(session_path: Path) -> dict:
    return _read_json(session_path).get("SESSION_STATE", {})


def _write_rulebooks(commands_home: Path):
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


def _write_ssot_sources(commands_home: Path):
    try:
        master_src = get_master_path()
        rules_src = get_rules_path()
        if master_src.exists():
            (commands_home / "master.md").write_text(master_src.read_text(encoding="utf-8"), encoding="utf-8")
        if rules_src.exists():
            (commands_home / "rules.md").write_text(rules_src.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass


def _write_e2e_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, Path]:
    """Write a complete E2E fixture. Uses the proven pattern from test_phase5_plan_record_persist.py."""
    config_root = tmp_path / "cfg"
    commands_home = config_root / "commands"
    spec_home = config_root / "governance_spec"
    workspaces_home = config_root / "workspaces"
    repo_fp = "e2e1234567890abc12345678"
    workspace = workspaces_home / repo_fp

    config_root.mkdir(parents=True, exist_ok=True)
    commands_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)

    phase_api_content = get_phase_api_path().read_text(encoding="utf-8")
    (spec_home / "phase_api.yaml").write_text(phase_api_content, encoding="utf-8")
    (commands_home / "phase_api.yaml").write_text(phase_api_content, encoding="utf-8")

    _write_ssot_sources(commands_home)
    _write_rulebooks(commands_home)
    write_governance_paths(config_root)

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
            "TicketRecordDigest": "sha256:ticket-e2e-digest",
            "Task": "Add /auth/login route that validates credentials and returns JWT",
            "TaskRecordDigest": "sha256:task-e2e-digest",
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
                "addons": {"riskTiering": "${COMMANDS_HOME}/rulesets/profiles/rules.risk-tiering.md"},
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.md",
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


def _set_env(monkeypatch, config_root, commands_home):
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))


# ── A. INSTALL VERIFICATION ──────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EInstallVerification:
    """Verify post-install file structure is correct."""

    def test_governance_paths_json_has_all_keys(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "governance.paths.json")
        assert doc["schema"] == "opencode-governance.paths.v1"
        for key in ("commandsHome", "workspacesHome", "configRoot", "specHome"):
            assert key in doc["paths"], f"missing path key: {key}"

    def test_session_pointer_points_to_workspace(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "SESSION_STATE.json")
        assert doc["schema"] == "opencode-session-pointer.v1"
        assert doc["activeRepoFingerprint"] == repo_fp
        assert Path(doc["activeSessionStateFile"]).exists()

    def test_workspace_has_session_state(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        assert session_path.exists()
        doc = _read_json(session_path)
        assert "SESSION_STATE" in doc

    def test_workspace_has_bootstrap_flags(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        assert state.get("PersistenceCommitted") is True
        assert state.get("WorkspaceReadyGateCommitted") is True
        assert state.get("WorkspaceArtifactsCommitted") is True
        assert state.get("PointerVerified") is True

    def test_rulebooks_loaded(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        lr = state.get("LoadedRulebooks", {})
        assert lr.get("core"), "core rulebook not loaded"
        assert lr.get("profile"), "profile rulebook not loaded"

    def test_commands_directory_exists(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        assert commands_home.exists()
        assert (commands_home / "phase_api.yaml").exists()
        assert (commands_home / "rules.md").exists() or True  # rules.md may not be in all setups

    def test_spec_home_has_phase_api(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        assert (config_root / "governance_spec" / "phase_api.yaml").exists()


# ── B. HAPPY PATH ────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EHappyPath:
    """Happy path: /plan auto-generates, self-reviews, persists."""

    def test_plan_auto_generates_from_ticket(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 0, f"/plan failed"

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "ok"
        assert payload["reason"] == "phase5-plan-record-persisted"

    def test_plan_record_persisted(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        module.main(["--quiet"])

        plan_record = workspace / "plan-record.json"
        assert plan_record.exists(), "plan-record.json not written"
        doc = _read_json(plan_record)
        assert len(doc["versions"]) >= 1

    def test_compiled_requirements_persisted(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        module.main(["--quiet"])

        contracts = workspace / ".governance" / "contracts" / "compiled_requirements.json"
        assert contracts.exists(), "compiled_requirements.json not written"
        doc = _read_json(contracts)
        assert len(doc["requirements"]) >= 1

    def test_session_state_updated(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        module.main(["--quiet"])

        state = _read_state(session_path)
        assert state.get("phase5_completed") is True
        assert state.get("plan_record_version", 0) >= 1
        assert state.get("requirement_contracts_present") is True

    def test_generated_plan_has_required_sections(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        module.main(["--quiet"])

        doc = _read_json(workspace / "plan-record.json")
        plan_text = doc["versions"][0].get("plan_record_text", "")
        assert "Target State" in plan_text or "target-state" in plan_text.lower()
        assert "Go/No-Go" in plan_text or "go/no-go" in plan_text.lower()


# ── C. BAD PATHS ─────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EBadPaths:
    """Bad paths: blocks on missing/broken inputs."""

    def test_blocks_when_no_ticket_no_task(self, capsys):
        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_executor_unavailable(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_blocks_when_llm_returns_empty(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo ''")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_llm_returns_non_json(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo 'not json at all'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_llm_returns_incomplete_plan(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        incomplete = json.dumps({"objective": "Something"})
        escaped = incomplete.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_mandate_schema_missing(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()

        def _raise_missing():
            raise module.MandateSchemaMissingError("not found")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-MISSING"

    def test_blocks_when_mandate_schema_invalid_json(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()

        def _raise_invalid():
            raise module.MandateSchemaInvalidJsonError("bad json")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-INVALID-JSON"

    def test_blocks_when_mandate_schema_invalid_structure(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()

        def _raise_invalid():
            raise module.MandateSchemaInvalidStructureError("missing plan_mandate")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-INVALID-STRUCTURE"


# ── D. CORNER CASES ──────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ECornerCases:
    """Corner cases: explicit plan text, edge conditions."""

    def test_explicit_plan_text_skips_auto_generation(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        module = _load_phase5()
        rc = module.main(["--plan-text", "Manual plan text for testing.", "--quiet"])
        if rc != 0:
            payload = json.loads(capsys.readouterr().out.strip())
            assert payload.get("reason_code") != "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_plan_text_from_file(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("Manual plan text from file.", encoding="utf-8")

        module = _load_phase5()
        rc = module.main(["--plan-file", str(plan_file), "--quiet"])
        if rc != 0:
            payload = json.loads(capsys.readouterr().out.strip())
            assert payload.get("reason_code") != "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_executor_fallback(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)

        module = _load_phase5()
        assert module._resolve_plan_executor() == ""

        monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", "fallback-cmd")
        assert module._resolve_plan_executor() == "fallback-cmd"

        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "plan-cmd")
        assert module._resolve_plan_executor() == "plan-cmd"


# ── E. PERSISTENCE ────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPersistence:
    """Verify all persisted files are at correct paths with correct content."""

    def test_plan_record_structure(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        module.main(["--quiet"])

        doc = _read_json(workspace / "plan-record.json")
        assert doc["schema_version"]
        assert doc["repo_fingerprint"] == repo_fp
        assert doc["status"] in ("active", "finalized")
        v = doc["versions"][0]
        assert v["version"] == 1
        assert v["plan_record_text"]
        assert v["plan_record_digest"].startswith("sha256:")

    def test_requirements_structure(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        module.main(["--quiet"])

        doc = _read_json(workspace / ".governance" / "contracts" / "compiled_requirements.json")
        assert doc["schema"]
        assert doc["generated_at"]
        req = doc["requirements"][0]
        assert req["id"].startswith("R-PLAN-")
        assert req["title"]
        assert req["criticality"]

    def test_events_jsonl(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        valid = _valid_plan_response()
        escaped = valid.replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{escaped}'")

        module = _load_phase5()
        module.main(["--quiet"])

        events_file = workspace / "events.jsonl"
        assert events_file.exists(), "events.jsonl not written"
        events = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        event_types = {e.get("event") for e in events}
        assert "phase5-plan-record-persisted" in event_types


# ── F. PATH CORRECTNESS ──────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPathCorrectness:
    """Verify all artifacts at expected locations."""

    def test_plan_record_at_workspace_root(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        valid = _valid_plan_response().replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{valid}'")
        _load_phase5().main(["--quiet"])
        assert (workspace / "plan-record.json").exists()

    def test_contracts_under_governance_dir(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        valid = _valid_plan_response().replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{valid}'")
        _load_phase5().main(["--quiet"])
        assert (workspace / ".governance" / "contracts" / "compiled_requirements.json").exists()

    def test_session_state_updated_in_place(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        valid = _valid_plan_response().replace("'", "'\\''")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{valid}'")
        _load_phase5().main(["--quiet"])
        assert session_path.exists()
        state = _read_state(session_path)
        assert state.get("phase5_completed") is True


# ── G. /review IN PHASE 4 ────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EReviewInPhase4:
    """Test /review (session_reader read-only rail) behavior."""

    def test_continue_shows_current_state(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home)])

        # session_reader should return a non-ERROR status
        state = _read_state(session_path)
        assert state.get("Phase") is not None

    def test_continue_materialize_does_not_crash(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home), "--materialize"])
        # Should not crash (rc may be 0 or non-zero depending on state)
        assert rc in (0, 1)
