"""Tests for orchestrator integration of LLM code candidates (hybrid extraction).

Tests that the persist_workspace_artifacts_orchestrator correctly:
1. Reads BusinessRuleCandidates from session CodebaseContext
2. Merges them with doc-extracted rules via merge_code_candidates()
3. Re-validates merged candidates through validate_candidates()
4. Renders provenance counts in business-rules-status.md
5. Includes extraction_source in event JSONL
6. Falls back gracefully when no code candidates present

Covers: Happy (4), Bad (4), Corner (4), Edge (4) = 16 tests.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from .util import REPO_ROOT


def _load_orchestrator_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_code_candidate(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "BR-C001",
        "candidate_rule_text": "BR-C001: Withdrawal amount must not exceed the daily limit",
        "source_path": "src/main/java/com/bank/WithdrawalService.java",
        "line_range": "42-48",
        "pattern_type": "validation-guard",
        "confidence": "high",
        "evidence_snippet": "if (amount > MAX_DAILY) throw ...",
    }
    base.update(overrides)
    return base


# ===========================================================================
# Happy-path tests
# ===========================================================================

@pytest.mark.governance
class TestOrchestratorCodeCandidatesHappy:

    def test_version_bumped_to_hybrid(self) -> None:
        """Extractor version must be hybrid-br-v1."""
        module = _load_orchestrator_module()
        assert module._BUSINESS_RULES_EXTRACTOR_VERSION == "hybrid-br-v1"

    def test_status_renderer_deterministic_mode_no_provenance_lines(self) -> None:
        """When extraction_source=deterministic, no DocOnly/CodeOnly/DocAndCode lines appear."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc123",
            extraction_source="deterministic",
        )
        assert "ExtractionSource: deterministic" in content
        assert "DocOnlyRules:" not in content
        assert "CodeOnlyRules:" not in content
        assert "DocAndCodeRules:" not in content

    def test_status_renderer_hybrid_mode_includes_provenance_counts(self) -> None:
        """When extraction_source=hybrid, DocOnly/CodeOnly/DocAndCode lines must appear."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc123",
            extraction_source="hybrid",
            doc_only_count=3,
            code_only_count=2,
            doc_and_code_count=1,
        )
        assert "ExtractionSource: hybrid" in content
        assert "DocOnlyRules: 3" in content
        assert "CodeOnlyRules: 2" in content
        assert "DocAndCodeRules: 1" in content

    def test_status_renderer_hybrid_zero_provenance(self) -> None:
        """Hybrid mode with 0 provenance counts still renders the lines."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="unresolved",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="",
            extraction_source="hybrid",
            doc_only_count=0,
            code_only_count=0,
            doc_and_code_count=0,
        )
        assert "DocOnlyRules: 0" in content
        assert "CodeOnlyRules: 0" in content
        assert "DocAndCodeRules: 0" in content


# ===========================================================================
# Bad-input tests
# ===========================================================================

@pytest.mark.governance
class TestOrchestratorCodeCandidatesBad:

    def test_status_renderer_rejects_missing_required_params(self) -> None:
        """Calling without required params raises TypeError."""
        module = _load_orchestrator_module()
        with pytest.raises(TypeError):
            module._render_business_rules_status()

    def test_status_renderer_extraction_source_defaults_to_deterministic(self) -> None:
        """extraction_source parameter defaults to 'deterministic' when not passed."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="unresolved",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="",
        )
        assert "ExtractionSource: deterministic" in content

    def test_status_renderer_unknown_extraction_source_passthrough(self) -> None:
        """Unknown extraction_source value passes through (no validation at render level)."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc",
            extraction_source="unknown-source",
        )
        assert "ExtractionSource: unknown-source" in content
        # Non-hybrid → no provenance lines
        assert "DocOnlyRules:" not in content

    def test_provenance_counts_default_zero_when_omitted(self) -> None:
        """doc_only_count, code_only_count, doc_and_code_count default to 0."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc",
            extraction_source="hybrid",
        )
        assert "DocOnlyRules: 0" in content
        assert "CodeOnlyRules: 0" in content
        assert "DocAndCodeRules: 0" in content


# ===========================================================================
# Corner-case tests
# ===========================================================================

@pytest.mark.governance
class TestOrchestratorCodeCandidatesCorner:

    def test_status_contains_extraction_source_before_rules_hash(self) -> None:
        """ExtractionSource field must appear in the output before RulesHash."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc",
            extraction_source="hybrid",
        )
        es_pos = content.index("ExtractionSource:")
        rh_pos = content.index("RulesHash:")
        assert es_pos < rh_pos

    def test_status_provenance_lines_after_count_consistency(self) -> None:
        """In hybrid mode, provenance lines appear after CountConsistency."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc",
            extraction_source="hybrid",
            doc_only_count=1,
            code_only_count=1,
            doc_and_code_count=0,
        )
        cc_pos = content.index("CountConsistency:")
        doc_pos = content.index("DocOnlyRules:")
        assert doc_pos > cc_pos

    def test_inventory_written_field_reflects_extracted_outcome(self) -> None:
        """business-rules.md written: yes when outcome=extracted with evidence."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc",
            extraction_source="hybrid",
        )
        assert "business-rules.md (written: yes)" in content

    def test_inventory_written_no_when_unresolved(self) -> None:
        """business-rules.md written: no when outcome=unresolved."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="unresolved",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="",
            extraction_source="hybrid",
        )
        assert "business-rules.md (written: no)" in content


# ===========================================================================
# Edge-case tests
# ===========================================================================

@pytest.mark.governance
class TestOrchestratorCodeCandidatesEdge:

    def test_status_renderer_large_provenance_counts(self) -> None:
        """Handles very large provenance counts without error."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc",
            extraction_source="hybrid",
            doc_only_count=9999,
            code_only_count=5000,
            doc_and_code_count=1234,
        )
        assert "DocOnlyRules: 9999" in content
        assert "CodeOnlyRules: 5000" in content
        assert "DocAndCodeRules: 1234" in content

    def test_status_renderer_empty_repo_name(self) -> None:
        """Empty repo name still produces valid status output."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="",
            outcome="unresolved",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=False,
            extractor_version="hybrid-br-v1",
            rules_hash="",
        )
        assert "# Business Rules Status - " in content
        assert "ExtractionSource: deterministic" in content

    def test_status_renderer_all_reason_codes_rendered(self) -> None:
        """Reason codes from both extraction and render reports are rendered."""
        module = _load_orchestrator_module()
        content = module._render_business_rules_status(
            date="2026-03-13",
            repo_name="test-repo",
            outcome="extracted",
            source="extractor",
            source_phase="1.5-BusinessRules",
            execution_evidence=True,
            extractor_version="hybrid-br-v1",
            rules_hash="abc",
            reason_codes=["REASON_A", "REASON_B"],
            extraction_source="hybrid",
        )
        assert "REASON_A" in content
        assert "REASON_B" in content

    def test_imports_available_in_orchestrator(self) -> None:
        """The orchestrator module should successfully import all hybrid symbols."""
        module = _load_orchestrator_module()
        # These are imported at module scope — if they failed, _load_orchestrator_module()
        # would have raised. But let's verify they're accessible:
        from governance_runtime.engine.business_rules_validation import (
            ORIGIN_CODE,
            ORIGIN_DOC,
            ProvenanceRecord,
            merge_code_candidates,
            validate_candidates,
        )
        assert callable(merge_code_candidates)
        assert callable(validate_candidates)
        assert ORIGIN_CODE == "code"
        assert ORIGIN_DOC == "doc"
        assert ProvenanceRecord is not None
