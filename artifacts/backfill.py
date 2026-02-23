from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class ArtifactSpec:
    key: str
    path: Path
    create_content: str
    append_content: Optional[str] = None


def upsert_artifact(
    *,
    path: Path,
    create_content: str,
    append_content: Optional[str],
    force: bool,
    dry_run: bool,
    read_only: bool,
    write_text: Callable[[Path, str], None],
    append_text: Callable[[Path, str], None],
    normalize_existing: Callable[[Path, bool], str],
) -> str:
    if not path.exists():
        if read_only:
            return "blocked-read-only"
        if dry_run:
            return "write-requested"
        write_text(path, create_content)
        return "created"

    normalize_action = normalize_existing(path, dry_run)
    if not force:
        if normalize_action == "normalized":
            return "normalized"
        if normalize_action == "blocked-read-only":
            return "blocked-read-only"
        if normalize_action == "write-requested":
            return "write-requested"
        return "kept"

    if append_content is not None:
        if read_only:
            return "blocked-read-only"
        if dry_run:
            return "write-requested"
        append_text(path, append_content)
        return "appended"

    if read_only:
        return "blocked-read-only"
    if dry_run:
        return "write-requested"
    write_text(path, create_content)
    return "overwritten"


def run_backfill(
    *,
    specs: list[ArtifactSpec],
    force: bool,
    dry_run: bool,
    read_only: bool,
    write_text: Callable[[Path, str], None],
    append_text: Callable[[Path, str], None],
    normalize_existing: Callable[[Path, bool], str],
) -> Dict[str, str]:
    actions: Dict[str, str] = {}
    for spec in specs:
        actions[spec.key] = upsert_artifact(
            path=spec.path,
            create_content=spec.create_content,
            append_content=spec.append_content,
            force=force,
            dry_run=dry_run,
            read_only=read_only,
            write_text=write_text,
            append_text=append_text,
            normalize_existing=normalize_existing,
        )
    return actions
