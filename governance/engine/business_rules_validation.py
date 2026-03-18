"""Legacy compatibility bridge for engine module `business_rules_validation`.

DEPRECATED: use governance_runtime.engine.business_rules_validation.
"""

from governance_runtime.engine.business_rules_validation import *  # noqa: F401,F403
from governance_runtime.engine.business_rules_validation import (  # noqa: F401
    _validate_rule_text,
    _has_section_signal,
    _is_heading_line,
)
