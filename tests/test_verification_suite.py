from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, write_governance_paths


def _load_preflight_module():
    script = REPO_ROOT / "diagnostics" / "start_preflight_persistence.py"
    spec = importlib.util.spec_from_file_location("start_preflight_persistence", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_persistence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_start_nested_cwd_without_repo_override_is_non_destructive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / ".config" / "opencode"
    write_governance_paths(cfg)

    diagnostics_dst = cfg / "commands" / "diagnostics"
    diagnostics_dst.mkdir(parents=True, exist_ok=True)
    for name in ["bootstrap_session_state.py", "workspace_lock.py", "error_logs.py"]:
        shutil.copy2(REPO_ROOT / "diagnostics" / name, diagnostics_dst / name)

    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    nested = repo_root / "src" / "feature"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_preflight_module()
    monkeypatch.setattr(module.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(module, "PYTHON_COMMAND", sys.executable)
    monkeypatch.setattr(module.shutil, "which", lambda cmd: "/usr/bin/git" if cmd == "git" else None)
    module.ROOT = cfg
    module.COMMANDS_RUNTIME_DIR = cfg / "commands"
    module.WORKSPACES_HOME = cfg / "workspaces"
    module.BINDING_OK = True
    module.BINDING_EVIDENCE_PATH = cfg / "commands" / "governance.paths.json"
    module.DIAGNOSTICS_DIR = diagnostics_dst
    module.BOOTSTRAP_HELPER = diagnostics_dst / "bootstrap_session_state.py"

    assert module.bootstrap_identity_if_needed() is False
    assert not (cfg / "workspaces").exists()
    assert not (cfg / "SESSION_STATE.json").exists()


@pytest.mark.governance
def test_pipeline_missing_binding_blocks_without_prompt_fields(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    module = _load_preflight_module()
    monkeypatch.setattr(module, "BINDING_OK", False)
    monkeypatch.setattr(
        module,
        "load_json",
        lambda _path: {"required_now": [{"command": "git"}], "required_later": []},
    )
    monkeypatch.setattr(module.shutil, "which", lambda _cmd: "/usr/bin/git")

    module.emit_preflight()
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["block_now"] is True
    assert payload["binding_evidence"] == "invalid"
    assert "prompt" not in json.dumps(payload).lower()


@pytest.mark.governance
def test_windows_path_with_spaces_uses_argv_first(monkeypatch: pytest.MonkeyPatch):
    module = _load_preflight_module()
    monkeypatch.setattr(module, "PYTHON_COMMAND", "py -3")
    repo_root = Path("C:/Users/Test User/Repo Root")
    argv = module.persist_command_argv(repo_root)
    assert argv[:2] == ["py", "-3"]
    assert argv[-1] == str(repo_root)


@pytest.mark.governance
def test_repo_identity_stable_across_remote_url_styles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    module = _load_preflight_module()

    def make_repo(name: str, url: str) -> Path:
        repo = tmp_path / name
        git_dir = repo / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        (git_dir / "config").write_text(f"[remote \"origin\"]\n    url = {url}\n", encoding="utf-8")
        return repo

    a = make_repo("a", "git@github.com:Example/Team-Repo.git")
    b = make_repo("b", "https://github.com/example/team-repo")

    fp_a = module.derive_repo_fingerprint(a)
    fp_b = module.derive_repo_fingerprint(b)
    assert fp_a == fp_b
