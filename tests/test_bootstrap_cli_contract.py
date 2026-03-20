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
    for dirname in ("governance", "governance_runtime", "profiles", "scripts", "templates"):
        src = checkout_root / dirname
        if src.exists():
            shutil.copytree(src, commands_home / dirname, dirs_exist_ok=True)
    for filename in ("master.md", "rules.md", "QUALITY_INDEX.md", "CONFLICT_RESOLUTION.md", "phase_api.yaml"):
        src = checkout_root / filename
        if src.exists():
            shutil.copy2(src, commands_home / filename)

    canonical_phase_api = checkout_root / "governance_spec" / "phase_api.yaml"
    if canonical_phase_api.exists() and not (commands_home / "phase_api.yaml").exists():
        shutil.copy2(canonical_phase_api, commands_home / "phase_api.yaml")


def _write_governance_paths(*, config_root: Path, commands_home: Path, workspaces_home: Path) -> None:
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    local_root = config_root.parent / f"{config_root.name}-local"
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
    (config_root / "governance.paths.json").write_text(
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
    env["OPENCODE_PYTHON"] = sys.executable
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
    env["OPENCODE_PYTHON"] = sys.executable
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
    env["OPENCODE_PYTHON"] = sys.executable
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


@pytest.mark.e2e_governance
def test_cli_help_exposes_init_profile_and_alias(tmp_path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]
    launcher = _bootstrap_launcher(checkout_root)
    env = dict(os.environ)
    env["OPENCODE_PYTHON"] = sys.executable
    env["COMMANDS_HOME"] = str(checkout_root)
    env["OPENCODE_CONFIG_ROOT"] = str(checkout_root)
    proc = _run(launcher + ["--help"], cwd=tmp_path, env=env)
    assert proc.returncode == 0
    text = (proc.stdout or "") + (proc.stderr or "")
    assert "init" in text
    assert "--profile" in text
    assert "--set-operating-mode" in text


@pytest.mark.e2e_governance
def test_cli_init_profile_writes_repo_policy(tmp_path: Path) -> None:
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
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["COMMANDS_HOME"] = str(commands_home)
    env["OPENCODE_PYTHON"] = sys.executable
    env["CI"] = ""
    user_site = site.getusersitepackages()
    if user_site:
        env["PYTHONPATH"] = os.pathsep.join([part for part in (user_site, env.get("PYTHONPATH", "")) if part])

    proc = _run(
        launcher + ["init", "--profile", "solo", "--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    policy_path = repo / ".opencode" / "governance-repo-policy.json"
    assert policy_path.exists()
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    assert payload["operatingMode"] == "solo"
    assert payload["schema"] == "opencode-governance-repo-policy.v1"
    assert "repoOperatingMode = solo" in proc.stdout


@pytest.mark.e2e_governance
def test_cli_alias_set_operating_mode_updates_existing_policy(tmp_path: Path) -> None:
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
    policy_path = repo / ".opencode" / "governance-repo-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "schema": "opencode-governance-repo-policy.v1",
                "repoFingerprint": "",
                "operatingMode": "solo",
                "source": "manual",
                "createdAt": "2020-01-01T00:00:00Z",
            },
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["COMMANDS_HOME"] = str(commands_home)
    env["OPENCODE_PYTHON"] = sys.executable
    env["CI"] = ""
    user_site = site.getusersitepackages()
    if user_site:
        env["PYTHONPATH"] = os.pathsep.join([part for part in (user_site, env.get("PYTHONPATH", "")) if part])

    proc = _run(
        launcher + ["--set-operating-mode", "regulated", "--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    assert payload["operatingMode"] == "regulated"
    assert payload["createdAt"] == "2020-01-01T00:00:00Z"


@pytest.mark.e2e_governance
def test_cli_init_rejects_invalid_profile_value(tmp_path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]
    launcher = _bootstrap_launcher(checkout_root)
    repo = tmp_path / "repo"
    _git_init_repo(repo)
    env = dict(os.environ)
    proc = _run(launcher + ["init", "--profile", "invalid", "--repo-root", str(repo)], cwd=repo, env=env)
    assert proc.returncode != 0


@pytest.mark.e2e_governance
def test_cli_profile_without_init_is_rejected(tmp_path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]
    launcher = _bootstrap_launcher(checkout_root)
    repo = tmp_path / "repo"
    _git_init_repo(repo)
    env = dict(os.environ)
    proc = _run(launcher + ["--profile", "solo", "--repo-root", str(repo)], cwd=repo, env=env)
    assert proc.returncode != 0
