# Backend Python Templates Addon Rulebook (v2.0)

## Intent (binding)

Provide deterministic backend-python templates so assistant-generated code/tests stay reviewable, boundary-safe, and reproducible.

## Scope (binding)

Python template patterns for API handlers (CRUD variations), services/use-cases, domain models, repository boundaries, error handling, and deterministic test scaffolding (unit, integration, test data builders).

## Activation (binding)

Addon class: `required`.

This addon MUST be loaded at code-phase (Phase 4+) when `SESSION_STATE.ActiveProfile = "backend-python"`.
- Missing-addon handling MUST follow canonical required-addon policy from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`.
- This rulebook MUST NOT redefine blocking semantics.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This required addon refines template defaults and MUST NOT override `master.md`, `rules.md`, or `rules.backend-python.md` constraints.
- In conflicts, this addon's templates override abstract style/principles per `RULEBOOK-PRECEDENCE-POLICY` (concrete-template > abstract-style, same priority tier).

## Phase integration (binding)

- Phase 2: discover python runtime/build/test conventions and capture deterministic seams.
- Phase 4: apply template defaults for changed scope and record only minimal convention-aligned deviations.
- Phase 5.3: verify template-derived quality claims with concrete evidence.

## Evidence contract (binding)

- Record template load/evidence in `SESSION_STATE.LoadedRulebooks.templates` and `SESSION_STATE.RulebookLoadEvidence.templates`.
- Template-derived gate claims MUST reference `SESSION_STATE.BuildEvidence.items[]` identifiers.
- Missing evidence MUST remain `NOT_VERIFIED`.

Evidence artifact codes (binding):

- `EV-TPL-CODE`: code conformance evidence (path + snippet references)
- `EV-TPL-TEST`: test conformance evidence (path + test names)
- `EV-TPL-GATE`: gate decision evidence (pass/fail with rationale)

## Shared Principal Governance Contracts (Binding)

To keep this addon focused on backend-python template mechanics, shared principal governance contracts are modularized into advisory rulebooks:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior for this addon:

- At code/review phases (Phase 4+), these shared contracts MUST be loaded as advisory governance contracts.
- If one shared rulebook is unavailable, emit warning, keep affected claims `not-verified`, and continue conservatively.

## Tooling (recommended)

- SHOULD use repo-native Python commands and lockfile-aware invocation (`pytest`, `ruff`, `mypy`, `uv`, `poetry`, `pip-tools`, `alembic`).
- Preserve deterministic command order (lint -> type -> targeted tests -> full tests).
- If host cannot run required tooling, emit one concrete recovery command and keep affected claims `NOT_VERIFIED`.

## Correctness by construction (binding)

Inputs required:
- endpoint/use-case name and module path
- boundary contract context (request/response/domain mapping)
- persistence boundary expectations

Outputs guaranteed:
- handler/service/domain/repository/test scaffolds for changed scope
- explicit deterministic seams for time/random/external side effects
- explicit DTO/domain mapping boundaries
- error handling with stable error codes

Evidence expectation:
- template-derived claims MUST be backed by lint/type/test evidence or remain `NOT_VERIFIED`.
evidence_kinds_required:
  - "unit-test"
  - "lint"
  - "integration-test"

Golden examples:
- API handler delegates business decisions to service in one clear call.
- Service depends on injected boundary interfaces and deterministic seams.

Anti-example:
- Transport-layer object leaks into domain logic with no explicit mapper boundary.

---

## 14. LLM CODE GENERATION PATTERNS (Binding)

### Core Principle

LLMs are **pattern matchers**, not abstract reasoners.

- BAD **Abstract rule:** "Handlers should delegate to services"
  -> LLM generates 10 different variations (inconsistent)

- GOOD **Concrete template:** `result = service.create_item(domain_input)`
  -> LLM copies exact structure (consistent, correct)

**Rule (Binding):**
When generating code, the assistant MUST follow the templates in this section as the default structure, substituting placeholders marked with `{...}`.

If a template conflicts with repository-established conventions (locked in `SESSION_STATE`), the assistant MUST:
- keep the same architectural intent,
- apply the minimal convention-aligned adaptation,
- and record the deviation briefly in the plan/evidence.

---

### 14.1 Handler Pattern (REST API Endpoint)

**Template for POST (Create):**

```python
from pydantic import BaseModel
from fastapi import APIRouter, Depends, status

router = APIRouter()


class Create{Resource}Request(BaseModel):
    name: str


class {Resource}Response(BaseModel):
    id: str
    name: str


