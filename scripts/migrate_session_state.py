"""Deterministically migrate SESSION_STATE documents to canonical fields.

This tool is intentionally non-destructive:
- it creates a `.backup` copy before the first canonicalizing write
- it never deletes backups
- it exits with machine-readable codes (`0=ok`, `2=blocked`)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from governance.engine.reason_codes import BLOCKED_STATE_OUTDATED, REASON_CODE_NONE
from governance.engine.session_state_repository import SessionStateRepository, _canonicalize_for_write

EXIT_OK = 0
EXIT_BLOCKED = 2


def _resolve_target_path(*, workspace: str | None, workspaces_root: Path, file_path: Path | None) -> Path:
    """Resolve SESSION_STATE target path from CLI arguments."""

    if file_path is not None:
        return file_path
    if workspace is None or not workspace.strip():
        raise ValueError("--workspace is required when --file is not provided")
    return workspaces_root / workspace.strip() / "SESSION_STATE.json"


def _read_json_document(path: Path) -> dict[str, Any]:
    """Read and validate one SESSION_STATE JSON document."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("SESSION_STATE payload must be a JSON object")
    return payload


def migrate_session_state_file(path: Path, *, engine_version: str = "1.1.0") -> tuple[int, dict[str, Any]]:
    """Migrate one file to canonical SESSION_STATE fields.

    Returns `(exit_code, result_payload)` where exit code follows this contract:
    - `0`: success/no-op
    - `2`: blocked (missing file, malformed payload, or migration failure)
    """

    if not path.exists():
        return (
            EXIT_BLOCKED,
            {
                "status": "blocked",
                "reason_code": BLOCKED_STATE_OUTDATED,
                "message": "SESSION_STATE file does not exist",
                "path": str(path),
            },
        )

    try:
        document = _read_json_document(path)
        canonical, changed = _canonicalize_for_write(document)
        backup_path = path.with_suffix(path.suffix + ".backup")

        if changed and not backup_path.exists():
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        repo = SessionStateRepository(path, engine_version=engine_version)
        repo.save(canonical)
        return (
            EXIT_OK,
            {
                "status": "ok",
                "reason_code": REASON_CODE_NONE,
                "message": "SESSION_STATE migrated" if changed else "SESSION_STATE already canonical",
                "path": str(path),
                "changed": changed,
                "backup_path": str(backup_path) if changed else "",
            },
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return (
            EXIT_BLOCKED,
            {
                "status": "blocked",
                "reason_code": BLOCKED_STATE_OUTDATED,
                "message": str(exc),
                "path": str(path),
            },
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for deterministic SESSION_STATE migration."""

    parser = argparse.ArgumentParser(description="Migrate SESSION_STATE to canonical fields.")
    parser.add_argument("--workspace", default=None, help="Workspace identifier under workspaces root.")
    parser.add_argument(
        "--workspaces-root",
        default="workspaces",
        help="Base workspaces directory used with --workspace (default: workspaces).",
    )
    parser.add_argument("--file", default=None, help="Explicit SESSION_STATE file path.")
    parser.add_argument("--engine-version", default="1.1.0", help="Engine version recorded in migration metadata.")

    args = parser.parse_args(argv)

    try:
        path = _resolve_target_path(
            workspace=args.workspace,
            workspaces_root=Path(args.workspaces_root),
            file_path=Path(args.file) if args.file is not None else None,
        )
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason_code": BLOCKED_STATE_OUTDATED,
                    "message": str(exc),
                },
                ensure_ascii=True,
            )
        )
        return EXIT_BLOCKED

    code, payload = migrate_session_state_file(path, engine_version=args.engine_version)
    print(json.dumps(payload, ensure_ascii=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
