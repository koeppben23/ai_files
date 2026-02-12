# Customer Install Bundle v1

This document defines the professional customer delivery bundle that sits on top of the raw release archives.

## Goal

- Keep deterministic `governance-<version>.zip` and `governance-<version>.tar.gz` as base artifacts.
- Add a customer-facing bundle with checksum-verified install entrypoints for macOS/Linux and Windows.
- Publish one auditable package that a customer can use without GitHub access.

## Build command

```bash
python3 scripts/build.py --out-dir dist --formats zip,tar.gz
python3 scripts/build_customer_install_bundle.py --dist-dir dist
```

## Produced files in `dist/`

- `governance-<version>.zip`
- `governance-<version>.tar.gz`
- `SHA256SUMS.txt`
- `verification-report.json`
- `customer-install-bundle-v1/` (expanded bundle directory)
- `customer-install-bundle-v1.zip` (customer handoff artifact)
- `customer-install-bundle-v1.SHA256` (bundle checksum)

## Bundle directory structure

```text
customer-install-bundle-v1/
  README.md
  BUNDLE_MANIFEST.json
  artifacts/
    governance-<version>.zip
    governance-<version>.tar.gz
    SHA256SUMS.txt
    verification-report.json
  install/
    install.sh
    install.ps1
```

## Installer wrapper behavior

- `install/install.sh`
  - validates checksum of `governance-<version>.zip` against `artifacts/SHA256SUMS.txt`
  - extracts zip to temporary local folder
  - executes `python3 install.py` with forwarded arguments

- `install/install.ps1`
  - validates checksum of `governance-<version>.zip` against `artifacts/SHA256SUMS.txt`
  - extracts archive using `Expand-Archive`
  - executes `python install.py` with forwarded arguments

## CI release path (current)

`CI` workflow `build-artifacts` job executes:

1. `python scripts/build.py`
2. `python scripts/build_customer_install_bundle.py --dist-dir dist`
3. artifact smoke test from release archives
4. upload `dist/*` as `governance-dist` artifact

## GitHub release pipeline

Professional publishing is handled by `.github/workflows/release.yml`:

- trigger via tag push (`v*`) or manual dispatch with existing tag
- enforce tag/version consistency with `master.md`
- execute release and build test gates before publishing
- upload base artifacts + customer install bundle to the GitHub release

For one-command release automation (including version/changelog/tag updates), use `.github/workflows/release-orchestrator.yml`, which cuts the release commit and tag first, then dispatches `release.yml`.

## Customer handoff recommendation

- Deliver `customer-install-bundle-v1.zip` and `customer-install-bundle-v1.SHA256` together.
- Instruct customer to verify SHA256 before extraction.
- Use wrapper installer (`install.sh` or `install.ps1`) instead of manual extraction.
