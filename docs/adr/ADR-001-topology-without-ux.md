# ADR-001: Topologie ohne UX-Texte

**Status:** Accepted  
**Date:** 2026-03-24  
**Decision Makers:** Architecture Team  
**Related:** machine_topology.yaml, messages.yaml

## Context

Die aktuelle `phase_api.yaml` mischt Struktur (States, Transitions) mit UX-Texten (`active_gate`, `next_gate_condition`). Das erzeugt eine zweite Wahrheit: Änderungen an Texten erfordern Struktur-Änderungen und umgekehrt.

## Decision

**`machine_topology.yaml` trennt Struktur von UX, erlaubt aber non-runtime Metadata:**

### Struktur (Pflicht)
| Feld | Beschreibung |
|------|--------------|
| `state.id` | Stabile Runtime-ID |
| `state.parent` | Informativ, nicht für Resolution |
| `state.is_terminal` | Terminal-Flag |

### Non-Runtime Metadata (Optional)
| Feld | Beschreibung | Einschränkung |
|------|--------------|---------------|
| `description` | Technische Beschreibung | **Nie für Guard/Routing** |
| `tags` | Klassifikationstags | **Nie für Runtime** |
| `display_name` | Anzeigename | **Nie für Runtime** |

### Verboten (UX/Operator-Texte)
| Feld | Grund |
|------|-------|
| `active_gate` | UX-Text → `messages.yaml` |
| `next_gate_condition` | UX-Text → `messages.yaml` |
| `phase` (altes Format) | Display-Name → `messages.yaml` |

**Regel:** UX-/Operator-/Prompt-Texte verboten. Non-runtime Metadata optional erlaubt, aber **nie** für Guard-/Routing-Entscheidungen.

## Consequences

- Topologie ist maschinenzentriert und stabil
- UX-Änderungen erfordern keinen Struktur-Change
- Non-runtime Metadata erlaubt für Debugging, Diagramm-Export
- `machine_topology.yaml` Validierung prüft UX-Felder, nicht Metadata
- Session-Reader nutzt Message-Katalog für UX

## Validation

```python
UX_FIELDS = ["active_gate", "next_gate_condition"]

def test_no_ux_in_topology():
    for state in topology.states:
        for field in UX_FIELDS:
            assert field not in state.raw, f"UX field {field} in topology"

def test_metadata_not_used_for_resolution():
    """Non-runtime metadata darf Resolution nicht beeinflussen."""
    state = topology.get_state("6.execution")
    # Resolution nutzt nur id, parent ist informativ
    assert state.id == "6.execution"
```