@router.post("/{resources}", response_model={Resource}Response, status_code=status.HTTP_201_CREATED)
def create_{resource}(
    payload: Create{Resource}Request,
    service: "{Resource}Service" = Depends(get_{resource}_service),
) -> {Resource}Response:
    # 1. Map to domain
    domain_input = map_request_to_domain(payload)

    # 2. Delegate (single call, no logic here)
    result = service.create_{resource}(domain_input)

    # 3. Map to response
    return map_domain_to_response(result)
```

**Template for GET (Read by ID):**

```python
@router.get("/{resources}/{{resource_id}}", response_model={Resource}Response)
def get_{resource}(
    resource_id: str,
    service: "{Resource}Service" = Depends(get_{resource}_service),
) -> {Resource}Response:
    result = service.find_by_id(resource_id)
    if result is None:
        raise {Resource}NotFoundError(resource_id)
    return map_domain_to_response(result)
```

**Template for GET (List with pagination):**

```python
class {Resource}ListResponse(BaseModel):
    items: list[{Resource}Response]
    total: int
    page: int
    page_size: int


@router.get("/{resources}", response_model={Resource}ListResponse)
def list_{resources}(
    page: int = 1,
    page_size: int = 20,
    service: "{Resource}Service" = Depends(get_{resource}_service),
) -> {Resource}ListResponse:
    items, total = service.list_{resources}(page=page, page_size=page_size)
    return {Resource}ListResponse(
        items=[map_domain_to_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
```

**Template for PUT (Update):**

```python
class Update{Resource}Request(BaseModel):
    name: str


@router.put("/{resources}/{{resource_id}}", response_model={Resource}Response)
def update_{resource}(
    resource_id: str,
    payload: Update{Resource}Request,
    service: "{Resource}Service" = Depends(get_{resource}_service),
) -> {Resource}Response:
    domain_input = map_update_to_domain(payload)
    result = service.update_{resource}(resource_id, domain_input)
    return map_domain_to_response(result)
```

**Template for DELETE:**

```python
@router.delete("/{resources}/{{resource_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_{resource}(
    resource_id: str,
    service: "{Resource}Service" = Depends(get_{resource}_service),
) -> None:
    service.delete_{resource}(resource_id)
```

**Binding Rules:**
- Handlers MUST NOT contain business branching (no `if` for business rules).
- Handlers MUST delegate to service in a **single call**.
- Transport/domain mapping MUST be explicit (dedicated mapper functions).
- Handlers MUST use Pydantic models for request/response validation.
- Handlers MUST use dependency injection (`Depends(...)`) for service access.

---

### 14.2 Service Pattern (Use Case / Business Logic)

**Template for Service:**

```python
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class {Resource}Service:
    repository: "{Resource}Repository"
    clock: "ClockPort"

    def create_{resource}(self, command: "Create{Resource}Command") -> "{Resource}":
        now = self.clock.now_utc()
        {resource} = {Resource}.create(name=command.name, created_at=now)
        {resource}.validate()
        return self.repository.save({resource})

    def find_by_id(self, resource_id: str) -> "{Resource} | None":
        return self.repository.find_by_id(resource_id)

    def list_{resources}(
        self, *, page: int = 1, page_size: int = 20
    ) -> tuple[list["{Resource}"], int]:
        return self.repository.find_all(page=page, page_size=page_size)

    def update_{resource}(
        self, resource_id: str, command: "Update{Resource}Command"
    ) -> "{Resource}":
        existing = self.repository.find_by_id(resource_id)
        if existing is None:
            raise {Resource}NotFoundError(resource_id)
        existing.update(name=command.name, updated_at=self.clock.now_utc())
        return self.repository.save(existing)

    def delete_{resource}(self, resource_id: str) -> None:
        existing = self.repository.find_by_id(resource_id)
        if existing is None:
            raise {Resource}NotFoundError(resource_id)
        existing.validate_can_be_deleted()
        self.repository.delete(existing)
```

**Binding Rules:**
- Services MUST inject deterministic seams (`clock`, repositories) via constructor/dataclass fields.
- Services MUST keep business decisions in domain/service, not in handler.
- Services SHOULD delegate validation and state mutation to domain model methods.
- Services coordinate **orchestration** (call multiple repos/domain objects).
- Services MUST NOT import or depend on transport-layer types (Pydantic request/response models).

---

### 14.3 Domain Model Pattern (Rich Domain)

**Template for Domain Model:**

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Self


@dataclass
class {Resource}:
    id: str | None = None
    name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1

    @classmethod
    def create(cls, *, name: str, created_at: datetime) -> Self:
        """Factory method for creating a new {resource}."""
        instance = cls(name=name, created_at=created_at, updated_at=created_at)
        instance.validate()
        return instance

    def validate(self) -> None:
        """Enforce domain invariants."""
        if not self.name or not self.name.strip():
            raise ValidationError("Name is required")
        if len(self.name) > 100:
            raise ValidationError("Name must not exceed 100 characters")

    def update(self, *, name: str, updated_at: datetime) -> None:
        """Update mutable fields via domain method (not direct assignment)."""
        self.name = name
        self.updated_at = updated_at
        self.validate()

    def validate_can_be_deleted(self) -> None:
        """Check invariants before deletion."""
        # Example: if self.has_active_contracts():
        #     raise BusinessError("Cannot delete: active contracts exist")
        pass
```

**Binding Rules:**
- Domain models MUST enforce invariants in domain methods (not in handlers or mappers).
- Domain models MUST NOT have direct dependencies on infrastructure (ORM, HTTP, etc.).
- Domain models SHOULD use `@classmethod` factory methods for creation with validation.
- Mutable state changes MUST go through named domain methods (not bare attribute assignment from outside).
- Timestamps MUST be `datetime` with timezone awareness (UTC).

---

### 14.4 Error Handling Pattern

**Template for Custom Domain Exception:**

```python
class {Resource}NotFoundError(Exception):
    """Raised when a {resource} cannot be found by its identifier."""

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        super().__init__(f"{Resource} not found: {resource_id}")


class ValidationError(Exception):
    """Raised when domain invariant validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        self.field = field
        super().__init__(message)


class BusinessError(Exception):
    """Raised when a business rule prevents an operation."""

    def __init__(self, message: str, code: str = "BUSINESS_RULE_VIOLATED") -> None:
        self.code = code
        super().__init__(message)
```

**Template for Global Exception Handler (FastAPI):**

```python
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def register_exception_handlers(app: FastAPI, clock: "ClockPort") -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler({Resource}NotFoundError)
    async def handle_{resource}_not_found(
        request: Request, exc: {Resource}NotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "status": 404,
                "message": str(exc),
                "code": "{RESOURCE}_NOT_FOUND",
                "timestamp": clock.now_utc().isoformat(),
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(ValidationError)
    async def handle_validation(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "status": 400,
                "message": str(exc),
                "code": "VALIDATION_FAILED",
                "field": exc.field,
                "timestamp": clock.now_utc().isoformat(),
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(BusinessError)
    async def handle_business_error(
        request: Request, exc: BusinessError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "message": str(exc),
                "code": exc.code,
                "timestamp": clock.now_utc().isoformat(),
                "path": str(request.url.path),
            },
        )
```

**Binding Rules:**
- Exception handlers MUST use FastAPI's `@app.exception_handler` or equivalent framework mechanism.
- Error responses MUST have stable error codes (not just HTTP status).
- Error responses SHOULD include timestamp (from injected clock) and request path.
- Domain exceptions MUST NOT depend on transport/framework types.
- Handler tests MUST NOT assert on timestamp unless Clock is controlled/mocked.

---

### 14.5 Placeholder Substitution Rules (Binding)

When using templates above, substitute:

| Placeholder | Substitution | Example |
|------------|--------------|---------|
| `{Resource}` | Entity name (singular, PascalCase) | `User`, `Order`, `Product` |
| `{resource}` | Entity name (singular, snake_case) | `user`, `order`, `product` |
| `{resources}` | Entity name (plural, snake_case/lowercase) | `users`, `orders`, `products` |
| `{RESOURCE}` | Entity name (singular, UPPER_SNAKE) | `USER`, `ORDER`, `PRODUCT` |

Placeholders MUST be substituted in class names, function names, variable names, route paths, and string literals (e.g., error messages, error codes).

**Examples:**
- Template: `{Resource}Service` -> Substituted: `UserService`, `OrderService`
- Template: `create_{resource}` -> Substituted: `create_user`, `create_order`
- Template: `/{resources}` -> Substituted: `/users`, `/orders`
- Template: `{RESOURCE}_NOT_FOUND` -> Substituted: `USER_NOT_FOUND`, `ORDER_NOT_FOUND`

---

## 15. LLM TEST GENERATION PATTERNS (Binding)

### Core Principle

Tests are HARDER for LLMs than business code. Without templates:
- BAD Flaky (uses `datetime.now()`)
- BAD Overspecified (tests implementation, not behavior)
- BAD Inconsistent (different styles every ticket)

With templates:
- GOOD Deterministic (fixed time, seeded random)
- GOOD Behavior-focused (tests outcomes, not internals)
- GOOD Consistent (always same structure)

---

### 15.1 Test Data Builder Pattern (MUST use)

**Template for Test Data Builder:**

```python
from datetime import datetime, timezone


FIXED_TIME = datetime(2026, 1, 31, 10, 0, 0, tzinfo=timezone.utc)


def given_{resource}(**overrides) -> "{Resource}":
    """Build a {Resource} with sensible defaults. Override any field via kwargs."""
    defaults = {
        "id": "test-id-1",
        "name": "Test {Resource}",
        "created_at": FIXED_TIME,
        "updated_at": FIXED_TIME,
        "version": 1,
    }
    defaults.update(overrides)
    return {Resource}(**defaults)


def given_create_{resource}_request(**overrides) -> "Create{Resource}Request":
    """Build a Create{Resource}Request with sensible defaults."""
    defaults = {
        "name": "Test {Resource}",
    }
    defaults.update(overrides)
    return Create{Resource}Request(**defaults)


def given_{resource}_response(**overrides) -> "{Resource}Response":
    """Build a {Resource}Response with sensible defaults."""
    defaults = {
        "id": "test-id-1",
        "name": "Test {Resource}",
    }
    defaults.update(overrides)
    return {Resource}Response(**defaults)
```

**Binding Rules:**
- MUST use builder functions (never construct domain objects with raw constructors in tests).
- MUST use `FIXED_TIME` (never `datetime.now()` or `datetime.utcnow()`).
- MUST use `given_{resource}()` naming convention for builder functions.
- Builder functions MUST accept `**overrides` for field-level customization.
- Test data builders MUST be in the test directory (same package structure as production code).

---

### 15.2 Service Unit Test Template

**Template for Service Test:**

```python
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

FIXED_TIME = datetime(2026, 1, 31, 10, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    """Deterministic clock for testing."""

    def __init__(self, fixed_time: datetime = FIXED_TIME) -> None:
        self._now = fixed_time

    def now_utc(self) -> datetime:
        return self._now


class TestCreate{Resource}:
    """Tests for {Resource}Service.create_{resource}()."""

    def test_create_{resource}_persists_with_timestamps(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)
        command = Create{Resource}Command(name="alpha")

        # WHEN
        created = service.create_{resource}(command)

        # THEN
        assert created.name == "alpha"
        assert created.created_at == FIXED_TIME
        assert created.updated_at == FIXED_TIME
        assert fake_repository.saved_items == [created]

    def test_create_{resource}_with_invalid_name_raises_validation_error(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)
        command = Create{Resource}Command(name="")

        # WHEN / THEN
        with pytest.raises(ValidationError, match="Name is required"):
            service.create_{resource}(command)


class TestFind{Resource}ById:
    """Tests for {Resource}Service.find_by_id()."""

    def test_find_by_id_when_exists_returns_{resource}(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        existing = given_{resource}()
        fake_repository.saved_items = [existing]
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)

        # WHEN
        result = service.find_by_id(existing.id)

        # THEN
        assert result is not None
        assert result.id == existing.id
        assert result.name == existing.name

    def test_find_by_id_when_not_exists_returns_none(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)

        # WHEN
        result = service.find_by_id("nonexistent-id")

        # THEN
        assert result is None


class TestUpdate{Resource}:
    """Tests for {Resource}Service.update_{resource}()."""

    def test_update_{resource}_applies_changes(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        existing = given_{resource}(id="res-1", name="old-name")
        fake_repository.saved_items = [existing]
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)
        command = Update{Resource}Command(name="new-name")

        # WHEN
        result = service.update_{resource}("res-1", command)

        # THEN
        assert result.name == "new-name"
        assert result.updated_at == FIXED_TIME

    def test_update_{resource}_when_not_found_raises_error(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)

        # WHEN / THEN
        with pytest.raises({Resource}NotFoundError):
            service.update_{resource}("nonexistent", Update{Resource}Command(name="x"))


class TestDelete{Resource}:
    """Tests for {Resource}Service.delete_{resource}()."""

    def test_delete_{resource}_removes_from_repository(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        existing = given_{resource}(id="res-1")
        fake_repository.saved_items = [existing]
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)

        # WHEN
        service.delete_{resource}("res-1")

        # THEN
        assert fake_repository.saved_items == []

    def test_delete_{resource}_when_not_found_raises_error(
        self, fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
    ) -> None:
        # GIVEN
        service = {Resource}Service(repository=fake_repository, clock=fake_clock)

        # WHEN / THEN
        with pytest.raises({Resource}NotFoundError):
            service.delete_{resource}("nonexistent")
```

**Binding Rules:**
- Test classes MUST group tests by method under test (one class per method).
- Test classes MUST have descriptive docstrings indicating the method under test.
- Test methods MUST follow pattern: `test_{method_name}_{condition}_{expected_outcome}`.
- Test methods MUST use GIVEN/WHEN/THEN comments for structure.
- Test methods MUST use pytest assertions (not `unittest.TestCase`).
- Test methods MUST use pytest.raises for exception assertions.
- Clock MUST be faked with `FIXED_TIME` (never `datetime.now()`).
- Repository MUST be faked with in-memory implementation (not mocks, unless testing interaction contracts).

---

### 15.3 Handler Integration Test Template

**Template for Handler Integration Test:**

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock


FIXED_TIME = datetime(2026, 1, 31, 10, 0, 0, tzinfo=timezone.utc)


class TestCreate{Resource}Handler:
    """Integration tests for POST /{resources}."""

    def test_create_with_valid_request_returns_201(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        # GIVEN
        request_body = {"name": "Test {Resource}"}
        domain_{resource} = given_{resource}()
        mock_service.create_{resource}.return_value = domain_{resource}

        # WHEN
        response = client.post("/{resources}", json=request_body)

        # THEN
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == domain_{resource}.id
        assert data["name"] == domain_{resource}.name

    def test_create_with_empty_name_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        # GIVEN
        request_body = {"name": ""}

        # WHEN
        response = client.post("/{resources}", json=request_body)

        # THEN
        assert response.status_code == 422

    def test_create_with_missing_name_returns_422(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        # GIVEN
        request_body = {}

        # WHEN
        response = client.post("/{resources}", json=request_body)

        # THEN
        assert response.status_code == 422


class TestGet{Resource}Handler:
    """Integration tests for GET /{resources}/{id}."""

    def test_get_when_exists_returns_200(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        # GIVEN
        domain_{resource} = given_{resource}(id="res-1")
        mock_service.find_by_id.return_value = domain_{resource}

        # WHEN
        response = client.get("/{resources}/res-1")

        # THEN
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "res-1"
        assert data["name"] == domain_{resource}.name

    def test_get_when_not_exists_returns_404(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        # GIVEN
        mock_service.find_by_id.return_value = None

        # WHEN
        response = client.get("/{resources}/nonexistent")

        # THEN
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "{RESOURCE}_NOT_FOUND"


class TestDelete{Resource}Handler:
    """Integration tests for DELETE /{resources}/{id}."""

    def test_delete_when_exists_returns_204(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        # GIVEN
        mock_service.delete_{resource}.return_value = None

        # WHEN
        response = client.delete("/{resources}/res-1")

        # THEN
        assert response.status_code == 204

    def test_delete_when_not_found_returns_404(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        # GIVEN
        mock_service.delete_{resource}.side_effect = {Resource}NotFoundError("res-1")

        # WHEN
        response = client.delete("/{resources}/res-1")

        # THEN
        assert response.status_code == 404
```

**Binding Rules:**
- Handler tests MUST use `TestClient` (FastAPI) or equivalent framework test client.
- Handler tests MUST test HTTP contract (status codes, JSON structure).
- Handler tests MUST mock the service layer (not the repository).
- Handler tests MUST validate error cases (400, 404, 422, etc.).
- Handler tests MUST NOT assert on timestamps unless Clock is controlled/mocked.

---

### 15.4 Repository Test Template

**Template for Repository Interface and In-Memory Test Double:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class {Resource}Repository(ABC):
    """Abstract boundary for {resource} persistence."""

    @abstractmethod
    def save(self, {resource}: "{Resource}") -> "{Resource}": ...

    @abstractmethod
    def find_by_id(self, resource_id: str) -> "{Resource} | None": ...

    @abstractmethod
    def find_all(
        self, *, page: int = 1, page_size: int = 20
    ) -> tuple[list["{Resource}"], int]: ...

    @abstractmethod
    def delete(self, {resource}: "{Resource}") -> None: ...


@dataclass
class InMemory{Resource}Repository({Resource}Repository):
    """Deterministic test double for {resource} persistence."""

    saved_items: list["{Resource}"] = field(default_factory=list)

    def save(self, {resource}: "{Resource}") -> "{Resource}":
        # Update if exists, otherwise append
        self.saved_items = [
            item for item in self.saved_items if item.id != {resource}.id
        ]
        self.saved_items.append({resource})
        return {resource}

    def find_by_id(self, resource_id: str) -> "{Resource} | None":
        return next(
            (item for item in self.saved_items if item.id == resource_id), None
        )

    def find_all(
        self, *, page: int = 1, page_size: int = 20
    ) -> tuple[list["{Resource}"], int]:
        total = len(self.saved_items)
        start = (page - 1) * page_size
        end = start + page_size
        return self.saved_items[start:end], total

    def delete(self, {resource}: "{Resource}") -> None:
        self.saved_items = [
            item for item in self.saved_items if item.id != {resource}.id
        ]
```

**Template for SQLAlchemy Repository Integration Test:**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def db_session() -> Session:
    """Create an in-memory SQLite session for integration tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


class TestSqlAlchemy{Resource}Repository:
    """Integration tests for the SQL-backed {resource} repository."""

    def test_save_and_retrieve_{resource}(self, db_session: Session) -> None:
        # GIVEN
        repo = SqlAlchemy{Resource}Repository(session=db_session)
        {resource} = given_{resource}(id=None)

        # WHEN
        saved = repo.save({resource})
        db_session.flush()

        # THEN
        found = repo.find_by_id(saved.id)
        assert found is not None
        assert found.name == {resource}.name

    def test_find_by_id_when_not_exists_returns_none(
        self, db_session: Session
    ) -> None:
        # GIVEN
        repo = SqlAlchemy{Resource}Repository(session=db_session)

        # WHEN
        result = repo.find_by_id("nonexistent")

        # THEN
        assert result is None

    def test_delete_removes_{resource}(self, db_session: Session) -> None:
        # GIVEN
        repo = SqlAlchemy{Resource}Repository(session=db_session)
        {resource} = given_{resource}(id=None)
        saved = repo.save({resource})
        db_session.flush()

        # WHEN
        repo.delete(saved)
        db_session.flush()

        # THEN
        assert repo.find_by_id(saved.id) is None
```

**Binding Rules:**
- Repository boundary MUST be an abstract interface (ABC), not a concrete implementation.
- Test doubles MUST be deterministic and side-effect-free (InMemory implementation).
- Integration tests MUST use isolated database sessions (in-memory SQLite or test containers).
- Integration tests MUST flush before assertions to ensure persistence is exercised.
- Repository tests MUST test CRUD operations and constraint violations.

---

### 15.5 Pytest Fixtures Template

**Template for conftest.py shared fixtures:**

```python
import pytest
from datetime import datetime, timezone

FIXED_TIME = datetime(2026, 1, 31, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fake_clock() -> FakeClock:
    """Provide a deterministic clock fixed to FIXED_TIME."""
    return FakeClock(fixed_time=FIXED_TIME)


@pytest.fixture
def fake_repository() -> "InMemory{Resource}Repository":
    """Provide an empty in-memory repository."""
    return InMemory{Resource}Repository()


@pytest.fixture
def {resource}_service(
    fake_clock: FakeClock, fake_repository: "InMemory{Resource}Repository"
) -> "{Resource}Service":
    """Provide a fully-wired service with deterministic dependencies."""
    return {Resource}Service(repository=fake_repository, clock=fake_clock)


@pytest.fixture
def client(mock_service: MagicMock) -> TestClient:
    """Provide a TestClient with mocked service dependency."""
    app.dependency_overrides[get_{resource}_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def mock_service() -> MagicMock:
    """Provide a mock service for handler integration tests."""
    return MagicMock(spec={Resource}Service)
```

**Binding Rules:**
- Fixtures MUST be in `conftest.py` (pytest convention for shared fixtures).
- Fixtures MUST provide deterministic dependencies (fake clock, in-memory repos).
- Fixtures MUST NOT use production databases or external services.
- Fixture teardown MUST clean up dependency overrides (`app.dependency_overrides.clear()`).

---

## 16. BUSINESS LOGIC PLACEMENT GUIDE (Binding)

### 16.1 Decision Tree: WHERE to place business logic?

```
QUESTION: Where should I put this business logic?

START
  |
IS logic specific to ONE domain entity?
  |-- YES -> Domain model method (Rich Domain)
  |           Example: item.validate()
  |           Example: order.calculate_total()
  |           Example: user.activate()
  |
  +-- NO -+
          |
          IS logic a PURE FUNCTION (no state, no side-effects)?
          |-- YES -> Module-level function or static method
          |           Example: calculate_tax(amount, region)
          |           Example: parse_date_range(raw_input)
          |
          +-- NO -+
                  |
                  DOES logic orchestrate MULTIPLE entities/aggregates?
                  |-- YES -> Service (use case)
                  |           Example: order_service.checkout(order, payment)
                  |           Example: user_service.transfer_ownership(from_user, to_user)
                  |
                  +-- NO -> ASK USER
                           (unclear responsibility)
```

**Binding Rule:**
When generating code, the assistant MUST follow this decision tree and document the placement decision in the plan/response.

---

### 16.2 Examples: Correct vs. Wrong

#### Example 1: Can user be deleted?

**BAD (Service has the logic):**

```python
@dataclass
class UserService:
    repository: "UserRepository"
    clock: "ClockPort"

    def delete_user(self, user_id: str) -> None:
        user = self.repository.find_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        # BAD: Business logic in service
        if user.active_contracts:
            raise BusinessError("User has active contracts")

        self.repository.delete(user)
```

**GOOD (Domain model has the logic):**

```python
@dataclass
class User:
    # ...

    def validate_can_be_deleted(self) -> None:
        # GOOD: Business logic in domain model
        if self.active_contracts:
            raise BusinessError("User has active contracts")


@dataclass
class UserService:
    repository: "UserRepository"
    clock: "ClockPort"

    def delete_user(self, user_id: str) -> None:
        user = self.repository.find_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        user.validate_can_be_deleted()  # GOOD: Delegate to domain
        self.repository.delete(user)
```

---

#### Example 2: Calculate order total

**BAD (Handler has the logic):**

```python
@router.get("/orders/{order_id}/total")
def calculate_total(
    order_id: str,
    service: "OrderService" = Depends(get_order_service),
) -> TotalResponse:
    order = service.find_by_id(order_id)

    # BAD: Business logic in handler
    total = sum(item.price * item.quantity for item in order.items)

    return TotalResponse(total=total)
```

**GOOD (Domain model has the logic):**

```python
@dataclass
class Order:
    items: list["OrderItem"]

    def calculate_total(self) -> Decimal:
        # GOOD: Business logic in domain model
        return sum(
            (item.line_total() for item in self.items),
            start=Decimal("0"),
        )


@router.get("/orders/{order_id}/total")
def calculate_total(
    order_id: str,
    service: "OrderService" = Depends(get_order_service),
) -> TotalResponse:
    order = service.find_by_id(order_id)
    total = order.calculate_total()  # GOOD: Delegate to domain
    return TotalResponse(total=total)
```

---

#### Example 3: Transfer ownership (multiple aggregates)

**GOOD (Service orchestrates):**

```python
@dataclass
class UserService:
    user_repository: "UserRepository"
    resource_repository: "ResourceRepository"
    clock: "ClockPort"

    def transfer_ownership(self, from_user_id: str, to_user_id: str) -> None:
        # GOOD: Service orchestrates multiple aggregates
        from_user = self.user_repository.find_by_id(from_user_id)
        to_user = self.user_repository.find_by_id(to_user_id)

        if from_user is None or to_user is None:
            raise UserNotFoundError(from_user_id if from_user is None else to_user_id)

        # Validation on domain models
        from_user.validate_can_transfer_ownership()
        to_user.validate_can_receive_ownership()

        # Orchestration in service
        resources = self.resource_repository.find_by_owner_id(from_user_id)
        for resource in resources:
            resource.set_owner(to_user)

        self.resource_repository.save_all(resources)
```

---

### 16.3 Quick Reference Table

| Logic Type | Location | Example |
|-----------|----------|---------|
| Single entity validation | Domain model method | `user.validate()` |
| Single entity calculation | Domain model method | `order.calculate_total()` |
| Single entity state change | Domain model method | `user.activate()` |
| Pure function (no state) | Module-level function | `calculate_tax(amount, region)` |
| Multi-aggregate orchestration | Service | `order_service.checkout()` |
| External system call | Service | `payment_service.charge()` |
| HTTP/validation/mapping | Handler | `@router.post(...)` |

---

## 17. INTEGRATION CHECKLIST

To ensure LLMs generate optimal Python code, verify:

### Code Generation
- Handler follows template (Section 14.1) with all CRUD variations
- Service follows template (Section 14.2) with deterministic seams
- Domain model follows template (Section 14.3) with invariant enforcement
- Error handling follows template (Section 14.4) with stable error codes
- Placeholders substituted correctly (Section 14.5)

### Test Generation
- Test data builders used (Section 15.1) with `FIXED_TIME` and `given_{resource}()`
- Service tests follow template (Section 15.2) with GIVEN/WHEN/THEN
- Handler tests follow template (Section 15.3) with TestClient
- Repository tests follow template (Section 15.4) with isolated sessions
- Pytest fixtures centralized in conftest.py (Section 15.5)

### Architecture
- Business logic placement correct (Section 16.1 decision tree)
- No logic in handlers (only delegate)
- Clock injected (no `datetime.now()`)
- Tests deterministic (`FIXED_TIME`)
- Repository boundary is abstract (ABC)

---

## 18. APPENDIX: WHY TEMPLATES MATTER

### LLM Behavior Analysis

**Without Templates (Abstract Rules):**
```
Prompt: "Create a REST endpoint for User creation"

LLM reads: "Handlers should validate and delegate"

LLM generates:
- Variation 1: Manual validation in handler
- Variation 2: Service validates
- Variation 3: Domain model validates
-> Inconsistent (different every ticket)
```

**With Templates (Concrete Patterns):**
```
Prompt: "Create a REST endpoint for User creation"

LLM reads: Template 14.1 (Handler Pattern)

LLM generates:
- Always: Pydantic model for request validation
- Always: map_request_to_domain(payload)
- Always: service.create_user(domain_input)
-> Consistent (same every ticket)
```

---

**END OF TEMPLATE ADDON**

---
## Principal Hardening v2 - Python Template Conformance (Binding)

### PTPH2-1 Template conformance gate (binding)

For generated Python business/test code, the workflow MUST verify and record conformance against templates T1-T4 (Sections 14.1-14.4) and test templates (Sections 15.1-15.5).

Minimum conformance checks for changed scope:

- Handler delegates in one call (no business branching in handler/route layer)
- Service uses deterministic seams (clock, repository interfaces)
- Domain model enforces invariants via domain methods (not in handlers or services)
- Repository boundary uses abstract interface pattern (ABC)
- Tests use deterministic setup (fake clock, in-memory repository) and assert behavior over internals
- Error handling uses stable error codes and injected clock for timestamps

If any conformance item fails, principal completion cannot be declared.

### PTPH2-2 Evidence artifact contract (binding)

When templates are used, BuildEvidence MUST include references for:

- `EV-TPL-CODE`: code conformance evidence (path + snippet references)
- `EV-TPL-TEST`: test conformance evidence (path + test names)
- `EV-TPL-GATE`: gate decision evidence (pass/fail with rationale)

Claims without these evidence refs MUST be marked `not-verified`.

### PTPH2-3 High-risk template extensions (binding)

When touched scope includes persistence, security, or async messaging, template usage alone is not sufficient.
The workflow MUST add risk-specific checks and tests (constraints, auth/error semantics, idempotency/retry behavior).

### PTPH2-4 Template deviation protocol (binding)

If repo conventions require deviation from templates, record:

- deviation reason
- preserved architectural intent
- risk impact (`low` | `medium` | `high`)
- compensating test added

Without deviation record, gate result cannot be `pass`.

---

## Examples (GOOD/BAD)

GOOD:
- Service orchestrates use case, injects `ClockPort`, and delegates state mutation to domain methods (`update`, `validate`).

BAD:
- Handler performs business branching and directly mutates domain objects without domain method boundaries.

GOOD:
- Tests use builder functions (`given_user()`) with `FIXED_TIME` and assert behavior/contract outcomes.

BAD:
- Tests depend on `datetime.now()` and brittle mock-based implementation-level verifications.

GOOD:
- Error responses include stable error codes (`USER_NOT_FOUND`) and timestamps from injected clock.

BAD:
- Error handling uses bare `HTTPException(status_code=404)` with no error code and `datetime.now()` for timestamp.

## Troubleshooting

1) Symptom: Generated code violates repo style or framework conventions
- Cause: template applied without adapting to locked repo conventions
- Fix: apply minimal convention-aligned adaptation and record deviation evidence.

2) Symptom: Gate shows determinism risk for changed tests
- Cause: uncontrolled time/randomness/order assumptions in tests
- Fix: inject deterministic seams (`FakeClock`, fixed IDs/order) and remove timing sleeps.

3) Symptom: Review flags domain mutation drift (direct attribute assignment)
- Cause: template adaptation reintroduced setter-based domain writes
- Fix: restore domain-method mutation pattern and keep critical fields mutation-free from outside.

4) Symptom: Handler contains business logic
- Cause: validation or calculation was placed in handler instead of domain/service
- Fix: move logic to appropriate layer per Section 16.1 decision tree.

5) Symptom: Tests are brittle and break on refactoring
- Cause: tests assert on implementation details (mock call counts, internal state)
- Fix: restructure tests to assert on behavioral outcomes (return values, side effects on fakes).

---

Copyright (c) 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
