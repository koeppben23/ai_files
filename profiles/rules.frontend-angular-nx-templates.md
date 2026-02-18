# Frontend Angular + Nx Templates (ADDON)

## Intent (binding)

Provide deterministic, high-signal templates for Angular business code and tests so LLM output is consistent and reviewable.

## Scope (binding)

Angular+Nx template structures for components, facades, API boundaries, and deterministic frontend test scaffolding.

## Activation (binding)

Addon class: `required`.

This addon MUST be loaded at code-phase (Phase 4+) when `SESSION_STATE.ActiveProfile = "frontend-angular-nx"`.
- Missing-addon handling MUST follow canonical required-addon policy from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`.
- This rulebook MUST NOT redefine blocking semantics.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This required addon refines template defaults and MUST NOT override `master.md`, `rules.md`, or `rules.frontend-angular-nx.md` constraints.

Rule (binding): templates are default structures. If a template conflicts with locked repo conventions, apply minimal adaptation and record the deviation.

## Phase integration (binding)

- Phase 2: capture template-relevant repo conventions (signals/store/testing style, Nx boundaries).
- Phase 4: use these templates for changed scope and record deviations explicitly.
- Phase 5.3: verify template-derived behavior via repo-native lint/test targets or mark `not-verified`.

## Evidence contract (binding)

- Record loaded template path in `SESSION_STATE.LoadedRulebooks.templates`.
- Record major deviations under `SESSION_STATE.DecisionDrivers` with evidence refs.

## Tooling (recommended)

- Prefer repo-native Nx targets (for example `npx nx affected -t lint,test,build`).
- If target names differ, document the resolved equivalent commands in BuildEvidence.

## Correctness by construction (binding)

Inputs required:
- feature/module path(s)
- selected state pattern (signals/ngrx/component-store) from repo conventions
- API/contract mapping context for changed scope

Outputs guaranteed:
- container/presentational/facade/API-boundary scaffolds aligned to repo conventions
- deterministic frontend test scaffold for changed behavior
- explicit boundary-safe mapping points

Evidence expectation:
- after template application, run repo-native lint/test targets (or mark `not-verified` with recovery command)
- template-derived claims MUST reference BuildEvidence item ids.
evidence_kinds_required:
  - "unit-test"
  - "e2e"
  - "lint"

Golden examples:
- container orchestrates only and delegates state transitions via facade/store abstraction.
- API boundary maps DTOs explicitly before UI consumption.

Anti-example:
- introducing ad-hoc second state architecture or leaking transport DTOs into UI contracts.

## Examples (GOOD/BAD)

GOOD:
- Templates are adapted minimally to the repo state pattern (signals/ngrx/component-store) with deviation evidence.

BAD:
- Introducing a second ad-hoc state architecture while applying templates to changed scope.

## Troubleshooting

- Signal/store mismatch: adapt template state layer to repo pattern (signals/ngrx/component-store) and document deviation.
- Boundary violations: split feature/data-access/ui libs to satisfy Nx constraints before wiring component templates.

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

## Shared Principal Governance Contracts (Binding)

This rulebook uses shared advisory governance contracts:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior:

- When this rulebook is active in execution/review phases, load these as advisory governance contracts.
- Record when loaded:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`
- If one of these shared rulebooks is unavailable, emit WARN + recovery, mark affected claims as
  `not-verified`, and continue conservatively.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
