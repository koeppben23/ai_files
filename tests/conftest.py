"""Pytest configuration for governance tests."""
import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def _allow_repo_local_config():
    """Allow repo-local config for tests (dev environment)."""
    os.environ["OPENCODE_ALLOW_REPO_LOCAL_CONFIG"] = "1"
    yield
    os.environ.pop("OPENCODE_ALLOW_REPO_LOCAL_CONFIG", None)
