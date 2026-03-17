import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_phases_alias_note_present():
    # Check governance_content first (SSOT), then fall back to legacy
    phases = REPO / "governance_content" / "docs" / "phases.md"
    if not phases.exists():
        phases = REPO / "docs" / "phases.md"
    assert phases.exists(), "phases.md must exist in docs/ or governance_content/docs/"
    text = phases.read_text(encoding="utf-8").lower()
    # Expect an explicit note about Phase 1.5 alias or 2.2 alias
    assert "phase 1.5" in text or "phase 2.2" in text or "optional" in text
