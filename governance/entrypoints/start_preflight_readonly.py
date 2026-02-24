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
from typing import Any

_COMMANDS_HOME = str(Path(__file__).parent.parent)
if _COMMANDS_HOME not in sys.path:
    sys.path.insert(0, _COMMANDS_HOME)

from governance.entrypoints.command_profiles import render_command_profiles
from governance.entrypoints.write_policy import writes_allowed, EFFECTIVE_MODE
_BindingEvidenceResolver: Any = None
try:
    from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver as _ImportedBindingEvidenceResolver

    _BindingEvidenceResolver = _ImportedBindingEvidenceResolver
except Exception:
    class _FallbackBindingEvidence:
        def __init__(self, commands_home: Path):
            self.commands_home = commands_home
            self.workspaces_home = commands_home.parent / "workspaces"
            self.binding_ok = False
            self.governance_paths_json: Path | None = None
            self.python_command = "python3"

    class _FallbackBindingEvidenceResolver:
        def resolve(self, mode: str = "user") -> _FallbackBindingEvidence:
            _ = mode
            commands_home = Path(__file__).parent.parent
            evidence = _FallbackBindingEvidence(commands_home)
            candidate = commands_home / "governance.paths.json"
            if not candidate.is_file():
                return evidence
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                paths = payload.get("paths") if isinstance(payload, dict) else None
                if isinstance(paths, dict):
                    configured_commands = paths.get("commandsHome")
                    configured_workspaces = paths.get("workspacesHome")
                    configured_python = paths.get("pythonCommand")
                    if isinstance(configured_commands, str) and configured_commands.strip():
                        evidence.commands_home = Path(configured_commands.strip())
                    if isinstance(configured_workspaces, str) and configured_workspaces.strip():
                        evidence.workspaces_home = Path(configured_workspaces.strip())
                    if isinstance(configured_python, str) and configured_python.strip():
                        evidence.python_command = configured_python.strip()
                evidence.binding_ok = True
                evidence.governance_paths_json = candidate
            except Exception:
                evidence.binding_ok = False
            return evidence

    _BindingEvidenceResolver = _FallbackBindingEvidenceResolver

try:
    from bootstrap.repo_identity import derive_fingerprint as _derive_fingerprint_ssot
except Exception:
    _derive_fingerprint_ssot = None

try:
    from governance.infrastructure.logging.global_error_handler import (
        emit_gate_failure,
        install_global_handlers,
        resolve_log_path,
        set_error_context,
    )
except Exception:
    from governance.infrastructure.logging.error_logs import safe_log_error

    def install_global_handlers(context_provider=None):  # type: ignore
        _ = context_provider

    def set_error_context(ctx):  # type: ignore
        _ = ctx

    def emit_gate_failure(*args: Any, **kwargs: Any) -> bool:  # type: ignore
        _ = args
        gate = str(kwargs.get("gate") or "PERSISTENCE")
        code = str(kwargs.get("code") or "BLOCKED-WORKSPACE-PERSISTENCE")
        message = str(kwargs.get("message") or "Gate failure")
        observed = kwargs.get("observed")
        expected = kwargs.get("expected")
        remediation = kwargs.get("remediation")
        phase = str(kwargs.get("phase") or "1.1-Bootstrap")
        repo_fingerprint = kwargs.get("repo_fingerprint")
        raw_config_root = kwargs.get("config_root")
        config_root_path = Path(str(raw_config_root)) if raw_config_root else None
        result = safe_log_error(
            reason_key=code,
            message=message,
            config_root=config_root_path,
            phase=phase,
            gate=gate,
            mode=_effective_mode(),
            repo_fingerprint=(str(repo_fingerprint) if repo_fingerprint else None),
            command="start_preflight_readonly.py",
            component="start-preflight",
            observed_value={"observed": observed, "expected": expected},
            expected_constraint=str(expected) if expected else None,
            remediation=str(remediation) if remediation else None,
            result="blocked",
        )
        return result.get("status") == "logged"

    def resolve_log_path(*, config_root=None, commands_home=None, workspaces_home=None, repo_fingerprint=None) -> Path:  # type: ignore
        root = Path(config_root) if config_root else (Path.home() / ".config" / "opencode")
        if repo_fingerprint and workspaces_home:
            return Path(workspaces_home) / repo_fingerprint / "logs" / "error.log.jsonl"
        if commands_home:
            return Path(commands_home) / "logs" / "error.log.jsonl"
        return root / "logs" / "error.log.jsonl"
# SSOT: Ensure global error handler is installed before any operations
def _install_global_error_handler() -> None:
    try:
        from governance.infrastructure.logging.global_error_handler import install_global_handlers
        install_global_handlers()
    except Exception:
        pass

_install_global_error_handler()


def _effective_mode() -> str:
    return EFFECTIVE_MODE


def _resolve_bindings() -> tuple[Path, Path, bool, Path | None, str]:
    resolver = _BindingEvidenceResolver()
    effective_mode = _effective_mode()
    evidence = resolver.resolve(mode=effective_mode)
    python_command = evidence.python_command.strip() if evidence.python_command else ""
    if not python_command:
        python_command = "python3"
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


