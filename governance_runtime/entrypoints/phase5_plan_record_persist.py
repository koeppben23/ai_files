#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.application.use_cases.phase_router import route_phase
from governance_runtime.application.use_cases.rework_clarification import consume_rework_clarification_state
from governance_runtime.application.use_cases.session_state_helpers import with_kernel_result
from governance_runtime.contracts.compiler import compile_plan_to_requirements
from governance_runtime.contracts.validator import validate_requirement_contracts
from governance_runtime.domain import reason_codes
from governance_runtime.domain.phase_state_machine import normalize_phase_token
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.plan_record_repository import PlanRecordRepository
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance_runtime.infrastructure.workspace_paths import plan_record_archive_dir, plan_record_path


BLOCKED_P5_PLAN_RECORD_PERSIST = reason_codes.BLOCKED_P5_PLAN_RECORD_PERSIST
_PHASE5_REVIEW_MAX_ITERATIONS = 3
_PHASE5_REVIEW_MIN_ITERATIONS = 1

_MANDATE_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def _load_mandates_schema() -> dict[str, object] | None:
    """Load the compiled governance mandates schema (JSON). Returns None if unavailable."""
    if not _MANDATE_SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_MANDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_review_mandate_text(schema: dict[str, object]) -> str:
    """Build a plain-text review mandate from the compiled JSON schema."""
    rm = schema.get("review_mandate", {})
    if not isinstance(rm, dict):
        return ""

    lines: list[str] = []

    role = str(rm.get("role", "")).strip()
    if role:
        lines.append(f"Role: {role}")

    posture = rm.get("core_posture", [])
    if posture:
        for item in posture:
            lines.append(f"- {item}")

    evidence = rm.get("evidence_rule", [])
    if evidence:
        lines.append("Evidence rule:")
        for item in evidence:
            lines.append(f"- {item}")

    objectives = rm.get("primary_objectives", [])
    if objectives:
        lines.append("Review objectives:")
        for item in objectives:
            lines.append(f"- {item}")

    lenses = rm.get("review_lenses", [])
    if lenses:
        lines.append("Review lenses:")
        for idx, lens in enumerate(lenses, 1):
            if isinstance(lens, dict):
                name = lens.get("name", "")
                body = lens.get("body", [])
                ask = lens.get("ask", [])
                lines.append(f"{idx}. {name}")
                for b in body:
                    lines.append(f"- {b}")
                for a in ask:
                    lines.append(f"  Ask: {a}")

    adversarial = rm.get("adversarial_method", [])
    if adversarial:
        lines.append("Adversarial method:")
        for item in adversarial:
            lines.append(f"- {item}")

    contract = rm.get("output_contract", {})
    if contract:
        lines.append("Output contract:")
        if isinstance(contract, dict):
            for key, desc in contract.items():
                if isinstance(desc, dict):
                    lines.append(f"- {key}:")
                    for subk, subv in desc.items():
                        lines.append(f"  - {subk}: {subv}")
                else:
                    lines.append(f"- {key}: {desc}")

    decision = rm.get("decision_rules", [])
    if decision:
        lines.append("Decision rules:")
        for item in decision:
            lines.append(f"- {item}")

    addendum = rm.get("governance_addendum", [])
    if addendum:
        lines.append("Governance addendum:")
        for item in addendum:
            lines.append(f"- {item}")

    return "\n".join(lines)


def _has_active_desktop_llm_binding() -> bool:
    """Check if active OpenCode Desktop LLM binding is available."""
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


def _get_review_output_schema_text() -> str:
    """Return the review output schema as a JSON string for LLM context."""
    try:
        schema = _load_mandates_schema()
        if schema:
            defs = schema.get("$defs", {})
            for key in defs:
                if key == "reviewOutputSchema":
                    return json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **defs[key]}, indent=2)
    except Exception:
        pass
    return ""


