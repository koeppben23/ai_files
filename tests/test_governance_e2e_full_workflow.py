"""
test_governance_e2e_full_workflow.py — E2E governance runtime tests.

Tests the governance runtime entrypoints and routing chains in a controlled
fixture environment (no real installer, no real workspace).

Test categories:
  A. FIXTURE CLEANLINESS  — governance.paths.json and specHome layout
  B. COMMAND CHAINS       — /plan with explicit plan text; routing assertions
  C. PATH CORRECTNESS     — artifacts written at correct canonical locations
  D. BAD PATHS            — blocks on missing/broken inputs
  E. CORNER CASES         — explicit plan text, file input, executor fallback
  F. SESSION READER       — --materialize traverses Phase 5 sub-gates

Marked @pytest.mark.e2e_governance — runs on CI (governance-e2e job),
blocks on main merge if any test fails.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from .util import REPO_ROOT, get_phase_api_path, write_governance_paths


# ── Module Loaders ───────────────────────────────────────────────────────

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


# ── Helpers ──────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_state(session_path: Path) -> dict:
    return _read_json(session_path).get("SESSION_STATE", {})


def _write_rulebooks(commands_home: Path):
    """Write rulebook files at canonical paths under commands_home.

    Rulebooks live under commands_home/rulesets/ (bootstrap baseline convention).
    """
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


def _write_e2e_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, Path]:
    """Write a complete E2E fixture using the canonical layout.

    Layout:
      config_root/governance.paths.json  — path manifest
      config_root/commands/              — command surface (NOT spec authority)
      config_root/governance_spec/       — specHome (contains phase_api.yaml ONLY)
      config_root/workspaces/<fp>/       — workspace with SESSION_STATE.json

    Key invariants:
      - phase_api.yaml is ONLY in specHome (not in commands_home)
      - SSOT sources are NOT mirrored into commands_home
      - Rulebooks are under commands_home/rulesets/ (bootstrap convention)
      - governance.paths.json maps all homes correctly
    """
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

    (spec_home / "phase_api.yaml").write_text(
        get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8"
    )

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
                "core": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.md",
                "templates": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.md",
                "addons": {"riskTiering": "${COMMANDS_HOME}/rulesets/profiles/rules.risk-tiering.md"},
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.md",
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


# ── A. FIXTURE CLEANLINESS ─────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EFixtureCleanliness:
    """Verify the test fixture itself follows the canonical layout."""

    def test_governance_paths_json_has_all_keys(self, tmp_path, monkeypatch):
        """governance.paths.json must have every required home key."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "governance.paths.json")
        assert doc["schema"] == "opencode-governance.paths.v1"
        for key in ("commandsHome", "workspacesHome", "configRoot", "specHome"):
            assert key in doc["paths"], f"missing path key: {key}"

    def test_session_pointer_schema_and_references(self, tmp_path, monkeypatch):
        """Pointer must reference an existing workspace session state file."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "SESSION_STATE.json")
        assert doc["schema"] == "opencode-session-pointer.v1"
        assert doc["activeRepoFingerprint"] == repo_fp
        assert Path(doc["activeSessionStateFile"]).exists()
        assert doc["activeSessionStateFile"] == str(session_path)

    def test_workspace_session_state_has_required_fields(self, tmp_path, monkeypatch):
        """Session state at workspace root must have Phase 5 fields and all persistence flags."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        assert state.get("Phase") == "5-ArchitectureReview"
        assert state.get("PersistenceCommitted") is True
        assert state.get("WorkspaceReadyGateCommitted") is True
        assert state.get("WorkspaceArtifactsCommitted") is True
        assert state.get("PointerVerified") is True
        assert state.get("Ticket") and state.get("Task")

    def test_loaded_rulebooks_reference_commands_home(self, tmp_path, monkeypatch):
        """LoadedRulebooks paths must be anchored to ${COMMANDS_HOME}, not arbitrary paths."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        lr = state.get("LoadedRulebooks", {})
        assert lr.get("core", "").startswith("${COMMANDS_HOME}/")
        assert lr.get("profile", "").startswith("${COMMANDS_HOME}/")
        assert lr.get("templates", "").startswith("${COMMANDS_HOME}/")

    def test_spec_home_has_phase_api_only(self, tmp_path, monkeypatch):
        """specHome must contain phase_api.yaml and nothing else governance-relevant."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        spec_home = config_root / "governance_spec"
        assert (spec_home / "phase_api.yaml").exists()
        entries = {p.name for p in spec_home.iterdir()}
        assert "phase_api.yaml" in entries
        assert "rules.md" not in entries
        assert "master.md" not in entries

    def test_commands_home_has_no_phase_api(self, tmp_path, monkeypatch):
        """commands_home must NOT contain phase_api.yaml (spec authority is specHome only)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        assert not (commands_home / "phase_api.yaml").exists(), (
            "commands_home/phase_api.yaml must not exist; spec authority lives in specHome"
        )

    def test_commands_home_has_rulebooks(self, tmp_path, monkeypatch):
        """Rulebooks must be present under commands_home/rulesets/."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        assert (commands_home / "rulesets" / "profiles" / "rules.fallback-minimum.md").exists()
        assert (commands_home / "rulesets" / "profiles" / "rules.risk-tiering.md").exists()


