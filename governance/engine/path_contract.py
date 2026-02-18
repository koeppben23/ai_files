"""Backward-compatible import surface for path contract.

Canonical implementation lives in `governance.infrastructure.path_contract`.
"""

from governance.infrastructure.path_contract import (  # noqa: F401
    BindingEvidenceLocation,
    NotAbsoluteError,
    PathContractError,
    WindowsDriveRelativeError,
    binding_evidence_location,
    canonical_commands_home,
    canonical_config_root,
    deterministic_home,
    normalize_absolute_path,
    normalize_for_fingerprint,
)
