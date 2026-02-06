# Changelog
All notable changes to this project will be documented in this file.

This project follows **Keep a Changelog** and **Semantic Versioning**.

## [Unreleased]
### Added
### Changed
### Fixed
### Removed
### Security

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
