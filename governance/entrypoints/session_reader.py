#!/usr/bin/env python3
"""Governance session reader -- self-bootstrapping entrypoint.

Reads SESSION_STATE.json via the global pointer and outputs a minimal
YAML-like snapshot to stdout for LLM consumption.

Self-bootstrapping: this script resolves its own location to derive
commands_home, then reads governance.paths.json for validation. No
external PYTHONPATH setup is required.

Output format: minimal key-value pairs (YAML-compatible), one per line.
On error: prints ``status: ERROR`` with a human-readable ``error:`` line.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Schema / version constants
# ---------------------------------------------------------------------------
SNAPSHOT_SCHEMA = "governance-session-snapshot.v1"
POINTER_SCHEMA = "opencode-session-pointer.v1"


def _derive_commands_home() -> Path:
    """Derive commands_home from this script's own location.

    Layout: commands/governance/entrypoints/session_reader.py
    So commands_home = parents[2] relative to __file__.
    """
    return Path(__file__).resolve().parents[2]


def _ensure_commands_home_on_syspath(commands_home: Path) -> None:
    root = str(commands_home)
    if root and root not in sys.path:
        sys.path.insert(0, root)


def _read_json(path: Path) -> dict:
    """Read and parse a JSON file. Raises on any failure."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def _write_json_atomic(path: Path, payload: dict) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _safe_str(value: object) -> str:
    """Coerce a value to a YAML-safe scalar string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_list(items: list) -> str:
    """Format a list as a YAML inline sequence."""
    if not items:
        return "[]"
    return "[" + ", ".join(_safe_str(i) for i in items) + "]"


def _coerce_int(value: object) -> int:
    """Coerce a value to a non-negative int, defaulting to 0."""
    if value is None:
        return 0
    try:
        result = int(value)  # type: ignore[arg-type]
        return max(0, result)
    except (TypeError, ValueError):
        return 0


def _quote_if_needed(value: str) -> str:
    """Wrap value in double quotes if it contains YAML-special characters."""
    if any(c in value for c in (":", "#", "'", '"', "{", "}", "[", "]", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _resolve_session_document(commands_home: Path) -> tuple[Path, dict, Path, dict]:
    config_root = commands_home.parent
    pointer_path = config_root / "SESSION_STATE.json"
    if not pointer_path.exists():
        raise RuntimeError(f"No session pointer at {pointer_path}")

    try:
        pointer = _read_json(pointer_path)
    except Exception as exc:
        raise RuntimeError(f"Invalid session pointer JSON: {exc}") from exc
    if pointer.get("schema") not in (POINTER_SCHEMA, "active-session-pointer.v1"):
        raise RuntimeError(f"Unknown pointer schema: {pointer.get('schema')}")

    session_file_raw = pointer.get("activeSessionStateFile")
    if not session_file_raw:
        rel = pointer.get("activeSessionStateRelativePath")
        if rel:
            session_file_raw = str(config_root / rel)
    if not session_file_raw:
        raise RuntimeError("Pointer contains no session state file path")

    session_path = Path(session_file_raw)
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


def _build_runtime_context(
    *, commands_home: Path, config_root: Path, pointer: dict, state_doc: dict,
) -> tuple[str, Any]:
    """Build a RuntimeContext and resolved phase token from session state.

    Returns (requested_phase, RuntimeContext).  Shared by both the
    materialise (write) and readonly-eval (read) code paths.
    """
    from governance.domain.phase_state_machine import normalize_phase_token
    from governance.kernel.phase_kernel import RuntimeContext

    state_view = _session_state_view(state_doc)
    requested_phase = normalize_phase_token(
        state_view.get("Phase")
        or state_view.get("phase")
        or state_doc.get("Phase")
        or state_doc.get("phase")
        or "4"
    ) or "4"

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
    from governance.application.use_cases.session_state_helpers import with_kernel_result
    from governance.kernel.phase_kernel import execute

    requested_phase, ctx = _build_runtime_context(
        commands_home=commands_home,
        config_root=config_root,
        pointer=pointer,
        state_doc=state_doc,
    )

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

    # Auto-grant phase_transition_evidence when the kernel successfully
    # evaluates a forward transition (Fix 2.0 / Ergänzung C).
    # This prevents /continue self-loops where evidence stays False
    # because only bootstrap_preflight used to set it.
    if result.status == "OK" and result.route_strategy == "next":
        ss = materialized.get("SESSION_STATE")
        if isinstance(ss, dict):
            ss["phase_transition_evidence"] = True

    _write_json_atomic(session_path, materialized)
    return materialized


def _should_emit_continue_next_action(snapshot: dict) -> bool:
    """Determine whether to append 'Next action: run /continue.' to output.

    The rule is symmetric across all phases (Fix 1.3):
    1. Never emit when status is error/blocked.
    2. Never emit when the kernel signals a user-input gate (ticket intake,
       plan draft, rulebook load, etc.) — those require /ticket or manual action.
    3. Always emit when the condition explicitly contains '/continue'.
    4. Otherwise emit for any OK-status snapshot where the condition does
       not match a known user-input or blocking pattern.
    """
    status = str(snapshot.get("status", "")).strip().lower()
    if status in {"", "error", "blocked"}:
        return False

    next_condition = str(snapshot.get("next_gate_condition", "")).strip().lower()

    # Explicit /continue mention is an unconditional yes.
    if "/continue" in next_condition or "resume via /continue" in next_condition:
        return True

    # Conditions that require user-provided input or are explicitly blocked.
    if any(
        token in next_condition
        for token in (
            "provide ticket/task",
            "collect ticket",
            "create and persist",
            "produce a plan draft",
            "load required rulebooks",
            "phase_blocked",
            "blocked",
            "wait for",
            "run bootstrap",
        )
    ):
        return False

    # For any other non-error, non-blocked state the user should /continue
    # to re-enter the kernel and advance.  This covers Phase 5 review loops,
    # Phase 6 implementation loops, and all intermediate stay-strategy phases
    # symmetrically without hardcoding specific phase/gate combinations.
    return True


# -- Blocking patterns that indicate the user should work in chat, not run /continue.
_GATE_WORK_PATTERNS: tuple[str, ...] = (
    "phase-transition-evidence-required",
    "phase-5-self-review-required",
    "implementation-review-pending",
)


def _resolve_next_action_line(snapshot: dict) -> str:
    """Return the appropriate next-action guidance line (Fix 3.2 / B7).

    Two possible outputs:
    1. ``"Next action: run /continue."``
       — when kernel materialization would advance the phase or trigger an
         internal kernel operation (e.g. plan generation, gate propagation).
    2. ``"Next action: continue in chat with the active gate work."``
       — when the user should do work in the conversation (gate work,
         self-review iterations) rather than blindly re-running /continue.
    3. ``""`` (empty string) — when no next-action hint is appropriate
       (error, blocked, or user-input gates).

    The distinction prevents /continue self-loops (B7) where the system
    recommends /continue but nothing changes because the user hasn't done
    the required gate work yet.
    """
    if not _should_emit_continue_next_action(snapshot):
        return ""

    # If the snapshot carries a kernel source (from Fix 2.0's transition
    # evidence hint or from the readonly eval), check whether the source
    # indicates the user must do gate work rather than re-materialize.
    _hint = str(snapshot.get("transition_evidence_hint", "")).strip()
    if _hint:
        # Evidence is blocking — user must do gate work, not /continue.
        return "Next action: continue in chat with the active gate work."

    # Check the self_review_iterations_met flag from Fix 3.1 (B6).
    # If iterations are NOT met and phase is 5, the user should do
    # review work in chat, not re-run /continue which would self-loop.
    phase_str = str(snapshot.get("phase", "")).strip()
    if phase_str.startswith("5"):
        review_met = snapshot.get("self_review_iterations_met", True)
        if review_met is False:
            return "Next action: continue in chat with the active gate work."

    # Check the implementation_review_complete flag from Fix 3.4 (B13).
    # If review is NOT complete and phase is 6, the user should do
    # implementation review work in chat, not re-run /continue which
    # would self-loop.
    if phase_str.startswith("6"):
        review_complete = snapshot.get("implementation_review_complete", True)
        if review_complete is False:
            return "Next action: continue in chat with the active gate work."

    return "Next action: run /continue."


def read_session_snapshot(commands_home: Path | None = None, *, materialize: bool = False) -> dict:
    """Read the current governance session state and return a snapshot dict.

    Parameters
    ----------
    commands_home:
        Override for commands_home (useful for testing). If *None*, derived
        from the script's own filesystem location.

    Returns
    -------
    dict
        Snapshot dict with at minimum ``schema`` and ``status`` keys.
    """
    if commands_home is None:
        commands_home = _derive_commands_home()
    _ensure_commands_home_on_syspath(commands_home)
    from governance.infrastructure.plan_record_state import resolve_plan_record_signal

    try:
        config_root, pointer, session_path, state = _resolve_session_document(commands_home)
    except Exception as exc:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": str(exc),
        }

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
            from governance.kernel.phase_kernel import evaluate_readonly

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

    # --- 4. Extract minimal fields ---
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

    snapshot: dict = {
        "schema": SNAPSHOT_SCHEMA,
        "status": _safe_str(status),
        "phase": _safe_str(phase),
        "next": _safe_str(next_phase),
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
        "commands_home": str(commands_home),
    }
    if transition_evidence_hint:
        snapshot["transition_evidence_hint"] = transition_evidence_hint

    # --- Fix 3.1 (B6): Phase 5 self-review diagnostics ---
    # Surface kernel-owned exit conditions so users can see WHY an exit
    # from the Architecture Review Gate is not yet possible.
    phase_str = _safe_str(phase)
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

    # --- Fix 3.3 (B8): Route target explanation for intermediate next tokens ---
    # When the kernel evaluates a route_strategy="next" with a next_token,
    # the user needs to understand that the target is an intermediate routing
    # step, not a stable phase the system will remain in.
    if kernel_result is not None and kernel_result.route_strategy == "next" and kernel_result.next_token:
        snapshot["route_target"] = kernel_result.next_token
        snapshot["route_strategy"] = "next"
        snapshot["route_explanation"] = (
            f"Kernel routes to {kernel_result.next_token}; "
            "this is an intermediate target, not a stable state."
        )

    return snapshot


def format_snapshot(snapshot: dict) -> str:
    """Format a snapshot dict as YAML-compatible key-value output."""
    lines = [f"# {SNAPSHOT_SCHEMA}"]
    for key, value in snapshot.items():
        if key == "schema":
            continue
        if isinstance(value, list):
            lines.append(f"{key}: {_format_list(value)}")
        else:
            lines.append(f"{key}: {_quote_if_needed(_safe_str(value))}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    commands_home: Path | None = None
    audit_mode = False
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
            from governance.application.use_cases.audit_readout_builder import build_audit_readout

            payload = build_audit_readout(commands_home=home, tail_count=tail_count)
        except Exception as exc:
            print("status: ERROR", file=sys.stdout)
            print(f"error: {exc}", file=sys.stdout)
            return 1
        sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")
        return 0

    snapshot = read_session_snapshot(commands_home=commands_home, materialize=materialize_mode)
    rendered = format_snapshot(snapshot)
    if materialize_mode:
        action_line = _resolve_next_action_line(snapshot)
        if action_line:
            rendered = rendered + action_line + "\n"
    sys.stdout.write(rendered)
    return 0 if snapshot.get("status") != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
