"""Backward-compatible engine orchestrator import surface.

Canonical use-case implementation lives in
`governance.application.use_cases.orchestrate_run`.
"""

from __future__ import annotations

import os

from governance.application.use_cases import orchestrate_run as _impl
from governance.infrastructure.phase4_config_resolver import configure_phase4_self_review_resolver
from governance.infrastructure.phase5_config_resolver import configure_phase5_review_resolver
from governance.infrastructure.mode_repo_rules import resolve_env_operating_mode
from governance.infrastructure.wiring import configure_gateway_registry

EngineOrchestratorOutput = _impl.EngineOrchestratorOutput
build_reason_payload = _impl.build_reason_payload


def run_engine_orchestrator(**kwargs):
    """Compatibility shim with monkeypatch passthrough for tests."""

    effective_mode = resolve_env_operating_mode()
    if effective_mode == "invalid":
        effective_mode = "pipeline"
    configure_phase4_self_review_resolver(mode=effective_mode)
    configure_phase5_review_resolver(mode=effective_mode)
    configure_gateway_registry()
    _impl.build_reason_payload = build_reason_payload
    return _impl.run_engine_orchestrator(**kwargs)
