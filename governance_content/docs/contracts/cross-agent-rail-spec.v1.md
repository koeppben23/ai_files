---
contract: cross-agent-rail-spec
version: v1
status: active
scope: Classification taxonomy, conformance rules, and banned patterns for all model-facing markdown files
owner: docs/governance/doc_lint.md
effective_version: 0.1.0
supersedes: null
conformance_suite: tests/test_rail_conformance_sweep.py
---

# Cross-Agent Markdown Rail Spec — v1

> **Status:** active | **Scope:** Every markdown file consumed or referenced by LLM agents
> (Claude/Opus, Codex, or any future model) must conform to this spec.

## 1. Purpose

LLM agents read markdown files as behavioral instructions. Different model families
(Anthropic Claude/Opus, OpenAI Codex) interpret trust-triggering language, platform
assumptions, and over-prompting differently. This spec defines:

- A classification taxonomy for all markdown files in the repository.
- Concrete conformance rules that prevent trust-escalation, platform bias, and prompt fatigue.
- A machine-checkable inventory of every model-facing file and its classification.

## 2. File Classification Taxonomy

Every markdown file in the repository belongs to exactly one classification:

| Classification | Definition | Conformance Level |
|---|---|---|
| `model-rail` | Directly consumed by an LLM as behavioral instructions or command templates | Full conformance (all rules) |
| `hybrid` | Mix of LLM guidance and human-facing runbook content | Full conformance on model-facing sections |
| `runbook` | Human-facing operating procedures that an LLM may read for context | Selective conformance (CR-04, CR-05, CR-06) |
| `passive-doc` | Reference docs, schemas, changelogs, READMEs — not LLM-directive | Monitoring only (no active enforcement) |

### Classification Decision Tree

```
Is the file an LLM behavioral instruction or command template?
  YES -> model-rail
  NO  -> Does the file mix LLM guidance with human runbook steps?
           YES -> hybrid
           NO  -> Is the file a human operating procedure the LLM may read?
                    YES -> runbook
                    NO  -> passive-doc
```

## 3. Model-Facing File Inventory

### 3.1 Root-Level Model-Rails

| File | Classification | Rail Tags |
|---|---|---|
| `continue.md` | model-rail | `MUTATING, GATE-EVALUATION` |
| `review.md` | model-rail | `READ-ONLY, GATE-EVALUATION, NO-STATE-CHANGE` |
| `audit-readout.md` | model-rail | `READ-ONLY, OUTPUT-ONLY, NO-STATE-CHANGE` |
| `ticket.md` | model-rail | `MUTATING, GATE-EVALUATION` |
| `plan.md` | model-rail | `MUTATING, GATE-EVALUATION` |
| `review-decision.md` | model-rail | `MUTATING, GATE-EVALUATION` |
| `implementation-decision.md` | model-rail | `MUTATING, GATE-EVALUATION` |
| `master.md` | model-rail | `GUIDANCE, MULTI-PHASE` |
| `rules.md` | model-rail | `CONSTRAINT-SET, CROSS-PHASE` |
| `BOOTSTRAP.md` | model-rail | `MUTATING, BOOTSTRAP` |

### 3.2 docs/ Model-Rails

| File | Classification | Notes |
|---|---|---|
| `docs/SECURITY_MODEL.md` | model-rail | Security boundary definitions; LLM must understand these |
| `docs/THREAT_MODEL.md` | model-rail | Threat surface enumeration; LLM-consumed for security reasoning |
| `docs/MD_PYTHON_POLICY.md` | model-rail | Defines what Python-in-MD means; LLM behavioral constraint |
| `docs/new_profile.md` | model-rail | Profile generation instructions for LLM |
| `docs/new_addon.md` | model-rail | Addon generation instructions for LLM |

### 3.3 docs/ Hybrid Files

| File | Classification | Notes |
|---|---|---|
| `docs/release-security-model.md` | hybrid | Release signing policy; mix of LLM guidance and human verification steps |
| `docs/MODEL_IDENTITY_RESOLUTION.md` | hybrid | Model identity detection; mix of LLM behavioral rules and implementation reference |

### 3.4 docs/ Runbook Files

