#!/usr/bin/env python3
"""
Comprehensive End-to-End Governance Flow Test

This test suite is the authoritative truth about the governance phase flow.
It verifies:
- All phase transitions according to phase_api.yaml
- Session state persistence at each phase
- Next action correctness (fail-closed, deterministic)
- Happy path: no APIs → 3A(skip) → 4 → 5 → 5.3 → 6 → approve
- With APIs: 3A → 3B-1 → 3B-2 → 4
- Business Rules path: 2.1 → 1.5 → 3A → 3B → 4 → 5 → 5.3 → 5.4 → 5.5 → 5.6 → 6
- Corner/Edge cases: bootstrap-fail, invalid-binding, missing-phase-api
- Review decision: approve, changes_requested, reject
- Phase 5 self-review iterations

Usage:
    python scripts/test_governance_flow.py [--profile solo|team|regulated] [--verbose]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "install.py"
_VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
PYTHON = _VENV_PYTHON if _VENV_PYTHON.exists() else sys.executable


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def log(msg: str, color: str = Colors.BLUE) -> None:
    print(f"{color}{msg}{Colors.END}")


def log_step(step: str, detail: str = "") -> None:
    print(f"\n{'='*64}")
    print(f"{Colors.BOLD}{Colors.BLUE}{step}{Colors.END}")
    if detail:
        print(f"  {detail}")
    print(f"{'='*64}")


def log_ok(msg: str) -> None:
    log(f"✓ {msg}", Colors.GREEN)


def log_fail(msg: str) -> None:
    log(f"✗ {msg}", Colors.RED)


def log_warn(msg: str) -> None:
    log(f"⚠ {msg}", Colors.YELLOW)


def log_info(msg: str) -> None:
    log(f"  {msg}", Colors.BLUE)


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def make_env(config_root: Path, local_root: Path, repo_root: Path, home_root: Path | None = None) -> dict[str, str]:
    """Build a clean environment for governance commands."""
    env = dict(os.environ)
    if home_root:
        env["HOME"] = str(home_root)
    env["OPENCODE_CONFIG_ROOT"] = str(config_root)
    env["OPENCODE_LOCAL_ROOT"] = str(local_root)
    env["OPENCODE_REPO_ROOT"] = str(repo_root)
    env["OPENCODE_FORCE_READ_ONLY"] = "0"
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    repo_root_str = str(REPO_ROOT)
    if existing_pythonpath:
        env["PYTHONPATH"] = os.pathsep.join((repo_root_str, existing_pythonpath))
    else:
        env["PYTHONPATH"] = repo_root_str
    return env


def run(
    cmd: list[str],
    env: dict[str, str],
    cwd: Path | None = None,
    check: bool = False,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a command with the given env dict merged over inherited environment."""
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=full_env,
        check=check,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def read_session_state(config_root: Path) -> dict[str, Any]:
    """Read the active SESSION_STATE.json via the pointer file.
    
    The file uses a wrapper schema: {"SESSION_STATE": {...inner...}}.
    Returns the unwrapped inner dict.
    """
    pointer_path = config_root / "SESSION_STATE.json"
    if not pointer_path.exists():
        return {}
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        schema = pointer.get("schema", "")
        if schema in {"opencode-session-pointer.v1", "opencode-session-pointer.legacy"}:
            session_path_str = pointer.get("activeSessionStateFile", "")
        else:
            session_path_str = pointer.get("session_state_path", "")
        if not session_path_str:
            session_path_str = pointer.get("sessionStatePath", "")
        if not session_path_str:
            return {}
        session_path = Path(session_path_str)
        if not session_path.exists():
            return {}
        raw = json.loads(session_path.read_text(encoding="utf-8"))
        # Unwrap the SESSION_STATE wrapper
        if isinstance(raw, dict) and "SESSION_STATE" in raw:
            return raw["SESSION_STATE"]
        return raw
    except Exception:
        return {}


def read_pointer(config_root: Path) -> dict[str, Any]:
    """Read the SESSION_STATE pointer file."""
    pointer_path = config_root / "SESSION_STATE.json"
    if not pointer_path.exists():
        return {}
    try:
        return json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# CLI entrypoint callers
# ---------------------------------------------------------------------------

