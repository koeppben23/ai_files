"""Model Identity Resolution Service - Infrastructure layer.

Resolves model identity with proper precedence, audit events, and fail-closed behavior.

Context Limit Semantics (DOMAIN INVARIANT):
- context_limit == 0: Unknown/unset → BLOCKED in pipeline
- context_limit < 0: Invalid → BLOCKED in all modes
- context_limit > 0: Valid

Trust Model for Pipeline Mode:
- binding_env ONLY is trusted_for_routing in pipeline
- host_capability is NOT trusted_for_routing in pipeline (must use binding_env)
- This prevents silent trust escalation through host capabilities

Event Determinism:
- All events contain canonicalized values
- No raw provider responses in events
- No unnormalized URLs
- No stack traces
"""

from __future__ import annotations

import hashlib
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
    BLOCKED_MODEL_CONTEXT_LIMIT_INVALID,
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


def _canonicalize_provider(provider: str) -> str:
    """Canonicalize provider name for deterministic events."""
    return provider.lower().strip()


def _canonicalize_model_id(model_id: str) -> str:
    """Canonicalize model ID for deterministic events."""
    return model_id.strip()


def _compute_binding_file_digest(binding_file: str) -> str | None:
    """Compute SHA256 digest of binding file for audit trail."""
    try:
        path = Path(binding_file)
        if not path.exists():
            return None
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]
    except Exception:
        return None


