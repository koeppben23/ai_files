# Clean Architecture Violation Analysis

## Violations Found

### 1. CRITICAL: start.md contains executable Python code

**Lines 17 and 48:**
```
!`${PYTHON_COMMAND} -c "import runpy;from pathlib import Path;..."`
```

**Problem:**
- Implementation logic embedded in policy document
- LLM must parse and understand Python code
- Violates: "MD files = descriptions, Kernel = implementation"

**Correct approach:**
- start.md should describe WHAT must happen (the policy)
- Python scripts should implement HOW it happens
- If OpenCode needs to execute something, reference the script path, don't embed the code

### 2. ACCEPTABLE: master.md contains Java example code

**Lines 3566-3616:**
- Inside fenced code blocks (```java)
- Marked as examples/anti-patterns
- Educational/illustrative purpose
- NOT executable

**Verdict:** OK - This is documentation, not implementation

## Proposed Fix for start.md

### Current (WRONG):
```markdown
!`${PYTHON_COMMAND} -c "import runpy;from pathlib import Path;from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver;e=BindingEvidenceResolver().resolve();root=e.commands_home.parent if e.binding_ok else Path.home()/'.config'/'opencode';runpy.run_path(str(root/'commands'/'diagnostics'/'start_binding_evidence.py'),run_name='__main__')" || ...`
```

### Correct (Policy-only):
```markdown
## Auto-Binding Evidence (OpenCode)

When executed as an OpenCode command (`/start`), the following MUST happen:

1. Execute binding evidence resolver: `${COMMANDS_HOME}/diagnostics/start_binding_evidence.py`
2. If binding file exists at `${COMMANDS_HOME}/governance.paths.json`:
   - Load and validate binding evidence
   - Proceed with bootstrap
3. If binding file missing:
   - Return `BLOCKED-MISSING-BINDING-FILE`
   - Provide recovery command: `python3 install.py`

Implementation: The OpenCode host executes the diagnostics helper scripts.
Policy: This document defines the expected behavior and error handling.
```

## Principle

| Layer | Contains | Example |
|-------|----------|---------|
| **Policy (MD)** | WHAT, WHEN, WHY, error handling | "MUST execute binding resolver" |
| **Kernel (Python)** | HOW (implementation) | `start_binding_evidence.py` |
| **Execution (OpenCode)** | Script invocation | Calls Python scripts |

## Files to Fix

| File | Violation | Action |
|------|-----------|--------|
| `start.md` | Lines 17, 48 | Replace Python code with policy description |
| Other MD files | None | Already compliant |

## Success Criteria

- [ ] No executable Python code in MD files
- [ ] All implementation in Python scripts
- [ ] MD files only describe policy/behavior
- [ ] Scripts are referenced by path, not embedded
