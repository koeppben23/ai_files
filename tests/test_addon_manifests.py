from __future__ import annotations

import re
from pathlib import Path

import pytest

from .util import REPO_ROOT, git_ls_files, read_text


@pytest.mark.governance
def test_addon_manifests_reference_existing_rulebooks():
    """Addon manifests are declarative; they must not point to missing rulebooks."""
    manifests = list(git_ls_files("profiles/addons/*.addon.yml"))
    assert manifests, "No addon manifests found under profiles/addons/*.addon.yml"

    missing = []
    for rel in manifests:
        p = REPO_ROOT / rel
        t = read_text(p)
        m = re.search(r"^rulebook:\s*([^\s#]+)\s*$", t, flags=re.MULTILINE)
        assert m, f"Missing 'rulebook:' field in addon manifest: {rel}"

        rb = m.group(1).strip()
        rb_path = (REPO_ROOT / "profiles" / rb) if not rb.startswith("profiles/") else (REPO_ROOT / rb)
        if not rb_path.exists():
            missing.append((rel, rb))

    assert not missing, "Addon manifests reference missing rulebooks:\n" + "\n".join(
        [f"- {m}: {rb}" for m, rb in missing]
    )


@pytest.mark.governance
def test_addon_manifests_have_addon_key():
    manifests = list(git_ls_files("profiles/addons/*.addon.yml"))
    assert manifests, "No addon manifests found under profiles/addons/*.addon.yml"

    bad = []
    for rel in manifests:
        t = read_text(REPO_ROOT / rel)
        if re.search(r"^addon_key:\s*\S+\s*$", t, flags=re.MULTILINE) is None:
            bad.append(rel)

    assert not bad, "Addon manifests missing addon_key:\n" + "\n".join([f"- {r}" for r in bad])
