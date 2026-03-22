# Sprint K: Konsolidierung und Allowlist-Abbau

**Status:** In Progress  
**Erstellt:** 2026-03-22

## Ziel

Den neuen Architekturzustand finalisieren und die letzten Übergangsreste systematisch reduzieren.

---

## Durchgeführt

### 1. Allowlist-Audit (31 → 29 Einträge)

**Ergebnis:**

| Kategorie | Anzahl | Status |
|-----------|--------|--------|
| KEEP (permanent) | 14 | Bleibt |
| OTHER | 6 | Necesary für jetzt |
| ENTRYPOINT | 10 | Necesary für jetzt |
| **Total** | **29** | -2 von 31 |

**Entfernt:**
- `legacy_compat.py` → durch `plan_reader.py` ersetzt

**Verbleibende Entries sind begründet:**
- Entrypoints: Lesen SESSION_STATE.json direkt (fachlich nötig)
- ENGINE/KERNEL: Brauchen Raw-State für Invarianten/Kernel-Logik
- INFRA: Infrastructure-Layer

### 2. Weitere Reduktion

**Erkenntnis:** Weitere Reduktion erfordert Migration der Entrypoints auf state_accessor.py.

Das ist eine größere Arbeit und nicht Teil dieses Sprint-K-Konsolidierungssprints.

---

## Verbleibende Allowlist-Einträge (29)

### KEEP (Permanent legitim)

1. `state_normalizer.py` - PRIMÄR
2. `orchestrator.py` - MIGRATED
3. `phase5_normalizer.py` - MIGRATED
4. `state_accessor.py` - MIGRATED
5. `policy_resolver.py` - MIGRATED
6. `transition_model.py` - MIGRATED
7. `state_document_validator.py` - SCHEMA
8. `session_state_invariants.py` - ENGINE
9. `phase_kernel.py` - KERNEL
10-14. INFRA (5 files)

### REVIEW (Necesary für jetzt)

15-25. ENTRYPOINT (10 files)
26-29. OTHER (4 files)

---

## Nächste Schritte (außerhalb Sprint K)

1. **Migration Entrypoints auf state_accessor.py**
   - Entrypoints können teilweise state_accessor.py verwenden
   - Reduziert Allowlist weiter

2. **L: Messen und Optimieren**
   - Cache im state_accessor.py
   - Hot-Path-Analyse in session_reader.py
   - unnötige Mehrfach-Normalisierung

---

## Sprint K Fazit

| Ziel | Status |
|------|--------|
| Allowlist auditieren | ✓ |
| Entries klassifizieren | ✓ |
| Entries dokumentieren | ✓ |
| legacy_compat.py entfernen | ✓ |
| Plan-Reader erstellen | ✓ |

**Allowlist: 31 → 29**
