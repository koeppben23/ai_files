from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_golden_outputs.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


@pytest.mark.governance
def test_generate_golden_outputs_uses_real_pipeline_fields(tmp_path: Path):
    out = tmp_path / "goldens"
    result = _run(["--repo-root", str(REPO_ROOT), "--output-dir", str(out)])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"

    expected = {"start.json", "what_blocks_me.json", "show_diagnostics.json", "where_am_i.json"}
    actual = {path.name for path in out.glob("*.json")}
    assert actual == expected

    sample = json.loads((out / "where_am_i.json").read_text(encoding="utf-8"))
    assert sample["schema"] == "governance-golden-intent-output.v1"
    assert sample["intent"] == "where_am_i"
    assert sample["engine"]["activation_hash"]
    assert sample["engine"]["ruleset_hash"]
    assert sample["engine"]["phase"]
    assert sample["parity"]["reason_code"]
    assert sample["render"]["header"]["next_command"] == sample["engine"]["next_command"]
