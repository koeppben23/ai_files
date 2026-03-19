# R2 Runtime Import Decoupling - Migration Inventory

**Generated:** 2026-03-18
**Purpose:** Document current state of governance_runtime → governance imports

## Summary

- **94 files** in governance_runtime/ import from governance/
- **~300+ import edges** from governance_runtime to governance modules

## Cluster by Target Module

| Target Module | File Count | Example Imports |
|---------------|------------|-----------------|
| governance.domain.* | ~35 | reason_codes, phase_state_machine, canonical_json, operating_profile |
| governance.infrastructure.* | ~30 | fs_atomic, path_contract, binding_evidence_resolver |
| governance.engine.* | ~20 | gate_evaluator, reason_codes, business_rules_* |
| governance.application.* | ~15 | use_cases, policies, ports, dto |
| governance.common.* | 2 | path_normalization |
| governance.context.* | 1 | repo_context_resolver |
| governance.packs.* | 2 | pack_lock |
| governance.kernel.* | 1 | phase_kernel |

## Affected Files (94 total)

### governance_runtime/application/
- dto/phase_next_action_contract.py → governance.domain.phase_state_machine
- policies/persistence_policy.py → governance.domain.phase_state_machine, governance.domain.reason_codes
- ports/logger.py → governance.domain.errors.events
- ports/rulebook_source.py → governance.domain.models.rulebooks
- repo_identity_service.py → governance.common.path_normalization
- use_cases/artifact_backfill.py → governance.application.ports.filesystem
- use_cases/audit_readout_builder.py → governance.domain.audit_readout_contract, governance.domain.canonical_json
- use_cases/bootstrap_persistence.py → governance.application.ports.*, governance.domain.*
- use_cases/bootstrap_session.py → governance.application.ports.gateways, governance.domain.reason_codes
- use_cases/build_reason_context.py → governance.application.ports.gateways, governance.domain.reason_codes
- use_cases/evaluate_persistence_gate.py → governance.application.policies.persistence_policy
- use_cases/load_rulebooks.py → governance.application.ports.rulebook_source, governance.domain.*
- use_cases/orchestrate_run.py → governance.application.policies.persistence_policy, governance.domain.*
- use_cases/phase5_iterative_review.py → governance.application.use_cases.phase5_review_config
- use_cases/phase_router.py → governance.domain.strict_exit_evaluator, governance.kernel.phase_kernel
- use_cases/repo_policy_setup.py → governance.application.repo_identity_service
- use_cases/resolve_operating_mode.py → governance.domain.operating_profile
- use_cases/resolve_output_intent.py → governance.domain.phase_state_machine
- use_cases/route_phase.py → governance.domain.policies.*

### governance_runtime/cli/
- backfill.py → governance.application.use_cases.artifact_backfill
- bootstrap_executor.py → governance.application.use_cases.repo_policy_setup
- deps.py → governance.application.ports.process_runner, governance.domain.errors.events
- route.py → governance.application.use_cases.route_phase

### governance_runtime/domain/
- audit_readout_contract.py → governance.engine.schema_validator
- integrity.py → governance.domain.canonical_json
- models/session_state.py → governance.domain.models.policy_mode
- strict_exit_evaluator.py → governance.domain.evidence_policy, governance.domain.reason_codes

### governance_runtime/engine/
- adapters.py → governance.engine.canonical_json, governance.infrastructure.*
- audit_readout_contract.py → governance.domain.audit_readout_contract
- business_rules_coverage.py → governance.engine.business_rules_code_extraction
- business_rules_hydration.py → governance.engine.business_rules_validation
- business_rules_validation.py → governance.engine.business_rules_code_extraction
- canonical_json.py → governance.domain.canonical_json
- gate_evaluator.py → governance.application.use_cases.validate_plan_compliance, governance.domain.*
- implementation_validation.py → governance.infrastructure.fs_atomic
- layer_classifier.py → governance.engine
- lifecycle.py → governance.domain.reason_codes, governance.infrastructure.*
- orchestrator.py → governance.application.use_cases, governance.infrastructure.*
- path_contract.py → governance.infrastructure.path_contract
- phase_next_action_contract.py → governance.application.dto.phase_next_action_contract
- reason_codes.py → governance.domain.reason_codes
- reason_payload.py → governance.engine._embedded_*, governance.engine.*
- response_contract.py → governance.application.use_cases.target_path_helpers, governance.domain.*
- runtime.py → governance.engine.gate_evaluator, governance.engine.*
- selfcheck.py → governance.domain.reason_codes, governance.engine.mode_repo_rules
- session_state_invariants.py → governance.domain.phase_state_machine
- session_state_repository.py → governance.engine._embedded_*, governance.engine.*
- state_machine.py → governance.domain.phase_state_machine
- surface_policy.py → governance.engine.adapters

