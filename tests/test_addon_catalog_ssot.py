"""Regression: addon catalog SSOT module is importable and non-empty."""
from __future__ import annotations

import pytest

from governance.addon_catalog import (
    ALLOWED_CAPABILITIES,
    ALLOWED_CLASSES,
    ALLOWED_EVIDENCE_KINDS,
    ALLOWED_SIGNAL_KEYS,
    ALLOWED_SURFACES,
)


@pytest.mark.governance
def test_all_constants_are_frozenset():
    for name, val in [
        ("ALLOWED_CAPABILITIES", ALLOWED_CAPABILITIES),
        ("ALLOWED_CLASSES", ALLOWED_CLASSES),
        ("ALLOWED_EVIDENCE_KINDS", ALLOWED_EVIDENCE_KINDS),
        ("ALLOWED_SIGNAL_KEYS", ALLOWED_SIGNAL_KEYS),
        ("ALLOWED_SURFACES", ALLOWED_SURFACES),
    ]:
        assert isinstance(val, frozenset), f"{name} must be frozenset"
        assert len(val) > 0, f"{name} must be non-empty"


@pytest.mark.governance
def test_capabilities_and_surfaces_have_no_unexpected_overlap():
    overlap = ALLOWED_CAPABILITIES & ALLOWED_SURFACES
    assert overlap <= {"governance_docs"}, f"unexpected overlap: {overlap - {'governance_docs'}}"
