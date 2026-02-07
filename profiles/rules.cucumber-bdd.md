# Cucumber BDD Addon Rulebook (v1.1)

This document defines the **Cucumber/BDD** addon rules.
It is applied **in addition** to the Core Rulebook (`rules.md`), the Master Prompt (`master.md`), and the active profile.

Priority order on conflict:
`master.md` > `rules.md` (Core) > active profile > this addon.

**Addon class (binding):** advisory addon.
**Non-blocking policy:** This addon never hard-blocks progress. If required context, conventions, or tooling are missing/unclear, emit a **status code** with a concrete recovery action and continue with conservative defaults.

---

## 0. Core principle (binding)

> Feature files are **executable specifications**: stable, readable, and deterministic.
> Prefer **business semantics** (domain language) over implementation details.

**Binding rules:**
- Write scenarios so that they are deterministic across runs (no sleeps, no time-of-day dependencies, no shared mutable state).
- Prefer “Given/When/Then” that describe intent and observable outcomes, not internal method names.
- If implementation details are unavoidable, isolate them in step definitions, not in feature text.

---

## 1. Activation and evidence (binding)

**Separation of concerns:**
- **Activation signals** (how to detect Cucumber usage) belong to the addon manifest (`profiles/addons/cucumber.addon.yml`).
- This rulebook defines **behavior**, structure, and quality gates.

When this addon is active, the system MUST record evidence in Session State:

- `SESSION_STATE.AddonsEvidence.cucumber.required: boolean`
- `SESSION_STATE.AddonsEvidence.cucumber.signals: string[]`
- `SESSION_STATE.AddonsEvidence.cucumber.status: "loaded"|"skipped"|"missing-rulebook"|<warn-code>`

Suggested warn-codes for this addon:
- `WARN-CUCUMBER-VERSION-UNKNOWN`
- `WARN-CUCUMBER-RUNNER-UNKNOWN`
- `WARN-CUCUMBER-CONVENTIONS-UNKNOWN`
- `WARN-CUCUMBER-FLAKINESS-RISK`
- `WARN-CUCUMBER-NO-EVIDENCE`

---

## 2. Version and capability inference (binding)

The system SHOULD infer versions/capabilities automatically:

**Primary sources (prefer):**
- `pom.xml` / dependencyManagement (Cucumber BOM) → infer major/minor.
- `build.gradle` equivalents if present.
- Test runtime setup (JUnit Platform vs JUnit 4 runner).

If inference fails:
- Set `SESSION_STATE.AddonsEvidence.cucumber.status = WARN-CUCUMBER-VERSION-UNKNOWN`
- Continue using conservative assumptions:
  - Prefer JUnit Platform patterns (modern default)
  - Avoid framework-specific APIs that are version-sensitive

---

## 3. Phase integration

### Phase 1 — Discovery
When scanning the repo, collect:
- Feature file roots (`src/test/resources/**/*.feature`)
- Runner location(s) if present
- Step-definition package roots
- Evidence of glue configuration (JUnit, Spring context, etc.)

If no feature files are found but dependency suggests Cucumber:
- Mark `WARN-CUCUMBER-NO-EVIDENCE` and proceed (may be unused dependency).

### Phase 2 — Plan (required output)
For any ticket affecting behavior or tests, produce a Cucumber plan section:
- Which features/scenarios to add or update
- Step-definition strategy (reuse vs new)
- Test data strategy (fixtures, seed, cleanup)
- Execution strategy (tags, profiles, parallelization constraints)

### Phase 3 — Implementation (business + steps)
Implement:
- Feature updates
- Step definitions with clean glue boundaries
- Support utilities (test data builders, API clients, DB helpers) in test scope only

### Phase 5 — Verification
- Run relevant tagged subset first (fast feedback)
- Then full Cucumber suite or the repo’s standard test target
- If flaky behavior detected, record `WARN-CUCUMBER-FLAKINESS-RISK` with suspected causes and remediation

---

