"""Pytest configuration for governance tests."""
import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def _allow_repo_local_config():
    """Allow repo-local config for tests (dev environment)."""
    os.environ["OPENCODE_ALLOW_REPO_LOCAL_CONFIG"] = "1"
    
    # Configure the phase4_self_review resolver to use the infrastructure resolver
    # which reads the OPENCODE_ALLOW_REPO_LOCAL_CONFIG env var
    from governance.infrastructure.phase4_config_resolver import configure_phase4_self_review_resolver
    from governance.infrastructure.phase5_config_resolver import configure_phase5_review_resolver
    configure_phase4_self_review_resolver()
    configure_phase5_review_resolver()
    
    yield
    os.environ.pop("OPENCODE_ALLOW_REPO_LOCAL_CONFIG", None)