# ── B. COMMAND CHAINS ───────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ECommandChains:
    """Test /plan with explicit plan text through the governance routing chain."""

    def test_plan_explicit_text_persists_and_routes(self, tmp_path, monkeypatch, capsys):
        """--plan-text produces plan-record.json and updates session state Phase."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        rc = module.main(["--plan-text", "Architecture plan: add JWT /auth/login endpoint.", "--quiet"])
        assert rc == 0, f"/plan returned {rc}"

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "ok"
        assert payload["reason"] == "phase5-plan-record-persisted"
        assert payload.get("self_review_iterations_met") is True
        assert payload.get("phase5_completed") is True

    def test_plan_record_structure_after_persist(self, tmp_path, monkeypatch, capsys):
        """plan-record.json must have correct schema: schema_version, repo_fingerprint, status, versions."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Architecture plan v1.", "--quiet"])

        plan_record = _read_json(workspace / "plan-record.json")
        assert plan_record["schema_version"]
        assert plan_record["repo_fingerprint"] == repo_fp
        assert plan_record["status"] in ("active", "finalized")
        v = plan_record["versions"][0]
        assert v["version"] == 1
        assert v["plan_record_text"]
        assert v["plan_record_digest"].startswith("sha256:")

    def test_session_state_updated_after_plan(self, tmp_path, monkeypatch, capsys):
        """After /plan, session state must have Phase 5 completion markers and plan record fields.

        Note: self_review_iterations is in the stdout payload, not the persisted state
        (kernel routing overwrites the state with the routed phase). We verify
        phase5_completed and PlanRecordVersions which are preserved through routing.
        """
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Architecture plan v1.", "--quiet"])

        state = _read_state(session_path)
        assert state.get("phase5_completed") is True
        assert state.get("PlanRecordVersions", 0) >= 1
        assert state.get("requirement_contracts_present") is True
        assert state.get("PlanRecordStatus") == "active"

    def test_requirements_structure(self, tmp_path, monkeypatch, capsys):
        """compiled_requirements.json must have schema, generated_at, and requirement entries."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Architecture plan v1.", "--quiet"])

        contracts = _read_json(workspace / ".governance" / "contracts" / "compiled_requirements.json")
        assert contracts["schema"]
        assert contracts["generated_at"]
        req = contracts["requirements"][0]
        assert req["id"].startswith("R-PLAN-")
        assert req["title"]
        assert req["criticality"]

    def test_plan_text_from_file_persists(self, tmp_path, monkeypatch, capsys):
        """--plan-file reads plan text from a file and persists it."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("Plan from file input.", encoding="utf-8")

        module = _load_phase5()
        rc = module.main(["--plan-file", str(plan_file), "--quiet"])
        assert rc == 0

        plan_record = _read_json(workspace / "plan-record.json")
        assert "Plan from file input" in plan_record["versions"][0]["plan_record_text"]

    def test_events_jsonl_records_phase5_event(self, tmp_path, monkeypatch, capsys):
        """events.jsonl must contain a phase5-plan-record-persisted event."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Plan for test.", "--quiet"])

        events_file = workspace / "events.jsonl"
        assert events_file.exists()
        events = [
            json.loads(l)
            for l in events_file.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        event_types = {e.get("event") for e in events}
        assert "phase5-plan-record-persisted" in event_types


# ── C. PATH CORRECTNESS ─────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPathCorrectness:
    """Verify artifacts land at the correct canonical locations."""

    def test_plan_record_at_workspace_root(self, tmp_path, monkeypatch, capsys):
        """plan-record.json must be at <workspace>/plan-record.json."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Plan.", "--quiet"])
        assert (workspace / "plan-record.json").exists()

    def test_contracts_under_governance_dir(self, tmp_path, monkeypatch, capsys):
        """compiled_requirements.json must be at <workspace>/.governance/contracts/."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Plan.", "--quiet"])
        assert (workspace / ".governance" / "contracts" / "compiled_requirements.json").exists()

    def test_session_state_preserves_phase5_fields_after_plan(self, tmp_path, monkeypatch, capsys):
        """After /plan, SESSION_STATE.json must exist and preserve Phase 5 completion fields.

        The kernel may overwrite the Phase field with the routed phase (e.g. Phase 1.1
        if workspace is not ready), but Phase 5 fields set before routing must persist.
        """
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Plan.", "--quiet"])

        assert session_path.exists()
        state = _read_state(session_path)
        assert state.get("phase5_completed") is True
        assert state.get("PlanRecordVersions", 0) >= 1

    def test_pointer_unchanged_after_plan(self, tmp_path, monkeypatch, capsys):
        """Session pointer at config_root/SESSION_STATE.json must not be modified by /plan."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        pointer_before = _read_json(config_root / "SESSION_STATE.json")
        _load_phase5().main(["--plan-text", "Plan.", "--quiet"])
        pointer_after = _read_json(config_root / "SESSION_STATE.json")

        assert pointer_before["schema"] == pointer_after["schema"]
        assert pointer_before["activeRepoFingerprint"] == pointer_after["activeRepoFingerprint"]


