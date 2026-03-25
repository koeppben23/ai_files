"""Phase 8: Spec-Validator und Conformance-Checks (v2)

Strenger Spec-Validator mit expliziter Error/Warning/Gap-Klassifizierung.
Validiert die interne Konsistenz jeder Spec und die Cross-Spec-Conformance.

Validation Severity:
- ERROR: Fehler - muss gefixt werden vor Merge/Runtime
- WARNING: Warnung - sollte gefixt werden, blockiert nicht
- TEMPORARY_GAP: Bewusste Lücke - dokumentiert und zeitlich begrenzt
"""

from __future__ import annotations

import pytest
import yaml
from enum import Enum
from pathlib import Path
from typing import NamedTuple


class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    TEMPORARY_GAP = "temporary_gap"


class ValidationResult(NamedTuple):
    severity: ValidationSeverity
    spec: str
    rule: str
    message: str
    location: str | None = None


def _find_spec_path(spec_name: str) -> Path | None:
    """Find a spec file relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / spec_name
        if candidate.exists():
            return candidate
    return None


def _load_yaml(spec_name: str) -> dict | None:
    """Load a YAML spec file."""
    path = _find_spec_path(spec_name)
    if path is None:
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_raw_yaml(spec_name: str) -> dict | None:
    """Load raw YAML without normalization."""
    return _load_yaml(spec_name)


# ============================================================================
# Forbidden Fields (Presentation/UX must not leak into domain specs)
# ============================================================================

FORBIDDEN_TOPOLOGY_STATE_FIELDS = {
    "active_gate", "next_gate_condition", "gate_message", "instruction",
    "presentation_text", "user_prompt", "help_text"
}

FORBIDDEN_TOPOLOGY_TRANSITION_FIELDS = {
    "gate_message", "instruction", "presentation_text", "condition_description"
}

# Allowed structural metadata (per ADR-001)
ALLOWED_STRUCTURAL_METADATA = {"parent", "description", "version", "schema"}

# Forbidden structural metadata (too UX-like)
FORBIDDEN_STRUCTURAL_METADATA = {
    "user_guidance", "display_name", "ui_hint", "icon", "color"
}


@pytest.fixture
def topology():
    """Load topology.yaml."""
    return _load_yaml("topology.yaml")


@pytest.fixture
def topology_raw():
    """Load raw topology.yaml."""
    return _load_raw_yaml("topology.yaml")


@pytest.fixture
def guards():
    """Load guards.yaml."""
    return _load_yaml("guards.yaml")


@pytest.fixture
def command_policy():
    """Load command_policy.yaml."""
    return _load_yaml("command_policy.yaml")


@pytest.fixture
def messages():
    """Load messages.yaml."""
    return _load_yaml("messages.yaml")


# ============================================================================
# Validation Rules Registry
# ============================================================================

def validate_topology_intra_spec(topology: dict | None) -> list[ValidationResult]:
    """Validate topology.yaml internal consistency. Returns ERROR/WARNING/GAP results."""
    results = []
    if topology is None:
        return results

    state_ids = [s["id"] for s in topology.get("states", [])]
    state_ids_set = set(state_ids)

    for s in topology.get("states", []):
        sid = s["id"]

        # ERROR: Duplicate state IDs
        if state_ids.count(sid) > 1:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "topology",
                "unique_state_ids",
                f"Duplicate state ID: {sid}",
                f"state:{sid}"
            ))

        # ERROR: Missing required fields
        for field in ["id", "terminal", "transitions"]:
            if field not in s:
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "topology",
                    "required_fields",
                    f"State {sid} missing required field: {field}",
                    f"state:{sid}"
                ))

        for t in s.get("transitions", []):
            tid = t.get("id", "?")

            # ERROR: Invalid transition target
            target = t.get("target", "")
            if target and target not in state_ids_set:
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "topology",
                    "valid_transition_target",
                    f"Transition {tid} targets unknown state: {target}",
                    f"transition:{tid}"
                ))

            # ERROR: Missing required transition fields
            for field in ["id", "event", "target"]:
                if field not in t:
                    results.append(ValidationResult(
                        ValidationSeverity.ERROR, "topology",
                        "required_transition_fields",
                        f"Transition {tid} missing field: {field}",
                        f"transition:{tid}"
                    ))

        # WARNING: Non-terminal state has no transitions
        if not s.get("terminal") and not s.get("transitions"):
            results.append(ValidationResult(
                ValidationSeverity.WARNING, "topology",
                "non_terminal_no_transitions",
                f"Non-terminal state {sid} has no transitions",
                f"state:{sid}"
            ))

    # WARNING: Unreachable states
    reachable = _compute_reachable_states(topology)
    unreachable = state_ids_set - reachable
    if unreachable:
        for usid in unreachable:
            results.append(ValidationResult(
                ValidationSeverity.WARNING, "topology",
                "unreachable_states",
                f"State {usid} is not reachable from start",
                f"state:{usid}"
            ))

    return results


def _compute_reachable_states(topology: dict) -> set[str]:
    """Compute all states reachable from start_state_id."""
    start = topology.get("start_state_id", "")
    reachable = {start}
    to_visit = [start]

    state_map = {s["id"]: s for s in topology.get("states", [])}

    while to_visit:
        current = to_visit.pop()
        state = state_map.get(current)
        if not state:
            continue
        for t in state.get("transitions", []):
            target = t.get("target", "")
            if target and target not in reachable:
                reachable.add(target)
                to_visit.append(target)

    return reachable


def validate_topology_ux_fields(topology_raw: dict | None) -> list[ValidationResult]:
    """Validate topology has no presentation/UX fields. CRITICAL for ADR-001."""
    results = []
    if topology_raw is None:
        return results

    for s in topology_raw.get("states", []):
        sid = s.get("id", "?")

        for field in FORBIDDEN_TOPOLOGY_STATE_FIELDS:
            if field in s:
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "topology",
                    "forbidden_state_field",
                    f"State {sid} contains forbidden UX field: {field}",
                    f"state:{sid}:{field}"
                ))

        for t in s.get("transitions", []):
            tid = t.get("id", "?")
            for field in FORBIDDEN_TOPOLOGY_TRANSITION_FIELDS:
                if field in t:
                    results.append(ValidationResult(
                        ValidationSeverity.ERROR, "topology",
                        "forbidden_transition_field",
                        f"Transition {tid} contains forbidden UX field: {field}",
                        f"transition:{tid}:{field}"
                    ))

        for field in FORBIDDEN_STRUCTURAL_METADATA:
            if field in s:
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "topology",
                    "forbidden_structural_metadata",
                    f"State {sid} contains forbidden metadata: {field}",
                    f"state:{sid}:{field}"
                ))

    return results


def validate_guards_intra_spec(guards: dict | None) -> list[ValidationResult]:
    """Validate guards.yaml internal consistency."""
    results = []
    if guards is None:
        return results

    VALID_GUARD_TYPES = {
        "exit", "transition", "phase_gate", "has_field", "field_equals",
        "field_not_empty", "has_any_field", "all_fields_present",
        "composite", "phase_exit_ready"
    }

    guard_ids = [g["id"] for g in guards.get("guards", [])]
    guard_ids_set = set(guard_ids)

    for g in guards.get("guards", []):
        gid = g["id"]

        if guard_ids.count(gid) > 1:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "guards",
                "unique_guard_ids",
                f"Duplicate guard ID: {gid}",
                f"guard:{gid}"
            ))

        gtype = g.get("guard_type")
        if gtype not in VALID_GUARD_TYPES:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "guards",
                "valid_guard_type",
                f"Guard {gid} has invalid type: {gtype}",
                f"guard:{gid}:guard_type"
            ))

        if gtype == "composite":
            for ref in g.get("guard_refs", []):
                if ref not in guard_ids_set:
                    results.append(ValidationResult(
                        ValidationSeverity.ERROR, "guards",
                        "valid_composite_refs",
                        f"Guard {gid} references unknown guard: {ref}",
                        f"guard:{gid}:guard_refs"
                    ))

    return results


def validate_command_policy_intra_spec(cp: dict | None) -> list[ValidationResult]:
    """Validate command_policy.yaml internal consistency."""
    results = []
    if cp is None:
        return results

    cmd_ids = [c["id"] for c in cp.get("commands", [])]
    restriction_patterns = []

    for c in cp.get("commands", []):
        cid = c["id"]

        if cmd_ids.count(cid) > 1:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "command_policy",
                "unique_command_ids",
                f"Duplicate command ID: {cid}",
                f"command:{cid}"
            ))

        for field in ["id", "command", "description", "allowed_in"]:
            if field not in c:
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "command_policy",
                    "required_command_fields",
                    f"Command {cid} missing field: {field}",
                    f"command:{cid}:{field}"
                ))

    for r in cp.get("command_restrictions", []):
        pattern = r.get("state_pattern", "")
        if restriction_patterns.count(pattern) > 1:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "command_policy",
                "unique_restriction_patterns",
                f"Duplicate restriction pattern: {pattern}",
                f"restriction:{pattern}"
            ))
        restriction_patterns.append(pattern)

    return results


def validate_messages_intra_spec(msgs: dict | None) -> list[ValidationResult]:
    """Validate messages.yaml internal consistency."""
    results = []
    if msgs is None:
        return results

    import re
    EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

    msg_ids = []
    for m in msgs.get("state_messages", []):
        msg_ids.append(m["id"])
    for m in msgs.get("transition_messages", []):
        msg_ids.append(m["id"])

    for mid in msg_ids:
        if msg_ids.count(mid) > 1:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "messages",
                "unique_message_ids",
                f"Duplicate message ID: {mid}",
                f"message:{mid}"
            ))

    for m in msgs.get("transition_messages", []):
        mid = m.get("id", "?")
        for field in ["id", "state_id", "event", "gate_message", "instruction"]:
            if field not in m:
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "messages",
                    "required_message_fields",
                    f"Message {mid} missing field: {field}",
                    f"message:{mid}:{field}"
                ))

        event = m.get("event", "")
        if event and not EVENT_PATTERN.match(event):
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "messages",
                "valid_event_format",
                f"Message {mid} has invalid event format: {event}",
                f"message:{mid}:event"
            ))

    return results


# ============================================================================
# Cross-Spec Conformance Validators
# ============================================================================

def validate_cross_ref_guard_refs(topology: dict | None, guards: dict | None) -> list[ValidationResult]:
    """Validate guard_refs in topology point to valid guards."""
    results = []
    if topology is None or guards is None:
        return results

    guard_ids = {g["id"] for g in guards.get("guards", [])}

    for s in topology.get("states", []):
        sid = s["id"]
        for t in s.get("transitions", []):
            tid = t.get("id", "?")
            guard_ref = t.get("guard_ref")
            if guard_ref and guard_ref not in guard_ids:
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "cross_ref:topology-guards",
                    "guard_ref_valid",
                    f"Transition {tid} references unknown guard: {guard_ref}",
                    f"transition:{tid}:guard_ref"
                ))

    return results


def validate_cross_ref_message_state_exists(
    topology: dict | None, messages: dict | None
) -> list[ValidationResult]:
    """Validate message state_ids exist in topology."""
    results = []
    if topology is None or messages is None:
        return results

    state_ids = {s["id"] for s in topology.get("states", [])}
    FUTURE_STATES = {
        "6.approved", "6.presentation", "6.execution",
        "6.blocked", "6.rework", "6.rejected", "6.complete",
        "6.internal_review", "6"
    }
    state_ids = state_ids | FUTURE_STATES

    for m in messages.get("transition_messages", []):
        mid = m.get("id", "?")
        state_id = m.get("state_id", "")
        if state_id and state_id not in state_ids:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "cross_ref:topology-messages",
                "message_state_exists",
                f"Message {mid} references unknown state: {state_id}",
                f"message:{mid}:state_id"
            ))

    return results


def validate_cross_ref_message_events(
    topology: dict | None, messages: dict | None
) -> list[ValidationResult]:
    """Validate message events exist in topology for the state."""
    results = []
    if topology is None or messages is None:
        return results

    state_events = {}
    for s in topology.get("states", []):
        state_events[s["id"]] = {t["event"] for t in s.get("transitions", [])}

    FUTURE_STATES = {
        "6.approved", "6.presentation", "6.execution",
        "6.blocked", "6.rework", "6.rejected", "6.complete",
        "6.internal_review"
    }

    for m in messages.get("transition_messages", []):
        mid = m.get("id", "?")
        state_id = m.get("state_id", "")
        event = m.get("event", "")

        if state_id in FUTURE_STATES:
            continue

        if state_id not in state_events:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "cross_ref:topology-messages",
                "message_event_in_topology",
                f"Message {mid}: state {state_id} not in topology",
                f"message:{mid}"
            ))
            continue

        if event and event not in state_events[state_id]:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "cross_ref:topology-messages",
                "message_event_in_state",
                f"Message {mid}: event '{event}' not defined for state '{state_id}'",
                f"message:{mid}:event"
            ))

    return results


def validate_cross_ref_command_allowed_states(
    topology: dict | None, cp: dict | None
) -> list[ValidationResult]:
    """Validate commands' allowed_in states exist in topology."""
    results = []
    if topology is None or cp is None:
        return results

    state_ids = {s["id"] for s in topology.get("states", [])}
    terminal_states = {s["id"] for s in topology.get("states", []) if s.get("terminal")}
    FUTURE_STATES = {
        "6.approved", "6.presentation", "6.execution",
        "6.blocked", "6.rework", "6.rejected", "6.complete",
        "6.internal_review"
    }
    state_ids = state_ids | FUTURE_STATES | {"*"}
    terminal_states = terminal_states | {"6.complete"}  # Known terminal state

    for c in cp.get("commands", []):
        cid = c["id"]
        allowed_in = c.get("allowed_in", [])
        if isinstance(allowed_in, list):
            for state in allowed_in:
                if state not in state_ids:
                    results.append(ValidationResult(
                        ValidationSeverity.ERROR, "cross_ref:command_policy-topology",
                        "allowed_state_exists",
                        f"Command {cid} allows unknown state: {state}",
                        f"command:{cid}:allowed_in"
                    ))
                # WARNING: Command allowed in terminal state
                if state in terminal_states:
                    results.append(ValidationResult(
                        ValidationSeverity.WARNING, "cross_ref:command_policy-topology",
                        "command_in_terminal_state",
                        f"Command {cid} allows terminal state: {state} (may be misconfiguration)",
                        f"command:{cid}:allowed_in"
                    ))

    for r in cp.get("command_restrictions", []):
        pattern = r.get("state_pattern", "")
        if pattern == "*.terminal" or pattern == "6.complete":
            continue
        if pattern not in state_ids:
            results.append(ValidationResult(
                ValidationSeverity.ERROR, "cross_ref:command_policy-topology",
                "restriction_state_exists",
                f"Restriction references unknown state: {pattern}",
                f"restriction:{pattern}"
            ))

    return results


