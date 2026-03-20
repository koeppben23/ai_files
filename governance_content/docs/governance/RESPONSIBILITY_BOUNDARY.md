# Governance Responsibility Boundary

## Binding vs Non-Binding

This repository uses a strict separation of concerns.

Terminology (explicit):
- **bindend** = runtime-authoritative (kernel/config/schema contracts)
- **nicht-bindend** = AI guidance/presentation rails only

- Kernel + `phase_api.yaml` are binding runtime control.
- Schemas + contracts are binding data and response contracts.
- Markdown rails are non-binding AI guidance.

## Ownership Matrix

| Surface | Role | Binding | Notes |
|---|---|---|---|
| `governance_runtime/kernel/*` | Runtime routing, transitions, gate decisions | Yes | Source of execution truth |
| `${COMMANDS_HOME}/phase_api.yaml` | Phase graph and transition config | Yes | Kernel-consumed control plane |
| `governance_runtime/assets/schemas/*` | Data contract validation | Yes | Session/document shape |
| `governance_runtime/assets/catalogs/*` | Deterministic catalogs/templates | Yes | Contracted fixtures/templates |
| `master.md` / `rules.md` / `start.md` | AI behavior rails | No | Guidance only; no runtime authority |

## Practical Rule

If markdown guidance conflicts with kernel/config/schema behavior, kernel/config/schema wins.

Markdown rails should describe quality and communication behavior, not runtime branching logic.
