#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.engine.sanitization import apply_fresh_start_business_rules_neutralization
from governance_runtime.engine.business_rules_hydration import hydrate_business_rules_state_from_artifacts
from governance_runtime.infrastructure.run_audit_artifacts import purge_runtime_artifacts
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance_runtime.infrastructure.work_run_archive import archive_active_run
from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.json_store import append_jsonl as _append_jsonl
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic

try:
    from governance_runtime.infrastructure.governance_hooks import run_post_archive_governance as _run_post_archive_governance
    _GOVERNANCE_AVAILABLE = True
except Exception:
    _run_post_archive_governance = None  # type: ignore[assignment]
    _GOVERNANCE_AVAILABLE = False
try:
    from governance_runtime.entrypoints.workspace_lock import acquire_workspace_lock
except Exception:
    from workspace_lock import acquire_workspace_lock  # type: ignore



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


def _new_run_id() -> str:
    return f"work-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _canonical_reason(value: str) -> str:
    return " ".join((value or "").strip().split())


def _canonical_session_id(value: str) -> str:
    return " ".join((value or "").strip().split())


def _reset_for_new_work(
    state: dict[str, object],
    *,
    new_run_id: str,
    observed_at: str,
    workspace_path: Path,
) -> None:
    state["session_run_id"] = new_run_id
    state["Ticket"] = None
    state["Task"] = None
    state["TicketRecordDigest"] = None
    state["TaskRecordDigest"] = None
    state["phase4_intake_evidence"] = False
    state["phase4_intake_source"] = "new-work-session"
    state["phase4_intake_updated_at"] = observed_at
    state["phase_transition_evidence"] = False

    state["Phase"] = "4"
    state["phase"] = "4"
    state["Next"] = "4"
    state["next"] = "4"
    state["Mode"] = "IN_PROGRESS"
    state["status"] = "OK"
    state["active_gate"] = "Ticket Input Gate"
    state["next_gate_condition"] = "Collect ticket and planning constraints (or run /review for review-only lead/staff feedback)."
    apply_fresh_start_business_rules_neutralization(state)
    hydrate_business_rules_state_from_artifacts(
        state=state,
        status_path=workspace_path / "business-rules-status.md",
        inventory_path=workspace_path / "business-rules.md",
    )

    gates = state.get("Gates")
    base_gates: dict[str, str] = {
        "P5-Architecture": "pending",
        "P5.3-TestQuality": "pending",
        "P5.4-BusinessRules": "pending",
        "P5.5-TechnicalDebt": "pending",
        "P5.6-RollbackSafety": "pending",
        "P6-ImplementationQA": "pending",
    }
    if isinstance(gates, dict):
        for key, value in base_gates.items():
            gates[key] = value
        state["Gates"] = gates
    else:
        state["Gates"] = base_gates

    for stale_key in (
        "ArchitectureDecisions",
        "TestQualityAssessment",
        "BusinessRulesCompliance",
        "TechnicalDebtRegister",
        "RollbackPlan",
        "ReviewFindings",
        "GateArtifacts",
        "FeatureComplexity",
    ):
        if stale_key in state:
            del state[stale_key]


def _guard_file(workspace_home: Path, repo_fingerprint: str) -> Path:
    return workspace_home / repo_fingerprint / ".new_work_guard.json"


def _check_recent_duplicate(
    guard_path: Path,
    *,
    trigger_source: str,
    session_id: str,
    ttl_seconds: int,
) -> tuple[bool, dict[str, object]]:
    if not session_id or not guard_path.exists():
        return False, {}
    try:
        guard_doc = _load_json(guard_path)
    except Exception:
        return False, {}

    last = guard_doc.get("last")
    if not isinstance(last, dict):
        return False, {}
    if str(last.get("trigger_source") or "") != trigger_source:
        return False, {}
    if str(last.get("session_id") or "") != session_id:
        return False, {}

    observed = str(last.get("observed_at") or "")
    if not observed:
        return False, {}
    try:
        when = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError:
        return False, {}
    age = (datetime.now(timezone.utc) - when).total_seconds()
    if age < 0 or age > ttl_seconds:
        return False, {}
    return True, guard_doc


def _record_guard(
    guard_path: Path,
    *,
    trigger_source: str,
    session_id: str,
    run_id: str,
    observed_at: str,
) -> None:
    payload = {
        "schema": "governance.new-work-guard.v1",
        "last": {
            "trigger_source": trigger_source,
            "session_id": session_id,
            "run_id": run_id,
            "observed_at": observed_at,
        },
    }
    _write_json_atomic(guard_path, payload)


