# Changelog
All notable changes to this project will be documented in this file.

This project follows **Keep a Changelog** and **Semantic Versioning**.

## [Unreleased]

## [1.0.1-BETA] - 2026-02-06
### Added
- Initialize post-1.0.1-BETA development baseline.

### Changed
### Fixed
### Removed
### Security
## [1.0.1-BETA] - 2026-02-06
### Added
- PR-gated “Release Readiness” workflow to enforce branch protection on `main`.

### Changed
- Release automation now enforces LF newlines across platforms.
- Pre-release handling extended for `-BETA`, `beta.x`, and `rc.x` identifiers.

### Fixed
- Release dry-run no longer introduces newline drift on Windows systems.
- Version propagation is now fully consistent across governance files.

### Removed

### Security
- Release pipeline blocks execution on dirty git working trees.

## [1.0.0-BETA] - 2026-02-06
### Added
- Deterministic installer (`install.py`) with **mandatory** governance version.
- Manifest-based uninstall: the manifest is the *only* delete source.
- Deterministic release artifacts (`scripts/build.py`) producing `zip` + `tar.gz` and `SHA256SUMS.txt`.
- CI spec guards (fail-fast) for drift prevention.

### Changed
- Windows-safe conventions: path variables (`${CONFIG_ROOT}`) and case-collision protection.

### Fixed
- Packaging drift / legacy artifacts removed (no unresolved placeholders, no `opencode.json` remnants).
- Uninstall fallback hardened to not depend on the repo source directory.

### Security
- Hard CI gates to block silent fallback behavior and prevent spec drift.
