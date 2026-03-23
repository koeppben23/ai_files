# AI Engineering Governance Platform

AI-assisted engineering with explicit governance, deterministic workflow control, and exportable audit evidence.

---

## Positioning

The AI Engineering Governance Platform is designed for organizations that need more than AI-generated code. It provides a governed execution model for planning, implementation, review, approval, and evidence capture across controlled software delivery workflows.

It turns AI-assisted software delivery from an unstructured chat interaction into a deterministic, policy-bound workflow with explicit phases, gates, canonical state, audit artifacts, and fail-closed enforcement.

---

## Why it exists

Most AI coding tools optimize for speed and code generation. That is useful, but insufficient for organizations that must answer:

- Who requested this change?
- What exactly was approved?
- Which rules and profiles were active?
- What evidence exists for the implementation?
- Which controls blocked or allowed the next step?
- Can we export the full record for audit, risk, or legal review?

The platform solves that gap. It is designed for organizations that want AI-assisted engineering productivity **with the operating discipline of a controlled software process**.

---

## Deployment Profiles

The platform operates in three modes, selected at bootstrap:

### Solo

For individual engineers who want structured execution, explicit checkpoints, and a complete work record without enterprise overhead.

### Team

For engineering teams that need repeatable planning, review visibility, and shared execution discipline across contributors.

### Regulated

For organizations that require controlled approvals, auditable decisions, retained evidence, redaction support, and fail-closed governance behavior.

---

## Built for Controlled Engineering Environments

The platform is designed for organizations that cannot rely on opaque assistant behavior alone. It fits environments where software delivery must be governed, reviewable, and operationally accountable — including:

- regulated and quality-sensitive software organizations
- enterprise engineering teams
- financial institutions
- industrial and infrastructure software providers
- organizations with audit, approval, and change-control requirements

---

## Core Capabilities

The platform does not just document AI-assisted work. It gates, reviews, exports, and enforces it:

- governed AI-assisted engineering workflows
- deterministic execution through explicit phases and gates
- reviewable plans, decisions, and receipts
- exportable audit evidence for internal control environments
- fail-closed behavior when state or evidence is invalid

---

## How it works

### 1. Bootstrap and binding

Every governed session starts from an explicit bootstrap path:

```
opencode-governance-bootstrap init --profile <solo|team|regulated> --repo-root <repo-root>
```

Bootstrap establishes the workspace context, binding data, profile selection, and repo-scoped persistence prerequisites. If required evidence or path binding is missing, the system blocks rather than guessing.

### 2. Governed command surface

The platform exposes a constrained command surface mapped to governance rails:

- `/continue`
- `/ticket`
- `/plan`
- `/review`
- `/review-decision <approve|changes_requested|reject>`
- `/implement`
- `/audit-readout`

These are governance entrypoints tied to state, transition logic, gate expectations, and evidence production.

### 3. Explicit phase workflow

The platform uses a multi-phase workflow that moves work through governed stages rather than allowing arbitrary jumps. The runtime includes explicit gate and transition logic so that the next authorized action is computed rather than inferred.

### 4. Canonical state and deterministic next action

The governance runtime is built around a canonical state model. This gives the platform a stable execution contract. In controlled environments, "the system should probably continue" is not good enough. The platform is designed so the runtime can say either:

- **this is the next allowed action**
- or **execution is blocked, with a concrete reason**

### 5. Review and approval gating

Important progress points require review semantics. Planning output must be reviewed before implementation is authorized. Evidence presentation is required before final approval. `approve`, `changes_requested`, and `reject` outcomes explicitly route the workflow.

### 6. Two-plane architecture

The system separates:

- **runtime plane** — active session state, derived artifacts, and locks
- **audit plane** — immutable run archives, manifests, checksums, and finalized records

This separation is a core enterprise property. Active working state and formal audit records are not treated as the same thing. That matters for reviewability, export, retention, and tamper detection.

---

## Governance Model

### Security design principle

**Repository content is data, not authority.**

