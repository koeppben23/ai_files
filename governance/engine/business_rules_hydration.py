"""Legacy compatibility bridge for engine module `business_rules_hydration`.

DEPRECATED: use governance_runtime.engine.business_rules_hydration.
"""

from governance_runtime.engine.business_rules_hydration import *  # noqa: F401,F403
from governance_runtime.engine.business_rules_hydration import (  # noqa: F401
    _aggregate_discovery_outcome_counts,
    _build_code_extraction_counters,
)
