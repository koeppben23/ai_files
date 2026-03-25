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
from governance_runtime.application.services.phase5_presentation_contract import (
    TITLE as PHASE5_PRESENTATION_TITLE,
    build_presentation_contract,
    english_violations,
)
from governance_runtime.contracts.compiler import compile_plan_to_requirements
from governance_runtime.contracts.validator import validate_requirement_contracts
from governance_runtime.domain import reason_codes
from governance_runtime.domain.phase_state_machine import normalize_phase_token
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.plan_record_repository import PlanRecordRepository
from governance_runtime.infrastructure.workspace_paths import plan_record_archive_dir, plan_record_path
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.json_store import append_jsonl as _append_jsonl
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic
from governance_runtime.infrastructure.session_locator import resolve_active_session_paths


BLOCKED_P5_PLAN_RECORD_PERSIST = reason_codes.BLOCKED_P5_PLAN_RECORD_PERSIST
BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE = "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"

# Canonical mandate schema error types (Python exceptions, not reason codes)
class MandateSchemaMissingError(Exception):
    pass
class MandateSchemaInvalidJsonError(Exception):
    pass
class MandateSchemaInvalidStructureError(Exception):
    pass
class MandateSchemaUnavailableError(Exception):
    pass
_PHASE5_REVIEW_MIN_ITERATIONS = 1


def _get_phase5_max_review_iterations(workspace_root: Path | None = None) -> int:
    """Get phase5 max review iterations from governance config.
    
    Args:
        workspace_root: Path to workspace root. If None, uses default value 3.
    
    Returns:
        Max review iterations (3 by default).
    """
    from governance_runtime.infrastructure.governance_config_loader import get_review_iterations
    phase5, _ = get_review_iterations(workspace_root)
    return phase5


def _clear_phase5_max_iterations_cache() -> None:
    """Clear the phase5 max iterations cache (for testing).
    
    Note: Cache is centralized in governance_config_loader. This function
    exists for API compatibility during transition.
    """
    pass


_MANDATE_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def _load_mandates_schema() -> dict[str, object] | None:
    """Load the compiled governance mandates schema (JSON).
    Canonical path only; no fallbacks allowed."""
    if not _MANDATE_SCHEMA_PATH.exists():
        raise MandateSchemaMissingError(
            f"Mandate schema not found at canonical path: {_MANDATE_SCHEMA_PATH}"
        )
    try:
        data = json.loads(_MANDATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MandateSchemaInvalidJsonError(f"Mandate schema JSON invalid: {exc}") from exc
    except Exception as exc:
        raise MandateSchemaUnavailableError(
            f"Mandate schema unavailable due to IO error: {exc}"
        ) from exc

    # Structural validation: must be dict with a valid 'review_mandate' block
    if not isinstance(data, dict):
        raise MandateSchemaInvalidStructureError("Mandate schema root must be an object")
    rm = data.get("review_mandate")
    if not isinstance(rm, dict):
        raise MandateSchemaInvalidStructureError("Mandate schema missing or invalid 'review_mandate' block")
    return data


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


def _build_plan_mandate_text(schema: dict[str, object]) -> str:
    """Build a plain-text plan mandate from the compiled JSON schema."""
    pm = schema.get("plan_mandate", {})
    if not isinstance(pm, dict):
        return ""

    lines: list[str] = []

    role = str(pm.get("role", "")).strip()
    if role:
        lines.append(f"Role: {role}")

    posture = pm.get("core_posture", [])
    if posture:
        for item in posture:
            lines.append(f"- {item}")

    evidence = pm.get("evidence_rule", [])
    if evidence:
        lines.append("Evidence rule:")
        for item in evidence:
            lines.append(f"- {item}")

    objectives = pm.get("primary_objectives", [])
    if objectives:
        lines.append("Planning objectives:")
        for item in objectives:
            lines.append(f"- {item}")

    lenses = pm.get("planning_lenses", [])
    if lenses:
        lines.append("Planning lenses:")
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

    contract = pm.get("output_contract", {})
    if contract:
        lines.append("Output contract:")
        if isinstance(contract, dict):
            for key, desc in contract.items():
                lines.append(f"- {key}: {desc}")

    decision = pm.get("decision_rules", [])
    if decision:
        lines.append("Decision rules:")
        for item in decision:
            lines.append(f"- {item}")

    style = pm.get("style_rules", [])
    if style:
        lines.append("Style rules:")
        for item in style:
            lines.append(f"- {item}")

    addendum = pm.get("governance_addendum", [])
    if addendum:
        lines.append("Governance addendum:")
        for item in addendum:
            lines.append(f"- {item}")

    return "\n".join(lines)


def _get_plan_output_schema_text() -> str:
    """Extract planOutputSchema text from mandates schema."""
    try:
        schema = _load_mandates_schema()
        if schema:
            defs = schema.get("$defs", {})
            for key in defs:
                if key == "planOutputSchema":
                    return json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **defs[key]}, indent=2)
    except Exception:
        pass
    return ""


