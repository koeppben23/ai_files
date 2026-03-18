# R4b Legacy Sunset Delete Preparation

Generated: 2026-03-18

## Bridge Purity Snapshot

- Bridge files detected in `governance/**`: **117**
- Bridge files still containing active logic (`def`/`class`): **0**

## Bridge Files (Current Compatibility Surface)

- `governance/application/dto/phase_next_action_contract.py`
- `governance/application/policies/persistence_policy.py`
- `governance/application/repo_identity_service.py`
- `governance/application/use_cases/artifact_backfill.py`
- `governance/application/use_cases/audit_readout_builder.py`
- `governance/application/use_cases/bootstrap_persistence.py`
- `governance/application/use_cases/bootstrap_session.py`
- `governance/application/use_cases/build_reason_context.py`
- `governance/application/use_cases/evaluate_persistence_gate.py`
- `governance/application/use_cases/load_rulebooks.py`
- `governance/application/use_cases/orchestrate_run.py`
- `governance/application/use_cases/phase4_self_review.py`
- `governance/application/use_cases/phase5_iterative_review.py`
- `governance/application/use_cases/phase5_review_config.py`
- `governance/application/use_cases/phase_router.py`
- `governance/application/use_cases/repo_policy_setup.py`
- `governance/application/use_cases/resolve_operating_mode.py`
- `governance/application/use_cases/resolve_output_intent.py`
- `governance/application/use_cases/rework_clarification.py`
- `governance/application/use_cases/route_phase.py`
- `governance/application/use_cases/session_state_helpers.py`
- `governance/application/use_cases/target_path_helpers.py`
- `governance/application/use_cases/validate_plan_compliance.py`
- `governance/common/path_normalization.py`
- `governance/context/repo_context_resolver.py`
- `governance/domain/strict_exit_evaluator.py`
- `governance/engine/_embedded_reason_registry.py`
- `governance/engine/_embedded_reason_schemas.py`
- `governance/engine/_embedded_session_state_schema.py`
- `governance/engine/adapters.py`
- `governance/engine/audit_readout_contract.py`
- `governance/engine/business_rules_code_extraction.py`
- `governance/engine/business_rules_coverage.py`
- `governance/engine/business_rules_hydration.py`
- `governance/engine/business_rules_validation.py`
- `governance/engine/canonical_json.py`
- `governance/engine/command_surface.py`
- `governance/engine/content_classifier.py`
- `governance/engine/error_reason_router.py`
- `governance/engine/gate_evaluator.py`
- `governance/engine/implementation_validation.py`
- `governance/engine/interaction_gate.py`
- `governance/engine/invariants.py`
- `governance/engine/layer_classifier.py`
- `governance/engine/lifecycle.py`
- `governance/engine/mode_repo_rules.py`
- `governance/engine/next_action_resolver.py`
- `governance/engine/orchestrator.py`
- `governance/engine/path_contract.py`
- `governance/engine/phase_next_action_contract.py`
- `governance/engine/reason_codes.py`
- `governance/engine/reason_payload.py`
- `governance/engine/response_contract.py`
- `governance/engine/runtime.py`
- `governance/engine/sanitization.py`
- `governance/engine/schema_validator.py`
- `governance/engine/selfcheck.py`
- `governance/engine/session_state_invariants.py`
- `governance/engine/session_state_repository.py`
- `governance/engine/spec_classifier.py`
- `governance/engine/state_classifier.py`
- `governance/engine/state_machine.py`
- `governance/engine/surface_policy.py`
- `governance/infrastructure/archive_export.py`
- `governance/infrastructure/artifact_integrity.py`
- `governance/infrastructure/binding_evidence_resolver.py`
- `governance/infrastructure/binding_paths.py`
- `governance/infrastructure/current_run_pointer.py`
- `governance/infrastructure/error_reason_router.py`
- `governance/infrastructure/fs_atomic.py`
- `governance/infrastructure/governance_config_loader.py`
- `governance/infrastructure/governance_hooks.py`
- `governance/infrastructure/governance_orchestrator.py`
- `governance/infrastructure/governance_retention_guard.py`
- `governance/infrastructure/governed_archive.py`
- `governance/infrastructure/host_adapter.py`
- `governance/infrastructure/interaction_gate.py`
- `governance/infrastructure/io_actions.py`
- `governance/infrastructure/io_atomic_write.py`
- `governance/infrastructure/io_verify.py`
- `governance/infrastructure/lifecycle_repository.py`
- `governance/infrastructure/mode_repo_rules.py`
- `governance/infrastructure/model_identity_resolver.py`
- `governance/infrastructure/model_identity_service.py`
- `governance/infrastructure/pack_lock.py`
- `governance/infrastructure/path_contract.py`
- `governance/infrastructure/persist_confirmation_store.py`
- `governance/infrastructure/phase4_config_resolver.py`
- `governance/infrastructure/phase5_config_resolver.py`
- `governance/infrastructure/phase_api_output_policy_loader.py`
- `governance/infrastructure/plan_record_repository.py`
- `governance/infrastructure/plan_record_state.py`
- `governance/infrastructure/policy_bundle_loader.py`
- `governance/infrastructure/reason_payload.py`
- `governance/infrastructure/reason_registry_selfcheck.py`
- `governance/infrastructure/recovery_executor.py`
- `governance/infrastructure/redaction.py`
- `governance/infrastructure/repo_root_resolver.py`
- `governance/infrastructure/run_audit_artifacts.py`
- `governance/infrastructure/run_summary_writer.py`
- `governance/infrastructure/runtime_activation.py`
- `governance/infrastructure/selfcheck.py`
- `governance/infrastructure/session_pointer.py`
- `governance/infrastructure/session_state_repository.py`
- `governance/infrastructure/surface_policy.py`
- `governance/infrastructure/tenant_config.py`
- `governance/infrastructure/wiring.py`
- `governance/infrastructure/work_run_archive.py`
- `governance/infrastructure/workspace_memory_repository.py`
- `governance/infrastructure/workspace_paths.py`
- `governance/infrastructure/workspace_ready_gate.py`
- `governance/infrastructure/write_policy.py`
- `governance/kernel/gates.py`
- `governance/kernel/phase_api_spec.py`
- `governance/kernel/phase_kernel.py`
- `governance/packs/pack_lock.py`
- `governance/persistence/write_policy.py`

## Non-Pure Bridge Exceptions (Must Migrate Before Delete)

- None

## R4b Outcome

- Hard gate in conformance: bridge modules that delegate to runtime must not define local logic.
- Legacy sunset delete readiness can proceed file-by-file from this compatibility surface.
