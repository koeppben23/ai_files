"""Generate deterministic golden outputs from real governance intent/engine/render paths."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from governance.engine.adapters import HostCapabilities, OperatingMode
from governance.engine.orchestrator import run_engine_orchestrator
from governance.render import build_two_layer_output, route_intent


@dataclass(frozen=True)
class ScriptAdapter:
    env: dict[str, str]
    cwd_path: Path
    caps: HostCapabilities
    default_mode: OperatingMode = "user"

    def capabilities(self) -> HostCapabilities:
        return self.caps

    def environment(self) -> dict[str, str]:
        return self.env

    def cwd(self) -> Path:
        return self.cwd_path.resolve()

    def default_operating_mode(self) -> OperatingMode:
        return self.default_mode


def _scenario_for_intent(intent: str) -> tuple[str, str, str]:
    if intent == "where_am_i":
        return ("2.1-DecisionPack", "context.where-am-i", "Report deterministic session/repo context")
    if intent == "what_blocks_me":
        return ("3A-Activation", "diagnostics.blockers", "Explain active blockers and recovery")
    if intent == "what_now":
        return ("4-Implement", "operator.next-step", "Return next deterministic operator step")
    return ("3B-Snapshot", "diagnostics.summary", "Return compact deterministic diagnostics summary")


def _normalized_status(parity_status: str) -> str:
    return "BLOCKED" if parity_status == "blocked" else "OK"


def generate_golden_outputs(*, repo_root: Path, output_dir: Path) -> None:
    adapter = ScriptAdapter(
        env={
            "OPENCODE_REPO_ROOT": str(repo_root.resolve()),
            "OPENCODE_DISABLE_GIT": "0",
        },
        cwd_path=repo_root.resolve(),
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    canonical_inputs = {
        "start": "/start",
        "what_blocks_me": "what blocks me",
        "show_diagnostics": "show diagnostics",
        "where_am_i": "where am i",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for key, prompt in canonical_inputs.items():
        intent = route_intent(prompt)
        phase, active_gate, primary_action = _scenario_for_intent(intent)
        orchestrated = run_engine_orchestrator(
            adapter=adapter,
            phase=phase,
            active_gate=active_gate,
            mode="OK",
            next_gate_condition=primary_action,
            requested_operating_mode="user",
        )

        rendered = build_two_layer_output(
            status=_normalized_status(orchestrated.parity["status"]),
            phase_gate=f"{phase}|{active_gate}",
            primary_action=primary_action,
            phase=phase,
            active_gate=active_gate,
            reason_code=orchestrated.parity["reason_code"],
            next_command=orchestrated.parity["next_action.command"],
            details={
                "activation_hash": orchestrated.activation_hash,
                "ruleset_hash": orchestrated.ruleset_hash,
                "effective_operating_mode": orchestrated.effective_operating_mode,
            },
        )

        payload = {
            "schema": "governance-golden-intent-output.v1",
            "input": prompt,
            "intent": intent,
            "parity": orchestrated.parity,
            "engine": {
                "phase": orchestrated.runtime.state.phase,
                "active_gate": orchestrated.runtime.state.active_gate,
                "activation_hash": orchestrated.activation_hash,
                "ruleset_hash": orchestrated.ruleset_hash,
                "next_command": orchestrated.parity["next_action.command"],
            },
            "render": {
                "header": rendered["header"],
                "operator_view": rendered["operator_view"],
                "reason_to_action": rendered["reason_to_action"],
            },
        }
        (output_dir / f"{key}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate governance golden outputs from intent/engine/render contracts.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    generate_golden_outputs(repo_root=repo_root, output_dir=output_dir)
    print(json.dumps({"status": "OK", "output_dir": str(output_dir)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
