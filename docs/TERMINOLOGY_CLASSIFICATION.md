# Terminology Classification for Governance Documents

## Three Categories

### 1. KERNEL-ENFORCED (Leitplanken)

**Definition**: The kernel validates and enforces this. If LLM ignores/misunderstands,
kernel STILL prevents unsafe behavior.

**Examples**:
- Phase-Gates (P5, P5.3, P5.4, P5.6, P6)
- Evidence validation
- Reason code schema
- Degenerate path validation
- Workspace-ready gate
- Scope/command/permission boundaries

**Litmus Test**: "If LLM ignores this, can kernel still prevent harm?" → YES

### 2. POLICY (Definition)

**Definition**: Defines WHAT, WHEN, WHY. Kernel implements the HOW.

**Examples**:
- Phase transition rules
- Conflict resolution policy
- Precedence order
- Default decision policies
- Evidence requirements per phase

**Litmus Test**: "Is this a rule/invariant that kernel must enforce?" → YES

### 3. PRESENTATION ADVISORY (Schienen)

**Definition**: Output format conventions, templates, examples.
LLM should follow, but kernel doesn't depend on it.

**Examples**:
- [NEXT-ACTION] format
- [SNAPSHOT] format
- [SESSION_STATE] formatting
- Output mode (STRICT/COMPAT)
- Banner format

**Litmus Test**: "If LLM ignores this, does kernel still work correctly?" → YES

## Migration Plan

| Current Label | New Label | Category |
|---------------|-----------|----------|
| `(Binding)` for gates/evidence | `(Kernel-Enforced)` | Leitplanken |
| `(Binding)` for policy rules | `(Policy)` | Definition |
| `(Binding)` for output formats | `(Presentation Advisory)` | Schienen |

## Critical Principle

**MD files MUST NEVER replace Kernel-Enforced logic.**

If an MD instruction starts behaving like a Leitplanke, it MUST move to kernel.
