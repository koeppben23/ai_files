"""Legacy compatibility bridge for path contract utilities.

DEPRECATED: use governance_runtime.infrastructure.path_contract.
"""

from governance_runtime.infrastructure.path_contract import (  # noqa: F401
    BindingEvidenceLocation,
    NotAbsoluteError,
    PathContractError,
    PathTraversalError,
    WindowsDriveRelativeError,
    binding_evidence_location,
    canonical_config_root,
    deterministic_home,
    normalize_absolute_path,
)

__all__ = [
    "BindingEvidenceLocation",
    "NotAbsoluteError",
    "PathContractError",
    "PathTraversalError",
    "WindowsDriveRelativeError",
    "binding_evidence_location",
    "canonical_config_root",
    "deterministic_home",
    "normalize_absolute_path",
]
