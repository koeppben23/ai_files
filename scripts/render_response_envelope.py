#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from governance_runtime.render.response_formatter import render_response

try:
    from governance_runtime.infrastructure.logging.global_error_handler import emit_gate_failure, resolve_log_path
except Exception:
    def emit_gate_failure(**kwargs: Any) -> bool:  # type: ignore[no-redef]
        return False

    def resolve_log_path(*, config_root=None, commands_home=None, workspaces_home=None, repo_fingerprint=None):  # type: ignore[no-redef]
        base = Path(config_root) if config_root is not None else (Path.home() / ".config" / "opencode")
        if repo_fingerprint and workspaces_home:
            return Path(workspaces_home) / repo_fingerprint / "logs" / "error.log.jsonl"
        if commands_home:
            return Path(commands_home) / "logs" / "error.log.jsonl"
        return base / "logs" / "error.log.jsonl"


def _read_payload(path_arg: str) -> dict[str, Any]:
    if path_arg == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path_arg).read_text(encoding="utf-8")

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("payload root must be a JSON object")
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render governance response envelopes in markdown/plain/json.")
    parser.add_argument(
        "--input",
        default="-",
        help="Path to response envelope JSON (default: stdin '-').",
    )
    parser.add_argument(
        "--format",
        default="auto",
        choices=("auto", "markdown", "plain", "json"),
        help="Output format contract. auto=markdown for interactive TTY, json for non-TTY.",
    )
    parser.add_argument(
        "--output-mode",
        choices=("STRICT", "COMPAT"),
        default=None,
        help="Optional expected envelope mode validation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        payload = _read_payload(args.input)
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON input: {exc}")
        return 1
    except (OSError, ValueError) as exc:
        print(f"FAIL: unable to read payload: {exc}")
        return 1

    if args.output_mode is not None:
        mode = payload.get("mode")
        if mode != args.output_mode:
            print(f"FAIL: output mode mismatch, expected {args.output_mode}, got {mode!r}")
            return 1

    try:
        rendered = render_response(payload, output_format=args.format)
    except ValueError as exc:
        message = str(exc)
        if "invalid phase/next_action contract" in message:
            session_state = payload.get("session_state") if isinstance(payload.get("session_state"), dict) else {}
            repo_fingerprint = ""
            if isinstance(session_state, dict):
                fp = session_state.get("repo_fingerprint") or session_state.get("RepoFingerprint")
                if isinstance(fp, str):
                    repo_fingerprint = fp.strip()
            commands_home = None
            workspaces_home = None
            try:
                from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver

                evidence = BindingEvidenceResolver().resolve(mode="kernel")
                commands_home = evidence.commands_home
                workspaces_home = evidence.workspaces_home
            except Exception:
                pass
            try:
                log_path = resolve_log_path(
                    config_root=None,
                    commands_home=commands_home,
                    workspaces_home=workspaces_home,
                    repo_fingerprint=repo_fingerprint or None,
                )
            except Exception:
                log_path = Path("")
            emit_gate_failure(
                gate="RESPONSE_CONTRACT",
                code="BLOCKED-INVALID-NEXT-ACTION",
                message="Response contract validation rejected next_action for current phase.",
                expected="next_action.type=command before phase 4",
                observed={
                    "error": message,
                    "next_action": payload.get("next_action"),
                    "phase": session_state.get("phase") if isinstance(session_state, dict) else None,
                },
                remediation="Set next_action.type to command for pre-phase4 responses and rerun.",
                repo_fingerprint=repo_fingerprint or None,
                commands_home=commands_home,
                workspaces_home=workspaces_home,
            )
            blocked_payload = {
                "status": "BLOCKED",
                "reason_code": "BLOCKED-INVALID-NEXT-ACTION",
                "missing_evidence": ["phase-aligned next_action contract"],
                "recovery_steps": ["set next_action.type to command before phase 4"],
                "next_command": "render_response_envelope.py --input <payload.json>",
                "log_path": str(log_path),
            }
            sys.stdout.write(json.dumps(blocked_payload, ensure_ascii=True) + "\n")
            return 2
        print(f"FAIL: {exc}")
        return 1

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
