from __future__ import annotations

import hashlib
import re

from diagnostics.persist_workspace_artifacts import _derive_fingerprint_from_repo
from diagnostics.start_preflight_persistence import derive_repo_fingerprint


def _is_short_hex(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{16}", value) is not None


def test_start_preflight_derive_repo_fingerprint_requires_git_repo(tmp_path):
    fp = derive_repo_fingerprint(tmp_path)
    assert fp is None


def test_start_preflight_derive_repo_fingerprint_falls_back_without_origin(tmp_path):
    (tmp_path / ".git").mkdir()
    fp = derive_repo_fingerprint(tmp_path)
    assert isinstance(fp, str)
    assert _is_short_hex(fp)


def test_persist_helper_derive_fingerprint_requires_git_repo(tmp_path):
    derived = _derive_fingerprint_from_repo(tmp_path)
    assert derived is None


def test_persist_helper_derive_fingerprint_falls_back_without_origin(tmp_path):
    (tmp_path / ".git").mkdir()
    derived = _derive_fingerprint_from_repo(tmp_path)
    assert derived is not None
    fp, material = derived
    assert _is_short_hex(fp)
    assert material.startswith("local-git|")


def test_persist_helper_path_fingerprint_material_is_normalized(tmp_path):
    repo_root = tmp_path / "Repo-MixedCase"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()

    derived = _derive_fingerprint_from_repo(repo_root)
    assert derived is not None
    fp, material = derived
    assert _is_short_hex(fp)

    normalized = repo_root.expanduser().resolve().as_posix().replace("\\", "/").casefold()
    assert material == f"local-git|{normalized}|main"


def test_start_preflight_path_fingerprint_uses_normalized_path_material(tmp_path):
    repo_root = tmp_path / "Repo-MixedCase"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()

    fp = derive_repo_fingerprint(repo_root)
    assert isinstance(fp, str)
    assert _is_short_hex(fp)

    normalized = repo_root.expanduser().resolve().as_posix().replace("\\", "/").casefold()
    expected = hashlib.sha256(f"local-git|{normalized}|main".encode("utf-8")).hexdigest()[:16]
    assert fp == expected
