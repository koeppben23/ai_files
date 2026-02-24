#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, cast

_emit_error_event_ssot: Any = None
_resolve_ssot_log_path: Any = None
try:
    from diagnostics.global_error_handler import emit_error_event as _emit_error_event_ssot
    from diagnostics.global_error_handler import resolve_log_path as _resolve_ssot_log_path
except Exception:
    pass


def emit_error_event_ssot(**kwargs: Any) -> bool:
    if callable(_emit_error_event_ssot):
        return bool(_emit_error_event_ssot(**kwargs))
    return False


def resolve_ssot_log_path(
    *,
    config_root: Path | str | None = None,
    commands_home: Path | str | None = None,
    workspaces_home: Path | str | None = None,
    repo_fingerprint: str | None = None,
) -> Path:
    if callable(_resolve_ssot_log_path):
        return cast(Path, _resolve_ssot_log_path(
            config_root=config_root,
            commands_home=commands_home,
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
        ))
    cfg = Path(config_root) if config_root is not None else canonical_config_root()
    cmd = Path(commands_home) if commands_home is not None else (cfg / "commands")
    ws = Path(workspaces_home) if workspaces_home is not None else (cfg / "workspaces")
    if repo_fingerprint:
        return ws / repo_fingerprint / "logs" / "error.log.jsonl"
    return cmd / "logs" / "error.log.jsonl"

try:
    from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
    from governance.infrastructure.fs_atomic import atomic_write_text
    from governance.infrastructure.path_contract import canonical_config_root, normalize_absolute_path
    from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver as ImportedBindingEvidenceResolver

    _BindingEvidenceResolver: Any = ImportedBindingEvidenceResolver
except Exception:
    class NotAbsoluteError(Exception):
        pass

    class WindowsDriveRelativeError(Exception):
        pass

    def canonical_config_root() -> Path:
        return Path(os.path.normpath(os.path.abspath(str(Path.home().expanduser() / ".config" / "opencode"))))

    def normalize_absolute_path(raw: str, *, purpose: str) -> Path:
        token = str(raw or "").strip()
        if not token:
            raise NotAbsoluteError(f"{purpose}: empty path")
        candidate = Path(token).expanduser()
        if os.name == "nt" and re.match(r"^[A-Za-z]:[^/\\]", token):
            raise WindowsDriveRelativeError(f"{purpose}: drive-relative path is not allowed")
        if not candidate.is_absolute():
            raise NotAbsoluteError(f"{purpose}: path must be absolute")
        return Path(os.path.normpath(os.path.abspath(str(candidate))))

    def atomic_write_text(path: Path, text: str, newline_lf: bool = True, attempts: int = 5, backoff_ms: int = 50) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text.replace("\r\n", "\n") if newline_lf else text
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n" if newline_lf else None,
                dir=str(path.parent),
                prefix=path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)
            for attempt in range(max(attempts, 1)):
                try:
                    os.replace(str(temp_path), str(path))
                    return attempt
                except OSError:
                    if attempt == max(attempts, 1) - 1:
                        raise
                    time.sleep(max(backoff_ms, 1) / 1000.0)
            return 0
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _append_line_with_lock(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8", newline="\n") as handle:
            for attempt in range(8):
                try:
                    if os.name == "nt":
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                    break
                except OSError:
                    if attempt == 7:
                        raise
                    time.sleep(0.02)
            try:
                handle.seek(0, os.SEEK_END)
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def write_jsonl_event(path: Path, event: dict[str, Any], *, append: bool) -> None:
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        if append:
            _append_line_with_lock(path, line)
            return
        atomic_write_text(path, line, newline_lf=True)

    class _FallbackBindingEvidence:
        binding_ok = False
        governance_paths_json: Path | None = None

    class _FallbackBindingEvidenceResolver:
        def resolve(self, *, mode: str = "diagnostics") -> _FallbackBindingEvidence:
            _ = mode
            return _FallbackBindingEvidence()

    _BindingEvidenceResolver: Any = _FallbackBindingEvidenceResolver


DEFAULT_RETENTION_DAYS = 30
ERROR_INDEX_FILE_NAME = "errors-index.json"


def default_config_root() -> Path:
    return canonical_config_root()


try:
    from diagnostics.write_policy import writes_allowed
except ImportError:
    def writes_allowed() -> bool:  # type: ignore[no-redef]
        return os.environ.get("OPENCODE_DIAGNOSTICS_ALLOW_WRITE", "0") == "1"


def _read_only() -> bool:
    return not writes_allowed()

def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_binding_paths(paths_file: Path, *, expected_config_root: Path | None = None) -> tuple[Path, Path, Path]:
    data = _load_json(paths_file)
    if not data:
        raise ValueError(f"binding evidence unreadable: {paths_file}")
    paths = data.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"binding evidence invalid: missing paths object in {paths_file}")
    config_root_raw = paths.get("configRoot")
    commands_raw = paths.get("commandsHome")
    workspaces_raw = paths.get("workspacesHome")
    if not isinstance(config_root_raw, str) or not config_root_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.configRoot missing in {paths_file}")
    if not isinstance(commands_raw, str) or not commands_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.commandsHome missing in {paths_file}")
    if not isinstance(workspaces_raw, str) or not workspaces_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.workspacesHome missing in {paths_file}")
    config_root = normalize_absolute_path(config_root_raw, purpose="paths.configRoot")
    if expected_config_root is not None:
        expected = normalize_absolute_path(str(expected_config_root), purpose="expected_config_root")
        if config_root != expected:
            raise ValueError("binding evidence mismatch: config root does not match explicit input")
    workspaces_home = normalize_absolute_path(workspaces_raw, purpose="paths.workspacesHome")
    commands_home = normalize_absolute_path(commands_raw, purpose="paths.commandsHome")
    return config_root, workspaces_home, commands_home


