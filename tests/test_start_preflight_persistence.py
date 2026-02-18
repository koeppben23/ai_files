from __future__ import annotations

import importlib.util
import json
import platform
from pathlib import Path

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "diagnostics" / "start_preflight_persistence.py"
    spec = importlib.util.spec_from_file_location("start_preflight_persistence", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_persistence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_emit_preflight_treats_python3_as_python_equivalent(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Preflight should not block when python3 exists but python alias is missing."""

    module = _load_module()
    monkeypatch.setattr(module, "TOOL_CATALOG", REPO_ROOT / "diagnostics" / "tool_requirements.json")

    def fake_which(command: str):
        if command == "git":
            return "/usr/bin/git"
        if command == "python3":
            return "/usr/bin/python3"
        if command == "python":
            return None
        return None

    monkeypatch.setattr(module.shutil, "which", fake_which)
    monkeypatch.setattr(module, "BINDING_OK", True)
    monkeypatch.setattr(
        module,
        "load_json",
        lambda _path: {
            "required_now": [
                {"command": "git"},
                {"command": "python"},
                {"command": "python3"},
            ],
            "required_later": [],
        },
    )

    module.emit_preflight()
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert payload["preflight"] == "ok"
    assert payload["block_now"] is False
    assert payload["missing"] == []
    assert "python" in payload["available"]
    assert "python3" in payload["available"]
    assert "windows_longpaths" in payload
    assert "git_safe_directory" in payload
    assert "advisories" in payload


@pytest.mark.governance
def test_emit_preflight_blocks_when_both_python_aliases_missing(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Preflight should block when neither python nor python3 is available."""

    module = _load_module()
    monkeypatch.setattr(module, "TOOL_CATALOG", REPO_ROOT / "diagnostics" / "tool_requirements.json")

    def fake_which(command: str):
        if command == "git":
            return "/usr/bin/git"
        return None

    monkeypatch.setattr(module.shutil, "which", fake_which)
    monkeypatch.setattr(module, "BINDING_OK", True)
    monkeypatch.setattr(
        module,
        "load_json",
        lambda _path: {
            "required_now": [
                {"command": "git"},
                {"command": "python"},
                {"command": "python3"},
            ],
            "required_later": [],
        },
    )

    module.emit_preflight()
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert payload["preflight"] == "degraded"
    assert payload["block_now"] is True
    assert set(payload["missing"]) == {"python", "python3"}
    assert "windows_longpaths" in payload
    assert "git_safe_directory" in payload


@pytest.mark.governance
def test_emit_preflight_blocks_on_invalid_binding_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    monkeypatch.setattr(module, "BINDING_OK", False)
    monkeypatch.setattr(
        module,
        "load_json",
        lambda _path: {
            "required_now": [{"command": "git"}],
            "required_later": [],
        },
    )
    monkeypatch.setattr(module.shutil, "which", lambda _c: "/usr/bin/git")

    module.emit_preflight()
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["binding_evidence"] == "invalid"
    assert payload["block_now"] is True


@pytest.mark.governance
def test_preflight_discovers_binding_from_cwd_ancestor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / "commands"
    cfg.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(tmp_path),
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    nested = tmp_path / "repo" / "a" / "b"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))

    module = _load_module()
    assert module.BINDING_OK is False


@pytest.mark.governance
def test_preflight_discovers_binding_from_cwd_ancestor_with_dev_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cfg = tmp_path / "commands"
    cfg.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(tmp_path),
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    nested = tmp_path / "repo" / "a" / "b"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.setenv("OPENCODE_ALLOW_CWD_BINDINGS", "1")

    module = _load_module()
    assert module.BINDING_OK is False


@pytest.mark.governance
def test_preflight_discovers_binding_from_canonical_home_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / ".config" / "opencode"
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(cfg / "commands"),
            "workspacesHome": str(cfg / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (cfg / "commands").mkdir(parents=True, exist_ok=True)
    (cfg / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)

    module = _load_module()
    assert module.BINDING_OK is True


@pytest.mark.governance
def test_preflight_rejects_relative_binding_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / ".config" / "opencode"
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": "./commands",
            "workspacesHome": "./workspaces",
            "pythonCommand": "python3",
        },
    }
    (cfg / "commands").mkdir(parents=True, exist_ok=True)
    (cfg / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)

    module = _load_module()
    assert module.BINDING_OK is False


