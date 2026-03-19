from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    assert path.exists(), f"Missing file: {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


@pytest.mark.conformance
class TestReadmeUxCompletion:
    def test_governance_content_docs_are_not_shims(self) -> None:
        for rel in [
            "governance_content/README.md",
            "governance_content/README-OPENCODE.md",
            "governance_content/QUICKSTART.md",
        ]:
            content = _read(REPO_ROOT / rel)
            assert "shim" not in content.lower(), f"{rel} must be a completed UX doc, not a shim"
            assert len(content.splitlines()) >= 30, f"{rel} must contain substantive content"

    def test_readme_surfaces_include_canonical_rail_progression(self) -> None:
        readme = _read(REPO_ROOT / "governance_content" / "README.md")
        assert "/continue" in readme
        assert "/review" in readme
        assert "read-only rail entrypoint" in readme
        assert "/review-decision" in readme
        assert "/implement" in readme

    def test_readme_uses_final_state_layer_authority_language(self) -> None:
        readme = _read(REPO_ROOT / "governance_content" / "README.md")
        assert "governance_runtime/" in readme
        assert "governance_content/" in readme
        assert "governance_spec/" in readme
        assert "compatibility surface" in readme.lower()
        assert "Installer-managed runtime and policy assets under `governance/`." not in readme

    def test_quickstart_does_not_present_legacy_kernel_as_authority(self) -> None:
        quickstart = _read(REPO_ROOT / "governance_content" / "QUICKSTART.md")
        assert "Kernel: `governance/kernel/*` is the only control-plane implementation." not in quickstart
        assert "governance_runtime/kernel/*" in quickstart

    def test_readme_links_to_quickstarts_and_documents_install_layout(self) -> None:
        readme = _read(REPO_ROOT / "governance_content" / "README.md")
        assert "Quickstarts: `QUICKSTART.md`, `README-OPENCODE.md`" in readme
        assert "Post-install directory layout" in readme
        assert "<config_root>/" in readme
        assert "<local_root>/" in readme
        assert "governance.paths.json" in readme
        assert "plugins/" in readme
        assert "workspaces/" in readme
        assert "<repo_fingerprint>/" in readme
        assert "_global/" in readme
        assert "governance_runtime/" in readme
        assert "governance_content/" in readme
        assert "governance_spec/" in readme

    def test_opencode_readme_covers_launcher_and_gates(self) -> None:
        opencode = _read(REPO_ROOT / "governance_content" / "README-OPENCODE.md")
        assert "opencode-governance-bootstrap" in opencode
        assert "/continue" in opencode
        assert "/review" in opencode
        assert "read-only rail entrypoint" in opencode
        assert "/review-decision" in opencode
        assert "governance_runtime/" in opencode

    def test_quickstart_covers_end_to_end_operator_flow(self) -> None:
        quickstart = _read(REPO_ROOT / "governance_content" / "QUICKSTART.md")
        assert "Step 1: Install" in quickstart
        assert "opencode-governance-bootstrap" in quickstart
        assert "/continue" in quickstart
        assert "/review" in quickstart
        assert "read-only rail entrypoint" in quickstart
        assert "/review-decision" in quickstart

    def test_canonical_bootstrap_command_is_consistent_across_user_docs(self) -> None:
        expected = "opencode-governance-bootstrap init --profile"
        docs = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
            REPO_ROOT / "governance_content" / "README.md",
            REPO_ROOT / "governance_content" / "QUICKSTART.md",
            REPO_ROOT / "governance_content" / "README-OPENCODE.md",
        ]
        for path in docs:
            content = _read(path)
            assert expected in content, f"{path.relative_to(REPO_ROOT)} missing canonical bootstrap command"

    def test_python_module_invocation_not_primary_in_user_docs(self) -> None:
        docs = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
            REPO_ROOT / "governance_content" / "README.md",
            REPO_ROOT / "governance_content" / "QUICKSTART.md",
            REPO_ROOT / "governance_content" / "README-OPENCODE.md",
        ]
        for path in docs:
            content = _read(path)
            assert "python -m governance" not in content
            assert "python -m governance_runtime" not in content

    def test_operator_truth_paths_are_consistent(self) -> None:
        docs = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
            REPO_ROOT / "governance_content" / "README.md",
            REPO_ROOT / "governance_content" / "QUICKSTART.md",
            REPO_ROOT / "governance_content" / "README-OPENCODE.md",
        ]
        contents = {path: _read(path) for path in docs}
        for path, content in contents.items():
            assert ".config/opencode" in content, f"{path.relative_to(REPO_ROOT)} missing config root truth"
            assert ".local/opencode" in content, f"{path.relative_to(REPO_ROOT)} missing local root truth"
            assert "commands" in content, f"{path.relative_to(REPO_ROOT)} missing commands truth"
            assert "plugins" in content, f"{path.relative_to(REPO_ROOT)} missing plugins truth"
            assert "workspaces" in content, f"{path.relative_to(REPO_ROOT)} missing workspaces truth"

        merged = "\n".join(contents.values())
        required_tokens = [
            "governance_runtime",
            "governance_content",
            "governance_spec",
        ]
        for token in required_tokens:
            assert token in merged, f"Operator truth missing canonical payload token: {token}"
