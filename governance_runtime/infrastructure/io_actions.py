from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class WriteAction(str, Enum):
    CREATE = "create"
    OVERWRITE = "overwrite"
    SKIP = "skip"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class ActionOutcome:
    action: WriteAction
    path: str
    success: bool
    error: Optional[str] = None
    bytes_written: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "path": self.path,
            "success": self.success,
            "error": self.error,
            "bytes_written": self.bytes_written,
        }
