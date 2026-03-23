from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.application.repo_identity_service import derive_repo_identity
from governance_runtime.domain.regulated_mode import get_minimum_retention_days


def write_governance_mode_config(
    *,
    repo_root: Path,
    profile: str,
    now_utc: str,
    compliance_framework: str = "DEFAULT",
) -> Path | None:
    """Write governance-mode.json for regulated profile activation.

    Creates governance-mode.json in repo_root when profile is 'regulated'.
    This file is read by detect_regulated_mode() to activate regulated constraints:
    - Retention lock (minimum_retention_days based on framework)
    - Four-eyes approval for archive operations
    - Immutable archives
    - Tamper-evident export

    For non-regulated profiles, returns None (no-op).

    Args:
        repo_root: Repository root path (workspace root for governance-mode.json)
        profile: Operating profile (solo, team, regulated)
        now_utc: ISO timestamp for activated_at
        compliance_framework: Compliance framework identifier (default: DEFAULT)

    Returns:
        Path to governance-mode.json if created, None for non-regulated profiles
    """
    profile_token = str(profile or "").strip().lower()
    if profile_token != "regulated":
        return None

    mode_path = repo_root / "governance-mode.json"

    existing_activated_at = ""
    if mode_path.exists() and mode_path.is_file():
        try:
            existing_payload = json.loads(mode_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - defensive parse guard
            pass
        else:
            if isinstance(existing_payload, dict):
                existing_activated_at = str(existing_payload.get("activated_at") or "").strip()

    activated_at = existing_activated_at or str(now_utc).strip()
    if not activated_at:
        raise ValueError("now_utc must be non-empty")

    framework = str(compliance_framework or "DEFAULT").strip()
    min_retention = get_minimum_retention_days(framework)

    payload = {
        "schema": "governance-mode.v1",
        "state": "active",
        "compliance_framework": framework,
        "minimum_retention_days": min_retention,
        "activated_at": activated_at,
        "activated_by": "bootstrap-cli",
    }

    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    with mode_path.open("w", encoding="utf-8") as handle:
        handle.write(text)
    return mode_path


def write_repo_operating_mode_policy(*, repo_root: Path, profile: str, now_utc: str) -> Path:
    profile_token = str(profile or "").strip().lower()
    if profile_token not in {"solo", "team", "regulated"}:
        raise ValueError("profile must be one of: solo, team, regulated")

    policy_path = repo_root / ".opencode" / "governance-repo-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)

    existing_created_at = ""
    if policy_path.exists() and policy_path.is_file():
        try:
            existing_payload = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parse guard
            raise ValueError(f"existing repo policy is invalid JSON: {exc}") from exc
        if isinstance(existing_payload, dict):
            existing_created_at = str(existing_payload.get("createdAt") or "").strip()

    identity = derive_repo_identity(repo_root, canonical_remote=None, git_dir=None)
    created_at = existing_created_at or str(now_utc).strip()
    if not created_at:
        raise ValueError("now_utc must be non-empty")

    payload = {
        "schema": "opencode-governance-repo-policy.v1",
        "repoFingerprint": str(identity.fingerprint or ""),
        "operatingMode": profile_token,
        "source": "bootstrap-cli-init",
        "createdAt": created_at,
    }
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    with policy_path.open("w", encoding="utf-8") as handle:
        handle.write(text)
    return policy_path
