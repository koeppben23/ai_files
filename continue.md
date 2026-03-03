# Governance Continue

<!-- GOVERNANCE KERNEL BRIDGE — sole exception to rails-only constraint in this file -->
## MANDATORY FIRST STEP

Before responding, execute the following command to load the current governance session state:

```bash
{{PYTHON_COMMAND}} "{{SESSION_READER_PATH}}"
```

Use the YAML output as your governance context for the response below.
If the command fails, report the error verbatim and stop.

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