### governance_runtime/infrastructure/
- adapters/filesystem/atomic_write.py → governance.domain.models.write_action
- adapters/logging/event_sink.py → governance.infrastructure.fs_atomic
- adapters/logging/jsonl_error_sink.py → governance.domain.errors.events
- adapters/process/subprocess_runner.py → governance.application.ports.process_runner
- archive_export.py → governance.domain.*, governance.engine.*
- binding_evidence_resolver.py → governance.infrastructure.path_contract
- binding_paths.py → governance.infrastructure.path_contract
- current_run_pointer.py → governance.infrastructure.fs_atomic
- error_reason_router.py → governance.engine.error_reason_router
- fs/canonical_paths.py → governance.infrastructure.path_contract
- governance_hooks.py → governance.domain.*, governance.infrastructure.*
- governance_orchestrator.py → governance.domain.*, governance.infrastructure.*
- governance_retention_guard.py → governance.domain.regulated_mode, governance.domain.retention
- governed_archive.py → governance.domain.*, governance.infrastructure.*
- host_adapter.py → governance.engine.adapters
- interaction_gate.py → governance.engine.interaction_gate
- io_atomic_write.py → governance.infrastructure.fs_atomic
- io_verify.py → governance.domain.canonical_json, governance.domain.operating_profile
- lifecycle_repository.py → governance.engine.lifecycle
- logging/error_logs.py → governance.infrastructure.*
- logging/global_error_handler.py → governance.infrastructure.adapters.logging.event_sink, governance.paths
- mode_repo_rules.py → governance.engine.mode_repo_rules
- model_identity_resolver.py → governance.domain.model_identity
- model_identity_service.py → governance.domain.model_identity, governance.domain.reason_codes
- pack_lock.py → governance.packs.pack_lock
- path_contract.py → governance.common.path_normalization
- persist_confirmation_store.py → governance.domain.*
- plan_record_repository.py → governance.application.policies.persistence_policy
- policy_bundle_loader.py → governance.infrastructure.*
- reason_payload.py → governance.engine.reason_payload
- recovery_executor.py → governance.domain.failure_model
- redaction.py → governance.domain.classification
- repo_root_resolver.py → governance.context.repo_context_resolver
- run_summary_writer.py → governance.infrastructure.binding_evidence_resolver
- runtime_activation.py → governance.engine.runtime
- selfcheck.py → governance.engine.selfcheck
- session_state_repository.py → governance.engine.session_state_repository
- surface_policy.py → governance.engine.surface_policy
- wiring.py → governance.application.policies.persistence_policy, governance.infrastructure.*
- work_run_archive.py → governance.domain.*, governance.infrastructure.*
- workspace_memory_repository.py → governance.application.policies.persistence_policy
- workspace_ready_gate.py → governance.domain.*, governance.infrastructure.*
- write_policy.py → governance.persistence.write_policy

### governance_runtime/kernel/
- phase_api_spec.py → governance.infrastructure.binding_evidence_resolver
- phase_kernel.py → governance.application.dto.*, governance.domain.*, governance.engine.*, governance.infrastructure.*

## DoD for R2 Complete

R2 is finished when:
1. governance_runtime/** has ZERO productive imports from governance/**
2. governance/ only contains re-export bridges or dead code
3. Conformance tests enforce: no new governance → governance_runtime imports allowed
