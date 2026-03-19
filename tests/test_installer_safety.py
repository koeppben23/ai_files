from __future__ import annotations

from pathlib import Path

import pytest

from .util import run_install


@pytest.mark.installer
def test_uninstall_preserves_non_owned_files(tmp_path: Path):
    """
    Enforces: strict command-surface allowlist removes non-owned extras under commands/.
    """
    config_root = tmp_path / "opencode-config-nonowned"
    commands = config_root / "commands"
    commands.mkdir(parents=True, exist_ok=True)

    user_file = commands / "USER_NOTE.txt"
    user_file.write_text("do not delete\n", encoding="utf-8")
    assert user_file.exists()

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"
    assert not user_file.exists(), "install must remove non-allowlisted files under commands/"

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"
    assert not user_file.exists(), "uninstall must not recreate non-allowlisted files under commands/"


@pytest.mark.installer
def test_config_root_with_spaces_and_unicode(tmp_path: Path):
    config_root = tmp_path / "Config Root Ünicode 你好"

    r = run_install(["--dry-run", "--config-root", str(config_root)])
    assert r.returncode == 0, f"dry-run failed:\n{r.stderr}\n{r.stdout}"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"


@pytest.mark.installer
def test_force_uninstall_without_manifest_removes_all_command_files(tmp_path: Path):
    config_root = tmp_path / "opencode-config-missing-manifest"
    commands = config_root / "commands"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    user_profile = commands / "profiles" / "custom-user-rule.md"
    user_diag = commands / "governance" / "custom-user-note.txt"
    user_profile.parent.mkdir(parents=True, exist_ok=True)
    user_diag.parent.mkdir(parents=True, exist_ok=True)
    user_profile.write_text("# user custom profile\n", encoding="utf-8")
    user_diag.write_text("keep me\n", encoding="utf-8")

    manifest = config_root / "INSTALL_MANIFEST.json"
    assert manifest.exists(), "expected installer manifest to exist after install"
    manifest.unlink()

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall with missing manifest failed:\n{r.stderr}\n{r.stdout}"

    assert not user_profile.exists(), "fallback uninstall must purge every file under commands/"
    assert not user_diag.exists(), "fallback uninstall must purge every file under commands/"


@pytest.mark.installer
def test_uninstall_removes_empty_profiles_addons_and_workspaces_dirs(tmp_path: Path):
    config_root = tmp_path / "opencode-config-empty-dirs"
    local_root = tmp_path / "opencode-config-empty-dirs-local"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    profiles_addons = local_root / "governance_content" / "profiles" / "addons"
    workspaces = config_root / "workspaces"
    assert profiles_addons.exists() and profiles_addons.is_dir()
    assert workspaces.exists() and workspaces.is_dir()

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert not profiles_addons.exists(), "local payload files must be removed on uninstall"
    assert not workspaces.exists(), "empty workspaces dir should be removed on uninstall"


@pytest.mark.installer
def test_uninstall_purges_runtime_error_logs_but_preserves_non_matching_user_logs(tmp_path: Path):
    config_root = tmp_path / "opencode-config-error-logs"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    global_logs = config_root / "commands" / "logs"
    workspace_logs = config_root / "workspaces" / "demo-repo-logs" / "logs"
    global_logs.mkdir(parents=True, exist_ok=True)
    workspace_logs.mkdir(parents=True, exist_ok=True)

    global_error = global_logs / "error.log.jsonl"
    global_index = config_root / "logs" / "errors-index.json"
    legacy_global_error = config_root / "logs" / "errors-global-2026-02-07.jsonl"
    workspace_error = workspace_logs / "error.log.jsonl"
    workspace_index = workspace_logs / "errors-index.json"
    user_note = global_logs / "user-note.txt"
    global_index.parent.mkdir(parents=True, exist_ok=True)

    global_error.write_text('{"level":"error"}\n', encoding="utf-8")
    legacy_global_error.write_text('{"level":"error"}\n', encoding="utf-8")
    global_index.write_text('{"schema":"opencode.error-index.v1"}\n', encoding="utf-8")
    workspace_error.write_text('{"level":"error"}\n', encoding="utf-8")
    workspace_index.write_text('{"schema":"opencode.error-index.v1"}\n', encoding="utf-8")
    user_note.write_text("keep me\n", encoding="utf-8")

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert not global_error.exists(), "global runtime error log should be purged on uninstall"
    assert not legacy_global_error.exists(), "legacy global runtime error log should be purged on uninstall"
    assert not global_index.exists(), "global runtime error index should be purged on uninstall"
    assert not workspace_error.exists(), "workspace runtime error log should be purged on uninstall"
    assert not workspace_index.exists(), "workspace runtime error index should be purged on uninstall"
    assert not user_note.exists(), "all files under commands/ must be removed on uninstall"


