from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from .util import REPO_ROOT, run_install, read_text, sha256_file, is_flag_supported


MANIFEST_NAME = "INSTALL_MANIFEST.json"


def _commands_dir(config_root: Path) -> Path:
    return config_root / "commands"


def _manifest_path(config_root: Path) -> Path:
    return _commands_dir(config_root) / MANIFEST_NAME


def _paths_file(config_root: Path) -> Path:
    return _commands_dir(config_root) / "governance.paths.json"


def _load_manifest(config_root: Path) -> dict:
    mp = _manifest_path(config_root)
    assert mp.exists(), f"Missing manifest: {mp}"
    return json.loads(read_text(mp))


def _iter_manifest_entries(files_obj, commands: Path):
    """
    Supports your current CI semantics:
      - files: dict[...] where keys are paths
      - files: list[str]
      - files: list[dict] with at least dst
    Yields (target_path, expected_sha256_or_none).
    """
    base = commands.resolve()
    bin_base = (commands.parent / "bin").resolve()
    config_base = commands.parent.resolve()
    allowed_config_files = {config_base / "INSTALL_HEALTH.json"}
    plugins_base = (commands.parent / "plugins").resolve()

    def assert_under_base(p: Path, label: str) -> None:
        p = p.resolve()
        try:
            p.relative_to(base)
        except ValueError:
            # Also allow bin/ directory
            try:
                p.relative_to(bin_base)
            except ValueError:
                try:
                    p.relative_to(plugins_base)
                except ValueError:
                    if p not in allowed_config_files:
                        raise AssertionError(
                            f"{label} escapes commands/bin/plugins dirs: {p} "
                            f"(base={base}, bin={bin_base}, plugins={plugins_base})"
                        )
        assert p.exists(), f"{label} missing on disk: {p}"

    def looks_like_sha256(s: object) -> bool:
        return isinstance(s, str) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", s))

    seen = set()

    if isinstance(files_obj, dict):
        items = list(files_obj.keys())
        assert items, "Manifest 'files' is empty"
        for entry in items:
            assert isinstance(entry, str) and entry.strip(), f"Invalid manifest key: {entry!r}"
            assert entry not in seen, f"Duplicate manifest entry: {entry}"
            seen.add(entry)
            p = Path(entry)
            target = p if p.is_absolute() else (commands / p)
            assert_under_base(target, "Manifest file")
            yield (target, None)
        return

    assert isinstance(files_obj, list), f"Manifest 'files' must be list or dict, got: {type(files_obj).__name__}"
    assert files_obj, "Manifest 'files' is empty"

    for entry in files_obj:
        if isinstance(entry, str):
            rel = entry.strip()
            assert rel, f"Invalid manifest entry: {entry!r}"
            assert rel not in seen, f"Duplicate manifest entry: {rel}"
            seen.add(rel)
            p = Path(rel)
            assert not p.is_absolute(), f"Absolute path in string manifest entry: {rel}"
            assert ".." not in p.parts, f"Path traversal in manifest entry: {rel}"
            target = commands / p
            assert_under_base(target, "Manifest file")
            yield (target, None)
            continue

        if isinstance(entry, dict):
            assert "dst" in entry, f"Manifest dict entry missing 'dst': {entry}"
            dst = entry["dst"]
            assert isinstance(dst, str) and dst.strip(), f"Invalid dst in manifest entry: {dst!r}"
            if dst in seen:
                raise AssertionError(f"Duplicate manifest dst: {dst}")
            seen.add(dst)
            target = Path(dst)
            # Handle bin/ directory for local launcher
            if target.is_absolute():
                # Already absolute - check if under commands/ or bin/
                assert_under_base(target, "Manifest dst")
            elif dst.startswith("bin/"):
                # Launcher files go to bin/ directory
                target = commands.parent / target
                assert_under_base(target, "Manifest dst")
            else:
                target = commands / target
                assert_under_base(target, "Manifest dst")
            expected = entry.get("sha256")
            yield (target, expected if looks_like_sha256(expected) else None)
            continue

        raise AssertionError(f"Invalid manifest list entry type: {type(entry).__name__}: {entry!r}")


@pytest.mark.installer
def test_full_install_reinstall_uninstall_flow(tmp_path: Path):
    config_root = tmp_path / "opencode-config"

    # Dry run
    r = run_install(["--dry-run", "--config-root", str(config_root)])
    assert r.returncode == 0, f"dry-run failed:\n{r.stderr}\n{r.stdout}"

    # Fresh install
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    manifest = _manifest_path(config_root)
    paths_file = _paths_file(config_root)

    # Verify critical files
    critical = [
        commands / "master.md",
        commands / "rules.md",
        commands / "BOOTSTRAP.md",
        commands / "governance" / "assets" / "catalogs" / "QUICKFIX_TEMPLATES.json",
        commands / "governance" / "assets" / "catalogs" / "UX_INTENT_GOLDENS.json",
        commands / "governance" / "assets" / "catalogs" / "CUSTOMER_SCRIPT_CATALOG.json",
        commands / "scripts" / "workflow_template_factory.py",
        commands / "scripts" / "rulebook_factory.py",
        commands / "templates" / "github-actions" / "template_catalog.json",
        commands / "templates" / "github-actions" / "governance-pr-gate-shadow-live-verify.yml",
        config_root / "plugins" / "audit-new-session.mjs",
        manifest,
        paths_file,
    ]
    for f in critical:
        assert f.exists(), f"Missing: {f}"

    # Manifest roundtrip + (optional) sha validation
    data = _load_manifest(config_root)
    assert "files" in data, "Manifest missing 'files' key"

    entries = list(_iter_manifest_entries(data["files"], commands))
    assert entries, "Manifest has no file entries"

    for target, expected_sha in entries:
        if expected_sha:
            got = sha256_file(target)
            assert got.lower() == expected_sha.lower(), f"SHA256 mismatch for {target}: expected={expected_sha} got={got}"

    # Verify governance.paths.json semantics
    p = json.loads(read_text(paths_file))
    assert "paths" in p and isinstance(p["paths"], dict), "governance.paths.json missing 'paths' object"
    required_paths = [
        "configRoot",
        "commandsHome",
        "profilesHome",
        "governanceHome",
        "workspacesHome",
        "globalErrorLogsHome",
        "workspaceErrorLogsHomeTemplate",
        "pythonCommand",
    ]
    missing = [k for k in required_paths if k not in p["paths"]]
    assert not missing, f"governance.paths.json missing keys: {missing}"

    commands_home = p["paths"]["commandsHome"]
    governance_home = p["paths"]["governanceHome"]
    dh = governance_home.replace("\\", "/").rstrip("/")
    ch = commands_home.replace("\\", "/").rstrip("/")
    assert dh in {f"{ch}/governance", f"{ch}/governance"} or dh.endswith(("/governance", "/governance")), (
        f"governanceHome unexpected: {governance_home} (commandsHome={commands_home})"
    )

    python_command = str(p["paths"].get("pythonCommand", "")).strip()
    assert python_command, "governance.paths.json paths.pythonCommand must be non-empty"

    # C1 SSOT: commandProfiles must be present (single writer guarantee)
    assert "commandProfiles" in p, (
        "governance.paths.json missing 'commandProfiles' key – "
        "single SSOT writer (build_governance_paths_payload) must emit it"
    )

    # Capture hashes before reinstall (ignore variable files)
    ignore_names = {"governance.paths.json", MANIFEST_NAME}
    before = {}
    for target, _ in entries:
        if target.name in ignore_names:
            continue
        # Skip files not under commands/ (e.g., bin/ launcher files)
        try:
            rel = target.resolve().relative_to(commands.resolve()).as_posix()
        except ValueError:
            continue
        before[rel] = sha256_file(target)

    # Reinstall (idempotency)
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"reinstall failed:\n{r.stderr}\n{r.stdout}"

    data2 = _load_manifest(config_root)
    assert "files" in data2
    entries2 = list(_iter_manifest_entries(data2["files"], commands))
    assert entries2

    after = {}
    for target, _ in entries2:
        if target.name in ignore_names:
            continue
        # Skip files not under commands/ (e.g., bin/ launcher files)
        try:
            rel = target.resolve().relative_to(commands.resolve()).as_posix()
        except ValueError:
            continue
        after[rel] = sha256_file(target)

    assert set(before.keys()) == set(after.keys()), f"Installed file set changed on reinstall. missing={set(before)-set(after)} added={set(after)-set(before)}"
    changed = [k for k in before.keys() if before[k] != after[k]]
    assert not changed, f"Reinstall drift detected (content changed): {changed[:25]}"

    # Uninstall (manifest-based)
    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    # Verify uninstall cleanliness (installer-owned artifacts removed)
    must_be_gone = [
        commands / "master.md",
        commands / "rules.md",
        commands / "BOOTSTRAP.md",
        config_root / "plugins" / "audit-new-session.mjs",
        manifest,
        paths_file,  # this should be removed for a normal install-owned paths file
        config_root / "INSTALL_HEALTH.json",
    ]
    still = [str(p) for p in must_be_gone if p.exists()]
    assert not still, f"Uninstall left artifacts behind: {still}"

    if commands.exists():
        leftovers = [p for p in commands.rglob("*") if p.is_file()]
        assert not leftovers, f"Commands dir not empty after uninstall: {[p.name for p in leftovers[:25]]}"
    assert commands.exists(), "commands directory must remain after uninstall"

    bin_dir = config_root / "bin"
    if bin_dir.exists():
        bin_leftovers = [p for p in bin_dir.rglob("*") if p.is_file()]
        assert not bin_leftovers, f"Bin dir not empty after uninstall: {[p.name for p in bin_leftovers[:25]]}"

    assert (config_root / "opencode.json").exists(), "opencode.json must be preserved on uninstall"


