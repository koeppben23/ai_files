#!/usr/bin/env python3
"""Global error handler for governance diagnostics and bootstrap.

This module provides fail-closed error handling that ALWAYS fires on:
- Unhandled exceptions (sys.excepthook)
- Threading exceptions
- Gate failures (missing pointer, missing artifacts, write blocked, verification fail)
- Rulebook load failures

JSONL Logging (SSOT):
    - If workspace fingerprint known: ${WORKSPACES_HOME}/{fp}/logs/error.log.jsonl
    - Fallback: ${OPENCODE_HOME}/logs/error.log.jsonl

Exit Behavior:
    - All unhandled exceptions: Exit != 0
    - All gate failures: Exit != 0 (never WARN for required gates)

Copyright (c) 2026 Benjamin Fuchs. All rights reserved.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ContextManager, Optional, cast

try:
    from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
    from governance.infrastructure.path_contract import canonical_config_root, normalize_absolute_path
except Exception:
    def canonical_config_root() -> Path:
        return Path(os.path.normpath(os.path.abspath(str(Path.home().expanduser() / ".config" / "opencode"))))

    def normalize_absolute_path(raw: str, *, purpose: str) -> Path:
        token = str(raw or "").strip()
        if not token:
            raise ValueError(f"{purpose}: empty path")
        candidate = Path(token).expanduser()
        if not candidate.is_absolute():
            raise ValueError(f"{purpose}: path must be absolute")
        return Path(os.path.normpath(os.path.abspath(str(candidate))))

    def atomic_write_text(path: Path, text: str, newline_lf: bool = True, attempts: int = 5, backoff_ms: int = 50) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text.replace("\r\n", "\n") if newline_lf else text
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n" if newline_lf else None,
                dir=str(path.parent),
                prefix=path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)
            max_attempts = max(attempts, 1)
            for attempt in range(max_attempts):
                try:
                    os.replace(str(temp_path), str(path))
                    return attempt
                except OSError:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(max(backoff_ms, 1) / 1000.0)
            return 0
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _append_line_with_lock(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8", newline="\n") as handle:
            for attempt in range(8):
                try:
                    if os.name == "nt":
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                    break
                except OSError:
                    if attempt == 7:
                        raise
                    time.sleep(0.02)
            try:
                handle.seek(0, os.SEEK_END)
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def write_jsonl_event(path: Path, event: dict[str, Any], *, append: bool) -> None:
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        if append:
            _append_line_with_lock(path, line)
            return
        atomic_write_text(path, line, newline_lf=True)


ERROR_HANDLER_INSTALLED = False
_ERROR_CONTEXT: dict[str, Any] = {
    "repo_fingerprint": None,
    "repo_root": None,
    "config_root": None,
    "commands_home": None,
    "workspaces_home": None,
    "phase": "unknown",
    "command": "unknown",
}


class ErrorContext:
    """Context provider for error logging."""
    
    def __init__(
        self,
        *,
        repo_fingerprint: str | None = None,
        repo_root: Path | None = None,
        config_root: Path | None = None,
        commands_home: Path | None = None,
        workspaces_home: Path | None = None,
        phase: str = "unknown",
        command: str = "unknown",
    ):
        self.repo_fingerprint = repo_fingerprint
        self.repo_root = repo_root
        self.config_root = config_root
        self.commands_home = commands_home
        self.workspaces_home = workspaces_home
        self.phase = phase
        self.command = command

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_fingerprint": self.repo_fingerprint,
            "repo_root": str(self.repo_root) if self.repo_root else None,
            "config_root": str(self.config_root) if self.config_root else None,
            "commands_home": str(self.commands_home) if self.commands_home else None,
            "workspaces_home": str(self.workspaces_home) if self.workspaces_home else None,
            "phase": self.phase,
            "command": self.command,
        }


def set_error_context(ctx: ErrorContext) -> None:
    """Set global error context for subsequent error events."""
    global _ERROR_CONTEXT
    _ERROR_CONTEXT = ctx.to_dict()


def update_error_context(**kwargs: Any) -> None:
    """Update global error context partially."""
    global _ERROR_CONTEXT
    _ERROR_CONTEXT.update({k: v for k, v in kwargs.items() if v is not None})


def _resolve_log_path(
    *,
    config_root: Path | None = None,
    commands_home: Path | None = None,
    workspaces_home: Path | None = None,
    repo_fingerprint: str | None = None,
) -> Path:
    """Resolve the target JSONL log file path.
    
    Priority:
        1. Workspace log: ${WORKSPACES_HOME}/{fp}/logs/error.log.jsonl
        2. Global fallback: ${COMMANDS_HOME}/logs/error.log.jsonl
        3. Global fallback: ${CONFIG_ROOT}/logs/error.log.jsonl
    """
    cfg = config_root or _ERROR_CONTEXT.get("config_root")
    cmd = commands_home if commands_home is not None else (_ERROR_CONTEXT.get("commands_home") if config_root is None else None)
    ws = workspaces_home or _ERROR_CONTEXT.get("workspaces_home")
    fp = repo_fingerprint or _ERROR_CONTEXT.get("repo_fingerprint")
    
    if cfg is None:
        try:
            cfg = canonical_config_root()
        except Exception:
            cfg = Path.home() / ".config" / "opencode"
    
    if fp and ws:
        ws_path = Path(ws) if isinstance(ws, str) else ws
        workspace_log = ws_path / fp / "logs" / "error.log.jsonl"
        return workspace_log

    if cmd:
        cmd_path = Path(cmd) if isinstance(cmd, str) else cmd
        return cmd_path / "logs" / "error.log.jsonl"
    
    cfg_path = Path(cfg) if isinstance(cfg, str) else cfg
    return cfg_path / "logs" / "error.log.jsonl"


def resolve_log_path(
    *,
    config_root: Path | str | None = None,
    commands_home: Path | str | None = None,
    workspaces_home: Path | str | None = None,
    repo_fingerprint: str | None = None,
) -> Path:
    """Public helper for deterministic blocker log-path reporting."""

    cfg = Path(config_root) if isinstance(config_root, str) else config_root
    cmd = Path(commands_home) if isinstance(commands_home, str) else commands_home
    ws = Path(workspaces_home) if isinstance(workspaces_home, str) else workspaces_home
    return _resolve_log_path(
        config_root=cfg,
        commands_home=cmd,
        workspaces_home=ws,
        repo_fingerprint=repo_fingerprint,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit_jsonl_event(event: dict[str, Any], target_path: Path) -> bool:
    """Emit a single JSONL event to the target file.
    
    Uses atomic append to ensure durability.
    Returns True on success, False on failure.
    """
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        emitter = cast(Any, write_jsonl_event)
        try:
            emitter(target_path, event, append=True)
        except TypeError:
            emitter(target_path, event)
        return True
    except Exception:
        return False


def emit_error_event(
    *,
    severity: str,
    code: str,
    message: str,
    context: dict[str, Any] | None = None,
    exception: BaseException | None = None,
    repo_fingerprint: str | None = None,
    config_root: Path | None = None,
    workspaces_home: Path | None = None,
    commands_home: Path | None = None,
    phase: str | None = None,
) -> bool:
    """Emit a structured error event to JSONL log.
    
    Args:
        severity: CRITICAL | HIGH | MEDIUM
        code: Error code (e.g., PERSISTENCE_FAILED, POINTER_MISSING, UNHANDLED_EXCEPTION)
        message: Human-readable error message
        context: Additional context dictionary
        exception: Optional exception to include
        repo_fingerprint: Repository fingerprint (for workspace log)
        config_root: Config root path
        workspaces_home: Workspaces home path
        phase: Current phase
    
    Returns:
        True if event was logged successfully, False otherwise.
    """
    event_id = uuid.uuid4().hex
    ts = _utc_now()
    
    if repo_fingerprint is not None:
        effective_fp = repo_fingerprint
    elif workspaces_home is not None or config_root is not None:
        effective_fp = None
    else:
        effective_fp = _ERROR_CONTEXT.get("repo_fingerprint")
    effective_cfg = config_root or _ERROR_CONTEXT.get("config_root")
    effective_ws = workspaces_home or _ERROR_CONTEXT.get("workspaces_home")
    if commands_home is not None:
        effective_commands_home = commands_home
    elif config_root is not None:
        effective_commands_home = None
    else:
        effective_commands_home = _ERROR_CONTEXT.get("commands_home")
    effective_phase = phase or _ERROR_CONTEXT.get("phase", "unknown")
    effective_command_name = _ERROR_CONTEXT.get("command", "unknown")
    
    event: dict[str, Any] = {
        "schema": "opencode-error-log.v1",
        "ts_utc": ts,
        "event_id": event_id,
        "severity": severity.upper(),
        "code": code,
        "message": message,
        "context": {
            "repo_root": _ERROR_CONTEXT.get("repo_root"),
            "config_root": str(effective_cfg) if effective_cfg else None,
            "workspaces_home": str(effective_ws) if effective_ws else None,
            "commands_home": str(effective_commands_home) if effective_commands_home else None,
            "fp": effective_fp,
            "phase": effective_phase,
            "command": effective_command_name,
        },
    }
    
    if context:
        event["context"].update(context)
    
    if exception:
        event["exception"] = {
            "type": type(exception).__name__,
            "msg": str(exception)[:500],
            "stack": traceback.format_exception(type(exception), exception, exception.__traceback__)[-5:] if exception.__traceback__ else [],
        }
    
    target_path = _resolve_log_path(
        config_root=effective_cfg,
        commands_home=effective_commands_home,
        workspaces_home=effective_ws,
        repo_fingerprint=effective_fp,
    )
    
    return _emit_jsonl_event(event, target_path)


def emit_gate_failure(
    *,
    gate: str,
    code: str,
    message: str,
    expected: str | None = None,
    observed: Any = None,
    remediation: str | None = None,
    **kwargs: Any,
) -> bool:
    """Emit a gate failure event (always BLOCKED, never WARN).
    
    This is the canonical way to log gate failures that block progress.
    """
    context: dict[str, Any] = {"gate": gate}
    if expected:
        context["expected"] = expected
    if observed is not None:
        context["observed"] = observed
    if remediation:
        context["remediation"] = remediation
    
    return emit_error_event(
        severity="CRITICAL",
        code=code,
        message=message,
        context=context,
        **kwargs,
    )


def _global_exception_handler(exc_type: type, exc_value: BaseException, exc_tb: Any) -> None:
    """Global exception handler for sys.excepthook."""
    emit_error_event(
        severity="CRITICAL",
        code="UNHANDLED_EXCEPTION",
        message=f"Unhandled exception: {exc_type.__name__}: {exc_value}",
        exception=exc_value,
    )
    
    sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.exit(1)


def _threading_exception_handler(args: threading.ExceptHookArgs) -> None:
    """Global exception handler for threading exceptions."""
    emit_error_event(
        severity="CRITICAL",
        code="UNHANDLED_THREAD_EXCEPTION",
        message=f"Unhandled thread exception: {args.exc_type.__name__}: {args.exc_value}",
        exception=args.exc_value,
        context={"thread_name": args.thread.name if args.thread else None},
    )


def install_global_handlers(context_provider: Callable[[], ErrorContext] | None = None) -> None:
    """Install global exception handlers.
    
    This MUST be called early in bootstrap to ensure all unhandled
    exceptions are logged to JSONL.
    
    Args:
        context_provider: Optional callable that returns current error context.
    """
    global ERROR_HANDLER_INSTALLED
    
    if ERROR_HANDLER_INSTALLED:
        return
    
    sys.excepthook = _global_exception_handler
    threading.excepthook = _threading_exception_handler
    
    if context_provider:
        try:
            ctx = context_provider()
            set_error_context(ctx)
        except Exception:
            pass
    
    ERROR_HANDLER_INSTALLED = True


@contextmanager
def error_context(
    *,
    repo_fingerprint: str | None = None,
    repo_root: Path | None = None,
    config_root: Path | None = None,
    commands_home: Path | None = None,
    workspaces_home: Path | None = None,
    phase: str = "unknown",
    command: str = "unknown",
) -> Any:
    """Context manager for setting error context within a block.
    
    Usage:
        with error_context(phase="2-Discovery", command="persist_artifacts"):
            # ... code that might fail
    """
    global _ERROR_CONTEXT
    old_context = _ERROR_CONTEXT.copy()
    ctx = ErrorContext(
        repo_fingerprint=repo_fingerprint,
        repo_root=repo_root,
        config_root=config_root,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        phase=phase,
        command=command,
    )
    set_error_context(ctx)
    try:
        yield
    finally:
        _ERROR_CONTEXT = old_context


def blocked_exit(
    *,
    code: str,
    message: str,
    exit_code: int = 1,
    **kwargs: Any,
) -> None:
    """Emit error event and exit with non-zero code.
    
    This is the canonical fail-closed exit for blocked states.
    """
    emit_error_event(
        severity="CRITICAL",
        code=code,
        message=message,
        **kwargs,
    )
    sys.exit(exit_code)
