import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def verify_exists(path: Path) -> Tuple[bool, Optional[str]]:
    if not path.exists():
        return False, f"Path does not exist: {path}"
    return True, None


def verify_is_file(path: Path) -> Tuple[bool, Optional[str]]:
    exists, error = verify_exists(path)
    if not exists:
        return False, error
    
    if not path.is_file():
        return False, f"Path is not a file: {path}"
    
    return True, None


def verify_is_dir(path: Path) -> Tuple[bool, Optional[str]]:
    exists, error = verify_exists(path)
    if not exists:
        return False, error
    
    if not path.is_dir():
        return False, f"Path is not a directory: {path}"
    
    return True, None


def verify_schema(data: Dict[str, Any], expected_schema: str) -> Tuple[bool, Optional[str]]:
    if not isinstance(data, dict):
        return False, "Data is not a dictionary"
    
    schema = data.get("schema")
    if not isinstance(schema, str):
        return False, "Missing or invalid 'schema' field"
    
    if schema != expected_schema:
        return False, f"Schema mismatch: expected {expected_schema}, got {schema}"
    
    return True, None


def verify_pointer(pointer_path: Path, expected_fingerprint: str) -> Tuple[bool, Optional[str]]:
    is_file, error = verify_is_file(pointer_path)
    if not is_file:
        return False, error
    
    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        return False, f"Failed to read pointer: {e}"
    
    valid, error = verify_schema(data, "opencode-session-pointer.v1")
    if not valid:
        return False, error
    
    fingerprint = data.get("activeRepoFingerprint")
    if not isinstance(fingerprint, str):
        return False, "Missing or invalid 'activeRepoFingerprint' in pointer"
    
    if fingerprint != expected_fingerprint:
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
    if session_rel.replace("\\", "/") != expected_rel:
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
    
    results = {}
    all_exist = True
    
    for name in artifact_names:
        artifact_path = workspace_root / name
        exists = artifact_path.is_file()
        results[name] = exists
        if not exists:
            all_exist = False
    
    if all_exist:
        return True, results, None
    else:
        missing = [k for k, v in results.items() if not v]
        return False, results, f"Missing artifacts: {', '.join(missing)}"


def verify_session_state(session_path: Path) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    is_file, error = verify_is_file(session_path)
    if not is_file:
        return False, None, error
    
    try:
        data = json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        return False, None, f"Failed to read session state: {e}"
    
    valid, error = verify_schema(data, "opencode-session.v1")
    if not valid:
        return False, None, error
    
    return True, data, None
