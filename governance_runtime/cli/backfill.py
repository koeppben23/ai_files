from __future__ import annotations

import argparse
import json
from typing import Optional

from governance_runtime.application.use_cases.artifact_backfill import (
    ArtifactBackfillInput,
    ArtifactBackfillService,
    ArtifactSpec,
)

from governance_runtime.cli.deps import LocalFS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill workspace artifacts")
    parser.add_argument("--artifact", action="append", default=[], help="key=path")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--require-phase2", action="store_true")
    return parser


def _parse_specs(values: list[str]) -> tuple[ArtifactSpec, ...]:
    specs: list[ArtifactSpec] = []
    for value in values:
        if "=" not in value:
            continue
        key, path = value.split("=", 1)
        specs.append(ArtifactSpec(key=key.strip(), path=path.strip(), content="pending", required_phase2=True))
    return tuple(specs)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    service = ArtifactBackfillService(fs=LocalFS())
    summary = service.run(
        ArtifactBackfillInput(
            specs=_parse_specs(args.artifact),
            force=args.force,
            dry_run=args.dry_run,
            read_only=args.read_only,
            require_phase2=args.require_phase2,
        )
    )
    print(
        json.dumps(
            {
                "actions": summary.actions,
                "missing": list(summary.missing),
                "phase2Ok": summary.phase2_ok,
                "gateCode": summary.gate_code,
            },
            ensure_ascii=True,
        )
    )
    return 0 if summary.gate_code == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