def _load_effective_review_policy_text(
    state: Mapping[str, object],
    commands_home: Path,
) -> tuple[str, str]:
    """Load and format effective review policy for LLM injection.

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
        Path(__file__).resolve().parents[1]
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


BLOCKED_PLAN_GENERATION_FAILED = "BLOCKED-PLAN-GENERATION-FAILED"
BLOCKED_PLAN_EXECUTOR_UNAVAILABLE = "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"


def _resolve_plan_executor() -> str:
    """Resolve the plan LLM executor command.

    Priority:
    1. OPENCODE_PLAN_LLM_CMD (plan-specific)
    2. OPENCODE_IMPLEMENT_LLM_CMD (fallback, for backward compat)
    """
    plan_cmd = str(os.environ.get("OPENCODE_PLAN_LLM_CMD") or "").strip()
    if plan_cmd:
        return plan_cmd
    return str(os.environ.get("OPENCODE_IMPLEMENT_LLM_CMD") or "").strip()


def _call_llm_generate_plan(
    ticket_text: str,
    task_text: str,
    plan_mandate: str,
    effective_authoring_policy: str = "",
    re_review: bool = False,
) -> dict[str, object]:
    """Call LLM to generate a plan from ticket/task context.

    Fail-closed: returns blocked state on any failure.
    """
    executor_cmd = _resolve_plan_executor()
    if not executor_cmd:
        return {
            "blocked": True,
            "reason": "plan-executor-unavailable",
            "reason_code": BLOCKED_PLAN_EXECUTOR_UNAVAILABLE,
            "recovery_action": "Set OPENCODE_PLAN_LLM_CMD or OPENCODE_IMPLEMENT_LLM_CMD to enable plan generation.",
        }

    plan_dir = Path.home() / ".governance" / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    context_file = plan_dir / "llm_plan_context.json"
    stdout_file = plan_dir / "llm_plan_stdout.log"
    stderr_file = plan_dir / "llm_plan_stderr.log"

    output_schema_text = _get_plan_output_schema_text()
    instruction_parts = [
        "You are a governance planner. Generate a structured plan from the ticket and task below.",
    ]
    if plan_mandate:
        instruction_parts.append("Apply the plan mandate below.")
    if effective_authoring_policy:
        instruction_parts.append("Apply the effective authoring policy below for active profile and addons.")
    instruction_parts.append(
        "You MUST respond with valid JSON that conforms to the output schema below.\n"
        "All textual output MUST be in English only (language='en').\n"
        "Do NOT include any text outside the JSON object.\n\n"
        "Output schema:\n" + output_schema_text
    )

    context = {
        "schema": "opencode.plan.llm-context.v1",
        "ticket": ticket_text,
        "task": task_text,
    }
    if plan_mandate:
        context["plan_mandate"] = plan_mandate
    if effective_authoring_policy:
        context["effective_authoring_policy"] = effective_authoring_policy
        context["effective_policy_loaded"] = True
    context["instruction"] = "\n".join(instruction_parts)
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
                "blocked": True,
                "reason": "plan-llm-empty-response",
                "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
                "recovery_action": "LLM returned empty response for plan generation.",
            }
        return _parse_plan_generation_response(response_text, re_review=re_review)
    except Exception as exc:
        atomic_write_text(stderr_file, str(exc))
        return {
            "blocked": True,
            "reason": f"plan-llm-error: {exc}",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "Check LLM executor configuration and retry /plan.",
        }


def _parse_plan_generation_response(response_text: str, *, re_review: bool = False) -> dict[str, object]:
    """Parse and validate LLM plan generation response.

    Fail-closed: only structured, schema-valid JSON responses proceed.
    Validator must be importable — no fallback to manual field check.
    planOutputSchema must be present and non-empty.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "governance_runtime" / "application" / "validators"))
    try:
        from llm_response_validator import validate_plan_response
    except Exception as exc:
        return {
            "blocked": True,
            "reason": f"plan-validator-unavailable: {exc}",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "Ensure llm_response_validator module is importable for plan validation.",
        }

    raw_text = response_text.strip()

    if not raw_text:
        return {
            "blocked": True,
            "reason": "plan-llm-empty-response",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "LLM returned empty response for plan generation.",
        }

    parsed_data: dict[str, object] | None = None

    if raw_text.startswith("{"):
        try:
            parsed_data = json.loads(raw_text)
        except json.JSONDecodeError:
            pass

    if parsed_data is None:
        return {
            "blocked": True,
            "reason": f"plan-response-not-json: received {len(raw_text)} chars starting with: {raw_text[:80]!r}",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "LLM did not return valid JSON for plan generation.",
        }

    violations = english_violations(parsed_data)
    if violations:
        return {
            "blocked": True,
            "reason": f"plan-language-violation: {violations}",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "Plan output must be English-only across required fields.",
            "validation_violations": violations,
        }

    normalized_data = dict(parsed_data)
    normalized_data["language"] = "en"
    normalized_data["presentation_contract"] = build_presentation_contract(
        normalized_data,
        re_review=re_review,
    )

    # Load planOutputSchema — must be present and non-empty
    try:
        mandates_schema = _load_mandates_schema()
        defs = mandates_schema.get("$defs", {})
        plan_schema = defs.get("planOutputSchema")
        if not plan_schema or not isinstance(plan_schema, dict):
            return {
                "blocked": True,
                "reason": "plan-output-schema-missing: planOutputSchema not found in mandates schema",
                "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
                "recovery_action": "Ensure planOutputSchema is defined in governance_mandates.v1.schema.json.",
            }
    except (
        MandateSchemaMissingError,
        MandateSchemaInvalidJsonError,
        MandateSchemaInvalidStructureError,
        MandateSchemaUnavailableError,
    ):
        return {
            "blocked": True,
            "reason": "plan-mandate-schema-unavailable",
            "reason_code": "MANDATE-SCHEMA-UNAVAILABLE",
            "recovery_action": "Ensure governance_mandates.v1.schema.json is loadable.",
        }

    # Validate against planOutputSchema — fail-closed, no fallback
    validation = validate_plan_response(normalized_data, plan_schema=plan_schema)
    if not validation.valid:
        validation_rules = [v.rule for v in validation.violations]
        return {
            "blocked": True,
            "reason": f"plan-schema-violation: {validation_rules}",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "LLM response did not conform to planOutputSchema.",
            "validation_violations": validation_rules,
        }

    # Convert structured plan to markdown plan text for the existing review/persist chain
    plan_text = _structured_plan_to_markdown(normalized_data)
    return {
        "blocked": False,
        "plan_text": plan_text,
        "structured_plan": normalized_data,
    }


