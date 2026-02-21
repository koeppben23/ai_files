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
from governance.application.use_cases.start_bootstrap import evaluate_start_identity
from governance.engine.adapters import LocalHostAdapter
from governance.infrastructure.path_contract import normalize_absolute_path
from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.mode_repo_rules import resolve_env_operating_mode
from governance.infrastructure.wiring import configure_gateway_registry


_is_pipeline = os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no", "off"}


def _effective_mode() -> str:
    mode = resolve_env_operating_mode()
    if mode == "invalid":
        return "pipeline"
    return mode


def _writes_allowed(*, mode: str) -> bool:
    if str(os.environ.get("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "")).strip() == "1":
        return False
    return True


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

    configure_gateway_registry()
    identity = evaluate_start_identity(adapter=cast(Any, _RepoIdentityProbeAdapter(normalized_repo_root)))
    fp = (identity.repo_fingerprint or "").strip()
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
        "writes_allowed": _writes_allowed(mode=mode),
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
    if not _writes_allowed(mode=mode):
        result = {
            "workspacePersistenceHook": "blocked",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "reason": "writes-not-allowed",
            "impact": "fingerprint + persistence are required before any phase >= 2.1",
            "mode": mode,
            "writes_allowed": False,
        }
        print(json.dumps(result, ensure_ascii=True))
        raise SystemExit(2)

    from diagnostics.start_persistence_hook import run_persistence_hook as _run_hook
    result = _run_hook()
    print(json.dumps(result, ensure_ascii=True))
    if str(result.get("workspacePersistenceHook")).strip().lower() != "ok":
        raise SystemExit(2)
    return result


def main() -> int:
    emit_preflight()
    emit_permission_probes()
    run_persistence_hook()
    if os.getenv("OPENCODE_ENGINE_SHADOW_EMIT") == "1":
        print(json.dumps({"engineRuntimeShadow": build_engine_shadow_snapshot()}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
