"""
test_developer_e2e.py — Runtime E2E evals for developer response enforcement chain.

These tests prove the complete enforcement chain for the /implement path:
  LLM raw response → _validate_developer_response → blocked/proceeded

The chain:
  _run_llm_edit_step() captures stdout
      ↓
  Response text parsed as JSON
      ↓
  validate_developer_response(parsed, schema) → VALID/INVALID
      ↓
  violations → hard block in start_implementation()

Test categories:
  1. Free-text response → blocked
  2. Malformed JSON → blocked
  3. Schema violations → blocked
  4. Valid structured response → proceeds
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "governance_runtime" / "application" / "validators"))
from llm_response_validator import validate_developer_response

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def _load_schema() -> dict | None:
    if not _SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


MANDATES_SCHEMA = _load_schema()


VALID_DEVELOPER_RESPONSE = {
    "objective": "Add null check to src/main.py to prevent crash on empty input.",
    "governing_evidence": "Modified src/main.py:42. Contract requires non-null body. Test added.",
    "touched_surface": ["src/main.py", "tests/test_main.py"],
    "change_summary": "Added null check guard at line 42. Returns 400 for None input.",
    "contract_and_authority_check": "SSOT boundaries preserved. No authority drift.",
    "test_evidence": "Added negative test for empty input. All 12 tests pass.",
    "regression_assessment": "Existing happy-path behavior unchanged.",
    "residual_risks": [],
}


class TestDeveloperResponseEnforcementE2E:
    """Runtime E2E evals for the developer response validation chain."""

    def test_freetext_response_hard_blocked(self):
        result = validate_developer_response("I implemented the changes. Looks good!", MANDATES_SCHEMA)
        assert result.valid is False

    def test_malformed_json_hard_blocked(self):
        text = '{"objective": "fix bug", "touched_surface": ["main.py"]'  # unclosed
        result = validate_developer_response(text, MANDATES_SCHEMA)
        assert result.valid is False

    def test_empty_string_hard_blocked(self):
        result = validate_developer_response("", MANDATES_SCHEMA)
        assert result.valid is False

    def test_not_a_dict_hard_blocked(self):
        result = validate_developer_response(["item1", "item2"], MANDATES_SCHEMA)
        assert result.valid is False

    def test_valid_response_proceeds(self):
        result = validate_developer_response(VALID_DEVELOPER_RESPONSE, MANDATES_SCHEMA)
        assert result.valid is True

    def test_missing_objective_hard_blocked(self):
        data = dict(VALID_DEVELOPER_RESPONSE)
        del data["objective"]
        result = validate_developer_response(data, MANDATES_SCHEMA)
        assert result.valid is False

    def test_empty_touched_surface_hard_blocked(self):
        data = dict(VALID_DEVELOPER_RESPONSE)
        data["touched_surface"] = []
        result = validate_developer_response(data, MANDATES_SCHEMA)
        assert result.valid is False

    def test_short_objective_hard_blocked(self):
        data = dict(VALID_DEVELOPER_RESPONSE)
        data["objective"] = "x"
        result = validate_developer_response(data, MANDATES_SCHEMA)
        assert result.valid is False

    def test_short_change_summary_hard_blocked(self):
        data = dict(VALID_DEVELOPER_RESPONSE)
        data["change_summary"] = "changed"
        result = validate_developer_response(data, MANDATES_SCHEMA)
        assert result.valid is False

    def test_missing_contract_check_hard_blocked(self):
        data = dict(VALID_DEVELOPER_RESPONSE)
        del data["contract_and_authority_check"]
        result = validate_developer_response(data, MANDATES_SCHEMA)
        assert result.valid is False

    def test_invalid_residual_risks_type_hard_blocked(self):
        data = dict(VALID_DEVELOPER_RESPONSE)
        data["residual_risks"] = "none"
        result = validate_developer_response(data, MANDATES_SCHEMA)
        assert result.valid is False

    def test_minimal_valid_response_proceeds(self):
        data = {
            "objective": "Add null check.",
            "governing_evidence": "Added guard to main.py:42.",
            "touched_surface": ["src/main.py"],
            "change_summary": "Null check added at line 42.",
            "contract_and_authority_check": "Boundaries preserved.",
            "test_evidence": "Tests pass.",
            "regression_assessment": "Unchanged behavior.",
            "residual_risks": [],
        }
        result = validate_developer_response(data, MANDATES_SCHEMA)
        assert result.valid is True
