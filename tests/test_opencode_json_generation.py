"""Tests for ensure_opencode_json() — OpenCode Desktop config generation.

Validates:
- Fresh install creates opencode.json with correct command_files array
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
    OPENCODE_COMMAND_FILES,
    OPENCODE_PLUGIN_KEY,
    OPENCODE_PLUGIN_RELATIVE,
    ensure_opencode_json,
    remove_installer_plugin_from_opencode_json,
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

    def test_correct_command_files(self, config_root: Path) -> None:
        """Created file has exactly the 3 core instruction entries."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "command_files" in data
        assert data["command_files"] == list(OPENCODE_COMMAND_FILES)

    def test_adds_plugin_entry(self, config_root: Path) -> None:
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        expected_plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()
        assert data[OPENCODE_PLUGIN_KEY] == [expected_plugin_uri]

    def test_command_files_are_relative_paths(self, config_root: Path) -> None:
        """All instruction entries are relative paths starting with 'commands/'."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        for entry in data["command_files"]:
            assert entry.startswith("commands/"), f"Expected relative path, got: {entry}"

    def test_three_core_files(self, config_root: Path) -> None:
        """The 8 command file entries are the slash command files."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        basenames = [entry.split("/")[-1] for entry in data["command_files"]]
        assert "continue.md" in basenames
        assert "plan.md" in basenames
        assert "implement.md" in basenames

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
        assert "command_files" in data

    def test_plugin_merge_is_minimal_invasive(self, config_root: Path) -> None:
        existing = {
            "command_files": ["commands/master.md"],
            OPENCODE_PLUGIN_KEY: ["file:///custom/other-plugin.mjs"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        expected_plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()
        assert data[OPENCODE_PLUGIN_KEY][0] == "file:///custom/other-plugin.mjs"
        assert expected_plugin_uri in data[OPENCODE_PLUGIN_KEY]

    def test_adds_missing_entries(self, config_root: Path) -> None:
        """Missing command file entries are appended to existing array."""
        existing = {
            "command_files": ["commands/master.md"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "commands/master.md" in data["command_files"]
        assert "commands/continue.md" in data["command_files"]
        assert "commands/plan.md" in data["command_files"]

    def test_preserves_user_instruction_entries(self, config_root: Path) -> None:
        """User's own instruction entries are not removed."""
        existing = {
            "command_files": ["my-custom-prompt.md", "commands/master.md"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "my-custom-prompt.md" in data["command_files"]

    def test_preserves_order(self, config_root: Path) -> None:
        """Existing entries keep their order; new entries are appended."""
        existing = {
            "command_files": ["first.md", "commands/master.md"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert data["command_files"][0] == "first.md"
        assert data["command_files"][1] == "commands/master.md"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_no_duplicate_entries(self, config_root: Path) -> None:
        """Running twice does not duplicate instruction entries."""
        ensure_opencode_json(config_root, dry_run=False)
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert len(data["command_files"]) == len(OPENCODE_COMMAND_FILES)

    def test_merge_idempotent(self, config_root: Path) -> None:
        """Merge status on second run still works correctly."""
        ensure_opencode_json(config_root, dry_run=False)
        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "merged"
        data = _read_opencode_json(config_root)
        assert data["command_files"] == list(OPENCODE_COMMAND_FILES)

    def test_plugin_entry_not_duplicated(self, config_root: Path) -> None:
        ensure_opencode_json(config_root, dry_run=False)
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        expected_plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()
        assert data[OPENCODE_PLUGIN_KEY].count(expected_plugin_uri) == 1


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
        assert data["command_files"] == list(OPENCODE_COMMAND_FILES)

    def test_non_dict_existing_file(self, config_root: Path) -> None:
        """Existing file containing a JSON array (not object) is handled."""
        target = config_root / OPENCODE_JSON_NAME
        target.write_text('["just", "an", "array"]', encoding="utf-8")

        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "merged"
        data = _read_opencode_json(config_root)
        assert data["command_files"] == list(OPENCODE_COMMAND_FILES)

    def test_command_files_key_is_not_list(self, config_root: Path) -> None:
        """If command_files is a non-list value, it's replaced with the correct array."""
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps({"command_files": "bad"}), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert isinstance(data["command_files"], list)
        assert len(data["command_files"]) == len(OPENCODE_COMMAND_FILES)

    def test_nested_parent_dirs_created(self, config_root: Path) -> None:
        """If config_root doesn't exist yet, parent directories are created."""
        deep_root = config_root / "deep" / "nested" / "config"
        result = ensure_opencode_json(deep_root, dry_run=False)
        assert result["status"] == "created"
        assert (deep_root / OPENCODE_JSON_NAME).exists()


class TestPluginCleanup:
    def test_cleanup_removes_only_installer_plugin_entry(self, config_root: Path) -> None:
        ensure_opencode_json(config_root, dry_run=False)
        target = config_root / OPENCODE_JSON_NAME
        payload = _read_opencode_json(config_root)
        payload[OPENCODE_PLUGIN_KEY].insert(0, "file:///custom/keep.mjs")
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        result = remove_installer_plugin_from_opencode_json(config_root, dry_run=False)
        assert result["status"] == "removed-plugin"

        data = _read_opencode_json(config_root)
        expected_plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()
        assert "file:///custom/keep.mjs" in data[OPENCODE_PLUGIN_KEY]
        assert expected_plugin_uri not in data[OPENCODE_PLUGIN_KEY]
