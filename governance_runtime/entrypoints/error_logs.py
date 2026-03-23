from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


from pathlib import Path
from typing import Any

from governance_runtime.infrastructure.logging import error_logs as _impl
from governance_runtime.entrypoints.write_policy import writes_allowed

# Compatibility tokens retained for static contract checks:
# error.log.jsonl
# reasonKey phase gate repoFingerprint DEFAULT_RETENTION_DAYS

DEFAULT_RETENTION_DAYS = 30


def _read_only() -> bool:
    return not writes_allowed()


def emit_error_event_ssot(**kwargs: Any) -> bool:
    return _impl.emit_error_event_ssot(**kwargs)


def resolve_paths_full(config_root: Path | None = None) -> tuple[Path, Path, Path]:
    return _impl.resolve_paths_full(config_root)


def resolve_ssot_log_path(**kwargs: Any) -> Path:
    return _impl.resolve_ssot_log_path(**kwargs)


def _update_error_index(*args: Any, **kwargs: Any) -> None:
    return _impl._update_error_index(*args, **kwargs)


def write_error_event(**kwargs: Any) -> Path:
    if _read_only() and not kwargs.get("gate"):
        raise RuntimeError("governance-read-only")
    allowed = {
        "reason_key",
        "message",
        "config_root",
        "phase",
        "gate",
        "repo_fingerprint",
        "command",
        "component",
        "observed_value",
        "expected_constraint",
        "remediation",
        "action",
        "result",
        "details",
    }
    payload = {k: v for k, v in kwargs.items() if k in allowed}
    return _impl.write_error_event(**payload)


def safe_log_error(**kwargs: Any) -> dict[str, str]:
    if _read_only() and not kwargs.get("gate"):
        return {"status": "read-only"}
    try:
        p = write_error_event(**kwargs)
        return {"status": "logged", "path": str(p)}
    except Exception as exc:
        return {"status": "log-failed", "error": str(exc)}
