from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "workflow_template_factory.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


def _write_catalog(repo_root: Path, templates: list[dict[str, str]]) -> None:
    catalog = {
        "schema": "governance.workflow-template-catalog.v1",
        "catalog_version": 1,
        "templates": templates,
    }
    path = repo_root / "templates" / "github-actions" / "template_catalog.json"
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


@pytest.mark.governance
def test_workflow_template_factory_check_passes_for_repo_catalog():
    result = _run(["check"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert "governance-pr-gate-shadow-live-verify" in payload["template_keys"]


@pytest.mark.governance
def test_workflow_template_factory_scaffold_adds_file_and_catalog_entry(tmp_path: Path):
    repo_root = tmp_path / "repo"
    workflow_dir = repo_root / "templates" / "github-actions"
    workflow_dir.mkdir(parents=True)

    existing_file = workflow_dir / "governance-existing.yml"
    existing_file.write_text("name: Existing\n", encoding="utf-8")
    _write_catalog(
        repo_root,
        [
            {
                "template_key": "governance-existing",
                "file": "templates/github-actions/governance-existing.yml",
                "archetype": "pipeline_roles_hardened",
                "purpose": "Existing template",
            }
        ],
    )

    result = _run(
        [
            "scaffold",
            "--repo-root",
            str(repo_root),
            "--template-key",
            "governance-sample-gate",
            "--archetype",
            "pr_gate_shadow_live_verify",
            "--title",
            "Governance Sample Gate",
            "--purpose",
            "Sample gate template",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"

    created_file = workflow_dir / "governance-sample-gate.yml"
    assert created_file.exists()
    assert "name: Governance Sample Gate" in created_file.read_text(encoding="utf-8")

    catalog = json.loads((workflow_dir / "template_catalog.json").read_text(encoding="utf-8"))
    keys = [entry["template_key"] for entry in catalog["templates"]]
    assert keys == sorted(keys)
    assert "governance-sample-gate" in keys

    check = _run(["check", "--repo-root", str(repo_root)])
    assert check.returncode == 0, check.stderr


@pytest.mark.governance
def test_workflow_template_factory_check_blocks_untracked_template(tmp_path: Path):
    repo_root = tmp_path / "repo"
    workflow_dir = repo_root / "templates" / "github-actions"
    workflow_dir.mkdir(parents=True)

    tracked_file = workflow_dir / "governance-tracked.yml"
    tracked_file.write_text("name: Tracked\n", encoding="utf-8")
    untracked_file = workflow_dir / "governance-orphan.yml"
    untracked_file.write_text("name: Orphan\n", encoding="utf-8")

    _write_catalog(
        repo_root,
        [
            {
                "template_key": "governance-tracked",
                "file": "templates/github-actions/governance-tracked.yml",
                "archetype": "golden_output_stability",
                "purpose": "Tracked template",
            }
        ],
    )

    result = _run(["check", "--repo-root", str(repo_root)])
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert "templates/github-actions/governance-orphan.yml" in payload["untracked_files"]
