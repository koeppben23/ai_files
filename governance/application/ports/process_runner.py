"""Process runner port interface.

.. deprecated::
    Use governance_runtime.application.ports.process_runner instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class ProcessRunnerPort:
    def run(self, argv: list[str], env: dict[str, str] | None = None) -> ProcessResult:
        raise NotImplementedError
