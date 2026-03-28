#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.application.use_cases.phase_router import route_phase
from governance_runtime.application.use_cases.rework_clarification import consume_rework_clarification_state
from governance_runtime.application.use_cases.session_state_helpers import with_kernel_result
from governance_runtime.application.services.state_accessor import get_phase
from governance_runtime.application.services.phase5_presentation_contract import (
    TITLE as PHASE5_PRESENTATION_TITLE,
    build_presentation_contract,
    build_machine_requirements,
    english_violations,
)
from governance_runtime.contracts.compiler import compile_plan_to_requirements
from governance_runtime.contracts.validator import validate_requirement_contracts
from governance_runtime.domain import reason_codes
from governance_runtime.domain.phase_state_machine import normalize_phase_token
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.opencode_model_binding import (
    has_active_desktop_llm_binding as _has_desktop_llm_binding,
    resolve_active_opencode_model,
)
from governance_runtime.infrastructure.governance_binding_resolver import (
    GovernanceBindingResolutionError,
    resolve_governance_binding,
)
from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.governance_context_materializer import (
    GovernanceContextMaterializationError,
    materialize_governance_artifacts,
    validate_materialized_artifacts,
)
from governance_runtime.infrastructure.plan_record_repository import PlanRecordRepository
from governance_runtime.infrastructure.workspace_paths import (
    governance_plan_dir,
    governance_review_dir,
    governance_runtime_state_dir,
)
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


def _build_bridge_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "OPENCODE",
        "OPENCODE_CLIENT",
        "OPENCODE_PID",
        "OPENCODE_SERVER_USERNAME",
        "OPENCODE_SERVER_PASSWORD",
    ):
        env.pop(key, None)
    permission_overlay = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "bash": "deny",
            "read": "deny",
            "edit": "deny",
            "glob": "deny",
            "grep": "deny",
            "list": "deny",
            "task": "deny",
            "skill": "deny",
            "webfetch": "deny",
            "websearch": "deny",
            "codesearch": "deny",
            "external_directory": "deny",
        },
    }
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(permission_overlay, ensure_ascii=True)
    return env


def _resolve_active_opencode_session_id() -> str:
    session_id = str(os.environ.get("OPENCODE_SESSION_ID") or "").strip()
    if session_id:
        return session_id
    model_info = resolve_active_opencode_model()
    if not isinstance(model_info, dict):
        return ""
    return str(model_info.get("session_id") or "").strip()


