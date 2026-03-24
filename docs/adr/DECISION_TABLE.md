# Entscheidungstabelle: Architektur-Freeze Phase 0

**Status:** Frozen  
**Date:** 2026-03-24  
**Scope:** State-Machine Refactoring v2

## Zusammenfassung

Diese Tabelle dokumentiert alle expliziten Architekturentscheidungen, die vor Implementierung getroffen werden müssen. Jede Entscheidung ist binär oder hat eine klare Ziellösung.

---

## 1. Topologie-Struktur

| Entscheidung | Ziellösung | Begründung | ADR |
|-------------|------------|------------|-----|
| Enthält Topologie UX-Texte? | **NEIN** - nur Struktur | Zweite Wahrheit vermeiden | ADR-001 |
| `active_gate` in Topologie? | **VERBOTEN** | Gehört in Messages | ADR-001 |
| `next_gate_condition` in Topologie? | **VERBOTEN** | Gehört in Messages | ADR-001 |
| `description` in State? | **VERBOTEN** | Nur ids, parent, is_terminal | ADR-001 |
| `parent` in State? | **ERLAUBT** (informativ nur) | Nicht für Resolution | ADR-001 |

## 2. Guard-Syntax

| Entscheidung | Ziellösung | Begründung | ADR |
|-------------|------------|------------|-----|
| String-DSL für Conditions? | **NEIN** - nur strukturiert | Eine Semantik, kein Parser | ADR-002 |
| `description` in Guard? | **PFICHT** | Debugging, Audit | ADR-002 |
| `fail_mode` in Guard? | **PFICHT** | `block` oder `fail_closed` | ADR-002 |
| `error_code` in Guard? | **OPTIONAL** | Für strukturierte Fehler | ADR-002 |
| `priority` in Guard? | **OPTIONAL** (int, höher=wichtiger) | Konfliktlösung | ADR-002 |
| Erlaubte Condition-Typen | `all_of`, `any_of`, `key_present`, `key_equals`, `numeric_gte`, `state_flag` | Strukturiert, kein String | ADR-002 |

## 3. Phase 6 Substates

| Entscheidung | Ziellösung | Begründung | ADR |
|-------------|------------|------------|-----|
| Phase 6 = ein Token? | **NEIN** - explizite Substates | Wartbarkeit, Klarheit | ADR-003 |
| Approval-Zustand? | **JA** - `6.approved` | Auditierbarkeit | ADR-003 |
| `/implement` aus `6.presentation`? | **NEIN** - blockiert | Erst Approval nötig | ADR-003 |
| `/implement` aus `6.approved`? | **JA** - erlaubt | Klare Trennung | ADR-003 |
| Reihenfolge | `6.presentation` → approve → `6.approved` → `/implement` → `6.execution` | Deterministisch | ADR-003 |

## 4. Command → Event

| Entscheidung | Ziellösung | Begründung | ADR |
|-------------|------------|------------|-----|
| Commands = Events? | **NEIN** - unterschiedliche Klassen | Klarheit, Audit | ADR-004 |
| Mapping in YAML? | **JA** - `command_policy.yaml` | Maschinenlesbar | ADR-004 |
| Mapping testbar? | **JA** - explizite Tests | Konformität | ADR-004 |
| `/continue` Mapping | `determined_by_state` | Spezialfall, explizit | ADR-004 |
| Read-only Commands | `event_mapping: null` | Kein Event erzeugt | ADR-004 |
| System-Events distinguised? | **JA** - `is_system_event()` | Kernel vs. User | ADR-004 |

## 5. Audit-Events

