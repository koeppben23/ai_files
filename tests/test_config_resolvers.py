from __future__ import annotations

import pytest


@pytest.mark.governance
def test_phase4_resolver_resolves_canonical_path():
    from governance.infrastructure.phase4_config_resolver import CanonicalRootConfigResolver

    path = CanonicalRootConfigResolver(mode="user").resolve_config_path()
    assert path is not None
    assert path.name == "phase4_self_review_config.yaml"


@pytest.mark.governance
def test_phase5_resolver_resolves_canonical_path():
    from governance.infrastructure.phase5_config_resolver import CanonicalRootPhase5ConfigResolver

    path = CanonicalRootPhase5ConfigResolver(mode="agents_strict").resolve_config_path()
    assert path is not None
    assert path.name == "phase5_review_config.yaml"


@pytest.mark.governance
def test_runtime_wiring_configures_phase_resolvers():
    from governance.infrastructure.wiring import configure_gateway_registry
    from governance.application.use_cases.phase4_self_review import get_config_path_resolver as get_phase4_resolver
    from governance.application.use_cases.phase5_review_config import get_config_path_resolver as get_phase5_resolver

    configure_gateway_registry()
    assert get_phase4_resolver() is not None
    assert get_phase5_resolver() is not None
