#!/usr/bin/env python3
import argparse
import os
import sys
import subprocess

def main():
    parser = argparse.ArgumentParser(prog="opencode-bootstrap-executor", description="Execute bootstrap preflight until Phase 4")
    parser.add_argument("--config-root", help="Path to OpenCode config root", required=False)
    parser.add_argument("--repo-root", help="Path to repository root", required=False)
    args = parser.parse_args()
    env = os.environ.copy()
    if args.config_root:
        env["OPENCODE_CONFIG_ROOT"] = os.path.abspath(args.config_root)
    if args.repo_root:
        env["OPENCODE_REPO_ROOT"] = os.path.abspath(args.repo_root)
    # Run the preflight bootstrap until ready for Phase 4
    ret = subprocess.run([sys.executable, "-m", "governance.entrypoints.bootstrap_preflight_readonly"], env=env)
    return ret.returncode

if __name__ == "__main__":
    raise SystemExit(main())
