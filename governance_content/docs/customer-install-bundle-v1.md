# Customer Install Bundle (v1)

- `install/install.sh`
  - validates checksum of `governance-<version>.zip` against `artifacts/SHA256SUMS.txt`
  - extracts zip to temporary local folder
  - executes `${PYTHON_COMMAND} install.py` from the extracted release with forwarded arguments

- `install/install.ps1`
  - validates checksum of `governance-<version>.zip` against `artifacts/SHA256SUMS.txt`
  - extracts archive using `Expand-Archive`
  - executes `python install.py` from the extracted release with forwarded arguments

## CI release path (current)


1. `python scripts/build.py`
2. `python scripts/build_customer_install_bundle.py --dist-dir dist`
3. release artifact smoke test:
   - import check from extracted artifact (e.g. `python -c "import governance_runtime.entrypoints.bootstrap_preflight_readonly"`)
   - full path check: extract -> run `install.py` from extracted release -> run bootstrap launcher with `--repo-root`
4. upload `dist/*` as `governance-dist` artifact

## GitHub release pipeline

> Placeholder — release pipeline steps to be documented when CI/CD is finalized.
