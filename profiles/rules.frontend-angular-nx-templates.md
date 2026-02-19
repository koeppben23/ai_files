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

- SHOULD use repo-native Nx targets (for example `npx nx affected -t lint,test,build`).
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
- MUST keep boundary mapping in facade/data-access layer.
- Error paths MUST be explicit.
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

## T7. Reactive Form Template

**Template for Typed Reactive Form Component:**

```ts
@Component({
  selector: 'app-{feature}-form',
  templateUrl: './{feature}-form.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  standalone: true,
  imports: [ReactiveFormsModule],
})
export class {Feature}FormComponent {
  private readonly facade = inject({Feature}Facade);

  readonly form = new FormGroup({
    name: new FormControl<string>('', {
      nonNullable: true,
      validators: [Validators.required, Validators.maxLength(100)],
    }),
    email: new FormControl<string>('', {
      nonNullable: true,
      validators: [Validators.required, Validators.email],
    }),
  });

  @Output() submitted = new EventEmitter<{Feature}FormValue>();

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitted.emit(this.form.getRawValue());
  }

  onCancel(): void {
    this.form.reset();
  }
}
```

**Template for Form HTML:**

```html
<form [formGroup]="form" (ngSubmit)="onSubmit()">
  <div>
    <label for="name">Name</label>
    <input id="name" formControlName="name" />
    @if (form.controls.name.hasError('required') && form.controls.name.touched) {
      <span class="error">Name is required</span>
    }
  </div>

  <div>
    <label for="email">Email</label>
    <input id="email" formControlName="email" type="email" />
    @if (form.controls.email.hasError('email') && form.controls.email.touched) {
      <span class="error">Invalid email format</span>
    }
  </div>

  <button type="submit" [disabled]="form.invalid">Save</button>
  <button type="button" (click)="onCancel()">Cancel</button>
</form>
```

**Binding rules:**
- Forms MUST use typed `FormGroup` / `FormControl<T>` (not untyped `FormGroup`).
- Forms MUST use `nonNullable: true` where applicable.
- Validation MUST be declared in the component class (not only in template).
- Form submission MUST check `form.invalid` before emitting.
- Forms SHOULD emit a typed value object (`FormValue`), not the raw form group.

---

## T7.1 Form Unit Test Template

```ts
describe('{Feature}FormComponent', () => {
  let component: {Feature}FormComponent;
  let fixture: ComponentFixture<{Feature}FormComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [{Feature}FormComponent],
    });
    fixture = TestBed.createComponent({Feature}FormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should be invalid when name is empty', () => {
    component.form.controls.name.setValue('');
    expect(component.form.valid).toBeFalse();
  });

  it('should be valid when all fields are filled correctly', () => {
    component.form.controls.name.setValue('Test Name');
    component.form.controls.email.setValue('test@example.com');
    expect(component.form.valid).toBeTrue();
  });

  it('should emit submitted event on valid submit', () => {
    const spy = spyOn(component.submitted, 'emit');
    component.form.controls.name.setValue('Test Name');
    component.form.controls.email.setValue('test@example.com');

    component.onSubmit();

    expect(spy).toHaveBeenCalledWith({
      name: 'Test Name',
      email: 'test@example.com',
    });
  });

  it('should NOT emit submitted event on invalid submit', () => {
    const spy = spyOn(component.submitted, 'emit');
    component.form.controls.name.setValue('');

    component.onSubmit();

    expect(spy).not.toHaveBeenCalled();
  });

  it('should mark all fields as touched on invalid submit', () => {
    component.form.controls.name.setValue('');

    component.onSubmit();

    expect(component.form.controls.name.touched).toBeTrue();
  });
});
```

**Binding rules:**
- Form tests MUST test validation states (valid, invalid, specific validators).
- Form tests MUST test submit behavior (emit on valid, block on invalid).
- Form tests MUST NOT test internal template rendering logic unless testing user interaction flows.

