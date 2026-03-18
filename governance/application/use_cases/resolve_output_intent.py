"""Legacy compatibility bridge for `governance.application.use_cases.resolve_output_intent`.

DEPRECATED: use governance_runtime.application.use_cases.resolve_output_intent.
"""

from governance_runtime.application.use_cases.resolve_output_intent import *  # noqa: F401,F403
from governance_runtime.application.use_cases.resolve_output_intent import (  # noqa: F401
    _RESTRICTIVE_FALLBACK_POLICY,
    _TOKEN_INTENT_MAP,
    _infer_primary_intent,
)
