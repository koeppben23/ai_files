# MD Rails Refactor Baseline

**Date:** 2026-02-25
**Branch:** docs/md-rails-refactor-v4
**Base:** main

---

## Current State (Before Refactor)

### master.md
- **Lines:** 3696
- **Key Sections:** Phase execution, gates, output contracts, next-action, blocker envelope, start modes, snapshots, quick-fix commands, architect autopilot, trusted discovery, rulebook evidence, phase 2/2.1/1.5 specifics, host constraint compat, SESSION_STATE formatting

### rules.md
- **Lines:** 1858
- **Key Sections:** Technical rules, evidence, profile selection, gates, output presentation

### start.md
- **Lines:** 186
- **Key Content:** Output envelope specs, search order, bootstrap_policy references, blocker envelopes, start banners

### Other MD files
- continue.md: 23 lines
- resume.md: 34 lines
- resume_prompt.md: 44 lines

### Current Test/Lint Status
- governance_lint.py: ✅ PASS on main
- test_md_rails_coverage.py: N/A (doesn't exist)

---

## Known Issues with Current State

1. **MDs contain kernel-owned logic:** Output rendering, envelope formats, presentation details
2. **Over-specified:** Too many exact tokens required
3. **Redundancy:** Same rules duplicated across MDs
4. **Tight coupling:** Lint enforces exact wording

---

## Migration Planning Table

| Rule/Content | Current Source | Target | Action |
|--------------|---------------|--------|--------|
| Global Principles | master.md | master.md | KEEP |
| Priority Order | master.md | master.md | KEEP |
| Fail-Closed Mode | master.md/rules.md | master.md | KEEP |
| Scope Lock | rules.md | rules.md | KEEP |
| Evidence Ladder | rules.md | rules.md | KEEP |
| Phase Table | master.md | - | REDUCE to reference |
| Output Envelope | master.md/rules/start | - | REMOVE (kernel-owned) |
| NEXT-ACTION Format | master.md/rules/start | - | REMOVE (kernel-owned) |
| Blocker Envelope | master.md/rules/start | - | REMOVE (kernel-owned) |
| Start Mode Banner | master.md/rules/start | - | REMOVE (kernel-owned) |
| Snapshot Format | master.md/rules/start | - | REMOVE (kernel-owned) |
| Quick-Fix Commands | master.md/rules/start | - | REMOVE (kernel-owned) |
| Trusted Discovery | master.md | - | REMOVE (kernel-owned) |
| SESSION_STATE Format | master.md/rules/start | - | REMOVE (kernel-owned) |
| Host Constraint Compat | master.md/rules/start | - | REMOVE (kernel-owned) |
| Thematic Rails | master.md | docs/governance/rails/ | MOVE reference |

---

## Target State (After Refactor)

- master.md: ~100 lines (global guidance)
- rules.md: ~250 lines (technical core)
- start.md: ~60 lines (bootstrap semantics)
- governance_lint.py: Adapted to reduced scope
