# Scope-Freeze: State-Machine Refactoring v2

**Status:** Frozen  
**Date:** 2026-03-24  
**Effective until:** Release 12 complete

## Scope

Dieses Refactoring betrifft ausschließlich:

1. **State-Machine Topologie** - `machine_topology.yaml`
2. **Guard-/Invariant-Schicht** - `guards.yaml`
3. **Command-Policy** - `command_policy.yaml`
4. **Presentation/Messages** - `messages.yaml`
5. **Runtime-Executor** - `phase_kernel.py`, `execution_context.py`
6. **Audit-Events** - `audit_events.py`
7. **Spec-Validator** - `spec_validator.py`

## Was NICHT im Scope ist

- Änderungen an bestehender Business-Logik
- Neue Features außerhalb der State-Machine
- UI-/CLI-Änderungen (außer Message-Referenzen)
- Persistenzformat-Änderungen

## Änderungskontrolle

| Art | Erlaubt? | Bedingung |
|-----|----------|-----------|
| Neue Guard | Ja | Strukturierte Syntax, beschreibungspflichtig |
| Neue Command | Ja | In `command_policy.yaml` registriert |
| Neue Message | Ja | In `messages.yaml` registriert |
| Neue Transition | Ja | In `machine_topology.yaml`, Guard-Referenz valide |
| UX-Änderung | Ja | Nur in `messages.yaml` |
| Topologie-Änderung | Nur mit Review | Struktur-Änderung erfordert ADR |
| Guard-Syntax-Änderung | Nur mit Review | Neue Condition-Typen erfordern ADR |

## Phase-0-Abnahmekriterien

Phase 0 ist abgeschlossen, wenn:

- [ ] 6 ADRs geschrieben und reviewed
- [ ] Entscheidungstabelle vollständig
- [ ] Alle offenen Entscheidungen sind entweder:
  - Getroffen und dokumentiert, oder
  - Explizit als "offen" markiert mit Empfehlung
- [ ] Scope-Freeze dokumentiert
- [ ] Review-Sitzung stattgefunden

## Abbruchkriterien

Refactoring wird abgebrochen wenn:

- Golden-Flow-Vergleich zeigt unbeabsichtigte Verhaltensänderungen
- Performance-Regression > 100% in Hot-Path
- Test-Coverage fällt unter 90% für geänderte Module
- Doku-Drift超过 2 Wochen unaddressed

---

**Nächster Schritt:** Phase 1 (Ist-Modell inventarisieren)