def _structured_plan_to_markdown(plan: dict[str, object]) -> str:
    """Convert structured plan output to markdown plan text.

    The markdown format is what the existing Phase 5 review/persist chain expects.
    """
    lines: list[str] = []

    presentation = plan.get("presentation_contract")
    if isinstance(presentation, Mapping):
        title = str(presentation.get("title") or PHASE5_PRESENTATION_TITLE).strip()
        badge = str(presentation.get("plan_status_badge") or "PLAN (not implemented)").strip()
        decision = str(presentation.get("decision_required") or "").strip()
        lines.append(f"# {title}\n")
        lines.append(f"{badge}\n")
        if decision:
            lines.append(f"## Decision Required\n{decision}\n")

    objective = str(plan.get("objective", "")).strip()
    if objective:
        lines.append(f"# Plan Objective\n{objective}\n")

    target_state = str(plan.get("target_state", "")).strip()
    if target_state:
        lines.append(f"## Target State\n{target_state}\n")

    target_flow = str(plan.get("target_flow", "")).strip()
    if target_flow:
        lines.append(f"## Target Flow\n{target_flow}\n")

    state_machine = str(plan.get("state_machine", "")).strip()
    if state_machine:
        lines.append(f"## State Machine\n{state_machine}\n")

    blocker_taxonomy = str(plan.get("blocker_taxonomy", "")).strip()
    if blocker_taxonomy:
        lines.append(f"## Blocker Taxonomy\n{blocker_taxonomy}\n")

    audit = str(plan.get("audit", "")).strip()
    if audit:
        lines.append(f"## Audit\n{audit}\n")

    go_no_go = str(plan.get("go_no_go", "")).strip()
    if go_no_go:
        lines.append(f"## Go/No-Go\n{go_no_go}\n")

    test_strategy = str(plan.get("test_strategy", "")).strip()
    if test_strategy:
        lines.append(f"## Test Strategy\n{test_strategy}\n")

    assumptions = str(plan.get("assumptions", "")).strip()
    if assumptions:
        lines.append(f"## Assumptions\n{assumptions}\n")

    risks = str(plan.get("risks", "")).strip()
    if risks:
        lines.append(f"## Risks\n{risks}\n")

    non_goals = str(plan.get("non_goals", "")).strip()
    if non_goals:
        lines.append(f"## Non-Goals\n{non_goals}\n")

    open_questions = str(plan.get("open_questions", "")).strip()
    if open_questions:
        lines.append(f"## Open Questions\n{open_questions}\n")

    reason_code = str(plan.get("reason_code", "")).strip()
    if reason_code:
        lines.append(f"## Reason Code\n{reason_code}\n")

    if isinstance(presentation, Mapping):
        next_actions = presentation.get("next_actions")
        if isinstance(next_actions, list) and next_actions:
            lines.append("## Next Actions")
            for action in next_actions:
                lines.append(f"- {str(action)}")
            lines.append("")

    return "\n".join(lines)


