# Phase 12: Release-Schnitt

**Status:** Release Ready (with acknowledged debt)  
**Date:** 2026-03-25  
**Version:** 2.0.0

> **HINWEIS:** Dieser Release ist "architecturally stabilized", aber nicht "100% debt-free".
> Einige Restpunkte bleiben und sind unten dokumentiert.

---

## 1. Release-Zusammenfassung

### Was wurde refactored

| Komponente | Vorher | Nachher |
|------------|--------|---------|
| State Machine | Monolith `phase_api.yaml` | 4 separate Specs |
| Topology | Gemischte Struktur + UX | `topology.yaml` (strukturiert) |
| Guards | String-DSL | `guards.yaml` (strukturiert) |
| Commands | Implizit | `command_policy.yaml` (explizit) |
| Messages | Embedded | `messages.yaml` (getrennt) |
| Phase 6 | Single State | 8 Substates |

### Architektur-Entscheidungen

| ADR | Titel | Status |
|-----|-------|--------|
| ADR-001 | Topology ohne UX | ✅ |
| ADR-002 | Strukturierte Guards, kein DSL | ✅ |
| ADR-003 | Phase 6 Approval vor Implementierung | ✅ |
| ADR-004 | Command → Event Mapping | ✅ |
| ADR-005 | Audit Events First-Class | ✅ |
| ADR-006 | Runtime IDs Final | ✅ |
| ADR-007 | Phase 6 Integration Fixes | ✅ |

---

## 2. Neue Spec-Struktur

```
governance_spec/
├── topology.yaml          # State-Machine Topologie
├── guards.yaml            # Guard-Bedingungen
├── command_policy.yaml     # Command → Event Mapping
├── messages.yaml          # Präsentations-Schicht
└── phase_api.yaml         # Legacy (bis Release 12)
```

### Spec-Felder (per ADR-001)

**Struktur (Runtime):** `id`, `terminal`, `transitions`, `parent`

**Allowed Descriptive Metadata:** `description` (never for routing/guards/ranking)

**Verboten:** `active_gate`, `next_gate_condition`, `gate_message`, `instruction`

---

## 3. Phase 6 Substates

```
6.internal_review   # Internal review loop
6.presentation      # Evidence presentation
6.approved          # Plan approved, ready for /implement (ADR-003)
6.execution        # Implementation execution
6.blocked          # Implementation blocked
6.rework           # Rework clarification required
6.rejected         # Rejected, return to Phase 4
6.complete         # Workflow complete (terminal)
```

### Design-Entscheidungen

| Entscheidung | Status | Dokumentiert |
|-------------|--------|-------------|
| 6.approved → workflow_complete → 6.complete | EDGE CASE | ✅ |
| 6.rejected → default → 4 | TRANSITIONAL | ✅ |
| /implement produziert `implementation_started` | KANONISCH | ✅ |
| /implement in 4 States (Start/Continue/Retry) | SEMANTISCH BREIT | ⚠️ |
| Messages teilweise instruktional | HYGIENE | ⚠️ |

---

## 4. Test-Abdeckung

| Kategorie | Tests | Status |
|-----------|-------|--------|
| Architecture Tests | 300+ | ✅ |
| Golden Flows | 6 | ✅ |
| Adversarial Tests | 5 | ✅ |
| Conformance Tests | 472 | ✅ |
| Vollständige Suite | 6144 | ✅ |

### Kritische Tests

- `test_6_approved_requires_explicit_implement` (ADR-003)
- `test_no_workflow_rejected_event` (Single Reject Source)
- `test_phase6_state_container_removed` (No Dead States)
- `test_blocked_has_recovery_path` (blocked/rework Härtung)

---

## 5. Verbleibende Restkomponenten (Acknowledged Debt)

### 5.1 Runtime Spec-Duplikation - ACKNOWLEDGED

**Status:** ACKNOWLEDGED DEBT

Die NEW Spec-Files sind definiert (`topology.yaml`, `guards.yaml`), aber die Runtime (`phase_kernel.py`) liest sie noch nicht. Stattdessen nutzt sie hartcodierte Logik.

```
NEU (definiert):      governance_spec/topology.yaml, guards.yaml
ALT (aktiv):          governance_runtime/kernel/phase_kernel.py
```

**Warum akzeptiert:**
- Spec-Files definieren die Zielarchitektur
- Runtime-Migration ist separate Aufgabe
- Phase 12 fokussiert auf Architektur-Definition

**Follow-up:** Runtime migrieren um NEW Spec-Files zu lesen.

### 5.2 Legacy-Bridge - VERBLEIBEND

**Status:** ACKNOWLEDGED DEBT

Die Legacy-Bridge (`_detect_phase6_substate_legacy`) ist **noch im Code** und muss nach Migration entfernt werden.

```
PATH: governance_runtime/kernel/phase_kernel.py
FUNCTION: _detect_phase6_substate_legacy()
```

**Warum noch drin:**
- Bestehende Sessions ohne `phase6_state` Feld
- On-the-fly Migration während Transition

**Exit-Kriterien:**
- [ ] < 1% Sessions nutzen Bridge
- [ ] Alle neuen Sessions setzen `phase6_state`
- [ ] Monitoring zeigt keine Nutzung

**Follow-up:** Nach erfolgreicher Migration Bridge entfernen.

### 5.2 6.rejected -> default -> 4 - TRANSITIONAL MARKER

**Status:** ACKNOWLEDGED DESIGN CHOICE

Die Transition `6.rejected -> default -> 4` nutzt `default` als Übergangspfad.

