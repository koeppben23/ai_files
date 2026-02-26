from pathlib import Path
import pytest

# Local imports from the same repo
import install as installer  # type: ignore

from tests.util import REPO_ROOT


def test_smoke_installer_creates_wrappers(tmp_path: Path):
    source_dir = REPO_ROOT
    config_root = tmp_path / "opencode-config-smoke"

    plan = installer.build_plan(
        source_dir=source_dir,
        config_root=config_root,
        skip_paths_file=False,
        deterministic_paths_file=False,
    )

    # Create runtime dirs
    installer.ensure_dirs(config_root, dry_run=False)

    created = installer.create_launcher(plan, dry_run=False, force=False)

    bin_unix = config_root / "bin" / "opencode-governance-bootstrap"
    bin_win = config_root / "bin" / "opencode-governance-bootstrap.cmd"

    assert bin_unix.exists(), f"Unix launcher not installed: {bin_unix}"
    assert bin_win.exists(), f"Windows launcher not installed: {bin_win}"
    assert bin_unix.stat().st_size > 0
    assert bin_win.stat().st_size > 0
    assert isinstance(created, list)
