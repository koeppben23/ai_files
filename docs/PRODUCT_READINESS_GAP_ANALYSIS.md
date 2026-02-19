# Product Readiness Gap Analysis

## Current State

| Aspect | Status | Gap |
|--------|--------|-----|
| **Kernel Engine** | ✅ Complete | Deterministic enforcement, gates, evidence |
| **Policy System** | ✅ Complete | master.md, rules.md, profiles |
| **Terminology** | ✅ Complete | Kernel-Enforced / Policy / Presentation Advisory |
| **Audit Artifacts** | ⚠️ Internal only | JSON files exist, not exportable/queryable |
| **CI Integration** | ✅ GitHub Actions | Workflows exist |
| **Developer Experience** | ⚠️ Technical | Missing: quickstart, clear errors, debug CLI |
| **Product Positioning** | ❌ Missing | No clear wedge, no differentiation story |
| **Metrics/Monitoring** | ❌ Missing | No measurable outcomes |
| **Security Docs** | ⚠️ Partial | STABILITY_SLA.md exists, no threat model doc |
| **Model Independence** | ⚠️ Implicit | No explicit "BYO model" positioning |

## Critical Gaps for Product

### 1. WEDGE - Clear Problem Statement (MISSING)

**Current:** "AI Governance Engine" (technical description)
**Needed:** "Deterministic LLM SDLC Orchestrator" (value proposition)

**Wedge Use Cases:**
- Regulated repos (FinTech, HealthTech, Auto, Defense)
- CI-only orgs with mandatory policy gates
- Security-sensitive teams (no silent escalation)

### 2. Evidence Export/Query (MISSING)

**Current:** 
- SESSION_STATE.json (internal)
- governance_lint_report.json (internal)
- Audit reports in workspaces/

**Needed:**
- Unified Audit Log Format (JSONL events)
- CLI: `governance audit why --run <run_id>`
- CLI: `governance audit evidence --run <run_id>`
- Replay: `governance replay --run <run_id>`

### 3. Developer Experience (PARTIAL)

**Current:**
- Install: `python install.py`
- Run: `/start` in LLM
- Errors: Reason codes in output

**Needed:**
- Quickstart: `< 5 minutes to first run`
- Error messages: `reason_code` + `how to fix` + `copy-paste command`
- Debug CLI: `governance debug evidence-bundle --run <run_id>`
- Interactive mode for local dev

### 4. Integration Hooks (PARTIAL)

**Current:**
- GitHub Actions workflows
- Git hooks (commitlint, husky)

**Needed:**
- Jira/Linear ticket integration (fetch ticket context)
- CODEOWNERS awareness (who must approve)
- PR template generation (pre-filled with governance evidence)

### 5. Metrics/Dashboard (MISSING)

**Current:** None

**Needed:**
```
PR throughput: ↑/↓ trend
Flaky changes: ↓/stable
CI failures: ↓/stable
Review time: ↓/stable
Policy violations: 0 (fail-closed)
Evidence coverage: X%
```

### 6. Threat Model Documentation (PARTIAL)

**Current:**
- STABILITY_SLA.md (SLA criteria)
- SECURITY_GATE_POLICY.json (scanner config)

**Needed:**
- docs/THREAT_MODEL.md
- Trust boundaries diagram
- Attack surface: repo docs hostile
- Security guarantees: deterministic path binding, no silent escalation

### 7. Model Independence (IMPLICIT)

**Current:** Works with any LLM (architecture-agnostic)

**Needed:**
- Explicit positioning: "Bring Your Own Model"
- Provider abstraction layer documented
- Example: Same governance for Claude, GPT-4, local models

## Product Positioning Framework

### Tagline
**"Deterministic Governance for LLM-Assisted Development"**

### Value Props
1. **Deterministic**: Kernel enforces, not prompts
2. **Auditable**: Every decision has evidence chain
3. **Fail-Closed**: Missing evidence = BLOCKED, not "best effort"
4. **CI-First**: Silent in pipeline, verbose in user mode

### Competitive Differentiation

| Competitor | Weakness | Our Strength |
|------------|----------|--------------|
| Cursor/Copilot | No governance | Deterministic kernel |
| Aider | Prompt-based | Evidence-based |
| Devin/Devin-like | Black box | Audit trail, reason codes |
| Custom prompts | No enforcement | Fail-closed gates |

## Implementation Priority

### P0 (Blocking)
1. Audit export/query CLI
2. Quickstart guide (< 5 min)
3. Threat model documentation
4. Clear wedge positioning

### P1 (Important)
5. Metrics collection
6. Jira/Linear integration
7. PR template generation
8. Model independence docs

### P2 (Nice-to-have)
9. Dashboard UI
10. Team analytics
11. Custom profile marketplace

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Setup time | < 5 min | Time from install to first governed run |
| Error clarity | > 90% self-serve | % errors fixed without docs |
| Evidence coverage | 100% | All decisions have evidence |
| Policy violations | 0 | Fail-closed guarantee |
| Adoption friction | < 3 config steps | Config complexity |
