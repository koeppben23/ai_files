from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "rulebook_factory.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


@pytest.mark.governance
def test_rulebook_factory_generates_profile_rulebook(tmp_path: Path):
    result = _run(
        [
            "profile",
            "--profile-key",
            "backend-rust",
            "--stack-scope",
            "Rust backend services",
            "--applicability-signal",
            "cargo-lock-present",
            "--quality-focus",
            "deterministic tests",
            "--blocking-policy",
            "missing required evidence blocks Phase 4 entry",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"

    rulebook = tmp_path / "profiles" / "rules_backend-rust.md"
    assert rulebook.exists()
    text = rulebook.read_text(encoding="utf-8")
    assert "RULEBOOK-PRECEDENCE-POLICY" in text
    assert "Shared Principal Governance Contracts" in text


@pytest.mark.governance
def test_rulebook_factory_generates_addon_pair(tmp_path: Path):
    result = _run(
        [
            "addon",
            "--addon-key",
            "rustApiTemplates",
            "--addon-class",
            "required",
            "--rulebook-name",
            "backend-rust-templates",
            "--signal",
            "fileGlob=**/*.rs",
            "--domain-scope",
            "Template conformance for Rust APIs",
            "--critical-quality-claim",
            "template output is evidence-backed",
            "--owns-surface",
            "backend_templates",
            "--touches-surface",
            "api_contract",
            "--capability-any",
            "python",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"

    manifest = tmp_path / "profiles" / "addons" / "rustApiTemplates.addon.yml"
    rulebook = tmp_path / "profiles" / "rules.backend-rust-templates.md"
    assert manifest.exists()
    assert rulebook.exists()
    assert "addon_key: rustApiTemplates" in manifest.read_text(encoding="utf-8")
    assert "BLOCKED-MISSING-ADDON:rustApiTemplates" in rulebook.read_text(encoding="utf-8")


@pytest.mark.governance
def test_rulebook_factory_blocks_addon_without_capability(tmp_path: Path):
    result = _run(
        [
            "addon",
            "--addon-key",
            "rustApiTemplates",
            "--addon-class",
            "required",
            "--rulebook-name",
            "backend-rust-templates",
            "--signal",
            "fileGlob=**/*.rs",
            "--domain-scope",
            "Template conformance for Rust APIs",
            "--critical-quality-claim",
            "template output is evidence-backed",
            "--owns-surface",
            "backend_templates",
            "--touches-surface",
            "api_contract",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert "capability" in payload["message"]
