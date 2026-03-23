from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


from typing import Any

try:
    from governance_runtime.infrastructure.logging.global_error_handler import (
        emit_gate_failure,
        install_global_handlers,
        set_error_context,
    )
    from governance_runtime.infrastructure.logging.global_error_handler import ErrorContext as _CanonicalErrorContext

    def ErrorContext(**kwargs: Any):  # type: ignore[no-redef]
        return _CanonicalErrorContext(**kwargs)
except ImportError:
    class _FallbackErrorContext:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    def ErrorContext(**kwargs: Any):  # type: ignore[no-redef]
        return _FallbackErrorContext(**kwargs)

    def install_global_handlers(context_provider=None):  # type: ignore[no-redef]
        return None

    def set_error_context(ctx):  # type: ignore[no-redef]
        return None

    def emit_gate_failure(**kwargs: Any) -> bool:  # type: ignore[no-redef]
        return False
