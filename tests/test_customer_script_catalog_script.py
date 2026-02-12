from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "customer_script_catalog.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


@pytest.mark.governance
def test_customer_script_catalog_check_passes():
    result = _run([])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert payload["ship_in_release_count"] >= 1


@pytest.mark.governance
def test_customer_script_catalog_lists_shipped_scripts():
    result = _run(["list", "--shipped-only"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"

    shipped_paths = {entry["path"] for entry in payload["scripts"]}
    assert "scripts/workflow_template_factory.py" in shipped_paths
    assert "scripts/rulebook_factory.py" in shipped_paths