def resolve_paths_full(config_root: Path | None = None) -> tuple[Path, Path, Path]:
    if config_root is not None:
        root = normalize_absolute_path(str(config_root), purpose="config_root")
        paths_file = root / "commands" / "governance.paths.json"
        return _load_binding_paths(paths_file, expected_config_root=root)

    evidence = _BindingEvidenceResolver().resolve(mode="diagnostics")
    if not evidence.binding_ok or evidence.governance_paths_json is None:
        raise ValueError("binding evidence invalid or missing governance.paths.json")
    return _load_binding_paths(evidence.governance_paths_json)


def resolve_paths(config_root: Path | None = None) -> tuple[Path, Path]:
    # SSOT-only: resolve via BindingEvidenceResolver; no script-location search.
    # Optional explicit config_root stays supported (mainly for dev/test), but still uses binding evidence file.
    cfg, workspaces_home, _commands_home = resolve_paths_full(config_root)
    return cfg, workspaces_home


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


def _target_log_file(config_root: Path, workspaces_home: Path, repo_fingerprint: str | None) -> Path:
    # Per-event file; no JSONL append (avoids non-atomic writes on Windows).
    event_id = uuid.uuid4().hex
    if repo_fingerprint:
        fp = _validate_repo_fingerprint(repo_fingerprint)
        return workspaces_home / fp / "logs" / f"errors-{_today_iso()}-{event_id}.jsonl"
    return config_root / "logs" / f"errors-global-{_today_iso()}-{event_id}.jsonl"


def _extract_log_date(name: str) -> date | None:
    patterns = [
        r"^errors-(\d{4}-\d{2}-\d{2})-[A-Fa-f0-9]{8,64}\.jsonl$",
        r"^errors-(\d{4}-\d{2}-\d{2})\.jsonl$",
        r"^errors-global-(\d{4}-\d{2}-\d{2})-[A-Fa-f0-9]{8,64}\.jsonl$",
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

    atomic_write_text(index_path, json.dumps(idx, indent=2, ensure_ascii=True) + "\n", newline_lf=True)


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
    cfg, workspaces_home, commands_home = resolve_paths_full(config_root)
    if _read_only() and not str(gate or "").strip():
        raise RuntimeError("diagnostics-read-only")

    target = resolve_ssot_log_path(
        config_root=cfg,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        repo_fingerprint=repo_fingerprint,
    )
    context_payload = {
        "gate": str(gate),
        "mode": str(mode),
        "command": str(command),
        "component": str(component),
        "observedValue": _normalize_value(observed_value),
        "expectedConstraint": _normalize_value(expected_constraint),
        "action": str(action),
        "result": str(result),
        "remediation": _normalize_value(remediation),
        "details": _normalize_value(details),
        "retention_days": int(retention_days),
    }

    ok = emit_error_event_ssot(
        severity="CRITICAL" if str(result).lower() == "blocked" else "HIGH",
        code=str(reason_key),
        message=str(message),
        context=context_payload,
        repo_fingerprint=repo_fingerprint,
        config_root=cfg,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        phase=str(phase),
    )
    if not ok:
        raise RuntimeError("ssot-error-emission-failed")
    return target


def safe_log_error(**kwargs: Any) -> dict[str, str]:
    if _read_only():
        # SSOT: Always write errors for gate failures and critical diagnostics
        if kwargs.get("gate"):
            try:
                p = write_error_event(**kwargs)
                return {"status": "logged", "path": str(p)}
            except Exception as exc:
                return {"status": "log-failed", "error": str(exc)}
        return {"status": "read-only"}
    try:
        p = write_error_event(**kwargs)
        return {"status": "logged", "path": str(p)}
    except Exception as exc:
        return {"status": "log-failed", "error": str(exc)}
