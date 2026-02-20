#!/usr/bin/env python3
"""
Persistence hook for /start bootstrap.

This module is called by start_preflight_readonly.py when writes are enabled.
It is intentionally separate to maintain SoC and keep preflight truly read-only
by default.

Environment:
    OPENCODE_DIAGNOSTICS_ALLOW_WRITE=1 - Required to enable writes
    CI - If set, writes are always disabled (pipeline safety)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

_is_pipeline = os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no", "off"}
READ_ONLY = _is_pipeline or os.environ.get("OPENCODE_DIAGNOSTICS_ALLOW_WRITE", "0") != "1"

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

try:
    from diagnostics.error_logs import safe_log_error
except ImportError:
    def safe_log_error(**kwargs):
        return {"status": "log-disabled"}

try:
    from governance.application.use_cases.start_bootstrap import evaluate_start_identity
    from governance.engine.adapters import LocalHostAdapter
    from governance.infrastructure.path_contract import normalize_absolute_path
    from governance.infrastructure.wiring import configure_gateway_registry
    from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
except ImportError as exc:
    print(json.dumps({
        "persistence_hook": "failed",
        "reason": "import-error",
        "error": str(exc),
        "read_only": READ_ONLY,
    }, ensure_ascii=True))
    sys.exit(1)


def _resolve_bindings() -> tuple[Path, Path, bool, Path | None, str]:
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode="user")
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


class _RepoIdentityAdapter(LocalHostAdapter):
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
    identity = evaluate_start_identity(adapter=cast(Any, _RepoIdentityAdapter(normalized_repo_root)))
    fp = (identity.repo_fingerprint or "").strip()
    return fp or None


def run_persistence_hook(*, repo_root: Path | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "workspacePersistenceHook": "skipped",
        "reason": "read-only-mode",
        "impact": "workspace/index persistence is kernel-owned only",
        "read_only": READ_ONLY,
    }

    if READ_ONLY:
        return result

    cwd = repo_root or Path.cwd()
    repo_fp = derive_repo_fingerprint(cwd)

    if not repo_fp:
        result = {
            "workspacePersistenceHook": "failed",
            "reason": "repo-fingerprint-derivation-failed",
            "impact": "cannot create workspace without repo fingerprint",
            "read_only": False,
        }
        safe_log_error(
            reason_key="ERR-PERSISTENCE-FINGERPRINT-DERIVATION-FAILED",
            message="Could not derive repo fingerprint from git metadata during persistence hook.",
            config_root=COMMANDS_HOME.parent,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode="user",
            repo_fingerprint=None,
            command="start_persistence_hook.py",
            component="persistence-hook",
            observed_value={"repo_root": str(cwd)},
            expected_constraint="git repository with valid origin or local path",
            remediation="Ensure cwd is a git repository with valid .git metadata.",
        )
        return result

    bootstrap_script = COMMANDS_HOME / "diagnostics" / "bootstrap_session_state.py"
    if not bootstrap_script.exists():
        result = {
            "workspacePersistenceHook": "failed",
            "reason": "bootstrap-script-not-found",
            "impact": f"bootstrap_session_state.py not found at {bootstrap_script}",
            "read_only": False,
        }
        safe_log_error(
            reason_key="ERR-PERSISTENCE-BOOTSTRAP-SCRIPT-MISSING",
            message="bootstrap_session_state.py not found at expected location.",
            config_root=COMMANDS_HOME.parent,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode="user",
            repo_fingerprint=repo_fp,
            command="start_persistence_hook.py",
            component="persistence-hook",
            observed_value={"expected_path": str(bootstrap_script)},
            expected_constraint="bootstrap_session_state.py exists in ${COMMANDS_HOME}/diagnostics/",
            remediation="Reinstall governance or verify commands home configuration.",
        )
        return result

    repo_name = cwd.name
    cmd = [
        PYTHON_COMMAND,
        str(bootstrap_script),
        "--repo-fingerprint", repo_fp,
        "--repo-name", repo_name,
    ]

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd),
        )
        if proc.returncode == 0:
            result = {
                "workspacePersistenceHook": "ok",
                "reason": "bootstrap-completed",
                "repo_fingerprint": repo_fp,
                "repo_name": repo_name,
                "read_only": False,
            }
        else:
            result = {
                "workspacePersistenceHook": "failed",
                "reason": "bootstrap-returncode-nonzero",
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip()[:500] if proc.stdout else "",
                "stderr": proc.stderr.strip()[:500] if proc.stderr else "",
                "read_only": False,
            }
            safe_log_error(
                reason_key="ERR-PERSISTENCE-BOOTSTRAP-NONZERO-EXIT",
                message="bootstrap_session_state.py returned non-zero exit code.",
                config_root=COMMANDS_HOME.parent,
                phase="1.1-Bootstrap",
                gate="PERSISTENCE",
                mode="user",
                repo_fingerprint=repo_fp,
                command="start_persistence_hook.py",
                component="persistence-hook",
                observed_value={
                    "returncode": proc.returncode,
                    "stdout": (proc.stdout or "").strip()[:500],
                    "stderr": (proc.stderr or "").strip()[:500],
                },
                expected_constraint="bootstrap_session_state.py must exit with code 0",
                remediation="Inspect stdout/stderr and fix bootstrap issues.",
            )
    except Exception as exc:
        result = {
            "workspacePersistenceHook": "failed",
            "reason": "bootstrap-exception",
            "error": str(exc)[:500],
            "read_only": False,
        }
        safe_log_error(
            reason_key="ERR-PERSISTENCE-BOOTSTRAP-EXCEPTION",
            message=f"Exception while running bootstrap_session_state.py: {exc}",
            config_root=COMMANDS_HOME.parent,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode="user",
            repo_fingerprint=repo_fp,
            command="start_persistence_hook.py",
            component="persistence-hook",
            observed_value={"exception": str(exc)[:500]},
            expected_constraint="bootstrap_session_state.py executes without exception",
            remediation="Check Python environment and bootstrap script integrity.",
        )

    return result


def main() -> int:
    result = run_persistence_hook()
    print(json.dumps(result, ensure_ascii=True))
    
    if result.get("workspacePersistenceHook") == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