| Entscheidung | Ziellösung | Begründung | ADR |
|-------------|------------|------------|-----|
| Audit-Events First-Class? | **JA** - eigener Workstream | Governance erfordert Audit | ADR-005 |
| Outcome: nur `success/blocked/failed`? | **NEIN** - feiner differenziert | Präzise Analyse | ADR-005 |
| Outcomes | `success`, `blocked_missing_evidence`, `rejected_by_policy`, `failed_system_error` | Klar getrennt | ADR-005 |
| Event-Schema | Strukturiert (dataclass) | Maschinenlesbar | ADR-005 |
| Event pro Aktion? | **JA** | Nachvollziehbarkeit | ADR-005 |

## 6. ID-Schema

| Entscheidung | Ziellösung | Begründung | ADR |
|-------------|------------|------------|-----|
| ID-Format | `{entity}.{qualifier}` oder `{parent}.{qualifier}` | Stabil, lesbar | ADR-006 |
| State-IDs technisch? | **JA** - Runtime-IDs stabil | Revisionssicher | ADR-006 |
| `start_token` | **`start_state_id`** | Semantisch sauberer | ADR-006 |
| Display-Trennung | Optional (nicht für V1) | Erweiterbar | ADR-006 |
| ID-Uniqueness validiert? | **JA** - Loader prüft | Fail-closed | ADR-006 |

## 7. Kompatibilität und Migration

| Entscheidung | Ziellösung | Begründung |
|-------------|------------|------------|
| Neue Spec Dateien | `machine_topology.yaml`, `guards.yaml`, `command_policy.yaml`, `messages.yaml` | Klare Trennung |
| Alte `phase_api.yaml` | Parallel bis Release 12 | Kein Big Bang |
| Kompatibilitätsdauer | Bis Release-12-Checkliste komplett | Kontrollierter Cutover |
| Golden-Flow-Messung | State-Transition-Trace | Deterministisch vergleichbar |

## 8. Performance

| Entscheidung | Ziellösung | CI Guardrail | Local Goal |
|-------------|------------|--------------|------------|
| Spec-Load Budget | Unter Schwellwert | < 200ms | < 50ms |
| Transition-Resolve Budget | Unter Schwellwert | < 50ms | < 10ms |
| ExecutionContext Budget | Unter Schwellwert | < 500ms | < 100ms |
| Config/State Doppelload | Keine pro Run | Max 1 pro Typ | 1 pro Typ |
| Regression Alert | > 50% slower | Fail | Warn |

## 9. /continue Einschränkung

| Entscheidung | Ziellösung | Begründung |
|-------------|------------|------------|
| /continue = Super-Command? | **NEIN** - strikt deterministisch | Versteckte Mutationen vermeiden |
| Events pro State definiert? | **JA** - `allowed_events_per_state` | Klarheit |
| Block bei Ambiguität? | **JA** - `blocking_on_ambiguity: true` | Fail-closed |
| Hidden Mutation verboten? | **JA** - `never_hidden_mutation: true` | Sicherheit |

## 10. Teststrategie

| Test-Kategorie | Enthalten | Pflicht |
|---------------|-----------|---------|
| Happy Path | Ja | Ja |
| Bad/Negative Path | Ja | Ja |
| Corner Cases | Ja | Ja |
| Edge Cases | Ja | Ja |
| Conformance | Ja | Ja |
| Regression | Ja | Ja |
| Metamorphic | Ja | Ja |
| Model-based | Ja (seeded + adversarial) | Ja |
| Performance SLO | CI guardrails + local goals | Ja |
| Golden Flow Equivalenz | Ja | Ja |

## Offene Entscheidungen vor Start

| # | Entscheidung | Empfehlung | Status |
|---|--------------|------------|--------|
| 1 | CI Guardrail-Werte finalisieren | 200/50/500ms | **Offen** |
| 2 | Adversarial Test-Seeds definieren | Feste Corpora | **Offen** |
| 3 | Audit-Event-Sink-Implementierung | Structured Logging | **Offen** |
| 4 | Golden-Flow-Tooling | Trace-Vergleich | **Offen** |

---

**Nächster Schritt:** Scope-Freeze dokumentieren und Phase 1 starten.
