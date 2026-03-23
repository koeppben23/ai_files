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
