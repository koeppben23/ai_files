from __future__ import annotations

from pathlib import Path

from scripts.install_layout_gate import EXPECTED_CONFIG_DIRS, EXPECTED_CONFIG_FILES, EXPECTED_LOCAL_TOP_LEVEL, EXPECTED_RAILS, verify_install_layout


def _touch(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_happy(config_root: Path, local_root: Path) -> None:
    for name in EXPECTED_CONFIG_DIRS:
        (config_root / name).mkdir(parents=True, exist_ok=True)
    for name in EXPECTED_CONFIG_FILES:
        _touch(config_root / name)
    for rail in EXPECTED_RAILS:
        _touch(config_root / "commands" / rail, "# rail\n")
    for name in EXPECTED_LOCAL_TOP_LEVEL:
        path = local_root / name
        if name == "VERSION":
            _touch(path, "1.2.3\n")
        else:
            path.mkdir(parents=True, exist_ok=True)


def test_install_layout_gate_happy(tmp_path: Path) -> None:
    config_root = tmp_path / "cfg"
    local_root = tmp_path / "local"
    _seed_happy(config_root, local_root)
    issues = verify_install_layout(config_root, local_root)
    assert issues == []


def test_install_layout_gate_bad_extra_legacy_dir(tmp_path: Path) -> None:
    config_root = tmp_path / "cfg"
    local_root = tmp_path / "local"
    _seed_happy(config_root, local_root)
    (local_root / "governance_runtime").mkdir(parents=True, exist_ok=True)
    issues = verify_install_layout(config_root, local_root)
    assert any("must not contain governance/" in item for item in issues)


def test_install_layout_gate_corner_missing_required_file(tmp_path: Path) -> None:
    config_root = tmp_path / "cfg"
    local_root = tmp_path / "local"
    _seed_happy(config_root, local_root)
    (config_root / "INSTALL_HEALTH.json").unlink()
    issues = verify_install_layout(config_root, local_root)
    assert any("missing required entry: INSTALL_HEALTH.json" in item for item in issues)


def test_install_layout_gate_edge_unexpected_commands_json(tmp_path: Path) -> None:
    config_root = tmp_path / "cfg"
    local_root = tmp_path / "local"
    _seed_happy(config_root, local_root)
    _touch(config_root / "commands" / "shadow.json", "{}")
    issues = verify_install_layout(config_root, local_root)
    assert any("unexpected md/json" in item for item in issues)
