from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.infrastructure.governance_context_materializer import (
    GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED,
    GovernanceContextMaterialization,
    GovernanceContextMaterializationError,
    _materialize_text_file,
    _sha256_digest,
    materialize_governance_artifacts,
    validate_materialized_artifacts,
)


@pytest.fixture
def governance_root(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path
    out = home / ".governance" / "runtime_state"
    out.mkdir(parents=True)
    return out, home


def _materialize(governance_root: tuple[Path, Path], **kwargs) -> GovernanceContextMaterialization:
    out, home = governance_root
    return materialize_governance_artifacts(output_dir=out, home=home, **kwargs)


class TestSha256Digest:
    def test_sha256_digest_same_content(self):
        assert _sha256_digest("x") == _sha256_digest("x")

    def test_sha256_digest_different_content(self):
        assert _sha256_digest("x") != _sha256_digest("y")


class TestMaterializeGovernanceArtifacts:
    def test_materialize_plan_mandate_only(self, governance_root: tuple[Path, Path]):
        result = _materialize(governance_root, plan_mandate="Test plan mandate")
        assert result.plan_mandate_file is not None
        assert result.plan_mandate_file.read_text() == "Test plan mandate"
        assert result.effective_policy_file is None
        assert result.review_mandate_file is None

    def test_materialize_effective_policy_only(self, governance_root: tuple[Path, Path]):
        result = _materialize(governance_root, effective_policy="Test effective policy")
        assert result.effective_policy_file is not None
        assert result.effective_policy_file.read_text() == "Test effective policy"
        assert result.plan_mandate_file is None

    def test_materialize_review_mandate_only(self, governance_root: tuple[Path, Path]):
        result = _materialize(governance_root, review_mandate="Test review mandate")
        assert result.review_mandate_file is not None
        assert result.review_mandate_file.read_text() == "Test review mandate"

    def test_materialize_all_artifacts(self, governance_root: tuple[Path, Path]):
        result = _materialize(
            governance_root,
            plan_mandate="Plan mandate",
            effective_policy="Effective policy",
            review_mandate="Review mandate",
        )
        assert result.plan_mandate_sha256 == _sha256_digest("Plan mandate")
        assert result.effective_policy_sha256 == _sha256_digest("Effective policy")
        assert result.review_mandate_sha256 == _sha256_digest("Review mandate")
        assert result.has_materialized() is True

    def test_has_materialized_false_when_empty(self, governance_root: tuple[Path, Path]):
        result = _materialize(governance_root)
        assert result.has_materialized() is False


class TestMaterializeBadCases:
    def test_materialize_nonexistent_output_dir(self):
        with pytest.raises(GovernanceContextMaterializationError) as exc:
            materialize_governance_artifacts(
                output_dir=Path("/nonexistent/path/that/does/not/exist"),
                plan_mandate="Test",
            )
        assert exc.value.reason_code == GOVERNANCE_CONTEXT_MATERIALIZATION_FAILED

    def test_materialize_empty_content_rejected(self, governance_root: tuple[Path, Path]):
        out, _ = governance_root
        with pytest.raises(GovernanceContextMaterializationError):
            _materialize_text_file(out, "test", "")

    def test_materialize_whitespace_only_content_rejected(self, governance_root: tuple[Path, Path]):
        out, _ = governance_root
        with pytest.raises(GovernanceContextMaterializationError):
            _materialize_text_file(out, "test", "   ")

    def test_materialize_output_dir_not_within_allowed_roots(self, tmp_path: Path):
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        with pytest.raises(GovernanceContextMaterializationError) as exc:
            materialize_governance_artifacts(
                output_dir=outside_dir,
                home=tmp_path,
                plan_mandate="Test",
            )
        assert "allowed governance roots" in exc.value.reason.lower()


class TestValidateMaterializedArtifacts:
    def test_validate_all_artifacts_valid(self, governance_root: tuple[Path, Path]):
        result = _materialize(
            governance_root,
            plan_mandate="Test mandate",
            effective_policy="Test policy",
            review_mandate="Test review",
        )
        validate_materialized_artifacts(result)

    def test_validate_missing_file(self, tmp_path: Path):
        materialization = GovernanceContextMaterialization(
            plan_mandate_file=tmp_path / "nonexistent.txt",
            plan_mandate_sha256="abc123",
            plan_mandate_label="Test",
            effective_policy_file=None,
            effective_policy_sha256=None,
            effective_policy_label="",
            review_mandate_file=None,
            review_mandate_sha256=None,
            review_mandate_label="",
        )
        with pytest.raises(GovernanceContextMaterializationError):
            validate_materialized_artifacts(materialization)

    def test_validate_digest_mismatch(self, tmp_path: Path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")
        materialization = GovernanceContextMaterialization(
            plan_mandate_file=test_file,
            plan_mandate_sha256="wrong_digest",
            plan_mandate_label="Test",
            effective_policy_file=None,
            effective_policy_sha256=None,
            effective_policy_label="",
            review_mandate_file=None,
            review_mandate_sha256=None,
            review_mandate_label="",
        )
        with pytest.raises(GovernanceContextMaterializationError):
            validate_materialized_artifacts(materialization)

    def test_validate_empty_file(self, tmp_path: Path):
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")
        materialization = GovernanceContextMaterialization(
            plan_mandate_file=test_file,
            plan_mandate_sha256=_sha256_digest(""),
            plan_mandate_label="Test",
            effective_policy_file=None,
            effective_policy_sha256=None,
            effective_policy_label="",
            review_mandate_file=None,
            review_mandate_sha256=None,
            review_mandate_label="",
        )
        with pytest.raises(GovernanceContextMaterializationError):
            validate_materialized_artifacts(materialization)