**Warum akzeptiert:**
- `6.rejected` ist ein kurzer transitional Marker
- `/continue` konsumiert `default` und führt nach Phase 4
- Expliziter als `return_to_phase4` wäre schöner, ist aber nicht kritisch

**Follow-up:** Bei späterem Cleanup expliziter modellieren.

### 5.3 blocked/rework - BEOBACHTUNGSZONEN

**Status:** MONITOR

Diese Zustände haben die höchste Drift-Gefahr:
- 6.blocked: Wann ist Blockade aufgehoben?
- 6.rework: Wann ist Clarification abgeschlossen?

**Follow-up:** Nach Release beobachten.

### 5.4 /implement Command - SEMANTISCH BREIT

**Status:** ACKNOWLEDGED DESIGN CHOICE

`/implement` ist erlaubt in:
- 6.approved (Start)
- 6.execution (Continue)
- 6.blocked (Rerun nach Blockade)
- 6.rework (Rerun nach Rework)

**Problem:** Ein Command für vier semantisch unterschiedliche Aktionen.

**Warum akzeptiert:**
- Praktisch für Benutzer
- Alle Aktionen resultieren in `implementation_started` Event
- Guards prüfen Preconditions

**Follow-up:** Bei späterem Cleanup expliziter trennen:
- `/implement` = Start
- `/continue` oder Systemevent = Resume/Retry

### 5.5 Messages - TEILWEISE INSTRUKTIONAL

**Status:** HYGIENE ISSUE

Messages enthalten teilweise instruktionale Texte:
- "resolve blockers and rerun /implement"
- "rerun /implement after clarifying"

**Problem:** Messages werden mehr als Präsentation + halbe Prozesswahrheit.

**Warum akzeptiert:**
- Conformance-Tests prüfen Command-Valdität
- Messages sind formal getrennt

**Follow-up:** Messages weiter auf Presentation-only trimmen.

### Migration Mapping

| Legacy Indikator | Kanonischer Substate |
|-----------------|----------------------|
| `workflow_complete: true` | `6.complete` |
| `user_review_decision: "reject"` | `6.rejected` |
| `implementation_execution_status: "in_progress"` | `6.execution` |
| `implementation_hard_blockers` | `6.blocked` |
| `workflow_approved: true` | `6.approved` |
| Default (Phase 6 aktiv) | `6.internal_review` |

---

## 6. Breaking Changes

### Von Legacy zu Kanonisch

1. **State IDs:** `6` → `6.internal_review` (für Phase 6 Sessions)
2. **Command Mapping:** `/implement` produziert jetzt `implementation_started`
3. **Reject Events:** `workflow_rejected` entfernt, nur `review_rejected`
4. **Messages:** Verschoben nach `messages.yaml`

### Migration für Consumers

1. Sessions ohne `phase6_state` nutzen **Legacy-Bridge** (temporär)
2. Nach Migration: `phase6_state` setzen
3. Legacy-Bridge nach Migration **entfernen**

> **WARNUNG:** Legacy-Bridge ist noch aktiv bis alle Sessions migriert sind.

---

## 7. Deprecations

| Komponente | Deprecated | Entfernt | Status |
|-----------|-----------|----------|--------|
| `phase_api.yaml` | v2.0 | Release 12 | WARNUNG: Noch aktiv |
| `_detect_phase6_substate_legacy` | v2.0 | Nach Migration | NOCH IM CODE |
| `workflow_rejected` Event | v2.0 | v2.0 | ✅ Entfernt |
| Hardcoded Runtime-Logik | v2.0 | Nach Runtime-Migration | NOCH AKTIV |

---

## 8. Verbleibende Aufgaben (Post-Release)

### Must-Fix nach Migration

- [ ] Legacy-Bridge entfernen (`_detect_phase6_substate_legacy`)
- [ ] `phase_api.yaml` mit Release 12 entfernen

### Runtime-Migration (Follow-up)

- [ ] Runtime migrieren um NEW Spec-Files zu lesen
- [ ] Hardcoded Logik in `phase_kernel.py` durch Spec-Interpretation ersetzen

### Monitoring nach Release

- [ ] Bridge-Nutzung < 1% sicherstellen
- [ ] blocked/rework Drift beobachten
- [ ] Session-Migration validieren

### Follow-up (Nice-to-Have)

- [ ] 6.rejected expliziter modellieren (späterer Cleanup)
- [ ] Message-Texte weiter auf Presentation-only trimmen

---

## 9. Nächste Schritte

1. **Release 2.0.0:** Neues Spec-Format ausliefern
2. **Migration:** Sessions zu `phase6_state` migrieren
3. **Monitoring:** Bridge-Nutzung beobachten
4. **Cleanup:** Legacy-Bridge nach erfolgreicher Migration entfernen

## 10. Ehrlicher Status

> **Release ist:**
> - ✅ Architecturally stabilized (Spec-Files definiert)
> - ✅ Test coverage complete
> - ✅ Migration path defined
> - ✅ Breaking changes documented
>
> **Release ist NICHT:**
> - ❌ 100% debt-free
> - ❌ Legacy-bridge-free
> - ❌ Spec-driven runtime
> - ❌ No follow-up needed

**Verbleibende Debt:**
- Legacy-Bridge (nach Migration entfernen)
- Runtime Spec-Duplikation (Runtime liest NEW Specs noch nicht)
- 6.rejected Default-Übergang (später expliziter)
- blocked/rework Beobachtung (Monitoring)

---

## 11. Kontakt

Für Fragen zum Release: Architecture Team
