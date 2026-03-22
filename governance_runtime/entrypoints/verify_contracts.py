#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance_runtime.verification.runner import run_contract_verification
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.session_locator import resolve_active_session_paths


def _write_json(path: Path, payload: dict[str, object]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")


def _resolve_active_session_path() -> tuple[Path, Path]:
    session_path, _, workspace_dir = resolve_active_session_paths()
    events_path = workspace_dir / "events.jsonl"
    return session_path, events_path
def _append_event(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist contract verification completion matrix")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        session_path, events_path = _resolve_active_session_path()
        state_doc = _load_json(session_path)
        state_obj = state_doc.get("SESSION_STATE")
        state = state_obj if isinstance(state_obj, dict) else state_doc
        repo_root = Path(__file__).absolute().parents[2]

        result = run_contract_verification(repo_root=repo_root)
        ts = _now_iso()
        event_id = f"verify-{uuid.uuid4().hex}"

        matrix = result.get("matrix")
        if not isinstance(matrix, dict):
            matrix = {
                "completion_matrix": [],
                "overall_status": "FAIL",
                "release_blocking_requirements_failed": [],
                "release_blocking_requirements_unverified": [],
            }

        state["completion_matrix"] = matrix
        state["completion_matrix_overall_status"] = str(matrix.get("overall_status") or "FAIL")
        state["completion_matrix_verified_at"] = ts
        state["completion_matrix_receipt"] = {
            "receipt_type": "verification_receipt",
            "requirement_scope": "all-release-blocking",
            "content_digest": str(result.get("merge_reason") or "none"),
            "rendered_at": ts,
            "render_event_id": event_id,
            "gate": str(state.get("active_gate") or "unknown"),
            "session_id": str(state.get("session_run_id") or "unknown-session"),
            "state_revision": str(state.get("session_materialization_event_id") or event_id),
            "source_command": "/verify-contracts",
            "status": str(result.get("status") or "FAIL"),
        }

        _write_json(session_path, state_doc)
        _append_event(
            events_path,
            {
                "schema": "opencode.contract-verification.v1",
                "event": "CONTRACT_VERIFICATION",
                "event_id": event_id,
                "ts_utc": ts,
                "status": str(result.get("status") or "FAIL"),
                "overall_status": str(matrix.get("overall_status") or "FAIL"),
                "merge_allowed": bool(result.get("merge_allowed")),
                "merge_reason": str(result.get("merge_reason") or "unknown"),
            },
        )

        status = "ok" if str(result.get("status") or "FAIL") == "PASS" else "blocked"
        payload = _payload(
            status,
            overall_status=str(matrix.get("overall_status") or "FAIL"),
            merge_allowed=bool(result.get("merge_allowed")),
            merge_reason=str(result.get("merge_reason") or "unknown"),
            next_action=(
                "run /implementation-decision <approve|changes_requested|reject>."
                if status == "ok"
                else "resolve failing or unverified requirements, then run /verify-contracts."
            ),
        )
    except Exception as exc:
        payload = _payload(
            "error",
            reason_code="BLOCKED-UNSPECIFIED",
            message=f"contract verification failed: {exc}",
        )

    print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
