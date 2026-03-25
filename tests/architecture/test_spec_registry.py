"""Tests for SpecRegistry - WP0: Spec Registry Foundation.

Tests cover:
- Happy Path: Spec loading succeeds
- Negative: Missing/invalid specs fail with clear errors
- Edge Cases: Boundary conditions
- Regression: Existing specs load correctly
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from governance_runtime.kernel.spec_registry import (
    SpecRegistry,
    SpecBundle,
    SpecNotFoundError,
    SpecValidationError,
    SpecInconsistencyError,
)


@pytest.fixture
def temp_spec_dir(tmp_path: Path) -> Path:
    """Create a temporary spec directory with valid specs."""
    spec_dir = tmp_path / "governance_spec"
    spec_dir.mkdir()
    return spec_dir


@pytest.fixture
def valid_topology(temp_spec_dir: Path) -> dict:
    """Valid topology spec."""
    return {
        "version": 1,
        "schema": "opencode.topology.v1",
        "start_state_id": "0",
        "states": [
            {
                "id": "0",
                "terminal": False,
                "transitions": [
                    {"id": "t0-1", "event": "default", "target": "1"}
                ]
            },
            {
                "id": "6.approved",
                "terminal": False,
                "parent": "6",
                "description": "Plan approved",
                "transitions": [
                    {"id": "t6a-6e", "event": "implementation_started", "target": "6.execution"}
                ]
            },
            {
                "id": "6.complete",
                "terminal": True,
                "parent": "6",
                "description": "Workflow complete"
            }
        ]
    }


@pytest.fixture
def valid_command_policy(temp_spec_dir: Path) -> dict:
    """Valid command policy spec."""
    return {
        "version": 1,
        "schema": "opencode.command_policy.v1",
        "commands": [
            {
                "id": "cmd_implement",
                "command": "/implement",
                "allowed_in": ["6.approved"],
                "mutating": True,
                "behavior": {"type": "start_implementation"}
            }
        ]
    }


@pytest.fixture
def valid_guards(temp_spec_dir: Path) -> dict:
    """Valid guards spec."""
    return {
        "version": 1,
        "schema": "opencode.guards.v1",
        "guards": [
            {
                "id": "guard_workflow_complete",
                "guard_type": "transition",
                "event": "workflow_complete",
                "condition": {"type": "key_present", "key": "workflow_complete"}
            }
        ]
    }


@pytest.fixture
def valid_messages(temp_spec_dir: Path) -> dict:
    """Valid messages spec."""
    return {
        "version": 1,
        "schema": "opencode.messages.v1",
        "messages": []
    }


@pytest.fixture
def write_specs(
    temp_spec_dir: Path,
    valid_topology: dict,
    valid_command_policy: dict,
    valid_guards: dict,
    valid_messages: dict
) -> Path:
    """Write all valid specs to temp directory."""
    import yaml
    
    (temp_spec_dir / "topology.yaml").write_text(yaml.dump(valid_topology))
    (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(valid_command_policy))
    (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
    (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
    
    return temp_spec_dir


class TestSpecRegistryLoadAll:
    """Happy Path: Spec loading succeeds."""
    
    def test_load_all_returns_bundle(
        self,
        write_specs: Path,
        valid_topology: dict,
        valid_command_policy: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Happy: load_all returns SpecBundle with all specs."""
        SpecRegistry.reset()
        bundle = SpecRegistry.load_all(spec_home=write_specs)
        
        assert isinstance(bundle, SpecBundle)
        assert bundle.topology == valid_topology
        assert bundle.command_policy == valid_command_policy
        assert bundle.guards == valid_guards
        assert bundle.messages == valid_messages
    
    def test_load_all_is_singleton(
        self,
        write_specs: Path
    ):
        """Happy: Multiple calls return same instance."""
        SpecRegistry.reset()
        bundle1 = SpecRegistry.load_all(spec_home=write_specs)
        bundle2 = SpecRegistry.load_all(spec_home=write_specs)
        
        assert bundle1 is bundle2
    
    def test_metadata_is_populated(
        self,
        write_specs: Path
    ):
        """Happy: Metadata contains path and hash for each spec."""
        SpecRegistry.reset()
        bundle = SpecRegistry.load_all(spec_home=write_specs)
        
        assert "topology" in bundle.metadata
        assert "command_policy" in bundle.metadata
        assert "guards" in bundle.metadata
        assert "messages" in bundle.metadata
        
        topo_meta = bundle.metadata["topology"]
        assert topo_meta.path == write_specs / "topology.yaml"
        assert len(topo_meta.sha256) == 64
        assert topo_meta.loaded_at


