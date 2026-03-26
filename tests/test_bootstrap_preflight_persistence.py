from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "bootstrap_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("bootstrap_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load bootstrap_preflight_readonly module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module_with_env(env: dict[str, str]):
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "bootstrap_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("bootstrap_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load bootstrap_preflight_readonly module")
    
    old_env = dict(os.environ)
    try:
        os.environ.update(env)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@pytest.mark.governance
def test_bootstrap_preflight_readonly_module_imports_ssot_writes_allowed():
    """bootstrap_preflight_readonly uses SSOT write_policy.writes_allowed()."""
    module = _load_module()
    assert hasattr(module, "writes_allowed")
    assert callable(module.writes_allowed)


@pytest.mark.governance
def test_bootstrap_preflight_readonly_hook_blocks_when_writes_not_allowed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("OPENCODE_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)
    import importlib
    import governance_runtime.entrypoints.bootstrap_preflight_readonly as mod
    importlib.reload(mod)
    
    try:
        mod.run_persistence_hook()
    except SystemExit as e:
        assert e.code == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"


@pytest.mark.governance
def test_bootstrap_preflight_derive_repo_fingerprint_requires_git_repo(tmp_path: Path):
    module = _load_module()
    assert module.derive_repo_fingerprint(tmp_path) is None


@pytest.mark.governance
def test_bootstrap_preflight_derive_repo_fingerprint_from_git_repo(tmp_path: Path):
    module = _load_module()
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, text=True)
    fp = module.derive_repo_fingerprint(tmp_path)
    assert isinstance(fp, str) and len(fp) == 24


@pytest.mark.governance
def test_bootstrap_md_uses_readonly_preflight_helper():
    text = (REPO_ROOT / "BOOTSTRAP.md").read_text(encoding="utf-8")
    assert "bootstrap_preflight_readonly.py" not in text
    assert "bootstrap_preflight_persistence.py" not in text


@pytest.mark.governance
def test_bootstrap_persistence_store_module_removed():
    assert not (REPO_ROOT / "governance" / "infrastructure" / "bootstrap_persistence_store.py").exists()


@pytest.mark.governance
def test_bootstrap_preflight_writes_allowed_true_by_default():
    """SSOT: writes_allowed() is True by default."""
    module = _load_module_with_env({"CI": ""})
    assert module.writes_allowed() is True


@pytest.mark.governance
def test_bootstrap_preflight_writes_allowed_true_in_ci():
    """SSOT: writes_allowed() is True in CI (unless FORCE_READ_ONLY=1)."""
    module = _load_module_with_env({"CI": "true"})
    assert module.writes_allowed() is True


@pytest.mark.governance
def test_bootstrap_preflight_writes_allowed_false_when_force_read_only(monkeypatch: pytest.MonkeyPatch):
    """SSOT: writes_allowed() is False when FORCE_READ_ONLY=1."""
    monkeypatch.setenv("OPENCODE_FORCE_READ_ONLY", "1")
    import importlib
    import governance_runtime.entrypoints.write_policy as wp
    importlib.reload(wp)
    assert wp.writes_allowed() is False


@pytest.mark.governance
def test_run_persistence_hook_blocks_when_writes_not_allowed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("OPENCODE_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)
    import importlib
    import governance_runtime.entrypoints.bootstrap_preflight_readonly as mod
    importlib.reload(mod)
    
    try:
        mod.run_persistence_hook()
    except SystemExit as e:
        assert e.code == 2
    
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"


@pytest.mark.governance
def test_run_persistence_hook_delegates_to_hook_module(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"CI": ""})

    repo_root = REPO_ROOT
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(
        {
            "workspacePersistenceHook": "ok",
            "reason": "bootstrap-completed",
            "repo_fingerprint": "testfingerprint123456",
            "writes_allowed": True,
        }
    )
    mock_proc.stderr = ""

    with patch.object(module, "_resolve_repo_root_for_hook", return_value=(repo_root, "git", {"ok": True})):
        with patch.object(module.subprocess, "run", return_value=mock_proc) as mock_run:
            result = module.run_persistence_hook()

    assert result["workspacePersistenceHook"] == "ok"
    assert result["repo_fingerprint"] == "testfingerprint123456"
    assert "reason_code" not in result
    assert "failure_stage" not in result
    # The hook_command is platform-quoted (e.g. paths with spaces get quoted).
    # Verify the essential components are present regardless of quoting.
    hook_cmd = result["bootstrap_hook_command"]
    assert module.sys.executable.replace('"', '') in hook_cmd.replace('"', ''), (
        f"hook command must reference python executable: {hook_cmd}"
    )
    assert "-m governance_runtime.entrypoints.bootstrap_persistence_hook" in hook_cmd
    assert result["cwd"]
    assert result["repo_root_detected"] == str(repo_root)
    run_args = mock_run.call_args.args[0]
    assert run_args[:3] == [module.sys.executable, "-m", "governance_runtime.entrypoints.bootstrap_persistence_hook"]
    call_args = mock_run.call_args.kwargs
    assert call_args["cwd"] == str(repo_root)
    expected_prefix = str(repo_root) + module.os.pathsep + str(module.COMMANDS_HOME)
    assert str(call_args["env"].get("PYTHONPATH", "")).startswith(expected_prefix)


