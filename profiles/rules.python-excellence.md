# Python Excellence Rulebook

This document defines language-specific excellence standards for Python.
It is an advisory addon that provides best practices complementing the UserMaxQuality addon.

## Intent (binding)

Enforce Python language excellence through:
- Pattern library for idiomatic Python
- Anti-pattern catalog with clear reasoning
- Test quality standards specific to Python
- Code quality verification commands

## Scope (binding)

All Python code changes including:
- Backend services (FastAPI/Flask/Django)
- CLI tools and scripts
- Test code
- Domain and infrastructure layers

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
As an advisory addon, this rulebook refines Python behavior and MUST NOT override master/core/profile constraints.

## Activation (binding)

Activation is manifest-owned via `profiles/addons/pythonExcellence.addon.yml`.
This rulebook defines behavior after activation and MUST NOT redefine activation signals.

## Phase integration (binding)

- Phase 2: detect Python patterns in codebase, initialize excellence checklist
- Phase 4: apply pattern/anti-pattern checks to changed scope
- Phase 5: verify excellence criteria with evidence refs
- Phase 6: ensure unresolved violations marked with recovery steps

## Evidence contract (binding)

- Maintain `SESSION_STATE.AddonsEvidence.pythonExcellence.status` (`loaded|skipped|missing-rulebook`).
- Advisory findings are represented via WARN codes in `warnings[]`; do not hard-block solely from this addon.

## Tooling (binding)

Use repository-native Python tooling for verification:
- Format/lint: `ruff check .` or configured formatter
- Type checking: `mypy --strict src/` when mypy is configured
- Tests: `pytest tests/ --cov=src --cov-report=term-missing`
- Security: `pip-audit` or `safety check`

When tooling is unavailable in host:
- Emit recovery commands
- Mark affected claims as `NOT_VERIFIED`
- Continue conservatively without fabricating evidence

---

## Quality Contract (Binding)

### Required Output Sections (User Mode)

When this addon is active with UserMaxQuality, Python-specific sections enhance the base sections:

1. **Intent & Scope** - Include Python-specific choices (async vs sync, framework choice)
2. **Non-goals** - Include Python features explicitly deferred (e.g., type hints migration)
3. **Design/Architecture** - Include module structure, import boundaries, dependency injection pattern
4. **Invariants & Failure Modes** - Include Python-specific failure modes (GIL, async/await, exceptions)
5. **Test Plan (Matrix)** - Include pytest fixtures, async test strategy, mock strategy
6. **Edge Cases Checklist** - Include Python-specific edges (None, empty collections, type coercion)
7. **Verification Commands** - Include Python-specific commands (pytest, mypy, ruff)
8. **Risk Review** - Include Python-specific risks (GIL contention, circular imports, memory leaks)
9. **Rollback Plan** - Include Python-specific rollback (dependency pins, virtual env recreate)

### Verification Handshake (Binding)

Inherits from UserMaxQuality. Python-specific verification:

```
LLM Output: "Verification Commands: [pytest, mypy, ruff check]"
Human Response: "Executed pytest: 42 passed, 0 failed; Executed mypy: Success; Executed ruff: 3 warnings fixed"
LLM: Set `Verified` only after receiving results
```

### Risk-Tier Triggers (Binding)

Python-specific risk surfaces and additional requirements:

| Risk Surface | Trigger Patterns | Additional Requirements |
|--------------|------------------|------------------------|
| Async/Concurrency | `async def`, `await`, `asyncio`, `threading` | Async test coverage, deadlock audit, GIL impact analysis |
| Type Safety | `Any`, `# type: ignore`, missing annotations | mypy strict mode, type coverage report |
| Exceptions | `except Exception`, `except:`, bare raise | Exception hierarchy audit, error propagation review |
| Dependencies | `requirements*.txt`, `pyproject.toml`, `setup.py` | Dependency audit, version pinning, security scan |

### Claim Verification (Binding)

Python-specific claim markers:

- **ASSUMPTION(PY)**: Python version, package availability, virtual environment
  - Example: `ASSUMPTION(PY): Python 3.11+ for typing.Self`
  - Example: `ASSUMPTION(PY): pytest-asyncio available for async tests`

- **NOT_VERIFIED(PY)**: Python-specific execution not performed
  - Example: `NOT_VERIFIED(PY): mypy strict passes (not run)`
  - Example: `NOT_VERIFIED(PY): No circular imports (not verified)`

---

## Pattern Library (Binding)

### PAT-PY01: Dependency Injection via Constructor

**Pattern:** Services receive dependencies as constructor parameters, not module-level imports.

```python
# GOOD
class UserService:
    def __init__(self, repository: UserRepository, clock: ClockPort):
        self._repository = repository
        self._clock = clock

    def create_user(self, command: CreateUserCommand) -> User:
        now = self._clock.now()
        user = User.create(name=command.name, created_at=now)
        return self._repository.save(user)

# BAD - implicit dependency
class UserService:
    def create_user(self, command: CreateUserCommand) -> User:
        now = datetime.now()  # Implicit, untestable
        user = User.create(name=command.name, created_at=now)
        return get_repository().save(user)  # Hidden dependency
```

