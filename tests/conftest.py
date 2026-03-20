import json
import os
import shutil
import tempfile
from pathlib import Path
import sys

import pytest

from tests.util import REPO_ROOT


_ERROR_CONTEXT_DEFAULTS: dict = {
    "repo_fingerprint": None,
    "repo_root": None,
    "config_root": None,
    "commands_home": None,
    "workspaces_home": None,
    "phase": "unknown",
    "command": "unknown",
}


@pytest.fixture(autouse=True)
def _isolate_error_context():
    """Prevent _ERROR_CONTEXT state leaking between tests."""
    import governance_runtime.infrastructure.logging.global_error_handler as geh

    original = geh._ERROR_CONTEXT.copy()
    geh._ERROR_CONTEXT.clear()
    geh._ERROR_CONTEXT.update(_ERROR_CONTEXT_DEFAULTS)
    yield
    geh._ERROR_CONTEXT.clear()
    geh._ERROR_CONTEXT.update(original)


@pytest.fixture(autouse=True, scope="session")
def _configure_binding_evidence(tmp_path_factory: pytest.TempPathFactory):
    """Provide canonical binding evidence for tests."""
    home = tmp_path_factory.mktemp("opencode-home")
    config_root = home / ".config" / "opencode"
    commands_home = Path(str(REPO_ROOT))
    workspaces_home = config_root / "workspaces"
    evidence_file = config_root / "governance.paths.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(config_root),
            "localRoot": str(REPO_ROOT),
            "commandsHome": str(commands_home),
            "runtimeHome": str(REPO_ROOT / "governance_runtime"),
            "governanceHome": str(REPO_ROOT / "governance_runtime"),
            "contentHome": str(REPO_ROOT / "governance_content"),
            "specHome": str(REPO_ROOT / "governance_spec"),
            "profilesHome": str(REPO_ROOT / "governance_content" / "profiles"),
            "workspacesHome": str(workspaces_home),
            "pythonCommand": sys.executable,
        },
    }
    evidence_file.write_text(json.dumps(payload), encoding="utf-8")

    original_home = Path.home
    Path.home = staticmethod(lambda: home)  # type: ignore[assignment]
    os.environ["OPENCODE_OPERATING_MODE"] = "user"

    from governance_runtime.infrastructure.phase4_config_resolver import configure_phase4_self_review_resolver
    from governance_runtime.infrastructure.phase5_config_resolver import configure_phase5_review_resolver

    configure_phase4_self_review_resolver()
    configure_phase5_review_resolver()

    yield
    Path.home = original_home  # type: ignore[assignment]
    os.environ.pop("OPENCODE_OPERATING_MODE", None)


@pytest.fixture()
def short_tmp(request: pytest.FixtureRequest):
    """Provide a short temporary directory path to stay within Windows MAX_PATH (260).

    The default pytest ``tmp_path`` includes the full test function name,
    which can push deep archive paths (``governance-records/<fp>/runs/…``)
    past 260 characters on Windows.  This fixture creates a directory under
    the system temp root with an 8-char random name (e.g. ``C:\\Users\\X\\AppData\\Local\\Temp\\gv_a1b2c3d4``)
    and cleans it up after the test.
    """
    d = Path(tempfile.mkdtemp(prefix="gv_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)