---

## T8. Route Guard Template

**Template for Functional Route Guard (canActivate):**

```ts
export const authGuard: CanActivateFn = (
  route: ActivatedRouteSnapshot,
  state: RouterStateSnapshot,
): boolean | UrlTree => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    return true;
  }

  return router.createUrlTree(['/login'], {
    queryParams: { returnUrl: state.url },
  });
};
```

**Template for Role-Based Guard:**

```ts
export const roleGuard = (requiredRole: string): CanActivateFn => {
  return (route, state) => {
    const authService = inject(AuthService);
    const router = inject(Router);

    if (!authService.isAuthenticated()) {
      return router.createUrlTree(['/login'], {
        queryParams: { returnUrl: state.url },
      });
    }

    if (!authService.hasRole(requiredRole)) {
      return router.createUrlTree(['/forbidden']);
    }

    return true;
  };
};
```

**Template for Route Configuration with Guards:**

```ts
export const {FEATURE}_ROUTES: Routes = [
  {
    path: '',
    component: {Feature}PageComponent,
    canActivate: [authGuard],
  },
  {
    path: 'admin',
    component: {Feature}AdminComponent,
    canActivate: [roleGuard('ADMIN')],
  },
  {
    path: ':id',
    component: {Feature}DetailComponent,
    canActivate: [authGuard],
  },
];
```

**Binding rules:**
- Guards MUST use functional guard pattern (`CanActivateFn`), not class-based guards (deprecated).
- Guards MUST return `boolean | UrlTree` (not `Observable<boolean>` unless async auth is required).
- Guards MUST redirect to login with `returnUrl` for unauthenticated users.
- Role guards SHOULD be parameterized factory functions.

---

## T8.1 Route Guard Test Template

```ts
describe('authGuard', () => {
  let authService: jasmine.SpyObj<AuthService>;
  let router: jasmine.SpyObj<Router>;

  beforeEach(() => {
    authService = jasmine.createSpyObj('AuthService', ['isAuthenticated']);
    router = jasmine.createSpyObj('Router', ['createUrlTree']);

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: authService },
        { provide: Router, useValue: router },
      ],
    });
  });

  it('should allow access when authenticated', () => {
    authService.isAuthenticated.and.returnValue(true);

    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, { url: '/dashboard' } as RouterStateSnapshot),
    );

    expect(result).toBeTrue();
  });

  it('should redirect to login when not authenticated', () => {
    authService.isAuthenticated.and.returnValue(false);
    const loginTree = {} as UrlTree;
    router.createUrlTree.and.returnValue(loginTree);

    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, { url: '/dashboard' } as RouterStateSnapshot),
    );

    expect(result).toBe(loginTree);
    expect(router.createUrlTree).toHaveBeenCalledWith(['/login'], {
      queryParams: { returnUrl: '/dashboard' },
    });
  });
});
```

**Binding rules:**
- Guard tests MUST use `TestBed.runInInjectionContext()` for functional guards.
- Guard tests MUST test both allowed and denied paths.
- Guard tests MUST verify redirect URL includes `returnUrl` query parameter.

---

## T9. HTTP Interceptor Template

**Template for Auth Token Interceptor (Functional):**

```ts
export const authInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
): Observable<HttpEvent<unknown>> => {
  const authService = inject(AuthService);
  const token = authService.getToken();

  if (token) {
    const cloned = req.clone({
      setHeaders: { Authorization: `Bearer ${token}` },
    });
    return next(cloned);
  }

  return next(req);
};
```

**Template for Error Handling Interceptor:**

```ts
export const errorInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
): Observable<HttpEvent<unknown>> => {
  const router = inject(Router);
  const notificationService = inject(NotificationService);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      switch (error.status) {
        case 401:
          router.navigate(['/login']);
          break;
        case 403:
          router.navigate(['/forbidden']);
          break;
        case 0:
          notificationService.showError('Network error. Please check your connection.');
          break;
        default:
          notificationService.showError(
            error.error?.message ?? 'An unexpected error occurred.',
          );
          break;
      }
      return throwError(() => error);
    }),
  );
};
```

