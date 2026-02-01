# OpenCode Master Workflow (Canonical)

This document defines the canonical OpenCode workflow.
It is normative and binding.

Single Source of Truth:
- SESSION_STATE_SCHEMA.md

---

## 0. Global Invariants (Binding)

- No gate may be passed without evidence.
- If `Mode = BLOCKED`, then `Next` MUST start with `BLOCKED-`.
- Persistent artifacts MUST NOT be written into the repository.
- Lazy loading is mandatory; rulebooks are loaded only when required.
- No code output is allowed if `ConfidenceLevel < 70`.

---

## 1. SESSION_STATE Bootstrap (Phase 1.1) (Binding)

At session start, the following state MUST be initialized.

```yaml
SESSION_STATE:
  Phase: "1.1-Bootstrap"
  Mode: "NORMAL"
  ConfidenceLevel: 0
  Next: "Phase1.2-ProfileDetection"
  LoadedRulebooks:
    core: ""        # deferred until Phase 4
    profile: ""     # deferred until post-Phase-2
    templates: ""   # deferred until Phase 4 and only if mandated
  ActiveProfile: ""
  ProfileSource: "deferred"
  ProfileEvidence: "deferred-until-phase-2"
  Gates: {}
```

---

## 2. Lazy Loading Rules (Binding)

- Until Phase 2 completes:
  - `ActiveProfile` MAY be empty
  - `LoadedRulebooks.profile` MUST be empty

- Until Phase 4 begins:
  - `LoadedRulebooks.core` MAY be empty
  - `LoadedRulebooks.templates` MAY be empty

- When Phase 4 begins:
  - `LoadedRulebooks.core` MUST be loaded
  - If the active profile mandates templates:
    - `LoadedRulebooks.templates` MUST be loaded
    - Otherwise the workflow MUST transition to:
      - `Mode = BLOCKED`
      - `Next = BLOCKED-TEMPLATES-MISSING`

---

## 3. Phase Overview

### Phase 1.1 – Bootstrap
- Initialize SESSION_STATE only.
- No discovery, no rules loaded.

### Phase 1.2 – Profile Detection
- Repo signals may be inspected.
- No rulebooks loaded yet.

### Phase 1.3 – Core Rules Activation (Deferred)
- Core rules are NOT loaded here.
- This phase only records intent.

### Phase 2 – Repo Discovery
- Full discovery if cache invalid or missing.
- No code generation allowed.

### Phase 3A / 3B – Analysis & Planning
- Still no templates.
- Still no code generation.

### Phase 4 – Code Phase (Implementation Planning / Execution)
- Core rules MUST be loaded.
- Profile rules MUST be loaded.
- Templates MUST be loaded if mandated by profile.

---

## 4. Core Rules Activation (Phase 4) (Binding)

Trigger:
- When `SESSION_STATE.Phase` enters the code-phase set (Phase 4+).

Actions:
- Load `rules.md`
- Merge active profile rules
- Record path in:
  - `SESSION_STATE.LoadedRulebooks.core`
  - `SESSION_STATE.LoadedRulebooks.profile`

---

## 5. Template Activation (Phase 4) (Binding)

Trigger:
- When `SESSION_STATE.Phase` enters the code-phase set (Phase 4+).

Actions:
- If `SESSION_STATE.ActiveProfile` mandates templates:
  - Load templates addon
  - Record path in:
    - `SESSION_STATE.LoadedRulebooks.templates`
- If required templates cannot be loaded:
  - `Mode = BLOCKED`
  - `Next = BLOCKED-TEMPLATES-MISSING`

---

## 6. MIN Output Template (Binding)

All outputs MUST at least include the following fields.

```yaml
SESSION_STATE:
  Phase: "<current-phase>"
  Mode: "NORMAL | DEGRADED | BLOCKED"
  ConfidenceLevel: <0-100>
  Next: "<next-step-or-block>"
  LoadedRulebooks:
    core: "<path-or-empty>"
    profile: "<path-or-empty>"
    templates: "<path-or-empty>"
  ActiveProfile: "<profile-or-empty>"
```

---

## 7. Example: Phase 1 Complete (Illustrative)

```yaml
SESSION_STATE:
  Phase: "1.3-CoreRulesActivation"
  Mode: "NORMAL"
  ConfidenceLevel: 20
  Next: "Phase2-RepoDiscovery"
  LoadedRulebooks:
    core: ""
    profile: ""
    templates: ""
  ActiveProfile: "backend-java"
```

---

## 8. Blocking Semantics (Binding)

- BLOCKED means no further progress.
- Resume MUST NOT reinterpret previous decisions.
- Only missing artifacts may unblock the workflow.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE — master.md
