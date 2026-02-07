#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_config_root() -> Path:
    if os.name == "nt":
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            return Path(user_profile) / ".config" / "opencode"

        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "opencode"

        return Path.home() / ".config" / "opencode"

    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "opencode"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def resolve_config_root(config_root: Path | None = None) -> Path:
    if config_root is not None:
        return config_root.expanduser().resolve()

    env_value = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_value:
        return Path(env_value).expanduser().resolve()

    # Installed location: <config_root>/commands/diagnostics/error_logs.py
    script_path = Path(__file__).resolve()
    diagnostics_dir = script_path.parent
    if diagnostics_dir.name == "diagnostics" and diagnostics_dir.parent.name == "commands":
        candidate = diagnostics_dir.parent / "governance.paths.json"
        data = _load_json(candidate)
        if data and isinstance(data.get("paths"), dict):
            cfg = data["paths"].get("configRoot")
            if isinstance(cfg, str) and cfg.strip():
                return Path(cfg).expanduser().resolve()

    # Source-tree fallback
    fallback = default_config_root()
    candidate = fallback / "commands" / "governance.paths.json"
    data = _load_json(candidate)
    if data and isinstance(data.get("paths"), dict):
        cfg = data["paths"].get("configRoot")
        if isinstance(cfg, str) and cfg.strip():
            return Path(cfg).expanduser().resolve()

    return fallback.resolve()


def _validate_repo_fingerprint(value: str) -> str:
    token = value.strip()
    if not token:
        raise ValueError("repo fingerprint must not be empty")
    if not re.fullmatch(r"[A-Za-z0-9._-]{6,128}", token):
        raise ValueError("repo fingerprint must match [A-Za-z0-9._-]{6,128}")
    return token


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out[str(k)] = _normalize_value(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    return str(value)


def _target_log_file(config_root: Path, repo_fingerprint: str | None) -> Path:
    if repo_fingerprint:
        fp = _validate_repo_fingerprint(repo_fingerprint)
        return config_root / "workspaces" / fp / "logs" / f"errors-{_today_iso()}.jsonl"
    return config_root / "logs" / f"errors-global-{_today_iso()}.jsonl"


def write_error_event(
    *,
    reason_key: str,
    message: str,
    config_root: Path | None = None,
    phase: str = "unknown",
    gate: str = "unknown",
    mode: str = "repo-aware",
    repo_fingerprint: str | None = None,
    command: str = "unknown",
    component: str = "unknown",
    observed_value: Any = None,
    expected_constraint: str | None = None,
    remediation: str | None = None,
    action: str = "block",
    result: str = "blocked",
    details: Any = None,
) -> Path:
    cfg = resolve_config_root(config_root)
    target = _target_log_file(cfg, repo_fingerprint)
    target.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "schema": "opencode.error-log.v1",
        "eventId": uuid.uuid4().hex,
        "timestamp": _utc_now(),
        "level": "error",
        "reasonKey": str(reason_key),
        "phase": str(phase),
        "gate": str(gate),
        "mode": str(mode),
        "repoFingerprint": repo_fingerprint if repo_fingerprint else "unknown",
        "command": str(command),
        "component": str(component),
        "message": str(message),
        "observedValue": _normalize_value(observed_value),
        "expectedConstraint": _normalize_value(expected_constraint),
        "action": str(action),
        "result": str(result),
        "remediation": _normalize_value(remediation),
        "details": _normalize_value(details),
    }

    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")

    return target


def safe_log_error(**kwargs: Any) -> dict[str, str]:
    try:
        p = write_error_event(**kwargs)
        return {"status": "logged", "path": str(p)}
    except Exception as exc:
        return {"status": "log-failed", "error": str(exc)}
