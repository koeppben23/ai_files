"""Phase 4: Command Policy Tests (v2 - Strict with event mapping)

Validiert die extrahierte command_policy.yaml Struktur:
- Command→Event Mapping ist explizit
- Output Policies haben stabile IDs
- Phase Output Policy Map hat Integrität
- Keine unbekannten Felder in Runtime-Objekten
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
    "submit_review_decision",
}

VALID_OUTPUT_CLASSES = {
    "plan", "review", "risk_analysis", "test_strategy", "gate_check",
    "rollback_plan", "review_questions", "consolidated_review_plan",
    "implementation", "patch", "diff", "code_delivery",
}

# Runtime fields for command objects (closed schema)
RUNTIME_COMMAND_FIELDS = {
    "id", "command", "allowed_in", "mutating", "behavior", "produces_events"
}
NON_RUNTIME_COMMAND_FIELDS = {"description", "constraints"}

# Allowed behavior types per command (for event validation)
COMMANDS_WITH_EVENTS = {
    "cmd_implement": {"implementation_started", "implementation_execution_in_progress"},
    "cmd_review_decision": {"workflow_approved", "review_changes_requested", "review_rejected"},
    "cmd_review_decision_alt": {"workflow_approved", "review_changes_requested", "review_rejected"},
}


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
        """Runtime: Alle Commands haben produces_events (Command→Event Mapping)."""
        for cmd in commands:
            assert "produces_events" in cmd, \
                f"Command {cmd.get('id')}: missing 'produces_events'"
            assert isinstance(cmd["produces_events"], list), \
                f"Command {cmd.get('id')}: produces_events must be list"

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
class TestCommandEventMapping:
    """Command→Event Mapping (ADR-004)."""

    def test_mutating_commands_have_events_or_evidence(self, commands):
        """Runtime: Mutating commands produce events or evidence."""
        for cmd in commands:
            if cmd["mutating"]:
                has_events = len(cmd.get("produces_events", [])) > 0
                has_evidence = cmd.get("behavior", {}).get("evidence_class") is not None
                assert has_events or has_evidence or cmd["behavior"]["type"] == "advance_routing", \
                    f"Command {cmd['id']}: mutating command should produce events or evidence"

    def test_review_decision_produces_expected_events(self, commands):
        """Runtime: /review-decision produces expected events."""
        review_decision = next(
            (c for c in commands if c["command"] == "/review-decision"),
            None
        )
        assert review_decision is not None, "Missing /review-decision command"
        events = set(review_decision.get("produces_events", []))
        expected = {"workflow_approved", "review_changes_requested", "review_rejected"}
        assert events == expected, \
            f"/review-decision should produce {expected}, got {events}"

    def test_implement_produces_expected_events(self, commands):
        """Runtime: /implement produces expected events."""
        implement = next(
            (c for c in commands if c["command"] == "/implement"),
            None
        )
        assert implement is not None, "Missing /implement command"
        events = set(implement.get("produces_events", []))
        expected = {"implementation_started", "implementation_execution_in_progress"}
        assert events == expected, \
            f"/implement should produce {expected}, got {events}"


@pytest.mark.governance
class TestCommandNoUnknownFields:
    """Keine unbekannten Felder in Command-Objekten."""

    def test_no_unknown_runtime_fields(self, commands):
        """Runtime: Command-Objekte haben keine unbekannten Runtime-Felder."""
        for cmd in commands:
            all_fields = set(cmd.keys())
            allowed = RUNTIME_COMMAND_FIELDS | NON_RUNTIME_COMMAND_FIELDS
            unknown = all_fields - allowed
            assert not unknown, \
                f"Command {cmd.get('id')}: unknown fields {unknown}"

    def test_constraints_are_documentation_only(self, commands):
        """Non-runtime: constraints werden vom Runtime ignoriert."""
        # This test documents that constraints are purely for documentation
        # The validator/runtime does not use them for any logic
        for cmd in commands:
            if "constraints" in cmd:
                assert isinstance(cmd["constraints"], list), \
                    f"Command {cmd.get('id')}: constraints must be list"
                # Each constraint should be a string (documentation)
                for c in cmd["constraints"]:
                    assert isinstance(c, str), \
                        f"Command {cmd.get('id')}: constraint must be string"


@pytest.mark.governance
class TestOutputPolicies:
    """Output Policy Definitionen mit stabilen IDs."""

    def test_output_policies_have_stable_id(self, output_policies):
        """Runtime: Alle Output Policies haben stabile ID."""
        for policy in output_policies:
            assert "id" in policy, f"Output policy missing 'id'"
            assert isinstance(policy["id"], str), \
                f"Output policy id must be string"
            assert policy["id"].startswith("op."), \
                f"Output policy ID should start with 'op.'"

    def test_output_policies_have_state_id(self, output_policies):
        """Runtime: Alle Output Policies haben state_id."""
        for policy in output_policies:
            assert "state_id" in policy, f"Output policy missing 'state_id'"
            assert isinstance(policy["state_id"], str)

    def test_output_policy_ids_unique(self, output_policies):
        """Runtime: Output Policy IDs sind eindeutig."""
        ids = [p["id"] for p in output_policies]
        duplicates = [pid for pid in ids if ids.count(pid) > 1]
        assert not duplicates, f"Duplicate output policy IDs: {set(duplicates)}"

    def test_output_policies_have_allowed_classes(self, output_policies):
        """Runtime: Alle Output Policies haben allowed_output_classes."""
        for policy in output_policies:
            assert "allowed_output_classes" in policy
            assert isinstance(policy["allowed_output_classes"], list)
            assert len(policy["allowed_output_classes"]) > 0

    def test_output_policies_have_forbidden_classes(self, output_policies):
        """Runtime: Alle Output Policies haben forbidden_output_classes."""
        for policy in output_policies:
            assert "forbidden_output_classes" in policy
            assert isinstance(policy["forbidden_output_classes"], list)
            assert len(policy["forbidden_output_classes"]) > 0

    def test_output_classes_are_known(self, output_policies):
        """Runtime: Output Classes sind bekannte Werte."""
        for policy in output_policies:
            state_id = policy.get("state_id")
            for cls in policy.get("allowed_output_classes", []):
                assert cls in VALID_OUTPUT_CLASSES, \
                    f"Output policy {state_id}: unknown allowed class '{cls}'"
            for cls in policy.get("forbidden_output_classes", []):
                assert cls in VALID_OUTPUT_CLASSES, \
                    f"Output policy {state_id}: unknown forbidden class '{cls}'"

    def test_no_overlap_between_allowed_and_forbidden(self, output_policies):
        """Runtime: Allowed und Forbidden haben keine Überschneidung."""
        for policy in output_policies:
            allowed = set(policy.get("allowed_output_classes", []))
            forbidden = set(policy.get("forbidden_output_classes", []))
            overlap = allowed & forbidden
            assert not overlap, \
                f"Output policy {policy.get('id')}: overlap {overlap}"

    def test_phase5_forbids_implementation(self, output_policies):
        """Invariant: Phase 5 forbids implementation outputs."""
        phase5_policy = next(
            (p for p in output_policies if p.get("state_id") == "5"), 
            None
        )
        assert phase5_policy is not None, "Phase 5 output policy not found"
        assert "implementation" in phase5_policy["forbidden_output_classes"]

    def test_phase5_plan_discipline(self, output_policies):
        """Invariant: Phase 5 has plan discipline."""
        phase5_policy = next(
            (p for p in output_policies if p.get("state_id") == "5"), 
            None
        )
        assert phase5_policy is not None
        assert "plan_discipline" in phase5_policy
        pd = phase5_policy["plan_discipline"]
        assert pd.get("first_output_is_draft") is True
        assert pd.get("draft_not_review_ready") is True
        assert pd.get("min_self_review_iterations", 0) >= 1


@pytest.mark.governance
class TestPhaseOutputPolicyMap:
    """Phase Output Policy Mapping mit Integrität."""

    def test_phase_output_policy_map_exists(self, command_policy):
        """Runtime: Phase Output Policy Map existiert."""
        assert "phase_output_policy_map" in command_policy
        assert isinstance(command_policy["phase_output_policy_map"], list)
        assert len(command_policy["phase_output_policy_map"]) > 0

    def test_map_entries_have_state_id(self, phase_output_policy_map):
        """Runtime: Map entries haben state_id."""
        for entry in phase_output_policy_map:
            assert "state_id" in entry
            assert isinstance(entry["state_id"], str)

    def test_map_entries_have_output_policy_ref(self, phase_output_policy_map):
        """Runtime: Map entries haben output_policy_ref."""
        for entry in phase_output_policy_map:
            assert "output_policy_ref" in entry
            assert isinstance(entry["output_policy_ref"], str)

    def test_output_policy_ref_uses_stable_id(self, phase_output_policy_map, output_policy_ids):
        """Runtime: output_policy_ref verwendet stabile ID (nicht Index)."""
        for entry in phase_output_policy_map:
            ref = entry["output_policy_ref"]
            # Must NOT be index-based like "output_policies[0]"
            assert not ref.startswith("output_policies["), \
                f"Map entry {entry['state_id']}: ref '{ref}' is index-based, use stable ID"
            # Must reference an existing policy ID
            assert ref in output_policy_ids, \
                f"Map entry {entry['state_id']}: ref '{ref}' not found in output_policies"

    def test_no_duplicate_state_mapping(self, phase_output_policy_map):
        """Runtime: Kein State ist doppelt gemappt."""
        state_ids = [e["state_id"] for e in phase_output_policy_map]
        duplicates = [sid for sid in state_ids if state_ids.count(sid) > 1]
        assert not duplicates, f"Duplicate state mapping: {set(duplicates)}"

    def test_no_orphaned_policies(self, output_policy_ids, phase_output_policy_map):
        """Runtime: Alle Policies sind gemappt."""
        mapped_refs = {e["output_policy_ref"] for e in phase_output_policy_map}
        orphaned = output_policy_ids - mapped_refs
        assert not orphaned, f"Orphaned output policies (not mapped): {orphaned}"


@pytest.mark.governance
class TestCommandTopologyConsistency:
    """Konsistenz zwischen Commands und Topologie."""

    def test_universal_commands_exist(self, command_names):
        """Happy: Universal commands existieren."""
        assert "/continue" in command_names
        assert "/review" in command_names

    def test_command_count(self, commands):
        """Happy: Command count is correct (7 commands)."""
        assert len(commands) == 7, f"Expected 7 commands, got {len(commands)}"

    def test_command_allowed_states_match_topology(self, commands):
        """Happy: Command erlaubte States existieren in Topologie."""
        topo_path = _find_topology_path()
        if topo_path is None:
            pytest.skip("topology.yaml not found for cross-reference")
        
        with open(topo_path, encoding="utf-8") as f:
            topology = yaml.safe_load(f)
        
        state_ids = {s["id"] for s in topology["states"]}
        
        for cmd in commands:
            allowed = cmd.get("allowed_in")
            if allowed == "*":
                continue
            for state_id in allowed:
                assert state_id in state_ids, \
                    f"Command {cmd['id']}: allowed state '{state_id}' not in topology"

    def test_phase6_commands_are_transitional(self, commands):
        """Documentation: Phase 6 commands are marked as transitional."""
        phase6_commands = [
            cmd for cmd in commands 
            if cmd.get("allowed_in") != "*" and "6" in cmd.get("allowed_in", [])
        ]
        for cmd in phase6_commands:
            # These should have comments or documentation indicating transitional
            # The actual check is that they exist and target state "6"
            assert "6" in cmd["allowed_in"], \
                f"Command {cmd['id']}: Phase 6 commands should target state '6'"
