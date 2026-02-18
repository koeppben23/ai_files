from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.path_contract import normalize_absolute_path


def _normalize(path: Path) -> str:
    normalized = os.path.normpath(os.path.abspath(str(path.expanduser())))
    return normalized.replace("\\", "/")


def _repo_index_path(*, workspaces_home: Path, repo_root: Path) -> Path:
    key = hashlib.sha256(_normalize(repo_root).encode("utf-8")).hexdigest()[:24]
    return workspaces_home / "index" / key / "repo-context.json"


def write_unresolved_runtime_context(
    *,
    config_root: Path,
    commands_home: Path,
    binding_evidence_path: Path | None,
    cwd: Path,
    discovery_method: str,
    reason: str,
    session_id: str,
) -> bool:
    try:
        target = config_root / "state" / "runs" / session_id / "repo-context.unresolved.json"
        payload = {
            "schema": "repo-context.v1",
            "status": "unresolved",
            "session_id": session_id,
            "repo_root": None,
            "repo_fingerprint": "",
            "discovered_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "discovery_method": discovery_method,
            "cwd_hint": str(normalize_absolute_path(str(cwd), purpose="cwd_hint")),
            "binding_evidence_path": str(binding_evidence_path) if binding_evidence_path is not None else "",
            "commands_home": str(commands_home),
            "reason": reason,
        }
        atomic_write_text(target, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
        return True
    except Exception:
        return False


def commit_workspace_identity(
    *,
    workspaces_home: Path,
    repo_root: Path,
    repo_fingerprint: str,
    binding_evidence_path: Path | None,
    commands_home: Path,
    discovery_method: str,
    session_id: str,
) -> bool:
    fingerprint = str(repo_fingerprint).strip()
    if not fingerprint:
        return False
    workspace_dir = workspaces_home / fingerprint
    workspace_dir.mkdir(parents=True, exist_ok=True)
    marker = workspace_dir / ".workspace-ready"
    atomic_write_text(marker, "ready\n")

    payload = {
        "schema": "repo-context.v1",
        "session_id": session_id,
        "repo_root": _normalize(repo_root),
        "repo_fingerprint": fingerprint,
        "discovered_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "discovery_method": discovery_method,
        "binding_evidence_path": str(binding_evidence_path) if binding_evidence_path is not None else "",
        "commands_home": str(commands_home),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    atomic_write_text(workspace_dir / "repo-context.json", text)
    index_path = _repo_index_path(workspaces_home=workspaces_home, repo_root=repo_root)
    atomic_write_text(index_path, text)
    return True
