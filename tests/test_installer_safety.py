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


@pytest.mark.installer
def test_force_uninstall_without_manifest_preserves_user_profile_files(tmp_path: Path):
    config_root = tmp_path / "opencode-config-missing-manifest"
    commands = config_root / "commands"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    user_profile = commands / "profiles" / "custom-user-rule.md"
    user_diag = commands / "diagnostics" / "custom-user-note.txt"
    user_profile.parent.mkdir(parents=True, exist_ok=True)
    user_diag.parent.mkdir(parents=True, exist_ok=True)
    user_profile.write_text("# user custom profile\n", encoding="utf-8")
    user_diag.write_text("keep me\n", encoding="utf-8")

    manifest = commands / "INSTALL_MANIFEST.json"
    assert manifest.exists(), "expected installer manifest to exist after install"
    manifest.unlink()

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall with missing manifest failed:\n{r.stderr}\n{r.stdout}"

    assert user_profile.exists(), "fallback uninstall must preserve user-owned profile files"
    assert user_diag.exists(), "fallback uninstall must preserve user-owned diagnostics files"


@pytest.mark.installer
def test_uninstall_removes_empty_profiles_addons_and_workspaces_dirs(tmp_path: Path):
    config_root = tmp_path / "opencode-config-empty-dirs"
    commands = config_root / "commands"

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    profiles_addons = commands / "profiles" / "addons"
    workspaces = config_root / "workspaces"
    assert profiles_addons.exists() and profiles_addons.is_dir()
    assert workspaces.exists() and workspaces.is_dir()

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert not profiles_addons.exists(), "empty commands/profiles/addons should be removed on uninstall"
    assert not workspaces.exists(), "empty workspaces dir should be removed on uninstall"
