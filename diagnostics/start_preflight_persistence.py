#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
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
except Exception:  # pragma: no cover - unavailable on Windows
    pwd = None
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from command_profiles import render_command_profiles


def config_root() -> Path:
    system = platform.system()
    if system == "Darwin" and pwd is not None:
        return (Path(pwd.getpwuid(os.getuid()).pw_dir).resolve() / ".config" / "opencode").resolve()
    return (Path.home().resolve() / ".config" / "opencode").resolve()


def _candidate_config_roots() -> list[Path]:
    candidates: list[Path] = [config_root()]

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _allow_cwd_binding_discovery() -> bool:
    return str(os.getenv("OPENCODE_ALLOW_CWD_BINDINGS", "")).strip() == "1"


def _resolve_bound_paths(root: Path) -> tuple[Path, Path, bool]:
    commands_home = root / "commands"
    workspaces_home = root / "workspaces"
    candidates: list[Path] = [commands_home / "governance.paths.json"]
    for config in _candidate_config_roots():
        candidates.append(config / "commands" / "governance.paths.json")
    if _allow_cwd_binding_discovery():
        cwd = Path.cwd().resolve()
        for parent in (cwd, *cwd.parents):
            candidates.append(parent / "commands" / "governance.paths.json")

    binding_file: Path | None = None
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            binding_file = resolved
            break

    if binding_file is None:
        return commands_home, workspaces_home, False
    try:
        payload = json.loads(binding_file.read_text(encoding="utf-8"))
    except Exception:
        return commands_home, workspaces_home, False
    if not isinstance(payload, dict):
        return commands_home, workspaces_home, False
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return commands_home, workspaces_home, False
    commands_raw = paths.get("commandsHome")
    workspaces_raw = paths.get("workspacesHome")
    resolved_commands = (
        Path(commands_raw).expanduser().resolve()
        if isinstance(commands_raw, str) and commands_raw.strip()
        else commands_home
    )
    resolved_workspaces = (
        Path(workspaces_raw).expanduser().resolve()
        if isinstance(workspaces_raw, str) and workspaces_raw.strip()
        else workspaces_home
    )
    if not resolved_commands.is_absolute() or not resolved_workspaces.is_absolute():
        return commands_home, workspaces_home, False
    return resolved_commands, resolved_workspaces, True


ROOT = config_root()
COMMANDS_RUNTIME_DIR, WORKSPACES_HOME, BINDING_OK = _resolve_bound_paths(ROOT)
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


def resolve_repo_root() -> Path:
    def _search_repo_root(start: Path) -> Path | None:
        candidate = start.resolve()
        for probe in (candidate, *candidate.parents):
            git_path = probe / ".git"
            if git_path.is_dir() or git_path.is_file():
                return probe
        return None

    env_candidates = [
        os.getenv("OPENCODE_REPO_ROOT"),
        os.getenv("OPENCODE_WORKSPACE_ROOT"),
        os.getenv("REPO_ROOT"),
        os.getenv("GITHUB_WORKSPACE"),
    ]
    for candidate in env_candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser().resolve()
        if not path.exists():
            continue
        repo_root = _search_repo_root(path)
        if repo_root is not None:
            return repo_root
    cwd_repo_root = _search_repo_root(Path.cwd().resolve())
    return cwd_repo_root if cwd_repo_root is not None else Path.cwd().resolve()


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
        candidate = (repo_root / candidate).resolve()
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


def read_default_branch(git_dir: Path) -> str:
    head_ref = git_dir / "refs" / "remotes" / "origin" / "HEAD"
    if head_ref.exists():
        try:
            text = head_ref.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = head_ref.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"ref:\s*refs/remotes/origin/(.+)", text)
        if match:
            branch = match.group(1).strip()
            if branch:
                return branch
    return "main"


def _normalize_path_for_fingerprint(path: Path) -> str:
    """Normalize filesystem paths for deterministic cross-platform fingerprints."""

    resolved = path.expanduser().resolve()
    return resolved.as_posix().replace("\\", "/").casefold()


def derive_repo_fingerprint(repo_root: Path) -> str | None:
    resolved_root = repo_root.expanduser().resolve()
    git_dir = resolve_git_dir(resolved_root)
    if not git_dir:
        return None

    origin = read_origin_remote(git_dir / "config")
    branch = read_default_branch(git_dir)
    if origin:
        material = f"{origin}|{branch}"
    else:
        material = f"local-git|{_normalize_path_for_fingerprint(resolved_root)}|{branch}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


PYTHON_COMMAND = resolve_python_command()


def bootstrap_command(repo_fp: str | None) -> str:
    return _preferred_shell_command(render_command_profiles(bootstrap_command_argv(repo_fp)))


def bootstrap_command_argv(repo_fp: str | None) -> list[str]:
    if repo_fp:
        return [PYTHON_COMMAND, str(BOOTSTRAP_HELPER), "--repo-fingerprint", repo_fp, "--config-root", str(ROOT)]
    return [PYTHON_COMMAND, str(BOOTSTRAP_HELPER), "--repo-fingerprint", "<repo_fingerprint>", "--config-root", str(ROOT)]


def persist_command(repo_root: Path) -> str:
    return _preferred_shell_command(render_command_profiles(persist_command_argv(repo_root)))


def persist_command_argv(repo_root: Path) -> list[str]:
    return [PYTHON_COMMAND, str(PERSIST_HELPER), "--repo-root", str(repo_root)]


def _command_available(command: str) -> bool:
    """Return command availability with canonical alias handling."""

    if command in {"python", "python3", "py", "py -3"}:
        return shutil.which("python") is not None or shutil.which("python3") is not None
    parts = shlex.split(command, posix=(os.name != "nt"))
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
    repo_root = resolve_repo_root()
    inferred_fp = derive_repo_fingerprint(repo_root) or pointer_fingerprint()

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
        [sys.executable, str(BOOTSTRAP_HELPER), "--repo-fingerprint", repo_fp, "--config-root", str(ROOT)],
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
                        "recovery": persist_command(Path.cwd().resolve()),
                    }
                )
            )
        return

    if not bootstrap_identity_if_needed():
        return

    repo_root = resolve_repo_root()
    repo_fp = derive_repo_fingerprint(repo_root) or pointer_fingerprint()
    if not repo_fp:
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

    run = subprocess.run(
        [
            sys.executable,
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
                        sys.executable,
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
                        "recovery": persist_command(Path.cwd().resolve()),
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
                "recovery": persist_command(Path.cwd().resolve()),
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
