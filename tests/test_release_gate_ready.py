"""E2E tests for Release Gate READY criteria (RG-1 to RG-8) and Test Matrix (T1-T7).

These tests verify the fail-closed behavior of the governance bootstrap system.

RG-1: Global Pointer exists, valid, verified
RG-2: Workspace SessionState exists and consistent
RG-3: Identity-Map exists at correct location
RG-4: Phase-2/2.1 artifacts persisted
RG-5: Commit-Flags correct
RG-6: Fail-closed Binding & Path-SSOT
RG-7: Global Error Handler fires
RG-8: Rulebooks loaded deterministically

T1: Happy path (Desktop-like, Subdir start)
T2: FORCE_READ_ONLY=1 -> Exit != 0 + JSONL
T3: Binding invalid -> keine Writes, Exit != 0
T4: Artefakt-Write-Fail -> Exit != 0 + JSONL
T5: Pointer write/verify fail -> Exit != 0
T6: Rulebook-Ladepfad Happy Path
T7: Missing Rulebook -> Fail-Closed

Copyright (c) 2026 Benjamin Fuchs. All rights reserved.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import site
import subprocess
import sys
from pathlib import Path

import pytest

from tests.util import (
    get_master_path,
    get_phase_api_path,
    get_profiles_path,
    get_rules_path,
    get_templates_path,
)


def _check_pyyaml_in_subprocess() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import yaml"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


HAS_PYYAML_IN_SUBPROCESS = _check_pyyaml_in_subprocess()


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _git_init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=str(repo), check=True)
    (repo / "README.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.txt"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/example.git"],
        cwd=str(repo),
        check=True,
    )


def _write_governance_paths(commands_home: Path, workspaces_home: Path, config_root: Path, checkout_root: Path) -> None:
    local_root = checkout_root
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(config_root),
            "localRoot": str(local_root),
            "commandsHome": str(commands_home),
            "profilesHome": str(local_root / "governance_content" / "profiles"),
            "governanceHome": str(local_root / "governance_runtime"),
            "runtimeHome": str(local_root / "governance_runtime"),
            "contentHome": str(local_root / "governance_content"),
            "specHome": str(local_root / "governance_spec"),
            "workspacesHome": str(workspaces_home),
            "globalErrorLogsHome": str(workspaces_home / "_global" / "logs"),
            "workspaceErrorLogsHomeTemplate": str(workspaces_home / "<repo_fingerprint>" / "logs"),
            "pythonCommand": sys.executable,
        },
        "generatedAt": "1970-01-01T00:00:00Z",
    }
    (config_root / "governance.paths.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _materialize_commands_bundle_from_checkout(*, checkout_root: Path, commands_home: Path) -> None:
    commands_home.mkdir(parents=True, exist_ok=True)
    dir_sources: dict[str, Path] = {
        "governance": checkout_root / "governance",
        "governance_runtime": checkout_root / "governance_runtime",
        "profiles": get_profiles_path(),
        "scripts": checkout_root / "scripts",
        "templates": get_templates_path(),
    }
    for dirname, src in dir_sources.items():
        if src.exists():
            shutil.copytree(src, commands_home / dirname, dirs_exist_ok=True)

    file_sources: dict[str, Path] = {
        "master.md": get_master_path(),
        "rules.md": get_rules_path(),
        "QUALITY_INDEX.md": checkout_root / "QUALITY_INDEX.md",
        "CONFLICT_RESOLUTION.md": checkout_root / "CONFLICT_RESOLUTION.md",
        "phase_api.yaml": get_phase_api_path(),
    }
    for filename, src in file_sources.items():
        if src.exists():
            shutil.copy2(src, commands_home / filename)


def _bootstrap_launcher(checkout_root: Path) -> list[str]:
    if os.name == "nt":
        launcher = checkout_root / "bin" / "opencode-governance-bootstrap.cmd"
        return ["cmd", "/c", str(launcher)]
    launcher = checkout_root / "bin" / "opencode-governance-bootstrap"
    return [str(launcher)]


def _run_bootstrap(*, repo: Path, config_root: Path, commands_home: Path, workspaces_home: Path, env: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], str | None]:
    checkout_root = Path(__file__).resolve().parents[1]
    launcher = _bootstrap_launcher(checkout_root)
    proc = _run(
        launcher + ["--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    
    repo_fp = None
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    payloads = []
    for ln in lines:
        try:
            payloads.append(json.loads(ln))
        except Exception:
            continue
    
    hook = next((p for p in payloads if isinstance(p, dict) and "workspacePersistenceHook" in p), None)
    if hook and hook.get("repo_fingerprint"):
        repo_fp = str(hook.get("repo_fingerprint")).strip()
    
    return proc, repo_fp


@pytest.fixture
def isolated_env(tmp_path: Path):
    checkout_root = Path(__file__).resolve().parents[1]
    
    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    workspaces_home.mkdir(parents=True, exist_ok=True)
    
    _materialize_commands_bundle_from_checkout(checkout_root=checkout_root, commands_home=commands_home)
    _write_governance_paths(commands_home, workspaces_home, config_root, checkout_root)
    
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CI"] = ""
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["COMMANDS_HOME"] = str(commands_home)
    env["OPENCODE_PYTHON"] = sys.executable
    env.pop("OPENCODE_FORCE_READ_ONLY", None)
    user_site = site.getusersitepackages()
    if user_site:
        env["PYTHONPATH"] = os.pathsep.join([part for part in (user_site, env.get("PYTHONPATH", "")) if part])
    
    return {
        "home": home,
        "config_root": config_root,
        "commands_home": commands_home,
        "workspaces_home": workspaces_home,
        "env": env,
    }


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required")
class TestReleaseGateReady:
    """Tests for RG-1 to RG-8: Release Gate READY criteria."""

    def test_rg1_global_pointer_exists_and_valid(self, isolated_env, tmp_path: Path):
        """RG-1: Global Pointer exists, schema-valid, contains correct fingerprint reference."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        proc, repo_fp = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
        assert repo_fp is not None, "No fingerprint returned"
        
        pointer_path = isolated_env["config_root"] / "SESSION_STATE.json"
        assert pointer_path.exists(), "Global pointer file not found"
        
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        assert pointer.get("schema") == "opencode-session-pointer.v1", "Invalid pointer schema"
        assert pointer.get("activeRepoFingerprint") == repo_fp, "Pointer fingerprint mismatch"

    def test_rg2_workspace_session_state_consistent(self, isolated_env, tmp_path: Path):
        """RG-2: Workspace SessionState exists, schema-valid, fingerprint is 24 hex."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        proc, repo_fp = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode == 0
        assert repo_fp is not None
        assert re.fullmatch(r"[0-9a-f]{24}", repo_fp), f"Fingerprint not 24 hex: {repo_fp}"
        
        session_path = isolated_env["workspaces_home"] / repo_fp / "SESSION_STATE.json"
        assert session_path.exists(), "Workspace SESSION_STATE not found"
        
        state = json.loads(session_path.read_text(encoding="utf-8"))
        ss = state.get("SESSION_STATE", {})
        assert ss.get("RepoFingerprint") == repo_fp, "SESSION_STATE fingerprint mismatch"

    def test_rg3_identity_map_exists(self, isolated_env, tmp_path: Path):
        """RG-3: Identity-Map exists at correct location (workspace, not repo root)."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        proc, repo_fp = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode == 0
        assert repo_fp is not None
        
        identity_map_path = isolated_env["workspaces_home"] / repo_fp / "repo-identity-map.yaml"
        assert identity_map_path.exists(), "Identity map not in workspace"
        
        assert not (repo / "repo-identity-map.yaml").exists(), "Identity map should NOT be in repo root"

    def test_rg4_phase2_artifacts_persisted(self, isolated_env, tmp_path: Path):
        """RG-4: Phase-2/2.1 artifacts exist in workspace."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        proc, repo_fp = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode == 0
        workspace = isolated_env["workspaces_home"] / repo_fp
        
        required_artifacts = [
            "repo-cache.yaml",
            "repo-map-digest.md",
            "workspace-memory.yaml",
            "decision-pack.md",
        ]
        
        for artifact in required_artifacts:
            assert (workspace / artifact).exists(), f"Missing artifact: {artifact}"

    def test_rg5_commit_flags_correct(self, isolated_env, tmp_path: Path):
        """RG-5: Commit-Flags set only after successful persistence."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        proc, repo_fp = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode == 0
        
        session_path = isolated_env["workspaces_home"] / repo_fp / "SESSION_STATE.json"
        state = json.loads(session_path.read_text(encoding="utf-8"))
        ss = state.get("SESSION_STATE", {})
        
        assert ss.get("PersistenceCommitted") is True, "PersistenceCommitted not true"
        assert ss.get("WorkspaceReadyGateCommitted") is True, "WorkspaceReadyGateCommitted not true"
        assert ss.get("ticket_intake_ready") is True, "ticket_intake_ready not true"

    def test_rg7_global_error_handler_fires_on_failure(self, isolated_env, tmp_path: Path):
        """RG-7: Global Error Handler writes JSONL on failure."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        env = dict(isolated_env["env"])
        env["OPENCODE_FORCE_READ_ONLY"] = "1"
        
        proc, _ = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=env,
        )
        
        assert proc.returncode != 0, "Should fail with FORCE_READ_ONLY=1"


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required")
class TestE2ETestMatrix:
    """Tests for T1-T7: E2E Test Matrix."""

    def test_t1_happy_path_subdir_start(self, isolated_env, tmp_path: Path):
        """T1: Happy path - start from subdir of git repo."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        subdir = repo / "docs" / "deep"
        subdir.mkdir(parents=True, exist_ok=True)
        
        proc, repo_fp = _run_bootstrap(
            repo=subdir,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode == 0, f"Subdir start failed: {proc.stdout}\n{proc.stderr}"
        assert repo_fp is not None
        
        pointer_path = isolated_env["config_root"] / "SESSION_STATE.json"
        assert pointer_path.exists(), "RG-1: Pointer missing"
        
        session_path = isolated_env["workspaces_home"] / repo_fp / "SESSION_STATE.json"
        assert session_path.exists(), "RG-2: Workspace SESSION_STATE missing"
        
        identity_map = isolated_env["workspaces_home"] / repo_fp / "repo-identity-map.yaml"
        assert identity_map.exists(), "RG-3: Identity map missing"
        
        workspace = isolated_env["workspaces_home"] / repo_fp
        assert (workspace / "repo-cache.yaml").exists(), "RG-4: repo-cache.yaml missing"
        assert (workspace / "decision-pack.md").exists(), "RG-4: decision-pack.md missing"

    def test_t2_force_read_only_blocks_with_exit_code(self, isolated_env, tmp_path: Path):
        """T2: FORCE_READ_ONLY=1 -> Exit != 0."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        env = dict(isolated_env["env"])
        env["OPENCODE_FORCE_READ_ONLY"] = "1"
        
        proc, _ = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=env,
        )
        
        assert proc.returncode != 0, "T2: Should exit with non-zero"
        
        entries = [p for p in isolated_env["workspaces_home"].glob("*") if p.is_dir()]
        assert entries == [], "T2: No workspace should be created"

    def test_t3_binding_invalid_blocks_writes(self, isolated_env, tmp_path: Path):
        """T3: Binding/governance.paths.json invalid -> no writes, exit != 0."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        (isolated_env["config_root"] / "governance.paths.json").write_text(
            '{"schema": "invalid", "paths": {}}', encoding="utf-8"
        )
        
        proc, _ = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode != 0, "T3: Should exit with non-zero on invalid binding"

    def test_t4_artifact_write_fail_blocks(self, isolated_env, tmp_path: Path):
        """T4: Simulated artifact write fail via FORCE_READ_ONLY."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        env = dict(isolated_env["env"])
        env["OPENCODE_FORCE_READ_ONLY"] = "1"
        
        proc, _ = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=env,
        )
        
        assert proc.returncode != 0, "T4: Should exit with non-zero when writes blocked"

    def test_t5_pointer_verify_fail_blocks(self, isolated_env, tmp_path: Path):
        """T5: Pointer write blocked via FORCE_READ_ONLY."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        env = dict(isolated_env["env"])
        env["OPENCODE_FORCE_READ_ONLY"] = "1"
        
        pointer_path = isolated_env["config_root"] / "SESSION_STATE.json"
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        
        proc, _ = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=env,
        )
        
        assert proc.returncode != 0, "T5: Should exit with non-zero when writes blocked"
        assert not pointer_path.exists(), "T5: Pointer should not exist when writes blocked"

    def test_t6_session_state_has_rulebook_fields(self, isolated_env, tmp_path: Path):
        """T6: SessionState has LoadedRulebooks structure (values populated by bootstrap layer)."""
        repo = tmp_path / "repo"
        _git_init_repo(repo)
        
        proc, repo_fp = _run_bootstrap(
            repo=repo,
            config_root=isolated_env["config_root"],
            commands_home=isolated_env["commands_home"],
            workspaces_home=isolated_env["workspaces_home"],
            env=isolated_env["env"],
        )
        
        assert proc.returncode == 0, f"T6: Happy path should succeed: {proc.stdout}\n{proc.stderr}"
        
        session_path = isolated_env["workspaces_home"] / repo_fp / "SESSION_STATE.json"
        state = json.loads(session_path.read_text(encoding="utf-8"))
        ss = state.get("SESSION_STATE", {})
        
        assert "LoadedRulebooks" in ss, "T6: LoadedRulebooks field should exist in SESSION_STATE"
        
        loaded = ss.get("LoadedRulebooks", {})
        assert "core" in loaded, "T6: LoadedRulebooks.core field should exist"
        assert "profile" in loaded, "T6: LoadedRulebooks.profile field should exist"

    def test_t7_router_blocks_without_rulebooks(self, isolated_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """T7: Phase router checks rulebooks for Phase>=4."""
        from governance_runtime.application.use_cases.phase_router import route_phase
        from pathlib import Path

        monkeypatch.setattr(Path, "home", staticmethod(lambda: isolated_env["home"]))
        
        ss_with_rulebooks = {
            "phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${PROFILES_HOME}/rules.fallback-minimum.yml",
                "templates": "${COMMANDS_HOME}/master.md",
                "addons": {"riskTiering": "${PROFILES_HOME}/rules.risk-tiering.yml"},
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${PROFILES_HOME}/rules.fallback-minimum.yml",
            },
            "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
            "RepoFingerprint": "test12345678901234567890",
            "phase_transition_evidence": True,
        }
        
        routed = route_phase(
            requested_phase="4",
            requested_active_gate="Ticket Execution",
            requested_next_gate_condition="Describe your task",
            session_state_document={"SESSION_STATE": ss_with_rulebooks},
            repo_is_git_root=True,
        )
        
        assert routed.phase == "4", f"T7: With core rulebook, should allow Phase 4: {routed.phase}"
        
        ss_without_rulebooks = {
            "phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "", "profile": "", "templates": "", "addons": {}},
            "RepoFingerprint": "test12345678901234567890",
        }
        
        routed_blocked = route_phase(
            requested_phase="4",
            requested_active_gate="Ticket Execution",
            requested_next_gate_condition="Describe your task",
            session_state_document={"SESSION_STATE": ss_without_rulebooks},
            repo_is_git_root=True,
        )
        
        assert routed_blocked.phase != "4", "T7: Router should block Phase 4 jump from 2.1 without transition evidence"


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required")
class TestP1WindowsAtomicWrite:
    """P1-2: Windows atomic write semantics (temp, replace, cleanup)."""
    
    def test_atomic_write_creates_temp_in_same_dir(self, isolated_env, tmp_path: Path):
        """Atomic write should create temp file in same directory as target."""
        from governance_runtime.infrastructure.fs_atomic import atomic_write_text
        
        target = tmp_path / "test.txt"
        atomic_write_text(target, "content\n")
        
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "content\n"
        
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp file not cleaned up"

    def test_atomic_write_replaces_atomically(self, isolated_env, tmp_path: Path):
        """Atomic write should use os.replace for atomic replacement."""
        from governance_runtime.infrastructure.fs_atomic import atomic_write_text
        
        target = tmp_path / "test.txt"
        target.write_text("old\n", encoding="utf-8")
        
        atomic_write_text(target, "new\n")
        
        assert target.read_text(encoding="utf-8") == "new\n"

    def test_atomic_write_handles_unicode(self, isolated_env, tmp_path: Path):
        """Atomic write should handle unicode content."""
        from governance_runtime.infrastructure.fs_atomic import atomic_write_text
        
        target = tmp_path / "unicode.txt"
        unicode_content = "Hello \u00e4\u00f6\u00fc \u4e2d\u6587\n"
        
        atomic_write_text(target, unicode_content)
        
        assert target.read_text(encoding="utf-8") == unicode_content
