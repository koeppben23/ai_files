from __future__ import annotations

import pytest

from governance_runtime.presentation.renderer import GovernanceRenderer


@pytest.mark.governance
def test_renderer_facade_returns_string_payload():
    renderer = GovernanceRenderer()
    output = renderer.render(
        {
            "phase": "1.1-Bootstrap",
            "active_gate": "Gate",
            "next_action": {"command": "opencode-governance-bootstrap"},
            "reason_code": "none",
        }
    )
    assert isinstance(output, str)
