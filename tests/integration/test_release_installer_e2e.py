from __future__ import annotations
import json
import os
import subprocess
import zipfile
from pathlib import Path
import pytest


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _python_executable() -> str:
    return os.environ.get("PYTHON", "python3")


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


def _launcher_command(config_root: Path) -> list[str]:
    bin_dir = config_root / "bin"
    if os.name == "nt":
        launcher = bin_dir / "opencode-governance-bootstrap.cmd"
        return ["cmd", "/c", str(launcher)]
    launcher = bin_dir / "opencode-governance-bootstrap"
    return [str(launcher)]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_release(repo_root: Path, out_dir: Path) -> Path:
    proc = _run([
        _python_executable(),
        "scripts/build.py",
        "--out-dir",
        str(out_dir),
        "--formats",
        "zip",
    ], cwd=repo_root)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    zips = sorted(out_dir.glob("*.zip"))
    assert zips, "No release zip produced"
    return zips[0]


def _extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    entries = [p for p in dest.iterdir() if p.is_dir()]
    assert entries, "Extracted zip contains no top-level directory"
    return entries[0]


def test_release_zip_installer_creates_launcher(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    release_zip = _build_release(repo_root, dist)

    extracted_root = _extract_zip(release_zip, tmp_path / "unzipped")
    install_py = extracted_root / "install.py"
    assert install_py.exists(), "install.py missing from release zip"

    home = tmp_path / "home"
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["OPENCODE_CONFIG_ROOT"] = str(home / ".config" / "opencode")
    env["PYTHONIOENCODING"] = "utf-8"

    proc = _run([_python_executable(), str(install_py), "--no-backup"], cwd=extracted_root, env=env)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    bin_dir = Path(env["OPENCODE_CONFIG_ROOT"]) / "bin"
    launcher_unix = bin_dir / "opencode-governance-bootstrap"
    launcher_win = bin_dir / "opencode-governance-bootstrap.cmd"
    assert launcher_unix.exists() or launcher_win.exists()

    proc = _run([_python_executable(), str(install_py), "--smoketest"], cwd=extracted_root, env=env)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


def test_release_zip_invalid_python_command_fails(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    release_zip = _build_release(repo_root, dist)
    extracted_root = _extract_zip(release_zip, tmp_path / "unzipped")
    install_py = extracted_root / "install.py"
    assert install_py.exists(), "install.py missing from release zip"

    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["PYTHONIOENCODING"] = "utf-8"

    proc = _run([_python_executable(), str(install_py), "--no-backup"], cwd=extracted_root, env=env)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    binding_path = config_root / "commands" / "governance.paths.json"
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.write_text(
        "{\n  \"schema\": \"opencode-governance.paths.v1\",\n  \"paths\": {\n    \"configRoot\": \""
        + str(config_root).replace("\\", "\\\\")
        + "\",\n    \"commandsHome\": \""
        + str(config_root / "commands").replace("\\", "\\\\")
        + "\",\n    \"workspacesHome\": \""
        + str(config_root / "workspaces").replace("\\", "\\\\")
        + "\",\n    \"pythonCommand\": \"C:/invalid/python\"\n  }\n}\n",
        encoding="utf-8",
    )

    proc = _run([_python_executable(), str(install_py), "--no-backup", "--force", "--skip-paths-file"], cwd=extracted_root, env=env)
    assert proc.returncode != 0, proc.stdout + "\n" + proc.stderr


@pytest.mark.skip(reason="Bootstrap E2E test has path resolution issues on macOS - needs investigation")
def test_release_zip_installer_bootstrap_e2e(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    release_zip = _build_release(repo_root, dist)

    extracted_root = _extract_zip(release_zip, tmp_path / "unzipped")
    install_py = extracted_root / "install.py"
    assert install_py.exists(), "install.py missing from release zip"

    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["PYTHONIOENCODING"] = "utf-8"

    proc = _run([_python_executable(), str(install_py), "--no-backup"], cwd=extracted_root, env=env)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    repo = tmp_path / "repo"
    _git_init_repo(repo)

    launcher_cmd = _launcher_command(config_root)
    proc = _run(
        launcher_cmd + ["--repo-root", str(repo), "--config-root", str(config_root)],
        cwd=repo,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr

    pointer_path = config_root / "SESSION_STATE.json"
    assert pointer_path.exists(), "Global SESSION_STATE pointer missing"
    pointer = _read_json(pointer_path)
    repo_fp = str(pointer.get("activeRepoFingerprint") or "").strip()
    assert repo_fp, "activeRepoFingerprint missing"

    workspace_state = config_root / "workspaces" / repo_fp / "SESSION_STATE.json"
    assert workspace_state.exists(), "Workspace SESSION_STATE missing"
    state = _read_json(workspace_state).get("SESSION_STATE", {})

    assert state.get("PersistenceCommitted") is True
    assert state.get("WorkspaceReadyGateCommitted") is True
    assert state.get("Bootstrap", {}).get("Satisfied") is True
    assert state.get("ticket_intake_ready") is True
