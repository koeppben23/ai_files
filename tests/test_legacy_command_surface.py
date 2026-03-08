from __future__ import annotations

import re

from .util import REPO_ROOT


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


class TestLegacyCommandSurfaceMigration:
    """Guard active surfaces against /resume and /audit legacy drift."""

    _ACTIVE_SURFACES = [
        "governance/assets/reasons/blocked_reason_catalog.yaml",
        "governance/assets/config/blocked_reason_catalog.yaml",
        "governance/assets/catalogs/reason_codes.registry.json",
        "SESSION_STATE_SCHEMA.md",
        "phase_api.yaml",
        "governance/assets/catalogs/audit.md",
        "docs/operator-runbook.md",
        "README.md",
        "README-OPENCODE.md",
        "QUICKSTART.md",
    ]

    def test_happy_reason_catalogs_use_continue(self) -> None:
        files = [
            "governance/assets/reasons/blocked_reason_catalog.yaml",
            "governance/assets/config/blocked_reason_catalog.yaml",
            "governance/assets/catalogs/reason_codes.registry.json",
        ]
        for relpath in files:
            content = _read(relpath)
            assert "/continue" in content, f"Expected /continue guidance in {relpath}"

    def test_corner_session_schema_uses_audit_readout(self) -> None:
        content = _read("SESSION_STATE_SCHEMA.md")
        assert "/audit-readout" in content
        assert "/continue" in content

    def test_edge_phase_api_uses_continue_vocabulary(self) -> None:
        content = _read("phase_api.yaml")
        assert "continue via /continue" in content
        assert "resume via /continue" not in content

    def test_happy_audit_catalog_uses_audit_readout_vocabulary(self) -> None:
        content = _read("governance/assets/catalogs/audit.md")
        assert "/audit-readout" in content
        assert "The `/audit` command" not in content
        assert "- `/audit` MUST NOT" not in content

    def test_happy_operator_runbook_uses_continue_for_recovery(self) -> None:
        content = _read("docs/operator-runbook.md")
        assert "Run `/continue`" in content
        assert "Run `/resume`" not in content

    def test_happy_contract_defines_canonical_command_surfaces(self) -> None:
        content = _read("docs/contracts/command-surface-contract.v1.md")
        assert "Session continuation surface: `/continue`" in content
        assert "Audit read-only surface: `/audit-readout`" in content
        assert "`/resume` is deprecated" in content
        assert "`/audit` is deprecated" in content

    def test_bad_no_active_resume_or_short_audit_in_target_surfaces(self) -> None:
        for relpath in self._ACTIVE_SURFACES:
            content = _read(relpath)
            assert re.search(r"(?<!docs)/resume(?!\.md)", content) is None, (
                f"Deprecated /resume command surface found in {relpath}"
            )
            assert re.search(r"/audit(?![-a-zA-Z0-9_])", content) is None, (
                f"Deprecated /audit surface found in {relpath}"
            )

    def test_bad_active_surfaces_must_not_recommend_resume_templates(self) -> None:
        for relpath in self._ACTIVE_SURFACES:
            content = _read(relpath)
            assert "resume_prompt.md" not in content, (
                f"Active surface references deprecated resume template in {relpath}"
            )

    def test_bad_active_surfaces_must_not_recommend_reload_addons(self) -> None:
        for relpath in self._ACTIVE_SURFACES:
            content = _read(relpath)
            assert "/reload-addons" not in content, (
                f"Active surface references non-canonical reload command in {relpath}"
            )

    def test_bad_blocked_catalogs_must_not_use_raw_entrypoint_quick_fixes(self) -> None:
        for relpath in [
            "governance/assets/reasons/blocked_reason_catalog.yaml",
            "governance/assets/config/blocked_reason_catalog.yaml",
        ]:
            content = _read(relpath)
            assert "governance.entrypoints.phase4_intake_persist" not in content
            assert "governance.entrypoints.phase5_plan_record_persist" not in content

    def test_bad_blocked_catalogs_must_not_use_resume_pointer_key(self) -> None:
        for relpath in [
            "governance/assets/reasons/blocked_reason_catalog.yaml",
            "governance/assets/config/blocked_reason_catalog.yaml",
        ]:
            content = _read(relpath)
            assert "resume_pointer:" not in content
            assert "next_command_pointer:" in content
