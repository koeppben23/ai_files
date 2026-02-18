from __future__ import annotations

import hashlib
import re

from diagnostics.persist_workspace_artifacts import _derive_fingerprint_from_repo
from diagnostics.start_preflight_persistence import derive_repo_fingerprint
from governance.infrastructure.path_contract import normalize_for_fingerprint


def _is_short_hex(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{24}", value) is not None


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
    assert material.startswith("repo:local:")


def test_persist_helper_path_fingerprint_material_is_normalized(tmp_path):
    repo_root = tmp_path / "Repo-MixedCase"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()

    derived = _derive_fingerprint_from_repo(repo_root)
    assert derived is not None
    fp, material = derived
    assert _is_short_hex(fp)

    normalized = normalize_for_fingerprint(repo_root)
    assert material == f"repo:local:{normalized}"


def test_start_preflight_path_fingerprint_uses_normalized_path_material(tmp_path):
    repo_root = tmp_path / "Repo-MixedCase"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()

    fp = derive_repo_fingerprint(repo_root)
    assert isinstance(fp, str)
    assert _is_short_hex(fp)

    normalized = normalize_for_fingerprint(repo_root)
    expected = hashlib.sha256(f"repo:local:{normalized}".encode("utf-8")).hexdigest()[:24]
    assert fp == expected


def test_remote_origin_canonicalization_ignores_transport_variants(tmp_path):
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    for repo in (repo_a, repo_b):
        (repo / ".git").mkdir(parents=True, exist_ok=True)

    (repo_a / ".git" / "config").write_text(
        """[remote \"origin\"]\n    url = git@github.com:Example/Team-Repo.git\n""",
        encoding="utf-8",
    )
    (repo_b / ".git" / "config").write_text(
        """[remote \"origin\"]\n    url = ssh://github.com/example/team-repo\n""",
        encoding="utf-8",
    )

    fp_a = derive_repo_fingerprint(repo_a)
    fp_b = derive_repo_fingerprint(repo_b)
    assert fp_a == fp_b
def test_remote_origin_canonicalization_ignores_scheme_variants(tmp_path):
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    for repo in (repo_a, repo_b):
        (repo / ".git").mkdir(parents=True, exist_ok=True)

    (repo_a / ".git" / "config").write_text(
        """[remote \"origin\"]\n    url = https://github.com/example/team-repo.git\n""",
        encoding="utf-8",
    )
    (repo_b / ".git" / "config").write_text(
        """[remote \"origin\"]\n    url = ssh://git@github.com/example/team-repo\n""",
        encoding="utf-8",
    )

    fp_a = derive_repo_fingerprint(repo_a)
    fp_b = derive_repo_fingerprint(repo_b)
    assert fp_a == fp_b
