# Phase 12: Release-Schnitt

**Status:** Ready for Release  
**Date:** 2026-03-25  
**Version:** 2.0.0

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

| Entscheidung | Dokumentiert |
|-------------|-------------|
| 6.approved → workflow_complete → 6.complete | EDGE CASE (zero-implementation) |
| 6.rejected → default → 4 | Via /continue |
| /implement produziert `implementation_started` | Kanonisch |

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

## 5. Legacy-Bridge

### Status: TRANSITIONAL

Die Legacy-Bridge (`_detect_phase6_substate_legacy`) ist ein **temporärer Shim** für Sessions ohne `phase6_state` Feld.

**EXIT CONDITION:** Entfernen nach vollständiger Migration.

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

1. Sessions ohne `phase6_state` nutzen Legacy-Bridge
2. Nach Migration: `phase6_state` setzen
3. Legacy-Bridge nach Migration entfernen

---

## 7. Deprecations

| Komponente | Deprecated | Entfernt |
|-----------|-----------|----------|
| `phase_api.yaml` | v2.0 | Release 12 |
| `_detect_phase6_substate_legacy` | v2.0 | Nach Migration |
| `workflow_rejected` Event | v2.0 | v2.0 |

---

## 8. Checkliste

### Pre-Release

- [x] Alle Tests grün (6144)
- [x] ADRs dokumentiert (ADR-001 bis ADR-007)
- [x] Spec-Validator implementiert
- [x] Golden Flows definiert
- [x] Legacy-Bridge als transitional markiert
- [x] Design-Entscheidungen dokumentiert

### Post-Release

- [ ] Legacy-Bridge nach Migration entfernen
- [ ] `phase_api.yaml` mit Release 12 entfernen
- [ ] Session-Migration validieren
- [ ] Monitoring für Bridge-Nutzung

---

## 9. Nächste Schritte

1. **Release 2.0.0:** Neues Spec-Format ausliefern
2. **Migration:** Sessions zu `phase6_state` migrieren
3. **Monitoring:** Bridge-Nutzung beobachten
4. **Cleanup:** Legacy-Bridge nach erfolgreicher Migration entfernen

---

## 10. Kontakt

Für Fragen zum Release: Architecture Team