def _call_llm_review(
    content: str,
    mandate: str,
    effective_review_policy: str = "",
) -> dict[str, object]:
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
    instruction_parts = []
    if mandate:
        instruction_parts.append("Apply the review mandate to review the provided plan.")
    if effective_review_policy:
        instruction_parts.append("Apply the effective review policy below for active profile and addons.")
    instruction_parts.append(
        "You MUST respond with valid JSON that conforms to the output schema below.\n"
        "Do NOT include any text outside the JSON object.\n\n"
        "Output schema:\n" + output_schema_text
    )

    context = {
        "schema": "opencode.review.llm-context.v3",
        "content_to_review": content,
    }
    if mandate:
        context["review_mandate"] = mandate
    if effective_review_policy:
        context["effective_review_policy"] = effective_review_policy
        context["effective_policy_loaded"] = True
    context["instruction"] = "\n".join(instruction_parts)
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
        # Fail-closed: mandate schema MUST be available for response validation
        try:
            mandates_schema = _load_mandates_schema()
        except MandateSchemaMissingError as exc:
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": [f"mandate-schema-missing: {exc}"],
                "reason_code": "MANDATE-SCHEMA-MISSING",
            }
        except MandateSchemaInvalidJsonError as exc:
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": [f"mandate-schema-invalid-json: {exc}"],
                "reason_code": "MANDATE-SCHEMA-INVALID-JSON",
            }
        except MandateSchemaInvalidStructureError as exc:
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": [f"mandate-schema-invalid-structure: {exc}"],
                "reason_code": "MANDATE-SCHEMA-INVALID-STRUCTURE",
            }
        except MandateSchemaUnavailableError as exc:
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": [f"mandate-schema-unavailable: {exc}"],
                "reason_code": "MANDATE-SCHEMA-UNAVAILABLE",
            }
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


