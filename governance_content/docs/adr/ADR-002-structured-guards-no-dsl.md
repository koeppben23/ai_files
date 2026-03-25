# ADR-002: Strukturierte Guards, keine String-DSL

**Status:** Accepted  
**Date:** 2026-03-24  
**Decision Makers:** Architecture Team  
**Related:** guards.yaml

## Context

Guard-Bedingungen könnten als String-DSL formuliert werden:
```yaml
condition: "ticket_intake_ready == true OR task_present == true"
```

Das birgt Risiken:
- Parser-/Interpretationskomplexität
- Debugging-Aufwand
- Implizite Typprobleme
- Zweite Semantik neben Python

## Decision

**Guards verwenden strukturierte deklarative Syntax ohne String-DSL:**

```yaml
condition:
  any_of:
    - key_equals: { key: "ticket_intake_ready", value: true }
    - key_present: "task_present"
```

### Erlaubte Condition-Typen

| Typ | Syntax | Beschreibung |
|-----|--------|--------------|
| `all_of` | `all_of: [...]` | Alle Sub-Bedingungen erfüllt (AND) |
| `any_of` | `any_of: [...]` | Mind. eine Sub-Bedingung erfüllt (OR) |
| `key_present` | `key_present: "key_name"` | Key existiert in State |
| `key_equals` | `key_equals: { key: "x", value: <any> }` | Key hat bestimmten Wert |
| `numeric_gte` | `numeric_gte: { field: "x", threshold: <int\|from_state> }` | Numerisch größer gleich |
| `state_flag` | `state_flag: { flag: "x" }` | Boolean Flag ist true |

### Jede Guard ist verpflichtend

```yaml
g.example:
  description: "Beschreibung ist Pflicht"    # PFICHT
  fail_mode: "block"                          # PFICHT
  error_code: "GUARD_MISSING_REQUIRED_KEY"    # optional (stabiles Schema)
  priority: 50                                # optional
  condition:                                   # PFICHT
    key_present: "required_key"
```

## Consequences

- Kein Parser notwendig
- Eine Semantik (Python), nicht zwei
- Debugging ist klar und nachvollziehbar
- Guard-Validierung ist deterministisch

## Alternatives Considered

| Alternative | Warum verworfen |
|-------------|-----------------|
| String-DSL | Zu komplexe Fehlerbehandlung, schwer zu debuggen |
| Nur guard_ref → Python | Keine Struktur in YAML, schwer zu validieren |
| Gemischt (DSL + Python) | Zwei Semantiken, konsistenz-riskant |

## Addendum (WP4/WP5)

Die Runtime nutzt Guards evaluator-first:

- Phase-6 topology-authoritativer Pfad: GuardEvaluator bestimmt das Event, Topology den Zielzustand.
- Nicht-Phase-6 Pfad: GuardEvaluator zuerst, dann eng begrenzter Legacy-Restpfad.

Aktueller Legacy-Restpfad ist absichtlich minimal und explizit allowlist-basiert:

- `implementation_presentation_ready`

Zusätzlich sichern Architekturtests die Abdeckung:

- `test_all_phase_api_transition_events_are_guarded_or_explicit_legacy`
- `test_phase6_topology_events_are_guarded_or_default`
- `test_execute_non_allowlisted_legacy_event_does_not_bypass_default`

Restschuld (explizit):

- Der Legacy-Restpfad `implementation_presentation_ready` bleibt bewusst allowlisted,
  bis die verbleibende Übergangssemantik vollständig in `guards.yaml` modelliert ist.

Damit wird Doppelwahrheit reduziert und neue nicht-modellierte Guard-Events werden fail-safe blockiert, statt still im Legacy-Pfad zu laufen.
