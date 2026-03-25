# Phase 1: Ist-Modell Inventarisierung

**Status:** Draft  
**Date:** 2026-03-24  
**Source:** `governance_spec/phase_api.yaml`

---

## 1. Spec-Felder Klassifizierung

### 1.1 State-Level Fields

| Feld | Quelle | Zielschicht | Bemerkung |
|------|--------|-------------|-----------|
| `token` | phase_api.yaml | **Topologie** | → wird `state_id` |
| `phase` | phase_api.yaml | **Messaging** | Display-Name → `messages.state_names` |
| `active_gate` | phase_api.yaml | **Messaging** | UX-Text → `messages.gate_messages` |
| `next_gate_condition` | phase_api.yaml | **Messaging** | UX-Text → `messages.next_action_hints` |
| `next` | phase_api.yaml | **Topologie** | Default-Nachfolger |
| `route_strategy` | phase_api.yaml | **Topologie** | `stay` oder `next` |

### 1.2 Transition-Level Fields

| Feld | Quelle | Zielschicht | Bemerkung |
|------|--------|-------------|-----------|
| `transitions[].when` | phase_api.yaml | **Guard** | Transition condition / guard input (migrates toward `guard_ref` in V2) |
| `transitions[].next` | phase_api.yaml | **Topologie** | Ziel-State-ID |
| `transitions[].source` | phase_api.yaml | **Topologie** | Provenance label (z.B. "6.execution → 6.internal_review") |
| `transitions[].active_gate` | phase_api.yaml | **Messaging** | → `messages` |
| `transitions[].next_gate_condition` | phase_api.yaml | **Messaging** | → `messages` |

### 1.3 Guard-Related Fields

| Feld | Quelle | Zielschicht | Bemerkung |
|------|--------|-------------|-----------|
| `exit_required_keys` | phase_api.yaml | **Guard** | → `guards.exit_guards` |
| `output_policy` | phase_api.yaml | **Command-Policy** | → `command_policy` (vorsichtig: nur Policy-Teil, nicht gesamte Command-Registry) |

### 1.4 Meta Fields

| Feld | Quelle | Zielschicht | Bemerkung |
|------|--------|-------------|-----------|
| `version` | phase_api.yaml | **Meta** | Spec-Version |
| `schema` | phase_api.yaml | **Meta** | Schema-Referenz |
| `start_token` | phase_api.yaml | **Topologie** | → `start_state_id` |

---

## 2. Phase 6 Substates Inventarisierung

### 2.1 Aktuelle Struktur (Monolith)

Phase 6 ist aktuell ein einziges Token `"6"` mit `route_strategy: "stay"`.

### 2.2 Identifizierte Substates (aus active_gate-Werten)

| Aktuelles `active_gate` | Beschreibung | V1 Runtime-ID | Übergang aus |
|------------------------|--------------|---------------|--------------|
| "Implementation Internal Review" | Review-Loop läuft | `6.internal_review` | `6.execution` |
| "Implementation Execution In Progress" | Implementierung läuft | `6.execution` | `6.approved` |
| "Implementation Accepted" | Implementation akzeptiert | `6.execution` | `6.internal_review` |
| "Implementation Blocked" | Implementierung blockiert | `6.blocked` | `6.internal_review` |
| "Implementation Rework Clarification Gate" | Rework-Klärung | `6.rework` | `6.presentation` |
| "Implementation Presentation Gate" | Evidence bereit | `6.presentation` | `6.internal_review` |
| "Implementation Started" | Gestartet | `6.execution` | `6.approved` |
| "Workflow Complete" | Abgeschlossen | `6.complete` | `6.presentation` |
| "Rework Clarification Gate" | Rework-Klärung | `6.rework` | `6.presentation` |
| "Evidence Presentation Gate" | Decision Gate | `6.presentation` | `6.internal_review` |

### 2.3 Mapping zu V1 Substates

| V1 Substate | Quelle (aktive_gate) | Übergänge |
|-------------|---------------------|-----------|
| `6.execution` | "Implementation Execution In Progress", "Implementation Started", "Implementation Accepted" | → `6.internal_review` |
| `6.internal_review` | "Implementation Internal Review" | → `6.execution` (loop), → `6.presentation` (done) |
| `6.presentation` | "Evidence Presentation Gate", "Implementation Presentation Gate" | → `6.approved`, `6.rework`, `6.rejected` |
| `6.approved` | **NEU** | → `6.execution` (via /implement) |
| `6.blocked` | "Implementation Blocked" | → `6.execution` (after fix) |
| `6.rework` | "Rework Clarification Gate", "Implementation Rework Clarification Gate" | → `4` (re-plan) |
| `6.rejected` | **NEU** (aus `review_rejected`) | → `4` |
| `6.complete` | "Workflow Complete" | Terminal |

