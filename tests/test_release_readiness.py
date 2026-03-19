from __future__ import annotations

import re

import pytest

from .util import REPO_ROOT, read_text


@pytest.mark.release
def test_governance_version_file_exists():
    version_file = REPO_ROOT / "governance" / "VERSION"
    assert version_file.exists(), "governance/VERSION not found"
    version = version_file.read_text(encoding="utf-8").strip()
    assert version, "governance/VERSION is empty"


@pytest.mark.release
def test_install_py_has_version_constant():
    text = read_text(REPO_ROOT / "governance_runtime" / "install" / "install.py")
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    assert m, "No VERSION found in install.py"


@pytest.mark.release
def test_versions_are_consistent_version_install_changelog():
    version_file = REPO_ROOT / "governance" / "VERSION"
    gv = version_file.read_text(encoding="utf-8").strip()
    assert gv, "governance/VERSION is empty"

    install_text = read_text(REPO_ROOT / "governance_runtime" / "install" / "install.py")
    m_inst = re.search(r'VERSION\s*=\s*"([^"]+)"', install_text)
    assert m_inst, "No VERSION found in install.py"
    iv = m_inst.group(1)

    changelog = read_text(REPO_ROOT / "CHANGELOG.md")
    assert f"## [{gv}]" in changelog, f"CHANGELOG.md missing section for [{gv}]"

    assert iv == gv, f"runtime installer VERSION ({iv}) != governance/VERSION ({gv})"
