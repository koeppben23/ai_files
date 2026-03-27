"""
Governance context materializer.

Materializes governance artifacts (mandates, policies) to files
and provides references with SHA256 digests for auditability.

Fail-closed: raises exception if materialization fails.

Security:
    - Output directory must be within allowed governance roots
    - All artifacts are validated for existence, readability, and digest integrity
    - No silent fallbacks - fail-closed on any error
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib

from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.workspace_paths import governance_allowed_artifact_dirs


GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED = "GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED"

def _is_within_allowed_root(path: Path, allowed_roots: tuple[Path, ...]) -> bool:
    """Check if path is within allowed governance roots."""
    try:
        resolved = path.resolve()
        for allowed in allowed_roots:
            try:
                resolved.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue

        return False
    except OSError:
        return False


class GovernanceContextMaterializationError(Exception):
    """Raised when governance context materialization fails."""

    def __init__(self, reason: str, reason_code: str = GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED):
        self.reason = reason
        self.reason_code = reason_code
        super().__init__(reason)


@dataclass(frozen=True)
class GovernanceContextMaterialization:
    """Immutable container for materialized governance artifacts."""

    plan_mandate_file: Path | None
    plan_mandate_sha256: str | None
    plan_mandate_label: str

    effective_policy_file: Path | None
    effective_policy_sha256: str | None
    effective_policy_label: str

    review_mandate_file: Path | None
    review_mandate_sha256: str | None
    review_mandate_label: str

    def has_materialized(self) -> bool:
        """Check if any artifacts were actually materialized."""
        return bool(
            self.plan_mandate_file
            or self.effective_policy_file
            or self.review_mandate_file
        )


def _sha256_digest(content: str) -> str:
    """Compute SHA256 hex digest of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _validate_output_dir(output_dir: Path, config_root: Path | None = None) -> None:
    """Validate output directory exists, is a directory, and is within allowed governance roots."""
    if config_root is None:
        config_root = Path.home() / ".governance"

    try:
        output_dir.resolve(strict=True)
    except FileNotFoundError:
        raise GovernanceContextMaterializationError(
            reason=f"Output directory does not exist: {output_dir}",
            reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
        )

    resolved = output_dir.resolve()
    if not resolved.is_dir():
        raise GovernanceContextMaterializationError(
            reason=f"Output path is not a directory: {output_dir}",
            reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
        )

    config_root = config_root.resolve()
    allowed_roots = governance_allowed_artifact_dirs(config_root)
    if not _is_within_allowed_root(output_dir, allowed_roots):
        raise GovernanceContextMaterializationError(
            reason=(
                "Output directory must be within allowed governance roots "
                f"(config_root={config_root}), got: {output_dir}"
            ),
            reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
        )


def _materialize_text_file(output_dir: Path, prefix: str, content: str) -> tuple[Path, str]:
    """
    Materialize text content to a file with SHA256-based name.

    Returns: (file_path, sha256_digest)
    """
    if not content or not content.strip():
        raise GovernanceContextMaterializationError(
            reason=f"Cannot materialize empty or whitespace-only content for {prefix}",
            reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
        )

    # Keep digest calculation aligned with fs_atomic.atomic_write_text(), which
    # canonicalizes CRLF to LF by default.
    normalized_content = content.replace("\r\n", "\n")
    digest = _sha256_digest(normalized_content)
    filename = f"{prefix}_{digest[:16]}.txt"
    file_path = output_dir / filename

    try:
        atomic_write_text(file_path, normalized_content)
    except OSError as e:
        raise GovernanceContextMaterializationError(
            reason=f"Failed to write {prefix} file: {e}",
            reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
        )

    written_digest = _sha256_digest(file_path.read_text())
    if written_digest != digest:
        raise GovernanceContextMaterializationError(
            reason=f"Digest mismatch after writing {prefix} file",
            reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
        )

    return file_path, digest


def materialize_governance_artifacts(
    output_dir: Path,
    config_root: Path | None = None,
    home: Path | None = None,
    plan_mandate: str | None = None,
    effective_policy: str | None = None,
    review_mandate: str | None = None,
) -> GovernanceContextMaterialization:
    """
    Materialize governance artifacts (mandates, policies) to files.

    Args:
        output_dir: Target directory for materialized files (required).
        plan_mandate: Plan mandate text to materialize.
        effective_policy: Effective policy text to materialize (used for both authoring and review).
        review_mandate: Review mandate text to materialize.

    Returns:
        GovernanceContextMaterialization with file paths and digests.

    Raises:
        GovernanceContextMaterializationError: If materialization fails (fail-closed).
    """
    if config_root is None and home is not None:
        config_root = home / ".governance"
    _validate_output_dir(output_dir, config_root)

    plan_file = plan_sha256 = None
    if plan_mandate:
        plan_file, plan_sha256 = _materialize_text_file(output_dir, "plan_mandate", plan_mandate)

    policy_file = policy_sha256 = None
    if effective_policy:
        policy_file, policy_sha256 = _materialize_text_file(output_dir, "effective_policy", effective_policy)

    review_file = review_sha256 = None
    if review_mandate:
        review_file, review_sha256 = _materialize_text_file(output_dir, "review_mandate", review_mandate)

    return GovernanceContextMaterialization(
        plan_mandate_file=plan_file,
        plan_mandate_sha256=plan_sha256,
        plan_mandate_label="Plan mandate",
        effective_policy_file=policy_file,
        effective_policy_sha256=policy_sha256,
        effective_policy_label="Effective policy",
        review_mandate_file=review_file,
        review_mandate_sha256=review_sha256,
        review_mandate_label="Review mandate",
    )


def validate_materialized_artifacts(materialization: GovernanceContextMaterialization) -> None:
    """
    Validate that all materialized artifacts exist, are readable, and match digests.

    Raises:
        GovernanceContextMaterializationError: If any validation fails (fail-closed).
    """
    artifacts = [
        (materialization.plan_mandate_file, materialization.plan_mandate_sha256, "plan_mandate"),
        (materialization.effective_policy_file, materialization.effective_policy_sha256, "effective_policy"),
        (materialization.review_mandate_file, materialization.review_mandate_sha256, "review_mandate"),
    ]

    for file_path, expected_digest, label in artifacts:
        if file_path is None or expected_digest is None:
            continue

        if not file_path.exists():
            raise GovernanceContextMaterializationError(
                reason=f"{label}: file not found: {file_path}",
                reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
            )

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as e:
            raise GovernanceContextMaterializationError(
                reason=f"{label}: cannot read file: {e}",
                reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
            )

        if not content.strip():
            raise GovernanceContextMaterializationError(
                reason=f"{label}: file is empty: {file_path}",
                reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
            )

        actual_digest = _sha256_digest(content)
        if actual_digest != expected_digest:
            raise GovernanceContextMaterializationError(
                reason=f"{label}: digest mismatch (expected {expected_digest[:16]}, got {actual_digest[:16]})",
                reason_code=GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
            )
