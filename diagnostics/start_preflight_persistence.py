#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

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
        return normalized.replace("\\", "/").casefold()

from command_profiles import render_command_profiles
try:
    from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver as BindingEvidenceResolver  # type: ignore[assignment]
except Exception:
    from dataclasses import dataclass
    from typing import Mapping

    @dataclass(frozen=True)
    class _BindingEvidenceFallback:
        commands_home: Path
        workspaces_home: Path
        governance_paths_json: Path | None
        binding_ok: bool

    class _FallbackBindingEvidenceResolver:
        def __init__(self, *, env: Mapping[str, str] | None = None, config_root: Path | None = None):
            self._env = env if env is not None else os.environ
            self._config_root = config_root if config_root is not None else canonical_config_root()

        def resolve(self, *, mode: str = "user", host_caps=None):
            _ = mode
            _ = host_caps
            commands_home = self._config_root / "commands"
            workspaces_home = self._config_root / "workspaces"
            binding_file = commands_home / "governance.paths.json"
            if not binding_file.exists():
                return _BindingEvidenceFallback(commands_home, workspaces_home, None, False)
            try:
                payload = json.loads(binding_file.read_text(encoding="utf-8"))
                paths = payload.get("paths") if isinstance(payload, dict) else None
                if not isinstance(paths, dict):
                    raise ValueError("paths missing")
                commands_home = normalize_absolute_path(str(paths.get("commandsHome", "")), purpose="paths.commandsHome")
                workspaces_home = normalize_absolute_path(str(paths.get("workspacesHome", "")), purpose="paths.workspacesHome")
                return _BindingEvidenceFallback(commands_home, workspaces_home, binding_file, True)
            except Exception:
                return _BindingEvidenceFallback(commands_home, workspaces_home, binding_file, False)

    BindingEvidenceResolver = _FallbackBindingEvidenceResolver  # type: ignore[assignment]

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


def config_root() -> Path:
    return canonical_config_root()


def _resolve_bound_paths(root: Path) -> tuple[Path, Path, bool, Path | None]:
    mode = str(os.getenv("OPENCODE_OPERATING_MODE", "user") or "user")
    evidence = BindingEvidenceResolver(env=os.environ, config_root=root).resolve(mode=mode)
    return evidence.commands_home, evidence.workspaces_home, evidence.binding_ok, evidence.governance_paths_json


ROOT = config_root()
COMMANDS_RUNTIME_DIR, WORKSPACES_HOME, BINDING_OK, BINDING_EVIDENCE_PATH = _resolve_bound_paths(ROOT)
DIAGNOSTICS_DIR = COMMANDS_RUNTIME_DIR / "diagnostics"
PERSIST_HELPER = DIAGNOSTICS_DIR / "persist_workspace_artifacts.py"
BOOTSTRAP_HELPER = DIAGNOSTICS_DIR / "bootstrap_session_state.py"
LOGGER = DIAGNOSTICS_DIR / "error_logs.py"
TOOL_CATALOG = DIAGNOSTICS_DIR / "tool_requirements.json"

if str(COMMANDS_RUNTIME_DIR) not in sys.path and COMMANDS_RUNTIME_DIR.exists():
    sys.path.insert(0, str(COMMANDS_RUNTIME_DIR))

# Contract compatibility notes for governance specs:
# - legacy probe mode may use --no-session-update
# - historical reason key reference: ERR-WORKSPACE-PERSISTENCE-MISSING-IDENTITY-MAP


def workspace_identity_map(repo_fp: str) -> Path:
    return WORKSPACES_HOME / repo_fp / "repo-identity-map.yaml"


def legacy_identity_map() -> Path:
    return ROOT / "repo-identity-map.yaml"


def identity_map_exists(repo_fp: str | None) -> bool:
    if repo_fp:
        if workspace_identity_map(repo_fp).exists():
            return True
    return legacy_identity_map().exists()


