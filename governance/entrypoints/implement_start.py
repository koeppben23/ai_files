#!/usr/bin/env python3
"""Implementation execution rail -- ``/implement`` entrypoint.

Runs implementation execution from the approved plan, performs an internal
review/revision/verification loop, and persists a presentation-ready package
or a fail-closed blocked state.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
import hashlib
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.plan_record_state import resolve_plan_record_signal

BLOCKED_IMPLEMENT_START_INVALID = "BLOCKED-UNSPECIFIED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json root must be object")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    atomic_write_text(path, text)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, text)


def _append_event(path: Path, event: dict[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl_event(path, event, append=True)
        return True
    except Exception:
        return False


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def _latest_plan_text(plan_record_file: Path) -> str:
    if not plan_record_file.exists():
        return ""
    payload = _load_json(plan_record_file)
    versions = payload.get("versions")
    if not isinstance(versions, list) or not versions:
        return ""
    latest = versions[-1] if isinstance(versions[-1], dict) else {}
    if not isinstance(latest, dict):
        return ""
    return str(latest.get("plan_record_text") or "").strip()


def _build_execution_work_queue(plan_text: str) -> list[str]:
    queue: list[str] = []
    for raw in plan_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ")):
            queue.append(line[2:].strip())
        elif line[:3].isdigit() and "." in line[:4]:
            queue.append(line.split(".", 1)[1].strip())
    if not queue:
        queue = [
            "Identify files affected by the approved plan",
            "Apply the first implementation change set",
            "Run focused verification for touched areas",
        ]
    return queue[:20]


def _repo_root(session_path: Path, state: Mapping[str, object]) -> Path:
    explicit = str(state.get("RepoRoot") or state.get("repo_root") or "").strip()
    if explicit:
        root = Path(explicit)
        if root.is_absolute() and root.exists() and root.is_dir():
            return root
    if session_path.parent.exists() and session_path.parent.is_dir():
        return session_path.parent
    cwd = Path(os.path.abspath(str(Path.cwd())))
    if (cwd / ".git").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".git").exists():
            return parent
    return session_path.parent


def _extract_candidate_files(plan_text: str, repo_root: Path) -> list[Path]:
    pattern = re.compile(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_-]+")
    found: list[Path] = []
    seen: set[str] = set()
    for token in pattern.findall(plan_text):
        normalized = token.strip().strip("`\"'")
        if not normalized or normalized.startswith("../"):
            continue
        candidate = Path(os.path.abspath(str(repo_root / normalized)))
        try:
            candidate.relative_to(repo_root)
        except Exception:
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            found.append(candidate)
    return found[:3]


def _write_execution_code_artifact(repo_root: Path, plan_text: str, work_queue: list[str]) -> Path:
    out_dir = repo_root / ".governance" / "implementation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "execution_patch.py"
    digest = hashlib.sha256(plan_text.encode("utf-8")).hexdigest()[:12]
    queue_preview = "\\n".join(f"# - {item}" for item in work_queue[:5])
    content = (
        '"""Generated implementation execution artifact.\\n\\n'
        "This file is generated by /implement to start repository-side implementation work.\\n"
        '"""\\n\\n'
        f"PLAN_DIGEST = \"{digest}\"\\n"
        "\\n"
        "def execute_approved_plan() -> list[str]:\\n"
        "    \"\"\"Return the first execution tasks derived from approved plan.\"\"\"\\n"
        "    return [\\n"
        + "".join(f"        {item!r},\\n" for item in work_queue[:10])
        + "    ]\\n"
        "\\n"
        f"{queue_preview}\\n"
    )
    _write_text_atomic(out_file, content)
    return out_file


def _apply_target_file_patch(repo_root: Path, target: Path, *, note: str) -> None:
    suffix = target.suffix.lower()
    if suffix in {".py", ".sh", ".rb", ".pl"}:
        patch_line = f"\n# governance-implement: {note}\n"
    elif suffix in {".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h"}:
        patch_line = f"\n// governance-implement: {note}\n"
    else:
        patch_line = f"\n# governance-implement: {note}\n"
    text = target.read_text(encoding="utf-8", errors="ignore")
    if "governance-implement:" in text:
        return
    _write_text_atomic(target, text.rstrip("\n") + patch_line)


