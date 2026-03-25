from __future__ import annotations

from pathlib import Path

from install import CANONICAL_RAIL_FILENAMES
from install import enforce_local_payload_hygiene
from install import has_installation
from install import resolve_known_config_roots


def test_resolve_known_config_roots_contains_primary(tmp_path: Path) -> None:
    primary = tmp_path / "cfg"
    roots = resolve_known_config_roots(primary)
    assert primary.resolve() in roots


def test_has_installation_true_only_when_all_canonical_rails_exist(tmp_path: Path) -> None:
    root = tmp_path / "cfg"
    commands = root / "commands"
    commands.mkdir(parents=True)

    assert has_installation(root) is False

    for name in CANONICAL_RAIL_FILENAMES:
        (commands / name).write_text("# cmd\n", encoding="utf-8")

    assert has_installation(root) is True


def test_local_payload_hygiene_treats_ds_store_as_harmless(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    local_root.mkdir(parents=True)
    (local_root / ".DS_Store").write_text("meta", encoding="utf-8")

    removed, violations = enforce_local_payload_hygiene(local_root=local_root, dry_run=False)

    assert ".DS_Store" in removed
    assert ".DS_Store" not in violations
