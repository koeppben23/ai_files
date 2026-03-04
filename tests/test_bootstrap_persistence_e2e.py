from __future__ import annotations

import json
import os
import shlex
import shutil
import site
import subprocess
import sys
from pathlib import Path

import pytest

from install import inject_session_reader_path, inject_session_reader_path_for_command


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


def _bootstrap_launcher(checkout_root: Path) -> list[str]:
    if os.name == "nt":
        launcher = checkout_root / "bin" / "opencode-governance-bootstrap.cmd"
        return ["cmd", "/c", str(launcher)]
    launcher = checkout_root / "bin" / "opencode-governance-bootstrap"
    return [str(launcher)]


def _read_json_lines(stdout: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for line in stdout.splitlines():
        token = line.strip()
        if not token:
            continue
        try:
            payload = json.loads(token)
        except Exception:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _assert_no_blocked_gate_failures(log_path: Path) -> None:
    if not log_path.exists():
        return
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in lines:
        payload = json.loads(line)
        joined = json.dumps(payload, ensure_ascii=True).upper()
        assert "BLOCKED" not in joined
        assert "GATE_FAILURE" not in joined


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _extract_first_step_command(commands_home: Path, command_markdown: str) -> str:
    command_md = commands_home / command_markdown
    text = command_md.read_text(encoding="utf-8")
    in_bash_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower() == "```bash":
            in_bash_block = True
            continue
        if in_bash_block and line == "```":
            break
        if not in_bash_block:
            continue
        if not line or line.startswith("#"):
            continue
        return line
    return ""


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
            "governanceHome": str(commands_home / "governance"),
            "workspacesHome": str(workspaces_home),
            "globalErrorLogsHome": str(commands_home / "logs"),
            "workspaceErrorLogsHomeTemplate": str(workspaces_home / "<repo_fingerprint>" / "logs"),
            "pythonCommand": sys.executable,
        },
        "generatedAt": "1970-01-01T00:00:00Z",
    }
    (commands_home / "governance.paths.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _materialize_commands_bundle_from_checkout(*, checkout_root: Path, commands_home: Path) -> None:
    commands_home.mkdir(parents=True, exist_ok=True)
    for dirname in ("governance", "governance", "profiles", "scripts", "templates"):
        src = checkout_root / dirname
        if src.exists():
            shutil.copytree(src, commands_home / dirname, dirs_exist_ok=True)
    for filename in (
        "master.md",
        "rules.md",
        "continue.md",
        "review.md",
        "QUALITY_INDEX.md",
        "CONFLICT_RESOLUTION.md",
        "phase_api.yaml",
    ):
        src = checkout_root / filename
        if src.exists():
            shutil.copy2(src, commands_home / filename)


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required in subprocess Python for E2E persistence test")
def test_bootstrap_preflight_persists_workspace_and_pointer(tmp_path: Path) -> None:
    """
    Hard regression guard:
      - bootstrap MUST create fingerprint workspace
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
    inject_session_reader_path(commands_home, python_command=sys.executable, dry_run=False)
    inject_session_reader_path_for_command(
        commands_home,
        command_markdown="review.md",
        python_command=sys.executable,
        dry_run=False,
    )

    repo = tmp_path / "repo"
    _git_init_repo(repo)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CI"] = ""
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["COMMANDS_HOME"] = str(commands_home)
    env.pop("OPENCODE_FORCE_READ_ONLY", None)
    user_site = site.getusersitepackages()
    if user_site:
        env["PYTHONPATH"] = os.pathsep.join(
            [part for part in (user_site, env.get("PYTHONPATH", "")) if part]
        )

    launcher = _bootstrap_launcher(checkout_root)
    proc = _run(
        launcher + ["--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    payloads = _read_json_lines(proc.stdout)
    hook = next((p for p in payloads if "workspacePersistenceHook" in p), None)
    assert hook is not None, proc.stdout
    assert hook.get("workspacePersistenceHook") == "ok"
    hook_command = str(hook.get("bootstrap_hook_command") or "")
    if hook_command:
        if os.name == "nt":
            assert " -m governance.entrypoints.bootstrap_persistence_hook" in hook_command
            assert Path(hook_command.split(" -m ", 1)[0]).name.lower().startswith("python")
        else:
            hook_argv = shlex.split(hook_command)
            assert len(hook_argv) >= 3
            assert hook_argv[1:3] == ["-m", "governance.entrypoints.bootstrap_persistence_hook"]
    assert hook.get("cwd") == str(repo)
    assert hook.get("repo_root_detected") == str(repo)
    repo_fp = str(hook.get("repo_fingerprint") or "").strip()
    assert repo_fp, hook

    workspace = workspaces_home / repo_fp
    assert workspace.exists() and workspace.is_dir()
    assert (workspace / "SESSION_STATE.json").exists()
    assert (workspace / "repo-identity-map.yaml").exists()
    assert (workspace / "repo-cache.yaml").exists()
    assert (workspace / "workspace-memory.yaml").exists()
    assert (workspace / "decision-pack.md").exists()

    state = json.loads((workspace / "SESSION_STATE.json").read_text(encoding="utf-8"))
    ss = state.get("SESSION_STATE", {})
    assert ss.get("RepoFingerprint") == repo_fp
    assert ss.get("PersistenceCommitted") is True
    assert ss.get("WorkspaceReadyGateCommitted") is True
    assert ss.get("ticket_intake_ready") is True
    phase_ready = ss.get("phase_ready")
    assert phase_ready is None or int(phase_ready) >= 4
    assert ss.get("Phase") != "1.2-ActivationIntent"
    assert ss.get("Phase") == "4"
    assert ss.get("LoadedRulebooks", {}).get("core")
    assert ss.get("RulebookLoadEvidence", {}).get("core")
    assert ss.get("RepoDiscovery", {}).get("Completed") is True
    assert ss.get("DecisionPack", {}).get("FilePath") == "${REPO_DECISION_PACK_FILE}"
    assert ss.get("APIInventory", {}).get("Status") == "not-applicable"
    assert not (workspace / "business-rules.md").exists()
    assert (workspace / "business-rules-status.md").exists()
    business_rules = ss.get("BusinessRules", {})
    inventory = business_rules.get("Inventory", {}) if isinstance(business_rules, dict) else {}
    assert isinstance(inventory.get("sha256"), str) and inventory.get("sha256")
    rules = business_rules.get("Rules") if isinstance(business_rules, dict) else None
    assert rules == []
    assert business_rules.get("Outcome") == "not-applicable"
    assert business_rules.get("ExecutionEvidence") is True

    events = _read_jsonl(workspace / "events.jsonl")
    phase_tokens = [str(event.get("phase_token") or "") for event in events]
    assert "2.1" in phase_tokens
    assert "3A" in phase_tokens
    assert any(str(event.get("next_token") or "") == "4" for event in events)

    next_gate_condition = str(ss.get("next_gate_condition") or "")
    assert "/master" not in next_gate_condition.lower()

    continuation_payload = next((p for p in payloads if "kernelContinuation" in p), None)
    assert continuation_payload is not None, proc.stdout
    assert continuation_payload.get("kernelContinuation") == "ok"
    assert continuation_payload.get("auto_continuation") == "route_phase"
    assert continuation_payload.get("route_phase_invoked") is True
    assert continuation_payload.get("phase") == "4"

    assert (config_root / "SESSION_STATE.json").exists()

    decision_pack_text = (workspace / "decision-pack.md").read_text(encoding="utf-8")
    assert "A) Yes" not in decision_pack_text
    assert "B) No" not in decision_pack_text

    _assert_no_blocked_gate_failures(workspace / "logs" / "error.log.jsonl")
    _assert_no_blocked_gate_failures(config_root / "commands" / "logs" / "error.log.jsonl")


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required in subprocess Python for E2E persistence test")
def test_bootstrap_preflight_blocks_when_force_read_only(tmp_path: Path) -> None:
    """
    Fail-closed guard:
      If OPENCODE_FORCE_READ_ONLY=1 then bootstrap must exit non-zero
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
    inject_session_reader_path(commands_home, python_command=sys.executable, dry_run=False)
    inject_session_reader_path_for_command(
        commands_home,
        command_markdown="review.md",
        python_command=sys.executable,
        dry_run=False,
    )

    repo = tmp_path / "repo"
    _git_init_repo(repo)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CI"] = ""
    env["OPENCODE_FORCE_READ_ONLY"] = "1"
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["COMMANDS_HOME"] = str(commands_home)
    user_site = site.getusersitepackages()
    if user_site:
        env["PYTHONPATH"] = os.pathsep.join(
            [part for part in (user_site, env.get("PYTHONPATH", "")) if part]
        )

    launcher = _bootstrap_launcher(checkout_root)
    proc = _run(
        launcher + ["--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    assert proc.returncode != 0

    entries = [p for p in workspaces_home.glob("*") if p.is_dir()]
    assert entries == []


@pytest.mark.e2e_governance
@pytest.mark.skipif(not HAS_PYYAML_IN_SUBPROCESS, reason="pyyaml required in subprocess Python for E2E persistence test")
def test_continue_first_step_executes_after_bootstrap(tmp_path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]

    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    workspaces_home.mkdir(parents=True, exist_ok=True)

    _materialize_commands_bundle_from_checkout(checkout_root=checkout_root, commands_home=commands_home)
    _write_governance_paths(commands_home, workspaces_home, config_root)
    inject_session_reader_path(commands_home, python_command=sys.executable, dry_run=False)
    inject_session_reader_path_for_command(
        commands_home,
        command_markdown="review.md",
        python_command=sys.executable,
        dry_run=False,
    )

    repo = tmp_path / "repo"
    _git_init_repo(repo)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CI"] = ""
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["COMMANDS_HOME"] = str(commands_home)
    env.pop("OPENCODE_FORCE_READ_ONLY", None)
    user_site = site.getusersitepackages()
    if user_site:
        env["PYTHONPATH"] = os.pathsep.join(
            [part for part in (user_site, env.get("PYTHONPATH", "")) if part]
        )

    launcher = _bootstrap_launcher(checkout_root)
    proc = _run(
        launcher + ["--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    command = _extract_first_step_command(commands_home, "continue.md")
    assert command, "continue.md must contain a runnable session-reader command in a bash block"

    review_command = _extract_first_step_command(commands_home, "review.md")
    assert review_command, "review.md must contain a runnable session-reader command in a bash block"

    run_continue = subprocess.run(
        command,
        cwd=str(repo),
        env=env,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run_continue.returncode == 0, run_continue.stdout + "\n" + run_continue.stderr

    lines = [line.strip() for line in run_continue.stdout.splitlines() if line.strip()]
    assert any(line.startswith("status:") for line in lines), run_continue.stdout
    assert "status: OK" in run_continue.stdout
    assert "status: ERROR" not in run_continue.stdout