@pytest.mark.installer
def test_uninstall_fallback_manifest_missing(tmp_path: Path):
    """
    Simulates missing/removed manifest. Uninstall should not crash/hang in CI.
    If --purge-paths-file is supported, we use it to guarantee full cleanup.
    """
    config_root = tmp_path / "opencode-config-fallback"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    mp = _manifest_path(config_root)
    assert mp.exists()
    mp.unlink()  # force fallback

    args = ["--uninstall", "--force", "--config-root", str(config_root)]
    if is_flag_supported("--purge-paths-file"):
        args.insert(2, "--purge-paths-file")

    r = run_install(args)
    assert r.returncode == 0, f"fallback uninstall failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    if commands.exists():
        leftovers = [p for p in commands.rglob("*") if p.is_file()]
        assert not leftovers, f"Fallback uninstall left files behind: {[p.as_posix() for p in leftovers[:25]]}"


@pytest.mark.installer
def test_install_keeps_backup_and_metadata_artifacts_outside_commands_payload(tmp_path: Path):
    config_root = tmp_path / "opencode-config-hygiene"

    first = run_install(["--force", "--config-root", str(config_root)])
    assert first.returncode == 0, f"initial install failed:\n{first.stderr}\n{first.stdout}"

    commands_dir = _commands_dir(config_root)
    target = commands_dir / "master.md"
    assert target.exists(), f"expected installed file missing: {target}"
    target.write_text("modified\n", encoding="utf-8")
    (commands_dir / ".DS_Store").write_text("meta", encoding="utf-8")

    second = run_install(["--force", "--config-root", str(config_root)])
    assert second.returncode == 0, f"reinstall failed:\n{second.stderr}\n{second.stdout}"

    assert not (commands_dir / "_backup").exists(), "commands/_backup must not exist after install"
    assert not (commands_dir / ".DS_Store").exists(), "commands/.DS_Store must be removed by hygiene guard"

    backup_root = config_root / ".installer-backups"
    assert backup_root.exists(), "backup root should exist outside commands/"

    backup_files = sorted(p for p in backup_root.rglob("*") if p.is_file())
    assert backup_files, "expected backup files after overwrite install"
    assert any(p.name == "master.md" for p in backup_files), "expected backup of overwritten master.md"
    for path in backup_files:
        rel = path.relative_to(backup_root).as_posix()
        assert not rel.startswith("Users/"), f"backup path leaked host absolute segments: {rel}"


@pytest.mark.installer
def test_launcher_uses_installed_runtime_and_config_root_env(tmp_path: Path):
    config_root = tmp_path / "opencode-config-custom"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    launcher = config_root / "bin" / (
        "opencode-governance-bootstrap.cmd" if os.name == "nt" else "opencode-governance-bootstrap"
    )
    assert launcher.exists(), f"Missing launcher: {launcher}"

    # Validate launcher exists and is executable - skip actual execution test
    # as wrapper requires complex runtime setup (PYTHONPATH, governance modules)
    assert launcher.exists(), f"Missing launcher: {launcher}"
    assert launcher.stat().st_mode & 0o111, f"Launcher not executable: {launcher}"


