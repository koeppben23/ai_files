# Sprint I: Compatibility-Aufräumen

**Status:** In Progress  
**Erstellt:** 2026-03-22

## Ziel

Verbleibende Compatibility-Ränder und Allowlist-Einträge gezielt abbauen. Klare Trennung:
- `state_normalizer.py` = einzige Alias-Quelle
- `state_accessor.py` = Access Layer für Entrypoints
- ENGINE/KERNEL = separater Fokus

---

## Scope

### Im Scope
- Allowlist-Audit und echte Reduktion
- session_reader.py gezielt ausdünnen
- Entrypoints auf state_accessor.py umstellen
- legacy_compat.py Minimalität verifizieren
- ENGINE/KERNEL-Layer: direkte Legacy-Reads reduzieren

### Nicht im Scope
- Neues State-Modell
- Neue Schema-Engine
- Große Performance-Optimierung
- Neue Architekturwelle
- Pauschale Utility-Konsolidierung ohne klares Zielmodul

---

## Task 1 — Allowlist-Audit

### Ziel

Jeden verbleibenden Allowlist-Eintrag begründen.

### Fragestellung pro Eintrag

1. Warum existiert er noch?
2. Ist er fachlich nötig oder historisch?
3. Kann er sofort entfernt werden?
4. Falls nein: welches Folgeticket entfernt ihn?

### Done-Contract

- [ ] Jeder verbleibende Eintrag ist begründet
- [ ] Mindestens 1-2 Einträge verschwinden wirklich
- [ ] Keine "vorsorglichen" Ausnahmen

---

## Task 2 — session_reader.py gezielt ausdünnen

### Ziel

Klare Liste: welche `_`-Funktionen sind lokal, welche sind tot, welche sind Wrapper?

### Nicht erlaubt

- Neue Sammeldatei bauen
- Unklare "Utility"-Schicht erzeugen

### Done-Contract

- [ ] Tote Funktionen entfernt
- [ ] Wrapper konsolidiert oder entfernt
- [ ] Lokale Kopien wo möglich durch Accessor-Aufrufe ersetzt

---

## Task 3 — Entrypoints auf state_accessor.py umstellen

### Regel

Entrypoints sollen keine verstreuten `.get(...)`-Reads auf Kernfeldern machen.

### Stattdessen

```python
from governance_runtime.application.services.state_accessor import (
    get_phase,
    get_active_gate,
    get_status,
    get_next_gate_condition,
    # etc.
)
```

### Wichtig

- Alias-Auflösung bleibt in `state_normalizer.py`
- `state_accessor.py` nutzt intern `normalize_to_canonical()` 
- Keine zweite Alias-Engine in `state_accessor.py`

### Done-Contract

- [ ] Direkte Kernfeld-Zugriffe in Entrypoints spürbar reduziert
- [ ] Neue direkte Alias-/Legacy-Reads verboten

---

## Task 4 — legacy_compat.py Minimalität verifizieren

### Für jede Funktion

| Funktion | Entscheidung | Begründung |
|----------|-------------|------------|
| `read_plan_body` | keep / move / delete | |
| `sync_phase6_completion_fields` | keep / move / delete | |

### Done-Contract

- [ ] Für jede Funktion: keep/move/delete dokumentiert
- [ ] Graue Zone aufgelöst

---

## Task 5 — ENGINE/KERNEL Layer auditieren

### Focus

- Direkte Legacy-Key-Zugriffe
- Vermeidbare Raw-State-Reads
- Umstellung auf kanonische Accessors

### Done-Contract

- [ ]ENGINE/KERNEL-Layer: Legacy-Reads reduziert

---

## Risiken

| Risiko | Mitigation |
|--------|-----------|
| Versehentliches Entfernen benötigter Funktionen | Erst auditieren, dann löschen |
| Zweite Alias-Engine entsteht | Klare Regel: nur state_normalizer.py |
| ENGINE/KERNEL zu groß | Separater Fokus, nicht alles auf einmal |

---

## Nächste Schritte

1. Task 1 starten: Allowlist-Audit
2. Jeden Eintrag analysieren
3. Sofort entfernbaren Entries finden
4. migration planen
