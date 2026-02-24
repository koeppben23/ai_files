from __future__ import annotations

import sys
import threading
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast

from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance.infrastructure.path_contract import canonical_config_root


_ERROR_CONTEXT: dict[str, Any] = {
    "repo_fingerprint": None,
    "repo_root": None,
    "config_root": None,
    "commands_home": None,
    "workspaces_home": None,
    "phase": "unknown",
    "command": "unknown",
}
ERROR_HANDLER_INSTALLED = False


@dataclass(frozen=True)
class ErrorContext:
    repo_fingerprint: str | None = None
    repo_root: Path | None = None
    config_root: Path | None = None
    commands_home: Path | None = None
    workspaces_home: Path | None = None
    phase: str = "unknown"
    command: str = "unknown"

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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def set_error_context(ctx: ErrorContext) -> None:
    global _ERROR_CONTEXT
    _ERROR_CONTEXT = ctx.to_dict()


def update_error_context(**kwargs: Any) -> None:
    global _ERROR_CONTEXT
    _ERROR_CONTEXT.update({k: v for k, v in kwargs.items() if v is not None})


def _candidate_log_paths(
    *,
    config_root: Path | None = None,
    commands_home: Path | None = None,
    workspaces_home: Path | None = None,
    repo_fingerprint: str | None = None,
) -> list[Path]:
    cfg = config_root if config_root is not None else _ERROR_CONTEXT.get("config_root")
    cmd = commands_home if commands_home is not None else _ERROR_CONTEXT.get("commands_home")
    ws = workspaces_home if workspaces_home is not None else _ERROR_CONTEXT.get("workspaces_home")
    if repo_fingerprint is not None:
        fp = repo_fingerprint
    elif any(v is not None for v in (config_root, commands_home, workspaces_home)):
        fp = None
    else:
        fp = _ERROR_CONTEXT.get("repo_fingerprint")

    if cfg is None:
        cfg = canonical_config_root()
    cfg_path = Path(cfg) if isinstance(cfg, str) else cfg
    cmd_path = Path(cmd) if isinstance(cmd, str) else cmd
    ws_path = Path(ws) if isinstance(ws, str) else ws

    candidates: list[Path] = []
    if fp and ws_path is not None:
        candidates.append(ws_path / fp / "logs" / "error.log.jsonl")
        candidates.append(ws_path / fp / "events.jsonl")
    if cmd_path is not None:
        candidates.append(cmd_path / "logs" / "error.log.jsonl")
    candidates.append(cfg_path / "logs" / "error.log.jsonl")
    return candidates


def resolve_log_path(
    *,
    config_root: Path | str | None = None,
    commands_home: Path | str | None = None,
    workspaces_home: Path | str | None = None,
    repo_fingerprint: str | None = None,
) -> Path:
    cfg = Path(config_root) if isinstance(config_root, str) else config_root
    cmd = Path(commands_home) if isinstance(commands_home, str) else commands_home
    ws = Path(workspaces_home) if isinstance(workspaces_home, str) else workspaces_home
    return _candidate_log_paths(
        config_root=cfg,
        commands_home=cmd,
        workspaces_home=ws,
        repo_fingerprint=repo_fingerprint,
    )[0]


def _emit_jsonl_event(event: dict[str, Any], target_path: Path) -> bool:
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        emitter = cast(Any, write_jsonl_event)
        try:
            emitter(target_path, event, append=True)
        except TypeError:
            getattr(emitter, "__call__")(target_path, event)
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
    event_id = uuid.uuid4().hex
    event: dict[str, Any] = {
        "schema": "opencode-error-log.v1",
        "ts_utc": _utc_now(),
        "event_id": event_id,
        "severity": severity.upper(),
        "code": code,
        "message": message,
        "context": {
            "repo_root": _ERROR_CONTEXT.get("repo_root"),
            "config_root": str(config_root or _ERROR_CONTEXT.get("config_root") or ""),
            "workspaces_home": str(workspaces_home or _ERROR_CONTEXT.get("workspaces_home") or ""),
            "commands_home": str(commands_home or _ERROR_CONTEXT.get("commands_home") or ""),
            "fp": repo_fingerprint if repo_fingerprint is not None else _ERROR_CONTEXT.get("repo_fingerprint"),
            "phase": phase or _ERROR_CONTEXT.get("phase", "unknown"),
            "command": _ERROR_CONTEXT.get("command", "unknown"),
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

    for path in _candidate_log_paths(
        config_root=config_root,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        repo_fingerprint=repo_fingerprint,
    ):
        if _emit_jsonl_event(event, path):
            return True
    return False


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
    details: dict[str, Any] = {"gate": gate}
    if expected:
        details["expected"] = expected
    if observed is not None:
        details["observed"] = observed
    if remediation:
        details["remediation"] = remediation
    return emit_error_event(severity="CRITICAL", code=code, message=message, context=details, **kwargs)


def _global_exception_handler(exc_type: type, exc_value: BaseException, exc_tb: Any) -> None:
    emit_error_event(
        severity="CRITICAL",
        code="UNHANDLED_EXCEPTION",
        message=f"Unhandled exception: {exc_type.__name__}: {exc_value}",
        exception=exc_value,
    )
    sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.exit(1)


def _threading_exception_handler(args: threading.ExceptHookArgs) -> None:
    emit_error_event(
        severity="CRITICAL",
        code="UNHANDLED_THREAD_EXCEPTION",
        message=f"Unhandled thread exception: {args.exc_type.__name__}: {args.exc_value}",
        exception=args.exc_value,
        context={"thread_name": args.thread.name if args.thread else None},
    )


def install_global_handlers(context_provider: Callable[[], ErrorContext] | None = None) -> None:
    global ERROR_HANDLER_INSTALLED
    if ERROR_HANDLER_INSTALLED:
        return
    sys.excepthook = _global_exception_handler
    threading.excepthook = _threading_exception_handler
    if context_provider:
        try:
            set_error_context(context_provider())
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
    global _ERROR_CONTEXT
    old_context = _ERROR_CONTEXT.copy()
    set_error_context(
        ErrorContext(
            repo_fingerprint=repo_fingerprint,
            repo_root=repo_root,
            config_root=config_root,
            commands_home=commands_home,
            workspaces_home=workspaces_home,
            phase=phase,
            command=command,
        )
    )
    try:
        yield
    finally:
        _ERROR_CONTEXT = old_context


def blocked_exit(*, code: str, message: str, exit_code: int = 1, **kwargs: Any) -> None:
    emit_error_event(severity="CRITICAL", code=code, message=message, **kwargs)
    sys.exit(exit_code)
