# Cucumber BDD Addon Rulebook (v1.0)

This document defines the **Cucumber/BDD** addon rules.
It is applied **in addition** to the Core Rulebook (`rules.md`), the Master Prompt (`master.md`), and any active profile.

Priority order on conflict:
`master.md` > `rules.md` (Core) > active profile > this addon.

---

## 0. Core principle (binding)

> Feature files are executable specifications: stable, readable, and deterministic.

The assistant MUST NOT introduce flakey steps, time-based sleeps, or environment-dependent behavior.

---

## 1. Discovery & conventions lock (binding)

When this addon is required, the assistant MUST detect and lock the repo's conventions:
- feature file location (e.g., `src/test/resources/**`)
- step definitions package conventions
- runner configuration (JUnit Platform, Cucumber-JUnit, Spring integration)
- tagging strategy (e.g., `@smoke`, `@regression`, `@wip`)

If conventions are unclear, the assistant MUST mark them as `unknown` and avoid introducing new conventions.

---

## 2. Feature writing rules (binding)

- Each scenario MUST state intent in business language.
- Scenarios SHOULD be focused: one behavior, one outcome.
- Prefer tables/data-driven steps for variants instead of duplicated scenarios.
- Avoid over-specifying UI or technical details unless the repo is explicitly UI-driven.

### 2.1 Step granularity

- Steps MUST be reusable but not overly generic.
- Prefer domain vocabulary (Given/When/Then) over technical vocabulary.

---

## 3. Step definitions rules (binding)

- Steps MUST be deterministic and side-effect controlled.
- No arbitrary sleeps. If asynchronous behavior exists, use deterministic polling utilities (repo-driven) or explicit waiting constructs.
- Steps MUST not depend on execution order; scenario state MUST be isolated.
- Step code MUST follow the repo's standard test style (AssertJ, JUnit assertions, etc.).

### 3.1 Test data management

- Use dedicated builders/factories and stable IDs.
- Avoid using real-time timestamps without injecting a controllable `Clock` or fixed time provider.
- Clean up persistent data between scenarios (transaction rollback, dedicated schema, or explicit cleanup), matching repo practice.

---

## 4. Evidence (binding)

Claims like "BDD tests pass" MUST be backed by build evidence (log excerpt references, CI output references) recorded in the session state.
If evidence is missing, the assistant MUST say: "Not verified – evidence missing."
