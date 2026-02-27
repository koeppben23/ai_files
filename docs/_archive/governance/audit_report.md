# Governance Docs Audit Report

Status: draft (baseline)
Scope: master.md, rules.md
Goal: identify structure, redundancies, conflicts, and must-preserve anchors before refactor.

## Structure Map (High Level)

master.md
- Phase 0 bootstrap activation + path bindings
- Identity + tool preflight contracts
- Phase routing, gates, and operator contracts
- Output contracts and blocker envelopes
- Priority order and conflict resolution

rules.md
- Core-Lite governance scope
- Evidence and scope lock
- Profile selection rules
- Gate policies (schema/contract, business rules, tests)
- Output format contracts and safety constraints

## Redundancy / Drift Risks

- Phase descriptions repeated across master.md and rules.md with slightly different terminology.
- Gate semantics and output contracts appear in multiple sections (risk of wording drift).
- Presentation advisory rules are mixed with policy rules; semantic priority is unclear.

## Must-Preserve List

### Must-Preserve Tokens (tests/lint depend on these)
- "## 1. PRIORITY ORDER"
- "4. Activated templates/addon rulebooks (manifest-driven)"
- "5. Ticket specification"
- "Stability sync note (binding): governance release/readiness decisions MUST also satisfy `STABILITY_SLA.md`."
- "Profile selection is kernel-enforced"
- "governance/assets/reasons/blocked_reason_catalog.yaml"
- "Canonical conflict precedence is defined once in Section 1 (`PRIORITY ORDER`) and MUST NOT be redefined here."
- "They MUST NOT be interpreted as a second precedence model; canonical conflict precedence remains Section 1 (`PRIORITY ORDER`)."
- "DO NOT read rulebooks from the repo working tree"
- "BLOCKED-MISSING-RULEBOOK:<file>"
- "Bootstrap Process"
- "governance.paths.json"
- "### 7.3.10 Bootstrap Preflight Output Contract (Kernel-Enforced)"
- "Preflight probes MUST be fresh (`ttl=0`)"
- "Preflight MUST include `observed_at`"
- "Preflight MUST report at most 5 checks."
- "`available: <comma-separated commands or none>`"
- "`missing: <comma-separated commands or none>`"
- "`impact: <one concise sentence>`"
- "`next: <single concrete next step>`"
- "`restart_required_if_path_edited`"
- "`no_restart_if_binary_in_existing_path`"
- "### 7.3.13 Smart Retry + Restart Guidance (Kernel-Enforced)"
- "RulebookLoadEvidence"
- "BLOCKED-RULEBOOK-EVIDENCE-MISSING"
- "RULEBOOK-PRECEDENCE-POLICY"
- "ADDON-CLASS-BEHAVIOR-POLICY"
- "Master Prompt > Core Rulebook > Active Profile Rulebook > Activated Addon/Template Rulebooks > Ticket > Repo docs"
- "Release/readiness decisions MUST satisfy `STABILITY_SLA.md` invariants; conflicts are resolved fail-closed."
- "provide a ranked shortlist of plausible profiles with brief evidence per candidate"
- "request explicit selection using a single targeted numbered prompt"
- "0=abort/none"

### Must-Preserve Section IDs
- "## 1. PRIORITY ORDER"
- "### 7.3.10 Bootstrap Preflight Output Contract (Kernel-Enforced)"

### Must-Preserve Test Anchors
- Stability SLA references in master.md + rules.md
- Precedence list uniqueness in master.md
- Rulebook precedence anchors in rules.md
- Preflight output contract tokens in master.md/rules.md

## Breaking-Change Check (Baseline)

Breaking changes include:
- Gate name changes (P5/P5.3/P5.4/P5.6/P6)
- Phase name changes or renumbering
- Removing test/lint anchor tokens
- Renaming schema keys used in tests
- Changing default BLOCKED behavior

## Progress Notes

- Welle A started: terminology freeze + schema references added.
- Redundant output-shape text in rules.md consolidated; anchors preserved.
