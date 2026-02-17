from __future__ import annotations

from pathlib import Path

import pytest

from diagnostics import schema_selfcheck


@pytest.mark.governance
def test_reason_payload_schema_selfcheck_passes():
    # Executes shipped selfcheck against repository diagnostics tree.
    rc = schema_selfcheck.main()
    assert rc == 0


@pytest.mark.governance
def test_reason_payload_registry_exists_at_expected_path():
    root = Path(__file__).resolve().parents[1]
    assert (root / "diagnostics" / "reason_codes.registry.json").exists()