def _call_llm_review(content: str, mandate: str) -> dict[str, object]:
    """Call LLM for review with structured output enforcement."""
    executor_cmd = str(os.environ.get("OPENCODE_IMPLEMENT_LLM_CMD") or "").strip()
    if not executor_cmd:
        return {
            "llm_invoked": False,
            "verdict": "changes_requested",
            "findings": ["No LLM executor configured (OPENCODE_IMPLEMENT_LLM_CMD not set)"],
        }

    review_dir = Path.home() / ".governance" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    context_file = review_dir / "llm_review_context.json"
    stdout_file = review_dir / "llm_review_stdout.log"
    stderr_file = review_dir / "llm_review_stderr.log"

    output_schema_text = _get_review_output_schema_text()
    instruction = (
        "Apply the review mandate to review the provided plan.\n"
        "You MUST respond with valid JSON that conforms to the output schema below.\n"
        "Do NOT include any text outside the JSON object.\n\n"
        "Output schema:\n" + output_schema_text
    )

    context = {
        "schema": "opencode.review.llm-context.v2",
        "content_to_review": content,
        "review_mandate": mandate,
        "instruction": instruction,
    }
    atomic_write_text(context_file, json.dumps(context, ensure_ascii=True, indent=2) + "\n")

    final_cmd = executor_cmd
    if "{context_file}" in final_cmd:
        final_cmd = final_cmd.replace("{context_file}", str(context_file))
    try:
        import subprocess
        result = subprocess.run(
            final_cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        atomic_write_text(stdout_file, str(result.stdout or ""))
        atomic_write_text(stderr_file, str(result.stderr or ""))
        response_text = result.stdout or ""
        if not response_text.strip():
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": ["LLM executor returned empty response"],
            }
        mandates_schema = _load_mandates_schema()
        return _parse_llm_review_response(response_text, mandates_schema=mandates_schema)
    except Exception as exc:
        atomic_write_text(stderr_file, str(exc))
        return {"llm_invoked": False, "error": str(exc), "verdict": "changes_requested", "findings": [f"LLM review failed: {exc}"]}


