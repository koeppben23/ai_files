from __future__ import annotations

import json
from pathlib import Path

from governance.application.use_cases.bootstrap_persistence import (
    ACTIVATION_INTENT_FILE,
    BootstrapInput,
    BootstrapPersistenceService,
)
from governance.domain.models.binding import Binding
from governance.domain.models.layouts import WorkspaceLayout
from governance.domain.models.repo_identity import RepoIdentity
from governance.infrastructure.adapters.filesystem.in_memory import InMemoryFS


class DummyRunner:
    class _Result:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    def run(self, argv, env=None):
        _ = argv, env
        return DummyRunner._Result()


class DummyLogger:
    def __init__(self) -> None:
        self.events: list[object] = []

    def write(self, event):
        self.events.append(event)


def _payload(*, mode: str) -> BootstrapInput:
    return BootstrapInput(
        repo_identity=RepoIdentity(
            repo_root="/tmp/repo",
            fingerprint="abcdef0123456789abcdef01",
            repo_name="repo",
            source="test",
        ),
        binding=Binding(
            config_root="/tmp/config",
            commands_home="/tmp/config/commands",
            workspaces_home="/tmp/config/workspaces",
            python_command="python3",
        ),
        layout=WorkspaceLayout(
            repo_home="/tmp/config/workspaces/abcdef0123456789abcdef01",
            session_state_file="/tmp/config/workspaces/abcdef0123456789abcdef01/SESSION_STATE.json",
            identity_map_file="/tmp/config/workspaces/abcdef0123456789abcdef01/repo-identity-map.yaml",
            pointer_file="/tmp/config/SESSION_STATE.json",
        ),
        required_artifacts=(),
        effective_mode=mode,
        write_policy_reasons=(),
        no_commit=True,
    )


def test_bootstrap_creates_default_activation_intent_in_user_mode():
    fs = InMemoryFS()
    logger = DummyLogger()
    service = BootstrapPersistenceService(fs=fs, runner=DummyRunner(), logger=logger)

    result = service.run(_payload(mode="user"))

    assert result.ok is True
    assert result.write_actions.get("activation_intent") == "created-default"
    path = f"/tmp/config/{ACTIVATION_INTENT_FILE}"
    assert fs.exists(Path(path)) is True
    payload = json.loads(fs.read_text(Path(path)))
    assert payload.get("schema") == "opencode-activation-intent.v1"


def test_bootstrap_blocks_without_activation_intent_outside_user_mode():
    fs = InMemoryFS()
    logger = DummyLogger()
    service = BootstrapPersistenceService(fs=fs, runner=DummyRunner(), logger=logger)

    result = service.run(_payload(mode="pipeline"))

    assert result.ok is False
    assert result.gate_code == "ACTIVATION_INTENT_REQUIRED"