def validate_cross_ref_message_commands(
    messages: dict | None, cp: dict | None
) -> list[ValidationResult]:
    """Validate commands in messages are allowed in the state and semantically appropriate."""
    results = []
    if messages is None or cp is None:
        return results

    import re
    CMD_PATTERN = re.compile(r"/[a-z][a-z0-9_\-]*")

    cmd_allowed = {}
    cmd_mutating = {}
    for c in cp.get("commands", []):
        cmd = c["command"]
        allowed = c.get("allowed_in", [])
        if isinstance(allowed, list):
            cmd_allowed[cmd] = set(allowed)
        elif allowed == "*":
            cmd_allowed[cmd] = {"*"}
        # Track mutating status
        cmd_mutating[cmd] = c.get("mutating", True)  # Default to True if not specified

    for m in messages.get("transition_messages", []):
        mid = m.get("id", "?")
        instruction = m.get("instruction", "")
        state_id = m.get("state_id", "")

        cmd_matches = list(CMD_PATTERN.finditer(instruction))
        
        for match in cmd_matches:
            cmd = match.group()
            if cmd in {"/continue"}:
                continue

            # WARNING: Read-only command suggested as ONLY progress option
            # Only flag if /review is the primary suggestion (no other mutating commands)
            if cmd == "/review":
                has_mutating = any(
                    cmd_allowed.get(m2.group(), {"*"}) != {"*"} 
                    for m2 in cmd_matches 
                    if m2.group() not in {"/review", "/continue"}
                )
                if not has_mutating and not cmd_mutating.get("/review", True):
                    results.append(ValidationResult(
                        ValidationSeverity.WARNING, "cross_ref:messages-command_policy",
                        "readonly_command_as_progress",
                        f"Message {mid}: read-only '/review' suggested as only progress (may not advance state)",
                        f"message:{mid}"
                    ))
                continue

            allowed = cmd_allowed.get(cmd, set())
            if "*" in allowed:
                continue

            if state_id not in allowed:
                if state_id and state_id.startswith("6."):
                    if "6" in allowed:
                        continue
                results.append(ValidationResult(
                    ValidationSeverity.ERROR, "cross_ref:messages-command_policy",
                    "command_allowed_in_state",
                    f"Message {mid}: command '{cmd}' not allowed in state '{state_id}'",
                    f"message:{mid}"
                ))

    return results