def resolve_repo_context() -> tuple[Path | None, str]:
    def _search_repo_root(start: Path) -> Path | None:
        try:
            candidate = normalize_absolute_path(str(start), purpose="repo_search_start")
        except Exception:
            return None
        for probe in (candidate, *candidate.parents):
            git_path = probe / ".git"
            if git_path.is_dir() or git_path.is_file():
                return probe
        return None

    env_candidates = [
        ("OPENCODE_REPO_ROOT", os.getenv("OPENCODE_REPO_ROOT")),
        ("OPENCODE_WORKSPACE_ROOT", os.getenv("OPENCODE_WORKSPACE_ROOT")),
        ("REPO_ROOT", os.getenv("REPO_ROOT")),
        ("GITHUB_WORKSPACE", os.getenv("GITHUB_WORKSPACE")),
    ]
    for key, candidate in env_candidates:
        if not candidate:
            continue
        try:
            path = normalize_absolute_path(str(candidate), purpose=f"env:{key}")
        except Exception:
            continue
        if not path.exists():
            continue
        repo_root = _search_repo_root(path)
        if repo_root is not None:
            return repo_root, f"env:{key}"
    cwd_path = normalize_absolute_path(str(Path.cwd()), purpose="cwd")
    cwd_repo_root = _search_repo_root(cwd_path)
    if cwd_repo_root is not None:
        return cwd_repo_root, "cwd_parent_walk"
    return None, "cwd"


def resolve_repo_root() -> Path | None:
    repo_root, _method = resolve_repo_context()
    return repo_root


def pointer_fingerprint() -> str | None:
    pointer = load_json(ROOT / "SESSION_STATE.json")
    if not isinstance(pointer, dict):
        return None
    if pointer.get("schema") != "opencode-session-pointer.v1":
        return None
    fp = pointer.get("activeRepoFingerprint")
    if isinstance(fp, str) and fp.strip():
        return fp.strip()
    return None


def load_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def resolve_python_command() -> str:
    payload = load_json(COMMANDS_RUNTIME_DIR / "governance.paths.json")
    if isinstance(payload, dict):
        paths = payload.get("paths")
        if isinstance(paths, dict):
            raw = paths.get("pythonCommand")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return "py -3" if os.name == "nt" else "python3"


def resolve_git_dir(repo_root: Path) -> Path | None:
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git
    if not dot_git.is_file():
        return None

    try:
        text = dot_git.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = dot_git.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"gitdir:\s*(.+)", text)
    if not match:
        return None
    candidate = Path(match.group(1).strip())
    if not candidate.is_absolute():
        candidate = normalize_absolute_path(str(repo_root / candidate), purpose="gitdir_relative")
    return candidate if candidate.exists() else None


def read_origin_remote(config_path: Path) -> str | None:
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
        if not in_origin:
            continue
        match = re.match(r"url\s*=\s*(.+)", stripped)
        if match:
            return match.group(1).strip()
    return None


def _canonicalize_origin_remote(remote: str) -> str | None:
    return canonicalize_origin_url(remote)


def _normalize_path_for_fingerprint(path: Path) -> str:
    """Normalize filesystem paths for deterministic cross-platform fingerprints."""

    return normalize_for_fingerprint(path)


def derive_repo_fingerprint(repo_root: Path) -> str | None:
    normalized_root = Path(os.path.normpath(os.path.abspath(str(repo_root.expanduser()))))
    git_dir = resolve_git_dir(normalized_root)
    if not git_dir:
        return None

    origin = read_origin_remote(git_dir / "config")
    canonical_origin = _canonicalize_origin_remote(origin) if origin else None
    identity = derive_repo_identity(normalized_root, canonical_remote=canonical_origin, git_dir=git_dir)
    return identity.fingerprint


def _discover_repo_session_id() -> str:
    candidate = str(os.getenv("OPENCODE_SESSION_ID", "")).strip()
    if candidate:
        return candidate
    cwd = normalize_absolute_path(str(Path.cwd()), purpose="session_id_cwd")
    return hashlib.sha256(str(cwd).encode("utf-8")).hexdigest()[:16]


