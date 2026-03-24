# Phase 2: Kanonische Topologie extrahieren

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/topology.yaml`

---

## 1. Ziel

Extrahiere die reine Topologie (States, Transitions, Start-State) aus der monolithischen `phase_api.yaml` in eine separate `topology.yaml`-Datei.

## 2. Prinzipien

### 2.1 Topologie ohne UX
Die `topology.yaml` enthält **keine** UX-Texte:
- Kein `phase` (Display-Name)
- Kein `active_gate` (UX-Text)
- Kein `next_gate_condition` (UX-Text)

### 2.2 Strukturelle Felder
Die `topology.yaml` enthält nur:
- `id` (State-ID)
- `route_strategy` (`stay` oder `next`)
- `default_next` (optional, Default-Nachfolger)
- `transitions` (Liste von `{when, next}`)

### 2.3 Referenz-Integrität
Alle `next`-Referenzen (in `default_next` und `transitions`) müssen auf existierende State-IDs verweisen.

## 3. Erstellte Dateien

### 3.1 `governance_spec/topology.yaml`

Enthält die kanonische Topologie mit 18 States und allen Transitions.

**Struktur:**
```yaml
version: 1
schema: opencode.topology.v1
start_state: "0"

states:
  - id: "0"
    route_strategy: "next"
    default_next: "1.1"
  # ... weitere States
```

### 3.2 `tests/architecture/test_topology.py`

12 Tests für die Topologie-Struktur:
- `TestTopologyStructure` (3 Tests): Laden, Start-State, Eindeutigkeit
- `TestTransitionIntegrity` (2 Tests): Referenz-Integrität
- `TestRouteStrategy` (2 Tests): Gültige Strategien, Self-Transitions
- `TestTopologyReachability` (1 Test): Alle States erreichbar
- `TestPhase6Monolith` (4 Tests): Phase 6 Monolith-Struktur

## 4. Testergebnisse

```
tests/architecture/test_topology.py ... 12 passed
tests/architecture/test_spec_inventory.py ... 18 passed
```

## 5. Unterschiede zu `phase_api.yaml`

| Feld | `phase_api.yaml` | `topology.yaml` |
|------|------------------|-----------------|
| `token` | State-ID | `id` |
| `phase` | UX-Text | **entfernt** |
| `active_gate` | UX-Text | **entfernt** |
| `next_gate_condition` | UX-Text | **entfernt** |
| `next` | Default-Nachfolger | `default_next` |
| `transitions[].source` | Provenance label | **entfernt** |
| `transitions[].active_gate` | UX-Text | **entfernt** |
| `transitions[].next_gate_condition` | UX-Text | **entfernt** |

## 6. Nächste Schritte

1. **Phase 3**: Guard-/Invariant-Schicht extrahieren
2. **Phase 4**: Command-Policy separat modellieren
3. **Phase 5**: Presentation/Messages herauslösen

---

**Nächster Schritt:** Guard-/Invariant-Schicht extrahieren.
