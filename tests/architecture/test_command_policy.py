"""Phase 4: Command Policy Tests

Validiert die extrahierte command_policy.yaml Struktur:
- Alle Commands haben ID, command, allowed_in, behavior
- Commands sind eindeutig
- Output Policies haben allowed/forbidden classes
- Phase Output Policy Map ist konsistent
- Cross-Spec Konsistenz mit Topologie

Diese Tests laufen GEGEN die extrahierte command_policy.yaml.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from typing import Any


# ============================================================================
# Valid Types
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

# Runtime fields for command objects
RUNTIME_COMMAND_FIELDS = {"id", "command", "allowed_in", "mutating", "behavior"}
NON_RUNTIME_COMMAND_FIELDS = {"description", "constraints"}


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
            # Can be "*" (all states) or list of state IDs
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
class TestOutputPolicies:
    """Output Policy Definitionen."""

    def test_output_policies_have_state_id(self, output_policies):
        """Runtime: Alle Output Policies haben state_id."""
        for policy in output_policies:
            assert "state_id" in policy, f"Output policy missing 'state_id'"
            assert isinstance(policy["state_id"], str), \
                f"Output policy state_id must be string"

    def test_output_policies_have_allowed_classes(self, output_policies):
        """Runtime: Alle Output Policies haben allowed_output_classes."""
        for policy in output_policies:
            assert "allowed_output_classes" in policy, \
                f"Output policy {policy.get('state_id')} missing 'allowed_output_classes'"
            assert isinstance(policy["allowed_output_classes"], list), \
                f"Output policy allowed_output_classes must be list"
            assert len(policy["allowed_output_classes"]) > 0, \
                f"Output policy {policy.get('state_id')}: allowed_output_classes must not be empty"

    def test_output_policies_have_forbidden_classes(self, output_policies):
        """Runtime: Alle Output Policies haben forbidden_output_classes."""
        for policy in output_policies:
            assert "forbidden_output_classes" in policy, \
                f"Output policy {policy.get('state_id')} missing 'forbidden_output_classes'"
            assert isinstance(policy["forbidden_output_classes"], list), \
                f"Output policy forbidden_output_classes must be list"
            assert len(policy["forbidden_output_classes"]) > 0, \
                f"Output policy {policy.get('state_id')}: forbidden_output_classes must not be empty"

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
            state_id = policy.get("state_id")
            allowed = set(policy.get("allowed_output_classes", []))
            forbidden = set(policy.get("forbidden_output_classes", []))
            overlap = allowed & forbidden
            assert not overlap, \
                f"Output policy {state_id}: overlap between allowed and forbidden: {overlap}"

    def test_phase5_forbids_implementation(self, output_policies):
        """Invariant: Phase 5 forbids implementation outputs."""
        phase5_policy = next(
            (p for p in output_policies if p.get("state_id") == "5"), 
            None
        )
        assert phase5_policy is not None, "Phase 5 output policy not found"
        assert "implementation" in phase5_policy["forbidden_output_classes"], \
            "Phase 5 must forbid 'implementation' output class"

    def test_phase5_plan_discipline(self, output_policies):
        """Invariant: Phase 5 has plan discipline."""
        phase5_policy = next(
            (p for p in output_policies if p.get("state_id") == "5"), 
            None
        )
        assert phase5_policy is not None
        assert "plan_discipline" in phase5_policy, \
            "Phase 5 must have plan_discipline"
        pd = phase5_policy["plan_discipline"]
        assert pd.get("first_output_is_draft") is True
        assert pd.get("draft_not_review_ready") is True
        assert isinstance(pd.get("min_self_review_iterations"), int)
        assert pd["min_self_review_iterations"] >= 1


@pytest.mark.governance
class TestPhaseOutputPolicyMap:
    """Phase Output Policy Mapping."""

    def test_phase_output_policy_map_exists(self, command_policy):
        """Runtime: Phase Output Policy Map existiert."""
        assert "phase_output_policy_map" in command_policy, \
            "command_policy.yaml must have phase_output_policy_map"
        assert isinstance(command_policy["phase_output_policy_map"], list)

    def test_phase_output_policy_map_entries_have_state_id(self, phase_output_policy_map):
        """Runtime: Map entries haben state_id."""
        for entry in phase_output_policy_map:
            assert "state_id" in entry, f"Map entry missing 'state_id'"
            assert isinstance(entry["state_id"], str)

    def test_phase_output_policy_map_entries_have_ref(self, phase_output_policy_map):
        """Runtime: Map entries haben output_policy_ref."""
        for entry in phase_output_policy_map:
            assert "output_policy_ref" in entry, \
                f"Map entry {entry.get('state_id')} missing 'output_policy_ref'"
            assert isinstance(entry["output_policy_ref"], str)


@pytest.mark.governance
class TestCommandTopologyConsistency:
    """Konsistenz zwischen Commands und Topologie."""

    def test_universal_commands_exist(self, command_names):
        """Happy: Universal commands /continue und /review existieren."""
        assert "/continue" in command_names, "Missing /continue command"
        assert "/review" in command_names, "Missing /review command"

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
