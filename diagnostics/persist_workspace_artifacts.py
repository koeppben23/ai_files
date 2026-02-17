#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from error_logs import safe_log_error
except Exception:  # pragma: no cover
    def safe_log_error(**kwargs):  # type: ignore[no-redef]
        return {"status": "log-disabled"}

from workspace_lock import acquire_workspace_lock
from command_profiles import render_command_profiles


def default_config_root() -> Path:
    return (Path.home().resolve() / ".config" / "opencode").resolve()


def _normalize_absolute_path(raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw).expanduser()
    token = raw.strip()
    if os.name == "nt" and re.match(r"^[A-Za-z]:[^/\\]", token):
        return None
    if not candidate.is_absolute():
        return None
    normalized = os.path.normpath(os.path.abspath(str(candidate)))
    return Path(normalized)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_binding_paths(paths_file: Path, *, expected_config_root: Path | None = None) -> tuple[Path, dict[str, Any]]:
    payload = _load_json(paths_file)
    if not payload:
        raise ValueError(f"binding evidence unreadable: {paths_file}")
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"binding evidence invalid: missing paths object in {paths_file}")
    config_root_raw = paths.get("configRoot")
    workspaces_raw = paths.get("workspacesHome")
    if not isinstance(config_root_raw, str) or not config_root_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.configRoot missing in {paths_file}")
    if not isinstance(workspaces_raw, str) or not workspaces_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.workspacesHome missing in {paths_file}")
    config_root = _normalize_absolute_path(config_root_raw)
    _workspaces_home = _normalize_absolute_path(workspaces_raw)
    if config_root is None:
        raise ValueError(f"binding evidence invalid: paths.configRoot must be absolute in {paths_file}")
    if _workspaces_home is None:
        raise ValueError(f"binding evidence invalid: paths.workspacesHome must be absolute in {paths_file}")
    if expected_config_root is not None and config_root != expected_config_root.resolve():
        raise ValueError("binding evidence mismatch: config root does not match explicit input")
    return config_root, paths


def _resolve_python_command(paths: dict[str, Any]) -> str:
    raw = paths.get("pythonCommand")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "py -3" if os.name == "nt" else "python3"


def _preferred_shell_command(profiles: dict[str, object]) -> str:
    if os.name == "nt":
        return str(profiles.get("powershell") or profiles.get("cmd") or profiles.get("bash") or "")
    return str(profiles.get("bash") or profiles.get("json") or "")


def resolve_binding_config(explicit: Path | None) -> tuple[Path, dict[str, Any], Path]:
    if explicit is not None:
        root = explicit.expanduser().resolve()
        candidate = root / "commands" / "governance.paths.json"
        config_root, paths = _load_binding_paths(candidate, expected_config_root=root)
        return config_root, paths, candidate

    env_value = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_value:
        root = Path(env_value).expanduser().resolve()
        candidate = root / "commands" / "governance.paths.json"
        config_root, paths = _load_binding_paths(candidate, expected_config_root=root)
        return config_root, paths, candidate

    script_path = Path(__file__).resolve()
    diagnostics_dir = script_path.parent
    if diagnostics_dir.name == "diagnostics" and diagnostics_dir.parent.name == "commands":
        candidate = diagnostics_dir.parent / "governance.paths.json"
        config_root, paths = _load_binding_paths(candidate)
        return config_root, paths, candidate

    fallback = default_config_root().resolve()
    candidate = fallback / "commands" / "governance.paths.json"
    config_root, paths = _load_binding_paths(candidate, expected_config_root=fallback)
    return config_root, paths, candidate


def _validate_repo_fingerprint(value: str) -> str:
    token = value.strip()
    if not token:
        raise ValueError("repo fingerprint must not be empty")
    if not re.fullmatch(r"[A-Za-z0-9._-]{6,128}", token):
        raise ValueError(
            "repo fingerprint must match [A-Za-z0-9._-]{6,128} (no slashes, spaces, or traversal)"
        )
    return token


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
            candidate = (repo_root / candidate).resolve()
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
    if parsed.port:
        host = f"{host}:{parsed.port}"

    path = parsed.path.replace("\\", "/")
    path = re.sub(r"/+", "/", path).strip()
    if not path:
        return None
    if not path.startswith("/"):
        path = f"/{path}"
    if path.lower().endswith(".git"):
        path = path[:-4]
    path = path.rstrip("/")
    if not path:
        return None
    path = path.casefold()

    return f"repo://{host}{path}"


