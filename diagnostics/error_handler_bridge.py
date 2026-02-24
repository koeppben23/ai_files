from __future__ import annotations

from typing import Any

try:
    from governance.infrastructure.logging.global_error_handler import (
        emit_gate_failure,
        install_global_handlers,
        set_error_context,
    )
    from governance.infrastructure.logging.global_error_handler import ErrorContext as _CanonicalErrorContext

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
