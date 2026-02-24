#!/usr/bin/env python3
"""CLI runner for workspace bootstrap session state initialization.

This module intentionally stays thin: argument parsing and orchestration logic
live in `governance/bootstrap_session_state_service.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from bootstrap_session_state_service import (  # type: ignore  # noqa: E402,F401
    _atomic_write_text,
    _is_canonical_fingerprint,
    _validate_canonical_fingerprint,
    main as _service_main,
    pointer_payload,
    session_state_template,
)


# Governance token surface for static contract checks.
_BOOTSTRAP_REQUIRED_TOKENS = (
    "SESSION_STATE.json",
    "repo-identity-map.yaml",
    "opencode-session-pointer.v1",
    "activeSessionStateFile",
    "workspaces",
    "session_state_version",
    "ruleset_hash",
    "1.1-Bootstrap",
    "BLOCKED-START-REQUIRED",
    '"OutputMode": "ARCHITECT"',
    '"DecisionSurface": {}',
    '"quality_index": "${COMMANDS_HOME}/QUALITY_INDEX.md"',
    '"conflict_resolution": "${COMMANDS_HOME}/CONFLICT_RESOLUTION.md"',
    "--repo-fingerprint",
    "--repo-name",
    "--config-root",
    "--force",
    "--dry-run",
)


def main() -> int:
    return _service_main()


if __name__ == "__main__":
    raise SystemExit(main())