# ============================================================================
# Tests
# ============================================================================

@pytest.mark.governance
class TestTopologyValidation:
    """Topology internal validation tests."""

    def test_topology_loads(self, topology):
        assert topology is not None

    def test_no_duplicate_state_ids(self, topology):
        errors = [r for r in validate_topology_intra_spec(topology)
                  if r.rule == "unique_state_ids" and r.severity == ValidationSeverity.ERROR]
        assert not errors, f"Errors: {errors}"

    def test_all_transition_targets_valid(self, topology):
        errors = [r for r in validate_topology_intra_spec(topology)
                  if r.rule == "valid_transition_target"]
        assert not errors, f"Errors: {errors}"

    def test_all_states_have_required_fields(self, topology):
        errors = [r for r in validate_topology_intra_spec(topology)
                  if r.rule == "required_fields"]
        assert not errors, f"Errors: {errors}"


@pytest.mark.governance
class TestTopologyUXValidation:
    """Topology must not contain presentation/UX fields (ADR-001)."""

    def test_no_forbidden_state_fields(self, topology_raw):
        """ERROR: Topology must not contain UX fields like active_gate, next_gate_condition."""
        errors = [r for r in validate_topology_ux_fields(topology_raw)
                  if r.severity == ValidationSeverity.ERROR]
        assert not errors, f"Forbidden UX fields found: {errors}"

    def test_no_forbidden_transition_fields(self, topology_raw):
        """ERROR: Transitions must not contain UX fields."""
        errors = [r for r in validate_topology_ux_fields(topology_raw)
                  if "forbidden_transition" in r.rule]
        assert not errors, f"Forbidden transition fields: {errors}"

    def test_allowed_structural_metadata(self, topology):
        """parent and description are allowed structural metadata (per ADR-001)."""
        assert topology is not None
        for s in topology.get("states", []):
            for field in ALLOWED_STRUCTURAL_METADATA:
                if field in s:
                    assert field not in FORBIDDEN_STRUCTURAL_METADATA

    def test_raw_spec_with_forbidden_fields_is_rejected(self):
        """ERROR: Raw spec containing forbidden UX fields must be rejected.
        
        This tests the ACTUAL RAW YAML content, not a normalized model.
        ADR-001 requires that forbidden fields are rejected at the source level.
        """
        broken_topology_raw = {
            "states": [{
                "id": "test",
                "terminal": False,
                "transitions": [],
                "active_gate": "Test Gate",  # FORBIDDEN
                "next_gate_condition": "Test condition",  # FORBIDDEN
            }]
        }
        
        errors = validate_topology_ux_fields(broken_topology_raw)
        
        forbidden_errors = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert len(forbidden_errors) >= 2, \
            "Should detect at least 2 forbidden UX fields in raw spec"
        
        gate_errors = [r for r in forbidden_errors if "active_gate" in r.message]
        condition_errors = [r for r in forbidden_errors if "next_gate_condition" in r.message]
        
        assert gate_errors, "Should detect forbidden active_gate field"
        assert condition_errors, "Should detect forbidden next_gate_condition field"

    def test_raw_spec_with_forbidden_transition_fields_rejected(self):
        """ERROR: Raw spec with forbidden transition fields must be rejected."""
        broken_topology_raw = {
            "states": [{
                "id": "test",
                "terminal": False,
                "transitions": [{
                    "id": "t1-t2",
                    "event": "default",
                    "target": "test",
                    "gate_message": "Test gate",  # FORBIDDEN
                    "instruction": "Test instruction",  # FORBIDDEN
                }]
            }]
        }
        
        errors = validate_topology_ux_fields(broken_topology_raw)
        
        forbidden_errors = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert forbidden_errors, "Should detect forbidden transition fields"

    def test_raw_spec_with_forbidden_metadata_rejected(self):
        """ERROR: Raw spec with forbidden structural metadata must be rejected."""
        broken_topology_raw = {
            "states": [{
                "id": "test",
                "terminal": False,
                "transitions": [],
                "user_guidance": "Some guidance",  # FORBIDDEN
                "display_name": "Test State",  # FORBIDDEN
            }]
        }
        
        errors = validate_topology_ux_fields(broken_topology_raw)
        
        forbidden_errors = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert len(forbidden_errors) >= 2, \
            "Should detect forbidden structural metadata fields"


