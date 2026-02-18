from __future__ import annotations

import re

import pytest

from .util import REPO_ROOT, read_text


@pytest.mark.release
def test_install_py_has_version_constant():
    text = read_text(REPO_ROOT / "install.py")
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    assert m, "No VERSION found in install.py"


@pytest.mark.release
def test_master_md_has_governance_version_header():
    head = "\n".join(read_text(REPO_ROOT / "master.md").splitlines()[:60])
    m = re.search(r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)", head)
    assert m, "No Governance-Version header found in master.md"


@pytest.mark.release
def test_versions_are_consistent_master_install_changelog():
    master_head = "\n".join(read_text(REPO_ROOT / "master.md").splitlines()[:80])
    m_master = re.search(
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        master_head,
    )
    assert m_master, "No Governance-Version header found in master.md"
    gv = m_master.group(1)

    install_text = read_text(REPO_ROOT / "install.py")
    m_inst = re.search(r'VERSION\s*=\s*"([^"]+)"', install_text)
    assert m_inst, "No VERSION found in install.py"
    iv = m_inst.group(1)

    changelog = read_text(REPO_ROOT / "CHANGELOG.md")
    assert f"## [{gv}]" in changelog, f"CHANGELOG.md missing section for [{gv}]"

    assert iv == gv, f"install.py VERSION ({iv}) != master.md Governance-Version ({gv})"
