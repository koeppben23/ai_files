from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_installer_is_thin_delegator() -> None:
    root_installer = REPO_ROOT / "install.py"
    runtime_installer = REPO_ROOT / "governance_runtime" / "install" / "install.py"
    assert root_installer.exists()
    assert runtime_installer.exists()
    root_source = root_installer.read_text(encoding="utf-8")
    assert "import governance_runtime.install.install as _impl" in root_source
    assert "def main(" in root_source
    assert "_runtime_main(args)" in root_source
    assert "if __name__ == \"__main__\":" in root_source
    assert "raise SystemExit(main(sys.argv[1:]))" in root_source


def test_runtime_installer_remains_canonical_authority() -> None:
    runtime_installer = REPO_ROOT / "governance_runtime" / "install" / "install.py"
    source = runtime_installer.read_text(encoding="utf-8")
    assert "def build_governance_paths_payload(" in source
    assert "def parse_args(" in source
    assert "def ensure_dirs(" in source
    assert "def create_launcher(" in source
    assert "def install(" in source
    assert "def main(" in source


def test_root_installer_has_no_embedded_install_logic() -> None:
    root_source = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
    for forbidden in (
        "def build_governance_paths_payload(",
        "def ensure_dirs(",
        "def create_launcher(",
        "def run_install(",
    ):
        assert forbidden not in root_source, (
            "Root installer must remain a delegator, not a second logic source"
        )