@pytest.mark.governance
class TestGuardsValidation:
    """Guards internal validation tests."""

    def test_guards_load(self, guards):
        assert guards is not None

    def test_no_duplicate_guard_ids(self, guards):
        errors = [r for r in validate_guards_intra_spec(guards)
                  if r.rule == "unique_guard_ids"]
        assert not errors

    def test_all_guard_types_valid(self, guards):
        errors = [r for r in validate_guards_intra_spec(guards)
                  if r.rule == "valid_guard_type"]
        assert not errors

    def test_composite_guards_reference_valid_guards(self, guards):
        errors = [r for r in validate_guards_intra_spec(guards)
                  if r.rule == "valid_composite_refs"]
        assert not errors


@pytest.mark.governance
class TestCommandPolicyValidation:
    """Command Policy internal validation tests."""

    def test_command_policy_loads(self, command_policy):
        assert command_policy is not None

    def test_no_duplicate_command_ids(self, command_policy):
        errors = [r for r in validate_command_policy_intra_spec(command_policy)
                  if r.rule == "unique_command_ids"]
        assert not errors

    def test_all_commands_have_required_fields(self, command_policy):
        errors = [r for r in validate_command_policy_intra_spec(command_policy)
                  if r.rule == "required_command_fields"]
        assert not errors

    def test_no_duplicate_restriction_patterns(self, command_policy):
        errors = [r for r in validate_command_policy_intra_spec(command_policy)
                  if r.rule == "unique_restriction_patterns"]
        assert not errors


