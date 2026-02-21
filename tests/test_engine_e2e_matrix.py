from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governance.engine.adapters import ExecResult, HostCapabilities, OperatingMode
from governance.engine.orchestrator import run_engine_orchestrator


@dataclass(frozen=True)
class StubAdapter:
    """Deterministic adapter for end-to-end orchestrator matrix tests."""

    env: dict[str, str]
    cwd_path: Path
    caps: HostCapabilities
    default_mode: OperatingMode = "user"
    now_utc_value: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def capabilities(self) -> HostCapabilities:
        return self.caps

    def environment(self) -> dict[str, str]:
        return self.env

    def cwd(self) -> Path:
        return self.cwd_path.resolve()

    def default_operating_mode(self) -> OperatingMode:
        return self.default_mode

    def now_utc(self) -> datetime:
        return self.now_utc_value

    def exec_argv(self, argv, *, cwd=None, timeout_seconds=10):
        _ = timeout_seconds
        args = tuple(str(x) for x in argv)
        run_cwd = Path(cwd) if cwd is not None else self.cwd_path.resolve()
        if "--show-toplevel" in args:
            if (run_cwd / ".git").exists():
                return ExecResult(argv=args, cwd=str(run_cwd), exit_code=0, stdout=str(run_cwd) + "\n", stderr="")
            return ExecResult(argv=args, cwd=str(run_cwd), exit_code=128, stdout="", stderr="not a git repository")
        return ExecResult(argv=args, cwd=str(run_cwd), exit_code=0, stdout="", stderr="")


def _git_root(path: Path) -> Path:
    """Create minimal git root marker for matrix scenarios."""

    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


@pytest.mark.governance
@pytest.mark.parametrize(
    "name,cwd_is_git,git_available,target_path,require_hash_match,observed_ruleset_hash,requested_mode,required_evidence,observed_evidence,expected_status,expected_reason",
    [
        (
            "wrong-cwd-no-git",
            False,
            False,
            "${WORKSPACE_MEMORY_FILE}",
            False,
            None,
            None,
            [],
            [],
            "blocked",
            "BLOCKED-REPO-IDENTITY-RESOLUTION",
        ),
        (
            "denied-surface-user-mode",
            True,
            True,
            "${COMMANDS_HOME}/master.md",
            False,
            None,
            "user",
            [],
            [],
            "blocked",
            "BLOCKED-SYSTEM-MODE-REQUIRED",
        ),
        (
            "hash-mismatch",
            True,
            True,
            "${WORKSPACE_MEMORY_FILE}",
            True,
            "deadbeef",
            None,
            [],
            [],
            "blocked",
            "BLOCKED-RULESET-HASH-MISMATCH",
        ),
        (
            "mode-downgrade",
            True,
            True,
            "${WORKSPACE_MEMORY_FILE}",
            False,
            None,
            "pipeline",
            [],
            [],
            "blocked",
            "BLOCKED-OPERATING-MODE-REQUIRED",
        ),
        (
            "missing-evidence",
            True,
            True,
            "${WORKSPACE_MEMORY_FILE}",
            False,
            None,
            None,
            ["ev-1"],
            [],
            "not_verified",
            "NOT_VERIFIED-MISSING-EVIDENCE",
        ),
    ],
)
def test_engine_orchestrator_e2e_matrix(
    tmp_path: Path,
    name: str,
    cwd_is_git: bool,
    git_available: bool,
    target_path: str,
    require_hash_match: bool,
    observed_ruleset_hash: str | None,
    requested_mode: OperatingMode | None,
    required_evidence: list[str],
    observed_evidence: list[str],
    expected_status: str,
    expected_reason: str,
):
    """Core orchestrator matrix should keep deterministic status/reason behavior."""

    cwd = tmp_path / name
    if cwd_is_git:
        cwd = _git_root(cwd)
    else:
        cwd.mkdir(parents=True, exist_ok=True)

    caps = HostCapabilities(
        cwd_trust="trusted",
        fs_read_commands_home=True,
        fs_write_config_root=True,
        fs_write_commands_home=(name != "mode-downgrade"),
        fs_write_workspaces_home=True,
        fs_write_repo_root=True,
        exec_allowed=True,
        git_available=git_available,
    )
    adapter = StubAdapter(env={"OPENCODE_REPO_ROOT": str(cwd)}, cwd_path=cwd, caps=caps)

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        target_path=target_path,
        require_hash_match=require_hash_match,
        observed_ruleset_hash=observed_ruleset_hash,
        requested_operating_mode=requested_mode,
        required_evidence_ids=required_evidence,
        observed_evidence_ids=observed_evidence,
    )
    assert out.parity["status"] == expected_status
    assert out.parity["reason_code"] == expected_reason
    if name == "wrong-cwd-no-git":
        assert out.repo_context.repo_root is None
        assert out.repo_context.is_git_root is False
    if name == "mode-downgrade":
        assert out.repo_context.repo_root == cwd.resolve()
        assert out.repo_context.is_git_root is True
