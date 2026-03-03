#!/usr/bin/env python3
"""Persist workspace artifacts for repository discovery phases.

This module creates and maintains the Phase 2+ artifacts in a repository's
workspace directory. These artifacts capture the results of repository
discovery and analysis.

Artifacts Created:
    - repo-cache.yaml: Repository profile, detected conventions, build info
    - repo-map-digest.md: Architecture summary, modules, entry points
    - decision-pack.md: Decision records from discovery
    - workspace-memory.yaml: Persistent memory for patterns and decisions
    - business-rules.md: Business rules inventory (if Phase 1.5 completed)

Fingerprint Derivation:
    The repository fingerprint can be derived from:
        1. Explicit --repo-fingerprint argument (must be 24-hex)
        2. Git metadata (remote URL → SHA256[:24])
        3. Global SESSION_STATE pointer fallback

Phase 2 Completion:
    Phase 2 is considered complete only when all three core artifacts exist:
        - repo-cache.yaml
        - repo-map-digest.md
        - workspace-memory.yaml

Exit Codes:
    0: Success (or read-only mode with --quiet)
    2: Blocked (missing binding, invalid fingerprint, config inside repo)

Environment Variables:
    OPENCODE_FORCE_READ_ONLY: Set to "1" to block all writes
    OPENCODE_CONFIG_ROOT: Override config root location
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from governance.entrypoints.write_policy import EFFECTIVE_MODE, is_write_allowed, writes_allowed
try:
    from artifacts.backfill import (
        ArtifactSpec as ArtifactSpec,  # type: ignore[no-redef]
        run_backfill as run_backfill,  # type: ignore[no-redef]
        upsert_artifact as _run_upsert_artifact,
    )
    from artifacts.normalization import (
        has_legacy_decision_pack_ab_prompt,
        normalize_legacy_placeholder_phrasing,
    )
    from artifacts.writers.repo_cache import render_repo_cache
    from artifacts.writers.repo_map_digest import (
        repo_map_digest_section,
        render_repo_map_digest_create,
    )
    from artifacts.writers.decision_pack import (
        decision_pack_section,
        render_decision_pack_create,
    )
    from artifacts.writers.workspace_memory import render_workspace_memory
    from artifacts.writers.business_rules import render_business_rules_inventory
except ImportError:
    from dataclasses import dataclass
    from typing import Callable

    @dataclass(frozen=True)
    class ArtifactSpec:
        key: str
        path: Path
        create_content: str
        append_content: str | None = None

    def normalize_legacy_placeholder_phrasing(text: str) -> tuple[str, bool]:
        replacements = {
            "Backfill placeholder: refresh after Phase 2 discovery.": "Seed snapshot: refresh after evidence-backed Phase 2 discovery.",
            "none (backfill placeholder)": "none (no evidence-backed digest yet)",
            "Backfill placeholder; refresh after evidence-backed Phase 2 discovery.": "Seed snapshot; refresh after evidence-backed Phase 2 discovery.",
            "Evidence: Backfill initialization only; no fresh Phase 2 domain extraction attached": "Evidence: Bootstrap seed only; no fresh Phase 2 domain extraction attached",
        }
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        return updated, updated != text

    def has_legacy_decision_pack_ab_prompt(text: str) -> bool:
        return bool(re.search(r"(?im)^\s*A\)\s*Yes\s*$", text) or re.search(r"(?im)^\s*B\)\s*No\s*$", text))

    def _run_upsert_artifact(
        *,
        path: Path,
        create_content: str,
        append_content: str | None,
        force: bool,
        dry_run: bool,
        read_only: bool,
        write_text: Callable[[Path, str], None],
        append_text: Callable[[Path, str], None],
        normalize_existing: Callable[[Path, bool], str],
    ) -> str:
        if not path.exists():
            if read_only:
                return "blocked-read-only"
            if dry_run:
                return "write-requested"
            write_text(path, create_content)
            return "created"

        normalize_action = normalize_existing(path, dry_run)
        if not force:
            if normalize_action == "normalized":
                return "normalized"
            if normalize_action == "blocked-read-only":
                return "blocked-read-only"
            if normalize_action == "write-requested":
                return "write-requested"
            return "kept"

        if append_content is not None:
            if read_only:
                return "blocked-read-only"
            if dry_run:
                return "write-requested"
            append_text(path, append_content)
            return "appended"

        if read_only:
            return "blocked-read-only"
        if dry_run:
            return "write-requested"
        write_text(path, create_content)
        return "overwritten"

    def run_backfill(
        *,
        specs: list[ArtifactSpec],
        force: bool,
        dry_run: bool,
        read_only: bool,
        write_text: Callable[[Path, str], None],
        append_text: Callable[[Path, str], None],
        normalize_existing: Callable[[Path, bool], str],
    ) -> dict[str, str]:
        actions: dict[str, str] = {}
        for spec in specs:
            actions[spec.key] = _run_upsert_artifact(
                path=spec.path,
                create_content=spec.create_content,
                append_content=spec.append_content,
                force=force,
                dry_run=dry_run,
                read_only=read_only,
                write_text=write_text,
                append_text=append_text,
                normalize_existing=normalize_existing,
            )
        return actions

    def render_repo_cache(*, date: str, repo_name: str, profile: str, profile_evidence: str, repository_type: str) -> str:
        return "\n".join(
            [
                "RepoCache:",
                '  Version: "1.0"',
                f'  LastUpdated: "{date}"',
                f'  RepoName: "{repo_name}"',
                '  GitHead: "unknown"',
                '  RepoSignature: "unknown"',
                f'  ProfileDetected: "{profile}"',
                f'  ProfileEvidence: "{profile_evidence}"',
                "  RepoMapDigest:",
                f'    RepositoryType: "{repository_type}"',
                '    Architecture: "unknown"',
                "    Modules: []",
                "    EntryPoints: []",
                "    DataStores: []",
                "    Testing: []",
                "  ConventionsDigest:",
                '    - "Seed snapshot: refresh after evidence-backed Phase 2 discovery."',
                "  BuildAndTooling: {}",
                "  CacheHashChecks: []",
                "  InvalidateOn:",
                '    - "Profile change"',
                '    - "Rulebook update"',
                '    - "Repository structure change"',
                "",
            ]
        )

    def repo_map_digest_section(date: str, repository_type: str) -> str:
        return "\n".join(
            [
                f"## Repo Map Digest — {date}",
                "Meta:",
                "- GitHead: unknown",
                "- RepoSignature: unknown",
                "- ComponentScope: none",
                "- Provenance: Phase2",
                "",
                f"RepositoryType: {repository_type}",
                "Architecture: unknown",
                "Modules:",
                "- none (no evidence-backed digest yet)",
                "EntryPoints:",
                "- none",
                "DataStores:",
                "- none",
                "BuildAndTooling:",
                "- unknown",
                "Testing:",
                "- unknown",
                "ConventionsDigest:",
                "- Seed snapshot; refresh after evidence-backed Phase 2 discovery.",
                "ArchitecturalInvariants:",
                "- unknown",
                "",
            ]
        )

    def render_repo_map_digest_create(*, date: str, repo_name: str, repository_type: str) -> str:
        section = repo_map_digest_section(date, repository_type)
        return "# Repo Map Digest\n" f"Repo: {repo_name}\n" f"LastUpdated: {date}\n\n" f"{section}"

    def decision_pack_section(date: str, date_compact: str) -> str:
        return "\n".join(
            [
                f"## Decision Pack — {date}",
                "D-001: Record Business Rules bootstrap outcome",
                f"ID: DP-{date_compact}-001",
                "Status: automatic",
                "Action: Persist business-rules outcome as extracted|skipped|not-applicable|deferred.",
                "Policy: business-rules.md is written only when outcome is extracted.",
                "What would change it: scope evidence or Phase 1.5 extraction state.",
                "",
            ]
        )

    def render_decision_pack_create(*, date: str, date_compact: str, repo_name: str) -> str:
        section = decision_pack_section(date, date_compact)
        return "# Decision Pack\n" f"Repo: {repo_name}\n" f"LastUpdated: {date}\n\n" f"{section}"

    def render_workspace_memory(*, date: str, repo_name: str, repo_fingerprint: str) -> str:
        return "\n".join(
            [
                "WorkspaceMemory:",
                '  Version: "1.0"',
                "  Repo:",
                f'    RepoName: "{repo_name}"',
                f'    RepoFingerprint: "{repo_fingerprint}"',
                f'  UpdatedAt: "{date}"',
                "  Provenance:",
                '    Source: "Phase2+Phase5"',
                '    EvidenceMode: "evidence-required"',
                "  Conventions: {}",
                "  Patterns: {}",
                "  Decisions:",
                "    Defaults: []",
                "  Deviations: []",
                "",
            ]
        )

    def render_business_rules_inventory(*, date: str, repo_name: str) -> str:
        return "\n".join(
            [
                f"# Business Rules Inventory — {repo_name}",
                "",
                "SchemaVersion: BRINV-1",
                "Placeholder: true",
                "Source: Phase 1.5 Business Rules Discovery",
                f"Last Updated: {date}",
                "Scope: global",
                "",
                "## BR-001 — Inventory scaffold",
                "Status: CANDIDATE",
                "Rule: Placeholder rule scaffold generated by workspace persistence helper.",
                "Scope: global",
                "Trigger: when Phase 1.5 state indicates extracted rules but no inventory file exists",
                "Enforcement: MISSING",
                "Source: inferred",
                "Confidence: 0",
                f"Last Verified: {date}",
                "Owners: none",
                "Evidence: MISSING",
                "Tests: MISSING",
                "Conflicts: none",
                "",
            ]
        )

# Keep baseline decision-pack text discoverable in this orchestrator module
# for governance contract checks.
_PERSISTENCE_DECISION_PACK_BASELINE = (
    "D-001: Record Business Rules bootstrap outcome",
    "Status: automatic",
    "Action: Persist business-rules outcome as extracted|skipped|not-applicable|deferred.",
    "Policy: business-rules.md is written only when outcome is extracted.",
)

from governance.entrypoints.error_handler_bridge import (
    ErrorContext,
    emit_gate_failure,
    install_global_handlers,
    set_error_context,
)
try:
    from governance.infrastructure.logging.global_error_handler import resolve_log_path
except Exception:
    def resolve_log_path(*, config_root=None, commands_home=None, workspaces_home=None, repo_fingerprint=None):
        _ = config_root
        if repo_fingerprint and workspaces_home:
            return Path(workspaces_home) / repo_fingerprint / "logs" / "error.log.jsonl"
        if commands_home:
            return Path(commands_home) / "logs" / "error.log.jsonl"
        raise RuntimeError("no writable error log target available")

try:
    from governance.domain.phase_state_machine import normalize_phase_token, phase_rank
except Exception:
    def normalize_phase_token(value: object) -> str:
        token = str(value or "").strip().upper()
        if token.startswith("1.1"):
            return "1.1"
        if token.startswith("1.2"):
            return "1.2"
        if token.startswith("1.3"):
            return "1.3"
        if token.startswith("1.5"):
            return "1.5"
        if token.startswith("2.1"):
            return "2.1"
        if token.startswith("2"):
            return "2"
        if token.startswith("3A"):
            return "3A"
        if token.startswith("3B-1"):
            return "3B-1"
        if token.startswith("3B-2"):
            return "3B-2"
        if token.startswith("4"):
            return "4"
        return ""

    def phase_rank(token: str) -> int:
        ranks = {
            "1.1": 11,
            "1.2": 12,
            "1.3": 13,
            "1.5": 15,
            "2": 20,
            "2.1": 21,
            "3A": 30,
            "3B-1": 31,
            "3B-2": 32,
            "4": 40,
        }
        return ranks.get(token, -1)

def _read_only() -> bool:
    return not writes_allowed()

try:
    from governance.infrastructure.path_contract import (
        canonical_config_root,
        normalize_absolute_path,
        normalize_for_fingerprint,
    )
except Exception:
    class NotAbsoluteError(Exception):
        pass

    class WindowsDriveRelativeError(Exception):
        pass

    def canonical_config_root() -> Path:
        return Path(os.path.normpath(os.path.abspath(str(Path.home().expanduser() / ".config" / "opencode"))))

    def normalize_absolute_path(raw: str, *, purpose: str) -> Path:
        token = str(raw or "").strip()
        if not token:
            raise NotAbsoluteError(f"{purpose}: empty path")
        candidate = Path(token).expanduser()
        if os.name == "nt" and re.match(r"^[A-Za-z]:[^/\\]", token):
            raise WindowsDriveRelativeError(f"{purpose}: drive-relative path is not allowed")
        if not candidate.is_absolute():
            raise NotAbsoluteError(f"{purpose}: path must be absolute")
        return Path(os.path.normpath(os.path.abspath(str(candidate))))

    def normalize_for_fingerprint(path: Path) -> str:
        normalized = os.path.normpath(os.path.abspath(str(path.expanduser())))
        normalized = normalized.replace("\\", "/")
        if os.name == "nt":
            return normalized.casefold()
        return normalized

try:
    from error_logs import safe_log_error
except Exception:  # pragma: no cover
    def safe_log_error(**kwargs):  # type: ignore[no-redef]
        return {"status": "log-disabled"}

from workspace_lock import acquire_workspace_lock
from command_profiles import render_command_profiles
try:
    from governance.infrastructure.fs_atomic import atomic_write_text
except Exception:
    def atomic_write_text(path: Path, text: str, newline_lf: bool = True, attempts: int = 5, backoff_ms: int = 50) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text.replace("\r\n", "\n") if newline_lf else text
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n" if newline_lf else None,
                dir=str(path.parent),
                prefix=path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)
            os.replace(str(temp_path), str(path))
            return 0
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

try:
    from governance.application.repo_identity_service import canonicalize_origin_url, derive_repo_identity
except Exception:
    import hashlib
    from urllib.parse import urlsplit

    class _FallbackRepoIdentity:
        def __init__(self, fingerprint: str, material_class: str, canonical_remote: str | None, normalized_repo_root: str, git_dir_path: str | None) -> None:
            self.fingerprint = fingerprint
            self.material_class = material_class
            self.canonical_remote = canonical_remote
            self.normalized_repo_root = normalized_repo_root
            self.git_dir_path = git_dir_path

    def canonicalize_origin_url(remote: str) -> str | None:
        raw = remote.strip()
        if not raw:
            return None
        scp_style = re.match(r"^(?P<user>[^@/\s]+)@(?P<host>[^:/\s]+):(?P<path>[^\s]+)$", raw)
        if scp_style:
            raw = f"ssh://{scp_style.group('user')}@{scp_style.group('host')}/{scp_style.group('path')}"
        try:
            parsed = urlsplit(raw)
        except Exception:
            return None
        if not parsed.scheme or not parsed.netloc:
            return None
        host = parsed.hostname.casefold() if parsed.hostname else ""
        if not host:
            return None
        path = parsed.path.replace("\\", "/").strip()
        if path.lower().endswith(".git"):
            path = path[:-4]
        path = path.rstrip("/").casefold()
        if not path.startswith("/"):
            path = f"/{path}"
        return f"repo://{host}{path}"

    def _derive_repo_identity_fallback(repo_root: Path, *, canonical_remote: str | None, git_dir: Path | None):
        normalized_root = normalize_for_fingerprint(repo_root)
        if canonical_remote:
            material = f"repo:{canonical_remote}"
            fp = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
            return _FallbackRepoIdentity(fp, "remote_canonical", canonical_remote, normalized_root, str(git_dir) if git_dir else None)
        material = f"repo:local:{normalized_root}"
        fp = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        return _FallbackRepoIdentity(fp, "local_path", None, normalized_root, str(git_dir) if git_dir else None)

    derive_repo_identity = _derive_repo_identity_fallback  # type: ignore[assignment]


def default_config_root() -> Path:
    return canonical_config_root()


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_binding_paths(paths_file: Path, *, expected_config_root: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Load binding paths with SSOT validation.
    
    This function validates binding paths consistently with the SSOT loader
    but works both in-repo (with governance module) and in-release (standalone).
    
    Validates:
    - commandsHome must be configRoot/commands
    - workspacesHome must be configRoot/workspaces
    
    Args:
        paths_file: Path to governance.paths.json
        expected_config_root: Optional expected config root for additional validation
    
    Returns:
        Tuple of (config_root, paths_dict)
    
    Raises:
        ValueError: If binding file is invalid or paths don't match constraints.
    """
    payload = _load_json(paths_file)
    if not payload:
        raise ValueError(f"binding evidence unreadable: {paths_file}")
    
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"binding evidence invalid: missing paths object in {paths_file}")
    
    config_root_raw = paths.get("configRoot")
    commands_raw = paths.get("commandsHome")
    workspaces_raw = paths.get("workspacesHome")
    
    if not isinstance(config_root_raw, str) or not config_root_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.configRoot missing in {paths_file}")
    if not isinstance(commands_raw, str) or not commands_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.commandsHome missing in {paths_file}")
    if not isinstance(workspaces_raw, str) or not workspaces_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.workspacesHome missing in {paths_file}")
    
    try:
        config_root = normalize_absolute_path(config_root_raw, purpose="paths.configRoot")
        commands_home = normalize_absolute_path(commands_raw, purpose="paths.commandsHome")
        workspaces_home = normalize_absolute_path(workspaces_raw, purpose="paths.workspacesHome")
    except Exception as exc:
        raise ValueError(f"binding evidence invalid: {exc}") from exc
    
    if expected_config_root is not None:
        expected = normalize_absolute_path(str(expected_config_root), purpose="expected_config_root")
        if config_root != expected:
            raise ValueError("binding evidence mismatch: config root does not match explicit input")
    
    return config_root, paths