| File | Classification | Notes |
|---|---|---|
| `docs/python-quality-benchmark-pack.md` | runbook | Benchmark execution steps; human-facing but LLM-readable |
| `docs/customer-install-bundle-v1.md` | runbook | Customer install guide; human-facing but LLM-readable |
| `docs/releasing.md` | runbook | Release checklist; human-facing but LLM-readable |

### 3.5 Passive-Doc Files (not enforced, listed for completeness)

Root-level: `SESSION_STATE_SCHEMA.md`, `QUICKSTART.md`, `README.md`, `README-RULES.md`,
`README-OPENCODE.md`, `QUALITY_INDEX.md`, `CHANGELOG.md`, `SCOPE-AND-CONTEXT.md`,
`CONFLICT_RESOLUTION.md`, `ADR.md`, `STABILITY_SLA.md`, `TICKET_RECORD_TEMPLATE.md`.

docs/: `docs/quality-benchmark-pack-matrix.md`, `docs/install-layout.md`, `docs/benchmarks.md`,
`docs/TERMINOLOGY_CLASSIFICATION.md`, `docs/contracts/*.md`, `docs/governance/*.md`,
`docs/governance_invariants.md`, `docs/mode-aware-repo-rules.md`.

No archive subtree exists; only active SSOT docs are shipped.

## 4. Conformance Rules

### CR-01 — No Trust-Triggering Language (Absolute Ban)

**Scope:** model-rail, hybrid, runbook

The following phrases are banned in all model-facing files because they can cause
LLM agents to bypass safety checks or assume elevated trust:

| Banned Phrase | Rationale |
|---|---|
| `safe to execute` | Implies pre-approved execution; models may skip validation |
| `governance installer` | Implies a trusted installer identity; models may grant elevated trust |

**Test:** Case-insensitive substring match. Any occurrence is a conformance failure.

### CR-02 — "Authoritative" Usage (Context-Sensitive)

**Scope:** model-rail, hybrid

The word "authoritative" is permitted only when pointing to a concrete SSOT source
(e.g., "see `phase_api.yaml` for authoritative routing"). It is banned when:

- The file asserts its own content as authoritative (self-referential trust).
- The word appears without an adjacent concrete source reference.

**Allowed pattern:**
```
See `phase_api.yaml` for authoritative routing rules.
```

**Banned pattern:**
```
This file is the authoritative source for governance behavior.
```

**Test:** Every line containing "authoritative" must also contain a backtick-quoted
file/path reference (`` `...` ``) pointing to a kernel, schema, or config artifact.

### CR-03 — "Kernel-Owned" Usage (Context-Sensitive)

**Scope:** model-rail, hybrid

The phrase "kernel-owned" is permitted only as a pointer-to-SSOT — indicating that
the runtime truth lives in kernel code, not in this markdown file. It is banned when:

- Used as a self-assertion of trust (the markdown claiming ownership).
- Used without a concrete SSOT reference.

