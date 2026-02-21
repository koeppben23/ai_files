"""Run Summary Writer - Creates deterministic run summaries for audit/explain."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


def compute_run_id(session_state: Mapping[str, Any], timestamp: str) -> str:
    """Compute deterministic run ID from session state + timestamp."""
    payload = json.dumps(
        {
            "phase": session_state.get("Phase", "unknown"),
            "mode": session_state.get("Mode", "unknown"),
            "timestamp": timestamp,
            "ruleset_hash": session_state.get("ruleset_hash", ""),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _default_reason_remediation(reason_code: str) -> dict[str, Any]:
    return {
        "summary": reason_code,
        "how_to_fix": "Check SESSION_STATE.Diagnostics.ReasonPayloads for details.",
        "copy_paste_command": None,
        "docs_link": None,
    }


def _resolve_diagnostics_root(mode: str) -> Path | None:
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode=mode)
    if evidence.binding_ok and evidence.commands_home:
        diagnostics_root = evidence.commands_home.parent / "diagnostics"
        if diagnostics_root.exists():
            return diagnostics_root
    return None


def _load_reason_remediation(reason_code: str, mode: str = "user") -> dict[str, Any]:
    """Load remediation guidance from canonical blocked reason catalog."""
    if yaml is None:
        return _default_reason_remediation(reason_code)

    diagnostics_root = _resolve_diagnostics_root(mode)
    if diagnostics_root is None:
        return _default_reason_remediation(reason_code)

    catalog_path = diagnostics_root / "blocked_reason_catalog.yaml"
    if not catalog_path.exists():
        return _default_reason_remediation(reason_code)

    try:
        payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return _default_reason_remediation(reason_code)

    blocked = payload.get("blocked_reasons") if isinstance(payload, dict) else None
    if not isinstance(blocked, dict):
        return _default_reason_remediation(reason_code)

    entry = blocked.get(reason_code)
    if not isinstance(entry, dict):
        return _default_reason_remediation(reason_code)

    quick_fix_commands = entry.get("quick_fix_commands")
    command = None
    if isinstance(quick_fix_commands, list) and quick_fix_commands:
        first = quick_fix_commands[0]
        if isinstance(first, str) and first.strip():
            command = first

    recovery_steps = entry.get("recovery_steps")
    how_to_fix = "Check SESSION_STATE.Diagnostics.ReasonPayloads for details."
    if isinstance(recovery_steps, list) and recovery_steps:
        first_step = recovery_steps[0]
        if isinstance(first_step, str) and first_step.strip():
            how_to_fix = first_step

    return {
        "summary": entry.get("message_template", reason_code),
        "how_to_fix": how_to_fix,
        "copy_paste_command": command,
        "docs_link": None,
    }


def _extract_precedence_events(session_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract precedence events from session state."""
    events = []

    if "ActivationHash" in session_state:
        events.append(
            {
                "event": "ACTIVATION_HASH_COMPUTED",
                "source": "kernel",
                "details": {"activation_hash": session_state["ActivationHash"]},
            }
        )

    if "ruleset_hash" in session_state:
        events.append(
            {
                "event": "RULESET_HASH_COMPUTED",
                "source": "kernel",
                "details": {"ruleset_hash": session_state["ruleset_hash"]},
            }
        )

    diagnostics = session_state.get("Diagnostics", {})
    reason_payloads = diagnostics.get("ReasonPayloads", [])
    for payload in reason_payloads:
        if isinstance(payload, dict) and "precedence" in payload.get("reason_code", "").lower():
            events.append(
                {
                    "event": "POLICY_PRECEDENCE_APPLIED",
                    "source": payload.get("source", "unknown"),
                    "details": payload,
                }
            )

    return events


def _extract_prompt_budget(session_state: Mapping[str, Any]) -> dict[str, int]:
    """Extract prompt budget from session state."""
    budget = session_state.get("PromptBudget", {})
    return {
        "used": budget.get("used", 0),
        "allowed": budget.get("allowed", 100),
        "repo_docs_used": budget.get("repo_docs_used", 0),
        "repo_docs_allowed": budget.get("repo_docs_allowed", 10),
    }


def _extract_evidence_pointers(session_state: Mapping[str, Any], workspaces_home: Path) -> dict[str, str]:
    """Extract evidence pointer paths."""
    pointers = {}

    repo_cache = session_state.get("RepoCacheFile", {})
    if isinstance(repo_cache, dict) and "SourcePath" in repo_cache:
        pointers["repo_cache"] = repo_cache["SourcePath"]

    if workspaces_home.exists():
        repo_fp = session_state.get("repo_fingerprint", "unknown")
        session_file = workspaces_home / repo_fp / "SESSION_STATE.json"
        if session_file.exists():
            pointers["session_state"] = str(session_file)

    return pointers


