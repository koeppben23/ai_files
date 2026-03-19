"""Receipt builders."""

from __future__ import annotations

import hashlib


def build_presentation_receipt(
    *,
    receipt_type: str,
    requirement_scope: str,
    content_source: str,
    rendered_at: str,
    render_event_id: str,
    gate: str,
    session_id: str,
    state_revision: str,
    source_command: str,
) -> dict[str, str]:
    digest = hashlib.sha256(str(content_source).encode("utf-8")).hexdigest()
    return {
        "receipt_type": str(receipt_type),
        "requirement_scope": str(requirement_scope),
        "content_digest": digest,
        "rendered_at": str(rendered_at),
        "render_event_id": str(render_event_id),
        "gate": str(gate),
        "session_id": str(session_id),
        "state_revision": str(state_revision),
        "source_command": str(source_command),
        # Backward compatibility aliases used by existing logic/tests
        "digest": digest,
        "presented_at": str(rendered_at),
        "materialization_event_id": str(render_event_id),
        "contract": "guided-ui.v1",
    }
