#!/usr/bin/env python3
"""Governance session hydration entry point.

/hydrate is the first session-bound governance step after OpenCode Desktop starts.
It binds the governance runtime to the active OpenCode session, validates the knowledge base,
and prepares the session for productive work.

This command:
1. Checks server reachability
2. Resolves active session
3. Validates knowledge base
4. Writes hydration brief to session
5. Persists hydration receipt
6. Opens ticket gate

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from governance_runtime.infrastructure.session_pointer import (
    resolve_active_session_state_path,
)
from governance_runtime.infrastructure.session_locator import resolve_active_session_paths
from governance_runtime.infrastructure.json_store import (
    load_json,
    write_json_atomic,
)
from governance_runtime.application.services.state_accessor import get_phase
from governance_runtime.infrastructure.opencode_server_client import (
    check_server_health,
    get_active_session,
    send_session_message,
    ServerNotAvailableError,
    APIError,
)
from governance_runtime.shared.next_action import NextActions


HYDRATION_RECEIPT_SCHEMA = "governance.hydration.receipt.v1"
HYDRATION_STATUS_HYDRATED = "hydrated"
HYDRATION_STATUS_FAILED = "failed"


def _blocked_payload(
    reason: str,
    reason_code: str,
    recovery_action: str,
    observed: str = "",
) -> dict[str, Any]:
    return {
        "blocked": True,
        "status": "blocked",
        "reason": reason,
        "reason_code": reason_code,
        "recovery_action": recovery_action,
        "next_action": "run /hydrate.",
        "next_action_command": "/hydrate",
        "observed": observed,
    }


def _success_payload(
    hydrated_session_id: str,
    hydrated_at: str,
    digest: str,
) -> dict[str, Any]:
    return {
        "blocked": False,
        "status": "success",
        "hydrated_session_id": hydrated_session_id,
        "hydrated_at": hydrated_at,
        "digest": digest,
        "phase": "4",
        "next": "Ticket Intake Gate",
        "active_gate": "Ticket Intake Gate",
        "next_gate_condition": "TicketRecordVersion > 0",
        "next_action": "run /ticket.",
        "next_action_command": "/ticket",
    }


def _build_hydration_brief(
    repo_root: Path,
    workspace_dir: Path,
) -> str:
    """Build a compact hydration brief from available knowledge artifacts."""
    parts = []

    repo_name = repo_root.name
    parts.append(f"# Governance Hydration Brief\n")
    parts.append(f"**Repository:** {repo_name}\n")
    parts.append(f"**Hydrated:** {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}\n\n")

    parts.append("## Known Artifacts\n")

    artifact_paths = [
        ("REPO_MAP", workspace_dir / "repo-map.json"),
        ("DECISION_PACK", workspace_dir / "decision-pack.json"),
        ("BUSINESS_RULES", workspace_dir / "business-rules-status.json"),
        ("API_INVENTORY", workspace_dir / "api-inventory.json"),
    ]

    found_count = 0
    for name, path in artifact_paths:
        if path.exists():
            try:
                data = load_json(path)
                count = len(data.get("items", []) if isinstance(data, dict) else data)
                parts.append(f"- {name}: {count} items")
                found_count += 1
            except Exception:
                parts.append(f"- {name}: present (parse error)")
                found_count += 1
        else:
            parts.append(f"- {name}: not found")

    parts.append(f"\n**Coverage:** {found_count}/{len(artifact_paths)} artifacts\n")

    return "".join(parts)


def _persist_hydration_receipt(
    session_path: Path,
    hydrated_session_id: str,
    hydrated_at: str,
    digest: str,
    project_path: str,
) -> None:
    receipt = {
        "$schema": HYDRATION_RECEIPT_SCHEMA,
        "hydrated_session_id": hydrated_session_id,
        "hydrated_at": hydrated_at,
        "digest": digest,
        "project_path": project_path,
        "status": HYDRATION_STATUS_HYDRATED,
    }

    receipts_dir = session_path.parent / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    receipt_path = receipts_dir / f"hydration-{hydrated_session_id}.json"
    write_json_atomic(receipt_path, receipt)


def _update_session_state_for_hydration(
    session_path: Path,
    hydrated_session_id: str,
    hydrated_at: str,
    digest: str,
) -> None:
    document = load_json(session_path)
    state = document.get("SESSION_STATE", {})

    state["SessionHydration"] = {
        "hydrated_session_id": hydrated_session_id,
        "hydrated_at": hydrated_at,
        "digest": digest,
        "status": HYDRATION_STATUS_HYDRATED,
    }

    current_phase = get_phase(state)
    if current_phase not in ("4", 4):
        state["phase"] = "4"
    if not state.get("active_gate"):
        state["active_gate"] = "Ticket Intake Gate"

    document["SESSION_STATE"] = state

    write_json_atomic(session_path, document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hydrate governance session - bind to OpenCode session and validate knowledge base"
    )
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    parser.add_argument(
        "--project-path",
        default="",
        help="Project path to match session (defaults to repo root from session state)",
    )
    args = parser.parse_args(argv)

    try:
        session_path, repo_fingerprint, workspaces_home, workspace_dir = resolve_active_session_paths()
    except Exception as exc:
        payload = _blocked_payload(
            reason=f"session-state-unreadable: {exc}",
            reason_code="HYDRATION-SESSION-UNAVAILABLE",
            recovery_action="Ensure session state is loadable",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    try:
        document = load_json(session_path)
        state = document.get("SESSION_STATE", {})
    except Exception as exc:
        payload = _blocked_payload(
            reason=f"session-state-corrupt: {exc}",
            reason_code="HYDRATION-SESSION-CORRUPT",
            recovery_action="Ensure session state is valid JSON",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    project_path = args.project_path
    if not project_path:
        project_path = str(state.get("repo_root") or "")

    health_check_skipped = os.environ.get("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "").strip().lower()

    if health_check_skipped not in ("1", "true", "yes"):
        try:
            health = check_server_health()
        except ServerNotAvailableError as exc:
            payload = _blocked_payload(
                reason=f"server-unreachable: {exc}",
                reason_code="HYDRATION-SERVER-UNAVAILABLE",
                recovery_action="Start OpenCode Desktop or run: opencode serve --port 4096",
                observed=str(exc),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except Exception as exc:
            payload = _blocked_payload(
                reason=f"server-error: {exc}",
                reason_code="HYDRATION-SERVER-ERROR",
                recovery_action="Check OpenCode Desktop status",
                observed=str(exc),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

    try:
        active_session = get_active_session(project_path if project_path else None)
        session_id = active_session.get("id", "")
        session_title = active_session.get("title", "")
    except ServerNotAvailableError as exc:
        payload = _blocked_payload(
            reason=f"server-unreachable: {exc}",
            reason_code="HYDRATION-SERVER-UNAVAILABLE",
            recovery_action="Start OpenCode Desktop or run: opencode serve --port 4096",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2
    except APIError as exc:
        payload = _blocked_payload(
            reason=f"session-unavailable: {exc}",
            reason_code="HYDRATION-SESSION-UNAVAILABLE",
            recovery_action="Start a session in OpenCode Desktop before running /hydrate",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    if not session_id:
        payload = _blocked_payload(
            reason="no-active-session",
            reason_code="HYDRATION-NO-SESSION",
            recovery_action="Start a session in OpenCode Desktop before running /hydrate",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    repo_root = None
    if state.get("repo_root"):
        try:
            repo_root = Path(str(state["repo_root"]))
        except Exception:
            pass

    if not repo_root:
        try:
            repo_root = Path(os.getcwd())
        except Exception:
            pass

    hydration_brief = ""
    if repo_root and workspace_dir:
        try:
            hydration_brief = _build_hydration_brief(repo_root, workspace_dir)
        except Exception:
            hydration_brief = "# Governance Hydration Brief\n\n(No artifacts available)"

    try:
        send_session_message(hydration_brief, session_id)
    except APIError as exc:
        payload = _blocked_payload(
            reason=f"session-write-failed: {exc}",
            reason_code="HYDRATION-SESSION-WRITE-FAILED",
            recovery_action="Check OpenCode Desktop session status",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    hydrated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256(f"{session_id}:{hydrated_at}".encode()).hexdigest()[:16]

    try:
        _persist_hydration_receipt(
            session_path=session_path,
            hydrated_session_id=session_id,
            hydrated_at=hydrated_at,
            digest=digest,
            project_path=project_path,
        )
    except Exception as exc:
        payload = _blocked_payload(
            reason=f"receipt-persist-failed: {exc}",
            reason_code="HYDRATION-RECEIPT-FAILED",
            recovery_action="Check workspace write permissions",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    try:
        _update_session_state_for_hydration(
            session_path=session_path,
            hydrated_session_id=session_id,
            hydrated_at=hydrated_at,
            digest=digest,
        )
    except Exception as exc:
        payload = _blocked_payload(
            reason=f"state-update-failed: {exc}",
            reason_code="HYDRATION-STATE-UPDATE-FAILED",
            recovery_action="Check session state write permissions",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    payload = _success_payload(
        hydrated_session_id=session_id,
        hydrated_at=hydrated_at,
        digest=digest,
    )

    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