def _resolve_python_command(paths: dict[str, Any]) -> str:
    """Resolve the Python command to use for subprocess calls.
    
    Args:
        paths: The paths dictionary from governance.paths.json.
    
    Returns:
        The python command string (from config or sys.executable).
    """
    raw = paths.get("pythonCommand")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return str(sys.executable or "python")


def _resolve_repo_root_strict(
    explicit: Path | None,
    *,
    require_git_marker: bool = True,
) -> tuple[Path | None, str, dict[str, object]]:
    if explicit is not None:
        try:
            normalized = normalize_absolute_path(str(explicit), purpose="repo_root")
            has_git_marker = (normalized / ".git").exists() or (normalized / ".git").is_file()
            if has_git_marker or not require_git_marker:
                return normalized, "explicit", {"ok": True, "source": "explicit", "path": str(normalized)}
            return None, "explicit-invalid", {"ok": False, "source": "explicit", "path": str(normalized), "reason": "missing-.git"}
        except Exception as exc:
            return None, "explicit-invalid", {"ok": False, "source": "explicit", "error": str(exc)[:200]}

    env_root = os.environ.get("OPENCODE_REPO_ROOT", "").strip()
    if env_root:
        try:
            normalized = normalize_absolute_path(env_root, purpose="OPENCODE_REPO_ROOT")
            if (normalized / ".git").exists() or (normalized / ".git").is_file():
                return normalized, "env", {"ok": True, "source": "env", "path": str(normalized)}
            return None, "env-invalid", {"ok": False, "source": "env", "path": str(normalized), "reason": "missing-.git"}
        except Exception as exc:
            return None, "env-invalid", {"ok": False, "source": "env", "raw": env_root, "error": str(exc)[:200]}

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception as exc:
        return None, "git-probe-failed", {"ok": False, "source": "git", "error": str(exc)[:200]}

    root = (result.stdout or "").strip()
    if result.returncode == 0 and root:
        try:
            return normalize_absolute_path(root, purpose="git-rev-parse"), "git", {
                "ok": True,
                "source": "git",
                "stdout": root,
                "returncode": result.returncode,
            }
        except Exception as exc:
            return None, "git-invalid", {
                "ok": False,
                "source": "git",
                "stdout": root,
                "returncode": result.returncode,
                "error": str(exc)[:200],
            }

    return None, "git-miss", {
        "ok": False,
        "source": "git",
        "stdout": root,
        "stderr": (result.stderr or "").strip()[:240],
        "returncode": result.returncode,
    }


