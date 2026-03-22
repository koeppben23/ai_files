# Sprint H: Legacy-Abbau

**Status:** Phase 1 - Planung  
**Erstellt:** 2026-03-22

## Ziel

Legacy-Kompatibilitätsschichten gezielt abbauen, verbleibende Alias-Allowlist-Einträge minimieren und das System auf die kanonischen Contracts ziehen.

---

## Scope / Nicht im Scope

### Im Scope

- **legacy_compat.py** - Gezielt ausdünnen, nicht mehr benötigte Wrapper entfernen
- **Alias-Allowlist** - Verbleibende Einträge analysieren und migrieren wo möglich
- **Alte Übergangspfade** - Nicht mehr benötigte Legacy-Funktionen identifizieren

### Nicht im Scope

- Big-Bang Rewrite alter Module
- Entfernung kritischer Legacy-Funktionalität ohne Ersatz
- Performance-Optimierungen

---

## Phase 1 — legacy_compat.py Analyse

### Ziel

Verstehen was in legacy_compat.py noch benötigt wird und was entfernt werden kann.

### Deliverables

1. **Inventur der Funktionen**
   - Welche Funktionen werden noch verwendet?
   - Welche sind nur für Tests?
   - Welche können entfernt werden?

2. **Analyse der Abhängigkeiten**
   - Woher werden Funktionen importiert?
   - Können direkte Imports verwendet werden?

---

## Phase 2 — Alias-Allowlist Abbau

### Ziel

Die verbleibende Allowlist reduzieren.

### Aktuelle Allowlist-Einträge

| Kategorie | Dateien |
|-----------|---------|
| MIGRATED | 6 |
| LEGACY COMPAT | 2 |
| ENTRYPOINTS | 9 |
| ENGINE | 3 |
| INFRASTRUCTURE | 5 |
| OTHER | 4 |

### Strategie

1. **Offensichtliche Kandidaten zuerst**
   - `legacy_compat.py` - Wenn Funktionen nicht mehr verwendet werden
   - `next_action_resolver.py` - Wurde bereits migriert (nutzt jetzt transition_model)

2. **Entry Points mit Vorsicht**
   - Entrypoints dürfen Legacy schreiben, aber sollten kanonisch lesen
   - Prüfen welche wirklich Alias-Auflösung brauchen

---

## Phase 3 — Legacy-Übergangspfade identifizieren

### Ziel

Nicht mehr benötigte Legacy-Übergangspfade identifizieren.

### Zu prüfen

- Legacy-Funktionen ohne Aufrufer
- Deprecated Marker
- Ungenutzte Exporte

---

## Done-Contract

### Für Sprint H als abgeschlossen gilt, wenn:

1. ✓ `legacy_compat.py` analysiert und dokumentiert
2. ✓ Nicht mehr benötigte Einträge aus Allowlist entfernt
3. ✓ Mindestens 2-3 Allowlist-Einträge migriert oder entfernt
4. ✓ Bestehende Tests bleiben grün
5. ✓ Keine neue Legacy-Logik eingeführt

---

## Risiken

| Risiko | Mitigation |
|--------|-----------|
| Versehentliches Entfernen benötigter Funktionen | Inventur vor Entfernung |
| Brechende Änderungen | Tests prüfen |
| Zu aggressiver Abbau | Konservativ bleiben, nur Offensichtliches |

---

## Nächste Schritte

1. legacy_compat.py Inventur erstellen
2. Allowlist-Einträge analysieren
3. Migration planen
4. Änderungen umsetzen
