"""Phase-6 Review Orchestrator.

Encapsulates the Phase-6 internal review loop, LLM invocation,
response validation, policy loading, and mandate building.

Extracted from session_reader.py to isolate review-loop logic from
session rendering and snapshot building.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from governance_runtime.infrastructure.json_store import append_jsonl, load_json, write_json_atomic
from governance_runtime.infrastructure.number_utils import coerce_int as _coerce_int
from governance_runtime.infrastructure.text_utils import safe_str as _safe_str
from governance_runtime.infrastructure.text_utils import sha256_text as _sha256_text
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso

# ---------------------------------------------------------------------------
# Schema / version constants
# ---------------------------------------------------------------------------
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "governance_runtime"
    / "assets"
    / "schemas"
    / "governance_mandates.v1.schema.json"
)

BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE = "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"


def _derive_commands_home() -> Path | None:
    """Resolve commands_home in strict dual-root order.

    Priority:
    1) COMMANDS_HOME env override
    2) OPENCODE_CONFIG_ROOT + /commands
    3) Binding evidence resolver (governance.paths.json) with env=os.environ
    4) Canonical OS default ~/.config/opencode/commands
    """
    env_commands = os.environ.get("COMMANDS_HOME", "").strip()
    if env_commands:
        try:
            return Path(env_commands).expanduser().resolve()
        except Exception:
            pass

    env_config = os.environ.get("OPENCODE_CONFIG_ROOT", "").strip()
    if env_config:
        try:
            candidate = (Path(env_config).expanduser().resolve() / "commands").resolve()
            if candidate.exists():
                return candidate
        except Exception:
            pass

    try:
        from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver

        evidence = BindingEvidenceResolver(env=os.environ).resolve(mode="kernel")
        if evidence.commands_home is not None:
            return evidence.commands_home
    except Exception:
        pass

    try:
        default_home = Path("~/.config/opencode/commands").expanduser().resolve()
        if default_home.exists():
            return default_home
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Mandate helpers
# ---------------------------------------------------------------------------

def load_mandates_schema() -> dict[str, object] | None:
    """Load the governance_mandates.v1.schema.json, or None."""
    if not _SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_review_output_schema_text() -> str:
    """Extract the reviewOutputSchema JSON text from the mandates schema."""
    schema = load_mandates_schema()
    if schema:
        try:
            defs = schema.get("$defs", {})
            for key in defs:
                if key == "reviewOutputSchema":
                    return json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **defs[key]}, indent=2)
        except Exception:
            pass
    return ""


def build_review_mandate_text(schema: dict[str, object]) -> str:
    """Build a human-readable review mandate text from the mandates schema."""
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

    method = rm.get("adversarial_method", [])
    if method:
        lines.append("Adversarial method:")
        for item in method:
            lines.append(f"- {item}")

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


# ---------------------------------------------------------------------------
# LLM executor helpers
# ---------------------------------------------------------------------------

def has_any_llm_executor() -> bool:
    """Return True if OPENCODE_IMPLEMENT_LLM_CMD is configured."""
    executor = str(os.environ.get("OPENCODE_IMPLEMENT_LLM_CMD") or "").strip()
    return bool(executor)


def load_effective_review_policy_text(
    state: Mapping[str, object],
    commands_home: Path,
) -> tuple[str, str]:
    """Load and format effective review policy for Phase 6 LLM injection.

    Returns (policy_text, error_code). error_code is empty on success.
    Fail-closed: returns error_code if policy cannot be built.
    """
    from governance_runtime.application.use_cases.build_effective_llm_policy import (
        BLOCKED_EFFECTIVE_POLICY_EMPTY,
        BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID,
        BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED,
        BLOCKED_RULEBOOK_CONTENT_UNLOADABLE,
        EffectivePolicyInput,
        build_effective_llm_policy,
        format_review_policy_for_llm,
    )

    lrb: dict[str, object] = {}
    addons_ev: dict[str, object] = {}
    active_profile = "profile.fallback-minimum"

    state_obj = state
    if isinstance(state, dict):
        nested = state.get("SESSION_STATE")
        if isinstance(nested, dict):
            state_obj = nested
    if isinstance(state_obj, dict):
        lrb_raw = state_obj.get("LoadedRulebooks")
        if isinstance(lrb_raw, dict):
            lrb = lrb_raw
        addons_ev_raw = state_obj.get("AddonsEvidence")
        if isinstance(addons_ev_raw, dict):
            addons_ev = addons_ev_raw
        active_profile = str(
            state_obj.get("ActiveProfile")
            or state_obj.get("active_profile")
            or "profile.fallback-minimum"
        ).strip()

    if not lrb:
        return "", BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "governance_runtime"
        / "assets"
        / "schemas"
        / "effective_llm_policy.v1.schema.json"
    )
    compiled_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    try:
        input_data = EffectivePolicyInput(
            active_profile=active_profile,
            loaded_rulebooks=lrb,
            addons_evidence=addons_ev,
            commands_home=commands_home,
            schema_path=schema_path,
            compiled_at=compiled_at,
        )
        result = build_effective_llm_policy(input_data)
        policy_text = format_review_policy_for_llm(result.policy.review_policy)
        return policy_text, ""
    except (
        BLOCKED_RULEBOOK_CONTENT_UNLOADABLE,
        BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED,
        BLOCKED_EFFECTIVE_POLICY_EMPTY,
        BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID,
    ):
        return "", BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE
    except Exception:
        return "", BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE


def call_llm_impl_review(
    *,
    ticket: str,
    task: str,
    plan_text: str,
    implementation_summary: str,
    mandate: str,
    effective_review_policy: str = "",
) -> dict[str, object]:
    """Invoke the LLM executor for implementation review and parse the response."""
    executor_cmd = str(os.environ.get("OPENCODE_IMPLEMENT_LLM_CMD") or "").strip()
    if not executor_cmd:
        return {
            "llm_invoked": False,
            "verdict": "changes_requested",
            "findings": ["No LLM executor configured (OPENCODE_IMPLEMENT_LLM_CMD not set)"],
        }

    review_dir = Path.home() / ".governance" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    context_file = review_dir / "llm_impl_review_context.json"
    stdout_file = review_dir / "llm_impl_review_stdout.log"
    stderr_file = review_dir / "llm_impl_review_stderr.log"

    output_schema_text = get_review_output_schema_text()
    if not output_schema_text:
        return {
            "llm_invoked": False,
            "verdict": "changes_requested",
            "findings": ["mandate-schema-missing: governance_mandates.v1.schema.json unavailable - cannot enforce structured output contract"],
        }

    instruction_parts = []
    if mandate:
        instruction_parts.append("Apply the review mandate below to review the implementation result.")
    if effective_review_policy:
        instruction_parts.append("Apply the effective review policy below for active profile and addons.")
    instruction_parts.append(
        "You MUST respond with valid JSON that conforms to the output schema below.\n"
        "Do NOT include any text outside the JSON object.\n\n"
        "Output schema:\n" + output_schema_text
    )

    context: dict[str, object] = {
        "schema": "opencode.impl-review.llm-context.v2",
        "ticket": ticket,
        "task": task,
        "approved_plan": plan_text,
        "implementation_summary": implementation_summary,
    }
    if mandate:
        context["review_mandate"] = mandate
    if effective_review_policy:
        context["effective_review_policy"] = effective_review_policy
        context["effective_policy_loaded"] = True
    context["instruction"] = "\n".join(instruction_parts)
    write_json_atomic(context_file, context)

    final_cmd = executor_cmd
    if "{context_file}" in final_cmd:
        final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))

    try:
        result = subprocess.run(
            final_cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        with open(stdout_file, "w", encoding="utf-8") as fh:
            fh.write(str(result.stdout or ""))
        with open(stderr_file, "w", encoding="utf-8") as fh:
            fh.write(str(result.stderr or ""))
        response_text = result.stdout or ""
        if not response_text.strip():
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": ["LLM executor returned empty response"],
            }
        mandates_schema = load_mandates_schema()
        return parse_llm_review_response(response_text, mandates_schema=mandates_schema)
    except Exception as exc:
        with open(stderr_file, "w", encoding="utf-8") as fh:
            fh.write(str(exc))
        return {"llm_invoked": False, "error": str(exc), "verdict": "changes_requested", "findings": [f"LLM review failed: {exc}"]}


def parse_llm_review_response(
    response_text: str,
    mandates_schema: dict[str, object] | None = None,
) -> dict[str, object]:
    """Parse and validate an LLM review response. Fail-closed on non-JSON / invalid."""
    # Add the validators directory to sys.path for import
    validators_dir = Path(__file__).resolve().parent.parent / "validators"
    if str(validators_dir) not in sys.path:
        sys.path.insert(0, str(validators_dir))
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

    if validate_review_response is None:
        return {
            "llm_invoked": True,
            "verdict": "changes_requested",
            "findings": ["validator-not-available: llm_response_validator could not be imported"],
            "validation_valid": False,
            "validation_violations": ["validator-not-available"],
            "raw_response": raw_text[:1000],
        }

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


# ---------------------------------------------------------------------------
# Phase-6 Review Loop
# ---------------------------------------------------------------------------

def read_plan_body(*, session_path: Path) -> str:
    """Read the latest plan_record_text from plan-record.json."""
    try:
        plan_record_path = session_path.parent / "plan-record.json"
        if not plan_record_path.is_file():
            return "none"
        payload = load_json(plan_record_path)
        versions = payload.get("versions")
        if not isinstance(versions, list) or not versions:
            return "none"
        latest = versions[-1] if isinstance(versions[-1], dict) else {}
        if not isinstance(latest, dict):
            return "none"
        text = str(latest.get("plan_record_text") or "").strip()
        return text or "none"
    except Exception:
        return "none"


def run_phase6_internal_review_loop(
    *, state_doc: dict, session_path: Path, commands_home: Path | None = None
) -> dict | None:
    """Run kernel-owned Phase 6 internal review iterations.

    Deterministic rules:
    - max 3 iterations
    - early-stop allowed only when digest is unchanged after minimum iterations
    - otherwise hard-stop at max iterations

    LLM review: each iteration calls the LLM with implementation context and
    REVIEW_MANDATE from rules.md. Response must be structured JSON conforming
    to reviewOutputSchema. Fail-closed: non-JSON / schema-invalid responses
    are treated as changes_requested.

    Args:
        state_doc: The session state document.
        session_path: Path to the session state file.
        commands_home: Optional commands home path. If None, will be derived.
    """
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    phase_raw = state.get("Phase") or state.get("phase") or ""
    phase_text = str(phase_raw).strip()
    if not phase_text.startswith("6"):
        return

    review_block_raw = state.get("ImplementationReview")
    review_block = dict(review_block_raw) if isinstance(review_block_raw, dict) else {}

    max_iterations = _coerce_int(
        review_block.get("max_iterations")
        or review_block.get("MaxIterations")
        or state.get("phase6_max_review_iterations")
        or state.get("phase6MaxReviewIterations")
        or 3
    )
    max_iterations = min(max(max_iterations, 1), 3)

    min_iterations = _coerce_int(
        review_block.get("min_self_review_iterations")
        or review_block.get("MinSelfReviewIterations")
        or state.get("phase6_min_self_review_iterations")
        or state.get("phase6MinSelfReviewIterations")
        or 1
    )
    min_iterations = max(1, min(min_iterations, max_iterations))

    iteration = _coerce_int(
        review_block.get("iteration")
        or review_block.get("Iteration")
        or state.get("phase6_review_iterations")
        or state.get("phase6ReviewIterations")
    )
    iteration = min(max(iteration, 0), max_iterations)

    prev_digest = str(
        review_block.get("prev_impl_digest")
        or review_block.get("PrevImplDigest")
        or state.get("phase6_prev_impl_digest")
        or state.get("phase6PrevImplDigest")
        or ""
    ).strip()
    curr_digest = str(
        review_block.get("curr_impl_digest")
        or review_block.get("CurrImplDigest")
        or state.get("phase6_curr_impl_digest")
        or state.get("phase6CurrImplDigest")
        or ""
    ).strip()

    base_seed = str(
        state.get("phase5_plan_record_digest")
        or state.get("phase5PlanRecordDigest")
        or state.get("TicketRecordDigest")
        or state.get("ticket_record_digest")
        or "phase6"
    )
    if not prev_digest:
        prev_digest = f"sha256:{_sha256_text(base_seed + ':initial')}"
    if not curr_digest:
        curr_digest = f"sha256:{_sha256_text(base_seed + ':0')}"

    force_stable = bool(state.get("phase6_force_stable_digest", False))

    has_executor = has_any_llm_executor()
    mandate_text = ""
    effective_review_policy = ""
    effective_policy_error = ""
    if has_executor:
        schema = load_mandates_schema()
        if schema:
            mandate_text = build_review_mandate_text(schema)
        # Derive commands_home if not provided
        resolved_commands_home = commands_home
        if resolved_commands_home is None:
            resolved_commands_home = _derive_commands_home()
        if resolved_commands_home is not None:
            # Check if there's a mock on session_reader (for test compatibility)
            try:
                import governance_runtime.entrypoints.session_reader as _sr
                policy_loader = getattr(_sr, "_load_effective_review_policy_text", load_effective_review_policy_text)
            except ImportError:
                policy_loader = load_effective_review_policy_text
            effective_review_policy, effective_policy_error = policy_loader(
                state=state,
                commands_home=resolved_commands_home,
            )
            if effective_policy_error and has_executor:
                return {
                    "blocked": True,
                    "reason": "effective-review-policy-unavailable",
                    "reason_code": BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
                    "recovery_action": "Ensure rulebooks and addons are loadable and contain valid policy content.",
                }

    ticket = str(state.get("Ticket") or state.get("ticket") or "").strip()
    task = str(state.get("Task") or state.get("task") or "").strip()
    plan_text = read_plan_body(session_path=session_path)
    changed_files = (
        state.get("implementation_changed_files")
        or state.get("implementation_package_changed_files")
        or []
    )
    domain_changed = (
        state.get("implementation_domain_changed_files")
        or state.get("implementation_package_domain_changed_files")
        or []
    )
    validation_report = state.get("implementation_validation_report") or {}
    checks = state.get("implementation_checks_executed") or []
    checks_ok = bool(state.get("implementation_checks_ok", False))

    impl_summary_parts: list[str] = []
    if changed_files:
        impl_summary_parts.append(f"Changed files ({len(changed_files)}): " + ", ".join(str(f) for f in changed_files[:20]))
    if domain_changed:
        impl_summary_parts.append(f"Domain files changed ({len(domain_changed)}): " + ", ".join(str(f) for f in domain_changed[:20]))
    if checks:
        impl_summary_parts.append(f"Checks executed ({len(checks)}): " + ", ".join(str(c) for c in checks))
    if checks_ok:
        impl_summary_parts.append("Checks result: PASS")
    else:
        impl_summary_parts.append("Checks result: FAIL or not executed")
    impl_summary = "\n".join(impl_summary_parts) if impl_summary_parts else "No implementation data available."

    audit_rows: list[dict[str, object]] = []
    revision_delta = "none" if (prev_digest and curr_digest and prev_digest == curr_digest) else "changed"
    llm_approve = False
    complete = False

    while iteration < max_iterations and not complete:
        iteration += 1
        previous = curr_digest
        if force_stable and iteration >= 2:
            curr_digest = previous
        else:
            curr_digest = f"sha256:{_sha256_text(base_seed + ':' + str(iteration))}"
        revision_delta = "none" if curr_digest == previous else "changed"

        llm_result: dict[str, object] = {}
        if has_executor:
            llm_result = call_llm_impl_review(
                ticket=ticket,
                task=task,
                plan_text=plan_text,
                implementation_summary=impl_summary,
                mandate=mandate_text,
                effective_review_policy=effective_review_policy,
            )
            review_block[f"llm_review_iteration_{iteration}"] = llm_result
            review_block["llm_review_valid"] = llm_result.get("validation_valid", False)
            review_block["llm_review_verdict"] = llm_result.get("verdict", "unknown")
            review_block["llm_review_findings"] = llm_result.get("findings", [])
            if llm_result.get("validation_valid") is True and llm_result.get("verdict") == "approve":
                llm_approve = True
                if iteration >= max_iterations:
                    complete = True
                elif iteration >= min_iterations and revision_delta == "none":
                    complete = True

        audit_rows.append(
            {
                "event": "phase6-implementation-review-iteration",
                "iteration": iteration,
                "input_digest": previous,
                "revision_delta": revision_delta,
                "outcome": "completed" if complete else "revised",
                "completion_status": "phase6-completed" if complete else "phase6-in-progress",
                "reason_code": "none",
                "impl_digest": curr_digest,
                "llm_review_invoked": llm_result.get("llm_invoked", False) if llm_result else False,
                "llm_review_valid": llm_result.get("validation_valid", False) if llm_result else False,
                "llm_review_verdict": llm_result.get("verdict", "unknown") if llm_result else "unknown",
            }
        )
        prev_digest = previous
        if complete:
            break

    review_block["iteration"] = iteration
    review_block["max_iterations"] = max_iterations
    review_block["min_self_review_iterations"] = min_iterations
    review_block["prev_impl_digest"] = prev_digest
    review_block["curr_impl_digest"] = curr_digest
    review_block["revision_delta"] = revision_delta
    review_block["completion_status"] = "phase6-completed" if complete else "phase6-in-progress"
    review_block["implementation_review_complete"] = complete
    review_block["llm_review_executor_available"] = has_executor
    state["ImplementationReview"] = review_block

    state["phase6_review_iterations"] = iteration
    state["phase6_max_review_iterations"] = max_iterations
    state["phase6_min_self_review_iterations"] = min_iterations
    state["phase6_prev_impl_digest"] = prev_digest
    state["phase6_curr_impl_digest"] = curr_digest
    state["phase6_revision_delta"] = revision_delta
    state["implementation_review_complete"] = complete
    state["phase6_state"] = "phase6_completed" if complete else "phase6_in_progress"
    state["phase6_blocker_code"] = "none"

    events_path = session_path.parent / "events.jsonl"
    for row in audit_rows:
        row_payload = dict(row)
        row_payload["observed_at"] = _now_iso()
        append_jsonl(events_path, row_payload)


def sync_phase6_completion_fields(*, state_doc: dict) -> None:
    """Normalize Phase 6 completion fields to a consistent, derived truth.

    This prevents drift where gate text reports completed review while persisted
    completion flags remain stale from pre-Phase-6 values.
    """
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    phase_raw = state.get("Phase") or state.get("phase") or ""
    phase_text = str(phase_raw).strip()
    if not phase_text.startswith("6"):
        return

    review_block_raw = state.get("ImplementationReview")
    review_block = dict(review_block_raw) if isinstance(review_block_raw, dict) else {}

    iteration = _coerce_int(
        review_block.get("iteration")
        or review_block.get("Iteration")
        or state.get("phase6_review_iterations")
        or state.get("phase6ReviewIterations")
    )
    max_iterations = _coerce_int(
        review_block.get("max_iterations")
        or review_block.get("MaxIterations")
        or state.get("phase6_max_review_iterations")
        or state.get("phase6MaxReviewIterations")
        or 3
    )
    min_iterations = _coerce_int(
        review_block.get("min_self_review_iterations")
        or review_block.get("MinSelfReviewIterations")
        or state.get("phase6_min_self_review_iterations")
        or state.get("phase6MinSelfReviewIterations")
        or 1
    )

    max_iterations = max(1, max_iterations)
    min_iterations = max(1, min(min_iterations if min_iterations >= 1 else 1, max_iterations))

    prev_digest = str(
        review_block.get("prev_impl_digest")
        or review_block.get("PrevImplDigest")
        or state.get("phase6_prev_impl_digest")
        or state.get("phase6PrevImplDigest")
        or ""
    ).strip()
    curr_digest = str(
        review_block.get("curr_impl_digest")
        or review_block.get("CurrImplDigest")
        or state.get("phase6_curr_impl_digest")
        or state.get("phase6CurrImplDigest")
        or ""
    ).strip()
    if prev_digest and curr_digest and prev_digest == curr_digest:
        revision_delta = "none"
    else:
        revision_delta = str(
            review_block.get("revision_delta")
            or review_block.get("RevisionDelta")
            or state.get("phase6_revision_delta")
            or state.get("phase6RevisionDelta")
            or "changed"
        ).strip().lower()
        if revision_delta not in {"none", "changed"}:
            revision_delta = "changed"

    llm_review_valid = bool(review_block.get("llm_review_valid") is True)
    llm_review_verdict = str(review_block.get("llm_review_verdict") or "").strip().lower()
    llm_approve = llm_review_valid and llm_review_verdict == "approve"

    has_llm_data = any(
        review_block.get(f"llm_review_iteration_{i}") is not None
        for i in range(1, max(max_iterations, 1) + 1)
    )

    if has_llm_data:
        complete = False
        if llm_approve:
            if iteration >= max_iterations:
                complete = True
            elif iteration >= min_iterations and revision_delta == "none":
                complete = True
    else:
        complete = iteration >= max_iterations or (iteration >= min_iterations and revision_delta == "none")

    review_block["iteration"] = iteration
    review_block["max_iterations"] = max_iterations
    review_block["min_self_review_iterations"] = min_iterations
    if prev_digest:
        review_block["prev_impl_digest"] = prev_digest
    if curr_digest:
        review_block["curr_impl_digest"] = curr_digest
    review_block["revision_delta"] = revision_delta
    review_block["completion_status"] = "phase6-completed" if complete else "phase6-in-progress"
    review_block["implementation_review_complete"] = complete
    state["ImplementationReview"] = review_block

    state["phase6_review_iterations"] = iteration
    state["phase6_max_review_iterations"] = max_iterations
    state["phase6_min_self_review_iterations"] = min_iterations
    if prev_digest:
        state["phase6_prev_impl_digest"] = prev_digest
    if curr_digest:
        state["phase6_curr_impl_digest"] = curr_digest
    state["phase6_revision_delta"] = revision_delta
    state["implementation_review_complete"] = complete
    state["phase6_state"] = "phase6_completed" if complete else "phase6_in_progress"
