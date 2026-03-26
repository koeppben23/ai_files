# AI Engineering Governance Platform

AI-assisted engineering with explicit governance, deterministic workflow control, and exportable audit evidence.

---

## Executive Summary

The **AI Engineering Governance Platform** transforms AI-assisted software delivery from unstructured chat interactions into **deterministic, policy-bound workflows** with explicit phases, gates, canonical state, audit artifacts, and fail-closed enforcement.

Built for **regulated industries, enterprise engineering teams, and organizations with audit or compliance requirements**, the platform provides the operating discipline that AI-driven development needs to meet controlled software delivery standards.

**Key Value Proposition:** Organizations can now use AI for software delivery while maintaining proof, control, and auditability — not just generated code.

---

## The Problem

Most AI coding tools optimize for speed and code generation. That's useful, but insufficient for organizations that must answer:

- **Who** requested this change?
- **What** exactly was approved?
- **Which** rules and profiles were active?
- **What** evidence exists for the implementation?
- **Which** controls blocked or allowed the next step?
- **Can** we export the full record for audit, risk, or legal review?

Existing AI tools leave these questions unanswered. The platform closes this gap.

---

## Key Capabilities

### Deterministic Workflow Control

- **18 explicit phases** from bootstrap through post-flight
- **Phase gates** that require evidence before progression
- **Computed next actions** — the system tells you exactly what is allowed, not guessed
- **Fail-closed enforcement** — execution blocks when evidence or state is invalid

### Governance & Compliance

- **Role-based profiles:** Solo (individual), Team (collaborative), Regulated (strictest controls)
- **Business rules extraction** — the platform discovers and tracks governance-relevant code patterns
- **Code surface analysis** — understanding what surfaces exist in your codebase
- **Reason-coded blocking** — every blocker has a specific error code and remediation

### Audit & Evidence

- **Two-plane architecture** — separates active runtime state from immutable audit records
- **Exportable audit bundles** — full provenance, checksums, decisions, and evidence
- **Decision receipts** — complete trail of who approved what and when
- **Tamper detection** — checksums and integrity verification

### Enterprise Integration

- **CI/CD ready** — team profile supports automated approval flows
- **Profile system** — language-specific rules (Python, Java, Angular, etc.)
- **Add-on architecture** — extensible governance rules and quality gates
- **Self-hosted** — no external dependencies, full data sovereignty

---

## How It Works

### 1. Bootstrap

Every governed session starts with explicit binding:
```
opencode-governance-bootstrap init --profile <solo|team|regulated>
```

The system establishes workspace context, profile selection, and persistence prerequisites. If required evidence is missing, execution **blocks** rather than guessing.

### 2. Governed Command Surface

Eight governance rails map to workflow phases:

| Command | Purpose |
|---------|---------|
| `/continue` | Materialize and display current state |
| `/ticket` | Submit task/ticket for Phase 4 intake |
| `/plan` | Persist architecture/planning evidence |
| `/review` | Submit work for human review |
| `/review-decision` | Record approve/changes_requested/reject |
| `/implement` | Execute implementation with evidence |
| `/implementation-decision` | Record final implementation decision |
| `/audit-readout` | Export complete audit evidence |

Each command is tied to state transitions, gate expectations, and evidence production.

### 3. Phase Workflow

The platform moves work through **explicit phases** rather than allowing arbitrary jumps:

- **Phase 1:** Bootstrap & Activation — workspace setup, rulebook loading
- **Phase 2:** Repository Discovery — identity, cache, map digest
- **Phase 3:** API & Code Surface Analysis — what exists in the codebase
- **Phase 4:** Ticket Intake — task definition and scope
- **Phase 5:** Architecture Review — planning, review, quality gates
- **Phase 6:** Implementation & Post-Flight — execution, verification, audit

**Every phase transition requires evidence.** The system computes whether progression is allowed.

### 4. Canonical State Model

The governance runtime maintains **canonical state** — a stable execution contract that answers:

- Current phase and next allowed action
- Active profile and rulebooks
- Evidence chain and decision history
- Gate status and blockers (if any)

In controlled environments, "the system should probably continue" is not acceptable. The platform says either:

- **This is the next allowed action**, or
- **Execution is blocked, with a concrete reason**

### 5. Two-Plane Architecture

The system explicitly separates:

- **Runtime Plane** — active session state, derived artifacts, working locks
- **Audit Plane** — immutable run archives, manifests, checksums, finalized records

