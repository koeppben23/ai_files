"""Run Summary Writer - Creates deterministic run summaries for audit/explain."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def compute_run_id(session_state: Mapping[str, Any], timestamp: str) -> str:
    """Compute deterministic run ID from session state + timestamp."""
    payload = json.dumps({
        "phase": session_state.get("Phase", "unknown"),
        "mode": session_state.get("Mode", "unknown"),
        "timestamp": timestamp,
        "ruleset_hash": session_state.get("ruleset_hash", ""),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_reason_remediation(reason_code: str) -> dict[str, Any]:
    """Load remediation guidance for a reason code."""
    script_dir = Path(__file__).resolve().parents[2]
    remediation_file = script_dir / "diagnostics" / "REASON_REMEDIATION_MAP.json"
    
    if not remediation_file.exists():
        return {
            "summary": reason_code,
            "how_to_fix": "Check SESSION_STATE.Diagnostics.ReasonPayloads for details.",
            "copy_paste_command": None,
            "docs_link": None,
        }
    
    try:
        with open(remediation_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        mappings = data.get("mappings", {})
        if reason_code in mappings:
            return mappings[reason_code]
        return data.get("default_unmapped", {
            "summary": reason_code,
            "how_to_fix": "Unknown reason code",
            "copy_paste_command": None,
            "docs_link": None,
        })
    except (json.JSONDecodeError, OSError):
        return {
            "summary": reason_code,
            "how_to_fix": "Check SESSION_STATE.Diagnostics.ReasonPayloads for details.",
            "copy_paste_command": None,
            "docs_link": None,
        }


def _extract_precedence_events(session_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract precedence events from session state."""
    events = []
    
    if "ActivationHash" in session_state:
        events.append({
            "event": "ACTIVATION_HASH_COMPUTED",
            "source": "kernel",
            "details": {"activation_hash": session_state["ActivationHash"]},
        })
    
    if "ruleset_hash" in session_state:
        events.append({
            "event": "RULESET_HASH_COMPUTED",
            "source": "kernel",
            "details": {"ruleset_hash": session_state["ruleset_hash"]},
        })
    
    diagnostics = session_state.get("Diagnostics", {})
    reason_payloads = diagnostics.get("ReasonPayloads", [])
    for payload in reason_payloads:
        if isinstance(payload, dict) and "precedence" in payload.get("reason_code", "").lower():
            events.append({
                "event": "POLICY_PRECEDENCE_APPLIED",
                "source": payload.get("source", "unknown"),
                "details": payload,
            })
    
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
    
    binding_file = os.environ.get("OPENCODE_BINDING_FILE", "")
    if binding_file and Path(binding_file).exists():
        pointers["binding_file"] = binding_file
    
    return pointers


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
    
    mode = session_state.get("Mode", "user").lower()
    if mode not in {"user", "pipeline", "architect", "implement"}:
        mode = "user"
    
    phase = str(session_state.get("Phase", "0"))
    
    reason: dict[str, Any] = {"code": reason_code or "OK"}
    if reason_code and reason_code != "OK":
        remediation = _load_reason_remediation(reason_code)
        reason["message"] = remediation.get("summary", reason_code)
        reason["how_to_fix"] = remediation.get("how_to_fix")
        if reason_payload:
            reason["payload"] = reason_payload
    
    precedence_events = _extract_precedence_events(session_state)
    prompt_budget = _extract_prompt_budget(session_state)
    
    if workspaces_home is None:
        config_root = os.environ.get("OPENCODE_CONFIG_ROOT", "")
        if config_root:
            workspaces_home = Path(config_root) / "workspaces"
        else:
            workspaces_home = Path.home() / ".config" / "opencode" / "workspaces"
    
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
    
    runs_dir = workspaces_home / repo_fingerprint / "evidence" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    run_file = runs_dir / f"{summary['run_id']}.json"
    
    with open(run_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    
    latest_link = runs_dir / "latest.json"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(run_file.name)
    
    return run_file