def _bridge_timeout_seconds() -> int:
    raw = str(os.environ.get("AI_GOVERNANCE_BRIDGE_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return 120
    try:
        value = int(raw)
    except ValueError:
        return 120
    return max(30, min(value, 600))


def _resolve_desktop_bridge_cmd(*, repo_root: Path, message: str) -> str:
    candidate_env = str(os.environ.get("OPENCODE_CLI_BIN") or "").strip()
    candidate_paths: list[str] = []
    if candidate_env:
        candidate_paths.append(candidate_env)
    candidate_paths.append("/Applications/OpenCode.app/Contents/MacOS/opencode-cli")
    which_opencode = shutil.which("opencode")
    if which_opencode:
        candidate_paths.append(which_opencode)
    which_opencode_cli = shutil.which("opencode-cli")
    if which_opencode_cli:
        candidate_paths.append(which_opencode_cli)

    cli_bin = ""
    for token in candidate_paths:
        path = Path(token)
        if path.exists() and os.access(str(path), os.X_OK):
            cli_bin = str(path)
            break
    if not cli_bin:
        return ""

    session_id = _resolve_active_opencode_session_id()
    if not session_id:
        return ""

    model_info = resolve_active_opencode_model()
    model_token = ""
    if isinstance(model_info, dict):
        provider = str(model_info.get("provider") or "").strip()
        model_id = str(model_info.get("model_id") or "").strip()
        if provider and model_id:
            model_token = f"{provider}/{model_id}"

    cmd_parts = [
        shlex.quote(cli_bin),
        "run",
        "--session",
        shlex.quote(session_id),
        "--format",
        "json",
        "--file",
        "{context_file}",
    ]
    if model_token:
        cmd_parts.extend(["--model", shlex.quote(model_token)])
    cmd_parts.append(shlex.quote(message))
    return " ".join(cmd_parts)


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


@lru_cache(maxsize=1)
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


@lru_cache(maxsize=1)
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


@lru_cache(maxsize=1)
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
BLOCKED_REVIEW_EXECUTOR_TIMEOUT = "BLOCKED-REVIEW-EXECUTOR-TIMEOUT"
BLOCKED_REVIEW_TOOL_USE_DISALLOWED = "BLOCKED-REVIEW-TOOL-USE-DISALLOWED"


def _resolve_plan_execution_binding(*, workspace_dir: Path | None) -> tuple[bool, str, str]:
    """Resolve planning execution binding.

    Returns (pipeline_mode, binding_value, source).
    """
    resolution = resolve_governance_binding(
        role="execution",
        workspace_root=workspace_dir,
        env_reader=lambda key: os.environ.get(key),
        has_active_chat_binding=_has_active_desktop_llm_binding(),
    )
    return resolution.pipeline_mode, resolution.binding_value, resolution.source


def _resolve_plan_review_binding(*, workspace_dir: Path | None) -> tuple[bool, str, str]:
    """Resolve planning internal-review binding.

    Returns (pipeline_mode, binding_value, source).
    """
    resolution = resolve_governance_binding(
        role="review",
        workspace_root=workspace_dir,
        env_reader=lambda key: os.environ.get(key),
        has_active_chat_binding=_has_active_desktop_llm_binding(),
    )
    return resolution.pipeline_mode, resolution.binding_value, resolution.source


def _has_active_desktop_llm_binding() -> bool:
    """Return True when OpenCode Desktop model binding is available."""
    return _has_desktop_llm_binding()


def _parse_json_events_to_text(response_text: str) -> str:
    """Parse OpenCode JSON events and extract assistant text response.

    When --format json is used, opencode run returns NDJSON events.
    We only accept 'text' type events as the assistant response payload.

    Args:
        response_text: Raw stdout from opencode run --format json

    Returns:
        Extracted text content from assistant response, or original text if parsing fails.
    """
    if not response_text.strip():
        return response_text

    try:
        lines = response_text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "text":
                continue
            part = event.get("part", {})
            text_content = part.get("text", "")
            if text_content:
                return text_content
    except Exception:
        pass

    return response_text


def _call_llm_generate_plan(
    ticket_text: str,
    task_text: str,
    plan_mandate: str,
    effective_authoring_policy: str = "",
    re_review: bool = False,
    workspace_dir: Path | None = None,
    config_root: Path | None = None,
    workspaces_home: Path | None = None,
    repo_fingerprint: str | None = None,
) -> dict[str, object]:
    """Call LLM to generate a plan from ticket/task context.

    Fail-closed: returns blocked state on any failure.
    """
    try:
        pipeline_mode, binding_value, _binding_source = _resolve_plan_execution_binding(
            workspace_dir=workspace_dir
        )
    except GovernanceBindingResolutionError as exc:
        return {
            "blocked": True,
            "reason": "plan-executor-unavailable",
            "reason_code": BLOCKED_PLAN_EXECUTOR_UNAVAILABLE,
            "recovery_action": str(exc),
            "binding_role": "execution",
        }

    binding_source = str(_binding_source or "").strip()

    executor_cmd = binding_value if pipeline_mode else ""

    resolved_workspaces_home = workspaces_home
    resolved_repo_fingerprint = str(repo_fingerprint or "").strip()
    if resolved_workspaces_home is None or not resolved_repo_fingerprint:
        scope_root = workspace_dir or config_root or (Path.home() / ".governance")
        resolved_workspaces_home = scope_root / "workspaces"
        candidate = str(scope_root.name or "").strip()
        if re.fullmatch(r"[0-9a-f]{24}", candidate):
            resolved_repo_fingerprint = candidate
        else:
            resolved_repo_fingerprint = hashlib.sha256(str(scope_root).encode("utf-8")).hexdigest()[:24]

    plan_dir = governance_plan_dir(resolved_workspaces_home, resolved_repo_fingerprint)
    runtime_state_dir = governance_runtime_state_dir(resolved_workspaces_home, resolved_repo_fingerprint)
    governance_root = resolved_workspaces_home
    plan_dir.mkdir(parents=True, exist_ok=True)
    context_file = plan_dir / "llm_plan_context.json"
    stdout_file = plan_dir / "llm_plan_stdout.log"
    stderr_file = plan_dir / "llm_plan_stderr.log"

    runtime_state_dir.mkdir(parents=True, exist_ok=True)

    try:
        materialization = materialize_governance_artifacts(
            output_dir=runtime_state_dir,
            config_root=governance_root,
            plan_mandate=plan_mandate if plan_mandate else None,
            effective_policy=effective_authoring_policy if effective_authoring_policy else None,
        )
    except GovernanceContextMaterializationError as e:
        return {
            "blocked": True,
            "reason": f"governance-context-materialization-failed: {e.reason}",
            "reason_code": e.reason_code,
            "recovery_action": "Failed to materialize governance artifacts.",
            "pipeline_mode": pipeline_mode,
            "binding_role": "execution",
            "binding_source": binding_source,
        }

    output_schema_text = _get_plan_output_schema_text()
    instruction_parts = [
        "NO TOOLS. JSON ONLY. Respond with raw JSON only, no text before or after.",
        "Fields: objective, target_state, target_flow, state_machine, blocker_taxonomy, audit, go_no_go, test_strategy, reason_code, language, presentation_contract.",
        "Return language='en'. Do not call tools. Do not emit markdown or explanations.",
    ]
    if output_schema_text:
        instruction_parts.append("Schema source: planOutputSchema is authoritative; satisfy required fields and constraints.")

    context = {
        "schema": "opencode.plan.llm-context.v1",
        "ticket": ticket_text,
        "task": task_text,
    }
    if materialization.plan_mandate_file:
        context["plan_mandate_file"] = str(materialization.plan_mandate_file)
        context["plan_mandate_sha256"] = materialization.plan_mandate_sha256
        context["plan_mandate_label"] = materialization.plan_mandate_label
    if materialization.effective_policy_file:
        context["effective_policy_file"] = str(materialization.effective_policy_file)
        context["effective_policy_sha256"] = materialization.effective_policy_sha256
        context["effective_policy_label"] = materialization.effective_policy_label
    context["effective_policy_loaded"] = materialization.has_materialized()
    if materialization.has_materialized():
        context["context_materialization_complete"] = True
    context["instruction"] = "\n".join(instruction_parts)
    atomic_write_text(context_file, json.dumps(context, ensure_ascii=True, indent=2) + "\n")

    try:
        validate_materialized_artifacts(materialization)
    except GovernanceContextMaterializationError as e:
        return {
            "blocked": True,
            "reason": f"governance-context-validation-failed: {e.reason}",
            "reason_code": e.reason_code,
            "recovery_action": "Materialized artifacts failed validation.",
            "pipeline_mode": pipeline_mode,
            "binding_role": "execution",
            "binding_source": binding_source,
        }

    bridge_mode = False
    if not executor_cmd and not pipeline_mode and _has_active_desktop_llm_binding():
        bridge_cmd = _resolve_desktop_bridge_cmd(
            repo_root=Path.cwd(),
            message="Read the attached planning context JSON and produce only valid JSON conforming to the provided output schema.",
        )
        if bridge_cmd:
            executor_cmd = bridge_cmd
            bridge_mode = True
        else:
            return {
                "blocked": True,
                "reason": "plan-llm-executor-unavailable",
                "reason_code": "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE",
                "recovery_action": "Direct mode requires active chat binding, resolvable session id, and callable desktop bridge.",
                "pipeline_mode": pipeline_mode,
                "binding_role": "execution",
                "binding_source": binding_source,
                "binding_resolved": True,
                "invoke_backend_available": False,
            }

    final_cmd = executor_cmd
    if "{context_file}" in final_cmd:
        final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))
    import subprocess
    try:
        result = subprocess.run(
            final_cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=_bridge_timeout_seconds() if bridge_mode else None,
            env=_build_bridge_env() if bridge_mode else None,
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
                "pipeline_mode": pipeline_mode,
                "binding_role": "execution",
                "binding_source": binding_source,
            }
        if bridge_mode and '"type":"tool_use"' in response_text and '"type":"text"' not in response_text:
            return {
                "blocked": True,
                "reason": "plan-llm-tool-use-disallowed",
                "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
                "recovery_action": "LLM must return JSON directly without tool calls in plan mode.",
                "pipeline_mode": pipeline_mode,
                "binding_role": "execution",
                "binding_source": binding_source,
            }
        response_text = _parse_json_events_to_text(response_text)
        parsed = _parse_plan_generation_response(response_text, re_review=re_review)
        parsed["pipeline_mode"] = pipeline_mode
        parsed["binding_role"] = "execution"
        parsed["binding_source"] = binding_source
        return parsed
    except subprocess.TimeoutExpired:
        return {
            "blocked": True,
            "reason": "plan-llm-timeout",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "LLM planning timed out. Retry /plan after confirming active session responsiveness.",
            "pipeline_mode": pipeline_mode,
            "binding_role": "execution",
            "binding_source": binding_source,
        }
    except Exception as exc:
        atomic_write_text(stderr_file, str(exc))
        return {
            "blocked": True,
            "reason": f"plan-llm-error: {exc}",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "Check LLM executor configuration and retry /plan.",
            "pipeline_mode": pipeline_mode,
            "binding_role": "execution",
            "binding_source": binding_source,
        }


