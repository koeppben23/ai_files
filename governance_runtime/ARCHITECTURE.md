# Governance Runtime — Architektur-Dokumentation

**Version:** 1.0.0  
**Status:** Stabil  
**Letzte Aktualisierung:** 2026-03-22

---

## Überblick

Die Governance Runtime ist ein zustandsbasierter Workflow-Orchestrator für OpenCode-Projekte. Er implementiert ein Phasenmodell (Bootstrap → Intake → Architecture → Review → Implementation → Delivery).

## Kernarchitektur

### State Management

```
┌─────────────────────────────────────────────────────────────┐
│                     SESSION_STATE.json                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 state_normalizer.py                         │
│                 (PRIMÄRE ALIAS-QUELLE)                     │
│                                                             │
│  Kanonisiert Legacy-Aliases:                               │
│  - Phase ↔ phase                                           │
│  - Next ↔ next                                             │
│  - WorkflowComplete ↔ workflow_complete                     │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  state_accessor  │ │  transition_    │ │  state_document │
│  .py             │ │  model.py       │ │  _validator.py  │
│                 │ │                 │ │                 │
│ Access-Layer    │ │ Next-Action     │ │ Fail-Closed    │
│ für Entrypoints │ │ Resolver        │ │ Validierung    │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Schichtenarchitektur

| Layer | Verantwortung | Key-Module |
|-------|--------------|------------|
| **Domain** | Geschäftslogik, Gate-Evaluatoren | `gate_evaluator.py`, `phase_state_machine.py` |
| **Application** | Services, Use-Cases | `state_normalizer.py`, `state_accessor.py`, `transition_model.py` |
| **Engine** | Workflow-Orchestrierung | `next_action_resolver.py`, `session_state_invariants.py` |
| **Kernel** | Phasen-Kernel | `phase_kernel.py` |
| **Infrastructure** | I/O, Persistenz, Rendering | `json_store.py`, `snapshot_renderer.py` |
| **Entrypoints** | CLI/API-Schnittstellen | `session_reader.py`, `*_persist.py` |

## Zustandsmodell

### Kanonische Felder

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `phase` | str | Aktuelle Phase (z.B. "6-PostFlight") |
| `next` | str | Nächste Phase (z.B. "5", "6") |
| `active_gate` | str | Aktives Gate |
| `status` | str | Session-Status |
| `mode` | str | Betriebsmodus |
| `Gates` | dict | Gate-Status-Map |

### Alias-Auflösung

**Regel:** Alias-Auflösung NUR in `state_normalizer.py`.

Zulässige Aliases:
- `Phase` ↔ `phase`
- `Next` ↔ `next`
- `WorkflowComplete` ↔ `workflow_complete`
- `Phase5State` ↔ `phase5_state`

## Validierung

### Fail-Closed Policy

```python
validate_state_document(state_doc)  # Wirft bei ungültigem State
validate_review_payload(payload)    # Wirft bei ungültigem Review
validate_plan_payload(payload)      # Wirft bei ungültigem Plan
```

### Übergangsmodell

`transition_model.py` definiert alle gültigen Übergänge:
- Guard-Funktionen prüfen Preconditions
- Next-Action wird explizit berechnet
- Keine impliziten Fallbacks

## Profile Resolution

### Operating Profile Hierarchy

```
solo (1) < team (2) < regulated (3)
```

Profile sind monoton: Ein höheres Profil ist strenger und kann nicht auf ein niedrigeres zurückgestuft werden (außer mit Break-Glass).

### Runtime Mode Mapping

| Profile | Runtime Mode | Bootstrap Flag | Auto-Approve | CI Signal |
|---------|-------------|---------------|--------------|----------|
| solo | user | `--profile solo` | No | - |
| team | pipeline | `--profile team` | Yes (at Evidence Gate) | CI=true |
| regulated | agents_strict | `--profile regulated` | No | Must not collapse to pipeline |

**Wichtig:** CI alone does not erase regulated semantics. A repo initialized with `--profile regulated` maintains `agents_strict` mode even in CI pipelines. Pipeline auto-approve does NOT apply to regulated/agents_strict mode.

### Regulated Mode Activation

When `--profile regulated` is specified during bootstrap:

1. `.opencode/governance-repo-policy.json` is created with `operatingMode: "regulated"`
2. `governance-mode.json` is created at repo root with `state: "active"`
3. `detect_regulated_mode()` reads `governance-mode.json` to enforce constraints:
   - Retention lock (framework-specific minimum retention)
   - Four-eyes approval for archive operations
   - Immutable archives
   - Tamper-evident export

### Pipeline Auto-Approve (Team Profile)

The team profile (`--profile team`) enables non-interactive auto-approve at the Evidence Presentation Gate.

**Eligibility Conditions (ALL must be true):**
- `effective_operating_mode == "pipeline"`
- Internal review is complete
- At Evidence Presentation Gate
- No existing review decision recorded
- Workflow not already complete

**How it works:**
1. Kernel evaluates transition eligibility via `pipeline_auto_approve_eligible()`
2. When eligible, kernel signals `source="pipeline-auto-approve"`
3. `session_reader._materialize_authoritative_state()` consumes the signal
4. `apply_review_decision(decision="")` is called automatically
5. Workflow completes without manual intervention

**Important:**
- Pipeline auto-approve only applies to team/pipeline mode
- Regulated/agents_strict mode does NOT support pipeline auto-approve
- Solo/user mode requires explicit `/review-decision`

### Governance Configuration (governance-config.json)

The `governance-config.json` file at workspace root provides policy knobs for governance behavior.

**Location:** `<workspace>/governance-config.json`

**Configuration Sections:**
- `review`: Review iteration limits (phase5_max_review_iterations, phase6_max_review_iterations)
- `pipeline`: Pipeline mode settings (allow_pipeline_mode, auto_approve_enabled)
- `regulated`: Regulated mode settings (allow_auto_approve, require_governance_mode_active)

**Behavior:**
- File missing → use defaults (backward compatible)
- File present + valid → use loaded values
- File present + invalid → fail-closed (RuntimeError)

**See Also:** `GOVERNANCE_CONFIG.md` for full documentation.

### Profile vs Runtime Mode vs CI Environment

- **Profile**: Bootstrap-Konfiguration (solo, team, regulated)
- **Runtime Mode**: Effektiver Modus für Logik (user, pipeline, agents_strict)
- **CI Environment**: Kann Pipeline-Modus aktivieren, aber nicht regulated downgraden

## Allowlist

**31 Allowlist-Einträge** für Alias-Zugriff (Stand: Sprint K/M).

### Permanent legitim

- `state_normalizer.py` — PRIMÄR (einzige Alias-Quelle)
- `orchestrator.py`, `phase5_normalizer.py`, `state_accessor.py`, `policy_resolver.py`, `transition_model.py` — MIGRATED
- `state_document_validator.py` — SCHEMA
- `session_state_invariants.py`, `phase_kernel.py` — ENGINE/KERNEL
- 5 INFRA-Files

### Review/Migration erforderlich

- 10 ENTRYPOINT-Files
- 5 OTHER-Files

## Services

### plan_reader.py

Dedizierter Service für das Lesen von Plan-Content:

```python
from governance_runtime.application.services.plan_reader import read_plan_body

