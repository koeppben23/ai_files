"""
MD Rails Coverage Tests

This test suite verifies that MD files maintain required governance contracts
after refactoring. It is designed to work with the reduced MD scope where
output presentation details have been moved to the kernel/render layer.
"""

from __future__ import annotations

from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).parent.parent


class TestMasterMdContracts:
    """Tests for master.md expected contracts"""

    @pytest.fixture
    def master_content(self):
        return (REPO_ROOT / "master.md").read_text(encoding="utf-8")

    def test_global_principles_present(self, master_content):
        """Master.md must contain global governance principles"""
        # Core principles that should exist
        required = ["Fail-Closed", "Evidence-Based", "Scope Lock", "Repo-First"]
        missing = [p for p in required if p.lower() not in master_content.lower()]
        assert not missing, f"Missing global principles: {missing}"

    def test_priority_order_present(self, master_content):
        """Master.md must contain priority order"""
        assert "Priority Order" in master_content or "PRIORITY ORDER" in master_content
        assert "Master Prompt" in master_content
        assert "rules.md" in master_content

    def test_boundary_ssot_present(self, master_content):
        """Master.md must clarify SSOT/boundary"""
        assert "SSOT" in master_content or "phase_api.yaml" in master_content

    def test_stability_sla_reference_present(self, master_content):
        """Master.md must reference STABILITY_SLA.md"""
        assert "STABILITY_SLA" in master_content


class TestRulesMdContracts:
    """Tests for rules.md expected contracts"""

    @pytest.fixture
    def rules_content(self):
        return (REPO_ROOT / "rules.md").read_text(encoding="utf-8")

    def test_no_fabrication_present(self, rules_content):
        """Rules.md must contain no fabrication rule"""
        assert "fabrication" in rules_content.lower() or "no invented" in rules_content.lower()

    def test_scope_lock_present(self, rules_content):
        """Rules.md must contain scope lock"""
        assert "scope" in rules_content.lower()

    def test_evidence_obligations_present(self, rules_content):
        """Rules.md must contain evidence obligations"""
        assert "evidence" in rules_content.lower()

    def test_profile_selection_present(self, rules_content):
        """Rules.md must contain profile selection guidance"""
        assert "profile" in rules_content.lower()

    def test_blocking_transparency_present(self, rules_content):
        """Rules.md must contain blocking transparency"""
        assert "BLOCKED" in rules_content or "blocking" in rules_content.lower()


class TestStartMdContracts:
    """Tests for start.md expected contracts"""

    @pytest.fixture
    def start_content(self):
        return (REPO_ROOT / "start.md").read_text(encoding="utf-8")

    def test_start_purpose_present(self, start_content):
        """Start.md must describe /start purpose"""
        assert "/start" in start_content or "bootstrap" in start_content.lower()

    def test_binding_evidence_present(self, start_content):
        """Start.md must contain binding evidence requirement"""
        assert "binding" in start_content.lower() or "evidence" in start_content.lower()

    def test_start_modes_present(self, start_content):
        """Start.md must contain Cold/Warm start modes"""
        assert "Cold Start" in start_content or "Warm Start" in start_content

    def test_blocked_states_present(self, start_content):
        """Start.md must contain blocked state handling"""
        assert "blocked" in start_content.lower() or "BLOCKED" in start_content


class TestCognitiveHeuristics:
    """Tests to ensure cognitive heuristics are preserved"""

    @pytest.fixture
    def all_content(self):
        master = (REPO_ROOT / "master.md").read_text(encoding="utf-8")
        rules = (REPO_ROOT / "rules.md").read_text(encoding="utf-8")
        start = (REPO_ROOT / "start.md").read_text(encoding="utf-8")
        return master + "\n" + rules + "\n" + start

    def test_fail_closed_heuristic(self, all_content):
        """Fail-closed mode must be preserved"""
        assert "fail-closed" in all_content.lower() or "fail closed" in all_content.lower()

    def test_evidence_heuristic(self, all_content):
        """Evidence-based reasoning must be preserved"""
        assert "evidence" in all_content.lower()

    def test_scope_lock_heuristic(self, all_content):
        """Scope lock must be preserved"""
        assert "scope" in all_content.lower()

    def test_no_fabrication_heuristic(self, all_content):
        """No fabrication rule must be preserved"""
        assert "fabrication" in all_content.lower() or "hallucination" in all_content.lower()

    def test_gate_enforcement_heuristic(self, all_content):
        """Gate enforcement must be preserved"""
        assert "gate" in all_content.lower()


class TestNoKernelLogicInWrongFile:
    """Tests to ensure kernel-owned logic is not in MD files"""

    @pytest.fixture
    def master_content(self):
        return (REPO_ROOT / "master.md").read_text(encoding="utf-8")

    def test_references_kernel_boundary(self, master_content):
        """Master.md should reference kernel boundary"""
        assert "kernel" in master_content.lower() or "phase_api" in master_content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
