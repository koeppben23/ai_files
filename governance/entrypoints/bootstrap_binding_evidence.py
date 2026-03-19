#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


import json
import sys
from pathlib import Path

_COMMANDS_HOME = str(Path(__file__).parent.parent)
if _COMMANDS_HOME not in sys.path:
    sys.path.insert(0, _COMMANDS_HOME)

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


def main() -> int:
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode="start")

    if not evidence.binding_ok:
        payload = {
            "schema": "opencode-governance.paths.v1",
            "status": "blocked",
            "reason_code": "BLOCKED-MISSING-BINDING-FILE",
            "message": "Installer-owned governance.paths.json could not be loaded via resolver.",
            "missing_evidence": [
                "${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"
            ],
            "next_command": "opencode-governance-bootstrap",
            "nonEvidence": "debug-only",
            "debugComputedPaths": {
                "configRoot": str(evidence.config_root) if evidence.config_root else "unknown",
                "commandsHome": str(evidence.commands_home) if evidence.commands_home else "unknown",
            },
            "bindingEvidenceSource": evidence.source,
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 2  # Non-zero exit for blocked state

    config_root = evidence.commands_home.parent if evidence.commands_home else None
    debug_paths = {
        "configRoot": str(config_root) if config_root else "unknown",
        "commandsHome": str(evidence.commands_home) if evidence.commands_home else "unknown",
        "localRoot": str(evidence.local_root) if evidence.local_root else "unknown",
        "profilesHome": str(evidence.profiles_home) if evidence.profiles_home else "unknown",
        "governanceHome": str(evidence.governance_home) if evidence.governance_home else "unknown",
        "runtimeHome": str(evidence.runtime_home) if evidence.runtime_home else "unknown",
        "contentHome": str(evidence.content_home) if evidence.content_home else "unknown",
        "specHome": str(evidence.spec_home) if evidence.spec_home else "unknown",
        "workspacesHome": str(evidence.workspaces_home) if evidence.workspaces_home else "unknown",
    }

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
                "next_command": "opencode-governance-bootstrap",
                "nonEvidence": "debug-only",
                "debugComputedPaths": debug_paths,
                "bindingEvidenceSource": evidence.source,
            }
            print(json.dumps(payload, ensure_ascii=True))
            return 2

    payload = {
        "schema": "opencode-governance.paths.v1",
        "status": "blocked",
        "reason_code": "BLOCKED-MISSING-BINDING-FILE",
        "missing_evidence": [
            "${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"
        ],
        "next_command": "opencode-governance-bootstrap",
        "nonEvidence": "debug-only",
        "debugComputedPaths": debug_paths,
        "bindingEvidenceSource": evidence.source,
    }
    print(json.dumps(payload, ensure_ascii=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
