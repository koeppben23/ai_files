from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from governance_runtime.application.use_cases.bootstrap_persistence import (
    ACTIVATION_INTENT_FILE,
    BootstrapInput,
    BootstrapPersistenceService,
)
from governance_runtime.domain.models.binding import Binding
from governance_runtime.domain.models.layouts import WorkspaceLayout
from governance_runtime.domain.models.repo_identity import RepoIdentity
from governance_runtime.infrastructure.adapters.filesystem.in_memory import InMemoryFS


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
            repo_root="/mock/repo",
            fingerprint="abcdef0123456789abcdef01",
            repo_name="repo",
            source="test",
        ),
        binding=Binding(
            config_root="/mock/config",
            commands_home="/mock/config/commands",
            workspaces_home="/mock/config/workspaces",
            python_command="python3",
        ),
        layout=WorkspaceLayout(
            repo_home="/mock/config/workspaces/abcdef0123456789abcdef01",
            session_state_file="/mock/config/workspaces/abcdef0123456789abcdef01/SESSION_STATE.json",
            identity_map_file="/mock/config/workspaces/abcdef0123456789abcdef01/repo-identity-map.yaml",
            pointer_file="/mock/config/SESSION_STATE.json",
        ),
        required_artifacts=(),
        effective_mode=mode,
        write_policy_reasons=(),
        no_commit=True,
    )


def test_bootstrap_creates_default_activation_intent_in_user_mode():
    fs = InMemoryFS()
    logger = DummyLogger()
    service = BootstrapPersistenceService(fs=fs, runner=DummyRunner(), logger=logger)  # type: ignore[arg-type]
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = service.run(_payload(mode="user"), created_at)

    assert result.ok is True
    assert result.write_actions.get("activation_intent") == "created-default"
    path = f"/mock/config/{ACTIVATION_INTENT_FILE}"
    assert fs.exists(Path(path)) is True
    payload = json.loads(fs.read_text(Path(path)))
    assert payload.get("schema") == "opencode-activation-intent.v1"
    assert payload.get("discovery_scope") == "full"


def test_bootstrap_blocks_without_activation_intent_outside_user_mode():
    fs = InMemoryFS()
    logger = DummyLogger()
    service = BootstrapPersistenceService(fs=fs, runner=DummyRunner(), logger=logger)  # type: ignore[arg-type]
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = service.run(_payload(mode="pipeline"), created_at)

    assert result.ok is False
    assert result.gate_code == "ACTIVATION_INTENT_REQUIRED"


def test_bootstrap_rejects_activation_intent_without_discovery_scope():
    fs = InMemoryFS()
    logger = DummyLogger()
    service = BootstrapPersistenceService(fs=fs, runner=DummyRunner(), logger=logger)  # type: ignore[arg-type]

    path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
    fs.write_text_atomic(
        path,
        json.dumps(
            {
                "schema": "opencode-activation-intent.v1",
                "default_scope": "governance-pipeline-only",
                "allowed_actions": {"read_only": True, "write_allowed_in_user_mode": True},
                "default_question_policy": {"no_questions_before_phase4": True, "blocked_when_no_safe_default": True},
                "single_dev_mode": True,
            }
        ),
    )

    result = service.run(_payload(mode="user"), datetime.now(timezone.utc).isoformat(timespec="seconds"))
    assert result.ok is False
    assert result.gate_code == "ACTIVATION_INTENT_INVALID"
