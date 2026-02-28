# Governance Doc-Lint Standard

This checklist prevents `master.md` and `rules.md` from drifting into SSOT or duplicating kernel/schema contracts.

## Hard Rules

1) **Authority boundary is explicit**
   - Each file states: schema/validator/kernel are authoritative.
   - Markdown is not SSOT and does not define runtime truth.

2) **No field lists or token lists**
   - No enumerations of field names, response keys, tokens, transition metadata, or status vocabularies.
   - Exception only for a *clearly marked, non-binding excerpt* with a direct authoritative reference.

3) **No runtime invariants in Markdown**
   - No detailed IFF/validation logic, step-by-step execution rules, or technical preconditions.
   - Instead: “See schema/validator/kernel” with a concrete reference.

4) **No shadow SSOT via “reference-only” mirrors**
   - If a schema/kernel change would require updating Markdown, it is too close to SSOT.
   - Replace with a short intent sentence plus authoritative reference.

5) **Strict role separation**
   - `master.md`: governance posture, orchestration principles, operator guidance, authority boundary.
   - `rules.md`: constraint policy, evidence semantics, allowed interpretation limits.
   - No duplicated runtime explanations across both files.

6) **Every behavioral claim has a reference**
   - Any statement about behavior, format, validation, or state points to a schema/validator/kernel/contract file.

## Quick Self-Check

- Would a schema/kernel change require editing Markdown? If yes, cut more.
- Are there bracketed output blocks or strict/compat matrices? If yes, remove or replace with references.
- Are there long “minimum requirements” lists that mirror schemas? If yes, replace with intent + reference.

***

End of doc-lint standard.
