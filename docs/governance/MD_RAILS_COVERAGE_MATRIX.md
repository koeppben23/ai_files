# MD Rails Guidance Coverage Matrix

This document defines the required coverage for each core MD file to ensure governance functionality is not broken by refactoring.

**This is a review artifact, not self-praise. Update on each significant MD change.**

---

## 1. File Contract Coverage

| Contract | Canonical Source | Required | Verification |
|----------|------------------|----------|--------------|
| Global Principles (fail-closed, evidence-based, scope lock, repo-first, stack-agnostic) | master.md | Required | Section present |
| Priority Order (Master > rules > profile > addons > ticket > model) | master.md | Required | Section present |
| SSOT/Boundary clarification (phase_api.yaml binding, MD non-binding) | master.md | Required | Section present |
| Stability SLA reference | master.md | Required | Token present |
| Execution Flow (high-level phase model reference) | master.md | Optional reference | Section present |
| Decision Memory (ADR requirement) | master.md | Required | Section present |
| Thematic Rails references | master.md | Required | References present |
| Output discipline reference | master.md | Advisory | Section present |

### rules.md

| Contract | Canonical Source | Required | Verification |
|----------|------------------|----------|--------------|
| No Fabrication rule | rules.md | Required | Section present |
| Scope Lock | rules.md | Required | Section present |
| Evidence Obligations | rules.md | Required | Section present |
| Component Scope (monorepos) | rules.md | Required | Section present |
| Profile Selection (explicit preferred, detection fallback) | rules.md | Required | Section present |
| Ambiguity Handling | rules.md | Required | Section present |
| Repository Guidelines as Constraints | rules.md | Required | Section present |
| Contract & Schema Evolution Gate | rules.md | Required | Section present |
| Business Rules Ledger (conditional) | rules.md | Conditional | Section present |
| Test Coverage Matrix (conditional) | rules.md | Conditional | Section present |
| Fast Lane (escape hatch) | rules.md | Advisory | Section present |
| Blocking Transparency | rules.md | Required | Section present |
| Architecture Decision Output | rules.md | Required | Section present |
| Change Matrix | rules.md | Required | Section present |

### Anchor Requirements (governance_lint.py)

| Anchor | Canonical Source | Required | Verification |
|--------|------------------|----------|--------------|
| RULEBOOK-PRECEDENCE-POLICY | rules.md | Required | Anchor present |
| ADDON-CLASS-BEHAVIOR-POLICY | rules.md | Required | Section present |
| Stability sync note | master.md | Required | Token present |
| Master Prompt precedence chain | rules.md | Required | Text present |

---

## start.md

| Contract | Canonical Source | Required | Verification |
|----------|------------------|----------|--------------|
| /start purpose (bootstrap entrypoint) | start.md | Required | Section present |
| Binding Evidence requirement | start.md | Required | Section present |
| Preflight checks | start.md | Required | Section present |
| Cold/Warm Start modes | start.md | Required | Section present |
| After Start behavior | start.md | Required | Section present |
| Blocked States semantics | start.md | Required | Section present |
| Recovery semantics | start.md | Required | Section present |
| Kernel boundary reference | start.md | Required | Reference present |

### Kernel-Enforced References

| Reference | Canonical Source | Required | Verification |
|-----------|------------------|----------|--------------|
| bootstrap_policy.yaml | start.md | Required | Token present |
| blocked_reason_catalog.yaml | start.md | Required | Token present |
| Evidence boundary note | start.md | Required | Token present |

---

## 2. Cognitive Heuristics Coverage

These are the "thinking patterns" that must NOT be lost. They may live in any MD file but must exist somewhere.

| Heuristic | Must Survive Refactor | Expected Location | Verification |
|-----------|---------------------|-------------------|--------------|
| Fail-closed default (missing evidence = block) | Yes | master.md | Semantic present |
| Evidence-based reasoning requirement | Yes | master.md/rules.md | Semantic present |
| Scope lock enforcement | Yes | rules.md | Semantic present |
| Repo-first persistence | Yes | master.md | Semantic present |
| Stack-agnostic approach | Yes | master.md | Semantic present |
| Priority-based conflict resolution | Yes | master.md | Semantic present |
| Phase gating for code production | Yes | master.md | Semantic present |
| No fabrication / no hallucination | Yes | rules.md | Semantic present |
| Evidence ladder (build > code > tests > docs > ticket) | Yes | rules.md | Semantic present |
| Component scope for monorepos | Yes | rules.md | Semantic present |
| Profile detection with fallback | Yes | rules.md | Semantic present |
| Ambiguity handling (don't guess) | Yes | rules.md | Semantic present |
| Contract/Schema gate enforcement | Yes | rules.md | Semantic present |
| Business rules gate (conditional) | Yes | rules.md | Semantic present |
| Test coverage gate (conditional) | Yes | rules.md | Semantic present |
| Blocking transparency | Yes | rules.md | Semantic present |
| Bootstrap validation requirement | Yes | start.md | Semantic present |
| Cold/Warm start distinction | Yes | start.md | Semantic present |
| Blocked state recovery | Yes | start.md | Semantic present |
| Kernel ownership boundary | Yes | start.md | Semantic present |

---

## 3. Regression Rules

What must NOT happen:

- [ ] Required contract missing entirely
- [ ] Contract duplicated normatively across files
- [ ] Kernel-owned logic reintroduced in MD files
- [ ] Important heuristic removed without updating coverage matrix
- [ ] Anchor shifted without test adjustment

---

## 4. Verification Methods

| Method | Used For | Definition |
|--------|----------|------------|
| Section present | Structural requirements | Heading exists and contains substantive content |
| Token present | Specific phrases/anchors | Exact phrase or anchor exists |
| Semantic present | Cognitive heuristics | Text still expresses the same operational intent, even if wording changed. Key indicators: same safety posture, same conflict handling intent, same failure behavior intent, same scope discipline intent |
| Anchor present | governance_lint.py string anchors | Anchor exists in file |
| Reference present | Cross-file references | Reference to external file/catalog exists |

---

## 5. Review Checklist

Before merging any MD refactor:

- [ ] All Required contracts still present (see Section 1)
- [ ] All Cognitive heuristics preserved (see Section 2)
- [ ] No Regression Rules triggered (see Section 3)
- [ ] governance_lint.py passes
- [ ] test_md_rails_coverage.py passes
- [ ] Semantic review: Is intended behavior and guidance preserved?

---

## 6. Change Log for Coverage Decisions

| Date | File | Change | Coverage Impact | Matrix Updated |
|------|------|--------|-----------------|---------------|
| 2026-02-25 | master.md | Initial refactor: reduced to core guidance | No required contract loss | Yes |
| 2026-02-25 | rules.md | Initial refactor: focused on technical core rules | No required contract loss | Yes |
| 2026-02-25 | start.md | Initial refactor: minimal bootstrap semantics | No required contract loss | Yes |
| 2026-02-25 | governance_lint.py | Commented out output-detail checks | Adapted to reduced MD scope | Yes |

---

Last Updated: 2026-02-25
Last Reviewer: [PR Author / Reviewer]
