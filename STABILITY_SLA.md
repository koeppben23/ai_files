# Stability-SLA: AI Governance System (Go/No-Go)

This SLA defines when the governance system is considered stable and when changes to
`master.md`, `rules.md`, `profiles/*`, `profiles/addons/*`, and template rulebooks may be released.

## 1) Single Canonical Precedence

- Exactly one canonical precedence definition exists:
  `master > core rules > active profile > activated addons/templates > ticket`.
- `governance-lint` MUST fail on duplicates or divergent precedence variants.

## 2) Deterministic Activation

- For identical `RepoFacts + Capabilities + Manifests + Ruleset`, `activation_plan` MUST be bit-identical.
- Profile/addon ambiguity MUST produce `BLOCKED-*` (no guessing, no best-effort activation).

## 3) Fail-Closed for Required

- Missing/invalid required addons/templates/rulebooks MUST block codegen.
- Recovery output MUST include at most 3 concrete steps and `next_command`.

## 4) Surface Ownership and Conflict Safety

- `owns_surfaces` / `touches_surfaces` MUST validate against a canonical surface registry.
- Same-surface ownership conflicts or incompatible constraints on the same surface MUST resolve deterministically:
  - either via defined conflict resolution,
  - or `BLOCKED-ADDON-CONFLICT:<surface>` with proof/trace.

## 5) Evidence-Gated Claims (No Claim Without Evidence)

- Claims like "tests green", "static clean", "no drift" require compatible evidence:
  - evidence kind,
  - verified status,
  - scope compatibility,
  - artifacts present.
- Without sufficient evidence, output MUST be `not-verified` and state missing evidence explicitly.

## 6) Verified Requires Pinning

- `verified` for build/test/analysis requires tool/runtime version evidence or `env_fingerprint`.
- Without pinning evidence, results remain `not-verified` (planning may continue).

## 7) SESSION_STATE Versioning and Isolation

- `session_state_version` and `ruleset_hash` are mandatory.
- Outdated/mismatched state MUST trigger `BLOCKED-STATE-OUTDATED` with concrete recovery.
- Evidence MUST be ticket/run isolated (no cross-ticket verified leakage).

## 8) Activation Delta Guard

- State includes hashes for manifests, RepoFacts/capabilities, and ruleset.
- If hash changes are not consistently recomputed into activation/evidence, workflow MUST block (no stale plan).

## 9) Proof-Carrying Explain Contracts (Read-only)

- `/why-blocked` and `/explain-activation` are read-only.
- Output MUST include:
  - `reason_code`
  - `surface`
  - `signals_used`
  - `decision_trace`
  - `recovery_steps`
  - `next_command`
- Explain outputs MUST NOT contain implicit verification claims.

## 10) Regression Gates (CI Required)

- Governance changes MUST pass required checks:
  - `governance-lint`
  - `pytest -m governance`
  - governance e2e flow coverage (`pytest -m e2e_governance`)
  - template quality gate (`inputs/outputs/evidence expectation + golden/anti + claim safety`)
- Release/merge MUST be blocked if any required check fails.

## Operational Pass/Fail

- PASS: all 10 criteria are satisfied and enforced by required CI checks.
- FAIL: any non-determinism, missing required component, unproven claim, or unguarded conflict remains possible.
