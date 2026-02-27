from __future__ import annotations
import os
import subprocess
import zipfile
from pathlib import Path


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
    return os.environ.get("PYTHON", "python")


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
