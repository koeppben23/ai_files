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
    from governance.application.use_cases.start_persistence import decide_start_persistence as _decide_start_persistence
    from governance.engine.adapters import OpenCodeDesktopAdapter
    from governance.infrastructure.start_persistence_store import (
        commit_workspace_identity as _commit_workspace_identity,
        write_unresolved_runtime_context as _write_unresolved_runtime_context,
    )
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

    _decide_start_persistence = None
    OpenCodeDesktopAdapter = None

    _commit_workspace_identity = None
    _write_unresolved_runtime_context = None


def decide_start_persistence(*, env, cwd):
    _ = env
    _ = cwd
    if callable(_decide_start_persistence) and OpenCodeDesktopAdapter is not None:
        try:
            return _decide_start_persistence(adapter=OpenCodeDesktopAdapter())
        except Exception:
            pass
    return {
        "repo_root": None,
        "repo_fingerprint": "",
        "discovery_method": "cwd",
        "workspace_ready": False,
        "reason_code": "BLOCKED-REPO-IDENTITY-RESOLUTION",
        "reason": "repo-root-not-git",
    }


def write_unresolved_runtime_context(**kwargs):
    if callable(_write_unresolved_runtime_context):
        return _write_unresolved_runtime_context(**kwargs)
    _ = kwargs
    return False


def commit_workspace_identity(**kwargs):
    if callable(_commit_workspace_identity):
        return _commit_workspace_identity(**kwargs)
    _ = kwargs
    return False


def _identity_value(identity: object, key: str):
    if isinstance(identity, dict):
        return identity.get(key)
    return getattr(identity, key, None)


def _persistence_value(decision: object, key: str):
    if isinstance(decision, dict):
        return decision.get(key)
    return getattr(decision, key, None)


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
    decision = decide_start_persistence(env=os.environ, cwd=normalize_absolute_path(str(Path.cwd()), purpose="cwd"))
    return _persistence_value(decision, "repo_root"), str(_persistence_value(decision, "discovery_method") or "cwd")


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


def write_repo_context(repo_root: Path, repo_fingerprint: str, discovery_method: str) -> bool:
    try:
        return bool(
            commit_workspace_identity(
                workspaces_home=WORKSPACES_HOME,
                repo_root=repo_root,
                repo_fingerprint=repo_fingerprint,
                binding_evidence_path=BINDING_EVIDENCE_PATH,
                commands_home=COMMANDS_RUNTIME_DIR,
                discovery_method=discovery_method,
                session_id=_discover_repo_session_id(),
            )
        )
    except Exception as exc:
        log_error(
            "ERR-REPO-CONTEXT-WRITE-FAILED",
            "Failed to persist repo-context evidence via core persistence use-case.",
            {"error": str(exc)[:240]},
        )
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
    decision = decide_start_persistence(env=os.environ, cwd=normalize_absolute_path(str(Path.cwd()), purpose="cwd"))
    repo_root = _persistence_value(decision, "repo_root")
    inferred_fp = str(_persistence_value(decision, "repo_fingerprint") or "").strip() or None
    if repo_root is None or not inferred_fp:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "workspacePersistenceHook": "blocked",
                    "reason_code": "BLOCKED-REPO-IDENTITY-RESOLUTION",
                    "reason": "identity-bootstrap-fingerprint-missing",
                    "impact": "workspace artifacts skipped until repo identity is resolved",
                    "recovery": "run /start from a git repository root or set OPENCODE_REPO_ROOT to the repo root",
                }
            )
        )
        return False

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

    if not bootstrap_identity_if_needed():
        return

    decision = decide_start_persistence(env=os.environ, cwd=normalize_absolute_path(str(Path.cwd()), purpose="cwd"))
    repo_root = _persistence_value(decision, "repo_root")
    discovery_method = str(_persistence_value(decision, "discovery_method") or "cwd")
    repo_fp = str(_persistence_value(decision, "repo_fingerprint") or "").strip() or None
    if repo_root is None or not repo_fp:
        print(
            json.dumps(
                {
                    "workspacePersistenceHook": "blocked",
                    "reason_code": "BLOCKED-REPO-IDENTITY-RESOLUTION",
                    "reason": "repo-root-not-git",
                    "impact": "workspace artifact backfill skipped until repo identity is resolved",
                    "recovery": "run /start from repository root or set OPENCODE_REPO_ROOT",
                }
            )
        )
        return

    print(
        json.dumps(
            {
                "workspacePersistenceHook": "ok",
                "mode": "non-destructive",
                "repoFingerprint": repo_fp,
                "repoRoot": str(repo_root),
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
