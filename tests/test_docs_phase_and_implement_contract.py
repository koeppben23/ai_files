from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def _read(relpath: str) -> str:
    return (REPO / relpath).read_text(encoding="utf-8")


def test_phase4_not_described_as_implementation_phase_in_core_docs() -> None:
    docs = [
        "docs/phases.md",
        "profiles/rules.docs-governance.md",
    ]
    banned = (
        "phase 4 (implementation)",
        "phase 4 - ticket execution",
    )
    for rel in docs:
        lowered = _read(rel).lower()
        for token in banned:
            assert token not in lowered, f"{rel} contains stale phrase: {token}"


def test_rulebook_load_is_mapped_to_phase_1_3_in_runbook() -> None:
    content = _read("docs/operator-runbook.md")
    assert "BLOCKED-RULEBOOK-LOAD-FAILED" in content
    assert "Phase 1.3" in content
    assert "Phase 4 entry" not in content


def test_phase_1_5_documented_as_conditional_branch_not_parallel() -> None:
    content = _read("docs/phases.md")
    lowered = content.lower()
    assert "phase 1.5 is an optional business-rules routing branch" in lowered
    assert "may run in parallel" not in lowered


def test_router_priority_semantics_documented_in_order() -> None:
    content = _read("docs/phases.md")
    assert "first matching `specific` transition" in content
    assert "otherwise `default`" in content
    assert "otherwise `next`" in content
    assert "otherwise terminal/config error" in content


def test_implement_docs_use_desktop_llm_default_and_override_semantics() -> None:
    content = _read("implement.md")
    assert "default executor is the active OpenCode Desktop LLM binding" in content
    assert "optional override" in content
    assert "neither override nor active Desktop LLM binding" in content
