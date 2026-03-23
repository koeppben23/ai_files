from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceLayout:
    repo_home: str
    session_state_file: str
    identity_map_file: str
    pointer_file: str
