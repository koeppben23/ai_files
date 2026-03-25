"""Phase 4: Command Policy Tests (v3 - Deterministic /continue, no constraints)

Validiert die extrahierte command_policy.yaml Struktur:
- Command→Event Mapping ist explizit und deterministisch
- /continue hat determinism-Kontrakt
- Keine constraints/textuelle Neben-Semantik
- Output Policies haben stabile IDs
- Phase Output Policy Map hat Integrität
- Terminal/Blocked State Regeln
- Cross-Spec Konsistenz mit Topologie

Diese Tests laufen GEGEN die extrahierte command_policy.yaml.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from typing import Any


# ============================================================================
# Valid Types and Schemas
# ============================================================================

VALID_COMMAND_BEHAVIOR_TYPES = {
    "advance_routing",
    "review_readonly",
    "persist_evidence",
    "start_implementation",
    "resume_implementation",
    "submit_review_decision",
}

VALID_OUTPUT_CLASSES = {
    "plan", "review", "risk_analysis", "test_strategy", "gate_check",
    "rollback_plan", "review_questions", "consolidated_review_plan",
    "implementation", "patch", "diff", "code_delivery",
}

# Runtime fields for command objects (closed schema, NO constraints)
RUNTIME_COMMAND_FIELDS = {
    "id", "command", "allowed_in", "mutating", "behavior", "produces_events"
}

# Only description is allowed as non-runtime field
NON_RUNTIME_FIELDS = {"description"}


# ============================================================================
# Fixtures
# ============================================================================

def _find_command_policy_path() -> Path | None:
    """Find command_policy.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "command_policy.yaml"
        if candidate.exists():
            return candidate
    return None


