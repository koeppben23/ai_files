from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


def _validate_repo_fingerprint(value: str) -> str:
    """Validate repo fingerprint is canonical 24-hex format."""
    token = value.strip()
    if not token:
        raise ValueError("repo fingerprint must not be empty")
    if not re.fullmatch(r"[0-9a-f]{24}", token):
        raise ValueError(
            "repo fingerprint must be a 24-character hex string (canonical hash-based format). "
            "Legacy slug-style fingerprints are not accepted."
        )
    return token


def _validate_canonical_fingerprint(value: str) -> str:
    return _validate_repo_fingerprint(value)


def _is_canonical_fingerprint(value: str) -> bool:
    token = value.strip()
    return bool(re.fullmatch(r"[0-9a-f]{24}", token))


def repo_session_state_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "SESSION_STATE.json"


def session_pointer_path(config_root: Path) -> Path:
    return config_root / "SESSION_STATE.json"


def repo_identity_map_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "repo-identity-map.yaml"


def session_state_template(repo_fingerprint: str, repo_name: str | None) -> dict:
    repository = repo_name.strip() if isinstance(repo_name, str) and repo_name.strip() else repo_fingerprint
    return {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fingerprint,
            "PersistenceCommitted": False,
            "WorkspaceReadyGateCommitted": False,
            "phase_transition_evidence": False,
            "session_state_version": 1,
            "ruleset_hash": None,
            "Phase": "1.1-Bootstrap",
            "Mode": "BLOCKED",
            "ConfidenceLevel": 0,
            "Next": "BLOCKED-START-REQUIRED",
            "OutputMode": "ARCHITECT",
            "DecisionSurface": {},
            "Kernel": {
                "PhaseApiPath": "${COMMANDS_HOME}/phase_api.yaml",
                "PhaseApiSha256": "",
                "LastPhaseEventId": "",
            },
            "Bootstrap": {
                "Present": False,
                "Satisfied": False,
                "Evidence": "not-initialized",
            },
            "Scope": {
                "Repository": repository,
                "RepositoryType": "",
                "ExternalAPIs": [],
                "BusinessRules": "pending",
            },
            "LoadedRulebooks": {
                "core": "",
                "profile": "",
                "templates": "",
                "addons": {},
            },
            "ticket_intake_ready": False,
            "AddonsEvidence": {},
            "RulebookLoadEvidence": {
                "top_tier": {
                    "quality_index": "${COMMANDS_HOME}/QUALITY_INDEX.md",
                    "conflict_resolution": "${COMMANDS_HOME}/CONFLICT_RESOLUTION.md",
                },
                "core": "deferred",
                "profile": "deferred",
                "templates": "deferred",
                "addons": {},
            },
            "ActiveProfile": None,
            "ProfileSource": None,
            "ProfileEvidence": None,
            "Gates": {
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pending",
                "P5.4-BusinessRules": "pending",
                "P5.5-TechnicalDebt": "pending",
                "P5.6-RollbackSafety": "pending",
                "P6-ImplementationQA": "pending",
            },
            "CreatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    }


def pointer_payload(repo_fingerprint: str, session_state_file: Path | None = None) -> dict:
    try:
        from governance.infrastructure.session_pointer import build_pointer_payload

        return build_pointer_payload(
            repo_fingerprint=repo_fingerprint,
            session_state_file=session_state_file,
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    except ImportError:
        pass

    payload = {
        "schema": "opencode-session-pointer.v1",
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "activeRepoFingerprint": repo_fingerprint,
    }
    if session_state_file is not None:
        payload["activeSessionStateFile"] = str(session_state_file)
    else:
        payload["activeSessionStateRelativePath"] = f"workspaces/{repo_fingerprint}/SESSION_STATE.json"
    return payload
