"""Infrastructure loader for phase_api.yaml output policy data.

Bridges the domain-layer output policy resolver with the filesystem.
The domain layer (phase_state_machine.py) defines pure data structures and
resolution logic; this module provides the I/O to load phase_api.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


def _candidate_phase_api_paths() -> list[Path]:
    """Resolve ordered candidates for phase_api.yaml.

    Priority:
    1) Runtime spec home (binding evidence)
    2) Runtime commands home (legacy fallback)
    3) OPENCODE_LOCAL_ROOT/governance_spec/phase_api.yaml
    4) Repo SSOT fallback (governance_spec/phase_api.yaml)
    5) Legacy repo root fallback (phase_api.yaml)
    """

    candidates: list[Path] = []

    try:
        from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver

        binding_resolver = BindingEvidenceResolver()
        evidence = binding_resolver.resolve(mode="kernel")
        if evidence.spec_home is not None:
            candidates.append(evidence.spec_home / "phase_api.yaml")
        if evidence.commands_home is not None:
            candidates.append(evidence.commands_home / "phase_api.yaml")
    except Exception:
        pass

    env_local_root = os.environ.get("OPENCODE_LOCAL_ROOT", "").strip()
    if env_local_root:
        candidates.append(Path(env_local_root).expanduser() / "governance_spec" / "phase_api.yaml")

    env_commands_home = os.environ.get("COMMANDS_HOME", "").strip()
    if env_commands_home:
        candidates.append(Path(env_commands_home).expanduser() / "phase_api.yaml")

    env_config_root = os.environ.get("OPENCODE_CONFIG_ROOT", "").strip()
    if env_config_root:
        candidates.append(Path(env_config_root).expanduser() / "commands" / "phase_api.yaml")

    candidates.append(Path.home() / ".config" / "opencode" / "commands" / "phase_api.yaml")
    candidates.append(Path.home() / ".opencode" / "commands" / "phase_api.yaml")

    search = Path(__file__).parent
    for _ in range(10):
        candidates.append(search / "governance_spec" / "phase_api.yaml")
        candidates.append(search / "phase_api.yaml")
        parent = search.parent
        if parent == search:
            break
        search = parent

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        token = str(path)
        if token in seen:
            continue
        seen.add(token)
        unique.append(path)
    return unique


def _find_phase_api_yaml() -> Path | None:
    for candidate in _candidate_phase_api_paths():
        if candidate.is_file():
            return candidate
    return None


def load_phase_api_phases() -> list[Mapping[str, Any]]:
    """Load phases list from phase_api.yaml for output policy resolution."""
    try:
        import yaml
    except ImportError:
        return []

    path = _find_phase_api_yaml()
    if path is None:
        return []

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        return []
    phases = raw.get("phases", [])
    return phases if isinstance(phases, list) else []


def configure_phase_output_policy_loader() -> None:
    """Register the filesystem-based loader with the domain layer."""
    from governance_runtime.domain.phase_state_machine import set_phase_api_loader
    set_phase_api_loader(load_phase_api_phases)
