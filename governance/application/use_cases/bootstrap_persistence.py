"""Legacy compatibility bridge for `governance.application.use_cases.bootstrap_persistence`.

DEPRECATED: use governance_runtime.application.use_cases.bootstrap_persistence.
"""

from governance_runtime.application.use_cases.bootstrap_persistence import *  # noqa: F401,F403
from governance_runtime.application.use_cases.bootstrap_persistence import (  # noqa: F401
    _is_valid_pointer_payload,
    _session_state_payload,
)
