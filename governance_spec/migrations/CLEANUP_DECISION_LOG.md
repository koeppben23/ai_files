# Cleanup Decision Log

Generated: 2026-03-19

This log records explicit keep/archive/delete decisions for high-risk cleanup candidates.

## Decisions

| Path | Decision | Class | Rationale |
|------|----------|-------|-----------|
| `governance_content/docs/archived/governance-layer-separation-decisions.md` | archive | K3 (historical proof context) | Historical architecture rationale retained for audit context, not active operator policy input. |
| `governance_spec/migrations/archived/R2_Migration_Units.md` | archive | K3 (historical proof context) | Historical migration planning record retained; no active runtime/contract role. |
| `governance_spec/migrations/archived/R2_Import_Inventory.md` | archive | K3 (historical proof context) | Historical import inventory retained; active migrations use final-state proofs. |
| `governance_spec/migrations/archived/WAVE_22_MIGRATION_INVENTORY.md` | archive | K3 (historical proof context) | Historical wave inventory retained in archive boundary only. |
| `governance_content/docs/backlog/guidance-language-cleanup.md` | delete | K4 (junk) | Unclassified backlog note with no active contract/proof/runtime/user-path value. |
| `governance_spec/migrations/F100_Frozen_Compatibility_Surface.txt` | delete | K4 (redundant dump) | Raw compatibility dump superseded by active `R10_Final_State_Proof.md` + conformance gates. |
| `governance_content/README.md` | keep | K1 (user value) | Primary operator truth + bootstrap guidance surface. |
| `governance_runtime/install/install.py` | keep | K2 (system value) | Canonical installer authority for active runtime/layout behavior. |
| `governance_spec/migrations/F100_Completion_Gate.md` | keep | K3 (proof value) | Active final-state completion contract for fail-closed governance proofing. |

## Notes

- `governance/` remains present under local-root payload as frozen compatibility surface (Model B), not primary runtime authority.
- Active migration and docs boundaries are enforced by conformance tests under `tests/conformance/`.
