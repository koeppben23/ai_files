# MD File Violation Analysis

## Summary

**113 MUST statements** found in core MD files. Many are violations of the Schienen principle.

## Critical Violations

### 1. EXECUTION FLOW CONTROL (Forbidden)

**master.md:1433**
```
`continue.md` MUST execute ONLY the step referenced by `SESSION_STATE.Next`.
```
**Problem:** MD is defining execution flow, not just output format.
**Fix:** This should be kernel-enforced, not MD-defined.

**master.md:2915**
```
Before presenting the plan, the LLM MUST execute exactly **3 self-critique rounds**
```
**Problem:** MD is defining execution procedure with specific iteration count.
**Fix:** Should be kernel-enforced or described as output quality rule.

**master.md:3738-3752**
```
When build tools are available, the LLM MUST execute them autonomously...
Execute `SESSION_STATE.BuildToolchain.CompileCmd`.
Maximum 3 compile-fix iterations.
```
**Problem:** MD is defining:
- WHEN to execute
- WHAT to execute
- HOW MANY iterations
- Detailed error handling flow

**Fix:** All of this should be kernel-enforced.

### 2. POLICY/AUTHORITY LANGUAGE (Forbidden)

**master.md:270**
```
The following are FORBIDDEN:
```
**Problem:** MD is declaring what's forbidden (System Rule), not describing output format.

**master.md:841**
```
Code generation is ONLY permitted if...
```
**Problem:** MD is defining permission policy (System Rule).

**master.md:3407-3408**
```
If `test-quality-fail` → Code generation is FORBIDDEN
If `test-quality-pass-with-exceptions` → Code generation is ALLOWED
```
**Problem:** MD is defining permission policy (System Rule).

### 3. MODE POLICY (Forbidden - Kernel Authority)

**master.md:1286-1292**
```
ARCHITECT: Decision-first output; no full code diffs.
IMPLEMENT: Full implementation output is allowed only after explicit operator trigger.
```
**Problem:** MD is defining mode policy (System Rule).
**Fix:** Mode policy should be kernel-enforced.

## Acceptable Patterns (Schienen)

### Output Format Rules (OK)
- "Output MUST include [NEXT-ACTION]"
- "Responses SHOULD include phase progress"
- "SESSION_STATE output MUST be formatted as fenced YAML"

### Quality Rules for Output (OK)
- "No assumptions"
- "If unclear → mark as MISSING/EVIDENCE_REQUIRED"
- "Always add tests"

### Non-executable Examples (OK)
- Code blocks with `# EXAMPLE ONLY`
- Do/Don't patterns
- Templates

## Classification

| Category | Count | Status |
|----------|-------|--------|
| Output Format Rules | ~30 | ✅ OK |
| Quality Rules for Output | ~20 | ✅ OK |
| Execution Flow Control | ~15 | ❌ VIOLATION |
| Policy/Authority Language | ~25 | ❌ VIOLATION |
| Mode/Permission Policy | ~10 | ❌ VIOLATION |
| Constraint Hints | ~13 | ⚠️ Borderline |

## Recommended Actions

### P0 - Critical Violations (Must Fix)

1. **master.md:3738-3762 (Build Verification Loop)**
   - Move to kernel: `governance/application/use_cases/build_verification.py`
   - MD should only say: "When build tools available, the workflow will run verification"
   - Kernel enforces: WHEN, HOW, iterations, error handling

2. **master.md:1433 (continue.md execution)**
   - Move to kernel: `governance/engine/orchestrator.py`
   - MD should only say: "Continue workflow from SESSION_STATE.Next"

3. **master.md:2915 (self-critique rounds)**
   - Move to kernel or describe as output quality rule
   - MD: "Plans SHOULD include self-critique notes"

### P1 - Policy Language Violations

4. **Replace "FORBIDDEN/ALLOWED/PERMITTED" with Output Rules**

   Current (VIOLATION):
   ```
   Code generation is FORBIDDEN if test-quality-fail
   ```

   Correct (Schienen):
   ```
   When test-quality-fail: Do NOT output code diffs. Output fix recommendations instead.
   ```

5. **Remove Mode Policy from MD**

   Current (VIOLATION):
   ```
   ARCHITECT: no full code diffs
   ```

   Correct:
   ```
   In ARCHITECT mode: Output decisions and architecture, not code diffs.
   ```

## Ignorability Test Results

| MD Statement | If LLM Ignores | Kernel Still Safe? | Verdict |
|--------------|----------------|-------------------|---------|
| "Output [NEXT-ACTION]" | Missing footer | Yes | ✅ OK |
| "Execute build loop" | Doesn't execute | NO - could skip verification | ❌ VIOLATION |
| "Code gen FORBIDDEN" | Outputs code | NO - could bypass gates | ❌ VIOLATION |
| "No Path.resolve()" | Uses Path.resolve() | Yes (kernel checks) | ✅ OK |

## Widening Test Results

| MD Statement | Widens Side-Effects? | Verdict |
|--------------|---------------------|---------|
| "Execute compile" | YES - adds execution | ❌ VIOLATION |
| "Maximum 3 iterations" | NO - limits | ⚠️ Borderline |
| "ask user for X" | NO - just output | ✅ OK |

## Hard Fixes Required

1. Remove all "execute" commands from MD
2. Replace "FORBIDDEN/ALLOWED" with output format rules
3. Move Build Verification Loop to kernel
4. Move continue.md execution logic to kernel
5. Convert mode policy to output descriptions

## Estimated Work

| Task | Complexity |
|------|------------|
| Move Build Verification to kernel | Medium |
| Fix policy language | Low |
| Update tests | Medium |
| Total | ~2-3 hours |
