"""Legacy compatibility bridge for `governance.application.use_cases.session_state_helpers`.

DEPRECATED: use governance_runtime.application.use_cases.session_state_helpers.
"""

from governance_runtime.application.use_cases.session_state_helpers import *  # noqa: F401,F403
from governance_runtime.application.use_cases.session_state_helpers import (  # noqa: F401
    _auto_propagate_gates,
)
