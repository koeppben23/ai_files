from __future__ import annotations

import pytest


@pytest.mark.governance
def test_phase4_resolver_disables_repo_local_fallback_in_pipeline(monkeypatch):
    from governance.infrastructure.phase4_config_resolver import CanonicalRootConfigResolver

    monkeypatch.setenv("OPENCODE_ALLOW_REPO_LOCAL_CONFIG", "1")
    assert CanonicalRootConfigResolver(mode="pipeline").allow_repo_local_fallback() is False
    assert CanonicalRootConfigResolver(mode="user").allow_repo_local_fallback() is True


@pytest.mark.governance
def test_phase5_resolver_disables_repo_local_fallback_in_pipeline(monkeypatch):
    from governance.infrastructure.phase5_config_resolver import CanonicalRootPhase5ConfigResolver

    monkeypatch.setenv("OPENCODE_ALLOW_REPO_LOCAL_CONFIG", "1")
    assert CanonicalRootPhase5ConfigResolver(mode="pipeline").allow_repo_local_fallback() is False
    assert CanonicalRootPhase5ConfigResolver(mode="agents_strict").allow_repo_local_fallback() is True


@pytest.mark.governance
def test_runtime_wiring_configures_phase_resolvers():
    from governance.infrastructure.wiring import configure_gateway_registry
    from governance.application.use_cases.phase4_self_review import get_config_path_resolver as get_phase4_resolver
    from governance.application.use_cases.phase5_review_config import get_config_path_resolver as get_phase5_resolver

    configure_gateway_registry()
    assert get_phase4_resolver() is not None
    assert get_phase5_resolver() is not None
