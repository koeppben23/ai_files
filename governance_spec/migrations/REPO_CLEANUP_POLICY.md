# Repo Cleanup Policy

Generated: 2026-03-19

## Classification Rules

### Keep

Keep artifacts with at least one active purpose:

- User value (README/quickstart/operator guidance)
- Runtime or installer value
- Active contract or proof value
- Final-state gate value
- Frozen compatibility value

### Archive

Archive artifacts that keep historical traceability but are no longer operational.

- Archived migration records belong under `governance_spec/migrations/archived/`
- Archived records must not be used as active policy inputs

### Delete

Delete artifacts that have no active value and no archive value:

- Python/test cache artifacts (`__pycache__`, `*.pyc`, `.pytest_cache`)
- Unclassified backlog notes
- Redundant raw dumps replaced by canonical proof documents

## Active vs Archived Migration Scope

Active migration records remain in `governance_spec/migrations/`.
Historical migration records move to `governance_spec/migrations/archived/`.

## Cleanup Invariants

- No Python cache artifacts tracked in the repository tree.
- No unclassified backlog markdown under `governance_content/docs/backlog/`.
- No redundant frozen-surface raw dump in active migrations.
- Historical R2 migration records stay archived, not active.