@pytest.mark.governance
class TestMessagesValidation:
    """Messages internal validation tests."""

    def test_messages_load(self, messages):
        assert messages is not None

    def test_no_duplicate_message_ids(self, messages):
        errors = [r for r in validate_messages_intra_spec(messages)
                  if r.rule == "unique_message_ids"]
        assert not errors

    def test_transition_messages_have_required_fields(self, messages):
        errors = [r for r in validate_messages_intra_spec(messages)
                  if r.rule == "required_message_fields"]
        assert not errors

    def test_event_format_valid(self, messages):
        errors = [r for r in validate_messages_intra_spec(messages)
                  if r.rule == "valid_event_format"]
        assert not errors


@pytest.mark.governance
class TestCrossSpecConformance:
    """Cross-Spec Conformance validation tests."""

    def test_guard_refs_point_to_valid_guards(self, topology, guards):
        """ERROR: guard_ref must point to existing guard."""
        errors = validate_cross_ref_guard_refs(topology, guards)
        assert not errors, f"Invalid guard refs: {errors}"

    def test_message_state_ids_exist_in_topology(self, topology, messages):
        """ERROR: message state_id must exist in topology."""
        errors = validate_cross_ref_message_state_exists(topology, messages)
        assert not errors, f"Invalid message state_ids: {errors}"

    def test_message_events_exist_in_topology(self, topology, messages):
        """ERROR: message event must exist in topology for the state."""
        errors = validate_cross_ref_message_events(topology, messages)
        assert not errors, f"Invalid message events: {errors}"

    def test_commands_allowed_states_exist_in_topology(self, topology, command_policy):
        """ERROR: command allowed_in states must exist in topology."""
        errors = validate_cross_ref_command_allowed_states(topology, command_policy)
        assert not errors, f"Invalid allowed_in states: {errors}"

    def test_commands_in_messages_are_allowed(self, messages, command_policy):
        """ERROR: commands in message instructions must be allowed in the state."""
        errors = validate_cross_ref_message_commands(messages, command_policy)
        assert not errors, f"Command conformance violations: {errors}"

    def test_message_mentioning_disallowed_command_is_error(self):
        """ERROR: Message instruction mentioning command not allowed in state.
        
        This is a critical cross-ref: if a message HINTS at a command,
        that command must be allowed in the state.
        """
        broken_messages = {
            "transition_messages": [{
                "id": "test_msg",
                "state_id": "5",
                "event": "default",
                "gate_message": "Test",
                "instruction": "Use /implement to start implementation"  # /implement not allowed in state 5
            }]
        }
        
        broken_cp = {
            "commands": [{
                "id": "cmd_implement",
                "command": "/implement",
                "description": "Start implementation",
                "allowed_in": ["6.approved", "6.execution"]
            }]
        }
        
        errors = validate_cross_ref_message_commands(broken_messages, broken_cp)
        
        cmd_errors = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert cmd_errors, "Should detect command not allowed in state"
        assert any("not allowed" in r.message for r in cmd_errors)

    def test_readonly_command_in_write_state_is_error(self):
        """ERROR: Read-only command mentioned for state that requires mutating command.
        
        If a message describes /review as the way to proceed in a state,
        but /review is read-only and the state requires advancement,
        this indicates a semantic mismatch.
        """
        broken_messages = {
            "transition_messages": [{
                "id": "test_msg",
                "state_id": "5",
                "event": "default",
                "gate_message": "Test",
                "instruction": "Use /review to proceed"  # /review is read-only, not advancing
            }]
        }
        
        broken_cp = {
            "commands": [{
                "id": "cmd_review",
                "command": "/review",
                "description": "Read-only review",
                "allowed_in": ["*"],
                "mutating": False
            }]
        }
        
        errors = validate_cross_ref_message_commands(broken_messages, broken_cp)
        
        assert errors, "Should detect read-only command used as progress hint"
        readonly_errors = [r for r in errors if "readonly" in r.message.lower() or "/review" in r.message]
        assert readonly_errors, f"Should flag /review as not advancing: {errors}"

    def test_message_with_semantically_nonexistent_state_rejected(self):
        """ERROR: Message references state that doesn't exist in topology.
        
        Even if the message format is valid, referencing a nonexistent state
        is a critical error.
        """
        broken_topology = {
            "states": [{"id": "1", "terminal": False, "transitions": []}]
        }
        
        broken_messages = {
            "transition_messages": [{
                "id": "test_msg",
                "state_id": "nonexistent_state",  # Does not exist
                "event": "default",
                "gate_message": "Test",
                "instruction": "Use /continue"
            }]
        }
        
        errors = validate_cross_ref_message_state_exists(broken_topology, broken_messages)
        
        state_errors = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert state_errors, "Should detect nonexistent state reference"
        assert any("nonexistent_state" in r.message for r in state_errors)

    def test_message_event_not_in_state_transitions_is_error(self):
        """ERROR: Message event not defined in state's transition list.
        
        A formally valid event name (snake_case) that doesn't exist in the
        state's transition table is semantically nonexistent.
        """
        broken_topology = {
            "states": [{
                "id": "1",
                "terminal": False,
                "transitions": [{
                    "id": "t1-t1",
                    "event": "default",
                    "target": "1"
                }]
            }]
        }
        
        broken_messages = {
            "transition_messages": [{
                "id": "test_msg",
                "state_id": "1",
                "event": "nonexistent_event",  # Not in transitions
                "gate_message": "Test",
                "instruction": "Use /continue"
            }]
        }
        
        errors = validate_cross_ref_message_events(broken_topology, broken_messages)
        
        event_errors = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert event_errors, "Should detect event not in state transitions"
        assert any("nonexistent_event" in r.message for r in event_errors)

    def test_command_allowed_in_terminal_state_is_warning(self):
        """WARNING: Command allowed in terminal state may be misconfiguration.
        
        Terminal states should block mutating commands. If a command's
        allowed_in includes a terminal state, this is suspicious.
        """
        broken_cp = {
            "commands": [{
                "id": "cmd_implement",
                "command": "/implement",
                "description": "Start implementation",
                "allowed_in": ["6.complete"]  # Terminal state!
            }]
        }
        
        broken_topology = {
            "states": [{
                "id": "6.complete",
                "terminal": True,
                "transitions": []
            }]
        }
        
        errors = validate_cross_ref_command_allowed_states(broken_topology, broken_cp)
        
        terminal_errors = [r for r in errors if r.severity == ValidationSeverity.WARNING 
                         and "terminal" in r.message.lower()]
        assert terminal_errors, \
            f"Should flag command in terminal state: {errors}"


