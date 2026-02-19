# Clean Architecture Cleanup Analysis

## Problem

master.md enthält 55+ "the assistant MUST..." Instruktionen, die Clean Architecture verletzen.

### Verantwortlichkeiten (SOLLTE)

| Layer | Verantwortung | Beispiele |
|-------|---------------|-----------|
| **Policy (master.md)** | WAS, WANN, WARUM | "Workflow MUST persist X after Phase Y" |
| **Kernel (Python)** | WIE (Implementierung) | `persist_artifacts()`, `phase_router.py` |
| **LLM Frontend** | Präsentation, Interaktion | Output-Formatierung, User-Dialog |

### Aktuelle Verletzung (IST)

```
master.md: "The assistant MUST output X"
           ↑ Policy instruiert direkt das Frontend
           ↑ Verletzt: Policy sollte nicht wissen WER implementiert
```

## Identifizierte Probleme

### 1. "the assistant" Referenzen (55+ in master.md)

**Falsch:**
```
- The assistant MUST output a short activation summary
- The assistant MUST wait for explicit user confirmation
- The assistant MUST emit one terminal summary line
```

**Richtig:**
```
- The workflow MUST produce a short activation summary
- The workflow MUST wait for explicit confirmation at gates
- The output MUST include one terminal summary line
```

### 2. Output-Format-Definitionen in Policy

**Falsch:**
```
[NEXT-ACTION]
PhaseGate: ...
Status: ...
```
Dies definiert das Output-Format in master.md.

**Richtig:**
- Output-Format in `diagnostics/RESPONSE_ENVELOPE_SCHEMA.json` oder Kernel-Code
- master.md verweist nur auf das Schema: "Output MUST conform to RESPONSE_ENVELOPE_SCHEMA"

### 3. "OpenCode-only" Missverständlich

**Falsch:**
```
#### OpenCode-only: Persist Repo Cache (Binding when applicable)
```

**Richtig:**
```
#### Kernel-Enforced: Persist Repo Cache (Mandatory after Phase 2)
```

### 4. Überschneidung Kernel vs Policy

| Aspekt | master.md (Policy) | Kernel (Python) |
|--------|-------------------|-----------------|
| Persistenz-Trigger | "MUST write after Phase 2" | `persistence_policy.py`, `phase_router.py` |
| Output-Format | `[NEXT-ACTION]` blocks | `response_formatter.py` |
| Session State | Schema-Referenz | `session_state_repository.py` |

## Cleanup-Plan

### Commit 1: Terminologie-Bereinigung
- "the assistant" -> "the workflow" oder "the kernel"
- "OpenCode-only" -> "Kernel-Enforced" oder entfernen
- "Binding when applicable" -> "Mandatory when X"

### Commit 2: Output-Format-Extraktion
- Output-Format-Definitionen aus master.md entfernen
- Verweis auf `RESPONSE_ENVELOPE_SCHEMA.json` hinzufügen
- Kernel implementiert Format, Policy definiert nur Contract

### Commit 3: Persistenz-Contract-Klärung
- master.md: Nur "MUST persist X after Phase Y"
- Kernel: Implementiert Trigger in `phase_router.py`
- Keine "assistant MUST produce..." mehr

### Commit 4: Separation of Concerns
- Policy-Regeln: WAS muss passieren
- Kernel-Code: WIE passiert es
- LLM-Frontend: WIE wird es präsentiert

## Ergebnis

Nach Cleanup:
- master.md: Reine Policy-Definition (keine Implementierungsdetails)
- Kernel: Implementiert alle MUST-Regeln deterministisch
- LLM-Frontend: Empfängt Kernel-Output, formatiert für User