@pytest.mark.installer
def test_uninstall_with_keep_error_logs_flag_preserves_runtime_error_logs(tmp_path: Path):
    config_root = tmp_path / "opencode-config-error-logs-keep"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    workspace_logs = config_root / "workspaces" / "repo-keep-logs" / "logs"
    workspace_logs.mkdir(parents=True, exist_ok=True)
    global_error = workspace_logs / "error.log.jsonl"
    global_error.write_text('{"level":"error"}\n', encoding="utf-8")

    r = run_install([
        "--uninstall",
        "--force",
        "--keep-error-logs",
        "--config-root",
        str(config_root),
    ])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert global_error.exists(), "runtime error log should be preserved when --keep-error-logs is set"


# ---------------------------------------------------------------------------
# Uninstall: runtime workspace state cleanup
# ---------------------------------------------------------------------------


def _seed_workspace_state(config_root: Path) -> dict[str, Path]:
    """Create a realistic set of runtime workspace state files and return a
    dict mapping descriptive keys to their paths."""
    workspaces = config_root / "workspaces"
    fp = "a1b2c3d4e5f6a1b2c3d4e5f6"  # fake 24-hex fingerprint
    ws = workspaces / fp
    ws.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}

    # activation_intent.json at config root level
    ai = config_root / "governance.activation_intent.json"
    ai.write_text('{"schema":"opencode.activation_intent.v1","discovery_scope":"full"}', encoding="utf-8")
    files["activation_intent"] = ai

    # global SESSION_STATE pointer
    gp = config_root / "SESSION_STATE.json"
    gp.write_text('{"pointer": true}', encoding="utf-8")
    files["global_pointer"] = gp

    # per-workspace flat artifacts
    artifact_names = [
        "SESSION_STATE.json",
        "repo-identity-map.yaml",
        "repo-cache.yaml",
        "repo-map-digest.md",
        "workspace-memory.yaml",
        "decision-pack.md",
        "business-rules.md",
        "business-rules-status.md",
        "plan-record.json",
    ]
    for name in artifact_names:
        f = ws / name
        f.write_text(f"# {name}\n", encoding="utf-8")
        files[f"ws/{name}"] = f

    # per-workspace subtree dirs
    archive = ws / "plan-record-archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "plan-record-2026-01-01.json").write_text("{}", encoding="utf-8")
    files["ws/plan-record-archive"] = archive

    evidence = ws / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "coverage.json").write_text("{}", encoding="utf-8")
    files["ws/evidence"] = evidence

    lock_dir = ws / ".lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "owner.json").write_text('{"pid":1234}', encoding="utf-8")
    files["ws/.lock"] = lock_dir

    files["workspace_dir"] = ws
    files["workspaces_dir"] = workspaces
    return files


@pytest.mark.installer
def test_uninstall_removes_activation_intent_json(tmp_path: Path):
    """governance.activation_intent.json must be removed on uninstall."""
    config_root = tmp_path / "opencode-config-ai"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    state = _seed_workspace_state(config_root)

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert not state["activation_intent"].exists(), (
        "governance.activation_intent.json must be removed on uninstall"
    )


@pytest.mark.installer
def test_uninstall_removes_global_session_state_pointer(tmp_path: Path):
    """Global SESSION_STATE.json pointer must be removed on uninstall."""
    config_root = tmp_path / "opencode-config-gp"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    state = _seed_workspace_state(config_root)

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert not state["global_pointer"].exists(), (
        "Global SESSION_STATE.json pointer must be removed on uninstall"
    )


