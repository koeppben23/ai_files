#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, cast

_COMMANDS_HOME = str(Path(__file__).parent.parent)
if _COMMANDS_HOME not in sys.path:
    sys.path.insert(0, _COMMANDS_HOME)

from diagnostics.command_profiles import render_command_profiles
from diagnostics.write_policy import writes_allowed, EFFECTIVE_MODE
from governance.application.use_cases.start_bootstrap import evaluate_start_identity
from governance.engine.adapters import LocalHostAdapter
from governance.infrastructure.path_contract import normalize_absolute_path
from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.mode_repo_rules import resolve_env_operating_mode
from governance.infrastructure.wiring import configure_gateway_registry

try:
    from diagnostics.global_error_handler import (
        emit_gate_failure,
        install_global_handlers,
        resolve_log_path,
        set_error_context,
    )
except ImportError:
    def install_global_handlers(context_provider=None):  # type: ignore
        pass
    def set_error_context(ctx):  # type: ignore
        pass
    def emit_gate_failure(*args: Any, **kwargs: Any) -> bool:  # type: ignore
        return False
    def resolve_log_path(*, config_root=None, workspaces_home=None, repo_fingerprint=None) -> Path:  # type: ignore
        root = Path(config_root) if config_root else (Path.home() / ".config" / "opencode")
        if repo_fingerprint and workspaces_home:
            return Path(workspaces_home) / repo_fingerprint / "logs" / "error.log.jsonl"
        return root / "logs" / "error.log.jsonl"
# SSOT: Ensure global error handler is installed before any operations
def _install_global_error_handler() -> None:
    try:
        from diagnostics.global_error_handler import install_global_handlers
        install_global_handlers()
    except ImportError:
        pass

_install_global_error_handler()


def _effective_mode() -> str:
    return EFFECTIVE_MODE


def _resolve_bindings() -> tuple[Path, Path, bool, Path | None, str]:
    resolver = BindingEvidenceResolver()
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
TOOL_CATALOG = COMMANDS_HOME / "diagnostics" / "tool_requirements.json"


class _RepoIdentityProbeAdapter(LocalHostAdapter):
    def __init__(self, repo_root: Path):
        super().__init__()
        resolved = normalize_absolute_path(str(repo_root), purpose="repo_root")
        self._repo_root = resolved
        env = dict(os.environ)
        env["OPENCODE_REPO_ROOT"] = str(resolved)
        self._env = env

    def environment(self):
        return self._env

    def cwd(self) -> Path:
        return self._repo_root


def derive_repo_fingerprint(repo_root: Path) -> str | None:
    try:
        normalized_repo_root = normalize_absolute_path(str(repo_root), purpose="repo_root")
    except Exception:
        return None

    try:
        configure_gateway_registry()
        identity = evaluate_start_identity(adapter=cast(Any, _RepoIdentityProbeAdapter(normalized_repo_root)))
        fp = (identity.repo_fingerprint or "").strip()
    except Exception:
        fp = None

    return fp or None


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
    if TOOL_CATALOG.exists():
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
    return [PYTHON_COMMAND, "diagnostics/bootstrap_session_state.py", "--repo-fingerprint", repo_value]


def bootstrap_command(repo_fp: str | None) -> str:
    return str(render_command_profiles(bootstrap_command_argv(repo_fp)).get("bash") or "")


def _resolve_repo_root_for_hook() -> tuple[Path | None, str, dict[str, object]]:
    env_root = os.environ.get("OPENCODE_REPO_ROOT", "").strip()
    if env_root:
        try:
            resolved_env_root = normalize_absolute_path(env_root, purpose="OPENCODE_REPO_ROOT")
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
            resolved_git_root = normalize_absolute_path(root_text, purpose="git-rev-parse")
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
        next_gate_condition="Read-only diagnostics completed",
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