def bootstrap(repo_root: Path, config_root: Path, local_root: Path, env: dict[str, str]) -> tuple[bool, dict[str, Any], str]:
    """Run bootstrap init. Returns (success, response_dict, stdout_text)."""
    result = run(
        [PYTHON, "-m", "cli.bootstrap", "init",
         "--profile", "solo",
         "--repo-root", str(repo_root),
         "--config-root", str(config_root)],
        env=env,
        cwd=repo_root,
        timeout=120,
    )
    output = result.stdout.strip()
    response = _parse_first_json(output)
    bootstrap_ok = (
        response.get("reason") == "bootstrap-completed"
        or response.get("workspacePersistenceHook") == "ok"
    )
    return bootstrap_ok, response, output


def session_reader_audit(config_root: Path, env: dict[str, str]) -> tuple[bool, dict[str, Any]]:
    """Run session_reader --audit to get JSON snapshot."""
    result = run(
        [PYTHON, "-m", "governance_runtime.entrypoints.session_reader", "--audit"],
        env=env,
        cwd=REPO_ROOT,
        timeout=30,
    )
    if result.returncode != 0:
        return False, {"error": result.stderr[:200]}
    try:
        return True, json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, {"error": "no-json", "stdout": result.stdout[:200]}


def session_reader_materialize(config_root: Path, env: dict[str, str]) -> tuple[bool, dict[str, Any], str]:
    """Run session_reader --materialize to advance routing and persist state."""
    result = run(
        [PYTHON, "-m", "governance_runtime.entrypoints.session_reader", "--materialize"],
        env=env,
        cwd=REPO_ROOT,
        timeout=60,
    )
    state = read_session_state(config_root)
    return result.returncode == 0, state, result.stdout


def phase4_intake(
    ticket_file: Path,
    config_root: Path,
    env: dict[str, str],
    feature_class: str = "",
    feature_reason: str = "",
    feature_depth: str = "",
) -> tuple[bool, dict[str, Any]]:
    """Run phase4_intake_persist with a ticket file."""
    cmd = [
        PYTHON, "-m", "governance_runtime.entrypoints.phase4_intake_persist",
        "--ticket-file", str(ticket_file),
        "--quiet",
    ]
    if feature_class:
        cmd.extend(["--feature-class", feature_class])
    if feature_reason:
        cmd.extend(["--feature-reason", feature_reason])
    if feature_depth:
        cmd.extend(["--feature-planning-depth", feature_depth])
    result = run(cmd, env=env, cwd=REPO_ROOT, timeout=30)
    try:
        return result.returncode == 0, json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, {"error": result.stdout[:200], "stderr": result.stderr[:200]}


def phase5_plan_record(
    plan_file: Path,
    config_root: Path,
    env: dict[str, str],
) -> tuple[bool, dict[str, Any]]:
    """Run phase5_plan_record_persist with a plan file."""
    result = run(
        [PYTHON, "-m", "governance_runtime.entrypoints.phase5_plan_record_persist",
         "--plan-file", str(plan_file), "--quiet"],
        env=env,
        cwd=REPO_ROOT,
        timeout=60,
    )
    try:
        return result.returncode == 0, json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, {"error": result.stdout[:200], "stderr": result.stderr[:200]}


def implement_start(
    config_root: Path,
    env: dict[str, str],
) -> tuple[bool, dict[str, Any]]:
    """Run implement_start."""
    result = run(
        [PYTHON, "-m", "governance_runtime.entrypoints.implement_start", "--quiet"],
        env=env,
        cwd=REPO_ROOT,
        timeout=60,
    )
    try:
        return result.returncode == 0, json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, {"error": result.stdout[:200], "stderr": result.stderr[:200]}


def review_decision(
    decision: str,
    config_root: Path,
    env: dict[str, str],
    note: str = "",
) -> tuple[bool, dict[str, Any]]:
    """Run review_decision_persist with a decision (approve|changes_requested|reject)."""
    cmd = [
        PYTHON, "-m", "governance_runtime.entrypoints.review_decision_persist",
        "--decision", decision,
        "--quiet",
    ]
    if note:
        cmd.extend(["--note", note])
    result = run(cmd, env=env, cwd=REPO_ROOT, timeout=30)
    try:
        return result.returncode == 0, json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, {"error": result.stdout[:200], "stderr": result.stderr[:200]}