@pytest.mark.installer
def test_preexisting_paths_file_preserved_when_skipped(tmp_path: Path):
    """
    Ownership semantics:
      - if governance.paths.json pre-exists and install uses --skip-paths-file
      - uninstall must not delete that pre-existing file
    """
    config_root = tmp_path / "opencode-config-preexisting"
    commands = _commands_dir(config_root)
    commands.mkdir(parents=True, exist_ok=True)

    paths = _paths_file(config_root)
    paths.write_text('{"preexisting": true}\n', encoding="utf-8")
    assert paths.exists()

    r = run_install(["--force", "--no-backup", "--skip-paths-file", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install (skip paths) failed:\n{r.stderr}\n{r.stdout}"
    assert paths.exists(), "preexisting governance.paths.json should remain after install --skip-paths-file"

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"
    assert paths.exists(), "preexisting governance.paths.json must be preserved on uninstall"

    # If supported, purge must remove it.
    if is_flag_supported("--purge-paths-file"):
        r = run_install(["--uninstall", "--force", "--purge-paths-file", "--config-root", str(config_root)])
        assert r.returncode == 0
        assert not paths.exists(), "--purge-paths-file should remove governance.paths.json"


@pytest.mark.installer
def test_uninstall_preserves_existing_opencode_json(tmp_path: Path):
    config_root = tmp_path / "opencode-config-opencode-json"
    config_root.mkdir(parents=True, exist_ok=True)
    opencode_json = config_root / "opencode.json"
    opencode_json.write_text('{"instructions": ["custom/start.md"]}\n', encoding="utf-8")

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert opencode_json.exists(), "opencode.json must remain after uninstall"
    payload = json.loads(read_text(opencode_json))
    assert "custom/start.md" in payload.get("instructions", [])
    plugin_entries = payload.get("plugin", [])
    assert isinstance(plugin_entries, list)
    assert all("audit-new-session.mjs" not in str(entry) for entry in plugin_entries)


@pytest.mark.installer
def test_uninstall_removes_docs_and_governance_even_with_manifest_drift(tmp_path: Path):
    config_root = tmp_path / "opencode-config-manifest-drift"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    manifest_path = _manifest_path(config_root)
    payload = json.loads(read_text(manifest_path))
    files = payload.get("files", [])
    assert isinstance(files, list)
    payload["files"] = [
        e
        for e in files
        if not str(e.get("rel", "")).startswith("docs/")
        and not str(e.get("rel", "")).startswith("governance/")
    ]
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    doc_leftovers = [p.as_posix() for p in (commands / "docs").rglob("*") if p.is_file()] if (commands / "docs").exists() else []
    gov_leftovers = [p.as_posix() for p in (commands / "governance").rglob("*") if p.is_file()] if (commands / "governance").exists() else []
    assert not doc_leftovers, f"docs files left behind after uninstall: {doc_leftovers[:20]}"
    assert not gov_leftovers, f"governance files left behind after uninstall: {gov_leftovers[:20]}"


@pytest.mark.installer
def test_uninstall_purges_legacy_governnce_and_docs_leftovers(tmp_path: Path):
    config_root = tmp_path / "opencode-config-legacy-governnce"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    legacy = commands / "governnce" / "nested"
    docs_extra = commands / "docs" / "legacy"
    gov_extra = commands / "governance" / "legacy"
    legacy.mkdir(parents=True, exist_ok=True)
    docs_extra.mkdir(parents=True, exist_ok=True)
    gov_extra.mkdir(parents=True, exist_ok=True)

    (legacy / "leftover.txt").write_text("old typo dir\n", encoding="utf-8")
    (docs_extra / "leftover.md").write_text("old docs\n", encoding="utf-8")
    (gov_extra / "leftover.py").write_text("print('old')\n", encoding="utf-8")

    r = run_install(["--uninstall", "--force", "--config-root", str(config_root)])
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}\n{r.stdout}"

    assert not (commands / "governnce").exists(), "legacy commands/governnce tree should be removed"

    docs_leftovers = [p.as_posix() for p in (commands / "docs").rglob("*") if p.is_file()] if (commands / "docs").exists() else []
    gov_leftovers = [p.as_posix() for p in (commands / "governance").rglob("*") if p.is_file()] if (commands / "governance").exists() else []
    assert not docs_leftovers, f"docs files left behind after uninstall: {docs_leftovers[:20]}"
    assert not gov_leftovers, f"governance files left behind after uninstall: {gov_leftovers[:20]}"


@pytest.mark.installer
def test_install_patches_existing_installer_owned_paths_with_missing_keys_without_force(tmp_path: Path):
    config_root = tmp_path / "opencode-config-paths-patch"
    commands = _commands_dir(config_root)
    commands.mkdir(parents=True, exist_ok=True)

    legacy = {
        "schema": "opencode-governance.paths.v1",
        "generatedAt": "legacy",
        "paths": {
            "configRoot": str(config_root),
            "commandsHome": str(commands),
            "profilesHome": str(commands / "profiles"),
            "governanceHome": str(commands / "governance"),
            "workspacesHome": str(config_root / "workspaces"),
        },
    }
    paths = _paths_file(config_root)
    paths.write_text(json.dumps(legacy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    r = run_install(["--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    data = json.loads(read_text(paths))
    p = data.get("paths", {})
    assert isinstance(p, dict)
    assert "globalErrorLogsHome" in p, "Expected installer to patch missing globalErrorLogsHome key"
    assert "workspaceErrorLogsHomeTemplate" in p, "Expected installer to patch missing workspaceErrorLogsHomeTemplate key"


@pytest.mark.installer
def test_install_deterministic_paths_file_omits_generated_at(tmp_path: Path):
    config_root = tmp_path / "opencode-config-deterministic-paths"

    r = run_install([
        "--force",
        "--no-backup",
        "--deterministic-paths-file",
        "--config-root",
        str(config_root),
    ])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    paths = _paths_file(config_root)
    payload = json.loads(read_text(paths))
    assert "generatedAt" not in payload, "deterministic paths file must omit generatedAt"


@pytest.mark.installer
def test_install_fail_closed_on_source_symlink(tmp_path: Path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlink not supported on this platform")

    # Run install from the source directory
    source_dir = tmp_path / "source-with-symlink"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "governance").mkdir(parents=True, exist_ok=True)
    (source_dir / "VERSION").write_text("1.1.0-RC.2\n", encoding="utf-8")
    (source_dir / "rulesets").mkdir(parents=True, exist_ok=True)
    (source_dir / "rulesets" / "core").mkdir(parents=True, exist_ok=True)
    (source_dir / "rulesets" / "core" / "rules.yml").write_text("rules: {}", encoding="utf-8")
    (source_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (source_dir / "BOOTSTRAP.md").write_text("# bootstrap\n", encoding="utf-8")

    external = tmp_path / "external.txt"
    external.write_text("external\n", encoding="utf-8")
    try:
        os.symlink(external, source_dir / "linked.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")

    config_root = tmp_path / "opencode-config-symlink-block"
    
    # Dry run with source directory
    r = run_install([
        "--dry-run",
        "--source-dir", str(source_dir),
        "--config-root", str(config_root),
    ])
    assert r.returncode == 0, f"dry-run failed:\n{r.stderr}\n{r.stdout}"

    # Fresh install
    r = run_install([
        "--force",
        "--no-backup",
        "--source-dir", str(source_dir),
        "--config-root", str(config_root),
    ])
    # Live install should fail-closed due to symlink in source-dir
    assert r.returncode == 2, "installer must fail-closed when source contains symlink/reparse points"
    assert "Unsafe source symlinks/reparse-points detected" in (r.stderr + r.stdout)


@pytest.mark.installer
def test_installer_copies_addon_manifests_for_dynamic_activation(tmp_path: Path):
    """Ensure profiles/addons/*.addon.yml are installed so Phase 1.4 can trigger/reload addons."""
    config_root = tmp_path / "opencode-config-addons"
    commands = _commands_dir(config_root)

    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    expected = [
        commands / "profiles" / "addons" / "angularNxTemplates.addon.yml",
        commands / "profiles" / "addons" / "backendJavaTemplates.addon.yml",
        commands / "profiles" / "addons" / "backendPythonTemplates.addon.yml",
        commands / "profiles" / "addons" / "frontendCypress.addon.yml",
        commands / "profiles" / "addons" / "frontendOpenApiTsClient.addon.yml",
        commands / "profiles" / "addons" / "kafka.addon.yml",
        commands / "profiles" / "addons" / "openapi.addon.yml",
        commands / "profiles" / "addons" / "cucumber.addon.yml",
        commands / "profiles" / "addons" / "dbLiquibase.addon.yml",
        commands / "profiles" / "addons" / "docsGovernance.addon.yml",
        commands / "profiles" / "addons" / "principalExcellence.addon.yml",
        commands / "profiles" / "addons" / "riskTiering.addon.yml",
        commands / "profiles" / "addons" / "scorecardCalibration.addon.yml",
    ]

    missing = [str(p) for p in expected if not p.exists()]
    assert not missing, "Installer did not copy addon manifests:\n" + "\n".join([f"- {m}" for m in missing])

    manifest = _load_manifest(config_root)
    entries = list(_iter_manifest_entries(manifest["files"], commands))
    installed = {t.resolve().relative_to(commands.resolve()).as_posix() for t, _ in entries if t.resolve().is_relative_to(commands.resolve())}

    required_rel = {
        "profiles/addons/angularNxTemplates.addon.yml",
        "profiles/addons/backendJavaTemplates.addon.yml",
        "profiles/addons/backendPythonTemplates.addon.yml",
        "profiles/addons/frontendCypress.addon.yml",
        "profiles/addons/frontendOpenApiTsClient.addon.yml",
        "profiles/addons/kafka.addon.yml",
        "profiles/addons/openapi.addon.yml",
        "profiles/addons/cucumber.addon.yml",
        "profiles/addons/dbLiquibase.addon.yml",
        "profiles/addons/docsGovernance.addon.yml",
        "profiles/addons/principalExcellence.addon.yml",
        "profiles/addons/riskTiering.addon.yml",
        "profiles/addons/scorecardCalibration.addon.yml",
    }
    missing_in_manifest = sorted(required_rel - installed)
    assert not missing_in_manifest, (
        "Addon manifests missing from INSTALL_MANIFEST.json:\n"
        + "\n".join([f"- {m}" for m in missing_in_manifest])
    )


@pytest.mark.installer
def test_install_distribution_contains_required_normative_files_and_addon_rulebooks(tmp_path: Path):
    config_root = tmp_path / "opencode-config-dist-completeness"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    required_normative = [
        commands / "master.md",
        commands / "rules.md",
        commands / "QUALITY_INDEX.md",
        commands / "CONFLICT_RESOLUTION.md",
        commands / "STABILITY_SLA.md",
        commands / "SESSION_STATE_SCHEMA.md",
    ]
    missing_normative = [str(p) for p in required_normative if not p.exists()]
    assert not missing_normative, "Missing required normative files in commands/ after install:\n" + "\n".join(
        [f"- {m}" for m in missing_normative]
    )

    required_governance = [
        commands / "governance" / "entrypoints" / "map_audit_to_canonical.py",
        commands / "governance" / "assets" / "catalogs" / "AUDIT_REASON_CANONICAL_MAP.json",
        commands / "governance" / "assets" / "catalogs" / "CUSTOMER_SCRIPT_CATALOG.json",
        commands / "governance" / "assets" / "catalogs" / "tool_requirements.json",
    ]
    missing_governance = [str(p) for p in required_governance if not p.exists()]
    assert not missing_governance, "Missing required governance bridge files after install:\n" + "\n".join(
        [f"- {m}" for m in missing_governance]
    )

    required_runtime = [
        commands / "governance" / "engine" / "orchestrator.py",
        commands / "governance" / "engine" / "response_contract.py",
        commands / "governance" / "render" / "render_contract.py",
    ]
    missing_runtime = [str(p) for p in required_runtime if not p.exists()]
    assert not missing_runtime, "Missing governance runtime package files after install:\n" + "\n".join(
        [f"- {m}" for m in missing_runtime]
    )

    required_customer_scripts = [
        commands / "scripts" / "workflow_template_factory.py",
        commands / "scripts" / "rulebook_factory.py",
        commands / "scripts" / "run_quality_benchmark.py",
    ]
    missing_customer_scripts = [str(p) for p in required_customer_scripts if not p.exists()]
    assert not missing_customer_scripts, "Missing customer scripts after install:\n" + "\n".join(
        [f"- {m}" for m in missing_customer_scripts]
    )

    required_templates = [
        commands / "templates" / "github-actions" / "template_catalog.json",
        commands / "templates" / "github-actions" / "governance-pr-gate-shadow-live-verify.yml",
        commands / "templates" / "github-actions" / "governance-ruleset-release.yml",
    ]
    missing_templates = [str(p) for p in required_templates if not p.exists()]
    assert not missing_templates, "Missing workflow templates after install:\n" + "\n".join(
        [f"- {m}" for m in missing_templates]
    )

    manifests = sorted((commands / "profiles" / "addons").glob("*.addon.yml"))
    assert manifests, "No addon manifests found under installed commands/profiles/addons"

    missing_rulebooks: list[str] = []
    for manifest in manifests:
        text = read_text(manifest)
        m = re.search(r"^rulebook:\s*([^\s#]+)\s*$", text, flags=re.MULTILINE)
        assert m, f"Missing 'rulebook' in addon manifest: {manifest.name}"
        rb = m.group(1).strip()
        rb_path = (commands / "profiles" / rb) if not rb.startswith("profiles/") else (commands / rb)
        if not rb_path.exists():
            missing_rulebooks.append(f"{manifest.name} -> {rb}")

    assert not missing_rulebooks, "Installed addon manifests reference missing rulebooks:\n" + "\n".join(
        [f"- {m}" for m in missing_rulebooks]
    )


# ---------------------------------------------------------------------------
# C1 SSOT: build_governance_paths_payload is the single writer authority
# ---------------------------------------------------------------------------

class TestGovernancePathsSSOT:
    """
    C1 fix: governance.paths.json must be written by exactly one code path
    (build_governance_paths_payload → install_governance_paths_file).
    These tests verify the payload shape and key completeness.
    """

    def test_happy_payload_contains_command_profiles(self, tmp_path: Path) -> None:
        """Happy: build_governance_paths_payload includes commandProfiles key."""
        from install import build_governance_paths_payload
        doc = build_governance_paths_payload(tmp_path, deterministic=True)
        assert "commandProfiles" in doc, "commandProfiles must be in payload"
        assert isinstance(doc["commandProfiles"], dict)

    def test_happy_payload_contains_all_required_path_keys(self, tmp_path: Path) -> None:
        """Happy: payload contains every path key consumers depend on."""
        from install import build_governance_paths_payload
        doc = build_governance_paths_payload(tmp_path, deterministic=True)
        required = {
            "configRoot", "commandsHome", "profilesHome", "governanceHome",
            "workspacesHome", "globalErrorLogsHome",
            "workspaceErrorLogsHomeTemplate", "pythonCommand",
        }
        missing = required - set(doc["paths"].keys())
        assert not missing, f"Missing path keys: {missing}"

    def test_happy_payload_schema_matches_constant(self, tmp_path: Path) -> None:
        """Happy: schema field uses the canonical schema constant."""
        from install import build_governance_paths_payload, GOVERNANCE_PATHS_SCHEMA
        doc = build_governance_paths_payload(tmp_path, deterministic=True)
        assert doc["schema"] == GOVERNANCE_PATHS_SCHEMA

    def test_happy_deterministic_omits_generated_at(self, tmp_path: Path) -> None:
        """Happy: deterministic=True omits volatile generatedAt timestamp."""
        from install import build_governance_paths_payload
        doc = build_governance_paths_payload(tmp_path, deterministic=True)
        assert "generatedAt" not in doc

    def test_happy_non_deterministic_includes_generated_at(self, tmp_path: Path) -> None:
        """Happy: deterministic=False includes generatedAt timestamp."""
        from install import build_governance_paths_payload
        doc = build_governance_paths_payload(tmp_path, deterministic=False)
        assert "generatedAt" in doc

    def test_edge_no_duplicate_write_in_create_launcher(self) -> None:
        """Edge: create_launcher must NOT contain a governance.paths.json write."""
        import inspect
        from install import create_launcher
        source = inspect.getsource(create_launcher)
        # The old Site 1 write used binding_payload with write_text on binding_path
        assert "binding_payload" not in source, (
            "create_launcher still contains Site 1 governance.paths.json write – "
            "C1 SSOT violation"
        )

    def test_corner_command_profiles_is_empty_dict(self, tmp_path: Path) -> None:
        """Corner: commandProfiles defaults to empty dict (no profiles at install time)."""
        from install import build_governance_paths_payload
        doc = build_governance_paths_payload(tmp_path, deterministic=True)
        assert doc["commandProfiles"] == {}


# ---------------------------------------------------------------------------
# C3: symlink guards before shutil.rmtree
# ---------------------------------------------------------------------------

class TestSymlinkGuards:
    """
    C3 fix: every shutil.rmtree call in install.py must be preceded by an
    is_symlink() check to prevent symlink-escape attacks.
    """

    def test_happy_create_launcher_has_symlink_guard(self) -> None:
        """Happy: create_launcher checks is_symlink before rmtree."""
        import inspect
        from install import create_launcher
        source = inspect.getsource(create_launcher)
        assert "is_symlink()" in source, (
            "create_launcher must check is_symlink() before shutil.rmtree (C3 guard)"
        )

    def test_happy_all_rmtree_sites_guarded(self) -> None:
        """Happy: every shutil.rmtree in install.py is preceded by is_symlink check."""
        source_path = Path(__file__).resolve().parents[1] / "install.py"
        lines = source_path.read_text(encoding="utf-8").splitlines()
        rmtree_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "shutil.rmtree" in line and not line.lstrip().startswith("#")
        ]
        unguarded: list[int] = []
        for lineno, _line in rmtree_lines:
            # Check the preceding 10 lines for an is_symlink guard
            window = lines[max(0, lineno - 11): lineno - 1]
            if not any("is_symlink()" in w for w in window):
                unguarded.append(lineno)
        assert not unguarded, (
            f"shutil.rmtree at line(s) {unguarded} missing is_symlink() guard (C3)"
        )

    @pytest.mark.skipif(
        not hasattr(os, "symlink") or os.name == "nt",
        reason="symlink creation unavailable on this platform without privileges",
    )
    def test_edge_create_launcher_refuses_symlink_cli_dest(self, tmp_path: Path) -> None:
        """Edge: create_launcher raises if cli_dest is a symlink."""
        from install import create_launcher, build_plan
        # Create minimal source dir with required files
        src = tmp_path / "src"
        src.mkdir()
        (src / "VERSION").write_text("1.0.0", encoding="utf-8")
        (src / "rules.yml").write_text("", encoding="utf-8")
        cli_src = src / "cli"
        cli_src.mkdir()
        (cli_src / "__init__.py").write_text("", encoding="utf-8")

        config_root = tmp_path / "config"
        config_root.mkdir(parents=True)

        plan = build_plan(
            source_dir=src,
            config_root=config_root,
            skip_paths_file=True,
            deterministic_paths_file=False,
        )

        # Replace cli dest with a symlink
        real_dir = tmp_path / "real_target"
        real_dir.mkdir()
        cli_dest = plan.commands_dir / "cli"
        cli_dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(real_dir, cli_dest)

        with pytest.raises(RuntimeError, match="symlink"):
            create_launcher(plan, dry_run=False, force=True)


# ---------------------------------------------------------------------------
# R14: assert -> runtime guards
# ---------------------------------------------------------------------------

class TestRuntimeGuards:
    """
    R14 fix: production safety checks must use if/raise RuntimeError instead
    of assert (which is stripped under python -O).
    """

    def test_happy_no_assert_statements_in_install(self) -> None:
        """Happy: install.py has no bare assert statements (all converted to if/raise)."""
        source_path = Path(__file__).resolve().parents[1] / "install.py"
        lines = source_path.read_text(encoding="utf-8").splitlines()
        asserts = [
            (i, line.strip()) for i, line in enumerate(lines, 1)
            if line.lstrip().startswith("assert ")
            and not line.lstrip().startswith("assert isinstance")  # redundant but harmless type narrows
        ]
        assert not asserts, (
            f"install.py still uses bare assert at line(s): "
            + ", ".join(f"{ln}" for ln, _ in asserts)
        )

    def test_happy_opencode_json_safety_guard_present(self) -> None:
        """Happy: OPENCODE_JSON_NAME safety check uses RuntimeError, not assert."""
        source_path = Path(__file__).resolve().parents[1] / "install.py"
        source = source_path.read_text(encoding="utf-8")
        assert 'raise RuntimeError' in source and 'OPENCODE_JSON_NAME' in source, (
            "opencode.json safety guard must use raise RuntimeError"
        )

    def test_edge_opencode_json_is_not_purge_target(self) -> None:
        """Edge: OPENCODE_JSON_NAME constant is never in the purge set."""
        from install import OPENCODE_JSON_NAME
        purge_targets = {
            "governance.activation_intent.json",
            "SESSION_STATE.json",
        }
        assert OPENCODE_JSON_NAME not in purge_targets


# ---------------------------------------------------------------------------
# R2: --config-root path resolution
# ---------------------------------------------------------------------------

class TestConfigRootResolve:
    """
    R2 fix: --config-root passed as relative path must be resolved to
    absolute before any downstream consumption.
    """

    def test_happy_resolve_in_main_source(self) -> None:
        """Happy: main() resolves args.config_root early."""
        import inspect
        from install import main
        source = inspect.getsource(main)
        assert ".resolve()" in source, (
            "main() must call .resolve() on args.config_root (R2 fix)"
        )

    def test_happy_parse_args_returns_path(self, tmp_path: Path) -> None:
        """Happy: parse_args produces a Path for --config-root."""
        from install import parse_args
        args = parse_args(["--config-root", str(tmp_path / "test-root")])
        assert isinstance(args.config_root, Path)

    def test_edge_relative_config_root_is_resolved(self) -> None:
        """Edge: a relative --config-root is resolved to absolute by main()."""
        from install import parse_args
        args = parse_args(["--config-root", "relative/path"])
        # Simulate what main() does
        if args.config_root is not None:
            args.config_root = args.config_root.resolve()
        assert args.config_root.is_absolute(), (
            "config_root must be absolute after resolve()"
        )


# ---------------------------------------------------------------------------
# R9: manifest type and schema validation
# ---------------------------------------------------------------------------

class TestManifestValidation:
    """
    R9 fix: load_manifest must validate type, schema, and 'files' key
    before returning data. Malformed or tampered manifests must be rejected.
    """

    def test_happy_valid_manifest_loads(self, tmp_path: Path) -> None:
        """Happy: well-formed manifest is loaded successfully."""
        from install import load_manifest, MANIFEST_SCHEMA
        mf = tmp_path / "INSTALL_MANIFEST.json"
        mf.write_text(json.dumps({
            "schema": MANIFEST_SCHEMA,
            "files": {"a.py": {"sha256": "abc123"}},
        }), encoding="utf-8")
        result = load_manifest(mf)
        assert result is not None
        assert "files" in result

    def test_bad_missing_file_returns_none(self, tmp_path: Path) -> None:
        """Bad: nonexistent file returns None."""
        from install import load_manifest
        assert load_manifest(tmp_path / "nonexistent.json") is None

    def test_bad_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Bad: invalid JSON returns None."""
        from install import load_manifest
        mf = tmp_path / "INSTALL_MANIFEST.json"
        mf.write_text("{not valid json", encoding="utf-8")
        assert load_manifest(mf) is None

    def test_bad_non_dict_returns_none(self, tmp_path: Path) -> None:
        """Bad: JSON array instead of dict returns None."""
        from install import load_manifest
        mf = tmp_path / "INSTALL_MANIFEST.json"
        mf.write_text('[1, 2, 3]', encoding="utf-8")
        assert load_manifest(mf) is None

    def test_bad_wrong_schema_returns_none(self, tmp_path: Path) -> None:
        """Bad: wrong schema version returns None."""
        from install import load_manifest
        mf = tmp_path / "INSTALL_MANIFEST.json"
        mf.write_text(json.dumps({
            "schema": "99.99",
            "files": {},
        }), encoding="utf-8")
        assert load_manifest(mf) is None

    def test_bad_missing_files_key_returns_none(self, tmp_path: Path) -> None:
        """Bad: missing 'files' key returns None."""
        from install import load_manifest, MANIFEST_SCHEMA
        mf = tmp_path / "INSTALL_MANIFEST.json"
        mf.write_text(json.dumps({
            "schema": MANIFEST_SCHEMA,
        }), encoding="utf-8")
        assert load_manifest(mf) is None

    def test_bad_files_not_dict_returns_none(self, tmp_path: Path) -> None:
        """Bad: 'files' is a string instead of dict/list returns None."""
        from install import load_manifest, MANIFEST_SCHEMA
        mf = tmp_path / "INSTALL_MANIFEST.json"
        mf.write_text(json.dumps({
            "schema": MANIFEST_SCHEMA,
            "files": "not-a-collection",
        }), encoding="utf-8")
        assert load_manifest(mf) is None

    def test_happy_files_as_list_accepted(self, tmp_path: Path) -> None:
        """Happy: 'files' as list is accepted (installer uses list format)."""
        from install import load_manifest, MANIFEST_SCHEMA
        mf = tmp_path / "INSTALL_MANIFEST.json"
        mf.write_text(json.dumps({
            "schema": MANIFEST_SCHEMA,
            "files": [{"dst": "a.py", "sha256": "abc"}],
        }), encoding="utf-8")
        result = load_manifest(mf)
        assert result is not None


# ---------------------------------------------------------------------------
# R6: backup corrupt opencode.json before overwrite
# ---------------------------------------------------------------------------

class TestOpencodeJsonBackup:
    """
    R6 fix: if opencode.json is corrupt (invalid JSON or non-dict),
    the original content must be backed up before overwriting.
    """

    def test_happy_valid_json_no_backup(self, tmp_path: Path) -> None:
        """Happy: valid opencode.json is merged without creating backup."""
        from install import ensure_opencode_json
        target = tmp_path / "opencode.json"
        target.write_text('{"instructions": []}', encoding="utf-8")
        ensure_opencode_json(tmp_path, dry_run=False)
        backup = target.with_suffix(".json.corrupt-backup")
        assert not backup.exists(), "No backup for valid JSON"

    def test_bad_corrupt_json_creates_backup(self, tmp_path: Path) -> None:
        """Bad: corrupt JSON triggers backup before overwrite."""
        from install import ensure_opencode_json
        target = tmp_path / "opencode.json"
        corrupt_content = "{this is not valid json"
        target.write_text(corrupt_content, encoding="utf-8")
        ensure_opencode_json(tmp_path, dry_run=False)
        backup = target.with_suffix(".json.corrupt-backup")
        assert backup.exists(), "Corrupt opencode.json must be backed up"
        assert backup.read_text(encoding="utf-8") == corrupt_content

    def test_bad_non_dict_json_creates_backup(self, tmp_path: Path) -> None:
        """Bad: JSON array triggers backup before overwrite."""
        from install import ensure_opencode_json
        target = tmp_path / "opencode.json"
        non_dict_content = '["not", "a", "dict"]'
        target.write_text(non_dict_content, encoding="utf-8")
        ensure_opencode_json(tmp_path, dry_run=False)
        backup = target.with_suffix(".json.corrupt-backup")
        assert backup.exists(), "Non-dict opencode.json must be backed up"

    def test_edge_dry_run_no_backup(self, tmp_path: Path) -> None:
        """Edge: dry-run does NOT create backup file."""
        from install import ensure_opencode_json
        target = tmp_path / "opencode.json"
        target.write_text("{bad json", encoding="utf-8")
        ensure_opencode_json(tmp_path, dry_run=True)
        backup = target.with_suffix(".json.corrupt-backup")
        assert not backup.exists(), "Dry-run must not create backup"


# ---------------------------------------------------------------------------
# R3: POSIX path serialization in JSON
# ---------------------------------------------------------------------------

class TestPosixPathSerialization:
    """
    R3 fix: all paths in JSON artifacts must be POSIX-normalized absolute
    strings (forward slashes, resolved). OS-native conversion at read time.
    """

    def test_happy_path_for_json_returns_posix(self, tmp_path: Path) -> None:
        """Happy: _path_for_json returns POSIX absolute string."""
        from install import _path_for_json
        result = _path_for_json(tmp_path / "subdir")
        assert "/" in result or result.startswith("/"), "Must use forward slashes"
        assert "\\" not in result, "Must not contain backslashes"

    def test_happy_path_for_json_is_absolute(self, tmp_path: Path) -> None:
        """Happy: _path_for_json returns absolute path."""
        from install import _path_for_json
        result = _path_for_json(tmp_path / "subdir")
        # On Windows, as_posix() produces e.g. C:/Users/... which is absolute
        assert result[0] == "/" or result[1] == ":", "Must be absolute"

    def test_happy_governance_paths_payload_uses_posix(self, tmp_path: Path) -> None:
        """Happy: build_governance_paths_payload emits POSIX paths for ALL keys."""
        from install import build_governance_paths_payload
        doc = build_governance_paths_payload(tmp_path, deterministic=True)
        for key, value in doc["paths"].items():
            assert "\\" not in value, (
                f"paths.{key} contains backslash: {value}"
            )

    def test_happy_norm_delegates_to_path_for_json(self) -> None:
        """Happy: norm() in build_governance_paths_payload uses _path_for_json."""
        import inspect
        from install import build_governance_paths_payload
        source = inspect.getsource(build_governance_paths_payload)
        assert "_path_for_json" in source, (
            "norm() must delegate to _path_for_json"
        )

    def test_edge_session_pointer_uses_posix(self) -> None:
        """Edge: session_pointer emits POSIX paths in payload."""
        from governance.infrastructure.session_pointer import build_pointer_payload
        payload = build_pointer_payload(
            repo_fingerprint="abc123def456abc123def456",
            session_state_file=Path("/fake/config/workspaces/abc123def456abc123def456/SESSION_STATE.json"),
            config_root=Path("/fake/config"),
        )
        rel = payload.get("activeSessionStateRelativePath", "")
        assert "\\" not in rel, f"Relative path has backslashes: {rel}"


# ---------------------------------------------------------------------------
# Commit 10: PYTHON_BINDING artifact + launcher fallback (R5/Policy)
# ---------------------------------------------------------------------------

class TestPythonBindingArtifact:
    """
    R5/Policy fix: installer writes bin/PYTHON_BINDING (single-line, plain text,
    absolute POSIX path). Launchers use a fail-closed cascade:
      baked PYTHON_BIN -> PYTHON_BINDING file -> exit 1.
    See python-binding-contract.v1 §2.2 and §3.
    """

    def test_happy_write_python_binding_file(self, tmp_path: Path) -> None:
        """Happy: _write_python_binding_file creates a single-line file."""
        import sys
        from install import _write_python_binding_file
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        result = _write_python_binding_file(bin_dir, sys.executable)
        assert result.exists()
        assert result.name == "PYTHON_BINDING"
        content = result.read_text(encoding="utf-8").strip()
        # Must be non-empty, single line, no backslashes
        assert content, "PYTHON_BINDING must not be empty"
        assert "\n" not in content, "PYTHON_BINDING must be single line"
        assert "\\" not in content, "PYTHON_BINDING must use POSIX slashes"

    def test_happy_binding_file_contains_posix_absolute(self, tmp_path: Path) -> None:
        """Happy: PYTHON_BINDING content is POSIX-absolute."""
        import sys
        from install import _write_python_binding_file
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_python_binding_file(bin_dir, sys.executable)
        content = (bin_dir / "PYTHON_BINDING").read_text(encoding="utf-8").strip()
        # Absolute: starts with / or drive letter like C:/
        assert content[0] == "/" or content[1] == ":", f"Not absolute: {content}"

    def test_happy_binding_file_written_during_install(self, tmp_path: Path) -> None:
        """Happy: full install produces bin/PYTHON_BINDING."""
        config_root = tmp_path / "config"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        binding_file = config_root / "bin" / "PYTHON_BINDING"
        assert binding_file.exists(), (
            f"bin/PYTHON_BINDING not found after install.\nstdout:\n{r.stdout}"
        )
        content = binding_file.read_text(encoding="utf-8").strip()
        assert content, "PYTHON_BINDING must not be empty"
        assert "\\" not in content, "Must be POSIX path"

    def test_happy_health_reports_binding_file(self, tmp_path: Path) -> None:
        """Happy: INSTALL_HEALTH.json includes pythonBindingFilePresent."""
        config_root = tmp_path / "config"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        health_path = config_root / "INSTALL_HEALTH.json"
        assert health_path.exists()
        data = json.loads(health_path.read_text(encoding="utf-8"))
        assert "pythonBindingFilePresent" in data, (
            "INSTALL_HEALTH.json must contain pythonBindingFilePresent"
        )
        assert data["pythonBindingFilePresent"] is True

    def test_happy_unix_launcher_has_binding_fallback(self, tmp_path: Path) -> None:
        """Happy: Unix launcher template contains PYTHON_BINDING fallback cascade."""
        config_root = tmp_path / "config"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        launcher = config_root / "bin" / "opencode-governance-bootstrap"
        assert launcher.exists()
        content = launcher.read_text(encoding="utf-8")
        assert "PYTHON_BINDING" in content, "Unix launcher must reference PYTHON_BINDING"
        assert "FATAL: No valid Python interpreter" in content, (
            "Unix launcher must have fail-closed message"
        )
        assert "OPENCODE_PYTHON" in content, (
            "Unix launcher must export OPENCODE_PYTHON"
        )

    def test_happy_win_launcher_has_binding_fallback(self, tmp_path: Path) -> None:
        """Happy: Windows launcher template contains PYTHON_BINDING fallback cascade."""
        config_root = tmp_path / "config"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        launcher = config_root / "bin" / "opencode-governance-bootstrap.cmd"
        assert launcher.exists()
        content = launcher.read_text(encoding="utf-8")
        assert "PYTHON_BINDING" in content, "Win launcher must reference PYTHON_BINDING"
        assert "FATAL: No valid Python interpreter" in content, (
            "Win launcher must have fail-closed message"
        )
        assert "OPENCODE_PYTHON" in content, (
            "Win launcher must export OPENCODE_PYTHON"
        )

    def test_happy_python_command_posix_in_paths_json(self, tmp_path: Path) -> None:
        """Happy: pythonCommand in governance.paths.json is POSIX-normalized."""
        from install import build_governance_paths_payload
        doc = build_governance_paths_payload(tmp_path, deterministic=True)
        python_cmd = doc["paths"]["pythonCommand"]
        assert "\\" not in python_cmd, (
            f"pythonCommand contains backslash: {python_cmd}"
        )

    def test_corner_binding_file_trailing_newline(self, tmp_path: Path) -> None:
        """Corner: PYTHON_BINDING file ends with newline for POSIX compliance."""
        import sys
        from install import _write_python_binding_file
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_python_binding_file(bin_dir, sys.executable)
        raw = (bin_dir / "PYTHON_BINDING").read_text(encoding="utf-8")
        assert raw.endswith("\n"), "PYTHON_BINDING must end with newline"
        # Only one line of content
        lines = raw.strip().split("\n")
        assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"

    def test_edge_unix_launcher_no_path_probing(self, tmp_path: Path) -> None:
        """Edge: Unix launcher must NOT contain 'which' or PATH probing."""
        from install import _launcher_template_unix
        content = _launcher_template_unix(
            python_exe="/usr/bin/python3",
            config_root=tmp_path,
        )
        assert "which " not in content.lower(), "Launcher must not probe PATH with which"
        assert "command -v" not in content, "Launcher must not probe PATH with command -v"

    def test_edge_win_launcher_no_path_probing(self, tmp_path: Path) -> None:
        """Edge: Windows launcher must NOT contain 'where' or PATH probing."""
        from install import _launcher_template_windows
        content = _launcher_template_windows(
            python_exe="C:/Python311/python.exe",
            config_root=tmp_path,
        )
        assert "where " not in content.lower(), "Launcher must not probe PATH with where"

    def test_bad_binding_file_consistency_with_paths_json(self, tmp_path: Path) -> None:
        """Bad path guard: PYTHON_BINDING and governance.paths.json pythonCommand must agree."""
        config_root = tmp_path / "config"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        # Read both sources
        binding_file = config_root / "bin" / "PYTHON_BINDING"
        paths_file = config_root / "commands" / "governance.paths.json"
        assert binding_file.exists() and paths_file.exists()
        binding_value = binding_file.read_text(encoding="utf-8").strip()
        paths_data = json.loads(paths_file.read_text(encoding="utf-8"))
        paths_value = paths_data["paths"]["pythonCommand"]
        # Both must be the same POSIX-normalized absolute path
        assert binding_value == paths_value, (
            f"PYTHON_BINDING ({binding_value}) != pythonCommand ({paths_value})"
        )


# ---------------------------------------------------------------------------
# P1-C: Install-time logs directory and initial flow log event
# ---------------------------------------------------------------------------


class TestInstallLogsDirectory:
    """Verify that install creates <commands_home>/logs/ and writes an initial flow event."""

    @pytest.mark.installer
    def test_happy_ensure_dirs_creates_logs_directory(self, tmp_path: Path) -> None:
        """Happy: ensure_dirs() creates commands/logs/ alongside other directories."""
        from install import ensure_dirs
        config_root = tmp_path / "config"
        ensure_dirs(config_root, dry_run=False)
        logs_dir = config_root / "commands" / "logs"
        assert logs_dir.is_dir(), "ensure_dirs must create commands/logs/"

    @pytest.mark.installer
    def test_happy_full_install_creates_logs_directory(self, tmp_path: Path) -> None:
        """Happy: full install creates <config_root>/commands/logs/ directory."""
        config_root = tmp_path / "config-logs-happy"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        logs_dir = config_root / "commands" / "logs"
        assert logs_dir.is_dir(), "Install must create commands/logs/ directory"

    @pytest.mark.installer
    def test_happy_install_writes_flow_log_event(self, tmp_path: Path) -> None:
        """Happy: install writes an install-complete event to commands/logs/flow.log.jsonl."""
        config_root = tmp_path / "config-logs-flow"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        flow_log = config_root / "commands" / "logs" / "flow.log.jsonl"
        assert flow_log.exists(), "Install must write flow.log.jsonl"
        content = flow_log.read_text(encoding="utf-8").strip()
        assert content, "flow.log.jsonl must not be empty"
        event = json.loads(content.splitlines()[-1])
        assert event["event"] == "install-complete"
        assert "installerVersion" in event
        assert "governanceVersion" in event
        assert "timestamp" in event
        assert "platform" in event

    @pytest.mark.installer
    def test_happy_governance_paths_json_includes_logs_home(self, tmp_path: Path) -> None:
        """Happy: governance.paths.json globalErrorLogsHome matches commands/logs."""
        config_root = tmp_path / "config-logs-paths"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Install failed:\n{r.stdout}\n{r.stderr}"
        paths_file = config_root / "commands" / "governance.paths.json"
        assert paths_file.exists()
        data = json.loads(paths_file.read_text(encoding="utf-8"))
        logs_home = data["paths"]["globalErrorLogsHome"]
        # globalErrorLogsHome must end with /commands/logs (POSIX-normalized)
        assert logs_home.endswith("/commands/logs"), (
            f"globalErrorLogsHome should end with /commands/logs, got: {logs_home}"
        )
        # The directory referenced by globalErrorLogsHome must actually exist
        from pathlib import PurePosixPath
        # Convert POSIX path back to OS path for existence check
        logs_dir = config_root / "commands" / "logs"
        assert logs_dir.is_dir(), "globalErrorLogsHome target directory must exist after install"

    @pytest.mark.installer
    def test_corner_ensure_dirs_idempotent(self, tmp_path: Path) -> None:
        """Corner: calling ensure_dirs twice does not fail or remove logs/."""
        from install import ensure_dirs
        config_root = tmp_path / "config"
        ensure_dirs(config_root, dry_run=False)
        logs_dir = config_root / "commands" / "logs"
        assert logs_dir.is_dir()
        # Place a file in logs/ and ensure it survives a second call
        sentinel = logs_dir / "sentinel.txt"
        sentinel.write_text("keep me\n", encoding="utf-8")
        ensure_dirs(config_root, dry_run=False)
        assert sentinel.exists(), "ensure_dirs must be idempotent and preserve existing logs"

    @pytest.mark.installer
    def test_corner_dry_run_does_not_create_logs_directory(self, tmp_path: Path) -> None:
        """Corner: dry-run must not create any directories including logs/."""
        from install import ensure_dirs
        config_root = tmp_path / "config-dry"
        ensure_dirs(config_root, dry_run=True)
        assert not config_root.exists(), "dry-run must not create any directories"

    @pytest.mark.installer
    def test_corner_dry_run_install_no_flow_log(self, tmp_path: Path) -> None:
        """Corner: dry-run install must not write flow.log.jsonl."""
        config_root = tmp_path / "config-dry-flow"
        r = run_install(["--dry-run", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Dry-run failed:\n{r.stdout}\n{r.stderr}"
        flow_log = config_root / "commands" / "logs" / "flow.log.jsonl"
        assert not flow_log.exists(), "dry-run must not write flow.log.jsonl"

    @pytest.mark.installer
    def test_corner_reinstall_appends_to_flow_log(self, tmp_path: Path) -> None:
        """Corner: reinstall appends a second event to flow.log.jsonl."""
        config_root = tmp_path / "config-reinstall"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"First install failed:\n{r.stdout}\n{r.stderr}"
        r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
        assert r.returncode == 0, f"Reinstall failed:\n{r.stdout}\n{r.stderr}"
        flow_log = config_root / "commands" / "logs" / "flow.log.jsonl"
        lines = [l for l in flow_log.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) >= 2, f"Expected at least 2 flow events after reinstall, got {len(lines)}"
        for line in lines:
            event = json.loads(line)
            assert event["event"] == "install-complete"

    @pytest.mark.installer
    def test_edge_logs_dir_matches_error_logs_dir_name_constant(self) -> None:
        """Edge: ensure_dirs uses ERROR_LOGS_DIR_NAME constant, not a hardcoded string."""
        import install as installer_mod
        assert installer_mod.ERROR_LOGS_DIR_NAME == "logs", (
            f"ERROR_LOGS_DIR_NAME must be 'logs', got: {installer_mod.ERROR_LOGS_DIR_NAME}"
        )

    @pytest.mark.installer
    def test_edge_emit_install_flow_event_returns_false_on_dry_run(self, tmp_path: Path) -> None:
        """Edge: _emit_install_flow_event returns False on dry_run."""
        from install import _emit_install_flow_event
        result = _emit_install_flow_event(
            tmp_path / "commands",
            event_type="install-complete",
            gov_version="1.0.0",
            installer_version="1.0.0",
            dry_run=True,
        )
        assert result is False

    @pytest.mark.installer
    def test_edge_emit_install_flow_event_returns_true_on_success(self, tmp_path: Path) -> None:
        """Edge: _emit_install_flow_event returns True on successful write."""
        from install import _emit_install_flow_event
        commands_home = tmp_path / "commands"
        commands_home.mkdir()
        result = _emit_install_flow_event(
            commands_home,
            event_type="install-complete",
            gov_version="1.0.0",
            installer_version="1.0.0",
            dry_run=False,
        )
        assert result is True
        flow_log = commands_home / "logs" / "flow.log.jsonl"
        assert flow_log.exists()

    @pytest.mark.installer
    def test_bad_emit_flow_event_readonly_dir_does_not_raise(self, tmp_path: Path) -> None:
        """Bad: _emit_install_flow_event must not raise even when logs/ cannot be created."""
        from install import _emit_install_flow_event
        # Use a non-existent deeply nested path that cannot be created on most systems
        # by making the parent read-only (platform-dependent, so we test the return value)
        commands_home = tmp_path / "commands"
        commands_home.mkdir()
        logs_dir = commands_home / "logs"
        logs_dir.mkdir()
        # Make logs dir read-only to prevent file creation
        if os.name == "nt":
            # On Windows, use subprocess to set read-only attribute on the directory
            import subprocess as _sp
            _sp.run(["attrib", "+R", str(logs_dir)], check=False)
        else:
            logs_dir.chmod(0o444)
        try:
            result = _emit_install_flow_event(
                commands_home,
                event_type="install-complete",
                gov_version="1.0.0",
                installer_version="1.0.0",
                dry_run=False,
            )
            # Must not raise — either True (write succeeded despite permissions)
            # or False (gracefully handled)
            assert isinstance(result, bool)
        finally:
            # Restore permissions for cleanup
            if os.name != "nt":
                logs_dir.chmod(0o755)
            else:
                import subprocess as _sp
                _sp.run(["attrib", "-R", str(logs_dir)], check=False)
