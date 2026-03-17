from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
from tests.util import get_master_path, get_rules_path, get_docs_path, get_profiles_path


@pytest.mark.governance
def test_md_lint_runs_in_ci_mode_and_reports_json():
    script = REPO_ROOT / "governance" / "entrypoints" / "md_lint.py"
    assert script.exists(), "md_lint.py missing"
    files = [
        get_master_path(),
        get_rules_path(),
        REPO_ROOT / "continue.md",
        REPO_ROOT / "review.md",
        get_docs_path() / "resume.md",
        get_docs_path() / "resume_prompt.md",
        get_docs_path() / "new_profile.md",
        get_docs_path() / "new_addon.md",
        REPO_ROOT / "BOOTSTRAP.md",
    ]
    files.extend(sorted((get_profiles_path()).glob("rules*.md")))
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
