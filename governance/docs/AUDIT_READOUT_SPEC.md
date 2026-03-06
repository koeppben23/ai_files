# AUDIT_READOUT_SPEC

## Purpose
Defines the audit readout contract for workspace state, archived run snapshots, event chain, and integrity checks.

This spec is normative for readout shape and deterministic checks. Kernel routing and phase policy remain in `phase_api.yaml` and runtime code.

---

## Version
`AUDIT_READOUT_SPEC.v1`

---

## Workspace Model (Normative)

- Root working copy (mutable):
  - `SESSION_STATE.json`
  - `plan-record.json` (optional)
  - `events.jsonl`
  - `current_run.json`
- Archived runs (immutable): `runs/<run_id>/...`
  - `SESSION_STATE.json` (required)
  - `metadata.json` (required)
  - `plan-record.json` (optional)

`events.jsonl` is workspace-root only and MUST NOT be mirrored in `runs/<run_id>/`.

---

## Readout Contract (v1)

Top-level fields:

- `contract_version`
- `active`
- `last_snapshot`
- `chain`
- `integrity`

### `contract_version`
MUST equal `AUDIT_READOUT_SPEC.v1`.

### `active`
Current mutable working state from root `SESSION_STATE.json`.

Required:

- `run_id`
- `phase`
- `active_gate`
- `next`
- `updated_at` (RFC3339 UTC with `Z`)

### `last_snapshot`
Most recent archived immutable snapshot distinct from active root working copy.

Required:

- `snapshot_path`
- `snapshot_digest`
- `archived_at`
- `source_phase`
- `run_id`

Selection rule:

1. Prefer the latest `new_work_session_created` event reference in `events.jsonl` that resolves to an existing archived run and is distinct from active run.
2. Fallback to newest archive by `metadata.archived_at` in `runs/<run_id>/` (excluding active run when possible).

### `chain`
Tail of root `events.jsonl` (newest last).

Required:

- `tail_count`
- `events[]`

Each event requires:

- `event`
- `observed_at` (RFC3339 UTC with `Z`)
- `repo_fingerprint`
- `session_id`
- `run_id`

Event-specific requirements:

- `new_work_session_created`: MUST include `snapshot_path`, `snapshot_digest`, `new_run_id`.
- `work_session_reactivated`: MUST include `reactivated_run_id`.
- `new_work_session_deduped` / `new_work_session_dedupe_bypassed`: MUST include `reason`.

Read-only revisit operations MUST NOT emit chain events.

### `integrity`
Deterministic consistency checks.

Required:

- `snapshot_ref_present` (bool)
- `run_id_consistent` (bool)
- `monotonic_timestamps` (bool)
- `active_run_pointer_consistent` (bool)
- `reactivation_chain_consistent` (bool)
- `notes[]` (optional diagnostics; never used as logic input)

---

## Snapshot Metadata Contract (Archived Run)

`metadata.json` minimum fields:

- `schema`
- `repo_fingerprint`
- `run_id`
- `archived_at`
- `source_phase`
- `source_active_gate`
- `source_next`
- `snapshot_digest`
- `snapshot_digest_scope`
- `archived_files`
- optional: `ticket_digest`, `task_digest`, `plan_record_digest`, `impl_digest`

`plan-record.json` remains optional; its absence MUST NOT invalidate readout.

---

## Digest Norm

`snapshot_digest` is evaluated by `snapshot_digest_scope`.

For `snapshot_digest_scope = session_state`:

- canonical JSON serialization of archived `SESSION_STATE.json`
- UTF-8
- sorted object keys
- no insignificant whitespace
- SHA-256 lowercase hex

---

## Deterministic Rules

1. Mutable vs immutable
   - root `SESSION_STATE.json` is mutable
   - `current_run.json` is mutable pointer state
   - `runs/<run_id>/...` is immutable

2. Run chain consistency
   - `run_id_consistent=true` iff active run matches latest relevant chain node:
     - `new_work_session_created` -> `active.run_id == new_run_id`
     - `work_session_reactivated` -> `active.run_id == reactivated_run_id`
     - else -> `active.run_id == run_id`

3. Pointer consistency
   - `active_run_pointer_consistent=true` iff `current_run.json.active_run_id == active.run_id`.

4. Reactivation consistency
   - `reactivation_chain_consistent=true` iff every `reactivated_run_id` exists in archives and the latest reactivation aligns with active root + pointer.

5. Monotonic timestamps
   - event timestamps are non-decreasing in chain tail
   - `last_snapshot.archived_at <= first chain event referencing that snapshot` (if reference present)

---

## Acceptance

Audit-readout is compliant when:

- active root state, pointer state, archive state, and event chain are all represented
- `last_snapshot` comes from archive model (never from mutable root)
- no `work_runs/*` assumptions remain in code/tests/spec
- event timeline remains reconstructable for create + reactivation flows