def _resolve_workspaces_home(mode: str) -> Path:
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode=mode)
    if evidence.binding_ok:
        return evidence.workspaces_home
    if str(mode).strip().lower() == "pipeline":
        return Path("/")
    return Path.home() / ".config" / "opencode" / "workspaces"


def create_run_summary(
    session_state: Mapping[str, Any],
    result: str,
    reason_code: str | None = None,
    reason_payload: dict[str, Any] | None = None,
    workspaces_home: Path | None = None,
    model_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a run summary from session state.

    Args:
        session_state: Current session state
        result: Final result status (OK, BLOCKED, WARN, NOT_VERIFIED)
        reason_code: Canonical reason code if blocked
        reason_payload: Structured payload for reason
        workspaces_home: Path to workspaces directory
        model_identity: Model identity dict with provider, model_id, context_limit, temperature

    Returns:
        Run summary dict conforming to RUN_SUMMARY_SCHEMA.json
    """

    timestamp = datetime.now(timezone.utc).isoformat()
    run_id = compute_run_id(session_state, timestamp)

    mode = str(session_state.get("Mode", "user")).lower()
    if mode not in {"user", "pipeline", "architect", "implement"}:
        mode = "unknown"

    phase = str(session_state.get("Phase", "0"))

    reason: dict[str, Any] = {"code": reason_code or "OK"}
    if reason_code and reason_code != "OK":
        remediation = _load_reason_remediation(reason_code, mode=mode)
        reason["message"] = remediation.get("summary", reason_code)
        reason["how_to_fix"] = remediation.get("how_to_fix")
        if reason_payload:
            reason["payload"] = reason_payload

    precedence_events = _extract_precedence_events(session_state)
    prompt_budget = _extract_prompt_budget(session_state)

    if workspaces_home is None:
        workspaces_home = _resolve_workspaces_home(mode)

    evidence_pointers = _extract_evidence_pointers(session_state, workspaces_home)

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp": timestamp,
        "mode": mode,
        "phase": phase,
        "result": result,
        "reason": reason,
        "precedence_events": precedence_events,
        "prompt_budget": prompt_budget,
        "evidence_pointers": evidence_pointers,
    }

    if "repo_fingerprint" in session_state:
        summary["git_context"] = {
            "repo_fingerprint": session_state["repo_fingerprint"],
        }

    # Model identity is CRITICAL for reproducibility
    if model_identity:
        model_ctx: dict[str, Any] = {
            "provider": model_identity.get("provider", "unknown"),
            "model_id": model_identity.get("model_id", "unknown"),
            "context_limit": model_identity.get("context_limit", 0),
            "temperature": model_identity.get("temperature", 0.0),
        }
        if "version" in model_identity:
            model_ctx["version"] = model_identity["version"]
        if "quantization" in model_identity:
            model_ctx["quantization"] = model_identity["quantization"]
        if "deployment_id" in model_identity:
            model_ctx["deployment_id"] = model_identity["deployment_id"]

        # Compute identity hash for comparison
        identity_str = json.dumps(model_ctx, sort_keys=True, separators=(",", ":"))
        model_ctx["identity_hash"] = hashlib.sha256(identity_str.encode("utf-8")).hexdigest()[:16]

        summary["model_context"] = model_ctx

    # Rulebook hashes for reproducibility
    if "ruleset_hash" in session_state:
        summary["rulebook_hashes"] = {
            "ruleset": session_state["ruleset_hash"],
        }
    if "ActivationHash" in session_state:
        if "rulebook_hashes" not in summary:
            summary["rulebook_hashes"] = {}
        summary["rulebook_hashes"]["activation"] = session_state["ActivationHash"]

    return summary


def write_run_summary(
    summary: dict[str, Any],
    workspaces_home: Path,
    repo_fingerprint: str,
) -> Path:
    """Write run summary to disk."""

    if not workspaces_home.is_absolute():
        raise ValueError("workspaces_home must be absolute")

    runs_dir = workspaces_home / repo_fingerprint / "evidence" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_file = runs_dir / f"{summary['run_id']}.json"

    from governance.infrastructure.fs_atomic import atomic_write_json

    atomic_write_json(run_file, summary, ensure_ascii=True, indent=2)

    latest_link = runs_dir / "latest.json"
    if os.name != "nt":
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(run_file.name)
    else:
        atomic_write_json(latest_link, summary, ensure_ascii=True, indent=2)

    return run_file
