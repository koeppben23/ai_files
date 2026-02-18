from __future__ import annotations

from governance.domain.canonical_json import canonical_json_hash

def hash_payload(payload: dict[str, object]) -> str:
    return canonical_json_hash(payload)


def build_ruleset_hash(
    *,
    selected_pack_ids: list[str] | None,
    pack_engine_version: str | None,
    expected_pack_lock_hash: str,
) -> str:
    payload = {
        "selected_pack_ids": sorted(selected_pack_ids or []),
        "pack_engine_version": pack_engine_version or "",
        "expected_pack_lock_hash": expected_pack_lock_hash,
    }
    return hash_payload(payload)


def build_activation_hash(
    *,
    phase: str,
    active_gate: str,
    next_gate_condition: str,
    target_path: str,
    effective_operating_mode: str,
    capabilities_hash: str,
    repo_source: str,
    repo_is_git_root: bool,
    repo_identity: str,
    ruleset_hash: str,
) -> str:
    payload = {
        "phase": phase,
        "active_gate": active_gate,
        "next_gate_condition": next_gate_condition,
        "target_path": target_path,
        "effective_operating_mode": effective_operating_mode,
        "capabilities_hash": capabilities_hash,
        "repo_identity": repo_identity,
        "repo_source": repo_source,
        "repo_is_git_root": repo_is_git_root,
        "ruleset_hash": ruleset_hash,
    }
    return hash_payload(payload)
