from __future__ import annotations

import re

import pytest

from .util import REPO_ROOT, read_text


def _governance_version() -> str:
    head = "\n".join(read_text(REPO_ROOT / "master.md").splitlines()[:80])
    m = re.search(
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        head,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert m, "Missing Governance-Version in master.md"
    return m.group(1)


@pytest.mark.release
def test_changelog_exists_and_has_required_sections():
    p = REPO_ROOT / "CHANGELOG.md"
    assert p.exists(), "Missing CHANGELOG.md at repo root"

    text = read_text(p)
    assert re.search(r"^##\s*\[Unreleased\]", text, flags=re.MULTILINE), "CHANGELOG.md must have [Unreleased]"

    ver = _governance_version()
    pat = rf"^##\s*\[{re.escape(ver)}\]\s*-\s*\d{{4}}-\d{{2}}-\d{{2}}\s*$"
    assert re.search(pat, text, flags=re.MULTILINE), f"CHANGELOG.md must contain a version section for {ver!r}"


@pytest.mark.release
def test_changelog_has_some_content_for_current_version():
    ver = _governance_version()
    text = read_text(REPO_ROOT / "CHANGELOG.md")
    m = re.search(
        rf"^##\s*\[{re.escape(ver)}\].*$\n(?P<body>.*?)(?=^##\s*\[|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert m, f"Could not locate changelog body for version {ver!r}"
    body = m.group("body").strip()
    assert re.search(r"^\s*-\s+\S+", body, flags=re.MULTILINE), f"Changelog section for {ver!r} must contain at least one bullet"
