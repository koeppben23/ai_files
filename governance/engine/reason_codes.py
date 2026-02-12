"""Canonical governance reason-code registry.

Wave A keeps behavior parity: values in this module must match currently emitted
runtime reason codes until a deliberate migration updates both emitters and tests.
"""

from __future__ import annotations

from typing import Final

# Sentinel used when a gate has no blocking/warning reason.
REASON_CODE_NONE: Final[str] = "none"

# Blocking reason codes.
BLOCKED_MISSING_BINDING_FILE: Final[str] = "BLOCKED-MISSING-BINDING-FILE"
BLOCKED_VARIABLE_RESOLUTION: Final[str] = "BLOCKED-VARIABLE-RESOLUTION"
BLOCKED_WORKSPACE_PERSISTENCE: Final[str] = "BLOCKED-WORKSPACE-PERSISTENCE"
BLOCKED_ENGINE_SELFCHECK: Final[str] = "BLOCKED-ENGINE-SELFCHECK"
BLOCKED_REPO_IDENTITY_RESOLUTION: Final[str] = "BLOCKED-REPO-IDENTITY-RESOLUTION"
BLOCKED_SYSTEM_MODE_REQUIRED: Final[str] = "BLOCKED-SYSTEM-MODE-REQUIRED"
BLOCKED_OPERATING_MODE_REQUIRED: Final[str] = "BLOCKED-OPERATING-MODE-REQUIRED"
BLOCKED_STATE_OUTDATED: Final[str] = "BLOCKED-STATE-OUTDATED"
BLOCKED_PACK_LOCK_REQUIRED: Final[str] = "BLOCKED-PACK-LOCK-REQUIRED"
BLOCKED_PACK_LOCK_INVALID: Final[str] = "BLOCKED-PACK-LOCK-INVALID"
BLOCKED_PACK_LOCK_MISMATCH: Final[str] = "BLOCKED-PACK-LOCK-MISMATCH"
BLOCKED_SURFACE_CONFLICT: Final[str] = "BLOCKED-SURFACE-CONFLICT"
BLOCKED_RULESET_HASH_MISMATCH: Final[str] = "BLOCKED-RULESET-HASH-MISMATCH"
BLOCKED_ACTIVATION_HASH_MISMATCH: Final[str] = "BLOCKED-ACTIVATION-HASH-MISMATCH"
BLOCKED_RELEASE_HYGIENE: Final[str] = "BLOCKED-RELEASE-HYGIENE"
BLOCKED_SESSION_STATE_LEGACY_UNSUPPORTED: Final[str] = "BLOCKED-SESSION-STATE-LEGACY-UNSUPPORTED"
BLOCKED_UNSPECIFIED: Final[str] = "BLOCKED-UNSPECIFIED"
BLOCKED_PERSISTENCE_TARGET_DEGENERATE: Final[str] = "BLOCKED-PERSISTENCE-TARGET-DEGENERATE"
BLOCKED_PERSISTENCE_PATH_VIOLATION: Final[str] = "BLOCKED-PERSISTENCE-PATH-VIOLATION"

# UX blocking reason codes (installer, lint).
BLOCKED_INSTALL_PRECHECK_MISSING_SOURCE: Final[str] = "BLOCKED-INSTALL-PRECHECK-MISSING-SOURCE"
BLOCKED_INSTALL_VERSION_MISSING: Final[str] = "BLOCKED-INSTALL-VERSION-MISSING"
BLOCKED_INSTALL_CONFIG_ROOT_INVALID: Final[str] = "BLOCKED-INSTALL-CONFIG-ROOT-INVALID"

