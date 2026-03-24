# Phase 2: Kanonische Topologie extrahieren (v2 - Strict)

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/topology.yaml`

---

## 1. Ziel

Extrahiere die reine **Runtime-Topologie** aus der monolithischen `phase_api.yaml` in eine separate `topology.yaml`-Datei.

Die Topologie enthält **nur** Runtime-relevante Felder - keine UX-Texte, keine Display-Names, keine Gate-Messages.

## 2. Prinzipien

### 2.1 Runtime Core Only
Die `topology.yaml` enthält **nur**:

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `start_state_id` | string | Startzustand (kanonische ID) |
| `states[].id` | string | State-ID (alphanumerisch mit . und -) |
| `states[].terminal` | boolean | Terminal-Flag |
| `states[].transitions` | list | Liste von Transitions |
| `states[].parent` | string? | **Optional**, non-runtime Metadaten |

### 2.2 Keine UX-Felder
Verbotene Felder in Topologie (werden von Tests geprüft):

**States:**
- `phase`, `active_gate`, `next_gate_condition` (UX-Texte)
- `description`, `display_name`, `title`, `help_text` (Non-runtime Metadata)

**Transitions:**
- `source`, `active_gate`, `next_gate_condition`, `description`

### 2.3 Strikte ID-Formate

| ID-Typ | Schema | Beispiel |
|--------|--------|----------|
| State ID | `^[a-zA-Z0-9][a-zA-Z0-9.\-]*$` | `0`, `1.1`, `3A`, `3B-1` |
| Transition ID | `^t<source>-<target>[-<suffix>]$` | `t0-t1.1`, `t5-t5-missing` |
| Event Name | `^[a-z][a-z0-9_]*$` | `default`, `ticket_present` |

### 2.4 Transition-ID Schema

Transition-IDs folgen dem Schema `t<source>-<target>[-<suffix>]`:
- `source`: Quell-State-ID (ohne 't' prefix)
- `target`: Ziel-State-ID
- `suffix`: Optional, für Self-Transitions mit gleichem Target

**Beispiele:**
- `t0-t1.1` - Transition von State `0` zu State `1.1`
- `t4-t4` - Self-Transition von State `4` zu State `4`
- `t5-t5-missing` - Self-Transition mit Suffix (plan_record_missing)

## 3. Erstellte Dateien

### 3.1 `governance_spec/topology.yaml`

Enthält die kanonische Runtime-Topologie mit 18 States und allen Transitions.

**Struktur:**
```yaml
version: 1
schema: opencode.topology.v1
start_state_id: "0"

states:
  - id: "0"
    terminal: false
    transitions:
      - id: "t0-t1.1"
        event: default
        target: "1.1"
  # ... weitere States
```

### 3.2 `tests/architecture/test_topology.py`

31 Tests für die strikte Topologie-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestTopologyStructure` | 7 | Grundlegende Struktur |
| `TestStateIdFormat` | 3 | Strikte State-ID Validierung |
| `TestTransitionIdFormat` | 5 | Transition-ID Validierung |
| `TestTransitionIntegrity` | 3 | Transition-Referenzen |
| `TestNoUxInTopology` | 2 | UX-Felder in YAML (YAML-Ebene) |
| `TestNoUxInLoadedModel` | 1 | UX-Felder im Modell (Model-Ebene) |
| `TestTerminalStates` | 2 | Terminal-Flags |
| `TestTopologyReachability` | 1 | Erreichbarkeit |
| `TestPhase6Monolith` | 4 | Phase 6 Struktur |
| `TestParentMetadata` | 2 | Parent als non-runtime |
| `TestCrossSpecConformance` | 1 | Guard-Ref Vorbereitung (Phase 8) |

## 4. Testergebnisse

```
tests/architecture/test_topology.py ... 31 passed
tests/architecture/test_spec_inventory.py ... 18 passed
```

## 5. Änderungen gegenüber Phase 2 v1

| Aspect | Phase 2 v1 | Phase 2 v2 (Strict) |
|--------|------------|---------------------|
| `start_token` | ✗ | `start_state_id` ✓ |
| `route_strategy` | enthalten | **entfernt** |
| `default_next` | enthalten | **entfernt** |
| `terminal` | fehlt | enthalten |
| `parent` | fehlt | **optional** |
| Transition-ID | abgeleitet | **stabil: t\<source\>-\<target\>[-\<suffix\>]** |
| State-ID Schema | permissiv | **strikt: alphanumerisch mit . und -** |
| UX Check | YAML only | **YAML + Model** |
| Guard-Ref Test | enthalten | **Phase 8 vorbehalten** |

## 6. Nächste Schritte

1. **Phase 3**: Guard-/Invariant-Schicht extrahieren
2. **Phase 4**: Command-Policy separat modellieren
3. **Phase 5**: Presentation/Messages herauslösen

---

**Nächster Schritt:** Guard-/Invariant-Schicht extrahieren.
