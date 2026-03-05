"""Infrastructure loader for phase_api.yaml output policy data.

Bridges the domain-layer output policy resolver with the filesystem.
The domain layer (phase_state_machine.py) defines pure data structures and
resolution logic; this module provides the I/O to load phase_api.yaml.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def _find_phase_api_yaml() -> Path | None:
    """Locate phase_api.yaml by searching upward from this file."""
    search = Path(__file__).parent
    for _ in range(10):
        candidate = search / "phase_api.yaml"
        if candidate.exists():
            return candidate
        parent = search.parent
        if parent == search:
            break
        search = parent
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
    from governance.domain.phase_state_machine import set_phase_api_loader
    set_phase_api_loader(load_phase_api_phases)