# Warning reason codes.
WARN_UNMAPPED_AUDIT_REASON: Final[str] = "WARN-UNMAPPED-AUDIT-REASON"
WARN_WORKSPACE_PERSISTENCE: Final[str] = "WARN-WORKSPACE-PERSISTENCE"
WARN_ENGINE_LIVE_DENIED: Final[str] = "WARN-ENGINE-LIVE-DENIED"
WARN_MODE_DOWNGRADED: Final[str] = "WARN-MODE-DOWNGRADED"
WARN_PERMISSION_LIMITED: Final[str] = "WARN-PERMISSION-LIMITED"
WARN_SESSION_STATE_LEGACY_COMPAT_MODE: Final[str] = "WARN-SESSION-STATE-LEGACY-COMPAT-MODE"
NOT_VERIFIED_MISSING_EVIDENCE: Final[str] = "NOT_VERIFIED-MISSING-EVIDENCE"
NOT_VERIFIED_EVIDENCE_STALE: Final[str] = "NOT_VERIFIED-EVIDENCE-STALE"

BLOCKED_PERMISSION_DENIED: Final[str] = "BLOCKED-PERMISSION-DENIED"
BLOCKED_EXEC_DISALLOWED: Final[str] = "BLOCKED-EXEC-DISALLOWED"

# Default used by audit reason-code bridging when a key is not explicitly mapped.
DEFAULT_UNMAPPED_AUDIT_REASON: Final[str] = WARN_UNMAPPED_AUDIT_REASON

# Flat canonical set for validation and parity checks.
CANONICAL_REASON_CODES: Final[tuple[str, ...]] = (
    BLOCKED_MISSING_BINDING_FILE,
    BLOCKED_VARIABLE_RESOLUTION,
    BLOCKED_WORKSPACE_PERSISTENCE,
    BLOCKED_ENGINE_SELFCHECK,
    BLOCKED_REPO_IDENTITY_RESOLUTION,
    BLOCKED_SYSTEM_MODE_REQUIRED,
    BLOCKED_OPERATING_MODE_REQUIRED,
    BLOCKED_STATE_OUTDATED,
    BLOCKED_PACK_LOCK_REQUIRED,
    BLOCKED_PACK_LOCK_INVALID,
    BLOCKED_PACK_LOCK_MISMATCH,
    BLOCKED_SURFACE_CONFLICT,
    BLOCKED_RULESET_HASH_MISMATCH,
    BLOCKED_ACTIVATION_HASH_MISMATCH,
    BLOCKED_RELEASE_HYGIENE,
    BLOCKED_SESSION_STATE_LEGACY_UNSUPPORTED,
    BLOCKED_UNSPECIFIED,
    BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
    BLOCKED_PERSISTENCE_PATH_VIOLATION,
    BLOCKED_INSTALL_PRECHECK_MISSING_SOURCE,
    BLOCKED_INSTALL_VERSION_MISSING,
    BLOCKED_INSTALL_CONFIG_ROOT_INVALID,
)


def is_registered_reason_code(reason_code: str, *, allow_none: bool = True) -> bool:
    """Return True if the reason code is in the canonical registry.

    `none` is accepted by default because it is used as a deterministic
    non-blocking sentinel in boundary contracts.
    """

    normalized = reason_code.strip()
    if allow_none and normalized == REASON_CODE_NONE:
        return True
    return normalized in CANONICAL_REASON_CODES


# UX hints for operator-facing messages.
REASON_CODE_HINTS: Final[dict[str, str]] = {
    BLOCKED_INSTALL_PRECHECK_MISSING_SOURCE: (
        "Required governance source files are missing. "
        "If installing from source: clone the repository. "
        "If using a bundle: extract it first, then run install.py from the extracted directory. "
        "If already installed: run 'python3 install.py --status' to check installation health."
    ),
    BLOCKED_INSTALL_VERSION_MISSING: (
        "Governance version not found in master.md. "
        "Ensure master.md contains 'Governance-Version: <semver>' header."
    ),
    BLOCKED_INSTALL_CONFIG_ROOT_INVALID: (
        "Config root path is invalid or not writable. "
        "Check path permissions and try again."
    ),
}
