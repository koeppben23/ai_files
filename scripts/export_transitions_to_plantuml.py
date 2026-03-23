"""Export governance transitions to PlantUML format.

Usage:
    python scripts/export_transitions_to_plantuml.py > governance_runtime/docs/state_machines/governance.puml
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from governance_runtime.application.services.transition_model import (
    PHASE4_TRANSITIONS,
    PHASE5_TRANSITIONS,
    PHASE6_TRANSITIONS,
    TransitionTable,
)


def _fmt_node(name: str | None) -> str:
    """Format a state node for PlantUML.

    Args:
        name: State name, or None for initial/final pseudostate.

    Returns:
        PlantUML node string: [name] for states, [*] for pseudostates.
    """
    return f"[{name}]" if name else "[*]"


def export_transition_table(table: TransitionTable, phase_name: str) -> list[str]:
    """Export a TransitionTable to PlantUML format.

    Args:
        table: The transition table to export.
        phase_name: Name for the phase (e.g., "Phase 4").

    Returns:
        List of PlantUML lines.
    """
    lines = []
    lines.append(f'    package "{phase_name}" {{')

    # Collect unique states (exclude pseudostates)
    states = set()
    for t in table.transitions:
        if t.source_gate:
            states.add(t.source_gate)
        if t.target_gate:
            states.add(t.target_gate)

    # Add state nodes
    for state in sorted(states):
        lines.append(f'        [{state}]')

    # Add transitions
    for t in table.transitions:
        source = _fmt_node(t.source_gate)
        target = _fmt_node(t.target_gate)
        label = t.label_template.replace("{command}", t.command)
        guard_info = f" ({t.reason})" if t.reason else ""
        lines.append(f'        {source} --> {target} : {label}{guard_info}')

    lines.append('    }')
    return lines


def main() -> None:
    """Main entry point."""
    lines = []
    lines.append("@startuml governance")
    lines.append("")
    lines.append("title Governance State Machine")
    lines.append("")

    # Phase 4
    lines.extend(export_transition_table(PHASE4_TRANSITIONS, "Phase 4 - Ticket/Plan"))
    lines.append("")

    # Phase 5
    lines.extend(export_transition_table(PHASE5_TRANSITIONS, "Phase 5 - Architecture Review"))
    lines.append("")

    # Phase 6
    lines.extend(export_transition_table(PHASE6_TRANSITIONS, "Phase 6 - Post Flight"))
    lines.append("")

    lines.append("@enduml")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
