from __future__ import annotations

import re

from diagnostics.persist_workspace_artifacts import _derive_fingerprint_from_repo
from diagnostics.start_preflight_persistence import derive_repo_fingerprint


def _is_short_hex(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{16}", value) is not None


def test_start_preflight_derive_repo_fingerprint_falls_back_without_git(tmp_path):
    fp = derive_repo_fingerprint(tmp_path)
    assert isinstance(fp, str)
    assert _is_short_hex(fp)


def test_start_preflight_derive_repo_fingerprint_falls_back_without_origin(tmp_path):
    (tmp_path / ".git").mkdir()
    fp = derive_repo_fingerprint(tmp_path)
    assert isinstance(fp, str)
    assert _is_short_hex(fp)


def test_persist_helper_derive_fingerprint_falls_back_without_git(tmp_path):
    derived = _derive_fingerprint_from_repo(tmp_path)
    assert derived is not None
    fp, material = derived
    assert _is_short_hex(fp)
    assert material.startswith("local-path|")


def test_persist_helper_derive_fingerprint_falls_back_without_origin(tmp_path):
    (tmp_path / ".git").mkdir()
    derived = _derive_fingerprint_from_repo(tmp_path)
    assert derived is not None
    fp, material = derived
    assert _is_short_hex(fp)
    assert material.startswith("local-git|")
