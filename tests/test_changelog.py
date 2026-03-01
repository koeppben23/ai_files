from __future__ import annotations

import re

import pytest

from .util import REPO_ROOT, read_text


def _governance_version() -> str:
    version_file = REPO_ROOT / "governance" / "VERSION"
    assert version_file.exists(), "Missing governance/VERSION"
    version = version_file.read_text(encoding="utf-8").strip()
    assert version, "Empty governance/VERSION"
    return version


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
        rf"^##\s*\[{re.escape(ver)}\][^\n]*$\n(?P<body>.*?)(?=^##\s*\[|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert m, f"Could not locate changelog body for version {ver!r}"
    body = m.group("body").strip()
    assert re.search(r"^\s*-\s+\S+", body, flags=re.MULTILINE), f"Changelog section for {ver!r} must contain at least one bullet"
