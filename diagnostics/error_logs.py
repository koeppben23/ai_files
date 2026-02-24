from __future__ import annotations
import os
from typing import Any

from governance.entrypoints import error_logs as _impl

from governance.entrypoints.error_logs import *  # noqa: F401,F403
# OPENCODE_DIAGNOSTICS_ALLOW_WRITE", "0"
DEFAULT_RETENTION_DAYS = 30
def _read_only() -> bool:
    if os.environ.get("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY","0")=="1":
        return True
    if os.environ.get("OPENCODE_DIAGNOSTICS_ALLOW_WRITE","0")=="1":
        return False
    return os.environ.get("CI","").strip().lower() not in {"1","true","yes"}


def safe_log_error(**kwargs: Any) -> dict[str, str]:
    if _read_only() and not kwargs.get("gate"):
        return {"status": "read-only"}
    return _impl.safe_log_error(**kwargs)
