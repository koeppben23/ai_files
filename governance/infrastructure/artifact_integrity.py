"""Runtime integrity verification for governance release artifacts.

Verifies that manifest.json and lock.json in a governance release directory
have not been tampered with by comparing their SHA256 hashes against the
stored values in hashes.json.

Threat model (honest scope):
  ✓ Accidental file corruption
  ✓ Naive/unsophisticated tampering (attacker modifies lock.json but not hashes.json)
  ✓ Build pipeline inconsistencies
  ✗ Attacker who controls both lock.json AND hashes.json (not detectable)
  ✗ Supply-chain attacks at the build/release level (requires Cosign/Sigstore)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class IntegrityMismatch:
    """A single file whose actual hash does not match the stored hash."""

    file: str
    expected: str
    actual: str


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of artifact integrity verification."""

    passed: bool
    directory: str
    mismatches: tuple[IntegrityMismatch, ...] = ()
    error: str | None = None

    @property
    def summary(self) -> str:
        if self.passed:
            return f"integrity OK: {self.directory}"
        if self.error:
            return f"integrity FAILED: {self.directory} — {self.error}"
        details = "; ".join(f"{m.file}: expected {m.expected[:12]}… got {m.actual[:12]}…" for m in self.mismatches)
        return f"integrity FAILED: {self.directory} — {details}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Files that must be present and hash-verified in every governance release.
VERIFIED_FILES = ("manifest.json", "lock.json")


def verify_ruleset_integrity(ruleset_dir: Path) -> VerificationResult:
    """Verify SHA256 integrity of governance release artifacts.

    Args:
        ruleset_dir: Path to a governance release directory containing
                     manifest.json, lock.json, and hashes.json.

    Returns:
        VerificationResult with passed=True if all hashes match,
        or passed=False with details about mismatches or errors.
    """
    dir_label = str(ruleset_dir)

    hashes_path = ruleset_dir / "hashes.json"
    if not hashes_path.exists():
        return VerificationResult(
            passed=False,
            directory=dir_label,
            error="hashes.json not found",
        )

    try:
        stored = json.loads(hashes_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return VerificationResult(
            passed=False,
            directory=dir_label,
            error=f"hashes.json unreadable: {exc}",
        )

    if not isinstance(stored, dict):
        return VerificationResult(
            passed=False,
            directory=dir_label,
            error="hashes.json must be a JSON object",
        )

    mismatches: list[IntegrityMismatch] = []

    for filename in VERIFIED_FILES:
        file_path = ruleset_dir / filename
        if not file_path.exists():
            mismatches.append(
                IntegrityMismatch(file=filename, expected=stored.get(filename, "?"), actual="FILE_MISSING")
            )
            continue

        expected_hash = stored.get(filename)
        if not expected_hash or not isinstance(expected_hash, str):
            mismatches.append(
                IntegrityMismatch(file=filename, expected="NOT_IN_HASHES", actual=_sha256(file_path))
            )
            continue

        actual_hash = _sha256(file_path)
        if actual_hash != expected_hash:
            mismatches.append(
                IntegrityMismatch(file=filename, expected=expected_hash, actual=actual_hash)
            )

    if mismatches:
        return VerificationResult(
            passed=False,
            directory=dir_label,
            mismatches=tuple(mismatches),
        )

    return VerificationResult(passed=True, directory=dir_label)


def verify_all_releases(governance_releases_dir: Path) -> list[VerificationResult]:
    """Verify integrity of all governance releases under a directory.

    Args:
        governance_releases_dir: Path to rulesets/governance/ containing
                                 version-numbered subdirectories.

    Returns:
        List of VerificationResult, one per release directory.
    """
    results: list[VerificationResult] = []
    if not governance_releases_dir.is_dir():
        return results
    for release_dir in sorted(governance_releases_dir.iterdir()):
        if release_dir.is_dir() and (release_dir / "hashes.json").exists():
            results.append(verify_ruleset_integrity(release_dir))
    return results