@pytest.mark.governance
def test_resolve_repo_root_returns_none_without_verified_git_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    nested = repo_root / "src" / "feature"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_module()
    assert module.resolve_repo_root() is None


@pytest.mark.governance
def test_resolve_repo_context_reports_env_discovery_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(repo_root))
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)

    module = _load_module()
    monkeypatch.setattr(
        module,
        "decide_start_persistence",
        lambda **kwargs: {
            "repo_root": repo_root.resolve(),
            "discovery_method": "env:GITHUB_WORKSPACE:git-rev-parse",
            "repo_fingerprint": "abc123",
            "workspace_ready": True,
        },
    )
    resolved_root, method = module.resolve_repo_context()
    assert resolved_root == repo_root.resolve()
    assert method == "env:GITHUB_WORKSPACE:git-rev-parse"


@pytest.mark.governance
def test_resolve_repo_context_returns_none_when_cwd_is_not_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    non_repo = tmp_path / "backup"
    non_repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(non_repo)
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_module()
    monkeypatch.setattr(
        module,
        "decide_start_persistence",
        lambda **kwargs: {
            "repo_root": None,
            "discovery_method": "cwd",
            "repo_fingerprint": "",
            "workspace_ready": False,
        },
    )
    resolved_root, method = module.resolve_repo_context()

    assert resolved_root is None
    assert method == "cwd"


@pytest.mark.governance
def test_bootstrap_identity_uses_derived_fingerprint_from_nested_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    nested = repo_root / "src" / "feature"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(repo_root))
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_module()
    helper = tmp_path / "bootstrap_session_state.py"
    helper.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setattr(module, "BOOTSTRAP_HELPER", helper)
    monkeypatch.setattr(module, "WORKSPACES_HOME", tmp_path / "workspaces")
    monkeypatch.setattr(module, "COMMANDS_RUNTIME_DIR", tmp_path / "commands")
    monkeypatch.setattr(module, "BINDING_EVIDENCE_PATH", tmp_path / "commands" / "governance.paths.json")
    monkeypatch.setattr(module.shutil, "which", lambda cmd: "/usr/bin/git" if cmd == "git" else None)
    monkeypatch.setattr(
        module,
        "decide_start_persistence",
        lambda **kwargs: {
            "repo_root": repo_root.resolve(),
            "repo_fingerprint": "abc123",
            "discovery_method": "env:OPENCODE_REPO_ROOT:git-rev-parse",
            "workspace_ready": True,
        },
    )

    assert module.bootstrap_identity_if_needed() is True
    assert capsys.readouterr().out.strip() == ""
    assert not (tmp_path / "workspaces").exists()


