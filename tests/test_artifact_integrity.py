"""Cluster 3 — Runtime artifact integrity verification tests.

Verifies:
  - SHA256 verification passes with intact governance release artifacts
  - Verification fails with tampered manifest.json, lock.json, or hashes.json
  - Verification fails with missing files
  - Engine refuses to activate on verification failure (fail-closed)
  - Existing lifecycle behavior is unchanged when ruleset_dir is None
  - All existing governance releases pass integrity verification
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from governance.infrastructure.artifact_integrity import (
    VerificationResult,
    verify_all_releases,
    verify_ruleset_integrity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_RELEASES = REPO_ROOT / "rulesets" / "governance"


def _sha256(path: Path) -> str:
    # Normalize CRLF -> LF to match artifact_integrity verifier behavior.
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _create_release(tmp_path: Path, *, tamper: str | None = None) -> Path:
    """Create a minimal governance release directory with correct hashes.

    Args:
        tmp_path: Temporary directory.
        tamper: If set, tamper with this component after hashes are written.
                One of "manifest", "lock", "hashes", "missing_hashes",
                "missing_manifest", "missing_lock".
    """
    release_dir = tmp_path / "0.1.0"
    release_dir.mkdir()

    manifest = {"schema_version": "1.0.0", "ruleset_id": "test"}
    lock = {"entries": [{"path": "test.yml", "sha256": "abc123"}]}

    manifest_path = release_dir / "manifest.json"
    lock_path = release_dir / "lock.json"
    hashes_path = release_dir / "hashes.json"

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    hashes = {
        "manifest.json": _sha256(manifest_path),
        "lock.json": _sha256(lock_path),
    }
    hashes_path.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")

    if tamper == "manifest":
        manifest_path.write_text('{"tampered": true}\n', encoding="utf-8")
    elif tamper == "lock":
        lock_path.write_text('{"tampered": true}\n', encoding="utf-8")
    elif tamper == "hashes":
        hashes["manifest.json"] = "0" * 64
        hashes_path.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    elif tamper == "missing_hashes":
        hashes_path.unlink()
    elif tamper == "missing_manifest":
        manifest_path.unlink()
    elif tamper == "missing_lock":
        lock_path.unlink()
    elif tamper == "corrupt_hashes":
        hashes_path.write_text("not json at all", encoding="utf-8")
    elif tamper == "hashes_not_object":
        hashes_path.write_text("[1, 2, 3]\n", encoding="utf-8")

    return release_dir


# ── Core verification tests ────────────────────────────────────────────


def test_verification_passes_with_intact_artifacts(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path)
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is True
    assert result.mismatches == ()
    assert result.error is None


def test_verification_fails_with_tampered_manifest(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="manifest")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert len(result.mismatches) == 1
    assert result.mismatches[0].file == "manifest.json"


def test_verification_fails_with_tampered_lock(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="lock")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert len(result.mismatches) == 1
    assert result.mismatches[0].file == "lock.json"


def test_verification_fails_with_wrong_hash_in_hashes_json(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="hashes")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert any(m.file == "manifest.json" for m in result.mismatches)


def test_verification_fails_with_missing_hashes_json(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="missing_hashes")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert result.error == "hashes.json not found"


def test_verification_fails_with_missing_manifest(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="missing_manifest")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert any(m.actual == "FILE_MISSING" for m in result.mismatches)


def test_verification_fails_with_missing_lock(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="missing_lock")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert any(m.file == "lock.json" and m.actual == "FILE_MISSING" for m in result.mismatches)


def test_verification_fails_with_corrupt_hashes_json(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="corrupt_hashes")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert "unreadable" in (result.error or "")


def test_verification_fails_with_non_object_hashes_json(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="hashes_not_object")
    result = verify_ruleset_integrity(release_dir)
    assert result.passed is False
    assert "must be a JSON object" in (result.error or "")


# ── Lifecycle integration tests ─────────────────────────────────────────

from governance.engine.lifecycle import stage_engine_activation


def test_engine_refuses_activation_on_integrity_failure(tmp_path: Path) -> None:
    """Fail-closed: engine must not activate with tampered artifacts."""
    release_dir = _create_release(tmp_path, tamper="manifest")
    paths_file = tmp_path / "governance.paths.json"

    with pytest.raises(RuntimeError, match="BLOCKED-INTEGRITY-FAILED"):
        stage_engine_activation(
            paths_file=paths_file,
            engine_version="0.1.0",
            engine_sha256="abc",
            ruleset_hash="def",
            ruleset_dir=release_dir,
        )

    # paths_file should NOT have been created (activation was blocked)
    assert not paths_file.exists()


def test_engine_activates_with_intact_artifacts(tmp_path: Path) -> None:
    """Activation succeeds when integrity verification passes."""
    release_dir = _create_release(tmp_path)
    paths_file = tmp_path / "governance.paths.json"

    payload = stage_engine_activation(
        paths_file=paths_file,
        engine_version="0.1.0",
        engine_sha256="abc",
        ruleset_hash="def",
        ruleset_dir=release_dir,
    )

    assert paths_file.exists()
    assert payload["engineLifecycle"]["active"]["version"] == "0.1.0"


def test_engine_activates_without_ruleset_dir_backward_compat(tmp_path: Path) -> None:
    """Backward compat: when ruleset_dir is None, no integrity check is performed."""
    paths_file = tmp_path / "governance.paths.json"

    payload = stage_engine_activation(
        paths_file=paths_file,
        engine_version="0.1.0",
        engine_sha256="abc",
        ruleset_hash="def",
        # ruleset_dir not provided — no integrity check
    )

    assert paths_file.exists()
    assert payload["engineLifecycle"]["active"]["version"] == "0.1.0"


# ── Real governance releases verification ───────────────────────────────


@pytest.mark.parametrize(
    "release_version",
    [d.name for d in sorted(GOVERNANCE_RELEASES.iterdir()) if d.is_dir() and (d / "hashes.json").exists()],
)
def test_real_governance_release_integrity(release_version: str) -> None:
    """Every committed governance release must pass integrity verification."""
    release_dir = GOVERNANCE_RELEASES / release_version
    result = verify_ruleset_integrity(release_dir)
    assert result.passed, f"Governance release {release_version} failed integrity: {result.summary}"


# ── verify_all_releases helper ──────────────────────────────────────────


def test_verify_all_releases_returns_results_per_directory(tmp_path: Path) -> None:
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir()
    _create_release(gov_dir)  # creates 0.1.0 subdir
    results = verify_all_releases(gov_dir)
    assert len(results) == 1
    assert results[0].passed is True


def test_verify_all_releases_handles_missing_directory(tmp_path: Path) -> None:
    results = verify_all_releases(tmp_path / "nonexistent")
    assert results == []


# ── Summary display ─────────────────────────────────────────────────────


def test_verification_result_summary_on_success(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path)
    result = verify_ruleset_integrity(release_dir)
    assert "integrity OK" in result.summary


def test_verification_result_summary_on_failure(tmp_path: Path) -> None:
    release_dir = _create_release(tmp_path, tamper="manifest")
    result = verify_ruleset_integrity(release_dir)
    assert "integrity FAILED" in result.summary
    assert "manifest.json" in result.summary
