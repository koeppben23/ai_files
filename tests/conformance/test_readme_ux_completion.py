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
            "DOCS.md",
            "QUICKSTART.md",
        ]:
            content = _read(REPO_ROOT / rel)
            assert "shim" not in content.lower(), f"{rel} must be a completed UX doc, not a shim"
            assert len(content.splitlines()) >= 30, f"{rel} must contain substantive content"

    def test_readme_links_to_docs(self) -> None:
        readme = _read(REPO_ROOT / "README.md")
        assert "DOCS.md" in readme

    def test_readme_uses_final_state_layer_authority_language(self) -> None:
        readme = _read(REPO_ROOT / "README.md")
        assert "governance_runtime/" in readme
        assert "governance_content/" in readme
        assert "governance_spec/" in readme
        assert "Installer-managed runtime and policy assets under `governance/`." not in readme

    def test_docs_md_uses_final_state_layer_authority_language(self) -> None:
        docs = _read(REPO_ROOT / "DOCS.md")
        assert "governance_runtime/" in docs
        assert "governance_content/" in docs
        assert "governance_spec/" in docs
        assert "Installer-managed runtime and policy assets under `governance/`." not in docs

    def test_quickstart_does_not_present_legacy_kernel_as_authority(self) -> None:
        quickstart = _read(REPO_ROOT / "QUICKSTART.md")
        assert "Kernel: `governance_runtime/kernel/*` is the only control-plane implementation." not in quickstart
        assert "governance_runtime/kernel/*" in quickstart

    def test_readme_provides_repo_layout_summary(self) -> None:
        readme = _read(REPO_ROOT / "README.md")
        # README should have a concise layout summary
        assert "governance_runtime/" in readme
        assert "governance_content/" in readme
        assert "governance_spec/" in readme

    def test_opencode_readme_covers_launcher_and_gates(self) -> None:
        opencode = _read(REPO_ROOT / "README-OPENCODE.md")
        assert "opencode-governance-bootstrap" in opencode
        assert "/continue" in opencode
        assert "/review" in opencode
        assert "read-only rail entrypoint" in opencode
        assert "/review-decision" in opencode
        assert "governance_runtime/" in opencode

    def test_docs_covers_end_to_end_operator_flow(self) -> None:
        docs = _read(REPO_ROOT / "DOCS.md")
        assert "Step 1: Install" in docs
        assert "opencode-governance-bootstrap" in docs
        assert "/continue" in docs
        assert "/review" in docs
        assert "read-only rail entrypoint" in docs
        assert "/review-decision" in docs

    def test_canonical_bootstrap_command_is_consistent_across_user_docs(self) -> None:
        expected = "opencode-governance-bootstrap init --profile"
        docs = [
            REPO_ROOT / "DOCS.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
        ]
        for path in docs:
            content = _read(path)
            assert expected in content, f"{path.relative_to(REPO_ROOT)} missing canonical bootstrap command"

    def test_canonical_bin_directory_truth_is_explicit(self) -> None:
        docs = [
            REPO_ROOT / "DOCS.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
        ]
        for path in docs:
            content = _read(path)
            assert ("~/.config/opencode/bin" in content) or ("${CONFIG_ROOT}/bin" in content), (
                f"{path.relative_to(REPO_ROOT)} missing canonical bin directory guidance"
            )

    def test_python_module_invocation_not_primary_in_user_docs(self) -> None:
        docs = [
            REPO_ROOT / "DOCS.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
        ]
        for path in docs:
            content = _read(path)
            assert "python -m governance" not in content
            assert "python -m governance_runtime" not in content

    def test_no_equal_rank_alternative_bootstrap_command_paths(self) -> None:
        docs = [
            REPO_ROOT / "DOCS.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
        ]
        for path in docs:
            content = _read(path)
            assert "governance.entrypoints.new_work_session" not in content
            assert "governance_runtime.entrypoints.new_work_session" not in content

    def test_operator_truth_paths_are_consistent(self) -> None:
        docs = [
            REPO_ROOT / "DOCS.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
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

    def test_master_surfaces_include_runtime_authority_and_operator_truth(self) -> None:
        docs = [
            REPO_ROOT / "governance_content" / "reference" / "master.md",
        ]
        for path in docs:
            content = _read(path)
            assert "governance_runtime/kernel/*" in content
            assert "governance/kernel/*" not in content
            assert "opencode-governance-bootstrap init --profile" in content
            assert ".config/opencode" in content
            assert ".local/opencode" in content
            assert "removed from productive runtime authority" in content

    def test_operator_runbook_contains_canonical_operator_truth(self) -> None:
        runbook = _read(REPO_ROOT / "governance_content" / "docs" / "operator-runbook.md")
        assert "opencode-governance-bootstrap init --profile" in runbook
        assert ".config/opencode" in runbook
        assert ".local/opencode" in runbook
        assert "python -m ..." in runbook
        assert "not primary operator guidance" in runbook

    def test_docs_do_not_present_commands_governance_as_primary_model(self) -> None:
        docs = [
            REPO_ROOT / "DOCS.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "BOOTSTRAP.md",
            REPO_ROOT / "governance_content" / "docs" / "operator-runbook.md",
        ]
        for path in docs:
            content = _read(path)
            assert "commands/governance/" not in content, (
                f"{path.relative_to(REPO_ROOT)} must not describe commands/governance as active model"
            )