@pytest.mark.governance
def test_bootstrap_identity_does_not_use_repo_context_index_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    non_repo = tmp_path / "outside"
    non_repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(non_repo)
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_module()
    monkeypatch.setattr(module, "WORKSPACES_HOME", tmp_path / "workspaces")
    monkeypatch.setattr(module, "COMMANDS_RUNTIME_DIR", tmp_path / "commands")
    monkeypatch.setattr(module, "BINDING_EVIDENCE_PATH", tmp_path / "commands" / "governance.paths.json")
    monkeypatch.setattr(module, "resolve_repo_context", lambda: (non_repo.resolve(), "cwd"))
    monkeypatch.setattr(module, "derive_repo_fingerprint", lambda _repo_root: None)
    monkeypatch.setattr(module, "pointer_fingerprint", lambda: None)

    cached_fp = "abcd1234abcd1234abcd1234"
    (tmp_path / "workspaces").mkdir(parents=True, exist_ok=True)
    module._repo_context_index_path(non_repo).parent.mkdir(parents=True, exist_ok=True)
    module._repo_context_index_path(non_repo).write_text(
        json.dumps(
            {
                "schema": "repo-context.v1",
                "repo_root": module._normalize_path_for_fingerprint(non_repo),
                "repo_fingerprint": cached_fp,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "identity_map_exists", lambda repo_fp: repo_fp == cached_fp)

    assert module.bootstrap_identity_if_needed() is False


@pytest.mark.governance
def test_bootstrap_command_argv_splits_python_launcher(monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    monkeypatch.setattr(module, "PYTHON_COMMAND", "py -3")
    monkeypatch.setattr(module, "BOOTSTRAP_HELPER", Path("C:/tmp/bootstrap.py"))

    argv = module.bootstrap_command_argv("abc123")
    assert argv[:2] == ["py", "-3"]
    assert "--repo-fingerprint" in argv


@pytest.mark.governance
def test_bootstrap_identity_skips_workspace_writes_when_fingerprint_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(non_repo)
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_module()
    monkeypatch.setattr(module, "WORKSPACES_HOME", tmp_path / "workspaces")
    monkeypatch.setattr(module, "COMMANDS_RUNTIME_DIR", tmp_path / "commands")
    monkeypatch.setattr(module, "BINDING_EVIDENCE_PATH", tmp_path / "commands" / "governance.paths.json")
    monkeypatch.setattr(module, "pointer_fingerprint", lambda: None)

    assert module.bootstrap_identity_if_needed() is False
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason"] == "identity-bootstrap-fingerprint-missing"
    assert not (tmp_path / "workspaces" / "_unresolved").exists()
    assert not module._repo_context_index_path(non_repo).exists()


@pytest.mark.governance
def test_windows_like_backup_cwd_never_creates_workspace_or_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    backup = tmp_path / "opencode_backup"
    backup.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(backup)
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_module()
    monkeypatch.setattr(module, "WORKSPACES_HOME", tmp_path / "workspaces")
    monkeypatch.setattr(module, "COMMANDS_RUNTIME_DIR", tmp_path / "commands")
    monkeypatch.setattr(module, "BINDING_EVIDENCE_PATH", tmp_path / "commands" / "governance.paths.json")

    assert module.bootstrap_identity_if_needed() is False
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason_code"] == "BLOCKED-REPO-IDENTITY-RESOLUTION"
    assert not any((tmp_path / "workspaces").rglob("*"))


@pytest.mark.governance
def test_bootstrap_identity_uses_python_command_argv_for_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo_root)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(repo_root))
    monkeypatch.delenv("OPENCODE_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("REPO_ROOT", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    module = _load_module()
    helper = tmp_path / "bootstrap_session_state.py"
    helper.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setattr(module, "BOOTSTRAP_HELPER", helper)
    monkeypatch.setattr(module, "PYTHON_COMMAND", "py -3")
    monkeypatch.setattr(module, "WORKSPACES_HOME", tmp_path / "workspaces")
    monkeypatch.setattr(module, "COMMANDS_RUNTIME_DIR", tmp_path / "commands")
    monkeypatch.setattr(module, "BINDING_EVIDENCE_PATH", tmp_path / "commands" / "governance.paths.json")
    monkeypatch.setattr(module.shutil, "which", lambda cmd: "/usr/bin/git" if cmd == "git" else None)
    monkeypatch.setattr(
        module,
        "decide_start_persistence",
        lambda **kwargs: {
            "repo_root": repo_root.resolve(),
            "repo_fingerprint": "abc123",
            "discovery_method": "env:OPENCODE_REPO_ROOT:git-rev-parse",
            "workspace_ready": True,
        },
    )

    assert module.bootstrap_identity_if_needed() is True
    assert not (tmp_path / "workspaces").exists()
@pytest.mark.governance
def test_command_available_accepts_py_launcher(monkeypatch: pytest.MonkeyPatch):
    module = _load_module()

    def fake_which(cmd: str):
        if cmd == "py":
            return "C:/Windows/py.exe"
        return None

    monkeypatch.setattr(module.shutil, "which", fake_which)
    assert module._command_available("py -3") is True
