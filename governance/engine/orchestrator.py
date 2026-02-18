"""Backward-compatible engine orchestrator import surface.

Canonical use-case implementation lives in
`governance.application.use_cases.orchestrate_run`.
"""

from __future__ import annotations

from governance.application.use_cases import orchestrate_run as _impl

EngineOrchestratorOutput = _impl.EngineOrchestratorOutput
build_reason_payload = _impl.build_reason_payload


def run_engine_orchestrator(**kwargs):
    """Compatibility shim with monkeypatch passthrough for tests."""

    _impl.build_reason_payload = build_reason_payload
    return _impl.run_engine_orchestrator(**kwargs)
