# Architecture Migration Status

**Stand:** 2026-02-23
**Branch:** docs/architecture-migration-status
**PRs:** #266 (merged), #267 (closed - failing)

---

## Executive Summary

### Completed (PR #266)

✅ **Phase 1: New Architecture Modules Created**
- session_state/schema.py, serde.py, transitions.py
- governance/paths/canonical.py, layout.py, binding.py
- diagnostics/io/atomic_write.py, fs_verify.py
- diagnostics/errors/global_handler.py
- bootstrap/repo_identity.py, persistence.py, backfill_client.py
- routing/phase_router.py, gates.py, phase_rank.py

✅ **Phase Router Partial Migration**
- `governance/application/use_cases/phase_router.py` imports from `routing/gates.py`
- Target-phase rulebook gate implemented
- Backward compatible

### Failed/Closed (PR #267)

❌ **bootstrap_session_state.py Migration**
- Attempted to import new modules
- **Failed**: Import errors in test environment
- **Reason**: Modules not available in test runner context

❌ **persist_workspace_artifacts.py Migration**
- Not attempted (1456 lines, high risk)

❌ **P0 Fixes**
- `--skip-artifact-backfill` blocking: Not implemented
- `PersistenceCommitted` guard: Not implemented

---

## What's Missing

### P0 Fixes (Critical)

**bootstrap_session_state.py**
```
❌ Block --skip-artifact-backfill in live runs
❌ Never set PersistenceCommitted=True if WorkspaceArtifactsCommitted!=True
❌ Fail-closed: Return non-zero if artifacts not committed
```

**Current State**: 922 lines, uses old architecture

### P1 Fixes (Important)

**phase_router.py**
```
✅ Target-phase rulebook gate (implemented in PR #266)
```

### Migration Tasks (Phase 3-5)

**Phase 3: Artifact Writers**
```
❌ artifacts/writers/repo_cache.py
❌ artifacts/writers/repo_map_digest.py
❌ artifacts/writers/workspace_memory.py
❌ artifacts/writers/decision_pack.py
❌ artifacts/normalization.py
❌ artifacts/backfill.py
```

**Phase 4: Bootstrap Service**
```
❌ Refactor bootstrap_session_state.py to thin CLI (~250 LOC)
❌ Integrate BootstrapPersistenceService
❌ Use new diagnostics/io modules
```

**Phase 5: Error Logging**
```
❌ Refactor error_logs.py to use global handler
❌ Ensure all gates use emit_gate_failure()
```

---

## Definition of Done - Gap Analysis

| Criterion | Target | Current Status | Gap |
|-----------|--------|----------------|-----|
| CLI files ≤ 250 LOC | Yes | No (922 LOC) | ❌ 672 LOC to remove |
| Gates in 1 module | Yes | Partial | ⚠️ Dual existence |
| WriteAction everywhere | Yes | No (only new modules) | ❌ All writes need refactoring |
| BootstrapResult as SSOT | Yes | Not integrated | ❌ Needs full rewrite |

---

## Test Failures

**Test:** `test_t7_router_blocks_without_rulebooks`
**Error:** With core rulebook loaded, router still blocks Phase 4
**Root Cause:** New routing logic may have bugs in edge cases

**Solution:** Need to:
1. Add comprehensive unit tests for new routing logic
2. Debug target-phase rulebook gate
3. Ensure backward compatibility

---

## Recommended Path Forward

### Immediate (Next 1-2 PRs)

1. **Fix test failures** in routing logic
2. **Implement P0 fixes** in bootstrap_session_state.py:
   - Block `--skip-artifact-backfill`
   - Guard `PersistenceCommitted` with artifacts check
3. **Add integration tests** for new modules

### Medium-term (3-5 PRs)

4. **Create artifact writers** (Phase 3)
   - Start with repo_cache.py (simplest)
   - Add one writer per PR

5. **Refactor bootstrap** (Phase 4)
   - Extract logic to service
   - Use new modules

### Long-term (6+ PRs)

6. **Error logging consolidation** (Phase 5)
7. **Remove old code paths**
8. **Documentation and examples**

---

## Complexity Metrics

**Original Plan:**
- 5 large files to refactor (900-1456 LOC each)
- ~30-40 hours estimated

**Current Progress:**
- New architecture: ~15 hours ✅
- Migration: ~5 hours (failed)
- **Total: ~20 hours**

**Remaining:**
- Migration: 25-35 hours
- Testing: 10-15 hours
- **Total: 35-50 hours**

---

## Key Insights

### What Worked

✅ **Creating new modules** - Clean, testable, SSOT
✅ **Target-phase rulebook gate** - Logical improvement
✅ **Backward compatible imports** - Safe migration path

### What Failed

❌ **Big-bang migration** - Too many changes at once
❌ **Test environment compatibility** - New modules not available in test runner
❌ **Breaking changes** - Changed imports broke existing code

### Lessons Learned

1. **Incremental migration** is essential
2. **Test environment** must be updated first
3. **One file per PR** reduces risk
4. **Keep old code paths** until new ones are proven

---

## Conclusion

**Architecture foundation is solid** (PR #266), but **migration is incomplete**.

**Recommendation:**
- Merge documentation PR
- Create focused PRs for each migration step
- Prioritize P0 fixes
- Test incrementally

**Estimated time to completion:** 35-50 hours across 6-10 PRs
