# R2 Migration Units

**Purpose:** Define migration units for systematic import decoupling

## Principle

Not all modules should be migrated at once. Modules must be grouped into **Migration Units** that:
1. Have strong internal coupling
2. Can be migrated atomically
3. Don't create circular dependencies

## Migration Units (in order)

### Unit A: State & Reason Primitives
**Priority: 1**

Modules:
- `governance.domain.reason_codes` → `governance_runtime/domain/reason_codes.py`
- `governance.domain.phase_state_machine` → `governance_runtime/domain/phase_state_machine.py`
- `governance.domain.canonical_json` → `governance_runtime/domain/canonical_json.py`
- `governance.domain.errors.events` → `governance_runtime/domain/errors/events.py`

Rationale: Most frequently imported. Used by almost every other module.

### Unit B: Domain Models (Types)
**Priority: 2**

Modules:
- `governance.domain.models.policy_mode` → `governance_runtime/domain/models/policy_mode.py`
- `governance.domain.models.rulebooks` → `governance_runtime/domain/models/rulebooks.py`
- `governance.domain.models.binding` → `governance_runtime/domain/models/binding.py`
- `governance.domain.models.layouts` → `governance_runtime/domain/models/layouts.py`
- `governance.domain.models.repo_identity` → `governance_runtime/domain/models/repo_identity.py`
- `governance.domain.models.write_action` → `governance_runtime/domain/models/write_action.py`

Rationale: Pure type definitions. No side effects. Easy to move.

### Unit C: DTOs & Contracts
**Priority: 3**

Modules:
- `governance.application.dto.phase_next_action_contract` → `governance_runtime/application/dto/phase_next_action_contract.py`
- `governance.domain.audit_readout_contract` → `governance_runtime/domain/audit_readout_contract.py`
- `governance.domain.evidence_policy` → `governance_runtime/domain/evidence_policy.py`
- `governance.domain.operating_profile` → `governance_runtime/domain/operating_profile.py`

Rationale: Contract definitions between layers.

### Unit D: Ports & Interfaces
**Priority: 4**

Modules:
- `governance.application.ports.filesystem` → `governance_runtime/application/ports/filesystem.py`
- `governance.application.ports.gateways` → `governance_runtime/application/ports/gateways.py`
- `governance.application.ports.logger` → `governance_runtime/application/ports/logger.py`
- `governance.application.ports.process_runner` → `governance_runtime/application/ports/process_runner.py`
- `governance.application.ports.rulebook_source` → `governance_runtime/application/ports/rulebook_source.py`

Rationale: Interface definitions for external dependencies.

### Unit E: Engine Core Helpers
**Priority: 5**

Modules:
- `governance.engine.reason_codes` → `governance_runtime/engine/reason_codes.py`
- `governance.engine.canonical_json` → `governance_runtime/engine/canonical_json.py`
- `governance.engine.phase_next_action_contract` → `governance_runtime/engine/phase_next_action_contract.py`
- `governance.engine.session_state_invariants` → `governance_runtime/engine/session_state_invariants.py`
- `governance.engine.schema_validator` → `governance_runtime/engine/schema_validator.py`

Rationale: Core engine utilities.

### Unit F: FS/Path Primitives
**Priority: 6**

Modules:
- `governance.infrastructure.fs_atomic` → `governance_runtime/infrastructure/fs_atomic.py`
- `governance.infrastructure.path_contract` → `governance_runtime/infrastructure/path_contract.py`
- `governance.infrastructure.binding_evidence_resolver` → `governance_runtime/infrastructure/binding_evidence_resolver.py`
- `governance.common.path_normalization` → `governance_runtime/common/path_normalization.py`

Rationale: Highly reusable, low coupling.

### Unit G: Kernel & Gate Path
**Priority: 7**

Modules:
- `governance.kernel.phase_kernel` → `governance_runtime/kernel/phase_kernel.py`
- `governance.engine.gate_evaluator` → `governance_runtime/engine/gate_evaluator.py`
- `governance.engine.business_rules_validation` → `governance_runtime/engine/business_rules_validation.py`
- `governance.engine.business_rules_hydration` → `governance_runtime/engine/business_rules_hydration.py`
- `governance.engine.business_rules_coverage` → `governance_runtime/engine/business_rules_coverage.py`
- `governance.domain.strict_exit_evaluator` → `governance_runtime/domain/strict_exit_evaluator.py`

Rationale: Core orchestration. Many dependencies.

### Unit H: Persistence/Logging Path
**Priority: 8**

Modules:
- `governance.persistence.write_policy` → `governance_runtime/persistence/write_policy.py`
- `governance.infrastructure.logging.global_error_handler` → `governance_runtime/infrastructure/logging/global_error_handler.py`
- `governance.infrastructure.session_pointer` → `governance_runtime/infrastructure/session_pointer.py`

Rationale: Infrastructure adapters.

### Unit I: Wiring & Orchestration
**Priority: 9**

Modules:
- `governance.engine.runtime` → `governance_runtime/engine/runtime.py`
- `governance.engine.orchestrator` → `governance_runtime/engine/orchestrator.py`
- `governance.infrastructure.wiring` → `governance_runtime/infrastructure/wiring.py`
- `governance.infrastructure.policy_bundle_loader` → `governance_runtime/infrastructure/policy_bundle_loader.py`

Rationale: High-level orchestration. Many cross-cutting concerns.

### Unit J: Remainder
**Priority: 10**

Modules:
- `governance.packs.pack_lock` → `governance_runtime/packs/pack_lock.py`
- `governance.context.repo_context_resolver` → `governance_runtime/context/repo_context_resolver.py`
- Other rare adapters and edge cases.

## Bridge Strategy

For modules that are heavily imported from governance/, create temporary re-export bridges:

```python
# governance/domain/reason_codes.py
# DEPRECATED: Migrate to governance_runtime/domain/reason_codes.py
# This module will be removed in a future release.
from governance_runtime.domain.reason_codes import *
```

## Migration Rules

1. **Move first, then re-export**: Create target in governance_runtime/, then update imports, then add bridge in governance/ (if needed)

2. **Atomic within unit**: All files in a unit should be migrated together

3. **Test after each unit**: Run conformance suite to verify no regressions

4. **Bridge allowed, but documented**: Re-export bridges are OK temporarily, but must have deprecation warnings

5. **No new governance imports**: After unit migration, governance_runtime files must NOT import from governance/

## DoD per Unit

Each unit is complete when:
1. All target modules exist under governance_runtime/
2. All imports in governance_runtime/ point to new locations
3. Bridge (if any) exists with deprecation warning
4. Conformance tests pass

## Complete R2 DoD

R2 is complete when:
- All 10 units are migrated
- Zero productive imports from governance/** in governance_runtime/**
- Conformance test enforces: no new governance → governance imports in governance_runtime/