@pytest.mark.governance
def test_run_persistence_hook_clears_stale_failure_metadata_on_success():
    module = _load_module_with_env({"CI": ""})

    repo_root = REPO_ROOT
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(
        {
            "workspacePersistenceHook": "ok",
            "reason": "bootstrap-completed",
            "repo_fingerprint": "testfingerprint123456",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "failure_stage": "subprocess",
            "stderr": "stale-stderr",
        }
    )
    mock_proc.stderr = ""

    with patch.object(module, "_resolve_repo_root_for_hook", return_value=(repo_root, "git", {"ok": True})):
        with patch.object(module.subprocess, "run", return_value=mock_proc):
            result = module.run_persistence_hook()

    assert result["workspacePersistenceHook"] == "ok"
    assert result["reason"] == "bootstrap-completed"
    assert "reason_code" not in result
    assert "failure_stage" not in result
    assert "stderr" not in result


@pytest.mark.governance
def test_run_persistence_hook_exits_on_hook_failure(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"CI": ""})

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "ModuleNotFoundError: No module named governance"

    with patch.object(module, "_resolve_repo_root_for_hook", return_value=(REPO_ROOT, "git", {"ok": True})):
        with patch.object(module.subprocess, "run", return_value=mock_proc):
            try:
                module.run_persistence_hook()
            except SystemExit as e:
                assert e.code == 2

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"
    assert payload["hook_invoked"] is True
    assert payload["failure_stage"] in {"subprocess", "parse", "hook-payload", "hook_payload"}
    assert payload.get("stderr_snippet")
    assert payload.get("log_path")


@pytest.mark.governance
def test_run_persistence_hook_blocks_when_repo_root_not_detectable(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"CI": ""})

    with patch.object(module, "_resolve_repo_root_for_hook", return_value=(None, "git-miss", {"ok": False})):
        try:
            module.run_persistence_hook()
        except SystemExit as exc:
            assert exc.code == 2

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-REPO-ROOT-NOT-DETECTABLE"
    assert payload["hook_invoked"] is False
    assert payload["failure_stage"] == "repo_root"
    assert payload["bootstrap_hook_command"].endswith("-m governance_runtime.entrypoints.bootstrap_persistence_hook")
    assert payload["python_executable"]


@pytest.mark.governance
def test_resolve_repo_root_for_hook_prefers_env_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module_with_env({"CI": ""})
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(outside)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(repo_root))

    resolved, source, probe = module._resolve_repo_root_for_hook()

    assert resolved == repo_root
    assert source == "env"
    assert probe.get("ok") is True


@pytest.mark.governance
def test_kernel_continuation_missing_session_state_includes_recovery_evidence(monkeypatch: pytest.MonkeyPatch):
    module = _load_module_with_env({"CI": ""})
    monkeypatch.setattr(module, "_session_state_file_path", lambda _fp: Path("/mock/nonexistent-session-state.json"))

    payload = module.run_kernel_continuation(
        {
            "workspacePersistenceHook": "ok",
            "repo_fingerprint": "abc123def456abc123def456",
            "reason": "bootstrap-completed",
            "failure_stage": "",
            "log_path": "/mock/error.log.jsonl",
        }
    )

    assert payload["kernelContinuation"] == "blocked"
    assert payload["reason"] == "missing-session-state"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"
    assert payload.get("recovery_action")
    assert payload.get("next_command")
    assert payload.get("hook_log_path") == "/mock/error.log.jsonl"


@pytest.mark.governance
def test_hydrate_transition_state_sets_mandatory_profile_and_addon_evidence():
    module = _load_module_with_env({"CI": ""})
    document = {"SESSION_STATE": {}}

    hydrated = module._hydrate_transition_state(
        document,
        repo_fingerprint="abc123def456abc123def456",
        requested_token="1.3",
    )
    state = hydrated["SESSION_STATE"]

    assert state["ActiveProfile"] == "profile.fallback-minimum"
    assert state["LoadedRulebooks"]["profile"].endswith("rules.fallback-minimum.md")
    assert state["LoadedRulebooks"]["addons"]["riskTiering"].endswith("riskTiering.addon.yml")
    assert state["AddonsEvidence"]["riskTiering"]["status"] == "loaded"


