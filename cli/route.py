from __future__ import annotations

import argparse
import json

from governance.application.use_cases.route_phase import RoutePhaseInput, RoutePhaseService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route phase with fail-closed gates")
    parser.add_argument("--requested-phase", default="1.1-Bootstrap")
    parser.add_argument("--target-phase")
    parser.add_argument("--core-loaded", action="store_true")
    parser.add_argument("--profile-loaded", action="store_true")
    parser.add_argument("--persistence-committed", action="store_true")
    parser.add_argument("--artifacts-committed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    loaded = {
        "core": "loaded" if args.core_loaded else "",
        "profile": "loaded" if args.profile_loaded else "",
    }
    persistence_state = {
        "CommitFlags": {
            "PersistenceCommitted": bool(args.persistence_committed),
            "WorkspaceArtifactsCommitted": bool(args.artifacts_committed),
        }
    }
    routed = RoutePhaseService().run(
        RoutePhaseInput(
            requested_phase=args.requested_phase,
            target_phase=args.target_phase,
            loaded_rulebooks=loaded,
            persistence_state=persistence_state,
        )
    )
    print(
        json.dumps(
            {
                "phase": routed.phase,
                "blockedCode": routed.blocked_code,
                "reason": routed.reason,
                "nextAction": routed.next_action,
            },
            ensure_ascii=True,
        )
    )
    return 0 if routed.blocked_code is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
