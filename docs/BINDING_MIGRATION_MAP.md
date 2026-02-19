# Binding → Category Migration Map

## KERNEL-ENFORCED (Leitplanken)

| Line | Section | Reason |
|------|---------|--------|
| 112 | Path Expression Hygiene | Degenerate-path validation, BLOCK on invalid |
| 204 | Repo Identity Evidence Policy | Preflight, command inventory, evidence validation |
| 782 | Rulebook Load Evidence | Must not mark loaded without evidence |
| 905 | Operator Reload Contract | Reload triggers, kernel-managed |
| 1022 | BLOCKED — Recovery Playbook | Recovery logic, reason codes |
| 1258 | Session Start Mode Banner | Cold/Warm start evidence-based decision |
| 1545 | Order of precedence | Precedence in file operations |
| 1552 | Cross-platform config root resolution | Path resolution |
| 1556 | Expected file location | File location validation |
| 1608 | Output requirements (Load Repo Cache) | Persistence triggers |
| 1631 | Cross-platform config root resolution | Path resolution |
| 1634 | Expected file location | File location validation |
| 1641 | Read behavior | Read logic |
| 1672 | Cross-platform config root resolution | Path resolution |
| 1675 | Expected file location | File location validation |
| 1678 | Read behavior | Read logic |
| 1684 | Validation | Schema validation |
| 1711 | Fast Path eligibility | Eligibility check |
| 1730 | Application | Application logic |
| 1775 | Build Codebase Context Record | Evidence-backed record building |
| 1800 | Rules (Codebase Context) | Rules for context |
| 1807 | Resolve Build Toolchain | Toolchain detection |
| 1837 | Rules (Build Toolchain) | Rules for toolchain |
| 2001 | Cross-platform config root resolution | Path resolution |
| 2004 | Target folder and file | File location |
| 2007 | Update behavior | Persistence logic |
| 2011 | Cache content | Content requirements |
| 2024 | Output requirements (Repo Cache) | Output requirements |
| 2046 | Cross-platform config root resolution | Path resolution |
| 2049 | Target folder and file | File location |
| 2056 | Update behavior | Persistence logic |
| 2060 | Output requirements (RepoMapDigest) | Output requirements |
| 2071 | RepoMapDigest section format | Format requirements |
| 2093 | Cross-platform config root resolution | Path resolution |
| 2096 | Target folder and file | File location |
| 2108 | Update behavior | Persistence logic |
| 2112 | Minimum required content | Content requirements |
| 2157 | Cross-platform config root resolution | Path resolution |
| 2160 | Expected file location | File location |
| 2168 | Read behavior | Read logic |
| 2241 | Cross-platform config root resolution | Path resolution |
| 2244 | Target folder and file | File location |
| 2252 | Update behavior | Persistence logic |
| 2257 | Output requirements (Decision Pack) | Output requirements |
| 2324 | Cross-platform config root resolution | Path resolution |
| 2327 | Expected file location | File location |
| 2335 | Read behavior | Read logic |
| 2448 | Cross-platform config root resolution | Path resolution |
| 2452 | Target folder and file | File location |
| 2460 | Output requirements (Business Rules) | Output requirements |
| 2482 | Update behavior | Persistence logic |
| 2688 | Phase 3B-2 Execution Rules | Gate execution rules |
| 2818 | Planning depth implications | Planning rules |
| 3295 | Eligibility | Eligibility check |
| 3300 | Write behavior | Write logic |
| 3789 | CHANGE MATRIX | Matrix requirements |

## POLICY (Definition)

| Line | Section | Reason |
|------|---------|--------|
| 768 | Conflict Resolution Policy | Defines WHAT: most restrictive wins |
| 850 | Rendering note | Policy for rendering |
| 976 | Clarification Format for Ambiguity | Format definition |
| 1004 | Confidence bands for Auto-Advance | Policy for auto-advance |
| 1269 | Architect-Only Autopilot Lifecycle | Lifecycle policy |
| 1298 | Default Decision Policies (DDP) | Default policies |

## PRESENTATION ADVISORY (Schienen)

| Line | Section | Reason |
|------|---------|--------|
| 1344 | Output Policy | Output format policy |
| 1375 | MIN Template | Template format |

## Summary

| Category | Count |
|----------|-------|
| Kernel-Enforced | 51 |
| Policy | 6 |
| Presentation Advisory | 2 |
| Unclear | 4 |
| **Total** | **63** |