**Why:** Enables unit testing without monkeypatching; explicit dependencies; single source of truth.

---

### PAT-PY02: In-Memory Fakes Over Mocks

**Pattern:** Use simple in-memory implementations for repositories and ports in tests.

```python
# GOOD - in-memory fake
class InMemoryUserRepository(UserRepository):
    def __init__(self):
        self._users: dict[UserId, User] = {}

    def save(self, user: User) -> User:
        self._users[user.id] = user
        return user

    def find_by_id(self, user_id: UserId) -> User | None:
        return self._users.get(user_id)

# BAD - mock overuse
def test_create_user():
    mock_repo = MagicMock()
    mock_repo.save.return_value = User(id=1, name="test")
    # This tests nothing about actual behavior
```

**Why:** Fakes test actual behavior; mocks only test call signatures; fakes are reusable across tests.

---

### PAT-PY03: Fixed Time in Tests

**Pattern:** All datetime-dependent code receives time via injected clock; tests use fixed time.

```python
# GOOD
FIXED_TIME = datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)

class FakeClock(ClockPort):
    def __init__(self, now: datetime = FIXED_TIME):
        self._now = now

    def now(self) -> datetime:
        return self._now

def test_user_created_at():
    clock = FakeClock()
    service = UserService(repository=fake_repo, clock=clock)
    user = service.create_user(CreateUserCommand(name="test"))
    assert user.created_at == FIXED_TIME

# BAD - datetime.now() in tests
def test_user_created_at():
    service = UserService(repository=fake_repo)
    user = service.create_user(CreateUserCommand(name="test"))
    assert user.created_at <= datetime.now()  # Flaky!
```

**Why:** Deterministic tests; reproducible failures; no flaky time-dependent assertions.

---

### PAT-PY04: Domain Models Without Framework Dependencies

**Pattern:** Domain models are pure Python classes without ORM/Pydantic annotations.

```python
# GOOD - pure domain
@dataclass(frozen=True)
class User:
    id: UserId
    name: str
    created_at: datetime

    @classmethod
    def create(cls, *, name: str, created_at: datetime) -> "User":
        if not name or len(name) > 100:
            raise ValidationError("name must be 1-100 characters")
        return cls(id=UserId(uuid4()), name=name, created_at=created_at)

    def update(self, *, name: str | None = None) -> "User":
        return User(
            id=self.id,
            name=name if name is not None else self.name,
            created_at=self.created_at,
        )

# BAD - framework-coupled
class User(BaseModel):  # Pydantic in domain
    id: UUID
    name: str

    @validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError("...")
        return v
```

**Why:** Domain logic testable without any framework; portable across persistence layers; no hidden validation behavior.

---

### PAT-PY05: Explicit Error Types

**Pattern:** Use custom exception classes with clear hierarchy, never bare `Exception`.

```python
# GOOD
class DomainError(Exception):
    """Base for all domain errors."""

class ValidationError(DomainError):
    """Input validation failed."""

class UserNotFoundError(DomainError):
    """User does not exist."""

class UserAlreadyExistsError(DomainError):
    """User with this identifier already exists."""

# Handler
def create_user(payload: CreateUserRequest, service: UserService) -> Response:
    try:
        command = map_request_to_command(payload)
        user = service.create_user(command)
        return JsonResponse(UserResponse.from_domain(user), status=201)
    except ValidationError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except UserAlreadyExistsError as e:
        return JsonResponse({"error": str(e)}, status=409)

# BAD
def create_user(payload):
    try:
        # ...
    except Exception as e:
        logger.error(f"Error: {e}")
        return JsonResponse({"error": "Internal error"}, status=500)
```

**Why:** Explicit error handling; proper HTTP status codes; errors are part of the API contract.

---

## Anti-Pattern Catalog (Binding)

### AP-PY-EXCEL-01: Fat Handler

**Pattern:** Business logic in route/handler functions.

**Detection:** Handler functions with `if`/`match` on domain state, calculations, or orchestration.

**Recovery:** Extract to service layer; handler only maps request → command, calls service, maps response.

---

### AP-PY-EXCEL-02: Nondeterministic Time

**Pattern:** `datetime.now()`, `time.time()`, `time.sleep()` in production or test code without injection.

**Detection:** Direct calls without injectable seams.

**Recovery:** Inject `ClockPort`; use `FakeClock` in tests with `FIXED_TIME`.

---

### AP-PY-EXCEL-03: Mock Overuse

**Pattern:** More `mock.patch`/`MagicMock` than assertions; tests that only `assert_called_with`.

**Detection:** Test files dominated by mock setup; no behavioral assertions.

**Recovery:** Create in-memory fakes; test actual behavior, not implementation details.

---

### AP-PY-EXCEL-04: Framework in Domain

**Pattern:** Pydantic, SQLAlchemy, or Django ORM classes in domain layer.

**Detection:** Domain imports from `pydantic`, `sqlalchemy`, `django.db`.

**Recovery:** Create pure Python domain models; map at repository boundary.

