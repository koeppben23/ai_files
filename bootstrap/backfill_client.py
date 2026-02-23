from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import subprocess
import json
import sys
import os


@dataclass(frozen=True)
class BackfillSummary:
    success: bool
    phase2_ok: bool
    status: str
    artifacts: Dict[str, str]
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "phase2_ok": self.phase2_ok,
            "status": self.status,
            "artifacts": self.artifacts,
            "error": self.error,
        }


def run_backfill_subprocess(
    repo_fingerprint: str,
    config_root: Path,
    repo_root: Path,
    workspaces_home: Path,
    python_cmd: Optional[str] = None,
    require_phase2: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> BackfillSummary:
    helper = config_root / "commands" / "diagnostics" / "persist_workspace_artifacts.py"
    
    if not helper.is_file():
        return BackfillSummary(
            success=False,
            phase2_ok=False,
            status="error",
            artifacts={},
            error=f"Backfill helper not found: {helper}",
        )
    
    cmd = [
        python_cmd or sys.executable,
        str(helper),
        "--repo-fingerprint",
        repo_fingerprint,
        "--config-root",
        str(config_root),
        "--repo-root",
        str(repo_root),
        "--skip-lock",
        "--quiet",
    ]
    
    if require_phase2:
        cmd.append("--require-phase2")
    
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    
    if run_env.get("OPENCODE_DIAGNOSTICS_ALLOW_WRITE") != "1":
        run_env["OPENCODE_DIAGNOSTICS_ALLOW_WRITE"] = "1"
    
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        env=run_env,
    )
    
    summary_data = None
    if result.stdout.strip():
        try:
            summary_data = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            pass
    
    if not isinstance(summary_data, dict):
        return BackfillSummary(
            success=False,
            phase2_ok=False,
            status="error",
            artifacts={},
            error=f"Invalid JSON summary: {result.stdout[:200]}",
        )
    
    phase2_artifacts = summary_data.get("phase2Artifacts", {})
    phase2_ok = isinstance(phase2_artifacts, dict) and phase2_artifacts.get("ok") is True
    status = summary_data.get("status", "unknown")
    
    artifacts = {}
    if isinstance(phase2_artifacts, dict):
        artifacts = {
            k: v.get("status", "unknown") if isinstance(v, dict) else "unknown"
            for k, v in phase2_artifacts.items()
        }
    
    success = result.returncode == 0 and phase2_ok and status == "ok"
    
    return BackfillSummary(
        success=success,
        phase2_ok=phase2_ok,
        status=status,
        artifacts=artifacts,
        error=None if success else f"Return code: {result.returncode}",
    )
