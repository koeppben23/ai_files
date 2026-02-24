#!/usr/bin/env python3
"""Thin CLI composition root for bootstrap session persistence."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


try:
    from governance.entrypoints.bootstrap_session_state_orchestrator import (  # noqa: F401
        _atomic_write_text,
        _is_canonical_fingerprint,
        _validate_canonical_fingerprint,
        _validate_repo_fingerprint,
        parse_args,
        pointer_payload,
        repo_identity_map_path,
        repo_session_state_path,
        resolve_binding_config,
        resolve_repo_root_ssot,
        session_pointer_path,
        session_state_template,
    )
    from governance.entrypoints.bootstrap_session_state_orchestrator import main as _orchestrator_main
except Exception:  # pragma: no cover
    from bootstrap_session_state_orchestrator import (  # type: ignore # noqa: F401
        _atomic_write_text,
        _is_canonical_fingerprint,
        _validate_canonical_fingerprint,
        _validate_repo_fingerprint,
        parse_args,
        pointer_payload,
        repo_identity_map_path,
        repo_session_state_path,
        resolve_binding_config,
        resolve_repo_root_ssot,
        session_pointer_path,
        session_state_template,
    )
    from bootstrap_session_state_orchestrator import main as _orchestrator_main  # type: ignore


def main() -> int:
    return _orchestrator_main()


if __name__ == "__main__":
    raise SystemExit(main())