## 4. Conventions (binding)

### 4.1 Feature file structure
- Keep each feature focused on one capability (avoid “mega features”).
- Prefer 3–10 scenarios per feature, grouped by tags if necessary.
- Use **Background** sparingly (only for truly shared preconditions).
- Prefer **Scenario Outline** when it increases coverage without duplicating logic.

### 4.2 Step phrasing and granularity
- Steps MUST describe **observable behavior**.
- Avoid steps that do multiple actions at once.
- Avoid hard-coded IDs and timestamps; generate or look up deterministically.

**Good:**
- `Given a person exists with status "ACTIVE"`
- `When I request the person details`
- `Then the response contains the person status "ACTIVE"`

**Bad:**
- `Given I call createPersonAndActivateAndPublishKafkaEvent`

### 4.3 Step definitions (glue) design
- Keep step definitions thin:
  - parse input
  - call a small test helper/service
  - assert outputs
- Put heavy logic in reusable helpers under test scope.
- Ensure steps are **idempotent** where possible (safe retries).

### 4.4 Tags and execution
- Use tags to partition:
  - `@smoke`, `@regression`, `@wip`
  - `@slow`, `@integration`
  - environment tags if needed (`@local`, `@ci`)
- Provide a default tag strategy in the plan:
  - Ticket-related scenarios should be runnable as a small subset.

---

## 5. Determinism and anti-flakiness (binding)

### 5.1 Time and async behavior
- Do not use fixed sleeps for async waits.
- Use polling with bounded timeout and clear failure messages.
- Normalize time:
  - Use fixed clocks where available
  - Avoid “now()” in assertions unless explicitly controlled

### 5.2 Test data lifecycle
- Each scenario must own its data:
  - Create minimal needed entities
  - Clean up deterministically (transaction rollback, truncation strategy, or unique namespaces)
- For integration tests, prefer:
  - isolated schemas/namespaces
  - deterministic IDs or well-known keys

If data isolation is unclear:
- emit `WARN-CUCUMBER-CONVENTIONS-UNKNOWN` and choose the safest available approach (unique prefixes, cleanup hooks).

---

## 6. Reporting and failure diagnostics (binding)

On failure, the system SHOULD:
- Include step-level context (inputs sanitized)
- Capture the last request/response (or equivalent) for API tests
- Provide hints for common causes:
  - environment drift
  - missing seed data
  - async timing

If runner/tooling is unknown:
- emit `WARN-CUCUMBER-RUNNER-UNKNOWN` and document how to locate it (search for `@Cucumber` / `CucumberOptions` / `cucumber-junit-platform-engine`).

---


## 7. Quick checks (recommended)

Before finishing a ticket:
- Ensure new/changed scenarios run in isolation.
- Ensure tags are applied consistently.
- Ensure step definitions avoid duplication (prefer reuse).
- Ensure assertions validate domain outcomes, not incidental formatting.

### 7.1 Suggested commands (copy/paste)

Prefer repo-native commands if they exist. If not, propose minimal equivalents:

**Run all Cucumber tests (Maven, JUnit Platform engine)**
```bash
mvn -q test
```

**Run only tagged tests**
```bash
mvn -q test -Dcucumber.filter.tags="@smoke and not @wip"
```

**Run a single feature**
```bash
mvn -q test -Dcucumber.features="src/test/resources/features/person.feature"
```

If your repo uses Gradle, mirror the same intent with `./gradlew test` and the repo’s Cucumber filtering configuration.

### 7.2 Example GitHub Actions job (reference)

If the repo uses GitHub Actions but has no dedicated Cucumber job, propose a minimal job like:

```yaml
name: cucumber
on:
  pull_request:
jobs:
  cucumber:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: "temurin"
          java-version: "21"
      - run: mvn -q test
```

### 7.3 Minimal structural linting for feature files (example)

If you need a light-weight guardrail (non-blocking), propose a tiny script:

