"""OS-aware command rendering helpers for user-facing recovery actions."""

from __future__ import annotations

import json
from typing import Sequence


def _bash_quote(value: str) -> str:
    if value == "":
        return "''"
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/:@%+=,"
    if all(ch in safe for ch in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def render_command_profiles(argv: Sequence[str]) -> dict[str, object]:
    parts = [str(p) for p in argv]

    def _cmd_quote(value: str) -> str:
        if not value or any(ch in value for ch in (' ', '\t', '"')):
            return '"' + value.replace('"', '\\"') + '"'
        return value

    bash = " ".join(_bash_quote(p) for p in parts)
    cmd = " ".join(_cmd_quote(p) for p in parts)
    powershell = " ".join(_cmd_quote(p) for p in parts)
    return {
        "argv": parts,
        "bash": bash,
        "cmd": cmd,
        "powershell": powershell,
        "json": json.dumps(parts, ensure_ascii=True),
    }
