from __future__ import annotations

from pathlib import Path

import pytest

from tests.util import REPO_ROOT

PLUGIN_PATH = REPO_ROOT / "governance_runtime" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"


def _read_plugin() -> str:
    return PLUGIN_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existing contract tests (updated for Commit 12 changes)
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_plugin_artifact_exists_in_governance_artifacts() -> None:
    assert PLUGIN_PATH.exists(), "global JS plugin artifact must exist"


@pytest.mark.governance
def test_plugin_uses_node_builtins_and_spawn_args_array() -> None:
    content = _read_plugin()

    assert 'from "node:child_process"' in content
    assert 'from "node:fs"' in content
    assert 'from "node:url"' in content, "plugin must import from node:url for fileURLToPath"
    assert "spawn(" in content
    assert "spawnSync(" in content
    assert "exec(" not in content
    assert '"-m"' in content
    assert '"governance_runtime.entrypoints.new_work_session"' in content
    assert '"--trigger-source"' in content
    assert '"desktop-plugin"' in content
    assert "OPENCODE_PYTHON" in content


@pytest.mark.governance
def test_plugin_listens_only_to_session_created_and_handles_field_variants() -> None:
    content = _read_plugin()

    assert 'event.type !== "session.created"' in content
    assert 'event.type === "file.watcher.updated"' in content
    assert "event.properties" in content
    assert "info?.id" in content
    assert "info?.directory" in content
    assert "event.sessionId" in content
    assert "event.session_id" in content
    assert "looksRepoPlausible" in content
    assert "OPENCODE_AUDIT_DEBUG" in content
    assert "process.cwd()" in content
    assert "export default AuditNewSession" in content
    assert "MAX_LOG_BYTES" in content


# ---------------------------------------------------------------------------
# Commit 12: PYTHON_BINDING resolution tests (contract §4.3)
# ---------------------------------------------------------------------------


class TestPluginPythonBindingResolution:
    """Verify the plugin reads PYTHON_BINDING per python-binding-contract.v1 §4.3."""

    def test_happy_resolve_binding_file_function_exists(self) -> None:
        """Happy: resolveBindingFile function is defined."""
        content = _read_plugin()
        assert "function resolveBindingFile()" in content

    def test_happy_reads_python_binding_file(self) -> None:
        """Happy: plugin reads PYTHON_BINDING file via readFileSync."""
        content = _read_plugin()
        assert "readFileSync" in content
        assert "PYTHON_BINDING" in content

    def test_happy_import_file_url_to_path(self) -> None:
        """Happy: plugin imports fileURLToPath for deriving config root."""
        content = _read_plugin()
        assert "fileURLToPath" in content
        assert "import.meta.url" in content

    def test_happy_three_priority_resolution_order(self) -> None:
        """Happy: resolvePython has three priorities in correct order.

        Contract §4.3:
        1. OPENCODE_PYTHON env
        2. PYTHON_BINDING file
        3. PATH probing (degraded)
        """
        content = _read_plugin()

        # Find the positions of each priority marker
        env_pos = content.find("OPENCODE_PYTHON")
        binding_pos = content.find("resolveBindingFile()")
        degraded_pos = content.find("degraded PATH probing")

        assert env_pos > 0, "OPENCODE_PYTHON check must exist"
        assert binding_pos > 0, "resolveBindingFile() call must exist"
        assert degraded_pos > 0, "degraded PATH probing comment must exist"

        # Verify ordering within resolvePython()
        fn_start = content.find("function resolvePython()")
        assert fn_start > 0

        # All three within resolvePython, in order
        env_rel = content.find("OPENCODE_PYTHON", fn_start)
        binding_rel = content.find("resolveBindingFile()", fn_start)
        degraded_rel = content.find("degraded PATH probing", fn_start)

        assert env_rel < binding_rel < degraded_rel, (
            "Resolution order must be: OPENCODE_PYTHON → PYTHON_BINDING → degraded PATH"
        )

    def test_happy_degraded_field_in_resolution_result(self) -> None:
        """Happy: resolution results include a 'degraded' boolean field."""
        content = _read_plugin()

        # OPENCODE_PYTHON and PYTHON_BINDING should have degraded: false
        assert "degraded: false" in content
        # PATH probing should have degraded: true
        assert "degraded: true" in content

    def test_happy_degraded_warning_logged(self) -> None:
        """Happy: when degraded fallback is used, a warning is logged."""
        content = _read_plugin()
        assert "python.degraded" in content
        assert "degraded PATH fallback" in content

    def test_happy_source_labels_for_path_probing_include_degraded(self) -> None:
        """Happy: PATH probing sources are labeled as degraded."""
        content = _read_plugin()
        # All PATH-probing source labels should include "(degraded)"
        assert '"python3 (degraded)"' in content
        assert '"python (degraded)"' in content

    def test_happy_binding_source_label(self) -> None:
        """Happy: PYTHON_BINDING resolution uses correct source label."""
        content = _read_plugin()
        assert '"PYTHON_BINDING"' in content

    def test_corner_binding_file_validation_empty(self) -> None:
        """Corner: resolveBindingFile rejects empty PYTHON_BINDING files."""
        content = _read_plugin()
        assert "PYTHON_BINDING empty" in content

    def test_corner_binding_file_validation_multiline(self) -> None:
        """Corner: resolveBindingFile rejects multi-line PYTHON_BINDING files."""
        content = _read_plugin()
        assert "PYTHON_BINDING malformed" in content
        assert "multi-line" in content

    def test_corner_windows_posix_path_conversion(self) -> None:
        """Corner: on Windows, POSIX paths from PYTHON_BINDING are converted to native."""
        content = _read_plugin()
        # The plugin should convert forward slashes to backslashes on Windows
        assert "boundPath.replace(" in content
        assert 'win32' in content

    def test_edge_binding_file_read_error_handled(self) -> None:
        """Edge: read errors on PYTHON_BINDING are caught and logged."""
        content = _read_plugin()
        assert "PYTHON_BINDING read error" in content

    def test_edge_import_meta_url_failure_handled(self) -> None:
        """Edge: import.meta.url failure is caught gracefully."""
        content = _read_plugin()
        # The try/catch around fileURLToPath should handle failures
        assert "import.meta.url not usable" in content or (
            "bundled or eval context" in content
        )

    def test_bad_no_exec_call_in_plugin(self) -> None:
        """Bad path: plugin must NEVER use exec() (shell injection risk)."""
        content = _read_plugin()
        assert "exec(" not in content

    def test_happy_well_known_default_fallback_path(self) -> None:
        """Happy: resolveBindingFile tries well-known ~/.config/opencode/bin/PYTHON_BINDING."""
        content = _read_plugin()
        assert '".config"' in content
        assert '"opencode"' in content
        assert '"bin"' in content
        assert '"PYTHON_BINDING"' in content

    def test_happy_derive_config_root_from_plugin_path(self) -> None:
        """Happy: resolveBindingFile derives config_root from its own file location."""
        content = _read_plugin()
        # Plugin at <config_root>/plugins/audit-new-session.mjs
        # dirname(thisFile) = <config_root>/plugins
        # dirname(pluginsDir) = <config_root>
        assert "dirname(thisFile)" in content or "pluginsDir" in content
        assert "dirname(pluginsDir)" in content or "configRoot" in content
