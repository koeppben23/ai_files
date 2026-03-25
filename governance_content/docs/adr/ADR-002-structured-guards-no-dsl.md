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

Aktueller Legacy-Restpfad ist deaktiviert (empty allowlist):

- `LEGACY_TRANSITION_GUARD_EVENTS = {}`

Zusätzlich sichern Architekturtests die Abdeckung:

- `test_all_phase_api_transition_events_are_guarded_or_explicit_legacy`
- `test_phase6_topology_events_are_guarded_or_default`
- `test_execute_non_allowlisted_legacy_event_does_not_bypass_default`

`implementation_presentation_ready` ist jetzt deklarativ in `guards.yaml` modelliert.

### Guard-State Bridge (_build_guard_evaluation_state)

Die Funktion bleibt eine notwendige Bridge zwischen SESSION_STATE und GuardEvaluator,
ist aber auf deterministische, nachvollziehbare Ableitungen begrenzt.

| Feld(gruppe) | Typ | Quelle / Regel |
|---|---|---|
| `active_gate`, `phase6_state`, `workflow_complete`, `rework_clarification_consumed` | canonical | Nur aus Input-State übernommen (keine Erfindung) |
| `user_review_decision` | derived (strict) | Nur aus validen Entscheidungen (`approve`, `changes_requested`, `reject`) |
| `plan_record_versions`, `phase5_self_review_iterations`, `ImplementationReview.revision_complete` | derived | Deterministische Ableitung aus vorhandenem State + `plan_record_versions` |
| `technical_debt_proposed`, `rollback_required`, `ticket_recorded` | legacy-bridge | Explizite Normalisierung historischer Alias-/Strukturformen |
| `implementation_*` Statusfelder | canonical-first | Keine Rekonstruktion mehr aus Gate-Text; nur explizite Status-/Flag-Felder |

Nicht mehr zulässig:

- Neue hardcoded Guard-Branches (`if event == ...`) außerhalb von `guards.yaml`
- Neue stille Legacy-Fallbacks für unbekannte Transition-Events

## Abschlusszustand (WP6)

Autoritative Quellen:

- `command_policy.yaml` (Command-Zulässigkeit)
- `topology.yaml` (Zielzustände / Transition-Struktur)
- `guards.yaml` (Event-Guard-Semantik)
- `SpecRegistry` (zentraler, fail-closed Spec-Zugriff)

Bewusste Restschuld:

- `_build_guard_evaluation_state(...)` bleibt als beobachtete Bridge erhalten,
  mit Invariant-Tests und Feldmatrix gegen Drift.

Nicht mehr erlaubt:

- Neue hardcoded Transition-/Guard-Wahrheit im Kernel
- Stille Fallbacks an kritischen Guard-/Topology-Boundaries

## Addendum (WP7 Slice 1)

Phase-5 Plan-Ausgaben sind jetzt sprachlich und strukturell gehärtet:

- `planOutputSchema` erzwingt `language = "en"` (fail-closed).
- Ein deterministischer `presentation_contract` ist verpflichtender Bestandteil
  der Planstruktur (Titel, Decision-Block, Summary, Risiken, Next Actions).
- `next_actions` ist auf genau drei finale Rails begrenzt:
  - `/review-decision approve`
  - `/review-decision changes_requested`
  - `/review-decision reject`
- Offensichtlich nicht-englische Pflichtfelder werden im Plan-Parser vor Persist
  blockiert (`plan-language-violation`), statt still übernommen zu werden.

Dadurch bleibt Phase-5-Ausgabe deterministisch, reviewbar und ohne sprachliche Drift.
