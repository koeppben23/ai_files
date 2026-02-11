from __future__ import annotations

import json
import os
import re
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

    def assert_under_base(p: Path, label: str) -> None:
        p = p.resolve()
        try:
            p.relative_to(base)
        except ValueError:
            raise AssertionError(f"{label} escapes commands dir: {p} (base={base})")
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
            target = target if target.is_absolute() else (commands / target)
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
        commands / "start.md",
        commands / "diagnostics" / "QUICKFIX_TEMPLATES.json",
        commands / "diagnostics" / "UX_INTENT_GOLDENS.json",
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
        "diagnosticsHome",
        "workspacesHome",
        "globalErrorLogsHome",
        "workspaceErrorLogsHomeTemplate",
    ]
    missing = [k for k in required_paths if k not in p["paths"]]
    assert not missing, f"governance.paths.json missing keys: {missing}"

    commands_home = p["paths"]["commandsHome"]
    diagnostics_home = p["paths"]["diagnosticsHome"]
    dh = diagnostics_home.replace("\\", "/").rstrip("/")
    ch = commands_home.replace("\\", "/").rstrip("/")
    assert dh == f"{ch}/diagnostics" or dh.endswith("/diagnostics"), (
        f"diagnosticsHome unexpected: {diagnostics_home} (commandsHome={commands_home})"
    )

    # Capture hashes before reinstall (ignore variable files)
    ignore_names = {"governance.paths.json", MANIFEST_NAME}
    before = {}
    for target, _ in entries:
        if target.name in ignore_names:
            continue
        rel = target.resolve().relative_to(commands.resolve()).as_posix()
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
        rel = target.resolve().relative_to(commands.resolve()).as_posix()
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
        commands / "start.md",
        manifest,
        paths_file,  # this should be removed for a normal install-owned paths file
    ]
    still = [str(p) for p in must_be_gone if p.exists()]
    assert not still, f"Uninstall left artifacts behind: {still}"

    if commands.exists():
        leftovers = [p for p in commands.rglob("*") if p.is_file()]
        assert not leftovers, f"Commands dir not empty after uninstall: {[p.name for p in leftovers[:25]]}"


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
            "diagnosticsHome": str(commands / "diagnostics"),
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

    source_dir = tmp_path / "source-with-symlink"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "master.md").write_text("# Governance-Version: 1.1.0-RC.1\n", encoding="utf-8")
    (source_dir / "rules.md").write_text("# rules\n", encoding="utf-8")
    (source_dir / "start.md").write_text("# start\n", encoding="utf-8")

    external = tmp_path / "external.txt"
    external.write_text("external\n", encoding="utf-8")
    try:
        os.symlink(external, source_dir / "linked.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")

    config_root = tmp_path / "opencode-config-symlink-block"
    r = run_install([
        "--force",
        "--no-backup",
        "--source-dir",
        str(source_dir),
        "--config-root",
        str(config_root),
    ])
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
    installed = {t.resolve().relative_to(commands.resolve()).as_posix() for t, _ in entries}

    required_rel = {
        "profiles/addons/angularNxTemplates.addon.yml",
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

    required_diagnostics = [
        commands / "diagnostics" / "map_audit_to_canonical.py",
        commands / "diagnostics" / "AUDIT_REASON_CANONICAL_MAP.json",
        commands / "diagnostics" / "tool_requirements.json",
    ]
    missing_diagnostics = [str(p) for p in required_diagnostics if not p.exists()]
    assert not missing_diagnostics, "Missing required diagnostics bridge files after install:\n" + "\n".join(
        [f"- {m}" for m in missing_diagnostics]
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
