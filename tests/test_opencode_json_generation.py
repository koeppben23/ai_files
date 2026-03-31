"""Tests for ensure_opencode_json() — OpenCode Desktop instructions-based config generation.

Validates:
- Fresh install creates opencode.json with ``instructions`` array (NOT ``command_files``)
- Existing ``command_files`` key is actively removed on merge
- User keys are preserved on merge
- Missing instruction entries are added to existing array
- Idempotent: re-running does not duplicate entries
- Dry-run mode does not write to disk
- Corrupt/non-dict existing file is handled gracefully
- Plugin entry is merged without duplication

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from install import (
    DEFAULT_OPENCODE_PORT,
    OPENCODE_JSON_NAME,
    OPENCODE_INSTRUCTIONS,
    OPENCODE_PLUGIN_KEY,
    OPENCODE_PLUGIN_RELATIVE,
    ensure_opencode_json,
    remove_installer_plugin_from_opencode_json,
    resolve_effective_opencode_port,
)


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

    def test_creates_instructions_key(self, config_root: Path) -> None:
        """Fresh install creates ``instructions`` key, NOT ``command_files``."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "instructions" in data
        assert "command_files" not in data

    def test_correct_instructions(self, config_root: Path) -> None:
        """Created file has exactly the 8 canonical instruction entries."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert data["instructions"] == list(OPENCODE_INSTRUCTIONS)

    def test_adds_plugin_entry(self, config_root: Path) -> None:
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        expected_plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()
        assert data[OPENCODE_PLUGIN_KEY] == [expected_plugin_uri]

    def test_instructions_are_relative_paths(self, config_root: Path) -> None:
        """All instruction entries are relative paths starting with 'commands/'."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        for entry in data["instructions"]:
            assert entry.startswith("commands/"), f"Expected relative path, got: {entry}"

    def test_nine_canonical_commands(self, config_root: Path) -> None:
        """The 9 instruction entries are the slash command files."""
        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        basenames = [entry.split("/")[-1] for entry in data["instructions"]]
        assert "continue.md" in basenames
        assert "plan.md" in basenames
        assert "implement.md" in basenames
        assert "review.md" in basenames
        assert len(basenames) == 9

    def test_valid_json_with_newline(self, config_root: Path) -> None:
        """Written file is valid JSON and ends with a newline."""
        ensure_opencode_json(config_root, dry_run=False)
        raw = (config_root / OPENCODE_JSON_NAME).read_text(encoding="utf-8")
        assert raw.endswith("\n")
        json.loads(raw)

    def test_can_emit_legacy_command_files_when_compat_enabled(self, config_root: Path) -> None:
        ensure_opencode_json(config_root, dry_run=False, include_legacy_command_files=True)
        data = _read_opencode_json(config_root)
        assert data["command_files"] == list(OPENCODE_INSTRUCTIONS)


# ---------------------------------------------------------------------------
# Merge with existing
# ---------------------------------------------------------------------------

