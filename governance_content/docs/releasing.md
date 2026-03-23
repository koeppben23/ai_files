# Releasing

This document centralizes release workflow details moved out of `README.md`.

## Release Workflow

Primary workflow: `.github/workflows/release.yml`

Supported triggers:

- `push` tags matching `v*` (for example `v1.2.3` or `v1.2.3-RC.1`)
- manual `workflow_dispatch` with an existing tag input

Fail-closed behavior:

- validates tag format and enforces tag/version match with `master.md`
- executes release gates before publish (`governance_lint`, `pytest -m release`, `pytest -m build`)
- builds deterministic release artifacts and customer install bundle
- signs release-critical artifacts with Sigstore/cosign keyless signing (OIDC)
- verifies signer identity constraints before publish
- generates SBOM files (SPDX JSON) for published ZIP artifacts
- publishes build provenance and SBOM attestations

## One-Command Release Orchestration

Use `.github/workflows/release-orchestrator.yml` for a single-step release flow that:

- updates version fields and changelog via `scripts/release.py`
- creates release commit + `v<version>` tag on `main`
- dispatches `release.yml` to build and publish assets

Example:

```bash
gh workflow run release-orchestrator.yml \
  -f version=1.2.0-RC2 \
  -f prerelease=true \
  -f draft=false \
  -f allow_empty_changelog=false
```

## Published Assets

- `governance-<version>.zip`
- `governance-<version>.tar.gz`
- `SHA256SUMS.txt`
- `verification-report.json`
- `customer-install-bundle-v1.zip`
- `customer-install-bundle-v1.SHA256`
- `governance-<version>.zip.spdx.json`
- `customer-install-bundle-v1.zip.spdx.json`
- signature bundles for each release-critical asset: `<asset>.sigstore.json`

## Verification Contract

- OIDC issuer: `https://token.actions.githubusercontent.com`
- allowed signer identity: `https://github.com/<org>/<repo>/.github/workflows/release.yml@refs/tags/v<semver-ish>`
- Replace `<org>/<repo>` with the actual release source repository before running verification commands.
- Authoritative identity values are also listed in `verification-report.json` for each release.

Example signature verification:

```bash
cosign verify-blob \
  --bundle governance-1.2.0.zip.sigstore.json \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github\.com/<org>/<repo>/\.github/workflows/release\.yml@refs/tags/v[0-9]+\.[0-9]+\.[0-9]+([-.+][0-9A-Za-z.-]+)?$' \
  governance-1.2.0.zip
```

Example attestation verification:

```bash
gh attestation verify governance-1.2.0.zip \
  --repo <org>/<repo> \
  --signer-workflow .github/workflows/release.yml
```

For threat model and signer constraints rationale, see [`release-security-model.md`](release-security-model.md).
