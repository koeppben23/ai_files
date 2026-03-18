#!/usr/bin/env python3
import os
import sys
import subprocess

def main():
    # Delegate to the bootstrap preflight readonly path
    env = os.environ.copy()
    if "OPENCODE_CONFIG_ROOT" in env:
        env["OPENCODE_CONFIG_ROOT"] = env["OPENCODE_CONFIG_ROOT"]
    if "OPENCODE_REPO_ROOT" in env:
        env["OPENCODE_REPO_ROOT"] = env["OPENCODE_REPO_ROOT"]
    code = subprocess.call([sys.executable, "-m", "governance.entrypoints.bootstrap_preflight_readonly"], env=env)
    return code

if __name__ == "__main__":
    raise SystemExit(main())
