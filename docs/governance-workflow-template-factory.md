# Governance Workflow Template Factory

This runbook standardizes GitHub Actions workflow templates the same way rulebooks are standardized: one catalog, deterministic validation, and scaffolded creation from known archetypes.

## Canonical files

- Catalog: `templates/github-actions/template_catalog.json`
- Factory contract: `diagnostics/GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json`
- Factory script: `scripts/workflow_template_factory.py`

## Validate catalog consistency

```bash
python3 scripts/workflow_template_factory.py
```

This check is fail-closed and enforced through `scripts/governance_lint.py`.

Validation guarantees:

- every `templates/github-actions/governance-*.yml` file is listed once in the catalog
- every catalog entry points to an existing workflow file
- `template_key` and file name stay deterministic (`templates/github-actions/<template_key>.yml`)
- only approved archetypes are allowed

## Scaffold a new workflow template

```bash
python3 scripts/workflow_template_factory.py scaffold \
  --template-key governance-example-gate \
  --archetype pr_gate_shadow_live_verify \
  --title "Governance Example Gate" \
  --purpose "Example shadow-to-review governance gate"
```

Scaffold behavior:

- creates `templates/github-actions/governance-example-gate.yml`
- appends a sorted entry to `templates/github-actions/template_catalog.json`
- starts from an archetype skeleton so new workflows begin with the same governance baseline

## Supported archetypes

- `pr_gate_shadow_live_verify`
- `pipeline_roles_hardened`
- `ruleset_release`
- `golden_output_stability`
- `golden_baseline_update`
