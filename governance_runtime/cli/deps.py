from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from governance_runtime.application.ports.process_runner import ProcessResult, ProcessRunnerPort
from governance_runtime.domain.errors.events import ErrorEvent
from governance_runtime.infrastructure.fs_atomic import atomic_write_text


class LocalFS:
    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write_text_atomic(self, path: Path, content: str) -> None:
        atomic_write_text(path, content, newline_lf=True)

    def exists(self, path: Path) -> bool:
        return path.exists()

    def mkdir_p(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)


class LocalProcessRunner(ProcessRunnerPort):
    def run(self, argv: list[str], env: Optional[dict[str, str]] = None) -> ProcessResult:
        run = subprocess.run(argv, text=True, capture_output=True, check=False, env=env)
        return ProcessResult(returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)


class GlobalErrorLogger:
    def write(self, event: ErrorEvent) -> None:
        try:
            from governance_runtime.infrastructure.logging.global_error_handler import emit_error_event

            emit_error_event(
                severity=event.severity,
                code=event.code,
                message=event.message,
                context=event.context,
            )
        except (OSError, RuntimeError):
            # best-effort: emit failure should not crash the CLI
            return
