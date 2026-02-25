from __future__ import annotations

from pathlib import Path
import json

from governance.kernel.phase_kernel import RuntimeContext, execute


def _write_phase_api(commands_home: Path) -> None:
    repo_spec = Path(__file__).resolve().parents[1] / "phase_api.yaml"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(repo_spec.read_text(encoding="utf-8"), encoding="utf-8")


def test_phase_api_start_token_is_bootstrap_entrypoint() -> None:
    repo_spec = Path(__file__).resolve().parents[1] / "phase_api.yaml"
    text = repo_spec.read_text(encoding="utf-8")
    assert 'start_token: "0"' in text


def test_kernel_blocks_when_phase_api_missing(tmp_path: Path) -> None:
    result = execute(
        current_token="2.1",
        session_state_doc={"SESSION_STATE": {}},
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=tmp_path / "commands",
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "phase-api-missing"


def test_kernel_routes_2_1_to_1_5_when_business_rules_unresolved(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/master.md"},
            "AddonsEvidence": {},
        }
    }
    result = execute(
        current_token="2.1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "1.5-BusinessRules"
    assert result.source == "phase-1.5-routing-required"


def test_kernel_routes_2_1_to_1_5_when_business_rules_execute_decision_set(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/master.md"},
            "AddonsEvidence": {},
            "BusinessRules": {"Decision": "execute"},
        }
    }
    result = execute(
        current_token="2.1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Decision Pack",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.phase == "1.5-BusinessRules"
    assert result.source == "phase-1.5-routing-required"


def test_kernel_blocks_phase_1_3_when_exit_evidence_missing(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "Phase": "1.3-RulebookLoad",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {},
            "AddonsEvidence": {},
        }
    }
    result = execute(
        current_token="1.3",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Rulebook Load Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    assert result.source == "phase-exit-evidence-missing"


def test_kernel_blocks_with_invalid_spec_and_writes_block_event(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(
        """
version: 1
start_token: "1.1"
phases:
  - token: "1.1"
    phase: "1.1-Bootstrap"
    active_gate: "Workspace Ready Gate"
    next_gate_condition: "Continue"
    next: "unknown"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = execute(
        current_token="1.1",
        session_state_doc={"SESSION_STATE": {}},
        runtime_ctx=RuntimeContext(
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "BLOCKED"
    rows = [
        json.loads(line)
        for line in (commands_home / "logs" / "flow.log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["event"] == "PHASE_BLOCKED"
