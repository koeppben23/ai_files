import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from tests.util import REPO_ROOT
import install as installer


@pytest.mark.skipif(os.name != 'nt', reason="Windows end-to-end smoke test enabled only on Windows CI")
def test_end_to_end_windows_wrapper_smoke():
    with tempfile.TemporaryDirectory() as tmp:
        config_root = Path(tmp) / "opencode-config-windows-smoke"
        # Build install plan for the smoke test
        plan = installer.build_plan(
            source_dir=REPO_ROOT,
            config_root=config_root,
            skip_paths_file=False,
            deterministic_paths_file=False,
        )

        # Run the full installer so that the governance runtime, launcher,
        # paths file, phase_api.yaml, and all other artifacts are in place.
        rc = installer.install(plan, dry_run=False, force=True, backup_enabled=False)
        assert rc == 0, f"installer.install() returned {rc}"

        wrapper_path = config_root / "bin" / "opencode-governance-bootstrap.cmd"
        assert wrapper_path.exists(), f"Windows wrapper not installed: {wrapper_path}"

        env = os.environ.copy()
        env["OPENCODE_CONFIG_ROOT"] = str(config_root)
        env["OPENCODE_REPO_ROOT"] = str(REPO_ROOT)

        # Execute the Windows launcher
        result = subprocess.run(
            [str(wrapper_path), "--repo-root", str(REPO_ROOT), "--config-root", str(config_root)],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Windows launcher exit code != 0. Stdout: {result.stdout}\nStderr: {result.stderr}"
        )
        # Expect a JSON payload on stdout
        payload_text = result.stdout.strip()
        assert payload_text, "Launcher did not print payload JSON"
        payload = None
        for line in payload_text.splitlines():
            try:
                candidate = json.loads(line)
            except Exception:
                continue
            if isinstance(candidate, dict) and "session_state_path" in candidate:
                payload = candidate
                break
        if payload is None:
            payload = json.loads(payload_text)
        assert isinstance(payload, dict)
        # Basic sanity checks on the payload
        assert 'phase' in payload, payload
        assert 'session_state_path' in payload
        session_path = Path(payload['session_state_path'])
        assert session_path.exists(), f"Session state path does not exist: {session_path}"
