#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, cast

_COMMANDS_HOME = str(Path(__file__).parent.parent)
if _COMMANDS_HOME not in sys.path:
    sys.path.insert(0, _COMMANDS_HOME)

from governance_runtime.entrypoints.command_profiles import render_command_profiles
from governance_runtime.entrypoints.write_policy import writes_allowed, EFFECTIVE_MODE
from governance_runtime.infrastructure.tenant_config import load_tenant_config, get_profile_override
from governance_runtime.application.use_cases.phase_router import route_phase
from governance_runtime.application.use_cases.session_state_helpers import with_kernel_result
from governance_runtime.domain.phase_state_machine import normalize_phase_token, phase_rank
from governance_runtime.engine.sanitization import apply_fresh_start_business_rules_neutralization
from governance_runtime.engine.business_rules_hydration import (
    canonicalize_business_rules_outcome,
    has_br_signal,
)
from governance_runtime.kernel.phase_kernel import api_in_scope
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver

try:
    from bootstrap.repo_identity import derive_fingerprint as _derive_fingerprint_ssot
except Exception:
    _derive_fingerprint_ssot = None

from governance_runtime.infrastructure.logging.global_error_handler import (
    emit_gate_failure,
    install_global_handlers,
    resolve_log_path,
    set_error_context,
)
# SSOT: Ensure global error handler is installed before any operations
def _install_global_error_handler() -> None:
    try:
        from governance_runtime.infrastructure.logging.global_error_handler import install_global_handlers
        install_global_handlers()
    except Exception:
        pass

_install_global_error_handler()


def _effective_mode() -> str:
    return EFFECTIVE_MODE


def _resolve_bindings() -> tuple[Path | None, Path | None, bool, Path | None, str]:
    resolver = BindingEvidenceResolver()
    effective_mode = _effective_mode()
    evidence = resolver.resolve(mode=effective_mode)
    python_command = evidence.python_command.strip() if evidence.python_command else ""
    if not python_command:
        # Use sys.executable instead of "python3" for Windows compatibility
        python_command = sys.executable
    return (
        evidence.commands_home,
        evidence.workspaces_home,
        evidence.binding_ok,
        evidence.governance_paths_json,
        python_command,
    )


COMMANDS_HOME, WORKSPACES_HOME, BINDING_OK, BINDING_EVIDENCE_PATH, PYTHON_COMMAND = _resolve_bindings()
TOOL_CATALOG = (
    COMMANDS_HOME / "governance" / "assets" / "catalogs" / "tool_requirements.json"
    if COMMANDS_HOME is not None
    else None
)

HOOK_STATUS_OK = "ok"
HOOK_STATUS_BLOCKED = "blocked"
HOOK_STATUS_FAILED = "failed"

DEFAULT_ACTIVE_PROFILE_ID = "fallback-minimum"
DEFAULT_ADDON_KEY = "riskTiering"
DEFAULT_ADDON_RULEBOOK = "rules.risk-tiering.yml"
_BUSINESS_RULES_RESOLVED_OUTCOMES = {"extracted", "gap-detected", "unresolved"}
SUPPORTED_PROFILE_IDS = {
    "backend-python",
    "backend-java",
    "frontend-angular-nx",
    DEFAULT_ACTIVE_PROFILE_ID,
}

FAILURE_STAGE_INIT = "init"
FAILURE_STAGE_WRITES_ALLOWED = "writes_allowed"
FAILURE_STAGE_REPO_ROOT = "repo_root"
FAILURE_STAGE_SUBPROCESS = "subprocess"
FAILURE_STAGE_PARSE = "parse"
FAILURE_STAGE_HOOK_PAYLOAD = "hook_payload"


def _normalize_abs_path(raw: str, *, purpose: str) -> Path:
    token = str(raw or "").strip()
    if not token:
        raise ValueError(f"{purpose}: empty path")
    candidate = Path(token).expanduser()
    if os.name == "nt" and re.match(r"^[A-Za-z]:[^/\\]", token):
        raise ValueError(f"{purpose}: drive-relative path is not allowed")
    if not candidate.is_absolute():
        raise ValueError(f"{purpose}: path must be absolute")
    return Path(os.path.normpath(os.path.abspath(str(candidate))))


