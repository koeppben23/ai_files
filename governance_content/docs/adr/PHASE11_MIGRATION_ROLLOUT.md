# Phase 11: Migration und Rollout (Operational Guidance)

**Status:** Draft - Operational Guidance Only  
**Date:** 2026-03-25

> **WARNUNG:** Dieses Dokument ist ein Rollout-Plan / operational guidance.
> Es beschreibt den geplanten Migrationsprozess und ist NICHT
> technisch vollständig im aktuellen Patch implementiert.

## 1. Ziel

Geordnete Migration von Legacy-State-Machine zur neuen Architektur mit minimalem Risiko.

**Hinweis:** Die technische Implementierung (Bridge, Feature Flags) ist noch nicht vollständig
im Code verankert. Dieses Dokument dient als Planungsgrundlage.

## 2. Migrationsstrategien

### 2.1 Big Bang vs Phased

| Strategie | Vorteil | Nachteil | Empfehlung |
|-----------|----------|----------|------------|
| Big Bang | Einfach, keine Dualität | Riskant, kein Rollback | ❌ |
| Phased | Risiko verteilt, lernbar | Komplexer, Dualbetrieb | ✅ |

**Entscheidung:** Phased Rollout mit Canary-Pattern

### 2.2 Migrationspfade

#### Legacy → Kanonisch Mapping

| Legacy Indikator | Kanonischer Substate |
|-----------------|----------------------|
| `workflow_complete: true` | `6.complete` |
| `user_review_decision: "reject"` | `6.rejected` |
| `implementation_execution_status: "in_progress"` | `6.execution` |
| `implementation_hard_blockers` | `6.blocked` |
| `implementation_rework_clarification_pending: true` | `6.rework` |
| `workflow_approved: true` | `6.approved` |
| `phase6_evidence_presentation_gate_active: true` | `6.presentation` |
| Default (Phase 6 aktiv) | `6.internal_review` |

### 2.3 Session-Migration

#### Automatische Migration (On-the-fly)
```
Session loaded
  → Prüfe phase6_state vorhanden?
    → Ja: Nutze kanonischen Wert
    → Nein: Lege phase6_state aus Legacy-Indikatoren ab
      → Speichere phase6_state in Session
      → Markiere Session als "migrated"
```

#### Batch-Migration (für alte Sessions)
```bash
# Script zum Migrieren aller Sessions
python scripts/migrate_phase6_sessions.py --all
```

## 3. Rollout-Phasen

### Phase 11.1: Canary (10% Traffic)
- **Zeitraum:** Woche 1-2
- **Ziel:** Validierung in Produktion mit kleinem Anteil
- **Kriterien:**
  - [ ] < 1% Fehlerrate
  - [ ] Latenz < Schwellwert
  - [ ] Keine Regression in Kernflüssen

### Phase 11.2: Ramp-up (50% Traffic)
- **Zeitraum:** Woche 3-4
- **Ziel:** Stabilität bei größerem Anteil
- **Kriterien:**
  - [ ] < 0.5% Fehlerrate
  - [ ] Golden Flows alle grün
  - [ ] Keine neuen Edge Cases

### Phase 11.3: Full Rollout (100% Traffic)
- **Zeitraum:** Woche 5-6
- **Ziel:** Vollständige Migration
- **Kriterien:**
  - [ ] 99.9% Sessions haben `phase6_state`
  - [ ] Legacy-Bridge wird nicht mehr erreicht
  - [ ] Legacy-Code kann deprecated werden

## 4. Monitoring

### 4.1 Key Metrics

| Metric | Ziel | Alert Threshold |
|--------|------|-----------------|
| Fehlerrate | < 1% | > 2% |
| Latenz P99 | < Guardrail | > 1.5x Guardrail |
| Bridge-Nutzung | < 10% | > 20% |
| Unbekannte States | 0 | > 5 |

### 4.2 Monitoring Dashboard

```
┌─────────────────────────────────────────────────┐
│ Phase 6 Migration Monitor                       │
├─────────────────────────────────────────────────┤
│ Sessions mit phase6_state:     95.3%           │
│ Sessions via Legacy-Bridge:    4.7% ⚠️        │
│ Fehlerrate:                   0.3% ✅          │
│ Latenz P99:                   45ms ✅          │
└─────────────────────────────────────────────────┘
```

### 4.3 Alerts

- [ ] `alert: legacy_bridge_usage_high` - Bridge wird zu oft genutzt
- [ ] `alert: phase6_transition_errors` - Fehler bei Transitionen
- [ ] `alert: unknown_substate_detected` - Unbekannter Substate

## 5. Rollback-Plan

### 5.1 Trigger

- [ ] Fehlerrate > 5%
- [ ] Latenz > 3x Guardrail
- [ ] Kritische Golden Flows fehlgeschlagen

### 5.2 Rollback-Schritte

```bash
# 1. Feature Flag deaktivieren
kubectl set env deploy/governance GOVERNANCE_PHASE6_ENABLED=false

# 2. Cache invalidieren
redis-cli FLUSHDB patterns "*phase6*"

# 3. Monitoren bis Stabilisierung
# 4. Incident post-mortem
```

## 6. Legacy-Bridge Retirement

### 6.1 Exit-Kriterien

| Kriterium | Schwellwert |
|-----------|-------------|
| Bridge-Nutzung | < 1% |
| Sessions ohne phase6_state | < 10 |
| Tage seit Canary-Start | > 30 |

### 6.2 Retirement-Schritte

1. Bridge-Code mit `DEPRECATED` markieren
2. Bridge-Code in separate Datei verschieben
3. Unit-Tests für Bridge entfernen
4. Bridge-Funktion löschen
5. ADR-007 aktualisieren

## 7. Kommunikation

### 7.1 Internes Update

- [ ] Team-Briefing vor Canary
- [ ] Monitoring-Dashboard freigeben
- [ ] Rollback-Prozedur kommunizieren

### 7.2 Dokumentation

- [ ] Runbook für Migration
- [ ] Troubleshooting-Guide
- [ ] FAQ für häufige Fragen

## 8. Checkliste

### Pre-Rollout
- [ ] Alle Tests grün
- [ ] Monitoring aktiv
- [ ] Alerts konfiguriert
- [ ] Rollback getestet
- [ ] Team geschult

### Während Rollout
- [ ] Tägliches Monitoring-Review
- [ ] Incidents dokumentieren
- [ ] Lessons Learned sammeln

### Post-Rollout
- [ ] Legacy-Bridge entfernt
- [ ] Dokumentation aktualisiert
- [ ] Post-mortem durchgeführt
- [ ] Follow-up Tasks erstellt

## 9. Timeline

```
Woche 1-2:   Canary (10%)
Woche 3-4:   Ramp-up (50%)
Woche 5-6:   Full Rollout (100%)
Woche 7:     Legacy Bridge Retirement
Woche 8:     Post-Mortem und Learnings
```
