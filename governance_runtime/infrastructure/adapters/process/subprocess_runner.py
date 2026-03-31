from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from governance_runtime.application.ports.process_runner import ProcessResult, ProcessRunnerPort


class SubprocessRunner(ProcessRunnerPort):
    """Subprocess-based process runner - Infrastructure implementation.
    
    This adapter implements the ProcessRunnerPort protocol using Python's
    subprocess module. It should be used through the port interface in
    application code.
    """

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
        timeout_seconds: float | None = None,
    ) -> ProcessResult:
        """Execute a process using subprocess.run.
        
        Args:
            argv: Command and arguments as a sequence.
            cwd: Working directory. If None, uses current directory.
            env: Environment variables to merge with current environment.
                If provided, these override/extend the current environment.
                If None, uses the current process environment.
            check: If True, raise exception on non-zero return code.
            timeout_seconds: Timeout in seconds. If None, no timeout.
                A value of 0 is treated as no timeout.
            
        Returns:
            ProcessResult with returncode, stdout, and stderr.
            
        Raises:
            subprocess.CalledProcessError: If check=True and process returns non-zero.
            subprocess.TimeoutExpired: If timeout is exceeded.
        """
        # Merge env with current environment if provided
        run_env: Mapping[str, str] | None = None
        if env is not None:
            run_env = {**os.environ, **env}
        
        # Normalize timeout: 0 means no timeout
        effective_timeout = timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        
        proc = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            check=check,
            cwd=str(cwd) if cwd is not None else None,
            env=run_env,
            timeout=effective_timeout,
        )
        return ProcessResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