def derive_repo_fingerprint(repo_root: Path) -> str | None:
    try:
        normalized_repo_root = _normalize_abs_path(str(repo_root), purpose="repo_root")
    except Exception:
        return None

    git_marker = normalized_repo_root / ".git"
    if not (git_marker.is_dir() or git_marker.is_file()):
        return None

    probe = subprocess.run(
        ["git", "-C", str(normalized_repo_root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if probe.returncode != 0 or (probe.stdout or "").strip().lower() != "true":
        return None

    if callable(_derive_fingerprint_ssot):
        try:
            candidate = str(_derive_fingerprint_ssot(normalized_repo_root) or "").strip()
            if re.fullmatch(r"[0-9a-f]{24}", candidate):
                return candidate
        except Exception:
            pass

    try:
        remote = subprocess.run(
            ["git", "-C", str(normalized_repo_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        material = (remote.stdout or "").strip()
    except Exception:
        material = ""
    if not material:
        material = f"repo:local:{normalized_repo_root}"
    fp = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]

    return fp


def _command_available(command: str) -> bool:
    if command in {"python", "python3", "py", "py -3"}:
        return (
            shutil.which("python") is not None
            or shutil.which("python3") is not None
            or shutil.which("py") is not None
        )
    token = str(command or "").strip()
    if not token:
        return False
    if token == "py -3":
        return shutil.which("py") is not None
    if token == "python -3":
        return shutil.which("python") is not None
    return shutil.which(token) is not None


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
    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        text=True,
        capture_output=True,
        check=False,
    )
    return "safe.directory" in (proc.stderr or "").lower()


def _load_tool_catalog() -> dict[str, object]:
    if TOOL_CATALOG is None or not TOOL_CATALOG.exists():
        return {}
    try:
        payload = json.loads(TOOL_CATALOG.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _normalize_tool_command(token: str) -> str:
    """Replace ``${PYTHON_COMMAND}`` with the resolved python path.

    If the resolved path contains spaces (e.g.
    ``C:\\Program Files\\Python311\\python.exe``) it is wrapped in
    double-quotes so that :func:`_split_verify_command` can keep it as
    a single argv token.  Multi-token commands like ``py -3`` never
    contain path separators so they remain unquoted.
    """
    cmd = PYTHON_COMMAND
    if " " in cmd and not cmd.startswith('"') and ("\\" in cmd or "/" in cmd):
        cmd = f'"{cmd}"'
    return token.replace("${PYTHON_COMMAND}", cmd).strip()


def _split_verify_command(verify_command: str) -> list[str]:
    """Split a verify_command string into a safe argv list.

    Uses simple whitespace splitting which is sufficient for the verify
    commands in the tool catalog (e.g. ``git --version``,
    ``python --version``).  Paths with spaces from ``${PYTHON_COMMAND}``
    substitution are handled by keeping quoted tokens intact: if the first
    character is a double-quote, the token extends to the closing quote.
    """
    token = str(verify_command or "").strip()
    if not token:
        return []
    # Simple parser: respect double-quoted segments for paths with spaces
    parts: list[str] = []
    i = 0
    n = len(token)
    while i < n:
        # skip whitespace
        while i < n and token[i] in (' ', '\t'):
            i += 1
        if i >= n:
            break
        if token[i] == '"':
            # quoted segment
            j = token.find('"', i + 1)
            if j < 0:
                j = n
            parts.append(token[i + 1 : j])
            i = j + 1
        else:
            j = i
            while j < n and token[j] not in (' ', '\t'):
                j += 1
            parts.append(token[i:j])
            i = j
    return parts


def _tool_inventory() -> tuple[list[str], list[str], list[dict[str, str]]]:
    payload = _load_tool_catalog()
    required_now: list[str] = []
    required_later: list[str] = []
    required_later_entries: list[dict[str, str]] = []

    if isinstance(payload, dict):
        required_now_raw = payload.get("required_now", [])
        if not isinstance(required_now_raw, list):
            required_now_raw = []
        for item in cast(list[object], required_now_raw):
            if isinstance(item, dict):
                cmd = _normalize_tool_command(str(item.get("command") or ""))
                if cmd and cmd not in required_now:
                    required_now.append(cmd)
        required_later_raw = payload.get("required_later", [])
        if not isinstance(required_later_raw, list):
            required_later_raw = []
        for item in cast(list[object], required_later_raw):
            if isinstance(item, dict):
                cmd = _normalize_tool_command(str(item.get("command") or ""))
                if cmd and cmd not in required_later and cmd not in required_now:
                    required_later.append(cmd)
                    required_later_entries.append(
                        {
                            "command": cmd,
                            "verify_command": _normalize_tool_command(str(item.get("verify_command") or "")),
                        }
                    )

    if not required_now:
        required_now = ["git", PYTHON_COMMAND]
    return required_now, required_later, required_later_entries


def _probe_tool_version(verify_command: str) -> str | None:
    if not verify_command:
        return None
    argv = _split_verify_command(verify_command)
    if not argv:
        return None
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return None
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    for line in output.splitlines():
        token = (line or "").strip()
        if token:
            return token[:200]
    return None


def _preflight_build_toolchain_snapshot() -> dict[str, object]:
    _required_now, _required_later, required_later_entries = _tool_inventory()
    detected: dict[str, str | None] = {}
    for entry in required_later_entries:
        cmd = entry.get("command", "").strip()
        if not cmd:
            continue
        if _command_available(cmd):
            detected[cmd] = _probe_tool_version(entry.get("verify_command", ""))
        else:
            detected[cmd] = None
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "DetectedTools": detected,
        "ObservedAt": observed_at,
    }


def emit_preflight() -> None:
    if os.getenv("OPENCODE_BOOTSTRAP_OUTPUT", "final").strip().lower() != "full":
        return
    required_now, required_later, _required_later_entries = _tool_inventory()

    available: list[str] = []
    missing: list[str] = []
    for command in required_now:
        if _command_available(command):
            available.append(command)
        else:
            missing.append(command)

    missing_later = [cmd for cmd in required_later if not _command_available(cmd)]
    block_now = bool(missing) or not BINDING_OK
    status = "degraded" if block_now else "ok"
    longpaths = _windows_longpaths_enabled()
    longpaths_note = "not_applicable" if longpaths is None else ("enabled" if longpaths else "disabled")
    git_safe_directory = "blocked" if (_command_available("git") and _git_safe_directory_issue()) else "ok"
    build_toolchain = _preflight_build_toolchain_snapshot()

    mode = _effective_mode()
    payload = {
        "preflight": status,
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "required_now": required_now,
        "required_later": required_later,
        "available": available,
        "missing": missing,
        "missing_later": missing_later,
        "block_now": block_now,
        "impact": (
            "required_now commands satisfied; preflight continues"
            if status == "ok"
            else "missing required_now commands may block bootstrap gates"
        ),
        "next": (
            "continue bootstrap"
            if status == "ok"
            else "install missing required_now tools or provide equivalent operator evidence"
        ),
        "binding_evidence": "ok" if BINDING_OK else "invalid",
        "windows_longpaths": longpaths_note,
        "git_safe_directory": git_safe_directory,
        "mode": mode,
        "writes_allowed": writes_allowed(),
        "build_toolchain": build_toolchain,
    }
    print(json.dumps(payload, ensure_ascii=True))


def emit_permission_probes() -> None:
    if os.getenv("OPENCODE_BOOTSTRAP_OUTPUT", "final").strip().lower() != "full":
        return
    checks = [
        {
            "probe": "fs.read_commands_home",
            "available": bool(COMMANDS_HOME is not None and COMMANDS_HOME.exists() and os.access(COMMANDS_HOME, os.R_OK)),
        },
        {
            "probe": "exec.allowed",
            "available": os.access(sys.executable, os.X_OK),
        },
        {
            "probe": "git.available",
            "available": shutil.which("git") is not None,
        },
    ]
    available = [item["probe"] for item in checks if item["available"]]
    missing = [item["probe"] for item in checks if not item["available"]]
    status = "ok" if not missing else "degraded"
    print(
        json.dumps(
            {
                "permissionProbes": {
                    "status": status,
                    "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "ttl": 0,
                    "available": available,
                    "missing": missing,
                    "impact": "all required runtime capabilities available" if not missing else "some runtime actions may be blocked",
                    "next": "continue bootstrap" if not missing else "grant required permissions and rerun the local bootstrap launcher",
                }
            },
            ensure_ascii=True,
        )
    )


def _python_command_argv() -> list[str]:
    """Split :data:`PYTHON_COMMAND` into a proper argv prefix.

    Multi-token commands like ``py -3`` must become ``["py", "-3"]``
    so that :func:`render_command_profiles` quotes each token
    individually rather than treating ``"py -3"`` as a single
    executable name.  Single-path values like
    ``C:\\Python311\\python.exe`` stay as one element.

    The function does **not** use ``shlex.split`` because the
    architecture guard forbids it in this file.
    """
    return _split_verify_command(PYTHON_COMMAND) or [sys.executable]


def bootstrap_command_argv(repo_fp: str | None) -> list[str]:
    repo_value = repo_fp if repo_fp else "<repo_fingerprint>"
    return [*_python_command_argv(), "-m", "governance_runtime.entrypoints.bootstrap_session_state", "--repo-fingerprint", repo_value]


def bootstrap_command(repo_fp: str | None) -> str:
    return str(render_command_profiles(bootstrap_command_argv(repo_fp)).get("bash") or "")


def _resolve_repo_root_for_hook() -> tuple[Path | None, str, dict[str, object]]:
    env_root = os.environ.get("OPENCODE_REPO_ROOT", "").strip()
    if env_root:
        try:
            resolved_env_root = _normalize_abs_path(env_root, purpose="OPENCODE_REPO_ROOT")
            if (resolved_env_root / ".git").exists() or (resolved_env_root / ".git").is_file():
                return resolved_env_root, "env", {"ok": True, "source": "env", "raw": env_root}
            return None, "env-invalid", {"ok": False, "source": "env", "raw": env_root, "reason": "missing-.git"}
        except Exception as exc:
            return None, "env-invalid", {"ok": False, "source": "env", "raw": env_root, "error": str(exc)[:200]}

    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    root_text = (probe.stdout or "").strip()
    if probe.returncode == 0 and root_text:
        try:
            resolved_git_root = _normalize_abs_path(root_text, purpose="git-rev-parse")
            return resolved_git_root, "git", {
                "ok": True,
                "source": "git",
                "returncode": probe.returncode,
                "stdout": root_text,
            }
        except Exception as exc:
            return None, "git-invalid", {
                "ok": False,
                "source": "git",
                "returncode": probe.returncode,
                "stdout": root_text,
                "error": str(exc)[:200],
            }
    return None, "git-miss", {
        "ok": False,
        "source": "git",
        "returncode": probe.returncode,
        "stdout": root_text,
        "stderr": (probe.stderr or "").strip()[:240],
    }


def build_engine_shadow_snapshot() -> dict[str, object]:
    try:
        from governance_runtime.engine.adapters import OpenCodeDesktopAdapter
        from governance_runtime.engine.orchestrator import run_engine_orchestrator
    except Exception as exc:  # pragma: no cover
        return {"available": False, "reason": "engine-runtime-module-unavailable", "error": str(exc)}

    output = run_engine_orchestrator(
        adapter=OpenCodeDesktopAdapter(),
        phase="1.1-Bootstrap",
        active_gate="ReadOnly Preflight",
        mode="user",
        next_gate_condition="Read-only governance completed",
        gate_key="PREFLIGHT",
        enable_live_engine=False,
    )
    return {
        "available": True,
        "runtime_mode": output.runtime.runtime_mode,
        "selfcheck_ok": output.runtime.selfcheck.ok,
        "repo_context_source": output.repo_context.source,
        "effective_operating_mode": output.effective_operating_mode,
        "resolved_operating_mode": output.resolved_operating_mode,
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


def _emit_persistence_gate_failure(
    *,
    code: str,
    message: str,
    expected: str,
    observed: dict[str, object],
    remediation: str,
    repo_fingerprint: str | None,
) -> Path:
    config_root = COMMANDS_HOME.parent if COMMANDS_HOME is not None else None
    emitted = emit_gate_failure(
        gate="PERSISTENCE",
        code=code,
        message=message,
        expected=expected,
        observed=observed,
        remediation=remediation,
        config_root=str(config_root) if config_root is not None else None,
        workspaces_home=str(WORKSPACES_HOME) if WORKSPACES_HOME is not None else None,
        repo_fingerprint=repo_fingerprint,
        phase="1.1-Bootstrap",
    )
    if not emitted:
        print(
            json.dumps(
                {
                    "persistenceGateFailure": "not-logged",
                    "reason_code": code,
                    "phase": "1.1-Bootstrap",
                    "message": "emit_gate_failure returned false",
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
    try:
        return resolve_log_path(
            config_root=config_root,
            commands_home=COMMANDS_HOME,
            workspaces_home=WORKSPACES_HOME,
            repo_fingerprint=repo_fingerprint,
        )
    except Exception:
        return Path("error.log.jsonl")


def _normalize_hook_failure_reason(proc: subprocess.CompletedProcess[str], result: dict[str, object]) -> tuple[str, str]:
    reason_code = str(result.get("reason_code") or "").strip()
    if reason_code:
        return reason_code, FAILURE_STAGE_HOOK_PAYLOAD
    if proc.returncode != 0:
        return "BLOCKED-WORKSPACE-PERSISTENCE", FAILURE_STAGE_SUBPROCESS
    return "BLOCKED-WORKSPACE-PERSISTENCE", FAILURE_STAGE_PARSE


def _canonical_hook_status(*, raw_status: object, reason_code: str, returncode: int) -> str:
    token = str(raw_status or "").strip().lower()
    if returncode != 0:
        if reason_code.startswith("BLOCKED-"):
            return HOOK_STATUS_BLOCKED
        return HOOK_STATUS_FAILED
    if token == HOOK_STATUS_OK:
        return HOOK_STATUS_OK
    if token not in {HOOK_STATUS_OK, HOOK_STATUS_BLOCKED, HOOK_STATUS_FAILED}:
        token = HOOK_STATUS_FAILED
    if reason_code.startswith("BLOCKED-"):
        return HOOK_STATUS_BLOCKED
    return token


def _clear_stale_failure_metadata(payload: dict[str, object]) -> None:
    for key in (
        "failure_stage",
        "reason_code",
        "stderr_snippet",
        "log_path",
        "stderr",
        "stdout",
        "hook_failure_stage",
        "hook_log_path",
    ):
        payload.pop(key, None)


def run_persistence_hook() -> dict[str, object]:
    output_mode = os.getenv("OPENCODE_BOOTSTRAP_OUTPUT", "final").strip().lower()
    mode = _effective_mode()
    hook_argv = [sys.executable, "-m", "governance_runtime.entrypoints.bootstrap_persistence_hook"]
    _hook_profiles = render_command_profiles(hook_argv)
    hook_command = str(_hook_profiles.get("cmd" if os.name == "nt" else "bash") or " ".join(hook_argv))

    if not writes_allowed():
        log_path = _emit_persistence_gate_failure(
            code="BLOCKED-WORKSPACE-PERSISTENCE",
            message="Persistence hook blocked by write policy before dispatch.",
            expected="writes allowed",
            observed={"mode": mode, "writes_allowed": False},
            remediation="Unset OPENCODE_FORCE_READ_ONLY or use a writable mode.",
            repo_fingerprint=None,
        )
        result = {
            "workspacePersistenceHook": HOOK_STATUS_BLOCKED,
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "reason": "writes-not-allowed",
            "impact": "fingerprint + persistence are required before any phase >= 2.1",
            "mode": mode,
            "writes_allowed": False,
            "log_path": str(log_path),
            "hook_invoked": False,
            "failure_stage": FAILURE_STAGE_WRITES_ALLOWED,
            "cwd": str(Path.cwd()),
            "repo_root_detected": "",
            "repo_root_source": "not-evaluated",
            "python_executable": sys.executable,
            "bootstrap_hook_command": hook_command,
            "git_probe": {"ok": False, "source": "not-evaluated"},
        }
        if output_mode != "silent":
            print(json.dumps(result, ensure_ascii=True))
        return result

    repo_root, repo_root_source, git_probe = _resolve_repo_root_for_hook()
    base_payload = {
        "cwd": str(Path.cwd()),
        "repo_root_detected": str(repo_root) if repo_root else "",
        "repo_root_source": repo_root_source,
        "python_executable": sys.executable,
        "bootstrap_hook_command": hook_command,
        "git_probe": git_probe,
        "hook_invoked": False,
        "failure_stage": FAILURE_STAGE_INIT,
    }

    if repo_root is None:
        log_path = _emit_persistence_gate_failure(
            code="BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            message="Repository root is not deterministically detectable for persistence hook dispatch.",
            expected="valid OPENCODE_REPO_ROOT or git rev-parse --show-toplevel",
            observed={"cwd": str(Path.cwd()), "git_probe": git_probe},
            remediation="Set OPENCODE_REPO_ROOT to a valid git repository root and rerun the local bootstrap launcher.",
            repo_fingerprint=None,
        )
        result = {
            **base_payload,
            "workspacePersistenceHook": "blocked",
            "reason_code": "BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            "reason": "repo-root-not-detectable",
            "writes_allowed": True,
            "log_path": str(log_path),
            "failure_stage": FAILURE_STAGE_REPO_ROOT,
        }
        if output_mode != "silent":
            print(json.dumps(result, ensure_ascii=True))
        return result

    env = dict(os.environ)
    env["OPENCODE_REPO_ROOT"] = str(repo_root)
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    repo_root_token = str(repo_root)
    commands_home_token = str(COMMANDS_HOME)
    if existing_pythonpath:
        env["PYTHONPATH"] = os.pathsep.join((repo_root_token, commands_home_token, existing_pythonpath))
    else:
        env["PYTHONPATH"] = os.pathsep.join((repo_root_token, commands_home_token))
    proc = subprocess.run(
        hook_argv,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
        env=env,
    )

    stdout_lines = [(line or "").strip() for line in (proc.stdout or "").splitlines() if (line or "").strip()]
    parsed_payload: dict[str, object] | None = None
    for candidate in reversed(stdout_lines):
        try:
            loaded = json.loads(candidate)
        except Exception:
            continue
        if isinstance(loaded, dict):
            parsed_payload = loaded
            break

    if parsed_payload is None:
        parsed_payload = {
            "workspacePersistenceHook": "blocked",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "reason": "hook-output-not-json",
            "stderr": (proc.stderr or "").strip()[:500],
            "stdout": (proc.stdout or "").strip()[:500],
        }

    result = {
        **parsed_payload,
        **base_payload,
        "hook_invoked": True,
    }
    if not isinstance(result.get("repo_fingerprint"), str):
        result["repo_fingerprint"] = ""

    raw_reason_code = str(result.get("reason_code") or "").strip()
    result["workspacePersistenceHook"] = _canonical_hook_status(
        raw_status=result.get("workspacePersistenceHook"),
        reason_code=raw_reason_code,
        returncode=proc.returncode,
    )

    hook_status = str(result.get("workspacePersistenceHook", "")).strip().lower()
    if hook_status == HOOK_STATUS_OK:
        _clear_stale_failure_metadata(result)
        if output_mode != "silent":
            print(json.dumps(result, ensure_ascii=True))
        return result

    result["failure_stage"] = FAILURE_STAGE_SUBPROCESS
    if parsed_payload.get("reason") == "hook-output-not-json":
        result["failure_stage"] = FAILURE_STAGE_PARSE
    elif hook_status != HOOK_STATUS_OK:
        result["failure_stage"] = FAILURE_STAGE_HOOK_PAYLOAD if proc.returncode == 0 else FAILURE_STAGE_SUBPROCESS

    reason_code, inferred_stage = _normalize_hook_failure_reason(proc, result)
    result["reason_code"] = reason_code

    if str(result.get("failure_stage", "")).strip() in {"", FAILURE_STAGE_INIT, FAILURE_STAGE_SUBPROCESS}:
        result["failure_stage"] = inferred_stage
    log_path = _emit_persistence_gate_failure(
        code=reason_code,
        message="Persistence hook module dispatch failed.",
        expected="python -m governance_runtime.entrypoints.bootstrap_persistence_hook exits with code 0",
        observed={
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "").strip()[:500],
            "stdout": (proc.stdout or "").strip()[:500],
            "payload_reason": str(result.get("reason") or ""),
        },
        remediation="Run the hook command directly and inspect returned reason_code/reason payload.",
        repo_fingerprint=(str(result.get("repo_fingerprint") or "") or None),
    )
    result["stderr_snippet"] = (proc.stderr or "").strip()[:500]
    result["log_path"] = str(log_path)

    if output_mode != "silent":
        print(json.dumps(result, ensure_ascii=True))
    return result


def emit_start_receipt() -> None:
    """Emit forensic receipt for desktop dispatch debugging."""
    repo_root, repo_root_source, _probe = _resolve_repo_root_for_hook()
    repo_fp = derive_repo_fingerprint(repo_root) if repo_root is not None else None
    planned_pointer_path = (COMMANDS_HOME.parent / "SESSION_STATE.json") if COMMANDS_HOME is not None else None
    planned_workspace_path = (WORKSPACES_HOME / repo_fp / "SESSION_STATE.json") if (repo_fp and WORKSPACES_HOME is not None) else None
    receipt = {
        "start_receipt": {
            "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "argv0": sys.argv[0] if sys.argv else "",
            "cwd": str(Path.cwd()),
            "file": __file__,
            "executable": sys.executable,
            "sys_path_0_3": sys.path[:3],
            "env_opencode_config_root": os.environ.get("OPENCODE_CONFIG_ROOT", ""),
            "env_opencode_home": os.environ.get("OPENCODE_HOME", ""),
            "computed_opencode_home": str(COMMANDS_HOME.parent) if COMMANDS_HOME is not None else None,
            "computed_commands_home": str(COMMANDS_HOME) if COMMANDS_HOME is not None else None,
            "computed_workspaces_home": str(WORKSPACES_HOME) if WORKSPACES_HOME is not None else None,
            "planned_pointer_path": str(planned_pointer_path) if planned_pointer_path is not None else None,
            "planned_workspace_session_path": str(planned_workspace_path) if planned_workspace_path else None,
            "derived_repo_fingerprint": repo_fp,
            "repo_root_detected": str(repo_root) if repo_root else "",
            "repo_root_source": repo_root_source,
            "binding_ok": BINDING_OK,
            "mode": _effective_mode(),
            "platform": platform.system().lower(),
        }
    }
    print(json.dumps(receipt, ensure_ascii=True))


def _session_state_file_path(repo_fingerprint: str) -> Path | None:
    if not repo_fingerprint or WORKSPACES_HOME is None:
        return None
    return WORKSPACES_HOME / repo_fingerprint / "SESSION_STATE.json"


def _read_json_document(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _write_json_document(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, str(path))
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def _root_state(document: Mapping[str, object]) -> dict[str, object]:
    root = document.get("SESSION_STATE")
    if isinstance(root, dict):
        return root
    if isinstance(root, Mapping):
        return dict(root)
    return {}


def _read_bool(state: Mapping[str, object], *keys: str) -> bool:
    for key in keys:
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _phase_ready_value(phase_value: object) -> int | None:
    token = normalize_phase_token(str(phase_value or ""))
    if not token:
        return None
    match = re.match(r"^(\d+)", token)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _bootstrap_satisfied(state: Mapping[str, object]) -> bool:
    bootstrap = state.get("Bootstrap")
    if not isinstance(bootstrap, Mapping):
        return False
    value = bootstrap.get("Satisfied")
    return isinstance(value, bool) and value is True


def _ticket_intake_ready(state: Mapping[str, object], phase_token: str) -> bool:
    if phase_rank(phase_token) < phase_rank("4"):
        return False
    if not _read_bool(state, "PersistenceCommitted", "persistence_committed"):
        return False
    if not _read_bool(state, "WorkspaceReadyGateCommitted", "workspace_ready_gate_committed"):
        return False
    if not _bootstrap_satisfied(state):
        return False
    return True


def _apply_ticket_intake_readiness(document: Mapping[str, object], *, phase_token: str) -> dict[str, object]:
    updated = dict(document)
    state = _root_state(updated)
    ready = _ticket_intake_ready(state, phase_token)
    state["ticket_intake_ready"] = ready
    phase_ready = _phase_ready_value(state.get("Phase") or phase_token)
    if phase_ready is not None:
        state["phase_ready"] = phase_ready
    updated["SESSION_STATE"] = state
    return updated


def _activation_intent_evidence() -> tuple[str, str, str]:
    config_root = COMMANDS_HOME.parent if COMMANDS_HOME is not None else None
    if config_root is None:
        return "${CONFIG_ROOT}/governance.activation_intent.json", "", "unknown"

    intent_path = config_root / "governance.activation_intent.json"
    canonical_path = "${CONFIG_ROOT}/governance.activation_intent.json"
    if not intent_path.exists():
        return canonical_path, "", "unknown"

    try:
        raw_text = intent_path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
    except Exception:
        return canonical_path, "", "unknown"

    if not isinstance(payload, dict):
        return canonical_path, "", "unknown"

    scope = str(payload.get("discovery_scope") or "full")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return canonical_path, sha256, scope


def _canonical_profile_id(raw: object) -> str:
    token = str(raw or "").strip()
    if not token:
        return ""
    if token.startswith("profile."):
        token = token[len("profile.") :]
    return token


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _detect_repo_profile(repo_root: Path | None) -> dict[str, object]:
    if repo_root is None or not repo_root.exists():
        return {
            "profile_id": DEFAULT_ACTIVE_PROFILE_ID,
            "profile_source": "repo-fallback",
            "profile_evidence": "repo-signals://unavailable",
            "repository_type": "unknown",
            "detection_confidence": "low",
        }

    scores: dict[str, int] = {
        "python": 0,
        "java": 0,
        "csharp": 0,
        "cpp": 0,
        "angular": 0,
    }
    evidence: dict[str, list[str]] = {key: [] for key in scores}

    strong_name_markers = {
        "python": {"pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.py", "setup.cfg", "pytest.ini"},
        "java": {"pom.xml", "build.gradle", "build.gradle.kts"},
        "csharp": {"global.json", "nuget.config"},
        "cpp": {"cmakelists.txt", "makefile"},
        "angular": {"angular.json", "nx.json"},
    }

    max_files = 12000
    seen_files = 0
    ignored_dirs = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
    }

    for current_root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        root_path = Path(current_root)
        for filename in files:
            seen_files += 1
            if seen_files > max_files:
                break
            lower_name = filename.lower()
            path = root_path / filename

            for ecosystem, markers in strong_name_markers.items():
                if lower_name in markers:
                    scores[ecosystem] += 3
                    if len(evidence[ecosystem]) < 8:
                        evidence[ecosystem].append(str(path.relative_to(repo_root)))

            suffix = path.suffix.lower()
            if suffix == ".py":
                scores["python"] += 1
            elif suffix == ".java":
                scores["java"] += 1
            elif suffix == ".cs":
                scores["csharp"] += 1
            elif suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"}:
                scores["cpp"] += 1

            if lower_name.endswith(".csproj") or lower_name.endswith(".sln"):
                scores["csharp"] += 3
                if len(evidence["csharp"]) < 8:
                    evidence["csharp"].append(str(path.relative_to(repo_root)))

            if lower_name == "package.json":
                package_json = _safe_read(path)
                if "@angular/core" in package_json or "@nrwl/angular" in package_json:
                    scores["angular"] += 3
                    if len(evidence["angular"]) < 8:
                        evidence["angular"].append(str(path.relative_to(repo_root)))
        if seen_files > max_files:
            break

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_key, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    repository_type = "unknown"
    profile_id = DEFAULT_ACTIVE_PROFILE_ID
    profile_source = "repo-fallback"
    confidence = "low"

    if top_score > 0 and second_score > 0 and (top_score - second_score) <= 1:
        repository_type = "polyglot"
        profile_source = "ambiguous"
        confidence = "low"
    elif top_score >= 4 and (top_score - second_score) >= 2:
        repository_type = top_key
        profile_source = "auto-detected-single"
        confidence = "high" if top_score >= 8 else "medium"
        profile_map = {
            "python": "backend-python",
            "java": "backend-java",
            "angular": "frontend-angular-nx",
            "csharp": DEFAULT_ACTIVE_PROFILE_ID,
            "cpp": DEFAULT_ACTIVE_PROFILE_ID,
        }
        candidate = profile_map.get(top_key, DEFAULT_ACTIVE_PROFILE_ID)
        profile_id = candidate if candidate in SUPPORTED_PROFILE_IDS else DEFAULT_ACTIVE_PROFILE_ID
    elif top_score > 0:
        repository_type = top_key
        profile_source = "repo-fallback"
        confidence = "low"

    top_evidence = ",".join(evidence[top_key][:3]) if top_key in evidence else "none"
    profile_evidence = f"repo-signals://{repository_type};top={top_key}:{top_score};second={second_score};markers={top_evidence}"

    return {
        "profile_id": profile_id,
        "profile_source": profile_source,
        "profile_evidence": profile_evidence,
        "repository_type": repository_type,
        "detection_confidence": confidence,
    }


def _profile_rulebook_path_token(profile_id: str) -> str:
    return f"${{COMMANDS_HOME}}/rulesets/profiles/rules.{profile_id}.yml"


def _addon_rulebook_path_token() -> str:
    return f"${{COMMANDS_HOME}}/rulesets/profiles/{DEFAULT_ADDON_RULEBOOK}"


def _normalize_business_rules_state(state: dict[str, object]) -> None:
    scope = state.get("Scope")
    if not isinstance(scope, dict):
        scope = {}

    business_rules = state.get("BusinessRules")
    if not isinstance(business_rules, dict):
        business_rules = {}

    declared_outcome = str(business_rules.get("Outcome") or scope.get("BusinessRules") or "").strip().lower()
    execution_evidence = bool(business_rules.get("ExecutionEvidence") is True)
    inventory_loaded = bool(business_rules.get("InventoryLoaded") is True)
    extracted_count = int(business_rules.get("ExtractedCount") or 0) if str(business_rules.get("ExtractedCount") or "0").isdigit() else 0
    final_report_available = bool(
        str(business_rules.get("ValidationResult") or "").strip()
        or str(business_rules.get("ReportSha") or "").strip()
    )
    signal = has_br_signal(
        declared_outcome=declared_outcome,
        report=business_rules.get("ValidationReport") if isinstance(business_rules.get("ValidationReport"), dict) else None,
        persistence_result={
            "execution_evidence": execution_evidence,
            "inventory_loaded": inventory_loaded,
            "extracted_count": extracted_count,
            "validation_signal": bool(str(business_rules.get("ValidationResult") or "").strip()),
            "report_sha_present": bool(str(business_rules.get("ReportSha") or "").strip()),
            "source_phase": str(business_rules.get("SourcePhase") or ""),
        },
    )
    extracted_allowed = (
        declared_outcome == "extracted"
        and execution_evidence
        and inventory_loaded
        and extracted_count > 0
        and str(business_rules.get("ValidationResult") or "").strip().lower() == "passed"
    )
    normalized = canonicalize_business_rules_outcome(
        declared_outcome=declared_outcome,
        extracted_allowed=extracted_allowed,
        final_report_available=final_report_available,
        br_signal=signal,
    )

    scope["BusinessRules"] = normalized
    business_rules["Outcome"] = normalized
    business_rules["HasSignal"] = signal
    business_rules.setdefault("ExecutionEvidence", False)
    business_rules.setdefault("InventoryLoaded", False)
    business_rules.setdefault("ExtractedCount", 0)
    if normalized == "extracted":
        business_rules["Decision"] = "execute"
        business_rules.setdefault("InventoryFileStatus", "written")
    elif normalized == "unresolved" and not signal:
        business_rules["Decision"] = "pending"
        business_rules.setdefault("InventoryFileStatus", "unknown")
    else:
        business_rules["Decision"] = "skip"
        business_rules.setdefault("InventoryFileStatus", "withheld")

    state["Scope"] = scope
    state["BusinessRules"] = business_rules


def _hydrate_transition_state(
    document: dict[str, object],
    *,
    repo_fingerprint: str,
    requested_token: str,
    repo_root: Path | None = None,
) -> dict[str, object]:
    state = _root_state(document)
    state.setdefault("phase_transition_evidence", False)

    profile_override = _canonical_profile_id(get_profile_override())
    detection = _detect_repo_profile(repo_root)
    detected_profile_id = str(detection.get("profile_id") or DEFAULT_ACTIVE_PROFILE_ID)
    profile_id = profile_override or detected_profile_id
    if profile_id not in SUPPORTED_PROFILE_IDS:
        profile_id = DEFAULT_ACTIVE_PROFILE_ID
    state["ActiveProfile"] = f"profile.{profile_id}"
    if profile_override:
        source = "workspace-config" if os.environ.get("OPENCODE_WORKSPACE_CONFIG") else "tenant-config"
        tenant = load_tenant_config()
        state["ProfileSource"] = source
        state["ProfileEvidence"] = f"{source}://{tenant.tenant_id if tenant else 'unknown'}/profile.{profile_id}"
    else:
        state["ProfileSource"] = str(detection.get("profile_source") or "repo-fallback")
        state["ProfileEvidence"] = str(detection.get("profile_evidence") or f"repo-signals://profile.{profile_id}")
    state["DetectionConfidence"] = str(detection.get("detection_confidence") or "low")

    intent_path, intent_sha, intent_scope = _activation_intent_evidence()
    state.setdefault(
        "Intent",
        {
            "Path": intent_path,
            "Sha256": intent_sha,
            "EffectiveScope": intent_scope,
        },
    )
    intent = state.get("Intent")
    if isinstance(intent, dict):
        intent.setdefault("Path", intent_path)
        intent.setdefault("Sha256", intent_sha)
        intent.setdefault("EffectiveScope", intent_scope)

    if phase_rank(requested_token) >= phase_rank("1.3"):
        profile_loaded = True
        addon_loaded = True
        loaded = state.get("LoadedRulebooks")
        if not isinstance(loaded, dict):
            loaded = {}
        if not isinstance(loaded.get("core"), str) or not str(loaded.get("core") or "").strip():
            loaded["core"] = "${COMMANDS_HOME}/rules.md"
        loaded["profile"] = _profile_rulebook_path_token(profile_id) if profile_loaded else ""
        loaded["templates"] = "${COMMANDS_HOME}/master.md"
        addons_loaded = loaded.get("addons")
        if not isinstance(addons_loaded, dict):
            addons_loaded = {}
        addons_loaded[DEFAULT_ADDON_KEY] = _addon_rulebook_path_token() if addon_loaded else ""
        loaded["addons"] = addons_loaded
        state["LoadedRulebooks"] = loaded

        evidence = state.get("RulebookLoadEvidence")
        if not isinstance(evidence, dict):
            evidence = {}
        if not isinstance(evidence.get("core"), str) or not str(evidence.get("core") or "").strip() or str(evidence.get("core")) == "deferred":
            evidence["core"] = "${COMMANDS_HOME}/rules.md"
        evidence["profile"] = loaded["profile"] if loaded["profile"] else "missing"
        evidence["templates"] = loaded["templates"]
        addons_evidence = evidence.get("addons")
        if not isinstance(addons_evidence, dict):
            addons_evidence = {}
        addons_evidence[DEFAULT_ADDON_KEY] = loaded["addons"].get(DEFAULT_ADDON_KEY) or "missing"
        evidence["addons"] = addons_evidence
        state["RulebookLoadEvidence"] = evidence
        addon_runtime = state.get("AddonsEvidence")
        if not isinstance(addon_runtime, dict):
            addon_runtime = {}
        addon_runtime[DEFAULT_ADDON_KEY] = {
            "status": "loaded" if addon_loaded else "missing",
            "path": _addon_rulebook_path_token(),
            "source": "bootstrap-baseline",
        }
        state["AddonsEvidence"] = addon_runtime

    if phase_rank(requested_token) >= phase_rank("2"):
        repo_home = WORKSPACES_HOME / repo_fingerprint if WORKSPACES_HOME is not None else None
        cache_exists = bool(repo_home and (repo_home / "repo-cache.yaml").exists())
        digest_exists = bool(repo_home and (repo_home / "repo-map-digest.md").exists())

        state.setdefault(
            "RepoDiscovery",
            {
                "Completed": bool(cache_exists and digest_exists),
                "RepoCacheFile": "${REPO_CACHE_FILE}",
                "RepoMapDigestFile": "${REPO_DIGEST_FILE}",
            },
        )
        repo_discovery = state.get("RepoDiscovery")
        if isinstance(repo_discovery, dict):
            repo_discovery["Completed"] = bool(cache_exists and digest_exists)
            repo_discovery.setdefault("RepoCacheFile", "${REPO_CACHE_FILE}")
            repo_discovery.setdefault("RepoMapDigestFile", "${REPO_DIGEST_FILE}")

        state.setdefault("RepoCacheFile", {"TargetPath": "${REPO_CACHE_FILE}", "FileStatus": "written" if cache_exists else "unknown"})
        state.setdefault("RepoMapDigestFile", {"FilePath": "${REPO_DIGEST_FILE}", "FileStatus": "written" if digest_exists else "unknown"})
        state.setdefault("DecisionPack", {"FilePath": "${REPO_DECISION_PACK_FILE}", "FileStatus": "written"})
        state.setdefault("WorkspaceMemoryFile", {"TargetPath": "${WORKSPACE_MEMORY_FILE}", "FileStatus": "written"})
        scope_obj = state.get("Scope")
        if not isinstance(scope_obj, dict):
            scope_obj = {}
        scope_obj["RepositoryType"] = str(detection.get("repository_type") or scope_obj.get("RepositoryType") or "unknown")
        state["Scope"] = scope_obj

    if phase_rank(requested_token) >= phase_rank("2.1"):
        _normalize_business_rules_state(state)
        scope = state.get("Scope")
        if not isinstance(scope, dict):
            scope = {}

        gates = state.get("Gates")
        if isinstance(gates, dict):
            scope_outcome = str(scope.get("BusinessRules") or "").strip().lower()
            br_raw = state.get("BusinessRules")
            br_state: dict[str, object] = dict(br_raw) if isinstance(br_raw, dict) else {}
            br_report = br_state.get("ValidationReport")
            has_br_artifact_signal = has_br_signal(
                declared_outcome=scope_outcome,
                report=cast(dict[str, object], br_report) if isinstance(br_report, dict) else None,
                persistence_result={
                    "execution_evidence": br_state.get("ExecutionEvidence") is True,
                    "inventory_loaded": br_state.get("InventoryLoaded") is True,
                    "extracted_count": br_state.get("ExtractedCount") or 0,
                    "validation_signal": bool(str(br_state.get("ValidationResult") or "").strip()),
                    "report_sha_present": bool(str(br_state.get("ReportSha") or "").strip()),
                    "source_phase": str(br_state.get("SourcePhase") or ""),
                },
            )
            if scope_outcome == "extracted":
                gates["P5.4-BusinessRules"] = gates.get("P5.4-BusinessRules") or "pending"
            elif scope_outcome == "gap-detected":
                gates["P5.4-BusinessRules"] = "gap-detected"
            elif has_br_artifact_signal:
                gates["P5.4-BusinessRules"] = "gap-detected"
            elif scope_outcome == "unresolved":
                gates["P5.4-BusinessRules"] = "pending"
            else:
                gates["P5.4-BusinessRules"] = "not-applicable"

    if requested_token == "3A":
        inventory = state.get("APIInventory")
        if not isinstance(inventory, dict):
            inventory = {}
        inventory["Status"] = "completed" if api_in_scope(state) else "not-applicable"
        state["APIInventory"] = inventory

    document["SESSION_STATE"] = state
    return document


def run_kernel_continuation(hook_result: Mapping[str, object]) -> dict[str, object]:
    hook_status = str(hook_result.get("workspacePersistenceHook") or "").strip().lower()
    if hook_status and hook_status != HOOK_STATUS_OK:
        payload: dict[str, object] = {
            "kernelContinuation": "blocked",
            "reason": "persistence-hook-blocked",
            "reason_code": str(hook_result.get("reason_code") or "BLOCKED-WORKSPACE-PERSISTENCE"),
            "repo_fingerprint": str(hook_result.get("repo_fingerprint") or ""),
            "session_state_path": "",
        }
        return dict(payload)
    repo_fingerprint = str(hook_result.get("repo_fingerprint") or "").strip()
    repo_root_value = str(hook_result.get("repo_root_detected") or "").strip()
    repo_root: Path | None = None
    if repo_root_value:
        candidate = Path(repo_root_value)
        if candidate.is_absolute() and candidate.exists():
            repo_root = candidate
    session_path = _session_state_file_path(repo_fingerprint)
    if session_path is None or not session_path.exists():
        next_cmd = bootstrap_command(repo_fingerprint if repo_fingerprint else None)
        payload: dict[str, object] = {
            "kernelContinuation": "blocked",
            "reason": "missing-session-state",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "repo_fingerprint": repo_fingerprint,
            "session_state_path": str(session_path) if session_path is not None else "",
            "hook_reason": str(hook_result.get("reason") or ""),
            "hook_failure_stage": str(hook_result.get("failure_stage") or ""),
            "hook_log_path": str(hook_result.get("log_path") or ""),
            "recovery_action": "Re-run the local bootstrap launcher; if it still fails, run the bootstrap command directly and inspect the returned reason/log path.",
            "next_command": next_cmd,
        }
        return dict(payload)

    document = _read_json_document(session_path)
    if document is None:
        payload: dict[str, object] = {
            "kernelContinuation": "blocked",
            "reason": "invalid-session-state-json",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "repo_fingerprint": repo_fingerprint,
            "session_state_path": str(session_path),
        }
        return dict(payload)

    state = _root_state(document)
    state["phase_transition_evidence"] = True
    preflight = state.get("Preflight")
    if not isinstance(preflight, dict):
        preflight = {}
    preflight.setdefault("BuildToolchain", _preflight_build_toolchain_snapshot())
    state["Preflight"] = preflight
    current_phase = str(state.get("Phase") or "")
    requested_token = normalize_phase_token(current_phase) or "1.2"
    max_hops = 8
    hops = 0
    last_result: dict[str, object] = {
        "phase": current_phase,
        "next_token": str(state.get("Next") or ""),
        "status": "OK",
        "active_gate": str(state.get("active_gate") or ""),
        "next_gate_condition": str(state.get("next_gate_condition") or ""),
        "source": "session-state",
    }

    resolved_token = normalize_phase_token(current_phase) or ""
    while hops < max_hops:
        hops += 1
        document = _hydrate_transition_state(
            document,
            repo_fingerprint=repo_fingerprint,
            requested_token=requested_token,
            repo_root=repo_root,
        )
        state = _root_state(document)
        requested_active_gate = str(state.get("active_gate") or state.get("ActiveGate") or "Automatic routing")
        requested_next_gate_condition = str(
            state.get("next_gate_condition") or state.get("NextGateCondition") or "Continue automatic phase routing"
        )

        routed = route_phase(
            requested_phase=requested_token,
            requested_active_gate=requested_active_gate,
            requested_next_gate_condition=requested_next_gate_condition,
            session_state_document=document,
            repo_is_git_root=True,
            live_repo_fingerprint=repo_fingerprint,
        )
        last_result = {
            "phase": routed.phase,
            "next_token": routed.next_token or "",
            "status": routed.status,
            "active_gate": routed.active_gate,
            "next_gate_condition": routed.next_gate_condition,
            "source": routed.source,
        }

        document = dict(
            with_kernel_result(
                document,
                phase=routed.phase,
                next_token=routed.next_token,
                active_gate=routed.active_gate,
                next_gate_condition=routed.next_gate_condition,
                status=routed.status,
                spec_hash=routed.spec_hash,
                spec_path=routed.spec_path,
                spec_loaded_at=routed.spec_loaded_at,
                log_paths=routed.log_paths,
                event_id=routed.event_id,
                plan_record_status=routed.plan_record_status,
                plan_record_versions=routed.plan_record_versions,
            )
        )

        resolved_token = normalize_phase_token(routed.phase)
        if routed.status != "OK" or phase_rank(resolved_token) >= phase_rank("4"):
            break

        next_token = normalize_phase_token(routed.next_token or "")
        if not next_token:
            break
        if next_token == requested_token and resolved_token == requested_token:
            break
        requested_token = next_token

    document = _apply_ticket_intake_readiness(document, phase_token=resolved_token)
    final_state = _root_state(document)
    final_state["phase_transition_evidence"] = False
    final_phase = str(final_state.get("Phase") or final_state.get("phase") or "").strip()
    has_ticket = bool(str(final_state.get("Ticket") or "").strip())
    has_task = bool(str(final_state.get("Task") or "").strip())
    has_ticket_digest = bool(str(final_state.get("TicketRecordDigest") or "").strip())
    has_task_digest = bool(str(final_state.get("TaskRecordDigest") or "").strip())
    if final_phase == "4" and not (has_ticket or has_task or has_ticket_digest or has_task_digest):
        final_state["phase4_intake_source"] = "bootstrap"
        final_state["phase4_intake_evidence"] = False
        final_state["phase4_intake_updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        final_state["phase_transition_evidence"] = False
        apply_fresh_start_business_rules_neutralization(final_state)
    _write_json_document(session_path, document)
    payload = {
        "kernelContinuation": "ok" if str(last_result.get("status") or "") == "OK" else "blocked",
        "auto_continuation": "route_phase",
        "route_phase_invoked": bool(hops > 0),
        "repo_fingerprint": repo_fingerprint,
        "session_state_path": str(session_path),
        "phase": str(last_result.get("phase") or ""),
        "next_token": str(last_result.get("next_token") or ""),
        "active_gate": str(last_result.get("active_gate") or ""),
        "next_gate_condition": str(last_result.get("next_gate_condition") or ""),
        "source": str(last_result.get("source") or ""),
        "hops": hops,
    }
    if phase_rank(resolved_token) >= phase_rank("4"):
        payload["next_step"] = "Open OpenCode Desktop in this repository and run /continue"
    else:
        payload["next_step"] = "Rerun the local bootstrap launcher until Phase 4 is reached"
    return payload


def main() -> int:
    if os.getenv("OPENCODE_FORCE_READ_ONLY", "").strip() == "1":
        raise SystemExit(2)
    if os.getenv("OPENCODE_BOOTSTRAP_VERBOSE", "").strip() == "1":
        emit_start_receipt()
    emit_preflight()
    emit_permission_probes()
    hook_result = run_persistence_hook()
    payload = run_kernel_continuation(hook_result)
    if os.getenv("OPENCODE_BOOTSTRAP_OUTPUT", "final").strip().lower() != "full":
        print(json.dumps(payload, ensure_ascii=True))
    hook_status = str(hook_result.get("workspacePersistenceHook") or "").strip().lower()
    if hook_status and hook_status != HOOK_STATUS_OK:
        raise SystemExit(2)
    if payload.get("kernelContinuation") != "ok":
        raise SystemExit(2)
    if os.getenv("OPENCODE_ENGINE_SHADOW_EMIT") == "1":
        print(json.dumps({"engineRuntimeShadow": build_engine_shadow_snapshot()}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
