from __future__ import annotations

import json

from governance.application.dto.response_envelope import GovernanceResponseEnvelope


class GovernanceRenderer:
    """Presentation facade for stable rendering entrypoint."""

    def render(self, payload: GovernanceResponseEnvelope) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
