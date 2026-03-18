import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from governance.infrastructure.io_actions import ActionOutcome, WriteAction
from governance_runtime.infrastructure.fs_atomic import safe_replace


def atomic_write_text(path: Path, content: str, dry_run: bool = False) -> ActionOutcome:
    if dry_run:
        return ActionOutcome(
            action=WriteAction.SKIP,
            path=str(path),
            success=True,
            bytes_written=len(content.encode("utf-8")),
        )

    try:
        existed_before = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Use a very short prefix to avoid exceeding Windows MAX_PATH (260 chars).
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".", suffix=".tmp")

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            safe_replace(Path(tmp_path), path, attempts=5, backoff_ms=50)

            return ActionOutcome(
                action=WriteAction.OVERWRITE if existed_before else WriteAction.CREATE,
                path=str(path),
                success=True,
                bytes_written=len(content.encode("utf-8")),
            )
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    except Exception as e:
        return ActionOutcome(
            action=WriteAction.FAILED,
            path=str(path),
            success=False,
            error=str(e),
        )


def atomic_write_json(path: Path, data: Dict[str, Any], dry_run: bool = False) -> ActionOutcome:
    content = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    return atomic_write_text(path, content, dry_run)