def _preferred_shell_command(profiles: dict[str, object]) -> str:
    """Get the preferred shell command for the current platform.
    
    Args:
        profiles: Command profiles dictionary.
    
    Returns:
        The preferred shell command string.
    """
    if os.name == "nt":
        return str(profiles.get("powershell") or profiles.get("cmd") or profiles.get("bash") or "")
    return str(profiles.get("bash") or profiles.get("json") or "")


def resolve_binding_config(explicit: Path | None) -> tuple[Path, dict[str, Any], Path]:
    """Resolve the binding configuration paths.
    
    Searches for governance.paths.json in the following order:
        1. COMMANDS_HOME environment variable
        2. Explicit --config-root argument
        3. OPENCODE_CONFIG_ROOT environment variable
        4. Default ~/.config/opencode location
    
    Args:
        explicit: Optional explicit config root path from --config-root.
    
    Returns:
        Tuple of (config_root, paths_dict, binding_file_path).
    
    Raises:
        ValueError: If binding file not found or invalid.
    """
    env_commands_home = os.environ.get("COMMANDS_HOME")
    if env_commands_home:
        try:
            commands_home = normalize_absolute_path(env_commands_home, purpose="COMMANDS_HOME env")
            root = commands_home.parent
            candidate = commands_home / "governance.paths.json"
            if candidate.exists():
                config_root, paths = _load_binding_paths(candidate, expected_config_root=root)
                return config_root, paths, candidate
        except Exception:
            pass

    if explicit is not None:
        root = normalize_absolute_path(str(explicit), purpose="explicit_config_root")
        candidate = root / "commands" / "governance.paths.json"
        config_root, paths = _load_binding_paths(candidate, expected_config_root=root)
        return config_root, paths, candidate

    env_value = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_value:
        root = normalize_absolute_path(env_value, purpose="env:OPENCODE_CONFIG_ROOT")
        candidate = root / "commands" / "governance.paths.json"
        config_root, paths = _load_binding_paths(candidate, expected_config_root=root)
        return config_root, paths, candidate

    fallback = default_config_root()
    candidate = fallback / "commands" / "governance.paths.json"
    config_root, paths = _load_binding_paths(candidate, expected_config_root=fallback)
    return config_root, paths, candidate


def _validate_repo_fingerprint(value: str) -> str:
    """Validate repo fingerprint is canonical 24-hex format.
    
    This enforces SSOT: only hash-based fingerprints are accepted.
    Legacy slug-style fingerprints (e.g., github.com-user-repo) are rejected.
    
    Args:
        value: The fingerprint string to validate.
    
    Returns:
        The validated fingerprint (lowercase, stripped).
    
    Raises:
        ValueError: If fingerprint is empty or not 24-hex format.
    """
    token = value.strip()
    if not token:
        raise ValueError("repo fingerprint must not be empty")
    if not re.fullmatch(r"[0-9a-f]{24}", token):
        raise ValueError(
            "repo fingerprint must be a 24-character hex string (canonical hash-based format). "
            "Legacy slug-style fingerprints are not accepted."
        )
    return token


def _is_canonical_fingerprint(value: str) -> bool:
    """Check if value is a canonical 24-hex fingerprint.
    
    Args:
        value: The string to check.
    
    Returns:
        True if value matches ^[0-9a-f]{24}$, False otherwise.
    """
    token = value.strip()
    return bool(re.fullmatch(r"[0-9a-f]{24}", token))


def _validate_canonical_fingerprint(value: str) -> str:
    """Alias for _validate_repo_fingerprint for clarity.
    
    Args:
        value: The fingerprint string to validate.
    
    Returns:
        The validated canonical fingerprint.
    """
    return _validate_repo_fingerprint(value)


PHASE2_ARTIFACTS = ["repo-cache.yaml", "repo-map-digest.md", "workspace-memory.yaml"]


