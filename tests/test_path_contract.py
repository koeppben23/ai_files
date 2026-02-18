from __future__ import annotations

import os
from pathlib import Path

import pytest

from governance.infrastructure.path_contract import (
    NotAbsoluteError,
    binding_evidence_location,
    canonical_commands_home,
    canonical_config_root,
    normalize_absolute_path,
    normalize_for_fingerprint,
)


@pytest.mark.governance
def test_canonical_roots_are_home_scoped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert canonical_config_root() == tmp_path / ".config" / "opencode"
    assert canonical_commands_home() == tmp_path / ".config" / "opencode" / "commands"


@pytest.mark.governance
def test_normalize_absolute_path_rejects_relative():
    with pytest.raises(NotAbsoluteError):
        normalize_absolute_path("./commands", purpose="test")


@pytest.mark.governance
def test_normalize_for_fingerprint_is_casefolded_and_slash_normalized(tmp_path: Path):
    value = normalize_for_fingerprint(tmp_path / "Repo" / "Sub")
    assert "\\" not in value
    if os.name == "nt":
        assert value == value.casefold()
    else:
        assert value.endswith("/Repo/Sub")


@pytest.mark.governance
def test_binding_evidence_location_uses_canonical_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    location = binding_evidence_location(
        trusted_commands_root=None,
        allow_trusted_override=False,
        mode="user",
    )
    assert location.source == "canonical"
    assert location.commands_home == tmp_path / ".config" / "opencode" / "commands"
