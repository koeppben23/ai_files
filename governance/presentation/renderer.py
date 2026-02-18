from __future__ import annotations

from typing import Any

from governance.render.response_formatter import render_response


class GovernanceRenderer:
    """Presentation facade for stable rendering entrypoint."""

    def render(self, payload: dict[str, Any]) -> str:
        return render_response(payload)
