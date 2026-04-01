#!/usr/bin/env python3
"""
LLM Governance System - Installer
Installs governance system files to OpenCode config directory.

Features:
- Canonical target on all OS: <user-home>/.config/opencode
- dry-run support
- backup-on-overwrite (timestamped) with --no-backup to disable
- uninstall (manifest-based; deletes only what was installed)
- manifest tracking (INSTALL_MANIFEST.json)

NOTE:
- This installer creates/merges opencode.json instructions for Desktop guidance,
  but uninstall intentionally preserves opencode.json.
- It generates installer-owned sidecar bindings at <config_root>/governance.paths.json for bootstrap.
- Installer governance use `ERR-*` reason keys as installer-internal keys; they are not canonical
  governance `reason_code` values (`BLOCKED-*|WARN-*|NOT_VERIFIED-*`).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
try:
    import pwd
except ImportError:  # pragma: no cover - unavailable on Windows
    pwd = None
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import Iterable


DEFAULT_OPENCODE_PORT = 4096

def get_governance_docs_root(base: Path) -> Path:
    new_path = base / "governance_content" / "docs"
    if new_path.exists():
        return new_path
    return base / "docs"


def get_profiles_root(base: Path) -> Path:
    new_path = base / "governance_content" / "profiles"
    if new_path.exists():
        return new_path
    return base / "profiles"


def get_templates_root(base: Path) -> Path:
    new_path = base / "governance_content" / "templates"
    if new_path.exists():
        return new_path
    return base / "templates"


def get_rulesets_root(base: Path) -> Path:
    new_path = base / "governance_spec" / "rulesets"
    if new_path.exists():
        return new_path
    return base / "rulesets"


def collect_content(base: Path, *, relative: bool) -> list[Path]:
    root = base / "governance_content"
    if not root.exists() or not root.is_dir():
        return []
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if relative:
        return [p.relative_to(base) for p in files]
    return files


def collect_specs(base: Path, *, relative: bool) -> list[Path]:
    root = base / "governance_spec"
    if not root.exists() or not root.is_dir():
        return []
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if relative:
        return [p.relative_to(base) for p in files]
    return files


def _source_master_md(source_dir: Path) -> Path:
    new_path = source_dir / "governance_content" / "reference" / "master.md"
    if new_path.exists():
        return new_path
    return source_dir / "master.md"


def _source_rules_md(source_dir: Path) -> Path:
    new_path = source_dir / "governance_content" / "reference" / "rules.md"
    if new_path.exists():
        return new_path
    return source_dir / "rules.md"


def _source_phase_api_yaml(source_dir: Path) -> Path:
    new_path = source_dir / "governance_spec" / "phase_api.yaml"
    if new_path.exists():
        return new_path
    return source_dir / "phase_api.yaml"


def _source_rules_yml(source_dir: Path) -> Path:
    new_path = source_dir / "governance_spec" / "rules.yml"
    if new_path.exists():
        return new_path
    return source_dir / "rules.yml"


def _source_core_rules_yml(source_dir: Path) -> Path:
    rulesets_root = get_rulesets_root(source_dir)
    return rulesets_root / "core" / "rules.yml"


def _validate_repo_topology(source_dir: Path) -> list[str]:
    """Validate that the source repository has the expected topology.
    
    Returns a list of issues found (empty if all checks pass).
    
    Topology checks:
    - opencode/commands/ must exist (contains command surface)
    - governance_content/reference/ should contain master.md and rules.md
    - governance_spec/ must contain phase_api.yaml and rules.yml
    - governance_runtime/ should exist as migration target
    """
    issues = []
    
    opencode_commands = source_dir / "opencode" / "commands"
    if not opencode_commands.is_dir():
        issues.append(f"opencode/commands/ not found at {opencode_commands}")
    else:
        md_names = sorted(p.name for p in opencode_commands.glob("*.md") if p.is_file())
        expected_names = sorted(CANONICAL_RAIL_FILENAMES)
        if md_names != expected_names:
            issues.append(
                "opencode/commands/ rail set mismatch: "
                f"expected {expected_names}, found {md_names}"
            )
    
    gov_content_ref = source_dir / "governance_content" / "reference"
    if not (gov_content_ref / "master.md").exists():
        issues.append(f"governance_content/reference/master.md not found")
    if not (gov_content_ref / "rules.md").exists():
        issues.append(f"governance_content/reference/rules.md not found")
    
    gov_spec = source_dir / "governance_spec"
    if not (gov_spec / "phase_api.yaml").exists():
        issues.append(f"governance_spec/phase_api.yaml not found")
    if not (gov_spec / "rules.yml").exists():
        issues.append(f"governance_spec/rules.yml not found")
    if not (gov_spec / "rulesets").is_dir():
        issues.append(f"governance_spec/rulesets/ not found")
    
    gov_runtime = source_dir / "governance_runtime"
    if not gov_runtime.is_dir():
        issues.append(f"governance_runtime/ not found (migration target)")
    
    return issues


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8", errors="replace")
        except (OSError, json.JSONDecodeError):
            pass


_ensure_utf8_stdio()

SCRIPT_DIR = Path(__file__).resolve().parent
GOVERNANCE_SOURCE_DIR = SCRIPT_DIR.parent


def _path_for_json(p: Path) -> str:
    """R3: Canonical POSIX-absolute path string for JSON serialization.

    All paths written to JSON files (governance.paths.json, INSTALL_HEALTH.json)
    are POSIX-normalized absolute strings (forward slashes, resolved symlinks).
    Consumers convert to OS-native paths at read time.
    """
    # Use lexical absolute normalization instead of Path.resolve().
    # resolve() can fail on Windows for template segments like
    # "<repo_fingerprint>", which are valid placeholders in installer payloads.
    normalized = os.path.normpath(os.path.abspath(str(p.expanduser())))
    return Path(normalized).as_posix()


def _load_error_logger() -> Callable[..., object]:
    helper = GOVERNANCE_SOURCE_DIR / "entrypoints" / "error_logs.py"
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
    except (ImportError, AttributeError, OSError):
        return lambda **kwargs: {"status": "log-disabled"}


safe_log_error = _load_error_logger()


def _emit_install_flow_event(
    commands_home: Path,
    *,
    event_type: str,
    gov_version: str | None,
    installer_version: str,
    dry_run: bool,
) -> bool:
    """No-op pre-workspace flow logging for final runtime mode.

    Final-state Option A: do not persist installer flow logs before
    a deterministic workspace fingerprint context exists.
    """
    _ = (commands_home, event_type, gov_version, installer_version, dry_run)
    return False


VERSION = "1.1.0-RC.2"
# Canonical command rail surface installed under <config_root>/commands/
CANONICAL_RAIL_FILENAMES = (
    "audit-readout.md",
    "continue.md",
    "hydrate.md",
    "implement.md",
    "implementation-decision.md",
    "plan.md",
    "review-decision.md",
    "review.md",
    "ticket.md",
)

# Files copied into <config_root>/commands
# Strategy: copy governance artifacts that are relevant at runtime.
# Classification now uses Governance API as single source of truth.
# - Include/Exclude logic is local to installer module
# - Legacy constants kept for uninstall safety net only

# Profiles copied into <local_root>/governance_content/profiles/**
PROFILES_DIR_NAME = "profiles"

# Customer helper scripts copied into <config_root>/commands/scripts/**
SCRIPTS_DIR_NAME = "scripts"

# Workflow templates copied into <config_root>/commands/templates/**
TEMPLATES_DIR_NAME = "templates"
TEMPLATE_CATALOG_REL = Path("templates/github-actions/template_catalog.json")
TEMPLATE_CATALOG_SCHEMA = "opencode.workflow-template-catalog.v1"

# Optional OpenCode plugins copied into <config_root>/plugins/**
OPENCODE_PLUGIN_SOURCE_DIR = Path("governance_runtime/artifacts/opencode-plugins")
OPENCODE_PLUGINS_DIR_NAME = "plugins"

# Customer script catalog controlling which scripts are shipped for customers
CUSTOMER_SCRIPT_CATALOG_REL = Path("governance_runtime/assets/catalogs/CUSTOMER_SCRIPT_CATALOG.json")
CUSTOMER_SCRIPT_CATALOG_SCHEMA = "opencode.customer-script-catalog.v1"

# Runtime assets copied into <local_root>/governance_runtime/assets/**
GOVERNANCE_ASSETS_DIR_NAME = "governance_runtime/assets"

# Runtime package copied into <local_root>/governance_runtime/**
GOVERNANCE_RUNTIME_DIR_NAME = "governance_runtime"

FORBIDDEN_METADATA_SEGMENTS = {"__MACOSX", "__pycache__", "_backup"}
FORBIDDEN_METADATA_FILENAMES = {".DS_Store", "Icon\r"}

MANIFEST_NAME = "INSTALL_MANIFEST.json"
MANIFEST_SCHEMA = "1.0"

# Governance paths bootstrap (used by local launcher)
GOVERNANCE_PATHS_NAME = "governance.paths.json"
GOVERNANCE_PATHS_SCHEMA = "opencode-governance.paths.v1"

# Runtime error logs (written by governance helpers; outside repository)
ERROR_LOGS_DIR_NAME = "logs"


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
    - Canonical path on all OS: <user-home>/.config/opencode
    - Override with OPENCODE_CONFIG_ROOT environment variable.
    """
    env_config_file = os.environ.get("OPENCODE_CONFIG")
    if env_config_file:
        return Path(env_config_file).expanduser().resolve().parent

    env_config_dir = os.environ.get("OPENCODE_CONFIG_DIR")
    if env_config_dir:
        return Path(env_config_dir).expanduser().resolve()

    env_config_root = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_config_root:
        return Path(env_config_root).expanduser().resolve()

    system = platform.system()

    if system == "Darwin" and pwd is not None:
        try:
            getpwuid = getattr(pwd, "getpwuid", None)
            getuid = getattr(os, "getuid", None)
            if callable(getpwuid) and callable(getuid):
                pw_entry = getpwuid(getuid())
                home = getattr(pw_entry, "pw_dir", None)
                if home:
                    return Path(home).resolve() / ".config" / "opencode"
        except (OSError, json.JSONDecodeError):
            pass
    return (Path.home().resolve() / ".config" / "opencode").resolve()


def get_local_root() -> Path:
    """Determine local payload root for runtime/content/spec payloads.

    Default: <user-home>/.local/share/opencode
    Override: OPENCODE_LOCAL_ROOT
    """
    env_local = os.environ.get("OPENCODE_LOCAL_ROOT")
    if env_local:
        return Path(env_local).expanduser().resolve()
    return (Path.home().resolve() / ".local" / "share" / "opencode").resolve()


def resolve_known_config_roots(primary_root: Path | None = None) -> list[Path]:
    """Resolve official config roots (single-root by design)."""
    roots: list[Path] = []
    if primary_root is not None:
        roots.append(primary_root.resolve())
    else:
        roots.append(get_config_root())

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        marker = root.as_posix()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(root)
    return deduped


def has_installation(root: Path) -> bool:
    """Best-effort check whether governance appears installed at root."""
    commands = root / "commands"
    if not commands.exists() or not commands.is_dir():
        return False
    rails = sorted(p.name for p in commands.glob("*.md") if p.is_file())
    return rails == sorted(CANONICAL_RAIL_FILENAMES)


def ensure_dirs(config_root: Path, local_root: Path | None = None, dry_run: bool = False) -> None:
    if local_root is None:
        local_root = get_local_root()
    dirs = [
        config_root,
        config_root / "bin",
        config_root / OPENCODE_PLUGINS_DIR_NAME,
        config_root / "commands",
        config_root / "workspaces",
        local_root,
        local_root / "governance_runtime",
        local_root / "governance_content",
        local_root / "governance_content" / "profiles",
        local_root / "governance_content" / "profiles" / "addons",
        local_root / "governance_spec",
    ]
    for d in dirs:
        if dry_run:
            print(f"  [DRY-RUN] mkdir -p {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ {d}")


