# Release Security Model

This note defines the release-signing threat model and deterministic verification contract.

## Release-critical artifacts

The following assets are considered release-critical and MUST be signed:

- `governance-<version>.zip`
- `governance-<version>.tar.gz`
- `SHA256SUMS.txt`
- `verification-report.json`
- `customer-install-bundle-v1.zip`
- `customer-install-bundle-v1.SHA256`

Each signed asset is paired with a Sigstore bundle file:

- `<asset>.sigstore.json`

## Signing authority

Only the GitHub Actions release workflow is allowed to sign release artifacts.

- Workflow path: `.github/workflows/release.yml`
- Repository: `<org>/<repo>` (current: `koeppben23/ai_files`)
- Allowed refs: `refs/tags/v<semver-ish>`
- OIDC issuer: `https://token.actions.githubusercontent.com`

Verification MUST enforce these identity constraints.

## Signing mode

Release workflow uses keyless Sigstore signing for blobs:

```bash
cosign sign-blob --yes --bundle <asset>.sigstore.json <asset>
```

## Verification contract

Verification MUST check both signature validity and signer identity constraints:

```bash
cosign verify-blob \
  --bundle <asset>.sigstore.json \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github\.com/<org>/<repo>/\.github/workflows/release\.yml@refs/tags/v[0-9]+\.[0-9]+\.[0-9]+([-.+][0-9A-Za-z.-]+)?$' \
  <asset>
```

## Customer/offline verification guidance

Minimum verification sequence before install:

1. Verify checksums from `SHA256SUMS.txt`.
2. Verify Sigstore bundle for each release-critical asset with identity constraints.
3. Install via `customer-install-bundle-v1` wrapper script.

If any verification step fails, installation MUST be blocked.
