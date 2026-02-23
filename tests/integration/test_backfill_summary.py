from governance.application.use_cases.artifact_backfill import (
    ArtifactBackfillInput,
    ArtifactBackfillService,
    ArtifactSpec,
    BackfillSummary,
)
from governance.infrastructure.adapters.filesystem.in_memory import InMemoryFS


def test_backfill_summary_defaults_fail_closed() -> None:
    summary = BackfillSummary()
    assert summary.phase2_ok is False


def test_backfill_service_marks_phase2_ok_when_required_artifacts_exist() -> None:
    fs = InMemoryFS()
    service = ArtifactBackfillService(fs=fs)
    payload = ArtifactBackfillInput(
        specs=(
            ArtifactSpec(key="repoCache", path="/ws/repo-cache.yaml", content="cache", required_phase2=True),
            ArtifactSpec(key="workspaceMemory", path="/ws/workspace-memory.yaml", content="memory", required_phase2=True),
        ),
        require_phase2=True,
    )

    result = service.run(payload)

    assert result.phase2_ok is True
    assert result.gate_code == "OK"
    assert result.actions["repoCache"] == "written"


def test_backfill_service_fail_closed_on_missing_required_artifacts() -> None:
    fs = InMemoryFS()
    service = ArtifactBackfillService(fs=fs)
    payload = ArtifactBackfillInput(
        specs=(
            ArtifactSpec(key="repoCache", path="/ws/repo-cache.yaml", content="cache", required_phase2=True),
        ),
        read_only=True,
        require_phase2=True,
    )

    result = service.run(payload)

    assert result.phase2_ok is False
    assert result.gate_code == "PERSISTENCE_READ_ONLY"
    assert result.missing == ("/ws/repo-cache.yaml",)
