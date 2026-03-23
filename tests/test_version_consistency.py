"""Cluster 1 — Version format consistency tests.

Verifies:
  - All governance catalog JSON files with a version field use semver-3 format
  - All version fields are named 'version' (not 'catalog_version', 'policy_version', etc.)
  - The session_state CURRENT_SESSION_STATE_VERSION integer is a documented exception
  - Benchmark packs, registries, and operational catalogs are all covered
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOGS_DIR = REPO_ROOT / "governance_runtime" / "assets" / "catalogs"

SEMVER3_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# Catalog files that carry a version field.
# Files without a version field (pure schemas/contracts) are excluded:
#   AUDIT_REPORT_SCHEMA.json, GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json,
#   PROFILE_ADDON_FACTORY_CONTRACT.json, RESPONSE_ENVELOPE_SCHEMA.json,
#   RUN_SUMMARY_SCHEMA.json
VERSIONED_CATALOGS = sorted(
    p.name
    for p in CATALOGS_DIR.glob("*.json")
    if p.name
    not in {
        "AUDIT_REPORT_SCHEMA.json",
        "GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json",
        "PROFILE_ADDON_FACTORY_CONTRACT.json",
        "RESPONSE_ENVELOPE_SCHEMA.json",
        "RUN_SUMMARY_SCHEMA.json",
    }
)

# Known non-version keys that must NOT appear in catalogs.
LEGACY_VERSION_KEYS = {"catalog_version", "policy_version"}


# ── Parametrized: every versioned catalog must have semver-3 'version' ──────


@pytest.mark.parametrize("filename", VERSIONED_CATALOGS)
def test_catalog_has_semver3_version_field(filename: str) -> None:
    """Each versioned catalog must have a top-level 'version' field matching X.Y.Z."""
    path = CATALOGS_DIR / filename
    data = json.loads(path.read_text(encoding="utf-8"))

    assert "version" in data, (
        f"{filename} is missing the 'version' field"
    )
    version = data["version"]
    assert isinstance(version, str), (
        f"{filename}: 'version' must be a string, got {type(version).__name__} ({version!r})"
    )
    assert SEMVER3_PATTERN.match(version), (
        f"{filename}: 'version' must be semver-3 (X.Y.Z), got {version!r}"
    )


@pytest.mark.parametrize("filename", VERSIONED_CATALOGS)
def test_catalog_has_no_legacy_version_keys(filename: str) -> None:
    """No catalog may use 'catalog_version' or 'policy_version' — only 'version'."""
    path = CATALOGS_DIR / filename
    data = json.loads(path.read_text(encoding="utf-8"))

    for legacy_key in LEGACY_VERSION_KEYS:
        assert legacy_key not in data, (
            f"{filename} still uses legacy key '{legacy_key}' — rename to 'version'"
        )


# ── Documented exception: session_state uses integer versioning ─────────────


def test_session_state_version_is_integer_exception() -> None:
    """CURRENT_SESSION_STATE_VERSION is an integer counter by design.

    This is a documented exception to the semver-3 policy.
    Session state uses monotonic integer versioning because it's a
    document-level counter, not a compatibility marker.
    Changing it would break the Wave B migration stub.
    """
    from governance_runtime.engine.session_state_repository import (
        CURRENT_SESSION_STATE_VERSION,
    )

    assert isinstance(CURRENT_SESSION_STATE_VERSION, int), (
        "CURRENT_SESSION_STATE_VERSION must remain an integer (documented exception)"
    )
    assert CURRENT_SESSION_STATE_VERSION >= 1


# ── Guard: schema/contract files must NOT have a version field ──────────────

SCHEMA_CONTRACTS = [
    "AUDIT_REPORT_SCHEMA.json",
    "GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json",
    "PROFILE_ADDON_FACTORY_CONTRACT.json",
    "RESPONSE_ENVELOPE_SCHEMA.json",
    "RUN_SUMMARY_SCHEMA.json",
]


@pytest.mark.parametrize("filename", SCHEMA_CONTRACTS)
def test_schema_contracts_have_no_version_field(filename: str) -> None:
    """Schema/contract files define structure, not versioned data — no 'version' field expected."""
    path = CATALOGS_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} does not exist")
    data = json.loads(path.read_text(encoding="utf-8"))
    # These files should not have any version-like top-level key
    for key in ("version", "catalog_version", "policy_version"):
        assert key not in data, (
            f"{filename} unexpectedly has '{key}' — schema/contract files should not carry version fields"
        )


# ── Coverage guard: ensure we're not missing any catalogs ───────────────────


def test_all_catalog_json_files_are_classified() -> None:
    """Every .json file in the catalogs directory must be either
    in VERSIONED_CATALOGS or in SCHEMA_CONTRACTS."""
    all_files = sorted(p.name for p in CATALOGS_DIR.glob("*.json"))
    classified = set(VERSIONED_CATALOGS) | set(SCHEMA_CONTRACTS)
    unclassified = [f for f in all_files if f not in classified]
    assert not unclassified, (
        f"Unclassified catalog files — add to VERSIONED_CATALOGS or SCHEMA_CONTRACTS: {unclassified}"
    )
