from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field

from governance.application.ports.filesystem import FileSystemPort


@dataclass(frozen=True)
class ArtifactSpec:
    key: str
    path: str
    content: str
    required_phase2: bool = False


@dataclass(frozen=True)
class ArtifactBackfillInput:
    specs: tuple[ArtifactSpec, ...]
    force: bool = False
    dry_run: bool = False
    read_only: bool = False
    require_phase2: bool = False


@dataclass(frozen=True)
class BackfillSummary:
    actions: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = field(default_factory=tuple)
    phase2_ok: bool = False
    gate_code: str = "OK"


class ArtifactBackfillService:
    def __init__(self, *, fs: FileSystemPort) -> None:
        self._fs = fs

    def run(self, payload: ArtifactBackfillInput) -> BackfillSummary:
        actions: dict[str, str] = {}
        for spec in payload.specs:
            artifact_path = Path(spec.path)
            if payload.read_only:
                actions[spec.key] = "blocked-read-only"
                continue
            if payload.dry_run:
                actions[spec.key] = "write-requested"
                continue
            if self._fs.exists(artifact_path) and not payload.force:
                actions[spec.key] = "kept"
                continue
            self._fs.write_text_atomic(artifact_path, spec.content)
            actions[spec.key] = "written"

        missing = tuple(
            spec.path
            for spec in payload.specs
            if spec.required_phase2 and not self._fs.exists(Path(spec.path))
        )
        phase2_ok = len(missing) == 0
        if payload.require_phase2 and not payload.dry_run and not phase2_ok:
            gate_code = "PERSISTENCE_READ_ONLY" if payload.read_only else "PHASE2_ARTIFACTS_MISSING"
            return BackfillSummary(actions=actions, missing=missing, phase2_ok=False, gate_code=gate_code)
        return BackfillSummary(actions=actions, missing=missing, phase2_ok=phase2_ok, gate_code="OK")
