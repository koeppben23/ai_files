#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

from governance_runtime.application.use_cases.repo_policy_setup import (
    write_governance_mode_config,
    write_repo_operating_mode_policy,
)

try:
    from governance_runtime.infrastructure.path_contract import normalize_absolute_path
except Exception:  # pragma: no cover
    normalize_absolute_path = None  # type: ignore

def _normalize_path(raw: str, *, purpose: str) -> Path:
    token = str(raw or "").strip()
    if not token:
        raise ValueError(f"{purpose}: empty path")
    if callable(normalize_absolute_path):
        return normalize_absolute_path(token, purpose=purpose)
    candidate = Path(token).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{purpose}: path must be absolute")
    return Path(os.path.normpath(os.path.abspath(str(candidate))))


def _validate_repo_root(raw: str) -> Path:
    repo_root = _normalize_path(raw, purpose="repo_root")
    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError("repo_root: path does not exist or is not a directory")
    git_marker = repo_root / ".git"
    if not git_marker.exists():
        raise ValueError("repo_root: missing .git")
    return repo_root


def _validate_config_root(raw: str) -> Path:
    config_root = _normalize_path(raw, purpose="config_root")
    if not config_root.exists() or not config_root.is_dir():
        raise ValueError("config_root: path does not exist or is not a directory")
    return config_root


def _parse_json_lines(text: str) -> list[dict[str, object]]:
    parsed: list[dict[str, object]] = []
    for line in (text or "").splitlines():
        token = line.strip()
        if not token:
            continue
        try:
            payload = json.loads(token)
        except Exception:
            continue
        if isinstance(payload, dict):
            parsed.append(payload)
    return parsed


def _first_with_key(items: list[dict[str, object]], key: str) -> Optional[dict[str, object]]:
    for item in items:
        if key in item:
            return item
    return None


def _lookup(mapping: dict[str, object], key: str) -> object:
    return mapping[key] if key in mapping else None


def _emit_verbose_flow(*, repo_root: Path, events: list[dict[str, object]]) -> None:
    hook = _first_with_key(events, "workspacePersistenceHook") or {}
    continuation = _first_with_key(events, "kernelContinuation") or {}

    phase = str(_lookup(continuation, "phase") or "unknown")
    gate = str(continuation.get("active_gate") or "unknown")
    next_token = str(continuation.get("next_token") or "unknown")
    fingerprint = str(_lookup(continuation, "repo_fingerprint") or _lookup(hook, "repo_fingerprint") or "unknown")

    lines = [
        "[bootstrap] repo detected",
        f"[bootstrap] repo root: {repo_root}",
        f"[bootstrap] fingerprint resolved: {fingerprint}",
        "[bootstrap] binding verified: governance.paths.json",
        "[bootstrap] workspace persistence hook invoked",
        f"[bootstrap] final phase: {phase}",
        f"[bootstrap] active gate: {gate}",
        f"[bootstrap] next token: {next_token}",
        "[bootstrap] next step: Open OpenCode Desktop in this repo and run /hydrate",
    ]
    for line in lines:
        print(line, file=sys.stderr)


def _combined_payload(*, events: list[dict[str, object]], repo_root: Path, selected_profile: str | None) -> dict[str, object]:
    hook = _first_with_key(events, "workspacePersistenceHook") or {}
    continuation = _first_with_key(events, "kernelContinuation") or {}

    repo_fingerprint = str(
        _lookup(continuation, "repo_fingerprint")
        or _lookup(hook, "repo_fingerprint")
        or ""
    ).strip()

    return {
        "result": "bootstrap-completed" if continuation.get("kernelContinuation") == "ok" else "bootstrap-incomplete",
        "repository": {
            "name": repo_root.name,
            "root": str(repo_root),
            "mode": selected_profile or "unknown",
            "fingerprint": repo_fingerprint,
        },
        "workspace": {
            "persistence_hook": hook.get("workspacePersistenceHook"),
            "writes_allowed": hook.get("writes_allowed"),
            "pointer_verified": hook.get("pointer_verified"),
            "workspace_session_verified": hook.get("workspace_session_verified"),
            "session_state": continuation.get("session_state_path"),
        },
        "routing": {
            "phase": _lookup(continuation, "phase"),
            "active_gate": continuation.get("active_gate"),
            "source": continuation.get("source"),
            "hops": continuation.get("hops"),
            "next_gate_condition": continuation.get("next_gate_condition"),
        },
        "next_action": {
            "command": "/hydrate",
            "context": "Open OpenCode Desktop in this repository",
            "text": continuation.get("next_step") or "Open OpenCode Desktop in this repository and run /hydrate",
        },
        # Backward-compatible top-level fields expected by tooling/tests
        "workspacePersistenceHook": hook.get("workspacePersistenceHook"),
        "kernelContinuation": continuation.get("kernelContinuation"),
        "repo_fingerprint": repo_fingerprint,
    }


