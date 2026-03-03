#!/usr/bin/env python3
"""Governance session reader -- self-bootstrapping entrypoint.

Reads SESSION_STATE.json via the global pointer and outputs a minimal
YAML-like snapshot to stdout for LLM consumption.

Self-bootstrapping: this script resolves its own location to derive
commands_home, then reads governance.paths.json for validation. No
external PYTHONPATH setup is required.

Output format: minimal key-value pairs (YAML-compatible), one per line.
On error: prints ``status: ERROR`` with a human-readable ``error:`` line.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Schema / version constants
# ---------------------------------------------------------------------------
SNAPSHOT_SCHEMA = "governance-session-snapshot.v1"
POINTER_SCHEMA = "opencode-session-pointer.v1"


def _derive_commands_home() -> Path:
    """Derive commands_home from this script's own location.

    Layout: commands/governance/entrypoints/session_reader.py
    So commands_home = parents[2] relative to __file__.
    """
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict:
    """Read and parse a JSON file. Raises on any failure."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def _safe_str(value: object) -> str:
    """Coerce a value to a YAML-safe scalar string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_list(items: list) -> str:
    """Format a list as a YAML inline sequence."""
    if not items:
        return "[]"
    return "[" + ", ".join(_safe_str(i) for i in items) + "]"


def _quote_if_needed(value: str) -> str:
    """Wrap value in double quotes if it contains YAML-special characters."""
    if any(c in value for c in (":", "#", "'", '"', "{", "}", "[", "]", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def read_session_snapshot(commands_home: Path | None = None) -> dict:
    """Read the current governance session state and return a snapshot dict.

    Parameters
    ----------
    commands_home:
        Override for commands_home (useful for testing). If *None*, derived
        from the script's own filesystem location.

    Returns
    -------
    dict
        Snapshot dict with at minimum ``schema`` and ``status`` keys.
    """
    if commands_home is None:
        commands_home = _derive_commands_home()

    config_root = commands_home.parent

    # --- 1. Locate and read the global pointer ---
    pointer_path = config_root / "SESSION_STATE.json"
    if not pointer_path.exists():
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": f"No session pointer at {pointer_path}",
        }

    try:
        pointer = _read_json(pointer_path)
    except Exception as exc:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": f"Invalid session pointer JSON: {exc}",
        }

    if pointer.get("schema") not in (POINTER_SCHEMA, "active-session-pointer.v1"):
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": f"Unknown pointer schema: {pointer.get('schema')}",
        }

    # --- 2. Resolve workspace SESSION_STATE path ---
    session_file_raw = pointer.get("activeSessionStateFile")
    if not session_file_raw:
        # Fallback: construct from relative path
        rel = pointer.get("activeSessionStateRelativePath")
        if rel:
            session_file_raw = str(config_root / rel)

    if not session_file_raw:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": "Pointer contains no session state file path",
        }

    session_path = Path(session_file_raw)
    if not session_path.exists():
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": f"Workspace session state missing: {session_path}",
        }

    # --- 3. Read workspace SESSION_STATE ---
    try:
        state = _read_json(session_path)
    except Exception as exc:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": f"Invalid workspace session state JSON: {exc}",
        }

    # --- 4. Extract minimal fields ---
    # Canonical documents store runtime fields under "SESSION_STATE".
    # Support both nested and top-level conventions while preferring nested.
    nested = state.get("SESSION_STATE")
    state_view = nested if isinstance(nested, dict) else state

    # Support both PascalCase and snake_case field conventions.
    phase = state_view.get("Phase") or state_view.get("phase") or state.get("Phase") or state.get("phase") or "unknown"
    next_phase = state_view.get("Next") or state_view.get("next") or state.get("Next") or state.get("next") or "unknown"
    mode = state_view.get("Mode") or state_view.get("mode") or state.get("Mode") or state.get("mode") or "unknown"
    status = state_view.get("status") or state.get("status") or "OK"
    output_mode = state_view.get("OutputMode") or state_view.get("output_mode") or state.get("OutputMode") or state.get("output_mode") or "unknown"
    active_gate = state_view.get("active_gate") or state.get("active_gate") or "none"
    next_gate_condition = state_view.get("next_gate_condition") or state.get("next_gate_condition") or "none"
    ticket_intake_ready = state_view.get("ticket_intake_ready", state.get("ticket_intake_ready", False))

    # Collect blocked gates from the Gates dict.
    gates = state_view.get("Gates") or state.get("Gates") or {}
    gates_blocked = [k for k, v in gates.items() if str(v).lower() == "blocked"] if isinstance(gates, dict) else []

    return {
        "schema": SNAPSHOT_SCHEMA,
        "status": _safe_str(status),
        "phase": _safe_str(phase),
        "next": _safe_str(next_phase),
        "mode": _safe_str(mode),
        "output_mode": _safe_str(output_mode),
        "active_gate": _safe_str(active_gate),
        "next_gate_condition": _safe_str(next_gate_condition),
        "ticket_intake_ready": _safe_str(ticket_intake_ready),
        "gates_blocked": gates_blocked,
        "commands_home": str(commands_home),
    }


def format_snapshot(snapshot: dict) -> str:
    """Format a snapshot dict as YAML-compatible key-value output."""
    lines = [f"# {SNAPSHOT_SCHEMA}"]
    for key, value in snapshot.items():
        if key == "schema":
            continue
        if isinstance(value, list):
            lines.append(f"{key}: {_format_list(value)}")
        else:
            lines.append(f"{key}: {_quote_if_needed(_safe_str(value))}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    commands_home: Path | None = None
    args = argv if argv is not None else sys.argv[1:]
    if args and args[0] == "--commands-home":
        if len(args) < 2:
            print("status: ERROR", file=sys.stdout)
            print("error: --commands-home requires a path argument", file=sys.stdout)
            return 1
        commands_home = Path(args[1])

    snapshot = read_session_snapshot(commands_home=commands_home)
    sys.stdout.write(format_snapshot(snapshot))
    return 0 if snapshot.get("status") != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
