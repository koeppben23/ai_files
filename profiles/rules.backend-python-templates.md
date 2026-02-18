## Intent (binding)

Provide deterministic backend-python templates so assistant-generated code/tests stay reviewable, boundary-safe, and reproducible.

## Scope (binding)

Python template patterns for API handlers, services/use-cases, repository boundaries, and deterministic test scaffolding.

## Activation (binding)

Addon class: `required`.

This addon MUST be loaded at code-phase (Phase 4+) when `SESSION_STATE.ActiveProfile = "backend-python"`.
- Missing-addon handling MUST follow canonical required-addon policy from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`.
- This rulebook MUST NOT redefine blocking semantics.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This required addon refines template defaults and MUST NOT override `master.md`, `rules.md`, or `rules.backend-python.md` constraints.

## Phase integration (binding)

- Phase 2: discover python runtime/build/test conventions and capture deterministic seams.
- Phase 4: apply template defaults for changed scope and record only minimal convention-aligned deviations.
- Phase 5.3: verify template-derived quality claims with concrete evidence.

## Evidence contract (binding)

- Record template load/evidence in `SESSION_STATE.LoadedRulebooks.templates` and `SESSION_STATE.RulebookLoadEvidence.templates`.
- Template-derived gate claims MUST reference `SESSION_STATE.BuildEvidence.items[]` identifiers.
- Missing evidence MUST remain `NOT_VERIFIED`.

## Shared Principal Governance Contracts (Binding)

To keep this addon focused on backend-python template mechanics, shared principal governance contracts are modularized into advisory rulebooks:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior for this addon:

- At code/review phases (Phase 4+), these shared contracts MUST be loaded as advisory governance contracts.
- If one shared rulebook is unavailable, emit warning, keep affected claims `not-verified`, and continue conservatively.

## Tooling (recommended)

- Prefer repo-native Python commands and lockfile-aware invocation (`pytest`, `ruff`, `mypy`, `uv`, `poetry`, `pip-tools`, `alembic`).
- Preserve deterministic command order (lint -> type -> targeted tests -> full tests).
- If host cannot run required tooling, emit one concrete recovery command and keep affected claims `NOT_VERIFIED`.

## Correctness by construction (binding)

Inputs required:
- endpoint/use-case name and module path
- boundary contract context (request/response/domain mapping)
- persistence boundary expectations

Outputs guaranteed:
- handler/service/repository/test scaffolds for changed scope
- explicit deterministic seams for time/random/external side effects
- explicit DTO/domain mapping boundaries

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

## Examples (GOOD/BAD)

GOOD:
- Template-generated endpoint keeps request validation, mapping, and delegation clearly separated.

BAD:
- Business branching is embedded in transport/controller/route layer.

## Troubleshooting

- Missing template evidence: run deterministic lint/type/test commands and ingest evidence IDs.
- Host constraint/tool unavailable: emit one actionable recovery command and keep claim `NOT_VERIFIED`.
- Repo convention mismatch: apply minimal adaptation and record deviation rationale.

---

## T1. API Handler Template

```python
from pydantic import BaseModel
from fastapi import APIRouter, Depends, status

router = APIRouter()


class CreateItemRequest(BaseModel):
    name: str


class ItemResponse(BaseModel):
    id: str
    name: str


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(payload: CreateItemRequest, service: "ItemService" = Depends("item_service_provider")) -> ItemResponse:
    domain_input = map_request_to_domain(payload)
    result = service.create_item(domain_input)
    return map_domain_to_response(result)
```

Binding rules:
- Handler MUST not contain business branching.
- Transport/domain mapping MUST be explicit.

## T2. Service Template

```python
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ItemService:
    repository: "ItemRepository"
    clock: "ClockPort"

    def create_item(self, command: "CreateItemCommand") -> "Item":
        now = self.clock.now_utc()
        item = Item.create(name=command.name, created_at=now)
        return self.repository.save(item)
```

Binding rules:
- Service MUST inject deterministic seams (`clock`, repositories).
- Service MUST keep business decisions in domain/service, not in handler.

## T3. Deterministic Unit-Test Template

```python
def test_create_item_persists_domain_entity(fake_clock, fake_repository):
    service = ItemService(repository=fake_repository, clock=fake_clock)

    created = service.create_item(CreateItemCommand(name="alpha"))

    assert created.name == "alpha"
    assert fake_repository.saved_items == [created]
```

Binding rules:
- Assert behavior/outcome, not implementation internals.
- Avoid timing/network nondeterminism unless explicitly controlled.
