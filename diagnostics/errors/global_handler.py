from __future__ import annotations

from typing import Any, Callable

from diagnostics.error_handler_bridge import (
    ErrorContext,
    emit_gate_failure,
    install_global_handlers,
)

ContextProvider = Callable[[], Any]


def set_context_provider(provider: ContextProvider) -> None:
    install_global_handlers(provider)


def emit_error_event_jsonl(**kwargs: Any) -> bool:
    return emit_gate_failure(
        gate=str(kwargs.get("gate") or "ERROR"),
        code=str(kwargs.get("code") or "ERROR_EVENT"),
        message=str(kwargs.get("message") or "error event"),
        expected=kwargs.get("expected"),
        observed=kwargs.get("observed"),
        remediation=kwargs.get("remediation"),
        config_root=kwargs.get("config_root"),
        workspaces_home=kwargs.get("workspaces_home"),
        repo_fingerprint=kwargs.get("repo_fingerprint"),
        phase=kwargs.get("phase"),
        command=kwargs.get("command"),
        component=kwargs.get("component"),
        mode=kwargs.get("mode"),
    )
