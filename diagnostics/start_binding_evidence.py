#!/usr/bin/env python3
from __future__ import annotations

import json

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


def main() -> int:
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode="start")
    config_root = evidence.commands_home.parent
    debug_paths = {
        "configRoot": str(config_root),
        "commandsHome": str(evidence.commands_home),
        "profilesHome": str(evidence.commands_home / "profiles"),
        "diagnosticsHome": str(evidence.commands_home / "diagnostics"),
        "workspacesHome": str(evidence.workspaces_home),
    }

    if not evidence.binding_ok:
        payload = {
            "schema": "opencode-governance.paths.v1",
            "status": "blocked",
            "reason_code": "BLOCKED-MISSING-BINDING-FILE",
            "message": "Installer-owned governance.paths.json could not be loaded via resolver.",
            "missing_evidence": [
                "${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"
            ],
            "next_command": "/start",
            "nonEvidence": "debug-only",
            "debugComputedPaths": debug_paths,
            "bindingEvidenceSource": evidence.source,
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 0

    binding_file = evidence.governance_paths_json
    if binding_file is not None and binding_file.exists():
        try:
            print(binding_file.read_text(encoding="utf-8"))
            return 0
        except Exception as ex:
            payload = {
                "schema": "opencode-governance.paths.v1",
                "status": "blocked",
                "reason_code": "BLOCKED-VARIABLE-RESOLUTION",
                "message": "Installer-owned governance.paths.json exists but could not be read.",
                "bindingFile": str(binding_file),
                "missing_evidence": [
                    "${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"
                ],
                "error": str(ex)[:240],
                "next_command": "/start",
                "nonEvidence": "debug-only",
                "debugComputedPaths": debug_paths,
                "bindingEvidenceSource": evidence.source,
            }
            print(json.dumps(payload, ensure_ascii=True))
            return 0

    payload = {
        "schema": "opencode-governance.paths.v1",
        "status": "blocked",
        "reason_code": "BLOCKED-MISSING-BINDING-FILE",
        "missing_evidence": [
            "${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"
        ],
        "next_command": "/start",
        "nonEvidence": "debug-only",
        "debugComputedPaths": debug_paths,
        "bindingEvidenceSource": evidence.source,
    }
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
