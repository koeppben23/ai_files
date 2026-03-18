"""Deterministic engine lifecycle pointer and rollback helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from governance_runtime.domain.reason_codes import BLOCKED_INTEGRITY_FAILED
from governance_runtime.infrastructure.artifact_integrity import verify_ruleset_integrity
from governance_runtime.infrastructure.fs_atomic import atomic_write_json


MAX_ROLLBACK_DEPTH = 5


def _read_paths_document(paths_file: Path) -> dict[str, Any]:
    """Load governance paths document or initialize default structure."""

    if not paths_file.exists():
        return {"paths": {}, "engineLifecycle": {"active": {}, "previous_stack": [], "audit_trail": []}}
    payload = json.loads(paths_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("governance.paths.json must be a JSON object")
    if "paths" not in payload or not isinstance(payload.get("paths"), dict):
        payload["paths"] = {}
    lifecycle = payload.get("engineLifecycle")
    if not isinstance(lifecycle, dict):
        lifecycle = {}
        payload["engineLifecycle"] = lifecycle
    if not isinstance(lifecycle.get("active"), dict):
        lifecycle["active"] = {}
    
    # Backward compatibility: convert legacy "previous" dict to "previous_stack"
    legacy_previous = lifecycle.get("previous")
    if isinstance(legacy_previous, dict) and legacy_previous:
        lifecycle["previous_stack"] = [legacy_previous]
        del lifecycle["previous"]
    
    if not isinstance(lifecycle.get("previous_stack"), list):
        lifecycle["previous_stack"] = []
    if not isinstance(lifecycle.get("audit_trail"), list):
        lifecycle["audit_trail"] = []
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write canonical JSON payload to target path."""

    atomic_write_json(path, payload, ensure_ascii=True, indent=2)


def stage_engine_activation(
    *,
    paths_file: Path,
    engine_version: str,
    engine_sha256: str,
    ruleset_hash: str,
    now_utc: datetime | None = None,
    ruleset_dir: Path | None = None,
) -> dict[str, Any]:
    """Stage one active engine pointer update with rollbackable previous pointer.

    If ``ruleset_dir`` is provided, SHA256 integrity of manifest.json and
    lock.json is verified against hashes.json before activation proceeds.
    Verification failure is fail-closed: raises ``RuntimeError``.
    """

    # ── Integrity gate (fail-closed) ───────────────────────────────────
    if ruleset_dir is not None:
        result = verify_ruleset_integrity(ruleset_dir)
        if not result.passed:
            raise RuntimeError(f"{BLOCKED_INTEGRITY_FAILED}: {result.summary}")

    observed_at = (now_utc or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    payload = _read_paths_document(paths_file)
    lifecycle = payload["engineLifecycle"]
    active = dict(lifecycle["active"])
    previous_stack = list(lifecycle["previous_stack"])

    if active:
        previous_stack.append(active)
        if len(previous_stack) > MAX_ROLLBACK_DEPTH:
            previous_stack = previous_stack[-MAX_ROLLBACK_DEPTH:]

    lifecycle["previous_stack"] = previous_stack
    lifecycle["active"] = {
        "version": engine_version,
        "sha256": engine_sha256,
        "ruleset_hash": ruleset_hash,
        "observed_at": observed_at,
    }
    lifecycle["audit_trail"].append(
        {
            "type": "activation_staged",
            "observed_at": observed_at,
            "active_version": engine_version,
            "stack_depth": len(previous_stack),
        }
    )
    _atomic_write_json(paths_file, payload)
    return payload


def rollback_engine_activation(
    *,
    paths_file: Path,
    trigger: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Rollback to previous active pointer and append deterministic rollback audit event."""

    observed_at = (now_utc or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    payload = _read_paths_document(paths_file)
    lifecycle = payload["engineLifecycle"]
    active = dict(lifecycle.get("active", {}))
    previous_stack = list(lifecycle.get("previous_stack", []))

    if not previous_stack:
        lifecycle["audit_trail"].append(
            {
                "type": "automatic_rollback_skipped",
                "observed_at": observed_at,
                "trigger": trigger,
                "reason": "empty_stack",
            }
        )
        _atomic_write_json(paths_file, payload)
        return payload

    recovered = previous_stack.pop()
    lifecycle["previous_stack"] = previous_stack
    lifecycle["active"] = recovered
    lifecycle["audit_trail"].append(
        {
            "type": "automatic_rollback",
            "observed_at": observed_at,
            "trigger": trigger,
            "recovered_version": recovered.get("version", ""),
            "remaining_stack_depth": len(previous_stack),
            "deviation": {
                "type": "DEVIATION",
                "scope": "engine_lifecycle",
                "impact": "active pointer rolled back to previous known-good engine",
            },
        }
    )
    _atomic_write_json(paths_file, payload)
    return payload
