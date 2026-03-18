"""Binding model.

.. deprecated::
    Use governance_runtime.domain.models.binding instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    config_root: str
    commands_home: str
    workspaces_home: str
    python_command: str
