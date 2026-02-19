# MD-File Python Policy

## Principle

MD files define **LLM Output Rules** (Schienen), not **System Rules** (Leitplanken).

## What's Allowed (Schienen)

Python snippets in MD are acceptable when they are:

| Type | Purpose | Example |
|------|---------|---------|
| **Output Format/Templates** | Show expected structure | "Test should look like this" |
| **Pseudo-Code/Examples** | Frame LLM output | "Implementation pattern" |
| **Do/Don't Patterns** | Prevent creativity drift | "DON'T: Path.resolve()" |
| **Decision Tables** | Mapping logic | "Phase → Artifact table" |

**Convention:** Python code blocks in MD MUST start with `# EXAMPLE ONLY` or be inside fenced blocks marked as examples.

## What's Forbidden (Leitplanken)

Python in MD becomes dangerous when it:

| Forbidden Pattern | Risk |
|-------------------|------|
| Execution path definition | Scope/Commands silently extended |
| Policy override | "If blocked, just do Y anyway" |
| New side-effects | Writes/Deletes/Network |
| Pipeline interactivity | "Ask the user..." |

## CI Enforcement

The following patterns are **FORBIDDEN** in MD files:

```
run:
execute
subprocess
pip install
curl
wget
import runpy
from pathlib import Path (in execution context)
```

**Exception:** Inside fenced code blocks marked as examples with `# EXAMPLE ONLY`.

## Hard Rule

> MD files may explain HOW to implement something, but never authorize THAT it may be executed.

## LLM Output Rules vs System Rules

| LLM Output Rules (MD) | System Rules (Kernel) |
|-----------------------|----------------------|
| "Output diffs" | Path resolution / Binding |
| "Write tests" | Which files may be written |
| "Use only API X" | Which commands are allowed |
| "Mark unknown as UNKNOWN" | When persistence is allowed |
| "List Preconditions/Evidence" | Prompt budget counting |
| | Reason payload generation |
| | Precedence/Overrides |

## Assumption Budget (Format Rule)

In MD files:

```markdown
When information is missing: write `MISSING: <what's missing>`
When estimating: write `ASSUMPTION: <risk level>`
```

Kernel enforcement:
- In pipeline: if `MISSING:` appears → `BLOCKED` (Reason Code)

## Evidence-First Prompting

In MD files:

```markdown
Quote Evidence-IDs/files before planning.
No "I think" - only "Evidence says".
```

## Deterministic Templates

- Plan-Template with fixed sections: Inputs, Constraints, Steps, Tests, Risks, Evidence Links
- Diff-Template
- No free-form narrative (reduces drift)