def _run_internal_phase5_self_review(
    plan_text: str,
    state: Mapping[str, object] | None = None,
    commands_home: Path | None = None,
    max_iterations: int | None = None,
) -> dict[str, object]:
    if max_iterations is None:
        max_iterations = _get_phase5_max_review_iterations(None)
    current_text = _canonicalize_text(plan_text)
    if not current_text:
        return {
            "blocked": True,
            "reason": "empty-plan-after-canonicalization",
            "reason_code": reason_codes.BLOCKED_P5_PLAN_EMPTY,
            "recovery_action": "provide non-empty plan text via --plan-text or --plan-file",
        }

    mandate_text = ""
    try:
        schema = _load_mandates_schema()
        if schema:
            mandate_text = _build_review_mandate_text(schema)
        else:
            mandate_text = ""
    except MandateSchemaMissingError:
        return {
            "blocked": True,
            "reason": "mandate-schema-missing",
            "reason_code": BLOCKED_P5_PLAN_RECORD_PERSIST,
            "recovery_action": "Provide governance_mandates.v1.schema.json at the canonical runtime location.",
        }
    except MandateSchemaInvalidJsonError:
        return {
            "blocked": True,
            "reason": "mandate-schema-invalid-json",
            "reason_code": BLOCKED_P5_PLAN_RECORD_PERSIST,
            "recovery_action": "Validate the JSON syntax of governance_mandates.v1.schema.json at the canonical runtime location.",
        }
    except MandateSchemaInvalidStructureError:
        return {
            "blocked": True,
            "reason": "mandate-schema-invalid-structure",
            "reason_code": BLOCKED_P5_PLAN_RECORD_PERSIST,
            "recovery_action": "Regenerate the compiled mandate schema from rules.md or ensure correct structure.",
        }
    except MandateSchemaUnavailableError:
        return {
            "blocked": True,
            "reason": "mandate-schema-unavailable",
            "reason_code": BLOCKED_P5_PLAN_RECORD_PERSIST,
            "recovery_action": "Provide governance_mandates.v1.schema.json at the canonical runtime location.",
        }
    except Exception:
        return {
            "blocked": True,
            "reason": "mandate-schema-unavailable",
            "reason_code": BLOCKED_P5_PLAN_RECORD_PERSIST,
            "recovery_action": "Provide governance_mandates.v1.schema.json at the canonical runtime location.",
        }

    iteration = 0
    prev_digest = _digest(current_text)
    final_digest = prev_digest
    revision_delta = "none"
    findings_summary: list[str] = []
    audit_rows: list[dict[str, object]] = []
    llm_review_results: list[dict[str, object]] = []
    has_executor = _has_any_llm_executor()

    while iteration < max_iterations:
        iteration += 1

        llm_result: dict[str, object] = {"llm_invoked": False, "verdict": "changes_requested", "findings": []}
        verdict = "changes_requested"
        findings_list: list[str] = []

        effective_review_policy = ""
        effective_policy_error = ""
        if commands_home is not None and state is not None:
            effective_review_policy, effective_policy_error = _load_effective_review_policy_text(
                state=state,
                commands_home=commands_home,
            )
            if effective_policy_error:
                return {
                    "blocked": True,
                    "reason": "effective-review-policy-unavailable",
                    "reason_code": BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
                    "recovery_action": "Ensure rulebooks and addons are loadable and contain valid policy content.",
                }

        if has_executor:
            llm_result = _call_llm_review(current_text, mandate_text, effective_review_policy)
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
            iteration >= max_iterations
            or (verdict == "approve" and revision_delta == "none" and iteration >= _PHASE5_REVIEW_MIN_ITERATIONS)
            or (mechanical_findings and iteration >= max_iterations)
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
        "max_iterations": max_iterations,
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

    # ── Load session state early (needed for auto-generation) ──
    try:
        session_path, repo_fingerprint, _, workspace_dir = resolve_active_session_paths()
        document = _load_json(session_path)
        state = document.get("SESSION_STATE")
        if not isinstance(state, dict):
            raise RuntimeError("SESSION_STATE root missing")
    except Exception as exc:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P5_PLAN_RECORD_PERSIST,
            reason="session-state-unreadable",
            observed=str(exc),
            recovery_action="ensure session state is loadable",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    # ── Auto-generate plan if none provided ──
    if not plan_text:
        ticket_text = str(state.get("Ticket") or "").strip()
        task_text = str(state.get("Task") or "").strip()
        if not ticket_text and not task_text:
            payload = _payload(
                "blocked",
                reason_code=BLOCKED_P5_PLAN_RECORD_PERSIST,
                reason="missing-plan-record-evidence",
                recovery_action="provide non-empty plan text via --plan-text or --plan-file, or persist ticket via /ticket first",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        resolver = BindingEvidenceResolver(env=os.environ)
        evidence = getattr(resolver, "resolve")(mode="user")
        commands_home = evidence.commands_home

        # Load mandate schema for plan mandate text — fail-closed
        plan_mandate = ""
        mandates_schema: dict[str, object] | None = None
        try:
            mandates_schema = _load_mandates_schema()
            plan_mandate = _build_plan_mandate_text(mandates_schema)
        except MandateSchemaMissingError as exc:
            payload = _payload(
                "blocked",
                reason_code="MANDATE-SCHEMA-MISSING",
                reason=f"plan-mandate-schema-missing: {exc}",
                recovery_action="Ensure governance_mandates.v1.schema.json exists at canonical path.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except MandateSchemaInvalidJsonError as exc:
            payload = _payload(
                "blocked",
                reason_code="MANDATE-SCHEMA-INVALID-JSON",
                reason=f"plan-mandate-schema-invalid-json: {exc}",
                recovery_action="Fix JSON syntax in governance_mandates.v1.schema.json.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except MandateSchemaInvalidStructureError as exc:
            payload = _payload(
                "blocked",
                reason_code="MANDATE-SCHEMA-INVALID-STRUCTURE",
                reason=f"plan-mandate-schema-invalid-structure: {exc}",
                recovery_action="Ensure mandate schema has valid plan_mandate block.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
        except MandateSchemaUnavailableError as exc:
            payload = _payload(
                "blocked",
                reason_code="MANDATE-SCHEMA-UNAVAILABLE",
                reason=f"plan-mandate-schema-unavailable: {exc}",
                recovery_action="Check file permissions for governance_mandates.v1.schema.json.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        if not plan_mandate:
            payload = _payload(
                "blocked",
                reason_code="PLAN-MANDATE-EMPTY",
                reason="plan-mandate-empty: mandate schema loaded but plan_mandate block produced no text",
                recovery_action="Ensure plan_mandate block in governance_mandates.v1.schema.json has content.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        # Load effective authoring policy — fail-closed (temporary — will be refactored to effective_plan_policy)
        effective_policy_text = ""
        effective_policy_error = ""
        try:
            from governance_runtime.entrypoints.implement_start import _load_effective_authoring_policy_text
            effective_policy_text, effective_policy_error = _load_effective_authoring_policy_text(
                state=state,
                commands_home=commands_home,
            )
        except Exception as exc:
            effective_policy_error = str(exc)
        if effective_policy_error:
            payload = _payload(
                "blocked",
                reason_code=BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
                reason=f"effective-policy-unavailable: {effective_policy_error}",
                recovery_action="Ensure rulebooks and addons are loadable and contain valid policy content.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        gen_result = _call_llm_generate_plan(
            ticket_text=ticket_text,
            task_text=task_text,
            plan_mandate=plan_mandate,
            effective_authoring_policy=effective_policy_text,
            re_review=bool(state.get("plan_record_version") or state.get("PlanRecordVersion")),
        )
        if gen_result.get("blocked") is True:
            payload = _payload(
                "blocked",
                reason_code=str(gen_result.get("reason_code") or BLOCKED_PLAN_GENERATION_FAILED),
                reason=str(gen_result.get("reason") or "plan-generation-failed"),
                recovery_action=str(gen_result.get("recovery_action") or "provide plan text via --plan-text or check LLM executor"),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        plan_text = _canonicalize_text(str(gen_result.get("plan_text") or ""))
        if not plan_text:
            payload = _payload(
                "blocked",
                reason_code=BLOCKED_PLAN_GENERATION_FAILED,
                reason="plan-generation-empty-result",
                recovery_action="LLM generated an empty plan. Provide plan text via --plan-text.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

    # ── Standard Phase 5 flow ──
    try:
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

        resolver = BindingEvidenceResolver(env=os.environ)
        evidence = getattr(resolver, "resolve")(mode="user")
        commands_home = evidence.commands_home

        max_iterations = _get_phase5_max_review_iterations(workspace_dir)
        review_result = _run_internal_phase5_self_review(plan_text, state=state, commands_home=commands_home, max_iterations=max_iterations)
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

        from governance_runtime.application.services.state_document_validator import validate_plan_payload
        plan_payload = {
            "body": plan_text,
            "status": "draft",
        }
        payload_validation = validate_plan_payload(plan_payload)
        if not payload_validation.valid:
            error_messages = [e.message for e in payload_validation.errors]
            payload = _payload(
                "blocked",
                reason_code=BLOCKED_P5_PLAN_RECORD_PERSIST,
                reason=f"Plan payload validation failed: {'; '.join(error_messages)}",
                recovery_action="verify plan has non-empty body and valid status",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

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
                        "max_iterations": _as_int(review_result.get("max_iterations"), max_iterations),
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
        state["phase5_max_review_iterations"] = _as_int(review_result.get("max_iterations"), max_iterations)
        state["phase5_revision_delta"] = str(review_result.get("revision_delta") or "changed")
        state["requirement_contracts_present"] = contracts_count > 0
        state["requirement_contracts_count"] = contracts_count
        state["requirement_contracts_digest"] = f"sha256:{contracts_digest}"
        state["requirement_contracts_source"] = str(_contracts_path(session_path))
        state["Phase5Review"] = {
            "iteration": _as_int(review_result.get("iterations"), 0),
            "max_iterations": _as_int(review_result.get("max_iterations"), max_iterations),
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
        max_iterations=_as_int(review_result.get("max_iterations"), max_iterations),
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