@pytest.mark.installer
def test_uninstall_removes_all_workspace_artifacts(tmp_path: Path):
    """All known workspace artifacts (flat files + subtrees) must be removed."""
    config_root = tmp_path / "opencode-config-ws"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    state = _seed_workspace_state(config_root)

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    # Check flat artifact files are gone
    artifact_keys = [
        "ws/SESSION_STATE.json",
        "ws/repo-identity-map.yaml",
        "ws/repo-cache.yaml",
        "ws/repo-map-digest.md",
        "ws/workspace-memory.yaml",
        "ws/decision-pack.md",
        "ws/business-rules.md",
        "ws/business-rules-status.md",
        "ws/plan-record.json",
    ]
    for key in artifact_keys:
        assert not state[key].exists(), f"{key} must be removed on uninstall"

    # Check subtree dirs are gone
    assert not state["ws/plan-record-archive"].exists(), "plan-record-archive/ must be removed on uninstall"
    assert not state["ws/evidence"].exists(), "evidence/ must be removed on uninstall"
    assert not state["ws/.lock"].exists(), ".lock/ must be removed on uninstall"

    # Workspace dir should be removed (now empty)
    assert not state["workspace_dir"].exists(), "empty workspace dir must be removed on uninstall"

    # Workspaces root should be removed (now empty)
    assert not state["workspaces_dir"].exists(), "empty workspaces dir must be removed on uninstall"


@pytest.mark.installer
def test_uninstall_preserves_workspace_state_with_keep_flag(tmp_path: Path):
    """--keep-workspace-state must preserve all workspace state files."""
    config_root = tmp_path / "opencode-config-keep-ws"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    state = _seed_workspace_state(config_root)

    r = run_install([
        "--uninstall",
        "--force",
        "--keep-workspace-state",
        "--config-root",
        str(config_root),
    ])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    # All state files must still exist
    assert state["activation_intent"].exists(), (
        "activation_intent must be preserved with --keep-workspace-state"
    )
    assert state["global_pointer"].exists(), (
        "global pointer must be preserved with --keep-workspace-state"
    )
    assert state["ws/SESSION_STATE.json"].exists(), (
        "workspace SESSION_STATE.json must be preserved with --keep-workspace-state"
    )
    assert state["ws/plan-record.json"].exists(), (
        "plan-record.json must be preserved with --keep-workspace-state"
    )
    assert state["ws/plan-record-archive"].exists(), (
        "plan-record-archive/ must be preserved with --keep-workspace-state"
    )


@pytest.mark.installer
def test_uninstall_preserves_unknown_files_in_workspace(tmp_path: Path):
    """Non-governance files in workspace dirs must survive uninstall."""
    config_root = tmp_path / "opencode-config-ws-user"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    state = _seed_workspace_state(config_root)

    # Add a user-owned file that is NOT a known governance artifact
    user_note = state["workspace_dir"] / "my-custom-notes.txt"
    user_note.write_text("user-owned, do not delete\n", encoding="utf-8")

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert user_note.exists(), "non-governance files in workspace must survive uninstall"
    # workspace dir should still exist because it contains the user file
    assert state["workspace_dir"].exists(), "workspace dir with user files must not be removed"


@pytest.mark.installer
def test_uninstall_handles_multiple_workspaces(tmp_path: Path):
    """Uninstall must clean state from all workspace fingerprint directories."""
    config_root = tmp_path / "opencode-config-multi-ws"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    workspaces = config_root / "workspaces"
    fps = ["aaa111bbb222ccc333ddd444", "eee555fff666000111222333"]
    ws_sessions = []
    for fp in fps:
        ws = workspaces / fp
        ws.mkdir(parents=True, exist_ok=True)
        ss = ws / "SESSION_STATE.json"
        ss.write_text('{"fp":"' + fp + '"}', encoding="utf-8")
        ai = ws / "repo-identity-map.yaml"
        ai.write_text("repo: test\n", encoding="utf-8")
        pr = ws / "plan-record.json"
        pr.write_text('{"schema":"plan-record.v1"}', encoding="utf-8")
        ws_sessions.append((ss, ai, pr, ws))

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    for ss, ai, pr, ws in ws_sessions:
        assert not ss.exists(), f"SESSION_STATE.json must be removed for {ws.name}"
        assert not ai.exists(), f"repo-identity-map.yaml must be removed for {ws.name}"
        assert not pr.exists(), f"plan-record.json must be removed for {ws.name}"
        assert not ws.exists(), f"empty workspace dir must be removed for {ws.name}"


