# AUDIT_READOUT_SPEC

## Purpose
This document defines the **audit readout contract** for a workspace: how to report the current run state, the last archived run snapshot, the event chain, and integrity checks.

It is **normative for readout shape and invariants**.
It does **not** redefine kernel routing or phase policy (SSOT remains in `phase_api.yaml` and runtime code).

---

## Scope and Non-Goals

### In scope
- Readout schema and required fields
- Snapshot/event minimum contracts
- Deterministic integrity checks
- Acceptance criteria for audit-complete behavior

### Out of scope
- Phase transition semantics
- Gate policy definitions
- Kernel decision logic internals

---

## Version
This specification is `AUDIT_READOUT_SPEC.v1`.
Any breaking contract change MUST bump the version.

---

## Readout Contract (v1)

A readout MUST provide the following top-level sections:

- `contract_version`
- `active`
- `last_snapshot`
- `chain`
- `integrity`

### `contract_version`
**Required**
- `contract_version` MUST equal `AUDIT_READOUT_SPEC.v1`.

### `active`
Current mutable working state from `SESSION_STATE.json`.

**Required fields**
- `run_id`
- `phase`
- `active_gate`
- `next`
- `updated_at`

**Time format**
- `updated_at` MUST be RFC3339 UTC (e.g., `2026-03-05T20:34:32Z`).

### `last_snapshot`
Metadata for the most recently archived immutable run snapshot in `work_runs/`.

**Required fields**
- `snapshot_path`
- `snapshot_digest`
- `archived_at`
- `source_phase`
- `run_id`

**Time format**
- `archived_at` MUST be RFC3339 UTC.

### `chain`
Tail of the append-only event chain from `events.jsonl`.

**Required fields**
- `tail_count` (N)
- `events[]` (last N events, newest last)

Each event item MUST include:
- `event`
- `observed_at`
- `repo_fingerprint`
- `session_id`
- `run_id`

`observed_at` MUST be RFC3339 UTC.

Events SHOULD include (when present in tail):
- `new_work_session_created`
- `new_work_session_deduped`
- `new_work_session_dedupe_bypassed`

### `integrity`
Deterministic integrity checks linking `active`, `last_snapshot`, and `chain`.

**Required fields**
- `snapshot_ref_present` (bool)
- `run_id_consistent` (bool)
- `monotonic_timestamps` (bool)
- `notes[]` (optional, human-readable findings)

`notes[]` MUST NOT be used for logic.

---

## Snapshot Contract (Immutable) - Minimum Fields

Every archived snapshot MUST include:

- `schema`
- `repo_fingerprint`
- `session_run_id`
- `archived_at`
- `source_phase`
- `source_active_gate`
- `source_next`
- `ticket_digest` (nullable allowed if ticket was never present)
- `task_digest` (nullable allowed if task was never present)
- `plan_record_digest` (nullable)
- `impl_digest` (nullable)
- `session_state` (full state at archive time)

### Immutability
- Snapshot files in `work_runs/` MUST be append-only / immutable once written.

---

## Snapshot Digest Norm

`snapshot_digest` MUST be computed over the **entire snapshot JSON document** using canonical JSON serialization and a fixed hash algorithm.

### Canonicalization MUST
- UTF-8 encoding
- Object keys sorted
- No insignificant whitespace
- Stable JSON number representation

### Hash MUST
- Algorithm: SHA-256
- Encoding: lowercase hex

### Integrity consequence
- `snapshot_digest` MUST change if **any** snapshot field changes (metadata or `session_state`).

### Optional companion digest
- `session_state_digest` MAY be provided for state-only comparisons.

---

## Event Contract (Append-Only) - Minimum Fields

All events in `events.jsonl` MUST include:

- `event`
- `observed_at`
- `repo_fingerprint`
- `session_id`
- `run_id`

### `new_work_session_created` additional fields
MUST include:
- `previous_run_id`
- `new_run_id`
- `phase`
- `next`
- `snapshot_path`
- `snapshot_digest`

(For v1, **both** `snapshot_path` and `snapshot_digest` are mandatory.)

### `new_work_session_deduped` / `new_work_session_dedupe_bypassed`
MUST include:
- `reason` (string; canonical reasons preferred)

### Append-only
- `events.jsonl` MUST be append-only. No in-place edits.

---

## Deterministic Audit Rules

1) **Mutable vs immutable**
- `SESSION_STATE.json` MAY be overwritten.
- `work_runs/*` snapshots MUST NOT be overwritten.

2) **Reset -> snapshot linkage**
- Every reset that sets Phase back to **Phase 4** MUST have exactly one referenceable snapshot of the prior run.
- Linkage MUST be reconstructable from `events.jsonl` via `previous_run_id -> new_run_id` and snapshot refs.

3) **Run chain consistency**
- Readout MUST reconstruct a run chain from `previous_run_id -> new_run_id`.
- `run_id_consistent=true` only if the active run id matches the latest relevant chain node:
  - for `new_work_session_created`: `active.run_id == last_event.new_run_id`
  - otherwise: `active.run_id == last_event.run_id`

4) **Monotonic timestamps**
- `monotonic_timestamps=true` only if:
  - event `observed_at` is non-decreasing within the tail, and
  - `last_snapshot.archived_at <= first event that references that snapshot` (if present in tail)

5) **Kernel invariants (observable)**
- No persisted state MUST contain `iteration > max_iterations` for any persisted review loop counters.

---

## Acceptance Tests (Smoke / Failure)

A system is audit-complete when:

1) **Single click "New Session"**
- Creates one immutable snapshot
- Resets active session to Phase 4
- Appends `new_work_session_created` with `snapshot_path + snapshot_digest`

2) **Double click / rapid repeat**
- Dedupe prevents duplicate archive corruption
- Either:
  - one snapshot + `new_work_session_deduped`, or
  - distinct snapshots with consistent run linkage (if explicitly intended)

3) **Crash between archive/reset**
- System MUST be either:
  - atomically completed, OR
  - leaves a detectable incomplete marker (and does not silently mis-link runs)

4) **Replay**
- From `last_snapshot` + `chain` tail, timeline of resets and run transitions MUST be reconstructable deterministically.

---

## Compliance
Implementations claiming v1 compliance MUST satisfy all `MUST` clauses in this document.