def run_persistence_hook() -> dict[str, object]:
    mode = _effective_mode()
    repo_root, repo_root_source, git_probe = _resolve_repo_root_for_hook()
    hook_argv = [sys.executable, "-m", "diagnostics.start_persistence_hook"]
    hook_command = " ".join(hook_argv)
    base_payload = {
        "cwd": str(Path.cwd()),
        "repo_root_detected": str(repo_root) if repo_root else "",
        "repo_root_source": repo_root_source,
        "python_executable": sys.executable,
        "bootstrap_hook_command": hook_command,
        "git_probe": git_probe,
    }

    if repo_root is None:
        log_path = resolve_log_path(
            config_root=COMMANDS_HOME.parent,
            workspaces_home=WORKSPACES_HOME,
            repo_fingerprint=None,
        )
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            message="Repository root is not deterministically detectable for persistence hook dispatch.",
            expected="valid OPENCODE_REPO_ROOT or git rev-parse --show-toplevel",
            observed={"cwd": str(Path.cwd()), "git_probe": git_probe},
            remediation="Set OPENCODE_REPO_ROOT to a valid git repository root and rerun /start.",
            config_root=str(COMMANDS_HOME.parent),
            workspaces_home=str(WORKSPACES_HOME),
            repo_fingerprint=None,
            phase="1.1-Bootstrap",
        )
        result = {
            "workspacePersistenceHook": "failed",
            "reason_code": "BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            "reason": "repo-root-not-detectable",
            "writes_allowed": writes_allowed(),
            "log_path": str(log_path),
            **base_payload,
        }
        print(json.dumps(result, ensure_ascii=True))
        raise SystemExit(2)

    if not writes_allowed():
        log_path = resolve_log_path(
            config_root=COMMANDS_HOME.parent,
            workspaces_home=WORKSPACES_HOME,
            repo_fingerprint=None,
        )
        result = {
            "workspacePersistenceHook": "blocked",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "reason": "writes-not-allowed",
            "impact": "fingerprint + persistence are required before any phase >= 2.1",
            "mode": mode,
            "writes_allowed": False,
            "log_path": str(log_path),
            **base_payload,
        }
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BLOCKED-WORKSPACE-PERSISTENCE",
            message="Persistence hook blocked by write policy before dispatch.",
            expected="writes allowed",
            observed={"mode": mode, "writes_allowed": False},
            remediation="Unset OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY or use a writable mode.",
            config_root=str(COMMANDS_HOME.parent),
            workspaces_home=str(WORKSPACES_HOME),
            repo_fingerprint=None,
            phase="1.1-Bootstrap",
        )
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
            "workspacePersistenceHook": "failed",
            "reason_code": "ERR-BOOTSTRAP-HOOK-IMPORT",
            "reason": "hook-output-not-json",
            "stderr": (proc.stderr or "").strip()[:500],
            "stdout": (proc.stdout or "").strip()[:500],
        }

    result = {
        **parsed_payload,
        **base_payload,
    }
    if not isinstance(result.get("repo_fingerprint"), str):
        result["repo_fingerprint"] = ""

    if proc.returncode != 0 and str(result.get("reason_code", "")).strip() in {"", "none"}:
        result["reason_code"] = "ERR-BOOTSTRAP-HOOK-IMPORT"

    if str(result.get("workspacePersistenceHook", "")).strip().lower() != "ok":
        reason_code = str(result.get("reason_code", "ERR-BOOTSTRAP-HOOK-IMPORT")).strip() or "ERR-BOOTSTRAP-HOOK-IMPORT"
        log_path = resolve_log_path(
            config_root=COMMANDS_HOME.parent,
            workspaces_home=WORKSPACES_HOME,
            repo_fingerprint=(result.get("repo_fingerprint") or None),
        )
        emit_gate_failure(
            gate="PERSISTENCE",
            code=reason_code,
            message="Persistence hook module dispatch failed.",
            expected="python -m diagnostics.start_persistence_hook exits with code 0",
            observed={
                "returncode": proc.returncode,
                "stderr": (proc.stderr or "").strip()[:500],
                "stdout": (proc.stdout or "").strip()[:500],
            },
            remediation="Run the hook command directly and fix import/runtime errors.",
            config_root=str(COMMANDS_HOME.parent),
            workspaces_home=str(WORKSPACES_HOME),
            repo_fingerprint=(result.get("repo_fingerprint") or None),
            phase="1.1-Bootstrap",
        )
        result["reason_code"] = reason_code
        result["stderr_snippet"] = (proc.stderr or "").strip()[:500]
        result["log_path"] = str(log_path)

    print(json.dumps(result, ensure_ascii=True))
    if str(result.get("workspacePersistenceHook")).strip().lower() != "ok":
        raise SystemExit(2)
    return result


def emit_start_receipt() -> None:
    """Emit forensic receipt for desktop dispatch debugging."""
    try:
        repo_fp = derive_repo_fingerprint(Path.cwd())
    except Exception:
        repo_fp = None
    planned_pointer_path = COMMANDS_HOME.parent / "SESSION_STATE.json"
    planned_workspace_path = WORKSPACES_HOME / repo_fp / "SESSION_STATE.json" if repo_fp else None
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
            "computed_opencode_home": str(COMMANDS_HOME.parent),
            "computed_commands_home": str(COMMANDS_HOME),
            "computed_workspaces_home": str(WORKSPACES_HOME),
            "planned_pointer_path": str(planned_pointer_path),
            "planned_workspace_session_path": str(planned_workspace_path) if planned_workspace_path else None,
            "derived_repo_fingerprint": repo_fp,
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