---

## 3. Runtime-Consumer Inventarisierung

### 3.1 Core Runtime

| Datei | Rolle | Liest | Schreibt |
|-------|-------|-------|----------|
| `phase_kernel.py` | Kern-Transitionen | phases, transitions, exit_required_keys | KernelResult |
| `phase_api_spec.py` | Spec-Parsing | phase_api.yaml | PhaseApiSpec |
| `session_reader.py` | State-Materialisierung | Spec, State | SESSION_STATE |
| `gate_evaluator.py` | Gate-Evaluation | phase_exit_contract | GateResult |

### 3.2 Entrypoints

| Datei | Rail | Liest | Schreibt |
|-------|------|-------|----------|
| `session_reader.py` | `/continue` | Spec, State | State, Next-Action |
| `phase4_intake_persist.py` | `/ticket` | State | State |
| `phase5_plan_record_persist.py` | `/plan` | State | State |
| `implement_start.py` | `/implement` | State | State |
| `review_decision_persist.py` | `/review-decision` | State | State |

### 3.3 Domain

| Datei | Rolle | Liest |
|-------|-------|-------|
| `phase_state_machine.py` | Phase-Rank, Normalisierung | State |
| `strict_exit_evaluator.py` | Strict-Exit Gates | State, Contract |
| `state_accessor.py` | State-Feldzugriff | State |
| `state_normalizer.py` | State-Normalisierung | State |

### 3.4 Infrastructure

| Datei | Rolle |
|-------|-------|
| `workspace_resolver.py` | Workspace-Pfad-Auflösung |
| `governance_config_loader.py` | Governance-Config laden |

---

## 4. Drift-Risiken

### 4.1 Aktuelle Risiken

| Risiko | Beschreibung | Auswirkung |
|--------|--------------|------------|
| UX in Topologie | `active_gate`, `next_gate_condition` in spec | Änderung an Text erfordert Struktur-Change |
| Hardcoded Guards | `_ticket_or_task_recorded`, etc. in kernel.py | Neue Guards erfordern Code-Change |
| Command-Policy implizit | Keine zentrale Registry | Audit schwierig |
| Phase 6 Monolith | 12+ Self-Transitions in einem Token | Wartbarkeit, Verständlichkeit |
| `/continue` Logik | Versteckte State-Resolution in session_reader.py | Konsistenz-Risiko |

### 4.2 Übergang zu V2

| V1 → V2 | Lösung |
|---------|--------|
| UX in Topologie | → `messages.yaml` |
| Hardcoded Guards | → `guards.yaml` (strukturiert) |
| Command-Policy implizit | → `command_policy.yaml` (kanonisch) |
| Phase 6 Monolith | → Explizite Substates |
| `/continue` Logik | → Explizite Constraints in Command-Policy |

---

## 5. Slash-Command / Review Semantik

### 5.1 Command-Liste (Aktuell)

| Command | Phase | Art | Beschreibung |
|---------|-------|-----|--------------|
| `/continue` | Alle | Mutating | Routing fortschreiten |
| `/ticket` | 4 | Mutating | Ticket/Task persistieren |
| `/plan` | 4, 5 | Mutating | Plan generieren |
| `/review` | 4 | **Read-only** | PR/Datei reviewen |
| `/implement` | 6.presentation *(Ist-Zustand)* | Mutating | Implementierung starten (nach ADR-003: sollte in 6.approved sein) |
| `/review-decision` | 6.presentation | Mutating | Finale Review-Entscheidung |

### 5.2 `/review` Semantik

- **Phase 4** - parallel zu `/ticket`
- **Read-only** - ändert keinen State
- **Input:** PR-URL, Dateipfad, Verzeichnispfad
- **Output:** Verdict (approve/changes_requested) + Findings
- **Kein State-Change** - nur Review-Ergebnis

---

## 6. Test-Spec-Inventory (Vorbereitung)

### Was der Inventory-Test prüfen muss:

1. **Alle `token`-Werte** sind eindeutig
2. **Alle `next`-Werte** referenzieren existierende Tokens
3. **Alle `transitions[].next`** referenzieren existierende Tokens
4. **`start_token`** existiert
5. **Keine UX-Felder** in Topologie (nach V2 Migration)
6. **Alle `when`-Bedingungen** haben Guard-Definitionen
7. **Phase 6 hat Self-Transitions** (monolithisch, vor Zerlegung)

---

**Nächster Schritt:** `test_spec_inventory.py` erstellen und Patch für Phase 1 erstellen.
