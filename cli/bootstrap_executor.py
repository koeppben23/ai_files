#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional

try:
    from governance.infrastructure.path_contract import normalize_absolute_path
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


def _emit_verbose_flow(*, repo_root: Path, events: list[dict[str, object]]) -> None:
    hook = _first_with_key(events, "workspacePersistenceHook") or {}
    continuation = _first_with_key(events, "kernelContinuation") or {}

    phase = str(continuation.get("phase") or "unknown")
    gate = str(continuation.get("active_gate") or "unknown")
    next_token = str(continuation.get("next_token") or "unknown")
    fingerprint = str(continuation.get("repo_fingerprint") or hook.get("repo_fingerprint") or "unknown")

    lines = [
        "[bootstrap] repo detected",
        f"[bootstrap] repo root: {repo_root}",
        f"[bootstrap] fingerprint resolved: {fingerprint}",
        "[bootstrap] binding verified: governance.paths.json",
        "[bootstrap] workspace persistence hook invoked",
        f"[bootstrap] final phase: {phase}",
        f"[bootstrap] active gate: {gate}",
        f"[bootstrap] next token: {next_token}",
        "[bootstrap] next step: Open OpenCode Desktop in this repo and run /continue",
    ]
    for line in lines:
        print(line, file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="opencode-governance-bootstrap",
        description="Execute bootstrap preflight until ready for Phase 4",
    )
    parser.add_argument("--config-root", help="Path to OpenCode config root", required=False)
    parser.add_argument("--repo-root", help="Path to repository root", required=True)
    parser.add_argument("--verbose", action="store_true", help="Show step-by-step bootstrap flow details")
    args = parser.parse_args()

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
    if args.verbose:
        env["OPENCODE_BOOTSTRAP_VERBOSE"] = "1"
        env["OPENCODE_BOOTSTRAP_OUTPUT"] = "full"

    ret = subprocess.run(
        [sys.executable, "-m", "governance.entrypoints.bootstrap_preflight_readonly"],
        env=env,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
    )

    stdout_text = ret.stdout or ""
    stderr_text = ret.stderr or ""
    if args.verbose:
        events = _parse_json_lines(stdout_text)
        if events:
            _emit_verbose_flow(repo_root=repo_root, events=events)
            continuation = _first_with_key(events, "kernelContinuation")
            if continuation is not None:
                enriched = dict(continuation)
                enriched.setdefault(
                    "next_step",
                    "Open OpenCode Desktop in this repository and run /continue",
                )
                print(json.dumps(enriched, ensure_ascii=True))
            else:
                print(stdout_text, end="")
        else:
            print(stdout_text, end="")
    else:
        print(stdout_text, end="")

    if stderr_text:
        print(stderr_text, end="", file=sys.stderr)
    return ret.returncode

if __name__ == "__main__":
    raise SystemExit(main())
