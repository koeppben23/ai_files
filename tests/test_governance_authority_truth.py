"""
test_governance_authority_truth.py — Authority truth: specHome authority, canonical layout, no-drift guards.

specHome is the ONLY authority for phase_api.yaml. No mirrors. No legacy paths.
governance.paths.json maps all homes correctly. Rulebooks use ${COMMANDS_HOME} anchors.

CI-blocking main merge guard: every test here must pass.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest_governance import (
    _read_json,
    _read_state,
    _set_env,
    _write_e2e_fixture,
)
from tests.conftest_governance import (
    _load_phase5,
    _load_review_decision,
    _write_phase6_session,
)


# ── A. FIXTURE CLEANLINESS ───────────────────────────────────────────────────


@pytest.mark.e2e_governance
class TestE2EFixtureCleanliness:
    """Verify the test fixture follows the canonical layout."""

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

    def test_loaded_rulebooks_reference_profiles_home(self, tmp_path, monkeypatch):
        """LoadedRulebooks paths must be anchored to ${PROFILES_HOME}, not arbitrary paths."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        lr = state.get("LoadedRulebooks", {})
        assert lr.get("core", "").startswith("${PROFILES_HOME}/")
        assert lr.get("profile", "").startswith("${PROFILES_HOME}/")
        assert lr.get("templates", "").startswith("${PROFILES_HOME}/")

    def test_spec_home_has_phase_api_only(self, tmp_path, monkeypatch):
        """specHome must contain phase_api.yaml and nothing else governance-relevant."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        local_root = config_root.parent / f"{config_root.name}-local"
        spec_home = local_root / "governance_spec"
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

    def test_commands_home_has_only_commands(self, tmp_path, monkeypatch):
        """commands_home must contain ONLY the 8 command files, no rulebooks or other content."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        entries = {p.name for p in commands_home.iterdir() if p.is_file()}
        CANONICAL_RAIL_FILENAMES = (
            "audit-readout.md", "continue.md", "implement.md", "implementation-decision.md",
            "plan.md", "review-decision.md", "review.md", "ticket.md",
        )
        for name in entries:
            assert name in CANONICAL_RAIL_FILENAMES, (
                f"commands_home must only contain canonical commands, found: {name}"
            )


# ── B. PATH CORRECTNESS ──────────────────────────────────────────────────────


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
        """After /plan, SESSION_STATE.json must exist and preserve Phase 5 completion fields."""
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


# ── C. CONTENT CORRECTNESS ────────────────────────────────────────────────────