body = read_plan_body(session_path, json_loader=_read_json)
```

Enthält Legacy-Kompatibilität für `body`/`planBody`/`plan_body` Felder.

## Performance

| Operation | Latenz |
|-----------|--------|
| `normalize_to_canonical()` | ~7µs |
| Zustandsvalidierung | <1ms |

## Testing

```bash
# Architektur-Tests
pytest tests/architecture/

# Unit-Tests
pytest tests/unit/test_state_normalizer.py
pytest tests/unit/test_state_accessor.py
pytest tests/unit/test_transition_model.py
pytest tests/unit/test_state_document_validator.py

# Integration
pytest tests/integration/
```

## Changelog

### v1.0.0 (2026-03-22)

- Sprint A-L abgeschlossen
- Kanonisches State-Modell etabliert
- state_normalizer als PRIMÄRE Alias-Quelle
- state_accessor als Access-Layer
- state_document_validator für Fail-Closed-Validierung
- legacy_compat.py entfernt
- plan_reader.py als dedizierter Service
- Performance: ~7µs pro Normalisierung

---

## Entwicklung

### Neue Features

1. Alias-Auflösung NUR in `state_normalizer.py`
2.state_accessor für Entrypoints verwenden
3. state_document_validator für Fail-Closed-Validierung

### Architektur-Regeln

1. **Alias-Auflösung** → nur in `state_normalizer.py`
2. **Raw State** → nur in ENGINE/KERNEL/INFRA
3. **Validierung** → fail-closed an kritischen Grenzen
4. **Übergänge** → explizit in `transition_model.py`