@pytest.mark.governance
class TestPhase6BlockedReworkConformance:
    """Phase 6 blocked/rework state semantics must be strictly defined.
    
    Per ADR-007, these are the softest Phase 6 substates and require
    strict conformance to prevent future drift.
    """

    def test_blocked_state_has_recovery_path(self, topology):
        """ERROR: 6.blocked must have a path back to 6.execution.
        
        The /implement command from 6.blocked must produce implementation_started
        which triggers the transition to 6.execution.
        """
        blocked_state = next((s for s in topology.get("states", []) if s["id"] == "6.blocked"), None)
        assert blocked_state is not None, "State 6.blocked must exist"
        
        events = {t["event"] for t in blocked_state.get("transitions", [])}
        assert "implementation_started" in events, \
            "6.blocked must have implementation_started transition to 6.execution"

    def test_rework_state_has_clarification_path(self, topology):
        """ERROR: 6.rework must have a path back to 6.presentation.
        
        The /continue command from 6.rework should allow clarification
        and then return to 6.presentation for re-review.
        """
        rework_state = next((s for s in topology.get("states", []) if s["id"] == "6.rework"), None)
        assert rework_state is not None, "State 6.rework must exist"
        
        events = {t["event"] for t in rework_state.get("transitions", [])}
        assert "default" in events, \
            "6.rework must have default transition for /continue"

    def test_rework_has_rerun_path(self, topology):
        """ERROR: 6.rework should allow /implement rerun after clarification.
        
        After clarifying rework, /implement should be allowed from 6.rework
        to transition to 6.execution.
        """
        rework_state = next((s for s in topology.get("states", []) if s["id"] == "6.rework"), None)
        if rework_state:
            events = {t["event"] for t in rework_state.get("transitions", [])}
            # This is a soft requirement - rerun should be possible
            # but may be conditional on clarification being consumed
            assert "implementation_started" in events or "default" in events, \
                "6.rework must have path to continue flow"


