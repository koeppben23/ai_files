import json
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import SessionState


def load_state(path: Path) -> SessionState:
    if not path.is_file():
        return SessionState()
    
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return SessionState()
        return SessionState.from_dict(data)
    except (json.JSONDecodeError, IOError, OSError):
        return SessionState()


def dump_state(state: SessionState, path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8"
        )
        return True
    except (IOError, OSError):
        return False


def validate_state_schema(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    
    schema = data.get("schema")
    if not isinstance(schema, str):
        return False
    
    if not schema.startswith("opencode-session"):
        return False
    
    return True


def load_raw_state(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if validate_state_schema(data):
            return data
        return None
    except (json.JSONDecodeError, IOError, OSError):
        return None
