from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "diagnostics" / "start_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("start_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_readonly module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_start_preflight_readonly_module_exists_and_declares_readonly():
    module = _load_module()
    assert module.READ_ONLY is True


@pytest.mark.governance
def test_start_preflight_readonly_hook_never_persists(capsys: pytest.CaptureFixture[str]):
    module = _load_module()
    module.run_persistence_hook()
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "skipped"
    assert payload["reason"] == "read-only-preflight"
    assert payload["read_only"] is True


@pytest.mark.governance
def test_start_preflight_derive_repo_fingerprint_requires_git_repo(tmp_path: Path):
    module = _load_module()
    assert module.derive_repo_fingerprint(tmp_path) is None


@pytest.mark.governance
def test_start_preflight_derive_repo_fingerprint_from_git_repo(tmp_path: Path):
    module = _load_module()
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)
    fp = module.derive_repo_fingerprint(tmp_path)
    assert isinstance(fp, str) and len(fp) == 24


@pytest.mark.governance
def test_start_md_uses_readonly_preflight_helper():
    text = (REPO_ROOT / "start.md").read_text(encoding="utf-8")
    assert "start_preflight_readonly.py" in text
    assert "start_preflight_persistence.py" not in text


@pytest.mark.governance
def test_start_persistence_store_module_removed():
    assert not (REPO_ROOT / "governance" / "infrastructure" / "start_persistence_store.py").exists()
