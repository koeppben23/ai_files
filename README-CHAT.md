# Governance & Prompt System — Chat-Only Usage Guide

This document explains how to use the **Governance & Prompt System**
in **pure chat environments** (ChatGPT, Claude, etc.),
**without OpenCode or repo indexing**.

---

## IMPORTANT — Non-Normative Document

This README is **descriptive, not normative**.

If anything in this file conflicts with:
- `master.md`
- `rules.md`

then **this README is wrong**.

👉 Always follow the rulebooks.

This document explains **usage**, not **behavioral rules**.

---

## 1. What “Chat-Only Usage” Means

Chat-only usage means:

- no repository indexing
- no implicit file access
- no automatic artifact discovery
- no guaranteed persistence beyond what you provide

The AI can only reason over:
- text you paste
- files you upload
- artifacts you explicitly describe

Anything not provided is **out of scope**.

---

## 2. When Chat-Only Usage Is Appropriate

Chat-only usage is well-suited for:

- planning and design discussions
- ticket analysis
- architecture reviews
- governance and quality reviews
- conceptual test strategies
- partial or isolated code changes

It is **not ideal** for:
- large refactorings across many files
- implicit business-rule discovery
- audit-grade verification of existing systems

---

## 3. Minimal Required Context

At the start of a chat-only session, you should provide:

1. `master.md`
2. `SCOPE-AND-CONTEXT.md`

These define:
- workflow phases
- gates
- scope lock
- session-state handling
- confidence and blocking behavior

Without these, the system cannot operate deterministically.

---

## 4. Optional Context (As Needed)

Depending on the task, you may also provide:

- `rules.md`  
  (only required once quality or test gates become relevant)

- Ticket descriptions

- Selected code files (copied or uploaded)

- API specs (OpenAPI, schemas, DTOs)

- Database schemas or migrations

> ⚠️ In chat mode, **nothing is implicitly available**.
> If it matters, you must provide it.

---

## 5. Workflow in Chat-Only Mode

### High-level flow

1. Governance is initialized via `master.md`
2. Phases progress implicitly
3. Gates block when required
4. Outputs are constrained by evidence and scope

### Key differences vs. repo-aware mode

| Aspect | Chat-Only | Repo-Aware |
|------|----------|-----------|
| Artifact discovery | Manual | Automatic |
| Business rules | Explicit only | Extractable from code |
| Evidence strength | Limited | Strong |
| Confidence ceiling | Often lower | Higher |

---

## 6. Scope & Evidence Rules (Critical)

In chat-only mode:

- The AI MUST NOT infer domain truth
- The AI MUST NOT invent missing files
- The AI MUST explicitly say:
  > “Not in the provided scope.”

If business logic is not present in artifacts,
it **cannot be treated as authoritative**.

---

## 7. Business Rules in Chat-Only Mode

Business rules can only come from:

- explicit ticket descriptions
- pasted code
- uploaded documents
- user confirmation

There is **no automatic discovery**.

As a result:
- Phase 1.5 (Business Rules Discovery) is usually **manual**
- Phase 5.4 (Business Rules Compliance) may be limited
- confidence may be capped

This is expected and correct behavior.

---

## 8. Test Quality Expectations

Test quality rules still apply.

However:
- test execution cannot be verified unless logs are provided
- BuildEvidence is usually `not-provided`
- conclusions remain **theoretical**

The AI may still:
- design high-quality test plans
- review test logic
- detect test anti-patterns in pasted code

---

## 9. Session State in Chat-Only Mode

If the workflow reaches Phase 2 or later,
the assistant will maintain a `[SESSION_STATE]` block.

You are responsible for:
- keeping it in the chat
- pasting it back when resuming
- ensuring continuity

There is no implicit session memory.

---

## 10. Common Pitfalls (Avoid These)

- “You already know the repo” → ❌ not in chat
- “Same as last project” → ❌ out of scope
- “Assume standard behavior” → ❌ forbidden
- Skipping gates “because it’s obvious” → ❌ blocked

---

## 11. Best Practices

- Provide fewer files, but complete ones
- Prefer explicit contracts over descriptions
- Accept blocking as a quality feature
- Use chat mode for **thinking**, not bulk editing

If full repo context is required, consider switching to
**OpenCode repo-aware mode**.

---

## 12. Guiding Principle

> In chat-only mode:
> precision beats speed,
> explicit beats implicit,
> blocking beats guessing.

This is not a limitation —
it is how correctness is preserved.

---

Copyright © 2026 Benjamin Fuchs.  
All rights reserved.

Unauthorized use, copying, modification, or distribution
is prohibited without explicit permission.

Note: These restrictions do not apply to the copyright holder
(Benjamin Fuchs), who may use this work without limitation.

_End of file_
