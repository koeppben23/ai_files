from __future__ import annotations

import os
from pathlib import Path

from governance_runtime import layer_adapter


def get_config_root() -> Path:
    env_root = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_root:
        return Path(env_root)
    return Path.home() / ".config" / "opencode"


def get_workspace_root(repo_fingerprint: str) -> Path:
    return get_config_root() / "workspaces" / repo_fingerprint


def get_workspace_logs_root(repo_fingerprint: str) -> Path:
    return get_workspace_root(repo_fingerprint) / "logs"


__all__ = ["get_config_root", "get_workspace_root", "get_workspace_logs_root", "layer_adapter"]