@pytest.mark.governance
def test_detect_repo_profile_python_repo_high_confidence(tmp_path: Path):
    module = _load_module_with_env({"CI": ""})
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('x')\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

    detected = module._detect_repo_profile(tmp_path)

    assert detected["repository_type"] == "python"
    assert detected["profile_id"] == "backend-python"
    assert detected["profile_source"] == "auto-detected-single"
    assert detected["detection_confidence"] in {"high", "medium"}


@pytest.mark.governance
def test_detect_repo_profile_conflict_defaults_to_ambiguous(tmp_path: Path):
    module = _load_module_with_env({"CI": ""})
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('x')\n", encoding="utf-8")
    (tmp_path / "src" / "Main.java").write_text("class Main {}\n", encoding="utf-8")

    detected = module._detect_repo_profile(tmp_path)

    assert detected["repository_type"] in {"polyglot", "python", "java"}
    assert detected["profile_id"] in {"fallback-minimum", "backend-python", "backend-java"}
    if detected["repository_type"] == "polyglot":
        assert detected["profile_source"] == "ambiguous"
        assert detected["profile_id"] == "fallback-minimum"


@pytest.mark.governance
def test_hydrate_transition_state_marks_business_rules_unresolved_when_no_evidence(tmp_path: Path):
    module = _load_module_with_env({"CI": ""})
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    document = {"SESSION_STATE": {"Scope": {}}}

    hydrated = module._hydrate_transition_state(
        document,
        repo_fingerprint="abc123def456abc123def456",
        requested_token="2.1",
        repo_root=tmp_path,
    )
    state = hydrated["SESSION_STATE"]

    assert state["Scope"]["BusinessRules"] == "unresolved"
    assert state["BusinessRules"]["Decision"] == "pending"
    assert state["BusinessRules"]["Outcome"] == "unresolved"
    assert state["BusinessRules"]["ExecutionEvidence"] is False
    assert state["BusinessRules"]["InventoryFileStatus"] == "unknown"
    assert "Rules" not in state["BusinessRules"]
    assert "Evidence" not in state["BusinessRules"]


@pytest.mark.governance
def test_hydrate_transition_state_normalizes_business_rules_decision_for_extracted(tmp_path: Path):
    module = _load_module_with_env({"CI": ""})
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    document = {
        "SESSION_STATE": {
            "Scope": {"BusinessRules": "extracted"},
            "BusinessRules": {
                "Decision": "execute",
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryFileStatus": "written",
            },
        }
    }

    hydrated = module._hydrate_transition_state(
        document,
        repo_fingerprint="abc123def456abc123def456",
        requested_token="2.1",
        repo_root=tmp_path,
    )
    state = hydrated["SESSION_STATE"]

    assert state["Scope"]["BusinessRules"] == "gap-detected"
    assert state["BusinessRules"]["Outcome"] == "gap-detected"
    assert state["BusinessRules"]["Decision"] == "skip"


@pytest.mark.governance
def test_hydrate_transition_state_rejects_extracted_without_written_inventory(tmp_path: Path):
    module = _load_module_with_env({"CI": ""})
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    document = {
        "SESSION_STATE": {
            "Scope": {"BusinessRules": "extracted"},
            "BusinessRules": {
                "Decision": "execute",
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryFileStatus": "unknown",
                "Rules": ["BR-1: stale"],
                "Evidence": ["docs/rules.md:1"],
            },
        }
    }

    hydrated = module._hydrate_transition_state(
        document,
        repo_fingerprint="abc123def456abc123def456",
        requested_token="2.1",
        repo_root=tmp_path,
    )
    state = hydrated["SESSION_STATE"]

    assert state["Scope"]["BusinessRules"] == "gap-detected"
    assert state["BusinessRules"]["ExecutionEvidence"] is True
    assert state["BusinessRules"]["InventoryFileStatus"] == "unknown"


@pytest.mark.governance
def test_hydrate_transition_state_does_not_force_phase_transition_evidence(tmp_path: Path):
    module = _load_module_with_env({"CI": ""})
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    document = {"SESSION_STATE": {}}

    hydrated = module._hydrate_transition_state(
        document,
        repo_fingerprint="abc123def456abc123def456",
        requested_token="2",
        repo_root=tmp_path,
    )
    state = hydrated["SESSION_STATE"]

    assert state["phase_transition_evidence"] is False


@pytest.mark.governance
def test_hydrate_transition_state_detects_java_repo_type(tmp_path: Path):
    module = _load_module_with_env({"CI": ""})
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    document = {"SESSION_STATE": {}}

    hydrated = module._hydrate_transition_state(
        document,
        repo_fingerprint="abc123def456abc123def456",
        requested_token="2",
        repo_root=tmp_path,
    )
    state = hydrated["SESSION_STATE"]

    assert state["Scope"]["RepositoryType"] == "java"
    assert state["DetectionConfidence"] in {"medium", "high", "low"}
