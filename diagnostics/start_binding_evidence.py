#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
<<<<<<< HEAD
from pathlib import Path

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
=======
try:
    import pwd
except Exception:  # pragma: no cover - unavailable on Windows
    pwd = None
from pathlib import Path

from command_profiles import render_command_profiles
>>>>>>> e05b3e0 (docs(governance): add invariant checklist references (#199))


def _abs(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(str(path))))


<<<<<<< HEAD
def main() -> int:
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode="start")
    if not evidence.binding_ok:
        payload = {
            "schema": "opencode-governance.paths.v1",
            "status": "blocked",
            "reason_code": "BLOCKED-MISSING-BINDING-FILE",
            "message": "Installer-owned governance.paths.json exists but could not be loaded via resolver.",
            "bindingEvidenceSource": evidence.source,
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 0

    binding_file = evidence.governance_paths_json
    if binding_file is not None and Path(binding_file).exists():
        try:
            print(Path(binding_file).read_text(encoding="utf-8"))
            return 0
        except Exception:
            pass

    payload = {
        "schema": "opencode-governance.paths.v1",
        "status": "blocked",
        "reason_code": "BLOCKED-MISSING-BINDING-FILE",
        "bindingEvidenceSource": evidence.source,
    }
    print(json.dumps(payload, ensure_ascii=True))
=======
def config_root() -> Path:
    system = platform.system()
    if system == "Darwin" and pwd is not None:
        return _abs(Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config" / "opencode")
    return _abs(Path.home() / ".config" / "opencode")


def _candidate_binding_files() -> list[Path]:
    root = config_root()
    candidates: list[Path] = [root / "commands" / "governance.paths.json"]
    if platform.system() == "Darwin" and pwd is not None:
        candidates.append(_abs(Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config" / "opencode" / "commands" / "governance.paths.json"))
    candidates.append(_abs(Path.home() / ".config" / "opencode" / "commands" / "governance.paths.json"))

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def main() -> int:
    root = config_root()
    binding_file = root / "commands" / "governance.paths.json"
    for candidate in _candidate_binding_files():
        if candidate.exists():
            binding_file = candidate
            break

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
>>>>>>> e05b3e0 (docs(governance): add invariant checklist references (#199))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