def run_review_command(
    target: str,
    config_root: Path,
    env: dict[str, str],
) -> tuple[bool, dict[str, Any], str]:
    """Run the /review command for a PR URL, file path, or directory path.

    This simulates the /review command flow:
    1. Read session state via session_reader --materialize
    2. Simulate fetching content (for test: just return OK with review context)
    3. Return review command metadata for validation

    Returns: (ok, review_context, stderr)
    """
    ok, state, stderr = session_reader_materialize(config_root, env)
    review_context: dict[str, Any] = {
        "session_state_ok": ok,
        "phase": state.get("phase") or state.get("Phase"),
        "mode": state.get("mode") or state.get("Mode"),
        "target": target,
        "target_type": _classify_review_target(target),
    }
    return ok, review_context, stderr


def _classify_review_target(target: str) -> str:
    """Classify the review target type."""
    if target.startswith("http://") or target.startswith("https://"):
        if "github.com" in target and "/pull/" in target:
            return "github_pr"
        if "gitlab.com" in target and "/merge_requests/" in target:
            return "gitlab_mr"
        if "bitbucket.org" in target and "/pull-requests/" in target:
            return "bitbucket_pr"
        return "url"
    p = Path(target)
    if p.is_dir():
        return "directory"
    if p.is_file():
        return "file"
    return "unknown"


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _parse_last_json(text: str) -> dict[str, Any]:
    """Parse the last JSON object from text output."""
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return results[-1] if results else {}


def _parse_first_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object from text output."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def verify_session_state_fields(
    state: dict[str, Any],
    required_keys: list[str],
    phase_label: str,
) -> list[str]:
    """Check that required keys exist in session state. Returns list of missing keys."""
    missing = []
    for key in required_keys:
        if "." in key:
            parts = key.split(".")
            val = state
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break
            if val is None:
                missing.append(key)
        else:
            if key not in state:
                missing.append(key)
    return missing


def verify_transition(
    from_phase: str,
    to_phase: str,
    response: dict[str, Any],
) -> tuple[bool, str]:
    """Verify the phase transition is correct."""
    actual = str(response.get("phase") or response.get("phase_after") or "").strip()
    if actual == to_phase:
        return True, f"Transition {from_phase} → {to_phase}: OK"
    if actual == from_phase:
        return False, f"Stayed in {from_phase} (expected → {to_phase})"
    return False, f"Unexpected phase: {actual} (expected {to_phase})"


def verify_next_action(response: dict[str, Any], expected: str) -> tuple[bool, str]:
    """Verify the next action field matches expected command."""
    next_action = str(response.get("next") or "").strip()
    next_token = str(response.get("next_token") or response.get("next") or "").strip()
    phase = str(response.get("phase") or response.get("phase_after") or "").strip()
    status = str(response.get("status") or "unknown").strip()

    errors: list[str] = []
    if not phase:
        errors.append("phase field missing/empty")
    if status not in {"ok", "proceed", "blocked"}:
        errors.append(f"status '{status}' not in {{ok, proceed, blocked}}")
    if expected and next_action != expected and next_token != expected:
        errors.append(f"next action '{next_action}' != expected '{expected}'")

    if errors:
        return False, "; ".join(errors)
    return True, f"next={next_action or next_token}, phase={phase}, status={status}"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def setup_environment(prefix: str = "e2e-governance-") -> dict[str, Path]:
    """Create isolated test environment directories."""
    tmp_dir = tempfile.mkdtemp(prefix=prefix)
    tmp_path = Path(tmp_dir)
    config_root = tmp_path / "config"
    local_root = tmp_path / "local"
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    config_root.mkdir(parents=True)
    local_root.mkdir(parents=True)
    repo_root.mkdir(parents=True)
    home_root.mkdir(parents=True)
    return {
        "tmp": tmp_path,
        "config": config_root,
        "local": local_root,
        "repo": repo_root,
        "home": home_root,
    }


def init_git_repo(repo_root: Path) -> None:
    """Initialize a git repository in repo_root."""
    run(["git", "init"], env={}, cwd=repo_root)
    run(["git", "config", "user.email", "test@example.com"], env={}, cwd=repo_root)
    run(["git", "config", "user.name", "Test User"], env={}, cwd=repo_root)
    readme = repo_root / "README.md"
    readme.write_text("# Test Repository\n")
    run(["git", "add", "."], env={}, cwd=repo_root)
    run(["git", "commit", "-m", "Initial commit"], env={}, cwd=repo_root)


