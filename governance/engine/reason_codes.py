"""Backward-compatible reason code import surface.

.. deprecated::
    Use governance_runtime.engine.reason_codes instead.
    This module will be removed in a future release.

Canonical constants live in `governance_runtime.engine.reason_codes`.
This module re-exports everything for legacy import paths.
"""

from __future__ import annotations

from governance_runtime.engine.reason_codes import *  # noqa: F401,F403
