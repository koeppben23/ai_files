from __future__ import annotations

from artifacts.normalization import has_legacy_decision_pack_ab_prompt, normalize_legacy_placeholder_phrasing


def test_normalize_legacy_decision_pack_ab_prompts() -> None:
    legacy = "D-001\nA) Yes\nB) No\n"
    updated, changed = normalize_legacy_placeholder_phrasing(legacy)
    assert changed is True
    assert "A) Yes" not in updated
    assert "B) No" not in updated
    assert "Status: automatic" in updated
    assert "Action: Persist business-rules outcome as extracted|gap-detected|unresolved." in updated


def test_legacy_decision_pack_prompt_detection() -> None:
    assert has_legacy_decision_pack_ab_prompt("A) YES\n") is True
    assert has_legacy_decision_pack_ab_prompt("Status: automatic\n") is False