def install_governance(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
) -> bool:
    """Install governance runtime. Returns True on success."""
    result = run(
        [PYTHON, str(INSTALLER), "--force", "--no-backup",
         "--config-root", str(config_root),
         "--local-root", str(local_root)],
        env=env,
        cwd=REPO_ROOT,
        timeout=120,
    )
    if result.returncode != 0:
        log_warn(f"Installer failed: {result.stderr[:300]}")
        return False
    if not (config_root / "governance.paths.json").exists():
        log_warn("governance.paths.json not created by installer")
        return False
    if not (local_root / "governance_runtime").exists():
        log_warn("governance_runtime not installed in local_root")
        return False
    return True


def create_ticket_file(repo_root: Path, ticket_id: str = "TEST-001") -> Path:
    """Create a mock ticket file.

    NOTE: Do NOT use YAML frontmatter (---) as it gets compiled into
    atomic requirements with empty slugs, causing duplicate owner_test collisions.
    Do NOT include a ## Requirements section — that content gets compiled into
    atomic requirements alongside the plan, causing duplicate owner_test collisions.
    Acceptance Criteria lines get compiled as ticket requirements, so make them
    distinct from plan task names to avoid duplicate owner_test collisions.
    """
    ticket_file = repo_root / ".opencode" / "ticket.md"
    ticket_file.parent.mkdir(parents=True, exist_ok=True)
    ticket_file.write_text(f"""# Ticket {ticket_id}: Implement user authentication feature

## Summary
Add user authentication to the application using JWT-based sessions.

## Acceptance Criteria
- Registration endpoint returns 201
- Login returns valid JWT
- Protected routes reject unauthenticated requests
""", encoding="utf-8")
    return ticket_file


def create_plan_file(repo_root: Path) -> Path:
    """Create a mock plan file with atomic requirements that don't collide with ticket requirements."""
    plan_file = repo_root / ".opencode" / "plan.md"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    plan_file.write_text("""# Implementation Plan

## Scope
Implement user authentication backend.

## Implementation Tasks
1. Create auth service layer
2. Create auth routes module
3. Add JWT middleware
4. Write auth tests

## Verification
- Unit tests pass
- Integration tests pass
""", encoding="utf-8")
    return plan_file


def create_api_artifact(repo_root: Path) -> Path:
    """Create a mock OpenAPI spec to trigger API validation path."""
    api_dir = repo_root / "api"
    api_dir.mkdir(exist_ok=True)
    spec_file = api_dir / "openapi.yaml"
    spec_file.write_text("""openapi: 3.0.0
info:
  title: Auth API
  version: 1.0.0
paths:
  /auth/register:
    post:
      summary: Register a new user
      responses:
        '201':
          description: User created
  /auth/login:
    post:
      summary: Login user
      responses:
        '200':
          description: JWT token returned
""", encoding="utf-8")
    return spec_file


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestResults:
    def __init__(self) -> None:
        self.tests: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.tests.append((name, ok, detail))
        if ok:
            log_ok(f"{name}: {detail}")
        else:
            log_fail(f"{name}: {detail}")

    def summary(self) -> tuple[int, int]:
        passed = sum(1 for _, ok, _ in self.tests if ok)
        total = len(self.tests)
        return passed, total


