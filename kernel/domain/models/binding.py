from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    config_root: str
    commands_home: str
    workspaces_home: str
    python_command: str
