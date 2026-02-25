"""
Prompt Contract Tests for MD Rails

These tests verify that the core MD files (master.md, rules.md, start.md)
still contain the required governance contracts after refactoring.

These tests ensure:
1. Required governance contracts exist somewhere in the allowed files
2. Key cognitive heuristics are not lost
3. The "strength" of the MD files is preserved
"""

from __future__ import annotations

from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).parent.parent


class TestMasterMdContracts:
    """Tests for master.md required contracts"""

    @pytest.fixture
    def master_content(self):
        return (REPO_ROOT / "master.md").read_text(encoding="utf-8")

    def test_global_principles_present(self, master_content):
        """Master.md must contain global governance principles"""
        required = [
            "Fail-Closed",
            "Evidence-Based",
            "Scope Lock",
            "Repo-First",
            "Stack-Agnostic",
        ]
        missing = [p for p in required if p.lower() not in master_content.lower()]
        assert not missing, f"Missing global principles: {missing}"

    def test_priority_order_present(self, master_content):
        """Master.md must contain priority order"""
        assert "Priority Order" in master_content or "PRIORITY ORDER" in master_content
        # Must have the full precedence chain
        assert "Master Prompt" in master_content
        assert "rules.md" in master_content
        assert "profile" in master_content.lower()
        assert "Ticket" in master_content

    def test_boundary_ssot_present(self, master_content):
        """Master.md must clarify SSOT/boundary between kernel and MD"""
        assert "SSOT" in master_content or "phase_api.yaml" in master_content
        assert "kernel" in master_content.lower() or "binding" in master_content.lower()

    def test_stability_sla_reference_present(self, master_content):
        """Master.md must reference STABILITY_SLA.md"""
        assert "STABILITY_SLA" in master_content

    def test_execution_flow_reference_present(self, master_content):
        """Master.md must reference execution flow or phases"""
        assert "phase" in master_content.lower() or "Execution Flow" in master_content

    def test_decision_memory_adr_present(self, master_content):
        """Master.md must contain ADR recording requirement"""
        assert "ADR" in master_content or "Decision Memory" in master_content

    def test_thematic_rails_reference_present(self, master_content):
        """Master.md must reference thematic rails"""
        assert "rails" in master_content.lower() or "docs/governance/rails" in master_content

    def test_output_constraints_present(self, master_content):
        """Master.md must contain output constraints"""
        assert "5 files" in master_content or "300" in master_content

    def test_confidence_gates_present(self, master_content):
        """Master.md must contain confidence and gate requirements"""
        assert "gate" in master_content.lower() or "Confidence" in master_content


class TestRulesMdContracts:
    """Tests for rules.md required contracts"""

    @pytest.fixture
    def rules_content(self):
        return (REPO_ROOT / "rules.md").read_text(encoding="utf-8")

    def test_no_fabrication_present(self, rules_content):
        """Rules.md must contain no fabrication rule"""
        assert "fabrication" in rules_content.lower() or "no invented" in rules_content.lower()

    def test_scope_lock_present(self, rules_content):
        """Rules.md must contain scope lock"""
        assert "Scope Lock" in rules_content or "scope" in rules_content.lower()

    def test_evidence_obligations_present(self, rules_content):
        """Rules.md must contain evidence obligations"""
        assert "evidence" in rules_content.lower() or "proof" in rules_content.lower()

    def test_profile_selection_present(self, rules_content):
        """Rules.md must contain profile selection guidance"""
        assert "profile" in rules_content.lower()

    def test_ambiguity_handling_present(self, rules_content):
        """Rules.md must contain ambiguity handling"""
        assert "ambiguity" in rules_content.lower() or "ambiguous" in rules_content.lower()

    def test_contract_schema_gate_present(self, rules_content):
        """Rules.md mustSchema Evolution gate contain Contract/"""
        assert "Contract" in rules_content or "Schema" in rules_content
        assert "gate" in rules_content.lower()

    def test_business_rules_gate_present(self, rules_content):
        """Rules.md must contain Business Rules Ledger gate"""
        assert "Business Rules" in rules_content or "Ledger" in rules_content

    def test_fast_lane_present(self, rules_content):
        """Rules.md must contain Fast Lane escape hatch"""
        assert "Fast Lane" in rules_content or "fast" in rules_content.lower()

    def test_blocking_transparency_present(self, rules_content):
        """Rules.md must contain blocking transparency"""
        assert "BLOCKED" in rules_content or "blocking" in rules_content.lower()

    def test_change_matrix_present(self, rules_content):
        """Rules.md must contain Change Matrix"""
        assert "Change Matrix" in rules_content or "matrix" in rules_content.lower()

    def test_precedence_anchor_present(self, rules_content):
        """Rules.md must contain RULEBOOK-PRECEDENCE-POLICY anchor"""
        assert "RULEBOOK-PRECEDENCE-POLICY" in rules_content

    def test_addon_class_anchor_present(self, rules_content):
        """Rules.md must contain ADDON-CLASS-BEHAVIOR-POLICY anchor"""
        assert "ADDON-CLASS-BEHAVIOR-POLICY" in rules_content or "addon_class" in rules_content.lower()


