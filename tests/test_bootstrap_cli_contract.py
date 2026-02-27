from __future__ import annotations

import json
import os
import shutil
import site
import subprocess
import sys
from pathlib import Path

import pytest


def _bootstrap_launcher(checkout_root: Path) -> list[str]:
    if os.name == "nt":
        launcher = checkout_root / "bin" / "opencode-governance-bootstrap.cmd"
        return ["cmd", "/c", str(launcher)]
    launcher = checkout_root / "bin" / "opencode-governance-bootstrap"
    return [str(launcher)]


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


def _materialize_commands_bundle_from_checkout(*, checkout_root: Path, commands_home: Path) -> None:
    commands_home.mkdir(parents=True, exist_ok=True)
    for dirname in ("governance", "governance", "profiles", "scripts", "templates"):
        src = checkout_root / dirname
        if src.exists():
            shutil.copytree(src, commands_home / dirname, dirs_exist_ok=True)
    for filename in ("master.md", "rules.md", "QUALITY_INDEX.md", "CONFLICT_RESOLUTION.md", "phase_api.yaml"):
        src = checkout_root / filename
        if src.exists():
            shutil.copy2(src, commands_home / filename)


def _write_governance_paths(*, config_root: Path, commands_home: Path, workspaces_home: Path) -> None:
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(config_root),
            "commandsHome": str(commands_home),
            "profilesHome": str(commands_home / "profiles"),
            "governanceHome": str(commands_home / "governance"),
            "workspacesHome": str(workspaces_home),
            "globalErrorLogsHome": str(commands_home / "logs"),
            "workspaceErrorLogsHomeTemplate": str(workspaces_home / "<repo_fingerprint>" / "logs"),
            "pythonCommand": sys.executable,
        },
        "generatedAt": "1970-01-01T00:00:00Z",
    }
    (commands_home / "governance.paths.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


@pytest.mark.e2e_governance
def test_cli_contract_requires_repo_root(tmp_path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]
    launcher = _bootstrap_launcher(checkout_root)
    env = dict(os.environ)
    env["OPENCODE_CONFIG_ROOT"] = str(tmp_path / "config")
    env["COMMANDS_HOME"] = str(tmp_path / "config" / "commands")
    env["HOME"] = str(tmp_path / "home")
    env["USERPROFILE"] = str(tmp_path / "home")
    proc = _run(launcher, cwd=tmp_path, env=env)
    assert proc.returncode != 0


@pytest.mark.e2e_governance
def test_cli_contract_rejects_invalid_repo_root(tmp_path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]
    launcher = _bootstrap_launcher(checkout_root)
    env = dict(os.environ)
    env["OPENCODE_CONFIG_ROOT"] = str(tmp_path / "config")
    env["COMMANDS_HOME"] = str(tmp_path / "config" / "commands")
    env["HOME"] = str(tmp_path / "home")
    env["USERPROFILE"] = str(tmp_path / "home")
    proc = _run(launcher + ["--repo-root", str(tmp_path / "missing")], cwd=tmp_path, env=env)
    assert proc.returncode != 0


@pytest.mark.e2e_governance
def test_cli_contract_uses_repo_root_and_config_root(tmp_path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]
    launcher = _bootstrap_launcher(checkout_root)

    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    _materialize_commands_bundle_from_checkout(checkout_root=checkout_root, commands_home=commands_home)
    _write_governance_paths(config_root=config_root, commands_home=commands_home, workspaces_home=workspaces_home)

    repo = tmp_path / "repo"
    _git_init_repo(repo)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CI"] = ""
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["COMMANDS_HOME"] = str(commands_home)
    user_site = site.getusersitepackages()
    if user_site:
        env["PYTHONPATH"] = os.pathsep.join(
            [part for part in (user_site, env.get("PYTHONPATH", "")) if part]
        )

    proc = _run(
        launcher + ["--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert (config_root / "SESSION_STATE.json").exists()
