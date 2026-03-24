# Phase 2: Kanonische Topologie extrahieren (v3 - Strict with bugfixes)

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
| `states[].parent` | string? | **Optional**, strukturelle Metadaten |

### 2.2 Dokument-Metadaten vs Runtime-Felder

| Kategorie | Felder | Erlaubt | Zweck |
|-----------|--------|---------|-------|
| **Dokument-Metadaten** | `version`, `schema` | Ja (Datei-Ebene) | Spec-Versionierung |
| **Strukturelle Metadaten** | `parent` | Ja (State-Ebene) | Hierarchie-Info |
| **Präsentations-Metadaten** | `description`, `display_name`, `title`, `help_text` | Nein | UX-Texte |
| **UX-Felder** | `phase`, `active_gate`, `next_gate_condition` | Nein | Gate-Messages |

### 2.3 Metadata-Trennung

**Strukturelle Metadaten** (erlaubt):
- `parent`: Referenziert übergeordneten State (nur für Hierarchie-Info)
- Muss String sein, kein komplexes Objekt
- Hat keinen Einfluss auf Runtime-Auflösung

**Präsentations-Metadaten** (verboten):
- `description`, `display_name`, `title`, `help_text`
- Enthalten UX-Texte für Anzeige
- Gehören in `messages.yaml`

### 2.4 Strikte ID-Formate

| ID-Typ | Schema | Beispiel |
|--------|--------|----------|
| State ID | `^[a-zA-Z0-9][a-zA-Z0-9.\-]*$` | `0`, `1.1`, `3A`, `3B-1` |
| Transition ID | `^t<source>-<target>[-<suffix>]$` | `t0-t1.1`, `t5-t5-missing` |
| Event Name | `^[a-z][a-z0-9_]*$` | `default`, `ticket_present` |

### 2.5 Transition-ID Schema (structurally validated)

Transition-IDs folgen dem Schema `t<source>-<target>[-<suffix>]`:
- `source`: Quell-State-ID (ohne 't' prefix in ID)
- `target`: Ziel-State-ID (mit 't' prefix in ID: `t<target>`)
- `suffix`: Optional, für Self-Transitions mit gleichem Target

**Beispiele:**
- `t0-t1.1` - Transition von State `0` zu State `1.1`
- `t4-t4` - Self-Transition von State `4` zu State `4`
- `t5-t5-missing` - Self-Transition mit Suffix (plan_record_missing)
- `t6-t6-review-pending` - Self-Transition mit Suffix (review_changes_requested)

## 3. Erstellte Dateien

### 3.1 `governance_spec/topology.yaml`

Enthält die kanonische Runtime-Topologie mit 18 States und allen Transitions.

### 3.2 `tests/architecture/test_topology.py`

34 Tests für die strikte Topologie-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestTopologyStructure` | 7 | Grundlegende Struktur, Dokument-Metadaten |
| `TestStateIdFormat` | 3 | Strikte State-ID Validierung |
| `TestTransitionIdFormat` | 6 | Transition-ID Validierung (structurally) |
| `TestTransitionIntegrity` | 3 | Transition-Referenzen |
| `TestNoUxInTopology` | 2 | UX-Felder in YAML (YAML-Ebene) |
| `TestNoUxInLoadedModel` | 2 | UX-Felder im Modell + Strukturelle Metadaten |
| `TestTerminalStates` | 3 | Terminal-Flags (terminal-aware) |
| `TestTopologyReachability` | 1 | Erreichbarkeit |
| `TestPhase6Monolith` | 4 | Phase 6 Struktur |
| `TestParentMetadata` | 2 | Parent als strukturelle Metadaten |
| `TestCrossSpecConformance` | 1 | Guard-Ref Phase 2 scope boundary |

## 4. Bugfixes in v3

| Issue | Fix |
|-------|-----|
| `test_transition_ids_unique` used set | Changed fixture to return list |
| `test_transition_id_target_state_exists` used substring | Structural validation with `t<target>` parsing |
| `test_no_version_or_schema_leak` was empty | Replaced with `test_document_metadata_allowed` |
| `test_all_states_have_transitions` not terminal-aware | Split into terminal-aware tests |
| `test_potential_terminal_states` asserted 0 | Removed global assertion |
| `parent` vs `description` semantics unclear | Documented structural vs presentation metadata |

## 5. Testergebnisse

```
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 68 passed
```

## 6. Nächste Schritte

1. **Phase 3**: Guard-/Invariant-Schicht extrahieren
2. **Phase 4**: Command-Policy separat modellieren
3. **Phase 5**: Presentation/Messages herauslösen

---

**Nächster Schritt:** Guard-/Invariant-Schicht extrahieren.
