"""Phase 1: Spec Inventory Tests

Validiert die aktuelle phase_api.yaml Struktur und identifiziert:
- Tote Referenzen (ungültige Token-Targets)
- Ungültige Ziel-States
- Fehlende Startzustände
- Doppelte State-IDs
- Phase 6 Monolith-Struktur (vor Zerlegung)

Diese Tests laufen GEGEN die aktuelle Spec (phase_api.yaml),
nicht gegen die zukünftige V2-Struktur.

Note: This is INVENTORY of the current state (Ist-Zustand).
Some fields (like /implement in 6.presentation) represent the current
behavior which may differ from the frozen Zielarchitektur (ADR-003).
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path


def _find_spec_path() -> Path | None:
    """Find phase_api.yaml relative to test file location.
    
    Returns None if not found - caller should handle the case.
    """
    current = Path(__file__).resolve()
    # Search upward from test file location
    for parent in current.parents:
        candidate = parent / "governance_spec" / "phase_api.yaml"
        if candidate.exists():
            return candidate
    return None


@pytest.fixture
def spec_path():
    """Provides the spec path, skipping test if not found."""
    path = _find_spec_path()
    if path is None:
        pytest.skip("phase_api.yaml not found - test requires spec file")
    return path


@pytest.fixture
def phase_api_spec(spec_path):
    """Lädt die aktuelle phase_api.yaml für Inventory-Tests."""
    with open(spec_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.governance
class TestSpecStructure:
    """Grundlegende Spec-Struktur."""

    def test_spec_loads_successfully(self, phase_api_spec):
        """Happy: Spec lädt erfolgreich."""
        assert "phases" in phase_api_spec
        assert "start_token" in phase_api_spec
        assert isinstance(phase_api_spec["phases"], list)
        assert len(phase_api_spec["phases"]) > 0

    def test_start_token_exists(self, phase_api_spec):
        """Happy: Startzustand existiert."""
        token_ids = {p["token"] for p in phase_api_spec["phases"]}
        assert phase_api_spec["start_token"] in token_ids

    def test_all_tokens_unique(self, phase_api_spec):
        """Happy: Alle State-IDs sind eindeutig."""
        token_ids = [p["token"] for p in phase_api_spec["phases"]]
        assert len(token_ids) == len(set(token_ids)), \
            f"Duplicate tokens: {[t for t in token_ids if token_ids.count(t) > 1]}"


@pytest.mark.governance
class TestTransitionIntegrity:
    """Transition-Referenzen."""

    def test_all_transition_targets_exist(self, phase_api_spec):
        """Happy: Alle Transition-Ziele existieren."""
        token_ids = {p["token"] for p in phase_api_spec["phases"]}
        errors = []
        for phase in phase_api_spec["phases"]:
            for t in phase.get("transitions", []):
                if t["next"] not in token_ids:
                    errors.append(f"{phase['token']} -> {t['next']}")
        assert not errors, f"Invalid transition targets: {errors}"

    def test_default_next_exists(self, phase_api_spec):
        """Happy: Alle default next tokens existieren."""
        token_ids = {p["token"] for p in phase_api_spec["phases"]}
        errors = []
        for phase in phase_api_spec["phases"]:
            if "next" in phase and phase["next"] not in token_ids:
                errors.append(f"{phase['token']} next -> {phase['next']}")
        assert not errors, f"Invalid default next: {errors}"

    def test_all_when_conditions_have_handler(self, phase_api_spec):
        """Happy: Jede when-Bedingung ist im Kernel bekannt."""
        known_conditions = {
            "default",
            "ticket_present",
            "ticket_or_task_recorded",
            "business_rules_execute",
            "no_apis",
            "plan_record_missing",
            "self_review_iterations_pending",
            "self_review_iterations_met",
            "business_rules_gate_required",
            "technical_debt_proposed",
            "rollback_required",
            "implementation_accepted",
            "implementation_blocked",
            "implementation_rework_clarification_pending",
            "implementation_presentation_ready",
            "implementation_execution_in_progress",
            "implementation_started",
            "workflow_approved",
            "review_changes_requested",
            "rework_clarification_pending",
            "review_rejected",
            "implementation_review_pending",
            "implementation_review_complete",
        }
        unknown = set()
        for phase in phase_api_spec["phases"]:
            for t in phase.get("transitions", []):
                when = t.get("when", "")
                if when and when not in known_conditions:
                    unknown.add(when)
        assert not unknown, f"Unknown when conditions: {unknown}"


@pytest.mark.governance
class TestPhase6Monolith:
    """Phase 6 Monolith-Struktur (vor Zerlegung)."""

    def test_phase6_exists(self, phase_api_spec):
        """Happy: Phase 6 Token existiert."""
        token_ids = {p["token"] for p in phase_api_spec["phases"]}
        assert "6" in token_ids

    def test_phase6_is_stay(self, phase_api_spec):
        """Phase 6 hat route_strategy 'stay'."""
        phase6 = next(p for p in phase_api_spec["phases"] if p["token"] == "6")
        assert phase6.get("route_strategy") == "stay"

    def test_phase6_has_many_transitions(self, phase_api_spec):
        """Corner: Phase 6 hat viele Self-Transitions (monolithisch)."""
        phase6 = next(p for p in phase_api_spec["phases"] if p["token"] == "6")
        transitions = phase6.get("transitions", [])
        assert len(transitions) >= 10, \
            f"Expected 10+ transitions for Phase 6, got {len(transitions)}"

    def test_phase6_self_transitions_target_itself(self, phase_api_spec):
        """Happy: Phase 6 Self-Transitions zielen auf '6' oder '4' (rejection)."""
        phase6 = next(p for p in phase_api_spec["phases"] if p["token"] == "6")
        valid_targets = {"6", "4"}  # 4 = rejection path to Phase 4
        for t in phase6.get("transitions", []):
            assert t["next"] in valid_targets, \
                f"Phase 6 transition {t['source']} targets {t['next']}, expected one of {valid_targets}"

    def test_phase6_identifies_implicit_substates(self, phase_api_spec):
        """Edge: Phase 6 aktive_gate-Werte sind implizite Substates."""
        phase6 = next(p for p in phase_api_spec["phases"] if p["token"] == "6")
        gates = set()
        for t in phase6.get("transitions", []):
            if "active_gate" in t:
                gates.add(t["active_gate"])
        
        # Mindestens die bekannten Substates sollten vorhanden sein
        expected_gates = {
            "Evidence Presentation Gate",
            "Implementation Internal Review",
            "Implementation Execution In Progress",
        }
        found = expected_gates & gates
        assert len(found) >= 2, \
            f"Expected at least 2 of {expected_gates}, found: {gates}"


@pytest.mark.governance
class TestGuardReferences:
    """Guard-Referenzen (aktueller Stand)."""

    def test_exit_required_keys_are_lists(self, phase_api_spec):
        """Happy: exit_required_keys sind Listen."""
        for phase in phase_api_spec["phases"]:
            keys = phase.get("exit_required_keys", [])
            if keys:
                assert isinstance(keys, list), \
                    f"Phase {phase['token']}: exit_required_keys is not a list"

    def test_exit_required_keys_non_empty_strings(self, phase_api_spec):
        """Happy: exit_required_keys sind nicht-leere Strings."""
        for phase in phase_api_spec["phases"]:
            for key in phase.get("exit_required_keys", []):
                assert isinstance(key, str) and key.strip(), \
                    f"Phase {phase['token']}: invalid exit_required_key '{key}'"


@pytest.mark.governance  
class TestOutputPolicy:
    """Output-Policy (Phase 5)."""

    def test_phase5_has_output_policy(self, phase_api_spec):
        """Happy: Phase 5 hat output_policy."""
        phase5 = next((p for p in phase_api_spec["phases"] if p["token"] == "5"), None)
        assert phase5 is not None, "Phase 5 not found"
        assert "output_policy" in phase5, "Phase 5 missing output_policy"

    def test_output_policy_has_allowed_classes(self, phase_api_spec):
        """Happy: Output-Policy definiert allowed_output_classes."""
        phase5 = next(p for p in phase_api_spec["phases"] if p["token"] == "5")
        policy = phase5["output_policy"]
        assert "allowed_output_classes" in policy
        assert isinstance(policy["allowed_output_classes"], list)
        assert len(policy["allowed_output_classes"]) > 0

    def test_output_policy_has_forbidden_classes(self, phase_api_spec):
        """Happy: Output-Policy definiert forbidden_output_classes."""
        phase5 = next(p for p in phase_api_spec["phases"] if p["token"] == "5")
        policy = phase5["output_policy"]
        assert "forbidden_output_classes" in policy
        assert "implementation" in policy["forbidden_output_classes"]
        assert "code_delivery" in policy["forbidden_output_classes"]


@pytest.mark.governance
class TestCommandReferences:
    """Command-Referenzen in der Spec."""

    def test_phase4_references_review_as_readonly(self, phase_api_spec):
        """Happy: Phase 4 erwähnt /review als Read-only."""
        phase4 = next(p for p in phase_api_spec["phases"] if p["token"] == "4")
        conditions = phase4.get("next_gate_condition", "")
        assert "/review" in conditions
        assert "read-only" in conditions.lower() or "no state change" in conditions.lower()

    def test_phase6_evidence_gate_references_review_decision(self, phase_api_spec):
        """Happy: Evidence Gate erwähnt /review-decision."""
        phase6 = next(p for p in phase_api_spec["phases"] if p["token"] == "6")
        evidence_transition = next(
            (t for t in phase6.get("transitions", [])
             if t.get("when") == "implementation_review_complete"),
            None
        )
        assert evidence_transition is not None
        assert "/review-decision" in evidence_transition.get("next_gate_condition", "")
