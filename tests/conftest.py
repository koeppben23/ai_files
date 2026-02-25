"""Pytest configuration for governance tests."""
import json
import os
from pathlib import Path
import sys

import pytest

from tests.util import REPO_ROOT


@pytest.fixture(autouse=True, scope="session")
def _configure_binding_evidence(tmp_path_factory: pytest.TempPathFactory):
    """Provide canonical binding evidence for tests."""
    home = tmp_path_factory.mktemp("opencode-home")
    config_root = home / ".config" / "opencode"
    commands_home = Path(str(REPO_ROOT))
    workspaces_home = config_root / "workspaces"
    evidence_file = config_root / "commands" / "governance.paths.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(config_root),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "pythonCommand": sys.executable,
        },
    }
    evidence_file.write_text(json.dumps(payload), encoding="utf-8")

    original_home = Path.home
    Path.home = staticmethod(lambda: home)  # type: ignore[assignment]
    os.environ["OPENCODE_OPERATING_MODE"] = "user"

    from governance.infrastructure.phase4_config_resolver import configure_phase4_self_review_resolver
    from governance.infrastructure.phase5_config_resolver import configure_phase5_review_resolver

    configure_phase4_self_review_resolver()
    configure_phase5_review_resolver()

    yield
    Path.home = original_home  # type: ignore[assignment]
    os.environ.pop("OPENCODE_OPERATING_MODE", None)
