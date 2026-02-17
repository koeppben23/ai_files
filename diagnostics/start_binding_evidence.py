#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from command_profiles import render_command_profiles


def config_root() -> Path:
    system = platform.system()
    if system == "Windows":
        user_profile = os.getenv("USERPROFILE")
        if user_profile:
            return Path(user_profile) / ".config" / "opencode"
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "opencode"
        raise SystemExit("Windows: USERPROFILE/APPDATA not set")

    xdg = os.getenv("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "opencode"


def main() -> int:
    root = config_root()
    binding_file = root / "commands" / "governance.paths.json"

    if binding_file.exists():
        try:
            print(binding_file.read_text(encoding="utf-8"))
            return 0
        except Exception as ex:
            print(
                json.dumps(
                    {
                        "schema": "opencode-governance.paths.v1",
                        "status": "blocked",
                        "reason_code": "BLOCKED-VARIABLE-RESOLUTION",
                        "message": "Installer-owned governance.paths.json exists but could not be read.",
                        "bindingFile": str(binding_file),
                        "missing_evidence": [
                            "${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"
                        ],
                        "error": str(ex)[:240],
                        "recovery_steps": [
                            "allow OpenCode host read access to governance.paths.json",
                            "rerun /start so host-provided binding evidence can be loaded",
                        ],
                        "next_command": "/start",
                        "next_command_profiles": render_command_profiles(["/start"]),
                        "nonEvidence": "debug-only",
                    },
                    indent=2,
                )
            )
            return 0

    def norm(path: Path) -> str:
        return str(path)

    print(
        json.dumps(
            {
                "schema": "opencode-governance.paths.v1",
                "status": "blocked",
                "reason_code": "BLOCKED-MISSING-BINDING-FILE",
                "message": "Missing installer-owned governance.paths.json; computed paths are debug-only and non-evidence.",
                "missing_evidence": [
                    "${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"
                ],
                "next_command": "/start",
                "next_command_profiles": render_command_profiles(["/start"]),
                "debugComputedPaths": {
                    "configRoot": norm(root),
                    "commandsHome": norm(root / "commands"),
                    "profilesHome": norm(root / "commands" / "profiles"),
                    "diagnosticsHome": norm(root / "commands" / "diagnostics"),
                    "workspacesHome": norm(root / "workspaces"),
                },
                "recovery_steps": [
                    "rerun installer to create commands/governance.paths.json",
                    "rerun /start after installer repair",
                ],
                "nonEvidence": "debug-only",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
