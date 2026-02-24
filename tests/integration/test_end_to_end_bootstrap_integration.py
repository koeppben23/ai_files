import json
import sys
from pathlib import Path
import pytest

from governance.application.use_cases.bootstrap_persistence import BootstrapInput
from governance.domain.models.binding import Binding
from governance.domain.models.layouts import WorkspaceLayout
from governance.domain.models.repo_identity import RepoIdentity
from governance.infrastructure.adapters.filesystem.in_memory import InMemoryFS

class DummyRunner:
    class _Result:
        def __init__(self):
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""
    def run(self, argv, env=None):
        return DummyRunner._Result()

class DummyLogger:
    def write(self, event):
        pass


def test_end_to_end_bootstrap_integration(tmp_path):
    fs = InMemoryFS()
    runner = DummyRunner()
    logger = DummyLogger()

    # Setup repo/config/workspace layout in a temp tree
    config_root = tmp_path / "config_root"
    config_root.mkdir()
    commands_home = config_root / "commands"
    commands_home.mkdir()
    workspaces_home = config_root / "workspaces"
    workspaces_home.mkdir()
    repo_root = tmp_path / "repo_root"
    repo_root.mkdir()

    repo_fp = "abcdef0123456789abcdef01"  # 24-char hex
    repo_home = workspaces_home / repo_fp
    repo_home.mkdir(parents=True)
    session_state_file = repo_home / "SESSION_STATE.json"
    identity_map_file = repo_home / "repo-identity-map.yaml"
    repo_cache = repo_home / "repo-cache.yaml"
    repo_map_digest = repo_home / "repo-map-digest.md"
    workspace_memory = repo_home / "workspace-memory.yaml"
    decision_pack = repo_home / "decision-pack.md"
    fs.write_text_atomic(repo_cache, "dummy")
    fs.write_text_atomic(repo_map_digest, "digest")
    fs.write_text_atomic(workspace_memory, "memory")
    fs.write_text_atomic(decision_pack, "pack")

    binding = Binding(
        config_root=str(config_root),
        commands_home=str(commands_home),
        workspaces_home=str(workspaces_home),
        python_command=sys.executable,
    )

    pointer_file = config_root / "pointer.json"
    session_state_file_str = str(session_state_file)

    layout = WorkspaceLayout(
        repo_home=str(repo_home),
        session_state_file=session_state_file_str,
        identity_map_file=str(identity_map_file),
        pointer_file=str(pointer_file),
    )

    repo_identity = RepoIdentity(repo_root=str(repo_root), fingerprint=repo_fp, repo_name="test-repo", source="integration")

    payload = BootstrapInput(
        repo_identity=repo_identity,
        binding=binding,
        layout=layout,
        required_artifacts=(str(repo_cache), str(repo_map_digest), str(workspace_memory), str(decision_pack)),
        force_read_only=False,
        skip_artifact_backfill=False,
        effective_mode="user",
        write_policy_reasons=(),
        no_commit=False,
    )

    from governance.application.use_cases.bootstrap_persistence import BootstrapPersistenceService
    service = BootstrapPersistenceService(fs=fs, runner=DummyRunner(), logger=logger)
    result = service.run(payload)
    assert result.ok

    final_state = fs.read_text(session_state_file)
    data = json.loads(final_state)
    st = data.get("SESSION_STATE", {})
    assert st.get("Phase") == "1.2-ActivationIntent"
    assert st.get("Next") == "P2-RepoDiscovery-ready"
    assert st.get("Bootstrap", {}).get("Present") is True
    assert st.get("Bootstrap", {}).get("Satisfied") is True

    # Pointer content
    pointer_text = fs.read_text(pointer_file)
    pointer = json.loads(pointer_text)
    assert pointer.get("schema") == "opencode-session-pointer.v1"
    assert pointer.get("activeRepoFingerprint") == repo_fp
