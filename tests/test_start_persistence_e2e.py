from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


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


def _write_governance_paths(commands_home: Path, workspaces_home: Path, config_root: Path) -> None:
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(config_root),
            "commandsHome": str(commands_home),
            "profilesHome": str(commands_home / "profiles"),
            "diagnosticsHome": str(commands_home / "diagnostics"),
            "workspacesHome": str(workspaces_home),
            "globalErrorLogsHome": str(config_root / "logs"),
            "workspaceErrorLogsHomeTemplate": str(workspaces_home / "<repo_fingerprint>" / "logs"),
            "pythonCommand": sys.executable,
        },
        "generatedAt": "1970-01-01T00:00:00Z",
    }
    (commands_home / "governance.paths.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _materialize_commands_bundle_from_checkout(*, checkout_root: Path, commands_home: Path) -> None:
    commands_home.mkdir(parents=True, exist_ok=True)
    for dirname in ("diagnostics", "governance", "profiles", "scripts", "templates"):
        src = checkout_root / dirname
        if src.exists():
            shutil.copytree(src, commands_home / dirname, dirs_exist_ok=True)
    for filename in ("master.md", "rules.md", "QUALITY_INDEX.md", "CONFLICT_RESOLUTION.md"):
        src = checkout_root / filename
        if src.exists():
            shutil.copy2(src, commands_home / filename)


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required in subprocess Python for E2E persistence test")
def test_start_preflight_persists_workspace_and_pointer(tmp_path: Path) -> None:
    """
    Hard regression guard:
      - /start MUST create fingerprint workspace
      - MUST write SESSION_STATE.json under that workspace
      - MUST write global pointer SESSION_STATE.json under OPENCODE_HOME/configRoot
    If any of these regress, CI must fail deterministically.
    """
    checkout_root = Path(__file__).resolve().parents[1]

    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    workspaces_home.mkdir(parents=True, exist_ok=True)

    _materialize_commands_bundle_from_checkout(checkout_root=checkout_root, commands_home=commands_home)
    _write_governance_paths(commands_home, workspaces_home, config_root)

    repo = tmp_path / "repo"
    _git_init_repo(repo)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CI"] = ""
    env.pop("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", None)

    start_script = commands_home / "diagnostics" / "start_preflight_readonly.py"
    proc = _run([sys.executable, str(start_script)], cwd=repo, env=env)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) >= 3, proc.stdout
    payloads = []
    for ln in lines:
        try:
            payloads.append(json.loads(ln))
        except Exception:
            continue

    hook = next((p for p in payloads if isinstance(p, dict) and "workspacePersistenceHook" in p), None)
    assert hook is not None, proc.stdout
    assert hook.get("workspacePersistenceHook") == "ok"
    repo_fp = str(hook.get("repo_fingerprint") or "").strip()
    assert repo_fp, hook

    workspace = workspaces_home / repo_fp
    assert workspace.exists() and workspace.is_dir()
    assert (workspace / "SESSION_STATE.json").exists()
    assert (workspace / "repo-identity-map.yaml").exists()

    state = json.loads((workspace / "SESSION_STATE.json").read_text(encoding="utf-8"))
    ss = state.get("SESSION_STATE", {})
    assert ss.get("RepoFingerprint") == repo_fp
    assert ss.get("PersistenceCommitted") is True
    assert ss.get("WorkspaceReadyGateCommitted") is True

    assert (config_root / "SESSION_STATE.json").exists()


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required in subprocess Python for E2E persistence test")
def test_start_preflight_blocks_when_force_read_only(tmp_path: Path) -> None:
    """
    Fail-closed guard:
      If OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY=1 then /start must exit non-zero
      and MUST NOT create a fingerprint workspace.
    """
    checkout_root = Path(__file__).resolve().parents[1]

    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    workspaces_home.mkdir(parents=True, exist_ok=True)

    _materialize_commands_bundle_from_checkout(checkout_root=checkout_root, commands_home=commands_home)
    _write_governance_paths(commands_home, workspaces_home, config_root)

    repo = tmp_path / "repo"
    _git_init_repo(repo)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CI"] = ""
    env["OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY"] = "1"

    start_script = commands_home / "diagnostics" / "start_preflight_readonly.py"
    proc = _run([sys.executable, str(start_script)], cwd=repo, env=env)
    assert proc.returncode != 0

    entries = [p for p in workspaces_home.glob("*") if p.is_dir()]
    assert entries == []