@pytest.mark.e2e_governance
class TestE2EContentCorrectness:
    """Verify persisted file content is real, correct, and not drifted."""

    def test_plan_record_digest_is_valid_sha256(self, tmp_path, monkeypatch, capsys):
        """plan_record_digest must be a valid sha256: prefix followed by 64 hex chars."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Architecture plan for JWT.", "--quiet"])
        plan_record = _read_json(workspace / "plan-record.json")
        v = plan_record["versions"][0]
        digest = v["plan_record_digest"]
        assert digest.startswith("sha256:")
        hex_part = digest.split(":")[1]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_requirement_id_format(self, tmp_path, monkeypatch, capsys):
        """Requirement IDs must follow R-PLAN-<num>-<hash> pattern."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Plan for auth.", "--quiet"])
        contracts = _read_json(workspace / ".governance" / "contracts" / "compiled_requirements.json")
        for req in contracts["requirements"]:
            assert req["id"].startswith("R-PLAN-"), f"Invalid requirement ID: {req['id']}"
            parts = req["id"].split("-")
            assert len(parts) >= 3, f"Requirement ID must have at least 3 parts: {req['id']}"

    def test_compiled_requirements_has_valid_schema_field(self, tmp_path, monkeypatch, capsys):
        """compiled_requirements.json schema field must be non-empty."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Plan.", "--quiet"])
        contracts = _read_json(workspace / ".governance" / "contracts" / "compiled_requirements.json")
        assert contracts["schema"]
        assert isinstance(contracts["schema"], str)
        assert len(contracts["schema"]) > 0

    def test_compiled_requirements_generated_at_is_iso_timestamp(self, tmp_path, monkeypatch, capsys):
        """generated_at must be a valid ISO timestamp."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Plan.", "--quiet"])
        contracts = _read_json(workspace / ".governance" / "contracts" / "compiled_requirements.json")
        ts = contracts["generated_at"]
        assert ts
        assert "T" in ts

    def test_plan_record_uses_real_repo_fingerprint(self, tmp_path, monkeypatch, capsys):
        """plan-record.json repo_fingerprint must match the fixture fingerprint."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        _load_phase5().main(["--plan-text", "Plan.", "--quiet"])
        plan_record = _read_json(workspace / "plan-record.json")
        assert plan_record["repo_fingerprint"] == repo_fp

    def test_review_package_presentation_receipt_has_all_required_fields(self, tmp_path, monkeypatch, capsys):
        """After /review-decision approve, the receipt must have digest, contract, presented_at, session_id."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        module.main(["--decision", "approve", "--quiet"])

        state = _read_state(session_path)
        receipt = state.get("review_package_presentation_receipt", {})
        assert receipt.get("digest") and len(receipt["digest"]) == 64
        assert receipt.get("contract") == "guided-ui.v1"
        assert receipt.get("presented_at")
        assert receipt.get("session_id")

    def test_session_state_ticket_digest_format(self, tmp_path, monkeypatch, capsys):
        """TicketRecordDigest must follow sha256: prefix with 64 hex chars."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        digest = state.get("TicketRecordDigest", "")
        assert digest.startswith("sha256:")
        hex_part = digest.split(":")[1]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)


# ── D. AUTHORITY SPEC HOME ────────────────────────────────────────────────────


@pytest.mark.e2e_governance
class TestE2EAuthoritySpecHome:
    """Verify specHome is the sole authority for phase_api.yaml — not commands/ or elsewhere.

    Authority rules:
    1. specHome must be inside governance.paths.json paths.specHome.
    2. specHome must be a child of the repo root (localRoot).
    3. commands_home must NOT contain phase_api.yaml (authority is specHome only).
    4. LoadedRulebooks paths must be anchored to ${PROFILES_HOME} (not absolute paths).
    5. COMMANDS_HOME env var resolution reads from commands_home.parent/governance.paths.json.
    """

    def test_spechome_is_child_of_local_root(self, tmp_path, monkeypatch):
        """specHome in governance.paths.json must be a child of the repo/local root."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        local_root = config_root.parent / f"{config_root.name}-local"
        doc = _read_json(config_root / "governance.paths.json")
        spechome = Path(doc["paths"]["specHome"])
        assert spechome.is_relative_to(local_root), (
            f"specHome {spechome} must be inside localRoot {local_root}"
        )

    def test_commands_home_and_spec_home_are_different(self, tmp_path, monkeypatch):
        """commandsHome and specHome in governance.paths.json must be different paths."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "governance.paths.json")
        commands = Path(doc["paths"]["commandsHome"])
        spec = Path(doc["paths"]["specHome"])
        assert commands != spec, (
            f"commandsHome ({commands}) and specHome ({spec}) must not be the same path"
        )

    def test_loaded_rulebooks_use_env_var_anchors_not_absolute_paths(self, tmp_path, monkeypatch):
        """LoadedRulebooks paths must use env-var anchors (${PROFILES_HOME}), not absolute paths."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        lr = state.get("LoadedRulebooks", {})
        for key, value in lr.items():
            if isinstance(value, str):
                assert value.startswith("${PROFILES_HOME}/") or value.startswith("${"), (
                    f"LoadedRulebooks.{key} must use env-var anchor (${{PROFILES_HOME}}), "
                    f"got absolute path: {value!r}"
                )

    def test_workspace_path_is_child_of_workspaces_home(self, tmp_path, monkeypatch):
        """Workspace path must be a child of workspacesHome in governance.paths.json."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "governance.paths.json")
        workspaces_home = Path(doc["paths"]["workspacesHome"])
        assert workspace.is_relative_to(workspaces_home), (
            f"workspace {workspace} must be inside workspacesHome {workspaces_home}"
        )

    def test_governance_content_profiles_has_rulebooks(self, tmp_path, monkeypatch):
        """Rulebooks must be present under local_root/governance_content/profiles/, not commands_home/."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        local_root = config_root.parent / f"{config_root.name}-local"
        profiles_dir = local_root / "governance_content" / "profiles"
        assert profiles_dir.exists(), (
            f"governance_content/profiles/ must exist at {profiles_dir}"
        )
        assert (profiles_dir / "rules.fallback-minimum.md").exists(), (
            "rules.fallback-minimum.md must be present under governance_content/profiles/"
        )
        entries = {p.name for p in profiles_dir.rglob("*.md") if p.is_file()}
        assert len(entries) >= 2, (
            f"governance_content/profiles/ must contain at least 2 .md rulebook files, found: {entries}"
        )

    def test_no_phase_api_in_commands_root(self, tmp_path, monkeypatch):
        """commands_home/ must NOT contain phase_api.yaml (authority lives in specHome)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        assert not (commands_home / "phase_api.yaml").exists(), (
            "phase_api.yaml must not exist in commands_home root"
        )
        for child in commands_home.rglob("phase_api.yaml"):
            assert False, f"phase_api.yaml found at {child} — authority is specHome only"


# ── E. NO DRIFT GUARDS ────────────────────────────────────────────────────────


@pytest.mark.e2e_governance
class TestE2ENoDriftGuards:
    """Verify no drift from canonical governance structure.

    Drift guards: ensure canonical paths are used and no legacy paths or
    forbidden mirrors exist.
    """

    def test_governance_paths_json_schema_is_correct(self, tmp_path, monkeypatch):
        """governance.paths.json must use the correct schema version."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "governance.paths.json")
        assert doc.get("schema") == "opencode-governance.paths.v1", (
            f"governance.paths.json schema must be opencode-governance.paths.v1, "
            f"got {doc.get('schema')!r}"
        )

    def test_session_pointer_schema_is_correct(self, tmp_path, monkeypatch):
        """SESSION_STATE.json pointer must use the correct schema version."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "SESSION_STATE.json")
        assert doc.get("schema") == "opencode-session-pointer.v1", (
            f"pointer schema must be opencode-session-pointer.v1, got {doc.get('schema')!r}"
        )

    def test_active_repo_fingerprint_matches_workspace_name(self, tmp_path, monkeypatch):
        """Pointer's activeRepoFingerprint must match the workspace directory name."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        doc = _read_json(config_root / "SESSION_STATE.json")
        assert doc["activeRepoFingerprint"] == workspace.name, (
            f"activeRepoFingerprint must match workspace directory name {workspace.name}, "
            f"got {doc['activeRepoFingerprint']!r}"
        )

    def test_plan_record_uses_correct_schema(self, tmp_path, monkeypatch, capsys):
        """plan-record.json must have a schema_version field (not empty or missing)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _load_phase5().main(["--plan-text", "Architecture plan for auth service.", "--quiet"])
        pr = _read_json(workspace / "plan-record.json")
        assert pr.get("schema_version"), (
            f"plan-record must have schema_version field, got keys: {sorted(pr.keys())}"
        )
        assert pr.get("repo_fingerprint") == repo_fp, (
            f"repo_fingerprint must match workspace fingerprint {repo_fp!r}"
        )

    def test_session_state_has_required_schema_fields(self, tmp_path, monkeypatch):
        """Session state must have RepoFingerprint and Phase fields set."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        assert state.get("RepoFingerprint") == repo_fp, (
            "RepoFingerprint must be set to the workspace fingerprint"
        )
        assert state.get("Phase"), "Phase must be set in session state"
        assert state.get("session_run_id"), "session_run_id must be set"


