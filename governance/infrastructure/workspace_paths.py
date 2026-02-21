"""SSOT path utilities for workspace-scoped artifacts.

All phase artifacts are written deterministically under:
${WORKSPACES_HOME}/<repo_fingerprint>/

This module provides canonical path functions for all persisted artifacts.
"""

from __future__ import annotations

from pathlib import Path


def workspace_root(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint


def session_state_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "SESSION_STATE.json"


def repo_cache_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "repo-cache.yaml"


def repo_map_digest_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "repo-map-digest.md"


def workspace_memory_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "workspace-memory.yaml"


def decision_pack_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "decision-pack.md"


def business_rules_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "business-rules.md"


def repo_identity_map_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "repo-identity-map.yaml"


def global_pointer_path(opencode_home: Path) -> Path:
    return opencode_home / "SESSION_STATE.json"


def evidence_dir(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "evidence"


def locks_dir(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "locks"


PHASE2_ARTIFACTS = ["repo-cache.yaml", "repo-map-digest.md", "workspace-memory.yaml"]
PHASE21_ARTIFACTS = ["decision-pack.md"]
PHASE15_ARTIFACTS = ["business-rules.md"]


def all_phase_artifact_paths(workspaces_home: Path, repo_fingerprint: str) -> dict[str, Path]:
    return {
        "session_state": session_state_path(workspaces_home, repo_fingerprint),
        "repo_cache": repo_cache_path(workspaces_home, repo_fingerprint),
        "repo_map_digest": repo_map_digest_path(workspaces_home, repo_fingerprint),
        "workspace_memory": workspace_memory_path(workspaces_home, repo_fingerprint),
        "decision_pack": decision_pack_path(workspaces_home, repo_fingerprint),
        "business_rules": business_rules_path(workspaces_home, repo_fingerprint),
    }


def phase2_artifact_paths(workspaces_home: Path, repo_fingerprint: str) -> dict[str, Path]:
    return {
        "repo_cache": repo_cache_path(workspaces_home, repo_fingerprint),
        "repo_map_digest": repo_map_digest_path(workspaces_home, repo_fingerprint),
        "workspace_memory": workspace_memory_path(workspaces_home, repo_fingerprint),
    }