Repository files can inform or describe, but they do not silently authorize behavior. Policy authority comes from the governance runtime and its configured profile/policy inputs.

### Fail-closed behavior

Critical boundaries are designed to validate and fail closed:

- missing evidence should block progress
- invalid state should block progress
- inconsistent or tampered audit artifacts should block verification
- unsupported or ambiguous resolution paths should not be best-effort accepted

### Reason-coded blocking

When the platform cannot safely proceed, it emits explicit blocked outcomes rather than vague failure states:

- bootstrap not satisfied
- missing binding file
- repo identity resolution failure
- rulebook or profile resolution problems
- integrity mismatch
- persistence path violations
- permission or operating-mode requirements

That gives operators and compliance stakeholders a concrete vocabulary for why the system stopped.

---

## Why regulated and enterprise teams buy it

### For engineering leadership

Engineering leaders get a way to standardize how AI work is initiated, planned, approved, implemented, and evidenced. It reduces the operational risk of chat-driven coding by introducing explicit workflow phases, policy-bound transitions, deterministic next actions, and review gates before implementation proceeds.

### For platform, security, and compliance teams

Non-feature teams get a concrete control plane instead of vague assurances. They can inspect active policy and profile selection, run manifests and provenance records, checksums and verification outcomes, classification and redaction policy, retention behavior, and reason-coded blocked decisions.

### For regulated customers

The platform helps answer typical control expectations around traceability, separation of runtime and audit records, integrity verification, explicit approval points, retention and deletion control, field-level classification and redaction, exportability for review or proceedings, and fail-closed handling when evidence or policy requirements are not satisfied.

---

## What it is not

- not a replacement for source control, CI system, or ticket system
- not a legal or compliance certification product by itself
- not a generic chatbot front-end
- not a promise that all code is automatically correct

The value is the **governed operating model around AI-assisted engineering**, not a claim of autonomous software delivery without oversight.

---

## Platform components

### Desktop environment

The interactive AI execution interface used by operators and engineers.

### Governance runtime

The deterministic execution core that handles state, transitions, policy-bound decisions, persistence, and fail-closed validation.

### Policy, profiles, and control content

Profiles, rules, contracts, control mappings, and operational documentation that shape how the runtime behaves in different environments.

### Bootstrap CLI

The installation, binding, repo-identity, and session-init path that makes the governed workflow reproducible and operable.

---

## Messaging pillars

### 1. Governed, not just assisted

AI can help produce software, but governance determines whether software work is acceptable, reviewable, and authorized.

### 2. Proof, not just output

The platform records why a change happened, how it was reviewed, what evidence exists, and whether the resulting run was finalized and verified.

### 3. Deterministic, not heuristic

The runtime uses canonical state, explicit transitions, and reason-coded blocked outcomes instead of relying on informal chat flow.

### 4. Enterprise-ready by design

The platform is built for separation of concerns, evidence retention, exportability, and fail-closed operation — the qualities regulated buyers actually ask about.

---

## Positioning statement

For regulated and quality-sensitive software teams, the AI Engineering Governance Platform turns AI-assisted development into a deterministic, reviewable, and auditable workflow.

Unlike general-purpose AI coding tools that primarily optimize generation speed, it adds explicit gates, canonical state, policy-bound transitions, immutable audit records, and fail-closed enforcement so organizations can use AI in software delivery under real operational control.

---

## Short description

**An AI engineering governance platform for organizations that need proof, control, and auditability — not just generated code.**

---

## Non-negotiable product truths

- The governance runtime is the authority for execution.
- Canonical state and explicit transitions are central to the system.
- Critical validation paths fail closed.
- Audit evidence is a first-class product capability, not an afterthought.
- Regulated and enterprise customers are a primary design target, not a late add-on.

---

## In one sentence

The AI Engineering Governance Platform makes AI-assisted software delivery usable in regulated and control-heavy environments by adding deterministic workflow control, explicit approvals, and audit-ready proof.

---

*Version: 1.2*  
*Last Updated: 2026-03-23*
