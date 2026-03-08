from __future__ import annotations

import re

from .util import REPO_ROOT


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


class TestLegacyCommandSurfaceMigration:
    """Guard active surfaces against /resume and /audit legacy drift."""

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

    def test_bad_no_active_resume_or_short_audit_in_target_surfaces(self) -> None:
        files = [
            "governance/assets/reasons/blocked_reason_catalog.yaml",
            "governance/assets/config/blocked_reason_catalog.yaml",
            "governance/assets/catalogs/reason_codes.registry.json",
            "SESSION_STATE_SCHEMA.md",
            "phase_api.yaml",
        ]
        for relpath in files:
            content = _read(relpath)
            assert re.search(r"(?<!docs)/resume(?!\.md)", content) is None, (
                f"Deprecated /resume command surface found in {relpath}"
            )
            assert re.search(r"(?<!-readout)\b/audit\b", content) is None, (
                f"Deprecated /audit surface found in {relpath}"
            )