class TestSpecRegistryGetters:
    """Happy Path: Getter methods return correct specs."""
    
    def test_get_topology_returns_topology_spec(
        self,
        write_specs: Path,
        valid_topology: dict
    ):
        """Happy: get_topology returns topology spec."""
        SpecRegistry.reset()
        SpecRegistry.load_all(spec_home=write_specs)
        topology = SpecRegistry.get_topology()
        
        assert topology["version"] == valid_topology["version"]
        assert topology["schema"] == valid_topology["schema"]
        assert "states" in topology
    
    def test_get_command_policy_returns_policy_spec(
        self,
        write_specs: Path,
        valid_command_policy: dict
    ):
        """Happy: get_command_policy returns command policy spec."""
        SpecRegistry.reset()
        SpecRegistry.load_all(spec_home=write_specs)
        policy = SpecRegistry.get_command_policy()
        
        assert policy["version"] == valid_command_policy["version"]
        assert "commands" in policy
    
    def test_get_guards_returns_guards_spec(
        self,
        write_specs: Path,
        valid_guards: dict
    ):
        """Happy: get_guards returns guards spec."""
        SpecRegistry.reset()
        SpecRegistry.load_all(spec_home=write_specs)
        guards = SpecRegistry.get_guards()
        
        assert guards["version"] == valid_guards["version"]
        assert "guards" in guards
    
    def test_get_messages_returns_messages_spec(
        self,
        write_specs: Path,
        valid_messages: dict
    ):
        """Happy: get_messages returns messages spec."""
        SpecRegistry.reset()
        SpecRegistry.load_all(spec_home=write_specs)
        messages = SpecRegistry.get_messages()
        
        assert messages["version"] == valid_messages["version"]
        assert "schema" in messages


