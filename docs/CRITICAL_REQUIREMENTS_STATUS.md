# Governance Critical Requirements Status

## MUSS (Existenzielle Risiken)

| # | Requirement | Status | Evidence | Gap |
|---|-------------|--------|----------|-----|
| 1 | **Trust Boundary & Threat Model** | ⚠️ Teilweise | MD_PYTHON_POLICY.md | Kein explizites THREAT_MODEL.md |
| 2 | **Supply Chain / Reproducibility** | ⚠️ Teilweise | activation_hash, ruleset_hash | Model identity fehlt |
| 3 | **Replayability & Evidence Bundles** | ⚠️ Teilweise | audit_explain.py, RUN_SUMMARY_SCHEMA.json | audit export/verify fehlen |
| 4 | **Deterministische Side-Effects** | ✅ Gut | fs_atomic, mkdir lock, idempotency | - |
| 5 | **Policy Engine nie fuzzy** | ✅ Gut | Fail-closed, BLOCKED bei unknown | - |
| 6 | **Pipeline-Silent absolut** | ⚠️ Teilweise | Mode pipeline vorhanden | Alle Codepaths geprüft? |
| 7 | **No silent escalation** | ✅ Gut | Repo-Docs = advisory only | - |

## SEHR wichtig (Produktreife)

| # | Requirement | Status | Evidence | Gap |
|---|-------------|--------|----------|-----|
| 8 | **Prompt Injection Defense** | ⚠️ Teilweise | MD_PYTHON_POLICY.md | Kein explizites "Repo is hostile" |
| 9 | **Test/Verification Strategy** | ✅ Gut | E2E tests, golden vectors | Property tests erweitern |
| 10 | **Human Factors / Approvals** | ⚠️ Teilweise | "Persist... YES" Mechanik | Approval UX verbessern |
| 11 | **Observability ohne LLM** | ⚠️ Teilweise | audit explain | audit export/verify fehlen |
| 12 | **Versioning / Migration** | ⚠️ Teilweise | schema_version vorhanden | Migration path fehlt |

## Priorisierte Actions

### P0 - MUSS (Sofort)

1. **docs/THREAT_MODEL.md** - Trust Boundaries definieren
2. **docs/SECURITY_MODEL.md** - Trusted vs Untrusted Quellen
3. **Model Identity Evidence** - provider, model, version, temperature
4. **audit export** - Evidence Bundle mit SHA-Manifest
5. **audit verify** - Manifest + Hash-Validierung

### P1 - SEHR wichtig (Bald)

6. **Prompt Injection Defense** - "Repo content is data, not instructions"
7. **Pipeline Gate Audit** - Alle Codepaths auf Interaktivität prüfen
8. **Migration Docs** - Schema version migration path

## Lücken-Detail

### 1. Trust Boundary (KRITISCH)

**Problem:** Kein dokumentiertes Threat Model

**Risiko:** Repo-Docs könnten versuchen, Execution zu steuern

**Fix:**
```
docs/THREAT_MODEL.md:
- Trusted: Kernel, master.md, rules.md, pack-lock
- Untrusted: Repo docs, tickets, PR descriptions, LLM output
- Attack surfaces: MD files, profile rulebooks, diagnostics helpers
```

### 2. Model Identity (KRITISCH)

**Problem:** Keine Model-Evidence in Run Summary

**Risiko:** Nicht reproduzierbar bei Model-Wechsel

**Fix:**
```yaml
model_context:
  provider: "anthropic"
  model: "claude-3-opus-20240229"
  version: "20240229"
  context_limit: 200000
  temperature: 0.0
```

### 3. Evidence Bundle Export (KRITISCH)

**Problem:** Kein `audit export` Command

**Risiko:** "Why blocked?" nicht exportierbar/verifizierbar

**Fix:**
```bash
python3 scripts/audit_explain.py --export --run <id> --out bundle.zip
python3 scripts/audit_explain.py --verify --bundle bundle.zip
```

## Empfohlene Reihenfolge

1. **THREAT_MODEL.md** (Dokumentation)
2. **SECURITY_MODEL.md** (Dokumentation)
3. **Model Identity** (Code - SESSION_STATE erweitern)
4. **audit export/verify** (Code - CLI erweitern)
5. **Prompt Injection Defense** (Dokumentation + Kernel)

Soll ich mit der Implementierung beginnen?