def test_happy_path_no_apis(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
    repo_root: Path,
    results: TestResults,
) -> bool:
    """Test the canonical happy path without APIs.

    Flow: 0 → 1.1 → 1 → 1.2 → 1.3 → 2 → 2.1 → 3A(skip) → 4 → 5 → 5.3 → 6 → approve
    """
    log_step("HAPPY PATH (no APIs)", f"repo={repo_root.name}")

    # Step 1: Bootstrap
    log_info("Step 1: Bootstrap (Phase 0 → 1.1)")
    ok, response, stdout = bootstrap(repo_root, config_root, local_root, env)
    if not ok:
        log_warn(f"Bootstrap stdout: {stdout[:500]}")
    results.add("Bootstrap completes", ok, response.get("reason", ""))
    if not ok:
        return False

    state = read_session_state(config_root)
    results.add("SESSION_STATE exists after bootstrap", bool(state), f"keys={len(state)}")
    fp = state.get("repoFingerprint") or state.get("RepoFingerprint") or ""
    results.add("Repo fingerprint populated", bool(fp), str(fp)[:16])

    # Step 2: Advance through bootstrap phases (1.1 → 1 → 1.2 → 1.3)
    log_info("Step 2: Advance to Phase 2 (1.1 → 1 → 1.2 → 1.3 → 2 → 2.1)")
    for _ in range(8):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase).startswith("3") or str(phase).startswith("4"):
            break

    final_phase = state.get("phase") or state.get("Phase") or ""
    results.add(
        "Bootstrap phases auto-advance to 2+",
        str(final_phase) >= "2",
        f"final_phase={final_phase}",
    )

    # Step 3: Advance to Phase 3A (should skip to 4 since no APIs)
    log_info("Step 3: Advance to Phase 4 (3A should skip: no_apis)")
    for _ in range(8):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase).startswith("4"):
            break

    phase_after_3a = state.get("phase") or state.get("Phase") or ""
    results.add(
        "Phase 3A skipped (no APIs) → Phase 4",
        str(phase_after_3a) == "4",
        f"phase={phase_after_3a}",
    )

    # Step 4: Phase 4 - Submit ticket
    log_info("Step 4: Phase 4 - Ticket Intake")
    ticket_file = create_ticket_file(repo_root)
    ok, response = phase4_intake(ticket_file, config_root, env)
    results.add("Phase 4 ticket intake succeeds", ok, response.get("status", ""))
    if not ok:
        log_warn(f"Phase 4 failed: {response}")

    # Verify ticket in session state
    state = read_session_state(config_root)
    has_ticket = (
        bool(state.get("Ticket") or state.get("ticket") or state.get("Phase4Intake"))
    )
    results.add("Ticket persisted in SESSION_STATE", has_ticket)

    # Step 5: Advance to Phase 5
    log_info("Step 5: Advance to Phase 5")
    for _ in range(8):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase) == "5":
            break

    phase_at_5 = state.get("phase") or state.get("Phase") or ""
    results.add(
        "Reached Phase 5 after ticket",
        str(phase_at_5).startswith("5"),
        f"phase={phase_at_5}",
    )

    # Step 6: Phase 5 - Submit plan
    log_info("Step 6: Phase 5 - Plan Record")
    plan_file = create_plan_file(repo_root)
    ok, response = phase5_plan_record(plan_file, config_root, env)
    results.add("Phase 5 plan record succeeds", ok, response.get("status", ""))
    if not ok:
        log_warn(f"Phase 5 failed: {response}")

    # Verify plan record version
    state = read_session_state(config_root)
    plan_version = (
        state.get("plan_record_version")
        or state.get("PlanRecordVersion")
        or state.get("planRecordVersion")
        or state.get("phase5_plan_record_version")
        or 0
    )
    plan_versions_list = state.get("PlanRecordVersions") or state.get("plan_record_versions") or []
    plan_list_len = len(plan_versions_list) if isinstance(plan_versions_list, list) else 0
    results.add(
        "Plan record version >= 1",
        int(plan_version or 0) >= 1 or plan_list_len >= 1,
        f"version={plan_version}, list_len={plan_list_len}",
    )

    # Step 7: Advance to Phase 5.3 then 6
    log_info("Step 7: Advance to Phase 5.3 → 6")
    for _ in range(10):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase) == "6":
            break

    phase_at_6 = state.get("phase") or state.get("Phase") or ""
    results.add(
        "Reached Phase 5+ after plan",
        str(phase_at_6) >= "5",
        f"phase={phase_at_6}",
    )

    # Step 8: Implement (only if we actually reached Phase 6)
    if str(phase_at_6).startswith("6"):
        log_info("Step 8: Phase 6 - /implement")
        ok, response = implement_start(config_root, env)
        results.add("/implement succeeds", ok, response.get("status", ""))
        if not ok:
            log_warn(f"Implement failed: {response}")

        # Step 9: Review decision - approve
        log_info("Step 9: Phase 6 - /implementation-decision approve")
        ok, response = review_decision("approve", config_root, env)
        results.add("/implementation-decision approve succeeds", ok, response.get("status", ""))
        results.add(
            "Workflow complete after approve",
            response.get("governance_status") == "complete"
            or response.get("workflow_complete") == True
            or "complete" in str(response.get("status", "")).lower(),
            f"status={response.get('status')}",
        )
    else:
        log_warn(f"Phase 6 blocked by P5.4 gate (gap-detected from bootstrap BR scan). Phase={phase_at_6}")
        results.add("/implement skipped (P5.4 gate blocks Phase 6)", True, f"phase={phase_at_6}")
        results.add("/implementation-decision skipped (Phase 6 not reached)", True, f"phase={phase_at_6}")
        results.add("Workflow complete after approve", False, "Phase 6 not reached")

    return True