def _print_human_summary(payload: dict[str, object], *, verbose: bool) -> None:
    repo = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {}
    routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
    next_action = payload.get("next_action") if isinstance(payload.get("next_action"), dict) else {}

    print("Bootstrap completed" if payload.get("result") == "bootstrap-completed" else "Bootstrap incomplete")
    print(f"Repo: {repo.get('name') or 'unknown'}")
    print(f"Mode: {repo.get('mode') or 'unknown'}")
    print(f"Fingerprint: {repo.get('fingerprint') or 'unknown'}")
    print(f"Phase: {routing.get('phase') or 'unknown'}")
    print(f"Next step: {next_action.get('text') or 'Open OpenCode Desktop in this repository and run /hydrate'}")

    print("\nWorkspace")
    print(f"  Writes allowed: {'yes' if workspace.get('writes_allowed') else 'no'}")
    print(f"  Pointer verified: {'yes' if workspace.get('pointer_verified') else 'no'}")
    print(f"  Workspace session verified: {'yes' if workspace.get('workspace_session_verified') else 'no'}")
    if workspace.get("session_state"):
        print(f"  Session state: {workspace.get('session_state')}")

    print("\nRouting")
    print(f"  Active gate: {routing.get('active_gate') or 'unknown'}")
    print(f"  Source: {routing.get('source') or 'unknown'}")
    print(f"  Hops: {routing.get('hops') or 0}")

    if verbose:
        print("\nDiagnostics")
        print(f"  Kernel continuation: {payload.get('kernelContinuation') or 'unknown'}")
        print(f"  Persistence hook: {payload.get('workspacePersistenceHook') or 'unknown'}")
        ngc = routing.get("next_gate_condition")
        if ngc:
            print(f"  Next gate condition: {ngc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="opencode-governance-bootstrap",
        description="Execute bootstrap preflight until ready for Phase 4",
    )
    parser.add_argument("command", nargs="?", choices=("init",), help="Bootstrap command (recommended: init)")
    parser.add_argument("--config-root", help="Path to OpenCode config root", required=False)
    parser.add_argument("--repo-root", help="Path to repository root", required=True)
    parser.add_argument("--profile", choices=("solo", "team", "regulated"), help="Operating mode profile for init")
    parser.add_argument(
        "--set-operating-mode",
        choices=("solo", "team", "regulated"),
        help="Alias for setting repo operating mode (admin alternative)",
    )
    parser.add_argument(
        "--compliance-framework",
        default="DEFAULT",
        help="Compliance framework for regulated mode (default: DEFAULT)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show step-by-step bootstrap flow details")
    parser.add_argument("--json", action="store_true", help="Emit one structured JSON document")
    args = parser.parse_args()

    if args.profile and args.command != "init":
        parser.error("--profile is supported with 'init' (recommended canonical setup path)")
    selected_profile = str(args.profile or args.set_operating_mode or "").strip().lower() or None
    if args.command == "init" and selected_profile is None:
        parser.error("init requires --profile {solo,team,regulated}")

    try:
        repo_root = _validate_repo_root(args.repo_root)
    except Exception as exc:
        print(f"invalid --repo-root: {exc}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    if args.config_root:
        try:
            config_root = _validate_config_root(args.config_root)
        except Exception as exc:
            print(f"invalid --config-root: {exc}", file=sys.stderr)
            return 2
        env["OPENCODE_CONFIG_ROOT"] = str(config_root)
        env["COMMANDS_HOME"] = str(config_root / "commands")

    env["OPENCODE_REPO_ROOT"] = str(repo_root)
    if selected_profile is not None:
        now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        try:
            policy_path = write_repo_operating_mode_policy(
                repo_root=repo_root,
                profile=selected_profile,
                now_utc=now_utc,
            )
        except Exception as exc:
            print(f"failed to set repo operating mode: {exc}", file=sys.stderr)
            return 2
        print(f"repoOperatingMode = {selected_profile}")
        print(f"resolvedOperatingMode default = {selected_profile}")
        print(f"policyPath = {policy_path}")

        if selected_profile == "regulated":
            try:
                mode_path = write_governance_mode_config(
                    repo_root=repo_root,
                    profile=selected_profile,
                    now_utc=now_utc,
                    compliance_framework=args.compliance_framework,
                )
                if mode_path:
                    print(f"governanceModeState = active")
                    print(f"governanceModePath = {mode_path}")
            except Exception as exc:
                print(f"failed to set regulated mode: {exc}", file=sys.stderr)
                return 2
    # Always request full preflight payloads, then format in this entrypoint.
    env["OPENCODE_BOOTSTRAP_OUTPUT"] = "full"
    if args.verbose:
        env["OPENCODE_BOOTSTRAP_VERBOSE"] = "1"

    ret = subprocess.run(
        [sys.executable, "-m", "governance_runtime.entrypoints.bootstrap_preflight_readonly"],
        env=env,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
    )

    stdout_text = ret.stdout or ""
    stderr_text = ret.stderr or ""
    events = _parse_json_lines(stdout_text)
    if events:
        if args.verbose:
            _emit_verbose_flow(repo_root=repo_root, events=events)
        combined = _combined_payload(events=events, repo_root=repo_root, selected_profile=selected_profile)
        if args.json:
            print(json.dumps(combined, ensure_ascii=True))
        else:
            _print_human_summary(combined, verbose=args.verbose)
    else:
        # Fallback diagnostics when event parsing fails.
        print(stdout_text, end="")

    if stderr_text:
        print(stderr_text, end="", file=sys.stderr)
    return ret.returncode

if __name__ == "__main__":
    raise SystemExit(main())
