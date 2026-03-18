"""Legacy compatibility bridge for engine module `response_contract`.

DEPRECATED: use governance_runtime.engine.response_contract.
"""

from governance_runtime.engine.response_contract import *  # noqa: F401,F403
from governance_runtime.engine.response_contract import (  # noqa: F401
    _apply_resolved_intent_policy,
    _validate_output_class_for_phase,
)
