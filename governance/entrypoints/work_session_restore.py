#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance.domain.canonical_json import canonical_json_hash
from governance.domain.operating_profile import derive_mode_evidence
from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.current_run_pointer import read_active_run_id, write_current_run_pointer
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance.infrastructure.workspace_paths import run_dir

try:
    from governance.entrypoints.workspace_lock import acquire_workspace_lock
except Exception:
    from workspace_lock import acquire_workspace_lock  # type: ignore


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    atomic_write_text(path, text)


def _append_jsonl(path: Path, event: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(event), ensure_ascii=True, separators=(",", ":")) + "\n")


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json root must be object")
    return payload


def _resolve_active_session_path() -> tuple[Path, str, Path]:
    resolver = BindingEvidenceResolver()
    evidence = getattr(resolver, "resolve")(mode="user")
    if evidence.config_root is None or evidence.workspaces_home is None:
        raise RuntimeError("binding unavailable")

    pointer_path = evidence.config_root / "SESSION_STATE.json"
    pointer = parse_session_pointer_document(_load_json(pointer_path))
    session_path = resolve_active_session_state_path(pointer, config_root=evidence.config_root)
    fingerprint = str(pointer.get("activeRepoFingerprint") or "").strip()
    if not fingerprint:
        raise RuntimeError("activeRepoFingerprint missing")
    if not session_path.exists():
        raise RuntimeError("active session missing")
    return session_path, fingerprint, evidence.workspaces_home


def _extract_state_view(document: Mapping[str, object]) -> Mapping[str, object]:
    nested = document.get("SESSION_STATE")
    if isinstance(nested, Mapping):
        return nested
    return document


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def _extract_mode_fields(state: Mapping[str, object]) -> tuple[str, str, str]:
    effective, resolved, verify_policy = derive_mode_evidence(
        effective_operating_mode=str(state.get("effective_operating_mode") or state.get("operating_mode") or "unknown"),
        resolved_operating_mode=str(state.get("resolved_operating_mode") or state.get("resolvedOperatingMode") or ""),
        verify_policy_version=str(state.get("verify_policy_version") or state.get("verifyPolicyVersion") or "v1"),
    )
    return effective, str(resolved), verify_policy


