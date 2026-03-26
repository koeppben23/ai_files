from __future__ import annotations

import os
from pathlib import Path

_config_root_override: Path | None = None


def set_config_root_override(path: str | Path | None) -> None:
    global _config_root_override
    _config_root_override = None if path is None else Path(path)


def get_config_root() -> Path:
    if _config_root_override is not None:
        return _config_root_override
    env_config = os.environ.get("OPENCODE_CONFIG")
    if env_config:
        return Path(env_config).expanduser().resolve().parent
    env_config_dir = os.environ.get("OPENCODE_CONFIG_DIR")
    if env_config_dir:
        return Path(env_config_dir).expanduser()
    env_root = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_root:
        return Path(env_root)
    return Path.home() / ".config" / "opencode"


def get_opencode_command_root() -> Path:
    return get_config_root() / "commands"


def get_governance_runtime_root() -> Path:
    return Path.home() / ".local" / "share" / "opencode" / "governance_runtime"


def get_workspace_root(repo_fingerprint: str) -> Path:
    return get_config_root() / "workspaces" / repo_fingerprint


def get_workspace_logs_root(repo_fingerprint: str) -> Path:
    return get_workspace_root(repo_fingerprint) / "logs"


def resolve_legacy_path(path: str | Path) -> Path:
    normalized = str(path).replace("\\", "/").strip("/")
    if not normalized or normalized == "commands":
        return get_opencode_command_root()

    if normalized.startswith("commands/"):
        suffix = normalized[len("commands/") :]

        if suffix == "docs" or suffix.startswith("docs/"):
            return Path.home() / ".local" / "share" / "opencode" / "governance_content" / suffix

        if suffix == "profiles" or suffix.startswith("profiles/"):
            return Path.home() / ".local" / "share" / "opencode" / "governance_content" / suffix

        if suffix == "governance_runtime" or suffix.startswith("governance_runtime/"):
            runtime_suffix = suffix[len("governance_runtime") :].lstrip("/")
            root = get_governance_runtime_root()
            return root if not runtime_suffix else root / runtime_suffix

    return get_opencode_command_root()