def _verify_phase2_artifacts_exist(repo_home: Path) -> tuple[bool, list[str]]:
    missing = []
    for artifact in PHASE2_ARTIFACTS:
        path = repo_home / artifact
        if not path.is_file():
            missing.append(artifact)
    return len(missing) == 0, missing


def _sanitize_repo_name(value: str, fallback: str) -> str:
    raw = value.strip().lower()
    raw = raw.replace(" ", "-")
    raw = re.sub(r"[^a-z0-9._-]", "", raw)
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw if raw else fallback


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_git_dir(repo_root: Path) -> Path | None:
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git

    if dot_git.is_file():
        try:
            text = dot_git.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = dot_git.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"gitdir:\s*(.+)", text)
        if not m:
            return None
        raw = m.group(1).strip()
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = normalize_absolute_path(str(repo_root / candidate), purpose="gitdir_relative")
        return candidate if candidate.exists() else None

    return None


def _read_origin_remote(config_path: Path) -> str | None:
    if not config_path.exists():
        return None

    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_origin = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_origin = stripped == '[remote "origin"]'
            continue
        if in_origin:
            m = re.match(r"url\s*=\s*(.+)", stripped)
            if m:
                return m.group(1).strip()

    return None


def _canonicalize_origin_remote(remote: str) -> str | None:
    return canonicalize_origin_url(remote)


def _normalize_path_for_fingerprint(path: Path) -> str:
    """Normalize filesystem paths for deterministic cross-platform fingerprints."""

    return normalize_for_fingerprint(path)


def _derive_fingerprint_from_repo(repo_root: Path) -> tuple[str, str] | None:
    root = Path(os.path.normpath(os.path.abspath(str(repo_root.expanduser()))))
    git_dir = _resolve_git_dir(root)
    if not git_dir:
        return None

    remote = _read_origin_remote(git_dir / "config")
    canonical_remote = _canonicalize_origin_remote(remote) if remote else None
    identity = derive_repo_identity(root, canonical_remote=canonical_remote, git_dir=git_dir)
    material = (
        f"repo:{identity.canonical_remote}"
        if identity.material_class == "remote_canonical" and identity.canonical_remote
        else f"repo:local:{identity.normalized_repo_root}"
    )
    fp = identity.fingerprint
    return fp, material


def _resolve_repo_fingerprint(
    config_root: Path,
    explicit: str | None,
    repo_root: Path,
) -> tuple[str, str, str]:
    if explicit:
        validated = _validate_repo_fingerprint(explicit)
        if not _is_canonical_fingerprint(validated):
            raise ValueError(
                f"explicit repo fingerprint must be canonical 24-hex format, got: {validated}"
            )
        return validated, "explicit", "operator-provided"

    derived = _derive_fingerprint_from_repo(repo_root)
    if derived:
        fp, material = derived
        return _validate_repo_fingerprint(fp), "git-metadata", material

    pointer_path = config_root / "SESSION_STATE.json"
    pointer = _load_json(pointer_path)
    if pointer and pointer.get("schema") == "opencode-session-pointer.v1":
        fp = pointer.get("activeRepoFingerprint")
        if isinstance(fp, str) and fp.strip():
            validated = _validate_repo_fingerprint(fp)
            if not _is_canonical_fingerprint(validated):
                raise ValueError(
                    f"pointer repo fingerprint must be canonical 24-hex format, got: {validated}"
                )
            return validated, "pointer", "global-pointer-fallback"

    raise ValueError(
        "repo fingerprint is required (use --repo-fingerprint with 24-hex canonical format), or run from a git repo root, or ensure global SESSION_STATE pointer exists"
    )


def _read_repo_session(path: Path) -> dict[str, Any] | None:
    data = _load_json(path)
    if not data:
        return None
    ss = data.get("SESSION_STATE")
    return ss if isinstance(ss, dict) else None


def _render_repo_cache(
    *,
    date: str,
    repo_name: str,
    profile: str,
    profile_evidence: str,
    repository_type: str,
) -> str:
    return render_repo_cache(
        date=date,
        repo_name=repo_name,
        profile=profile,
        profile_evidence=profile_evidence,
        repository_type=repository_type,
    )


def _repo_map_digest_section(date: str, repository_type: str) -> str:
    return repo_map_digest_section(date, repository_type)


def _render_repo_map_digest_create(*, date: str, repo_name: str, repository_type: str) -> str:
    return render_repo_map_digest_create(date=date, repo_name=repo_name, repository_type=repository_type)


def _decision_pack_section(date: str, date_compact: str) -> str:
    return decision_pack_section(date, date_compact)


def _render_decision_pack_create(*, date: str, date_compact: str, repo_name: str) -> str:
    return render_decision_pack_create(date=date, date_compact=date_compact, repo_name=repo_name)


def _render_workspace_memory(*, date: str, repo_name: str, repo_fingerprint: str) -> str:
    return render_workspace_memory(date=date, repo_name=repo_name, repo_fingerprint=repo_fingerprint)


def _should_write_business_rules_inventory(session: dict[str, Any] | None) -> bool:
    if not isinstance(session, dict):
        return False

    scope = session.get("Scope")
    business_rules_scope = ""
    if isinstance(scope, dict):
        raw = scope.get("BusinessRules")
        if isinstance(raw, str):
            business_rules_scope = raw.strip().lower()

    business_rules = session.get("BusinessRules")
    if isinstance(business_rules, dict):
        status = business_rules.get("InventoryFileStatus")
        if isinstance(status, str) and status.strip().lower() == "write-requested":
            return True

    active_gate = session.get("active_gate")
    if isinstance(active_gate, str) and "business_rules_persist" in active_gate.strip().lower():
        return True

    phase = session.get("Phase")
    if isinstance(phase, str) and phase.strip().upper().startswith("1.5"):
        return True

    return business_rules_scope == "extracted"


def _render_business_rules_inventory(*, date: str, repo_name: str) -> str:
    return render_business_rules_inventory(date=date, repo_name=repo_name)


def _write_text(path: Path, content: str, *, dry_run: bool, read_only: bool) -> None:
    if read_only or dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, content, read_only=read_only)


def _append_text(path: Path, content: str, *, dry_run: bool, read_only: bool) -> None:
    if read_only or dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        existing = path.read_text(encoding="utf-8", errors="replace")
    if not existing.endswith("\n"):
        existing += "\n"
    existing += "\n" + content
    _atomic_write_text(path, existing, read_only=read_only)


def _append_jsonl_event(path: Path, payload: dict[str, object], *, dry_run: bool, read_only: bool) -> str:
    if read_only:
        return "blocked-read-only"
    if dry_run:
        return "write-requested"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    existing = ""
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            existing = path.read_text(encoding="utf-8", errors="replace")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    updated = f"{existing}{line}\n"
    _atomic_write_text(path, updated, read_only=read_only)
    return "written"


def _atomic_write_text(path: Path, content: str, *, read_only: bool = False) -> None:
    if read_only:
        return
    atomic_write_text(path, content, newline_lf=True, attempts=5, backoff_ms=50)


def _normalize_legacy_placeholder_phrasing(path: Path, *, dry_run: bool, read_only: bool) -> str:
    if not path.exists() or not path.is_file():
        return "not-found"

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    updated, changed = normalize_legacy_placeholder_phrasing(text)

    if not changed:
        return "unchanged"

    if read_only:
        return "blocked-read-only"
    if dry_run:
        return "write-requested"
    _atomic_write_text(path, updated)
    return "normalized"


def _upsert_artifact(
    *,
    path: Path,
    create_content: str,
    append_content: str | None,
    force: bool,
    dry_run: bool,
    read_only: bool,
) -> str:
    return _run_upsert_artifact(
        path=path,
        create_content=create_content,
        append_content=append_content,
        force=force,
        dry_run=dry_run,
        read_only=read_only,
        write_text=lambda p, c: _write_text(p, c, dry_run=False, read_only=read_only),
        append_text=lambda p, c: _append_text(p, c, dry_run=False, read_only=read_only),
        normalize_existing=lambda p, d: _normalize_legacy_placeholder_phrasing(p, dry_run=d, read_only=read_only),
    )