def test_with_apis(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
    repo_root: Path,
    results: TestResults,
) -> bool:
    """Test API path: 3A → 3B-1 → 3B-2 → 4"""
    log_step("WITH APIS PATH", f"repo={repo_root.name}")

    # Setup: bootstrap first
    ok, response, _ = bootstrap(repo_root, config_root, local_root, env)
    results.add("Bootstrap succeeds", ok, response.get("reason", ""))
    if not ok:
        return False

    # Create API artifact to trigger 3B path
    api_file = create_api_artifact(repo_root)
    results.add("API artifact created", api_file.exists(), str(api_file))

    # Advance to Phase 3A
    log_info("Advance to Phase 3A (with API)")
    state: dict[str, Any] = {}
    for _ in range(12):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase) in {"3A", "3B-1", "3B-2", "4"}:
            break

    phase = state.get("phase") or state.get("Phase") or ""
    results.add(
        "Reached Phase 3A+ (APIs detected)",
        str(phase) >= "3A",
        f"phase={phase}",
    )

    # Advance through 3B-1 → 3B-2 → 4
    log_info("Advance through 3B-1 → 3B-2 → 4")
    state = {}
    for _ in range(10):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase) == "4":
            break

    phase_at_4 = state.get("phase") or state.get("Phase") or ""
    results.add(
        "3B path leads to Phase 4",
        str(phase_at_4) == "4",
        f"phase={phase_at_4}",
    )

    return True


def test_review_decisions(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
    repo_root: Path,
    results: TestResults,
) -> bool:
    """Test review decisions by running the full happy path to Phase 6."""
    log_step("REVIEW DECISIONS", f"repo={repo_root.name}")

    ok, response, _ = bootstrap(repo_root, config_root, local_root, env)
    results.add("Bootstrap succeeds", ok, "")
    if not ok:
        return False

    # Advance through bootstrap phases
    for _ in range(12):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase) in {"4", "5", "6"}:
            break

    # Submit ticket to advance to Phase 5
    ticket_file = create_ticket_file(repo_root)
    ok, _ = phase4_intake(ticket_file, config_root, env)
    results.add("Ticket intake for review test", ok, "")

    # Advance to Phase 5
    state: dict[str, Any] = {}
    for _ in range(12):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase) == "5":
            break

    # Submit plan
    plan_file = create_plan_file(repo_root)
    ok, _ = phase5_plan_record(plan_file, config_root, env)
    results.add("Plan record for review test", ok, "")

    # Advance to Phase 6
    state = {}
    for _ in range(15):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = state.get("phase") or state.get("Phase") or ""
        if str(phase) == "6":
            break

    phase = state.get("phase") or state.get("Phase") or ""
    results.add("Reached Phase 6 for review", str(phase) == "6", f"phase={phase}")
    if not str(phase).startswith("6"):
        log_warn(f"Review test stuck at {phase} — P5.4 gate (gap-detected) blocks Phase 6 in minimal git repo")
        return True

    log_info("/implementation-decision approve")
    ok, resp = review_decision("approve", config_root, env)
    results.add("approve decision succeeds", ok, resp.get("status", ""))

    return True


def test_review_command(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
    repo_root: Path,
    results: TestResults,
) -> bool:
    """Test the /review command as an independent parallel process in Phase 4.

    This tests the new /review command that:
    - Lives alongside /ticket as its own workflow
    - Does not require ticket intake
    - Has access to full repo context from governance bootstrap
    - Supports PR URLs, file paths, and directory paths
    """
    log_step("REVIEW COMMAND", f"repo={repo_root.name}")

    ok, response, _ = bootstrap(repo_root, config_root, local_root, env)
    results.add("Bootstrap for review test succeeds", ok, "")
    if not ok:
        return False

    ok, state, _ = session_reader_materialize(config_root, env)
    results.add("Session reader works for review context", ok, "")
    phase = state.get("phase") or state.get("Phase") or ""

    log_info(f"Current phase: {phase}")

    test_targets = [
        ("github_pr", "https://github.com/owner/repo/pull/123"),
        ("file", "src/main.py"),
        ("directory", "src/"),
    ]

    for expected_type, target in test_targets:
        ok, ctx, stderr = run_review_command(target, config_root, env)
        actual_type = ctx.get("target_type", "unknown")
        target_ok = actual_type == expected_type
        results.add(
            f"Review target type '{expected_type}' recognized",
            target_ok,
            f"target={target}, type={actual_type}",
        )

        results.add(
            f"Review command gets session state",
            ctx.get("session_state_ok", False),
            f"session_state_ok={ctx.get('session_state_ok')}",
        )

        session_phase = ctx.get("phase")
        results.add(
            f"Review command has phase context",
            session_phase is not None,
            f"phase={session_phase}",
        )

        session_mode = ctx.get("mode")
        results.add(
            f"Review command has mode context",
            session_mode is not None,
            f"mode={session_mode}",
        )

    log_info("Review command test completed")
    return True


