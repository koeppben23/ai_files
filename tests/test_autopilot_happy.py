from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

from governance.application.use_cases.session_state_helpers import with_kernel_result
from governance.kernel.phase_kernel import RuntimeContext, execute
from tests.util import get_phase_api_path


def _seed_binding(tmp_path: Path, monkeypatch) -> tuple[Path, str]:
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    commands_home = cfg / "commands"
    workspaces_home = cfg / "workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "pythonCommand": sys.executable,
        },
    }
    (commands_home / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    (commands_home / "phase_api.yaml").write_text(get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return workspaces_home, "88b39b036804c534a1b2c3d4"


def test_bootstrap_autopilot_happy_until_phase_2_1(tmp_path: Path, monkeypatch) -> None:
    workspaces_home, fp = _seed_binding(tmp_path, monkeypatch)
    state: dict[str, object] = {
        "SESSION_STATE": {
            "RepoFingerprint": fp,
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${COMMANDS_HOME}/master.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.yml",
                "templates": "${COMMANDS_HOME}/master.md",
                "addons": {
                    "riskTiering": "${COMMANDS_HOME}/rulesets/profiles/rules.risk-tiering.yml",
                },
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/master.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.yml",
            },
            "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
            "Intent": {"Path": "intent.md", "Sha256": "abc", "EffectiveScope": "repo"},
            "RepoDiscovery": {
                "Completed": True,
                "RepoCacheFile": "cache",
                "RepoMapDigestFile": "digest",
            },
            "Scope": {"BusinessRules": "not-applicable"},
        }
    }

    phases = ["1.1", "1", "1.2", "1.3", "2", "2.1"]

    for token in phases:
        current_state = state.get("SESSION_STATE")
        state_ss = dict(current_state) if isinstance(current_state, Mapping) else {}
        state_ss["phase"] = token
        state["SESSION_STATE"] = state_ss
        result = execute(
            current_token=token,
            session_state_doc=state,
            runtime_ctx=RuntimeContext(
                requested_active_gate="gate",
                requested_next_gate_condition="continue",
                repo_is_git_root=True,
                live_repo_fingerprint=fp,
            ),
        )
        if token == "2.1":
            assert result.status == "OK"
        assert "ticket" not in result.next_gate_condition.lower()

    final_result = execute(
        current_token="2.1",
        session_state_doc=state,
        runtime_ctx=RuntimeContext(
            requested_active_gate="gate",
            requested_next_gate_condition="continue",
            repo_is_git_root=True,
            live_repo_fingerprint=fp,
        )
    )
    state = dict(
        with_kernel_result(
            state,
            phase=final_result.phase,
            next_token=final_result.next_token,
            active_gate=final_result.active_gate,
            next_gate_condition=final_result.next_gate_condition,
            status=final_result.status,
            spec_hash=final_result.spec_hash,
            spec_path=final_result.spec_path,
            spec_loaded_at=final_result.spec_loaded_at,
            log_paths=final_result.log_paths,
            event_id=final_result.event_id,
        )
    )

    final_state = state.get("SESSION_STATE")
    assert isinstance(final_state, Mapping)
    kernel_block = final_state.get("Kernel")
    assert isinstance(kernel_block, Mapping)
    assert kernel_block["PhaseApiSha256"]
    assert kernel_block["PhaseApiPath"].endswith("phase_api.yaml")

    events_file = workspaces_home / fp / "events.jsonl"
    rows = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
    started = {row.get("phase_token") for row in rows if row.get("event") == "PHASE_STARTED"}
    completed = {row.get("phase_token") for row in rows if row.get("event") == "PHASE_COMPLETED"}
    assert {"1.1", "1", "1.2", "1.3", "2", "2.1"}.issubset(started)
    assert {"1.1", "1", "1.2", "1.3", "2", "2.1"}.issubset(completed)
