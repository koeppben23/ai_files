"""Tenant configuration loader.

Loads tenant configuration from the path specified by OPENCODE_TENANT_CONFIG
environment variable. Falls back gracefully (fail-open) to auto-detection
if the variable is not set or the file is invalid.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TENANT_CONFIG_ENV = "OPENCODE_TENANT_CONFIG"
TENANT_CONFIG_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class TenantConfig:
    """Tenant configuration overlay."""

    tenant_id: str
    default_profile: str
    allowed_addons: tuple[str, ...]
    blocked_addons: tuple[str, ...]
    audit_verbosity: str

    @property
    def profile_id(self) -> str:
        """Return the profile ID (without 'profile.' prefix for compatibility)."""
        return self.default_profile.replace("profile.", "")


def load_tenant_config() -> TenantConfig | None:
    """Load tenant configuration from the environment variable path.

    Returns:
        TenantConfig if OPENCODE_TENANT_CONFIG is set and valid,
        None otherwise (fail-open to auto-detection behavior).

    The function fails gracefully:
    - Missing env var → None
    - File not found → None
    - Invalid JSON → None
    - Missing required fields → None
    - Schema version mismatch → None
    """
    config_path = os.environ.get(TENANT_CONFIG_ENV)
    if not config_path:
        return None

    path = Path(config_path)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict):
        return None

    if data.get("version") != TENANT_CONFIG_SCHEMA_VERSION:
        return None

    required = ("tenant_id", "default_profile")
    if not all(data.get(k) for k in required):
        return None

    allowed = data.get("allowed_addons", [])
    blocked = data.get("blocked_addons", [])
    audit = data.get("audit_verbosity", "standard")

    return TenantConfig(
        tenant_id=data["tenant_id"],
        default_profile=data["default_profile"],
        allowed_addons=tuple(allowed) if isinstance(allowed, list) else (),
        blocked_addons=tuple(blocked) if isinstance(blocked, list) else (),
        audit_verbosity=audit if audit in ("minimal", "standard", "verbose") else "standard",
    )


def get_default_profile() -> str | None:
    """Get the default profile from tenant config, if available.

    Returns:
        Profile ID (e.g., 'python-safety') if tenant config specifies one,
        None otherwise (falls back to auto-detection).
    """
    config = load_tenant_config()
    return config.profile_id if config else None
