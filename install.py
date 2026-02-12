#!/usr/bin/env python3
"""
LLM Governance System - Installer
Installs governance system files to OpenCode config directory.

Features:
- Windows primary target: %USERPROFILE%/.config/opencode (fallback: %APPDATA%/opencode)
- dry-run support
- backup-on-overwrite (timestamped) with --no-backup to disable
- uninstall (manifest-based; deletes only what was installed)
- manifest tracking (INSTALL_MANIFEST.json)

NOTE:
- This installer does NOT generate opencode.json (to avoid schema validation errors).
- Instead it generates an installer-owned sidecar: commands/governance.paths.json for /start.
- Installer diagnostics use `ERR-*` reason keys as installer-internal keys; they are not canonical
  governance `reason_code` values (`BLOCKED-*|WARN-*|NOT_VERIFIED-*`).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
DIAGNOSTICS_SOURCE_DIR = SCRIPT_DIR / "diagnostics"


def _load_error_logger() -> Callable[..., object]:
    helper = DIAGNOSTICS_SOURCE_DIR / "error_logs.py"
    if not helper.exists():
        return lambda **kwargs: {"status": "log-disabled"}

    try:
        spec = importlib.util.spec_from_file_location("opencode_error_logs", helper)
        if spec is None or spec.loader is None:
            return lambda **kwargs: {"status": "log-disabled"}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "safe_log_error", None)
        return fn if callable(fn) else (lambda **kwargs: {"status": "log-disabled"})
    except Exception:
        return lambda **kwargs: {"status": "log-disabled"}


safe_log_error = _load_error_logger()

VERSION = "1.1.0-RC.2"
# Files copied into <config_root>/commands
# Strategy: copy (almost) all repo-root governance artifacts that are relevant at runtime.
# - Include: *.md, *.json, LICENSE (if present)
# - Exclude: installer scripts themselves
EXCLUDE_ROOT_FILES = {
    "install.py",
    "install.corrected.py",
    "install.updated.py",
    # Dev tooling (must not be installed into commands/)
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    ".commitlintrc",
    ".commitlintrc.js",
    ".commitlintrc.cjs",
}

# Profiles copied into <config_root>/commands/profiles/**
PROFILES_DIR_NAME = "profiles"

# Customer helper scripts copied into <config_root>/commands/scripts/**
SCRIPTS_DIR_NAME = "scripts"

# Workflow templates copied into <config_root>/commands/templates/**
TEMPLATES_DIR_NAME = "templates"
TEMPLATE_CATALOG_REL = Path("templates/github-actions/template_catalog.json")
TEMPLATE_CATALOG_SCHEMA = "governance.workflow-template-catalog.v1"

# Customer script catalog controlling which scripts are shipped for customers
CUSTOMER_SCRIPT_CATALOG_REL = Path("diagnostics/CUSTOMER_SCRIPT_CATALOG.json")
CUSTOMER_SCRIPT_CATALOG_SCHEMA = "governance.customer-script-catalog.v1"

# Diagnostics copied into <config_root>/commands/diagnostics/** (includes audit tooling + schemas)
DIAGNOSTICS_DIR_NAME = "diagnostics"

# Governance runtime package copied into <config_root>/commands/governance/**
GOVERNANCE_RUNTIME_DIR_NAME = "governance"

FORBIDDEN_METADATA_SEGMENTS = {"__MACOSX"}
FORBIDDEN_METADATA_FILENAMES = {".DS_Store", "Icon\r"}

MANIFEST_NAME = "INSTALL_MANIFEST.json"
MANIFEST_SCHEMA = "1.0"

# Governance paths bootstrap (used by /start)
GOVERNANCE_PATHS_NAME = "governance.paths.json"
GOVERNANCE_PATHS_SCHEMA = "opencode-governance.paths.v1"

# Runtime error logs (written by diagnostics helpers; outside repository)
ERROR_LOGS_DIR_NAME = "logs"

# Core governance files (static allowlist for conservative uninstall fallback)
CORE_COMMAND_FILES = {
    "master.md",
    "rules.md",
    "start.md",
    "continue.md",
    "resume.md",
    "resume_prompt.md",
    "QUALITY_INDEX.md",
    "CONFLICT_RESOLUTION.md",
    "SCOPE-AND-CONTEXT.md",
    "SESSION_STATE_SCHEMA.md",
    "ADR.md",
    "TICKET_RECORD_TEMPLATE.md",
    "README.md",
    "README-RULES.md",
    "README-OPENCODE.md",
    "README-CHAT.md",
    "CHANGELOG.md",
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "LICENCE",
    "LICENCE.md",
    "LICENCE.txt",
}

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now_ts() -> str:
    # ISO-ish, filesystem friendly
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def json_bytes(doc: dict) -> bytes:
    # Canonical bytes for both predicted (dry-run) and live write.
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def is_interactive() -> bool:
    # conservative: require both stdin and stdout to be TTY
    return sys.stdin.isatty() and sys.stdout.isatty()

def get_config_root() -> Path:
    """
    Determine OpenCode config root based on OS.

    Per requirement:
    - Windows primary: %USERPROFILE%/.config/opencode
      fallback: %APPDATA%/opencode
    - macOS/Linux: $XDG_CONFIG_HOME/opencode or ~/.config/opencode
    """
    system = platform.system()

    if system == "Windows":
        userprofile = os.getenv("USERPROFILE")
        if userprofile:
            return Path(userprofile) / ".config" / "opencode"
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "opencode"
        raise RuntimeError("Windows: USERPROFILE/APPDATA not set; cannot resolve config root.")

    # macOS / Linux / others POSIX-like
    xdg_config = os.getenv("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "opencode"
    return Path.home() / ".config" / "opencode"


def ensure_dirs(config_root: Path, dry_run: bool) -> None:
    dirs = [
        config_root,
        config_root / "commands",
        config_root / "commands" / "scripts",
        config_root / "commands" / "templates",
        config_root / "commands" / "templates" / "github-actions",
        config_root / "commands" / "profiles",
        config_root / "commands" / "profiles" / "addons",
        config_root / "workspaces",
    ]
    for d in dirs:
        if dry_run:
            print(f"  [DRY-RUN] mkdir -p {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ {d}")


def read_governance_version_from_master(master_md: Path) -> str | None:
    """
    Read the governance version from master.md.

    The installer requires a governance version (fail-closed). If no version is found,
    the install step aborts to prevent unversioned deployments.

    Supported conventions (must appear near the top of the file, within first ~40 lines):
      - Markdown header:   # Governance-Version: 1.0.0-RC.1
      - Markdown header:   # Version: 1.0.0-RC.1              (fallback)
      - Frontmatter key:   governanceVersion: 1.0.0
      - Frontmatter key:   governance_version: 1.0.0

    Returns:
      The raw version string (e.g. "1.0.0") or None if not found/parsable.
    """
    if not master_md.exists():
        return None
        
    # Keep permissive parsing, but require a reasonable "semver-ish" token.
    semverish = re.compile(r"\b\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\b")
        
    try:
        with master_md.open("r", encoding="utf-8") as f:
            for _ in range(40):
                line = f.readline()
                if not line:
                    break
                    
                # Frontmatter variants
                m = re.search(
                    r"^\s*(governanceVersion|governance_version|governance-version)\s*:\s*(.+?)\s*$",
                    line,
                    flags=re.IGNORECASE,
                )
                if m:
                    mm = semverish.search(m.group(2))
                    return mm.group(0) if mm else m.group(2).strip()    
                    
                if "Governance-Version:" in line:
                    val = line.split("Governance-Version:", 1)[1].strip()
                    mm = semverish.search(val)
                    return mm.group(0) if mm else val
                if line.lstrip().startswith("#") and "Version:" in line:
                    val = line.split("Version:", 1)[1].strip()
                    mm = semverish.search(val)
                    return mm.group(0) if mm else val
    except Exception:
        return None
    return None


@dataclass(frozen=True)
class InstallPlan:
    source_dir: Path
    config_root: Path
    commands_dir: Path
    profiles_dst_dir: Path
    manifest_path: Path
    governance_paths_path: Path
    skip_paths_file: bool
    deterministic_paths_file: bool


def build_plan(source_dir: Path, config_root: Path, *, skip_paths_file: bool, deterministic_paths_file: bool) -> InstallPlan:
    commands_dir = config_root / "commands"
    profiles_dst_dir = commands_dir / "profiles"
    manifest_path = commands_dir / MANIFEST_NAME
    governance_paths_path = commands_dir / GOVERNANCE_PATHS_NAME
    return InstallPlan(
        source_dir=source_dir,
        config_root=config_root,
        commands_dir=commands_dir,
        profiles_dst_dir=profiles_dst_dir,
        manifest_path=manifest_path,
        governance_paths_path=governance_paths_path,
        skip_paths_file=skip_paths_file,
        deterministic_paths_file=deterministic_paths_file,
    )


def required_source_files(source_dir: Path) -> list[str]:
    # critical minimal set
    return ["master.md", "rules.md", "start.md"]


def precheck_source(source_dir: Path) -> tuple[bool, list[str], list[str]]:
    missing = []
    for name in required_source_files(source_dir):
        if not (source_dir / name).exists():
            missing.append(name)
    unsafe_symlinks = collect_unsafe_source_symlinks(source_dir)
    return (len(missing) == 0 and len(unsafe_symlinks) == 0, missing, unsafe_symlinks)


def collect_unsafe_source_symlinks(source_dir: Path) -> list[str]:
    """
    Fail-closed source traversal guard:
    installer-managed payload MUST NOT be sourced from symlinks/reparse points.
    """
    unsafe: set[str] = set()

    for p in source_dir.iterdir():
        if p.is_symlink():
            unsafe.add(p.name)

    profiles_src_dir = source_dir / PROFILES_DIR_NAME
    if profiles_src_dir.exists():
        for p in profiles_src_dir.rglob("*"):
            if p.is_symlink():
                unsafe.add(str(p.relative_to(source_dir)).replace("\\", "/"))

    diag_dir = source_dir / DIAGNOSTICS_DIR_NAME
    if diag_dir.exists():
        for p in diag_dir.rglob("*"):
            if p.is_symlink():
                unsafe.add(str(p.relative_to(source_dir)).replace("\\", "/"))

    runtime_dir = source_dir / GOVERNANCE_RUNTIME_DIR_NAME
    if runtime_dir.exists():
        for p in runtime_dir.rglob("*"):
            if p.is_symlink():
                unsafe.add(str(p.relative_to(source_dir)).replace("\\", "/"))

    scripts_dir = source_dir / SCRIPTS_DIR_NAME
    if scripts_dir.exists():
        for p in scripts_dir.rglob("*"):
            if p.is_symlink():
                unsafe.add(str(p.relative_to(source_dir)).replace("\\", "/"))

    templates_dir = source_dir / TEMPLATES_DIR_NAME
    if templates_dir.exists():
        for p in templates_dir.rglob("*"):
            if p.is_symlink():
                unsafe.add(str(p.relative_to(source_dir)).replace("\\", "/"))

    return sorted(unsafe)


def _is_forbidden_metadata_path(path: Path, source_root: Path) -> bool:
    """Return True when path is a filesystem metadata artifact."""

    rel = path.relative_to(source_root)
    if any(segment in FORBIDDEN_METADATA_SEGMENTS for segment in rel.parts):
        return True
    name = path.name
    if name in FORBIDDEN_METADATA_FILENAMES:
        return True
    if name.startswith("._"):
        return True
    return False

def collect_command_root_files(source_dir: Path) -> list[Path]:
    """
    Collect root-level governance files to copy into <config_root>/commands/.
    Includes:
      - *.md
      - *.json
      - LICENSE (if present)
    Excludes:
      - installer scripts (EXCLUDE_ROOT_FILES)
      - (no opencode.json template handling; we never generate opencode.json)
    """
    files: list[Path] = []
    for p in source_dir.iterdir():
        if not p.is_file():
            continue

        name = p.name
        if name in EXCLUDE_ROOT_FILES:
            continue
        if _is_forbidden_metadata_path(p, source_dir):
            continue

        if name.lower().startswith("license"):
            files.append(p)
            continue

        if p.suffix.lower() in (".md", ".json"):
            files.append(p)

    return sorted(files)

def collect_diagnostics_files(source_dir: Path) -> list[Path]:
    """
    Collect diagnostics files to copy into <config_root>/commands/diagnostics/**.
    Includes everything under ./diagnostics (schemas, audit docs, etc.).
    """
    diag_dir = source_dir / DIAGNOSTICS_DIR_NAME
    if not diag_dir.exists() or not diag_dir.is_dir():
        return []
    return sorted(
        [
            p
            for p in diag_dir.rglob("*")
            if p.is_file() and not p.is_symlink() and not _is_forbidden_metadata_path(p, source_dir)
        ]
    )


def collect_governance_runtime_files(source_dir: Path) -> list[Path]:
    """Collect governance runtime files for packaged state-machine execution."""

    runtime_dir = source_dir / GOVERNANCE_RUNTIME_DIR_NAME
    if not runtime_dir.exists() or not runtime_dir.is_dir():
        return []
    return sorted(
        [
            p
            for p in runtime_dir.rglob("*")
            if p.is_file() and not p.is_symlink() and not _is_forbidden_metadata_path(p, source_dir)
        ]
    )


def collect_customer_script_files(source_dir: Path, *, strict: bool) -> list[Path]:
    """Collect customer-relevant scripts listed in diagnostics/CUSTOMER_SCRIPT_CATALOG.json."""

    catalog_path = source_dir / CUSTOMER_SCRIPT_CATALOG_REL
    payload = _load_json(catalog_path)
    if payload is None:
        if strict:
            raise RuntimeError(f"Missing or invalid customer script catalog: {CUSTOMER_SCRIPT_CATALOG_REL}")
        return []

    if payload.get("schema") != CUSTOMER_SCRIPT_CATALOG_SCHEMA:
        if strict:
            raise RuntimeError(
                f"Customer script catalog schema mismatch in {CUSTOMER_SCRIPT_CATALOG_REL}: "
                f"expected {CUSTOMER_SCRIPT_CATALOG_SCHEMA}"
            )
        return []

    raw = payload.get("scripts")
    if not isinstance(raw, list):
        if strict:
            raise RuntimeError(f"{CUSTOMER_SCRIPT_CATALOG_REL}: scripts must be an array")
        return []

    selected: list[Path] = []
    for idx, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            if strict:
                raise RuntimeError(f"{CUSTOMER_SCRIPT_CATALOG_REL}: scripts[{idx}] must be an object")
            continue

        if not bool(entry.get("ship_in_release")):
            continue

        rel_raw = entry.get("path")
        if not isinstance(rel_raw, str) or not rel_raw.strip():
            if strict:
                raise RuntimeError(f"{CUSTOMER_SCRIPT_CATALOG_REL}: scripts[{idx}] missing path")
            continue

        rel = rel_raw.replace("\\", "/")
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts or not rel.startswith("scripts/") or rel_path.suffix != ".py":
            if strict:
                raise RuntimeError(
                    f"{CUSTOMER_SCRIPT_CATALOG_REL}: scripts[{idx}].path must be scripts/*.py without traversal"
                )
            continue

        src = source_dir / rel_path
        if not src.exists() or not src.is_file() or src.is_symlink() or _is_forbidden_metadata_path(src, source_dir):
            if strict:
                raise RuntimeError(f"catalog references missing or invalid shipped script: {rel}")
            continue
        selected.append(src)

    if strict and not selected:
        raise RuntimeError("Customer script catalog has no ship_in_release=true script entries")
    return sorted(selected)


def collect_workflow_template_files(source_dir: Path, *, strict: bool) -> list[Path]:
    """Collect workflow template files declared in templates/github-actions/template_catalog.json."""

    catalog_path = source_dir / TEMPLATE_CATALOG_REL
    payload = _load_json(catalog_path)
    if payload is None:
        if strict:
            raise RuntimeError(f"Missing or invalid workflow template catalog: {TEMPLATE_CATALOG_REL}")
        return []

    if payload.get("schema") != TEMPLATE_CATALOG_SCHEMA:
        if strict:
            raise RuntimeError(
                f"Workflow template catalog schema mismatch in {TEMPLATE_CATALOG_REL}: expected {TEMPLATE_CATALOG_SCHEMA}"
            )
        return []

    raw = payload.get("templates")
    if not isinstance(raw, list):
        if strict:
            raise RuntimeError(f"{TEMPLATE_CATALOG_REL}: templates must be an array")
        return []

    selected: list[Path] = [catalog_path]
    for idx, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            if strict:
                raise RuntimeError(f"{TEMPLATE_CATALOG_REL}: templates[{idx}] must be an object")
            continue
        rel_raw = entry.get("file")
        if not isinstance(rel_raw, str) or not rel_raw.strip():
            if strict:
                raise RuntimeError(f"{TEMPLATE_CATALOG_REL}: templates[{idx}] missing file")
            continue

        rel = rel_raw.replace("\\", "/")
        rel_path = Path(rel)
        if (
            rel_path.is_absolute()
            or ".." in rel_path.parts
            or not rel.startswith("templates/github-actions/")
            or rel_path.suffix != ".yml"
        ):
            if strict:
                raise RuntimeError(
                    f"{TEMPLATE_CATALOG_REL}: templates[{idx}].file must be templates/github-actions/*.yml"
                )
            continue

        src = source_dir / rel_path
        if not src.exists() or not src.is_file() or src.is_symlink() or _is_forbidden_metadata_path(src, source_dir):
            if strict:
                raise RuntimeError(f"template catalog references missing or invalid template file: {rel}")
            continue
        selected.append(src)

    # Deduplicate while preserving deterministic order.
    unique = sorted(dict.fromkeys(selected), key=lambda p: str(p.relative_to(source_dir)).replace("\\", "/"))
    if strict and len(unique) <= 1:
        raise RuntimeError("workflow template catalog has no listed template files")
    return unique


def build_governance_paths_payload(config_root: Path, *, deterministic: bool) -> dict:
    """
    Create a small, installer-owned JSON document that records the canonical absolute paths
    derived from config_root. This is *not* an OpenCode config file and is therefore not
    validated against the OpenCode config schema.

    /start loads this file via shell output injection to avoid interactive path binding.
    """
    def norm(p: Path) -> str:
        return str(p)

    commands_home = config_root / "commands"
    profiles_home = commands_home / "profiles"
    diagnostics_home = commands_home / "diagnostics"
    workspaces_home = config_root / "workspaces"
    global_error_logs_home = config_root / ERROR_LOGS_DIR_NAME

    doc = {
        "schema": GOVERNANCE_PATHS_SCHEMA,
        "paths": {
            "configRoot": norm(config_root),
            "commandsHome": norm(commands_home),
            "profilesHome": norm(profiles_home),
            "diagnosticsHome": norm(diagnostics_home),
            "workspacesHome": norm(workspaces_home),
            "globalErrorLogsHome": norm(global_error_logs_home),
            "workspaceErrorLogsHomeTemplate": norm(workspaces_home / "<repo_fingerprint>" / "logs"),
        },
    }
    if not deterministic:
        doc["generatedAt"] = datetime.now().isoformat(timespec="seconds")
    return doc


def install_governance_paths_file(
    plan: InstallPlan,
    dry_run: bool,
    force: bool,
    backup_enabled: bool,
    backup_root: Path,
) -> dict:
    """
    Create/update <config_root>/commands/governance.paths.json.

    Semantics:
    - create if missing
    - overwrite only when --force
    - backup on overwrite when enabled
    - recorded in the manifest (installer-owned)
    """
    dst = plan.governance_paths_path
    dst_exists = dst.exists()

    desired_doc = build_governance_paths_payload(plan.config_root, deterministic=plan.deterministic_paths_file)

    if dst_exists and not force:
        existing = _load_json(dst)
        if existing and existing.get("schema") == GOVERNANCE_PATHS_SCHEMA and isinstance(existing.get("paths"), dict):
            existing_paths = existing["paths"]
            assert isinstance(existing_paths, dict)

            missing_keys: list[str] = []
            for k, v in desired_doc["paths"].items():
                if k not in existing_paths:
                    existing_paths[k] = v
                    missing_keys.append(k)

            if missing_keys:
                backup_path = None
                if backup_enabled:
                    backup_path = str(backup_file(dst, backup_root, dry_run))

                if dry_run:
                    print(f"  [DRY-RUN] patch {dst} (missing governance path keys: {missing_keys})")
                    return {
                        "status": "planned-patch",
                        "src": "generated",
                        "dst": str(dst),
                        "backup": backup_path,
                        "sha256": hashlib.sha256(json_bytes(existing)).hexdigest(),
                        "note": f"patched missing keys: {','.join(missing_keys)}",
                    }

                dst.write_bytes(json_bytes(existing))
                return {
                    "status": "patched",
                    "src": "generated",
                    "dst": str(dst),
                    "backup": backup_path,
                    "sha256": sha256_file(dst),
                    "note": f"patched missing keys: {','.join(missing_keys)}",
                }

        return {"status": "skipped-exists", "src": "generated", "dst": str(dst)}

    backup_path = None
    if dst_exists and backup_enabled:
        backup_path = str(backup_file(dst, backup_root, dry_run))

    sha_pred = hashlib.sha256(json_bytes(desired_doc)).hexdigest()

    if dry_run:
        print(f"  [DRY-RUN] write {dst} (governance paths)")
        return {
            "status": "planned-copy",
            "src": "generated",
            "dst": str(dst),
            "backup": backup_path,
            "sha256": sha_pred,
            "note": "governance paths bootstrap",
        }

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(json_bytes(desired_doc))
    return {
        "status": "copied",
        "src": "generated",
        "dst": str(dst),
        "backup": backup_path,
        "sha256": sha256_file(dst),
        "note": "governance paths bootstrap",
    }


def backup_file(dst: Path, backup_root: Path, dry_run: bool) -> Path:
    rel = confirm_relative(dst)
    backup_path = backup_root / rel
    if dry_run:
        print(f"  [DRY-RUN] backup {dst} -> {backup_path}")
        return backup_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dst, backup_path)
    return backup_path


def confirm_relative(path: Path) -> Path:
    """
    Create a relative-ish path fragment for backups by stripping drive/root.
    """
    p = path
    parts = list(p.parts)
    # On Windows, first part can be drive like 'C:\\'
    # We'll drop anchor parts and keep a safe relative representation.
    if p.is_absolute():
        # Drop root/drive and keep tail
        tail = parts[1:] if len(parts) > 1 else parts
        return Path(*tail)
    return Path(*parts)


def copy_with_optional_backup(
    src: Path,
    dst: Path,
    backup_enabled: bool,
    backup_root: Path,
    dry_run: bool,
    overwrite: bool,
) -> dict:
    """
    Returns a manifest entry dict for this file if copied, else None-ish.
    """
    if not src.exists():
        return {"status": "missing-source", "src": str(src), "dst": str(dst)}

    dst_exists = dst.exists()
    if dst_exists and not overwrite:
        return {"status": "skipped-exists", "src": str(src), "dst": str(dst)}

    # backup if overwriting
    backup_path = None
    if dst_exists and overwrite and backup_enabled:
        backup_path = str(backup_file(dst, backup_root, dry_run))

    if dry_run:
        op = "cp" if not dst_exists else "cp --overwrite"
        print(f"  [DRY-RUN] {op} {src} -> {dst}")
        dst_hash = sha256_file(src)  # predicted installed content hash
        return {
            "status": "planned-copy",
            "src": str(src),
            "dst": str(dst),
            "backup": backup_path,
            "sha256": dst_hash,
        }

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {
        "status": "copied",
        "src": str(src),
        "dst": str(dst),
        "backup": backup_path,
        "sha256": sha256_file(dst),
    }


def collect_profile_files(source_dir: Path) -> list[Path]:
    profiles_src_dir = source_dir / PROFILES_DIR_NAME
    if not profiles_src_dir.exists():
        return []
    return sorted(
        [
            p
            for p in profiles_src_dir.rglob("*.md")
            if p.is_file() and not p.is_symlink() and not _is_forbidden_metadata_path(p, source_dir)
        ]
    )


def collect_profile_addon_manifests(source_dir: Path) -> list[Path]:
    profiles_src_dir = source_dir / PROFILES_DIR_NAME
    if not profiles_src_dir.exists():
        return []
    return sorted(
        [
            p
            for p in profiles_src_dir.rglob("*.addon.yml")
            if p.is_file() and not p.is_symlink() and not _is_forbidden_metadata_path(p, source_dir)
        ]
    )


def write_manifest(manifest_path: Path, manifest: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY-RUN] write manifest -> {manifest_path}")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_manifest(manifest_path: Path) -> dict | None:
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def install(plan: InstallPlan, dry_run: bool, force: bool, backup_enabled: bool) -> int:
    ok, missing, unsafe_symlinks = precheck_source(plan.source_dir)
    if not ok:
        observed = {"missing": missing, "unsafeSymlinks": unsafe_symlinks}
        safe_log_error(
            reason_key="ERR-INSTALL-PRECHECK-MISSING-SOURCE",
            message="Installer precheck failed: required source files are missing.",
            config_root=plan.config_root,
            phase="installer",
            gate="precheck",
            mode="repo-aware",
            repo_fingerprint=None,
            command="install.py",
            component="installer-precheck",
            observed_value=observed,
            expected_constraint="Required source files present: master.md, rules.md, start.md",
            remediation="Restore missing governance source files and rerun install.",
            action="abort",
            result="failed",
            reason_namespace="installer-internal",
        )
        eprint("❌ Precheck failed.")
        if missing:
            eprint("   Missing required source files:")
            for m in missing:
                eprint(f"  - {m}")
        if unsafe_symlinks:
            eprint("   Unsafe source symlinks/reparse-points detected (installer fail-closed):")
            for s in unsafe_symlinks:
                eprint(f"  - {s}")
        return 2

    print(f"📁 Target config root: {plan.config_root}")
    print("📁 Ensuring directory structure...")
    ensure_dirs(plan.config_root, dry_run=dry_run)

    # backup root
    backup_root = plan.commands_dir / "_backup" / now_ts()

    # determine governance version from *source* master.md
    gov_ver = read_governance_version_from_master(plan.source_dir / "master.md")

    if not gov_ver:
        safe_log_error(
            reason_key="ERR-INSTALL-GOVERNANCE-VERSION-MISSING",
            message="Governance version not found in master.md.",
            config_root=plan.config_root,
            phase="installer",
            gate="version-check",
            mode="repo-aware",
            repo_fingerprint=None,
            command="install.py",
            component="installer-version",
            observed_value={"masterPath": str(plan.source_dir / "master.md")},
            expected_constraint="# Governance-Version: <semver>",
            remediation="Add Governance-Version header to master.md and rerun install.",
            action="abort",
            result="failed",
            reason_namespace="installer-internal",
        )
        eprint("❌ Governance-Version not found in master.md.")
        eprint("   Expected a header like:")
        eprint("     # Governance-Version: <semver>")
        eprint("   Installation aborted to prevent unversioned deployments.")
        return 2

    copied_entries: list[dict] = []

    # governance paths bootstrap (optional but recommended)
    if plan.skip_paths_file:
        print("\n⚙️  Governance paths bootstrap skipped (--skip-paths-file).")
    else:
        print("\n⚙️  Governance paths (governance.paths.json) bootstrap ...")
        paths_entry = install_governance_paths_file(
            plan=plan,
            dry_run=dry_run,
            force=force,
            backup_enabled=backup_enabled,
            backup_root=backup_root,
        )
        if paths_entry["status"] == "skipped-exists":
            print("  ⏭️  governance.paths.json exists (use --force to overwrite)")
        else:
            print(f"  ✅ governance.paths.json ({paths_entry['status']})")
            copied_entries.append(paths_entry)

    # copy main files
    print("\n📋 Copying governance files to commands/ ...")
    for src in collect_command_root_files(plan.source_dir):
        dst = plan.commands_dir / src.name
        entry = copy_with_optional_backup(
            src=src,
            dst=dst,
            backup_enabled=backup_enabled,
            backup_root=backup_root,
            dry_run=dry_run,
            overwrite=force,
        )
        copied_entries.append(entry)
        status = entry["status"]
        name = src.name
        if status == "missing-source":
            print(f"  ⚠️  {name} not found (skipping)")
        elif status == "skipped-exists":
            print(f"  ⏭️  {name} exists (use --force to overwrite)")
        else:
            print(f"  ✅ {name} ({status})")

    # copy profiles
    profile_files = collect_profile_files(plan.source_dir)
    if profile_files:
        print("\n📋 Copying profile rulebooks to commands/profiles/ ...")
        for pf in profile_files:
            dst = plan.profiles_dst_dir / pf.name
            # Preserve relative structure under profiles/
            rel = pf.relative_to(plan.source_dir)  # profiles/**.md
            dst = plan.commands_dir / rel
            entry = copy_with_optional_backup(
                src=pf,
                dst=dst,
                backup_enabled=backup_enabled,
                backup_root=backup_root,
                dry_run=dry_run,
                overwrite=force,
            )
            copied_entries.append(entry)
            status = entry["status"]
            if status in ("planned-copy", "copied"):
                print(f"  ✅ {rel} ({status})")
            elif status == "skipped-exists":
                print(f"  ⏭️  {rel} exists (use --force to overwrite)")
            else:
                print(f"  ⚠️  {rel} missing (skipping)")
    else:
        print("\nℹ️  No profiles directory found or no *.md profiles to copy.")

    # copy addon manifests (required for dynamic addon activation/reload)
    addon_manifests = collect_profile_addon_manifests(plan.source_dir)
    if addon_manifests:
        print("\n📋 Copying addon manifests to commands/profiles/addons/ ...")
        for af in addon_manifests:
            rel = af.relative_to(plan.source_dir)  # profiles/addons/*.addon.yml
            dst = plan.commands_dir / rel
            entry = copy_with_optional_backup(
                src=af,
                dst=dst,
                backup_enabled=backup_enabled,
                backup_root=backup_root,
                dry_run=dry_run,
                overwrite=force,
            )
            copied_entries.append(entry)
            status = entry["status"]
            if status in ("planned-copy", "copied"):
                print(f"  ✅ {rel} ({status})")
            elif status == "skipped-exists":
                print(f"  ⏭️  {rel} exists (use --force to overwrite)")
            else:
                print(f"  ⚠️  {rel} missing (skipping)")
    else:
        print("\nℹ️  No addon manifests found under profiles/addons/*.addon.yml.")

    # copy diagnostics (audit tooling, schemas, etc.)
    diag_files = collect_diagnostics_files(plan.source_dir)
    if diag_files:
        print("\n📋 Copying diagnostics to commands/diagnostics/ ...")
        for df in diag_files:
            rel = df.relative_to(plan.source_dir)
            dst = plan.commands_dir / rel

            entry = copy_with_optional_backup(
                src=df,
                dst=dst,
                backup_enabled=backup_enabled,
                backup_root=backup_root,
                dry_run=dry_run,
                overwrite=force,
            )
            copied_entries.append(entry)

            status = entry["status"]
            if status in ("planned-copy", "copied"):
                print(f"  ✅ {rel} ({status})")
            elif status == "skipped-exists":
                print(f"  ⏭️  {rel} exists (use --force to overwrite)")
            else:
                print(f"  ⚠️  {rel} missing (skipping)")
    else:
        print("\nℹ️  No diagnostics directory found (skipping).")

    # copy governance runtime package (state machine execution modules)
    runtime_files = collect_governance_runtime_files(plan.source_dir)
    if runtime_files:
        print("\n📋 Copying governance runtime package to commands/governance/ ...")
        for rf in runtime_files:
            rel = rf.relative_to(plan.source_dir)
            dst = plan.commands_dir / rel
            entry = copy_with_optional_backup(
                src=rf,
                dst=dst,
                backup_enabled=backup_enabled,
                backup_root=backup_root,
                dry_run=dry_run,
                overwrite=force,
            )
            copied_entries.append(entry)
            status = entry["status"]
            if status in ("planned-copy", "copied"):
                print(f"  ✅ {rel} ({status})")
            elif status == "skipped-exists":
                print(f"  ⏭️  {rel} exists (use --force to overwrite)")
            else:
                print(f"  ⚠️  {rel} missing (skipping)")
    else:
        print("\nℹ️  No governance runtime package found (skipping).")

    # copy customer helper scripts (catalog-driven)
    try:
        customer_scripts = collect_customer_script_files(plan.source_dir, strict=True)
    except RuntimeError as exc:
        safe_log_error(
            reason_key="ERR-INSTALL-CUSTOMER-SCRIPT-CATALOG-INVALID",
            message="Installer blocked: customer script catalog invalid or missing required entries.",
            config_root=plan.config_root,
            phase="installer",
            gate="customer-scripts",
            mode="repo-aware",
            repo_fingerprint=None,
            command="install.py",
            component="installer-customer-scripts",
            observed_value={"catalog": str(CUSTOMER_SCRIPT_CATALOG_REL), "error": str(exc)},
            expected_constraint="Valid diagnostics/CUSTOMER_SCRIPT_CATALOG.json with ship_in_release scripts",
            remediation="Restore customer script catalog and listed script files, then rerun install.",
            action="abort",
            result="failed",
            reason_namespace="installer-internal",
        )
        eprint(f"❌ {exc}")
        return 2

    print("\n📋 Copying customer scripts to commands/scripts/ ...")
    for sf in customer_scripts:
        rel = sf.relative_to(plan.source_dir)
        dst = plan.commands_dir / rel
        entry = copy_with_optional_backup(
            src=sf,
            dst=dst,
            backup_enabled=backup_enabled,
            backup_root=backup_root,
            dry_run=dry_run,
            overwrite=force,
        )
        copied_entries.append(entry)
        status = entry["status"]
        if status in ("planned-copy", "copied"):
            print(f"  ✅ {rel} ({status})")
        elif status == "skipped-exists":
            print(f"  ⏭️  {rel} exists (use --force to overwrite)")
        else:
            print(f"  ⚠️  {rel} missing (skipping)")

    # copy workflow templates (catalog-driven)
    try:
        workflow_templates = collect_workflow_template_files(plan.source_dir, strict=True)
    except RuntimeError as exc:
        safe_log_error(
            reason_key="ERR-INSTALL-WORKFLOW-TEMPLATE-CATALOG-INVALID",
            message="Installer blocked: workflow template catalog invalid or missing template files.",
            config_root=plan.config_root,
            phase="installer",
            gate="workflow-templates",
            mode="repo-aware",
            repo_fingerprint=None,
            command="install.py",
            component="installer-workflow-templates",
            observed_value={"catalog": str(TEMPLATE_CATALOG_REL), "error": str(exc)},
            expected_constraint="Valid templates/github-actions/template_catalog.json with existing template files",
            remediation="Restore workflow template catalog and listed files, then rerun install.",
            action="abort",
            result="failed",
            reason_namespace="installer-internal",
        )
        eprint(f"❌ {exc}")
        return 2

    print("\n📋 Copying workflow templates to commands/templates/ ...")
    for tf in workflow_templates:
        rel = tf.relative_to(plan.source_dir)
        dst = plan.commands_dir / rel
        entry = copy_with_optional_backup(
            src=tf,
            dst=dst,
            backup_enabled=backup_enabled,
            backup_root=backup_root,
            dry_run=dry_run,
            overwrite=force,
        )
        copied_entries.append(entry)
        status = entry["status"]
        if status in ("planned-copy", "copied"):
            print(f"  ✅ {rel} ({status})")
        elif status == "skipped-exists":
            print(f"  ⏭️  {rel} exists (use --force to overwrite)")
        else:
            print(f"  ⚠️  {rel} missing (skipping)")

    # validation (critical installed files)
    print("\n🔍 Validating installation...")
    critical = [plan.commands_dir / "master.md", plan.commands_dir / "rules.md", plan.commands_dir / "start.md"]
    missing_critical = [p.name for p in critical if not p.exists() and not dry_run]
    if missing_critical:
        eprint("❌ Installation incomplete; missing critical files:")
        for m in missing_critical:
            eprint(f"  - {m}")
        return 3

    # manifest: store only entries that were actually copied/planned
    installed_files = [
        {
            "dst": e["dst"],
            "rel": str(Path(e["dst"]).resolve().relative_to(plan.commands_dir.resolve())) if "dst" in e else None,
            "src": e["src"],
            "sha256": e.get("sha256", "unknown"),
            "backup": e.get("backup"),
            "status": e["status"],
        }
        for e in copied_entries
        if e["status"] in ("copied", "planned-copy", "patched", "planned-patch")
    ]

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "installerVersion": VERSION,
        "governanceVersion": gov_ver,
        "installedAt": datetime.now().isoformat(timespec="seconds"),
        "configRoot": str(plan.config_root),
        "commandsDir": str(plan.commands_dir),
        "files": installed_files,
    }

    print(f"\n🧾 Writing manifest: {plan.manifest_path.name}")
    write_manifest(plan.manifest_path, manifest, dry_run=dry_run)

    print("\n" + "=" * 60)
    if dry_run:
        print("✅ DRY-RUN complete (no changes were made).")
    else:
        print("🎉 Installation complete!")
    print("=" * 60)
    print(f"Commands dir: {plan.commands_dir}")
    print("Next: run /start in OpenCode (or load start.md).")
    return 0


def uninstall(
    plan: InstallPlan,
    dry_run: bool,
    force: bool,
    purge_paths_file: bool,
    keep_error_logs: bool,
) -> int:
    print(f"🧹 Uninstall from: {plan.commands_dir}")

    # We never manage opencode.json. Uninstall only removes installer-owned files under commands/,
    # based on the manifest (or conservative fallback).

    manifest = load_manifest(plan.manifest_path)
    if not manifest:
        print(f"⚠️  Manifest not found or invalid: {plan.manifest_path}")
        print("    For safety, uninstall requires a valid manifest (so we only delete what was installed).")
        print("    Options:")
        print("      - Re-run install once (will recreate manifest), then --uninstall")
        print("      - Or use --force to perform a conservative best-effort delete of known filenames only")
        if not force and not dry_run:
            safe_log_error(
                reason_key="ERR-UNINSTALL-MANIFEST-MISSING",
                message="Uninstall blocked: manifest missing and --force not provided.",
                config_root=plan.config_root,
                phase="installer",
                gate="uninstall",
                mode="repo-aware",
                repo_fingerprint=None,
                command="install.py",
                component="installer-uninstall",
                observed_value={"manifestPath": str(plan.manifest_path)},
                expected_constraint="Valid INSTALL_MANIFEST.json or --force fallback",
                remediation="Re-run install once to recreate manifest, or rerun uninstall with --force.",
                action="block",
                result="blocked",
                reason_namespace="installer-internal",
            )
            return 4

        # Conservative fallback: delete only installer-owned files resolvable from this source tree.
        targets: list[Path] = []

        # Root command files from current source snapshot
        for src in collect_command_root_files(plan.source_dir):
            targets.append(plan.commands_dir / src.name)

        # Static core allowlist as additional safety net for legacy installs
        for name in CORE_COMMAND_FILES:
            targets.append(plan.commands_dir / name)

        # Profiles and addon manifests from current source snapshot
        for src in collect_profile_files(plan.source_dir):
            rel = src.relative_to(plan.source_dir)
            targets.append(plan.commands_dir / rel)
        for src in collect_profile_addon_manifests(plan.source_dir):
            rel = src.relative_to(plan.source_dir)
            targets.append(plan.commands_dir / rel)

        # Diagnostics from current source snapshot
        for src in collect_diagnostics_files(plan.source_dir):
            rel = src.relative_to(plan.source_dir)
            targets.append(plan.commands_dir / rel)

        # Governance runtime from current source snapshot
        for src in collect_governance_runtime_files(plan.source_dir):
            rel = src.relative_to(plan.source_dir)
            targets.append(plan.commands_dir / rel)

        # Customer scripts and workflow templates from current source snapshot (best-effort in fallback mode).
        try:
            for src in collect_customer_script_files(plan.source_dir, strict=False):
                rel = src.relative_to(plan.source_dir)
                targets.append(plan.commands_dir / rel)
        except Exception:
            pass

        try:
            for src in collect_workflow_template_files(plan.source_dir, strict=False):
                rel = src.relative_to(plan.source_dir)
                targets.append(plan.commands_dir / rel)
        except Exception:
            pass

        # Remove governance.paths.json only when explicitly requested.
        if purge_paths_file:
            targets.append(plan.governance_paths_path)

        # Deduplicate while preserving order
        targets = list(dict.fromkeys(targets))
        # intentionally NOT deleting opencode.json (never managed by this installer)

        rc = delete_targets(targets, plan, dry_run=dry_run)
        if not keep_error_logs:
            rc = max(rc, purge_runtime_error_logs(plan.config_root, dry_run=dry_run))
        return rc

    # manifest-based targets
    files = manifest.get("files", [])
    targets: list[Path] = []
    for entry in files:
        rel = entry.get("rel")
        dst = entry.get("dst")
        if rel:
            # Prefer relative paths to make uninstall resilient after moving configRoot.
            targets.append(plan.commands_dir / rel)
        elif dst:
            targets.append(Path(dst))
            
    if purge_paths_file:
        # Explicit operator request: remove machine-specific binding even if it pre-existed.
        targets.append(plan.governance_paths_path)

    if not targets:
        print("ℹ️  Manifest contains no installed files. Nothing to uninstall.")
        return 0

    print("The following files will be removed:")
    for t in targets:
        print(f"  - {t}")

    if not force and not dry_run:
        if not is_interactive():
            eprint("❌ Refusing to prompt in non-interactive mode. Re-run with --force or use --dry-run.")
            return 4
        try:
            resp = input("Really uninstall? [y/N] ").strip().lower()
        except EOFError:
            eprint("❌ Refusing to prompt (stdin closed). Re-run with --force or use --dry-run.")
            return 4
        if resp not in ("y", "yes"):
            print("Uninstall cancelled.")
            return 0

    rc = delete_targets(targets, plan, dry_run=dry_run)

    if not keep_error_logs:
        rc = max(rc, purge_runtime_error_logs(plan.config_root, dry_run=dry_run))

    # remove manifest last (if everything went OK-ish)
    if dry_run:
        print(f"  [DRY-RUN] rm {plan.manifest_path}")
    else:
        if plan.manifest_path.exists():
            try:
                plan.manifest_path.unlink()
                print(f"  ✅ Removed manifest: {plan.manifest_path.name}")
            except Exception as e:
                eprint(f"  ⚠️  Could not remove manifest: {e}")

    # cleanup empty dirs (leaf -> parent)
    cleanup_dirs = [
        plan.commands_dir / "profiles" / "addons",
        plan.commands_dir / "profiles",
        plan.commands_dir / "templates" / "github-actions",
        plan.commands_dir / "templates",
        plan.commands_dir / "scripts",
        plan.commands_dir / "diagnostics",
        plan.commands_dir / "_backup",
        plan.config_root / "workspaces",
    ]
    for d in cleanup_dirs:
        try_remove_empty_dir(d, dry_run=dry_run)
    try_remove_empty_dir(plan.commands_dir, dry_run=dry_run)

    print("\n✅ Uninstall complete.")
    return rc


def delete_targets(targets: Iterable[Path], plan: InstallPlan, dry_run: bool) -> int:
    errors = 0
    for t in targets:
        # Safety guard: only delete within commands_dir
        try:
            t_resolved = t.resolve()
            base_resolved = plan.commands_dir.resolve()
            if base_resolved not in t_resolved.parents and t_resolved != base_resolved:
                safe_log_error(
                    reason_key="ERR-UNINSTALL-PATH-ESCAPE-REFUSED",
                    message="Refused deletion outside commands directory.",
                    config_root=plan.config_root,
                    phase="installer",
                    gate="uninstall-safety",
                    mode="repo-aware",
                    repo_fingerprint=None,
                    command="install.py",
                    component="installer-delete-guard",
                    observed_value={"target": str(t), "resolvedTarget": str(t_resolved)},
                    expected_constraint=f"Target must be under {base_resolved}",
                    remediation="Inspect manifest/targets and rerun uninstall.",
                    action="block",
                    result="blocked",
                    reason_namespace="installer-internal",
                )
                eprint(f"  ❌ Refusing to delete outside commands dir: {t}")
                errors += 1
                continue
        except Exception:
            # If resolution fails, refuse deletion
            safe_log_error(
                reason_key="ERR-UNINSTALL-PATH-RESOLUTION-FAILED",
                message="Refused deletion because target path could not be resolved safely.",
                config_root=plan.config_root,
                phase="installer",
                gate="uninstall-safety",
                mode="repo-aware",
                repo_fingerprint=None,
                command="install.py",
                component="installer-delete-guard",
                observed_value={"target": str(t)},
                expected_constraint="Target path must resolve safely under commands dir",
                remediation="Inspect uninstall targets and rerun.",
                action="block",
                result="blocked",
                reason_namespace="installer-internal",
            )
            eprint(f"  ❌ Refusing to delete (cannot resolve path safely): {t}")
            errors += 1
            continue

        if not t.exists():
            print(f"  ℹ️  Not found: {t}")
            continue

        if t.is_dir():
            # We normally don't expect dirs here; skip for safety
            print(f"  ⚠️  Skipping directory target (unexpected): {t}")
            continue

        if dry_run:
            print(f"  [DRY-RUN] rm {t}")
        else:
            try:
                t.unlink()
                print(f"  ✅ Removed: {t.name}")
            except Exception as e:
                safe_log_error(
                    reason_key="ERR-UNINSTALL-DELETE-FAILED",
                    message="Failed to delete uninstall target.",
                    config_root=plan.config_root,
                    phase="installer",
                    gate="uninstall",
                    mode="repo-aware",
                    repo_fingerprint=None,
                    command="install.py",
                    component="installer-delete",
                    observed_value={"target": str(t), "error": str(e)},
                    expected_constraint="Installer-owned targets should be deletable",
                    remediation="Check file permissions/locks and rerun uninstall.",
                    action="abort",
                    result="failed",
                    reason_namespace="installer-internal",
                )
                eprint(f"  ❌ Failed removing {t}: {e}")
                errors += 1
    return 0 if errors == 0 else 5


def purge_runtime_error_logs(config_root: Path, dry_run: bool) -> int:
    """
    Remove installer/runtime-owned error log files:
      - <config_root>/logs/errors-*.jsonl
      - <config_root>/logs/errors-index.json
      - <config_root>/workspaces/*/logs/errors-*.jsonl
      - <config_root>/workspaces/*/logs/errors-index.json

    Safety:
      - only matching files are removed
      - non-matching user files are preserved
    """
    print("\n🧾 Purging runtime error logs ...")

    targets = sorted(
        set(
            [
                *list((config_root / ERROR_LOGS_DIR_NAME).glob("errors-*.jsonl")),
                *list((config_root / ERROR_LOGS_DIR_NAME).glob("errors-index.json")),
                *list((config_root / "workspaces").glob("*/logs/errors-*.jsonl")),
                *list((config_root / "workspaces").glob("*/logs/errors-index.json")),
            ]
        )
    )

    if not targets:
        print("  ℹ️  No runtime error log files found.")
        return 0

    errors = 0
    touched_dirs: set[Path] = set()
    for t in targets:
        if dry_run:
            print(f"  [DRY-RUN] rm {t}")
        else:
            try:
                t.unlink()
                print(f"  ✅ Removed runtime log: {t}")
            except Exception as e:
                safe_log_error(
                    reason_key="ERR-UNINSTALL-ERROR-LOG-PURGE-FAILED",
                    message="Failed to remove runtime error log file during uninstall purge.",
                    config_root=config_root,
                    phase="installer",
                    gate="uninstall-log-purge",
                    mode="repo-aware",
                    repo_fingerprint=None,
                    command="install.py",
                    component="installer-log-purge",
                    observed_value={"target": str(t), "error": str(e)},
                    expected_constraint="Runtime error log file should be removable",
                    remediation="Check permissions/locks and retry uninstall.",
                    action="abort",
                    result="failed",
                    reason_namespace="installer-internal",
                )
                eprint(f"  ❌ Failed removing runtime log {t}: {e}")
                errors += 1
        touched_dirs.add(t.parent)

    # Remove empty log dirs when possible.
    for d in sorted(touched_dirs, key=lambda p: len(p.parts), reverse=True):
        try_remove_empty_dir(d, dry_run=dry_run)

    # Also try common parents if now empty.
    try_remove_empty_dir(config_root / ERROR_LOGS_DIR_NAME, dry_run=dry_run)
    for repo_logs in (config_root / "workspaces").glob("*/logs"):
        try_remove_empty_dir(repo_logs, dry_run=dry_run)

    return 0 if errors == 0 else 6


