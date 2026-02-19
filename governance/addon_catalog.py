"""Canonical addon catalog — SSOT for allowed capabilities, surfaces, and related sets.

Every script, linter, and test that needs to validate addon manifests MUST import
from this module instead of defining inline copies.  This eliminates the N-file
duplication that previously existed across validate_addons.py, governance_lint.py,
and test_addon_manifests.py.
"""

from __future__ import annotations

ALLOWED_CLASSES: frozenset[str] = frozenset({
    "advisory",
    "required",
})

ALLOWED_SIGNAL_KEYS: frozenset[str] = frozenset({
    "code_regex",
    "config_key_prefix",
    "file_glob",
    "maven_dep",
    "maven_dep_prefix",
    "workflow_file",
})

ALLOWED_SURFACES: frozenset[str] = frozenset({
    "api_contract",
    "backend_java_templates",
    "backend_python_templates",
    "bdd_framework",
    "build_tooling",
    "db_migration",
    "e2e_test_framework",
    "frontend_api_client",
    "frontend_templates",
    "governance_docs",
    "linting",
    "messaging",
    "principal_review",
    "release",
    "risk_model",
    "scorecard_calibration",
    "security",
    "static",
    "test_framework",
})

ALLOWED_CAPABILITIES: frozenset[str] = frozenset({
    "angular",
    "cucumber",
    "cypress",
    "governance_docs",
    "java",
    "kafka",
    "liquibase",
    "nx",
    "openapi",
    "python",
})

ALLOWED_EVIDENCE_KINDS: frozenset[str] = frozenset({
    "build",
    "contract-test",
    "e2e",
    "integration-test",
    "lint",
    "unit-test",
})
