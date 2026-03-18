"""Legacy compatibility bridge for `governance.infrastructure.run_summary_writer`.

DEPRECATED: use governance_runtime.infrastructure.run_summary_writer.
"""

from governance_runtime.infrastructure.run_summary_writer import *  # noqa: F401,F403
from governance_runtime.infrastructure.run_summary_writer import (  # noqa: F401
    _load_reason_remediation,
)