def create_launcher(
    plan: InstallPlan,
    dry_run: bool,
    force: bool,
    *,
    opencode_port: int = DEFAULT_OPENCODE_PORT,
) -> list[dict]:
    """Create local bootstrap launcher scripts. Returns list of created file entries for manifest."""
    import sys
    import json

    bin_dir = plan.config_root / "bin"
    python_exe = sys.executable
    commands_home = _path_for_json(plan.commands_dir)
    workspaces_home = _path_for_json(plan.config_root / "workspaces")

    created_entries: list[dict] = []
    if dry_run:
        created_entries.extend(
            _planned_launcher_entries(plan=plan, bin_dir=bin_dir)
        )

    launcher_unix = bin_dir / "opencode-governance-bootstrap"
    launcher_win = bin_dir / "opencode-governance-bootstrap.cmd"

    # Write INSTALL_HEALTH.json
    health_path = plan.config_root / "INSTALL_HEALTH.json"
    binding_path = plan.governance_paths_path

    binding_ok = False
    # NOTE: governance.paths.json is now written exclusively by
    # install_governance_paths_file() (single SSOT writer, see C1 fix).
    # The validation read below still runs to populate binding_ok for
    # INSTALL_HEALTH.json.

    if not dry_run:
        try:
            launcher_entries = _write_launcher_wrappers(
                plan=plan,
                python_exe=python_exe,
                dest_unix=launcher_unix,
                dest_win=launcher_win,
                opencode_port=opencode_port,
            )
            created_entries.extend(launcher_entries)
        except RuntimeError as exc:
            raise RuntimeError(f"Launcher generation failed: {exc}")

    if binding_path.exists():
        try:
            data = json.loads(binding_path.read_text(encoding="utf-8"))
            binding_ok = data.get("schema") == "opencode-governance.paths.v1"
        except (OSError, json.JSONDecodeError):
            pass

    git_available = shutil.which("git") is not None
    launcher_present = launcher_unix.exists() or launcher_win.exists()
    python_binding_file = bin_dir / "PYTHON_BINDING"

    health_data = {
        "schema": "opencode-install-health.v1",
        "installerVersion": VERSION,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "configRoot": _path_for_json(plan.config_root),
        "commandsHome": commands_home,
        "workspacesHome": workspaces_home,
        "pythonExecutable": _path_for_json(Path(python_exe)),
        "bindingFilePresent": binding_path.exists(),
        "bindingSchemaOk": binding_ok,
        "pythonBindingFilePresent": python_binding_file.exists(),
        "launcherPresent": launcher_present,
        "gitAvailable": git_available,
    }

    if dry_run:
        print(f"  [DRY-RUN] write {health_path}")
    else:
        import json
        health_path.write_text(json.dumps(health_data, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"  ✅ {health_path}")

    created_entries.append(
        {
            "dst": str(health_path.resolve()) if not dry_run else str(health_path),
            "rel": "INSTALL_HEALTH.json",
            "rel_base": "config",
            "status": "planned-copy" if dry_run else "copied",
            "src": "generated",
        }
    )

    return created_entries


def _resolve_python_executable(binding_path: Path, *, fallback: str, strict: bool = True) -> str:
    if not binding_path.exists():
        return fallback
    try:
        data = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid governance.paths.json: {exc}")
    paths = data.get("paths")
    if not isinstance(paths, dict):
        return fallback
    python_cmd = str(paths.get("pythonCommand") or "").strip()
    if python_cmd:
        if os.path.isabs(python_cmd) and not Path(python_cmd).exists():
            if strict:
                raise RuntimeError(f"pythonCommand not found: {python_cmd}")
            return fallback
    if not python_cmd:
        return fallback
    candidate = Path(python_cmd)
    if candidate.exists():
        return str(candidate)
    if strict:
        raise RuntimeError(f"pythonCommand not found: {python_cmd}")
    return fallback


def _launcher_template_unix(
    *,
    python_exe: str,
    config_root: Path,
    local_root: Path | None = None,
    opencode_port: int = DEFAULT_OPENCODE_PORT,
) -> str:
    if local_root is None:
        local_root = get_local_root()
    """Generate Unix launcher with fail-closed Python resolution and subcommand routing.

    Resolution cascade (python-binding-contract.v1 §3):
      1. Baked PYTHON_BIN (hardcoded at install time)
      2. PYTHON_BINDING file  (bin/PYTHON_BINDING, one line)
      3. Fail-closed: exit 1, NO silent PATH probing

    Subcommand routing (python-binding-contract.v1 §4):
      --session-reader [args]    -> session_reader.py entrypoint
      --ticket-persist [args]    -> phase4_intake_persist entrypoint (canonical)
      --plan-persist [args]      -> phase5_plan_record_persist entrypoint (canonical)
      --review-decision-persist [args] -> review_decision_persist entrypoint (canonical)
      --implement-start [args]   -> implement_start entrypoint (canonical)
      --implementation-decision-persist [args] -> implementation_decision_persist entrypoint (canonical)
      (default / no subcommand)  -> bootstrap_executor
    """
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -e",
            "SCRIPT_DIR=\"$(cd \"$(dirname \"$0\")\" && pwd)\"",
            f"OPENCODE_CONFIG_ROOT=\"{config_root}\"",
            f"OPENCODE_LOCAL_ROOT=\"{local_root}\"",
            "OPENCODE_REPO_ROOT=\"${OPENCODE_REPO_ROOT:-}\"",
            "COMMANDS_HOME=\"${OPENCODE_CONFIG_ROOT}/commands\"",
            "PYTHONPATH=\"${COMMANDS_HOME}:${OPENCODE_LOCAL_ROOT}:${PYTHONPATH}\"",
            "export OPENCODE_CONFIG_ROOT",
            "export OPENCODE_LOCAL_ROOT",
            "export OPENCODE_REPO_ROOT",
            "export COMMANDS_HOME",
            "export PYTHONPATH",
            f"OPENCODE_PORT=\"${{OPENCODE_PORT:-{opencode_port}}}\"",
            "export OPENCODE_PORT",
            "",
            "# --- Python resolution cascade (python-binding-contract.v1 §3) ---",
            f"PYTHON_BIN=\"{python_exe}\"",
            "if [ ! -x \"${PYTHON_BIN}\" ] 2>/dev/null; then",
            "    BINDING_FILE=\"${SCRIPT_DIR}/PYTHON_BINDING\"",
            "    if [ -f \"${BINDING_FILE}\" ]; then",
            "        read -r PYTHON_BIN < \"${BINDING_FILE}\"",
            "    fi",
            "fi",
            "if [ ! -x \"${PYTHON_BIN}\" ] 2>/dev/null; then",
            "    echo \"FATAL: No valid Python interpreter found.\" >&2",
            f"    echo \"  Baked path: {python_exe}\" >&2",
            "    echo \"  PYTHON_BINDING: ${SCRIPT_DIR}/PYTHON_BINDING\" >&2",
            "    echo \"  Re-run install.py to rebind.\" >&2",
            "    exit 1",
            "fi",
            "export OPENCODE_PYTHON=\"${PYTHON_BIN}\"",
            "",
            "# --- Subcommand routing (python-binding-contract.v1 §4) ---",
            "case \"${1:-}\" in",
            "    --session-reader)",
            "        shift",
            "        exec \"${PYTHON_BIN}\" -m governance_runtime.entrypoints.session_reader \"$@\"",
            "        ;;",
            "    --ticket-persist)",
            "        shift",
            "        exec \"${PYTHON_BIN}\" -m governance_runtime.entrypoints.phase4_intake_persist \"$@\"",
            "        ;;",
            "    --plan-persist)",
            "        shift",
            "        exec \"${PYTHON_BIN}\" -m governance_runtime.entrypoints.phase5_plan_record_persist \"$@\"",
            "        ;;",
            "    --review-decision-persist)",
            "        shift",
            "        exec \"${PYTHON_BIN}\" -m governance_runtime.entrypoints.review_decision_persist \"$@\"",
            "        ;;",
            "    --implement-start)",
            "        shift",
            "        exec \"${PYTHON_BIN}\" -m governance_runtime.entrypoints.implement_start \"$@\"",
            "        ;;",
            "    --implementation-decision-persist)",
            "        shift",
            "        exec \"${PYTHON_BIN}\" -m governance_runtime.entrypoints.implementation_decision_persist \"$@\"",
            "        ;;",
            "    *)",
            "        exec \"${PYTHON_BIN}\" -m governance_runtime.entrypoints.bootstrap_executor \"$@\"",
            "        ;;",
            "esac",
            "",
        ]
    )


def _launcher_template_windows(
    *,
    python_exe: str,
    config_root: Path,
    local_root: Path | None = None,
    opencode_port: int = DEFAULT_OPENCODE_PORT,
) -> str:
    if local_root is None:
        local_root = get_local_root()
    """Generate Windows launcher with fail-closed Python resolution and subcommand routing.

    Resolution cascade (python-binding-contract.v1 §3):
      1. Baked PYTHON_EXE (hardcoded at install time)
      2. PYTHON_BINDING file  (bin\\PYTHON_BINDING, one line)
      3. Fail-closed: exit /b 1, NO silent PATH probing

    Subcommand routing (python-binding-contract.v1 §4):
      --session-reader [args]    -> session_reader.py entrypoint
      --ticket-persist [args]    -> phase4_intake_persist entrypoint (canonical)
      --plan-persist [args]      -> phase5_plan_record_persist entrypoint (canonical)
      --review-decision-persist [args] -> review_decision_persist entrypoint (canonical)
      --implement-start [args]   -> implement_start entrypoint (canonical)
      --implementation-decision-persist [args] -> implementation_decision_persist entrypoint (canonical)
      (default / no subcommand)  -> bootstrap_executor
    """
    return "\n".join(
        [
            "@echo off",
            "setlocal EnableDelayedExpansion",
            "set \"SCRIPT_DIR=%~dp0\"",
            f"set \"OPENCODE_CONFIG_ROOT={config_root}\"",
            f"set \"OPENCODE_LOCAL_ROOT={local_root}\"",
            "set \"OPENCODE_REPO_ROOT=%OPENCODE_REPO_ROOT%\"",
            "if not defined OPENCODE_REPO_ROOT (",
            "    if defined GITHUB_WORKSPACE (",
            "        set \"OPENCODE_REPO_ROOT=%GITHUB_WORKSPACE%\"",
            "    )",
            ")",
            "set \"COMMANDS_HOME=%OPENCODE_CONFIG_ROOT%\\commands\"",
            "set \"OPENCODE_HOME=%OPENCODE_CONFIG_ROOT%\"",
            "set \"PYTHONPATH=%COMMANDS_HOME%;%OPENCODE_LOCAL_ROOT%;!PYTHONPATH!\"",
            "if not defined OPENCODE_PORT (",
            f"    set \"OPENCODE_PORT={opencode_port}\"",
            ")",
            "set \"OPENCODE_INTERNAL_BOOTSTRAP_CONFIG_ROOT=%OPENCODE_CONFIG_ROOT%\"",
            "set \"OPENCODE_BOOTSTRAP_BINDING_PATH=%OPENCODE_CONFIG_ROOT%\\governance.paths.json\"",
            "if defined OPENCODE_REPO_ROOT (",
            "    set \"PYTHONPATH=%OPENCODE_REPO_ROOT%;%PYTHONPATH%\"",
            ")",
            "",
            "rem --- Python resolution cascade (python-binding-contract.v1 §3) ---",
            f"set \"PYTHON_EXE={python_exe}\"",
            "if not exist \"!PYTHON_EXE!\" (",
            "    set \"BINDING_FILE=%SCRIPT_DIR%PYTHON_BINDING\"",
            "    if exist \"!BINDING_FILE!\" (",
            "        set /p PYTHON_EXE=<\"!BINDING_FILE!\"",
            "    )",
            ")",
            "if not exist \"!PYTHON_EXE!\" (",
            "    echo FATAL: No valid Python interpreter found. >&2",
            f"    echo   Baked path: {python_exe} >&2",
            "    echo   PYTHON_BINDING: %SCRIPT_DIR%PYTHON_BINDING >&2",
            "    echo   Re-run install.py to rebind. >&2",
            "    exit /b 1",
            ")",
            "set \"OPENCODE_PYTHON=!PYTHON_EXE!\"",
            "",
            "if not defined OPENCODE_BOOTSTRAP_VERBOSE (",
            "    set \"OPENCODE_BOOTSTRAP_VERBOSE=0\"",
            ")",
            "if not defined OPENCODE_BOOTSTRAP_OUTPUT (",
            "    set \"OPENCODE_BOOTSTRAP_OUTPUT=final\"",
            ")",
            "",
            "rem --- Subcommand routing (python-binding-contract.v1 §4) ---",
            "if \"%~1\"==\"--session-reader\" (",
            "    shift",
            "    \"!PYTHON_EXE!\" -m governance_runtime.entrypoints.session_reader %*",
            "    set \"WRAPPER_EXIT=%ERRORLEVEL%\"",
            "    endlocal & exit /b %WRAPPER_EXIT%",
            ")",
            "if \"%~1\"==\"--ticket-persist\" (",
            "    shift",
            "    \"!PYTHON_EXE!\" -m governance_runtime.entrypoints.phase4_intake_persist %*",
            "    set \"WRAPPER_EXIT=%ERRORLEVEL%\"",
            "    endlocal & exit /b %WRAPPER_EXIT%",
            ")",
            "if \"%~1\"==\"--plan-persist\" (",
            "    shift",
            "    \"!PYTHON_EXE!\" -m governance_runtime.entrypoints.phase5_plan_record_persist %*",
            "    set \"WRAPPER_EXIT=%ERRORLEVEL%\"",
            "    endlocal & exit /b %WRAPPER_EXIT%",
            ")",
            "if \"%~1\"==\"--review-decision-persist\" (",
            "    shift",
            "    \"!PYTHON_EXE!\" -m governance_runtime.entrypoints.review_decision_persist %*",
            "    set \"WRAPPER_EXIT=%ERRORLEVEL%\"",
            "    endlocal & exit /b %WRAPPER_EXIT%",
            ")",
            "if \"%~1\"==\"--implement-start\" (",
            "    shift",
            "    \"!PYTHON_EXE!\" -m governance_runtime.entrypoints.implement_start %*",
            "    set \"WRAPPER_EXIT=%ERRORLEVEL%\"",
            "    endlocal & exit /b %WRAPPER_EXIT%",
            ")",
            "if \"%~1\"==\"--implementation-decision-persist\" (",
            "    shift",
            "    \"!PYTHON_EXE!\" -m governance_runtime.entrypoints.implementation_decision_persist %*",
            "    set \"WRAPPER_EXIT=%ERRORLEVEL%\"",
            "    endlocal & exit /b %WRAPPER_EXIT%",
            ")",
            "\"!PYTHON_EXE!\" -m governance_runtime.entrypoints.bootstrap_executor %*",
            "set \"WRAPPER_EXIT=%ERRORLEVEL%\"",
            "endlocal & exit /b %WRAPPER_EXIT%",
            "",
        ]
    )


def _write_python_binding_file(bin_dir: Path, python_exe: str) -> Path:
    """Write the PYTHON_BINDING artifact: a single-line plain-text file
    containing the absolute POSIX-normalized interpreter path.

    This is the secondary resolution source for launchers (after baked
    PYTHON_BIN) and the primary file-based source for the plugin.
    See python-binding-contract.v1 Section 2.2.
    """
    binding_file = bin_dir / "PYTHON_BINDING"
    # Always POSIX-normalized absolute path (match governance.paths.json normalization)
    posix_path = Path(os.path.normpath(os.path.abspath(str(Path(python_exe).expanduser())))).as_posix()
    binding_file.write_text(posix_path + "\n", encoding="utf-8")
    return binding_file


def _write_launcher_wrappers(
    *,
    plan: InstallPlan,
    python_exe: str,
    dest_unix: Path,
    dest_win: Path,
    opencode_port: int,
) -> list[dict]:
    created: list[dict] = []
    binding_path = plan.governance_paths_path
    try:
        python_exec = _resolve_python_executable(binding_path, fallback=python_exe, strict=True)
    except RuntimeError as exc:
        raise RuntimeError(f"Invalid pythonCommand in governance.paths.json: {exc}")

    bin_dir = dest_unix.parent  # bin/

    # Write PYTHON_BINDING artifact (python-binding-contract.v1 §2.2)
    binding_file = _write_python_binding_file(bin_dir, python_exec)
    created.append({
        "dst": str(binding_file.resolve()),
        "rel": str(binding_file.relative_to(plan.config_root)),
        "rel_base": "config",
        "src": "generated",
        "status": "generated",
    })

    unix_payload = _launcher_template_unix(
        python_exe=python_exec,
        config_root=plan.config_root,
        local_root=plan.local_root,
        opencode_port=opencode_port,
    )
    win_payload = _launcher_template_windows(
        python_exe=python_exec,
        config_root=plan.config_root,
        local_root=plan.local_root,
        opencode_port=opencode_port,
    )

    dest_unix.write_text(unix_payload, encoding="utf-8")
    dest_unix.chmod(0o755)
    created.append({"dst": str(dest_unix.resolve()), "src": "generated", "status": "generated"})

    dest_win.write_text(win_payload, encoding="utf-8")
    created.append({"dst": str(dest_win.resolve()), "src": "generated", "status": "generated"})

    return created


def _planned_launcher_entries(*, plan: InstallPlan, bin_dir: Path) -> list[dict]:
    launcher_unix = bin_dir / "opencode-governance-bootstrap"
    launcher_win = bin_dir / "opencode-governance-bootstrap.cmd"
    binding_file = bin_dir / "PYTHON_BINDING"
    return [
        {
            "dst": str(binding_file),
            "rel": str(binding_file.relative_to(plan.config_root)),
            "rel_base": "config",
            "status": "planned-copy",
            "src": "generated",
        },
        {
            "dst": str(launcher_unix),
            "rel": str(launcher_unix.relative_to(plan.config_root)),
            "rel_base": "config",
            "status": "planned-copy",
            "src": "generated",
        },
        {
            "dst": str(launcher_win),
            "rel": str(launcher_win.relative_to(plan.config_root)),
            "rel_base": "config",
            "status": "planned-copy",
            "src": "generated",
        },
    ]


