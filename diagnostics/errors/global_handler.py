from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from pathlib import Path
import json
import datetime
import os
import sys
import traceback


@dataclass
class ErrorContext:
    config_root: Optional[str] = None
    workspaces_home: Optional[str] = None
    repo_fingerprint: Optional[str] = None
    phase: Optional[str] = None
    command: Optional[str] = None
    component: Optional[str] = None


ContextProvider = Callable[[], ErrorContext]


def _default_context_provider() -> ErrorContext:
    return ErrorContext()


_context_provider: ContextProvider = _default_context_provider


def set_context_provider(provider: ContextProvider) -> None:
    global _context_provider
    _context_provider = provider


def _get_error_log_path() -> Optional[Path]:
    config_root = os.environ.get("OPENCODE_CONFIG_ROOT")
    if config_root:
        return Path(config_root) / "error.log.jsonl"
    
    home = os.environ.get("OPENCODE_HOME") or os.environ.get("HOME")
    if home:
        return Path(home) / ".config" / "opencode" / "error.log.jsonl"
    
    return None


def emit_error_event_jsonl(**kwargs: Any) -> bool:
    log_path = _get_error_log_path()
    if not log_path:
        return False
    
    context = _context_provider()
    
    event = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "config_root": kwargs.get("config_root") or context.config_root,
        "workspaces_home": kwargs.get("workspaces_home") or context.workspaces_home,
        "repo_fingerprint": kwargs.get("repo_fingerprint") or context.repo_fingerprint,
        "phase": kwargs.get("phase") or context.phase,
        "command": kwargs.get("command") or context.command,
        "component": kwargs.get("component") or context.component,
        "gate": kwargs.get("gate"),
        "code": kwargs.get("code"),
        "message": kwargs.get("message"),
        "expected": kwargs.get("expected"),
        "observed": kwargs.get("observed"),
        "remediation": kwargs.get("remediation"),
        "mode": kwargs.get("mode"),
    }
    
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")
        return True
    except (IOError, OSError):
        return False


def emit_gate_failure(
    *,
    gate: str,
    code: str,
    message: str,
    expected: Optional[str] = None,
    observed: Optional[Any] = None,
    remediation: Optional[str] = None,
    **kwargs: Any
) -> bool:
    context = _context_provider()
    
    return emit_error_event_jsonl(
        gate=gate,
        code=code,
        message=message,
        expected=expected,
        observed=observed,
        remediation=remediation,
        config_root=kwargs.get("config_root") or context.config_root,
        workspaces_home=kwargs.get("workspaces_home") or context.workspaces_home,
        repo_fingerprint=kwargs.get("repo_fingerprint") or context.repo_fingerprint,
        phase=kwargs.get("phase") or context.phase,
        command=kwargs.get("command") or context.command,
        component=kwargs.get("component") or context.component,
        mode=kwargs.get("mode"),
    )


def install_global_handlers(context_provider: Optional[ContextProvider] = None) -> None:
    if context_provider:
        set_context_provider(context_provider)
    
    def handle_exception(exc_type, exc_value, exc_traceback):
        emit_error_event_jsonl(
            gate="UNHANDLED_EXCEPTION",
            code=exc_type.__name__,
            message=str(exc_value),
            observed={
                "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            }
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    sys.excepthook = handle_exception
