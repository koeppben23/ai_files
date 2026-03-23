#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKIP_COPY_DIRS = {".git", ".venv", "venv", "dist", "build", "__pycache__", ".pytest_cache", "node_modules"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete governance/ and run smoke gates")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    return parser.parse_args(argv)


def _copy_repo(src: Path, dst: Path) -> None:
    def _ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in SKIP_COPY_DIRS}

    shutil.copytree(src, dst, ignore=_ignore)


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    return result.returncode, result.stdout, result.stderr


def _ensure_spec_authority(config_root: Path, local_root: Path, repo_root: Path) -> str | None:
    config_root = config_root.resolve()
    local_root = local_root.resolve()
    binding = config_root / "governance.paths.json"

    payload: dict[str, object]
    paths: dict[str, object]
    if binding.exists():
        payload = json.loads(binding.read_text(encoding="utf-8"))
        raw_paths = payload.get("paths", payload)
        paths = dict(raw_paths) if isinstance(raw_paths, dict) else {}
    else:
        payload = {"schema": "opencode-governance.paths.v1", "paths": {}}
        paths = {}

    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    spec_home = local_root / "governance_spec"

    runtime_home = local_root / "governance_runtime"
    governance_home = local_root / "governance"
    content_home = local_root / "governance_content"
    profiles_home = content_home / "profiles"

    paths.update(
        {
            "configRoot": str(config_root),
            "localRoot": str(local_root),
            "commandsHome": str(commands_home),
            "runtimeHome": str(runtime_home),
            "governanceHome": str(governance_home),
            "contentHome": str(content_home),
            "workspacesHome": str(workspaces_home),
            "specHome": str(spec_home),
            "profilesHome": str(profiles_home),
            "pythonCommand": str(paths.get("pythonCommand") or sys.executable),
        }
    )
    payload["paths"] = paths
    binding.parent.mkdir(parents=True, exist_ok=True)
    binding.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    for path in (commands_home, workspaces_home, runtime_home, governance_home, content_home, spec_home, profiles_home):
        path.mkdir(parents=True, exist_ok=True)
    phase_api = spec_home / "phase_api.yaml"
    src = repo_root / "governance_spec" / "phase_api.yaml"
    if src.exists():
        phase_api.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return None


def run_delete_barrier(repo_root: Path, python_cmd: str) -> list[str]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="delete-barrier-") as tmp:
        tmp_root = Path(tmp)
        cloned = tmp_root / "repo"
        config_root = tmp_root / "cfg"
        local_root = tmp_root / "local"
        _copy_repo(repo_root, cloned)

        git_dir = cloned / ".git"
        if not git_dir.exists():
            init = subprocess.run(["git", "init", "-q"], cwd=str(cloned), text=True, capture_output=True)
            if init.returncode != 0:
                git_dir.mkdir(parents=True, exist_ok=True)

        legacy_dir = cloned / "governance"
        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)

        commands = [
            ([python_cmd, "-X", "utf8", "-c", "import governance_runtime.entrypoints.bootstrap_executor"], "import-smoke"),
            ([python_cmd, "-X", "utf8", "scripts/build.py"], "build-smoke"),
            (
                [
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
                ],
                "install-smoke",
            ),
            (
                [
                    python_cmd,
                    "-X",
                    "utf8",
                    "cli/bootstrap.py",
                    "init",
                    "--profile",
                    "solo",
                    "--repo-root",
                    str(cloned),
                    "--config-root",
                    str(config_root),
                ],
                "bootstrap-smoke",
            ),
            (
                [
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
                ],
                "uninstall-smoke",
            ),
        ]

        for cmd, label in commands:
            code, out, err = _run(cmd, cwd=cloned)
            if code != 0:
                issues.append(
                    f"{label} failed (code={code})\ncmd={' '.join(cmd)}\nstdout:\n{out}\nstderr:\n{err}"
                )
                break
            if label == "install-smoke":
                authority_issue = _ensure_spec_authority(config_root, local_root, cloned)
                if authority_issue is not None:
                    issues.append(f"authority setup failed: {authority_issue}")
                    break
    return issues


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    issues = run_delete_barrier(repo_root, args.python)
    if issues:
        print("❌ Delete barrier failed")
        for issue in issues:
            print(f" - {issue}")
        return 1
    print("✅ Delete barrier passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