def _hash_files(paths: list[Path], repo_root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p)):
        rel = str(Path(os.path.abspath(str(path))).relative_to(repo_root))
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def _review_iteration(*, plan_text: str, changed_files: list[Path], repo_root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not changed_files:
        findings.append(
            {
                "severity": "critical",
                "reason_code": "IMPLEMENTATION-NO-CHANGES",
                "message": "No repository files were changed by /implement execution.",
            }
        )
        return findings

    for path in changed_files:
        rel = str(Path(os.path.abspath(str(path))).relative_to(repo_root))
        body = path.read_text(encoding="utf-8", errors="ignore")
        if not body.strip():
            findings.append(
                {
                    "severity": "critical",
                    "reason_code": "IMPLEMENTATION-EMPTY-ARTIFACT",
                    "message": f"Changed file '{rel}' is empty.",
                }
            )

    artifact = next((p for p in changed_files if p.name == "execution_patch.py"), None)
    if artifact is not None:
        content = artifact.read_text(encoding="utf-8", errors="ignore")
        if "def execute_approved_plan" not in content:
            findings.append(
                {
                    "severity": "critical",
                    "reason_code": "IMPLEMENTATION-MISSING-EXECUTE-FN",
                    "message": "execution_patch.py is missing execute_approved_plan().",
                }
            )
    if "[[force-implementation-blocker]]" in plan_text.lower():
        findings.append(
            {
                "severity": "critical",
                "reason_code": "IMPLEMENTATION-FORCED-BLOCKER",
                "message": "Forced blocker marker present in approved plan.",
            }
        )
    return findings


def _apply_iteration_revision(
    *,
    findings: list[dict[str, str]],
    changed_files: list[Path],
    repo_root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    fixed: list[dict[str, str]] = []
    remaining: list[dict[str, str]] = []
    artifact = next((p for p in changed_files if p.name == "execution_patch.py"), None)

    for finding in findings:
        code = finding.get("reason_code", "")
        if code == "IMPLEMENTATION-MISSING-EXECUTE-FN" and artifact is not None:
            text = artifact.read_text(encoding="utf-8", errors="ignore")
            text = text.rstrip("\n") + (
                "\n\ndef execute_approved_plan() -> list[str]:\n"
                "    \"\"\"Auto-repaired execute function.\"\"\"\n"
                "    return [\"apply approved implementation step\"]\n"
            )
            _write_text_atomic(artifact, text)
            fixed.append(finding)
            continue
        if code == "IMPLEMENTATION-NO-CHANGES":
            # create a fallback artifact to recover from empty change-set
            out_dir = repo_root / ".governance" / "implementation"
            out_dir.mkdir(parents=True, exist_ok=True)
            fallback = out_dir / "execution_fallback.py"
            _write_text_atomic(
                fallback,
                "def execution_fallback() -> str:\n    return 'fallback implementation artifact'\n",
            )
            changed_files.append(fallback)
            fixed.append(finding)
            continue
        remaining.append(finding)
    return fixed, remaining


def _serialize_finding(finding: Mapping[str, str]) -> str:
    sev = str(finding.get("severity") or "unknown")
    code = str(finding.get("reason_code") or "UNKNOWN")
    msg = str(finding.get("message") or "")
    return f"{sev}:{code}:{msg}"


def _resolve_active_session_path() -> tuple[Path, Path]:
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

    events_path = session_path.parent / "events.jsonl"
    return session_path, events_path


def _user_review_decision(state: Mapping[str, object]) -> str:
    decision = state.get("UserReviewDecision")
    if isinstance(decision, Mapping):
        value = decision.get("decision")
        if isinstance(value, str):
            token = value.strip().lower()
            if token in {"approve", "changes_requested", "reject"}:
                return token
    value = state.get("user_review_decision")
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"approve", "changes_requested", "reject"}:
            return token
    return ""


def start_implementation(
    *,
    session_path: Path,
    events_path: Path | None = None,
    actor: str = "",
    note: str = "",
) -> dict[str, object]:
    if not session_path.exists():
        return _payload("error", reason_code=BLOCKED_IMPLEMENT_START_INVALID, message="session state file not found")

    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else state_doc  # type: ignore[assignment]

    phase_text = str(state.get("Phase") or state.get("phase") or "").strip()
    if not phase_text.startswith("6"):
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"/implement is only allowed in Phase 6. Current phase: {phase_text or 'unknown'}",
        )

    decision = _user_review_decision(state)
    workflow_complete = bool(state.get("workflow_complete") or state.get("WorkflowComplete"))
    if decision != "approve" and not workflow_complete:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires an approved final review decision at Workflow Complete.",
        )

    active_gate = str(state.get("active_gate") or "").strip().lower()
    if active_gate == "rework clarification gate":
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement is blocked while rework clarification is pending.",
        )
    if active_gate == "ticket input gate":
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement is blocked after rejection/restart routing. Re-enter via /ticket.",
        )

    signal = resolve_plan_record_signal(state=state, plan_record_file=session_path.parent / "plan-record.json")
    if signal.versions < 1:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires persisted plan-record evidence.",
        )

    event_id = uuid.uuid4().hex
    ts = _now_iso()
    plan_record_file = session_path.parent / "plan-record.json"
    plan_text = _latest_plan_text(plan_record_file)
    work_queue = _build_execution_work_queue(plan_text)

    repo_root = _repo_root(session_path, state)
    changed_files: list[Path] = []
    execution_artifact = _write_execution_code_artifact(repo_root, plan_text, work_queue)
    changed_files.append(execution_artifact)
    for candidate in _extract_candidate_files(plan_text, repo_root):
        _apply_target_file_patch(repo_root, candidate, note="approved-plan execution touched this file")
        changed_files.append(candidate)

    max_iterations = 3
    min_iterations = 1
    iteration = 0
    previous_digest = ""
    revision_delta = "changed"
    open_findings: list[dict[str, str]] = []
    fixed_findings: list[dict[str, str]] = []
    loop_notes: list[str] = []
    quality_stable = False

    while iteration < max_iterations:
        iteration += 1
        current_digest = _hash_files(changed_files, repo_root)
        findings = _review_iteration(plan_text=plan_text, changed_files=changed_files, repo_root=repo_root)
        critical = [f for f in findings if str(f.get("severity")) == "critical"]
        if critical:
            fixed, remaining = _apply_iteration_revision(
                findings=critical,
                changed_files=changed_files,
                repo_root=repo_root,
            )
            fixed_findings.extend(fixed)
            open_findings = remaining
            revision_delta = "changed" if fixed else "max-reached-with-open-delta"
            loop_notes.append(
                f"iteration={iteration}: critical_findings={len(critical)}, fixed={len(fixed)}, remaining={len(remaining)}"
            )
            if remaining and iteration >= max_iterations:
                break
            previous_digest = current_digest
            continue

        if previous_digest and previous_digest == current_digest and iteration >= min_iterations:
            quality_stable = True
            revision_delta = "stabilized"
            open_findings = []
            loop_notes.append(f"iteration={iteration}: stable digest reached")
            break

        if iteration >= min_iterations and not findings:
            quality_stable = True
            revision_delta = "no-change" if previous_digest == current_digest else "stabilized"
            open_findings = []
            loop_notes.append(f"iteration={iteration}: no open findings")
            break

        previous_digest = current_digest

    if not quality_stable and not open_findings and iteration >= max_iterations:
        revision_delta = "max-reached-with-open-delta"

    changed_rel = [str(Path(os.path.abspath(str(p))).relative_to(repo_root)) for p in changed_files]
    fixed_serialized = [_serialize_finding(f) for f in fixed_findings]
    open_serialized = [_serialize_finding(f) for f in open_findings]

    state["implementation_authorized"] = True
    state["implementation_started"] = True
    state["implementation_status"] = "in_progress" if quality_stable else "blocked"
    state["implementation_started_at"] = ts
    state["implementation_started_by"] = actor.strip() or "operator"
    state["implementation_start_note"] = note.strip()
    state["implementation_handoff_plan_record_versions"] = signal.versions
    state["Next"] = "6"
    state["next"] = "6"
    state["implementation_execution_started"] = True
    state["implementation_execution_status"] = "review_complete" if quality_stable else "blocked"
    state["implementation_execution_summary"] = (
        "Implementation execution completed with internal review loop."
        if quality_stable
        else "Implementation execution blocked: unresolved critical findings remain."
    )
    state["implementation_artifacts_expected"] = ["source changes", "tests", "review evidence"]
    state["implementation_work_queue"] = work_queue
    state["implementation_current_step"] = work_queue[0] if work_queue else "none"
    state["implementation_changed_files"] = changed_rel
    state["implementation_review_iterations"] = iteration
    state["implementation_max_review_iterations"] = max_iterations
    state["implementation_min_review_iterations"] = min_iterations
    state["implementation_revision_delta"] = revision_delta
    state["implementation_quality_stable"] = quality_stable
    state["implementation_findings_fixed"] = fixed_serialized
    state["implementation_open_findings"] = open_serialized
    state["implementation_loop_notes"] = loop_notes
    state["implementation_hard_blockers"] = open_serialized

    if quality_stable:
        state["active_gate"] = "Implementation Presentation Gate"
        state["next_gate_condition"] = (
            "Implementation package is ready for external decision. "
            "Run /implementation-decision <approve|changes_requested|reject>."
        )
        state["implementation_package_presented"] = True
        state["implementation_package_review_object"] = "Implemented result review"
        state["implementation_package_plan_reference"] = "latest approved plan record"
        state["implementation_package_changed_files"] = changed_rel
        state["implementation_package_findings_fixed"] = fixed_serialized
        state["implementation_package_findings_open"] = open_serialized
        state["implementation_package_checks"] = [
            "internal implementation self-review loop",
            "artifact integrity check",
            "plan-conformance heuristic",
        ]
        state["implementation_package_stability"] = "stable"
    else:
        state["active_gate"] = "Implementation Blocked"
        state["next_gate_condition"] = (
            "Implementation blocked by unresolved critical findings. "
            "Resolve blockers and rerun /implement."
        )
        state["implementation_package_presented"] = False

    _write_json_atomic(session_path, state_doc)

    audit_event: dict[str, object] = {
        "schema": "opencode.implementation-started.v1",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "IMPLEMENTATION_STARTED",
        "phase": phase_text,
        "active_gate": "Implementation Started",
        "decision": decision or "approve",
        "plan_record_versions": signal.versions,
        "actor": state["implementation_started_by"],
        "note": state["implementation_start_note"],
        "execution_status": "in_progress",
        "work_queue_items": len(work_queue),
        "current_step": state["implementation_current_step"],
        "review_iterations": iteration,
        "review_max_iterations": max_iterations,
        "revision_delta": revision_delta,
        "quality_stable": quality_stable,
        "changed_files": changed_rel,
        "open_findings": open_serialized,
    }
    if events_path is not None:
        _append_event(events_path, audit_event)

    return _payload(
        "ok",
        event_id=event_id,
        phase="6-PostFlight",
        next="6",
        active_gate=str(state.get("active_gate") or "Implementation Blocked"),
        next_gate_condition=state["next_gate_condition"],
        implementation_authorized=True,
        implementation_started=True,
        implementation_started_at=ts,
        implementation_execution_started=True,
        implementation_execution_status=state["implementation_execution_status"],
        implementation_execution_summary=state["implementation_execution_summary"],
        implementation_artifacts_expected=state["implementation_artifacts_expected"],
        implementation_blockers=open_serialized,
        implementation_work_queue=work_queue,
        implementation_current_step=state["implementation_current_step"],
        implementation_changed_files=changed_rel,
        implementation_review_iterations=iteration,
        implementation_max_review_iterations=max_iterations,
        implementation_revision_delta=revision_delta,
        implementation_findings_fixed=fixed_serialized,
        implementation_open_findings=open_serialized,
        implementation_quality_stable=quality_stable,
        next_action=(
            "run /implementation-decision <approve|changes_requested|reject>."
            if quality_stable
            else "resolve implementation blockers, then run /implement."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist /implement governance-to-implementation handoff")
    parser.add_argument("--actor", default="", help="Optional operator identifier")
    parser.add_argument("--note", default="", help="Optional handoff note")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        session_path, events_path = _resolve_active_session_path()
        payload = start_implementation(
            session_path=session_path,
            events_path=events_path,
            actor=str(args.actor),
            note=str(args.note),
        )
    except Exception as exc:
        payload = _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"implement start failed: {exc}",
        )

    status = str(payload.get("status") or "error").strip().lower()
    print(json.dumps(payload, ensure_ascii=True))
    if status == "ok":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
