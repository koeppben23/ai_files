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