This separation is critical for enterprise buyers. Active working state and formal audit records are not the same thing. This enables reviewability, export, retention, and tamper detection.

---

## Deployment Profiles

### Solo

For individual engineers who want structured execution, explicit checkpoints, and complete work records without enterprise overhead.

### Team

For engineering teams needing repeatable planning, review visibility, and shared execution discipline. Includes **CI/CD auto-approve** at the Evidence Presentation Gate for automated pipelines.

### Regulated

For organizations requiring controlled approvals, auditable decisions, retained evidence, redaction support, and **fail-closed governance behavior**. Maps to `agents_strict` runtime mode to prevent silent downgrade in CI environments.

---

## Platform Components

| Component | Description |
|-----------|-------------|
| **Desktop Environment** | Interactive AI execution interface for operators |
| **Governance Runtime** | Deterministic execution core — state, transitions, policy decisions |
| **Policy & Profiles** | Language-specific rules (Python, Java, Angular, etc.) and control content |
| **Bootstrap CLI** | Installation, binding, repo-identity, and session initialization |

---

## Why Enterprise Teams Choose Us

### For Engineering Leadership

Standardize how AI work is initiated, planned, approved, implemented, and evidenced. Reduce the operational risk of chat-driven coding through explicit workflow phases, policy-bound transitions, and review gates.

### For Platform & Compliance Teams

Get a concrete control plane instead of vague assurances. Inspect active policy and profile selection, run manifests and provenance records, checksums and verification outcomes, classification policy, retention behavior, and reason-coded blocked decisions.

### For Regulated Industries

Answer control expectations around **traceability**, **separation of runtime/audit records**, **integrity verification**, **explicit approval points**, **retention and deletion control**, **field-level classification**, **exportability**, and **fail-closed handling**.

---

## What We Are Not

- **Not** a replacement for source control, CI system, or ticket system
- **Not** a legal or compliance certification product by itself
- **Not** a generic chatbot front-end
- **Not** a promise that all AI-generated code is automatically correct

The value is the **governed operating model around AI-assisted engineering**, not autonomous software delivery without oversight.

---

## Competitive Differentiation

| Capability | Traditional AI Tools | Our Platform |
|------------|---------------------|--------------|
| Workflow phases | None | 18 explicit phases |
| Evidence requirements | Implicit | Explicit, gate-based |
| Audit trail | Chat history only | Complete, exportable |
| Next action computation | Heuristic | Deterministic |
| Blocking behavior | Silent failure | Reason-coded blocking |
| Enterprise profiles | None | Solo/Team/Regulated |
| Two-plane architecture | No | Runtime + Audit separation |

---

## Security Principles

### Repository Content Is Data, Not Authority

Repository files can inform or describe governance rules, but they do not silently authorize behavior. **Policy authority comes from the governance runtime**, not from repo content.

### Fail-Closed by Default

Critical boundaries validate and fail closed:
- Missing evidence → blocks progress
- Invalid state → blocks progress  
- Tampered audit artifacts → blocks verification
- Ambiguous resolution → fails rather than best-effort

### Reason-Coded Blocking

When the platform cannot proceed, it emits explicit blocked outcomes with specific codes:
- `BLOCKED_BOOTSTRAP_INCOMPLETE`
- `BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE`
- `BLOCKED_MISSING_BINDING_FILE`
- `BLOCKED_REPO_IDENTITY_UNRESOLVED`
- `BLOCKED_P5_PLAN_EMPTY`
- And 40+ more reason codes

This gives operators and compliance stakeholders a concrete vocabulary for system behavior.

---

## Product Facts

- **Current Version:** 1.1.0-RC.2
- **Supported Languages:** Python, Java, JavaScript/TypeScript (Angular), and growing
- **Profile System:** 15+ language-specific governance profiles
- **Phase Count:** 18 explicit workflow phases
- **Command Surface:** 8 governance rails
- **Add-on Architecture:** Extensible rules and quality gates
- **Self-Hosted:** No external dependencies, full data sovereignty

---

## In One Sentence

The AI Engineering Governance Platform makes AI-assisted software delivery usable in regulated and control-heavy environments by adding deterministic workflow control, explicit approvals, and audit-ready proof.

---

## Contact

For inquiries about deployment, enterprise features, or regulatory compliance:

[Your contact information here]

---

*Version: 1.1.0-RC.2*  
*Last Updated: 2026-03-26*