def _parse_llm_review_response(
    response_text: str,
    mandates_schema: dict[str, object] | None = None,
) -> dict[str, object]:
    """Parse and validate LLM review response against output contract.

    Fail-closed: only structured, schema-valid JSON responses proceed.
    Non-JSON and schema-violating responses are hard-blocked with changes_requested.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "governance_runtime" / "application" / "validators"))
    try:
        from llm_response_validator import validate_review_response
    except Exception:
        validate_review_response = None

    raw_text = response_text.strip()

    if not raw_text:
        return {
            "llm_invoked": True,
            "verdict": "changes_requested",
            "findings": ["LLM returned empty response"],
            "validation_valid": False,
            "validation_violations": ["response-not-structured-json"],
            "raw_response": "",
        }

    parsed_data: dict[str, object] | None = None

    if raw_text.startswith("{"):
        try:
            parsed_data = json.loads(raw_text)
        except json.JSONDecodeError:
            pass

    if parsed_data is None:
        return {
            "llm_invoked": True,
            "verdict": "changes_requested",
            "findings": [f"response-not-structured-json: LLM did not return valid JSON. Received {len(raw_text)} chars starting with: {raw_text[:80]!r}"],
            "validation_valid": False,
            "validation_violations": ["response-not-structured-json"],
            "raw_response": raw_text[:1000],
        }

    if validate_review_response is not None:
        validation = validate_review_response(parsed_data, mandates_schema=mandates_schema)
        if not validation.valid:
            return {
                "llm_invoked": True,
                "verdict": "changes_requested",
                "findings": [f"schema-violation: {v.rule}" for v in validation.violations],
                "validation_valid": False,
                "validation_violations": [v.rule for v in validation.violations],
                "raw_response": raw_text[:1000],
            }

    findings = []
    for f in parsed_data.get("findings", []) or []:
        if isinstance(f, dict):
            findings.append(
                f"[{f.get('severity', '?')}] {f.get('location', '?')}: {f.get('evidence', '')[:100]}"
            )
    return {
        "llm_invoked": True,
        "verdict": parsed_data.get("verdict", "changes_requested"),
        "findings": findings,
        "raw_response": raw_text[:1000],
        "validation_valid": True,
    }




def _phase_token(value: str) -> str:
    token = normalize_phase_token(value)
    return token or ""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _canonicalize_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _append_jsonl(path: Path, event: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(event), ensure_ascii=True, separators=(",", ":")) + "\n")


def _contracts_path(session_path: Path) -> Path:
    return session_path.parent / ".governance" / "contracts" / "compiled_requirements.json"


def _persist_compiled_contracts(
    *,
    session_path: Path,
    compiled: list[dict[str, object]],
    negative_contracts: list[dict[str, object]],
    verification_seed: list[dict[str, object]],
    completion_seed: list[dict[str, object]],
    generated_at: str,
) -> tuple[str, int]:
    payload = {
        "schema": "governance-compiled-requirements.v1",
        "generated_at": generated_at,
        "requirements": compiled,
        "negative_contracts": negative_contracts,
        "verification_seed": verification_seed,
        "completion_seed": completion_seed,
    }
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    path = _contracts_path(session_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, text)
    digest = _digest(text)
    return digest, len(compiled)


def _resolve_active_session_path() -> tuple[Path, str]:
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
    return session_path, fingerprint


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def _as_int(value: object, fallback: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        probe = value.strip()
        if probe.isdigit():
            return int(probe)
    return fallback


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _contains_ticket_or_task_evidence(state: Mapping[str, object]) -> bool:
    fields = (
        "TicketRecordDigest",
        "ticket_record_digest",
        "TaskRecordDigest",
        "task_record_digest",
    )
    for key in fields:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _extract_headings(text: str) -> set[str]:
    headings: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        heading_text = stripped.lstrip("#").strip().lower()
        if heading_text:
            headings.add(heading_text)
    return headings


def _normalize_label(label: str) -> str:
    lowered = label.lower()
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _collect_findings(plan_text: str) -> list[str]:
    section_aliases: dict[str, tuple[str, ...]] = {
        "target-state": ("target-state", "zielbild"),
        "target-flow": ("target-flow", "soll-flow"),
        "state-machine": ("state-machine",),
        "blocker-taxonomy": ("blocker-taxonomy", "blocker-taxonomie"),
        "audit": ("audit",),
        "go-no-go": ("go/no-go",),
    }
    headings = {_normalize_label(entry) for entry in _extract_headings(plan_text)}
    findings: list[str] = []
    for canonical, aliases in section_aliases.items():
        if not any(alias in headings for alias in aliases):
            findings.append(f"missing-section:{canonical}")
    if "reason code" not in plan_text.lower() and "reason_code" not in plan_text.lower():
        findings.append("missing-reason-code-contract")
    return findings


def _template_for_finding(finding: str) -> str:
    if finding.startswith("missing-section:"):
        section = finding.split(":", 1)[1]
        if section == "target-state":
            return "## Target-State\n- `/plan` orchestrates create -> self-review -> revise -> finalize/block without a manual chat loop."
        if section == "target-flow":
            return "## Target-Flow\n1. Persist plan_record vN.\n2. Run the internal self-review loop until the exit criterion is met.\n3. Materialize the official Phase-5 completion status or blocker."  # noqa: E501
        if section == "state-machine":
            return "## State-Machine\n- `plan_persisted`, `self_review_in_progress`, `revision_applied`, `phase5_completed`, `phase5_blocked`."
        if section == "blocker-taxonomy":
            return "## Blocker-Taxonomy\n- A kernel-owned reason_code is required; free text is evidence only, not the primary signal."
        if section == "audit":
            return "## Audit\n- Iteration fields: input_digest, iteration, findings_summary, revision_delta, plan_record_version, outcome, reason_code/completion_status."  # noqa: E501
        if section == "go-no-go":
            return "## Go/No-Go\n- `/plan` returns a final plan or a real blocker without an intermediate stop; max. 3 iterations."
    if finding == "missing-reason-code-contract":
        return "## Reason-Code Contract\n- Blockers must carry a canonical `reason_code`."
    return ""


def _revise_plan(plan_text: str, findings: Sequence[str], iteration: int) -> str:
    revised = plan_text
    additions: list[str] = []
    for finding in findings:
        snippet = _template_for_finding(finding)
        if snippet:
            additions.append(snippet)
    if additions:
        revised = revised.rstrip() + "\n\n" + "\n\n".join(additions)

    # Test hook to guarantee max-iteration hard-stop behavior deterministically.
    if "[[force-drift]]" in plan_text.lower():
        revised = revised.rstrip() + f"\n\n<!-- phase5-review-iteration:{iteration} -->"

    return _canonicalize_text(revised)


def _has_any_llm_executor() -> bool:
    """Check if an explicit LLM executor command is configured.

    Unlike implement_start.py, Phase-5 self-review does NOT fall back to
    Desktop LLM binding (OPENCODE=1). The binding only indicates an
    active Desktop session, not that a callable executor exists. An
    explicit OPENCODE_IMPLEMENT_LLM_CMD is required for deterministic
    behavior in the self-review loop.
    """
    executor_cmd = str(os.environ.get("OPENCODE_IMPLEMENT_LLM_CMD") or "").strip()
    return bool(executor_cmd)


def _run_internal_phase5_self_review(plan_text: str) -> dict[str, object]:
    current_text = _canonicalize_text(plan_text)
    if not current_text:
        return {
            "blocked": True,
            "reason": "empty-plan-after-canonicalization",
            "reason_code": reason_codes.BLOCKED_P5_PLAN_EMPTY,
            "recovery_action": "provide non-empty plan text via --plan-text or --plan-file",
        }

    mandate_text = ""
    schema = _load_mandates_schema()
    if schema:
        mandate_text = _build_review_mandate_text(schema)
    if not mandate_text:
        return {
            "blocked": True,
            "reason": "mandate-schema-unavailable",
            "reason_code": BLOCKED_P5_PLAN_RECORD_PERSIST,
            "recovery_action": "Ensure governance_mandates.v1.schema.json exists at governance_runtime/assets/schemas/. Run scripts/compile_rules.py if rules.md was modified.",
        }

    iteration = 0
    prev_digest = _digest(current_text)
    final_digest = prev_digest
    revision_delta = "none"
    findings_summary: list[str] = []
    audit_rows: list[dict[str, object]] = []
    llm_review_results: list[dict[str, object]] = []
    has_executor = _has_any_llm_executor()

    while iteration < _PHASE5_REVIEW_MAX_ITERATIONS:
        iteration += 1

        llm_result: dict[str, object] = {"llm_invoked": False, "verdict": "changes_requested", "findings": []}
        verdict = "changes_requested"
        findings_list: list[str] = []

        if has_executor:
            llm_result = _call_llm_review(current_text, mandate_text)
            llm_review_results.append(llm_result)
            verdict = str(llm_result.get("verdict", "")).strip().lower()
            llm_findings = llm_result.get("findings", [])
            if isinstance(llm_findings, list):
                findings_list = [str(f) for f in llm_findings]

        mechanical_findings = _collect_findings(current_text)

        combined = findings_list + list(mechanical_findings)
        findings_summary = combined if combined else ["none"]

        if mechanical_findings:
            revised_text = _revise_plan(current_text, mechanical_findings, iteration)
        elif findings_list:
            revision_note = f"\n\n## LLM Review Feedback (Iteration {iteration})\n"
            for f_item in findings_list:
                revision_note += f"- {f_item}\n"
            revised_text = current_text + revision_note
        elif "[[force-drift]]" in plan_text.lower():
            revised_text = current_text + f"\n\n<!-- phase5-review-iteration:{iteration} -->"
        else:
            revised_text = current_text

        current_digest = _digest(revised_text)
        revision_delta = "none" if current_digest == prev_digest else "changed"

        review_met = (
            iteration >= _PHASE5_REVIEW_MAX_ITERATIONS
            or (verdict == "approve" and revision_delta == "none" and iteration >= _PHASE5_REVIEW_MIN_ITERATIONS)
            or (mechanical_findings and iteration >= _PHASE5_REVIEW_MAX_ITERATIONS)
        )
        outcome = "completed" if review_met else "revised"
        completion_status = "phase5-complete" if review_met else "phase5-in-progress"

        audit_rows.append(
            {
                "input_digest": f"sha256:{prev_digest}",
                "iteration": iteration,
                "findings_summary": findings_summary,
                "llm_verdict": verdict,
                "llm_findings_count": len(findings_list),
                "revision_delta": revision_delta,
                "outcome": outcome,
                "completion_status": completion_status,
                "plan_digest": f"sha256:{current_digest}",
            }
        )

        current_text = revised_text
        final_digest = current_digest
        if review_met:
            break
        prev_digest = current_digest

    return {
        "blocked": False,
        "final_plan_text": current_text,
        "iterations": iteration,
        "max_iterations": _PHASE5_REVIEW_MAX_ITERATIONS,
        "min_iterations": _PHASE5_REVIEW_MIN_ITERATIONS,
        "revision_delta": revision_delta,
        "self_review_iterations_met": True,
        "phase5_completed": True,
        "completion_status": "phase5-completed",
        "prev_digest": f"sha256:{prev_digest}",
        "curr_digest": f"sha256:{final_digest}",
        "findings_summary": findings_summary,
        "audit_rows": audit_rows,
        "llm_review_results": llm_review_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist Phase-5 plan record evidence and reroute kernel state")
    parser.add_argument("--plan-text", default="", help="Plan record text input")
    parser.add_argument("--plan-file", default="", help="Path to plan markdown/text file")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        plan_source = args.plan_text
        if args.plan_file:
            plan_source = _read_text(Path(args.plan_file))
    except Exception as exc:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P5_PLAN_RECORD_PERSIST,
            reason="plan-source-unreadable",
            observed=str(exc),
            recovery_action="provide readable --plan-text or valid --plan-file",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    plan_text = _canonicalize_text(plan_source)
    if not plan_text:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P5_PLAN_RECORD_PERSIST,
            reason="missing-plan-record-evidence",
            recovery_action="provide non-empty plan text via --plan-text or --plan-file",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    try:
        session_path, repo_fingerprint = _resolve_active_session_path()
        document = _load_json(session_path)
        state = document.get("SESSION_STATE")
        if not isinstance(state, dict):
            raise RuntimeError("SESSION_STATE root missing")

        phase_before = str(state.get("Phase") or "")

        # /plan may be the directed exit rail from Phase-6 rework clarification.
        # Consume clarification state first, then force deterministic Phase-5
        # plan-record entry to avoid self-looping back into clarification.
        if consume_rework_clarification_state(state, consumed_by="plan", consumed_at=_now_iso()):
            state["Phase"] = "5-ArchitectureReview"
            state["phase"] = "5-ArchitectureReview"
            state["Next"] = "5"
            state["next"] = "5"
            state["active_gate"] = "Plan Record Preparation Gate"
            state["next_gate_condition"] = "Persist plan record evidence"

        mode = str(state.get("Mode") or "IN_PROGRESS")
        phase_for_write = str(state.get("Phase") or phase_before or "5")
        session_run_id = str(state.get("session_run_id") or state.get("SessionRunId") or "")
        plan_digest = _digest(plan_text)

        token_before = _phase_token(str(state.get("Phase") or phase_before))
        if token_before != "5":
            payload = _payload(
                "blocked",
                reason_code=reason_codes.BLOCKED_P5_PHASE_MISMATCH,
                reason="phase5-plan-persist-not-allowed-outside-phase5",
                observed=phase_before,
                recovery_action="run /ticket to enter Phase 5 first, then retry /plan",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        if not _contains_ticket_or_task_evidence(state):
            payload = _payload(
                "blocked",
                reason_code=reason_codes.BLOCKED_P5_TICKET_EVIDENCE_MISSING,
                reason="missing-ticket-intake-evidence",
                recovery_action="persist ticket/task evidence via /ticket before /plan",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        review_result = _run_internal_phase5_self_review(plan_text)
        if review_result.get("blocked") is True:
            payload = _payload(
                "blocked",
                reason_code=str(review_result.get("reason_code") or BLOCKED_P5_PLAN_RECORD_PERSIST),
                reason=str(review_result.get("reason") or "phase5-self-review-blocked"),
                recovery_action=str(review_result.get("recovery_action") or "revise plan input and rerun /plan"),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        final_plan_text = str(review_result.get("final_plan_text") or plan_text)
        review_digest = _digest(final_plan_text)

        compiled = compile_plan_to_requirements(
            plan_text=final_plan_text,
            scope_prefix="PLAN",
            ticket_text=str(state.get("Ticket") or ""),
            task_text=str(state.get("Task") or ""),
        )
        compiled_requirements = [dict(item) for item in compiled.requirements]
        negative_contracts = [dict(item) for item in compiled.negative_contracts]
        verification_seed = [dict(item) for item in compiled.verification_seed]
        completion_seed = [dict(item) for item in compiled.completion_seed]
        contract_validation = validate_requirement_contracts(compiled_requirements)
        if not contract_validation.ok:
            payload = _payload(
                "blocked",
                reason_code=reason_codes.BLOCKED_P5_PLAN_RECORD_PERSIST,
                reason="plan-contract-compilation-failed",
                observed=list(contract_validation.errors),
                recovery_action="revise plan text so atomic requirement contracts validate, then rerun /plan",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        contracts_digest, contracts_count = _persist_compiled_contracts(
            session_path=session_path,
            compiled=compiled_requirements,
            negative_contracts=negative_contracts,
            verification_seed=verification_seed,
            completion_seed=completion_seed,
            generated_at=_now_iso(),
        )

        workspace_home = session_path.parent
        repo = PlanRecordRepository(
            path=plan_record_path(workspace_home.parent, repo_fingerprint),
            archive_dir=plan_record_archive_dir(workspace_home.parent, repo_fingerprint),
        )
        write_result = repo.append_version(
                {
                    "timestamp": _now_iso(),
                    "phase": str(state.get("Phase") or "5-ArchitectureReview"),
                    "session_run_id": session_run_id,
                    "trigger": "phase5-plan-record-rail",
                    "plan_record_text": plan_text,
                    "plan_record_digest": f"sha256:{plan_digest}",
                },
                phase=phase_for_write,
                mode=mode,
                repo_fingerprint=repo_fingerprint,
            )
        if not write_result.ok:
            payload = _payload(
                "blocked",
                reason_code=write_result.reason_code,
                reason=write_result.reason,
                recovery_action="verify active phase is 4/5 and rerun with valid plan evidence",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        latest_version = write_result.version or 1
        if final_plan_text != plan_text:
            revised_write = repo.append_version(
                {
                    "timestamp": _now_iso(),
                    "phase": str(state.get("Phase") or "5-ArchitectureReview"),
                    "session_run_id": session_run_id,
                    "trigger": "phase5-self-review-loop",
                    "plan_record_text": final_plan_text,
                    "plan_record_digest": f"sha256:{review_digest}",
                    "review": {
                        "iterations": _as_int(review_result.get("iterations"), 0),
                        "max_iterations": _as_int(review_result.get("max_iterations"), _PHASE5_REVIEW_MAX_ITERATIONS),
                        "revision_delta": str(review_result.get("revision_delta") or "changed"),
                        "completion_status": str(review_result.get("completion_status") or "phase5-completed"),
                        "findings_summary": _as_list(review_result.get("findings_summary")),
                    },
                },
                phase=phase_for_write,
                mode=mode,
                repo_fingerprint=repo_fingerprint,
            )
            if not revised_write.ok:
                payload = _payload(
                    "blocked",
                    reason_code=reason_codes.BLOCKED_P5_REVIEW_PERSIST_FAILED,
                    reason=revised_write.reason,
                    recovery_action="review loop could not persist revised plan-record evidence; rerun /plan",
                )
                print(json.dumps(payload, ensure_ascii=True))
                return 2
            latest_version = revised_write.version or latest_version

        state["phase5_plan_record_digest"] = f"sha256:{review_digest}"
        state["plan_record_version"] = latest_version
        state["PlanRecordVersion"] = latest_version
        state["phase5_plan_record_updated_at"] = _now_iso()
        state["phase5_plan_record_source"] = "phase5-plan-record-rail"
        state["phase5_completed"] = bool(review_result.get("phase5_completed"))
        state["phase5_state"] = "phase5_completed"
        state["Phase5State"] = "phase5_completed"
        state["phase5_completion_status"] = str(review_result.get("completion_status") or "phase5-completed")
        state["phase5_blocker_code"] = "none"
        state["self_review_iterations_met"] = bool(review_result.get("self_review_iterations_met"))
        state["phase5_self_review_iterations"] = _as_int(review_result.get("iterations"), 0)
        state["phase5_max_review_iterations"] = _as_int(review_result.get("max_iterations"), _PHASE5_REVIEW_MAX_ITERATIONS)
        state["phase5_revision_delta"] = str(review_result.get("revision_delta") or "changed")
        state["requirement_contracts_present"] = contracts_count > 0
        state["requirement_contracts_count"] = contracts_count
        state["requirement_contracts_digest"] = f"sha256:{contracts_digest}"
        state["requirement_contracts_source"] = str(_contracts_path(session_path))
        state["Phase5Review"] = {
            "iteration": _as_int(review_result.get("iterations"), 0),
            "max_iterations": _as_int(review_result.get("max_iterations"), _PHASE5_REVIEW_MAX_ITERATIONS),
            "min_iterations": _as_int(review_result.get("min_iterations"), _PHASE5_REVIEW_MIN_ITERATIONS),
            "prev_plan_digest": str(review_result.get("prev_digest") or f"sha256:{plan_digest}"),
            "curr_plan_digest": str(review_result.get("curr_digest") or f"sha256:{review_digest}"),
            "revision_delta": str(review_result.get("revision_delta") or "changed"),
            "self_review_iterations_met": bool(review_result.get("self_review_iterations_met")),
            "completion_status": str(review_result.get("completion_status") or "phase5-completed"),
        }

        for row in _as_list(review_result.get("audit_rows")):
            if not isinstance(row, Mapping):
                continue
            _append_jsonl(
                session_path.parent / "events.jsonl",
                {
                    "event": "phase5-self-review-iteration",
                    "observed_at": _now_iso(),
                    "repo_fingerprint": repo_fingerprint,
                    "phase": "5-ArchitectureReview",
                    "input_digest": str(row.get("input_digest") or ""),
                    "iteration": _as_int(row.get("iteration"), 0),
                    "findings_summary": _as_list(row.get("findings_summary")),
                    "revision_delta": str(row.get("revision_delta") or "changed"),
                    "plan_record_version": latest_version,
                    "outcome": str(row.get("outcome") or "unknown"),
                    "completion_status": str(row.get("completion_status") or "phase5-in-progress"),
                    "reason_code": "none",
                    "plan_digest": str(row.get("plan_digest") or ""),
                },
            )

        routed = route_phase(
            requested_phase=normalize_phase_token(str(state.get("Phase") or "5")) or "5",
            requested_active_gate=str(state.get("active_gate") or "Plan Record Preparation Gate"),
            requested_next_gate_condition=str(state.get("next_gate_condition") or "Persist plan record evidence"),
            session_state_document=document,
            repo_is_git_root=True,
            live_repo_fingerprint=repo_fingerprint,
        )
        document = dict(
            with_kernel_result(
                document,
                phase=routed.phase,
                next_token=routed.next_token,
                active_gate=routed.active_gate,
                next_gate_condition=routed.next_gate_condition,
                status=routed.status,
                spec_hash=routed.spec_hash,
                spec_path=routed.spec_path,
                spec_loaded_at=routed.spec_loaded_at,
                log_paths=routed.log_paths,
                event_id=routed.event_id,
                plan_record_status=routed.plan_record_status,
                plan_record_versions=routed.plan_record_versions,
            )
        )
        state_after = document.get("SESSION_STATE")
        if isinstance(state_after, dict):
            active_gate_after = str(state_after.get("active_gate") or "").strip().lower()
            if active_gate_after in {
                "business rules validation",
                "technical debt review",
                "rollback safety review",
            }:
                state_after["phase5_completed"] = False
                state_after["phase5_state"] = "phase5-in-progress"
                state_after["Phase5State"] = "phase5-in-progress"
                state_after["phase5_completion_status"] = "phase5-in-progress"
                document["SESSION_STATE"] = state_after
        _write_json_atomic(session_path, document)
        _append_jsonl(
            session_path.parent / "events.jsonl",
            {
                "event": "phase5-plan-record-persisted",
                "observed_at": _now_iso(),
                "repo_fingerprint": repo_fingerprint,
                "phase_before": phase_before,
                "phase_after": routed.phase,
                "plan_record_digest": f"sha256:{review_digest}",
                "plan_record_version": latest_version,
                "source": "phase5-plan-record-rail",
                "phase5_completed": bool(review_result.get("phase5_completed")),
                "self_review_iterations_met": bool(review_result.get("self_review_iterations_met")),
                "self_review_iterations": _as_int(review_result.get("iterations"), 0),
                "phase5_revision_delta": str(review_result.get("revision_delta") or "changed"),
                "requirement_contracts_count": contracts_count,
                "requirement_contracts_digest": f"sha256:{contracts_digest}",
            },
        )
    except Exception as exc:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P5_PLAN_RECORD_PERSIST,
            reason="plan-record-persist-failed",
            observed=str(exc),
            recovery_action="verify active workspace pointer/session and rerun plan persist command",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    payload = _payload(
        "ok",
        reason="phase5-plan-record-persisted",
        repo_fingerprint=repo_fingerprint,
        session_state_path=str(session_path),
        phase_before=phase_before,
        phase_after=routed.phase,
        next_phase=str(routed.phase or ""),
        next_gate=routed.active_gate,
        next_action="run /continue.",
        active_gate=routed.active_gate,
        plan_record_version=latest_version,
        phase5_completed=bool(review_result.get("phase5_completed")),
        self_review_iterations=_as_int(review_result.get("iterations"), 0),
        max_iterations=_as_int(review_result.get("max_iterations"), _PHASE5_REVIEW_MAX_ITERATIONS),
        revision_delta=str(review_result.get("revision_delta") or "changed"),
        self_review_iterations_met=bool(review_result.get("self_review_iterations_met")),
    )
    if args.quiet:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
