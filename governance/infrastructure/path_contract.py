from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Literal


class PathContractError(Exception):
    pass


class NotAbsoluteError(PathContractError):
    pass


class WindowsDriveRelativeError(PathContractError):
    pass


def deterministic_home() -> Path:
    return Path.home().expanduser()


def canonical_config_root(home: Path | None = None) -> Path:
    base = home if home is not None else deterministic_home()
    return Path(os.path.normpath(os.path.abspath(str(base.expanduser() / ".config" / "opencode"))))


def canonical_commands_home(home: Path | None = None) -> Path:
    return canonical_config_root(home) / "commands"


@dataclass(frozen=True)
class BindingEvidenceLocation:
    commands_home: Path
    governance_paths_json: Path
    source: Literal["canonical", "trusted_override"]


def normalize_absolute_path(raw: str, *, purpose: str) -> Path:
    token = str(raw or "").strip()
    if not token:
        raise NotAbsoluteError(f"{purpose}: empty path")
    candidate = Path(token).expanduser()
    if os.name == "nt" and re.match(r"^[A-Za-z]:[^/\\]", token):
        raise WindowsDriveRelativeError(f"{purpose}: drive-relative path is not allowed")
    if not candidate.is_absolute():
        raise NotAbsoluteError(f"{purpose}: path must be absolute")
    return Path(os.path.normpath(os.path.abspath(str(candidate))))


def normalize_for_fingerprint(path: Path) -> str:
    normalized = os.path.normpath(os.path.abspath(str(path.expanduser())))
    return normalized.replace("\\", "/").casefold()


def binding_evidence_location(
    *,
    trusted_commands_root: str | None,
    allow_trusted_override: bool,
    mode: str,
) -> BindingEvidenceLocation:
    if allow_trusted_override and trusted_commands_root and str(mode).strip().lower() != "pipeline":
        commands_home = normalize_absolute_path(trusted_commands_root, purpose="trusted_commands_root")
        return BindingEvidenceLocation(
            commands_home=commands_home,
            governance_paths_json=commands_home / "governance.paths.json",
            source="trusted_override",
        )

    commands_home = canonical_commands_home()
    return BindingEvidenceLocation(
        commands_home=commands_home,
        governance_paths_json=commands_home / "governance.paths.json",
        source="canonical",
    )