def _state_is_fresh_phase4_run(state: Mapping[str, object], *, run_id: str) -> bool:
    if not run_id:
        return False
    current_run_id = str(state.get("session_run_id") or "").strip()
    if current_run_id != run_id:
        return False

    phase = str(state.get("Phase") or state.get("phase") or "").strip()
    if phase != "4":
        return False

    next_token = str(state.get("Next") or "").strip()
    if next_token != "4":
        return False

    active_gate = str(state.get("active_gate") or "").strip()
    if active_gate != "Ticket Input Gate":
        return False

    intake_evidence = state.get("phase4_intake_evidence")
    if intake_evidence is not False:
        return False

    return True


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a fresh repo-local work run at Phase 4")
    parser.add_argument("--trigger-source", default="cli", help="Trigger source (desktop-plugin|cli|pipeline)")
    parser.add_argument("--reason", default="", help="Optional reason metadata")
    parser.add_argument("--session-id", default="", help="Optional OpenCode session id for dedupe")
    parser.add_argument("--dedupe-window-seconds", type=int, default=8, help="Dedupe time window in seconds")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    trigger_source = (args.trigger_source or "cli").strip() or "cli"
    reason = _canonical_reason(args.reason)
    session_id = _canonical_session_id(args.session_id) or _canonical_session_id(os.environ.get("OPENCODE_SESSION_ID", ""))
    observed_at = _now_iso()

    try:
        session_path, repo_fingerprint, workspaces_home = _resolve_active_session_path()
    except Exception as exc:
        payload = _payload(
            "blocked",
            reason="new-work-session-init-failed",
            observed=str(exc),
            recovery_action="verify binding evidence and active session pointer",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    lock = None
    try:
        lock = acquire_workspace_lock(workspaces_home=workspaces_home, repo_fingerprint=repo_fingerprint)
        document = _load_json(session_path)
        state = document.get("SESSION_STATE")
        if not isinstance(state, dict):
            raise RuntimeError("SESSION_STATE root missing")

        guard_path = _guard_file(workspaces_home, repo_fingerprint)
        is_duplicate, guard_doc = _check_recent_duplicate(
            guard_path,
            trigger_source=trigger_source,
            session_id=session_id,
            ttl_seconds=max(1, int(args.dedupe_window_seconds)),
        )
        if is_duplicate:
            last_guard = guard_doc.get("last")
            last_guard_map = last_guard if isinstance(last_guard, dict) else {}
            run_id = str(last_guard_map.get("run_id") or state.get("session_run_id") or "")
            if not _state_is_fresh_phase4_run(state, run_id=run_id):
                _append_jsonl(
                    session_path.parent / "events.jsonl",
                    {
                        "event": "new_work_session_dedupe_bypassed",
                        "observed_at": observed_at,
                        "repo_fingerprint": repo_fingerprint,
                        "trigger_source": trigger_source,
                        "session_id": session_id,
                        "run_id": run_id,
                        "reason": "state-not-phase4-fresh-run",
                    },
                )
                is_duplicate = False

        if is_duplicate:
            last_guard = guard_doc.get("last")
            last_guard_map = last_guard if isinstance(last_guard, dict) else {}
            run_id = str(last_guard_map.get("run_id") or state.get("session_run_id") or "")
            _append_jsonl(
                session_path.parent / "events.jsonl",
                {
                    "event": "new_work_session_deduped",
                    "observed_at": observed_at,
                    "repo_fingerprint": repo_fingerprint,
                    "trigger_source": trigger_source,
                    "session_id": session_id,
                    "run_id": run_id,
                    "reason": "recent-duplicate-trigger",
                },
            )
            payload = _payload(
                "ok",
                reason="new-work-session-deduped",
                repo_fingerprint=repo_fingerprint,
                session_state_path=str(session_path),
                run_id=run_id,
                phase=str(state.get("Phase") or state.get("phase") or ""),
                next_token=str(state.get("Next") or ""),
                active_gate=str(state.get("active_gate") or ""),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 0

        previous_run_id = str(state.get("session_run_id") or "")
        archive_id = previous_run_id or f"legacy-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        archived = archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
            run_id=archive_id,
            observed_at=observed_at,
            session_state_document=deepcopy(document),
            state_view=deepcopy(state),
            write_json_atomic=_write_json_atomic,
        )

        # --- Governance pipeline hook (post-archive, pre-purge) ---
        if _GOVERNANCE_AVAILABLE and _run_post_archive_governance is not None:
            try:
                _gov_result = _run_post_archive_governance(
                    archive_path=run_dir(workspaces_home, repo_fingerprint, archive_id),
                    repo_fingerprint=repo_fingerprint,
                    run_id=archive_id,
                    observed_at=observed_at,
                    workspace_root=session_path.parent,
                    events_path=session_path.parent / "events.jsonl",
                )
            except Exception:
                pass  # governance hook is fail-open — never blocks session

        purged_runtime_files = purge_runtime_artifacts(session_path.parent)

        new_run_id = _new_run_id()

        _append_jsonl(
            session_path.parent / "events.jsonl",
            {
                "event": "new_work_session_created",
                "observed_at": observed_at,
                "repo_fingerprint": repo_fingerprint,
                "trigger_source": trigger_source,
                "reason": reason,
                "session_id": session_id,
                "previous_run_id": previous_run_id,
                "new_run_id": new_run_id,
                "phase": "4",
                "next": "4",
                "snapshot_path": str(archived.snapshot_path),
                "snapshot_digest": archived.snapshot_digest,
                "runtime_purge_files": purged_runtime_files,
            },
        )

        _reset_for_new_work(
            state,
            new_run_id=new_run_id,
            observed_at=observed_at,
            workspace_path=session_path.parent,
        )
        document["SESSION_STATE"] = state
        _write_json_atomic(session_path, document)
        _record_guard(
            guard_path,
            trigger_source=trigger_source,
            session_id=session_id,
            run_id=new_run_id,
            observed_at=observed_at,
        )
    except Exception as exc:
        try:
            _append_jsonl(
                session_path.parent / "events.jsonl",
                {
                    "event": "new_work_session_init_failed",
                    "observed_at": observed_at,
                    "repo_fingerprint": repo_fingerprint,
                    "trigger_source": trigger_source,
                    "session_id": session_id,
                    "run_id": "",
                    "reason": "new-work-session-init-failed",
                    "error": str(exc),
                },
            )
        except Exception:
            pass
        payload = _payload(
            "blocked",
            reason="new-work-session-init-failed",
            observed=str(exc),
            recovery_action="verify workspace lock/session state and rerun",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass

    payload = _payload(
        "ok",
        reason="new-work-session-created",
        repo_fingerprint=repo_fingerprint,
        session_state_path=str(session_path),
        run_id=str(document["SESSION_STATE"].get("session_run_id") or ""),
        phase="4",
        next_token="4",
        active_gate="Ticket Input Gate",
    )
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