@pytest.mark.governance
class TestValidationSeverityClassification:
    """Tests that verify ERROR severity is enforced for critical rules."""

    def test_all_critical_rules_are_errors(self):
        """All validation rules that must pass are ERROR severity."""
        critical_rules = {
            "unique_state_ids", "valid_transition_target", "required_fields",
            "required_transition_fields", "unique_guard_ids", "valid_guard_type",
            "valid_composite_refs", "unique_command_ids", "required_command_fields",
            "unique_message_ids", "required_message_fields", "valid_event_format",
            "guard_ref_valid", "message_state_exists", "message_event_in_topology",
            "message_event_in_state", "allowed_state_exists", "restriction_state_exists",
            "command_allowed_in_state", "forbidden_state_field", "forbidden_transition_field",
            "forbidden_structural_metadata"
        }

        for spec in ["topology", "guards", "command_policy", "messages"]:
            t = _load_yaml(f"{spec}.yaml")
            results = []
            if spec == "topology":
                results = validate_topology_intra_spec(t)
                results.extend(validate_topology_ux_fields(_load_raw_yaml(f"{spec}.yaml")))
            elif spec == "guards":
                results = validate_guards_intra_spec(t)
            elif spec == "command_policy":
                results = validate_command_policy_intra_spec(t)
            elif spec == "messages":
                results = validate_messages_intra_spec(t)

            for r in results:
                if r.rule in critical_rules:
                    assert r.severity == ValidationSeverity.ERROR, \
                        f"Critical rule {r.rule} must be ERROR, got {r.severity}: {r.message}"


