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

        # Create necessary dirs
        installer.ensure_dirs(config_root, dry_run=False)

        (config_root / "commands").mkdir(parents=True, exist_ok=True)
        phase_src = REPO_ROOT / "phase_api.yaml"
        if not phase_src.exists():
            raise AssertionError("phase_api.yaml missing from repo root")
        phase_dst = config_root / "commands" / "phase_api.yaml"
        if not phase_dst.exists():
            phase_dst.write_bytes(phase_src.read_bytes())

        # Create launcher (installs wrappers into runtime bin)
        created = installer.create_launcher(plan, dry_run=False, force=False)
        paths_file = plan.governance_paths_path
        if not paths_file.exists():
            installer.install_governance_paths_file(
                plan,
                dry_run=False,
                force=True,
                backup_enabled=False,
                backup_root=config_root,
            )

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