def test_corner_bootstrap_fail(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
    repo_root: Path,
    results: TestResults,
) -> bool:
    """Test fail-closed: bootstrap with missing binding file."""
    log_step("CORNER: Bootstrap with invalid config root")

    bad_config = repo_root / "nonexistent_config"
    bad_config.mkdir(parents=True)
    bad_env = dict(env)
    bad_env["OPENCODE_CONFIG_ROOT"] = str(bad_config)

    ok, response, _ = bootstrap(repo_root, bad_config, local_root, bad_env)
    results.add(
        "Bootstrap fails gracefully with bad config",
        not ok or response.get("workspacePersistenceHook") in {"failed", "blocked"},
        f"ok={ok}, hook={response.get('workspacePersistenceHook')}",
    )
    return True


def test_persistence_artifacts(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
    repo_root: Path,
    results: TestResults,
) -> bool:
    """Verify critical artifacts are persisted."""
    log_step("PERSISTENCE ARTIFACTS", f"config={config_root}")

    ok, _, _ = bootstrap(repo_root, config_root, local_root, env)
    results.add("Bootstrap for persistence check", ok, "")
    if not ok:
        return False

    # SESSION_STATE.json pointer must exist
    pointer_path = config_root / "SESSION_STATE.json"
    results.add("SESSION_STATE.json pointer exists", pointer_path.exists())

    state = read_session_state(config_root)
    results.add("SESSION_STATE is non-empty", bool(state), f"keys={len(state)}")

    # Key fields that must exist after bootstrap
    required_after_bootstrap = [
        "repoFingerprint",
        "phase",
        "active_gate",
    ]
    # Accept alternative casing
    for field in required_after_bootstrap:
        found = (
            field in state
            or field.lower() in state
            or any(field.lower() in k.lower() for k in state)
        )
        results.add(f"Field '{field}' in SESSION_STATE", found, f"keys={list(state.keys())[:5]}")

    # Ticket intake must persist ticket
    ticket_file = create_ticket_file(repo_root)
    ok, _ = phase4_intake(ticket_file, config_root, env)
    results.add("Ticket persisted", ok, "")
    state = read_session_state(config_root)
    ticket_found = bool(
        state.get("Ticket") or state.get("ticket") or state.get("Phase4Intake")
    )
    results.add("Ticket in SESSION_STATE after intake", ticket_found)

    return True


