"""Canonical addon catalog — SSOT for allowed capabilities, surfaces, and related sets.

Every script, linter, and test that needs to validate addon manifests MUST import
from this module instead of defining inline copies.  This eliminates the N-file
duplication that previously existed across validate_addons.py, governance_lint.py,
and test_addon_manifests.py.

Capability Derivation Notes:
- Most capabilities are repo-derived (java, python, kafka, etc.)
- Mode-derived capabilities (set by kernel/loader, NOT repo signals):
  - user_mode: Set when operating in user mode (high-quality, human-in-the-loop)
"""

from __future__ import annotations

ALLOWED_CLASSES: frozenset[str] = frozenset({
    "advisory",
    "required",
})

ALLOWED_SIGNAL_KEYS: frozenset[str] = frozenset({
    "capability",
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
    "implementation",
    "java_antipatterns",
    "java_best_practices",
    "java_patterns",
    "linting",
    "messaging",
    "output_sections",
    "principal_review",
    "python_antipatterns",
    "python_best_practices",
    "python_patterns",
    "quality_enforcement",
    "release",
    "risk_model",
    "scorecard_calibration",
    "security",
    "static",
    "test_framework",
    "testing",
    "verification_handshake",
    "review",
})

ALLOWED_CAPABILITIES: frozenset[str] = frozenset({
    "angular",
    "backend_java",
    "backend_python",
    "cucumber",
    "cypress",
    "governance_docs",
    "java",
    "kafka",
    "liquibase",
    "nx",
    "openapi",
    "python",
    "quality_contract",
    "spring_boot",
    "user_mode",
})

ALLOWED_EVIDENCE_KINDS: frozenset[str] = frozenset({
    "build",
    "contract-test",
    "e2e",
    "integration-test",
    "lint",
    "unit-test",
})
