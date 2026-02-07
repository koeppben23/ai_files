# Frontend Angular + Nx Templates (ADDON)

Purpose (binding): provide deterministic, high-signal templates for Angular business code and tests so LLM output is consistent and reviewable.

Addon class (binding): required addon.

Activation (binding): MUST be loaded at code-phase (Phase 4+) when `SESSION_STATE.ActiveProfile = "frontend-angular-nx"`.
- If missing at code-phase: `Mode = BLOCKED`, `Next = BLOCKED-MISSING-TEMPLATES`.

Precedence (binding): `master.md` > `rules.md` > this addon > `rules.frontend-angular-nx.md`.

Rule (binding): templates are default structures. If a template conflicts with locked repo conventions, apply minimal adaptation and record the deviation.

---

## T1. Container Component Pattern

```ts
@Component({
  selector: 'app-{feature}-page',
  templateUrl: './{feature}-page.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  standalone: true,
  imports: [{Feature}ViewComponent],
})
export class {Feature}PageComponent {
  private readonly facade = inject({Feature}Facade);

  readonly vm = this.facade.vm;

  onRefresh(): void {
    this.facade.refresh();
  }
}
```

Binding rules:
- Container orchestrates only; no transport parsing/business rules in component.
- Use typed view model (`vm`) and explicit event handlers.

---

## T2. Presentational Component Pattern

```ts
@Component({
  selector: 'app-{feature}-view',
  templateUrl: './{feature}-view.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  standalone: true,
})
export class {Feature}ViewComponent {
  @Input({ required: true }) vm!: {Feature}ViewModel;
  @Output() refresh = new EventEmitter<void>();
}
```

Binding rules:
- No HttpClient/state orchestration in presentational components.
- Inputs/outputs are typed and minimal.

---

## T3. Facade Pattern

```ts
@Injectable({ providedIn: 'root' })
export class {Feature}Facade {
  private readonly api = inject({Feature}Api);
  private readonly state = signal<{Feature}State>({ loading: false, items: [] });

  readonly vm = computed<{Feature}ViewModel>(() => ({
    loading: this.state().loading,
    items: this.state().items,
  }));

  refresh(): void {
    this.state.update((s) => ({ ...s, loading: true }));
    this.api.fetchAll().subscribe({
      next: (items) => this.state.set({ loading: false, items }),
      error: () => this.state.update((s) => ({ ...s, loading: false })),
    });
  }
}
```

Binding rules:
- Keep boundary mapping in facade/data-access layer.
- Error paths must be explicit.
- If repo uses ngrx/component-store instead of signals, mirror repo pattern.

---

## T4. API Boundary Pattern

```ts
@Injectable({ providedIn: 'root' })
export class {Feature}Api {
  private readonly http = inject(HttpClient);

  fetchAll(): Observable<ReadonlyArray<{Feature}Item>> {
    return this.http.get<{Feature}Response>('/api/{features}').pipe(
      map((dto) => dto.items.map(map{Feature}Item))
    );
  }
}
```

Binding rules:
- DTO-to-view/domain mapping is explicit.
- Do not leak backend DTOs into UI contracts.

---

## T5. Unit Test Template (Facade)

```ts
describe('{Feature}Facade', () => {
  let facade: {Feature}Facade;
  let api: jasmine.SpyObj<{Feature}Api>;

  beforeEach(() => {
    api = jasmine.createSpyObj<{Feature}Api>('{Feature}Api', ['fetchAll']);
    TestBed.configureTestingModule({
      providers: [
        {Feature}Facade,
        { provide: {Feature}Api, useValue: api },
      ],
    });
    facade = TestBed.inject({Feature}Facade);
  });

  it('refresh should expose loaded items', () => {
    api.fetchAll.and.returnValue(of([{ id: '1', name: 'A' }]));

    facade.refresh();

    expect(facade.vm().items).toEqual([{ id: '1', name: 'A' }]);
    expect(facade.vm().loading).toBeFalse();
  });
});
```

Binding rules:
- Assert behavior/state outcomes, not internal implementation details.
- Keep tests deterministic (no timers/sleeps unless controlled).

---

## T6. E2E Template (Cypress)

```ts
describe('{feature} flow', () => {
  it('loads list and shows item', () => {
    cy.intercept('GET', '/api/{features}', { fixture: '{feature}-list.json' });
    cy.visit('/{features}');
    cy.get('[data-testid="{feature}-row"]').should('have.length.at.least', 1);
  });
});
```

Binding rules:
- Use stable selectors and deterministic fixtures.
- Avoid fixed waits; use retryable assertions.

---

END OF ADDON

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

