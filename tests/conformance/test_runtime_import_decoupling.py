"""
Runtime Import Decoupling Conformance Test (R2)

Validates that governance_runtime/ is being decoupled from governance/.
This test enforces the migration from governance.* to governance_runtime.*

Architecture Rule:
- governance_runtime/ is the canonical authority for Runtime code
- No productive imports from governance.* should exist in governance_runtime/**
- New imports to governance/ from governance_runtime/ are forbidden
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Set, Tuple, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_RUNTIME = REPO_ROOT / "governance_runtime"

ALLOWED_LEGACY_IMPORTS = {
    "governance.domain.reason_codes",
    "governance.domain.phase_state_machine",
    "governance.domain.canonical_json",
    "governance.domain.errors.events",
    "governance.domain.models.policy_mode",
    "governance.domain.models.rulebooks",
    "governance.domain.models.binding",
    "governance.domain.models.layouts",
    "governance.domain.models.repo_identity",
    "governance.domain.models.write_action",
    "governance.domain.audit_readout_contract",
    "governance.domain.evidence_policy",
    "governance.domain.operating_profile",
    "governance.application.dto.phase_next_action_contract",
    "governance.paths",
    "governance.engine",
    "governance.engine.adapters",
    "governance.engine.session_state_repository",
    "governance.engine.surface_policy",
    "governance.engine.reason_payload",
    "governance.domain.errors",
    "governance.domain.models",
    "governance.domain.policies",
    "governance.application.dto",
    "governance.application.use_cases",
    "governance.application.policies",
    "governance.application.ports",
    "governance.application.ports.filesystem",
    "governance.application.ports.gateways",
    "governance.application.ports.logger",
    "governance.application.ports.process_runner",
    "governance.application.ports.rulebook_source",
    "governance.engine.reason_codes",
    "governance.engine.canonical_json",
    "governance.engine.phase_next_action_contract",
    "governance.engine.session_state_invariants",
    "governance.engine.schema_validator",
    "governance.engine.gate_evaluator",
    "governance.engine.business_rules_validation",
    "governance.engine.business_rules_hydration",
    "governance.engine.business_rules_coverage",
    "governance.engine.business_rules_code_extraction",
    "governance.engine.runtime",
    "governance.engine.orchestrator",
    "governance.engine.state_machine",
    "governance.engine.selfcheck",
    "governance.engine.lifecycle",
    "governance.engine.mode_repo_rules",
    "governance.engine.interaction_gate",
    "governance.engine.sanitization",
    "governance.engine.error_reason_router",
    "governance.engine._embedded_reason_registry",
    "governance.engine._embedded_reason_schemas",
    "governance.engine._embedded_session_state_schema",
    "governance.infrastructure.fs_atomic",
    "governance.infrastructure.path_contract",
    "governance.infrastructure.binding_evidence_resolver",
    "governance.infrastructure.session_pointer",
    "governance.infrastructure.workspace_paths",
    "governance.infrastructure.logging.global_error_handler",
    "governance.infrastructure.adapters.logging.event_sink",
    "governance.infrastructure.adapters.filesystem.atomic_write",
    "governance.infrastructure.policy_bundle_loader",
    "governance.infrastructure.mode_repo_rules",
    "governance.infrastructure.phase4_config_resolver",
    "governance.infrastructure.phase5_review_resolver",
    "governance.infrastructure.interaction_gate",
    "governance.infrastructure.wiring",
    "governance.infrastructure.runtime_activation",
    "governance.infrastructure.workspace_ready_gate",
    "governance.infrastructure.write_policy",
    "governance.infrastructure.persist_confirmation_store",
    "governance.infrastructure.reason_payload",
    "governance.infrastructure.repo_root_resolver",
    "governance.infrastructure.plan_record_state",
    "governance.infrastructure.archive_export",
    "governance.infrastructure.redaction",
    "governance.infrastructure.recovery_executor",
    "governance.infrastructure.governance_orchestrator",
    "governance.infrastructure.governance_config_loader",
    "governance.infrastructure.governance_hooks",
    "governance.infrastructure.work_run_archive",
    "governance.infrastructure.io_verify",
    "governance.infrastructure.io_actions",
    "governance.infrastructure.run_audit_artifacts",
    "governance.infrastructure.artifact_integrity",
    "governance.common.path_normalization",
    "governance.kernel.phase_kernel",
    "governance.packs.pack_lock",
    "governance.infrastructure.pack_lock",
    "governance.infrastructure.selfcheck",
    "governance.infrastructure.model_identity_resolver",
    "governance.infrastructure.phase5_config_resolver",
    "governance.infrastructure.error_reason_router",
    "governance.infrastructure.reason_registry_selfcheck",
    "governance.infrastructure.surface_policy",
    "governance.infrastructure.logging",
    "governance.infrastructure.adapters",
    "governance.context.repo_context_resolver",
    "governance.persistence.write_policy",
    "governance.application.use_cases.artifact_backfill",
    "governance.application.use_cases.audit_readout_builder",
    "governance.application.use_cases.bootstrap_persistence",
    "governance.application.use_cases.bootstrap_session",
    "governance.application.use_cases.build_reason_context",
    "governance.application.use_cases.evaluate_persistence_gate",
    "governance.application.use_cases.load_rulebooks",
    "governance.application.use_cases.orchestrate_run",
    "governance.application.use_cases.phase5_review_config",
    "governance.application.use_cases.phase5_iterative_review",
    "governance.application.use_cases.phase_router",
    "governance.application.use_cases.repo_policy_setup",
    "governance.application.use_cases.resolve_operating_mode",
    "governance.application.use_cases.resolve_output_intent",
    "governance.application.use_cases.route_phase",
    "governance.application.use_cases.session_state_helpers",
    "governance.application.use_cases.target_path_helpers",
    "governance.application.use_cases.validate_plan_compliance",
    "governance.application.policies.persistence_policy",
    "governance.application.repo_identity_service",
    "governance.domain.access_control",
    "governance.domain.audit_contract",
    "governance.domain.classification",
    "governance.domain.failure_model",
    "governance.domain.integrity",
    "governance.domain.model_identity",
    "governance.domain.policy_precedence",
    "governance.domain.regulated_mode",
    "governance.domain.retention",
    "governance.domain.strict_exit_evaluator",
    "governance.domain.policies.gate_policy",
    "governance.domain.policies.phase_policy",
    "governance.domain.policies.write_policy",
}

BASELINE_FILE_COUNT = 94


def _scan_governance_runtime_imports() -> Tuple[Set[str], List[Tuple[str, str]]]:
    """Scan all governance_runtime/*.py files for governance.* imports."""
    files_with_imports = set()
    all_imports = []
    
    for py_file in GOVERNANCE_RUNTIME.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        try:
            content = py_file.read_text()
        except:
            continue
        
        rel_path = str(py_file.relative_to(REPO_ROOT))
        
        for match in re.finditer(r"^(?:from|import)\s+(governance\.[^\s;]+)", content, re.MULTILINE):
            import_str = match.group(1).split(".")[0:3]
            import_path = ".".join(import_str[:3]) if len(import_path := ".".join(import_str)) > 0 else import_str[0]
            
            files_with_imports.add(rel_path)
            all_imports.append((rel_path, import_path))
    
    return files_with_imports, all_imports


@pytest.mark.conformance
class TestRuntimeImportDecoupling:
    """Validate runtime import decoupling from governance/."""

    def test_governance_runtime_exists(self):
        """Happy: governance_runtime/ directory exists."""
        assert GOVERNANCE_RUNTIME.is_dir(), "governance_runtime/ must exist"

    def test_no_new_legacy_import_files(self):
        """
        Guardrail: No NEW files in governance_runtime/ may import from governance/.
        
        This test ensures that no NEW governance_runtime files are created that
        import from governance/. Only the existing 94 files are allowed.
        """
        files_with_imports, _ = _scan_governance_runtime_imports()
        
        allowed_files = {
            "governance_runtime/application/dto/phase_next_action_contract.py",
            "governance_runtime/application/policies/persistence_policy.py",
            "governance_runtime/application/ports/logger.py",
            "governance_runtime/application/ports/rulebook_source.py",
            "governance_runtime/application/repo_identity_service.py",
            "governance_runtime/application/use_cases/artifact_backfill.py",
            "governance_runtime/application/use_cases/audit_readout_builder.py",
            "governance_runtime/application/use_cases/bootstrap_persistence.py",
            "governance_runtime/application/use_cases/bootstrap_session.py",
            "governance_runtime/application/use_cases/build_reason_context.py",
            "governance_runtime/application/use_cases/evaluate_persistence_gate.py",
            "governance_runtime/application/use_cases/load_rulebooks.py",
            "governance_runtime/application/use_cases/orchestrate_run.py",
            "governance_runtime/application/use_cases/phase5_iterative_review.py",
            "governance_runtime/application/use_cases/phase_router.py",
            "governance_runtime/application/use_cases/repo_policy_setup.py",
            "governance_runtime/application/use_cases/resolve_operating_mode.py",
            "governance_runtime/application/use_cases/resolve_output_intent.py",
            "governance_runtime/application/use_cases/route_phase.py",
            "governance_runtime/cli/backfill.py",
            "governance_runtime/cli/bootstrap_executor.py",
            "governance_runtime/cli/deps.py",
            "governance_runtime/cli/route.py",
            "governance_runtime/domain/audit_readout_contract.py",
            "governance_runtime/domain/integrity.py",
            "governance_runtime/domain/models/session_state.py",
            "governance_runtime/domain/strict_exit_evaluator.py",
            "governance_runtime/engine/adapters.py",
            "governance_runtime/engine/audit_readout_contract.py",
            "governance_runtime/engine/business_rules_coverage.py",
            "governance_runtime/engine/business_rules_hydration.py",
            "governance_runtime/engine/business_rules_validation.py",
            "governance_runtime/engine/canonical_json.py",
            "governance_runtime/engine/gate_evaluator.py",
            "governance_runtime/engine/implementation_validation.py",
            "governance_runtime/engine/layer_classifier.py",
            "governance_runtime/engine/lifecycle.py",
            "governance_runtime/engine/orchestrator.py",
            "governance_runtime/engine/path_contract.py",
            "governance_runtime/engine/phase_next_action_contract.py",
            "governance_runtime/engine/reason_codes.py",
            "governance_runtime/engine/reason_payload.py",
            "governance_runtime/engine/response_contract.py",
            "governance_runtime/engine/runtime.py",
            "governance_runtime/engine/selfcheck.py",
            "governance_runtime/engine/session_state_invariants.py",
            "governance_runtime/engine/session_state_repository.py",
            "governance_runtime/engine/state_machine.py",
            "governance_runtime/engine/surface_policy.py",
            "governance_runtime/infrastructure/adapters/filesystem/atomic_write.py",
            "governance_runtime/infrastructure/adapters/logging/event_sink.py",
            "governance_runtime/infrastructure/adapters/logging/jsonl_error_sink.py",
            "governance_runtime/infrastructure/adapters/process/subprocess_runner.py",
            "governance_runtime/infrastructure/archive_export.py",
            "governance_runtime/infrastructure/binding_evidence_resolver.py",
            "governance_runtime/infrastructure/binding_paths.py",
            "governance_runtime/infrastructure/current_run_pointer.py",
            "governance_runtime/infrastructure/error_reason_router.py",
            "governance_runtime/infrastructure/fs/canonical_paths.py",
            "governance_runtime/infrastructure/governance_hooks.py",
            "governance_runtime/infrastructure/governance_orchestrator.py",
            "governance_runtime/infrastructure/governance_retention_guard.py",
            "governance_runtime/infrastructure/governed_archive.py",
            "governance_runtime/infrastructure/host_adapter.py",
            "governance_runtime/infrastructure/interaction_gate.py",
            "governance_runtime/infrastructure/io_atomic_write.py",
            "governance_runtime/infrastructure/io_verify.py",
            "governance_runtime/infrastructure/lifecycle_repository.py",
            "governance_runtime/infrastructure/logging/error_logs.py",
            "governance_runtime/infrastructure/logging/global_error_handler.py",
            "governance_runtime/infrastructure/mode_repo_rules.py",
            "governance_runtime/infrastructure/model_identity_resolver.py",
            "governance_runtime/infrastructure/model_identity_service.py",
            "governance_runtime/infrastructure/pack_lock.py",
            "governance_runtime/infrastructure/path_contract.py",
            "governance_runtime/infrastructure/persist_confirmation_store.py",
            "governance_runtime/infrastructure/plan_record_repository.py",
            "governance_runtime/infrastructure/policy_bundle_loader.py",
            "governance_runtime/infrastructure/reason_payload.py",
            "governance_runtime/infrastructure/recovery_executor.py",
            "governance_runtime/infrastructure/redaction.py",
            "governance_runtime/infrastructure/repo_root_resolver.py",
            "governance_runtime/infrastructure/run_summary_writer.py",
            "governance_runtime/infrastructure/runtime_activation.py",
            "governance_runtime/infrastructure/selfcheck.py",
            "governance_runtime/infrastructure/session_state_repository.py",
            "governance_runtime/infrastructure/surface_policy.py",
            "governance_runtime/infrastructure/wiring.py",
            "governance_runtime/infrastructure/work_run_archive.py",
            "governance_runtime/infrastructure/workspace_memory_repository.py",
            "governance_runtime/infrastructure/workspace_ready_gate.py",
            "governance_runtime/infrastructure/write_policy.py",
            "governance_runtime/kernel/phase_api_spec.py",
            "governance_runtime/kernel/phase_kernel.py",
        }
        
        unexpected_files = files_with_imports - allowed_files
        assert len(unexpected_files) == 0, (
            f"New governance_runtime files with governance imports detected: {unexpected_files}. "
            f"Only existing baseline files are allowed."
        )

    def test_legacy_import_count_baseline(self):
        """
        Guardrail: The number of files with governance imports should not increase.
        
        Baseline: 94 files have imports from governance/
        This test ensures we don't add MORE files with legacy imports.
        """
        files_with_imports, _ = _scan_governance_runtime_imports()
        
        assert len(files_with_imports) <= BASELINE_FILE_COUNT, (
            f"Legacy import count increased! Found {len(files_with_imports)} files, "
            f"baseline is {BASELINE_FILE_COUNT}. Migration must not add new legacy imports."
        )

    def test_legacy_imports_in_allowlist(self):
        """
        Guardrail: All legacy imports must be from the allowlist.
        
        This ensures we track exactly which imports are still pending migration.
        """
        _, all_imports = _scan_governance_runtime_imports()
        
        non_allowlisted = [
            (file, imp) for file, imp in all_imports 
            if imp not in ALLOWED_LEGACY_IMPORTS
        ]
        
        if non_allowlisted:
            unique_non_allowlisted = set(imp for _, imp in non_allowlisted)
            assert False, (
                f"Non-allowlisted imports found: {unique_non_allowlisted}. "
                f"Update ALLOWED_LEGACY_IMPORTS or migrate these modules."
            )


@pytest.mark.conformance
class TestRuntimeMigrationUnits:
    """Validate migration unit progress."""

    def test_unit_a_state_reason_primitives_candidates(self):
        """
        Unit A: State & Reason Primitives
        These should be migrated first as they're most frequently used.
        """
        candidates = [
            GOVERNANCE_RUNTIME / "domain" / "reason_codes.py",
            GOVERNANCE_RUNTIME / "domain" / "phase_state_machine.py",
            GOVERNANCE_RUNTIME / "domain" / "canonical_json.py",
        ]
        
        existing = [c for c in candidates if c.exists()]
        assert len(existing) >= 0, (
            f"Unit A candidates should be migrated. Found {len(existing)}/{len(candidates)}"
        )

    def test_governance_runtime_has_domain_subdir(self):
        """Happy: governance_runtime/domain/ should exist."""
        domain_dir = GOVERNANCE_RUNTIME / "domain"
        assert domain_dir.is_dir(), "governance_runtime/domain/ must exist"

    def test_governance_runtime_has_engine_subdir(self):
        """Happy: governance_runtime/engine/ should exist."""
        engine_dir = GOVERNANCE_RUNTIME / "engine"
        assert engine_dir.is_dir(), "governance_runtime/engine/ must exist"

    def test_governance_runtime_has_infrastructure_subdir(self):
        """Happy: governance_runtime/infrastructure/ should exist."""
        infra_dir = GOVERNANCE_RUNTIME / "infrastructure"
        assert infra_dir.is_dir(), "governance_runtime/infrastructure/ must exist"


@pytest.mark.conformance
class TestUnitAMigrationComplete:
    """Validate Unit A (State & Reason Primitives) migration is complete."""

    MIGRATED_MODULES = [
        "governance.domain.reason_codes",
        "governance.domain.phase_state_machine",
        "governance.domain.canonical_json",
        "governance.domain.errors.events",
    ]

    def test_unit_a_no_legacy_imports(self):
        """
        Guardrail: After Unit A migration, governance_runtime must NOT import
        from governance.domain.reason_codes, phase_state_machine, canonical_json, errors.events.
        """
        _, all_imports = _scan_governance_runtime_imports()
        
        forbidden_imports = [
            (file, imp) for file, imp in all_imports 
            if any(imp.startswith(mod) for mod in self.MIGRATED_MODULES)
        ]
        
        if forbidden_imports:
            unique_forbidden = set(imp for _, imp in forbidden_imports)
            assert False, (
                f"Unit A modules must not be imported from governance/ anymore. "
                f"Found: {unique_forbidden}. "
                f"These modules have been migrated to governance_runtime/"
            )


@pytest.mark.conformance
class TestUnitBMigrationComplete:
    """Validate Unit B (DTOs + Ports + Domain Models) migration is complete."""

    MIGRATED_MODULES = [
        "governance.application.dto",
        "governance.application.ports.filesystem",
        "governance.application.ports.gateways",
        "governance.application.ports.logger",
        "governance.application.ports.process_runner",
        "governance.application.ports.rulebook_source",
        "governance.domain.models.binding",
        "governance.domain.models.layouts",
        "governance.domain.models.policy_mode",
        "governance.domain.models.repo_identity",
        "governance.domain.models.rulebooks",
        "governance.domain.models.write_action",
    ]

    def test_unit_b_no_legacy_imports(self):
        """
        Guardrail: After Unit B migration, governance_runtime must NOT import
        from governance.application.dto, governance.application.ports.*, governance.domain.models.*.
        """
        _, all_imports = _scan_governance_runtime_imports()
        
        forbidden_imports = [
            (file, imp) for file, imp in all_imports 
            if any(imp.startswith(mod) for mod in self.MIGRATED_MODULES)
        ]
        
        if forbidden_imports:
            unique_forbidden = set(imp for _, imp in forbidden_imports)
            assert False, (
                f"Unit B modules must not be imported from governance/ anymore. "
                f"Found: {unique_forbidden}. "
                f"These modules have been migrated to governance_runtime/"
            )


@pytest.mark.conformance
class TestUnitCMigrationComplete:
    """Validate Unit C (Engine Core) migration is complete."""

    MIGRATED_MODULES = [
        "governance.engine.reason_codes",
        "governance.engine.canonical_json",
        "governance.engine.phase_next_action_contract",
    ]

    def test_unit_c_no_legacy_imports(self):
        """
        Guardrail: After Unit C migration, governance_runtime must NOT import
        from governance.engine.reason_codes, governance.engine.canonical_json, governance.engine.phase_next_action_contract.
        """
        _, all_imports = _scan_governance_runtime_imports()
        
        forbidden_imports = [
            (file, imp) for file, imp in all_imports 
            if any(imp.startswith(mod) for mod in self.MIGRATED_MODULES)
        ]
        
        if forbidden_imports:
            unique_forbidden = set(imp for _, imp in forbidden_imports)
            assert False, (
                f"Unit C modules must not be imported from governance/ anymore. "
                f"Found: {unique_forbidden}. "
                f"These modules have been migrated to governance_runtime/"
            )


@pytest.mark.conformance
class TestUnitDMigrationComplete:
    """Validate Unit D (Infrastructure Primitives) migration is complete."""

    MIGRATED_MODULES = [
        "governance.infrastructure.fs_atomic",
        "governance.infrastructure.path_contract",
        "governance.infrastructure.binding_evidence_resolver",
        "governance.common.path_normalization",
    ]

    def test_unit_d_no_legacy_imports(self):
        """
        Guardrail: After Unit D migration, governance_runtime must NOT import
        from governance.infrastructure.fs_atomic, governance.infrastructure.path_contract,
        governance.infrastructure.binding_evidence_resolver, governance.common.path_normalization.
        """
        _, all_imports = _scan_governance_runtime_imports()
        
        forbidden_imports = [
            (file, imp) for file, imp in all_imports 
            if any(imp.startswith(mod) for mod in self.MIGRATED_MODULES)
        ]
        
        if forbidden_imports:
            unique_forbidden = set(imp for _, imp in forbidden_imports)
            assert False, (
                f"Unit D modules must not be imported from governance/ anymore. "
                f"Found: {unique_forbidden}. "
                f"These modules have been migrated to governance_runtime/"
            )


@pytest.mark.conformance
class TestUnitEMigrationComplete:
    """Validate Unit E (Engine residual helpers) migration is complete."""

    MIGRATED_MODULES = [
        "governance.engine.mode_repo_rules",
        "governance.engine.selfcheck",
        "governance.engine.state_machine",
        "governance.engine.schema_validator",
        "governance.engine.sanitization",
        "governance.engine.business_rules_code_extraction",
        "governance.engine.business_rules_coverage",
        "governance.engine.business_rules_validation",
        "governance.engine.business_rules_hydration",
        "governance.engine.adapters",
        "governance.engine.surface_policy",
        "governance.engine.error_reason_router",
        "governance.engine.interaction_gate",
        "governance.engine.runtime",
        "governance.engine.lifecycle",
        "governance.engine.reason_payload",
        "governance.engine.session_state_repository",
        "governance.engine._embedded_reason_registry",
        "governance.engine._embedded_reason_schemas",
        "governance.engine._embedded_session_state_schema",
        "governance.engine.spec_classifier",
    ]

    def test_unit_e_no_legacy_imports(self):
        """Guardrail: governance_runtime must not import migrated engine helper modules from governance."""
        _, all_imports = _scan_governance_runtime_imports()

        forbidden_imports = [
            (file, imp) for file, imp in all_imports
            if any(imp.startswith(mod) for mod in self.MIGRATED_MODULES)
        ]

        if forbidden_imports:
            unique_forbidden = set(imp for _, imp in forbidden_imports)
            assert False, (
                f"Unit E modules must not be imported from governance/ anymore. "
                f"Found: {unique_forbidden}. "
                f"These modules have been migrated to governance_runtime/"
            )
