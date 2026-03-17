from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def get_docs_path() -> Path:
    """
    Get the docs path supporting dual-read during migration.
    
    Prefers new structure (governance_content/docs/) over legacy (docs/).
    """
    new_docs = REPO_ROOT / "governance_content" / "docs"
    if new_docs.exists():
        return new_docs
    return REPO_ROOT / "docs"


def get_profiles_path() -> Path:
    """Get the profiles path supporting dual-read during migration."""
    new_profiles = REPO_ROOT / "governance_content" / "profiles"
    if new_profiles.exists():
        return new_profiles
    return REPO_ROOT / "profiles"


def get_profile_addons_path() -> Path:
    """Get the profile addons path supporting dual-read during migration."""
    return get_profiles_path() / "addons"


def get_profile_file(name: str) -> Path:
    """Get a specific profile file by name."""
    return get_profiles_path() / name


def get_templates_path() -> Path:
    """Get the templates path supporting dual-read during migration."""
    new_templates = REPO_ROOT / "governance_content" / "templates"
    if new_templates.exists():
        return new_templates
    return REPO_ROOT / "templates"


def get_rulesets_path() -> Path:
    """Get the rulesets path supporting dual-read during migration."""
    new_rulesets = REPO_ROOT / "governance_spec" / "rulesets"
    if new_rulesets.exists():
        return new_rulesets
    return REPO_ROOT / "rulesets"


def get_ruleset_core_path() -> Path:
    """Get the rulesets/core path supporting dual-read during migration."""
    return get_rulesets_path() / "core"


def get_ruleset_profiles_path() -> Path:
    """Get the rulesets/profiles path supporting dual-read during migration."""
    return get_rulesets_path() / "profiles"


def get_ruleset_file(relative_path: str) -> Path:
    """Get a specific ruleset file by relative path."""
    return get_rulesets_path() / relative_path


def run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        env=e,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_install(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    # Check if --source-dir is provided in args
    source_dir = None
    for i, arg in enumerate(args):
        if arg == "--source-dir" and i + 1 < len(args):
            source_dir = Path(args[i + 1])
            break
    
    # If no explicit --source-dir provided, default to repository root
    if source_dir is None:
        source_dir = REPO_ROOT
    # Always use the current interpreter (matrix python-version).
    # If the source_dir does not contain an install.py (some tests set up synthetic
    # governance sources), fall back to the repository's install.py to execute.
    script = source_dir / "install.py"
    if not script.exists():
        script = REPO_ROOT / "install.py"
    return run([sys.executable, "-X", "utf8", str(script), *args], env=env, cwd=source_dir)


def run_build(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return run([sys.executable, "scripts/build.py", *args], env=env)


def run_customer_bundle_build(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return run([sys.executable, "scripts/build_customer_install_bundle.py", *args], env=env)


def git_ls_files(*patterns: str) -> list[str]:
    cmd = ["git", "ls-files"]
    if patterns:
        cmd += list(patterns)
    r = run(cmd)
    if r.returncode == 0:
        return [l for l in r.stdout.splitlines() if l.strip()]

    files: set[str] = set()
    search_patterns = patterns or ("**/*",)
    for pattern in search_patterns:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file():
                files.add(path.relative_to(REPO_ROOT).as_posix())
    return sorted(files)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_governance_paths(config_root: Path, *, workspaces_home: Path | None = None) -> Path:
    """Create minimal installer-owned governance.paths.json for tests."""

    root = Path(os.path.normpath(os.path.abspath(config_root)))
    commands = root / "commands"
    governance = commands / "governance"
    workspaces = (Path(os.path.normpath(os.path.abspath(workspaces_home))) if workspaces_home is not None else (root / "workspaces"))
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(root),
            "commandsHome": str(commands),
            "profilesHome": str(root / "profiles"),
            "governanceHome": str(governance),
            "workspacesHome": str(workspaces),
            "globalErrorLogsHome": str(commands / "logs"),
            "workspaceErrorLogsHomeTemplate": str(workspaces / "<repo_fingerprint>" / "logs"),
            "pythonCommand": "py -3" if os.name == "nt" else "python3",
        },
    }
    commands.mkdir(parents=True, exist_ok=True)
    target = commands / "governance.paths.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return target


def sha256_file(p: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_flag_supported(flag: str) -> bool:
    r = run_install(["--help"])
    return flag in (r.stdout or "")
