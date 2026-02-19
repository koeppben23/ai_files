"""Model Identity Resolution Service - Infrastructure layer.

Resolves model identity with proper precedence, audit events, and fail-closed behavior.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from governance.domain.model_identity import (
    ModelIdentity,
    ModelIdentitySource,
    TrustLevel,
    infer_context_limit,
)
from governance.domain.reason_codes import (
    BLOCKED_MODEL_CONTEXT_LIMIT_REQUIRED,
    BLOCKED_MODEL_IDENTITY_UNTRUSTED,
)
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.model_identity_resolver import resolve_from_environment


def _resolve_workspaces_home(workspaces_home: Path | None, config_root: Path | None) -> Path:
    """Resolve workspaces home directory."""
    if workspaces_home is not None:
        return workspaces_home
    
    if config_root is not None:
        return config_root / "workspaces"
    
    config_root_env = os.environ.get("OPENCODE_CONFIG_ROOT", "")
    if config_root_env:
        return Path(config_root_env) / "workspaces"
    
    return Path.home() / ".config" / "opencode" / "workspaces"


@dataclass(frozen=True)
class ModelIdentityResolutionResult:
    """Result of model identity resolution."""
    identity: ModelIdentity | None
    blocked: bool = False
    reason_code: str | None = None
    reason_message: str | None = None
    precedence_chain: list[dict[str, Any]] = field(default_factory=list)
    event_path: Path | None = None


def resolve_model_identity(
    *,
    mode: str,
    workspaces_home: Path | None = None,
    config_root: Path | None = None,
    require_trusted_for_audit: bool = False,
) -> ModelIdentityResolutionResult:
    """Resolve model identity with precedence and audit events.
    
    Precedence (highest first):
    1. Environment from binding file (binding_env) - TRUSTED FOR AUDIT
    2. Environment from process (process_env) - ADVISORY ONLY
    3. Fallback: unresolved - BLOCKS AUDIT
    
    In pipeline mode:
    - context_limit MUST be from trusted source
    - Missing context_limit → BLOCKED_MODEL_CONTEXT_LIMIT_REQUIRED
    
    Args:
        mode: Operating mode (pipeline, user, architect, implement)
        workspaces_home: Path to workspaces directory for event storage
        config_root: Path to config root
        require_trusted_for_audit: If True, block if not trusted for audit
    
    Returns:
        ModelIdentityResolutionResult with identity or blocked status
    """
    precedence_chain: list[dict[str, Any]] = []
    
    identity = resolve_from_environment()
    
    if identity:
        precedence_chain.append({
            "source": identity.source,
            "trust_level": identity.trust_level().value,
            "winner": True,
        })
    else:
        identity = ModelIdentity(
            provider="unknown",
            model_id="unknown",
            context_limit=0,
            source="unresolved",
        )
        precedence_chain.append({
            "source": "unresolved",
            "trust_level": TrustLevel.BLOCKS_AUDIT.value,
            "winner": True,
            "reason": "no_environment_variables",
        })
    
    event_path = _write_resolution_event(
        identity=identity,
        precedence_chain=precedence_chain,
        workspaces_home=workspaces_home,
        config_root=config_root,
    )
    
    if mode == "pipeline":
        if identity.context_limit <= 0:
            return ModelIdentityResolutionResult(
                identity=None,
                blocked=True,
                reason_code=BLOCKED_MODEL_CONTEXT_LIMIT_REQUIRED,
                reason_message="Pipeline mode requires explicit context_limit from trusted source",
                precedence_chain=precedence_chain,
                event_path=event_path,
            )
        
        if not identity.is_trusted_for_routing():
            return ModelIdentityResolutionResult(
                identity=None,
                blocked=True,
                reason_code=BLOCKED_MODEL_IDENTITY_UNTRUSTED,
                reason_message="Pipeline mode requires model identity from trusted source (binding_env or host_capability)",
                precedence_chain=precedence_chain,
                event_path=event_path,
            )
    
    if require_trusted_for_audit and not identity.is_trusted_for_audit():
        return ModelIdentityResolutionResult(
            identity=None,
            blocked=True,
            reason_code=BLOCKED_MODEL_IDENTITY_UNTRUSTED,
            reason_message="Audit requires model identity from trusted source (binding_env)",
            precedence_chain=precedence_chain,
            event_path=event_path,
        )
    
    return ModelIdentityResolutionResult(
        identity=identity,
        precedence_chain=precedence_chain,
        event_path=event_path,
    )


def _write_resolution_event(
    *,
    identity: ModelIdentity,
    precedence_chain: list[dict[str, Any]],
    workspaces_home: Path | None,
    config_root: Path | None,
) -> Path | None:
    """Write MODEL_IDENTITY_RESOLVED audit event.
    
    Event is written atomically to:
    workspaces_home/events/MODEL_IDENTITY_RESOLVED/<timestamp>-<uuid>.json
    """
    resolved_workspaces = _resolve_workspaces_home(workspaces_home, config_root)
    
    events_dir = resolved_workspaces / "events" / "MODEL_IDENTITY_RESOLVED"
    events_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).isoformat()
    event_id = uuid4().hex[:12]
    
    event = {
        "schema": "opencode.model-identity-resolved.v1",
        "eventId": event_id,
        "timestamp": timestamp,
        "eventType": "MODEL_IDENTITY_RESOLVED",
        "identity": identity.to_dict(),
        "trustLevel": identity.trust_level().value,
        "isTrustedForAudit": identity.is_trusted_for_audit(),
        "isTrustedForRouting": identity.is_trusted_for_routing(),
        "precedenceChain": precedence_chain,
    }
    
    event_file = events_dir / f"{timestamp.replace(':', '-').replace('.', '-')}-{event_id}.json"
    
    try:
        atomic_write_text(
            event_file,
            json.dumps(event, indent=2, ensure_ascii=True) + "\n",
            newline_lf=True,
        )
        return event_file
    except Exception:
        return None