---

### AP-PY-EXCEL-05: Missing Type Annotations

**Pattern:** Public functions/methods without return type; parameters without types.

**Detection:** `mypy --strict` failures; functions with `-> None` implicit.

**Recovery:** Add explicit type annotations; run `mypy --strict` before commit.

---

### AP-PY-EXCEL-06: Circular Imports

**Pattern:** Import errors at startup; `TYPE_CHECKING` imports as workaround.

**Detection:** `ImportError` during import; circular dependency in module graph.

**Recovery:** Restructure to eliminate circular dependency; introduce interface module; use dependency injection.

---

### AP-PY-EXCEL-07: Async Without Boundaries

**Pattern:** Blocking I/O in `async def`; sync ORM in async handler.

**Detection:** `async def` calling sync database/HTTP without `to_thread`.

**Recovery:** Use async-native libraries (SQLAlchemy async, httpx); or wrap sync calls in `asyncio.to_thread`.

---

### AP-PY-EXCEL-08: Mutable Global State

**Pattern:** Module-level mutable variables modified at runtime.

**Detection:** `_cache = {}`, `_db = None` at module scope with runtime modification.

**Recovery:** Use dependency injection; pass state through constructor/parameters.

---

## Verification Commands (Binding)

When this addon is active, verify Python excellence with:

```bash
# Format and lint
ruff check .

# Type checking
mypy --strict src/

# Tests with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Import check (no circular imports)
python -c "from src import *"  # Should not raise ImportError

# Security scan
pip-audit  # or safety check
```

---

## Warning Codes (Binding)

- `WARN-PYTHON-EXCEL-MOCK-OVERUSE`: Test file has more mocks than assertions
- `WARN-PYTHON-EXCEL-MISSING-TYPES`: Public API missing type annotations
- `WARN-PYTHON-EXCEL-FRAMEWORK-IN-DOMAIN`: Domain imports framework
- `WARN-PYTHON-EXCEL-ASYNC-MIXING`: Async function calls blocking I/O

---

## Shared Principal Governance Contracts (Binding)

This addon delegates to shared governance contracts:

- `rules.principal-excellence.md` - Principal-grade review criteria
- `rules.risk-tiering.md` - Risk tier classification
- `rules.scorecard-calibration.md` - Scorecard evaluation

Tracking keys (audit pointers, not activation logic):
- `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
- `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
- `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`

---

## Examples (GOOD/BAD)

### GOOD: Complete Python Excellence

```python
# domain/user.py - pure domain
@dataclass(frozen=True)
class User:
    id: UserId
    name: str
    created_at: datetime

    @classmethod
    def create(cls, *, name: str, created_at: datetime) -> "User":
        if not name:
            raise ValidationError("name is required")
        return cls(id=UserId(uuid4()), name=name, created_at=created_at)

# service/user_service.py - dependency injection
class UserService:
    def __init__(self, repository: UserRepository, clock: ClockPort):
        self._repository = repository
        self._clock = clock

    def create_user(self, command: CreateUserCommand) -> User:
        user = User.create(name=command.name, created_at=self._clock.now())
        return self._repository.save(user)

# tests/test_user_service.py - in-memory fake, fixed time
FIXED_TIME = datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)

class InMemoryUserRepository(UserRepository):
    def __init__(self):
        self._users: dict[UserId, User] = {}
    def save(self, user: User) -> User:
        self._users[user.id] = user
        return user

def test_create_user():
    repo = InMemoryUserRepository()
    clock = FakeClock(FIXED_TIME)
    service = UserService(repository=repo, clock=clock)

    user = service.create_user(CreateUserCommand(name="Alice"))

    assert user.name == "Alice"
    assert user.created_at == FIXED_TIME
```

### BAD: Multiple Violations

```python
# Violations: no DI, datetime.now(), framework in domain, no types
class User(BaseModel):
    name: str

def create_user(payload):
    user = User(name=payload.name)
    user.created_at = datetime.now()  # Nondeterministic
    db.add(user)  # Hidden dependency, framework in domain
    db.commit()
    return user

def test_create_user():
    with patch("module.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 31)
        # Mocks everything, tests nothing about behavior
        user = create_user(Mock(name="test"))
        assert user.name == "test"
```

---

## Troubleshooting

1) Symptom: WARN-PYTHON-EXCEL-MOCK-OVERUSE
- Cause: Test file uses mocks instead of fakes
- Fix: Create in-memory fake for repository/port, remove mocks

2) Symptom: WARN-PYTHON-EXCEL-MISSING-TYPES
- Cause: Public function lacks return type annotation
- Fix: Add explicit return type; run `mypy --strict`

3) Symptom: WARN-PYTHON-EXCEL-FRAMEWORK-IN-DOMAIN
- Cause: Domain model imports Pydantic/SQLAlchemy
- Fix: Create pure Python dataclass; map at repository boundary

4) Symptom: WARN-PYTHON-EXCEL-ASYNC-MIXING
- Cause: async def calls sync database without to_thread
- Fix: Use async-native library or wrap in asyncio.to_thread

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
