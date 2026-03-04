# Governance Continue

<!-- GOVERNANCE KERNEL BRIDGE — sole exception to rails-only constraint in this file -->
## Resume Session State

Preferred: load the current governance session state using the following read-only command, if local command execution is allowed in your environment:

```bash
{{PYTHON_COMMAND}} "{{SESSION_READER_PATH}}"
```

Use the YAML output as your governance context for the response below.

**If the command cannot be executed** (e.g., sandboxed environment, model policy, or tool error), ask the user to paste the output of the command above — or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

**If no snapshot is available**, proceed using only the context visible in the current conversation and state your assumptions explicitly before continuing.

---

Continue uses canonical `SESSION_STATE` from `SESSION_STATE_SCHEMA.md`.

Rails-only scope:
- output structure and quality checklist only
- informational references to kernel-managed decisions
- no local execution policy or state-mutation directives

Output checklist:
- reflect current `SESSION_STATE.phase` and `SESSION_STATE.next`
- include delta-only progress for the active step
- if kernel reports a blocker or warning, render it with concise evidence and one recovery action
- keep profile context stable in the response narrative; do not redefine profile selection semantics here

Kernel references (informational):
- discovery/re-discovery behavior is kernel-managed
- blocked/degraded routing is kernel-managed
- fast-path scope changes are kernel-managed
- active profile resolution is kernel-managed

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
