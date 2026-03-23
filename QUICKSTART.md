# Quickstart

Short reference for getting started. For full details see [DOCS.md](DOCS.md).

SSOT: `${SPEC_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance_runtime/kernel/*` is the canonical control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`. Phase 4 Plan Mode auto-generates plans from tickets via Desktop LLM.

## Step 1: Install (2 min)

```bash
unzip customer-install-bundle-v1.zip && cd customer-install-bundle-v1
./install/install.sh
```

**Verify:** `./install/install.sh --status`

## Step 2: Verify installation

```bash
./install/install.sh --status
./install/install.sh --smoketest
```

## Step 3: Bootstrap session (1 min)

The installer places the `opencode-governance-bootstrap` launcher in a platform-specific config directory. Add that directory to your shell PATH, then invoke the launcher by name.

```bash
export PATH="$HOME/.config/opencode/bin:$PATH"
opencode-governance-bootstrap init --profile solo --repo-root /path/to/repo
```

**Profiles:** `solo`, `team`, `regulated`

## Step 4: Open Desktop and continue

After bootstrap succeeds, open OpenCode Desktop in the same repository and run `/continue`.

If `/continue` lands in Phase 4, run `/ticket` to persist the ticket/task, then run `/plan`. Use `/review` as a read-only rail entrypoint for review-depth feedback. At Phase 6 Evidence Presentation Gate, run `/review-decision <approve|changes_requested|reject>` for the final decision.

For rail details and lifecycle behavior, see README-OPENCODE.md.

## Key tests

| Test | Description |
|------|-------------|
| `tests/test_governance_flow_truth.py` | E2E workflow (Ticket → Plan → Review → Implement) |
| `tests/test_phase_transition_audit.py` | Phase transitions and audit logic |
| `tests/test_review_decision_persist_entrypoint.py` | Review decision validation |
| `tests/test_state_invariants.py` | State invariants (Phase 6, Gates) |
| `tests/test_session_reader.py` | Session snapshot and materialization |

```bash
# Run all tests
python3 -m pytest tests/ -q

# Run specific test
python3 -m pytest tests/test_governance_flow_truth.py -v
```

## Output Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | Rerun the installer from the bundle |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

## Further reading

- [README.md](README.md) - Full documentation
- [ARCHITECTURE_CANONICAL_STATE.md](governance_runtime/ARCHITECTURE_CANONICAL_STATE.md) - State model
- [OPERATING_RULES.md](governance_runtime/OPERATING_RULES.md) - Operating rules
