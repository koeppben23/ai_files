from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def get_docs_path() -> Path:
    """
    Get the SSOT docs path.
    """
    return REPO_ROOT / "governance_content" / "docs"


def get_profiles_path() -> Path:
    """Get the SSOT profiles path."""
    return REPO_ROOT / "governance_content" / "profiles"


def get_profile_addons_path() -> Path:
    """Get the SSOT profile addons path."""
    return REPO_ROOT / "governance_content" / "profiles" / "addons"


def get_profile_file(name: str) -> Path:
    """Get a specific profile file by name."""
    return REPO_ROOT / "governance_content" / "profiles" / name


def get_templates_path() -> Path:
    """Get the SSOT templates path."""
    return REPO_ROOT / "governance_content" / "templates"


def get_rulesets_path() -> Path:
    """Get the SSOT rulesets path."""
    return REPO_ROOT / "governance_spec" / "rulesets"


def get_ruleset_core_path() -> Path:
    """Get the SSOT rulesets/core path."""
    return REPO_ROOT / "governance_spec" / "rulesets" / "core"


def get_ruleset_profiles_path() -> Path:
    """Get the SSOT rulesets/profiles path."""
    return REPO_ROOT / "governance_spec" / "rulesets" / "profiles"


def get_ruleset_file(relative_path: str) -> Path:
    """Get a specific ruleset file by relative path."""
    return REPO_ROOT / "governance_spec" / "rulesets" / relative_path


def get_master_path() -> Path:
    """Get master.md path (SSOT only)."""
    return REPO_ROOT / "governance_content" / "reference" / "master.md"


def get_rules_path() -> Path:
    """Get rules.md path (SSOT only)."""
    return REPO_ROOT / "governance_content" / "reference" / "rules.md"


def get_phase_api_path() -> Path:
    """Get phase_api.yaml path (SSOT only)."""
    return REPO_ROOT / "governance_spec" / "phase_api.yaml"


def get_review_path() -> Path:
    """Get review.md path (SSOT only)."""
    return REPO_ROOT / "governance_content" / "docs" / "review.md"


def _remap_legacy_relative_path(rel: str) -> str:
    """Map legacy repo-relative paths to new structure."""
    if rel == "master.md":
        return "governance_content/reference/master.md"
    if rel == "rules.md":
        return "governance_content/reference/rules.md"
    if rel == "phase_api.yaml":
        return "governance_spec/phase_api.yaml"
    if rel.startswith("docs/"):
        return "governance_content/" + rel
    if rel.startswith("profiles/"):
        return "governance_content/" + rel
    if rel.startswith("templates/"):
        return "governance_content/" + rel
    if rel.startswith("rulesets/"):
        return "governance_spec/" + rel
    return rel


def run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        env=e,
        text=True,
        encoding="utf-8",
        errors="replace",
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
    effective_env = dict(env or {})
    if "OPENCODE_LOCAL_ROOT" not in effective_env:
        config_root_arg = None
        for i, arg in enumerate(args):
            if arg == "--config-root" and i + 1 < len(args):
                config_root_arg = Path(args[i + 1]).resolve()
                break
        if config_root_arg is not None:
            effective_env["OPENCODE_LOCAL_ROOT"] = str(config_root_arg.parent / f"{config_root_arg.name}-local")
    return run([sys.executable, "-X", "utf8", str(script), *args], env=effective_env, cwd=source_dir)


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
        tracked_files: list[str] = [str(l) for l in r.stdout.splitlines() if str(l).strip()]
        if tracked_files:
            return tracked_files

    # If legacy pattern yields no results, try new-structure mapped patterns.
    remapped_patterns = tuple(_remap_legacy_relative_path(p) for p in patterns)
    if remapped_patterns != patterns:
        cmd = ["git", "ls-files", *remapped_patterns]
        r = run(cmd)
        if r.returncode == 0:
            tracked_files: list[str] = [str(l) for l in r.stdout.splitlines() if str(l).strip()]
            if tracked_files:
                return tracked_files

    files: set[str] = set()
    search_patterns = patterns or ("**/*",)
    for pattern in search_patterns:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file():
                files.add(path.relative_to(REPO_ROOT).as_posix())
    return sorted(files)


def read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")

    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except Exception:
        rel = ""

    if rel:
        mapped = REPO_ROOT / _remap_legacy_relative_path(rel)
        if mapped.exists():
            return mapped.read_text(encoding="utf-8")

    return path.read_text(encoding="utf-8")


def write_governance_paths(
    config_root: Path,
    *,
    local_root: Path | None = None,
    workspaces_home: Path | None = None,
) -> Path:
    """Create minimal installer-owned governance.paths.json for tests."""

    root = Path(os.path.normpath(os.path.abspath(config_root)))
    commands = root / "commands"
    local = (Path(os.path.normpath(os.path.abspath(local_root))) if local_root is not None else (root.parent / f"{root.name}-local"))
    governance = local / "governance"
    workspaces = (Path(os.path.normpath(os.path.abspath(workspaces_home))) if workspaces_home is not None else (root / "workspaces"))
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(root),
            "localRoot": str(local),
            "commandsHome": str(commands),
            "profilesHome": str(local / "governance_content" / "profiles"),
            "governanceHome": str(governance),
            "runtimeHome": str(local / "governance_runtime"),
            "contentHome": str(local / "governance_content"),
            "specHome": str(local / "governance_spec"),
            "workspacesHome": str(workspaces),
            "globalErrorLogsHome": str(workspaces / "_global" / "logs"),
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
