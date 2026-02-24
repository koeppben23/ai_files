from __future__ import annotations

from pathlib import Path
from typing import Any

from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event as _sink_write_jsonl_event
from governance.infrastructure.logging import global_error_handler as _impl

write_jsonl_event = _sink_write_jsonl_event

ErrorContext = _impl.ErrorContext
set_error_context = _impl.set_error_context
update_error_context = _impl.update_error_context
install_global_handlers = _impl.install_global_handlers
error_context = _impl.error_context
blocked_exit = _impl.blocked_exit


def resolve_log_path(**kwargs: Any) -> Path:
    return _impl.resolve_log_path(**kwargs)


def emit_error_event(**kwargs: Any) -> bool:
    _impl.write_jsonl_event = write_jsonl_event
    return _impl.emit_error_event(**kwargs)


def emit_gate_failure(**kwargs: Any) -> bool:
    _impl.write_jsonl_event = write_jsonl_event
    return _impl.emit_gate_failure(**kwargs)
