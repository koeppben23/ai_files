from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast
import uuid

from diagnostics.global_error_handler import emit_error_event
from governance.application.dto.phase_next_action_contract import contains_ticket_prompt
from governance.domain.phase_state_machine import phase_rank
from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance.infrastructure.path_contract import canonical_config_root

from .phase_api_spec import PhaseApiSpec, PhaseApiSpecError, PhaseSpecEntry, load_phase_api


@dataclass(frozen=True)
class RuntimeContext:
    requested_active_gate: str
    requested_next_gate_condition: str
    repo_is_git_root: bool
    live_repo_fingerprint: str | None = None
    commands_home: Path | None = None
    config_root: Path | None = None
    workspaces_home: Path | None = None


@dataclass(frozen=True)
class KernelResult:
    phase: str
    next_token: str | None
    active_gate: str
    next_gate_condition: str
    workspace_ready: bool
    source: str
    status: str
    spec_hash: str
    spec_path: str
    log_paths: dict[str, str]
    event_id: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_state(document: Mapping[str, object] | None) -> Mapping[str, object]:
    if document is None:
        return {}
    payload = document.get("SESSION_STATE")
    if isinstance(payload, Mapping):
        return payload
    return document


def _extract_fingerprint(state: Mapping[str, object]) -> str:
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_phase(state: Mapping[str, object]) -> str:
    for key in ("Phase", "phase"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _state_text(state: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _transition_has_evidence(state: Mapping[str, object]) -> bool:
    value = state.get("phase_transition_evidence")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return False


def _read_bool(state: Mapping[str, object], *keys: str) -> bool | None:
    for key in keys:
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return None


def _persistence_gate_passed(state: Mapping[str, object]) -> tuple[bool, str]:
    commit_flags = state.get("CommitFlags")
    state_view = cast(Mapping[str, object], commit_flags) if isinstance(commit_flags, Mapping) else state
    persistence_committed = _read_bool(state_view, "PersistenceCommitted", "persistence_committed", "persistenceCommitted")
    if persistence_committed is not True:
        return False, "PersistenceCommitted not true"
    workspace_ready = _read_bool(state_view, "WorkspaceReadyGateCommitted", "workspace_ready_gate_committed")
    if workspace_ready is not True:
        return False, "WorkspaceReadyGateCommitted not true"
    artifacts_committed = _read_bool(state_view, "WorkspaceArtifactsCommitted", "workspace_artifacts_committed")
    if artifacts_committed is not True:
        return False, "WorkspaceArtifactsCommitted not true"
    pointer_verified = _read_bool(state_view, "PointerVerified", "pointer_verified")
    if pointer_verified is not True:
        return False, "PointerVerified not true"
    return True, "ok"


def _rulebook_gate_passed(state: Mapping[str, object]) -> tuple[bool, str]:
    loaded_rulebooks = state.get("LoadedRulebooks")
    if not isinstance(loaded_rulebooks, Mapping):
        return False, "LoadedRulebooks not set"
    core = loaded_rulebooks.get("core")
    if not isinstance(core, str) or not core.strip():
        return False, "core rulebook not loaded"
    active_profile = state.get("ActiveProfile")
    if isinstance(active_profile, str) and active_profile.strip():
        profile = loaded_rulebooks.get("profile")
        if not isinstance(profile, str) or not profile.strip():
            return False, f"profile rulebook '{active_profile}' not loaded"
    return True, "ok"


def _openapi_signal(state: Mapping[str, object]) -> bool:
    addons = state.get("AddonsEvidence")
    if isinstance(addons, Mapping):
        openapi = addons.get("openapi")
        if isinstance(openapi, Mapping) and openapi.get("detected") is True:
            return True
        if openapi is True:
            return True
    repo_caps = state.get("repo_capabilities")
    if isinstance(repo_caps, list):
        normalized = {str(item).strip().lower() for item in repo_caps}
        return "openapi" in normalized
    return False


def _external_api_artifacts(state: Mapping[str, object]) -> bool:
    scope = state.get("Scope")
    if isinstance(scope, Mapping):
        external_apis = scope.get("ExternalAPIs")
        if isinstance(external_apis, list) and len(external_apis) > 0:
            return True
    artifacts = state.get("external_api_artifacts")
    if isinstance(artifacts, list) and len(artifacts) > 0:
        return True
    return artifacts is True


def api_in_scope(state: Mapping[str, object]) -> bool:
    return _openapi_signal(state) or _external_api_artifacts(state)


def _business_rules_scope(state: Mapping[str, object]) -> str:
    scope = state.get("Scope")
    if isinstance(scope, Mapping):
        value = scope.get("BusinessRules")
        if isinstance(value, str):
            return value.strip().lower()
    return ""


def _business_rules_discovery_resolved(state: Mapping[str, object]) -> bool:
    business_rules = state.get("BusinessRules")
    if isinstance(business_rules, Mapping):
        decision = business_rules.get("Decision")
        if isinstance(decision, str) and decision.strip().lower() in {"execute", "skip"}:
            return True
        inventory_status = business_rules.get("InventoryFileStatus")
        if isinstance(inventory_status, str) and inventory_status.strip().lower() in {"written", "unchanged", "normalized"}:
            return True
    br_scope = _business_rules_scope(state)
    if br_scope in {"not-applicable", "extracted", "skipped"}:
        return True
    gates = state.get("Gates")
    if isinstance(gates, Mapping):
        p54 = gates.get("P5.4-BusinessRules")
        if isinstance(p54, str) and p54.strip().lower() == "not-applicable":
            return True
    return False


def _normalize_token(value: str, spec: PhaseApiSpec) -> str:
    probe = str(value or "").strip().upper()
    if not probe:
        return ""
    if probe in spec.entries:
        return probe
    for token in sorted(spec.entries.keys(), key=len, reverse=True):
        if probe.startswith(token):
            return token
    return ""


def _sanitize_ticket_progression(*, phase: str, next_gate_condition: str) -> str:
    phase_token = phase.split("-", 1)[0].strip().upper()
    if not phase_token:
        return next_gate_condition
    if phase_rank(phase_token) < phase_rank("4") and contains_ticket_prompt(next_gate_condition):
        return "Proceed with current phase evidence collection; ticket input is not allowed before phase 4"
    return next_gate_condition


def _resolve_paths(runtime_ctx: RuntimeContext) -> tuple[Path, Path | None, Path]:
    config_root = runtime_ctx.config_root or canonical_config_root()
    commands_home = runtime_ctx.commands_home or config_root / "commands"
    workspaces_home = runtime_ctx.workspaces_home or config_root / "workspaces"
    return commands_home, workspaces_home, config_root


def _resolve_flow_paths(commands_home: Path, workspaces_home: Path | None, config_root: Path, repo_fingerprint: str) -> dict[str, Path]:
    paths: dict[str, Path] = {
        "flow": commands_home / "logs" / "flow.log.jsonl",
        "flow_fallback": config_root / "logs" / "flow.log.jsonl",
    }
    if workspaces_home is not None and repo_fingerprint:
        paths["workspace_events"] = workspaces_home / repo_fingerprint / "events.jsonl"
    return paths


def _append_event(path: Path, event: dict[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl_event(path, event, append=True)
        return True
    except Exception:
        return False


def _read_nested_key(state: Mapping[str, object], path: str) -> object | None:
    current: object = state
    for key in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _validate_exit(entry: PhaseSpecEntry, state: Mapping[str, object]) -> tuple[bool, str]:
    if entry.token == "2.1" and not _business_rules_discovery_resolved(state):
        return False, "BusinessRules.Decision unresolved"
    for key_path in entry.exit_required_keys:
        value = _read_nested_key(state, key_path)
        if value is None:
            return False, f"missing exit evidence key: {key_path}"
        if isinstance(value, str) and not value.strip():
            return False, f"empty exit evidence key: {key_path}"
    return True, "ok"


def _select_transition(entry: PhaseSpecEntry, state: Mapping[str, object]) -> tuple[str | None, str, str | None, str | None]:
    if entry.transitions:
        for transition in entry.transitions:
            when = transition.when.strip().lower()
            if when == "business_rules_execute" and not _business_rules_discovery_resolved(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "no_apis" and not api_in_scope(state):
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
            if when == "default":
                return (
                    transition.next_token,
                    transition.source,
                    transition.active_gate,
                    transition.next_gate_condition,
                )
        return (entry.next_token, "spec-next", None, None)
    return (entry.next_token, "spec-next", None, None)


def execute(
    *,
    current_token: str,
    session_state_doc: Mapping[str, object] | None,
    runtime_ctx: RuntimeContext,
) -> KernelResult:
    state = _session_state(session_state_doc)
    commands_home, workspaces_home, config_root = _resolve_paths(runtime_ctx)
    repo_fingerprint = runtime_ctx.live_repo_fingerprint or _extract_fingerprint(state)
    event_id = uuid.uuid4().hex

    try:
        spec = load_phase_api(runtime_ctx.commands_home)
    except PhaseApiSpecError as exc:
        emit_error_event(
            severity="CRITICAL",
            code="PHASE_API_MISSING",
            message=str(exc),
            repo_fingerprint=repo_fingerprint or None,
            config_root=config_root,
            workspaces_home=workspaces_home,
            commands_home=commands_home,
            context={"phase_api_path": str(commands_home / "phase_api.yaml")},
        )
        return KernelResult(
            phase="1.1-Bootstrap",
            next_token="1.1",
            active_gate="Workspace Ready Gate",
            next_gate_condition="BLOCKED_PHASE_API_MISSING: phase_api.yaml is required in commands home.",
            workspace_ready=False,
            source="phase-api-missing",
            status="BLOCKED",
            spec_hash="",
            spec_path=str(commands_home / "phase_api.yaml"),
            log_paths={},
            event_id=event_id,
        )

    persisted_phase = _extract_phase(state)
    persisted_token = _normalize_token(persisted_phase, spec)
    requested_token = _normalize_token(current_token, spec)
    chosen_token = persisted_token or requested_token or spec.start_token

    if persisted_token and requested_token and phase_rank(requested_token) >= phase_rank(persisted_token):
        chosen_token = requested_token

    workspace_ready, workspace_reason = _persistence_gate_passed(state)
    if phase_rank(chosen_token or "") >= phase_rank("2") and not workspace_ready:
        return KernelResult(
            phase="1.1-Bootstrap",
            next_token="1.1",
            active_gate="Workspace Ready Gate",
            next_gate_condition=f"BLOCKED_PERSISTENCE_FAILED: {workspace_reason}. Commit workspace readiness before phase progression.",
            workspace_ready=False,
            source="workspace-ready-gate",
            status="BLOCKED",
            spec_hash=spec.stable_hash,
            spec_path=str(spec.path),
            log_paths={},
            event_id=event_id,
        )

    if persisted_token == "1.2" and workspace_ready:
        chosen_token = "1.2"

    if (
        persisted_token
        and requested_token
        and phase_rank(requested_token) < phase_rank(persisted_token)
        and not (persisted_token == "1.2" and workspace_ready)
    ):
        entry = spec.entries[persisted_token]
        persisted_gate = _state_text(state, "active_gate", "ActiveGate") or entry.active_gate or runtime_ctx.requested_active_gate
        persisted_condition = _state_text(state, "next_gate_condition", "NextGateCondition")
        if not persisted_condition:
            persisted_condition = runtime_ctx.requested_next_gate_condition or entry.next_gate_condition
        persisted_condition = _sanitize_ticket_progression(
            phase=entry.phase,
            next_gate_condition=persisted_condition,
        )
        return KernelResult(
            phase=entry.phase,
            next_token=persisted_token,
            active_gate=persisted_gate,
            next_gate_condition=persisted_condition,
            workspace_ready=workspace_ready,
            source="monotonic-session-phase",
            status="OK",
            spec_hash=spec.stable_hash,
            spec_path=str(spec.path),
            log_paths={},
            event_id=event_id,
        )

    if persisted_token and requested_token:
        if phase_rank(requested_token) - phase_rank(persisted_token) > 1 and not _transition_has_evidence(state):
            chosen_token = persisted_token
            entry = spec.entries[chosen_token]
            persisted_phase_text = persisted_phase or entry.phase
            return KernelResult(
                phase=persisted_phase_text,
                next_token=chosen_token,
                active_gate=entry.active_gate or runtime_ctx.requested_active_gate,
                next_gate_condition="Phase transition evidence required before advancing beyond next immediate phase",
                workspace_ready=workspace_ready,
                source="phase-transition-evidence-required",
                status="BLOCKED",
                spec_hash=spec.stable_hash,
                spec_path=str(spec.path),
                log_paths={},
                event_id=event_id,
            )

    if phase_rank(chosen_token) >= phase_rank("2"):
        rulebooks_ok, rulebook_reason = _rulebook_gate_passed(state)
        if not rulebooks_ok:
            entry = spec.entries.get("1.3")
            phase_text = entry.phase if entry else "1.3-RulebookLoad"
            gate_text = entry.active_gate if entry else "Rulebook Load Gate"
            return KernelResult(
                phase=phase_text,
                next_token="1.3",
                active_gate=gate_text,
                next_gate_condition=f"BLOCKED_RULEBOOK_MISSING: {rulebook_reason}. Load required rulebooks before advancing.",
                workspace_ready=workspace_ready,
                source="rulebook-load-gate",
                status="BLOCKED",
                spec_hash=spec.stable_hash,
                spec_path=str(spec.path),
                log_paths={},
                event_id=event_id,
            )

    entry = spec.entries[chosen_token]
    exit_ok, exit_reason = _validate_exit(entry, state)
    if not exit_ok and chosen_token == "1.3":
        return KernelResult(
            phase=entry.phase,
            next_token=chosen_token,
            active_gate=entry.active_gate,
            next_gate_condition=f"PHASE_BLOCKED: {exit_reason}",
            workspace_ready=workspace_ready,
            source="phase-exit-evidence-missing",
            status="BLOCKED",
            spec_hash=spec.stable_hash,
            spec_path=str(spec.path),
            log_paths={},
            event_id=event_id,
        )

    next_token, source, override_active_gate, override_next_condition = _select_transition(entry, state)
    resolved_phase = entry.phase
    resolved_active_gate = override_active_gate or entry.active_gate or runtime_ctx.requested_active_gate
    resolved_next_condition = override_next_condition or entry.next_gate_condition or runtime_ctx.requested_next_gate_condition

    if entry.route_strategy == "stay" and runtime_ctx.requested_next_gate_condition.strip():
        resolved_next_condition = runtime_ctx.requested_next_gate_condition.strip()

    if entry.route_strategy == "next" and next_token and next_token in spec.entries:
        next_entry = spec.entries[next_token]
        resolved_phase = next_entry.phase
        if override_active_gate is None:
            resolved_active_gate = next_entry.active_gate or resolved_active_gate

    resolved_next_condition = _sanitize_ticket_progression(
        phase=resolved_phase,
        next_gate_condition=resolved_next_condition,
    )

    event = {
        "schema": "opencode.phase-flow.v1",
        "ts_utc": _utc_now(),
        "event_id": event_id,
        "event": "PHASE_COMPLETED",
        "source": source,
        "phase": resolved_phase,
        "phase_token": chosen_token,
        "next_token": next_token,
        "status": "OK",
        "spec_hash": spec.stable_hash,
        "spec_path": str(spec.path),
    }

    log_paths = _resolve_flow_paths(commands_home, workspaces_home, config_root, repo_fingerprint)
    written_flow = _append_event(log_paths["flow"], event)
    if not written_flow:
        written_flow = _append_event(log_paths["flow_fallback"], event)
    workspace_written = False
    workspace_path = log_paths.get("workspace_events")
    if workspace_path is not None:
        workspace_written = _append_event(workspace_path, event)

    if not written_flow:
        emit_error_event(
            severity="CRITICAL",
            code="PHASE_FLOW_LOG_WRITE_FAILED",
            message="unable to write phase flow log",
            repo_fingerprint=repo_fingerprint or None,
            config_root=config_root,
            workspaces_home=workspaces_home,
            commands_home=commands_home,
            context={"phase": resolved_phase},
        )
        return KernelResult(
            phase=resolved_phase,
            next_token=next_token,
            active_gate=resolved_active_gate,
            next_gate_condition="PHASE_BLOCKED: flow log write failed",
            workspace_ready=workspace_ready,
            source="flow-log-write-failed",
            status="BLOCKED",
            spec_hash=spec.stable_hash,
            spec_path=str(spec.path),
            log_paths={"flow": str(log_paths["flow"]), "workspace_events": str(workspace_path) if workspace_path else ""},
            event_id=event_id,
        )

    result_paths = {
        "phase_flow": str(log_paths["flow"] if written_flow else log_paths["flow_fallback"]),
        "workspace_events": str(workspace_path) if workspace_written and workspace_path is not None else "",
    }
    return KernelResult(
        phase=resolved_phase,
        next_token=next_token,
        active_gate=resolved_active_gate,
        next_gate_condition=resolved_next_condition,
        workspace_ready=workspace_ready,
        source=source,
        status="OK",
        spec_hash=spec.stable_hash,
        spec_path=str(spec.path),
        log_paths=result_paths,
        event_id=event_id,
    )


__all__ = ["KernelResult", "RuntimeContext", "api_in_scope", "execute"]