def _find_topology_path() -> Path | None:
    """Find topology.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "topology.yaml"
        if candidate.exists():
            return candidate
    return None


@pytest.fixture
def command_policy_path():
    """Provides the command_policy path, skipping test if not found."""
    path = _find_command_policy_path()
    if path is None:
        pytest.skip("command_policy.yaml not found - test requires file")
    return path


@pytest.fixture
def command_policy(command_policy_path):
    """Lädt die command_policy.yaml für Struktur-Tests."""
    with open(command_policy_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def commands(command_policy):
    """Extract all commands."""
    return command_policy.get("commands", [])


@pytest.fixture
def output_policies(command_policy):
    """Extract all output policies."""
    return command_policy.get("output_policies", [])


@pytest.fixture
def command_restrictions(command_policy):
    """Extract command restrictions."""
    return command_policy.get("command_restrictions", [])


@pytest.fixture
def phase_output_policy_map(command_policy):
    """Extract phase output policy map."""
    return command_policy.get("phase_output_policy_map", [])


@pytest.fixture
def command_ids(commands):
    """Extract all command IDs."""
    return {c["id"] for c in commands}


@pytest.fixture
def command_names(commands):
    """Extract all command names."""
    return {c["command"] for c in commands}


@pytest.fixture
def output_policy_ids(output_policies):
    """Extract all output policy IDs."""
    return {p["id"] for p in output_policies}


# ============================================================================
# Test Classes
# ============================================================================

@pytest.mark.governance
class TestCommandPolicyStructure:
    """Grundlegende Command Policy Struktur."""

    def test_command_policy_loads_successfully(self, command_policy):
        """Happy: Command Policy lädt erfolgreich."""
        assert "version" in command_policy
        assert "schema" in command_policy
        assert "commands" in command_policy
        assert isinstance(command_policy["commands"], list)

    def test_schema_is_command_policy_v1(self, command_policy):
        """Happy: Schema ist opencode.command_policy.v1."""
        assert command_policy["schema"] == "opencode.command_policy.v1"

    def test_has_commands(self, command_policy):
        """Happy: Commands vorhanden."""
        assert len(command_policy["commands"]) > 0


@pytest.mark.governance
class TestCommands:
    """Command Definitionen."""

    def test_commands_have_id(self, commands):
        """Runtime: Alle Commands haben ID."""
        for cmd in commands:
            assert "id" in cmd, f"Command missing 'id'"
            assert isinstance(cmd["id"], str), f"Command id must be string"
            assert cmd["id"].startswith("cmd_"), \
                f"Command ID should start with 'cmd_'"

    def test_commands_have_command_name(self, commands):
        """Runtime: Alle Commands haben command name."""
        for cmd in commands:
            assert "command" in cmd, f"Command {cmd.get('id')} missing 'command'"
            assert isinstance(cmd["command"], str), f"Command name must be string"
            assert cmd["command"].startswith("/"), \
                f"Command name should start with '/'"

    def test_commands_have_allowed_in(self, commands):
        """Runtime: Alle Commands haben allowed_in."""
        for cmd in commands:
            assert "allowed_in" in cmd, f"Command {cmd.get('id')} missing 'allowed_in'"
            allowed = cmd["allowed_in"]
            assert allowed == "*" or isinstance(allowed, list), \
                f"Command {cmd.get('id')}: allowed_in must be '*' or list"

    def test_commands_have_mutating_flag(self, commands):
        """Runtime: Alle Commands haben mutating flag."""
        for cmd in commands:
            assert "mutating" in cmd, f"Command {cmd.get('id')} missing 'mutating'"
            assert isinstance(cmd["mutating"], bool), \
                f"Command {cmd.get('id')}: mutating must be boolean"

    def test_commands_have_behavior(self, commands):
        """Runtime: Alle Commands haben behavior."""
        for cmd in commands:
            assert "behavior" in cmd, f"Command {cmd.get('id')} missing 'behavior'"
            assert isinstance(cmd["behavior"], dict), \
                f"Command {cmd.get('id')}: behavior must be dict"
            assert "type" in cmd["behavior"], \
                f"Command {cmd.get('id')}: behavior missing 'type'"
            assert cmd["behavior"]["type"] in VALID_COMMAND_BEHAVIOR_TYPES, \
                f"Command {cmd.get('id')}: unknown behavior type '{cmd['behavior']['type']}'"

    def test_commands_have_produces_events(self, commands):
        """Runtime: Alle Commands haben produces_events."""
        for cmd in commands:
            assert "produces_events" in cmd, \
                f"Command {cmd.get('id')}: missing 'produces_events'"

    def test_command_ids_unique(self, commands):
        """Runtime: Command IDs sind eindeutig."""
        ids = [c["id"] for c in commands]
        duplicates = [cid for cid in ids if ids.count(cid) > 1]
        assert not duplicates, f"Duplicate command IDs: {set(duplicates)}"

    def test_command_names_unique(self, commands):
        """Runtime: Command Names sind eindeutig."""
        names = [c["command"] for c in commands]
        duplicates = [n for n in names if names.count(n) > 1]
        assert not duplicates, f"Duplicate command names: {set(duplicates)}"


@pytest.mark.governance
class TestCommandNoConstraints:
    """Keine constraints/textuelle Neben-Semantik in Command-Objekten."""

    def test_no_constraints_field(self, commands):
        """Runtime: Commands haben KEIN constraints-Feld."""
        for cmd in commands:
            assert "constraints" not in cmd, \
                f"Command {cmd.get('id')}: 'constraints' field is forbidden - " \
                f"all behavioral rules must be in guards, not text"

    def test_no_unknown_fields(self, commands):
        """Runtime: Command-Objekte haben keine unbekannten Felder."""
        for cmd in commands:
            all_fields = set(cmd.keys())
            allowed = RUNTIME_COMMAND_FIELDS | NON_RUNTIME_FIELDS
            unknown = all_fields - allowed
            assert not unknown, \
                f"Command {cmd.get('id')}: unknown fields {unknown} - " \
                f"only {allowed} are allowed"


@pytest.mark.governance
class TestContinueDeterminism:
    """/continue determinism contract."""

    def test_continue_has_determinism_in_behavior(self, commands):
        """Runtime: /continue hat determinism-Kontrakt."""
        continue_cmd = next(
            (c for c in commands if c["command"] == "/continue"),
            None
        )
        assert continue_cmd is not None, "Missing /continue command"
        assert "determinism" in continue_cmd["behavior"], \
            "/continue must specify determinism contract in behavior"
        assert continue_cmd["behavior"]["determinism"] == "exactly_one_guard_per_state", \
            "/continue determinism must be 'exactly_one_guard_per_state'"

    def test_continue_produces_via_guards(self, commands):
        """Runtime: /continue produces_events via guards."""
        continue_cmd = next(
            (c for c in commands if c["command"] == "/continue"),
            None
        )
        assert continue_cmd is not None
        # /continue uses special marker for guard-determined events
        produces = continue_cmd.get("produces_events")
        assert produces == "*_via_guards", \
            f"/continue produces_events should be '*_via_guards', got {produces}"

    def test_continue_is_mutating(self, commands):
        """Runtime: /continue ist mutierend (ändert State via Guard-Evaluation)."""
        continue_cmd = next(
            (c for c in commands if c["command"] == "/continue"),
            None
        )
        assert continue_cmd is not None
        assert continue_cmd["mutating"] is True, \
            "/continue must be mutating (it advances state via guards)"


@pytest.mark.governance
class TestReviewUniversalJustification:
    """Universelle read-only Commands mit expliziter Begründung."""

    def test_review_is_universal(self, commands):
        """Runtime: /review ist global erlaubt."""
        review_cmd = next(
            (c for c in commands if c["command"] == "/review"),
            None
        )
        assert review_cmd is not None
        assert review_cmd["allowed_in"] == "*", \
            "/review should be universally allowed"

    def test_review_is_readonly(self, commands):
        """Runtime: /review ist read-only."""
        review_cmd = next(
            (c for c in commands if c["command"] == "/review"),
            None
        )
        assert review_cmd is not None
        assert review_cmd["mutating"] is False, \
            "/review must be read-only (mutating: false)"

    def test_review_produces_no_events(self, commands):
        """Runtime: /review produziert keine State-Events."""
        review_cmd = next(
            (c for c in commands if c["command"] == "/review"),
            None
        )
        assert review_cmd is not None
        events = review_cmd.get("produces_events", [])
        assert events == [], \
            f"/review should produce no events, got {events}"


@pytest.mark.governance
class TestCommandEventMapping:
    """Command→Event Mapping (ADR-004)."""

    def test_implement_produces_expected_events(self, commands):
        """Runtime: /implement produces expected events."""
        implement = next(
            (c for c in commands if c["command"] == "/implement"),
            None
        )
        assert implement is not None
        events = set(implement.get("produces_events", []))
        expected = {"implementation_started", "implementation_execution_in_progress"}
        assert events == expected, \
            f"/implement should produce {expected}, got {events}"

    def test_review_decision_produces_expected_events(self, commands):
        """Runtime: /review-decision produces expected events."""
        review_decision = next(
            (c for c in commands if c["command"] == "/review-decision"),
            None
        )
        assert review_decision is not None
        events = set(review_decision.get("produces_events", []))
        expected = {"workflow_approved", "review_changes_requested", "review_rejected"}
        assert events == expected, \
            f"/review-decision should produce {expected}, got {events}"

    def test_review_decision_has_workflow_scope(self, commands):
        """Runtime: /review-decision hat decision_scope: workflow."""
        review_decision = next(
            (c for c in commands if c["command"] == "/review-decision"),
            None
        )
        assert review_decision is not None
        behavior = review_decision.get("behavior", {})
        assert behavior.get("decision_scope") == "workflow", \
            "/review-decision must have decision_scope: workflow"

    def test_implementation_decision_is_alias(self, commands):
        """Runtime: /implementation-decision ist Alias für /review-decision."""
        impl_decision = next(
            (c for c in commands if c["command"] == "/implementation-decision"),
            None
        )
        assert impl_decision is not None
        behavior = impl_decision.get("behavior", {})
        assert behavior.get("alias_of") == "cmd_review_decision", \
            "/implementation-decision should have alias_of: cmd_review_decision"
        # Same events as /review-decision
        events = set(impl_decision.get("produces_events", []))
        expected = {"workflow_approved", "review_changes_requested", "review_rejected"}
        assert events == expected


@pytest.mark.governance
class TestViaGuardsContract:
    """*_via_guards is a special marker - only /continue may use it."""

    def test_only_continue_uses_via_guards(self, commands):
        """Runtime: Nur /continue darf *_via_guards verwenden."""
        for cmd in commands:
            produces = cmd.get("produces_events")
            if produces == "*_via_guards":
                assert cmd["command"] == "/continue", \
                    f"Command {cmd['id']}: only /continue may use '*_via_guards', " \
                    f"other commands must have explicit event list or []"

    def test_via_guards_is_string(self, commands):
        """Runtime: *_via_guards ist exakt der String-Wert."""
        continue_cmd = next(
            (c for c in commands if c["command"] == "/continue"),
            None
        )
        assert continue_cmd is not None
        produces = continue_cmd.get("produces_events")
        assert isinstance(produces, str), \
            f"*_via_guards must be a string, got {type(produces)}"
        assert produces == "*_via_guards", \
            f"Expected exactly '*_via_guards', got '{produces}'"

    def test_non_continue_produces_events_is_list_or_empty(self, commands):
        """Runtime: Nicht-/continue Commands haben List oder [] für produces_events."""
        for cmd in commands:
            if cmd["command"] == "/continue":
                continue  # Skip /continue, it uses special marker
            produces = cmd.get("produces_events")
            assert isinstance(produces, list), \
                f"Command {cmd['id']}: produces_events must be list (not '{produces}'), " \
                f"except /continue which uses '*_via_guards'"


@pytest.mark.governance
class TestOutputPolicies:
    """Output Policy Definitionen mit stabilen IDs."""

    def test_output_policies_have_stable_id(self, output_policies):
        """Runtime: Alle Output Policies haben stabile ID."""
        for policy in output_policies:
            assert "id" in policy, f"Output policy missing 'id'"
            assert policy["id"].startswith("op."), \
                f"Output policy ID should start with 'op.'"

    def test_output_policies_have_state_id(self, output_policies):
        """Runtime: Alle Output Policies haben state_id."""
        for policy in output_policies:
            assert "state_id" in policy

    def test_output_policy_ids_unique(self, output_policies):
        """Runtime: Output Policy IDs sind eindeutig."""
        ids = [p["id"] for p in output_policies]
        duplicates = [pid for pid in ids if ids.count(pid) > 1]
        assert not duplicates, f"Duplicate output policy IDs: {set(duplicates)}"

    def test_output_classes_are_known(self, output_policies):
        """Runtime: Output Classes sind bekannte Werte."""
        for policy in output_policies:
            for cls in policy.get("allowed_output_classes", []):
                assert cls in VALID_OUTPUT_CLASSES, \
                    f"Output policy {policy.get('id')}: unknown allowed class '{cls}'"
            for cls in policy.get("forbidden_output_classes", []):
                assert cls in VALID_OUTPUT_CLASSES, \
                    f"Output policy {policy.get('id')}: unknown forbidden class '{cls}'"

    def test_no_overlap_allowed_forbidden(self, output_policies):
        """Runtime: Allowed und Forbidden haben keine Überschneidung."""
        for policy in output_policies:
            allowed = set(policy.get("allowed_output_classes", []))
            forbidden = set(policy.get("forbidden_output_classes", []))
            overlap = allowed & forbidden
            assert not overlap, f"Output policy {policy.get('id')}: overlap {overlap}"


@pytest.mark.governance
class TestPhaseOutputPolicyMap:
    """Phase Output Policy Mapping mit Integrität."""

    def test_phase_output_policy_map_exists(self, command_policy):
        """Runtime: Phase Output Policy Map existiert."""
        assert "phase_output_policy_map" in command_policy
        assert len(command_policy["phase_output_policy_map"]) > 0

    def test_output_policy_ref_uses_stable_id(self, phase_output_policy_map, output_policy_ids):
        """Runtime: output_policy_ref verwendet stabile ID."""
        for entry in phase_output_policy_map:
            ref = entry["output_policy_ref"]
            assert not ref.startswith("output_policies["), \
                f"Map entry {entry['state_id']}: ref '{ref}' is index-based"
            assert ref in output_policy_ids, \
                f"Map entry {entry['state_id']}: ref '{ref}' not found"

    def test_no_duplicate_state_mapping(self, phase_output_policy_map):
        """Runtime: Kein State ist doppelt gemappt."""
        state_ids = [e["state_id"] for e in phase_output_policy_map]
        duplicates = [sid for sid in state_ids if state_ids.count(sid) > 1]
        assert not duplicates, f"Duplicate state mapping: {set(duplicates)}"

    def test_no_orphaned_policies(self, output_policy_ids, phase_output_policy_map):
        """Runtime: Alle Policies sind gemappt."""
        mapped_refs = {e["output_policy_ref"] for e in phase_output_policy_map}
        orphaned = output_policy_ids - mapped_refs
        assert not orphaned, f"Orphaned output policies: {orphaned}"


@pytest.mark.governance
class TestCommandRestrictions:
    """Command Restriction Rules für Terminal/Blocked States."""

    def test_command_restrictions_exist(self, command_policy):
        """Runtime: Command Restrictions existieren."""
        assert "command_restrictions" in command_policy, \
            "command_policy.yaml must have command_restrictions"
        assert isinstance(command_policy["command_restrictions"], list)
        assert len(command_policy["command_restrictions"]) > 0

    def test_restrictions_have_state_pattern(self, command_restrictions):
        """Runtime: Restrictions haben state_pattern."""
        for restriction in command_restrictions:
            assert "state_pattern" in restriction, \
                f"Restriction missing 'state_pattern'"
            assert isinstance(restriction["state_pattern"], str)

    def test_restrictions_have_blocked_items(self, command_restrictions):
        """Runtime: Restrictions haben blocked Commands oder Types."""
        for restriction in command_restrictions:
            has_blocked = (
                "blocked_commands" in restriction or 
                "blocked_command_types" in restriction
            )
            assert has_blocked, \
                f"Restriction {restriction.get('state_pattern')}: " \
                f"must have blocked_commands or blocked_command_types"

    def test_restrictions_have_reason(self, command_restrictions):
        """Runtime: Restrictions haben reason (documentation)."""
        for restriction in command_restrictions:
            assert "reason" in restriction, \
                f"Restriction {restriction.get('state_pattern')}: missing reason"


@pytest.mark.governance
class TestCommandTopologyConsistency:
    """Konsistenz zwischen Commands und Topologie."""

    def test_universal_commands_exist(self, command_names):
        """Happy: Universal commands existieren."""
        assert "/continue" in command_names
        assert "/review" in command_names

    def test_command_count(self, commands):
        """Happy: Command count is correct (8 commands with /retry_implementation)."""
        assert len(commands) == 8, f"Expected 8 commands, got {len(commands)}"

    def test_command_allowed_states_match_topology(self, commands):
        """Happy: Command erlaubte States existieren in Topologie (oder sind future states)."""
        topo_path = _find_topology_path()
        if topo_path is None:
            pytest.skip("topology.yaml not found")
        
        with open(topo_path, encoding="utf-8") as f:
            topology = yaml.safe_load(f)
        
        state_ids = {s["id"] for s in topology["states"]}
        
        # Future states from ADR-003 (will be created in Phase 6 zerlegung)
        future_states = {"6.approved", "6.presentation", "6.execution", 
                         "6.internal_review", "6.blocked", "6.rework", 
                         "6.rejected", "6.complete"}
        
        for cmd in commands:
            allowed = cmd.get("allowed_in")
            if allowed == "*":
                continue
            for state_id in allowed:
                if state_id in future_states:
                    # Future state - will exist after Phase 6 zerlegung
                    continue
                assert state_id in state_ids, \
                    f"Command {cmd['id']}: state '{state_id}' not in topology"