# ── D. BAD PATHS ────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EBadPaths:
    """Bad paths: /plan must block on missing or broken inputs."""

    def test_blocks_when_executor_unavailable(self, tmp_path, monkeypatch, capsys):
        """Without OPENCODE_PLAN_LLM_CMD or OPENCODE_IMPLEMENT_LLM_CMD, /plan auto-generate fails."""
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
        """When LLM executor returns empty string, /plan must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo ''")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_llm_returns_non_json(self, tmp_path, monkeypatch, capsys):
        """When LLM executor returns non-JSON, /plan must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo 'not json at all'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_llm_returns_incomplete_plan(self, tmp_path, monkeypatch, capsys):
        """When LLM returns JSON missing mandatory planOutputSchema fields, /plan must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        incomplete = json.dumps({"objective": "Something"})
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{incomplete}'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_mandate_schema_missing(self, tmp_path, monkeypatch, capsys):
        """When mandate schema is absent, /plan auto-generate must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{\"objective\":\"x\"}'")

        module = _load_phase5()

        def _raise_missing():
            raise module.MandateSchemaMissingError("not found")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-MISSING"

    def test_blocks_when_mandate_schema_invalid_json(self, tmp_path, monkeypatch, capsys):
        """When mandate schema is corrupt JSON, /plan auto-generate must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{\"objective\":\"x\"}'")

        module = _load_phase5()

        def _raise_invalid():
            raise module.MandateSchemaInvalidJsonError("bad json")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-INVALID-JSON"

    def test_blocks_when_mandate_schema_invalid_structure(self, tmp_path, monkeypatch, capsys):
        """When mandate schema lacks plan_mandate block, /plan auto-generate must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{\"objective\":\"x\"}'")

        module = _load_phase5()

        def _raise_invalid():
            raise module.MandateSchemaInvalidStructureError("missing plan_mandate")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-INVALID-STRUCTURE"


# ── E. CORNER CASES ────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ECornerCases:
    """Corner cases: explicit inputs, executor fallback, edge conditions."""

    def test_executor_fallback_to_implement_llm_cmd(self, tmp_path, monkeypatch):
        """_resolve_plan_executor falls back to OPENCODE_IMPLEMENT_LLM_CMD when OPENCODE_PLAN_LLM_CMD is unset."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", "fallback-cmd")
        assert module._resolve_plan_executor() == "fallback-cmd"

        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "plan-cmd")
        assert module._resolve_plan_executor() == "plan-cmd"

    def test_explicit_plan_text_skips_auto_generation(self, tmp_path, monkeypatch, capsys):
        """--plan-text must skip auto-generate path and not require LLM executor."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        module = _load_phase5()
        rc = module.main(["--plan-text", "Manual plan text.", "--quiet"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "phase5-plan-record-persisted"

    def test_plan_file_input_works_without_llm_executor(self, tmp_path, monkeypatch, capsys):
        """--plan-file must work without LLM executor available."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("Plan text from file.", encoding="utf-8")

        module = _load_phase5()
        rc = module.main(["--plan-file", str(plan_file), "--quiet"])
        assert rc == 0


# ── F. SESSION READER ───────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ESessionReader:
    """session_reader --materialize traverses Phase 5 sub-gates toward Phase 6."""

    def test_materialize_does_not_crash_from_phase5(self, tmp_path, monkeypatch):
        """--materialize must not raise on a Phase 5 session."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home), "--materialize"])
        assert rc in (0, 1)

    def test_readonly_shows_phase5_state(self, tmp_path, monkeypatch):
        """Without --materialize, session_reader must return the Phase 5 state."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home)])

        state = _read_state(session_path)
        assert state.get("Phase") is not None
        assert state.get("Phase") == "5-ArchitectureReview"
        assert rc in (0, 1)