```python
# lint_features_minimal.py (example)
import re, sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src/test/resources")
features = list(root.rglob("*.feature"))

if not features:
    print("WARN: no .feature files found under", root)
    sys.exit(0)

bad = 0
for f in features:
    s = f.read_text(encoding="utf-8")
    if "	" in s:
        print(f"ERROR: tab character found: {f}")
        bad += 1
    if re.search(r"\bScenario\b.*\bScenario\b", s):
        print(f"WARN: suspicious duplicate 'Scenario' token: {f}")
    if "Given " not in s and "When " not in s and "Then " not in s:
        print(f"WARN: no Gherkin steps found: {f}")

sys.exit(1 if bad else 0)
```


---

## 8. Minimal recovery playbook (non-blocking)

If you hit unclear repo conventions:
1) Search for existing feature patterns and runner configuration.
2) Reuse existing tags and glue conventions.
3) If still unclear, choose conservative defaults and emit:
   - `WARN-CUCUMBER-CONVENTIONS-UNKNOWN`
   - plus a short note describing what was assumed.



## 9. Troubleshooting (non-blocking)

### Symptom: Tags/filters don’t work in CI
- **Likely cause:** repo uses a different runner (JUnit4 vs JUnit Platform) or a custom property name.
- **Action:** search for existing Cucumber configuration (`cucumber.properties`, `@CucumberOptions`, surefire config) and mirror that. If still unclear, emit `WARN-CUCUMBER-RUNNER-UNKNOWN` and run the full suite as a safe fallback.

### Symptom: Steps are flaky due to async processing (Kafka, DB eventual consistency)
- **Likely cause:** fixed sleeps, non-idempotent setup, or missing correlation IDs.
- **Action:** replace sleeps with bounded polling; make setup idempotent; add correlation IDs and assert eventual outcomes with timeouts. Record `WARN-CUCUMBER-FLAKINESS-RISK` and the mitigation.

### Symptom: Feature language diverges from domain vocabulary
- **Likely cause:** steps encode implementation details.
- **Action:** refactor steps to domain terms and push mechanics into helpers; keep feature files readable for business stakeholders.

### Symptom: No clear test-data cleanup strategy
- **Likely cause:** mixed integration scope or shared DB.
- **Action:** adopt per-scenario namespaces/unique prefixes; clean with hooks; if a transactional rollback is available, prefer it. If still unclear, emit `WARN-CUCUMBER-CONVENTIONS-UNKNOWN` and choose the safest default.

---

## Principal Excellence Contract (Binding)

This rulebook is considered principal-grade only when the contract below is satisfied.

### Gate Review Scorecard (binding)

When this rulebook is active and touches changed scope, the workflow MUST maintain a scorecard entry with weighted criteria, critical flags, and evidence references.

```yaml
SESSION_STATE:
  GateScorecards:
    principal_excellence:
      Score: 0
      MaxScore: 0
      Criteria:
        - id: PRINCIPAL-QUALITY-CLAIMS-EVIDENCED
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-001 | not-verified
        - id: PRINCIPAL-DETERMINISM-AND-TEST-RIGOR
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-002 | not-verified
        - id: PRINCIPAL-ROLLBACK-OR-RECOVERY-READY
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-003 | not-verified
```

### Claim-to-evidence (binding)

Any non-trivial claim (for example: contract-safe, tests green, architecture clean, deterministic) MUST map to an `evidenceRef`.
If evidence is missing, the claim MUST be marked `not-verified`.

### Exit criteria (binding)

- All criteria with `critical: true` MUST be `pass` before declaring principal-grade completion.
- Advisory add-ons MUST remain non-blocking, but MUST emit WARN status code + recovery when critical criteria are not pass.
- Required templates/add-ons MAY block code-phase according to master/core/profile policy when critical criteria cannot be satisfied safely.

### Recovery when evidence is missing (binding)

Emit a warning code plus concrete recovery commands/steps and keep completion status as `not-verified`.
Recommended code: `WARN-PRINCIPAL-EVIDENCE-MISSING`.

