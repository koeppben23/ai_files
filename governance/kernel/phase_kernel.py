"""Legacy compatibility bridge for `governance.kernel.phase_kernel`.

DEPRECATED: use governance_runtime.kernel.phase_kernel.
"""

from governance_runtime.kernel.phase_kernel import *  # noqa: F401,F403
from governance_runtime.kernel.phase_kernel import (  # noqa: F401
    _phase_1_5_executed,
    _select_transition,
    _deduplicate_criteria,
)
