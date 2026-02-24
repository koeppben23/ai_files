import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from governance.infrastructure.io_actions import ActionOutcome, WriteAction


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

        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            os.replace(tmp_path, str(path))

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