@pytest.mark.installer
def test_uninstall_removes_installer_backups_when_empty(tmp_path: Path):
    """Empty .installer-backups/ directory must be removed on uninstall."""
    config_root = tmp_path / "opencode-config-backups"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    backup_dir = config_root / ".installer-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert not backup_dir.exists(), "empty .installer-backups/ should be removed on uninstall"


@pytest.mark.installer
def test_uninstall_fallback_also_purges_workspace_state(tmp_path: Path):
    """Even without manifest (--force fallback), workspace state must be purged."""
    config_root = tmp_path / "opencode-config-fallback-ws"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    state = _seed_workspace_state(config_root)

    # Remove manifest to trigger fallback path
    manifest = config_root / "INSTALL_MANIFEST.json"
    assert manifest.exists()
    manifest.unlink()

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall (fallback) failed:\n{r.stderr}\n{r.stdout}"

    assert not state["activation_intent"].exists(), (
        "activation_intent must be removed even in fallback uninstall"
    )
    assert not state["global_pointer"].exists(), (
        "global pointer must be removed even in fallback uninstall"
    )
    assert not state["ws/SESSION_STATE.json"].exists(), (
        "workspace SESSION_STATE.json must be removed even in fallback uninstall"
    )


@pytest.mark.installer
def test_uninstall_dry_run_does_not_remove_workspace_state(tmp_path: Path):
    """--dry-run must NOT actually delete workspace state files."""
    config_root = tmp_path / "opencode-config-dryrun-ws"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    state = _seed_workspace_state(config_root)

    r = run_install(["--uninstall", "--force", "--dry-run", "--config-root", str(config_root)])
    assert r.returncode == 0, f"dry-run uninstall failed:\n{r.stderr}\n{r.stdout}"

    # All state files must still exist after dry-run
    assert state["activation_intent"].exists(), "dry-run must not delete activation_intent"
    assert state["global_pointer"].exists(), "dry-run must not delete global pointer"
    assert state["ws/SESSION_STATE.json"].exists(), "dry-run must not delete workspace SESSION_STATE"
    assert state["ws/plan-record.json"].exists(), "dry-run must not delete plan-record.json"
    assert state["ws/plan-record-archive"].exists(), "dry-run must not delete plan-record-archive/"


@pytest.mark.installer
def test_uninstall_preserves_opencode_json(tmp_path: Path):
    """opencode.json must NEVER be deleted on uninstall.

    opencode.json is user/team configuration that may be shared across
    team members and checked into version control.  It must survive both
    manifest-based and fallback uninstall paths.
    """
    config_root = tmp_path / "opencode-config-preserve-oj"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    # The installer creates/merges opencode.json during install.
    # If it doesn't exist yet (e.g. minimal fixture), create one manually.
    oj = config_root / "opencode.json"
    if not oj.exists():
        oj.write_text('{"customInstructions": ["commands/master.md"]}', encoding="utf-8")
    assert oj.exists(), "pre-condition: opencode.json must exist before uninstall"

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert oj.exists(), (
        "opencode.json must be preserved after uninstall — "
        "it is user/team configuration that other users may depend on"
    )


@pytest.mark.installer
def test_uninstall_preserves_opencode_json_fallback_path(tmp_path: Path):
    """opencode.json must also survive the fallback (no-manifest) uninstall path."""
    config_root = tmp_path / "opencode-config-preserve-oj-fallback"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    oj = config_root / "opencode.json"
    if not oj.exists():
        oj.write_text('{"customInstructions": ["commands/master.md"]}', encoding="utf-8")
    assert oj.exists(), "pre-condition: opencode.json must exist before uninstall"

    # Remove manifest to force fallback path
    manifest = config_root / "INSTALL_MANIFEST.json"
    if manifest.exists():
        manifest.unlink()

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    # Fallback path exits with 0 on success
    assert oj.exists(), (
        "opencode.json must be preserved after fallback uninstall — "
        "it is user/team configuration that other users may depend on"
    )