def _update_session_state(
    *,
    session_path: Path,
    dry_run: bool,
    business_rules_inventory_written: bool,
    business_rules_inventory_action: str,
    repo_cache_action: str,
    repo_map_digest_action: str,
    decision_pack_action: str,
    workspace_memory_action: str,
    read_only: bool,
) -> str:
    data = _load_json(session_path)
    if not data:
        return "no-session-file"
    ss = data.get("SESSION_STATE")
    if not isinstance(ss, dict):
        return "invalid-session-shape"

    def _action_to_status(action: str) -> str:
        if action in {"created", "overwritten", "appended"}:
            return "written"
        if action == "normalized":
            return "normalized"
        if action == "kept":
            return "unchanged"
        if action == "write-requested":
            return "write-requested"
        if action == "blocked-read-only":
            return "blocked-read-only"
        return "unknown"

    ss.setdefault("RepoCacheFile", {})
    if isinstance(ss["RepoCacheFile"], dict):
        ss["RepoCacheFile"]["TargetPath"] = "${REPO_CACHE_FILE}"
        ss["RepoCacheFile"]["FileStatus"] = _action_to_status(repo_cache_action)

    ss.setdefault("RepoMapDigestFile", {})
    if isinstance(ss["RepoMapDigestFile"], dict):
        ss["RepoMapDigestFile"]["FilePath"] = "${REPO_DIGEST_FILE}"
        ss["RepoMapDigestFile"]["FileStatus"] = _action_to_status(repo_map_digest_action)

    ss.setdefault("DecisionPack", {})
    if isinstance(ss["DecisionPack"], dict):
        ss["DecisionPack"]["FilePath"] = "${REPO_DECISION_PACK_FILE}"
        ss["DecisionPack"]["FileStatus"] = _action_to_status(decision_pack_action)

    ss.setdefault("WorkspaceMemoryFile", {})
    if isinstance(ss["WorkspaceMemoryFile"], dict):
        ss["WorkspaceMemoryFile"]["TargetPath"] = "${WORKSPACE_MEMORY_FILE}"
        ss["WorkspaceMemoryFile"]["FileStatus"] = _action_to_status(workspace_memory_action)

    scope = ss.get("Scope")
    business_rules_scope = ""
    if isinstance(scope, dict):
        raw = scope.get("BusinessRules")
        if isinstance(raw, str):
            business_rules_scope = raw.strip().lower()

    outcome = "deferred"
    if business_rules_scope in {"extracted", "skipped", "not-applicable", "deferred"}:
        outcome = business_rules_scope
    elif business_rules_inventory_written or business_rules_inventory_action in {"created", "overwritten", "kept"}:
        outcome = "extracted"
    elif business_rules_inventory_action in {"write-requested", "blocked-read-only"}:
        outcome = "deferred"
    else:
        outcome = "skipped"

    ss.setdefault("BusinessRules", {})
    if isinstance(ss["BusinessRules"], dict):
        inventory = ss["BusinessRules"]
        inventory["Outcome"] = outcome
        inventory["OutcomeSource"] = "scope" if business_rules_scope else "persistence-helper"
        inventory["InventoryFileStatus"] = _action_to_status(business_rules_inventory_action)
        if outcome in {"extracted", "deferred"}:
            inventory["InventoryFilePath"] = "${REPO_BUSINESS_RULES_FILE}"
        if business_rules_inventory_action == "created":
            inventory["InventoryFileMode"] = "create"
        elif business_rules_inventory_action in {"overwritten", "kept"}:
            inventory["InventoryFileMode"] = "update"
        else:
            inventory.setdefault("InventoryFileMode", "unknown")

    if dry_run:
        return "updated-dry-run"

    if read_only:
        return "updated-read-only"

    session_payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    _atomic_write_text(session_path, session_payload, read_only=read_only)
    return "updated"


def _bootstrap_missing_session_state(
    *,
    config_root: Path,
    repo_fingerprint: str,
    repo_name: str,
    repo_root: Path,
    python_cmd: str,
    dry_run: bool,
    read_only: bool,
) -> tuple[bool, str]:
    """Ensure repo-scoped SESSION_STATE exists before persistence update."""

    if dry_run:
        return True, "bootstrap-dry-run"
    if read_only:
        return True, "bootstrap-read-only"

    helper = SCRIPT_DIR / "bootstrap_session_state.py"
    if not helper.exists():
        return False, "missing-bootstrap-helper"

    token = str(python_cmd or "").strip()
    if token == "py -3":
        python_argv = ["py", "-3"]
    elif token == "python -3":
        python_argv = ["python", "-3"]
    else:
        python_argv = [token] if token else [str(sys.executable or "python")]
    cmd = [
        *python_argv,
        str(helper),
        "--repo-fingerprint",
        repo_fingerprint,
        "--repo-name",
        repo_name,
        "--repo-root",
        str(repo_root),
        "--config-root",
        str(config_root),
        "--skip-artifact-backfill",
        "--no-commit",
    ]
    env = os.environ.copy()
    env["OPENCODE_INTERNAL_ALLOW_SKIP_ARTIFACT_BACKFILL"] = "1"
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False, env=env)
    if proc.returncode != 0:
        return False, f"bootstrap-failed:{proc.returncode}"
    return True, "bootstrap-created"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill repo-scoped workspace persistence artifacts (cache, digest, decision pack, memory)."
    )
    p.add_argument(
        "--repo-fingerprint",
        default="",
        help="Repo workspace key. If omitted, derive from git metadata (repo root) then fallback to global SESSION_STATE pointer.",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Absolute git top-level path for this repo (SSOT). If omitted, OPENCODE_REPO_ROOT must be set.",
    )
    p.add_argument("--repo-name", default="", help="Optional repository display name.")
    p.add_argument("--config-root", type=Path, default=None, help="Override OpenCode config root.")
    p.add_argument("--force", action="store_true", help="Overwrite YAML artifacts and append markdown sections when artifacts already exist.")
    p.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files.")
    p.add_argument("--no-session-update", action="store_true", help="Do not update repo-scoped SESSION_STATE file pointers/status fields.")
    p.add_argument("--quiet", action="store_true", help="Print compact JSON summary only.")
    p.add_argument("--skip-lock", action="store_true", help="Internal use: skip workspace lock acquisition.")
    p.add_argument(
        "--require-phase2",
        action="store_true",
        help="Fail-closed if required Phase 2/2.1 artifacts are missing after backfill.",
    )
    return p.parse_args()