**Template for Interceptor Registration:**

```ts
export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(
      withInterceptors([authInterceptor, errorInterceptor]),
    ),
    provideRouter({FEATURE}_ROUTES),
  ],
};
```

**Binding rules:**
- Interceptors MUST use functional interceptor pattern (`HttpInterceptorFn`), not class-based (deprecated).
- Auth interceptor MUST clone the request (never mutate the original).
- Error interceptor MUST handle at least 401 (redirect to login), 403, and network errors (status 0).
- Error interceptor MUST re-throw the error after handling (`throwError`).
- Interceptors MUST be registered via `withInterceptors()` in `provideHttpClient()`.

---

## T9.1 HTTP Interceptor Test Template

```ts
describe('authInterceptor', () => {
  let authService: jasmine.SpyObj<AuthService>;
  let httpMock: HttpTestingController;
  let httpClient: HttpClient;

  beforeEach(() => {
    authService = jasmine.createSpyObj('AuthService', ['getToken']);

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: authService },
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });

    httpClient = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should add Authorization header when token exists', () => {
    authService.getToken.and.returnValue('test-token');

    httpClient.get('/api/data').subscribe();

    const req = httpMock.expectOne('/api/data');
    expect(req.request.headers.get('Authorization')).toBe('Bearer test-token');
    req.flush({});
  });

  it('should NOT add Authorization header when no token', () => {
    authService.getToken.and.returnValue(null);

    httpClient.get('/api/data').subscribe();

    const req = httpMock.expectOne('/api/data');
    expect(req.request.headers.has('Authorization')).toBeFalse();
    req.flush({});
  });
});

describe('errorInterceptor', () => {
  let router: jasmine.SpyObj<Router>;
  let notificationService: jasmine.SpyObj<NotificationService>;
  let httpMock: HttpTestingController;
  let httpClient: HttpClient;

  beforeEach(() => {
    router = jasmine.createSpyObj('Router', ['navigate']);
    notificationService = jasmine.createSpyObj('NotificationService', ['showError']);

    TestBed.configureTestingModule({
      providers: [
        { provide: Router, useValue: router },
        { provide: NotificationService, useValue: notificationService },
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });

    httpClient = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should redirect to login on 401', () => {
    httpClient.get('/api/data').subscribe({ error: () => {} });

    httpMock.expectOne('/api/data').flush('Unauthorized', {
      status: 401,
      statusText: 'Unauthorized',
    });

    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('should show notification on server error', () => {
    httpClient.get('/api/data').subscribe({ error: () => {} });

    httpMock.expectOne('/api/data').flush(
      { message: 'Internal error' },
      { status: 500, statusText: 'Internal Server Error' },
    );

    expect(notificationService.showError).toHaveBeenCalledWith('Internal error');
  });
});
```

**Binding rules:**
- Interceptor tests MUST use `HttpTestingController` for HTTP mocking.
- Interceptor tests MUST call `httpMock.verify()` in `afterEach`.
- Auth interceptor tests MUST test both with-token and without-token paths.
- Error interceptor tests MUST test at least 401 redirect and generic error notification.

---

## T10. NgRx Store Pattern (Alternative State Management)

When the repository uses NgRx for state management instead of signals, use these templates.

**Template for Actions:**

```ts
export const {Feature}Actions = createActionGroup({
  source: '{Feature}',
  events: {
    'Load {Feature}s': emptyProps(),
    'Load {Feature}s Success': props<{ items: ReadonlyArray<{Feature}Item> }>(),
    'Load {Feature}s Failure': props<{ error: string }>(),
    'Create {Feature}': props<{ payload: Create{Feature}Request }>(),
    'Create {Feature} Success': props<{ item: {Feature}Item }>(),
    'Create {Feature} Failure': props<{ error: string }>(),
  },
});
```

