# Kernel-Owned Passages Audit (Draft)

Default rule:
- If a passage is kernel-owned and Direct SSOT, preferred MD role is **Reference-only**.

Priority definitions:
- P0 = hard SSOT collision / kernel semantics duplicated normatively
- P1 = drift-prone / rewrite likely
- P2 = editorial improvement
- P3 = keep as-is

| File / Section | Line Range | Passage Type | Exact Passage (quoted) | Kernel-Owned? | Direct SSOT or Policy Documented | SSOT Source(s) | Recommended MD Role | Must Preserve Token? | Breaking Risk | Conflict Risk | Priority | Rewrite Suggestion (short) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| master.md / Intro | 19 | Route | "SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation." | Y | Direct SSOT | `phase_api.yaml` | Reference-only | Y | Low | Low | P3 | Keep; already reference-only. |
| master.md / Blocking semantics | 87-90 | Blocked Reason | "`SESSION_STATE.Mode` set to `BLOCKED`" + "Blocked reasons and recovery are kernel-enforced." | Y | Direct SSOT | `blocked_reason_catalog.yaml` + kernel state invariants | Reference-only | Y | Medium | Medium | P2 | Keep text but label as kernel-owned reference. |
| master.md / Preflight | 249-253 | TTL / Timing | "Preflight executes as Phase `0` / `1.1`" + "Tool probe TTL is zero (`ttl=0`)" + "observed_at" | Y | Direct SSOT | `bootstrap_preflight_readonly.py` | Reference-only | Y | Medium | High | P1 | Replace with short reference: "Kernel enforces preflight TTL/observed_at; see …" |
| master.md / Preflight | 275-283 | Evidence Rule | "`SESSION_STATE.Preflight.BuildToolchain` MUST contain" | Y | Direct SSOT | `bootstrap_preflight_readonly.py`, session schema | Reference-only | Y | Medium | Medium | P1 | Convert to schema reference (`governance.preflight.v1`). |
| master.md / Routing notes | 363-388 | Route | "Routing: Kernel-enforced from `${COMMANDS_HOME}/phase_api.yaml`." | Y | Direct SSOT | `phase_api.yaml` | Reference-only | N | Low | Low | P3 | Keep, already reference. |
| master.md / Gate skip | 870-871 | Gate | "Phase 5 is not skippable…" / "Phase 5.4 is not skippable…" | Y | Direct SSOT | `phase_api.yaml`, gate evaluator | Reference-only | N | Low | High | P1 | Shorten to reference-only, avoid duplicating logic. |
| master.md / Gates canonical | 820 | Gate | "The canonical machine state MUST be `SESSION_STATE.Gates.*` values…" | Y | Direct SSOT | session schema + invariants | Reference-only | N | Low | Medium | P2 | Convert to schema pointer; keep anchor if any. |
| master.md / Blocked catalog | 1038-1053 | Blocked Reason | "Blocked reason catalog (kernel-enforced): …" | Y | Direct SSOT | `blocked_reason_catalog.yaml` | Reference-only | N | Medium | High | P1 | Replace with link + "see catalog"; avoid full list duplication. |
| rules.md / Scope Lock | 93-99 | Invariant | "### 2.2 Scope Lock (Kernel-Enforced)" | Y | Direct SSOT | kernel scope guards | Reference-only | N | Low | Medium | P2 | Keep but mark as reference-only. |
| rules.md / Path Hygiene | 156-165 | Invariant | "### 3.3 Path Expression Hygiene (Kernel-Enforced)" | Y | Direct SSOT | kernel persistence guard | Reference-only | N | Medium | Medium | P2 | Keep; add schema reference if available. |
| rules.md / Rulebook precedence | 227-236 | Route | "### 4.6 Canonical Rulebook Precedence (Kernel-Enforced)" | Y | Direct SSOT | kernel rulebook loading | Reference-only | Y | High | High | P0 | Keep anchor tokens, convert to reference-only wording. |
| rules.md / Evidence ladder | 370-389 | Evidence Rule | "### 6.0 Evidence Ladder (Kernel-Enforced)" | Y | Direct SSOT | evidence policy in kernel | Reference-only | N | Medium | High | P1 | Replace with short reference + schema pointer. |
| rules.md / Gate artifacts | 432-446 | Evidence Rule | "### 6.4 Gate Artifact Completeness (Kernel-Enforced)" | Y | Direct SSOT | gate invariants | Reference-only | N | Medium | High | P1 | Replace with schema/gate reference. |
| rules.md / Blocker envelope | 709-723 | Output Contract | "### 7.3.2 Standard Blocker Output Envelope (Kernel-Enforced)" | Y | Direct SSOT | kernel output contract | Reference-only | N | Medium | Medium | P1 | Keep anchor; reduce to reference + schema ID. |
| rules.md / Preflight contract | 876-889 | Output Contract | "### 7.3.10 Bootstrap Preflight Output Contract (Kernel-Enforced)" | Y | Direct SSOT | preflight contract | Reference-only | Y | High | High | P0 | Keep anchors; make reference-only + schema ID. |
| rules.md / Status contract | 904-918 | Invariant | "### 7.3.11 Deterministic Status + NextAction Contract (Kernel-Enforced)" | Y | Direct SSOT | kernel status policy | Reference-only | N | Medium | High | P1 | Convert to reference-only with schema ID. |
| rules.md / Transition invariants | 936-948 | Invariant | "### 7.3.12 Session Transition Invariants (Kernel-Enforced)" | Y | Direct SSOT | kernel transition contract | Reference-only | N | Medium | Medium | P1 | Replace detailed rules with reference. |
| rules.md / Retry guidance | 955-967 | TTL / Timing | "### 7.3.13 Smart Retry + Restart Guidance (Kernel-Enforced)" | Y | Direct SSOT | kernel restart hints | Reference-only | N | Medium | Medium | P1 | Reduce to reference-only. |
| rules.md / Warn/Blocked | 971-985 | Invariant | "### 7.3.14 Phase Progress + Warn/Blocked Separation (Kernel-Enforced)" | Y | Direct SSOT | kernel status policy | Reference-only | N | Medium | Medium | P1 | Reduce to reference-only. |