def read_governance_version_metadata(version_file: Path) -> str | None:
    """Read canonical governance version from kernel-owned metadata file."""
    if not version_file.exists():
        return None

    # Keep permissive parsing, but require a reasonable "semver-ish" token.
    semverish = re.compile(r"\b\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\b")

    try:
        raw = version_file.read_text(encoding="utf-8").strip()
        mm = semverish.search(raw)
        if mm:
            return mm.group(0)
    except (OSError, UnicodeDecodeError):
        return None
    return None


@dataclass(frozen=True)
class InstallPlan:
    source_dir: Path
    config_root: Path
    local_root: Path
    commands_dir: Path
    profiles_dst_dir: Path
    manifest_path: Path
    governance_paths_path: Path
    skip_paths_file: bool
    deterministic_paths_file: bool


def build_plan(
    source_dir: Path,
    config_root: Path,
    local_root: Path | None = None,
    *,
    skip_paths_file: bool,
    deterministic_paths_file: bool,
) -> InstallPlan:
    if local_root is None:
        local_root = get_local_root()
    commands_dir = config_root / "commands"
    profiles_dst_dir = local_root / "governance_content" / "profiles"
    manifest_path = config_root / MANIFEST_NAME
    governance_paths_path = config_root / GOVERNANCE_PATHS_NAME
    return InstallPlan(
        source_dir=source_dir,
        config_root=config_root,
        local_root=local_root,
        commands_dir=commands_dir,
        profiles_dst_dir=profiles_dst_dir,
        manifest_path=manifest_path,
        governance_paths_path=governance_paths_path,
        skip_paths_file=skip_paths_file,
        deterministic_paths_file=deterministic_paths_file,
    )


def required_source_files(source_dir: Path) -> list[str]:
    # YAML rulebooks are authoritative; VERSION is required, YAML rulebooks preferred
    # MD files are guidance-only and optional
    # NOTE: Some downstream test bundles place files under alternative
    # locations (for example root VERSION and governance_spec/rulesets/core/rules.yml).
    # We keep the explicit list for compatibility, but augment precheck logic to
    # tolerate alternative layouts in case the expected paths are missing in a
    # given bundle. The actual existence checks are performed in precheck_source.
    _ = source_dir
    # Support both legacy root-based and new governance_spec paths for rules
    # The canonical rules now live under governance_spec/, but keep compatibility
    # by including both layouts if present.
    return [
        "VERSION",
        "governance_spec/rules.yml",
        "governance_spec/rulesets/core/rules.yml",
    ]


def precheck_source(source_dir: Path) -> tuple[bool, list[str], list[str]]:
    """Pre-checks for required governance source files.

    Accept multiple possible layouts to support different distributions/layouts
    of the governance source tarballs. Specifically, tolerate either root-based
    VERSION and rules.yml or their governance-namespaced equivalents.
    Additionally, if the tarball uses an alternative layout with a root rules.yml
    at other common locations, treat that as a valid source as well.
    """
    missing: list[str] = []

    # Version: allow VERSION at root or governance_runtime/VERSION
    version_root = source_dir / "VERSION"
    version_governance = source_dir / "governance_runtime" / "VERSION"
    has_version = version_root.exists() or version_governance.exists()
    if not has_version:
        missing.append("VERSION")

    # Rules.yml: tolerate multiple layouts
    rules_candidates = [
        _source_core_rules_yml(source_dir),
        _source_rules_yml(source_dir),
        source_dir / "governance_runtime" / "rulesets" / "core" / "rules.yml",
        source_dir / "governance_runtime" / "rules.yml",
    ]
    has_rules = any(p.exists() for p in rules_candidates)
    if not has_rules:
        # Fallback: look for rules.md or any *rules*.yml
        for p in source_dir.rglob("rules.md"):
            if p.is_file():
                has_rules = True
                break
        if not has_rules:
            for p in source_dir.rglob("*rules*.yml"):
                if p.is_file():
                    has_rules = True
                    break
    if not has_rules:
        # Fail closed: no source mutation/placeholders in installer precheck.
        if _source_core_rules_yml(source_dir).exists() is False:
            missing.append("rulesets/core/rules.yml")
        if _source_rules_yml(source_dir).exists() is False:
            missing.append("rules.yml")

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

    profiles_src_dir = get_profiles_root(source_dir)
    if profiles_src_dir.exists():
        for p in profiles_src_dir.rglob("*"):
            if p.is_symlink():
                unsafe.add(str(p.relative_to(source_dir)).replace("\\", "/"))

    governance_assets_dir = source_dir / GOVERNANCE_ASSETS_DIR_NAME
    if governance_assets_dir.exists():
        for p in governance_assets_dir.rglob("*"):
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

    templates_dir = get_templates_root(source_dir)
    if templates_dir.exists():
        for p in templates_dir.rglob("*"):
            if p.is_symlink():
                unsafe.add(str(p.relative_to(source_dir)).replace("\\", "/"))

    plugins_dir = source_dir / OPENCODE_PLUGIN_SOURCE_DIR
    if plugins_dir.exists():
        for p in plugins_dir.rglob("*"):
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


def _is_forbidden_installed_path(path: Path, commands_dir: Path) -> bool:
    """Return True when installed path is forbidden in customer payload."""

    try:
        rel = path.resolve().relative_to(commands_dir.resolve())
    except ValueError:
        return False
    if any(part == "_backup" for part in rel.parts):
        return True
    if any(part in FORBIDDEN_METADATA_SEGMENTS for part in rel.parts):
        return True
    if any(part.startswith("._") for part in rel.parts):
        return True
    if rel.name in FORBIDDEN_METADATA_FILENAMES:
        return True
    # Logs must never be inside deprecated command-tree leftovers.
    # The only valid runtime logs location is workspace-scoped:
    #   <config_root>/workspaces/<repo_fingerprint>/logs/
    if len(rel.parts) >= 2 and rel.parts[0] == "governance" and rel.parts[1] == ERROR_LOGS_DIR_NAME:
        return True
    return False


def enforce_commands_hygiene(*, commands_dir: Path, dry_run: bool) -> tuple[list[str], list[str]]:
    """Enforce strict commands/ allowlist and report residual violations.

    Allowed files under commands/:
    - 8 canonical rail markdown files
    """

    if not commands_dir.exists() or not commands_dir.is_dir():
        return ([], [])

    removed: list[str] = []
    allowed_names = set(CANONICAL_RAIL_FILENAMES)

    for path in sorted(commands_dir.iterdir(), key=lambda p: p.name):
        rel = path.relative_to(commands_dir).as_posix()
        if path.is_file():
            if path.name in allowed_names:
                continue
            removed.append(rel)
            if dry_run:
                print(f"  [DRY-RUN] rm {path}")
            else:
                try:
                    path.unlink()
                except OSError:
                    pass
            continue
        if path.is_dir():
            removed.append(rel)
            if dry_run:
                print(f"  [DRY-RUN] rm -rf {path}")
            else:
                if path.is_symlink():
                    try:
                        path.unlink()
                    except OSError:
                        pass
                else:
                    shutil.rmtree(path, ignore_errors=True)

    violations: list[str] = []
    for path in sorted(commands_dir.rglob("*")):
        rel = path.relative_to(commands_dir).as_posix()
        if path.is_dir():
            violations.append(rel + "/")
            continue
        if path.name not in allowed_names:
            violations.append(rel)

    md_files = sorted(p.name for p in commands_dir.glob("*.md") if p.is_file())
    expected_md = sorted(CANONICAL_RAIL_FILENAMES)
    if md_files != expected_md:
        violations.append(f"RAIL_SET_MISMATCH expected={expected_md} actual={md_files}")

    return (sorted(dict.fromkeys(removed)), sorted(dict.fromkeys(violations)))


def enforce_local_payload_hygiene(*, local_root: Path, dry_run: bool) -> tuple[list[str], list[str]]:
    """Preserve existing local-root contents, only manage installer-owned governance directories.
    
    CRITICAL: This function MUST NOT delete or modify any pre-existing content in local_root.
    It only ensures governance-owned directories exist and removes installer-generated
    metadata (like error logs), while PRESERVING all user content including 'opencode'.
    """
    removed: list[str] = []
    governance_dirs = {"governance_runtime", "governance_content", "governance_spec"}
    harmless_metadata = FORBIDDEN_METADATA_FILENAMES

    if local_root.exists() and local_root.is_dir():
        for path in sorted(local_root.iterdir(), key=lambda p: p.name):
            if path.name in harmless_metadata:
                rel = path.relative_to(local_root).as_posix()
                removed.append(rel)
                if dry_run:
                    print(f"  [DRY-RUN] rm {path}")
                else:
                    try:
                        path.unlink()
                    except OSError:
                        pass
            elif path.name in governance_dirs:
                continue
            print(f"  🛡️  PRESERVED (non-governance): {path.name}/")

    governance_logs = local_root / "governance_runtime" / ERROR_LOGS_DIR_NAME
    if governance_logs.exists() and governance_logs.is_dir():
        rel = governance_logs.relative_to(local_root).as_posix()
        removed.append(rel)
        if dry_run:
            print(f"  [DRY-RUN] rm -rf {governance_logs}")
        else:
            shutil.rmtree(governance_logs, ignore_errors=True)

    return removed, []

def collect_command_root_files(source_dir: Path) -> list[Path]:
    """
    Collect command files for installation to <config_root>/commands/.
    
    This is layer-pure: only canonical OpenCode commands.
    Does NOT include content, specs, or plugins.
    
    Returns absolute paths for compatibility with caller.
    """
    from pathlib import Path
    
    commands_root = source_dir / "opencode" / "commands"
    files: list[Path] = []
    for name in CANONICAL_RAIL_FILENAMES:
        p = commands_root / name
        if p.exists() and p.is_file() and not p.is_symlink() and not _is_forbidden_metadata_path(p, source_dir):
            files.append(p)
    return sorted(files, key=lambda p: str(p))


def collect_content_files(source_dir: Path) -> list[Path]:
    """
    Collect content files for installation.
    
    Includes: master.md, rules.md, docs/, profiles/, templates/
    
    Returns absolute paths.
    """
    files: list[Path] = []
    
    # Get content from canonical content tree
    for content in collect_content(source_dir, relative=False):
        files.append(content)
    
    # Exclude installer scripts
    exclude_names = {
        "install.py",
        "install.corrected.py",
        "install.updated.py",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        ".commitlintrc",
        ".commitlintrc.js",
        ".commitlintrc.cjs",
    }
    
    # Deduplicate: prefer governance_content version over legacy
    # Build a map of filename -> path, preferring governance_content
    file_map: dict[str, Path] = {}
    for f in files:
        if f.name in exclude_names:
            continue
        if _is_forbidden_metadata_path(f, source_dir):
            continue
        # If we already have this file and the new one is from legacy, skip it
        if f.name in file_map:
            existing = file_map[f.name]
            # Prefer non-governance_content path (the SSOT location)
            if "governance_content" in str(existing) and "governance_content" not in str(f):
                continue
            elif "governance_content" not in str(existing) and "governance_content" in str(f):
                # Replace with governance_content version
                file_map[f.name] = f
            continue
        file_map[f.name] = f
    
    return sorted(file_map.values(), key=lambda p: str(p))


def collect_spec_files(source_dir: Path) -> list[Path]:
    """
    Collect spec files for installation.
    
    Includes: phase_api.yaml, rules.yml, schemas/
    
    Returns absolute paths.
    """
    files: list[Path] = []
    
    for spec in collect_specs(source_dir, relative=False):
        files.append(spec)
    
    # Add VERSION files (special case)
    version_root = source_dir / "VERSION"
    if version_root.exists():
        files.append(version_root)
    version_gov = source_dir / "governance_runtime" / "VERSION"
    if version_gov.exists():
        files.append(version_gov)
    
    result: list[Path] = []
    for f in files:
        if _is_forbidden_metadata_path(f, source_dir):
            continue
        result.append(f)
    
    return sorted(result, key=lambda p: str(p))

def collect_governance_runtime_files(source_dir: Path) -> list[Path]:
    """
    Collect governance runtime files for packaged state-machine execution.
    
    This function collects canonical runtime modules.
    
    Includes:
    - Files from governance_runtime/
    
    Returns absolute paths (for compatibility with caller).
    """
    runtime_roots = [
        source_dir / GOVERNANCE_RUNTIME_DIR_NAME,
        source_dir / "governance_runtime",
    ]

    files: list[Path] = []
    for runtime_dir in runtime_roots:
        if not runtime_dir.exists() or not runtime_dir.is_dir():
            continue
        files.extend(p for p in runtime_dir.rglob("*") if p.is_file())

    if not files:
        return []
    
    result: list[Path] = []
    for f in files:
        abs_path = f
        # Exclude plugin files - they are collected separately via collect_opencode_plugin_files
        if "artifacts" in str(abs_path) and "opencode-plugins" in str(abs_path):
            continue
        if abs_path.is_file() and not abs_path.is_symlink() and not _is_forbidden_metadata_path(abs_path, source_dir):
            result.append(abs_path)
    
    return sorted(result, key=lambda p: str(p))


DOCS_DIR_NAME = "docs"


def collect_customer_docs_files(source_dir: Path) -> list[Path]:
    """
    Collect customer-relevant documentation from docs/ directory.
    
    This function uses the canonical content tree as single source of truth.
    It filters GOVERNANCE_CONTENT files from docs/ directory.
    """
    docs_dir = get_governance_docs_root(source_dir)
    if not docs_dir.exists() or not docs_dir.is_dir():
        return []
    
    # Determine if we're in SSOT mode (governance_content exists) or legacy mode
    is_ssot = (source_dir / "governance_content").exists()
    
    # Use governance API to get content files from docs/
    content_files = collect_content(source_dir, relative=True)
    
    result: list[Path] = []
    for f in content_files:
        # Only include files from the appropriate docs directory
        f_str = str(f)
        if is_ssot:
            # SSOT mode: only include governance_content/docs/
            if not f_str.startswith("governance_content/docs/"):
                continue
        else:
            # Legacy mode: only include docs/
            if not f_str.startswith("docs/"):
                continue
        parts = Path(f_str.replace("\\", "/")).parts
        if len(parts) >= 3 and parts[0] in {"docs", "governance_content"} and parts[1] == "docs" and parts[2] == "governance":
            continue
        abs_path = source_dir / f
        if abs_path.is_file() and abs_path.suffix.lower() == ".md":
            if not _is_forbidden_metadata_path(abs_path, source_dir):
                result.append(abs_path)
    
    return sorted(result, key=lambda p: str(p))


GOVERNANCE_DOCS_DIR_NAME = str(Path("docs") / "governance")


def collect_governance_docs_files(source_dir: Path) -> list[Path]:
    """Collect control documentation from docs governance directory.

    These files (e.g. governance_schemas.md, doc_lint.md) are heavily
    referenced by master.md and rules.md but were previously not installed.
    
    Uses dual-read resolver to support both old and new directory structures.
    """

    gov_docs_dir = get_governance_docs_root(source_dir) / "governance"
    if not gov_docs_dir.exists() or not gov_docs_dir.is_dir():
        return []
    return sorted(
        [
            p
            for p in gov_docs_dir.rglob("*.md")
            if p.is_file()
            and not p.is_symlink()
            and not _is_forbidden_metadata_path(p, source_dir)
        ]
    )