class TestMergeExisting:
    def test_preserves_user_keys(self, config_root: Path) -> None:
        """Existing user keys are not removed or altered."""
        existing = {"theme": "dark", "editor": "vim"}
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        result = ensure_opencode_json(config_root, dry_run=False)
        assert result["status"] == "merged"
        data = _read_opencode_json(config_root)
        assert data["theme"] == "dark"
        assert data["editor"] == "vim"
        assert "instructions" in data

    def test_removes_legacy_command_files_key(self, config_root: Path) -> None:
        """Legacy ``command_files`` key is actively removed on merge."""
        existing = {
            "command_files": ["commands/old.md"],
            "notes": "keep me",
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "command_files" not in data, "legacy command_files key must be removed"
        assert "notes" in data
        assert data["notes"] == "keep me"
        assert "commands/old.md" not in data.get("instructions", [])

    def test_plugin_merge_preserves_existing_plugins(self, config_root: Path) -> None:
        """Existing plugin entries are kept; installer plugin is appended without duplication."""
        existing = {
            OPENCODE_PLUGIN_KEY: ["file:///custom/other-plugin.mjs"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert data[OPENCODE_PLUGIN_KEY][0] == "file:///custom/other-plugin.mjs"
        expected_plugin_uri = (config_root / OPENCODE_PLUGIN_RELATIVE).resolve().as_uri()
        assert expected_plugin_uri in data[OPENCODE_PLUGIN_KEY]

    def test_adds_missing_instructions(self, config_root: Path) -> None:
        """Missing canonical instruction entries are appended to existing instructions."""
        existing = {"instructions": ["my-custom/start.md"]}
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "my-custom/start.md" in data["instructions"]
        assert "commands/continue.md" in data["instructions"]
        assert "commands/plan.md" in data["instructions"]

    def test_preserves_user_instruction_order(self, config_root: Path) -> None:
        """User's existing instruction order is preserved; new entries are appended."""
        existing = {"instructions": ["first.md", "commands/master.md"]}
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert data["instructions"][0] == "first.md"
        assert data["instructions"][1] == "commands/master.md"

    def test_command_files_legacy_merge_removed(self, config_root: Path) -> None:
        """Merging a file that has both command_files and instructions cleans up command_files."""
        existing = {
            "command_files": ["commands/legacy.md"],
            "instructions": ["commands/continue.md"],
            "custom": "value",
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False)
        data = _read_opencode_json(config_root)
        assert "command_files" not in data
        assert "custom" in data
        assert "commands/continue.md" in data["instructions"]
        assert "commands/legacy.md" not in data["instructions"]

    def test_command_files_legacy_merge_kept_when_compat_enabled(self, config_root: Path) -> None:
        existing = {
            "command_files": ["commands/legacy.md"],
            "instructions": ["commands/continue.md"],
        }
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(json.dumps(existing), encoding="utf-8")

        ensure_opencode_json(config_root, dry_run=False, include_legacy_command_files=True)
        data = _read_opencode_json(config_root)
        assert data["command_files"] == list(OPENCODE_INSTRUCTIONS)


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
        assert data["instructions"] == list(OPENCODE_INSTRUCTIONS)
        assert "command_files" not in data

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


class TestOpenCodePortResolution:
    def test_happy_cli_port_overrides_env(self) -> None:
        result = resolve_effective_opencode_port(
            cli_opencode_port="5001",
            env={"OPENCODE_PORT": "6001"},
        )
        assert result == 5001

    def test_happy_env_port_used_when_cli_missing(self) -> None:
        result = resolve_effective_opencode_port(
            cli_opencode_port=None,
            env={"OPENCODE_PORT": "6001"},
        )
        assert result == 6001

    def test_corner_default_when_no_cli_or_env(self) -> None:
        result = resolve_effective_opencode_port(cli_opencode_port=None, env={})
        assert result == DEFAULT_OPENCODE_PORT

    def test_bad_non_numeric_cli_port_rejected(self) -> None:
        with pytest.raises(ValueError, match="--opencode-port"):
            resolve_effective_opencode_port(cli_opencode_port="abc", env={})

    def test_bad_out_of_range_env_port_rejected(self) -> None:
        with pytest.raises(ValueError, match="OPENCODE_PORT"):
            resolve_effective_opencode_port(cli_opencode_port=None, env={"OPENCODE_PORT": "70000"})


class TestOpenCodeJsonServerPort:
    def test_happy_create_writes_effective_port(self, config_root: Path) -> None:
        ensure_opencode_json(config_root, dry_run=False, effective_opencode_port=5001)
        data = _read_opencode_json(config_root)
        assert data["server"]["hostname"] == "127.0.0.1"
        assert data["server"]["port"] == 5001

    def test_edge_merge_overwrites_server_port_to_effective_value(self, config_root: Path) -> None:
        target = config_root / OPENCODE_JSON_NAME
        target.write_text(
            json.dumps({"server": {"hostname": "localhost", "port": 4096, "tls": False}}),
            encoding="utf-8",
        )
        ensure_opencode_json(config_root, dry_run=False, effective_opencode_port=5100)
        data = _read_opencode_json(config_root)
        assert data["server"]["hostname"] == "127.0.0.1"
        assert data["server"]["port"] == 5100
        assert data["server"]["tls"] is False
