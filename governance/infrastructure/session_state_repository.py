"""Infrastructure repository compatibility surface.

Canonical implementation remains in `governance.engine.session_state_repository`.
"""

from governance.engine.session_state_repository import (  # noqa: F401
    SessionStateMigrationResult,
    SessionStateRepository,
    migrate_session_state_document,
)