def _compute_capabilities_hash() -> str:
    """Compute hash of relevant environment capabilities for drift detection."""
    caps = {
        "binding_file": os.environ.get("OPENCODE_BINDING_FILE", ""),
        "config_root": os.environ.get("OPENCODE_CONFIG_ROOT", ""),
    }
    payload = json.dumps(caps, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class ModelIdentityResolutionResult:
    """Result of model identity resolution."""
    identity: ModelIdentity | None
    blocked: bool = False
    reason_code: str | None = None
    reason_message: str | None = None
    precedence_chain: list[dict[str, Any]] = field(default_factory=list)
    event_path: Path | None = None
    evidence_path: Path | None = None


def resolve_model_identity(
    *,
    mode: str,
    phase: str = "unknown",
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
    - context_limit MUST be > 0 and from binding_env ONLY
    - host_capability is NOT trusted_for_routing in pipeline
    - Missing/invalid context_limit → BLOCKED
    
    Args:
        mode: Operating mode (pipeline, user, architect, implement)
        phase: Current phase for event context
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
    
    event_path, evidence_path = _write_resolution_event_and_evidence(
        identity=identity,
        mode=mode,
        phase=phase,
        precedence_chain=precedence_chain,
        workspaces_home=workspaces_home,
        config_root=config_root,
    )
    
    if identity.context_limit < 0:
        return ModelIdentityResolutionResult(
            identity=None,
            blocked=True,
            reason_code=BLOCKED_MODEL_CONTEXT_LIMIT_INVALID,
            reason_message="context_limit cannot be negative",
            precedence_chain=precedence_chain,
            event_path=event_path,
            evidence_path=evidence_path,
        )
    
    if mode == "pipeline":
        if identity.context_limit <= 0:
            return ModelIdentityResolutionResult(
                identity=None,
                blocked=True,
                reason_code=BLOCKED_MODEL_CONTEXT_LIMIT_REQUIRED,
                reason_message="Pipeline mode requires explicit context_limit from binding_env",
                precedence_chain=precedence_chain,
                event_path=event_path,
                evidence_path=evidence_path,
            )
        
        if identity.source != "binding_env":
            return ModelIdentityResolutionResult(
                identity=None,
                blocked=True,
                reason_code=BLOCKED_MODEL_IDENTITY_UNTRUSTED,
                reason_message="Pipeline mode requires model identity from binding_env only",
                precedence_chain=precedence_chain,
                event_path=event_path,
                evidence_path=evidence_path,
            )
    
    if require_trusted_for_audit and not identity.is_trusted_for_audit():
        return ModelIdentityResolutionResult(
            identity=None,
            blocked=True,
            reason_code=BLOCKED_MODEL_IDENTITY_UNTRUSTED,
            reason_message="Audit requires model identity from binding_env",
            precedence_chain=precedence_chain,
            event_path=event_path,
            evidence_path=evidence_path,
        )
    
    return ModelIdentityResolutionResult(
        identity=identity,
        precedence_chain=precedence_chain,
        event_path=event_path,
        evidence_path=evidence_path,
    )


def _write_resolution_event_and_evidence(
    *,
    identity: ModelIdentity,
    mode: str,
    phase: str,
    precedence_chain: list[dict[str, Any]],
    workspaces_home: Path | None,
    config_root: Path | None,
) -> tuple[Path | None, Path | None]:
    """Write MODEL_IDENTITY_RESOLVED event and evidence file.
    
    Event: workspaces_home/events/MODEL_IDENTITY_RESOLVED/<timestamp>-<uuid>.json
    Evidence: workspaces_home/evidence/model_identity/resolved.json
    
    Event is timeline, Evidence is state. Both are written atomically.
    """
    resolved_workspaces = _resolve_workspaces_home(workspaces_home, config_root)
    
    timestamp = datetime.now(timezone.utc).isoformat()
    event_id = uuid4().hex[:12]
    capabilities_hash = _compute_capabilities_hash()
    
    binding_file_digest: str | None = None
    if identity.source == "binding_env":
        binding_file = os.environ.get("OPENCODE_BINDING_FILE", "")
        if binding_file:
            binding_file_digest = _compute_binding_file_digest(binding_file)
    
    canonical_provider = _canonicalize_provider(identity.provider)
    canonical_model_id = _canonicalize_model_id(identity.model_id)
    
    event = {
        "schema": "opencode.model-identity-resolved.v1",
        "eventId": event_id,
        "timestamp": timestamp,
        "eventType": "MODEL_IDENTITY_RESOLVED",
        "mode": mode,
        "phase": phase,
        "identity": {
            "provider": canonical_provider,
            "model_id": canonical_model_id,
            "context_limit": identity.context_limit,
            "source": identity.source,
            "temperature": identity.temperature,
        },
        "trustLevel": identity.trust_level().value,
        "isTrustedForAudit": identity.is_trusted_for_audit(),
        "isTrustedForRouting": identity.is_trusted_for_routing(),
        "precedenceChain": precedence_chain,
        "capabilitiesHash": capabilities_hash,
        "bindingFileDigest": binding_file_digest,
    }
    
    event_path: Path | None = None
    evidence_path: Path | None = None
    
    try:
        events_dir = resolved_workspaces / "events" / "MODEL_IDENTITY_RESOLVED"
        events_dir.mkdir(parents=True, exist_ok=True)
        event_file = events_dir / f"{timestamp.replace(':', '-').replace('.', '-')}-{event_id}.json"
        atomic_write_text(
            event_file,
            json.dumps(event, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
            newline_lf=True,
        )
        event_path = event_file
    except Exception:
        pass
    
    evidence = {
        "schema": "opencode.model-identity-evidence.v1",
        "timestamp": timestamp,
        "mode": mode,
        "phase": phase,
        "identity": {
            "provider": canonical_provider,
            "model_id": canonical_model_id,
            "context_limit": identity.context_limit,
            "source": identity.source,
        },
        "trustLevel": identity.trust_level().value,
        "capabilitiesHash": capabilities_hash,
        "bindingFileDigest": binding_file_digest,
        "precedenceWinner": precedence_chain[0] if precedence_chain else None,
    }
    
    try:
        evidence_dir = resolved_workspaces / "evidence" / "model_identity"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_file = evidence_dir / "resolved.json"
        atomic_write_text(
            evidence_file,
            json.dumps(evidence, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
            newline_lf=True,
        )
        evidence_path = evidence_file
    except Exception:
        pass
    
    return event_path, evidence_path
