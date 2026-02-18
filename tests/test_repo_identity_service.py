from __future__ import annotations

from pathlib import Path

import pytest

from governance.application.repo_identity_service import canonicalize_origin_url, derive_repo_identity


@pytest.mark.governance
def test_canonicalize_origin_url_supports_scp_style():
    assert canonicalize_origin_url("git@github.com:Example/Repo.git") == "repo://github.com/example/repo"


@pytest.mark.governance
def test_derive_repo_identity_remote_vs_local_material_classes(tmp_path: Path):
    remote_identity = derive_repo_identity(tmp_path, canonical_remote="repo://github.com/example/repo", git_dir=None)
    local_identity = derive_repo_identity(tmp_path, canonical_remote=None, git_dir=None)

    assert remote_identity.material_class == "remote_canonical"
    assert local_identity.material_class == "local_path"
    assert remote_identity.fingerprint != local_identity.fingerprint
