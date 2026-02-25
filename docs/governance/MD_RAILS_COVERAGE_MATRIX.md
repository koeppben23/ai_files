# MD Rails Guidance Coverage Matrix

This document defines the required coverage for each core MD file to ensure governance functionality is not broken by refactoring.

## master.md - Required Contracts

| Contract | Status | Location |
|----------|--------|----------|
| Global Principles (fail-closed, evidence-based, scope lock, repo-first, stack-agnostic) | ✅ Present | Lines 16-22 |
| Priority Order (Master > rules > profile > addons > ticket > model) | ✅ Present | Lines 24-33 |
| SSOT/Boundary clarification (phase_api.yaml binding, MD non-binding) | ✅ Present | Lines 10-14 |
| Stability SLA reference | ✅ Present | Lines 37-41 |
| Execution Flow (phases, conditional branches) | ✅ Present | Lines 43-46 |
| Decision Memory (ADR requirement) | ✅ Present | Lines 48-57 |
| Thematic Rails references | ✅ Present | Lines 59-67 |
| Output Constraints (max files, diff lines) | ✅ Present | Lines 69-73 |
| Confidence & Gates | ✅ Present | Lines 75-79 |

### Anchor Requirements (for governance_lint.py)

| Anchor | Required |
|--------|----------|
| RULEBOOK-PRECEDENCE-POLICY | Via rules.md |
| ADDON-CLASS-BEHAVIOR-POLICY | Via rules.md |
| Stability sync note | ✅ Present |

---

## rules.md - Required Contracts

| Contract | Status | Location |
|----------|--------|----------|
| No Fabrication rule | ✅ Present | Section 1.1 |
| Scope Lock | ✅ Present | Section 1.2 |
| Evidence Obligations (ladder, proof requirements) | ✅ Present | Section 1.3 |
| Component Scope (monorepos) | ✅ Present | Section 1.4 |
| Profile Selection (explicit preferred, detection fallback) | ✅ Present | Section 2 |
| Ambiguity Handling | ✅ Present | Section 2.3 |
| Repository Guidelines as Constraints | ✅ Present | Section 3 |
| Contract & Schema Evolution Gate | ✅ Present | Section 4.1 |
| Business Rules Ledger (conditional) | ✅ Present | Section 4.2 |
| Test Coverage Matrix (conditional) | ✅ Present | Section 4.3 |
| Fast Lane (escape hatch) | ✅ Present | Section 4.4 |
| Blocking Transparency | ✅ Present | Section 6 |
| Architecture Decision Output | ✅ Present | Section 7 |
| Change Matrix | ✅ Present | Section 5 |

### Anchor Requirements (for governance_lint.py)

| Anchor | Required |
|--------|----------|
| RULEBOOK-PRECEDENCE-POLICY | ✅ Present |
| ADDON-CLASS-BEHAVIOR-POLICY | ✅ Present |
| Stability SLA reference | ✅ Present |
| Master Prompt > ... precedence | ✅ Present |

---

## start.md - Required Contracts

| Contract | Status | Location |
|----------|--------|----------|
| /start purpose (bootstrap entrypoint) | ✅ Present | Section "Purpose" |
| Binding Evidence requirement | ✅ Present | Section "Binding Evidence" |
| Preflight checks | ✅ Present | Section "Preflight" |
| Cold/Warm Start modes | ✅ Present | Section "Start Modes" |
| After Start behavior | ✅ Present | Section "After Start" |
| Blocked States semantics | ✅ Present | Section "Blocked States" |
| Kernel boundary reference | ✅ Present | Footer |

### Kernel-Enforced References

| Reference | Required |
|-----------|----------|
| bootstrap_policy.yaml | ✅ Present |
| blocked_reason_catalog.yaml | ✅ Present |
| Evidence boundary note | ✅ Present |

---

## Cognitive Heuristics Checklist

These are the "thinking patterns" that must NOT be lost:

### master.md

- [ ] Fail-closed default (missing evidence = block)
- [ ] Evidence-based reasoning requirement
- [ ] Scope lock enforcement
- [ ] Repo-first persistence
- [ ] Stack-agnostic approach
- [ ] Priority-based conflict resolution
- [ ] Phase gating for code production
- [ ] ADR recording for architectural decisions

### rules.md

- [ ] No fabrication / no hallucination
- [ ] Scope lock enforcement
- [ ] Evidence ladder (build > code > tests > docs > ticket)
- [ ] Component scope for monorepos
- [ ] Profile detection with fallback
- [ ] Ambiguity handling (don't guess)
- [ ] Contract/Schema gate enforcement
- [ ] Business rules gate (conditional)
- [ ] Test coverage gate (conditional)
- [ ] Fast lane escape hatch
- [ ] Blocking transparency

### start.md

- [ ] Bootstrap validation requirement
- [ ] Cold/Warm start distinction
- [ ] Blocked state recovery
- [ ] Kernel ownership boundary

---

## Test Coverage

Tests verifying these contracts exist in:

- `tests/test_md_rails_tripwire.py` - Operational markers absent
- `scripts/governance_lint.py` - Token/anchor presence
- `tests/test_validate_governance.py` - Governance validation

---

Last Updated: 2026-02-25