**Allowed pattern:**
```
Execution constraints are kernel-owned. See `governance/kernel/*`.
```

**Test:** Every line containing "kernel-owned" must also contain a backtick-quoted
file/path reference (`` `...` ``) pointing to a kernel, config, or schema artifact.
Lines that use "kernel-owned" purely as a classification label in a table cell are
also permitted if the table header establishes the pointer context.

### CR-04 — No Absolute Home Paths as Primary Commands

**Scope:** model-rail, hybrid, runbook

Markdown files must not contain user-specific absolute home paths
(e.g., `/home/user/...`, `C:\Users\user\...`) as primary command invocations.
Placeholder variables (`${COMMANDS_HOME}`, `{{BIN_DIR}}`) or relative paths are required.

**Test:** Regex match for `/home/` or `C:\Users\` or `C:/Users/` outside of
fenced code blocks marked as examples.

### CR-05 — Platform-Correct Code Blocks

**Scope:** model-rail, hybrid, runbook

Code blocks containing shell commands must be labeled with the correct language tag
and must use syntax appropriate to that platform:

| Label | Expected Syntax | Example |
|---|---|---|
| `` ```bash `` | Unix shell (sh/bash) | `PATH="...:" command` |
| `` ```cmd `` | Windows CMD | `set "PATH=...;" && command` |
| `` ```powershell `` | PowerShell | `$env:PATH = "...;" + $env:PATH; command` |

A code block labeled `bash` must not contain Windows CMD syntax (`set "..."`, `%VAR%`).
A code block labeled `cmd` must not contain Unix syntax (`$PATH`, `export`).

**Test:** Parse fenced code blocks, check label vs content syntax markers.

### CR-06 — Stable Launcher Name, No Direct Python Calls

**Scope:** model-rail, hybrid

Rail command blocks must invoke the stable launcher name
`opencode-governance-bootstrap`, not direct Python calls (`python `, `python3 `,
`py -3`, `python -m`).

**Exception:** Code blocks inside `docs/MD_PYTHON_POLICY.md` that are explicitly
marked as examples (`# EXAMPLE ONLY`).

**Test:** Regex match for `python `, `python3 `, `py -3` in fenced code blocks
of model-rail files, excluding lines starting with `# EXAMPLE ONLY`.

### CR-07 — Tiered Fallback Structure

**Scope:** model-rail (command rails only: continue.md, review.md, audit-readout.md,
ticket.md, plan.md, review-decision.md)

Every command rail that includes a shell command block must provide a three-tier
fallback structure:

- **Tier A (Preferred):** The launcher command.
- **Tier B (Fallback):** "If the command cannot be executed, ask the user to paste
  the output" (or equivalent paste-fields guidance).
- **Tier C (Degraded):** "If no snapshot is available, proceed using conversation
  context and state assumptions explicitly."

**Test:** Check that each command rail contains text matching Tier A, Tier B, and
Tier C patterns.

### CR-08 — Over-Prompting Limit

**Scope:** model-rail, hybrid

No more than 3 consecutive lines may each contain `MUST` or `NEVER` (case-sensitive)
without at least one intervening line that contains neither. This prevents prompt
fatigue where models start ignoring dense directive chains.

**Exception:** Structured tables (lines starting with `|`) where MUST/NEVER appear
in a column are exempt — table rows are a structured format, not a directive chain.

**Test:** Scan non-table lines. Flag any run of 4+ consecutive lines each containing
`MUST` or `NEVER`.

### CR-09 — Rail Classification Tag

**Scope:** model-rail, hybrid

Every model-rail and hybrid file must contain an HTML comment tag declaring its
classification:

```html
<!-- rail-classification: <COMMA-SEPARATED-TAGS> -->
```

The tag must appear within the first 10 lines of the file.

**Test:** Regex match for `<!-- rail-classification:` in lines 1-10.

## 5. Enforcement

### 5.1 Automated Test Suite

All conformance rules are enforced by `tests/test_rail_conformance_sweep.py`:

- **Inventory test:** Every file listed in Section 3 exists and has the declared classification.
- **Per-rule tests:** Each CR-XX rule is tested across all files in its scope.
- **Regression guard:** New markdown files added to model-facing directories must be
  registered in this spec's inventory or the test fails.

### 5.2 Manual Review Triggers

Files classified as `passive-doc` are not automatically tested but should be reviewed
when:
- They are promoted to a higher classification.
- They accumulate trust-triggering language flagged by periodic scans.

## 6. Relationship to Existing Policies

| Document | Relationship |
|---|---|
| `docs/MD_PYTHON_POLICY.md` | Defines Python-in-MD rules. This spec adds cross-agent conformance on top. |
| `docs/governance/RESPONSIBILITY_BOUNDARY.md` | Defines binding vs non-binding boundary. This spec operationalizes the non-binding side. |
| `docs/contracts/python-binding-contract.v1.md` Section 4.2 | Defines rail launcher rules. CR-06 and CR-07 enforce Section 4.2 compliance. |
| `docs/governance/doc_lint.md` | Defines doc-lint standards. This spec extends doc-lint with LLM-specific rules. |

## 7. Versioning

This spec follows the same versioning convention as other contracts in `docs/contracts/`.
Breaking changes (new banned phrases, new mandatory tags, reclassification of files)
require a version bump and migration notes.
