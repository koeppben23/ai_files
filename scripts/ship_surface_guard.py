#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path


EXPECTED_CONFIG_TOP_LEVEL = {
    "INSTALL_HEALTH.json",
    "INSTALL_MANIFEST.json",
    "bin",
    "commands",
    "governance.paths.json",
    "opencode.json",
    "plugins",
    "workspaces",
}

EXPECTED_LOCAL_TOP_LEVEL = {
    "VERSION",
    "governance_content",
    "governance_runtime",
    "governance_spec",
}

FORBIDDEN_INSTALL_TOKENS = (
    "archived/",
    "historical/",
    "governance_content/governance/assets/catalogs/audit.md",
    "governance_runtime/assets/reasons/blocked_reason_catalog.yaml",
    "governance_runtime/bin/opencode-governance-bootstrap",
    "governance_runtime/bin/opencode-governance-bootstrap.cmd",
)

FORBIDDEN_DIST_TOKENS = (
    "archived/",
    "historical/",
    "governance_content/governance/assets/catalogs/audit.md",
    "governance_runtime/assets/reasons/blocked_reason_catalog.yaml",
    "governance_runtime/bin/opencode-governance-bootstrap",
    "governance_runtime/bin/opencode-governance-bootstrap.cmd",
)

ALLOWED_MARKER_INIT_PATHS_PREFIXES = (
    "governance_runtime/infrastructure/rendering/__init__.py",
    "local/governance_runtime/infrastructure/rendering/__init__.py",
)


def _is_marker_init_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped in {"__all__ = []", "__all__=[]"}:
        return True
    if stripped.startswith("#") and "\n" not in stripped:
        return True
    if stripped in {'"""Package marker."""', '"""Namespace package marker."""'}:
        return True
    return False


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify install/artifact ship surfaces are lean")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    return parser.parse_args(argv)


def _list_top_level(root: Path) -> set[str]:
    return {entry.name for entry in root.iterdir()}


def _iter_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _check_install_surface(repo_root: Path, *, python_cmd: str) -> list[str]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ship-surface-") as tmp:
        tmp_root = Path(tmp)
        config_root = tmp_root / "config"
        local_root = tmp_root / "local"
        config_root.mkdir(parents=True, exist_ok=True)
        local_root.mkdir(parents=True, exist_ok=True)

        cmd = [
            python_cmd,
            "-X",
            "utf8",
            "install.py",
            "--force",
            "--no-backup",
            "--config-root",
            str(config_root),
            "--local-root",
            str(local_root),
        ]
        result = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)
        if result.returncode != 0:
            issues.append("install failed during ship-surface guard")
            issues.append(result.stderr.strip() or result.stdout.strip())
            return issues

        config_entries = _list_top_level(config_root)
        local_entries = _list_top_level(local_root)

        extra_config = sorted(config_entries - EXPECTED_CONFIG_TOP_LEVEL)
        missing_config = sorted(EXPECTED_CONFIG_TOP_LEVEL - config_entries)
        if extra_config:
            issues.append("config root unexpected entries: " + ", ".join(extra_config))
        if missing_config:
            issues.append("config root missing entries: " + ", ".join(missing_config))

        extra_local = sorted(local_entries - EXPECTED_LOCAL_TOP_LEVEL)
        missing_local = sorted(EXPECTED_LOCAL_TOP_LEVEL - local_entries)
        if extra_local:
            issues.append("local root unexpected entries: " + ", ".join(extra_local))
        if missing_local:
            issues.append("local root missing entries: " + ", ".join(missing_local))

        for file_path in _iter_files(config_root) + _iter_files(local_root):
            rel = file_path.relative_to(tmp_root).as_posix()
            if file_path.name == "__init__.py":
                text = file_path.read_text(encoding="utf-8", errors="replace")
                if _is_marker_init_text(text):
                    if not any(rel.endswith(prefix) for prefix in ALLOWED_MARKER_INIT_PATHS_PREFIXES):
                        issues.append(f"install surface contains marker-only __init__.py: {rel}")
            for token in FORBIDDEN_INSTALL_TOKENS:
                if token in rel:
                    issues.append(f"install surface contains forbidden path token '{token}': {rel}")

        uninstall_cmd = [
            python_cmd,
            "-X",
            "utf8",
            "install.py",
            "--uninstall",
            "--force",
            "--config-root",
            str(config_root),
            "--local-root",
            str(local_root),
        ]
        subprocess.run(uninstall_cmd, cwd=str(repo_root), text=True, capture_output=True)

    return issues


def _scan_zip(path: Path) -> list[str]:
    names: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        names = [name for name in zf.namelist() if not name.endswith("/")]
    return names


def _scan_zip_marker_inits(path: Path) -> list[str]:
    offenders: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            if not name.endswith("/__init__.py"):
                continue
            text = zf.read(name).decode("utf-8", errors="replace")
            if _is_marker_init_text(text):
                offenders.append(name)
    return offenders


def _scan_tgz(path: Path) -> list[str]:
    names: list[str] = []
    with tarfile.open(path, "r:gz") as tf:
        names = [member.name for member in tf.getmembers() if member.isfile()]
    return names


def _scan_tgz_marker_inits(path: Path) -> list[str]:
    offenders: list[str] = []
    with tarfile.open(path, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile() or not member.name.endswith("/__init__.py"):
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            text = extracted.read().decode("utf-8", errors="replace")
            if _is_marker_init_text(text):
                offenders.append(member.name)
    return offenders


def _check_dist_surface(repo_root: Path, *, python_cmd: str) -> list[str]:
    issues: list[str] = []
    tmp_out = repo_root / ".tmp_ship_surface_dist"
    if tmp_out.exists():
        shutil.rmtree(tmp_out)
    try:
        build_cmd = [python_cmd, "scripts/build.py", "--out-dir", ".tmp_ship_surface_dist"]
        result = subprocess.run(build_cmd, cwd=str(repo_root), text=True, capture_output=True)
        if result.returncode != 0:
            issues.append("artifact build failed during ship-surface guard")
            issues.append(result.stderr.strip() or result.stdout.strip())
            return issues

        archives = list(tmp_out.glob("*.zip")) + list(tmp_out.glob("*.tar.gz"))
        for archive in archives:
            if archive.suffix == ".zip":
                names = _scan_zip(archive)
                marker_inits = _scan_zip_marker_inits(archive)
            else:
                names = _scan_tgz(archive)
                marker_inits = _scan_tgz_marker_inits(archive)
            for name in names:
                for token in FORBIDDEN_DIST_TOKENS:
                    if token in name:
                        issues.append(f"artifact {archive.name} contains forbidden path '{name}'")
            for name in marker_inits:
                if not any(name.endswith(prefix) for prefix in ALLOWED_MARKER_INIT_PATHS_PREFIXES):
                    issues.append(f"artifact {archive.name} contains marker-only __init__.py: {name}")
    finally:
        if tmp_out.exists():
            shutil.rmtree(tmp_out)
    return issues


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    issues = _check_install_surface(repo_root, python_cmd=args.python)
    issues.extend(_check_dist_surface(repo_root, python_cmd=args.python))

    if issues:
        print("❌ Ship surface guard failed")
        for issue in issues:
            print(f" - {issue}")
        return 1

    print("✅ Ship surface guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
