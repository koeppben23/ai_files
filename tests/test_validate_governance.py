from __future__ import annotations

import re
from pathlib import Path

import pytest

from .util import REPO_ROOT, read_text


@pytest.mark.governance
def test_required_files_present():
    required = [
        "master.md",
        "rules.md",
        "start.md",
        "SESSION_STATE_SCHEMA.md",
    ]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    assert not missing, f"Missing: {missing}"


@pytest.mark.governance
def test_blocked_consistency_schema_vs_master():
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    master = read_text(REPO_ROOT / "master.md")

    s = set(re.findall(r"BLOCKED-[A-Z-]+", schema))
    m = set(re.findall(r"BLOCKED-[A-Z-]+", master))

    diff = s - m
    assert not diff, f"Missing in master: {sorted(diff)}"
