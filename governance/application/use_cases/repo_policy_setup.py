from __future__ import annotations

import json
from pathlib import Path

from governance.application.repo_identity_service import derive_repo_identity


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
