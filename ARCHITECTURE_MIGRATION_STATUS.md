# Architecture Migration Status

**Stand:** 2026-02-24  
**Branch:** main  
**Scope:** Governance SSOT kernel/orchestrator consolidation

---

## Executive Summary

The migration is now in the **stabilization phase** rather than the early failed state.
The old narrative around `PR #267` being the active status is obsolete.

Recent merged PRs on main:

- `#291` bootstrap mode SSOT + path guards + session compatibility restoration
- `#292` gitless test fallback (`git ls-files` fallback for distribution/ZIP contexts)
- `#293` fail-closed JSONL gate emission on blocked persistence preconditions
- `#294` bootstrap SSOT consolidation + rulebook gate hardening + templates payload completeness
- `#295` normalized write-action status mapping coverage
- `#296` gate-event completion for remaining non-zero exits
- `#297` atomic tmp cleanup regression coverage (replace failure path)

---

## Current Status by Priority

### P0 (critical)

- **P0-1 Governance SSOT orchestration:** substantially completed on active paths; governance bootstrap routes through governance use case.
- **P0-2 Mode SSOT:** completed (`OPENCODE_MODE` + force-read-only policy precedence).
- **P0-3 Fail-closed gate signaling:** completed for bootstrap/persistence non-zero and blocked exits in active paths.
- **P0-4 Hard guards:** completed for config-root/pointer path inside repo protections.

### P1 (important)

- **gitless distribution behavior:** completed (`#292`).
- **rulebook/target-phase hardening:** completed for phase `>= 4` gate semantics.
- **atomic/write durability edge coverage:** expanded (`#297` temp-file cleanup on replace failure).
- **additional persistence verification edge tests:** expanded (pointer/session verification failure paths + gate emissions).

### P2 (polish)

- Architecture drift reduced; further cleanup remains available where governance still contain compatibility fallbacks for release portability.

---

## Risk Notes for Reviewers/Testkunden

- The prior document state ("PR #267 failed" as headline status) is no longer representative.
- Governance SSOT flow, release checks, and installer matrix checks are green on the merged migration slices listed above.
- Remaining work is primarily **cleanup/polish**, not foundational unblockers.

---

## Remaining Cleanup Backlog (non-blocking)

1. Continue trimming governance compatibility fallbacks where runtime packaging guarantees are already enforced.
2. Keep expanding edge-case tests around corrupted artifacts/pointers and lock contention under matrix environments.
3. Maintain single-source behavior in governance use cases and avoid reintroducing duplicate orchestration logic.
