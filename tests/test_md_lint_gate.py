from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.governance
def test_md_lint_runs_in_ci_mode_and_reports_json():
    script = REPO_ROOT / "governance" / "entrypoints" / "md_lint.py"
    assert script.exists(), "md_lint.py missing"
    files = [
        REPO_ROOT / "master.md",
        REPO_ROOT / "rules.md",
        REPO_ROOT / "continue.md",
        REPO_ROOT / "docs" / "_archive" / "resume.md",
        REPO_ROOT / "docs" / "_archive" / "resume_prompt.md",
        REPO_ROOT / "docs" / "_archive" / "new_profile.md",
        REPO_ROOT / "docs" / "_archive" / "new_addon.md",
        REPO_ROOT / "BOOTSTRAP.md",
    ]
    files.extend(sorted((REPO_ROOT / "profiles").glob("rules*.md")))
    file_args = [str(p) for p in files if p.exists()]
    proc = subprocess.run(
        [sys.executable, str(script), *file_args, "--ci"],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode in {0, 1, 3}
    payload = json.loads(proc.stdout or "{}")
    assert "files_checked" in payload
    assert "findings_count" in payload
