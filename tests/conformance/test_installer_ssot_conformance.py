from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_and_runtime_installers_are_byte_identical() -> None:
    root_installer = REPO_ROOT / "install.py"
    runtime_installer = REPO_ROOT / "governance_runtime" / "install" / "install.py"
    assert root_installer.exists()
    assert runtime_installer.exists()
    assert root_installer.read_text(encoding="utf-8") == runtime_installer.read_text(encoding="utf-8"), (
        "install.py drift detected: root installer must mirror governance_runtime/install/install.py"
    )
