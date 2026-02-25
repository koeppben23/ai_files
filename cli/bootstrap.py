from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from governance.application.use_cases.bootstrap_persistence import (
    BootstrapInput,
    BootstrapPersistenceService,
)
from governance.domain.models.binding import Binding
from governance.domain.models.layouts import WorkspaceLayout
from governance.domain.models.repo_identity import RepoIdentity

from cli.deps import GlobalErrorLogger, LocalFS, LocalProcessRunner
from governance.entrypoints.write_policy import EFFECTIVE_MODE, write_policy_reasons


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap persistence orchestrator")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--repo-fingerprint", required=True)
    parser.add_argument("--repo-name", required=True)
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--workspaces-home", required=True)
    parser.add_argument("--python-command", default="python3")
    parser.add_argument("--required-artifact", action="append", default=[])
    parser.add_argument("--force-read-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    service = BootstrapPersistenceService(
        fs=LocalFS(),
        runner=LocalProcessRunner(),
        logger=GlobalErrorLogger(),
    )

    repo_home = f"{args.workspaces_home.rstrip('/')}/{args.repo_fingerprint}"
    payload = BootstrapInput(
        repo_identity=RepoIdentity(
            repo_root=args.repo_root,
            fingerprint=args.repo_fingerprint,
            repo_name=args.repo_name,
            source="cli",
        ),
        binding=Binding(
            config_root=args.config_root,
            commands_home=f"{args.config_root.rstrip('/')}/commands",
            workspaces_home=args.workspaces_home,
            python_command=args.python_command,
        ),
        layout=WorkspaceLayout(
            repo_home=repo_home,
            session_state_file=f"{repo_home}/SESSION_STATE.json",
            identity_map_file=f"{repo_home}/repo-identity-map.yaml",
            pointer_file=f"{args.config_root.rstrip('/')}/SESSION_STATE.json",
        ),
        required_artifacts=tuple(args.required_artifact),
        force_read_only=args.force_read_only,
        backfill_command=(
            args.python_command,
            "-m",
            "governance.entrypoints.persist_workspace_artifacts",
            "--repo-fingerprint",
            args.repo_fingerprint,
            "--config-root",
            args.config_root,
            "--repo-root",
            args.repo_root,
            "--require-phase2",
            "--skip-lock",
            "--quiet",
        ),
        effective_mode=EFFECTIVE_MODE,
        write_policy_reasons=write_policy_reasons(),
    )
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = service.run(payload, created_at)
    print(
        json.dumps(
            {
                "ok": result.ok,
                "gateCode": result.gate_code,
                "writeActions": result.write_actions,
                "errorCount": len(result.error_events),
            },
            ensure_ascii=True,
        )
    )
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
