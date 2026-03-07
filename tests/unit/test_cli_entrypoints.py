from __future__ import annotations

from cli.backfill import main as backfill_main
from cli.bootstrap import main as bootstrap_main
from cli.route import main as route_main


def test_route_cli_returns_blocked_code_for_missing_rulebooks() -> None:
    code = route_main(
        [
            "--requested-phase",
            "2.0",
            "--target-phase",
            "4.1",
            "--persistence-committed",
            "--artifacts-committed",
            "--core-loaded",
        ]
    )
    assert code == 2


def test_backfill_cli_dry_run_returns_zero() -> None:
    code = backfill_main(
        [
            "--artifact",
            "repoCache=/mock/repo-cache.yaml",
            "--dry-run",
            "--require-phase2",
        ]
    )
    assert code == 0


def test_bootstrap_cli_force_read_only_blocks_nonzero() -> None:
    code = bootstrap_main(
        [
            "--repo-root",
            "/repo",
            "--repo-fingerprint",
            "aaaaaaaaaaaaaaaaaaaaaaaa",
            "--repo-name",
            "repo",
            "--config-root",
            "/mock/cfg",
            "--workspaces-home",
            "/mock/ws",
            "--force-read-only",
        ]
    )
    assert code == 2