def emit_preflight() -> None:
    required_now: list[str] = []
    required_later: list[str] = []
    if TOOL_CATALOG is not None and TOOL_CATALOG.exists():
        payload = json.loads(TOOL_CATALOG.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for item in payload.get("required_now", []):
                if isinstance(item, dict):
                    cmd = str(item.get("command") or "").strip().replace("${PYTHON_COMMAND}", PYTHON_COMMAND)
                    if cmd and cmd not in required_now:
                        required_now.append(cmd)
            for item in payload.get("required_later", []):
                if isinstance(item, dict):
                    cmd = str(item.get("command") or "").strip().replace("${PYTHON_COMMAND}", PYTHON_COMMAND)
                    if cmd and cmd not in required_later and cmd not in required_now:
                        required_later.append(cmd)
    if not required_now:
        required_now = ["git", PYTHON_COMMAND]

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
    }
    print(json.dumps(payload, ensure_ascii=True))


def emit_permission_probes() -> None:
    checks = [
        {
            "probe": "fs.read_commands_home",
            "available": COMMANDS_HOME.exists() and os.access(COMMANDS_HOME, os.R_OK),
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
                    "next": "continue bootstrap" if not missing else "grant required permissions and rerun /start",
                }
            },
            ensure_ascii=True,
        )
    )


def bootstrap_command_argv(repo_fp: str | None) -> list[str]:
    repo_value = repo_fp if repo_fp else "<repo_fingerprint>"
    return [PYTHON_COMMAND, "-m", "governance.entrypoints.bootstrap_session_state", "--repo-fingerprint", repo_value]


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
        from governance.engine.adapters import OpenCodeDesktopAdapter
        from governance.engine.orchestrator import run_engine_orchestrator
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
        try:
            from governance.infrastructure.logging.error_logs import safe_log_error

            safe_log_error(
                reason_key=code,
                message=message,
                config_root=config_root,
                phase="1.1-Bootstrap",
                gate="PERSISTENCE",
                mode=_effective_mode(),
                repo_fingerprint=repo_fingerprint,
                command="start_preflight_readonly.py",
                component="start-preflight",
                observed_value=observed,
                expected_constraint=expected,
                remediation=remediation,
                result="blocked",
            )
        except Exception:
            pass
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
    if token == HOOK_STATUS_OK:
        return HOOK_STATUS_OK
    if token not in {HOOK_STATUS_OK, HOOK_STATUS_BLOCKED, HOOK_STATUS_FAILED}:
        token = HOOK_STATUS_FAILED
    if reason_code.startswith("BLOCKED-"):
        return HOOK_STATUS_BLOCKED
    if returncode != 0 and token == HOOK_STATUS_OK:
        return HOOK_STATUS_FAILED
    return token


def run_persistence_hook() -> dict[str, object]:
    mode = _effective_mode()
    hook_argv = [sys.executable, "-m", "governance.entrypoints.start_persistence_hook"]
    hook_command = " ".join(hook_argv)

    if not writes_allowed():
        log_path = _emit_persistence_gate_failure(
            code="BLOCKED-WORKSPACE-PERSISTENCE",
            message="Persistence hook blocked by write policy before dispatch.",
            expected="writes allowed",
            observed={"mode": mode, "writes_allowed": False},
            remediation="Unset OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY or use a writable mode.",
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
        print(json.dumps(result, ensure_ascii=True))
        raise SystemExit(2)

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
            remediation="Set OPENCODE_REPO_ROOT to a valid git repository root and rerun /start.",
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
        print(json.dumps(result, ensure_ascii=True))
        raise SystemExit(2)

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
        "failure_stage": FAILURE_STAGE_SUBPROCESS,
    }
    if not isinstance(result.get("repo_fingerprint"), str):
        result["repo_fingerprint"] = ""

    if parsed_payload.get("reason") == "hook-output-not-json":
        result["failure_stage"] = FAILURE_STAGE_PARSE
    elif proc.returncode != 0:
        result["failure_stage"] = FAILURE_STAGE_SUBPROCESS
    elif str(result.get("workspacePersistenceHook", "")).strip().lower() != HOOK_STATUS_OK:
        result["failure_stage"] = FAILURE_STAGE_HOOK_PAYLOAD

    reason_code, inferred_stage = _normalize_hook_failure_reason(proc, result)
    result["reason_code"] = reason_code
    result["workspacePersistenceHook"] = _canonical_hook_status(
        raw_status=result.get("workspacePersistenceHook"),
        reason_code=reason_code,
        returncode=proc.returncode,
    )

    if str(result.get("workspacePersistenceHook", "")).strip().lower() != HOOK_STATUS_OK:
        if str(result.get("failure_stage", "")).strip() in {"", FAILURE_STAGE_INIT, FAILURE_STAGE_SUBPROCESS}:
            result["failure_stage"] = inferred_stage
        log_path = _emit_persistence_gate_failure(
            code=reason_code,
            message="Persistence hook module dispatch failed.",
            expected="python -m governance.entrypoints.start_persistence_hook exits with code 0",
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

    print(json.dumps(result, ensure_ascii=True))
    if str(result.get("workspacePersistenceHook")).strip().lower() != HOOK_STATUS_OK:
        raise SystemExit(2)
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


def main() -> int:
    emit_start_receipt()
    emit_preflight()
    emit_permission_probes()
    run_persistence_hook()
    if os.getenv("OPENCODE_ENGINE_SHADOW_EMIT") == "1":
        print(json.dumps({"engineRuntimeShadow": build_engine_shadow_snapshot()}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
