#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


EXPECTED_RAILS = {
    "audit-readout.md",
    "continue.md",
    "implement.md",
    "implementation-decision.md",
    "plan.md",
    "review-decision.md",
    "review.md",
    "ticket.md",
}

EXPECTED_CONFIG_FILES = {
    "opencode.json",
    "INSTALL_HEALTH.json",
    "INSTALL_MANIFEST.json",
    "governance.paths.json",
}

EXPECTED_CONFIG_DIRS = {"commands", "plugins", "workspaces", "bin"}

EXPECTED_LOCAL_TOP_LEVEL = {
    "governance_runtime",
    "governance_content",
    "governance_spec",
    "VERSION",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify exact install layout contract")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--python", default=sys.executable, help="Python executable for install command")
    return parser.parse_args(argv)


def _run_install(repo_root: Path, python_cmd: str, config_root: Path, local_root: Path) -> None:
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
        raise RuntimeError(f"install failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")


def _list_top_level(root: Path) -> set[str]:
    return {entry.name for entry in root.iterdir()}


def verify_install_layout(config_root: Path, local_root: Path) -> list[str]:
    issues: list[str] = []

    config_entries = _list_top_level(config_root)
    for required in EXPECTED_CONFIG_DIRS | EXPECTED_CONFIG_FILES:
        if required not in config_entries:
            issues.append(f"config root missing required entry: {required}")

    commands_dir = config_root / "commands"
    if not commands_dir.exists() or not commands_dir.is_dir():
        issues.append("config root missing commands/")
    else:
        md_files = {p.name for p in commands_dir.glob("*.md") if p.is_file()}
        if md_files != EXPECTED_RAILS:
            missing = sorted(EXPECTED_RAILS - md_files)
            extra = sorted(md_files - EXPECTED_RAILS)
            if missing:
                issues.append(f"commands missing rails: {missing}")
            if extra:
                issues.append(f"commands unexpected rails: {extra}")

        extra_md_or_json = []
        for item in commands_dir.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix.lower() not in {".md", ".json"}:
                continue
            rel = item.relative_to(commands_dir).as_posix()
            if rel in EXPECTED_RAILS:
                continue
            extra_md_or_json.append(rel)
        if extra_md_or_json:
            issues.append("commands contains unexpected md/json: " + ", ".join(sorted(extra_md_or_json)))

    local_entries = _list_top_level(local_root)
    expected = set(EXPECTED_LOCAL_TOP_LEVEL)
    missing_local = sorted(expected - local_entries)
    extra_local = sorted(local_entries - expected)
    if missing_local:
        issues.append(f"local root missing required entries: {missing_local}")
    if extra_local:
        issues.append(f"local root has unexpected entries: {extra_local}")

    if (local_root / "governance").exists():
        issues.append("local root must not contain governance/")

    return issues


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    with tempfile.TemporaryDirectory(prefix="install-layout-gate-") as tmp:
        tmp_root = Path(tmp)
        config_root = tmp_root / "config"
        local_root = tmp_root / "local"
        config_root.mkdir(parents=True, exist_ok=True)
        local_root.mkdir(parents=True, exist_ok=True)
        _run_install(repo_root, args.python, config_root, local_root)
        issues = verify_install_layout(config_root, local_root)

        uninstall_cmd = [
            args.python,
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

        if issues:
            print("❌ Install layout gate failed")
            for issue in issues:
                print(f" - {issue}")
            return 1

    print("✅ Install layout gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
