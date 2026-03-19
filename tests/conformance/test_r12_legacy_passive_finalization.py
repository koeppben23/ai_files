from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestR12LegacyPassiveFinalization:
    def test_plugin_uses_runtime_entrypoint_not_legacy_entrypoint(self) -> None:
        plugin = (
            REPO_ROOT
            / "governance"
            / "artifacts"
            / "opencode-plugins"
            / "audit-new-session.mjs"
        ).read_text(encoding="utf-8")
        assert "governance_runtime.entrypoints.new_work_session" in plugin
        assert "governance.entrypoints.new_work_session" not in plugin

    def test_installer_places_compatibility_surface_under_local_root(self) -> None:
        source = (REPO_ROOT / "governance_runtime" / "install" / "install.py").read_text(encoding="utf-8")
        assert "dst = plan.local_root / rel" in source
        assert "governance_home = local_root / \"governance\"" in source
        assert "runtime_home = local_root / \"governance_runtime\"" in source

    def test_installer_no_longer_copies_legacy_runtime_payload_to_commands_surface(self) -> None:
        source = (REPO_ROOT / "governance_runtime" / "install" / "install.py").read_text(encoding="utf-8")
        assert "Copying governance runtime package to commands/governance" not in source
        marker = "for rf in runtime_files:"
        start = source.find(marker)
        assert start > 0, "runtime copy loop not found"
        runtime_block = source[start : start + 400]
        assert "dst = plan.local_root / rel" in runtime_block
        assert "dst = plan.commands_dir / rel" not in runtime_block

    def test_io_verify_accepts_runtime_launcher_only(self) -> None:
        source = (
            REPO_ROOT / "governance_runtime" / "infrastructure" / "io_verify.py"
        ).read_text(encoding="utf-8")
        assert "allowed_launcher = \"governance_runtime.entrypoints.new_work_session\"" in source
        assert "governance.entrypoints.new_work_session" not in source

    def test_r10_proof_states_legacy_is_passive_and_not_commands_surface_authority(self) -> None:
        proof = (REPO_ROOT / "governance_spec" / "migrations" / "R10_Final_State_Proof.md").read_text(
            encoding="utf-8"
        )
        assert "frozen passive compatibility surface only" in proof
        assert "commands/governance/" in proof
        assert "must not be used as active runtime installation target" in proof
