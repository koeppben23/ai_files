# Phase Core Map

Each phase lists Inputs, Outputs, Gates, Do/Don't, and Evidence requirements.

## Phase 1.1 - Bootstrap
Inputs: binding evidence, tool availability, repo identity evidence (if available)
Outputs: Preflight snapshot, session pointer, workspace artifacts
Gates: none (bootstrap is pre-gate)
Do: emit preflight, write binding/session state
Don't: require repo-local governance, assume tools
Evidence: tool probes, binding evidence

## Phase 2 - Repository Discovery
Inputs: repo identity, working tree access
Outputs: repo cache, repo map digest, workspace memory
Gates: none
Do: build repo context deterministically
Don't: infer build toolchain from profile alone
Evidence: repo signals, git metadata

## Phase 4 - Plan Creation
Inputs: ticket goal, repo context, active profile
Outputs: plan, mini-ADR, test strategy, change matrix (schema: governance.phase4.plan.v1)
Gates: none (planning-only)
Do: classify feature complexity, produce plan
Don't: emit code or diffs before P5+ approvals
Evidence: references to repo artifacts

## Phase 5 - Architecture Review
Inputs: plan + evidence
Outputs: gate status, issues/suggestions/questions (schema: governance.phase5.gates.v1)
Gates: P5-Architecture, P5.3-TestQuality, P5.4-BusinessRules (if applicable), P5.6-RollbackSafety
Do: review, block on missing evidence
Don't: auto-approve without gate evidence
Evidence: plan artifacts, test strategy, business rules

## Phase 6 - Implementation QA
Inputs: approved plan + gates
Outputs: ready-for-pr or fix-required (schema: governance.phase6.qa.v1)
Gates: P6-ImplementationQA
Do: verify build/test if toolchain available
Don't: claim build/test success without evidence
Evidence: BuildEvidence, tool outputs

## Compact Mode (Presentation)
Outputs may be summarized using schema: governance.compact_mode.v1
