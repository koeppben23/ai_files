from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from bootstrap.backfill_client import run_backfill_subprocess


def run_workspace_artifact_backfill(
    *,
    skip_artifact_backfill: bool,
    script_dir: Path,
    repo_fingerprint: str,
    config_root: Path,
    repo_root: Path,
    workspaces_home: Path,
    python_cmd: str,
    writes_allowed: bool,
    emit_gate_failure: Callable[..., object],
    safe_log_error: Callable[..., object],
    output: Callable[[str], None] = print,
) -> tuple[bool, bool]:
    backfill_failed = False
    artifacts_committed = False

    if skip_artifact_backfill:
        return backfill_failed, artifacts_committed

    helper = script_dir / "persist_workspace_artifacts.py"
    if not helper.exists():
        safe_log_error(
            reason_key="ERR-WORKSPACE-PERSISTENCE-HOOK-MISSING",
            message="Workspace artifact backfill helper missing during bootstrap.",
            config_root=config_root,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode="repo-aware",
            repo_fingerprint=repo_fingerprint,
            command="bootstrap_session_state.py",
            component="workspace-persistence-hook",
            observed_value={"helper": str(helper)},
            expected_constraint="persist_workspace_artifacts.py present under diagnostics",
            remediation="Reinstall governance package and rerun bootstrap.",
        )
        output("WARNING: persist_workspace_artifacts.py not found; skipping artifact backfill hook.")
        return backfill_failed, artifacts_committed

    env = os.environ.copy()
    if writes_allowed:
        env["OPENCODE_DIAGNOSTICS_ALLOW_WRITE"] = "1"

    summary_obj = run_backfill_subprocess(
        repo_fingerprint=repo_fingerprint,
        config_root=config_root,
        repo_root=repo_root,
        workspaces_home=workspaces_home,
        python_cmd=python_cmd,
        require_phase2=True,
        env=env,
    )
    if summary_obj.success and summary_obj.phase2_ok:
        output("Workspace artifact backfill hook completed (phase2 artifacts verified).")
        return backfill_failed, True

    if summary_obj.status == "invalid-json":
        backfill_failed = True
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BACKFALL_SUMMARY_INVALID",
            message="Backfill returned invalid JSON summary.",
            expected="JSON summary with phase2Artifacts.ok==true",
            observed={
                "stdout": (summary_obj.error or "")[:400],
                "returncode": summary_obj.returncode,
            },
            remediation="Check persist_workspace_artifacts.py output format.",
            config_root=str(config_root),
            workspaces_home=str(workspaces_home),
            repo_fingerprint=repo_fingerprint,
            phase="1.1-Bootstrap",
        )
        output("ERROR: backfill returned invalid summary.")
        return backfill_failed, artifacts_committed

    backfill_failed = True
    emit_gate_failure(
        gate="PERSISTENCE",
        code="BACKFILL_PHASE2_ARTIFACTS_MISSING",
        message="Backfill completed but required Phase 2/2.1 artifacts not verified.",
        expected="phase2Artifacts.ok==true and status=='ok'",
        observed={
            "status": summary_obj.status,
            "phase2_ok": summary_obj.phase2_ok,
            "artifacts": summary_obj.artifacts,
            "error": summary_obj.error,
            "returncode": summary_obj.returncode,
        },
        remediation="Check artifact paths and permissions, rerun bootstrap.",
        config_root=str(config_root),
        workspaces_home=str(workspaces_home),
        repo_fingerprint=repo_fingerprint,
        phase="1.1-Bootstrap",
    )
    output("ERROR: backfill completed but phase2 artifacts not verified.")

    if summary_obj.returncode not in (0, None):
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BACKFILL_NON_ZERO_EXIT",
            message="Workspace artifact backfill hook returned non-zero.",
            expected="Exit code 0 with valid JSON summary",
            observed={"returncode": summary_obj.returncode, "stderr": (summary_obj.error or "")[:400]},
            remediation="Inspect helper output and rerun bootstrap.",
            config_root=str(config_root),
            workspaces_home=str(workspaces_home),
            repo_fingerprint=repo_fingerprint,
            phase="1.1-Bootstrap",
        )
        output(f"WARNING: backfill exit code {summary_obj.returncode}.")
        if summary_obj.error:
            output(summary_obj.error)

    return backfill_failed, artifacts_committed
