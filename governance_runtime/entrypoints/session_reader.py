#!/usr/bin/env python3
"""Governance session reader -- self-bootstrapping entrypoint.

Reads SESSION_STATE.json via the global pointer and emits the guided
governance surface in normal mode. Debug, audit, and diagnostic views are
explicit opt-in modes.

Self-bootstrapping: this script resolves commands_home from binding evidence
or canonical config-root environment, then reads governance.paths.json for
validation. No external PYTHONPATH setup is required.

Normal mode output is the guided presentation used by operators. Debug and
diagnostic modes emit a machine-readable key-value view for troubleshooting.
On error: prints ``status: ERROR`` with a human-readable ``error:`` line.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from governance_runtime.engine.next_action_resolver import resolve_next_action
from governance_runtime.infrastructure.session_pointer import (
    CANONICAL_POINTER_SCHEMA,
    is_session_pointer_document,
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance_runtime.receipts.store import build_presentation_receipt

# ---------------------------------------------------------------------------
# Schema / version constants
# ---------------------------------------------------------------------------
POINTER_SCHEMA = CANONICAL_POINTER_SCHEMA


def _derive_commands_home() -> Path:
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

    return (Path.home() / ".config" / "opencode" / "commands").resolve()


def _ensure_commands_home_on_syspath(commands_home: Path) -> None:
    root = str(commands_home)
    if root and root not in sys.path:
        sys.path.insert(0, root)


from governance_runtime.infrastructure.json_store import append_jsonl as _append_jsonl
from governance_runtime.infrastructure.json_store import load_json as _read_json
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic
from governance_runtime.infrastructure.number_utils import coerce_int as _coerce_int
from governance_runtime.infrastructure.number_utils import quote_if_needed as _quote_if_needed
from governance_runtime.infrastructure.text_utils import format_list as _format_list
from governance_runtime.infrastructure.text_utils import safe_str as _safe_str
from governance_runtime.infrastructure.text_utils import sha256_text as _sha256_text
from governance_runtime.infrastructure.text_utils import truncate_text as _truncate_text
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso

# Import from orchestrator package (main API)
from governance_runtime.application.services.phase6_review_orchestrator import (
    run_review_loop,
    ReviewLoopConfig,
    ReviewResult,
    BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
)

# Import legacy compatibility helpers from dedicated module
from governance_runtime.application.services.phase6_review_orchestrator.legacy_compat import (
    load_mandates_schema as _load_mandates_schema,
    get_review_output_schema_text as _get_review_output_schema_text,
    build_review_mandate_text as _build_review_mandate_text,
    load_effective_review_policy_text as _load_effective_review_policy_text,
    has_any_llm_executor as _has_any_llm_executor,
    parse_llm_review_response as _parse_llm_review_response,
    read_plan_body as _build_plan_body,
    sync_phase6_completion_fields as _sync_phase6_completion_fields,
)

# Import from snapshot renderer
from governance_runtime.application.services.snapshot_renderer import (
    SNAPSHOT_SCHEMA,
    _GATE_PURPOSES,
    _append_list,
    _display_phase,
    _has_blocker,
    _render_blocker,
    _render_current_state,
    _render_execution_progress,
    _render_presented_review_content,
    _render_what_now,
    _resolve_next_action_line,
    _section,
    _should_emit_continue_next_action,
    format_guided_snapshot,
    format_snapshot,
)

# Import Phase-5 normalizer functions
from governance_runtime.application.services.phase5_normalizer import (
    canonicalize_legacy_p5x_surface as _canonicalize_legacy_p5x_surface,
    sync_conditional_p5_gate_states as _sync_conditional_p5_gate_states,
    normalize_phase6_p5_state as _normalize_phase6_p5_state,
)


def _public_next_token(value: object) -> str:
    raw = _safe_str(value)
    if not raw:
        return ""
    head = raw.split("-", 1)[0].strip()
    if "." in head:
        head = head.split(".", 1)[0]
    return head


def _build_ticket_summary(state_view: Mapping[str, object]) -> str:
    ticket = _truncate_text(state_view.get("Ticket"))
    task = _truncate_text(state_view.get("Task"))
    if ticket != "none":
        return ticket
    if task != "none":
        return task
    return "none"


def _build_plan_summary(*, state_view: Mapping[str, object], session_path: Path) -> str:
    try:
        plan_record_path = session_path.parent / "plan-record.json"
        if plan_record_path.is_file():
            payload = _read_json(plan_record_path)
            versions = payload.get("versions")
            if isinstance(versions, list) and versions:
                latest = versions[-1] if isinstance(versions[-1], dict) else {}
                if isinstance(latest, dict):
                    text = _truncate_text(latest.get("plan_record_text"))
                    if text != "none":
                        return text
    except Exception:
        pass
    return _truncate_text(state_view.get("phase5_plan_record_digest"))




def _persist_review_package_markers(*, state_doc: dict, session_path: Path) -> None:
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc
    phase = str(state.get("Phase") or state.get("phase") or "").strip()
    gate = str(state.get("active_gate") or "").strip().lower()

    if not phase.startswith("6") or gate != "evidence presentation gate":
        return

    plan_body = _build_plan_body(session_path=session_path)
    state["review_package_review_object"] = "Final Phase-6 implementation review decision"
    state["review_package_ticket"] = _build_ticket_summary(state)
    state["review_package_approved_plan_summary"] = _build_plan_summary(
        state_view=state,
        session_path=session_path,
    )
    state["review_package_plan_body"] = plan_body
    state["review_package_implementation_scope"] = "Implement the approved plan record in this repository."
    state["review_package_constraints"] = "Governance guards remain active; implementation must follow the approved plan scope."
    state["review_package_decision_semantics"] = (
        "approve=governance complete + implementation authorized; "
        "changes_requested=enter rework clarification gate; "
        "reject=return to phase 4 ticket input gate"
    )
    state["review_package_presented"] = True
    state["review_package_plan_body_present"] = plan_body != "none"
    receipt_source = "|".join(
        [
            str(state.get("review_package_review_object") or ""),
            str(state.get("review_package_ticket") or ""),
            str(state.get("review_package_approved_plan_summary") or ""),
            str(state.get("review_package_plan_body") or ""),
            str(state.get("review_package_implementation_scope") or ""),
            str(state.get("review_package_constraints") or ""),
            str(state.get("review_package_decision_semantics") or ""),
        ]
    )
    rendered_at = _now_iso()
    session_id = str(state.get("session_run_id") or session_path.parent.name or "unknown-session")
    state_revision = str(state.get("session_state_revision") or "")
    state["review_package_last_state_change_at"] = str(state.get("session_materialized_at") or rendered_at)
    state["review_package_presentation_receipt"] = build_presentation_receipt(
        receipt_type="governance_review_presentation_receipt",
        requirement_scope="R-REVIEW-DECISION-001",
        content_source=receipt_source,
        rendered_at=rendered_at,
        render_event_id=str(state.get("session_materialization_event_id") or ""),
        gate="Evidence Presentation Gate",
        session_id=session_id,
        state_revision=state_revision,
        source_command="/continue",
    )


def _persist_implementation_package_markers(*, state_doc: dict) -> None:
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc
    phase = str(state.get("Phase") or state.get("phase") or "").strip()
    gate = str(state.get("active_gate") or "").strip().lower()
    if not phase.startswith("6") or gate != "implementation presentation gate":
        return

    changed_files = state.get("implementation_package_changed_files") or state.get("implementation_changed_files") or []
    findings_fixed = state.get("implementation_package_findings_fixed") or state.get("implementation_findings_fixed") or []
    findings_open = state.get("implementation_package_findings_open") or state.get("implementation_open_findings") or []
    checks = state.get("implementation_package_checks") or []

    receipt_source = "|".join(
        [
            str(state.get("implementation_package_review_object") or "Implemented result review"),
            str(state.get("implementation_package_plan_reference") or "latest approved plan record"),
            json.dumps(changed_files, ensure_ascii=True, sort_keys=True),
            json.dumps(findings_fixed, ensure_ascii=True, sort_keys=True),
            json.dumps(findings_open, ensure_ascii=True, sort_keys=True),
            json.dumps(checks, ensure_ascii=True, sort_keys=True),
            str(state.get("implementation_package_stability") or ""),
        ]
    )
    state["implementation_package_presented"] = True
    rendered_at = _now_iso()
    session_id = str(state.get("session_run_id") or "unknown-session")
    state_revision = str(state.get("session_state_revision") or "")
    state["implementation_package_last_state_change_at"] = str(state.get("session_materialized_at") or rendered_at)
    state["implementation_package_presentation_receipt"] = build_presentation_receipt(
        receipt_type="implementation_presentation_receipt",
        requirement_scope="R-IMPLEMENTATION-DECISION-001",
        content_source=receipt_source,
        rendered_at=rendered_at,
        render_event_id=str(state.get("session_materialization_event_id") or ""),
        gate="Implementation Presentation Gate",
        session_id=session_id,
        state_revision=state_revision,
        source_command="/continue",
    )


def _resolve_session_document(commands_home: Path) -> tuple[Path, dict, Path, dict]:
    config_root = commands_home.parent
    pointer_path = config_root / "SESSION_STATE.json"
    if not pointer_path.exists():
        raise RuntimeError(f"No session pointer at {pointer_path}")

    try:
        raw_pointer = _read_json(pointer_path)
    except Exception as exc:
        raise RuntimeError(f"Invalid session pointer JSON: {exc}") from exc

    try:
        if not is_session_pointer_document(raw_pointer):
            if "schema" in raw_pointer:
                parse_session_pointer_document(raw_pointer)
            raise ValueError("Document is not a session pointer")
        pointer = parse_session_pointer_document(raw_pointer)
        session_path = resolve_active_session_state_path(pointer, config_root=config_root)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    if not session_path.exists():
        raise RuntimeError(f"Workspace session state missing: {session_path}")

    try:
        state = _read_json(session_path)
    except Exception as exc:
        raise RuntimeError(f"Invalid workspace session state JSON: {exc}") from exc
    return config_root, pointer, session_path, state


def _session_state_view(state: dict) -> dict:
    nested = state.get("SESSION_STATE")
    return nested if isinstance(nested, dict) else state


def _transition_evidence_truthy(state_view: dict, state_doc: dict) -> bool:
    raw = state_view.get("phase_transition_evidence", state_doc.get("phase_transition_evidence"))
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return bool(raw.strip())
    if isinstance(raw, list):
        return len(raw) > 0
    return False


def _build_runtime_context(
    *, commands_home: Path, config_root: Path, pointer: dict, state_doc: dict,
) -> tuple[str, Any]:
    """Build a RuntimeContext and resolved phase token from session state.

    Returns (requested_phase, RuntimeContext).  Shared by both the
    materialise (write) and readonly-eval (read) code paths.
    """
    from governance_runtime.domain.phase_state_machine import normalize_phase_token
    from governance_runtime.kernel.phase_kernel import RuntimeContext

    state_view = _session_state_view(state_doc)
    persisted_phase = normalize_phase_token(
        state_view.get("Phase")
        or state_view.get("phase")
        or state_doc.get("Phase")
        or state_doc.get("phase")
        or "4"
    ) or "4"

    requested_phase = persisted_phase
    next_token = normalize_phase_token(
        state_view.get("Next")
        or state_view.get("next")
        or state_doc.get("Next")
        or state_doc.get("next")
        or ""
    )

    # Stay-strategy phases may advertise a next_token that differs from the
    # current persisted phase (e.g. Phase 5 → 5.3 forward, Phase 6 → 4 on
    # reject).  When phase_transition_evidence is present, honour the
    # advertised next_token as the execution target so the session actually
    # advances (or retreats) instead of looping on the same stay-phase.
    if (
        next_token
        and next_token != persisted_phase
        and _transition_evidence_truthy(state_view, state_doc)
    ):
        requested_phase = next_token

    requested_active_gate = str(
        state_view.get("active_gate")
        or state_doc.get("active_gate")
        or "Ticket Input Gate"
    )
    requested_next_gate_condition = str(
        state_view.get("next_gate_condition")
        or state_doc.get("next_gate_condition")
        or "Continue automatic phase routing"
    )
    repo_fingerprint = str(
        pointer.get("activeRepoFingerprint")
        or state_view.get("RepoFingerprint")
        or state_view.get("repo_fingerprint")
        or ""
    ).strip() or None

    ctx = RuntimeContext(
        requested_active_gate=requested_active_gate,
        requested_next_gate_condition=requested_next_gate_condition,
        repo_is_git_root=True,
        live_repo_fingerprint=repo_fingerprint,
        commands_home=commands_home,
        workspaces_home=config_root / "workspaces",
        config_root=config_root,
    )
    return requested_phase, ctx


def _materialize_authoritative_state(*, commands_home: Path, config_root: Path, pointer: dict, session_path: Path, state_doc: dict) -> dict:
    from governance_runtime.application.use_cases.session_state_helpers import with_kernel_result
    from governance_runtime.kernel.phase_kernel import execute
    from governance_runtime.infrastructure.json_store import append_jsonl

    _canonicalize_legacy_p5x_surface(state_doc=state_doc)

    requested_phase, ctx = _build_runtime_context(
        commands_home=commands_home,
        config_root=config_root,
        pointer=pointer,
        state_doc=state_doc,
    )

    # Run Phase-6 review loop (orchestrator returns result, doesn't mutate state)
    if requested_phase.startswith("6"):
        state_obj = state_doc.get("SESSION_STATE")
        state = state_obj if isinstance(state_obj, dict) else state_doc
        config = ReviewLoopConfig.from_state(
            state=state,
            session_path=session_path,
            commands_home=commands_home,
        )
        review_result = run_review_loop(state_doc=state_doc, config=config)

        # Apply result to state (entrypoint's responsibility)
        if review_result.success and review_result.loop_result:
            updates = review_result.loop_result.to_state_updates()
            state.update(updates)

            # Persist audit events (entrypoint's responsibility)
            events = review_result.loop_result.to_audit_events()
            if events:
                events_path = session_path.parent / "events.jsonl"
                for row in events:
                    row["observed_at"] = _now_iso()
                    append_jsonl(events_path, row)

    result = execute(
        current_token=requested_phase,
        session_state_doc=state_doc,
        runtime_ctx=ctx,
    )

    materialized = dict(
        with_kernel_result(
            state_doc,
            phase=result.phase,
            next_token=result.next_token,
            active_gate=result.active_gate,
            next_gate_condition=result.next_gate_condition,
            status=result.status,
            spec_hash=result.spec_hash,
            spec_path=result.spec_path,
            spec_loaded_at=result.spec_loaded_at,
            log_paths=result.log_paths,
            event_id=result.event_id,
            plan_record_status=result.plan_record_status,
            plan_record_versions=result.plan_record_versions,
        )
    )

    ss = materialized.get("SESSION_STATE")
    if isinstance(ss, dict):
        source = str(result.source or "").strip().lower()
        phase_after = str(result.phase or "").strip()
        if source in {"phase-6-changes-requested-loop-reset", "phase-6-rejected-to-phase4"} or not phase_after.startswith("6"):
            ss.pop("UserReviewDecision", None)
            ss.pop("user_review_decision", None)

    # Auto-grant phase_transition_evidence when the kernel successfully
    # evaluates a forward transition (Fix 2.0 / Ergänzung C).
    # This prevents /continue self-loops where evidence stays False
    # because only bootstrap_preflight used to set it.
    # Fix 2.1: Also grant for stay-strategy phases that advertise a forward
    # next_token (e.g. Phase 5 stay → 5.3).  Without this, stay-strategy
    # phases can never transition because the evidence is never set.
    # Fix 2.2: Normalise result.phase to a token before comparing so that
    # stay-strategy self-loops (e.g. token "6" / phase "6-PostFlight") are
    # correctly detected as *non*-forward and do not set evidence spuriously.
    from governance_runtime.domain.phase_state_machine import normalize_phase_token as _npt
    _phase_as_token = _npt(str(result.phase or ""))
    _has_forward_transition = (
        result.route_strategy == "next"
        or (
            result.route_strategy == "stay"
            and result.next_token
            and str(result.next_token).strip() != _phase_as_token
        )
    )
    if result.status == "OK" and _has_forward_transition:
        ss = materialized.get("SESSION_STATE")
        if isinstance(ss, dict):
            ss["phase_transition_evidence"] = True

    state_obj = materialized.get("SESSION_STATE")
    state_map = state_obj if isinstance(state_obj, dict) else materialized
    if not str(state_map.get("session_run_id") or "").strip():
        state_map["session_run_id"] = f"session-{uuid.uuid4().hex[:12]}"
    current_revision = 0
    try:
        current_revision = int(str(state_map.get("session_state_revision") or "0").strip())
    except ValueError:
        current_revision = 0
    state_map["session_state_revision"] = current_revision + 1
    state_map["session_materialization_event_id"] = f"mat-{uuid.uuid4().hex}"
    state_map["session_materialized_at"] = _now_iso()

    _sync_conditional_p5_gate_states(state_doc=materialized)
    _sync_phase6_completion_fields(state_doc=materialized)
    _normalize_phase6_p5_state(
        state_doc=materialized,
        events_path=session_path.parent / "events.jsonl",
    )
    _persist_review_package_markers(state_doc=materialized, session_path=session_path)
    _persist_implementation_package_markers(state_doc=materialized)

    _write_json_atomic(session_path, materialized)
    return materialized


def read_session_snapshot(commands_home: Path | None = None, *, materialize: bool = False) -> dict:
    """Read governance session state and return the render source payload.

    Parameters
    ----------
    commands_home:
        Override for commands_home (useful for testing). If *None*, derived
        from the script's own filesystem location.

    Returns
    -------
    dict
        Render source payload with at minimum ``schema`` and ``status`` keys.
    """
    if commands_home is None:
        commands_home = _derive_commands_home()
    _ensure_commands_home_on_syspath(commands_home)
    from governance_runtime.infrastructure.plan_record_state import resolve_plan_record_signal

    try:
        config_root, pointer, session_path, state = _resolve_session_document(commands_home)
    except Exception as exc:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": str(exc),
        }

    _canonicalize_legacy_p5x_surface(state_doc=state)

    if materialize:
        try:
            state = _materialize_authoritative_state(
                commands_home=commands_home,
                config_root=config_root,
                pointer=pointer,
                session_path=session_path,
                state_doc=state,
            )
        except Exception as exc:
            return {
                "schema": SNAPSHOT_SCHEMA,
                "status": "ERROR",
                "error": f"Materialization failed: {exc}",
            }

    # --- 3b. Readonly kernel evaluation for non-materialize readout ---
    # When not materializing we still want *fresh* phase / gate / status
    # values computed by the kernel rather than stale persisted fields.
    # evaluate_readonly() is guaranteed side-effect-free (Fix 1.1 / 1.2).
    kernel_result = None
    if not materialize:
        try:
            from governance_runtime.kernel.phase_kernel import evaluate_readonly

            requested_phase, ctx = _build_runtime_context(
                commands_home=commands_home,
                config_root=config_root,
                pointer=pointer,
                state_doc=state,
            )
            kernel_result = evaluate_readonly(
                current_token=requested_phase,
                session_state_doc=state,
                runtime_ctx=ctx,
            )
        except Exception:
            # Graceful degradation -- fall back to persisted state.
            kernel_result = None

    # --- 4. Extract canonical fields for guided and debug surfaces ---
    # Canonical documents store runtime fields under "SESSION_STATE".
    # Support both nested and top-level conventions while preferring nested.
    state_view = _session_state_view(state)

    # Support both PascalCase and snake_case field conventions.
    phase = state_view.get("Phase") or state_view.get("phase") or state.get("Phase") or state.get("phase") or "unknown"
    next_phase = state_view.get("Next") or state_view.get("next") or state.get("Next") or state.get("next") or "unknown"
    mode = state_view.get("Mode") or state_view.get("mode") or state.get("Mode") or state.get("mode") or "unknown"
    status = state_view.get("status") or state.get("status") or "OK"
    output_mode = state_view.get("OutputMode") or state_view.get("output_mode") or state.get("OutputMode") or state.get("output_mode") or "unknown"
    active_gate = state_view.get("active_gate") or state.get("active_gate") or "none"
    next_gate_condition = state_view.get("next_gate_condition") or state.get("next_gate_condition") or "none"
    ticket_intake_ready = state_view.get("ticket_intake_ready", state.get("ticket_intake_ready", False))

    # Override kernel-authoritative fields with fresh readonly eval when
    # available.  This ensures the readout always reflects the kernel's
    # current evaluation rather than stale persisted values (Fix 1.2).
    if kernel_result is not None:
        phase = kernel_result.phase
        status = kernel_result.status
        active_gate = kernel_result.active_gate
        next_gate_condition = kernel_result.next_gate_condition
        if kernel_result.next_token:
            next_phase = kernel_result.next_token

    # Resolve phase_transition_evidence visibility (Fix 2.0 / Ergänzung C).
    # Prefer the kernel's evaluated signal; fall back to persisted state.
    if kernel_result is not None:
        transition_evidence_met = kernel_result.transition_evidence_met
    else:
        raw_evidence = state_view.get("phase_transition_evidence", state.get("phase_transition_evidence"))
        if isinstance(raw_evidence, bool):
            transition_evidence_met = raw_evidence
        elif isinstance(raw_evidence, str):
            transition_evidence_met = bool(raw_evidence.strip())
        elif isinstance(raw_evidence, list):
            transition_evidence_met = len(raw_evidence) > 0
        else:
            transition_evidence_met = False

    # Collect blocked gates from the Gates dict.
    gates = state_view.get("Gates") or state.get("Gates") or {}
    gates_blocked = [k for k, v in gates.items() if str(v).lower() == "blocked"] if isinstance(gates, dict) else []

    p54_evaluated_status = "unknown"
    p54_reason_code = "none"
    p54_invalid_rules = 0
    p54_dropped_candidates = 0
    p54_quality_reason_codes: list[str] = []
    p54_has_code_extraction = False
    p54_code_coverage_sufficient = False
    p54_code_candidate_count = 0
    p54_code_surface_count = 0
    p54_missing_code_surfaces: list[str] = []
    p55_evaluated_status = "unknown"
    p56_evaluated_status = "unknown"
    try:
        from governance_runtime.engine.gate_evaluator import (
            evaluate_p54_business_rules_gate,
            evaluate_p55_technical_debt_gate,
            evaluate_p56_rollback_safety_gate,
        )
        from governance_runtime.kernel.phase_kernel import _phase_1_5_executed

        _state_for_eval = state_view if isinstance(state_view, dict) else {}
        _phase15 = _phase_1_5_executed(_state_for_eval)
        p54_eval = evaluate_p54_business_rules_gate(
            session_state=_state_for_eval,
            phase_1_5_executed=_phase15,
        )
        p55_eval = evaluate_p55_technical_debt_gate(session_state=_state_for_eval)
        p56_eval = evaluate_p56_rollback_safety_gate(session_state=_state_for_eval)
        p54_evaluated_status = str(p54_eval.status)
        p54_reason_code = str(p54_eval.reason_code)
        p54_invalid_rules = int(getattr(p54_eval, "invalid_rule_count", 0) or 0)
        p54_dropped_candidates = int(getattr(p54_eval, "dropped_candidate_count", 0) or 0)
        _reason_codes = getattr(p54_eval, "quality_reason_codes", ())
        if isinstance(_reason_codes, tuple):
            p54_quality_reason_codes = [str(item) for item in _reason_codes if str(item).strip()]
        p54_has_code_extraction = bool(getattr(p54_eval, "has_code_extraction", False))
        p54_code_coverage_sufficient = bool(getattr(p54_eval, "code_extraction_sufficient", False))
        p54_code_candidate_count = int(getattr(p54_eval, "code_candidate_count", 0) or 0)
        p54_code_surface_count = int(getattr(p54_eval, "code_surface_count", 0) or 0)
        _missing_surfaces = getattr(p54_eval, "missing_code_surfaces", ())
        if isinstance(_missing_surfaces, tuple):
            p54_missing_code_surfaces = [str(item) for item in _missing_surfaces if str(item).strip()]
        p55_evaluated_status = str(p55_eval.status)
        p56_evaluated_status = str(p56_eval.status)
    except Exception:
        pass

    signal = resolve_plan_record_signal(
        state=state_view if isinstance(state_view, dict) else {},
        plan_record_file=session_path.parent / "plan-record.json",
    )

    # Prefer plan-record signal from kernel when available (already resolved
    # inside execute / evaluate_readonly with the same inputs).
    plan_status = kernel_result.plan_record_status if kernel_result is not None else signal.status
    plan_versions = kernel_result.plan_record_versions if kernel_result is not None else signal.versions

    # Diagnostic hint when evidence is missing and the kernel blocked on it
    # (Fix 2.0 / Ergänzung C).  This makes the invisible transition condition
    # visible so users understand why /continue self-loops.
    transition_evidence_hint = ""
    if not transition_evidence_met:
        _source = kernel_result.source if kernel_result is not None else ""
        _ngc = str(next_gate_condition).lower()
        if _source == "phase-transition-evidence-required" or "transition evidence" in _ngc:
            transition_evidence_hint = (
                "phase_transition_evidence is False — forward phase jump blocked. "
                "Run /continue to let the kernel auto-grant evidence when gate conditions are met."
            )

    # --- Fix 3.5 (B5): Draft vs persisted plan-record label ---
    # Distinguish "working draft" (chat-only, no persisted file) from
    # "persisted plan-record vN" to prevent users mistaking chat drafts
    # for official governance evidence.
    _plan_versions_int = _coerce_int(plan_versions)
    if _plan_versions_int >= 1 and str(plan_status).lower() not in ("absent", "error", "unknown", ""):
        plan_record_label = f"persisted plan-record v{_plan_versions_int}"
    else:
        plan_record_label = "working draft (not yet persisted)"

    from governance_runtime.domain.operating_profile import derive_mode_evidence

    effective_operating_mode, resolved_operating_mode, verify_policy_version = derive_mode_evidence(
        effective_operating_mode=_safe_str(
            state_view.get("effective_operating_mode")
            or state_view.get("operating_mode")
            or "unknown"
        ),
        resolved_operating_mode=_safe_str(
            state_view.get("resolved_operating_mode")
            or state_view.get("resolvedOperatingMode")
            or ""
        ),
        verify_policy_version=_safe_str(
            state_view.get("verify_policy_version")
            or state_view.get("verifyPolicyVersion")
            or "v1"
        ),
    )

    operating_mode_resolution = (
        state_view.get("operating_mode_resolution")
        or state_view.get("operatingModeResolution")
        or {}
    )
    if isinstance(operating_mode_resolution, dict) and not operating_mode_resolution:
        operating_mode_resolution = "none"

    snapshot: dict = {
        "schema": SNAPSHOT_SCHEMA,
        "status": _safe_str(status),
        "phase": _safe_str(phase),
        "next": _public_next_token(next_phase),
        "mode": _safe_str(mode),
        "output_mode": _safe_str(output_mode),
        "active_gate": _safe_str(active_gate),
        "next_gate_condition": _safe_str(next_gate_condition),
        "ticket_intake_ready": _safe_str(ticket_intake_ready),
        "phase_transition_evidence": transition_evidence_met,
        "gates_blocked": gates_blocked,
        "plan_record_status": plan_status,
        "plan_record_versions": plan_versions,
        "plan_record_label": plan_record_label,
        "effective_operating_mode": effective_operating_mode,
        "resolved_operating_mode": resolved_operating_mode,
        "verify_policy_version": verify_policy_version,
        "operating_mode_resolution": operating_mode_resolution,
        "commands_home": str(commands_home),
        "p54_evaluated_status": p54_evaluated_status,
        "p54_reason_code": p54_reason_code,
        "p54_invalid_rules": p54_invalid_rules,
        "p54_dropped_candidates": p54_dropped_candidates,
        "p54_quality_reason_codes": p54_quality_reason_codes,
        "p54_has_code_extraction": p54_has_code_extraction,
        "p54_code_coverage_sufficient": p54_code_coverage_sufficient,
        "p54_code_candidate_count": p54_code_candidate_count,
        "p54_code_surface_count": p54_code_surface_count,
        "p54_missing_code_surfaces": p54_missing_code_surfaces,
        "p55_evaluated_status": p55_evaluated_status,
        "p56_evaluated_status": p56_evaluated_status,
        "rework_clarification_input": _safe_str(
            state_view.get("rework_clarification_input")
            or state_view.get("ReworkClarificationInput")
            or ""
        ),
        "implementation_rework_clarification_input": _safe_str(
            state_view.get("implementation_rework_clarification_input")
            or state_view.get("ImplementationReworkClarificationInput")
            or ""
        ),
    }
    if transition_evidence_hint:
        snapshot["transition_evidence_hint"] = transition_evidence_hint

    phase_str = _safe_str(phase)
    if phase_str.startswith("6") and str(active_gate).strip().lower() == "evidence presentation gate":
        plan_body = _build_plan_body(session_path=session_path)
        snapshot["review_package_review_object"] = "Final Phase-6 implementation review decision"
        snapshot["review_package_ticket"] = _build_ticket_summary(state_view)
        snapshot["review_package_approved_plan_summary"] = _build_plan_summary(
            state_view=state_view,
            session_path=session_path,
        )
        snapshot["review_package_plan_body"] = plan_body
        snapshot["review_package_implementation_scope"] = "Implement the approved plan record in this repository."
        snapshot["review_package_constraints"] = "Governance guards remain active; implementation must follow the approved plan scope."
        snapshot["review_package_decision_semantics"] = (
            "approve=governance complete + implementation authorized; "
            "changes_requested=enter rework clarification gate; "
            "reject=return to phase 4 ticket input gate"
        )
        snapshot["effective_policy_loaded"] = bool(
            state_view.get("effective_policy_loaded") or state.get("effective_policy_loaded")
        )
        snapshot["effective_policy_error"] = str(
            state_view.get("effective_policy_error") or state.get("effective_policy_error") or ""
        )
        snapshot["review_package_presented"] = True
        snapshot["review_package_plan_body_present"] = plan_body != "none"

    # --- Fix 3.1 (B6): Phase 5 self-review diagnostics ---
    # Surface kernel-owned exit conditions so users can see WHY an exit
    # from the Architecture Review Gate is not yet possible.
    if phase_str.startswith("5"):
        p5_review = state_view.get("Phase5Review") or state.get("Phase5Review") or {}
        if isinstance(p5_review, dict):
            _iter = _coerce_int(
                p5_review.get("iteration")
                or p5_review.get("Iteration")
                or p5_review.get("rounds_completed")
                or p5_review.get("RoundsCompleted")
                or state_view.get("phase5_self_review_iterations")
                or state_view.get("self_review_iterations")
            )
            _max = _coerce_int(
                p5_review.get("max_iterations")
                or p5_review.get("MaxIterations")
                or state_view.get("phase5_max_review_iterations")
            )
            _prev = str(
                p5_review.get("prev_plan_digest")
                or p5_review.get("PrevPlanDigest")
                or ""
            ).strip()
            _curr = str(
                p5_review.get("curr_plan_digest")
                or p5_review.get("CurrPlanDigest")
                or ""
            ).strip()
            if _prev and _curr and _prev == _curr:
                _delta = "none"
            else:
                _delta = "changed"
        else:
            _iter, _max, _delta = 0, 3, "changed"

        _max = _max if _max >= 1 else 3
        _met = _iter >= _max or (_iter >= 1 and _delta == "none")

        snapshot["phase5_self_review_iterations"] = _iter
        snapshot["phase5_max_review_iterations"] = _max
        snapshot["phase5_revision_delta"] = _delta
        snapshot["self_review_iterations_met"] = _met

    # --- Fix 3.4 (B13): Phase 6 implementation-review diagnostics ---
    # Surface kernel-owned exit conditions for the Phase 6 internal
    # implementation review loop, mirroring the Phase 5 self-review block.
    # Without this, users cannot see iteration progress or exit criteria.
    if phase_str.startswith("6"):
        p6_review = state_view.get("ImplementationReview") or state.get("ImplementationReview") or {}
        if isinstance(p6_review, dict):
            _p6_iter = _coerce_int(
                p6_review.get("iteration")
                or p6_review.get("Iteration")
                or state_view.get("phase6_review_iterations")
                or state_view.get("phase6ReviewIterations")
            )
            _p6_max = _coerce_int(
                p6_review.get("max_iterations")
                or p6_review.get("MaxIterations")
                or state_view.get("phase6_max_review_iterations")
                or state_view.get("phase6MaxReviewIterations")
            )
            _p6_min = _coerce_int(
                p6_review.get("min_self_review_iterations")
                or p6_review.get("MinSelfReviewIterations")
                or state_view.get("phase6_min_self_review_iterations")
                or state_view.get("phase6MinSelfReviewIterations")
            )
            _p6_prev = str(
                p6_review.get("prev_impl_digest")
                or p6_review.get("PrevImplDigest")
                or ""
            ).strip()
            _p6_curr = str(
                p6_review.get("curr_impl_digest")
                or p6_review.get("CurrImplDigest")
                or ""
            ).strip()
            if _p6_prev and _p6_curr and _p6_prev == _p6_curr:
                _p6_delta = "none"
            else:
                _p6_delta = "changed"
        else:
            _p6_iter, _p6_max, _p6_min, _p6_delta = 0, 3, 1, "changed"

        _p6_max = _p6_max if _p6_max >= 1 else 3
        _p6_min = max(1, min(_p6_min, _p6_max)) if _p6_min >= 1 else 1
        _p6_complete = (
            _p6_iter >= _p6_max
            or (_p6_iter >= _p6_min and _p6_delta == "none")
        )

        snapshot["phase6_review_iterations"] = _p6_iter
        snapshot["phase6_max_review_iterations"] = _p6_max
        snapshot["phase6_min_review_iterations"] = _p6_min
        snapshot["phase6_revision_delta"] = _p6_delta
        snapshot["implementation_review_complete"] = _p6_complete

    if phase_str.startswith("6") and str(active_gate).strip().lower() == "evidence presentation gate":
        snapshot["review_package_evidence_summary"] = (
            f"plan_record_versions={_coerce_int(plan_versions)}, "
            f"implementation_review_complete={str(snapshot.get('implementation_review_complete', False)).lower()}"
        )
        snapshot["review_package_loop_status"] = (
            f"iterations={_coerce_int(snapshot.get('phase6_review_iterations'))}/"
            f"{_coerce_int(snapshot.get('phase6_max_review_iterations') or 3)}, "
            f"revision_delta={_safe_str(snapshot.get('phase6_revision_delta') or 'changed')}"
        )

    if phase_str.startswith("6") and str(active_gate).strip().lower() == "implementation internal review":
        snapshot["phase6_review_loop_status"] = (
            f"Review loop in progress: iteration={_coerce_int(snapshot.get('phase6_review_iterations'))}/"
            f"{_coerce_int(snapshot.get('phase6_max_review_iterations') or 3)}, "
            f"min_required={_coerce_int(snapshot.get('phase6_min_review_iterations') or 1)}, "
            f"revision_delta={_safe_str(snapshot.get('phase6_revision_delta') or 'changed')}"
        )
        snapshot["phase6_decision_availability"] = (
            "A final review decision is not yet available because the review package has not been fully presented."
        )

    if phase_str.startswith("6") and str(active_gate).strip().lower() == "implementation presentation gate":
        snapshot["implementation_package_review_object"] = _safe_str(
            state_view.get("implementation_package_review_object") or "Implemented result review"
        )
        snapshot["implementation_package_plan_reference"] = _safe_str(
            state_view.get("implementation_package_plan_reference") or "latest approved plan record"
        )
        snapshot["implementation_package_changed_files"] = state_view.get("implementation_package_changed_files") or state_view.get("implementation_changed_files") or []
        snapshot["implementation_package_findings_fixed"] = state_view.get("implementation_package_findings_fixed") or state_view.get("implementation_findings_fixed") or []
        snapshot["implementation_package_findings_open"] = state_view.get("implementation_package_findings_open") or state_view.get("implementation_open_findings") or []
        snapshot["implementation_package_checks"] = state_view.get("implementation_package_checks") or []
        snapshot["implementation_package_stability"] = _safe_str(
            state_view.get("implementation_package_stability")
            or ("stable" if bool(state_view.get("implementation_quality_stable")) else "unstable")
        )

    if phase_str.startswith("6") and str(active_gate).strip().lower() == "implementation review complete":
        snapshot["implementation_substate_history"] = state_view.get("implementation_substate_history") or []
        snapshot["implementation_review_summary"] = _safe_str(
            state_view.get("implementation_execution_summary")
            or "Internal implementation review loop completed."
        )
        snapshot["implementation_decision_availability"] = (
            "External implementation decision is not yet available until the Implementation Presentation Gate is materialized."
        )

    if phase_str.startswith("6"):
        validation_report = state_view.get("implementation_validation_report")
        if isinstance(validation_report, dict):
            snapshot["implementation_validation_report"] = validation_report
            snapshot["implementation_reason_codes"] = validation_report.get("reason_codes") or []
            snapshot["implementation_executor_invoked"] = bool(validation_report.get("executor_invoked"))
            changed = validation_report.get("changed_files")
            domain_changed = validation_report.get("domain_changed_files")
            snapshot["implementation_changed_files"] = changed if isinstance(changed, list) else []
            snapshot["implementation_domain_changed_files"] = (
                domain_changed if isinstance(domain_changed, list) else []
            )

    return snapshot


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    commands_home: Path | None = None
    audit_mode = False
    debug_mode = False
    diagnose_mode = False
    materialize_mode = False
    tail_count = 25
    args = argv if argv is not None else sys.argv[1:]

    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--commands-home":
            if idx + 1 >= len(args):
                print("status: ERROR", file=sys.stdout)
                print("error: --commands-home requires a path argument", file=sys.stdout)
                return 1
            commands_home = Path(args[idx + 1])
            idx += 2
            continue
        if arg == "--audit":
            audit_mode = True
            idx += 1
            continue
        if arg == "--debug":
            debug_mode = True
            idx += 1
            continue
        if arg == "--diagnose":
            diagnose_mode = True
            idx += 1
            continue
        if arg == "--materialize":
            materialize_mode = True
            idx += 1
            continue
        if arg == "--tail-count":
            if idx + 1 >= len(args):
                print("status: ERROR", file=sys.stdout)
                print("error: --tail-count requires an integer argument", file=sys.stdout)
                return 1
            try:
                tail_count = int(args[idx + 1])
            except ValueError:
                print("status: ERROR", file=sys.stdout)
                print("error: --tail-count must be an integer", file=sys.stdout)
                return 1
            idx += 2
            continue
        idx += 1

    if audit_mode:
        home = commands_home if commands_home is not None else _derive_commands_home()
        _ensure_commands_home_on_syspath(home)
        try:
            from governance_runtime.application.use_cases.audit_readout_builder import build_audit_readout

            payload = build_audit_readout(commands_home=home, tail_count=tail_count)
        except Exception as exc:
            print("status: ERROR", file=sys.stdout)
            print(f"error: {exc}", file=sys.stdout)
            return 1
        sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")
        return 0

    snapshot = read_session_snapshot(commands_home=commands_home, materialize=materialize_mode)
    if not audit_mode and not debug_mode and not diagnose_mode:
        rendered = format_guided_snapshot(snapshot)
    else:
        rendered = format_snapshot(snapshot)
        if materialize_mode:
            action_line = _resolve_next_action_line(snapshot)
            if action_line:
                rendered = rendered + action_line + "\n"
    sys.stdout.write(rendered)
    return 0 if snapshot.get("status") != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