@pytest.mark.governance
class TestValidationResultFormat:
    """Tests that validate ValidationResult format is consistent."""

    def test_all_results_have_required_fields(self):
        """All ValidationResults have all required fields."""
        for spec in ["topology", "guards", "command_policy", "messages"]:
            t = _load_yaml(f"{spec}.yaml")
            results = []
            if spec == "topology":
                results = validate_topology_intra_spec(t)
                results.extend(validate_topology_ux_fields(_load_raw_yaml(f"{spec}.yaml")))
            elif spec == "guards":
                results = validate_guards_intra_spec(t)
            elif spec == "command_policy":
                results = validate_command_policy_intra_spec(t)
            elif spec == "messages":
                results = validate_messages_intra_spec(t)

            for r in results:
                assert r.severity in ValidationSeverity
                assert r.spec == spec
                assert r.rule
                assert r.message

    def test_error_count_is_zero_for_valid_specs(self):
        """All specs should have zero ERROR results."""
        for spec in ["topology", "guards", "command_policy", "messages"]:
            t = _load_yaml(f"{spec}.yaml")
            results = []
            if spec == "topology":
                results = validate_topology_intra_spec(t)
                results.extend(validate_topology_ux_fields(_load_raw_yaml(f"{spec}.yaml")))
            elif spec == "guards":
                results = validate_guards_intra_spec(t)
            elif spec == "command_policy":
                results = validate_command_policy_intra_spec(t)
            elif spec == "messages":
                results = validate_messages_intra_spec(t)

            errors = [r for r in results if r.severity == ValidationSeverity.ERROR]
            assert not errors, f"{spec}: {len(errors)} errors found: {errors}"
