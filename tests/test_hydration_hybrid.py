"""Tests for hydration with hybrid extractor output.

Verifies that business_rules_hydration.py works correctly with:
1. ExtractorVersion: hybrid-br-v1 in status files
2. Mixed doc+code inventory (BR-xxx and BR-Cxxx rules)
3. Empty inventory (extractor ran, 0 rules)
4. Edge cases around the new ExtractionSource field

Covers: Happy (3), Bad (3), Corner (3), Edge (3) = 12 tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governance.engine.business_rules_hydration import hydrate_business_rules_state_from_artifacts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _status_hybrid(outcome: str = "extracted", evidence: str = "true") -> str:
    return (
        f"# Business Rules Status - test-repo\n"
        f"\n"
        f"Outcome: {outcome}\n"
        f"OutcomeSource: extractor\n"
        f"SourcePhase: 1.5-BusinessRules\n"
        f"ExecutionEvidence: {evidence}\n"
        f"ExtractorVersion: hybrid-br-v1\n"
        f"ExtractionSource: hybrid\n"
        f"RulesHash: abc123\n"
        f"ValidationResult: passed\n"
        f"ValidRules: 3\n"
        f"InvalidRules: 0\n"
        f"DroppedCandidates: 0\n"
        f"ReasonCodes: none\n"
        f"SourceDiagnostics: none\n"
        f"RenderConsistency: passed\n"
        f"CountConsistency: passed\n"
        f"DocOnlyRules: 1\n"
        f"CodeOnlyRules: 1\n"
        f"DocAndCodeRules: 1\n"
        f"InventoryPolicy: business-rules-status.md is always written; business-rules.md is written only when outcome=extracted with extractor evidence.\n"
        f"Last Updated: 2026-03-13\n"
    )


def _inventory_mixed() -> str:
    """Inventory with both doc-extracted (BR-xxx) and code-sourced (BR-Cxxx) rules."""
    return (
        "- BR-001: Access must be checked before any write operation\n"
        "- BR-002: Audit entries are immutable once created\n"
        "- BR-C001: Withdrawal amount must not exceed the daily limit\n"
    )


def _inventory_doc_only() -> str:
    return (
        "- BR-001: Access must be checked before any write operation\n"
        "- BR-002: Audit entries are immutable once created\n"
    )


# ===========================================================================
# Happy-path tests
# ===========================================================================

@pytest.mark.governance
class TestHydrationHybridHappy:

    def test_hydration_with_hybrid_version_succeeds(self, tmp_path: Path) -> None:
        """Hydration accepts ExtractorVersion: hybrid-br-v1 without error."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid())
        _write(inv, _inventory_mixed())
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        business = state["BusinessRules"]
        assert isinstance(business, dict)
        assert business["ExtractedCount"] == 3
        assert business["Outcome"] == "extracted"
        assert business["ExecutionEvidence"] is True

    def test_hydration_with_mixed_doc_and_code_rules_loads_all(self, tmp_path: Path) -> None:
        """Both BR-xxx and BR-Cxxx rules are loaded into inventory."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid())
        _write(inv, _inventory_mixed())
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        business = state["BusinessRules"]
        assert isinstance(business, dict)
        rules = business["Rules"]
        assert isinstance(rules, list)
        assert len(rules) == 3
        rule_ids = [r.split(":")[0].strip() for r in rules]
        assert "BR-001" in rule_ids
        assert "BR-002" in rule_ids
        assert "BR-C001" in rule_ids

    def test_hydration_not_applicable_with_hybrid_version_maps_to_gap_detected(self, tmp_path: Path) -> None:
        """Legacy not-applicable with BR signal maps to canonical gap-detected."""
        status = tmp_path / "business-rules-status.md"
        _write(status, _status_hybrid(outcome="not-applicable"))
        inv = tmp_path / "business-rules.md"
        # No inventory file for not-applicable
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        business = state["BusinessRules"]
        assert isinstance(business, dict)
        assert business["Outcome"] == "gap-detected"
        assert business["HasSignal"] is True


# ===========================================================================
# Bad-input tests
# ===========================================================================

@pytest.mark.governance
class TestHydrationHybridBad:

    def test_hydration_extracted_without_execution_evidence_fails(self, tmp_path: Path) -> None:
        """extracted outcome without execution evidence → hydration rejects."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid(evidence="false"))
        _write(inv, _inventory_mixed())
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]

    def test_hydration_extracted_without_inventory_file_fails(self, tmp_path: Path) -> None:
        """extracted outcome + missing inventory file → hydration rejects."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid())
        # Don't create inventory file
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]

    def test_hydration_extracted_with_empty_inventory_fails(self, tmp_path: Path) -> None:
        """extracted outcome + empty inventory file → hydration rejects (0 rules)."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid())
        _write(inv, "")
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]


# ===========================================================================
# Corner-case tests
# ===========================================================================

@pytest.mark.governance
class TestHydrationHybridCorner:

    def test_hydration_preserves_existing_scope_keys(self, tmp_path: Path) -> None:
        """Hydration adds Scope.BusinessRules without clobbering other Scope keys."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid())
        _write(inv, _inventory_mixed())
        state: dict[str, object] = {"Scope": {"Repository": "my-repo"}}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        scope = state["Scope"]
        assert isinstance(scope, dict)
        assert scope["Repository"] == "my-repo"
        assert scope["BusinessRules"] == "extracted"

    def test_hydration_doc_only_inventory_with_hybrid_status(self, tmp_path: Path) -> None:
        """Hybrid status + count mismatch fails closed."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid())
        _write(inv, _inventory_doc_only())
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]

    def test_hydration_skipped_outcome_with_hybrid_version_maps_to_gap_detected(self, tmp_path: Path) -> None:
        """Legacy skipped with BR signal maps to canonical gap-detected."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid(outcome="skipped"))
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        scope = state["Scope"]
        assert isinstance(scope, dict)
        assert scope["BusinessRules"] == "gap-detected"


# ===========================================================================
# Edge-case tests
# ===========================================================================

@pytest.mark.governance
class TestHydrationHybridEdge:

    def test_hydration_deferred_outcome_with_hybrid_version_maps_to_gap_detected(self, tmp_path: Path) -> None:
        """Legacy deferred with BR signal maps to canonical gap-detected."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid(outcome="deferred"))
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        scope = state["Scope"]
        assert isinstance(scope, dict)
        assert scope["BusinessRules"] == "gap-detected"

    def test_hydration_with_extra_status_fields_ignored(self, tmp_path: Path) -> None:
        """Unknown fields in status file (ExtractionSource, DocOnlyRules, etc.) are ignored."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        # Status with all hybrid fields
        _write(status, _status_hybrid())
        _write(inv, _inventory_mixed())
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        # Hydration doesn't crash or produce wrong values from unknown fields
        business = state["BusinessRules"]
        assert isinstance(business, dict)
        assert business["ExtractedCount"] == 3

    def test_hydration_quality_report_version_always_br_quality_v2(self, tmp_path: Path) -> None:
        """QualityReportVersion remains br-quality-v2 regardless of extractor version."""
        status = tmp_path / "business-rules-status.md"
        inv = tmp_path / "business-rules.md"
        _write(status, _status_hybrid())
        _write(inv, _inventory_mixed())
        state: dict[str, object] = {}

        ok = hydrate_business_rules_state_from_artifacts(
            state=state, status_path=status, inventory_path=inv
        )

        assert ok is True
        business = state["BusinessRules"]
        assert isinstance(business, dict)
        assert business["QualityReportVersion"] == "br-quality-v2"