**Template for Reducer:**

```ts
export interface {Feature}State {
  items: ReadonlyArray<{Feature}Item>;
  loading: boolean;
  error: string | null;
}

const initial{Feature}State: {Feature}State = {
  items: [],
  loading: false,
  error: null,
};

export const {feature}Reducer = createReducer(
  initial{Feature}State,
  on({Feature}Actions.load{Feature}s, (state) => ({
    ...state,
    loading: true,
    error: null,
  })),
  on({Feature}Actions.load{Feature}sSuccess, (state, { items }) => ({
    ...state,
    items,
    loading: false,
  })),
  on({Feature}Actions.load{Feature}sFailure, (state, { error }) => ({
    ...state,
    loading: false,
    error,
  })),
  on({Feature}Actions.create{Feature}Success, (state, { item }) => ({
    ...state,
    items: [...state.items, item],
  })),
);
```

**Template for Selectors:**

```ts
export const select{Feature}State = createFeatureSelector<{Feature}State>('{feature}');

export const select{Feature}Items = createSelector(
  select{Feature}State,
  (state) => state.items,
);

export const select{Feature}Loading = createSelector(
  select{Feature}State,
  (state) => state.loading,
);

export const select{Feature}Error = createSelector(
  select{Feature}State,
  (state) => state.error,
);

export const select{Feature}ViewModel = createSelector(
  select{Feature}Items,
  select{Feature}Loading,
  select{Feature}Error,
  (items, loading, error): {Feature}ViewModel => ({ items, loading, error }),
);
```

**Template for Effects:**

```ts
@Injectable()
export class {Feature}Effects {
  private readonly actions$ = inject(Actions);
  private readonly api = inject({Feature}Api);

  readonly load{Feature}s$ = createEffect(() =>
    this.actions$.pipe(
      ofType({Feature}Actions.load{Feature}s),
      switchMap(() =>
        this.api.fetchAll().pipe(
          map((items) => {Feature}Actions.load{Feature}sSuccess({ items })),
          catchError((error) =>
            of({Feature}Actions.load{Feature}sFailure({ error: error.message })),
          ),
        ),
      ),
    ),
  );

  readonly create{Feature}$ = createEffect(() =>
    this.actions$.pipe(
      ofType({Feature}Actions.create{Feature}),
      switchMap(({ payload }) =>
        this.api.create(payload).pipe(
          map((item) => {Feature}Actions.create{Feature}Success({ item })),
          catchError((error) =>
            of({Feature}Actions.create{Feature}Failure({ error: error.message })),
          ),
        ),
      ),
    ),
  );
}
```

**Binding rules:**
- MUST use `createActionGroup` for action definitions (not individual `createAction` calls).
- Reducers MUST be pure functions with no side effects.
- Selectors MUST compose from feature selector down (not access store directly).
- Effects MUST handle errors explicitly (no unhandled error propagation).
- Effects MUST use `switchMap` for loads and `concatMap`/`exhaustMap` for mutations (prevent race conditions).

---

## T10.1 NgRx Test Templates

**Template for Reducer Test:**

```ts
describe('{feature}Reducer', () => {
  it('should set loading to true on load{Feature}s', () => {
    const state = {feature}Reducer(initial{Feature}State, {Feature}Actions.load{Feature}s());

    expect(state.loading).toBeTrue();
    expect(state.error).toBeNull();
  });

  it('should set items on load{Feature}sSuccess', () => {
    const items = [{ id: '1', name: 'Test' }];
    const state = {feature}Reducer(
      { ...initial{Feature}State, loading: true },
      {Feature}Actions.load{Feature}sSuccess({ items }),
    );

    expect(state.items).toEqual(items);
    expect(state.loading).toBeFalse();
  });

  it('should set error on load{Feature}sFailure', () => {
    const state = {feature}Reducer(
      { ...initial{Feature}State, loading: true },
      {Feature}Actions.load{Feature}sFailure({ error: 'Network error' }),
    );

    expect(state.error).toBe('Network error');
    expect(state.loading).toBeFalse();
  });
});
```

