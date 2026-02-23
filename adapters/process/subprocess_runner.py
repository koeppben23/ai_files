from __future__ import annotations

import subprocess

from kernel.ports.process_runner import ProcessResult


class SubprocessRunner:
    def run(self, argv: list[str], env: dict[str, str] | None = None) -> ProcessResult:
        proc = subprocess.run(argv, text=True, capture_output=True, check=False, env=env)
        return ProcessResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
