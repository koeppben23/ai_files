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

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.engine.sanitization import apply_fresh_start_business_rules_neutralization
from governance.engine.business_rules_hydration import hydrate_business_rules_state_from_artifacts
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.work_run_archive import archive_active_run
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
    pointer = _load_json(pointer_path)
    fingerprint = str(pointer.get("activeRepoFingerprint") or "").strip()
    if not fingerprint:
        raise RuntimeError("activeRepoFingerprint missing")

    active_state = str(pointer.get("activeSessionStateFile") or "").strip()
    if active_state:
        session_path = Path(active_state)
    else:
        session_path = evidence.workspaces_home / fingerprint / "SESSION_STATE.json"

    if not session_path.is_absolute():
        raise RuntimeError("activeSessionStateFile must be absolute")
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
    state["Next"] = "5"
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
    if next_token != "5":
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
                "next": "5",
                "snapshot_path": str(archived.snapshot_path),
                "snapshot_digest": archived.snapshot_digest,
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
        next_token="5",
        active_gate="Ticket Input Gate",
    )
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
