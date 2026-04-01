#!/usr/bin/env python3
"""Governance session hydration entry point.

/hydrate is the first session-bound governance step after OpenCode Desktop starts.
It binds the governance runtime to the active OpenCode session, validates the knowledge base,
and prepares the session for productive work.

This command:
1. Checks server reachability
2. Resolves active session (fail-closed if no unique match for project)
3. Validates knowledge base
4. Writes hydration brief to session
5. Persists hydration receipt with artifact-based digest
6. Transitions to Ticket Intake Gate

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

from governance_runtime.infrastructure.session_locator import resolve_active_session_paths
from governance_runtime.infrastructure.json_store import (
    load_json,
    write_json_atomic,
)
from governance_runtime.infrastructure.workspace_paths import (
    repo_map_digest_path,
    workspace_memory_path,
    decision_pack_path,
    business_rules_path,
    governance_runtime_state_dir,
)
from governance_runtime.infrastructure.opencode_server_client import (
    check_server_health,
    ensure_opencode_server_running,
    get_active_session,
    send_session_message,
    ServerNotAvailableError,
    ServerTargetUnreachableError,
    ServerTargetUnhealthyError,
    ServerStartFailedError,
    ServerStartTimeoutError,
    APIError,
)
from governance_runtime.shared.next_action import NextActions


HYDRATION_RECEIPT_SCHEMA = "governance.hydration.receipt.v1"
HYDRATION_STATUS_HYDRATED = "hydrated"
HYDRATION_STATUS_FAILED = "failed"
TICKET_INTAKE_GATE = "Ticket Intake Gate"
CORE_KNOWLEDGE_ARTIFACTS = (
    "repo-map-digest.md",
    "workspace-memory.yaml",
    "decision-pack.md",
)


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
        "active_gate": TICKET_INTAKE_GATE,
        "next_gate_condition": "TicketRecordVersion > 0",
        "next_action": "run /ticket.",
        "next_action_command": "/ticket",
    }


def _compute_artifact_digest(
    repo_fingerprint: str,
    workspaces_home: Path,
) -> str:
    """Compute digest from actual workspace artifacts.

    Uses SHA256 of artifact file contents to create a stable digest
    that changes when workspace knowledge changes.
    """
    hasher = hashlib.sha256()

    artifact_paths = {
        "repo-map-digest.md": repo_map_digest_path(workspaces_home, repo_fingerprint),
        "workspace-memory.yaml": workspace_memory_path(workspaces_home, repo_fingerprint),
        "decision-pack.md": decision_pack_path(workspaces_home, repo_fingerprint),
        "business-rules.md": business_rules_path(workspaces_home, repo_fingerprint),
    }

    for name, path in artifact_paths.items():
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                hasher.update(name.encode("utf-8"))
                hasher.update(b"\0")
                hasher.update(content.encode("utf-8"))
                hasher.update(b"\0")
            except (OSError, UnicodeDecodeError):
                pass

    return hasher.hexdigest()


def _knowledge_base_artifact_paths(workspaces_home: Path, repo_fingerprint: str) -> dict[str, Path]:
    return {
        "repo-map-digest.md": repo_map_digest_path(workspaces_home, repo_fingerprint),
        "workspace-memory.yaml": workspace_memory_path(workspaces_home, repo_fingerprint),
        "decision-pack.md": decision_pack_path(workspaces_home, repo_fingerprint),
        "business-rules.md": business_rules_path(workspaces_home, repo_fingerprint),
    }


def _validate_knowledge_base(workspaces_home: Path, repo_fingerprint: str) -> tuple[bool, list[str], list[str]]:
    artifact_paths = _knowledge_base_artifact_paths(workspaces_home, repo_fingerprint)
    missing_or_empty: list[str] = []
    optional_missing: list[str] = []

    for name in CORE_KNOWLEDGE_ARTIFACTS:
        path = artifact_paths[name]
        if not path.exists():
            missing_or_empty.append(name)
            continue
        try:
            if not path.read_text(encoding="utf-8").strip():
                missing_or_empty.append(name)
        except (OSError, UnicodeDecodeError):
            missing_or_empty.append(name)

    optional_path = artifact_paths["business-rules.md"]
    if not optional_path.exists():
        optional_missing.append("business-rules.md")

    return (len(missing_or_empty) == 0, missing_or_empty, optional_missing)


def _build_hydration_brief(
    repo_root: Path,
    workspaces_home: Path,
    repo_fingerprint: str,
) -> str:
    """Build a comprehensive hydration brief from available knowledge artifacts.

    Creates a detailed working context for the LLM including:
    - Repository identity
    - Architecture summary (repo-map-digest)
    - Workspace memory
    - Decision pack
    - Governance mode
    """
    parts = []

    repo_name = repo_root.name
    parts.append(f"# Governance Hydration Brief\n\n")
    parts.append(f"**Repository:** {repo_name}\n")
    parts.append(f"**Fingerprint:** {repo_fingerprint}\n")
    parts.append(f"**Hydrated:** {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}\n\n")

    parts.append("---\n\n")
    parts.append("## 1. Architecture Summary (repo-map-digest)\n\n")

    repo_map = repo_map_digest_path(workspaces_home, repo_fingerprint)
    if repo_map.exists():
        try:
            content = repo_map.read_text(encoding="utf-8")
            lines = content.split("\n")[:30]
            parts.append("\n".join(lines))
            if len(content.split("\n")) > 30:
                parts.append("\n... (truncated)")
        except (OSError, UnicodeDecodeError) as e:
            parts.append(f"[Error reading repo-map: {e}]")
    else:
        parts.append("*No architecture summary available. Run bootstrap or persistence.*\n")

    parts.append("\n\n## 2. Workspace Memory\n\n")

    workspace_mem = workspace_memory_path(workspaces_home, repo_fingerprint)
    if workspace_mem.exists():
        try:
            content = workspace_mem.read_text(encoding="utf-8")
            lines = content.split("\n")[:20]
            parts.append("\n".join(lines))
            if len(content.split("\n")) > 20:
                parts.append("\n... (truncated)")
        except (OSError, UnicodeDecodeError) as e:
            parts.append(f"[Error reading workspace memory: {e}]")
    else:
        parts.append("*No workspace memory available.*\n")

    parts.append("\n\n## 3. Decision Pack\n\n")

    decision = decision_pack_path(workspaces_home, repo_fingerprint)
    if decision.exists():
        try:
            content = decision.read_text(encoding="utf-8")
            lines = content.split("\n")[:30]
            parts.append("\n".join(lines))
            if len(content.split("\n")) > 30:
                parts.append("\n... (truncated)")
        except (OSError, UnicodeDecodeError) as e:
            parts.append(f"[Error reading decision pack: {e}]")
    else:
        parts.append("*No decision pack available.*\n")

    parts.append("\n\n## 4. Business Rules\n\n")

    business_rules = business_rules_path(workspaces_home, repo_fingerprint)
    if business_rules.exists():
        try:
            content = business_rules.read_text(encoding="utf-8")
            lines = content.split("\n")[:30]
            parts.append("\n".join(lines))
            if len(content.split("\n")) > 30:
                parts.append("\n... (truncated)")
        except (OSError, UnicodeDecodeError) as e:
            parts.append(f"[Error reading business rules: {e}]")
    else:
        parts.append("*Business rules inventory not available (optional in some profiles).*\n")

    parts.append("\n\n## 5. Governance Context\n\n")

    runtime_state = governance_runtime_state_dir(workspaces_home, repo_fingerprint)
    config_path = runtime_state / "governance-config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            mode = config.get("governance", {}).get("mode", "unknown")
            parts.append(f"**Governance Mode:** {mode}\n")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            parts.append("*Governance mode unknown.*\n")
    else:
        parts.append("*No governance config found.*\n")

    parts.append("\n\n---\n\n")
    parts.append("**Next Action:** Run `/ticket` to create a ticket.\n")

    return "".join(parts)


def _persist_hydration_receipt(
    session_path: Path,
    hydrated_session_id: str,
    hydrated_at: str,
    digest: str,
    project_path: str,
    artifact_digest: str,
) -> None:
    receipt = {
        "$schema": HYDRATION_RECEIPT_SCHEMA,
        "hydrated_session_id": hydrated_session_id,
        "hydrated_at": hydrated_at,
        "digest": digest,
        "artifact_digest": artifact_digest,
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
    artifact_digest: str,
) -> None:
    document = load_json(session_path)
    state = document.get("SESSION_STATE", {})

    state["SessionHydration"] = {
        "hydrated_session_id": hydrated_session_id,
        "hydrated_at": hydrated_at,
        "digest": digest,
        "artifact_digest": artifact_digest,
        "status": HYDRATION_STATUS_HYDRATED,
    }
    state["session_hydrated"] = True

    state["phase"] = "4"
    state["active_gate"] = TICKET_INTAKE_GATE
    state["next_gate_condition"] = "TicketRecordVersion > 0"

    document["SESSION_STATE"] = state

    write_json_atomic(session_path, document)


def _is_server_healthy(payload: object) -> bool:
    """Return True only for explicit healthy server responses.

    Expected shape: {"healthy": true, ...}
    """
    if not isinstance(payload, Mapping):
        return False
    return payload.get("healthy") is True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hydrate governance session - bind to OpenCode session and validate knowledge base"
    )
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    parser.add_argument(
        "--project-path",
        default="",
        help="Project path to match session (required for unique session resolution)",
    )
    args = parser.parse_args(argv)

    try:
        session_path, repo_fingerprint, workspaces_home, workspace_dir = resolve_active_session_paths()
    except (ImportError, OSError, RuntimeError) as exc:
        payload = _blocked_payload(
            reason=f"session-state-unreadable: {exc}",
            reason_code="HYDRATION-SESSION-UNAVAILABLE",
            recovery_action="Ensure session state is loadable - run bootstrap first",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    try:
        document = load_json(session_path)
        state = document.get("SESSION_STATE", {})
    except (OSError, json.JSONDecodeError) as exc:
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
    project_path = str(project_path).strip()

    if not project_path:
        payload = _blocked_payload(
            reason="project-path-missing",
            reason_code="HYDRATION-PROJECT-PATH-MISSING",
            recovery_action="Set SESSION_STATE.repo_root or pass --project-path before running /hydrate",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    knowledge_ok, missing_or_empty, optional_missing = _validate_knowledge_base(workspaces_home, repo_fingerprint)
    if not knowledge_ok:
        observed = json.dumps(
            {
                "missing_or_empty": missing_or_empty,
                "optional_missing": optional_missing,
            },
            ensure_ascii=True,
        )
        payload = _blocked_payload(
            reason="knowledge-base-incomplete",
            reason_code="HYDRATION-KNOWLEDGE-BASE-INCOMPLETE",
            recovery_action=(
                "Run bootstrap/persist to generate repo-map-digest.md, workspace-memory.yaml, and decision-pack.md"
            ),
            observed=observed,
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    health_check_skipped = os.environ.get("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "").strip().lower()

    if health_check_skipped not in ("1", "true", "yes"):
        try:
            server_status = ensure_opencode_server_running()
            health = server_status if isinstance(server_status, dict) else {"healthy": False}
            if not _is_server_healthy(health):
                payload = _blocked_payload(
                    reason="server-unhealthy",
                    reason_code="BLOCKED-SERVER-TARGET-UNHEALTHY",
                    recovery_action="Ensure OpenCode Desktop server is healthy at /global/health before running /hydrate",
                    observed=json.dumps(health if isinstance(health, Mapping) else {"health": str(health)}, ensure_ascii=True),
                )
                print(json.dumps(payload, ensure_ascii=True))
                return 2
        except ServerTargetUnhealthyError as exc:
            payload = _blocked_payload(
                reason=f"server-unhealthy: {exc}",
                reason_code="BLOCKED-SERVER-TARGET-UNHEALTHY",
                recovery_action="Stop existing server or fix its health, then retry /hydrate",
                observed=str(exc),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except ServerStartTimeoutError as exc:
            payload = _blocked_payload(
                reason=f"server-start-timeout: {exc}",
                reason_code="BLOCKED-SERVER-START-TIMEOUT",
                recovery_action="Check system resources or start OpenCode Desktop manually: opencode serve",
                observed=str(exc),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except ServerStartFailedError as exc:
            payload = _blocked_payload(
                reason=f"server-start-failed: {exc}",
                reason_code="BLOCKED-SERVER-START-FAILED",
                recovery_action="Ensure OpenCode is installed: opencode serve should be available",
                observed=str(exc),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except ServerNotAvailableError as exc:
            payload = _blocked_payload(
                reason=f"server-unreachable: {exc}",
                reason_code="BLOCKED-SERVER-TARGET-UNREACHABLE",
                recovery_action="Start OpenCode Desktop or run: opencode serve --port <port> --hostname <hostname>",
                observed=str(exc),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except (OSError, RuntimeError) as exc:
            payload = _blocked_payload(
                reason=f"server-error: {exc}",
                reason_code="BLOCKED-SERVER-START-FAILED",
                recovery_action="Check OpenCode Desktop status or start manually: opencode serve",
                observed=str(exc),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

    try:
        active_session = get_active_session(project_path)
        session_id = active_session.get("id", "")
        session_title = active_session.get("title", "")
    except ServerNotAvailableError as exc:
        payload = _blocked_payload(
            reason=f"server-unreachable: {exc}",
            reason_code="HYDRATION-SERVER-UNAVAILABLE",
            recovery_action="Start OpenCode Desktop with configured port, then run /hydrate again",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2
    except APIError as exc:
        payload = _blocked_payload(
            reason=f"session-unavailable: {exc}",
            reason_code="HYDRATION-SESSION-UNAVAILABLE",
            recovery_action="Open a workspace in OpenCode Desktop before running /hydrate",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    if not session_id:
        payload = _blocked_payload(
            reason="no-active-session",
            reason_code="HYDRATION-NO-SESSION",
            recovery_action="Open a workspace in OpenCode Desktop before running /hydrate",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    repo_root = None
    if state.get("repo_root"):
        try:
            repo_root = Path(str(state["repo_root"]))
        except (ValueError, TypeError):
            pass

    if not repo_root:
        try:
            repo_root = Path(os.getcwd())
        except (OSError, ValueError):
            pass

    artifact_digest = ""
    hydration_brief = ""
    if repo_root and workspaces_home and repo_fingerprint:
        try:
            artifact_digest = _compute_artifact_digest(repo_fingerprint, workspaces_home)
        except (OSError, ValueError):
            artifact_digest = ""

        try:
            hydration_brief = _build_hydration_brief(repo_root, workspaces_home, repo_fingerprint)
        except (OSError, ValueError):
            hydration_brief = "# Governance Hydration Brief\n\n(No artifacts available)"

    try:
        send_session_message(hydration_brief, session_id)
    except APIError as exc:
        payload = _blocked_payload(
            reason=f"session-write-failed: {exc}",
            reason_code="HYDRATION-SESSION-WRITE-FAILED",
            recovery_action="Check OpenCode Desktop session status - ensure session is active",
            observed=str(exc),
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    hydrated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256(f"{session_id}:{hydrated_at}:{artifact_digest}".encode()).hexdigest()[:16]

    try:
        _persist_hydration_receipt(
            session_path=session_path,
            hydrated_session_id=session_id,
            hydrated_at=hydrated_at,
            digest=digest,
            artifact_digest=artifact_digest,
            project_path=project_path,
        )
    except (OSError, json.JSONDecodeError) as exc:
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
            artifact_digest=artifact_digest,
        )
    except (OSError, json.JSONDecodeError) as exc:
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
