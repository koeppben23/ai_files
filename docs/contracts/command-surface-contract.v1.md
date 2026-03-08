---
contract: command-surface
version: v1
status: active
scope: Canonical operator command surfaces and legacy alias policy
owner: governance policy
---

# Command Surface Contract — v1

## Canonical operator surfaces

- Session continuation surface: `/continue`
- Audit read-only surface: `/audit-readout`

These are the only canonical active surfaces for continuation and audit operations.

## Legacy alias policy

- `/resume` is deprecated and not an active command surface.
- `/audit` is deprecated and not an active command surface.
- Active rails, phase text, schema examples, reason catalogs, and remediation hints MUST NOT recommend deprecated aliases as normal actions.

## Compatibility boundary

- Historical compatibility docs may exist only as explicit legacy aliases.
- Legacy aliases must be marked deprecated and must point to canonical surfaces.
- Legacy alias documents must not define independent active workflow behavior.