**Template for Effects Test:**

```ts
describe('{Feature}Effects', () => {
  let effects: {Feature}Effects;
  let actions$: Observable<Action>;
  let api: jasmine.SpyObj<{Feature}Api>;

  beforeEach(() => {
    api = jasmine.createSpyObj('{Feature}Api', ['fetchAll', 'create']);

    TestBed.configureTestingModule({
      providers: [
        {Feature}Effects,
        provideMockActions(() => actions$),
        { provide: {Feature}Api, useValue: api },
      ],
    });

    effects = TestBed.inject({Feature}Effects);
  });

  it('should dispatch load success on successful fetch', () => {
    const items = [{ id: '1', name: 'Test' }];
    api.fetchAll.and.returnValue(of(items));
    actions$ = of({Feature}Actions.load{Feature}s());

    effects.load{Feature}s$.subscribe((action) => {
      expect(action).toEqual({Feature}Actions.load{Feature}sSuccess({ items }));
    });
  });

  it('should dispatch load failure on error', () => {
    api.fetchAll.and.returnValue(throwError(() => new Error('Network error')));
    actions$ = of({Feature}Actions.load{Feature}s());

    effects.load{Feature}s$.subscribe((action) => {
      expect(action).toEqual(
        {Feature}Actions.load{Feature}sFailure({ error: 'Network error' }),
      );
    });
  });
});
```

**Binding rules:**
- Reducer tests MUST test each action handler independently with known initial state.
- Effect tests MUST use `provideMockActions` and test both success and error paths.
- Selector tests SHOULD test composed selectors with known state slices.

---

## T11. Component Store Pattern (Alternative State Management)

When the repository uses NgRx Component Store for local/component-scoped state:

**Template for Component Store:**

```ts
export interface {Feature}State {
  items: ReadonlyArray<{Feature}Item>;
  loading: boolean;
  error: string | null;
}

const INITIAL_STATE: {Feature}State = {
  items: [],
  loading: false,
  error: null,
};

@Injectable()
export class {Feature}Store extends ComponentStore<{Feature}State> {
  private readonly api = inject({Feature}Api);

  constructor() {
    super(INITIAL_STATE);
  }

  // Selectors
  readonly items$ = this.select((state) => state.items);
  readonly loading$ = this.select((state) => state.loading);
  readonly vm$ = this.select(
    this.items$,
    this.loading$,
    (items, loading) => ({ items, loading }),
  );

  // Updaters
  readonly setLoading = this.updater((state, loading: boolean) => ({
    ...state,
    loading,
  }));

  readonly setItems = this.updater(
    (state, items: ReadonlyArray<{Feature}Item>) => ({
      ...state,
      items,
      loading: false,
    }),
  );

  readonly setError = this.updater((state, error: string) => ({
    ...state,
    error,
    loading: false,
  }));

  // Effects
  readonly load{Feature}s = this.effect((trigger$: Observable<void>) =>
    trigger$.pipe(
      tap(() => this.setLoading(true)),
      switchMap(() =>
        this.api.fetchAll().pipe(
          tapResponse(
            (items) => this.setItems(items),
            (error: Error) => this.setError(error.message),
          ),
        ),
      ),
    ),
  );
}
```

**Template for Container Component using Component Store:**

```ts
@Component({
  selector: 'app-{feature}-page',
  templateUrl: './{feature}-page.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  standalone: true,
  providers: [{Feature}Store],
  imports: [AsyncPipe, {Feature}ViewComponent],
})
export class {Feature}PageComponent implements OnInit {
  private readonly store = inject({Feature}Store);

  readonly vm$ = this.store.vm$;

  ngOnInit(): void {
    this.store.load{Feature}s(undefined);
  }

  onRefresh(): void {
    this.store.load{Feature}s(undefined);
  }
}
```