def _parse_plan_generation_response(response_text: str, *, re_review: bool = False) -> dict[str, object]:
    """Parse and validate LLM plan generation response.

    Fail-closed: only structured, schema-valid JSON responses proceed.
    Validator must be importable — no fallback to manual field check.
    planOutputSchema must be present and non-empty.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "governance_runtime" / "application" / "validators"))
    try:
        from llm_response_validator import coerce_output_against_schema, validate_plan_response
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

    normalized_payload = coerce_output_against_schema(parsed_data, plan_schema)
    if not isinstance(normalized_payload, dict):
        return {
            "blocked": True,
            "reason": "plan-response-normalization-failed",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "LLM plan output could not be normalized to object form.",
        }

    violations = english_violations(normalized_payload)
    if violations:
        return {
            "blocked": True,
            "reason": f"plan-language-violation: {violations}",
            "reason_code": BLOCKED_PLAN_GENERATION_FAILED,
            "recovery_action": "Plan output must be English-only across required fields.",
            "validation_violations": violations,
        }

    normalized_data = dict(normalized_payload)
    normalized_data["language"] = "en"
    normalized_data["presentation_contract"] = build_presentation_contract(
        normalized_data,
        re_review=re_review,
    )

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

    def _add_text_section(title: str, value: object) -> None:
        text = str(value or "").strip()
        if not text:
            return
        lines.append(f"## {title}")
        lines.append(text)
        lines.append("")

    def _add_list_section(title: str, values: object) -> None:
        if not isinstance(values, list):
            return
        compact = [str(item).strip() for item in values if str(item).strip()]
        if not compact:
            return
        lines.append(f"## {title}")
        for item in compact:
            lines.append(f"- {item}")
        lines.append("")

    def _add_recommendation_section(value: object, reasons: object) -> None:
        choice = str(value or "").strip()
        if not choice:
            return
        lines.append("## Recommendation")
        lines.append(f"Recommendation: {choice}")
        if isinstance(reasons, list):
            compact_reasons = [str(item).strip() for item in reasons if str(item).strip()]
            for item in compact_reasons[:3]:
                lines.append(f"- {item}")
        lines.append("")

    presentation = plan.get("presentation_contract")
    if isinstance(presentation, Mapping):
        title = str(presentation.get("title") or PHASE5_PRESENTATION_TITLE).strip()
        badge = str(presentation.get("plan_status_badge") or "PLAN (not implemented)").strip()
        decision = str(presentation.get("decision_required") or "").strip()
        lines.append(f"# {title}")
        lines.append(badge)
        lines.append("")
        _add_text_section("Decision Required", decision)
        _add_recommendation_section(
            presentation.get("recommendation"),
            presentation.get("recommendation_reasons"),
        )
        _add_list_section("Delivery Scope (Checklist)", presentation.get("delivery_scope"))
        _add_list_section("Acceptance Criteria (Measurable)", presentation.get("acceptance_criteria"))
        _add_list_section("Executive Summary", presentation.get("executive_summary"))
        _add_text_section("What Changed Since Last Review", presentation.get("delta_since_last_review"))
        _add_text_section("Scope", presentation.get("scope"))
        _add_list_section("Execution Slices", presentation.get("execution_slices"))
        _add_list_section("Risks & Mitigations (Plain Language)", presentation.get("risks_and_mitigations"))
        _add_text_section("Release Gates", presentation.get("release_gates"))
        _add_list_section("Open Decisions", presentation.get("open_decisions"))
        _add_list_section(
            "Next Steps if Changes Requested",
            presentation.get("changes_requested_actions"),
        )
        _add_list_section("Next Actions", presentation.get("next_actions"))

    # Keep legacy technical fields as appendix for compatibility with
    # existing compilation/review machinery while keeping decision-brief
    # sections as primary user surface.
    lines.append("## Technical Appendix")
    lines.append("")

    objective = str(plan.get("objective", "")).strip()
    if objective:
        lines.append(f"### Plan Objective\n{objective}\n")

    target_state = str(plan.get("target_state", "")).strip()
    if target_state:
        lines.append(f"### Target-State\n{target_state}\n")

    target_flow = str(plan.get("target_flow", "")).strip()
    if target_flow:
        lines.append(f"### Target-Flow\n{target_flow}\n")

    state_machine = str(plan.get("state_machine", "")).strip()
    if state_machine:
        lines.append(f"### State-Machine\n{state_machine}\n")

    blocker_taxonomy = str(plan.get("blocker_taxonomy", "")).strip()
    if blocker_taxonomy:
        lines.append(f"### Blocker-Taxonomy\n{blocker_taxonomy}\n")

    audit = str(plan.get("audit", "")).strip()
    if audit:
        lines.append(f"### Audit\n{audit}\n")

    go_no_go = str(plan.get("go_no_go", "")).strip()
    if go_no_go:
        lines.append(f"### Go/No-Go\n{go_no_go}\n")

    test_strategy = str(plan.get("test_strategy", "")).strip()
    if test_strategy:
        lines.append(f"### Test Strategy\n{test_strategy}\n")

    assumptions = str(plan.get("assumptions", "")).strip()
    if assumptions:
        lines.append(f"### Assumptions\n{assumptions}\n")

    risks = str(plan.get("risks", "")).strip()
    if risks:
        lines.append(f"### Risks\n{risks}\n")

    non_goals = str(plan.get("non_goals", "")).strip()
    if non_goals:
        lines.append(f"### Non-Goals\n{non_goals}\n")

    open_questions = str(plan.get("open_questions", "")).strip()
    if open_questions:
        lines.append(f"### Open Questions\n{open_questions}\n")

    reason_code = str(plan.get("reason_code", "")).strip()
    if reason_code:
        lines.append(f"### Reason Code\n{reason_code}\n")

    return "\n".join(lines).rstrip() + "\n"


def _extract_markdown_section(plan_text: str, heading: str) -> str:
    lines = [line.rstrip("\n") for line in str(plan_text or "").splitlines()]
    marker = f"## {heading}".lower()
    start = -1
    for idx, line in enumerate(lines):
        if line.strip().lower() == marker:
            start = idx + 1
            break
    if start == -1:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def _parse_bullets(text: str) -> list[str]:
    out: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        token = line.lstrip("-").strip()
        if token.startswith("[ ]"):
            token = token[3:].strip()
        if token:
            out.append(token)
    return out


def _machine_requirements_from_markdown(*, raw_source: str = "") -> list[dict[str, object]]:
    """Extract compilable machine requirements from allowlisted markdown sections only."""
    source = str(raw_source or "").strip()
    if not source:
        return []
    first_line = ""
    for raw in source.splitlines():
        line = re.sub(r"\s+", " ", raw.strip())
        if not line:
            continue
        if line.startswith("#"):
            continue
        first_line = line
        break
    if not first_line:
        return []
    return [
        {
            "title": first_line,
            "kind": "required_behavior",
            "required_behavior": f"Implement: {first_line}",
            "forbidden_behavior": f"forbid state: {first_line} not satisfied",
            "code_hotspots": [
                "governance_runtime/entrypoints/session_reader.py",
                "governance_runtime/entrypoints/implement_start.py",
            ],
            "verification_methods": [
                "behavioral_verification",
                "live_flow_verification",
                "static_verification",
            ],
        }
    ]


def _legacy_markdown_requirements_enabled() -> bool:
    token = str(os.environ.get("GOVERNANCE_ALLOW_LEGACY_MARKDOWN_REQUIREMENTS") or "").strip().lower()
    return token in {"1", "true", "yes", "on"}


def _call_llm_review(
    content: str,
    mandate: str,
    effective_review_policy: str = "",
    workspace_dir: Path | None = None,
    config_root: Path | None = None,
    workspaces_home: Path | None = None,
    repo_fingerprint: str | None = None,
) -> dict[str, object]:
    """Call LLM for review with structured output enforcement."""
    try:
        pipeline_mode, binding_value, _binding_source = _resolve_plan_review_binding(
            workspace_dir=workspace_dir
        )
    except GovernanceBindingResolutionError as exc:
        return {
            "llm_invoked": False,
            "verdict": "changes_requested",
            "findings": [str(exc)],
            "binding_role": "review",
        }

    binding_source = str(_binding_source or "").strip()

    executor_cmd = binding_value if pipeline_mode else ""

    resolved_workspaces_home = workspaces_home
    resolved_repo_fingerprint = str(repo_fingerprint or "").strip()
    if resolved_workspaces_home is None or not resolved_repo_fingerprint:
        scope_root = workspace_dir or config_root or (Path.home() / ".governance")
        resolved_workspaces_home = scope_root / "workspaces"
        candidate = str(scope_root.name or "").strip()
        if re.fullmatch(r"[0-9a-f]{24}", candidate):
            resolved_repo_fingerprint = candidate
        else:
            resolved_repo_fingerprint = hashlib.sha256(str(scope_root).encode("utf-8")).hexdigest()[:24]

    governance_root = resolved_workspaces_home
    review_dir = governance_review_dir(resolved_workspaces_home, resolved_repo_fingerprint)
    runtime_state_dir = governance_runtime_state_dir(resolved_workspaces_home, resolved_repo_fingerprint)
    review_dir.mkdir(parents=True, exist_ok=True)
    context_file = review_dir / "llm_review_context.json"
    stdout_file = review_dir / "llm_review_stdout.log"
    stderr_file = review_dir / "llm_review_stderr.log"

    runtime_state_dir.mkdir(parents=True, exist_ok=True)

    try:
        materialization = materialize_governance_artifacts(
            output_dir=runtime_state_dir,
            config_root=governance_root,
            review_mandate=mandate if mandate else None,
            effective_policy=effective_review_policy if effective_review_policy else None,
        )
    except GovernanceContextMaterializationError as e:
        return {
            "llm_invoked": False,
            "verdict": "changes_requested",
            "findings": [f"governance-context-materialization-failed: {e.reason}"],
            "reason_code": e.reason_code,
            "pipeline_mode": pipeline_mode,
            "binding_role": "review",
            "binding_source": binding_source,
        }

    output_schema_text = _get_review_output_schema_text()
    instruction_parts = []
    if materialization.review_mandate_file:
        instruction_parts.append(
            f"Load the review mandate from file: {materialization.review_mandate_file} "
            f"(SHA256: {materialization.review_mandate_sha256})"
        )
    if materialization.effective_policy_file:
        instruction_parts.append(
            f"Load the effective policy from file: {materialization.effective_policy_file} "
            f"(SHA256: {materialization.effective_policy_sha256})"
        )
    instruction_parts.append(
        "You MUST respond with valid JSON that conforms to the output schema below.\n"
        "All textual output MUST be in English only (language='en').\n"
        "Do NOT include any text outside the JSON object.\n\n"
        "Output schema:\n" + output_schema_text
    )

    context = {
        "schema": "opencode.review.llm-context.v3",
        "content_to_review": content,
    }
    if materialization.review_mandate_file:
        context["review_mandate_file"] = str(materialization.review_mandate_file)
        context["review_mandate_sha256"] = materialization.review_mandate_sha256
        context["review_mandate_label"] = materialization.review_mandate_label
    if materialization.effective_policy_file:
        context["effective_policy_file"] = str(materialization.effective_policy_file)
        context["effective_policy_sha256"] = materialization.effective_policy_sha256
        context["effective_policy_label"] = materialization.effective_policy_label
    context["effective_policy_loaded"] = materialization.has_materialized()
    if materialization.has_materialized():
        context["context_materialization_complete"] = True
    context["instruction"] = "\n".join(instruction_parts)
    atomic_write_text(context_file, json.dumps(context, ensure_ascii=True, indent=2) + "\n")

    try:
        validate_materialized_artifacts(materialization)
    except GovernanceContextMaterializationError as e:
        return {
            "llm_invoked": False,
            "verdict": "changes_requested",
            "findings": [f"governance-context-validation-failed: {e.reason}"],
            "reason_code": e.reason_code,
            "pipeline_mode": pipeline_mode,
            "binding_role": "review",
            "binding_source": binding_source,
        }

    bridge_mode = False
    if not executor_cmd and not pipeline_mode and _has_active_desktop_llm_binding():
        bridge_cmd = _resolve_desktop_bridge_cmd(
            repo_root=Path.cwd(),
            message="Read the attached review context JSON and produce only valid JSON conforming to the provided output schema.",
        )
        if bridge_cmd:
            executor_cmd = bridge_cmd
            bridge_mode = True
        else:
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": [
                    "Direct mode review binding resolved to active chat binding, but no callable desktop bridge with a resolvable session id is available."
                ],
                "reason_code": "BLOCKED-REVIEW-EXECUTOR-UNAVAILABLE",
                "pipeline_mode": pipeline_mode,
                "binding_role": "review",
                "binding_source": binding_source,
                "binding_resolved": True,
                "invoke_backend_available": False,
            }

    final_cmd = executor_cmd
    if "{context_file}" in final_cmd:
        final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))
    import subprocess
    try:
        result = subprocess.run(
            final_cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=_bridge_timeout_seconds() if bridge_mode else None,
            env=_build_bridge_env() if bridge_mode else None,
        )
        atomic_write_text(stdout_file, str(result.stdout or ""))
        atomic_write_text(stderr_file, str(result.stderr or ""))
        response_text = result.stdout or ""
        if not response_text.strip():
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": ["LLM executor returned empty response"],
                "pipeline_mode": pipeline_mode,
                "binding_role": "review",
                "binding_source": binding_source,
            }
        if bridge_mode and '"type":"tool_use"' in response_text and '"type":"text"' not in response_text:
            return {
                "llm_invoked": False,
                "verdict": "changes_requested",
                "findings": ["review-llm-tool-use-disallowed"],
                "reason_code": BLOCKED_REVIEW_TOOL_USE_DISALLOWED,
                "pipeline_mode": pipeline_mode,
                "binding_role": "review",
                "binding_source": binding_source,
            }
        response_text = _parse_json_events_to_text(response_text)
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
        parsed = _parse_llm_review_response(response_text, mandates_schema=mandates_schema)
        parsed["pipeline_mode"] = pipeline_mode
        parsed["binding_role"] = "review"
        parsed["binding_source"] = binding_source
        return parsed
    except subprocess.TimeoutExpired:
        return {
            "llm_invoked": False,
            "verdict": "changes_requested",
            "findings": ["review-llm-timeout"],
            "reason_code": BLOCKED_REVIEW_EXECUTOR_TIMEOUT,
            "pipeline_mode": pipeline_mode,
            "binding_role": "review",
            "binding_source": binding_source,
        }
    except Exception as exc:
        atomic_write_text(stderr_file, str(exc))
        return {
            "llm_invoked": False,
            "error": str(exc),
            "verdict": "changes_requested",
            "findings": [f"LLM review failed: {exc}"],
            "pipeline_mode": pipeline_mode,
            "binding_role": "review",
            "binding_source": binding_source,
        }


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
        from llm_response_validator import (
            coerce_output_against_mandates_schema,
            validate_review_response,
        )
    except (ImportError, ModuleNotFoundError):
        validate_review_response = None
        coerce_output_against_mandates_schema = None

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

    if coerce_output_against_mandates_schema is not None:
        normalized = coerce_output_against_mandates_schema(
            parsed_data,
            mandates_schema,
            "reviewOutputSchema",
        )
        if isinstance(normalized, dict):
            parsed_data = normalized

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
    source_authority: str,
    compiler_notes: list[str],
) -> tuple[str, int]:
    payload = {
        "schema": "governance-compiled-requirements.v1",
        "generated_at": generated_at,
        "source_authority": source_authority,
        "compiler_notes": compiler_notes,
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


def _has_any_llm_executor(*, workspace_dir: Path | None) -> bool:
    """Check if review-capable binding is available for current mode."""
    try:
        _resolve_plan_review_binding(workspace_dir=workspace_dir)
        return True
    except GovernanceBindingResolutionError:
        return False


def _run_internal_phase5_self_review(
    plan_text: str,
    state: Mapping[str, object] | None = None,
    commands_home: Path | None = None,
    workspace_dir: Path | None = None,
    config_root: Path | None = None,
    workspaces_home: Path | None = None,
    repo_fingerprint: str | None = None,
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
    except (OSError, IOError, PermissionError) as e:
        return {
            "blocked": True,
            "reason": "mandate-schema-io-error",
            "reason_code": BLOCKED_P5_PLAN_RECORD_PERSIST,
            "recovery_action": f"Cannot read mandate schema: {e}",
        }

    iteration = 0
    prev_digest = _digest(current_text)
    final_digest = prev_digest
    revision_delta = "none"
    findings_summary: list[str] = []
    audit_rows: list[dict[str, object]] = []
    llm_review_results: list[dict[str, object]] = []
    review_pipeline_mode: bool | None = None
    review_binding_source = ""
    has_executor = _has_any_llm_executor(workspace_dir=workspace_dir)
    desktop_binding_fallback = _has_active_desktop_llm_binding()

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
                if desktop_binding_fallback:
                    effective_review_policy = ""
                    effective_policy_error = ""
                else:
                    return {
                        "blocked": True,
                        "reason": "effective-review-policy-unavailable",
                        "reason_code": BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
                        "recovery_action": "Ensure rulebooks and addons are loadable and contain valid policy content.",
                    }

        if has_executor:
            llm_result = _call_llm_review(
                current_text,
                mandate_text,
                effective_review_policy,
                workspace_dir=workspace_dir,
                config_root=config_root,
                workspaces_home=workspaces_home,
                repo_fingerprint=repo_fingerprint,
            )
            llm_review_results.append(llm_result)
            if llm_result.get("reason_code") in {
                BLOCKED_REVIEW_EXECUTOR_TIMEOUT,
                BLOCKED_REVIEW_TOOL_USE_DISALLOWED,
            }:
                finding = "review-executor-blocked"
                raw_findings = llm_result.get("findings")
                if isinstance(raw_findings, list) and raw_findings:
                    finding = str(raw_findings[0])
                return {
                    "blocked": True,
                    "reason": finding,
                    "reason_code": str(llm_result.get("reason_code") or BLOCKED_P5_PLAN_RECORD_PERSIST),
                    "recovery_action": "Retry /plan after ensuring review returns direct JSON text and session remains responsive.",
                }
            if "pipeline_mode" in llm_result:
                review_pipeline_mode = bool(llm_result.get("pipeline_mode"))
            if llm_result.get("binding_source"):
                review_binding_source = str(llm_result.get("binding_source") or "")
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
        "review_pipeline_mode": review_pipeline_mode,
        "review_binding_role": "review",
        "review_binding_source": review_binding_source,
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
    raw_plan_source = plan_text

    # ── Load session state early (needed for auto-generation) ──
    try:
        session_path, repo_fingerprint, workspaces_home, workspace_dir = resolve_active_session_paths()
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

    structured_plan: dict[str, object] | None = None

    # ── Optional structured explicit input parse (JSON planOutputSchema) ──
    if plan_text and plan_text.lstrip().startswith("{"):
        parsed_input = _parse_plan_generation_response(plan_text, re_review=False)
        if parsed_input.get("blocked") is False:
            parsed_structured = parsed_input.get("structured_plan")
            if isinstance(parsed_structured, Mapping):
                structured_plan = dict(parsed_structured)
                plan_text = _canonicalize_text(str(parsed_input.get("plan_text") or plan_text))

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
            workspace_dir=workspace_dir,
            config_root=evidence.config_root,
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
        )
        if gen_result.get("blocked") is True:
            payload = _payload(
                "blocked",
                reason_code=str(gen_result.get("reason_code") or BLOCKED_PLAN_GENERATION_FAILED),
                reason=str(gen_result.get("reason") or "plan-generation-failed"),
                recovery_action=str(gen_result.get("recovery_action") or "provide plan text via --plan-text or check LLM executor"),
                pipeline_mode=gen_result.get("pipeline_mode"),
                binding_role=gen_result.get("binding_role"),
                binding_source=gen_result.get("binding_source"),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        plan_text = _canonicalize_text(str(gen_result.get("plan_text") or ""))
        candidate_structured = gen_result.get("structured_plan")
        if isinstance(candidate_structured, Mapping):
            structured_plan = dict(candidate_structured)
        if not plan_text:
            payload = _payload(
                "blocked",
                reason_code=BLOCKED_PLAN_GENERATION_FAILED,
                reason="plan-generation-empty-result",
                recovery_action="LLM generated an empty plan. Provide plan text via --plan-text.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        state["phase5_plan_execution_pipeline_mode"] = bool(gen_result.get("pipeline_mode", False))
        state["phase5_plan_execution_binding_role"] = str(gen_result.get("binding_role") or "execution")
        if gen_result.get("binding_source"):
            state["phase5_plan_execution_binding_source"] = str(gen_result.get("binding_source") or "")

    # ── Standard Phase 5 flow ──
    try:
        phase_before = get_phase(state)

        # /plan may be the directed exit rail from Phase-6 rework clarification.
        # Consume clarification state first, then force deterministic Phase-5
        # plan-record entry to avoid self-looping back into clarification.
        if consume_rework_clarification_state(state, consumed_by="plan", consumed_at=_now_iso()):
            state["phase"] = "5-ArchitectureReview"
            state["next"] = "5"
            state["active_gate"] = "Plan Record Preparation Gate"
            state["next_gate_condition"] = "Persist plan record evidence"

        mode = str(state.get("Mode") or "IN_PROGRESS")
        phase_for_write = str(get_phase(state) or phase_before or "5")
        session_run_id = str(state.get("session_run_id") or state.get("SessionRunId") or "")
        plan_digest = _digest(plan_text)

        token_before = _phase_token(str(get_phase(state) or phase_before))
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
        review_result = _run_internal_phase5_self_review(
            plan_text,
            state=state,
            commands_home=commands_home,
            workspace_dir=workspace_dir,
            config_root=evidence.config_root,
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
            max_iterations=max_iterations,
        )
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

        machine_requirements: list[dict[str, object]] = []
        source_authority = "machine_requirements"
        if isinstance(structured_plan, Mapping):
            machine_requirements = build_machine_requirements(structured_plan)
        if not machine_requirements and _legacy_markdown_requirements_enabled():
            machine_requirements = _machine_requirements_from_markdown(raw_source=raw_plan_source)
            if machine_requirements:
                source_authority = "legacy_markdown_requirements"

        if not machine_requirements:
            payload = _payload(
                "blocked",
                reason_code="REQUIREMENT_SOURCE_INVALID",
                reason="machine-requirements-missing",
                observed=[
                    "structured_plan_missing_or_invalid",
                    "legacy_markdown_mode_disabled_or_unusable",
                ],
                recovery_action=(
                    "Provide structured machine requirements via structured plan input, "
                    "or explicitly enable GOVERNANCE_ALLOW_LEGACY_MARKDOWN_REQUIREMENTS=1 for migration runs."
                ),
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2

        compiled = compile_plan_to_requirements(
            plan_text=final_plan_text,
            scope_prefix="PLAN",
            machine_requirements=machine_requirements,
            strict_source="machine_requirements",
        )
        if not compiled.requirements:
            payload = _payload(
                "blocked",
                reason_code="REQUIREMENT_SOURCE_INVALID",
                reason="compiled-requirements-source-invalid",
                observed=list(compiled.notes),
                recovery_action="Provide structured machine requirements and rerun /plan.",
            )
            print(json.dumps(payload, ensure_ascii=True))
            return 2
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
            source_authority=source_authority,
            compiler_notes=list(compiled.notes),
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
                    "phase": str(get_phase(state) or "5-ArchitectureReview"),
                    "session_run_id": session_run_id,
                    "trigger": "phase5-plan-record-rail",
                    "plan_record_text": plan_text,
                    "plan_record_digest": f"sha256:{plan_digest}",
                    "machine_requirements": machine_requirements,
                    "machine_requirements_source_authority": source_authority,
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
                    "phase": str(get_phase(state) or "5-ArchitectureReview"),
                    "session_run_id": session_run_id,
                    "trigger": "phase5-self-review-loop",
                    "plan_record_text": final_plan_text,
                    "plan_record_digest": f"sha256:{review_digest}",
                    "machine_requirements": machine_requirements,
                    "machine_requirements_source_authority": source_authority,
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
        state["requirement_contracts_source_authority"] = source_authority
        state["machine_requirements_count"] = len(machine_requirements)
        state["requirement_compiler_notes"] = list(compiled.notes)
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
        state["phase5_review_pipeline_mode"] = bool(review_result.get("review_pipeline_mode") is True)
        state["phase5_review_binding_role"] = str(review_result.get("review_binding_role") or "review")
        if review_result.get("review_binding_source"):
            state["phase5_review_binding_source"] = str(review_result.get("review_binding_source") or "")

        for row in _as_list(review_result.get("audit_rows")):
            if not isinstance(row, Mapping):
                continue
            _append_jsonl(
                session_path.parent / "logs" / "events.jsonl",
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
            requested_phase=normalize_phase_token(str(get_phase(state) or "5")) or "5",
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
            session_path.parent / "logs" / "events.jsonl",
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
                "requirement_contracts_source_authority": source_authority,
                "machine_requirements_count": len(machine_requirements),
                "requirement_compiler_notes": list(compiled.notes),
                "plan_execution_pipeline_mode": state.get("phase5_plan_execution_pipeline_mode"),
                "plan_execution_binding_source": state.get("phase5_plan_execution_binding_source", ""),
                "review_pipeline_mode": state.get("phase5_review_pipeline_mode"),
                "review_binding_source": state.get("phase5_review_binding_source", ""),
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
