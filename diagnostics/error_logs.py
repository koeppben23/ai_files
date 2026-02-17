#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_RETENTION_DAYS = 30
ERROR_INDEX_FILE_NAME = "errors-index.json"


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


def _load_binding_paths(paths_file: Path, *, expected_config_root: Path | None = None) -> Path:
    data = _load_json(paths_file)
    if not data:
        raise ValueError(f"binding evidence unreadable: {paths_file}")
    paths = data.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"binding evidence invalid: missing paths object in {paths_file}")
    config_root_raw = paths.get("configRoot")
    workspaces_raw = paths.get("workspacesHome")
    if not isinstance(config_root_raw, str) or not config_root_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.configRoot missing in {paths_file}")
    if not isinstance(workspaces_raw, str) or not workspaces_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.workspacesHome missing in {paths_file}")
    config_root = Path(config_root_raw).expanduser().resolve()
    if expected_config_root is not None and config_root != expected_config_root.resolve():
        raise ValueError("binding evidence mismatch: config root does not match explicit input")
    return config_root


def resolve_config_root(config_root: Path | None = None) -> Path:
    if config_root is not None:
        root = config_root.expanduser().resolve()
        return _load_binding_paths(root / "commands" / "governance.paths.json", expected_config_root=root)

    env_value = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_value:
        root = Path(env_value).expanduser().resolve()
        return _load_binding_paths(root / "commands" / "governance.paths.json", expected_config_root=root)

    # Installed location: <config_root>/commands/diagnostics/error_logs.py
    script_path = Path(__file__).resolve()
    diagnostics_dir = script_path.parent
    if diagnostics_dir.name == "diagnostics" and diagnostics_dir.parent.name == "commands":
        candidate = diagnostics_dir.parent / "governance.paths.json"
        return _load_binding_paths(candidate)

    # Source-tree fallback
    fallback = default_config_root()
    candidate = fallback / "commands" / "governance.paths.json"
    return _load_binding_paths(candidate, expected_config_root=fallback.resolve())


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


def _extract_log_date(name: str) -> date | None:
    patterns = [
        r"^errors-(\d{4}-\d{2}-\d{2})\.jsonl$",
        r"^errors-global-(\d{4}-\d{2}-\d{2})\.jsonl$",
    ]
    for pat in patterns:
        m = re.match(pat, name)
        if not m:
            continue
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _prune_old_logs(log_dir: Path, keep_days: int) -> int:
    if keep_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=keep_days)
    removed = 0
    for p in log_dir.glob("*.jsonl"):
        d = _extract_log_date(p.name)
        if d is None:
            continue
        if d < cutoff:
            try:
                p.unlink()
                removed += 1
            except Exception:
                continue
    return removed


def _load_error_index(index_path: Path) -> dict[str, Any]:
    existing = _load_json(index_path)
    if not existing:
        return {
            "schema": "opencode.error-index.v1",
            "updatedAt": _utc_now(),
            "totalEvents": 0,
            "byReason": {},
            "lastEvent": {},
            "latestLogFile": "",
        }

    if existing.get("schema") != "opencode.error-index.v1":
        existing["schema"] = "opencode.error-index.v1"

    if not isinstance(existing.get("byReason"), dict):
        existing["byReason"] = {}

    if not isinstance(existing.get("totalEvents"), int):
        existing["totalEvents"] = 0

    if not isinstance(existing.get("lastEvent"), dict):
        existing["lastEvent"] = {}

    if not isinstance(existing.get("latestLogFile"), str):
        existing["latestLogFile"] = ""

    return existing


def _update_error_index(index_path: Path, log_file: Path, record: dict[str, Any]) -> None:
    idx = _load_error_index(index_path)
    by_reason = idx.get("byReason", {})
    assert isinstance(by_reason, dict)
    reason = str(record.get("reasonKey", "unknown"))
    prev = by_reason.get(reason, 0)
    by_reason[reason] = int(prev) + 1

    idx["byReason"] = by_reason
    idx["totalEvents"] = int(idx.get("totalEvents", 0)) + 1
    idx["updatedAt"] = _utc_now()
    idx["latestLogFile"] = log_file.name
    idx["lastEvent"] = {
        "timestamp": record.get("timestamp"),
        "reasonKey": reason,
        "phase": record.get("phase"),
        "gate": record.get("gate"),
        "result": record.get("result"),
        "command": record.get("command"),
        "repoFingerprint": record.get("repoFingerprint"),
    }

    index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


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
    retention_days: int = DEFAULT_RETENTION_DAYS,
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

    # Keep same-directory index for fast diagnostics summarization.
    index_path = target.parent / ERROR_INDEX_FILE_NAME
    _update_error_index(index_path, target, record)

    # Best-effort retention cleanup (never block caller).
    _prune_old_logs(target.parent, retention_days)

    return target


def safe_log_error(**kwargs: Any) -> dict[str, str]:
    try:
        p = write_error_event(**kwargs)
        return {"status": "logged", "path": str(p)}
    except Exception as exc:
        return {"status": "log-failed", "error": str(exc)}