class TestSpecRegistryMissingSpec:
    """Negative: Missing spec files fail with clear error."""
    
    def test_missing_topology_raises_spec_not_found(
        self,
        temp_spec_dir: Path,
        valid_command_policy: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Negative: Missing topology.yaml raises SpecNotFoundError."""
        import yaml
        
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(valid_command_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecNotFoundError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "topology" in str(exc_info.value).lower()
        assert "not found" in str(exc_info.value).lower()
    
    def test_missing_command_policy_raises_spec_not_found(
        self,
        temp_spec_dir: Path,
        valid_topology: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Negative: Missing command_policy.yaml raises SpecNotFoundError."""
        import yaml
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(valid_topology))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecNotFoundError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "command_policy" in str(exc_info.value).lower()
    
    def test_missing_guards_raises_spec_not_found(
        self,
        temp_spec_dir: Path,
        valid_topology: dict,
        valid_command_policy: dict,
        valid_messages: dict
    ):
        """Negative: Missing guards.yaml raises SpecNotFoundError."""
        import yaml
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(valid_topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(valid_command_policy))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecNotFoundError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "guards" in str(exc_info.value).lower()
    
    def test_missing_messages_raises_spec_not_found(
        self,
        temp_spec_dir: Path,
        valid_topology: dict,
        valid_command_policy: dict,
        valid_guards: dict
    ):
        """Negative: Missing messages.yaml raises SpecNotFoundError."""
        import yaml
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(valid_topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(valid_command_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecNotFoundError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "messages" in str(exc_info.value).lower()


class TestSpecRegistryInvalidYaml:
    """Negative: Invalid YAML fails with clear error."""
    
    def test_invalid_yaml_raises_validation_error(
        self,
        temp_spec_dir: Path,
        valid_command_policy: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Negative: Invalid topology.yaml raises SpecValidationError."""
        import yaml
        
        (temp_spec_dir / "topology.yaml").write_text("invalid: yaml: content: [\n  - broken")
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(valid_command_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecValidationError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "topology" in str(exc_info.value).lower()
        assert "invalid" in str(exc_info.value).lower()
    
    def test_empty_file_raises_validation_error(
        self,
        temp_spec_dir: Path,
        valid_command_policy: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Negative: Empty topology.yaml raises SpecValidationError."""
        import yaml
        
        (temp_spec_dir / "topology.yaml").write_text("")
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(valid_command_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecValidationError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "empty" in str(exc_info.value).lower()


class TestSpecRegistryStructureValidation:
    """Negative: Invalid spec structure fails with clear error."""
    
    def test_topology_missing_states_raises_validation_error(
        self,
        temp_spec_dir: Path,
        valid_command_policy: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Negative: Topology without 'states' raises SpecValidationError."""
        import yaml
        
        invalid_topology = {
            "version": 1,
            "schema": "opencode.topology.v1",
            "start_state_id": "0"
        }
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(invalid_topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(valid_command_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecValidationError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "states" in str(exc_info.value)
    
    def test_command_policy_missing_commands_raises_validation_error(
        self,
        temp_spec_dir: Path,
        valid_topology: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Negative: Command policy without 'commands' raises SpecValidationError."""
        import yaml
        
        invalid_policy = {
            "version": 1,
            "schema": "opencode.command_policy.v1"
        }
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(valid_topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(invalid_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecValidationError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "commands" in str(exc_info.value)
    
    def test_command_policy_missing_version_raises_validation_error(
        self,
        temp_spec_dir: Path,
        valid_topology: dict,
        valid_guards: dict,
        valid_messages: dict
    ):
        """Negative: Command policy without 'version' raises SpecValidationError."""
        import yaml
        
        invalid_policy = {
            "schema": "opencode.command_policy.v1",
            "commands": []
        }
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(valid_topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(invalid_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(valid_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(valid_messages))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecValidationError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "version" in str(exc_info.value)


class TestSpecRegistryCrossSpecConsistency:
    """Cross-spec consistency validation tests."""
    
    def test_command_allowed_states_reference_existing_states(
        self,
        temp_spec_dir: Path
    ):
        """Negative: Command referencing non-existent state raises SpecInconsistencyError."""
        import yaml
        
        topology = {
            "version": 1,
            "schema": "opencode.topology.v1",
            "states": [
                {"id": "6.approved", "transitions": []}
            ]
        }
        
        policy = {
            "version": 1,
            "commands": [
                {
                    "id": "cmd_test",
                    "command": "/test",
                    "allowed_in": ["6.approved", "nonexistent.state"]
                }
            ]
        }
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump({"version": 1, "guards": []}))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump({"version": 1, "schema": "x"}))
        
        SpecRegistry.reset()
        
        with pytest.raises(SpecInconsistencyError) as exc_info:
            SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert "nonexistent.state" in str(exc_info.value)
        assert "does not exist" in str(exc_info.value)
    
    def test_wildcard_allowed_states_is_valid(
        self,
        temp_spec_dir: Path
    ):
        """Happy: Command with wildcard '*' allowed_states loads successfully."""
        import yaml
        
        topology = {
            "version": 1,
            "schema": "opencode.topology.v1",
            "states": [
                {"id": "6.approved", "transitions": []}
            ]
        }
        
        policy = {
            "version": 1,
            "commands": [
                {
                    "id": "cmd_continue",
                    "command": "/continue",
                    "allowed_in": "*"
                }
            ]
        }
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump({"version": 1, "guards": []}))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump({"version": 1, "schema": "x"}))
        
        SpecRegistry.reset()
        bundle = SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert bundle.command_policy["commands"][0]["allowed_in"] == "*"


class TestSpecRegistryEdgeCases:
    """Edge Cases: Boundary conditions."""
    
    def test_reset_allows_reload(
        self,
        write_specs: Path
    ):
        """Edge: reset() allows reloading from different path."""
        import yaml
        
        SpecRegistry.reset()
        bundle1 = SpecRegistry.load_all(spec_home=write_specs)
        
        new_path = write_specs.parent / "other_specs"
        new_path.mkdir()
        (new_path / "topology.yaml").write_text(yaml.dump({"version": 1, "schema": "x", "states": []}))
        (new_path / "command_policy.yaml").write_text(yaml.dump({"version": 1, "commands": []}))
        (new_path / "guards.yaml").write_text(yaml.dump({"version": 1, "guards": []}))
        (new_path / "messages.yaml").write_text(yaml.dump({"version": 1}))
        
        SpecRegistry.reset()
        bundle2 = SpecRegistry.load_all(spec_home=new_path)
        
        assert bundle1.topology != bundle2.topology
    
    def test_spec_with_only_required_keys_loads(
        self,
        temp_spec_dir: Path
    ):
        """Edge: Specs with only required keys load successfully."""
        import yaml
        
        minimal_topology = {
            "version": 1,
            "schema": "opencode.topology.v1",
            "states": []
        }
        minimal_policy = {"version": 1, "commands": []}
        minimal_guards = {"version": 1, "guards": []}
        minimal_messages = {"version": 1}
        
        (temp_spec_dir / "topology.yaml").write_text(yaml.dump(minimal_topology))
        (temp_spec_dir / "command_policy.yaml").write_text(yaml.dump(minimal_policy))
        (temp_spec_dir / "guards.yaml").write_text(yaml.dump(minimal_guards))
        (temp_spec_dir / "messages.yaml").write_text(yaml.dump(minimal_messages))
        
        SpecRegistry.reset()
        bundle = SpecRegistry.load_all(spec_home=temp_spec_dir)
        
        assert bundle.topology["states"] == []


class TestSpecRegistryRegression:
    """Regression: Existing specs in codebase load correctly."""
    
    def test_loads_real_governance_specs(self):
        """Regression: Real governance specs load successfully."""
        SpecRegistry.reset()
        
        bundle = SpecRegistry.load_all()
        
        assert "states" in bundle.topology
        assert "commands" in bundle.command_policy
        assert "guards" in bundle.guards
        assert "schema" in bundle.messages
    
    def test_phase6_states_in_real_topology(self):
        """Regression: Phase 6 substates present in real topology."""
        SpecRegistry.reset()
        topology = SpecRegistry.get_topology()
        
        state_ids = [s["id"] for s in topology.get("states", [])]
        
        assert "6.approved" in state_ids
        assert "6.complete" in state_ids
        assert "6.execution" in state_ids
    
    def test_implement_command_in_real_policy(self):
        """Regression: /implement command present in real policy."""
        SpecRegistry.reset()
        policy = SpecRegistry.get_command_policy()
        
        commands = policy.get("commands", [])
        command_names = [c["command"] for c in commands]
        
        assert "/implement" in command_names
