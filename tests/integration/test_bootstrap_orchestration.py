from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from governance_runtime.application.ports.process_runner import ProcessResult
from governance_runtime.application.ports.process_runner import ProcessRunnerPort
from governance_runtime.application.use_cases.bootstrap_persistence import (
    BootstrapInput,
    BootstrapPersistenceService,
)
from governance_runtime.domain.errors.events import ErrorEvent
from governance_runtime.domain.models.binding import Binding
from governance_runtime.domain.models.layouts import WorkspaceLayout
from governance_runtime.domain.models.repo_identity import RepoIdentity
from governance_runtime.infrastructure.adapters.filesystem.in_memory import InMemoryFS


class _FakeRunner(ProcessRunnerPort):
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def run(self, argv: list[str], env: dict[str, str] | None = None) -> ProcessResult:
        _ = (argv, env)
        return ProcessResult(returncode=self.returncode, stdout="{}", stderr="")


class _BackfillMutatingRunner(ProcessRunnerPort):
    def __init__(self, fs: InMemoryFS, session_state_file: str) -> None:
        self._fs = fs
        self._session_state_file = Path(session_state_file)

    def run(self, argv: list[str], env: dict[str, str] | None = None) -> ProcessResult:
        _ = (argv, env)
        payload = json.loads(self._fs.read_text(self._session_state_file))
        session = payload["SESSION_STATE"]
        session["Phase"] = "4"
        session["Next"] = "4"
        session["ticket_intake_ready"] = True
        session["BusinessRules"] = {
            "Decision": "skip",
            "Inventory": {"sha256": "abc123", "count": 2},
            "Rules": ["rule-one", "rule-two"],
        }
        self._fs.write_text_atomic(self._session_state_file, json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
        return ProcessResult(returncode=0, stdout="{}", stderr="")


class _FakeLogger:
    def __init__(self) -> None:
        self.events: list[ErrorEvent] = []

    def write(self, event: ErrorEvent) -> None:
        self.events.append(event)


class _TamperedInMemoryFS(InMemoryFS):
    def read_text(self, path: Path) -> str:
        value = super().read_text(path)
        if path.as_posix() == "/cfg/SESSION_STATE.json":
            return value + "tampered"
        return value


    def write_text_atomic(self, path: Path, content: str) -> None:
        if path.as_posix() == "/cfg/SESSION_STATE.json":
            content = content + "tampered"
        super().write_text_atomic(path, content)

    def exists(self, path: Path) -> bool:
        if path.as_posix() == "/cfg/SESSION_STATE.json":
            return True
        return super().exists(path)


def _payload() -> BootstrapInput:
    return BootstrapInput(
        repo_identity=RepoIdentity(
            repo_root="/repo",
            fingerprint="aaaaaaaaaaaaaaaaaaaaaaaa",
            repo_name="repo",
            source="test",
        ),
        binding=Binding(
            config_root="/cfg",
            commands_home="/cfg/commands",
            workspaces_home="/cfg/workspaces",
            python_command="python3",
        ),
        layout=WorkspaceLayout(
            repo_home="/cfg/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa",
            session_state_file="/cfg/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/SESSION_STATE.json",
            identity_map_file="/cfg/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/repo-identity-map.yaml",
            pointer_file="/cfg/SESSION_STATE.json",
        ),
        required_artifacts=(
            "/cfg/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/repo-cache.yaml",
            "/cfg/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/repo-map-digest.md",
            "/cfg/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/workspace-memory.yaml",
            "/cfg/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/decision-pack.md",
        ),
    )


def _payload_inside_repo() -> BootstrapInput:
    return BootstrapInput(
        repo_identity=RepoIdentity(
            repo_root="/repo",
            fingerprint="aaaaaaaaaaaaaaaaaaaaaaaa",
            repo_name="repo",
            source="test",
        ),
        binding=Binding(
            config_root="/repo/.config/opencode",
            commands_home="/repo/.config/opencode/commands",
            workspaces_home="/repo/.config/opencode/workspaces",
            python_command="python3",
        ),
        layout=WorkspaceLayout(
            repo_home="/repo/.config/opencode/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa",
            session_state_file="/repo/.config/opencode/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/SESSION_STATE.json",
            identity_map_file="/repo/.config/opencode/workspaces/aaaaaaaaaaaaaaaaaaaaaaaa/repo-identity-map.yaml",
            pointer_file="/repo/.config/opencode/SESSION_STATE.json",
        ),
        required_artifacts=(),
    )


def test_bootstrap_commits_only_after_all_checks() -> None:
    fs = InMemoryFS()
    for artifact in _payload().required_artifacts:
        fs.write_text_atomic(Path(artifact), "ok")
    logger = _FakeLogger()
    service = BootstrapPersistenceService(fs=fs, runner=_FakeRunner(returncode=0), logger=logger)

    result = service.run(_payload(), datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert result.ok is True
    assert result.gate_code == "OK"
    assert result.write_actions.get("session_state_final") == "written"


def test_bootstrap_preserves_backfill_business_rules_and_resets_phase_entrypoint() -> None:
    payload = _payload()
    fs = InMemoryFS()
    for artifact in payload.required_artifacts:
        fs.write_text_atomic(Path(artifact), "ok")
    logger = _FakeLogger()
    service = BootstrapPersistenceService(
        fs=fs,
        runner=_BackfillMutatingRunner(fs, payload.layout.session_state_file),
        logger=logger,
    )

    result = service.run(payload, datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert result.ok is True
    state = json.loads(fs.read_text(Path(payload.layout.session_state_file)))
    session = state["SESSION_STATE"]
    phase_val = session.get("phase") or session.get("Phase") or ""
    assert phase_val in ("1.2-ActivationIntent", "4")
    business = session.get("BusinessRules", {})
    assert business.get("Inventory", {}).get("sha256") == "abc123"
    assert business.get("Rules") == ["rule-one", "rule-two"]
    commit_flags = session.get("CommitFlags", {})
    assert commit_flags.get("PointerVerified") is True


def test_bootstrap_merge_falls_back_when_session_state_is_invalid_json() -> None:
    payload = _payload()
    fs = InMemoryFS()
    for artifact in payload.required_artifacts:
        fs.write_text_atomic(Path(artifact), "ok")
    logger = _FakeLogger()
    service = BootstrapPersistenceService(fs=fs, runner=_FakeRunner(returncode=0), logger=logger)
    # Corrupt initial session to trigger fallback path.
    fs.write_text_atomic(Path(payload.layout.session_state_file), "{not-json\n")

    result = service.run(payload, datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert result.ok is True
    state = json.loads(fs.read_text(Path(payload.layout.session_state_file)))
    assert state["SESSION_STATE"].get("PersistenceCommitted") is True


def test_bootstrap_fails_closed_when_required_artifacts_missing() -> None:
    fs = InMemoryFS()
    logger = _FakeLogger()
    service = BootstrapPersistenceService(fs=fs, runner=_FakeRunner(returncode=0), logger=logger)

    result = service.run(_payload(), datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert result.ok is False
    assert result.gate_code == "PHASE2_ARTIFACTS_MISSING"
    assert logger.events[-1].code == "PHASE2_ARTIFACTS_MISSING"


def test_bootstrap_fails_closed_on_pointer_verify_mismatch() -> None:
    fs = _TamperedInMemoryFS()
    for artifact in _payload().required_artifacts:
        fs.write_text_atomic(Path(artifact), "ok")
    logger = _FakeLogger()
    service = BootstrapPersistenceService(fs=fs, runner=_FakeRunner(returncode=0), logger=logger)

    result = service.run(_payload(), datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert result.ok is False
    assert result.gate_code == "POINTER_VERIFY_FAILED"


def test_bootstrap_blocks_when_config_root_is_inside_repo_root() -> None:
    fs = InMemoryFS()
    logger = _FakeLogger()
    service = BootstrapPersistenceService(fs=fs, runner=_FakeRunner(returncode=0), logger=logger)

    result = service.run(_payload_inside_repo(), datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert result.ok is False
    assert result.gate_code == "CONFIG_ROOT_INSIDE_REPO"


def test_bootstrap_blocks_when_pointer_is_inside_repo_root() -> None:
    fs = InMemoryFS()
    logger = _FakeLogger()
    service = BootstrapPersistenceService(fs=fs, runner=_FakeRunner(returncode=0), logger=logger)

    bad = _payload()
    bad = BootstrapInput(
        repo_identity=bad.repo_identity,
        binding=bad.binding,
        layout=WorkspaceLayout(
            repo_home=bad.layout.repo_home,
            session_state_file=bad.layout.session_state_file,
            identity_map_file=bad.layout.identity_map_file,
            pointer_file="/repo/SESSION_STATE.json",
        ),
        required_artifacts=bad.required_artifacts,
    )
    result = service.run(bad, datetime.now(timezone.utc).isoformat(timespec="seconds"))

    assert result.ok is False
    assert result.gate_code == "POINTER_PATH_INSIDE_REPO"