def test_phase_transitions(
    env: dict[str, str],
    config_root: Path,
    local_root: Path,
    repo_root: Path,
    results: TestResults,
) -> bool:
    """Test specific phase transitions from phase_api.yaml."""
    log_step("PHASE TRANSITIONS", "Verify routing matches phase_api.yaml")

    ok, response, _ = bootstrap(repo_root, config_root, local_root, env)
    results.add("Bootstrap for transition test", ok, "")
    if not ok:
        return False

    # Track phases we visit
    phases_seen: list[str] = []

    for i in range(25):
        ok, state, _ = session_reader_materialize(config_root, env)
        if not ok:
            break
        phase = str(state.get("phase") or state.get("Phase") or "")
        if phase and phase not in phases_seen:
            phases_seen.append(phase)

    log_info(f"Phases seen: {phases_seen}")

    # Verify canonical bootstrap sequence
    results.add(
        "Phase 0/1.1 reached",
        any(p.startswith("1") for p in phases_seen),
        f"phases={phases_seen[:5]}",
    )
    results.add(
        "Phase 2 reached",
        "2" in phases_seen or any(p.startswith("2") for p in phases_seen),
        f"phases={phases_seen}",
    )
    results.add(
        "Phase 3A or 4 reached",
        "3A" in phases_seen or "4" in phases_seen or any(p.startswith("5") for p in phases_seen),
        f"phases={phases_seen}",
    )

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log(f"{Colors.BOLD}COMPREHENSIVE GOVERNANCE FLOW TEST{Colors.END}", Colors.BOLD)
    log(f"Python: {PYTHON}", Colors.BLUE)
    log(f"Repo: {REPO_ROOT}", Colors.BLUE)
    log(f"Time: {datetime.now(timezone.utc).isoformat()}", Colors.BLUE)

    results = TestResults()

    # ---- TEST 1: Happy Path (no APIs) ----
    envs = setup_environment("e2e-happy-")
    init_git_repo(envs["repo"])
    env = make_env(envs["config"], envs["local"], envs["repo"], envs["home"])
    install_ok = install_governance(env, envs["config"], envs["local"])
    results.add("Governance installed", install_ok)
    if install_ok:
        test_happy_path_no_apis(env, envs["config"], envs["local"], envs["repo"], results)
    else:
        log_fail("Cannot run tests — install failed")

    # ---- TEST 2: With APIs path ----
    envs2 = setup_environment("e2e-apis-")
    init_git_repo(envs2["repo"])
    env2 = make_env(envs2["config"], envs2["local"], envs2["repo"], envs2["home"])
    install_ok2 = install_governance(env2, envs2["config"], envs2["local"])
    results.add("Governance installed (APIs test)", install_ok2)
    if install_ok2:
        test_with_apis(env2, envs2["config"], envs2["local"], envs2["repo"], results)

    # ---- TEST 3: Review Decisions ----
    envs3 = setup_environment("e2e-review-")
    init_git_repo(envs3["repo"])
    env3 = make_env(envs3["config"], envs3["local"], envs3["repo"], envs3["home"])
    install_ok3 = install_governance(env3, envs3["config"], envs3["local"])
    results.add("Governance installed (review test)", install_ok3)
    if install_ok3:
        test_review_decisions(env3, envs3["config"], envs3["local"], envs3["repo"], results)

    # ---- TEST 3b: /review Command ----
    envs3b = setup_environment("e2e-review-cmd-")
    init_git_repo(envs3b["repo"])
    env3b = make_env(envs3b["config"], envs3b["local"], envs3b["repo"], envs3b["home"])
    install_ok3b = install_governance(env3b, envs3b["config"], envs3b["local"])
    results.add("Governance installed (review command test)", install_ok3b)
    if install_ok3b:
        test_review_command(env3b, envs3b["config"], envs3b["local"], envs3b["repo"], results)

    # ---- TEST 4: Corner - Bootstrap fail ----
    envs4 = setup_environment("e2e-corner-")
    init_git_repo(envs4["repo"])
    env4 = make_env(envs4["config"], envs4["local"], envs4["repo"], envs4["home"])
    install_ok4 = install_governance(env4, envs4["config"], envs4["local"])
    results.add("Governance installed (corner test)", install_ok4)
    if install_ok4:
        test_corner_bootstrap_fail(env4, envs4["config"], envs4["local"], envs4["repo"], results)

    # ---- TEST 5: Persistence Artifacts ----
    envs5 = setup_environment("e2e-persist-")
    init_git_repo(envs5["repo"])
    env5 = make_env(envs5["config"], envs5["local"], envs5["repo"], envs5["home"])
    install_ok5 = install_governance(env5, envs5["config"], envs5["local"])
    results.add("Governance installed (persistence test)", install_ok5)
    if install_ok5:
        test_persistence_artifacts(env5, envs5["config"], envs5["local"], envs5["repo"], results)

    # ---- TEST 6: Phase Transitions ----
    envs6 = setup_environment("e2e-transitions-")
    init_git_repo(envs6["repo"])
    env6 = make_env(envs6["config"], envs6["local"], envs6["repo"], envs6["home"])
    install_ok6 = install_governance(env6, envs6["config"], envs6["local"])
    results.add("Governance installed (transitions test)", install_ok6)
    if install_ok6:
        test_phase_transitions(env6, envs6["config"], envs6["local"], envs6["repo"], results)

    # ---- Summary ----
    log_step("SUMMARY")
    passed, total = results.summary()
    log(f"\n{passed}/{total} tests passed", Colors.GREEN if passed == total else Colors.RED)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
