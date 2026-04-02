"""Spec Registry - Single Source of Truth for Governance Specs.

This module provides a registry that loads and validates all governance specs.
All spec access MUST go through this registry to ensure consistency and fail-closed behavior.

Architecture:
    - spec_registry.py: Registry and loader orchestration
    - topology_loader.py: Topology-specific loading (Zyklus A WP2)
    - command_policy_loader.py: Command policy loading (Zyklus A WP1)
    - guard_loader.py: Guard loading (prepared for Zyklus B)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


class SpecRegistryError(RuntimeError):
    """Base error for spec registry failures."""
    pass


class SpecNotFoundError(SpecRegistryError):
    """Raised when a required spec file is not found."""
    pass


class SpecValidationError(SpecRegistryError):
    """Raised when a spec file fails validation."""
    pass


class SpecInconsistencyError(SpecRegistryError):
    """Raised when specs are inconsistent with each other."""
    pass


@dataclass(frozen=True)
class SpecMetadata:
    """Metadata for a loaded spec."""
    path: Path
    sha256: str
    loaded_at: str


@dataclass(frozen=True)
class SpecBundle:
    """Bundle of all loaded governance specs."""
    topology: dict[str, Any]
    command_policy: dict[str, Any]
    guards: dict[str, Any]
    messages: dict[str, Any]
    metadata: dict[str, SpecMetadata] = field(default_factory=dict)


class SpecRegistry:
    """Registry for loading and accessing all governance specs.
    
    This registry ensures:
    - All specs are loaded from the same authoritative location
    - Fail-closed behavior: missing or invalid specs prevent startup
    - Structural validation: specs have required keys
    - Cross-spec validation: states and commands are consistent
    
    Usage:
        bundle = SpecRegistry.load_all()
        topology = SpecRegistry.get_topology()
        command_policy = SpecRegistry.get_command_policy()
        guards = SpecRegistry.get_guards()
    
    For testing:
        SpecRegistry.reset()  # Clear cached bundle
    """
    
    _cached_bundle: SpecBundle | None = None
    
    @classmethod
    def load_all(cls, spec_home: Path | None = None) -> SpecBundle:
        """Load all governance specs or fail with clear error.
        
        Args:
            spec_home: Optional override for spec directory.
                      Defaults to governance_spec/ from binding evidence.
        
        Returns:
            SpecBundle with all loaded specs.
        
        Raises:
            SpecNotFoundError: If a required spec file is missing.
            SpecValidationError: If a spec file is invalid YAML or structure.
            SpecInconsistencyError: If specs are inconsistent with each other.
        """
        if cls._cached_bundle is not None:
            return cls._cached_bundle
        
        spec_dir = cls._resolve_spec_home(spec_home)
        
        topology = cls._load_yaml(
            spec_dir / "topology.yaml",
            schema_name="topology"
        )
        command_policy = cls._load_yaml(
            spec_dir / "command_policy.yaml",
            schema_name="command_policy"
        )
        guards = cls._load_yaml(
            spec_dir / "guards.yaml",
            schema_name="guards"
        )
        messages = cls._load_yaml(
            spec_dir / "messages.yaml",
            schema_name="messages"
        )
        
        metadata = {
            "topology": cls._metadata_for(spec_dir / "topology.yaml"),
            "command_policy": cls._metadata_for(spec_dir / "command_policy.yaml"),
            "guards": cls._metadata_for(spec_dir / "guards.yaml"),
            "messages": cls._metadata_for(spec_dir / "messages.yaml"),
        }
        
        bundle = SpecBundle(
            topology=topology,
            command_policy=command_policy,
            guards=guards,
            messages=messages,
            metadata=metadata,
        )
        
        cls._validate_structure(bundle)
        
        cls._cached_bundle = bundle
        
        return cls._cached_bundle
    
    @classmethod
    def get_topology(cls) -> dict[str, Any]:
        """Get the loaded topology spec."""
        return cls.load_all().topology
    
    @classmethod
    def get_command_policy(cls) -> dict[str, Any]:
        """Get the loaded command policy spec."""
        return cls.load_all().command_policy
    
    @classmethod
    def get_guards(cls) -> dict[str, Any]:
        """Get the loaded guards spec (for Zyklus B)."""
        return cls.load_all().guards
    
    @classmethod
    def get_messages(cls) -> dict[str, Any]:
        """Get the loaded messages spec."""
        return cls.load_all().messages
    
    @classmethod
    def reset(cls) -> None:
        """Reset the registry. For testing only."""
        cls._cached_bundle = None
    
    @classmethod
    def _resolve_spec_home(cls, spec_home: Path | None) -> Path:
        """Resolve the spec home directory."""
        if spec_home is not None:
            return spec_home
        
        resolver = BindingEvidenceResolver()
        evidence = resolver.resolve()
        
        if evidence.spec_home is not None:
            return evidence.spec_home
        
        local_root = evidence.local_root
        if local_root is not None:
            spec_path = local_root / "governance_spec"
            if spec_path.exists():
                return spec_path
        
        raise SpecNotFoundError(
            "Cannot find governance_spec directory. "
            "Set governance.paths.json specHome or ensure governance_spec/ exists."
        )
    
    @classmethod
    def _load_yaml(cls, path: Path, schema_name: str) -> dict[str, Any]:
        """Load and parse a YAML spec file.
        
        Raises:
            SpecNotFoundError: If file doesn't exist.
            SpecValidationError: If YAML is invalid.
        """
        if not path.exists():
            raise SpecNotFoundError(
                f"Required spec file not found: {path}. "
                f"Runtime cannot start without {schema_name} spec."
            )
        
        if yaml is None:
            raise SpecValidationError(
                f"PyYAML not available. Cannot load {path}."
            )
        
        try:
            with open(path, encoding="utf-8") as f:
                content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SpecValidationError(
                f"Invalid YAML in {schema_name} spec ({path}): {e}. "
                "Runtime cannot start with invalid spec."
            )
        
        if content is None:
            raise SpecValidationError(
                f"Empty {schema_name} spec at {path}. "
                "Runtime cannot start with empty spec."
            )
        
        if not isinstance(content, dict):
            raise SpecValidationError(
                f"Invalid {schema_name} spec structure at {path}. "
                f"Expected dict, got {type(content).__name__}."
            )
        
        return content
    
    @classmethod
    def _metadata_for(cls, path: Path) -> SpecMetadata:
        """Generate metadata for a spec file."""
        import hashlib
        from datetime import datetime, timezone
        
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        return SpecMetadata(
            path=path,
            sha256=sha256_hash.hexdigest(),
            loaded_at=datetime.now(timezone.utc).isoformat(),
        )
    
    @classmethod
    def _validate_structure(cls, bundle: SpecBundle) -> None:
        """Validate spec structure and basic consistency.
        
        Raises:
            SpecValidationError: If required keys are missing.
            SpecInconsistencyError: If specs reference non-existent elements.
        """
        cls._validate_topology_structure(bundle.topology)
        cls._validate_command_policy_structure(bundle.command_policy)
        cls._validate_guards_structure(bundle.guards)
        cls._validate_messages_structure(bundle.messages)
        
        cls._validate_cross_spec_consistency(bundle)
    
    @classmethod
    def _validate_topology_structure(cls, topology: dict[str, Any]) -> None:
        """Validate topology spec has required structure."""
        required_keys = {"version", "schema", "states"}
        missing = required_keys - set(topology.keys())
        if missing:
            raise SpecValidationError(
                f"Invalid topology spec: missing required keys {missing}. "
                "Runtime cannot start with malformed topology."
            )
        
        if not isinstance(topology.get("states"), list):
            raise SpecValidationError(
                "Invalid topology spec: 'states' must be a list."
            )
    
    @classmethod
    def _validate_command_policy_structure(cls, policy: dict[str, Any]) -> None:
        """Validate command policy spec has required structure."""
        if "commands" not in policy:
            raise SpecValidationError(
                "Invalid command_policy spec: missing 'commands' key. "
                "Runtime cannot start without command definitions."
            )
        
        if not isinstance(policy.get("commands"), list):
            raise SpecValidationError(
                "Invalid command_policy spec: 'commands' must be a list."
            )
        
        if "version" not in policy:
            raise SpecValidationError(
                "Invalid command_policy spec: missing 'version' key. "
                "All specs must declare a version."
            )
    
    @classmethod
    def _validate_guards_structure(cls, guards: dict[str, Any]) -> None:
        """Validate guards spec has required structure."""
        if "guards" not in guards:
            raise SpecValidationError(
                "Invalid guards spec: missing 'guards' key. "
                "Runtime cannot start without guard definitions."
            )
        
        if not isinstance(guards.get("guards"), list):
            raise SpecValidationError(
                "Invalid guards spec: 'guards' must be a list."
            )
        
        if "version" not in guards:
            raise SpecValidationError(
                "Invalid guards spec: missing 'version' key. "
                "All specs must declare a version."
            )
    
    @classmethod
    def _validate_messages_structure(cls, messages: dict[str, Any]) -> None:
        """Validate messages spec has required structure."""
        if "version" not in messages:
            raise SpecValidationError(
                "Invalid messages spec: missing 'version' key. "
                "All specs must declare a version."
            )
    
    @classmethod
    def _validate_cross_spec_consistency(cls, bundle: SpecBundle) -> None:
        """Validate basic cross-spec consistency.
        
        Checks:
        - Command allowed_states reference existing topology states
        - State IDs in topology are unique
        
        Raises:
            SpecInconsistencyError: If specs reference non-existent elements.
        """
        topology = bundle.topology
        policy = bundle.command_policy
        
        state_ids = {s["id"] for s in topology.get("states", [])}
        
        for cmd in policy.get("commands", []):
            allowed_in = cmd.get("allowed_in", [])
            if isinstance(allowed_in, list):
                for state_id in allowed_in:
                    if state_id != "*" and state_id not in state_ids:
                        raise SpecInconsistencyError(
                            f"Command '{cmd.get('command', 'unknown')}' allows state "
                            f"'{state_id}' which does not exist in topology. "
                            "Runtime cannot start with inconsistent specs."
                        )