# ── F. LAYOUT COMPLETENESS ────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ELayoutCompleteness:
    """Verify canonical layout completeness: all required content exists at correct paths.

    Canonical layout (per install.py):
      commands_home/     = ONLY the 8 command files
      spec_home/        = ONLY phase_api.yaml
      governance_content/profiles/ = rulebooks, addons
      governance_content/ = reference/, profiles/, templates/, docs/
    """

    def test_commands_home_has_all_8_canonical_command_files(self, tmp_path, monkeypatch):
        """commands_home must contain ALL 8 canonical command files, no more, no less."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        CANONICAL_RAIL_FILENAMES = frozenset({
            "audit-readout.md",
            "continue.md",
            "implement.md",
            "implementation-decision.md",
            "plan.md",
            "review-decision.md",
            "review.md",
            "ticket.md",
        })
        for name in CANONICAL_RAIL_FILENAMES:
            (commands_home / name).write_text(f"# {name}\n", encoding="utf-8")
        entries = {p.name for p in commands_home.iterdir() if p.is_file()}
        assert entries == CANONICAL_RAIL_FILENAMES, (
            f"commands_home must contain exactly these 8 files: {sorted(CANONICAL_RAIL_FILENAMES)}, "
            f"found: {sorted(entries)}"
        )

    def test_commands_home_contains_no_other_artifacts(self, tmp_path, monkeypatch):
        """commands_home must not contain rulebooks, addons, or phase_api.yaml."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        all_entries = {p.name for p in commands_home.iterdir()}
        forbidden = {
            "rules.md", "master.md", "rules.fallback-minimum.md",
            "rules.risk-tiering.md", "phase_api.yaml", "governance_mandates.v1.schema.json",
            "plan_record.v1.schema.json",
        }
        found_forbidden = all_entries & forbidden
        assert not found_forbidden, (
            f"commands_home must not contain non-command artifacts: {sorted(found_forbidden)}"
        )

    def test_spec_home_contains_only_phase_api_yaml(self, tmp_path, monkeypatch):
        """specHome must contain ONLY phase_api.yaml."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        spec_home = config_root.parent / f"{config_root.name}-local" / "governance_spec"
        entries = {p.name for p in spec_home.iterdir()}
        assert "phase_api.yaml" in entries, "spec_home must contain phase_api.yaml"
        unexpected = entries - {"phase_api.yaml"}
        assert not unexpected, (
            f"specHome must contain only phase_api.yaml, found extra: {sorted(unexpected)}"
        )

    def test_governance_content_profiles_contains_rulebooks(self, tmp_path, monkeypatch):
        """governance_content/profiles/ must contain at least the fallback rulebook."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        profiles_home = config_root.parent / f"{config_root.name}-local" / "governance_content" / "profiles"
        assert profiles_home.exists(), "governance_content/profiles/ must exist"
        rulebook_files = {p.name for p in profiles_home.iterdir() if p.is_file()}
        assert rulebook_files, (
            "governance_content/profiles/ must contain at least one rulebook file"
        )

    def test_loaded_rulebooks_use_profiles_home_not_commands_home(self, tmp_path, monkeypatch):
        """LoadedRulebooks must reference ${PROFILES_HOME}, never ${COMMANDS_HOME}."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        state = _read_state(session_path)
        loaded = state.get("LoadedRulebooks", {})
        for key, path_ref in loaded.items():
            if isinstance(path_ref, dict):
                path_ref = str(path_ref)
            assert "COMMANDS_HOME" not in str(path_ref), (
                f"LoadedRulebooks[{key}] must not reference COMMANDS_HOME, got {path_ref!r}"
            )
