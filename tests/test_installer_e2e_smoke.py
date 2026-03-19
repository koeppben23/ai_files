import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from tests.util import REPO_ROOT, get_phase_api_path
from governance_runtime.install.install import (
    build_plan,
    create_launcher,
    ensure_dirs,
    install_governance_paths_file,
)


@pytest.mark.skipif(os.name != 'nt', reason="Windows end-to-end smoke test enabled only on Windows CI")
def test_end_to_end_windows_wrapper_smoke():
    with tempfile.TemporaryDirectory() as tmp:
        config_root = Path(tmp) / "opencode-config-windows-smoke"
        # Build install plan for the smoke test.
        plan = build_plan(
            source_dir=REPO_ROOT,
            config_root=config_root,
            skip_paths_file=False,
            deterministic_paths_file=False,
        )

        # Fast-path setup: only create directories, binding file, launcher,
        # and phase_api.yaml. Runtime code is loaded from REPO_ROOT via
        # OPENCODE_LOCAL_ROOT to avoid full payload copy in this smoke test.
        ensure_dirs(config_root, plan.local_root, dry_run=False)
        install_governance_paths_file(
            plan=plan,
            dry_run=False,
            force=True,
            backup_enabled=False,
            backup_root=config_root / ".installer-backups" / "smoke",
        )
        launcher_entries = create_launcher(plan, dry_run=False, force=True)
        assert launcher_entries, "launcher entries not created"

        commands_home = config_root / "commands"
        commands_home.mkdir(parents=True, exist_ok=True)
        phase_api_src = get_phase_api_path()
        assert phase_api_src.exists(), f"phase_api.yaml missing at {phase_api_src}"
        (commands_home / "phase_api.yaml").write_text(phase_api_src.read_text(encoding="utf-8"), encoding="utf-8")

        wrapper_path = config_root / "bin" / "opencode-governance-bootstrap.cmd"
        assert wrapper_path.exists(), f"Windows wrapper not installed: {wrapper_path}"

        env = os.environ.copy()
        env["OPENCODE_CONFIG_ROOT"] = str(config_root)
        env["OPENCODE_REPO_ROOT"] = str(REPO_ROOT)
        env["OPENCODE_LOCAL_ROOT"] = str(REPO_ROOT)
        env["COMMANDS_HOME"] = str(commands_home)

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