**Binding rules:**
- Component Store MUST be provided at component level (`providers: [{Feature}Store]`), not root.
- Updaters MUST be pure state transitions (no side effects).
- Effects MUST use `tapResponse` for error handling (prevents effect stream from dying).
- Selectors SHOULD compose from primitive selectors for memoization.

---

## T11.1 Component Store Test Template

```ts
describe('{Feature}Store', () => {
  let store: {Feature}Store;
  let api: jasmine.SpyObj<{Feature}Api>;

  beforeEach(() => {
    api = jasmine.createSpyObj('{Feature}Api', ['fetchAll']);

    TestBed.configureTestingModule({
      providers: [
        {Feature}Store,
        { provide: {Feature}Api, useValue: api },
      ],
    });

    store = TestBed.inject({Feature}Store);
  });

  it('should initialize with empty state', (done) => {
    store.vm$.subscribe((vm) => {
      expect(vm.items).toEqual([]);
      expect(vm.loading).toBeFalse();
      done();
    });
  });

  it('should load items successfully', (done) => {
    const items = [{ id: '1', name: 'Test' }];
    api.fetchAll.and.returnValue(of(items));

    store.load{Feature}s(undefined);

    store.items$.subscribe((result) => {
      expect(result).toEqual(items);
      done();
    });
  });

  it('should set error on load failure', (done) => {
    api.fetchAll.and.returnValue(throwError(() => new Error('Network error')));

    store.load{Feature}s(undefined);

    store.select((s) => s.error).subscribe((error) => {
      expect(error).toBe('Network error');
      done();
    });
  });
});
```

**Binding rules:**
- Component Store tests MUST test initial state, successful load, and error handling.
- Component Store tests MUST provide the store at test level (not root).
- Component Store tests MUST mock the API dependency.

---

## 14.5 Placeholder Substitution Rules (Binding)

When using templates above, substitute:

| Placeholder | Substitution | Example |
|------------|--------------|---------|
| `{Feature}` | Feature name (singular, PascalCase) | `User`, `Product`, `Dashboard` |
| `{feature}` | Feature name (singular, kebab-case) | `user`, `product`, `dashboard` |
| `{features}` | Feature name (plural, kebab-case) | `users`, `products`, `dashboards` |
| `{FEATURE}` | Feature name (singular, UPPER_SNAKE) | `USER`, `PRODUCT`, `DASHBOARD` |

Placeholders MUST be substituted in class names, selector strings, file names, route paths, and action group sources.

**Examples:**
- Template: `{Feature}Facade` -> Substituted: `UserFacade`, `ProductFacade`
- Template: `app-{feature}-page` -> Substituted: `app-user-page`, `app-product-page`
- Template: `/api/{features}` -> Substituted: `/api/users`, `/api/products`

---

## 16. FRONTEND LOGIC PLACEMENT GUIDE (Binding)

### 16.1 Decision Tree: WHERE to place frontend logic?

```
QUESTION: Where should I put this logic?

START
  |
IS it pure display/formatting logic?
  |-- YES -> Pipe or presentational component method
  |           Example: DatePipe, CurrencyPipe
  |           Example: formatUserName() in presentational component
  |
  +-- NO -+
          |
          IS it UI state management (loading, selection, pagination)?
          |-- YES -> Facade/Store (signals, ngrx, component-store)
          |           Example: facade.refresh(), store.setPage()
          |
          +-- NO -+
                  |
                  IS it data fetching or API communication?
                  |-- YES -> API boundary service
                  |           Example: {Feature}Api.fetchAll()
                  |
                  +-- NO -+
                          |
                          IS it cross-cutting (auth, error handling, logging)?
                          |-- YES -> Interceptor or Guard
                          |           Example: authInterceptor, errorInterceptor
                          |
                          +-- NO -> ASK USER
                                   (unclear responsibility)
```