def main() -> int:
    install_global_handlers()
    read_only = _read_only()
    args = parse_args()
    try:
        config_root, binding_paths, binding_file = resolve_binding_config(args.config_root)
    except Exception as exc:
        emit_gate_failure(
            gate="PERSISTENCE",
            code="MISSING_BINDING_FILE",
            message=str(exc),
            expected="installer-owned commands/governance.paths.json exists",
            observed={"config_root_arg": str(args.config_root) if args.config_root else ""},
            remediation="Restore governance.paths.json via installer or provide valid --config-root.",
        )
        payload = {
            "status": "blocked",
            "reason": str(exc),
            "reason_code": "BLOCKED-MISSING-BINDING-FILE",
            "missing_evidence": ["${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"],
            "recovery_steps": [
                "run installer to create commands/governance.paths.json",
                "or provide --config-root that contains commands/governance.paths.json",
            ],
            "required_operator_action": "restore installer-owned path binding evidence before persistence",
            "feedback_required": "reply with governance.paths.json location used for rerun",
            "next_command": "${PYTHON_COMMAND} governance/entrypoints/persist_workspace_artifacts.py --config-root <config_root>",
            "next_command_profiles": render_command_profiles(
                [
                    "${PYTHON_COMMAND}",
                    "governance/entrypoints/persist_workspace_artifacts.py",
                    "--config-root",
                    "<config_root>",
                ]
            ),
        }
        if args.quiet:
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print(f"ERROR: {exc}")
        return 2

    python_cmd = _resolve_python_command(binding_paths)
    
    repo_root, repo_root_source, git_probe = _resolve_repo_root_strict(
        args.repo_root,
        require_git_marker=not bool(args.no_session_update),
    )
    if repo_root is None:
        cmd_profiles = render_command_profiles(
            [
                python_cmd,
                "governance/entrypoints/persist_workspace_artifacts.py",
                "--repo-root",
                "<repo_root>",
                "--config-root",
                str(config_root),
            ]
        )
        log_path = resolve_log_path(
            config_root=str(config_root),
            commands_home=str(binding_paths.get("commandsHome", "")),
            workspaces_home=str(config_root / "workspaces"),
            repo_fingerprint=None,
        )
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            message="Repository root is not deterministically detectable.",
            expected="valid --repo-root, OPENCODE_REPO_ROOT, or git rev-parse --show-toplevel",
            observed={"cwd": str(Path.cwd()), "repo_root_source": repo_root_source, "git_probe": git_probe},
            remediation="Provide --repo-root or OPENCODE_REPO_ROOT with a valid git repository root.",
            config_root=str(config_root),
            workspaces_home=str(config_root / "workspaces"),
            repo_fingerprint=None,
            phase="2",
        )
        payload = {
            "status": "blocked",
            "reason": "repo root not detectable",
            "reason_code": "BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            "missing_evidence": ["deterministic repo root"],
            "recovery_steps": [
                "set OPENCODE_REPO_ROOT to an absolute git repository root",
                "or pass --repo-root explicitly",
            ],
            "required_operator_action": "provide deterministic repository root evidence before persistence",
            "feedback_required": "reply with the resolved repo root path used for rerun",
            "next_command": _preferred_shell_command(cmd_profiles),
            "next_command_profiles": cmd_profiles,
            "repo_root_detected": "",
            "git_probe": git_probe,
            "cwd": str(Path.cwd()),
            "log_path": str(log_path),
        }
        if args.quiet:
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print("ERROR: repository root is not deterministically detectable")
        return 2

    if (repo_root / ".git").exists() and _is_within(config_root, repo_root):
        emit_gate_failure(
            gate="PERSISTENCE",
            code="CONFIG_ROOT_INSIDE_REPO",
            message="Config root resolves inside repository root (blocked).",
            expected="configRoot must be outside repoRoot",
            observed={"configRoot": str(config_root), "repoRoot": str(repo_root)},
            remediation="Set OPENCODE_CONFIG_ROOT to an absolute location outside the repository and rerun.",
        )
        cmd_profiles = render_command_profiles(
            [
                python_cmd,
                "governance/entrypoints/persist_workspace_artifacts.py",
                "--config-root",
                "<outside_repo_config_root>",
                "--repo-root",
                "<repo_root>",
            ]
        )
        payload = {
            "status": "blocked",
            "reason": "config root resolves inside repository root",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "missing_evidence": [
                "valid config root outside repository working tree",
            ],
            "recovery_steps": [
                "set OPENCODE_CONFIG_ROOT to a user config location outside the repository",
                "or pass --config-root to an absolute path outside the repository",
            ],
            "required_operator_action": "rerun with a config root outside the repo working tree",
            "feedback_required": "reply with the chosen config root and rerun result",
            "next_command": _preferred_shell_command(cmd_profiles),
            "next_command_profiles": cmd_profiles,
        }
        if args.quiet:
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print("ERROR: config root resolves inside repository root")
            print(f"- config_root: {config_root}")
            print(f"- repo_root: {repo_root}")
        return 2

    try:
        repo_fingerprint, fp_source, fp_evidence = _resolve_repo_fingerprint(
            config_root,
            args.repo_fingerprint or None,
            repo_root,
        )
    except ValueError as exc:
        emit_gate_failure(
            gate="PERSISTENCE",
            code="REPO_FINGERPRINT_RESOLUTION_FAILED",
            message=str(exc),
            expected="Provide --repo-fingerprint, git metadata evidence, or global SESSION_STATE pointer evidence",
            observed={"repoFingerprintArg": args.repo_fingerprint, "repoRoot": str(repo_root)},
            remediation="Provide --repo-fingerprint explicitly or run from a valid git repository root.",
        )
        safe_log_error(
            reason_key="ERR-REPO-FINGERPRINT-RESOLUTION",
            message=str(exc),
            config_root=config_root,
            phase="2",
            gate="PERSISTENCE",
            mode="repo-aware",
            repo_fingerprint=None,
            command="persist_workspace_artifacts.py",
            component="workspace-persistence",
            observed_value={
                "repoFingerprintArg": args.repo_fingerprint,
                "repoRoot": str(repo_root),
            },
            expected_constraint=(
                "Provide --repo-fingerprint or run from a git repo root or have a valid global SESSION_STATE pointer"
            ),
            remediation="Provide --repo-fingerprint explicitly or invoke from the target repository root.",
        )
        if args.quiet:
            cmd_profiles = render_command_profiles(
                [
                    python_cmd,
                    "governance/entrypoints/persist_workspace_artifacts.py",
                    "--repo-fingerprint",
                    "<repo_fingerprint>",
                    "--repo-root",
                    "<repo_root>",
                ]
            )
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": str(exc),
                        "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
                        "missing_evidence": [
                            "repo fingerprint (provide --repo-fingerprint OR git metadata evidence OR global SESSION_STATE pointer)",
                        ],
                        "recovery_steps": [
                            "provide --repo-fingerprint explicitly",
                            "or run from a git repository root with valid .git metadata",
                            "or ensure global SESSION_STATE pointer is available",
                        ],
                        "required_operator_action": "run one recovery path and report back the chosen repo fingerprint",
                        "feedback_required": "reply with the repo fingerprint used so persistence can resume deterministically",
                        "next_command": _preferred_shell_command(cmd_profiles),
                        "next_command_profiles": cmd_profiles,
                    },
                    ensure_ascii=True,
                )
            )
        else:
            print(f"ERROR: {exc}")
        return 2

    if read_only:
        payload = {
            "status": "ok",
            "workspacePersistenceHook": "skipped",
            "reason": "governance-read-only",
            "impact": "workspace/index/session persistence is kernel-owned only",
            "repoFingerprint": repo_fingerprint,
            "repoFingerprintSource": fp_source,
            "repoFingerprintEvidence": fp_evidence,
            "read_only": read_only,
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 0

    workspaces_home = normalize_absolute_path(
        str(binding_paths.get("workspacesHome", "")),
        purpose="paths.workspacesHome",
    )
    repo_home = workspaces_home / repo_fingerprint
    session_path = repo_home / "SESSION_STATE.json"
    bootstrap_status = "not-required"
    if not args.no_session_update and not session_path.exists():
        bootstrap_ok, bootstrap_status = _bootstrap_missing_session_state(
            config_root=config_root,
            repo_fingerprint=repo_fingerprint,
            repo_name=args.repo_name or repo_root.name or repo_fingerprint,
            repo_root=repo_root,
            python_cmd=python_cmd,
            dry_run=args.dry_run,
            read_only=read_only,
        )
        if not bootstrap_ok:
            emit_gate_failure(
                gate="PERSISTENCE",
                code="REPO_SESSION_BOOTSTRAP_FAILED",
                message="Repo-scoped SESSION_STATE bootstrap failed before artifact persistence.",
                expected="repo-scoped SESSION_STATE.json exists",
                observed={"bootstrap_status": bootstrap_status, "repoFingerprint": repo_fingerprint},
                remediation="Run governance/entrypoints/bootstrap_session_state.py with the same --repo-fingerprint and --config-root, then rerun persistence.",
            )
            cmd_profiles = render_command_profiles(
                [
                    python_cmd,
                    "governance/entrypoints/bootstrap_session_state.py",
                    "--repo-fingerprint",
                    repo_fingerprint,
                    "--config-root",
                    str(config_root),
                ]
            )
            payload = {
                "status": "blocked",
                "reason": "repo session state bootstrap failed",
                "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
                "missing_evidence": ["repo-scoped SESSION_STATE.json"],
                "recovery_steps": [
                    "run governance/entrypoints/bootstrap_session_state.py with --repo-fingerprint and --config-root",
                    "rerun governance/entrypoints/persist_workspace_artifacts.py after bootstrap succeeds",
                ],
                "required_operator_action": "bootstrap repo-scoped session state and rerun persistence",
                "feedback_required": "reply with bootstrap helper output and repo fingerprint",
                "next_command": _preferred_shell_command(cmd_profiles),
                "next_command_profiles": cmd_profiles,
            }
            if args.quiet:
                print(json.dumps(payload, ensure_ascii=True))
            else:
                print("ERROR: repo session state bootstrap failed")
                print(f"- bootstrap_status: {bootstrap_status}")
                print(f"- repo_fingerprint: {repo_fingerprint}")
            return 2

    workspace_lock = None
    if not args.skip_lock:
        try:
            workspace_lock = acquire_workspace_lock(
                workspaces_home=workspaces_home,
                repo_fingerprint=repo_fingerprint,
            )
        except TimeoutError:
            emit_gate_failure(
                gate="PERSISTENCE",
                code="WORKSPACE_LOCK_TIMEOUT",
                message="Workspace lock acquisition timed out.",
                expected="exclusive workspace lock acquired before write",
                observed={"repoFingerprint": repo_fingerprint, "workspacesHome": str(workspaces_home)},
                remediation="Wait for active run to finish or clear stale lock after verification, then rerun.",
            )
            cmd_profiles = render_command_profiles(
                [
                    python_cmd,
                    "governance/entrypoints/persist_workspace_artifacts.py",
                    "--repo-fingerprint",
                    repo_fingerprint,
                    "--config-root",
                    str(config_root),
                ]
            )
            payload = {
                "status": "blocked",
                "reason": "workspace lock timeout",
                "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
                "missing_evidence": ["exclusive workspace lock"],
                "recovery_steps": [
                    "wait for active run to finish or clear stale lock after verification",
                    "rerun workspace persistence helper",
                ],
                "required_operator_action": "acquire exclusive workspace lock before writing artifacts",
                "feedback_required": "reply with rerun result after lock contention is resolved",
                "next_command": _preferred_shell_command(cmd_profiles),
                "next_command_profiles": cmd_profiles,
            }
            if args.quiet:
                print(json.dumps(payload, ensure_ascii=True))
            else:
                print("ERROR: workspace lock timeout")
            return 2

    session = _read_repo_session(session_path)

    scope = session.get("Scope", {}) if isinstance(session, dict) else {}
    active_profile = session.get("ActiveProfile", "") if isinstance(session, dict) else ""
    profile_evidence = session.get("ProfileEvidence", "") if isinstance(session, dict) else ""
    repository_from_state = scope.get("Repository", "") if isinstance(scope, dict) else ""
    repository_type = scope.get("RepositoryType", "") if isinstance(scope, dict) else ""

    repo_name_raw = (
        args.repo_name
        or (repository_from_state if isinstance(repository_from_state, str) else "")
        or repo_root.name
    )
    repo_name = _sanitize_repo_name(repo_name_raw, repo_fingerprint)
    profile = active_profile if isinstance(active_profile, str) and active_profile else "unknown"
    profile_evidence_text = (
        profile_evidence if isinstance(profile_evidence, str) and profile_evidence else "unknown"
    )
    repository_type_text = (
        repository_type if isinstance(repository_type, str) and repository_type else "unknown"
    )

    today = datetime.now(timezone.utc).date().isoformat()
    today_compact = today.replace("-", "")

    cache_path = repo_home / "repo-cache.yaml"
    digest_path = repo_home / "repo-map-digest.md"
    decision_path = repo_home / "decision-pack.md"
    memory_path = repo_home / "workspace-memory.yaml"
    business_rules_path = repo_home / "business-rules.md"

    cache_content = _render_repo_cache(
        date=today,
        repo_name=repo_name,
        profile=profile,
        profile_evidence=profile_evidence_text,
        repository_type=repository_type_text,
    )
    digest_create = _render_repo_map_digest_create(
        date=today, repo_name=repo_name, repository_type=repository_type_text
    )
    digest_append = _repo_map_digest_section(today, repository_type_text)
    decision_create = _render_decision_pack_create(
        date=today, date_compact=today_compact, repo_name=repo_name
    )
    decision_append = _decision_pack_section(today, today_compact)
    memory_content = _render_workspace_memory(
        date=today, repo_name=repo_name, repo_fingerprint=repo_fingerprint
    )
    should_write_business_rules = _should_write_business_rules_inventory(session)
    business_rules_action = "not-applicable"
    business_rules_bootstrap_event = "not-emitted"
    if should_write_business_rules:
        try:
            business_rules_action = _upsert_artifact(
                path=business_rules_path,
                create_content=_render_business_rules_inventory(date=today, repo_name=repo_name),
                append_content=None,
                force=args.force,
                dry_run=args.dry_run,
                read_only=read_only,
            )
            if business_rules_action in {"created", "overwritten", "appended"}:
                business_rules_bootstrap_event = _append_jsonl_event(
                    repo_home / "events.jsonl",
                    {
                        "event": "business-rules-bootstrapped",
                        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "phase": "1.5-BusinessRules",
                        "repo_fingerprint": repo_fingerprint,
                        "status": "placeholder-created",
                        "target": str(business_rules_path),
                    },
                    dry_run=args.dry_run,
                    read_only=read_only,
                )
        except OSError as exc:
            business_rules_action = "write-requested"
            emit_gate_failure(
                gate="PERSISTENCE",
                code="BUSINESS_RULES_PERSIST_WRITE_FAILED",
                message="Business rules inventory persistence failed; write downgraded to write-requested.",
                expected="Business rules inventory persists to workspace target",
                observed={"target": str(business_rules_path), "error": str(exc)[:240]},
                remediation="Persist the same content manually to ${REPO_BUSINESS_RULES_FILE} and rerun helper.",
            )
            safe_log_error(
                reason_key="ERR-BUSINESS-RULES-PERSIST-WRITE-FAILED",
                message="Business rules inventory persistence failed; keeping canonical target with write-requested status.",
                config_root=config_root,
                phase="1.5-BusinessRules",
                gate="PERSISTENCE",
                mode="repo-aware",
                repo_fingerprint=repo_fingerprint,
                command="persist_workspace_artifacts.py",
                component="business-rules-persistence",
                observed_value={"target": str(business_rules_path), "error": str(exc)[:240]},
                expected_constraint="Business rules inventory persists to ${REPO_BUSINESS_RULES_FILE}",
                remediation="Persist the same content manually to ${REPO_BUSINESS_RULES_FILE} and rerun helper.",
            )

    actions = run_backfill(
        specs=[
            ArtifactSpec(
                key="repoCache",
                path=cache_path,
                create_content=cache_content,
            ),
            ArtifactSpec(
                key="repoMapDigest",
                path=digest_path,
                create_content=digest_create,
                append_content=digest_append,
            ),
            ArtifactSpec(
                key="decisionPack",
                path=decision_path,
                create_content=decision_create,
                append_content=decision_append,
            ),
            ArtifactSpec(
                key="workspaceMemory",
                path=memory_path,
                create_content=memory_content,
            ),
        ],
        force=args.force,
        dry_run=args.dry_run,
        read_only=read_only,
        write_text=lambda p, c: _write_text(p, c, dry_run=False, read_only=read_only),
        append_text=lambda p, c: _append_text(p, c, dry_run=False, read_only=read_only),
        normalize_existing=lambda p, d: _normalize_legacy_placeholder_phrasing(p, dry_run=d, read_only=read_only),
    )
    actions["businessRulesInventory"] = business_rules_action
    actions["businessRulesBootstrapEvent"] = business_rules_bootstrap_event
    decision_pack_normalization_event = "not-emitted"
    if actions.get("decisionPack") == "normalized":
        decision_pack_normalization_event = _append_jsonl_event(
            repo_home / "events.jsonl",
            {
                "event": "decision-pack-normalized-legacy-format",
                "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "phase": "2.1-DecisionPack",
                "repo_fingerprint": repo_fingerprint,
                "status": "normalized",
                "target": str(decision_path),
            },
            dry_run=args.dry_run,
            read_only=read_only,
        )
    actions["decisionPackNormalizationEvent"] = decision_pack_normalization_event

    phase_value = ""
    if isinstance(session, dict):
        raw_phase = session.get("Phase") or session.get("phase")
        if isinstance(raw_phase, str):
            phase_value = raw_phase
    phase_token = normalize_phase_token(phase_value)
    if phase_rank(phase_token) >= 0 and phase_rank(phase_token) < phase_rank("4") and decision_path.exists():
        decision_text = decision_path.read_text(encoding="utf-8", errors="replace")
        if has_legacy_decision_pack_ab_prompt(decision_text):
            emit_gate_failure(
                gate="PERSISTENCE",
                code="BLOCKED-LEGACY-DECISION-PACK-FORMAT",
                message="Legacy decision-pack A/B prompt format is not allowed before Phase 4.",
                expected="Status: automatic policy wording without interactive A/B choices",
                observed={"phase": phase_value or "unknown", "decisionPack": str(decision_path)},
                remediation="Normalize decision-pack content to automatic policy format and rerun persistence.",
                config_root=str(config_root),
                workspaces_home=str(workspaces_home),
                repo_fingerprint=repo_fingerprint,
                phase=phase_value or "2",
            )
            payload = {
                "status": "blocked",
                "reason": "legacy decision-pack format detected before phase 4",
                "reason_code": "BLOCKED-LEGACY-DECISION-PACK-FORMAT",
                "missing_evidence": ["normalized decision-pack automatic policy format"],
                "recovery_steps": [
                    "replace legacy A/B prompts in decision-pack.md with automatic policy format",
                    "rerun governance/entrypoints/persist_workspace_artifacts.py",
                ],
                "required_operator_action": "normalize decision-pack markdown to non-interactive format",
                "feedback_required": "reply with rerun result after normalization",
                "next_command": f"{python_cmd} governance/entrypoints/persist_workspace_artifacts.py --repo-fingerprint {repo_fingerprint} --config-root {config_root}",
            }
            if workspace_lock is not None:
                workspace_lock.release()
            if args.quiet:
                print(json.dumps(payload, ensure_ascii=True))
            else:
                print("ERROR: legacy decision-pack format detected before phase 4")
            return 2

    session_update = "skipped"
    if not args.no_session_update:
        session_update = _update_session_state(
            session_path=session_path,
            dry_run=args.dry_run,
            business_rules_inventory_written=(
                business_rules_action in {"created", "kept", "overwritten"}
            ),
            business_rules_inventory_action=business_rules_action,
            repo_cache_action=actions["repoCache"],
            repo_map_digest_action=actions["repoMapDigest"],
            decision_pack_action=actions["decisionPack"],
            workspace_memory_action=actions["workspaceMemory"],
            read_only=read_only,
        )
        if session_update == "invalid-session-shape":
            emit_gate_failure(
                gate="PERSISTENCE",
                code="SESSION_STATE_INVALID_SHAPE",
                message="Repo SESSION_STATE file exists but has invalid shape.",
                expected="SESSION_STATE root object must contain SESSION_STATE dict",
                observed={"sessionPath": str(session_path), "sessionUpdate": session_update},
                remediation="Repair repo-scoped SESSION_STATE and rerun backfill helper.",
            )
            safe_log_error(
                reason_key="ERR-SESSION-STATE-INVALID-SHAPE",
                message="Repo SESSION_STATE file exists but has invalid shape.",
                config_root=config_root,
                phase="2",
                gate="PERSISTENCE",
                mode="repo-aware",
                repo_fingerprint=repo_fingerprint,
                command="persist_workspace_artifacts.py",
                component="session-state-update",
                observed_value={"sessionPath": str(session_path), "sessionUpdate": session_update},
                expected_constraint="SESSION_STATE root object must contain SESSION_STATE dict",
                remediation="Repair repo-scoped SESSION_STATE and rerun backfill helper.",
            )

    phase2_artifacts_ok, phase2_missing = _verify_phase2_artifacts_exist(repo_home)

    if not phase2_artifacts_ok and not args.dry_run and not read_only:
        emit_gate_failure(
            gate="PERSISTENCE",
            code="PHASE2_ARTIFACTS_MISSING_DETECTED",
            message="Phase 2 discovery did not write required artifacts.",
            expected="repo-cache.yaml, repo-map-digest.md, workspace-memory.yaml must exist",
            observed={"missing": phase2_missing, "repo_home": str(repo_home)},
            remediation="Re-run persist_workspace_artifacts.py with --force to recreate missing artifacts.",
        )
        safe_log_error(
            reason_key="ERR-PHASE2-ARTIFACTS-MISSING",
            message="Phase 2 discovery did not write required artifacts.",
            config_root=config_root,
            phase="2",
            gate="PERSISTENCE",
            mode="repo-aware",
            repo_fingerprint=repo_fingerprint,
            command="persist_workspace_artifacts.py",
            component="phase2-artifacts-verification",
            observed_value={"missing": phase2_missing, "repo_home": str(repo_home)},
            expected_constraint="repo-cache.yaml, repo-map-digest.md, workspace-memory.yaml must exist",
            remediation="Re-run persist_workspace_artifacts.py with --force to recreate missing artifacts.",
        )

    summary = {
        "status": "ok" if phase2_artifacts_ok else "degraded",
        "configRoot": str(config_root),
        "bindingEvidence": str(binding_file),
        "repoFingerprint": repo_fingerprint,
        "fingerprintSource": fp_source,
        "fingerprintEvidence": fp_evidence,
        "runId": workspace_lock.lock_id if workspace_lock is not None else "none",
        "repoHome": str(repo_home),
        "actions": actions,
        "sessionUpdate": session_update,
        "bootstrapSessionState": bootstrap_status,
        "phase2Artifacts": {
            "ok": phase2_artifacts_ok,
            "missing": phase2_missing,
        },
        "repo_root_detected": str(repo_root),
        "repo_root_source": repo_root_source,
        "git_probe": git_probe,
        "cwd": str(Path.cwd()),
    }

    if args.quiet:
        print(json.dumps(summary, ensure_ascii=True))
    else:
        print(f"Config root: {config_root}")
        print(f"Repo root: {repo_root}")
        print(f"Repo fingerprint: {repo_fingerprint}")
        print(f"Fingerprint source: {fp_source}")
        print(f"Fingerprint evidence: {fp_evidence}")
        print(f"Repo home: {repo_home}")
        for key, action in actions.items():
            print(f"- {key}: {action}")
        print(f"- sessionUpdate: {session_update}")

    if workspace_lock is not None:
        workspace_lock.release()
    
    if args.require_phase2 and not phase2_artifacts_ok and not args.dry_run:
        if read_only:
            emit_gate_failure(
                gate="PERSISTENCE",
                code="PERSISTENCE_READ_ONLY",
                message="Required Phase 2/2.1 artifacts missing but writes are blocked (READ_ONLY).",
                expected="writes allowed and artifacts created/updated",
                observed={"read_only": True, "missing": phase2_missing},
                remediation="Remove OPENCODE_FORCE_READ_ONLY or allow governance writes in user mode.",
            )
            return 2
        emit_gate_failure(
            gate="PERSISTENCE",
            code="PHASE2_ARTIFACTS_MISSING",
            message="Required Phase 2/2.1 artifacts missing after backfill.",
            expected="repo-cache.yaml, repo-map-digest.md, workspace-memory.yaml, decision-pack.md must exist under workspace home",
            observed={"missing": phase2_missing},
            remediation="Inspect artifact actions and fix write/paths/permissions.",
        )
        return 7
    
    if not phase2_artifacts_ok and not args.dry_run and not read_only:
        emit_gate_failure(
            gate="PERSISTENCE",
            code="PHASE2_ARTIFACTS_INCOMPLETE",
            message="Phase 2 artifacts incomplete after persistence run.",
            expected="Required Phase 2 artifacts exist",
            observed={"missing": phase2_missing},
            remediation="Run persistence backfill with writes enabled and inspect artifact actions.",
        )
        return 7
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