def _normalize_path_for_fingerprint(path: Path) -> str:
    """Normalize filesystem paths for deterministic cross-platform fingerprints."""

    absolute = Path(os.path.abspath(str(path.expanduser())))
    normalized = os.path.normpath(str(absolute))
    return normalized.replace("\\", "/").casefold()


def _derive_fingerprint_from_repo(repo_root: Path) -> tuple[str, str] | None:
    root = repo_root.expanduser().resolve()
    git_dir = _resolve_git_dir(root)
    if not git_dir:
        return None

    remote = _read_origin_remote(git_dir / "config")
    canonical_remote = _canonicalize_origin_remote(remote) if remote else None
    if canonical_remote:
        material = f"repo:{canonical_remote}"
    else:
        material = f"repo:local:{_normalize_path_for_fingerprint(root)}"
    fp = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return fp, material


def _resolve_repo_fingerprint(
    config_root: Path,
    explicit: str | None,
    repo_root: Path,
) -> tuple[str, str, str]:
    if explicit:
        return _validate_repo_fingerprint(explicit), "explicit", "operator-provided"

    derived = _derive_fingerprint_from_repo(repo_root)
    if derived:
        fp, material = derived
        return _validate_repo_fingerprint(fp), "git-metadata", material

    pointer_path = config_root / "SESSION_STATE.json"
    pointer = _load_json(pointer_path)
    if pointer and pointer.get("schema") == "opencode-session-pointer.v1":
        fp = pointer.get("activeRepoFingerprint")
        if isinstance(fp, str) and fp.strip():
            return _validate_repo_fingerprint(fp), "pointer", "global-pointer-fallback"

    raise ValueError(
        "repo fingerprint is required (use --repo-fingerprint), or run from a git repo root, or ensure global SESSION_STATE pointer exists"
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


def _repo_map_digest_section(date: str, repository_type: str) -> str:
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


def _render_repo_map_digest_create(*, date: str, repo_name: str, repository_type: str) -> str:
    section = _repo_map_digest_section(date, repository_type)
    return (
        "# Repo Map Digest\n"
        f"Repo: {repo_name}\n"
        f"LastUpdated: {date}\n\n"
        f"{section}"
    )


def _decision_pack_section(date: str, date_compact: str) -> str:
    return "\n".join(
        [
            f"## Decision Pack — {date}",
            "D-001: Run Phase 1.5 (Business Rules Discovery) now?",
            f"ID: DP-{date_compact}-001",
            "Status: proposed",
            "A) Yes",
            "B) No",
            "Recommendation: A (run lightweight Phase 1.5 to establish initial domain evidence)",
            "Evidence: Bootstrap seed context; lightweight discovery can improve downstream gate quality",
            "What would change it: keep B only when operator explicitly defers business-rules discovery",
            "",
        ]
    )


def _render_decision_pack_create(*, date: str, date_compact: str, repo_name: str) -> str:
    section = _decision_pack_section(date, date_compact)
    return (
        "# Decision Pack\n"
        f"Repo: {repo_name}\n"
        f"LastUpdated: {date}\n\n"
        f"{section}"
    )


def _render_workspace_memory(*, date: str, repo_name: str, repo_fingerprint: str) -> str:
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

    return business_rules_scope == "extracted"


def _render_business_rules_inventory(*, date: str, repo_name: str) -> str:
    return "\n".join(
        [
            f"# Business Rules Inventory — {repo_name}",
            "",
            "SchemaVersion: BRINV-1",
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


def _write_text(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, content)


def _append_text(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        existing = path.read_text(encoding="utf-8", errors="replace")
    if not existing.endswith("\n"):
        existing += "\n"
    existing += "\n" + content
    _atomic_write_text(path, existing)


def _is_retryable_replace_error(exc: OSError) -> bool:
    return exc.errno in {errno.EACCES, errno.EPERM, errno.EBUSY}


def _atomic_write_text(path: Path, content: str, retries: int = 3) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)

        for attempt in range(retries):
            try:
                os.replace(str(temp_path), str(path))
                return
            except OSError as exc:
                if attempt == retries - 1 or not _is_retryable_replace_error(exc):
                    raise
                time.sleep(0.05)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _normalize_legacy_placeholder_phrasing(path: Path, *, dry_run: bool) -> bool:
    if not path.exists() or not path.is_file():
        return False

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    replacements = {
        "Backfill placeholder: refresh after Phase 2 discovery.": "Seed snapshot: refresh after evidence-backed Phase 2 discovery.",
        "none (backfill placeholder)": "none (no evidence-backed digest yet)",
        "Backfill placeholder; refresh after evidence-backed Phase 2 discovery.": "Seed snapshot; refresh after evidence-backed Phase 2 discovery.",
        "Evidence: Backfill initialization only; no fresh Phase 2 domain extraction attached": "Evidence: Bootstrap seed only; no fresh Phase 2 domain extraction attached",
    }

    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)

    if updated == text:
        return False

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return True


def _upsert_artifact(
    *,
    path: Path,
    create_content: str,
    append_content: str | None,
    force: bool,
    dry_run: bool,
) -> str:
    if not path.exists():
        _write_text(path, create_content, dry_run=dry_run)
        return "created"

    normalized = _normalize_legacy_placeholder_phrasing(path, dry_run=dry_run)

    if not force:
        if normalized:
            return "normalized"
        return "kept"

    if append_content is not None:
        _append_text(path, append_content, dry_run=dry_run)
        return "appended"

    _write_text(path, create_content, dry_run=dry_run)
    return "overwritten"


def _update_session_state(
    *,
    session_path: Path,
    dry_run: bool,
    business_rules_inventory_written: bool,
    business_rules_inventory_action: str,
) -> str:
    data = _load_json(session_path)
    if not data:
        return "no-session-file"
    ss = data.get("SESSION_STATE")
    if not isinstance(ss, dict):
        return "invalid-session-shape"

    ss.setdefault("RepoCacheFile", {})
    if isinstance(ss["RepoCacheFile"], dict):
        ss["RepoCacheFile"]["TargetPath"] = "${REPO_CACHE_FILE}"
        ss["RepoCacheFile"]["FileStatus"] = "written"

    ss.setdefault("RepoMapDigestFile", {})
    if isinstance(ss["RepoMapDigestFile"], dict):
        ss["RepoMapDigestFile"]["FilePath"] = "${REPO_DIGEST_FILE}"
        ss["RepoMapDigestFile"]["FileStatus"] = "written"

    ss.setdefault("DecisionPack", {})
    if isinstance(ss["DecisionPack"], dict):
        ss["DecisionPack"]["FilePath"] = "${REPO_DECISION_PACK_FILE}"
        ss["DecisionPack"]["FileStatus"] = "written"

    ss.setdefault("WorkspaceMemoryFile", {})
    if isinstance(ss["WorkspaceMemoryFile"], dict):
        ss["WorkspaceMemoryFile"]["TargetPath"] = "${WORKSPACE_MEMORY_FILE}"
        ss["WorkspaceMemoryFile"]["FileStatus"] = "written"

    scope = ss.get("Scope")
    business_rules_scope = ""
    if isinstance(scope, dict):
        raw = scope.get("BusinessRules")
        if isinstance(raw, str):
            business_rules_scope = raw.strip().lower()

    if business_rules_scope == "extracted" or business_rules_inventory_written:
        ss.setdefault("BusinessRules", {})
        if isinstance(ss["BusinessRules"], dict):
            inventory = ss["BusinessRules"]
            inventory["InventoryFilePath"] = "${REPO_BUSINESS_RULES_FILE}"
            inventory["InventoryFileStatus"] = "written" if business_rules_inventory_written else "write-requested"
            if business_rules_inventory_action == "created":
                inventory["InventoryFileMode"] = "create"
            elif business_rules_inventory_action in {"overwritten", "kept"}:
                inventory["InventoryFileMode"] = "update"
            else:
                inventory.setdefault("InventoryFileMode", "unknown")

    if dry_run:
        return "updated-dry-run"

    session_payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    _atomic_write_text(session_path, session_payload)
    return "updated"


def _bootstrap_missing_session_state(
    *,
    config_root: Path,
    repo_fingerprint: str,
    repo_name: str,
    python_cmd: str,
    dry_run: bool,
) -> tuple[bool, str]:
    """Ensure repo-scoped SESSION_STATE exists before persistence update."""

    if dry_run:
        return True, "bootstrap-dry-run"

    helper = Path(__file__).resolve().parent / "bootstrap_session_state.py"
    if not helper.exists():
        return False, "missing-bootstrap-helper"

    python_argv = shlex.split(python_cmd, posix=(os.name != "nt")) or [python_cmd]
    cmd = [
        *python_argv,
        str(helper),
        "--repo-fingerprint",
        repo_fingerprint,
        "--repo-name",
        repo_name,
        "--config-root",
        str(config_root),
        "--skip-artifact-backfill",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
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
        default=Path("."),
        help="Repository root for deterministic fingerprint derivation from .git metadata.",
    )
    p.add_argument("--repo-name", default="", help="Optional repository display name.")
    p.add_argument("--config-root", type=Path, default=None, help="Override OpenCode config root.")
    p.add_argument("--force", action="store_true", help="Overwrite YAML artifacts and append markdown sections when artifacts already exist.")
    p.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files.")
    p.add_argument("--no-session-update", action="store_true", help="Do not update repo-scoped SESSION_STATE file pointers/status fields.")
    p.add_argument("--quiet", action="store_true", help="Print compact JSON summary only.")
    p.add_argument("--skip-lock", action="store_true", help="Internal use: skip workspace lock acquisition.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config_root, binding_paths, binding_file = resolve_binding_config(args.config_root)
    except ValueError as exc:
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
            "next_command": "${PYTHON_COMMAND} diagnostics/persist_workspace_artifacts.py --config-root <config_root>",
            "next_command_profiles": render_command_profiles(
                [
                    "${PYTHON_COMMAND}",
                    "diagnostics/persist_workspace_artifacts.py",
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
    repo_root = args.repo_root.expanduser().resolve()

    if (repo_root / ".git").exists() and _is_within(config_root, repo_root):
        cmd_profiles = render_command_profiles(
            [
                python_cmd,
                "diagnostics/persist_workspace_artifacts.py",
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
                    "diagnostics/persist_workspace_artifacts.py",
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

    workspaces_home = Path(str(binding_paths.get("workspacesHome", ""))).expanduser().resolve()
    repo_home = workspaces_home / repo_fingerprint
    session_path = repo_home / "SESSION_STATE.json"
    bootstrap_status = "not-required"
    if not args.no_session_update and not session_path.exists():
        bootstrap_ok, bootstrap_status = _bootstrap_missing_session_state(
            config_root=config_root,
            repo_fingerprint=repo_fingerprint,
            repo_name=args.repo_name or repo_root.name or repo_fingerprint,
            python_cmd=python_cmd,
            dry_run=args.dry_run,
        )
        if not bootstrap_ok:
            cmd_profiles = render_command_profiles(
                [
                    python_cmd,
                    "diagnostics/bootstrap_session_state.py",
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
                    "run diagnostics/bootstrap_session_state.py with --repo-fingerprint and --config-root",
                    "rerun diagnostics/persist_workspace_artifacts.py after bootstrap succeeds",
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
            cmd_profiles = render_command_profiles(
                [
                    python_cmd,
                    "diagnostics/persist_workspace_artifacts.py",
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
    if should_write_business_rules:
        try:
            business_rules_action = _upsert_artifact(
                path=business_rules_path,
                create_content=_render_business_rules_inventory(date=today, repo_name=repo_name),
                append_content=None,
                force=args.force,
                dry_run=args.dry_run,
            )
        except OSError as exc:
            business_rules_action = "write-requested"
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

    actions = {
        "repoCache": _upsert_artifact(
            path=cache_path,
            create_content=cache_content,
            append_content=None,
            force=args.force,
            dry_run=args.dry_run,
        ),
        "repoMapDigest": _upsert_artifact(
            path=digest_path,
            create_content=digest_create,
            append_content=digest_append,
            force=args.force,
            dry_run=args.dry_run,
        ),
        "decisionPack": _upsert_artifact(
            path=decision_path,
            create_content=decision_create,
            append_content=decision_append,
            force=args.force,
            dry_run=args.dry_run,
        ),
        "workspaceMemory": _upsert_artifact(
            path=memory_path,
            create_content=memory_content,
            append_content=None,
            force=args.force,
            dry_run=args.dry_run,
        ),
        "businessRulesInventory": business_rules_action,
    }

    session_update = "skipped"
    if not args.no_session_update:
        session_update = _update_session_state(
            session_path=session_path,
            dry_run=args.dry_run,
            business_rules_inventory_written=(
                business_rules_action in {"created", "kept", "overwritten"}
            ),
            business_rules_inventory_action=business_rules_action,
        )
        if session_update == "invalid-session-shape":
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

    summary = {
        "status": "ok",
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
