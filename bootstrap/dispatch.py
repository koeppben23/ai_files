from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import subprocess


@dataclass(frozen=True)
class DispatchResult:
    returncode: int
    stdout: str
    stderr: str


def run_bootstrap_dispatch(*, command: Sequence[str], cwd: Path) -> DispatchResult:
    proc = subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        cwd=str(cwd),
    )
    return DispatchResult(
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
