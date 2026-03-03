"""Tests for ensure_opencode_json() — OpenCode Desktop config generation.

Validates:
- Fresh install creates opencode.json with correct instructions array
- Existing file is merged non-destructively (user keys preserved)
- Missing instruction entries are added to existing array
- Idempotent: re-running does not duplicate entries
- Relative paths match the 3 core governance files
- Dry-run mode does not write to disk
- Corrupt/non-dict existing file is handled gracefully

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from install import (
    OPENCODE_JSON_NAME,
    OPENCODE_INSTRUCTIONS,
    ensure_opencode_json,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def config_root(tmp_path: Path) -> Path:
    """Provide a clean config_root directory."""
    cr = tmp_path / "config_root"
    cr.mkdir()
    return cr


def _read_opencode_json(config_root: Path) -> dict:
    """Read and parse opencode.json from config_root."""
    target = config_root / OPENCODE_JSON_NAME
    return json.loads(target.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fresh install
# ---------------------------------------------------------------------------

class TestFreshInstall:
    def test_creates_file(self, config_root: Path) -> None:
        """opencode.json is created when it doesn't exist."""
        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "created"
        assert (config_root / OPENCODE_JSON_NAME).exists()

    def test_correct_instructions(self, config_root: Path) -> None:
        """Created file has exactly the 3 core instruction entries."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "instructions" in data
        assert data["instructions"] == list(OPENCODE_INSTRUCTIONS)

    def test_instructions_are_relative_paths(self, config_root: Path) -> None:
        """All instruction entries are relative paths starting with 'commands/'."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        for entry in data["instructions"]:
            assert entry.startswith("commands/"), f"Expected relative path, got: {entry}"

    def test_three_core_files(self, config_root: Path) -> None:
        """The 3 instruction entries are master.md, rules.md, SESSION_STATE_SCHEMA.md."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        basenames = [entry.split("/")[-1] for entry in data["instructions"]]
        assert "master.md" in basenames
        assert "rules.md" in basenames
        assert "SESSION_STATE_SCHEMA.md" in basenames

    def test_valid_json_with_newline(self, config_root: Path) -> None:
        """Written file is valid JSON and ends with a newline."""
        ensure_opencode_json(config_root, dry_run=False)
        raw = (config_root / OPENCODE_JSON_NAME).read_text(encoding="utf-8")
        assert raw.endswith("\n")
        json.loads(raw)  # Should not raise


# ---------------------------------------------------------------------------
# Merge with existing
# ---------------------------------------------------------------------------

class TestMergeExisting:
    def test_preserves_user_keys(self, config_root: Path) -> None:
        """Existing user keys are not removed or altered."""
        existing = {
            "theme": "dark",
            "editor": "vim",
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "merged"
        data = _read_opencode_json(config_root)
        assert data["theme"] == "dark"
        assert data["editor"] == "vim"
        assert "instructions" in data

    def test_adds_missing_entries(self, config_root: Path) -> None:
        """Missing instruction entries are appended to existing array."""
        existing = {
            "instructions": ["commands/master.md"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "commands/master.md" in data["instructions"]
        assert "commands/rules.md" in data["instructions"]
        assert "commands/SESSION_STATE_SCHEMA.md" in data["instructions"]

    def test_preserves_user_instruction_entries(self, config_root: Path) -> None:
        """User's own instruction entries are not removed."""
        existing = {
            "instructions": ["my-custom-prompt.md", "commands/master.md"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "my-custom-prompt.md" in data["instructions"]

    def test_preserves_order(self, config_root: Path) -> None:
        """Existing entries keep their order; new entries are appended."""
        existing = {
            "instructions": ["first.md", "commands/master.md"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert data["instructions"][0] == "first.md"
        assert data["instructions"][1] == "commands/master.md"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_no_duplicate_entries(self, config_root: Path) -> None:
        """Running twice does not duplicate instruction entries."""
        ensure_opencode_json(config_root, dry_run=False)
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert len(data["instructions"]) == len(OPENCODE_INSTRUCTIONS)

    def test_merge_idempotent(self, config_root: Path) -> None:
        """Merge status on second run still works correctly."""
        ensure_opencode_json(config_root, dry_run=False)
        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "merged"
        data = _read_opencode_json(config_root)
        assert data["instructions"] == list(OPENCODE_INSTRUCTIONS)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_fresh_dry_run_no_file(self, config_root: Path) -> None:
        """Dry run on fresh install does not create the file."""
        result = ensure_opencode_json(config_root, dry_run=True)
        assert result["status"] == "planned-create"
        assert not (config_root / OPENCODE_JSON_NAME).exists()

    def test_merge_dry_run_no_change(self, config_root: Path) -> None:
        """Dry run merge does not alter the existing file."""
        existing = {"theme": "dark"}
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")
        original_content = target.read_text(encoding="utf-8")

        result = ensure_opencode_json(config_root, dry_run=True)
        assert result["status"] == "planned-merge"
        assert target.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_corrupt_existing_file(self, config_root: Path) -> None:
        """Non-JSON content in existing file is handled gracefully."""
        target = config_root / OPENCODE_JSON_NAME
        target.write_text("not json!", encoding="utf-8")

        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "merged"
        data = _read_opencode_json(config_root)
        assert data["instructions"] == list(OPENCODE_INSTRUCTIONS)

    def test_non_dict_existing_file(self, config_root: Path) -> None:
        """Existing file containing a JSON array (not object) is handled."""
        target = config_root / OPENCODE_JSON_NAME
        target.write_text('["just", "an", "array"]', encoding="utf-8")

        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "merged"
        data = _read_opencode_json(config_root)
        assert data["instructions"] == list(OPENCODE_INSTRUCTIONS)

    def test_instructions_key_is_not_list(self, config_root: Path) -> None:
        """If instructions is a non-list value, it's replaced with the correct array."""
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps({"instructions": "bad"}), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert isinstance(data["instructions"], list)
        assert len(data["instructions"]) == len(OPENCODE_INSTRUCTIONS)

    def test_nested_parent_dirs_created(self, config_root: Path) -> None:
        """If config_root doesn't exist yet, parent directories are created."""
        deep_root = config_root / "deep" / "nested" / "config"
        result = ensure_opencode_json(deep_root, dry_run=False)
        assert result["status"] == "created"
        assert (deep_root / OPENCODE_JSON_NAME).exists()
