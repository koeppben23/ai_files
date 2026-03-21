#!/usr/bin/env python3
"""Implementation execution rail -- ``/implement`` entrypoint.

This entrypoint is an executor orchestrator plus validator. It does not edit
domain files directly.

Allowed local writes from this entrypoint are limited to governance/session
diagnostics (for example ``.governance/implementation/*``, session state, and
events). Domain/source changes must come from the external LLM executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.contracts.enforcement import require_complete_contracts
from governance_runtime.engine.implementation_validation import (
    CheckResult,
    ExecutorRunResult,
    RC_EXECUTOR_FAILED,
    RC_EXECUTOR_NOT_CONFIGURED,
    RC_TARGETED_CHECKS_MISSING,
    build_plan_coverage,
    split_domain_changed_files,
    to_report_payload,
    validate_implementation,
    write_validation_report,
)
from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.plan_record_state import resolve_plan_record_signal
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)

BLOCKED_IMPLEMENT_START_INVALID = "BLOCKED-UNSPECIFIED"

_SCHEMA_PATH = Path(__file__).absolute().parents[2] / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def _load_mandates_schema() -> dict[str, object] | None:
    """Load the compiled governance mandates schema (JSON). Returns None if unavailable."""
    if not _SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_authoring_mandate_text(schema: dict[str, object]) -> str:
    """Build a plain-text authoring mandate from the compiled JSON schema."""
    dm = schema.get("developer_mandate", {})
    if not isinstance(dm, dict):
        return ""

    lines: list[str] = []

    role = str(dm.get("role", "")).strip()
    if role:
        lines.append(f"Role: {role}")

    posture = dm.get("core_posture", [])
    if posture:
        for item in posture:
            lines.append(f"- {item}")

    evidence = dm.get("evidence_rule", [])
    if evidence:
        lines.append("Evidence rule:")
        for item in evidence:
            lines.append(f"- {item}")

    objectives = dm.get("primary_authoring_objectives", [])
    if objectives:
        lines.append("Authoring objectives:")
        for item in objectives:
            lines.append(f"- {item}")

    lenses = dm.get("authoring_lenses", [])
    if lenses:
        lines.append("Authoring lenses:")
        for lens in lenses:
            if isinstance(lens, dict):
                name = lens.get("name", "")
                body = lens.get("body", [])
                ask = lens.get("ask", [])
                lines.append(f"{len(lines)}. {name}")
                for b in body:
                    lines.append(f"- {b}")
                for a in ask:
                    lines.append(f"  Ask: {a}")

    method = dm.get("authoring_method", [])
    if method:
        lines.append("Authoring method:")
        for item in method:
            lines.append(f"- {item}")

    contract = dm.get("output_contract", {})
    if contract:
        lines.append("Output contract:")
        if isinstance(contract, dict):
            for key, desc in contract.items():
                lines.append(f"- {key}: {desc}")

    decision = dm.get("decision_rules", [])
    if decision:
        lines.append("Decision rules:")
        for item in decision:
            lines.append(f"- {item}")

    addendum = dm.get("governance_addendum", [])
    if addendum:
        lines.append("Governance addendum:")
        for item in addendum:
            lines.append(f"- {item}")

    return "\n".join(lines)


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


def _contracts_path(session_path: Path, state: Mapping[str, object]) -> Path:
    explicit = str(state.get("requirement_contracts_source") or "").strip()
    if explicit:
        candidate = Path(explicit)
        if candidate.is_absolute():
            return candidate
        return session_path.parent / explicit
    return session_path.parent / ".governance" / "contracts" / "compiled_requirements.json"


def _load_compiled_requirements(session_path: Path, state: Mapping[str, object]) -> list[dict[str, object]]:
    path = _contracts_path(session_path, state)
    if not path.exists() or not path.is_file():
        return []
    try:
        payload = _load_json(path)
    except Exception:
        return []
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        return []
    out: list[dict[str, object]] = []
    for item in requirements:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def _extract_hotspot_files(requirements: list[dict[str, object]]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        hotspots = requirement.get("code_hotspots")
        if not isinstance(hotspots, list):
            continue
        for hotspot in hotspots:
            token = str(hotspot or "").strip().replace("\\", "/")
            if not token or token.startswith(".."):
                continue
            if token in seen:
                continue
            seen.add(token)
            files.append(token)
    return files


def _repo_root(session_path: Path, state: Mapping[str, object]) -> Path:
    explicit = str(state.get("RepoRoot") or state.get("repo_root") or "").strip()
    if explicit:
        root = Path(explicit)
        if root.is_absolute() and root.exists() and root.is_dir():
            return root
    if session_path.parent.exists() and session_path.parent.is_dir() and (session_path.parent / ".git").exists():
        return session_path.parent

    identity_map = session_path.parent / "repo-identity-map.yaml"
    if identity_map.exists() and identity_map.is_file():
        try:
            payload = _load_json(identity_map)
            mapped_root = Path(str(payload.get("repoRoot") or "").strip())
            if mapped_root.is_absolute() and mapped_root.exists() and mapped_root.is_dir():
                return mapped_root
        except Exception:
            pass

    if session_path.parent.exists() and session_path.parent.is_dir():
        return session_path.parent
    cwd = Path(os.path.abspath(str(Path.cwd())))
    if (cwd / ".git").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".git").exists():
            return parent
    return session_path.parent


def _parse_changed_files_from_git_status(repo_root: Path) -> list[str]:
    try:
        probe = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if probe.returncode != 0:
        return []
    changed_files: list[str] = []
    for raw in str(probe.stdout or "").splitlines():
        if len(raw) < 4:
            continue
        changed_files.append(raw[3:].strip().replace("\\", "/"))
    return sorted(set(changed_files))


def _has_active_desktop_llm_binding() -> bool:
    if str(os.environ.get("OPENCODE") or "").strip() == "1":
        return True
    binding_tokens = (
        "OPENCODE_MODEL",
        "OPENCODE_MODEL_ID",
        "OPENCODE_MODEL_PROVIDER",
        "OPENCODE_MODEL_CONTEXT_LIMIT",
        "OPENCODE_CLIENT_MODEL",
        "OPENCODE_CLIENT_PROVIDER",
    )
    for key in binding_tokens:
        if str(os.environ.get(key) or "").strip():
            return True
    return False


def _run_llm_edit_step(
    *,
    repo_root: Path,
    state: Mapping[str, object],
    ticket_text: str,
    task_text: str,
    plan_text: str,
    required_hotspots: list[str],
) -> dict[str, object]:
    executor_cmd = str(os.environ.get("OPENCODE_IMPLEMENT_LLM_CMD") or "").strip()
    implementation_dir = repo_root / ".governance" / "implementation"
    implementation_dir.mkdir(parents=True, exist_ok=True)
    context_file = implementation_dir / "llm_edit_context.json"
    stdout_file = implementation_dir / "executor_stdout.log"
    stderr_file = implementation_dir / "executor_stderr.log"

    mandate_text = ""
    schema = _load_mandates_schema()
    if schema:
        mandate_text = _build_authoring_mandate_text(schema)

    context: dict[str, object] = {
        "schema": "opencode.implement.llm-context.v3",
        "ticket": ticket_text,
        "task": task_text,
        "approved_plan": plan_text,
        "required_hotspots": required_hotspots,
        "phase": str(state.get("Phase") or state.get("phase") or ""),
        "active_gate": str(state.get("active_gate") or ""),
        "next_gate_condition": str(state.get("next_gate_condition") or ""),
        "forbidden_paths": [".governance/"],
        "requirements": {
            "domain_diff_required": True,
            "plan_step_coverage_required": True,
            "targeted_checks_required": True,
        },
    }
    if mandate_text:
        context["authoring_mandate"] = mandate_text
        context["instruction"] = (
            "Apply the authoring mandate below to implement approved plan steps. "
            "Build only what can be justified by the plan, contracts, and repository evidence. "
            "Do not limit changes to .governance artifacts."
        )
    else:
        context["instruction"] = (
            "Implement approved plan steps using repository edits. "
            "Do not limit changes to .governance artifacts."
        )
    _write_text_atomic(context_file, json.dumps(context, ensure_ascii=True, indent=2) + "\n")

    if not executor_cmd:
        if _has_active_desktop_llm_binding():
            changed_files = _parse_changed_files_from_git_status(repo_root)
            _write_text_atomic(stdout_file, "Using current OpenCode LLM session as implementation executor.\n")
            _write_text_atomic(stderr_file, "")
            return {
                "executor_invoked": True,
                "exit_code": 0,
                "reason_code": "",
                "message": "",
                "stdout_path": str(stdout_file),
                "stderr_path": str(stderr_file),
                "changed_files": changed_files,
            }
        _write_text_atomic(stdout_file, "")
        _write_text_atomic(stderr_file, "LLM executor command missing\n")
        return {
            "executor_invoked": False,
            "exit_code": 2,
            "reason_code": RC_EXECUTOR_NOT_CONFIGURED,
            "message": "No implementation executor binding available. Set OPENCODE_IMPLEMENT_LLM_CMD or run with an active OpenCode Desktop LLM binding.",
            "stdout_path": str(stdout_file),
            "stderr_path": str(stderr_file),
            "changed_files": [],
        }

    final_cmd = executor_cmd
    if "{context_file}" in final_cmd:
        final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))

    result = subprocess.run(
        final_cmd,
        shell=True,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    _write_text_atomic(stdout_file, str(result.stdout or ""))
    _write_text_atomic(stderr_file, str(result.stderr or ""))

    changed_files = _parse_changed_files_from_git_status(repo_root)
    return {
        "executor_invoked": True,
        "exit_code": int(result.returncode),
        "reason_code": "" if result.returncode == 0 else RC_EXECUTOR_FAILED,
        "message": "" if result.returncode == 0 else str(result.stderr or result.stdout or "").strip(),
        "stdout_path": str(stdout_file),
        "stderr_path": str(stderr_file),
        "changed_files": changed_files,
    }


def _run_targeted_checks(repo_root: Path, requirements: list[dict[str, object]]) -> tuple[tuple[CheckResult, ...], bool]:
    tests: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        acceptance = requirement.get("acceptance_tests")
        if not isinstance(acceptance, list):
            continue
        for item in acceptance:
            token = str(item or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            tests.append(token)

    if not tests:
        return (), False

    command = ["python3", "-m", "pytest", "-q", *tests]
    result = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, check=False)
    output_file = repo_root / ".governance" / "implementation" / "targeted_checks.log"
    output = (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
    _write_text_atomic(output_file, output)
    check_results = tuple(
        CheckResult(
            name=test,
            passed=result.returncode == 0,
            exit_code=int(result.returncode),
            output_path=str(output_file),
        )
        for test in tests
    )
    return check_results, True


def _resolve_active_session_path() -> tuple[Path, Path]:
    resolver = BindingEvidenceResolver(env=os.environ)
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

    enforcement = require_complete_contracts(
        repo_root=Path(__file__).absolute().parents[2],
        required_ids=("R-IMPLEMENT-001",),
    )
    if not enforcement.ok:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"{enforcement.reason}: {';'.join(enforcement.details)}",
        )

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

    contracts_present = bool(state.get("requirement_contracts_present"))
    try:
        contracts_count = int(str(state.get("requirement_contracts_count") or "0").strip())
    except ValueError:
        contracts_count = 0
    if not contracts_present or contracts_count < 1:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires compiled requirement contracts from /plan before execution can start.",
        )

    event_id = uuid.uuid4().hex
    ts = _now_iso()
    plan_record_file = session_path.parent / "plan-record.json"
    plan_text = _latest_plan_text(plan_record_file)
    repo_root = _repo_root(session_path, state)
    compiled_requirements = _load_compiled_requirements(session_path, state)
    required_hotspots = _extract_hotspot_files(compiled_requirements)

    llm_result = _run_llm_edit_step(
        repo_root=repo_root,
        state=state,
        ticket_text=str(state.get("Ticket") or ""),
        task_text=str(state.get("Task") or ""),
        plan_text=plan_text,
        required_hotspots=required_hotspots,
    )

    changed_files_raw = llm_result.get("changed_files")
    changed_files_seq = changed_files_raw if isinstance(changed_files_raw, list) else []
    changed_files = tuple(str(item).strip().replace("\\", "/") for item in changed_files_seq if str(item).strip())
    domain_changed = split_domain_changed_files(
        changed_files,
        forbidden_prefixes=(".governance/",),
    )
    executor_result = ExecutorRunResult(
        executor_invoked=bool(llm_result.get("executor_invoked")),
        exit_code=int(str(llm_result.get("exit_code") or "0")),
        stdout_path=str(llm_result.get("stdout_path") or "") or None,
        stderr_path=str(llm_result.get("stderr_path") or "") or None,
        changed_files=changed_files,
        domain_changed_files=domain_changed,
        governance_only_changes=bool(changed_files) and len(domain_changed) == 0,
    )

    check_results, checks_declared = _run_targeted_checks(repo_root, compiled_requirements)
    if not checks_declared:
        check_results = ()

    plan_coverage = build_plan_coverage(
        requirements=compiled_requirements,
        domain_changed_files=domain_changed,
    )
    forbidden_paths_changed = any(path.startswith(".governance/") for path in domain_changed)
    report = validate_implementation(
        executor_result=executor_result,
        plan_coverage=plan_coverage,
        checks=check_results,
        forbidden_paths_changed=forbidden_paths_changed,
    )

    implementation_dir = repo_root / ".governance" / "implementation"
    implementation_dir.mkdir(parents=True, exist_ok=True)
    report_path = implementation_dir / "implementation_validation_report.json"
    write_validation_report(report_path, report)

    state["implementation_authorized"] = True
    state["implementation_started"] = True
    state["implementation_started_at"] = ts
    state["implementation_started_by"] = actor.strip() or "operator"
    state["implementation_start_note"] = note.strip()
    state["implementation_execution_started"] = True
    state["implementation_validation_report"] = to_report_payload(report)
    state["implementation_validation_report_path"] = str(report_path)
    state["implementation_checks_executed"] = [item.name for item in report.checks]
    state["implementation_checks_ok"] = bool(report.checks) and all(item.passed for item in report.checks)
    state["implementation_changed_files"] = list(report.changed_files)
    state["implementation_domain_changed_files"] = list(report.domain_changed_files)
    state["implementation_required_hotspots"] = required_hotspots
    state["implementation_llm_step_executed"] = report.executor_invoked
    state["implementation_execution_status"] = "review_complete" if report.is_compliant else "blocked"
    state["implementation_status"] = "ready_for_review" if report.is_compliant else "blocked"
    state["implementation_reason_codes"] = list(report.reason_codes)
    state["Next"] = "6"
    state["next"] = "6"

    if report.is_compliant:
        state["active_gate"] = "Implementation Review Complete"
        state["next_gate_condition"] = "Implementation validation passed. Run /continue."
    else:
        state["active_gate"] = "Implementation Blocked"
        reason_text = ", ".join(report.reason_codes) if report.reason_codes else RC_TARGETED_CHECKS_MISSING
        state["next_gate_condition"] = (
            "Implementation validation failed. "
            f"reason_codes={reason_text}. Resolve blockers and rerun /implement."
        )

    _write_json_atomic(session_path, state_doc)

    audit_event: dict[str, object] = {
        "schema": "opencode.implementation-started.v2",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "IMPLEMENTATION_STARTED",
        "phase": phase_text,
        "decision": decision or "approve",
        "plan_record_versions": signal.versions,
        "actor": state["implementation_started_by"],
        "validation": to_report_payload(report),
    }
    if events_path is not None:
        _append_event(events_path, audit_event)

    payload = _payload(
        "ok" if report.is_compliant else "blocked",
        event_id=event_id,
        phase="6-PostFlight",
        next="6",
        active_gate=str(state.get("active_gate") or "Implementation Blocked"),
        next_gate_condition=state["next_gate_condition"],
        implementation_started=True,
        implementation_validation=to_report_payload(report),
        implementation_changed_files=list(report.changed_files),
        implementation_domain_changed_files=list(report.domain_changed_files),
        implementation_checks_executed=[item.name for item in report.checks],
        implementation_checks_ok=bool(report.checks) and all(item.passed for item in report.checks),
        next_action=(
            "run /continue."
            if report.is_compliant
            else "run configured LLM executor, produce domain diffs, satisfy plan coverage, and pass targeted checks."
        ),
    )
    if not report.is_compliant:
        payload["reason_codes"] = list(report.reason_codes)
        if RC_EXECUTOR_NOT_CONFIGURED in report.reason_codes:
            payload["reason_code"] = RC_EXECUTOR_NOT_CONFIGURED
        elif RC_EXECUTOR_FAILED in report.reason_codes:
            payload["reason_code"] = RC_EXECUTOR_FAILED
        else:
            payload["reason_code"] = report.reason_codes[0] if report.reason_codes else "IMPLEMENTATION_VALIDATION_FAILED"
    return payload


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