def _python_command_argv() -> list[str]:
    token = str(PYTHON_COMMAND or "").strip()
    if not token:
        return ["python3"]
    if token == "py -3":
        return ["py", "-3"]
    if token == "python -3":
        return ["python", "-3"]
    return [token]


def _repo_context_index_path(repo_root: Path) -> Path:
    normalized_root = _normalize_path_for_fingerprint(repo_root)
    key = hashlib.sha256(normalized_root.encode("utf-8")).hexdigest()[:24]
    return WORKSPACES_HOME / "index" / key / "repo-context.json"


def read_repo_context_fingerprint(repo_root: Path) -> str | None:
    index_path = _repo_context_index_path(repo_root)
    payload = load_json(index_path)
    if not isinstance(payload, dict):
        return None
    expected_root = _normalize_path_for_fingerprint(repo_root)
    observed_root = str(payload.get("repo_root") or "").strip()
    if observed_root != expected_root:
        return None
    fp = str(payload.get("repo_fingerprint") or "").strip()
    return fp or None


def _atomic_write_text(path: Path, text: str) -> None:
    attempts = 8 if os.name == "nt" else 2
    atomic_write_text(path, text, newline_lf=True, attempts=attempts, backoff_ms=50)


def _write_repo_context_payload(payload: dict, relative_target: str, repo_root: Path, repo_fingerprint: str) -> bool:
    try:
        if not repo_fingerprint.strip():
            return False
        target = WORKSPACES_HOME / relative_target
        workspace_dir = WORKSPACES_HOME / repo_fingerprint
        workspace_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
        _atomic_write_text(target, text)
        index = _repo_context_index_path(repo_root)
        _atomic_write_text(index, text)
        return True
    except Exception as exc:
        log_error(
            "ERR-REPO-CONTEXT-WRITE-FAILED",
            "Failed to persist repo-context evidence.",
            {"target": relative_target, "error": str(exc)[:240]},
        )
        return False


def write_repo_context(repo_root: Path, repo_fingerprint: str, discovery_method: str) -> bool:
    try:
        fingerprint = str(repo_fingerprint).strip()
        if not fingerprint:
            return False
        payload = {
            "schema": "repo-context.v1",
            "session_id": _discover_repo_session_id(),
            "repo_root": _normalize_path_for_fingerprint(repo_root),
            "repo_fingerprint": fingerprint,
            "discovered_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "discovery_method": discovery_method,
            "binding_evidence_path": str(BINDING_EVIDENCE_PATH) if BINDING_EVIDENCE_PATH is not None else "",
            "commands_home": str(COMMANDS_RUNTIME_DIR),
        }
        return _write_repo_context_payload(payload, f"{fingerprint}/repo-context.json", repo_root, fingerprint)
    except Exception:
        return False


PYTHON_COMMAND = resolve_python_command()


def bootstrap_command(repo_fp: str | None) -> str:
    return _preferred_shell_command(render_command_profiles(bootstrap_command_argv(repo_fp)))


def bootstrap_command_argv(repo_fp: str | None) -> list[str]:
    python_argv = _python_command_argv()
    if repo_fp:
        return [*python_argv, str(BOOTSTRAP_HELPER), "--repo-fingerprint", repo_fp, "--config-root", str(ROOT)]
    return [*python_argv, str(BOOTSTRAP_HELPER), "--repo-fingerprint", "<repo_fingerprint>", "--config-root", str(ROOT)]


def persist_command(repo_root: Path) -> str:
    return _preferred_shell_command(render_command_profiles(persist_command_argv(repo_root)))


def persist_command_argv(repo_root: Path) -> list[str]:
    python_argv = _python_command_argv()
    return [*python_argv, str(PERSIST_HELPER), "--repo-root", str(repo_root)]


