from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_ruleset_lock.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


@pytest.mark.governance
def test_build_ruleset_lock_outputs_hash_artifacts(tmp_path: Path):
    out_root = tmp_path / "rulesets"
    result = _run([
        "--ruleset-id",
        "default",
        "--version",
        "1.2.3",
        "--output-root",
        str(out_root),
    ])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert payload["ruleset_hash"]

    base = out_root / "default" / "1.2.3"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((base / "lock.json").read_text(encoding="utf-8"))
    hashes = json.loads((base / "hashes.json").read_text(encoding="utf-8"))

    assert manifest["schema"] == "governance-ruleset-manifest.v1"
    assert lock["schema"] == "governance-ruleset-lock.v1"
    assert lock["deterministic"] is True
    assert manifest["source_file_count"] == len(manifest["source_files"])
    assert lock["source_files"] == manifest["source_files"]
    assert lock["resolved_core_rulebooks"] == ["master.md", "rules.md", "start.md"]
    assert hashes["ruleset_hash"] == payload["ruleset_hash"]


@pytest.mark.governance
def test_build_ruleset_lock_rejects_invalid_version(tmp_path: Path):
    out_root = tmp_path / "rulesets"
    result = _run([
        "--ruleset-id",
        "default",
        "--version",
        "not-semver",
        "--output-root",
        str(out_root),
    ])

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert "semver" in payload["message"]