def _read_run_archive(*, run_root: Path) -> tuple[dict[str, object], dict[str, object] | None, Path, str]:
    archived_session_path = run_root / "SESSION_STATE.json"
    if not archived_session_path.exists():
        raise RuntimeError(f"run session snapshot missing: {archived_session_path}")
    archived_doc = _load_json(archived_session_path)
    state_view = _extract_state_view(archived_doc)
    if not isinstance(state_view, Mapping):
        raise RuntimeError("archived session snapshot invalid")
    archived_plan_path = run_root / "plan-record.json"
    archived_plan_doc: dict[str, object] | None = None
    if archived_plan_path.exists():
        archived_plan_doc = _load_json(archived_plan_path)
    return archived_doc, archived_plan_doc, archived_session_path, str(state_view.get("session_run_id") or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read or reactivate archived work-session runs")
    parser.add_argument("--mode", choices=["revisit", "reactivate"], required=True, help="Operation mode")
    parser.add_argument("--run-id", required=True, help="Archived run id under runs/<run_id>")
    parser.add_argument("--session-id", default="", help="Optional OpenCode session id")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    observed_at = _now_iso()
    run_id = str(args.run_id or "").strip()
    session_id = " ".join((args.session_id or os.environ.get("OPENCODE_SESSION_ID", "")).split())
    if not run_id:
        print(json.dumps(_payload("blocked", reason="missing-run-id"), ensure_ascii=True))
        return 2

    try:
        session_path, repo_fingerprint, workspaces_home = _resolve_active_session_path()
    except Exception as exc:
        print(
            json.dumps(
                _payload(
                    "blocked",
                    reason="work-session-restore-init-failed",
                    observed=str(exc),
                    recovery_action="verify binding evidence and active session pointer",
                ),
                ensure_ascii=True,
            )
        )
        return 2

    run_root = run_dir(workspaces_home, repo_fingerprint, run_id)

    if not run_root.exists() or not run_root.is_dir():
        print(
            json.dumps(
                _payload(
                    "blocked",
                    reason="run-archive-unavailable",
                    observed=f"run archive missing: {run_root}",
                    recovery_action="verify runs/<run_id>/SESSION_STATE.json exists and is valid JSON",
                ),
                ensure_ascii=True,
            )
        )
        return 2

    archive_ok, _, archive_verify_message = verify_run_archive(run_root)
    if not archive_ok:
        print(
            json.dumps(
                _payload(
                    "blocked",
                    reason="run-archive-integrity-failed",
                    observed=archive_verify_message or "archive verify failed",
                    recovery_action="repair or recreate the archived run before reactivation",
                ),
                ensure_ascii=True,
            )
        )
        return 2

    try:
        archived_doc, archived_plan_doc, archived_session_path, archived_session_run_id = _read_run_archive(run_root=run_root)
    except Exception as exc:
        print(
            json.dumps(
                _payload(
                    "blocked",
                    reason="run-archive-unavailable",
                    observed=str(exc),
                    recovery_action="verify runs/<run_id>/SESSION_STATE.json exists and is valid JSON",
                ),
                ensure_ascii=True,
            )
        )
        return 2

    state_view = _extract_state_view(archived_doc)
    phase = str(state_view.get("Phase") or state_view.get("phase") or "")
    active_gate = str(state_view.get("active_gate") or "")
    next_token = str(state_view.get("Next") or state_view.get("next") or "")
    effective_mode, resolved_mode, verify_policy_version = _extract_mode_fields(state_view)
    archived_digest = canonical_json_hash(archived_doc)

    if args.mode == "revisit":
        payload = _payload(
            "ok",
            reason="work-session-revisit",
            repo_fingerprint=repo_fingerprint,
            run_id=run_id,
            archived_session_run_id=archived_session_run_id,
            phase=phase,
            next=next_token,
            active_gate=active_gate,
            effective_operating_mode=effective_mode,
            resolved_operating_mode=resolved_mode,
            verify_policy_version=verify_policy_version,
            snapshot_path=str(archived_session_path),
            snapshot_digest=archived_digest,
            plan_record_present=archived_plan_doc is not None,
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 0

    lock = None
    try:
        lock = acquire_workspace_lock(workspaces_home=workspaces_home, repo_fingerprint=repo_fingerprint)
        active_doc = _load_json(session_path)
        active_state = _extract_state_view(active_doc)

        previous_run_id = read_active_run_id(workspaces_home=workspaces_home, repo_fingerprint=repo_fingerprint)
        if not previous_run_id:
            previous_run_id = str(active_state.get("session_run_id") or "").strip()

        if previous_run_id == run_id:
            payload = _payload(
                "ok",
                reason="work-session-reactivate-noop",
                repo_fingerprint=repo_fingerprint,
                active_run_id=run_id,
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 0

        _write_json_atomic(session_path, archived_doc)

        root_plan = session_path.parent / "plan-record.json"
        if archived_plan_doc is not None:
            _write_json_atomic(root_plan, archived_plan_doc)
        elif root_plan.exists():
            root_plan.unlink()

        pointer_path = write_current_run_pointer(
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
            active_run_id=run_id,
            updated_at=observed_at,
            activation_reason="reactivate-run",
        )

        _append_jsonl(
            session_path.parent / "events.jsonl",
            {
                "event": "work_session_reactivated",
                "observed_at": observed_at,
                "repo_fingerprint": repo_fingerprint,
                "session_id": session_id,
                "run_id": run_id,
                "previous_run_id": previous_run_id,
                "reactivated_run_id": run_id,
                "snapshot_path": str(archived_session_path),
                "snapshot_digest": archived_digest,
            },
        )
    except Exception as exc:
        print(
            json.dumps(
                _payload(
                    "blocked",
                    reason="work-session-reactivate-failed",
                    observed=str(exc),
                    recovery_action="verify archived run payload integrity and workspace write permissions",
                ),
                ensure_ascii=True,
            )
        )
        return 2
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass

    payload = _payload(
        "ok",
        reason="work-session-reactivated",
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        phase=phase,
        next=next_token,
        active_gate=active_gate,
        effective_operating_mode=effective_mode,
        resolved_operating_mode=resolved_mode,
        verify_policy_version=verify_policy_version,
        current_run_pointer=str(pointer_path),
    )
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