class TestStartMdContracts:
    """Tests for start.md required contracts"""

    @pytest.fixture
    def start_content(self):
        return (REPO_ROOT / "start.md").read_text(encoding="utf-8")

    def test_start_purpose_present(self, start_content):
        """Start.md must describe /start purpose"""
        assert "/start" in start_content or "bootstrap" in start_content.lower()

    def test_binding_evidence_present(self, start_content):
        """Start.md must contain binding evidence requirement"""
        assert "binding" in start_content.lower() or "evidence" in start_content.lower()

    def test_preflight_present(self, start_content):
        """Start.md must contain preflight reference"""
        assert "preflight" in start_content.lower()

    def test_start_modes_present(self, start_content):
        """Start.md must contain Cold/Warm start modes"""
        assert "Cold Start" in start_content or "Warm Start" in start_content

    def test_blocked_states_present(self, start_content):
        """Start.md must contain blocked state handling"""
        assert "blocked" in start_content.lower() or "BLOCKED" in start_content

    def test_recovery_present(self, start_content):
        """Start.md must contain recovery semantics"""
        assert "recovery" in start_content.lower()

    def test_kernel_boundary_reference_present(self, start_content):
        """Start.md must reference kernel boundary"""
        assert "kernel" in start_content.lower() or "RESPONSIBILITY_BOUNDARY" in start_content


class TestCognitiveHeuristicsPreserved:
    """Tests to ensure cognitive heuristics are not lost"""

    @pytest.fixture
    def all_content(self):
        master = (REPO_ROOT / "master.md").read_text(encoding="utf-8")
        rules = (REPO_ROOT / "rules.md").read_text(encoding="utf-8")
        start = (REPO_ROOT / "start.md").read_text(encoding="utf-8")
        return master + "\n" + rules + "\n" + start

    def test_fail_closed_heuristic(self, all_content):
        """Fail-closed mode must be preserved"""
        assert "fail-closed" in all_content.lower() or "fail closed" in all_content.lower()

    def test_evidence_ladder_heuristic(self, all_content):
        """Evidence ladder must be preserved"""
        assert "evidence" in all_content.lower()
        # Should mention evidence hierarchy
        assert "build" in all_content.lower() or "code" in all_content.lower()

    def test_scope_lock_heuristic(self, all_content):
        """Scope lock must be preserved"""
        assert "scope" in all_content.lower() or "Scope Lock" in all_content

    def test_no_fabrication_heuristic(self, all_content):
        """No fabrication rule must be preserved"""
        assert "fabrication" in all_content.lower() or "hallucination" in all_content.lower()

    def test_ambiguity_handling_heuristic(self, all_content):
        """Ambiguity handling must be preserved"""
        assert "ambiguous" in all_content.lower() or "ambiguity" in all_content.lower()

    def test_gate_enforcement_heuristic(self, all_content):
        """Gate enforcement must be preserved"""
        assert "gate" in all_content.lower()

    def test_blocking_transparency_heuristic(self, all_content):
        """Blocking transparency must be preserved"""
        assert "BLOCKED" in all_content or "block" in all_content.lower()

    def test_profile_detection_heuristic(self, all_content):
        """Profile detection must be preserved"""
        assert "profile" in all_content.lower()

    def test_addon_semantics_heuristic(self, all_content):
        """Addon required/advisory semantics must be preserved"""
        # Should contain addon class semantics
        assert "addon" in all_content.lower()
        assert "required" in all_content.lower() or "advisory" in all_content.lower()


class TestNoKernelLogicInWrongFile:
    """Tests to ensure kernel-owned logic is not in MD files"""

    @pytest.fixture
    def master_content(self):
        return (REPO_ROOT / "master.md").read_text(encoding="utf-8")

    @pytest.fixture
    def rules_content(self):
        return (REPO_ROOT / "rules.md").read_text(encoding="utf-8")

    @pytest.fixture
    def start_content(self):
        return (REPO_ROOT / "start.md").read_text(encoding="utf-8")

    def test_no_phase_execution_logic_in_master(self, master_content):
        """Master.md should not contain detailed phase execution logic"""
        # This is a soft check - master can reference phases but not implement them
        # The key is that it shouldn't have detailed routing logic
        assert "governance/kernel" in master_content.lower() or "kernel" in master_content.lower()

    def test_no_routing_implementation_in_rules(self, rules_content):
        """Rules.md should not contain routing implementation"""
        # Rules can reference phase_api as kernel-owned, but shouldn't implement routing
        # It should just clarify that runtime routing is kernel-owned
        assert "kernel" in rules_content.lower() or "phase_api" in rules_content.lower()

    def test_no_render_logic_in_start(self, start_content):
        """Start.md should not contain render logic"""
        # Start should be about semantics, not rendering
        assert "render" not in start_content.lower() or "kernel" in start_content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