**Binding Rule:**
When generating Angular code, the workflow MUST follow this decision tree and document the placement decision in the plan/response.

---

## 17. INTEGRATION CHECKLIST

To ensure LLMs generate optimal Angular code, verify:

### Code Generation
- Container component follows template (T1)
- Presentational component follows template (T2)
- Facade/Store follows template (T3 / T10 / T11, matching repo pattern)
- API boundary follows template (T4)
- Form follows template (T7) with typed reactive forms
- Guards follow template (T8) with functional guard pattern
- Interceptors follow template (T9) with functional interceptor pattern
- Placeholders substituted correctly (Section 14.5)

### Test Generation
- Facade/Store tests follow template (T5 / T10.1 / T11.1)
- E2E tests follow template (T6) with stable selectors
- Form tests follow template (T7.1) with validation coverage
- Guard tests follow template (T8.1) with allowed/denied paths
- Interceptor tests follow template (T9.1) with HttpTestingController

### Architecture
- Logic placement correct (Section 16.1 decision tree)
- No business logic in container/presentational components
- No direct HttpClient usage outside API boundary services
- State management pattern consistent across feature (no mixing signals + ngrx)
- ChangeDetection set to OnPush on all components
- All components are standalone

---

## 18. APPENDIX: WHY TEMPLATES MATTER FOR ANGULAR

### LLM Behavior Analysis

**Without Templates (Abstract Rules):**
```
Prompt: "Create a form component for user registration"

LLM reads: "Use reactive forms with validation"

LLM generates:
- Variation 1: Untyped FormGroup with template-driven validation
- Variation 2: Typed FormControl with class validation
- Variation 3: Mixed template-driven and reactive
-> Inconsistent (different every ticket)
```

**With Templates (Concrete Patterns):**
```
Prompt: "Create a form component for user registration"

LLM reads: Template T7 (Reactive Form Pattern)

LLM generates:
- Always: Typed FormGroup with FormControl<T>
- Always: nonNullable: true
- Always: Validators in class, markAllAsTouched on invalid submit
-> Consistent (same every ticket)
```

---

**END OF ANGULAR TEMPLATE ADDON EXPANSION**

---

## Principal Hardening v2 - Angular Template Conformance (Binding)

### ATPH2-1 Template conformance gate (binding)

For generated Angular business/test code, the workflow MUST verify and record conformance against templates T1–T11 (including form, guard, interceptor, and alternative state management templates).

Minimum conformance checks for changed scope:

- Container orchestrates only (no business branching or transport parsing in component)
- Presentational components use typed inputs/outputs with no state orchestration
- Facade/store pattern follows repo conventions (signals/ngrx/component-store)
- API boundary maps DTOs explicitly before UI consumption
- Tests assert behavior/state outcomes, not internal implementation

If any conformance item fails, principal completion cannot be declared.

### ATPH2-2 Evidence artifact contract (binding)

When templates are used, BuildEvidence MUST include references for:

- `EV-TPL-CODE`: code conformance evidence (path + snippet references)
- `EV-TPL-TEST`: test conformance evidence (path + test names)
- `EV-TPL-GATE`: gate decision evidence (pass/fail with rationale)

Claims without these evidence refs MUST be marked `not-verified`.

### ATPH2-3 High-risk template extensions (binding)

When touched scope includes routing guards, auth interceptors, or cross-lib Nx boundaries, template usage alone is not sufficient.
The workflow MUST add risk-specific checks and tests (guard behavior, auth/error semantics, boundary enforcement).

### ATPH2-4 Template deviation protocol (binding)

If repo conventions require deviation from templates, record:

- deviation reason
- preserved architectural intent
- risk impact (`low` | `medium` | `high`)
- compensating test added

Without deviation record, gate result cannot be `pass`.

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
