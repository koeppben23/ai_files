from __future__ import annotations

import json
from pathlib import Path

import pytest

from install import ensure_opencode_json, resolve_effective_opencode_port
from governance_runtime.infrastructure.opencode_server_client import (
    ServerNotAvailableError,
    resolve_opencode_server_base_url,
)


def _setup_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    config_root = home / ".config" / "opencode"
    config_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    return config_root


@pytest.mark.governance
def test_port_contract_cli_precedence_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLI > env > default and runtime resolver sees same configured port."""
    config_root = _setup_home(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCODE_PORT", "6123")

    effective = resolve_effective_opencode_port(
        cli_opencode_port="5123",
        env={"OPENCODE_PORT": "6123"},
    )
    ensure_opencode_json(config_root, dry_run=False, effective_opencode_port=effective)

    with pytest.warns(RuntimeWarning, match="drift detected"):
        base_url = resolve_opencode_server_base_url()
    assert base_url == "http://127.0.0.1:5123"


@pytest.mark.governance
def test_port_contract_env_fallback_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If CLI port is absent, env fallback becomes effective and persisted."""
    config_root = _setup_home(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCODE_PORT", "5007")

    effective = resolve_effective_opencode_port(
        cli_opencode_port=None,
        env={"OPENCODE_PORT": "5007"},
    )
    ensure_opencode_json(config_root, dry_run=False, effective_opencode_port=effective)

    base_url = resolve_opencode_server_base_url()
    assert base_url == "http://127.0.0.1:5007"


@pytest.mark.governance
def test_port_contract_default_4096_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If no CLI/env port is present, default 4096 is used consistently."""
    config_root = _setup_home(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENCODE_PORT", raising=False)

    effective = resolve_effective_opencode_port(cli_opencode_port=None, env={})
    ensure_opencode_json(config_root, dry_run=False, effective_opencode_port=effective)

    data = json.loads((config_root / "opencode.json").read_text(encoding="utf-8"))
    assert data["server"]["port"] == 4096
    assert resolve_opencode_server_base_url() == "http://127.0.0.1:4096"


@pytest.mark.governance
def test_port_contract_invalid_env_fails_closed_when_no_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invalid OPENCODE_PORT without opencode.json must fail closed."""
    _setup_home(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCODE_PORT", "99999")
    with pytest.raises(ServerNotAvailableError, match="OPENCODE_PORT"):
        resolve_opencode_server_base_url()