def collect_customer_script_files(source_dir: Path, *, strict: bool) -> list[Path]:
    """Collect customer-relevant scripts listed in runtime customer script catalog."""

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

    templates_root = get_templates_root(source_dir)
    catalog_path = templates_root / "github-actions" / "template_catalog.json"
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
            or not (
                rel.startswith("templates/github-actions/")
                or rel.startswith("governance_content/templates/github-actions/")
            )
            or rel_path.suffix != ".yml"
        ):
            if strict:
                raise RuntimeError(
                    f"{TEMPLATE_CATALOG_REL}: templates[{idx}].file must be templates/github-actions/*.yml"
                )
            continue

        src = source_dir / rel_path
        if not src.exists() and rel.startswith("templates/"):
            src = source_dir / "governance_content" / rel
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


def build_governance_paths_payload(config_root: Path, local_root: Path | None = None, *, deterministic: bool) -> dict:
    """
    Create a small, installer-owned JSON document that records the canonical absolute paths
    derived from config_root. This is *not* an OpenCode config file and is therefore not
    validated against the OpenCode config schema.

    The local bootstrap launcher loads this file via shell output injection to avoid interactive path binding.
    """
    def norm(p: Path) -> str:
        """R3: POSIX-normalized absolute path string for JSON serialization."""
        return _path_for_json(p)

    if local_root is None:
        local_root = get_local_root()

    commands_home = config_root / "commands"
    governance_home = local_root / "governance"
    runtime_home = local_root / "governance_runtime"
    content_home = local_root / "governance_content"
    profiles_home = content_home / "profiles"
    spec_home = local_root / "governance_spec"
    workspaces_home = config_root / "workspaces"
    global_error_logs_home = workspaces_home / "_global" / "logs"
    python_command = _path_for_json(Path(sys.executable))

    doc = {
        "schema": GOVERNANCE_PATHS_SCHEMA,
        "paths": {
            "configRoot": norm(config_root),
            "localRoot": norm(local_root),
            "commandsHome": norm(commands_home),
            "profilesHome": norm(profiles_home),
            "governanceHome": norm(governance_home),
            "runtimeHome": norm(runtime_home),
            "contentHome": norm(content_home),
            "specHome": norm(spec_home),
            "workspacesHome": norm(workspaces_home),
            "globalErrorLogsHome": norm(global_error_logs_home),
            "workspaceErrorLogsHomeTemplate": norm(workspaces_home / "<repo_fingerprint>" / "logs"),
            "pythonCommand": python_command,
        },
        "commandProfiles": {},
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
    Create/update <config_root>/governance.paths.json.

    Semantics:
    - create if missing
    - overwrite only when --force
    - backup on overwrite when enabled
    - recorded in the manifest (installer-owned)
    """
    dst = plan.governance_paths_path
    dst_exists = dst.exists()
    rel = GOVERNANCE_PATHS_NAME
    rel_base = "config"

    desired_doc = build_governance_paths_payload(plan.config_root, plan.local_root, deterministic=plan.deterministic_paths_file)

    if dst_exists and not force:
        existing = _load_json(dst)
        if existing and existing.get("schema") == GOVERNANCE_PATHS_SCHEMA and isinstance(existing.get("paths"), dict):
            existing_paths = existing["paths"]
            # existing_paths is guaranteed dict by the isinstance check above

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
                        "rel": rel,
                        "rel_base": rel_base,
                        "backup": backup_path,
                        "sha256": hashlib.sha256(json_bytes(existing)).hexdigest(),
                        "note": f"patched missing keys: {','.join(missing_keys)}",
                    }

                dst.write_bytes(json_bytes(existing))
                return {
                    "status": "patched",
                    "src": "generated",
                    "dst": str(dst),
                    "rel": rel,
                    "rel_base": rel_base,
                    "backup": backup_path,
                    "sha256": sha256_file(dst),
                    "note": f"patched missing keys: {','.join(missing_keys)}",
                }

        return {
            "status": "skipped-exists",
            "src": "generated",
            "dst": str(dst),
            "rel": rel,
            "rel_base": rel_base,
        }

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
            "rel": rel,
            "rel_base": rel_base,
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
        "rel": rel,
        "rel_base": rel_base,
        "backup": backup_path,
        "sha256": sha256_file(dst),
        "note": "governance paths bootstrap",
    }


def backup_file(dst: Path, backup_root: Path, dry_run: bool) -> Path:
    rel = confirm_relative(dst, base_root=backup_root.parent)
    backup_path = backup_root / rel
    if dry_run:
        print(f"  [DRY-RUN] backup {dst} -> {backup_path}")
        return backup_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dst, backup_path)
    return backup_path


def confirm_relative(path: Path, *, base_root: Path) -> Path:
    """
    Create a constrained relative path fragment for backups.
    """
    p = path.resolve()
    base = base_root.resolve()
    try:
        return p.relative_to(base)
    except ValueError:
        return Path("external") / p.name


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
    profiles_src_dir = get_profiles_root(source_dir)
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
    profiles_src_dir = get_profiles_root(source_dir)
    if not profiles_src_dir.exists():
        return []
    return sorted(
        [
            p
            for p in profiles_src_dir.rglob("*.addon.yml")
            if p.is_file() and not p.is_symlink() and not _is_forbidden_metadata_path(p, source_dir)
        ]
    )


def collect_opencode_plugin_files(source_dir: Path) -> list[Path]:
    plugins_src_dir = source_dir / OPENCODE_PLUGIN_SOURCE_DIR
    if not plugins_src_dir.exists():
        return []
    return sorted(
        [
            p
            for p in plugins_src_dir.rglob("*")
            if p.suffix.lower() in {".mjs", ".js"}
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_manifest(manifest_path: Path) -> dict | None:
    """Load and validate INSTALL_MANIFEST.json.

    Returns the parsed dict only if:
    - file exists and is valid JSON
    - top-level value is a dict
    - schema field matches MANIFEST_SCHEMA
    - 'files' key is present and is a list or dict

    Returns None for any validation failure (R9 safety gate).
    """
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema") != MANIFEST_SCHEMA:
        return None
    files = data.get("files")
    if not isinstance(files, (dict, list)):
        return None
    return data


# ---------------------------------------------------------------------------
# OpenCode Desktop bridge: opencode.json instructions + command template injection
# ---------------------------------------------------------------------------

OPENCODE_JSON_NAME = "opencode.json"

# Canonical command markdown files - ONLY these are true slash commands
# Note: NON-command content (master.md, rules.md, etc.) is NOT installed as command surface
OPENCODE_INSTRUCTIONS = [f"commands/{name}" for name in CANONICAL_RAIL_FILENAMES]
OPENCODE_PLUGIN_KEY = "plugin"
OPENCODE_PLUGIN_RELATIVE = f"{OPENCODE_PLUGINS_DIR_NAME}/audit-new-session.mjs"

SESSION_READER_PLACEHOLDER = "{{SESSION_READER_PATH}}"
PYTHON_COMMAND_PLACEHOLDER = "{{PYTHON_COMMAND}}"
BIN_DIR_PLACEHOLDER = "{{BIN_DIR}}"


def _parse_opencode_port(raw: str | int, *, purpose: str) -> int:
    token = str(raw).strip()
    if not token:
        raise ValueError(f"{purpose}: empty port")
    try:
        value = int(token)
    except ValueError as exc:
        raise ValueError(f"{purpose}: port must be an integer") from exc
    if value < 1 or value > 65535:
        raise ValueError(f"{purpose}: port must be between 1 and 65535")
    return value


def resolve_effective_opencode_port(
    *,
    cli_opencode_port: str | int | None,
    env: Mapping[str, str] | None = None,
    default_port: int = DEFAULT_OPENCODE_PORT,
) -> int:
    """Resolve the effective OpenCode port from a single contract.

    Priority:
      1) explicit CLI argument (--opencode-port)
      2) OPENCODE_PORT environment value
      3) default 4096
    """
    if cli_opencode_port is not None and str(cli_opencode_port).strip():
        return _parse_opencode_port(cli_opencode_port, purpose="--opencode-port")

    env_map = env if env is not None else os.environ
    env_port = str(env_map.get("OPENCODE_PORT", "")).strip()
    if env_port:
        return _parse_opencode_port(env_port, purpose="OPENCODE_PORT")

    return _parse_opencode_port(default_port, purpose="default OPENCODE port")


DEFAULT_OPENCODE_HOSTNAME = "127.0.0.1"


def resolve_effective_opencode_hostname(
    *,
    cli_opencode_hostname: str | None,
    opencode_json_config: dict | None = None,
    default_hostname: str = DEFAULT_OPENCODE_HOSTNAME,
) -> str:
    """Resolve the effective OpenCode hostname from a single contract.

    Priority:
      1) explicit CLI argument (cli_opencode_hostname)
      2) opencode.json server.hostname
      3) default 127.0.0.1

    Note: Unlike port, hostname does NOT have an environment variable fallback
    to avoid creating undocumented resolution paths. The JSON config is the
    authoritative source for hostname.
    """
    if cli_opencode_hostname is not None and str(cli_opencode_hostname).strip():
        return str(cli_opencode_hostname).strip()

    if opencode_json_config is not None:
        server_block = opencode_json_config.get("server", {})
        if isinstance(server_block, dict):
            hostname = server_block.get("hostname", "").strip()
            if hostname:
                return hostname

    return default_hostname


def ensure_opencode_json(
    config_root: Path,
    *,
    dry_run: bool,
    effective_opencode_port: int = DEFAULT_OPENCODE_PORT,
    include_legacy_command_files: bool = False,
) -> dict:
    """Generate or merge ``opencode.json`` with governance instructions for Desktop.

    - If the file does not exist, create it with the ``instructions`` array.
    - If it exists, merge: add missing instruction entries, ensure plugin is set,
      and actively remove any legacy ``command_files`` key unless
      include_legacy_command_files=True.
      Other user keys are preserved.

    Returns a status dict for logging.
    """
    target = config_root / OPENCODE_JSON_NAME

    plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()

    if target.exists():
        raw_text = target.read_text(encoding="utf-8")
        corrupt = False
        try:
            existing = json.loads(raw_text)
            if not isinstance(existing, dict):
                corrupt = True
                existing = {}
        except (OSError, json.JSONDecodeError):
            corrupt = True
            existing = {}

        # R6 fix: backup corrupt opencode.json before overwriting
        if corrupt and not dry_run:
            backup_name = target.with_suffix(".json.corrupt-backup")
            try:
                backup_name.write_text(raw_text, encoding="utf-8")
            except OSError:
                pass  # best-effort backup

        # Keep legacy command_files only when explicitly requested for
        # compatibility with older Desktop builds.
        if include_legacy_command_files:
            existing["command_files"] = list(OPENCODE_INSTRUCTIONS)
        else:
            existing.pop("command_files", None)

        current = existing.get("instructions")
        if not isinstance(current, list):
            current = []
        merged = list(current)
        for entry in OPENCODE_INSTRUCTIONS:
            if entry not in merged:
                merged.append(entry)
        existing["instructions"] = merged

        plugins_current = existing.get(OPENCODE_PLUGIN_KEY)
        if not isinstance(plugins_current, list):
            plugins_current = []
        plugins_merged = list(plugins_current)
        if plugin_uri not in plugins_merged:
            plugins_merged.append(plugin_uri)
        existing[OPENCODE_PLUGIN_KEY] = plugins_merged

        # Ensure deterministic server configuration (SSOT for server connection)
        server_block = existing.get("server")
        if not isinstance(server_block, dict):
            server_block = {}
        server_block["hostname"] = "127.0.0.1"
        server_block["port"] = effective_opencode_port
        existing["server"] = server_block

        if dry_run:
            print(f"  [DRY-RUN] merge instructions into {target}")
            return {"status": "planned-merge", "dst": str(target)}

        target.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {"status": "merged", "dst": str(target)}

    payload = {
        "instructions": list(OPENCODE_INSTRUCTIONS),
        OPENCODE_PLUGIN_KEY: [plugin_uri],
        "server": {
            "hostname": "127.0.0.1",
            "port": effective_opencode_port,
        },
    }
    if include_legacy_command_files:
        payload["command_files"] = list(OPENCODE_INSTRUCTIONS)
    if dry_run:
        print(f"  [DRY-RUN] create {target}")
        return {"status": "planned-create", "dst": str(target)}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"status": "created", "dst": str(target)}


def remove_installer_plugin_from_opencode_json(config_root: Path, *, dry_run: bool) -> dict:
    target = config_root / OPENCODE_JSON_NAME
    if not target.exists():
        return {"status": "skipped-missing", "dst": str(target)}

    payload = _load_json(target)
    if payload is None:
        return {"status": "skipped-invalid", "dst": str(target)}

    current = payload.get(OPENCODE_PLUGIN_KEY)
    if not isinstance(current, list):
        return {"status": "skipped-no-plugin-array", "dst": str(target)}

    plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()
    kept = [entry for entry in current if str(entry) != plugin_uri]
    if len(kept) == len(current):
        return {"status": "skipped-not-present", "dst": str(target)}

    payload[OPENCODE_PLUGIN_KEY] = kept
    if dry_run:
        print(f"  [DRY-RUN] remove installer plugin entry from {target}")
        return {"status": "planned-remove-plugin", "dst": str(target)}

    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "removed-plugin", "dst": str(target)}


def inject_session_reader_path_for_command(
    commands_dir: Path,
    *,
    command_markdown: str,
    python_command: str | None = None,
    bin_dir: str | None = None,
    dry_run: bool,
) -> dict:
    """Replace placeholders in installed command markdown template.

    Primary mode (bin_dir): Replaces ``{{BIN_DIR}}`` with the concrete
    absolute path to the ``bin/`` directory so the launcher-based rail
    invocation resolves deterministically.

    Legacy mode (python_command): Replaces ``{{PYTHON_COMMAND}}`` and
    ``{{SESSION_READER_PATH}}`` for backwards compatibility with older
    rail templates that have not yet migrated to the launcher pattern.

    Returns a status dict for logging.
    """
    command_md = commands_dir / command_markdown
    if not command_md.exists():
        return {"status": "skipped-missing", "dst": str(command_md)}

    content = command_md.read_text(encoding="utf-8")
    new_content = content

    # --- Primary: BIN_DIR placeholder (launcher-era rails) ---
    has_bin_dir_placeholder = BIN_DIR_PLACEHOLDER in content
    if has_bin_dir_placeholder and bin_dir is not None:
        # Platform-aware rail injection (python-binding-contract.v1.md §4.2):
        # Rails are installed as platform-specific — the installer writes only
        # the block matching the target OS.
        if os.name == "nt" and "```cmd" not in new_content:
            # Windows: keep the bash block intact (OpenCode's LLM tool runner
            # uses bash even on Windows via Git Bash / WSL) and *append* a cmd
            # block immediately after the bash code fence for native Windows
            # terminal invocation.
            #
            # The guard above (``"```cmd" not in new_content``) ensures
            # idempotency — re-running the installer will not duplicate the
            # cmd block.
            def _append_cmd_block(m: re.Match) -> str:
                bash_block = m.group(0)
                bin_path = m.group(1)
                trailing = m.group(2) or ""
                cmd_block = (
                    "```cmd\n"
                    f'set "PATH={bin_path};%PATH%" && opencode-governance-bootstrap.cmd'
                    f"{trailing}\n"
                    "```"
                )
                return f"{bash_block}\n\n{cmd_block}"

            new_content = re.sub(
                r'```bash\n'
                r'PATH="([^"]*?):\$PATH"\s+opencode-governance-bootstrap'
                r'([ \t][^\n]*)?\n'
                r'```',
                _append_cmd_block,
                new_content,
            )
        new_content = new_content.replace(BIN_DIR_PLACEHOLDER, bin_dir)

    # --- Legacy: PYTHON_COMMAND / SESSION_READER_PATH placeholders ---
    has_reader_placeholder = SESSION_READER_PLACEHOLDER in content
    has_python_placeholder = PYTHON_COMMAND_PLACEHOLDER in content

    if (has_reader_placeholder or has_python_placeholder) and python_command is not None:
        reader_path = commands_dir / "governance_runtime" / "entrypoints" / "session_reader.py"
        concrete_path = str(reader_path)

        # Quote the python command if it is a single-token path that contains
        # spaces (e.g. 'C:\Program Files\Python311\python.exe').
        # Multi-token commands like 'py -3' must NOT be quoted as a unit.
        safe_python = python_command
        if " " in safe_python and not (safe_python.startswith('"') and safe_python.endswith('"')):
            # Distinguish a single filesystem path with spaces from a multi-token
            # command.  shlex.split cannot reliably tell these apart because an
            # unquoted space is always a word boundary.  Instead, use a simple
            # heuristic: if the value contains a path separator (/ or \) it is
            # almost certainly a single path, not a multi-arg command.  True
            # multi-token commands like 'py -3' never contain path separators.
            _has_path_sep = ('\\' in safe_python or '/' in safe_python)
            if _has_path_sep:
                safe_python = f'"{safe_python}"'

        if has_reader_placeholder:
            new_content = new_content.replace(SESSION_READER_PLACEHOLDER, concrete_path)
        if has_python_placeholder:
            new_content = new_content.replace(PYTHON_COMMAND_PLACEHOLDER, safe_python)
    elif not has_bin_dir_placeholder and not has_reader_placeholder and not has_python_placeholder:
        # No known placeholders — attempt legacy regex fallback
        if python_command is not None:
            reader_path = commands_dir / "governance_runtime" / "entrypoints" / "session_reader.py"
            concrete_path = str(reader_path)
            safe_python = python_command
            if " " in safe_python and not (safe_python.startswith('"') and safe_python.endswith('"')):
                _has_path_sep = ('\\' in safe_python or '/' in safe_python)
                if _has_path_sep:
                    safe_python = f'"{safe_python}"'

            legacy_pattern = re.compile(
                r"(?m)^(?P<indent>\s*)(?:python(?:3)?|py(?:\s+-3)?)\s+[\"\'][^\"\']*session_reader\.py[\"\']\s*$"
            )
            if legacy_pattern.search(new_content):
                new_content = legacy_pattern.sub(
                    lambda m: f"{m.group('indent')}{safe_python} \"{concrete_path}\"",
                    new_content,
                    count=1,
                )
            else:
                return {"status": "skipped-no-placeholder", "dst": str(command_md)}
        else:
            return {"status": "skipped-no-placeholder", "dst": str(command_md)}

    if new_content == content:
        return {"status": "skipped-no-placeholder", "dst": str(command_md)}

    if dry_run:
        print(f"  [DRY-RUN] inject rail paths into {command_md}")
        return {"status": "planned-inject", "dst": str(command_md)}

    command_md.write_text(new_content, encoding="utf-8")
    return {"status": "injected", "dst": str(command_md)}


def inject_session_reader_path(
    commands_dir: Path,
    *,
    python_command: str,
    bin_dir: str | None = None,
    dry_run: bool,
) -> dict:
    """Backwards-compatible injector for ``continue.md``."""
    return inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="continue.md",
        python_command=python_command,
        bin_dir=bin_dir,
        dry_run=dry_run,
    )


def install(
    plan: InstallPlan,
    dry_run: bool,
    force: bool,
    backup_enabled: bool,
    *,
    opencode_port: int = DEFAULT_OPENCODE_PORT,
    include_legacy_command_files: bool = False,
) -> int:
    ok, missing, unsafe_symlinks = precheck_source(plan.source_dir)
    # Allow dry-run to bypass safety gating for unsafe symlinks to enable planning
    if not ok:
        if dry_run:
            ok = True
            missing = []
            unsafe_symlinks = []
        else:
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
                expected_constraint="Required source files present: VERSION, governance_spec/rulesets/core/rules.yml",
                remediation="Restore missing governance source files and rerun install.",
                action="abort",
                result="failed",
                reason_namespace="installer-internal",
            )
            eprint("❌ Precheck failed: required governance source files are missing.")
            if missing:
                eprint("   Missing files:")
                for m in missing:
                    eprint(f"  - {m}")
            if unsafe_symlinks:
                eprint("   Unsafe source symlinks/reparse-points detected (installer fail-closed):")
                for s in unsafe_symlinks:
                    eprint(f"  - {s}")
            eprint("")
            eprint("Recovery options:")
            eprint("  1. If installing from source: ensure you are in the governance repository directory.")
            eprint("  2. If using a customer bundle: extract it first, then run install.py from the extracted root.")
            eprint("  3. If already installed: run '${PYTHON_COMMAND} install.py --status' to check installation health.")
            eprint("")
            return 2

    print(f"Target config root: {plan.config_root}")
    print("Ensuring directory structure...")
    ensure_dirs(plan.config_root, plan.local_root, dry_run=dry_run)

    # backup root
    backup_root = plan.config_root / ".installer-backups" / now_ts()

    copied_entries: list[dict] = []

    # governance paths bootstrap MUST run before create_launcher() because
    # _write_launcher_wrappers reads governance.paths.json for pythonCommand.
    # Single SSOT writer – see C1 fix.
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

    print("\nCreating local bootstrap launcher...")
    launcher_entries = create_launcher(plan, dry_run=dry_run, force=force, opencode_port=opencode_port)

    # determine governance version from kernel-owned metadata
    # Version may live in root VERSION or governance_runtime/VERSION
    gov_ver = read_governance_version_metadata(plan.source_dir / "VERSION")
    if not gov_ver:
        gov_ver = read_governance_version_metadata(plan.source_dir / "governance_runtime" / "VERSION")

    if not gov_ver:
        safe_log_error(
            reason_key="ERR-INSTALL-GOVERNANCE-VERSION-MISSING",
            message="Governance version not found in VERSION.",
            config_root=plan.config_root,
            phase="installer",
            gate="version-check",
            mode="repo-aware",
            repo_fingerprint=None,
            command="install.py",
            component="installer-version",
            observed_value={"versionPath": str(plan.source_dir / "VERSION")},
            expected_constraint="VERSION contains <semver>",
            remediation="Add semantic version to VERSION and rerun install.",
            action="abort",
            result="failed",
            reason_namespace="installer-internal",
        )
        eprint("❌ Governance version metadata missing in VERSION.")
        eprint("")
        eprint("The file VERSION must contain a semantic version like:")
        eprint("  1.0.0")
        eprint("")
        eprint("Add the version to VERSION and rerun install.")
        return 2

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

    print("\nℹ️  Profiles/addons are installed via local governance_content payload copy.")

    print("\nℹ️  Installer no longer copies docs payload to commands/docs/ (R11 hardening).")

    # copy governance runtime + compatibility packages to local root
    runtime_files = collect_governance_runtime_files(plan.source_dir)
    if runtime_files:
        print("\n📋 Copying governance runtime/compatibility packages to local root ...")
        for rf in runtime_files:
            rel = rf.relative_to(plan.source_dir)
            dst = plan.local_root / rel
            entry = copy_with_optional_backup(
                src=rf,
                dst=dst,
                backup_enabled=backup_enabled,
                backup_root=backup_root,
                dry_run=dry_run,
                overwrite=force,
            )
            entry["rel"] = str(rel.as_posix())
            entry["rel_base"] = "local"
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

    # copy governance content + spec payloads to local root
    local_payload_roots = ["governance_content", "governance_spec"]
    print("\n📋 Copying governance content/spec payloads to local root ...")
    for local_dir_name in local_payload_roots:
        src_root = plan.source_dir / local_dir_name
        if not src_root.exists() or not src_root.is_dir():
            continue
        for lf in sorted(p for p in src_root.rglob("*") if p.is_file()):
            if _is_forbidden_metadata_path(lf, plan.source_dir):
                continue
            if "archived" in lf.parts:
                continue
            rel = lf.relative_to(plan.source_dir)
            dst = plan.local_root / rel
            entry = copy_with_optional_backup(
                src=lf,
                dst=dst,
                backup_enabled=backup_enabled,
                backup_root=backup_root,
                dry_run=dry_run,
                overwrite=force,
            )
            entry["rel"] = str(rel.as_posix())
            entry["rel_base"] = "local"
            copied_entries.append(entry)

    version_src = plan.source_dir / "VERSION"
    if version_src.exists() and version_src.is_file():
        entry = copy_with_optional_backup(
            src=version_src,
            dst=plan.local_root / "VERSION",
            backup_enabled=backup_enabled,
            backup_root=backup_root,
            dry_run=dry_run,
            overwrite=force,
        )
        entry["rel"] = "VERSION"
        entry["rel_base"] = "local"
        copied_entries.append(entry)

    print("\nℹ️  Installer no longer copies scripts/templates payloads to commands/ (R11 hardening).")

    # copy optional OpenCode plugins to global plugins dir
    plugin_files = collect_opencode_plugin_files(plan.source_dir)
    if plugin_files:
        print("\n📋 Copying OpenCode plugins to config/plugins/ ...")
        plugins_dst_root = plan.config_root / OPENCODE_PLUGINS_DIR_NAME
        for pf in plugin_files:
            rel = pf.relative_to(plan.source_dir)
            rel_plugin = rel.relative_to(OPENCODE_PLUGIN_SOURCE_DIR)
            dst = plugins_dst_root / rel_plugin
            entry = copy_with_optional_backup(
                src=pf,
                dst=dst,
                backup_enabled=backup_enabled,
                backup_root=backup_root,
                dry_run=dry_run,
                overwrite=force,
            )
            entry["rel"] = str((Path(OPENCODE_PLUGINS_DIR_NAME) / rel_plugin).as_posix())
            entry["rel_base"] = "config"
            copied_entries.append(entry)
            status = entry["status"]
            if status in ("planned-copy", "copied"):
                print(f"  ✅ {rel} -> {entry['rel']} ({status})")
            elif status == "skipped-exists":
                print(f"  ⏭️  {rel} exists (use --force to overwrite)")
            else:
                print(f"  ⚠️  {rel} missing (skipping)")
    else:
        print("\nℹ️  No OpenCode plugins found under governance_runtime/artifacts/opencode-plugins/ (skipping).")

    # validation (critical installed files)
    print("\n🔍 Validating installation...")
    critical = [
        plan.local_root / "governance_runtime" / "VERSION",
    ]
    missing_critical = [p.name for p in critical if not p.exists() and not dry_run]
    if missing_critical:
        eprint("❌ Installation incomplete; missing critical files:")
        for m in missing_critical:
            eprint(f"  - {m}")
        return 3

    print("\n🧹 Enforcing commands payload hygiene...")
    removed_entries, hygiene_violations = enforce_commands_hygiene(
        commands_dir=plan.commands_dir,
        dry_run=dry_run,
    )
    if removed_entries:
        preview = ", ".join(removed_entries[:6])
        suffix = "" if len(removed_entries) <= 6 else ", ..."
        print(f"  ✅ removed forbidden payload artifacts: {preview}{suffix}")
    if hygiene_violations:
        eprint("❌ Install payload hygiene failed. Forbidden artifacts remain under commands/:")
        for rel in hygiene_violations:
            eprint(f"  - {rel}")
        eprint("Recovery: remove forbidden artifacts and rerun installer.")
        return 3

    local_removed, _ = enforce_local_payload_hygiene(local_root=plan.local_root, dry_run=dry_run)
    if local_removed:
        preview = ", ".join(local_removed[:6])
        suffix = "" if len(local_removed) <= 6 else ", ..."
        print(f"  ✅ removed forbidden local payload artifacts: {preview}{suffix}")

    # --- OpenCode Desktop bridge: opencode.json + session reader path injection ---
    print("\n🔗 Configuring OpenCode Desktop governance bridge...")
    ojs = ensure_opencode_json(
        plan.config_root,
        dry_run=dry_run,
        effective_opencode_port=opencode_port,
        include_legacy_command_files=include_legacy_command_files,
    )
    print(f"  opencode.json: {ojs['status']}")

    binding_python = _resolve_python_executable(
        plan.governance_paths_path,
        fallback=sys.executable,
        strict=False,
    )
    concrete_bin_dir = _path_for_json(plan.config_root / "bin")
    template_injections = {
        "hydrate.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="hydrate.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "continue.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="continue.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "audit-readout.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="audit-readout.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "review.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="review.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "ticket.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="ticket.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "plan.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="plan.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "review-decision.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="review-decision.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "implement.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="implement.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
        "implementation-decision.md": inject_session_reader_path_for_command(
            plan.commands_dir,
            command_markdown="implementation-decision.md",
            bin_dir=concrete_bin_dir,
            python_command=binding_python,
            dry_run=dry_run,
        ),
    }
    print(f"  continue.md rail injection: {template_injections['continue.md']['status']}")
    print(f"  audit-readout.md rail injection: {template_injections['audit-readout.md']['status']}")
    print(f"  review.md rail injection: {template_injections['review.md']['status']}")
    print(f"  ticket.md rail injection: {template_injections['ticket.md']['status']}")
    print(f"  plan.md rail injection: {template_injections['plan.md']['status']}")
    print(f"  review-decision.md rail injection: {template_injections['review-decision.md']['status']}")
    print(f"  implement.md rail injection: {template_injections['implement.md']['status']}")
    print(f"  implementation-decision.md rail injection: {template_injections['implementation-decision.md']['status']}")

    # If session reader path was injected, update the SHA256 in copied_entries
    # so the manifest reflects the post-injection content.
    for injection in template_injections.values():
        if injection["status"] != "injected":
            continue
        injected_path = injection["dst"]
        for entry in copied_entries:
            if entry.get("dst") == injected_path and Path(injected_path).exists():
                entry["sha256"] = sha256_file(Path(injected_path))
                break

    # manifest: store only entries that were actually copied/planned
    installed_files = []
    for e in copied_entries:
        if e["status"] not in ("copied", "planned-copy", "patched", "planned-patch"):
            continue
        rel_base = str(e.get("rel_base") or "commands")
        rel_value = e.get("rel")
        if not rel_value:
            if rel_base == "config":
                base_dir = plan.config_root
            elif rel_base == "local":
                base_dir = plan.local_root
            else:
                base_dir = plan.commands_dir
            if "dst" in e:
                dst_path = Path(e["dst"]).resolve()
                try:
                    rel_value = str(dst_path.relative_to(base_dir.resolve()))
                except ValueError:
                    if dst_path.is_relative_to(plan.config_root.resolve()):
                        rel_base = "config"
                        rel_value = str(dst_path.relative_to(plan.config_root.resolve()))
                    elif dst_path.is_relative_to(plan.local_root.resolve()):
                        rel_base = "local"
                        rel_value = str(dst_path.relative_to(plan.local_root.resolve()))
                    elif dst_path.is_relative_to(plan.commands_dir.resolve()):
                        rel_base = "commands"
                        rel_value = str(dst_path.relative_to(plan.commands_dir.resolve()))
                    else:
                        rel_value = dst_path.name
            else:
                rel_value = None
        installed_files.append(
            {
                "dst": e["dst"],
                "rel": rel_value,
                "rel_base": rel_base,
                "src": e["src"],
                "sha256": e.get("sha256", "unknown"),
                "backup": e.get("backup"),
                "status": e["status"],
            }
        )

    # Add launcher entries to manifest
    for entry in launcher_entries:
        installed_files.append(
            {
                "dst": entry["dst"],
                "rel": entry.get("rel"),
                "rel_base": entry.get("rel_base", "config"),
                "src": entry.get("src", "generated"),
                "sha256": "generated",
                "backup": None,
                "status": entry["status"],
            }
        )

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "installerVersion": VERSION,
        "governanceVersion": gov_ver,
        "installedAt": datetime.now().isoformat(timespec="seconds"),
        "configRoot": _path_for_json(plan.config_root),
        "localRoot": _path_for_json(plan.local_root),
        "commandsDir": _path_for_json(plan.commands_dir),
        "files": installed_files,
    }

    print(f"\n🧾 Writing manifest: {plan.manifest_path.name}")
    write_manifest(plan.manifest_path, manifest, dry_run=dry_run)

    # Emit initial install flow event so logs/ is not empty after install
    _emit_install_flow_event(
        plan.commands_dir,
        event_type="install-complete",
        gov_version=gov_ver,
        installer_version=VERSION,
        dry_run=dry_run,
    )

    print("\n" + "=" * 60)
    if dry_run:
        print("✅ DRY-RUN complete (no changes were made).")
    else:
        print("🎉 Installation complete!")
    print("=" * 60)
    print(f"Commands dir: {plan.commands_dir}")
    print("Next: run the local bootstrap launcher:")
    print(f"  {plan.config_root}/bin/opencode-governance-bootstrap")
    print("Then open OpenCode Desktop in this repository and run /hydrate.")
    return 0


def uninstall(
    plan: InstallPlan,
    dry_run: bool,
    force: bool,
    purge_paths_file: bool,
    keep_error_logs: bool,
    keep_workspace_state: bool,
) -> int:
    print(f"🧹 Uninstall from: {plan.commands_dir}")

    # ── IMPORTANT: opencode.json is NEVER deleted on uninstall ───────────
    # opencode.json is a user/team configuration file that may be shared
    # across team members and checked into version control. It is created or
    # merged during install but intentionally preserved on uninstall so that
    # other users who depend on it are not affected.
    # Neither delete_targets() nor purge_runtime_state() touch this file.

    def collect_known_installer_targets() -> list[Path]:
        targets: list[Path] = []

        # Root command files from current source snapshot
        for src in collect_command_root_files(plan.source_dir):
            targets.append(plan.commands_dir / src.name)

        # Ensure placeholder rules.yml (if any) is also targeted for uninstall
        root_rules = plan.commands_dir / "rules.yml"
        if root_rules.exists():
            targets.append(root_rules)
        root_phase = plan.commands_dir / "phase_api.yaml"
        if root_phase.exists():
            targets.append(root_phase)
        core_rules = plan.commands_dir / "rulesets" / "core" / "rules.yml"
        if core_rules.exists():
            targets.append(core_rules)

        # CLI package (for bootstrap launcher)
        cli_dir = plan.commands_dir / "cli"
        if cli_dir.exists():
            for f in cli_dir.rglob("*"):
                if f.is_file():
                    targets.append(f)

        # Profiles and addon manifests from current source snapshot
        profiles_root = get_profiles_root(plan.source_dir)
        for src in collect_profile_files(plan.source_dir):
            rel = src.relative_to(profiles_root)
            targets.append(plan.commands_dir / "profiles" / rel)
        for src in collect_profile_addon_manifests(plan.source_dir):
            rel = src.relative_to(profiles_root)
            targets.append(plan.commands_dir / "profiles" / rel)

        # Governance runtime + compatibility packages from current source snapshot
        for src in collect_governance_runtime_files(plan.source_dir):
            rel = src.relative_to(plan.source_dir)
            targets.append(plan.local_root / rel)

        # Governance content/spec payloads under local root
        for local_dir_name in ("governance_content", "governance_spec"):
            src_root = plan.source_dir / local_dir_name
            if not src_root.exists() or not src_root.is_dir():
                continue
            for src in src_root.rglob("*"):
                if src.is_file() and not _is_forbidden_metadata_path(src, plan.source_dir):
                    rel = src.relative_to(plan.source_dir)
                    targets.append(plan.local_root / rel)

        src_version = plan.source_dir / "VERSION"
        if src_version.exists():
            targets.append(plan.local_root / "VERSION")

        # Customer docs from current source snapshot
        docs_root = get_governance_docs_root(plan.source_dir)
        for src in collect_customer_docs_files(plan.source_dir):
            rel = src.relative_to(docs_root)
            targets.append(plan.commands_dir / "docs" / rel)

        # Governance documentation from current source snapshot
        for src in collect_governance_docs_files(plan.source_dir):
            rel = src.relative_to(docs_root)
            targets.append(plan.commands_dir / "docs" / rel)

        # Customer scripts and workflow templates from current source snapshot.
        try:
            for src in collect_customer_script_files(plan.source_dir, strict=False):
                rel = src.relative_to(plan.source_dir)
                targets.append(plan.commands_dir / rel)
        except (OSError, json.JSONDecodeError):
            pass

        try:
            templates_root = get_templates_root(plan.source_dir)
            catalog = templates_root / "github-actions" / "template_catalog.json"
            if catalog.exists():
                rel = catalog.relative_to(templates_root)
                targets.append(plan.commands_dir / "templates" / rel)
            for src in collect_workflow_template_files(plan.source_dir, strict=False):
                rel = src.relative_to(templates_root)
                targets.append(plan.commands_dir / "templates" / rel)
        except (OSError, json.JSONDecodeError):
            pass

        # OpenCode plugins copied under config_root/plugins
        for src in collect_opencode_plugin_files(plan.source_dir):
            rel = src.relative_to(plan.source_dir)
            rel_plugin = rel.relative_to(OPENCODE_PLUGIN_SOURCE_DIR)
            targets.append(plan.config_root / OPENCODE_PLUGINS_DIR_NAME / rel_plugin)

        # Launcher scripts in bin/
        bin_dir = plan.config_root / "bin"
        if bin_dir.exists():
            for f in bin_dir.rglob("*"):
                if f.is_file():
                    targets.append(f)

        # Remove governance.paths.json only when explicitly requested.
        if purge_paths_file:
            targets.append(plan.governance_paths_path)

        targets.append(plan.config_root / "INSTALL_HEALTH.json")
        return targets

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

        # Conservative fallback: delete installer-owned files resolvable from source tree.
        targets = collect_known_installer_targets()

        # Deduplicate while preserving order
        targets = list(dict.fromkeys(targets))
        # intentionally NOT deleting opencode.json — it is user/team
        # configuration that must survive uninstall (see docstring above).

        rc = delete_targets(targets, plan, dry_run=dry_run)
        rc = max(rc, purge_tree_contents(plan.commands_dir, dry_run=dry_run))
        rc = max(rc, purge_governance_local_payload(plan.local_root, dry_run=dry_run))
        if not keep_error_logs:
            rc = max(rc, purge_runtime_error_logs(plan.config_root, dry_run=dry_run))
        if not keep_workspace_state:
            rc = max(rc, purge_runtime_state(plan.config_root, dry_run=dry_run))
        opencode_cleanup = remove_installer_plugin_from_opencode_json(plan.config_root, dry_run=dry_run)
        print(f"  opencode.json plugin cleanup: {opencode_cleanup['status']}")
        return rc

    # manifest-based targets
    files = manifest.get("files", [])
    targets: list[Path] = []
    for entry in files:
        rel = entry.get("rel")
        dst = entry.get("dst")
        if rel:
            rel_base = str(entry.get("rel_base") or "commands")
            if rel_base == "commands" and str(rel).startswith("bin/"):
                # Backward compatibility for manifests created before rel_base.
                rel_base = "config"
            if rel_base == "config":
                targets.append(plan.config_root / rel)
            elif rel_base == "local":
                targets.append(plan.local_root / rel)
            else:
                targets.append(plan.commands_dir / rel)
        elif dst:
            targets.append(Path(dst))
            
    if purge_paths_file:
        # Explicit operator request: remove machine-specific binding even if it pre-existed.
        targets.append(plan.governance_paths_path)
    targets.append(plan.config_root / "INSTALL_HEALTH.json")

    # Also include known installer-owned files by source snapshot to cover legacy
    # manifests that are missing entries (e.g., historical skipped-exists paths).
    targets.extend(collect_known_installer_targets())

    # Deduplicate while preserving order.
    targets = list(dict.fromkeys(targets))

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
    rc = max(rc, purge_tree_contents(plan.commands_dir, dry_run=dry_run))
    rc = max(rc, purge_governance_local_payload(plan.local_root, dry_run=dry_run))

    # Manifest-backed uninstall can safely clear stale installer trees that may
    # survive due to historical path drift (for example legacy "governnce/").
    rc = max(rc, purge_manifest_leftover_trees(plan.commands_dir, plan.local_root, dry_run=dry_run))

    if not keep_error_logs:
        rc = max(rc, purge_runtime_error_logs(plan.config_root, dry_run=dry_run))

    if not keep_workspace_state:
        rc = max(rc, purge_runtime_state(plan.config_root, dry_run=dry_run))

    # remove manifest last (if everything went OK-ish)
    if dry_run:
        print(f"  [DRY-RUN] rm {plan.manifest_path}")
    else:
        if plan.manifest_path.exists():
            try:
                plan.manifest_path.unlink()
                print(f"  ✅ Removed manifest: {plan.manifest_path.name}")
            except OSError as e:
                eprint(f"  ⚠️  Could not remove manifest: {e}")

    # cleanup empty dirs (leaf -> parent)
    cleanup_dirs = [
        plan.commands_dir / "profiles" / "addons",
        plan.commands_dir / "profiles",
        plan.commands_dir / "rulesets" / "core",
        plan.commands_dir / "rulesets",
        plan.commands_dir / "templates" / "github-actions",
        plan.commands_dir / "templates",
        plan.commands_dir / "scripts",
        plan.commands_dir / "governance",
        plan.commands_dir / "cli",
        plan.commands_dir / "docs",
        plan.commands_dir / "_backup",
        plan.local_root / "governance_runtime",
        plan.local_root / "governance_content",
        plan.local_root / "governance_spec",
        plan.local_root / "governance",
        plan.local_root,
        plan.config_root / "bin",
        plan.config_root / "workspaces",
        plan.config_root / OPENCODE_PLUGINS_DIR_NAME,
        plan.config_root / ".installer-backups",
        plan.config_root / "logs",
    ]
    for d in cleanup_dirs:
        try_remove_empty_dir(d, dry_run=dry_run)

    # Cleanup any placeholder created during uninstall (e.g., rules.yml) across the commands tree
    try:
        for f in (plan.commands_dir).rglob("rules.yml"):
            if f.is_file():
                f.unlink()
                print(f"  🧹 Removed placeholder: {f}")
    except OSError:
        pass

    opencode_cleanup = remove_installer_plugin_from_opencode_json(plan.config_root, dry_run=dry_run)
    print(f"  opencode.json plugin cleanup: {opencode_cleanup['status']}")

    print("\n✅ Uninstall complete.")
    return rc


def purge_manifest_leftover_trees(commands_dir: Path, local_root: Path, dry_run: bool) -> int:
    """Remove stale files under installer-owned trees after manifest uninstall."""

    errors = 0
    legacy_trees = [
        commands_dir / "docs",
        commands_dir / "governance",
        commands_dir / "governnce",
        local_root / "governance",
        local_root / "governnce",
    ]

    for root in legacy_trees:
        if not root.exists() or not root.is_dir():
            continue

        for item in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if item.is_file() or item.is_symlink():
                if dry_run:
                    print(f"  [DRY-RUN] rm {item}")
                else:
                    try:
                        item.unlink()
                        print(f"  ✅ Removed stale file: {item}")
                    except OSError as e:
                        eprint(f"  ❌ Failed removing stale file {item}: {e}")
                        errors += 1
            elif item.is_dir():
                try_remove_empty_dir(item, dry_run=dry_run)

        try_remove_empty_dir(root, dry_run=dry_run)

    return 0 if errors == 0 else 8


def purge_tree_contents(root: Path, dry_run: bool) -> int:
    """Remove all files/symlinks under a root and prune empty directories."""

    if not root.exists() or not root.is_dir():
        return 0

    errors = 0
    for item in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if item.is_symlink() or item.is_file():
            if dry_run:
                print(f"  [DRY-RUN] rm {item}")
            else:
                try:
                    item.unlink()
                    print(f"  ✅ Removed residual: {item}")
                except OSError as e:
                    eprint(f"  ❌ Failed removing residual file {item}: {e}")
                    errors += 1
        elif item.is_dir():
            try_remove_empty_dir(item, dry_run=dry_run)

    try_remove_empty_dir(root, dry_run=dry_run)
    return 0 if errors == 0 else 9


FORBIDDEN_LOCAL_ROOT_DIRS = {"opencode"}


def purge_governance_local_payload(local_root: Path, dry_run: bool) -> int:
    """Remove only governance-owned payloads from local_root.

    ONLY the following are deleted:
    - governance_content/ directory
    - governance_spec/ directory
    - governance_runtime/ directory
    - VERSION file

    The 'opencode' directory and any other unknown top-level items are
    STRICTLY PRESERVED to prevent accidental data loss.

    This is the ONLY safe way to clean local_root during uninstall.
    """
    if not local_root.exists() or not local_root.is_dir():
        return 0

    errors = 0

    allowed_local_payloads = {"governance_content", "governance_spec", "governance_runtime"}

    for item in sorted(local_root.iterdir(), key=lambda p: p.name):
        if item.name in FORBIDDEN_LOCAL_ROOT_DIRS:
            print(f"  🛡️  PRESERVED (forbidden): {item.name}/")
            continue

        if item.is_symlink():
            if dry_run:
                print(f"  [DRY-RUN] rm {item}")
            else:
                try:
                    item.unlink()
                    print(f"  ✅ Removed symlink: {item.name}")
                except OSError as e:
                    eprint(f"  ❌ Failed removing symlink {item.name}: {e}")
                    errors += 1
            continue

        if not item.is_dir() and item.name == "VERSION":
            if dry_run:
                print(f"  [DRY-RUN] rm {item}")
            else:
                try:
                    item.unlink()
                    print(f"  ✅ Removed: {item.name}")
                except OSError as e:
                    eprint(f"  ❌ Failed removing {item.name}: {e}")
                    errors += 1
            continue

        if item.name not in allowed_local_payloads:
            print(f"  🛡️  PRESERVED (unknown): {item.name}/")
            continue

        if item.name == "VERSION":
            continue

        for subitem in sorted(item.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if subitem.is_symlink() or subitem.is_file():
                if dry_run:
                    print(f"  [DRY-RUN] rm {subitem}")
                else:
                    try:
                        subitem.unlink()
                        print(f"  ✅ Removed: {subitem.relative_to(local_root)}")
                    except OSError as e:
                        eprint(f"  ❌ Failed removing {subitem.relative_to(local_root)}: {e}")
                        errors += 1
            elif subitem.is_dir():
                try_remove_empty_dir(subitem, dry_run=dry_run)

        try_remove_empty_dir(item, dry_run=dry_run)

    return 0 if errors == 0 else 9


def delete_targets(targets: Iterable[Path], plan: InstallPlan, dry_run: bool) -> int:
    errors = 0
    allowed_config_files = {
        (plan.config_root / "INSTALL_HEALTH.json").resolve(),
        plan.governance_paths_path.resolve(),
        plan.manifest_path.resolve(),
    }
    for t in targets:
        # Safety guard: only delete installer-owned locations.
        try:
            t_resolved = t.resolve()
            commands_resolved = plan.commands_dir.resolve()
            bin_resolved = (plan.config_root / "bin").resolve()
            plugins_resolved = (plan.config_root / OPENCODE_PLUGINS_DIR_NAME).resolve()
            local_resolved = plan.local_root.resolve()
            
            # Allow deletion in commands_dir, config_root/bin, config_root/plugins, local_root,
            # or explicit installer-owned config files.
            allowed_bases = [commands_resolved, bin_resolved, plugins_resolved, local_resolved]
            is_under_allowed = any(
                base_resolved in t_resolved.parents or t_resolved == base_resolved
                for base_resolved in allowed_bases
            )
            if t_resolved in allowed_config_files:
                is_under_allowed = True
            
            if not is_under_allowed:
                safe_log_error(
                    reason_key="ERR-UNINSTALL-PATH-ESCAPE-REFUSED",
                    message="Refused deletion outside installer-owned directories/files.",
                    config_root=plan.config_root,
                    phase="installer",
                    gate="uninstall-safety",
                    mode="repo-aware",
                    repo_fingerprint=None,
                    command="install.py",
                    component="installer-delete-guard",
                    observed_value={"target": str(t), "resolvedTarget": str(t_resolved)},
                    expected_constraint=(
                        f"Target must be under {commands_resolved}, {bin_resolved}, {plugins_resolved}, {local_resolved}, "
                        f"or in explicit installer-owned config files"
                    ),
                    remediation="Inspect manifest/targets and rerun uninstall.",
                    action="block",
                    result="blocked",
                    reason_namespace="installer-internal",
                )
                eprint(f"  ❌ Refusing to delete outside allowed dirs: {t}")
                errors += 1
                continue
        except OSError:
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
            except (OSError, ValueError) as e:
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
    Remove installer/runtime-owned error log files under workspace log roots:
      - <config_root>/workspaces/*/logs/error.log.jsonl
      - <config_root>/workspaces/*/logs/flow.log.jsonl
      - <config_root>/workspaces/*/logs/boot.log.jsonl
      - legacy: <config_root>/logs/errors-*.jsonl
      - legacy: <config_root>/logs/errors-index.json
      - legacy: <config_root>/workspaces/*/logs/errors-*.jsonl
      - legacy: <config_root>/workspaces/*/logs/errors-index.json

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
                *list((config_root / "commands" / ERROR_LOGS_DIR_NAME).glob("error.log.jsonl")),
                *list((config_root / "commands" / ERROR_LOGS_DIR_NAME).glob("flow.log.jsonl")),
                *list((config_root / "commands" / ERROR_LOGS_DIR_NAME).glob("boot.log.jsonl")),
                *list((config_root / "workspaces").glob("*/logs/errors-*.jsonl")),
                *list((config_root / "workspaces").glob("*/logs/errors-index.json")),
                *list((config_root / "workspaces").glob("*/logs/error.log.jsonl")),
                *list((config_root / "workspaces").glob("*/logs/flow.log.jsonl")),
                *list((config_root / "workspaces").glob("*/logs/boot.log.jsonl")),
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
            except (OSError, ValueError) as e:
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
    try_remove_empty_dir(config_root / "commands" / ERROR_LOGS_DIR_NAME, dry_run=dry_run)
    for repo_logs in (config_root / "workspaces").glob("*/logs"):
        try_remove_empty_dir(repo_logs, dry_run=dry_run)

    return 0 if errors == 0 else 6


def purge_runtime_state(config_root: Path, dry_run: bool) -> int:
    """
    Remove governance runtime state files created during bootstrap/persistence:
      - <config_root>/governance.activation_intent.json
      - <config_root>/SESSION_STATE.json (global active pointer)
      - <config_root>/workspaces/*/SESSION_STATE.json
      - <config_root>/workspaces/*/repo-identity-map.yaml
      - <config_root>/workspaces/*/repo-cache.yaml
      - <config_root>/workspaces/*/repo-map-digest.md
      - <config_root>/workspaces/*/workspace-memory.yaml
      - <config_root>/workspaces/*/decision-pack.md
      - <config_root>/workspaces/*/business-rules.md
      - <config_root>/workspaces/*/business-rules-status.md
      - <config_root>/workspaces/*/plan-record.json
      - <config_root>/workspaces/*/plan-record-archive/ (directory tree)
      - <config_root>/workspaces/*/evidence/ (directory tree)
      - <config_root>/workspaces/*/.lock/ (directory tree)

    Safety:
      - Only known governance artifact patterns are removed.
      - Non-matching user files are preserved.
      - opencode.json is NEVER removed — it is user configuration shared across
        team members and must survive uninstall/reinstall cycles.
      - Empty workspace directories are cleaned up after purge.
    """
    print("\n🧾 Purging runtime workspace state ...")

    errors = 0

    # ── Safety: opencode.json must NEVER be deleted ──────────────────────
    # opencode.json is user/team configuration (checked into repos, shared
    # across team members). It is NOT a runtime artifact. Verify at runtime
    # that it cannot accidentally appear in any removal list maintained here.
    if OPENCODE_JSON_NAME in {
        "governance.activation_intent.json",
        "SESSION_STATE.json",
    }:
        raise RuntimeError(
            f"CRITICAL: {OPENCODE_JSON_NAME} must never be a config-root purge target"
        )

    # 1. activation_intent.json at config root level
    activation_intent = config_root / "governance.activation_intent.json"
    if activation_intent.exists():
        if dry_run:
            print(f"  [DRY-RUN] rm {activation_intent}")
        else:
            try:
                activation_intent.unlink()
                print(f"  ✅ Removed: {activation_intent.name}")
            except (OSError, ValueError) as e:
                eprint(f"  ❌ Failed removing {activation_intent}: {e}")
                errors += 1

    # 2. Global SESSION_STATE pointer at config root level
    global_pointer = config_root / "SESSION_STATE.json"
    if global_pointer.exists():
        if dry_run:
            print(f"  [DRY-RUN] rm {global_pointer}")
        else:
            try:
                global_pointer.unlink()
                print(f"  ✅ Removed: {global_pointer.name}")
            except (OSError, ValueError) as e:
                eprint(f"  ❌ Failed removing {global_pointer}: {e}")
                errors += 1

    # 3. Per-workspace artifacts
    workspaces = config_root / "workspaces"
    if not workspaces.exists():
        print("  ℹ️  No workspaces directory found.")
        return 0 if errors == 0 else 7

    # Known workspace artifact file patterns (flat files inside workspace dirs)
    workspace_artifact_names = [
        "SESSION_STATE.json",
        "repo-identity-map.yaml",
        "repo-cache.yaml",
        "repo-map-digest.md",
        "workspace-memory.yaml",
        "decision-pack.md",
        "business-rules.md",
        "business-rules-status.md",
        "plan-record.json",
    ]

    if OPENCODE_JSON_NAME in workspace_artifact_names:
        raise RuntimeError(
            f"CRITICAL: {OPENCODE_JSON_NAME} must never appear in workspace_artifact_names"
        )

    # Known workspace subdirectories to remove as trees
    workspace_subtree_names = [
        "plan-record-archive",
        "evidence",
        ".lock",
    ]

    touched_workspace_dirs: set[Path] = set()
    for ws_dir in workspaces.iterdir():
        if not ws_dir.is_dir():
            continue
        touched_workspace_dirs.add(ws_dir)

        # Remove known flat artifact files
        for name in workspace_artifact_names:
            artifact = ws_dir / name
            if artifact.exists() and artifact.is_file():
                if dry_run:
                    print(f"  [DRY-RUN] rm {artifact}")
                else:
                    try:
                        artifact.unlink()
                        print(f"  ✅ Removed: {ws_dir.name}/{name}")
                    except OSError as e:
                        eprint(f"  ❌ Failed removing {artifact}: {e}")
                        errors += 1

        # Remove known subdirectory trees
        for subtree_name in workspace_subtree_names:
            subtree = ws_dir / subtree_name
            if subtree.exists() and subtree.is_dir():
                if subtree.is_symlink():
                    eprint(f"  ⚠️  Skipping symlink: {ws_dir.name}/{subtree_name}/ (C3 safety guard)")
                    continue
                if dry_run:
                    print(f"  [DRY-RUN] rmtree {subtree}")
                else:
                    try:
                        shutil.rmtree(subtree)
                        print(f"  ✅ Removed tree: {ws_dir.name}/{subtree_name}/")
                    except OSError as e:
                        eprint(f"  ❌ Failed removing tree {subtree}: {e}")
                        errors += 1

    # 4. Remove empty workspace dirs (leaf -> parent)
    for ws_dir in sorted(touched_workspace_dirs, key=lambda p: len(p.parts), reverse=True):
        try_remove_empty_dir(ws_dir, dry_run=dry_run)

    # Try removing the workspaces dir itself if now empty
    try_remove_empty_dir(workspaces, dry_run=dry_run)

    return 0 if errors == 0 else 7


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
    except (OSError, ValueError):
        return


def _detect_root_drift(primary_root: Path) -> tuple[list[Path], list[Path]]:
    """Return (known_roots, installed_roots)."""
    known_roots = resolve_known_config_roots(primary_root)
    installed_roots = [root for root in known_roots if has_installation(root)]
    return known_roots, installed_roots


def show_doctor(_source_dir: Path, config_root_arg: Path | None) -> int:
    """Run root-drift diagnostics and print concrete recovery commands."""
    print("=" * 60)
    print("LLM Governance System Doctor")
    print("=" * 60)

    config_root = config_root_arg if config_root_arg is not None else get_config_root()
    known_roots, installed_roots = _detect_root_drift(config_root)

    print(f"Primary config root: {config_root}")
    print("Known config roots:")
    for root in known_roots:
        marker = "installed" if root in installed_roots else "not-installed"
        print(f"  - {root} [{marker}]")

    issues: list[str] = []
    if not installed_roots:
        issues.append("no-installation")
    if len(installed_roots) > 1:
        issues.append("multiple-installed-roots")
    if installed_roots and config_root not in installed_roots:
        issues.append("primary-root-not-installed")

    local_root = get_local_root()
    for fname in sorted(FORBIDDEN_METADATA_FILENAMES):
        metadata_file = local_root / fname
        if metadata_file.exists():
            issues.append(f"harmless-local-metadata:{fname}")

    print("\nDiagnosis:")
    if not issues:
        print("  ✅ No drift detected.")
    else:
        for issue in issues:
            print(f"  ⚠️  {issue}")

    py = _path_for_json(Path(sys.executable))
    print("\nRecovery commands:")
    print(f"  - rm -f \"{_path_for_json(local_root / '.DS_Store')}\"")
    print(
        "  - "
        f"\"{py}\" install.py --force --config-root \"{_path_for_json(config_root)}\" "
        f"--local-root \"{_path_for_json(local_root)}\""
    )
    print("\n" + "=" * 60)
    return 0 if not issues else 1


def show_status(source_dir: Path, config_root_arg: Path | None) -> int:
    """Show installation status (read-only). Returns 0 on success, non-zero on errors."""

    print("=" * 60)
    print("LLM Governance System Status")
    print("=" * 60)

    # Resolve config root
    try:
        config_root = config_root_arg if config_root_arg is not None else get_config_root()
    except (OSError, ValueError) as e:
        print(f"❌ Failed to resolve config root: {e}")
        return 1

    print(f"Config Root: {config_root}")
    print(f"Commands Home: {config_root / 'commands'}")

    known_roots, installed_roots = _detect_root_drift(config_root)
    if len(known_roots) > 1:
        print("Known Roots:")
        for root in known_roots:
            marker = "installed" if root in installed_roots else "not-installed"
            print(f"  - {root} [{marker}]")
    if len(installed_roots) > 1:
        print("⚠️  Root drift detected: multiple config roots have installations.")
    elif installed_roots and config_root not in installed_roots:
        print("⚠️  Selected config root has no install; another known root is installed.")

    # Check if installed
    commands_home = config_root / "commands"
    if not commands_home.exists():
        print("\n⚠️  No installation found at this config root.")
        print("Run '${PYTHON_COMMAND} install.py' to install.")
        return 1

    # Read manifest if present
    manifest_path = config_root / MANIFEST_NAME
    manifest = load_manifest(manifest_path)

    if manifest:
        print(f"\n✅ Installation detected (manifest: {manifest_path.name})")
        gov_ver = manifest.get("governance_version", "unknown")
        print(f"Governance Version: {gov_ver}")
        installed_at = manifest.get("installed_at", "unknown")
        print(f"Installed At: {installed_at}")
        files_count = len(manifest.get("files", []))
        print(f"Installed Files: {files_count}")
    else:
        print("\n⚠️  Installation found but manifest missing (fallback mode).")
        print("Run '${PYTHON_COMMAND} install.py --force' to restore manifest.")

    # Check governance version metadata from source if available
    source_version = source_dir / "governance_runtime" / "VERSION"
    if source_version.exists():
        src_ver = read_governance_version_metadata(source_version)
        if src_ver:
            print(f"\nSource Governance Version: {src_ver}")
            if manifest and manifest.get("governance_version") != src_ver:
                print("⚠️  Source version differs from installed version.")

    # Check for binding file
    paths_file = config_root / GOVERNANCE_PATHS_NAME
    if paths_file.exists():
        print(f"\n✅ Governance paths file: {paths_file.name}")
    else:
        print(f"\n⚠️  Governance paths file missing: {paths_file.name}")

    # List command-surface files
    print("\nCommands Surface:")
    command_files = sorted(p.name for p in commands_home.glob("*") if p.is_file())
    print(f"  - files: {len(command_files)}")
    for name in command_files:
        print(f"    - {name}")

    print("\n" + "=" * 60)
    return 0


def show_health(source_dir: Path, config_root_arg: Path | None) -> int:
    """Run read-only health probes and show compact status. Returns 0 on all green, non-zero if issues found."""

    print("=" * 60)
    print("LLM Governance System Health")
    print("=" * 60)

    issues_found = []

    # Probe 1: Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"\n🐍 Python: {py_ver}")
    if sys.version_info < (3, 10):
        print("   ⚠️  Python 3.10+ recommended")
        issues_found.append("python-version")

    # Probe 2: Git availability (probe only, non-destructive)
    git_available = shutil.which("git") is not None
    git_status = "✅" if git_available else "⚠️"
    print(f"\n{git_status} Git: {'available' if git_available else 'not in PATH'}")
    if not git_available:
        issues_found.append("git-not-available")

    # Probe 3: Config root resolution
    try:
        config_root = config_root_arg if config_root_arg is not None else get_config_root()
        print(f"\n✅ Config root: {config_root}")
    except (OSError, ValueError) as e:
        print(f"\n❌ Config root: failed to resolve ({e})")
        issues_found.append("config-root-resolution")
        return 1

    known_roots, installed_roots = _detect_root_drift(config_root)
    if len(known_roots) > 1:
        print("\n📍 Known roots:")
        for root in known_roots:
            marker = "installed" if root in installed_roots else "not-installed"
            print(f"   - {root} [{marker}]")
    if len(installed_roots) > 1:
        print("   ⚠️  root drift: multiple known roots have active installations")
        issues_found.append("root-drift-multiple")

    # Probe 4: Write permissions per scope
    print("\n📁 Write permissions:")
    perms_ok = True
    for scope, path in [
        ("config_root", config_root),
        ("commands", config_root / "commands"),
        ("workspaces", config_root / "workspaces"),
    ]:
        writable = os.access(path, os.W_OK) if path.exists() else False
        icon = "✅" if writable else "❌"
        status = "writable" if writable else "NOT WRITABLE"
        print(f"   {icon} {scope}: {status}")
        if not writable:
            perms_ok = False
            issues_found.append(f"perm-{scope}")

    if not perms_ok:
        print("   ⚠️  Some scopes not writable (install may fail)")

    # Probe 5: Source directory accessibility (YAML rulebooks preferred, MD optional)
    source_rules = _source_core_rules_yml(source_dir)
    source_readable = source_rules.exists() and os.access(source_rules, os.R_OK)
    icon = "✅" if source_readable else "⚠️"
    print(f"\n{icon} Source rulesets/core/rules.yml: {'readable' if source_readable else 'not accessible (optional fallback to MD)'}")
    if not source_readable:
        # Fallback: check for legacy MD
        source_master = _source_master_md(source_dir)
        if source_master.exists() and os.access(source_master, os.R_OK):
            print(f"   ↳ Fallback: master.md accessible")
            source_readable = True
    if not source_readable:
        issues_found.append("source-not-accessible")

    # Probe 6: Installation health (if exists)
    commands_home = config_root / "commands"
    if commands_home.exists():
        manifest_path = config_root / MANIFEST_NAME
        manifest_exists = manifest_path.exists()
        manifest_icon = "✅" if manifest_exists else "⚠️"
        print(f"\n{manifest_icon} Manifest: {'present' if manifest_exists else 'missing (fallback mode)'}")
        if not manifest_exists:
            issues_found.append("manifest-missing")

        # Check key files
        key_files = list(CANONICAL_RAIL_FILENAMES)
        key_ok = True
        for kf in key_files:
            kf_path = commands_home / kf
            exists = kf_path.exists()
            icon = "✅" if exists else "❌"
            print(f"   {icon} {kf}: {'present' if exists else 'MISSING'}")
            if not exists:
                key_ok = False
                issues_found.append(f"key-file-missing-{kf}")
        if not key_ok:
            print("   ⚠️  Core governance files missing")

        # Check governance.paths.json
        paths_file = config_root / GOVERNANCE_PATHS_NAME
        paths_exists = paths_file.exists()
        paths_icon = "✅" if paths_exists else "⚠️"
        print(f"   {paths_icon} governance.paths.json: {'present' if paths_exists else 'missing'}")
        if not paths_exists:
            issues_found.append("paths-json-missing")

        manifest_exists = (config_root / MANIFEST_NAME).exists()
        manifest_icon = "✅" if manifest_exists else "❌"
        print(f"   {manifest_icon} {MANIFEST_NAME}: {'present' if manifest_exists else 'missing'}")
        if not manifest_exists:
            issues_found.append("manifest-file-missing")

        allowed = set(CANONICAL_RAIL_FILENAMES)
        extras = sorted(
            p.name for p in commands_home.glob("*") if p.is_file() and p.name not in allowed
        )
        md_files = sorted(p.name for p in commands_home.glob("*.md") if p.is_file())
        if extras:
            print(f"   ❌ commands/ contains non-allowlisted files: {extras}")
            issues_found.append("commands-allowlist-extra")
        if md_files != sorted(CANONICAL_RAIL_FILENAMES):
            print(f"   ❌ commands rail set mismatch: {md_files}")
            issues_found.append("commands-rail-set-mismatch")

        # Check local bootstrap launcher
        bin_dir = config_root / "bin"
        launcher_unix = bin_dir / "opencode-governance-bootstrap"
        launcher_win = bin_dir / "opencode-governance-bootstrap.cmd"
        launcher_exists = launcher_unix.exists() or launcher_win.exists()
        launcher_icon = "✅" if launcher_exists else "⚠️"
        print(f"   {launcher_icon} Local bootstrap launcher: {'present' if launcher_exists else 'missing'}")
        if not launcher_exists:
            issues_found.append("launcher-missing")

        # Check launcher can execute against installed runtime.
        launcher = launcher_unix if launcher_unix.exists() else launcher_win
        if launcher.exists():
            test_env = os.environ.copy()
            test_env["OPENCODE_CONFIG_ROOT"] = str(config_root)
            if os.name == "nt" and launcher_win.exists():
                cmd = ["cmd", "/c", str(launcher), "--help"]
            else:
                cmd = [str(launcher), "--help"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=test_env,
                cwd=str(config_root),
            )
            if result.returncode == 0:
                print("   ✅ launcher runtime: healthy")
            else:
                print("   ⚠️  launcher runtime: failed")
                issues_found.append("launcher-runtime-failed")
    else:
        print("\n⚠️  No installation found at config root")
        print("   Run '${PYTHON_COMMAND} install.py' to install")
        issues_found.append("no-installation")

    # Summary
    print("\n" + "=" * 60)
    if not issues_found:
        print("✅ All health checks passed")
        return 0
    else:
        print("⚠️  Health issues detected")
        print("\nOne command per issue:")
        if "python-version" in issues_found:
            print("   - Install Python 3.10+")
        if "git-not-available" in issues_found:
            print("   - Install git or add to PATH")
        if "perm-" in "".join(issues_found):
            print("   - Check directory permissions")
        if "no-installation" in issues_found:
            print("   - Run: ${PYTHON_COMMAND} install.py")
        if (
            "manifest-missing" in issues_found
            or "manifest-file-missing" in issues_found
            or "commands-allowlist-extra" in issues_found
            or "commands-rail-set-mismatch" in issues_found
            or any(i.startswith("key-file-") for i in issues_found)
        ):
            print("   - Run: ${PYTHON_COMMAND} install.py --force")
        if "launcher-missing" in issues_found:
            print("   - Run: ${PYTHON_COMMAND} install.py --force")
        if "launcher-runtime-failed" in issues_found:
            print("   - Reinstall and run smoketest to verify launcher runtime")
        return 1


def run_smoketest(config_root: Path) -> int:
    """Run installation smoketest. Returns 0 if healthy, non-zero if issues."""
    print("=" * 60)
    print("LLM Governance System Smoketest")
    print("=" * 60)

    issues = []

    # Check launcher exists
    bin_dir = config_root / "bin"
    launcher_unix = bin_dir / "opencode-governance-bootstrap"
    launcher_win = bin_dir / "opencode-governance-bootstrap.cmd"

    if not launcher_unix.exists() and not launcher_win.exists():
        print("❌ Local bootstrap launcher missing")
        issues.append("launcher-missing")
    else:
        print("✅ Local bootstrap launcher present")

    # Check governance.paths.json
    paths_json = config_root / GOVERNANCE_PATHS_NAME
    if not paths_json.exists():
        print("❌ governance.paths.json missing")
        issues.append("paths-json-missing")
    else:
        print("✅ governance.paths.json present")

    manifest_json = config_root / MANIFEST_NAME
    if not manifest_json.exists():
        print(f"❌ {MANIFEST_NAME} missing")
        issues.append("manifest-missing")
    else:
        print(f"✅ {MANIFEST_NAME} present")

    commands_home = config_root / "commands"
    allowed = set(CANONICAL_RAIL_FILENAMES)
    extras = sorted(p.name for p in commands_home.glob("*") if p.is_file() and p.name not in allowed)
    rails = sorted(p.name for p in commands_home.glob("*.md") if p.is_file())
    if extras:
        print(f"❌ commands/ contains non-allowlisted files: {extras}")
        issues.append("commands-allowlist-extra")
    else:
        print("✅ commands/ file allowlist clean")
    if rails != sorted(CANONICAL_RAIL_FILENAMES):
        print(f"❌ commands rail set mismatch: {rails}")
        issues.append("commands-rail-set-mismatch")
    else:
        print("✅ commands rail set exact (8)")

    # Check launcher execution against installed runtime (not source checkout).
    launcher = launcher_unix if launcher_unix.exists() else launcher_win
    if launcher.exists():
        test_env = os.environ.copy()
        test_env["OPENCODE_CONFIG_ROOT"] = str(config_root)
        if os.name == "nt" and launcher_win.exists():
            cmd = ["cmd", "/c", str(launcher), "--help"]
        else:
            cmd = [str(launcher), "--help"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=test_env,
            cwd=str(config_root),
        )
        if result.returncode == 0:
            print("✅ launcher executes with installed runtime")
        else:
            print("❌ launcher failed in installed runtime")
            if result.stderr.strip():
                print(f"   Error: {result.stderr.strip()}")
            issues.append("launcher-runtime-failed")

    # Check interpreter
    print(f"✅ Interpreter: {sys.executable}")

    print("\n" + "=" * 60)
    if issues:
        print("⚠️  Smoketest issues found")
        return 1
    print("✅ Smoketest passed")
    return 0


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
    p.add_argument(
        "--local-root",
        type=Path,
        default=None,
        help="Override local payload root (default: ~/.local/share/opencode).",
    )
    p.add_argument(
        "--opencode-port",
        default=None,
        help="OpenCode Desktop server port (priority: CLI > OPENCODE_PORT > 4096).",
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing anything.")
    p.add_argument("--force", action="store_true", help="Overwrite without prompting / uninstall without prompt.")
    p.add_argument("--no-backup", action="store_true", help="Disable backup on overwrite (install only).")
    p.add_argument("--uninstall", action="store_true", help="Uninstall previously installed governance files (manifest-based).")
    p.add_argument("--skip-paths-file", action="store_true", help="Do not create/overwrite governance.paths.json in config root.")
    p.add_argument(
        "--deterministic-paths-file",
        action="store_true",
        help="Write deterministic governance.paths.json payload (omit generatedAt timestamp).",
    )
    p.add_argument("--purge-paths-file", action="store_true", help="On uninstall: also remove config-root governance.paths.json even if it pre-existed or the manifest is missing.")
    p.add_argument(
        "--keep-error-logs",
        action="store_true",
        help="On uninstall: preserve runtime error logs under <config_root>/workspaces/*/logs (legacy <config_root>/logs paths may still exist).",
    )
    p.add_argument(
        "--keep-workspace-state",
        action="store_true",
        help="On uninstall: preserve workspace state (SESSION_STATE.json, governance.activation_intent.json, workspace artifacts, and the global SESSION_STATE pointer).",
    )
    p.add_argument("--version", action="store_true", help="Show installer and governance version, then exit.")
    p.add_argument("--status", action="store_true", help="Show installation status (read-only), then exit.")
    p.add_argument("--doctor", action="store_true", help="Diagnose root drift and print concrete recovery commands.")
    p.add_argument("--health", action="store_true", help="Run read-only health probes and show compact status, then exit.")
    p.add_argument("--smoketest", action="store_true", help="Run installation smoketest (checks launcher, paths.json, installed runtime execution).")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    # R2 fix: resolve --config-root to absolute path early, before any
    # downstream code consumes it. Relative paths from CLI would otherwise
    # produce inconsistent governance.paths.json entries.
    if args.config_root is not None:
        args.config_root = args.config_root.resolve()
    if args.local_root is not None:
        args.local_root = args.local_root.resolve()

    # --version: show version and exit (read-only)
    if args.version:
        print(f"Installer Version: {VERSION}")
        # Try to read governance version metadata from source
        source_version = args.source_dir / "governance_runtime" / "VERSION"
        if source_version.exists():
            gov_ver = read_governance_version_metadata(source_version)
            if gov_ver:
                print(f"Governance Version: {gov_ver}")
        return 0

    # --status: show installation status and exit (read-only)
    if args.status:
        return show_status(args.source_dir, args.config_root)

    # --doctor: root-drift diagnosis and concrete recovery commands
    if args.doctor:
        return show_doctor(args.source_dir, args.config_root)

    # --health: run read-only health probes and exit
    if args.health:
        return show_health(args.source_dir, args.config_root)

    # --smoketest: run installation smoketest
    if args.smoketest:
        config_root = args.config_root if args.config_root is not None else get_config_root()
        return run_smoketest(config_root)

    config_root = args.config_root if args.config_root is not None else get_config_root()
    local_root = args.local_root if args.local_root is not None else get_local_root()
    try:
        effective_opencode_port = resolve_effective_opencode_port(cli_opencode_port=args.opencode_port)
    except ValueError as exc:
        eprint(f"❌ Invalid OpenCode port: {exc}")
        return 2
    os.environ["OPENCODE_PORT"] = str(effective_opencode_port)

    plan = build_plan(
        args.source_dir,
        config_root,
        local_root,
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
            keep_workspace_state=args.keep_workspace_state,
        )

    # install flow
    print(f"Source dir:  {plan.source_dir}")
    print(f"Config root: {plan.config_root}")
    print(f"Local root:  {plan.local_root}")
    print(f"OpenCode port: {effective_opencode_port}")

    # prompt only if interactive and not forced and not dry-run
    if not args.force and not args.dry_run and is_interactive():
        resp = input(f"\nInstall to {plan.config_root}? [Y/n] ").strip().lower()
        if resp in ("n", "no"):
            print("Installation cancelled.")
            return 0

    backup_enabled = not args.no_backup
    return install(
        plan,
        dry_run=args.dry_run,
        force=args.force,
        backup_enabled=backup_enabled,
        opencode_port=effective_opencode_port,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
