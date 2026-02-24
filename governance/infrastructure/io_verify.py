import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def verify_pointer(pointer_path: Path, expected_fingerprint: str) -> Tuple[bool, Optional[str]]:
    if not pointer_path.is_file():
        return False, f"Path is not a file: {pointer_path}"

    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        return False, f"Failed to read pointer: {e}"

    schema = data.get("schema")
    if schema != "opencode-session-pointer.v1":
        return False, f"Schema mismatch: expected opencode-session-pointer.v1, got {schema}"

    fingerprint = data.get("activeRepoFingerprint")
    if not isinstance(fingerprint, str) or fingerprint != expected_fingerprint:
        return False, f"Fingerprint mismatch: expected {expected_fingerprint}, got {fingerprint}"

    session_file = data.get("activeSessionStateFile")
    if not isinstance(session_file, str) or not session_file.strip():
        return False, "Missing or invalid 'activeSessionStateFile' in pointer"
    session_file_path = Path(session_file)
    if not session_file_path.is_absolute():
        return False, "Pointer field 'activeSessionStateFile' must be absolute"

    session_rel = data.get("activeSessionStateRelativePath")
    if not isinstance(session_rel, str) or not session_rel.strip():
        return False, "Missing or invalid 'activeSessionStateRelativePath' in pointer"
    expected_rel = f"workspaces/{expected_fingerprint}/SESSION_STATE.json"
    normalized_rel = session_rel.replace("\\", "/")
    if normalized_rel != expected_rel:
        return False, f"Relative path mismatch: expected {expected_rel}, got {session_rel}"
    if not str(session_file_path).replace("\\", "/").endswith(expected_rel):
        return False, "Pointer absolute/relative session path mismatch"

    return True, None


def verify_artifacts(workspace_root: Path) -> Tuple[bool, Dict[str, bool], Optional[str]]:
    artifact_names = [
        "repo-cache.yaml",
        "repo-map-digest.md",
        "workspace-memory.yaml",
        "decision-pack.md",
    ]

    results: Dict[str, bool] = {}
    for name in artifact_names:
        results[name] = (workspace_root / name).is_file()

    if all(results.values()):
        return True, results, None
    missing = [k for k, v in results.items() if not v]
    return False, results, f"Missing artifacts: {', '.join(missing)}"
