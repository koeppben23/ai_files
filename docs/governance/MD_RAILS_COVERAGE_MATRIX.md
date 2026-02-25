# MD Rails Guidance Coverage Matrix

**Status:** PLANNING - Not yet verified
**Branch:** docs/md-rails-refactor-v4
**Last Updated:** 2026-02-25

---

## 1. Expected Contract Coverage

### master.md

| Contract | Canonical Source | Required | Verification |
|----------|------------------|----------|--------------|
| Global Principles (fail-closed, evidence-based, scope lock, repo-first, stack-agnostic) | master.md | Expected | Section present |
| Priority Order (Master > rules > profile > addons > ticket > model) | master.md | Expected | Section present |
| SSOT/Boundary clarification | master.md | Expected | Section present |
| Stability SLA reference | master.md | Expected | Token present |
| Execution Flow reference | master.md | Expected | Section present |
| Decision Memory (ADR) | master.md | Expected | Section present |
| Thematic Rails references | master.md | Expected | References present |
| Output discipline | master.md | Advisory | Section present |

### rules.md

| Contract | Canonical Source | Required | Verification |
|----------|------------------|----------|--------------|
| No Fabrication | rules.md | Expected | Section present |
| Scope Lock | rules.md | Expected | Section present |
| Evidence Obligations | rules.md | Expected | Section present |
| Component Scope | rules.md | Expected | Section present |
| Profile Selection | rules.md | Expected | Section present |
| Ambiguity Handling | rules.md | Expected | Section present |
| Repository Guidelines | rules.md | Expected | Section present |
| Contract/Schema Gate | rules.md | Expected | Section present |
| Business Rules Gate | rules.md | Conditional | Section present |
| Test Coverage Gate | rules.md | Conditional | Section present |
| Fast Lane | rules.md | Advisory | Section present |
| Blocking Transparency | rules.md | Expected | Section present |
| Architecture Decision Output | rules.md | Expected | Section present |
| Change Matrix | rules.md | Expected | Section present |

### Anchor Requirements

| Anchor | Canonical Source | Required | Verification |
|--------|------------------|----------|--------------|
| RULEBOOK-PRECEDENCE-POLICY | rules.md | Expected | Anchor present |
| ADDON-CLASS-BEHAVIOR-POLICY | rules.md | Expected | Section present |
| Stability sync note | master.md | Expected | Token present |

---

## 2. Expected Cognitive Heuristics

| Heuristic | Expected Location | Must Survive | Verification |
|-----------|-----------------|--------------|--------------|
| Fail-closed default | master.md | Yes | Semantic present |
| Evidence-based | master.md/rules.md | Yes | Semantic present |
| Scope lock | rules.md | Yes | Semantic present |
| Repo-first | master.md | Yes | Semantic present |
| Stack-agnostic | master.md | Yes | Semantic present |
| Priority resolution | master.md | Yes | Semantic present |
| Phase gating | master.md | Yes | Semantic present |
| No fabrication | rules.md | Yes | Semantic present |
| Evidence ladder | rules.md | Yes | Semantic present |
| Ambiguity handling | rules.md | Yes | Semantic present |
| Gate enforcement | rules.md | Yes | Semantic present |
| Blocking transparency | rules.md | Yes | Semantic present |
| Bootstrap validation | start.md | Yes | Semantic present |
| Cold/Warm start | start.md | Yes | Semantic present |
| Recovery semantics | start.md | Yes | Semantic present |
| Kernel boundary | start.md | Yes | Semantic present |

---

## 3. Regression Rules

What must NOT happen:

- [ ] Required contract missing entirely
- [ ] Contract duplicated normatively across files
- [ ] Kernel-owned logic in MD files
- [ ] Important heuristic removed

---

## 4. Verification Methods

| Method | Used For |
|--------|----------|
| Section present | Structural requirements |
| Token present | Specific phrases/anchors |
| Semantic present | Cognitive heuristics |

---

## 5. Review Checklist (To be completed after refactor)

- [ ] All Expected contracts present
- [ ] All Cognitive heuristics preserved
- [ ] No Regression Rules triggered
- [ ] governance_lint.py passes
- [ ] MD rails coverage checks pass
- [ ] Semantic review: Intended behavior preserved

---

## 6. Change Log (To be updated during refactor)

| Date | File | Change | Coverage Impact |
|------|------|--------|-----------------|
| 2026-02-25 | - | Baseline established | N/A |

---

*This matrix is a planning document. It will be verified after the refactoring effort.*