---

## Principal Hardening v2.1 - Standard Risk Tiering (Binding)

### RTN-1 Canonical tiers (binding)

All addon/template assessments MUST use this canonical tier syntax:

- `TIER-LOW`: local/internal changes with low blast radius and no external contract or persistence risk.
- `TIER-MEDIUM`: behavior changes with user-facing, API-facing, or multi-module impact.
- `TIER-HIGH`: contract, persistence/migration, messaging/async, security, or rollback-sensitive changes.

If uncertain, choose the higher tier.

### RTN-2 Tier evidence minimums (binding)

- `TIER-LOW`: build/lint (if present) + targeted changed-scope tests.
- `TIER-MEDIUM`: `TIER-LOW` evidence + at least one negative-path assertion for changed behavior.
- `TIER-HIGH`: `TIER-MEDIUM` evidence + one deterministic resilience/rollback-oriented proof (retry/idempotency/recovery/concurrency as applicable).

### RTN-3 Tier-based gate decisions (binding)

- A gate result cannot be `pass` when mandatory tier evidence is missing.
- For advisory addons, missing tier evidence remains non-blocking but MUST emit WARN + recovery and result `partial` or `fail`.
- For required addons/templates, missing `TIER-HIGH` evidence MAY block code-phase per master/core/profile policy.

### RTN-4 Required SESSION_STATE shape (binding)

```yaml
SESSION_STATE:
  RiskTiering:
    ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH
    Rationale: "short evidence-based reason"
    MandatoryEvidence:
      - EV-001
      - EV-002
    MissingEvidence: []
```

### RTN-5 Unresolved tier handling (binding)

If tier cannot be determined from available evidence, set status code `WARN-RISK-TIER-UNRESOLVED`, provide a conservative default (`TIER-HIGH`), and include recovery steps to refine classification.

---

## Principal Hardening v2.1.1 - Scorecard Calibration (Binding)

### CAL-1 Standard criterion weights by tier (binding)

For principal scorecards in addon/template rulebooks, criteria weights MUST use this standard model:

- `TIER-LOW`: each active criterion weight = `2`
- `TIER-MEDIUM`: each active criterion weight = `3`
- `TIER-HIGH`: each active criterion weight = `5`

No custom weights are allowed unless explicitly documented as repo-specific exception with rationale and risk note.

### CAL-2 Critical-flag normalization (binding)

The following criteria classes MUST be marked `critical: true` when applicable:

- contract/integration correctness
- determinism and anti-flakiness
- rollback/recovery safety
- security semantics and authorization behavior

Non-critical criteria MAY exist, but cannot compensate for a failed critical criterion.

### CAL-3 Tier score thresholds (binding)

A principal-grade gate result MAY be `pass` only if all conditions are true:

- all applicable critical criteria are `pass`
- total score ratio meets threshold:
  - `TIER-LOW`: >= `0.80`
  - `TIER-MEDIUM`: >= `0.85`
  - `TIER-HIGH`: >= `0.90`

If threshold is missed, result MUST be `partial` or `fail` with recovery actions.

### CAL-4 Cross-addon comparability (binding)

When multiple addons are active in one ticket, scorecards MUST be directly comparable by using:

- canonical tier labels (`TIER-LOW|MEDIUM|HIGH`)
- standardized weight model from CAL-1
- identical pass thresholds from CAL-3

### CAL-5 Required SESSION_STATE calibration evidence (binding)

```yaml
SESSION_STATE:
  GateScorecards:
    principal_excellence:
      ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH
      Score: 0
      MaxScore: 0
      ScoreRatio: 0.00
      Threshold: 0.80 | 0.85 | 0.90
      CalibrationVersion: v2.1.1
```

### CAL-6 Calibration warning code (binding)

If scorecard data is incomplete or non-comparable, emit `WARN-SCORECARD-CALIBRATION-INCOMPLETE` and block principal-grade declaration (`not-verified`).

