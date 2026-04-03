from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ProcessResult:
    """Result of a process execution."""
    returncode: int
    stdout: str
    stderr: str


class ProcessRunnerPort(Protocol):
    """Protocol for generic process execution.
    
    Application code should depend on this protocol, not the concrete
    implementation. Infrastructure provides subprocess-based implementations.
    
    This port is for generic command execution (tools, verification, etc.).
    For entrypoint-to-entrypoint dispatch, use a separate EntryPointDispatcher.
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
        """Execute a process and return the result.
        
        Args:
            argv: Command and arguments as a sequence.
            cwd: Working directory. If None, uses current directory.
            env: Environment variables to merge with current environment.
                If provided, these override/extend the current environment.
                If None, uses the current process environment.
            check: If True, raise exception on non-zero return code.
            timeout_seconds: Timeout in seconds. If None or 0, no timeout.
            
        Returns:
            ProcessResult with returncode, stdout, and stderr.
            
        Raises:
            CalledProcessError: If check=True and process returns non-zero.
            TimeoutExpired: If timeout is exceeded.
        """
        ...