def _command_available(command: str) -> bool:
    """Return command availability with canonical alias handling."""

    if command in {"python", "python3", "py", "py -3"}:
        return (
            shutil.which("python") is not None
            or shutil.which("python3") is not None
            or shutil.which("py") is not None
        )
    token = str(command or "").strip()
    if token == "py -3":
        parts = ["py", "-3"]
    elif token == "python -3":
        parts = ["python", "-3"]
    else:
        parts = [token] if token else []
    if not parts:
        return False
    return shutil.which(parts[0]) is not None


def _preferred_shell_command(profiles: dict[str, object]) -> str:
    if os.name == "nt":
        return str(profiles.get("powershell") or profiles.get("cmd") or profiles.get("bash") or "")
    return str(profiles.get("bash") or profiles.get("json") or "")


def _expand_command_placeholders(command: str) -> str:
    return command.replace("${PYTHON_COMMAND}", PYTHON_COMMAND)


def _windows_longpaths_enabled() -> bool | None:
    if platform.system() != "Windows":
        return None
    for scope in ("--system", "--global"):
        proc = subprocess.run(
            ["git", "config", scope, "--get", "core.longpaths"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip().lower() in {"true", "1", "yes", "on"}:
            return True
    return False


def _git_safe_directory_issue() -> bool:
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        text=True,
        capture_output=True,
        check=False,
    )
    stderr = (probe.stderr or "").lower()
    return "safe.directory" in stderr


def emit_preflight() -> None:
    now = subprocess.run(
        [
            sys.executable,
            "-c",
            "from datetime import datetime,timezone;print(datetime.now(timezone.utc).isoformat(timespec='seconds'))",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    observed = (now.stdout or "").strip() or "unknown"
    catalog = load_json(TOOL_CATALOG) if TOOL_CATALOG.exists() else None

    required_now: list[str] = []
    required_later: list[str] = []
    metadata: dict[str, dict[str, str]] = {}
    if isinstance(catalog, dict):
        for item in catalog.get("required_now", []):
            if not isinstance(item, dict):
                continue
            command = str(item.get("command") or "").strip()
            command = _expand_command_placeholders(command)
            if not command:
                continue
            if command not in required_now:
                required_now.append(command)
            metadata[command] = {
                "verify_command": _expand_command_placeholders(
                    str(item.get("verify_command") or (command + " --version"))
                ),
                "expected_after_fix": str(
                    _expand_command_placeholders(
                        str(item.get("expected_after_fix") or (command + " --version prints a version string"))
                    )
                ),
                "restart_hint": str(item.get("restart_hint") or "restart_required_if_path_edited"),
            }
        for item in catalog.get("required_later", []):
            if not isinstance(item, dict):
                continue
            command = str(item.get("command") or "").strip()
            command = _expand_command_placeholders(command)
            if command and command not in required_later and command not in required_now:
                required_later.append(command)

    if not required_now:
        required_now = ["git", PYTHON_COMMAND]

    available: list[str] = []
    missing: list[str] = []
    missing_details: list[dict[str, str]] = []

    for command in required_now:
        if _command_available(command):
            available.append(command)
        else:
            missing.append(command)
            meta = metadata.get(command, {})
            missing_details.append(
                {
                    "command": command,
                    "verify_command": _expand_command_placeholders(
                        meta.get("verify_command", command + " --version")
                    ),
                    "expected_after_fix": meta.get(
                        "expected_after_fix",
                        _expand_command_placeholders(command + " --version prints a version string"),
                    ),
                    "restart_hint": meta.get("restart_hint", "restart_required_if_path_edited"),
                }
            )

    missing_later = [command for command in required_later if not _command_available(command)]
    longpaths_state = _windows_longpaths_enabled()
    longpaths_note = "not_applicable"
    if longpaths_state is True:
        longpaths_note = "enabled"
    elif longpaths_state is False:
        longpaths_note = "disabled"
    git_safe_directory_blocked = _git_safe_directory_issue() if _command_available("git") else False

    status = "ok" if not missing else "degraded"
    block_now = bool(missing)
    if not BINDING_OK:
        status = "degraded"
        block_now = True
    impact = (
        "required_now commands satisfied; required_later tools are advisory until their gate"
        if status == "ok"
        else "missing required_now commands may block immediate bootstrap gates"
    )
    nxt = (
        "continue bootstrap"
        if status == "ok"
        else "install missing required_now tools or provide equivalent operator evidence"
    )
    print(
        json.dumps(
            {
                "preflight": status,
                "observed_at": observed,
                "required_now": required_now,
                "required_later": required_later,
                "available": available,
                "missing": missing,
                "missing_later": missing_later,
                "block_now": block_now,
                "impact": impact,
                "next": nxt,
                "missing_details": missing_details,
                "windows_longpaths": longpaths_note,
                "git_safe_directory": "blocked" if git_safe_directory_blocked else "ok",
                "advisories": (
                    [
                        {
                            "key": "windows_longpaths_disabled",
                            "message": "Enable git core.longpaths=true to reduce path-length failures on Windows toolchains.",
                        }
                    ]
                    if longpaths_state is False
                    else []
                )
                + (
                    [
                        {
                            "key": "git_safe_directory_blocked",
                            "message": "Git safe.directory policy is blocking repository access; add this repo to safe.directory and rerun.",
                        }
                    ]
                    if git_safe_directory_blocked
                    else []
                ),
                "binding_evidence": "ok" if BINDING_OK else "invalid",
            },
            ensure_ascii=True,
        )
    )


def emit_permission_probes() -> None:
    """Emit deterministic permission probe evidence (`ttl=0`)."""

    observed = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    checks = []

    commands_home = COMMANDS_RUNTIME_DIR
    workspaces_home = WORKSPACES_HOME
    checks.append({
        "probe": "fs.read_commands_home",
        "available": commands_home.exists() and os.access(commands_home, os.R_OK),
    })
    checks.append({
        "probe": "fs.write_workspaces_home",
        "available": (workspaces_home.exists() and os.access(workspaces_home, os.W_OK))
        or (not workspaces_home.exists() and os.access(workspaces_home.parent, os.W_OK)),
    })
    checks.append({
        "probe": "exec.allowed",
        "available": os.access(sys.executable, os.X_OK),
    })
    checks.append({
        "probe": "git.available",
        "available": shutil.which("git") is not None,
    })

    available = [p["probe"] for p in checks if p["available"]]
    missing = [p["probe"] for p in checks if not p["available"]]
    status = "ok" if not missing else "degraded"
    print(
        json.dumps(
            {
                "permissionProbes": {
                    "status": status,
                    "observed_at": observed,
                    "ttl": 0,
                    "available": available,
                    "missing": missing,
                    "impact": (
                        "all required runtime capabilities available"
                        if not missing
                        else "some runtime actions may be blocked or degraded"
                    ),
                    "next": (
                        "continue bootstrap"
                        if not missing
                        else "grant required permissions or run in restricted mode with explicit recovery"
                    ),
                }
            },
            ensure_ascii=True,
        )
    )


def log_error(reason_key: str, message: str, observed: dict) -> None:
    try:
        if not LOGGER.exists():
            return
        spec = importlib.util.spec_from_file_location("opencode_error_logs", str(LOGGER))
        if not spec or not spec.loader:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fn = getattr(module, "safe_log_error", None)
        if not callable(fn):
            return
        fn(
            reason_key=reason_key,
            message=message,
            config_root=ROOT,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode="repo-aware",
            command="start.md:/start",
            component="workspace-persistence-hook",
            observed_value=observed,
            expected_constraint="persist_workspace_artifacts.py available and returns code 0",
            remediation="Reinstall governance package and rerun /start.",
        )
    except Exception:
        return


def bootstrap_identity_if_needed() -> bool:
    repo_root, discovery_method = resolve_repo_context()
    inferred_fp = (
        (derive_repo_fingerprint(repo_root) or read_repo_context_fingerprint(repo_root))
        if repo_root is not None
        else None
    ) or pointer_fingerprint()

    if inferred_fp and repo_root is not None:
        write_repo_context(repo_root, inferred_fp, discovery_method)

    if identity_map_exists(inferred_fp):
        return True

    if not inferred_fp:
        print(
            json.dumps(
                {
                    "status": "warn",
                    "workspacePersistenceHook": "warn",
                    "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                    "reason": "identity-bootstrap-fingerprint-missing",
                    "impact": "workspace artifacts skipped for this turn (bootstrap can continue)",
                    "recovery": "rerun /start from repository root or set OPENCODE_REPO_ROOT to the repo root",
                }
            )
        )
        return False

    if not BOOTSTRAP_HELPER.exists():
        print(
            json.dumps(
                {
                    "status": "warn",
                    "workspacePersistenceHook": "warn",
                    "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                    "reason": "missing-bootstrap-helper",
                    "missing_evidence": ["diagnostics/bootstrap_session_state.py", "workspaces/<repo_fingerprint>/repo-identity-map.yaml"],
                    "recovery_steps": ["restore bootstrap_session_state.py helper and rerun /start"],
                    "required_operator_action": "restore diagnostics/bootstrap_session_state.py and rerun /start",
                    "feedback_required": "reply once helper is restored and /start rerun",
                    "next_command": "/start",
                    "next_command_profiles": render_command_profiles(["/start"]),
                }
            )
        )
        return False

    if shutil.which("git") is None:
        print(
            json.dumps(
                {
                    "status": "warn",
                    "workspacePersistenceHook": "warn",
                    "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                    "reason": "missing-git-for-identity-bootstrap",
                    "missing_evidence": ["git in PATH", "workspaces/<repo_fingerprint>/repo-identity-map.yaml"],
                    "recovery_steps": [
                        "install git and rerun /start, or bootstrap with explicit fingerprint"
                    ],
                    "required_operator_action": "install git or run bootstrap_session_state.py with explicit fingerprint, then rerun /start",
                    "feedback_required": "reply with the fingerprint used (if manual bootstrap) and helper result",
                    "next_command": bootstrap_command(inferred_fp),
                    "next_command_profiles": render_command_profiles(bootstrap_command_argv(inferred_fp)),
                }
            )
        )
        return False

    repo_fp = inferred_fp

    boot = subprocess.run(
        [*_python_command_argv(), str(BOOTSTRAP_HELPER), "--repo-fingerprint", repo_fp, "--config-root", str(ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )
    if boot.returncode != 0 or not identity_map_exists(repo_fp):
        boot_err = (boot.stderr or "")[:240]
        log_error(
            "ERR-WORKSPACE-PERSISTENCE-IDENTITY-BOOTSTRAP-FAILED",
            "/start identity bootstrap helper returned non-zero or identity map missing after run.",
            {"repoFingerprint": repo_fp, "stderr": boot_err},
        )
        print(
            json.dumps(
                {
                    "status": "warn",
                    "workspacePersistenceHook": "warn",
                    "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                    "reason": "identity-bootstrap-failed",
                    "missing_evidence": ["workspaces/<repo_fingerprint>/repo-identity-map.yaml"],
                    "recovery_steps": ["run bootstrap_session_state.py manually and rerun /start"],
                    "required_operator_action": "run bootstrap_session_state.py with explicit repo fingerprint, then rerun /start",
                    "feedback_required": "reply with helper stderr and repo fingerprint",
                    "next_command": bootstrap_command(repo_fp),
                    "next_command_profiles": render_command_profiles(bootstrap_command_argv(repo_fp)),
                }
            )
        )
        return False

    print(
        json.dumps(
            {
                "workspacePersistenceHook": "ok",
                "bootstrapSessionState": "created",
                "repoFingerprint": repo_fp,
                "identityMap": "created",
            }
        )
    )
    return True


def run_persistence_hook() -> None:
    if not BINDING_OK:
        print(
            json.dumps(
                {
                    "workspacePersistenceHook": "warn",
                    "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                    "reason": "invalid-binding-evidence",
                    "impact": "workspace persistence skipped until governance.paths.json is repaired",
                    "recovery": "rerun installer to regenerate commands/governance.paths.json and rerun /start",
                    "next_command": "/start",
                    "next_command_profiles": render_command_profiles(["/start"]),
                }
            )
        )
        return

    if not PERSIST_HELPER.exists():
        log_error(
            "ERR-WORKSPACE-PERSISTENCE-HOOK-MISSING",
            "/start workspace persistence helper is missing from diagnostics payload.",
            {"helper": str(PERSIST_HELPER)},
        )
        print(
            json.dumps(
                    {
                        "workspacePersistenceHook": "warn",
                        "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                        "reason": "helper-missing",
                        "impact": "workspace artifacts may be incomplete",
                        "recovery": persist_command(normalize_absolute_path(str(Path.cwd()), purpose="cwd_recovery")),
                    }
                )
            )
        return

    if not bootstrap_identity_if_needed():
        return

    repo_root, discovery_method = resolve_repo_context()
    repo_fp = (
        (derive_repo_fingerprint(repo_root) or read_repo_context_fingerprint(repo_root))
        if repo_root is not None
        else None
    ) or pointer_fingerprint()
    if repo_root is None or not repo_fp:
        print(
            json.dumps(
                {
                    "workspacePersistenceHook": "warn",
                    "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                    "reason": "repo-root-not-git",
                    "impact": "workspace artifact backfill skipped for this turn",
                    "recovery": "run /start from repository root or set OPENCODE_REPO_ROOT",
                }
            )
        )
        return

    write_repo_context(repo_root, repo_fp, discovery_method)

    run = subprocess.run(
        [
            *_python_command_argv(),
            str(PERSIST_HELPER),
            "--repo-root",
            str(repo_root),
            "--repo-fingerprint",
            repo_fp,
            "--quiet",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    out = (run.stdout or "").strip()
    err = (run.stderr or "").strip()

    if run.returncode == 0 and out:
        try:
            payload = json.loads(out)
        except Exception:
            payload = None

        if isinstance(payload, dict) and payload.get("sessionStateUpdate") == "no-session-file" and BOOTSTRAP_HELPER.exists():
            repo_fp = str(payload.get("repoFingerprint") or "").strip()
            if repo_fp:
                boot = subprocess.run(
                    [
                        *_python_command_argv(),
                        str(BOOTSTRAP_HELPER),
                        "--repo-fingerprint",
                        repo_fp,
                        "--config-root",
                        str(ROOT),
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if boot.returncode == 0:
                    print(
                        json.dumps(
                            {
                                "workspacePersistenceHook": "ok",
                                "bootstrapSessionState": "created",
                                "repoFingerprint": repo_fp,
                            }
                        )
                    )
                else:
                    boot_err = (boot.stderr or "")[:240]
                    log_error(
                        "ERR-SESSION-BOOTSTRAP-HOOK-FAILED",
                        "/start session bootstrap helper returned non-zero.",
                        {"repoFingerprint": repo_fp, "stderr": boot_err},
                    )
                    print(
                        json.dumps(
                            {
                                "workspacePersistenceHook": "warn",
                                "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                                "reason": "bootstrap-session-failed",
                                "repoFingerprint": repo_fp,
                                "error": boot_err,
                                "impact": "repo-scoped SESSION_STATE may be incomplete",
                                "recovery": bootstrap_command(repo_fp),
                            }
                        )
                    )
            else:
                print(out)
        elif isinstance(payload, dict) and payload.get("status") == "blocked":
            log_error(
                "ERR-WORKSPACE-PERSISTENCE-HOOK-BLOCKED",
                "/start workspace persistence helper reported blocked output.",
                payload,
            )
            print(
                json.dumps(
                    {
                        "workspacePersistenceHook": "warn",
                        "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                        "reason": "helper-reported-blocked",
                        "helperPayload": payload,
                        "impact": "workspace artifacts may be incomplete",
                        "recovery": persist_command(normalize_absolute_path(str(Path.cwd()), purpose="cwd_recovery")),
                    }
                )
            )
        else:
            print(out)
        return

    if run.returncode == 0:
        print(json.dumps({"workspacePersistenceHook": "ok"}))
        return

    log_error(
        "ERR-WORKSPACE-PERSISTENCE-HOOK-FAILED",
        "/start workspace persistence helper returned non-zero.",
        {"returncode": run.returncode, "stderr": err[:240]},
    )
    print(
        json.dumps(
            {
                "workspacePersistenceHook": "warn",
                "reason_code": "WARN-WORKSPACE-PERSISTENCE",
                "reason": "helper-failed",
                "code": run.returncode,
                "error": err[:240],
                "impact": "workspace artifacts may be incomplete",
                "recovery": persist_command(normalize_absolute_path(str(Path.cwd()), purpose="cwd_recovery")),
            }
        )
    )


def build_engine_shadow_snapshot() -> dict[str, object]:
    """Build optional Wave B shadow runtime diagnostics.

    This helper is intentionally non-blocking and side-effect free. It does not
    alter bootstrap behavior; callers may choose whether to emit the snapshot.
    """

    try:
        from governance.engine.adapters import OpenCodeDesktopAdapter
        from governance.engine.orchestrator import run_engine_orchestrator
    except Exception as exc:  # pragma: no cover - exercised in packaged hosts where module may be absent
        return {
            "available": False,
            "reason": "engine-runtime-module-unavailable",
            "error": str(exc),
        }

    requested_mode = str(os.getenv("OPENCODE_OPERATING_MODE", "")).strip().lower()
    if requested_mode not in {"user", "system", "pipeline"}:
        requested_mode = ""

    kwargs = {
        "adapter": OpenCodeDesktopAdapter(),
        "phase": "1.1-Bootstrap",
        "active_gate": "Persistence Preflight",
        "mode": "OK",
        "next_gate_condition": "Persistence helper execution completed",
        "gate_key": "PERSISTENCE",
        "target_path": "${WORKSPACE_MEMORY_FILE}",
        "enable_live_engine": False,
    }
    if requested_mode == "user":
        output = run_engine_orchestrator(**kwargs, requested_operating_mode="user")
    elif requested_mode == "system":
        output = run_engine_orchestrator(**kwargs, requested_operating_mode="system")
    elif requested_mode == "pipeline":
        output = run_engine_orchestrator(**kwargs, requested_operating_mode="pipeline")
    else:
        output = run_engine_orchestrator(**kwargs)
    return {
        "available": True,
        "runtime_mode": output.runtime.runtime_mode,
        "selfcheck_ok": output.runtime.selfcheck.ok,
        "repo_context_source": output.repo_context.source,
        "effective_operating_mode": output.effective_operating_mode,
        "capabilities_hash": output.capabilities_hash,
        "mode_downgraded": output.mode_downgraded,
        "deviation": (
            {
                "type": output.runtime.deviation.type,
                "scope": output.runtime.deviation.scope,
                "impact": output.runtime.deviation.impact,
                "recovery": output.runtime.deviation.recovery,
            }
            if output.runtime.deviation is not None
            else None
        ),
        "parity": output.parity,
    }


def main() -> int:
    emit_preflight()
    emit_permission_probes()
    run_persistence_hook()
    if os.getenv("OPENCODE_ENGINE_SHADOW_EMIT") == "1":
        print(json.dumps({"engineRuntimeShadow": build_engine_shadow_snapshot()}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
