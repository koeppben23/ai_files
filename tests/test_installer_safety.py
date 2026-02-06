from __future__ import annotations

from pathlib import Path

import pytest

from .util import run_install


@pytest.mark.installer
def test_uninstall_preserves_non_owned_files(tmp_path: Path):
    """
    Enforces: installer must not delete user-owned files under commands/ that were not installed via manifest.
    """
    config_root = tmp_path / "opencode-config-nonowned"
    commands = config_root / "commands"
    commands.mkdir(parents=True, exist_ok=True)

    user_file = commands / "USER_NOTE.txt"
    user_file.write_text("do not delete\n", encoding="utf-8")
    assert user_file.exists()

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"
    assert user_file.exists(), "install must not delete preexisting user files"

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"
    assert user_file.exists(), "uninstall must preserve non-owned files under commands/"


@pytest.mark.installer
def test_config_root_with_spaces_and_unicode(tmp_path: Path):
    config_root = tmp_path / "Config Root Ünicode 你好"

    r = run_install(["--dry-run", "--config-root", str(config_root)])
    assert r.returncode == 0, f"dry-run failed:\n{r.stderr}\n{r.stdout}"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"