def try_remove_empty_dir(d: Path, dry_run: bool) -> None:
    if not d.exists() or not d.is_dir():
        return
    try:
        # only remove if empty
        if any(d.iterdir()):
            return
        if dry_run:
            print(f"  [DRY-RUN] rmdir {d}")
        else:
            d.rmdir()
            print(f"  ✅ Removed empty dir: {d}")
    except Exception:
        return


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Install/Uninstall LLM Governance System files into OpenCode config dir.")
    p.add_argument(
        "--source-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing governance files (default: script directory).",
    )
    p.add_argument(
        "--config-root",
        type=Path,
        default=None,
        help="Override config root (default: auto-detect).",
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing anything.")
    p.add_argument("--force", action="store_true", help="Overwrite without prompting / uninstall without prompt.")
    p.add_argument("--no-backup", action="store_true", help="Disable backup on overwrite (install only).")
    p.add_argument("--uninstall", action="store_true", help="Uninstall previously installed governance files (manifest-based).")
    p.add_argument("--skip-paths-file", action="store_true", help="Do not create/overwrite commands/governance.paths.json.")
    p.add_argument(
        "--deterministic-paths-file",
        action="store_true",
        help="Write deterministic governance.paths.json payload (omit generatedAt timestamp).",
    )
    p.add_argument("--purge-paths-file", action="store_true", help="On uninstall: also remove commands/governance.paths.json even if it pre-existed or the manifest is missing.")
    p.add_argument(
        "--keep-error-logs",
        action="store_true",
        help="On uninstall: preserve runtime error logs under <config_root>/logs and <config_root>/workspaces/*/logs.",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    config_root = args.config_root if args.config_root is not None else get_config_root()
    plan = build_plan(
        args.source_dir,
        config_root,
        skip_paths_file=args.skip_paths_file,
        deterministic_paths_file=args.deterministic_paths_file,
    )

    print("=" * 60)
    print("LLM Governance System Installer")
    print(f"Installer Version: {VERSION}")
    print(f"Mode: {'UNINSTALL' if args.uninstall else 'INSTALL'} | {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    if args.uninstall:
        return uninstall(
            plan,
            dry_run=args.dry_run,
            force=args.force,
            purge_paths_file=args.purge_paths_file,
            keep_error_logs=args.keep_error_logs,
        )

    # install flow
    print(f"Source dir:  {plan.source_dir}")
    print(f"Config root: {plan.config_root}")

    # prompt only if interactive and not forced and not dry-run
    if not args.force and not args.dry_run and is_interactive():
        resp = input(f"\nInstall to {plan.config_root}? [Y/n] ").strip().lower()
        if resp in ("n", "no"):
            print("Installation cancelled.")
            return 0

    backup_enabled = not args.no_backup
    return install(plan, dry_run=args.dry_run, force=args.force, backup_enabled=backup_enabled)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
