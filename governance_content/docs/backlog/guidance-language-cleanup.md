# Backlog: Guidance-Surface Language Cleanup

**Status:** planned
**Priority:** medium
**Created:** 2026-03-07
**Context:** P3 Rail-Style-Spec v1 Rewrite (phase-b-contract-hardening)

## Summary

`master.md` and `rules.md` are classified as **guidance** documents in
`docs/contracts/rail-style-spec.v1.md` (Section 2, row "guidance"). They are
consumed by the LLM for cross-phase behavioral reasoning but are **not**
execution-facing command rails.

During P3, all 5 execution-facing rails and `BOOTSTRAP.md` were rewritten to
the rail-style-spec v1 5-block structure. Guidance documents were explicitly
excluded from that scope ("reviewed separately under the guidance-language
cleanup track").

## Scope

Review `master.md` and `rules.md` for:

1. **Banned patterns from rail-style-spec v1 Section 6** that leaked into
   guidance prose — e.g., `safe to execute`, self-referential `authoritative`
   (without backtick SSOT ref), `must NEVER` cascades.
2. **Pressure-based tiering language** (Tier A / Tier B / Tier C) — should not
   appear in guidance documents either.
3. **Cross-agent neutrality** — ensure guidance wording does not assume a
   specific model family's compliance behavior.
4. **`kernel-owned` usage** — verify every occurrence has a backtick SSOT ref
   (CR-03 already enforces this in tests, but a manual review may surface
   edge cases in table cells or prose).

## Out of Scope

- Rulebooks (`profiles/`) — separate track, not part of this backlog item.
- Execution-facing rails — already completed in P3 commits C1–C4.
- `BOOTSTRAP.md` — already completed in P3 commit C3.

## References

- `docs/contracts/rail-style-spec.v1.md` Section 2 (document classification)
- `docs/contracts/cross-agent-rail-spec.v1.md` CR-01..CR-09
- `tests/test_rail_conformance_sweep.py` (existing CR enforcement)

## Acceptance Criteria

- [ ] `master.md` reviewed; banned patterns removed or rewritten
- [ ] `rules.md` reviewed; banned patterns removed or rewritten
- [ ] All existing contract tests still pass after changes
- [ ] No new trust-triggering or pressure-based language introduced
